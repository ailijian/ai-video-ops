from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .config import Settings
from .database import connect, transaction
from .subprocess_env import pipeline_subprocess_env
from .task_service import (
    LeaseRecoveryMaintenance,
    STANDARD_BACKGROUND,
    claim_task,
    get_task,
    iso_utc,
    iter_queued_tasks,
    recover_expired_tasks,
    submit_task,
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
    created_by_user_id: int | None = None,
    queue_max: int = 20,
) -> dict[str, Any]:
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

    return submit_task(
        database_path,
        task_id_prefix=f"speaker-{speaker_id}",
        task_type="speaker_analysis",
        subject_ref=speaker_id,
        operation_identity=f"speaker_analysis:{business_id}:{speaker_id}",
        execution_lane=STANDARD_BACKGROUND,
        payload=payload,
        stage="等待开始",
        created_by_user_id=created_by_user_id,
        queue_max=queue_max,
        gpu_pending_per_user_max=1,
        include_awaiting_review=True,
    )


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
        self.worker_id = f"speaker-{os.getpid()}-{id(self):x}"
        self.maintenance = LeaseRecoveryMaintenance(
            interval_seconds=self.settings.task_heartbeat_seconds,
            name="speaker-lease-recovery",
            callback=self._recover_and_schedule,
        )

    def _reconcile_business_state(self, task_id: str) -> str | None:
        task = get_task(self.settings.database_path, task_id)
        if task is None:
            return None
        request_path = Path(str((task.get("payload") or {}).get("request_path") or ""))
        summary = request_path.parent / "speaker_onboarding_analysis_v1.json"
        return "awaiting_review" if summary.is_file() else None

    def start(self) -> None:
        if not (self.settings.speaker_analysis_worker_enabled):
            return
        self._recover_and_schedule()
        self.maintenance.start()

    def _recover_and_schedule(self) -> None:
        recover_expired_tasks(
            self.settings.database_path,
            task_types=("speaker_analysis",),
            reconciler=self._reconcile_business_state,
        )
        self.schedule_pending()

    def close(self) -> None:
        self.maintenance.close()
        self.executor.shutdown(
            wait=False,
            cancel_futures=False,
        )

    def schedule(self, task_id: str | None = None) -> None:
        self.schedule_pending()

    def schedule_pending(self) -> None:
        if not (self.settings.speaker_analysis_worker_enabled):
            return

        with self._lock:
            for task in iter_queued_tasks(
                self.settings.database_path,
                task_types=("speaker_analysis",),
            ):
                task_id = str(task["task_id"])
                if task_id in self._scheduled:
                    continue
                self._scheduled.add(task_id)
                self.executor.submit(self._run, task_id)

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
            worker_id=self.worker_id,
            lease_seconds=self.settings.task_lease_seconds,
            heartbeat_interval_seconds=self.settings.task_heartbeat_seconds,
        )

    def _run(
        self,
        task_id: str,
    ) -> None:
        try:
            if not claim_task(
                self.settings.database_path,
                task_id,
                worker_id=self.worker_id,
                lease_seconds=self.settings.task_lease_seconds,
                stage="读取出镜人资料",
                task_type="speaker_analysis",
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

            env = pipeline_subprocess_env(needs_deepseek=True)

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
