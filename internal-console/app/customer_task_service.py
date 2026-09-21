from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
)
from pathlib import Path
from typing import Any

from .config import Settings
from .database import transaction
from .subprocess_env import pipeline_subprocess_env
from .task_service import (
    LeaseRecoveryMaintenance,
    STANDARD_BACKGROUND,
    claim_task,
    get_task,
    iter_queued_tasks,
    iso_utc,
    recover_expired_tasks,
    submit_task,
    update_task,
)


def find_active_customer_task(
    database_path: Path,
    business_id: str,
) -> dict[str, Any] | None:
    from .database import connect

    connection = connect(database_path)

    try:
        rows = connection.execute(
            """
            SELECT task_id
            FROM tasks
            WHERE task_type = 'customer_analysis'
              AND subject_ref = ?
              AND status IN (
                  'queued',
                  'running',
                  'awaiting_review'
            )
            ORDER BY updated_at DESC
            """,
            (business_id,),
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        task = get_task(
            database_path,
            row["task_id"],
        )
        if task is None:
            continue
        if task["status"] == "awaiting_review" and (
            _customer_task_artifact_status(task) == "completed"
        ):
            update_task(
                database_path,
                task["task_id"],
                status="completed",
                progress=100,
                stage="客户事实审核完成",
                error_code=None,
                error_message=None,
            )
            continue
        return task

    return None


def _customer_task_artifact_status(
    task: dict[str, Any],
) -> str | None:
    request_path = Path(str((task.get("payload") or {}).get("request_path") or ""))
    root = request_path.parent
    review_path = root / "customer_fact_review_v1.json"
    if review_path.is_file():
        try:
            review = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            review = None
        if isinstance(review, dict) and review.get("status") in {
            "completed_persona_blocked",
            "completed_persona_review_required",
        }:
            return "completed"
    summary = root / "customer_onboarding_analysis_v1.json"
    return "awaiting_review" if summary.is_file() else None


def create_customer_task(
    database_path: Path,
    *,
    business_id: str,
    intake_id: str,
    request_path: str,
    customer_name: str,
    industry: str,
    created_by_user_id: int | None = None,
    queue_max: int = 20,
) -> dict[str, Any]:
    # Important:
    # raw Customer Materials are intentionally NOT
    # persisted in Console SQLite.
    payload = {
        "business_id": business_id,
        "intake_id": intake_id,
        "request_path": request_path,
        "customer_name": customer_name,
        "industry": industry,
    }

    return submit_task(
        database_path,
        task_id_prefix=f"customer-{business_id}",
        task_type="customer_analysis",
        subject_ref=business_id,
        operation_identity=f"customer_analysis:{business_id}",
        execution_lane=STANDARD_BACKGROUND,
        payload=payload,
        stage="等待开始",
        created_by_user_id=created_by_user_id,
        queue_max=queue_max,
        gpu_pending_per_user_max=1,
        include_awaiting_review=True,
    )


def mark_customer_task_reviewed(
    database_path: Path,
    business_id: str,
) -> None:
    timestamp = iso_utc()

    with transaction(database_path) as connection:
        connection.execute(
            """
            UPDATE tasks
            SET status = 'completed',
                progress = 100,
                stage = '客户事实审核完成',
                updated_at = ?
            WHERE task_type = 'customer_analysis'
              AND subject_ref = ?
              AND status = 'awaiting_review'
            """,
            (
                timestamp,
                business_id,
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
                str(value.get("code") or ("CUSTOMER_ANALYSIS_" "FAILED")),
                str(value.get("message") or ("客户信息分析没有完成。")),
            )

    return (
        "CUSTOMER_ANALYSIS_FAILED",
        "客户信息分析没有完成。",
    )


class CustomerTaskRunner:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.settings = settings

        self.executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=("customer-analysis"),
        )

        self._scheduled: set[str] = set()

        self._lock = threading.Lock()
        self.worker_id = f"customer-{os.getpid()}-{id(self):x}"
        self.maintenance = LeaseRecoveryMaintenance(
            interval_seconds=self.settings.task_heartbeat_seconds,
            name="customer-lease-recovery",
            callback=self._recover_and_schedule,
        )

    def _reconcile_business_state(self, task_id: str) -> str | None:
        task = get_task(self.settings.database_path, task_id)
        if task is None:
            return None
        return _customer_task_artifact_status(task)

    def start(self) -> None:
        if not (self.settings.customer_analysis_worker_enabled):
            return
        self._recover_and_schedule()
        self.maintenance.start()

    def _recover_and_schedule(self) -> None:
        recover_expired_tasks(
            self.settings.database_path,
            task_types=("customer_analysis",),
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
        if not (self.settings.customer_analysis_worker_enabled):
            return

        with self._lock:
            for task in iter_queued_tasks(
                self.settings.database_path,
                task_types=("customer_analysis",),
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

        checkpoints = (
            (
                "customer_intake_v1.json",
                20,
                "保存客户原始资料",
            ),
            (
                ("customer_intake_" "privacy_projection_v1.json"),
                35,
                "隐私检查",
            ),
            (
                ("persona_fact_" "candidates_v1.json"),
                68,
                "提取事实候选",
            ),
            (
                "speaker_discovery_candidates_v1.json",
                82,
                "识别可能的出镜人",
            ),
            (
                ("persona_onboarding_" "readiness_v1.json"),
                90,
                "评估信息完整度",
            ),
            (
                ("customer_onboarding_" "analysis_v1.json"),
                99,
                "生成审核结果",
            ),
        )

        progress = 8
        stage = "分析客户资料"

        for (
            filename,
            value,
            label,
        ) in checkpoints:
            if (root / filename).is_file():
                progress = value
                stage = label

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
                stage="读取客户资料",
                task_type="customer_analysis",
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
                    error_code=("CUSTOMER_REQUEST_" "MISSING"),
                    error_message=("客户分析请求不存在。"),
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
                    / ("customer_onboarding_" "analysis_v1.py")
                ),
                "--request",
                str(request_path.resolve()),
                "--pipeline-root",
                str(self.settings.pipeline_root),
            ]

            child_env = pipeline_subprocess_env(needs_deepseek=True)

            process = subprocess.Popen(
                command,
                cwd=(self.settings.repo_root),
                stdin=(subprocess.DEVNULL),
                stdout=(subprocess.PIPE),
                stderr=(subprocess.PIPE),
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
            )

            while process.poll() is None:
                self._sync_progress(
                    task_id,
                    request_path,
                )

                time.sleep(0.5)

            stdout, _ = process.communicate()

            self._sync_progress(
                task_id,
                request_path,
            )

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

            artifact_status = _customer_task_artifact_status(task)
            update_task(
                self.settings.database_path,
                task_id,
                status=(
                    "completed"
                    if artifact_status == "completed"
                    else "awaiting_review"
                ),
                progress=100,
                stage=(
                    "客户事实审核完成"
                    if artifact_status == "completed"
                    else "等待客户事实审核"
                ),
                error_code=None,
                error_message=None,
            )

        except Exception:
            # Never persist raw child exception text because
            # Customer Materials may appear inside an exception.
            update_task(
                self.settings.database_path,
                task_id,
                status="failed",
                stage="分析失败",
                error_code=("CUSTOMER_ANALYSIS_" "WORKER_FAILED"),
                error_message=("客户信息分析没有完成。"),
            )

        finally:
            with self._lock:
                self._scheduled.discard(task_id)
