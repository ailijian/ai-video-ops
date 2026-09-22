from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .content_delivery_gateway import (
    export_mix_excel,
    generate_scripts,
    get_content_delivery_state,
    resolve_content_plan,
)
from .news_delivery_gateway import (
    export_news_excel,
    get_news_delivery_state,
    resolve_news_plan,
)
from .novel_news_gateway import export_novel_news, generate_novel_news, novel_news_state
from .novel_news_rollout import require_novel_news_task
from .operation_lock import authority_operation_lock
from .task_service import (
    LeaseRecoveryMaintenance,
    STANDARD_BACKGROUND,
    claim_task,
    get_task,
    iter_queued_tasks,
    recover_expired_tasks,
    submit_task,
    update_task,
)


BACKGROUND_OPERATIONS: dict[str, tuple[str, str]] = {
    "content_plan": ("content_generation", "生成 Content Plan"),
    "script_generation": ("content_generation", "生成脚本"),
    "mix_export": ("excel_export", "导出 Mix Excel 并闭合 Ledger"),
    "news_plan": ("content_generation", "生成 News Plan"),
    "news_export": ("excel_export", "导出 News Excel"),
    "novel_news_generate": ("content_generation", "生成新闻体新内容"),
    "novel_news_export": ("excel_export", "导出新闻体新内容"),
}


def create_background_task(
    settings: Settings,
    *,
    operation: str,
    request_id: str,
    created_by_user_id: int,
) -> dict[str, Any]:
    if operation not in BACKGROUND_OPERATIONS:
        raise ValueError("unsupported background operation")
    if operation in {"novel_news_generate", "novel_news_export"}:
        require_novel_news_task(settings, created_by_user_id)
    if operation == "content_plan":
        state = get_content_delivery_state(settings, request_id)
        if state.get("source_coverage_supported") is not True:
            feasibility = state.get("production_feasibility") or {}
            raise CanonicalOperationError(
                "CONTENT_PLAN_SOURCE_COVERAGE_UNSUPPORTED",
                str(
                    feasibility.get("humanized_reason")
                    or state.get("coverage_reason")
                    or "当前创作结构暂时不能支持这批内容。"
                ),
                "请查看原因；可以结束本次创作，或在有真实信息时选择补充资料。",
                details={
                    "production_feasibility": feasibility,
                    "task_created": False,
                },
            )
    if operation in {"novel_news_generate", "novel_news_export"}:
        state = novel_news_state(settings, request_id)
        expected = "generation" if operation == "novel_news_generate" else "export"
        if state.get("stage") != expected:
            raise CanonicalOperationError(
                "NEWS_NOVEL_STAGE_INVALID", "当前新闻体阶段不允许此操作。",
                "请刷新创作进度，不会建立重复后台任务。",
            )
    task_type, stage = BACKGROUND_OPERATIONS[operation]
    return submit_task(
        settings.database_path,
        task_id_prefix=f"{operation}-{request_id}",
        task_type=task_type,
        subject_ref=request_id,
        operation_identity=f"{operation}:{request_id}",
        execution_lane=STANDARD_BACKGROUND,
        payload={"operation": operation, "request_id": request_id},
        stage=f"等待{stage}",
        created_by_user_id=created_by_user_id,
        queue_max=settings.task_queue_max,
        gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
    )


class BackgroundTaskRunner:
    def __init__(
        self,
        settings: Settings,
        *,
        handlers: dict[str, Callable[[Settings, str], dict[str, Any]]] | None = None,
    ) -> None:
        self.settings = settings
        self.handlers = handlers or {
            "content_plan": resolve_content_plan,
            "script_generation": generate_scripts,
            "mix_export": export_mix_excel,
            "news_plan": resolve_news_plan,
            "news_export": export_news_excel,
            "novel_news_generate": generate_novel_news,
            "novel_news_export": export_novel_news,
        }
        self.executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="standard-background"
        )
        self.operation_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="standard-operation"
        )
        self._scheduled: set[str] = set()
        self._lock = threading.Lock()
        self.worker_id = f"background-{os.getpid()}-{id(self):x}"
        self.maintenance = LeaseRecoveryMaintenance(
            interval_seconds=self.settings.task_heartbeat_seconds,
            name="background-lease-recovery",
            callback=self._recover_and_schedule,
        )

    def _reconcile_business_state(self, task_id: str) -> str | None:
        task = get_task(self.settings.database_path, task_id)
        if task is None:
            return None
        payload = task.get("payload") or {}
        operation = str(payload.get("operation") or "")
        request_id = str(payload.get("request_id") or task.get("subject_ref") or "")
        try:
            if operation in {"content_plan", "script_generation", "mix_export"}:
                state = get_content_delivery_state(self.settings, request_id)
                done = {
                    "content_plan": bool((state.get("content_plan") or {}).get("ready")),
                    "script_generation": bool((state.get("generation") or {}).get("ready")),
                    "mix_export": bool(state.get("stop_point_reached")),
                }[operation]
            elif operation in {"news_plan", "news_export"}:
                state = get_news_delivery_state(self.settings, request_id)
                done = (
                    state.get("next_action") != "RESOLVE_NEWS_PLAN"
                    if operation == "news_plan"
                    else bool(state.get("stop_point_reached"))
                )
            elif operation in {"novel_news_generate", "novel_news_export"}:
                state = novel_news_state(self.settings, request_id)
                done = state.get("stage") in (
                    {"review", "export", "completed"}
                    if operation == "novel_news_generate" else {"completed"}
                )
            else:
                return "failed"
        except CanonicalOperationError:
            return None
        return "completed" if done else None

    def start(self) -> None:
        if not self.settings.background_worker_enabled:
            return
        self._recover_and_schedule()
        self.maintenance.start()

    def _recover_and_schedule(self) -> None:
        recover_expired_tasks(
            self.settings.database_path,
            task_types=("content_generation", "excel_export"),
            reconciler=self._reconcile_business_state,
        )
        self.schedule_pending()

    def close(self) -> None:
        self.maintenance.close()
        self.executor.shutdown(wait=False, cancel_futures=False)
        self.operation_executor.shutdown(wait=False, cancel_futures=False)

    def schedule(self, task_id: str | None = None) -> None:
        self.schedule_pending()

    def schedule_pending(self) -> None:
        if not self.settings.background_worker_enabled:
            return
        with self._lock:
            for task in iter_queued_tasks(
                self.settings.database_path,
                task_types=("content_generation", "excel_export"),
            ):
                task_id = str(task["task_id"])
                if task_id in self._scheduled:
                    continue
                self._scheduled.add(task_id)
                self.executor.submit(self._run, task_id)

    def _run(self, task_id: str) -> None:
        try:
            task = get_task(self.settings.database_path, task_id)
            if task is None:
                return
            payload = task.get("payload") or {}
            operation = str(payload.get("operation") or "")
            request_id = str(payload.get("request_id") or task.get("subject_ref") or "")
            if operation not in self.handlers:
                update_task(
                    self.settings.database_path,
                    task_id,
                    status="failed",
                    stage="后台任务类型无效",
                    error_code="BACKGROUND_OPERATION_UNSUPPORTED",
                    error_message="后台任务类型无法识别。",
                )
                return
            if not claim_task(
                self.settings.database_path,
                task_id,
                worker_id=self.worker_id,
                lease_seconds=self.settings.task_lease_seconds,
                stage=BACKGROUND_OPERATIONS[operation][1],
                task_type=str(task["task_type"]),
            ):
                return

            def execute() -> dict[str, Any]:
                if operation in {"novel_news_generate", "novel_news_export"}:
                    require_novel_news_task(self.settings, (task.get("created_by") or {}).get("user_id"))
                lock_scope = "request"
                lock_identity = request_id
                if operation == "mix_export":
                    state = get_content_delivery_state(self.settings, request_id)
                    lock_scope = "business"
                    lock_identity = str(state.get("business_id") or "")
                elif operation == "news_export":
                    state = get_news_delivery_state(self.settings, request_id)
                    lock_scope = "business"
                    lock_identity = str(state.get("business_id") or "")
                elif operation == "novel_news_export":
                    state = novel_news_state(self.settings, request_id)
                    lock_scope = "business"
                    lock_identity = str(state.get("business_id") or "")
                with authority_operation_lock(
                    self.settings,
                    lock_scope,
                    lock_identity,
                    timeout_seconds=0.0,
                ):
                    return self.handlers[operation](self.settings, request_id)

            future = self.operation_executor.submit(execute)
            while not future.done():
                update_task(
                    self.settings.database_path,
                    task_id,
                    status="running",
                    worker_id=self.worker_id,
                    lease_seconds=self.settings.task_lease_seconds,
                    heartbeat_interval_seconds=self.settings.task_heartbeat_seconds,
                )
                time.sleep(min(1.0, self.settings.task_heartbeat_seconds / 2))
            future.result()

            # Completion only records execution. Callers must re-read the
            # canonical resolver before presenting business completion.
            update_task(
                self.settings.database_path,
                task_id,
                status="completed",
                progress=100,
                stage="执行完成，请刷新业务状态",
            )
        except CanonicalOperationError as exc:
            update_task(
                self.settings.database_path,
                task_id,
                status="failed",
                stage="后台操作失败",
                error_code=exc.code,
                error_message=exc.message,
            )
        except Exception:
            update_task(
                self.settings.database_path,
                task_id,
                status="failed",
                stage="后台操作失败",
                error_code="BACKGROUND_OPERATION_FAILED",
                error_message="后台操作没有完成。",
            )
        finally:
            with self._lock:
                self._scheduled.discard(task_id)
