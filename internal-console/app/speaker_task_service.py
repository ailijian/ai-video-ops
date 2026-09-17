from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .config import Settings
from .database import connect, transaction
from .task_service import (
    get_task,
    iso_utc,
    list_tasks,
    update_task,
)


def find_active_speaker_task(
    database_path: Path,
    speaker_id: str,
) -> dict[str, Any] | None:
    connection = connect(database_path)

    try:
        row = connection.execute(
            """
            SELECT task_id
            FROM tasks
            WHERE task_type = 'speaker_analysis'
              AND subject_ref = ?
              AND status IN (
                  'queued',
                  'running',
                  'awaiting_review'
              )
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (speaker_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return get_task(
        database_path,
        row["task_id"],
    )


def create_speaker_task(
    database_path: Path,
    *,
    business_id: str,
    speaker_id: str,
    intake_id: str,
    request_path: str,
    speaker_name: str,
    public_role: str,
) -> dict[str, Any]:
    existing = find_active_speaker_task(
        database_path,
        speaker_id,
    )

    if existing is not None:
        return existing

    task_id = f"speaker-{speaker_id}-" f"{uuid.uuid4().hex[:12]}"

    timestamp = iso_utc()

    # Raw Speaker Materials are canonical files,
    # never duplicated into Console SQLite.
    payload = {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "intake_id": intake_id,
        "request_path": request_path,
        "speaker_name": speaker_name,
        "public_role": public_role,
    }

    with transaction(database_path) as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                task_id,
                task_type,
                subject_ref,
                status,
                progress,
                stage,
                payload_json,
                created_at,
                updated_at
            )
            VALUES (
                ?,
                'speaker_analysis',
                ?,
                'queued',
                0,
                '等待开始',
                ?,
                ?,
                ?
            )
            """,
            (
                task_id,
                speaker_id,
                json.dumps(
                    payload,
                    ensure_ascii=False,
                ),
                timestamp,
                timestamp,
            ),
        )

    task = get_task(
        database_path,
        task_id,
    )

    assert task is not None

    return task


def mark_speaker_task_reviewed(
    database_path: Path,
    speaker_id: str,
) -> None:
    with transaction(database_path) as connection:
        connection.execute(
            """
            UPDATE tasks
            SET status = 'completed',
                progress = 100,
                stage = '出镜人事实审核完成',
                updated_at = ?
            WHERE task_type = 'speaker_analysis'
              AND subject_ref = ?
              AND status = 'awaiting_review'
            """,
            (
                iso_utc(),
                speaker_id,
            ),
        )


def _claim(
    database_path: Path,
    task_id: str,
) -> bool:
    with transaction(database_path) as connection:
        result = connection.execute(
            """
            UPDATE tasks
            SET status = 'running',
                stage = '读取出镜人资料',
                updated_at = ?
            WHERE task_id = ?
              AND task_type = 'speaker_analysis'
              AND status = 'queued'
            """,
            (
                iso_utc(),
                task_id,
            ),
        )

        return result.rowcount == 1


def _parse_failure(
    stdout: str,
) -> tuple[str, str]:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue

        if (
            isinstance(
                value,
                dict,
            )
            and value.get("ok") is False
        ):
            return (
                str(value.get("code") or ("SPEAKER_ANALYSIS_FAILED")),
                str(value.get("message") or "出镜人信息分析没有完成。"),
            )

    return (
        "SPEAKER_ANALYSIS_FAILED",
        "出镜人信息分析没有完成。",
    )


class SpeakerTaskRunner:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=("speaker-analysis"),
        )

        self._scheduled: set[str] = set()

        self._lock = threading.Lock()

    def start(self) -> None:
        if not (self.settings.speaker_analysis_worker_enabled):
            return

        with transaction(self.settings.database_path) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = 'queued',
                    stage = '恢复任务',
                    updated_at = ?
                WHERE task_type = 'speaker_analysis'
                  AND status = 'running'
                """,
                (iso_utc(),),
            )

        for task in list_tasks(
            self.settings.database_path,
            limit=100,
        ):
            if task["task_type"] == "speaker_analysis" and task["status"] == "queued":
                self.schedule(task["task_id"])

    def close(self) -> None:
        self.executor.shutdown(
            wait=False,
            cancel_futures=False,
        )

    def schedule(
        self,
        task_id: str,
    ) -> None:
        if not (self.settings.speaker_analysis_worker_enabled):
            return

        with self._lock:
            if task_id in self._scheduled:
                return

            self._scheduled.add(task_id)

        self.executor.submit(
            self._run,
            task_id,
        )

    def _sync_progress(
        self,
        task_id: str,
        request_path: Path,
    ) -> None:
        root = request_path.parent

        summary = root / "speaker_onboarding_analysis_v1.json"

        readiness = root / "speaker_onboarding_readiness_v1.json"

        candidates = root / "speaker_fact_candidates_v1.json"

        privacy = root / ("speaker_intake_" "privacy_projection_v1.json")

        intake = root / "speaker_intake_v1.json"

        if summary.is_file():
            progress = 99
            stage = "生成审核结果"

        elif readiness.is_file():
            progress = 90
            stage = "评估出镜人信息完整度"

        elif candidates.is_file():
            progress = 75
            stage = "事实候选提取完成"

        elif privacy.is_file():
            progress = 55
            stage = "AI 正在提取出镜人事实"

        elif intake.is_file():
            progress = 20
            stage = "保存出镜人原始资料"

        else:
            progress = 8
            stage = "读取出镜人资料"

        update_task(
            self.settings.database_path,
            task_id,
            status="running",
            progress=progress,
            stage=stage,
        )

    def _run(
        self,
        task_id: str,
    ) -> None:
        try:
            if not _claim(
                self.settings.database_path,
                task_id,
            ):
                return

            task = get_task(
                self.settings.database_path,
                task_id,
            )

            if task is None:
                return

            payload = task.get("payload") or {}

            request_path = Path(str(payload.get("request_path") or ""))

            if not request_path.is_file():
                update_task(
                    self.settings.database_path,
                    task_id,
                    status="failed",
                    stage="分析失败",
                    error_code=("SPEAKER_REQUEST_MISSING"),
                    error_message=("出镜人分析请求不存在。"),
                )

                return

            command = [
                (
                    self.settings.pipeline_python_executable
                    or self.settings.python_executable
                ),
                str(
                    self.settings.pipeline_root
                    / "scripts"
                    / ("speaker_onboarding_" "analysis_v1.py")
                ),
                "--request",
                str(request_path.resolve()),
                "--pipeline-root",
                str(self.settings.pipeline_root),
            ]

            env = os.environ.copy()

            env["PYTHONIOENCODING"] = "utf-8"

            env["PYTHONUTF8"] = "1"

            process = subprocess.Popen(
                command,
                cwd=self.settings.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            started = time.monotonic()
            timed_out = False

            while process.poll() is None:
                self._sync_progress(
                    task_id,
                    request_path,
                )

                if time.monotonic() - started > 210:
                    timed_out = True
                    process.kill()
                    break

                time.sleep(0.5)

            stdout, _ = process.communicate()

            self._sync_progress(
                task_id,
                request_path,
            )

            if timed_out:
                update_task(
                    self.settings.database_path,
                    task_id,
                    status="failed",
                    progress=55,
                    stage="分析失败",
                    error_code=("SPEAKER_ANALYSIS_TIMEOUT"),
                    error_message=("AI 出镜人事实提取超时，" "本次分析已经安全停止。"),
                )

                return

            if process.returncode != 0:
                code, message = _parse_failure(stdout)

                update_task(
                    self.settings.database_path,
                    task_id,
                    status="failed",
                    stage="分析失败",
                    error_code=code,
                    error_message=message,
                )

                return

            update_task(
                self.settings.database_path,
                task_id,
                status="awaiting_review",
                progress=100,
                stage="等待出镜人事实审核",
            )

        except Exception:
            update_task(
                self.settings.database_path,
                task_id,
                status="failed",
                stage="分析失败",
                error_code=("SPEAKER_ANALYSIS_WORKER_FAILED"),
                error_message=("出镜人信息分析没有完成。"),
            )

        finally:
            with self._lock:
                self._scheduled.discard(task_id)
