from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical_gateway import approved_case_attempt_id
from .config import Settings
from .database import connect, transaction
from .subprocess_env import pipeline_subprocess_env


GPU_HEAVY = "GPU_HEAVY"
STANDARD_BACKGROUND = "STANDARD_BACKGROUND"


class TaskSubmissionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class LeaseRecoveryMaintenance:
    """Small in-process loop that revisits leases after startup."""

    def __init__(self, *, interval_seconds: float, name: str, callback) -> None:
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.callback = callback
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=name,
            daemon=True,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._started:
            self._thread.join(timeout=min(2.0, self.interval_seconds + 0.5))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.callback()
            except Exception:
                # The next interval retries. Task state remains authoritative in
                # SQLite and no business mutation is attempted by this loop.
                continue


TASK_COLUMNS = """
    t.task_id, t.task_type, t.subject_ref, t.status, t.progress, t.stage,
    t.error_code, t.error_message, t.payload_json, t.created_at, t.updated_at,
    t.created_by_user_id, t.execution_lane, t.operation_identity,
    t.started_at, t.worker_id, t.heartbeat_at, t.lease_expires_at,
    t.attempt_count, u.phone AS created_by_phone
"""


def iso_utc(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _row_to_task(row: Any) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        payload = {}
    raw_error = row["error_message"]
    public_error = raw_error

    if row["error_code"]:
        task_type = str(row["task_type"] or "")

        lowered = str(raw_error or "").lower()

        if task_type == "customer_analysis":
            if "privacy" in lowered:
                public_error = "客户资料隐私检查没有通过，" "分析已停止。"
            else:
                public_error = "客户信息分析没有完成。"

        elif task_type == "speaker_analysis":
            if "privacy" in lowered:
                public_error = "出镜人资料隐私检查没有通过，" "分析已停止。"
            else:
                public_error = "出镜人信息分析没有完成。"

        elif task_type in {"content_generation", "excel_export"}:
            public_error = "后台操作没有完成，请按提示刷新业务状态后重试。"

        elif row["error_code"] == "SOURCE_PROVIDER_RATE_LIMITED":
            public_error = "视频解析请求较多，请稍后重新分析；也可以上传本地视频。"

        elif row["error_code"] == "SOURCE_PROVIDER_QUOTA_EXHAUSTED":
            public_error = "视频解析额度暂不可用，可以上传本地视频继续。"

        elif str(row["error_code"]).startswith(("SOURCE_PROVIDER_", "SOURCE_MEDIA_")):
            public_error = "原视频暂时无法自动获取，可以稍后重试或上传本地视频。"

        elif "no audio segments" in lowered or "audio-timeline" in lowered:
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
        "execution_lane": row["execution_lane"],
        "operation_identity": row["operation_identity"],
        "created_by": (
            {
                "user_id": row["created_by_user_id"],
                "phone": row["created_by_phone"],
            }
            if row["created_by_user_id"] is not None
            else None
        ),
        "started_at": row["started_at"],
        "worker_id": row["worker_id"],
        "heartbeat_at": row["heartbeat_at"],
        "lease_expires_at": row["lease_expires_at"],
        "attempt_count": row["attempt_count"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_tasks(database_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    connection = connect(database_path)
    try:
        rows = connection.execute(
            """
            SELECT {columns}
            FROM tasks AS t
            LEFT JOIN users AS u ON u.id = t.created_by_user_id
            ORDER BY t.updated_at DESC
            LIMIT ?
            """.format(columns=TASK_COLUMNS),
            (max(1, min(limit, 500)),),
        ).fetchall()
    finally:
        connection.close()
    return [_row_to_task(row) for row in rows]


def get_task(database_path: Path, task_id: str) -> dict[str, Any] | None:
    connection = connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT {columns}
            FROM tasks AS t
            LEFT JOIN users AS u ON u.id = t.created_by_user_id
            WHERE t.task_id = ?
            """.format(columns=TASK_COLUMNS),
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
            SELECT {columns}
            FROM tasks AS t
            LEFT JOIN users AS u ON u.id = t.created_by_user_id
            WHERE t.task_type = 'case_analysis' AND t.subject_ref = ?
              AND t.status IN ('queued', 'running', 'awaiting_review')
            ORDER BY t.updated_at DESC LIMIT 1
            """.format(columns=TASK_COLUMNS),
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
    operator_profile_hint: str,
    source_upload: dict[str, str] | None = None,
    acquisition_provider: str = "legacy_downloader",
    provider_source_url: str | None = None,
    industry: str = "待分类",
    reanalyze: bool = False,
    reason: str | None = None,
    created_by_user_id: int | None = None,
    queue_max: int = 20,
    gpu_pending_per_user_max: int = 3,
) -> dict[str, Any]:
    if operator_profile_hint not in {"mix", "news", "hybrid", "uncertain"}:
        raise ValueError("Case operator_profile_hint must be explicitly selected")
    if acquisition_provider not in {"legacy_downloader", "qiyun", "upload_only"}:
        raise ValueError("Unsupported case acquisition provider")
    payload = {
        "source_url": source_url,
        "operator_profile_hint": operator_profile_hint,
        "industry": industry,
        "reanalyze": reanalyze,
        "reason": reason,
        "acquisition_provider": acquisition_provider,
    }
    if source_upload is not None:
        payload["source_upload"] = source_upload
    if provider_source_url and source_upload is None and acquisition_provider == "qiyun":
        payload["provider_source_url"] = provider_source_url
    return submit_task(
        database_path,
        task_id_prefix=f"case-{case_id}",
        task_type="case_analysis",
        subject_ref=case_id,
        operation_identity=f"case_analysis:{case_id}",
        execution_lane=GPU_HEAVY,
        payload=payload,
        stage="等待开始",
        created_by_user_id=created_by_user_id,
        queue_max=queue_max,
        gpu_pending_per_user_max=gpu_pending_per_user_max,
        include_awaiting_review=True,
        allow_existing=(not reanalyze),
    )


def submit_task(
    database_path: Path,
    *,
    task_id_prefix: str,
    task_type: str,
    subject_ref: str,
    operation_identity: str,
    execution_lane: str,
    payload: dict[str, Any],
    stage: str,
    created_by_user_id: int | None,
    queue_max: int,
    gpu_pending_per_user_max: int,
    include_awaiting_review: bool = False,
    allow_existing: bool = True,
) -> dict[str, Any]:
    statuses = "'queued', 'running', 'awaiting_review'" if include_awaiting_review else "'queued', 'running'"
    timestamp = iso_utc()
    task_id = f"{task_id_prefix}-{uuid.uuid4().hex[:12]}"

    with transaction(database_path, immediate=True) as connection:
        existing = connection.execute(
            f"""
            SELECT task_id FROM tasks
            WHERE task_type = ? AND operation_identity = ?
              AND status IN ({statuses})
            ORDER BY created_at ASC, task_id ASC LIMIT 1
            """,
            (task_type, operation_identity),
        ).fetchone()
        if existing is not None:
            if allow_existing:
                existing_id = str(existing["task_id"])
            else:
                raise TaskSubmissionError(
                    "OPERATION_ALREADY_ACTIVE",
                    "The canonical operation already has an active task.",
                )
        else:
            upload_id = (payload.get("source_upload") or {}).get("upload_id")
            if upload_id and connection.execute(
                "SELECT 1 FROM tasks WHERE task_type = 'case_analysis' "
                "AND json_extract(payload_json, '$.source_upload.upload_id') = ? LIMIT 1", (upload_id,),
            ).fetchone():
                raise TaskSubmissionError("SOURCE_UPLOAD_ALREADY_USED", "该文件已用于一条分析任务，重新分析请重新上传。")
            active_count = connection.execute(
                "SELECT COUNT(*) AS count FROM tasks WHERE status IN ('queued', 'running')"
            ).fetchone()["count"]
            if int(active_count) >= queue_max:
                raise TaskSubmissionError("TASK_QUEUE_FULL", "The task queue is full.")

            if execution_lane == GPU_HEAVY and created_by_user_id is not None:
                gpu_count = connection.execute(
                    """
                    SELECT COUNT(*) AS count FROM tasks
                    WHERE execution_lane = 'GPU_HEAVY'
                      AND created_by_user_id = ?
                      AND status IN ('queued', 'running')
                    """,
                    (created_by_user_id,),
                ).fetchone()["count"]
                if int(gpu_count) >= gpu_pending_per_user_max:
                    raise TaskSubmissionError(
                        "GPU_PENDING_LIMIT_REACHED",
                        "The user already has the maximum number of pending GPU tasks.",
                    )

            try:
                connection.execute(
                    """
                    INSERT INTO tasks(
                        task_id, task_type, subject_ref, status, progress, stage,
                        payload_json, created_at, updated_at, created_by_user_id,
                        execution_lane, operation_identity
                    ) VALUES (?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        task_type,
                        subject_ref,
                        stage,
                        json.dumps(payload, ensure_ascii=False),
                        timestamp,
                        timestamp,
                        created_by_user_id,
                        execution_lane,
                        operation_identity,
                    ),
                )
                existing_id = task_id
            except sqlite3.IntegrityError:
                conflict = connection.execute(
                    """
                    SELECT task_id FROM tasks
                    WHERE task_type = ? AND operation_identity = ?
                      AND status IN ('queued', 'running')
                    ORDER BY created_at ASC, task_id ASC LIMIT 1
                    """,
                    (task_type, operation_identity),
                ).fetchone()
                if conflict is None or not allow_existing:
                    raise
                existing_id = str(conflict["task_id"])

    task = get_task(database_path, existing_id)
    assert task is not None
    return task


def list_queued_tasks(
    database_path: Path,
    *,
    task_types: tuple[str, ...] | None = None,
    after: tuple[str, str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    where = ["t.status = 'queued'"]
    values: list[Any] = []
    if task_types:
        placeholders = ",".join("?" for _ in task_types)
        where.append(f"t.task_type IN ({placeholders})")
        values.extend(task_types)
    if after:
        where.append("(t.created_at > ? OR (t.created_at = ? AND t.task_id > ?))")
        values.extend((after[0], after[0], after[1]))
    values.append(max(1, min(limit, 500)))
    connection = connect(database_path)
    try:
        rows = connection.execute(
            f"""
            SELECT {TASK_COLUMNS}
            FROM tasks AS t
            LEFT JOIN users AS u ON u.id = t.created_by_user_id
            WHERE {' AND '.join(where)}
            ORDER BY t.created_at ASC, t.task_id ASC
            LIMIT ?
            """,
            values,
        ).fetchall()
    finally:
        connection.close()
    return [_row_to_task(row) for row in rows]


def iter_queued_tasks(
    database_path: Path, *, task_types: tuple[str, ...] | None = None
):
    after: tuple[str, str] | None = None
    while True:
        page = list_queued_tasks(
            database_path, task_types=task_types, after=after, limit=100
        )
        if not page:
            return
        yield from page
        last = page[-1]
        after = (str(last["created_at"]), str(last["task_id"]))


def update_task(
    database_path: Path,
    task_id: str,
    *,
    status: str | None = None,
    progress: int | None = None,
    stage: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    worker_id: str | None = None,
    lease_seconds: int = 120,
    heartbeat_interval_seconds: int = 10,
) -> None:
    with transaction(database_path) as connection:
        row = connection.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if row is None:
            return
        if (row["task_type"] == "case_analysis" and row["status"] == "completed"
                and status in {"queued", "running", "awaiting_review", "failed"}):
            # Human review is terminal for this attempt. A late worker poll or
            # process exit must not reopen it after the decision is recorded.
            return
        changes: dict[str, Any] = {}
        for name, value in (
            ("status", status),
            ("progress", progress),
            ("stage", stage),
            ("error_code", error_code),
            ("error_message", error_message),
        ):
            if value is not None and row[name] != value:
                changes[name] = value

        now = datetime.now(timezone.utc)
        heartbeat_due = False
        if worker_id and (status or row["status"]) == "running":
            heartbeat = _parse_iso(row["heartbeat_at"])
            heartbeat_due = heartbeat is None or (
                now - heartbeat >= timedelta(seconds=heartbeat_interval_seconds)
            )
            if heartbeat_due:
                changes["heartbeat_at"] = iso_utc()
                changes["lease_expires_at"] = iso_utc(
                    now + timedelta(seconds=lease_seconds)
                )
            if row["worker_id"] != worker_id:
                changes["worker_id"] = worker_id
        target_status = status or row["status"]
        if target_status != "running" and row["lease_expires_at"] is not None:
            changes["lease_expires_at"] = None
        if not changes:
            return
        changes["updated_at"] = iso_utc()
        assignments = ", ".join(f"{name} = ?" for name in changes)
        values = [*changes.values(), task_id]
        connection.execute(
            f"UPDATE tasks SET {assignments} WHERE task_id = ?",
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


def mark_task_reviewed(
    database_path: Path, case_id: str, stage: str, *, attempt_id: str | None = None,
) -> None:
    if not attempt_id:
        return
    timestamp = iso_utc()
    with transaction(database_path) as connection:
        connection.execute(
            """
            UPDATE tasks
            SET status = 'completed', progress = 100, stage = ?,
                lease_expires_at = NULL, updated_at = ?
            WHERE task_type = 'case_analysis' AND subject_ref = ? AND task_id = ?
              AND status IN ('queued', 'running', 'awaiting_review')
            """,
            (stage, timestamp, case_id, attempt_id),
        )


def reconcile_approved_case_tasks(settings: Settings) -> int:
    """Close only tasks whose own attempt became an approved canonical Case."""
    connection = connect(settings.database_path)
    try:
        rows = connection.execute(
            """
            SELECT task_id, subject_ref FROM tasks
            WHERE task_type = 'case_analysis'
              AND status IN ('queued', 'running', 'awaiting_review', 'failed')
            """
        ).fetchall()
    finally:
        connection.close()
    approved_attempts: dict[str, str | None] = {}
    matched = []
    for row in rows:
        case_id = str(row["subject_ref"] or "")
        if case_id not in approved_attempts:
            approved_attempts[case_id] = approved_case_attempt_id(settings, case_id)
        if approved_attempts[case_id] == row["task_id"]:
            matched.append(str(row["task_id"]))
    if not matched:
        return 0
    updated = 0
    with transaction(settings.database_path) as connection:
        for task_id in matched:
            result = connection.execute(
                """
                UPDATE tasks
                SET status = 'completed', progress = 100, stage = '已批准入库',
                    error_code = NULL, error_message = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE task_id = ? AND task_type = 'case_analysis'
                  AND status IN ('queued', 'running', 'awaiting_review', 'failed')
                """,
                (iso_utc(), task_id),
            )
            updated += result.rowcount
    return updated


def claim_task(
    database_path: Path,
    task_id: str,
    *,
    worker_id: str,
    lease_seconds: int,
    stage: str,
    task_type: str | None = None,
) -> bool:
    now = datetime.now(timezone.utc)
    with transaction(database_path, immediate=True) as connection:
        task_type_clause = " AND task_type = ?" if task_type else ""
        values: list[Any] = [
            stage,
            iso_utc(now),
            worker_id,
            iso_utc(now),
            iso_utc(now + timedelta(seconds=lease_seconds)),
            iso_utc(now),
            task_id,
        ]
        if task_type:
            values.append(task_type)
        result = connection.execute(
            f"""
            UPDATE tasks
            SET status = 'running', stage = ?, started_at = ?, worker_id = ?,
                heartbeat_at = ?, lease_expires_at = ?, attempt_count = attempt_count + 1,
                updated_at = ?
            WHERE task_id = ? AND status = 'queued'{task_type_clause}
            """,
            values,
        )
        return result.rowcount == 1


def recover_expired_tasks(
    database_path: Path,
    *,
    task_types: tuple[str, ...],
    reconciler=None,
) -> list[str]:
    now = iso_utc()
    placeholders = ",".join("?" for _ in task_types)
    connection = connect(database_path)
    try:
        rows = connection.execute(
            f"""
            SELECT task_id FROM tasks
            WHERE task_type IN ({placeholders}) AND status = 'running'
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
            ORDER BY created_at ASC, task_id ASC
            """,
            (*task_types, now),
        ).fetchall()
    finally:
        connection.close()
    recovered: list[str] = []
    for row in rows:
        task_id = str(row["task_id"])
        projection = reconciler(task_id) if reconciler else None
        if projection in {"awaiting_review", "completed", "failed"}:
            update_task(
                database_path,
                task_id,
                status=projection,
                stage=("等待人工审核" if projection == "awaiting_review" else "已恢复业务状态"),
            )
            continue
        with transaction(database_path, immediate=True) as transaction_connection:
            result = transaction_connection.execute(
                """
                UPDATE tasks
                SET status = 'queued', stage = '恢复任务', worker_id = NULL,
                    heartbeat_at = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE task_id = ? AND status = 'running'
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                """,
                (iso_utc(), task_id, iso_utc()),
            )
            if result.rowcount == 1:
                recovered.append(task_id)
    return recovered


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
        self.worker_id = f"case-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._last_storage_maintenance = 0.0
        self.maintenance = LeaseRecoveryMaintenance(
            interval_seconds=self.settings.task_heartbeat_seconds,
            name="case-lease-recovery",
            callback=self._recover_and_schedule,
        )

    def _reconcile_business_state(self, task_id: str) -> str | None:
        task = get_task(self.settings.database_path, task_id)
        if task is None:
            return None
        case_id = str(task["subject_ref"] or "")
        if approved_case_attempt_id(self.settings, case_id) == task_id:
            return "completed"
        state_path = (
            self.settings.pipeline_root
            / "data"
            / "case_analysis_attempts"
            / case_id
            / task_id
            / "case_analysis_attempt_v1.json"
        )
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            status = str(state.get("status") or "")
            if status in {"awaiting_review", "failed"}:
                return status
            # A running exact attempt must resume from its own checkpoints even
            # when this case has an older approved canonical artifact.
            return None
        canonical = self.settings.pipeline_root / "data" / "cases" / case_id / "case_v1.json"
        return "completed" if canonical.is_file() else None

    def start(self) -> None:
        if not self.settings.case_analysis_worker_enabled:
            return
        self._recover_and_schedule()
        self.maintenance.start()

    def _recover_and_schedule(self) -> None:
        reconcile_approved_case_tasks(self.settings)
        recover_expired_tasks(
            self.settings.database_path,
            task_types=("case_analysis",),
            reconciler=self._reconcile_business_state,
        )
        self._run_storage_maintenance_if_due()
        self.schedule_pending()

    def _run_storage_maintenance_if_due(self) -> None:
        current = time.monotonic()
        if (
            self._last_storage_maintenance
            and current - self._last_storage_maintenance
            < self.settings.storage_maintenance_interval_seconds
        ):
            return
        self._last_storage_maintenance = current
        try:
            from .case_uploads import cleanup_unused_uploads
            cleanup_unused_uploads(self.settings)
            subprocess.run(
                [
                    self.settings.pipeline_python_executable
                    or self.settings.python_executable,
                    str(
                        self.settings.pipeline_root
                        / "scripts"
                        / "storage_retention_v1.py"
                    ),
                    "--pipeline-root",
                    str(self.settings.pipeline_root),
                    "--downloader-root",
                    str(self.settings.repo_root / "douyin-downloader"),
                    "--maintenance",
                ],
                cwd=self.settings.repo_root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=pipeline_subprocess_env(needs_deepseek=False),
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            # Storage cleanup is an operational lifecycle. The next hourly
            # pass retries without changing task or business authority state.
            return

    def close(self) -> None:
        self.maintenance.close()
        self.executor.shutdown(wait=False, cancel_futures=False)

    def schedule(self, task_id: str | None = None) -> None:
        self.schedule_pending()

    def schedule_pending(self) -> None:
        if not self.settings.case_analysis_worker_enabled:
            return
        with self._lock:
            for task in iter_queued_tasks(
                self.settings.database_path, task_types=("case_analysis",)
            ):
                task_id = str(task["task_id"])
                if task_id in self._scheduled:
                    continue
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
            worker_id=self.worker_id,
            lease_seconds=self.settings.task_lease_seconds,
            heartbeat_interval_seconds=self.settings.task_heartbeat_seconds,
        )

    def _run(self, task_id: str) -> None:
        try:
            if not claim_task(
                self.settings.database_path,
                task_id,
                worker_id=self.worker_id,
                lease_seconds=self.settings.task_lease_seconds,
                stage="获取视频",
                task_type="case_analysis",
            ):
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
                "--industry",
                str(payload.get("industry") or "待分类"),
                "--acquisition-provider",
                str(payload.get("acquisition_provider") or "legacy_downloader"),
            ]
            if payload.get("operator_profile_hint") in {"mix", "news", "hybrid", "uncertain"}:
                command.extend(["--operator-profile-hint", str(payload["operator_profile_hint"])])
            elif payload.get("profile") in {"mix", "news"}:
                # Pre-closure queued tasks already durably recorded an explicit
                # legacy profile. Resume that lineage without inventing a hint.
                command.extend(["--profile", str(payload["profile"])])
            else:
                raise ValueError("Case task has no recorded profile input")
            if payload.get("reanalyze"):
                command.append("--reanalyze")
            if payload.get("source_upload"):
                command.extend([
                    "--source-upload-id", payload["source_upload"]["upload_id"],
                    "--source-upload-receipt-sha256", payload["source_upload"]["receipt_sha256"],
                ])
            if payload.get("provider_source_url"):
                command.extend(["--provider-source-url", str(payload["provider_source_url"])])
            child_env = pipeline_subprocess_env(
                needs_deepseek=True,
                needs_qiyun=(payload.get("acquisition_provider") == "qiyun" and not payload.get("source_upload")),
            )
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
