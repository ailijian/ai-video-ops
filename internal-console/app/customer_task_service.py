from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from concurrent.futures import (
    ThreadPoolExecutor,
)
from pathlib import Path
from typing import Any

from .config import Settings
from .database import transaction
from .task_service import (
    get_task,
    iso_utc,
    update_task,
)


def find_active_customer_task(
    database_path: Path,
    business_id: str,
) -> dict[str, Any] | None:
    from .database import connect

    connection = connect(database_path)

    try:
        row = connection.execute(
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
            LIMIT 1
            """,
            (business_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return get_task(
        database_path,
        row["task_id"],
    )


def create_customer_task(
    database_path: Path,
    *,
    business_id: str,
    intake_id: str,
    request_path: str,
    customer_name: str,
    industry: str,
) -> dict[str, Any]:
    existing = find_active_customer_task(
        database_path,
        business_id,
    )

    if existing is not None:
        return existing

    task_id = f"customer-{business_id}-" f"{uuid.uuid4().hex[:12]}"

    timestamp = iso_utc()

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
                'customer_analysis',
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
                business_id,
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


def _claim_customer_task(
    database_path: Path,
    task_id: str,
) -> bool:
    with transaction(database_path) as connection:
        result = connection.execute(
            """
            UPDATE tasks
            SET status = 'running',
                stage = '读取客户资料',
                updated_at = ?
            WHERE task_id = ?
              AND task_type = 'customer_analysis'
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

    def start(self) -> None:
        if not (self.settings.customer_analysis_worker_enabled):
            return

        with transaction(self.settings.database_path) as connection:
            connection.execute(
                """
                UPDATE tasks
                SET status = 'queued',
                    stage = '恢复任务',
                    updated_at = ?
                WHERE task_type = 'customer_analysis'
                  AND status = 'running'
                """,
                (iso_utc(),),
            )

        from .task_service import (
            list_tasks,
        )

        for task in list_tasks(
            self.settings.database_path,
            limit=100,
        ):
            if task["task_type"] == "customer_analysis" and task["status"] == "queued":
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
        if not (self.settings.customer_analysis_worker_enabled):
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
                75,
                "提取事实候选",
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
        )

    def _run(
        self,
        task_id: str,
    ) -> None:
        try:
            if not _claim_customer_task(
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

            child_env = os.environ.copy()

            child_env["PYTHONIOENCODING"] = "utf-8"

            child_env["PYTHONUTF8"] = "1"

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

            update_task(
                self.settings.database_path,
                task_id,
                status="awaiting_review",
                progress=100,
                stage="等待客户事实审核",
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
