from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .database import connect, transaction


def iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_to_task(row: Any) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        payload = {}
    raw_error = row["error_message"]
    public_error = raw_error
    if row["error_code"]:
        lowered = str(raw_error or "").lower()
        if "no audio segments" in lowered or "audio-timeline" in lowered:
            public_error = "没有识别到可用于结构分析的口播内容。"
        elif "analyze-visual" in lowered or "visual" in lowered:
            public_error = "画面分析没有完成。"
        elif "privacy" in lowered:
            public_error = "隐私检查没有通过，分析已停止。"
        else:
            public_error = "案例分析没有完成。"
    return {
        "task_id": row["task_id"],
        "task_type": row["task_type"],
        "subject_ref": row["subject_ref"],
        "status": row["status"],
        "progress": row["progress"],
        "stage": row["stage"],
        "error_code": row["error_code"],
        "error_message": public_error,
        "payload": payload,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_tasks(database_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    connection = connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT task_id, task_type, subject_ref, status, progress, stage,
                   error_code, error_message, payload_json, created_at, updated_at
            FROM tasks
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
    finally:
        connection.close()
    return [_row_to_task(row) for row in rows]


def get_task(database_path: Path, task_id: str) -> dict[str, Any] | None:
    connection = connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT task_id, task_type, subject_ref, status, progress, stage,
                   error_code, error_message, payload_json, created_at, updated_at
            FROM tasks WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
    finally:
        connection.close()
    return _row_to_task(row) if row is not None else None


def find_active_case_task(database_path: Path, case_id: str) -> dict[str, Any] | None:
    connection = connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT task_id, task_type, subject_ref, status, progress, stage,
                   error_code, error_message, payload_json, created_at, updated_at
            FROM tasks
            WHERE task_type = 'case_analysis' AND subject_ref = ?
              AND status IN ('queued', 'running', 'awaiting_review')
            ORDER BY updated_at DESC LIMIT 1
            """,
            (case_id,),
        ).fetchone()
    finally:
        connection.close()
    return _row_to_task(row) if row is not None else None


def create_case_task(
    database_path: Path,
    *,
    source_url: str,
    case_id: str,
    profile: str = "mix",
    industry: str = "待分类",
    reanalyze: bool = False,
    reason: str | None = None,
) -> dict[str, Any]:
    existing = find_active_case_task(database_path, case_id)
    if existing is not None and (
        not reanalyze or existing.get("payload", {}).get("reanalyze") is True
    ):
        return existing
    task_id = f"case-{case_id}-{uuid.uuid4().hex[:12]}"
    timestamp = iso_utc()
    payload = {
        "source_url": source_url,
        "profile": profile,
        "industry": industry,
        "reanalyze": reanalyze,
        "reason": reason,
    }
    with transaction(database_path) as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                task_id, task_type, subject_ref, status, progress, stage,
                payload_json, created_at, updated_at
            ) VALUES (?, 'case_analysis', ?, 'queued', 0, '等待开始', ?, ?, ?)
            """,
            (
                task_id,
                case_id,
                json.dumps(payload, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    task = get_task(database_path, task_id)
    assert task is not None
    return task


def update_task(
    database_path: Path,
    task_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    assignments = ["updated_at = ?"]
    values: list[Any] = [iso_utc()]
    for name, value in (
        ("status", status),
        ("progress", progress),
        ("stage", stage),
        ("error_code", error_code),
        ("error_message", error_message),
    ):
        if value is not None:
            assignments.append(f"{name} = ?")
            values.append(value)
    values.append(task_id)
    with transaction(database_path) as connection:
        connection.execute(
            f"UPDATE tasks SET {', '.join(assignments)} WHERE task_id = ?",
            values,
        )


def patch_task_payload(
    database_path: Path,
    task_id: str,
    patch: dict[str, Any],
) -> None:
    if not patch:
        return

    with transaction(database_path) as connection:
        row = connection.execute(
            """
            SELECT payload_json
            FROM tasks
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()

        if row is None:
            return

        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        payload.update(patch)

        connection.execute(
            """
            UPDATE tasks
            SET payload_json = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (
                json.dumps(payload, ensure_ascii=False),
                iso_utc(),
                task_id,
            ),
        )


def mark_task_reviewed(database_path: Path, case_id: str, stage: str) -> None:
    timestamp = iso_utc()
    with transaction(database_path) as connection:
        connection.execute(
            """
            UPDATE tasks
            SET status = 'completed', progress = 100, stage = ?, updated_at = ?
            WHERE task_type = 'case_analysis' AND subject_ref = ?
              AND status = 'awaiting_review'
            """,
            (stage, timestamp, case_id),
        )


def _claim_task(database_path: Path, task_id: str) -> bool:
    with transaction(database_path) as connection:
        result = connection.execute(
            """
            UPDATE tasks SET status = 'running', stage = '获取视频', updated_at = ?
            WHERE task_id = ? AND status = 'queued'
            """,
            (iso_utc(), task_id),
        )
        return result.rowcount == 1


STAGE_LABELS = {
    "acquire": "获取视频",
    "transcribe": "提取语音",
    "visual": "分析画面",
    "structure": "理解内容结构",
    "review": "生成审核结果",
    "awaiting_review": "等待人工审核",
}


class CaseTaskRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="case-analysis"
        )
        self._scheduled: set[str] = set()
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.settings.case_analysis_worker_enabled:
            return
        with transaction(self.settings.database_path) as connection:
            connection.execute(
                """
                UPDATE tasks SET status = 'queued', stage = '恢复任务', updated_at = ?
                WHERE task_type = 'case_analysis' AND status = 'running'
                """,
                (iso_utc(),),
            )
        for task in list_tasks(self.settings.database_path, limit=100):
            if task["task_type"] == "case_analysis" and task["status"] == "queued":
                self.schedule(task["task_id"])

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=False)

    def schedule(self, task_id: str) -> None:
        if not self.settings.case_analysis_worker_enabled:
            return
        with self._lock:
            if task_id in self._scheduled:
                return
            self._scheduled.add(task_id)
        self.executor.submit(self._run, task_id)

    def _sync_progress(self, task_id: str, state_path: Path) -> None:
        if not state_path.is_file():
            return
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        stage = STAGE_LABELS.get(str(state.get("current_stage") or ""), "正在分析")
        update_task(
            self.settings.database_path,
            task_id,
            status="running",
            progress=max(0, min(99, int(state.get("progress") or 0))),
            stage=stage,
        )

    def _run(self, task_id: str) -> None:
        try:
            if not _claim_task(self.settings.database_path, task_id):
                return
            task = get_task(self.settings.database_path, task_id)
            if task is None:
                return
            payload = task["payload"]
            case_id = str(task["subject_ref"])
            state_path = (
                self.settings.pipeline_root
                / "data"
                / "case_analysis_attempts"
                / case_id
                / task_id
                / "case_analysis_attempt_v1.json"
            )
            command = [
                self.settings.pipeline_python_executable
                or self.settings.python_executable,
                str(self.settings.pipeline_root / "scripts" / "case_analysis_v1.py"),
                "--source-url",
                str(payload["source_url"]),
                "--attempt-id",
                task_id,
                "--profile",
                str(payload.get("profile") or "mix"),
                "--industry",
                str(payload.get("industry") or "待分类"),
            ]
            if payload.get("reanalyze"):
                command.append("--reanalyze")
            child_env = os.environ.copy()
            child_env["PYTHONIOENCODING"] = "utf-8"
            child_env["PYTHONUTF8"] = "1"
            process = subprocess.Popen(
                command,
                cwd=self.settings.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
            )
            while process.poll() is None:
                self._sync_progress(task_id, state_path)
                time.sleep(0.75)
            stdout, stderr = process.communicate()
            self._sync_progress(task_id, state_path)
            if process.returncode != 0:
                code = "CASE_ANALYSIS_FAILED"
                message = "案例分析失败，请检查来源后重试。"
                if state_path.is_file():
                    try:
                        state = json.loads(state_path.read_text(encoding="utf-8"))

                        code = str((state.get("error") or {}).get("code") or code)
                        message = str(
                            (state.get("error") or {}).get("message") or message
                        )

                        duplicate = state.get("duplicate")
                        if isinstance(duplicate, dict):
                            patch_task_payload(
                                self.settings.database_path,
                                task_id,
                                {
                                    "duplicate": duplicate,
                                },
                            )

                    except (OSError, json.JSONDecodeError):
                        pass

                elif stderr.strip() or stdout.strip():
                    message = (stderr.strip() or stdout.strip()).splitlines()[-1]
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
                stage="等待人工审核",
            )
        except Exception as exc:
            update_task(
                self.settings.database_path,
                task_id,
                status="failed",
                stage="分析失败",
                error_code="CASE_ANALYSIS_WORKER_FAILED",
                error_message=str(exc),
            )
        finally:
            with self._lock:
                self._scheduled.discard(task_id)
