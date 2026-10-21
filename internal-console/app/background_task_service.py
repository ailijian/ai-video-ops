from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable
from contextlib import contextmanager

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
    "publish_copy_generate": ("content_generation", "生成发布信息"),
    "publish_copy_export": ("excel_export", "导出完整交付"),
}


from .compatibility_gate import guarded as compatibility_guarded


@contextmanager
def _news_task_admission(settings,request_id,operation):
    from news_runtime_v1_2 import configured,current
    if not configured(settings.pipeline_root) or operation not in {
        'news_plan','news_export','novel_news_generate','novel_news_export'}:
        yield
        return
    from profile_compatibility_decisions_v1_1 import read
    from profile_compatibility_release_v1_1 import runtime_write
    from profile_compatibility_contract_v1_1 import CompatibilityError
    root=settings.pipeline_root
    path=(root/'data/news_deliveries'/request_id/'news_delivery_request_v1.json'
        if operation in {'news_plan','news_export'} else
        root/'data/generation_requests'/request_id/'generation_request_v1.json')
    pinned=read(path).get('profile_compatibility_v1_2')
    if not pinned:raise CanonicalOperationError('PROFILE_COMPATIBILITY_BLOCKED','请先核对新闻体资格。','保留原操作，核对当前版本。')
    try:
        current(root,reuse_intent=pinned['reuse_intent'],pinned=pinned)
        with runtime_write(root,pinned=pinned):yield
    except CompatibilityError as exc:
        raise CanonicalOperationError('PROFILE_COMPATIBILITY_BLOCKED',
            '新闻体的兼容性或发布资格已变化。',
            '请核对当前批准与发布版本；原请求和导出记录会保留，本次不会继续写入。') from exc


@compatibility_guarded
def create_background_task(
    settings: Settings,
    *,
    operation: str,
    request_id: str,
    created_by_user_id: int,
    generation_recovery: dict[str, str] | None = None,
    export_context: dict[str, Any] | None = None,
    novel_generation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if operation not in BACKGROUND_OPERATIONS:
        raise ValueError("unsupported background operation")
    if operation == 'mix_export' and (settings.pipeline_root / 'data/generation_batches' / request_id / 'generation_export_closure_v1.json').exists():
        raise CanonicalOperationError('EXPORT_ALREADY_CLOSED', '这次导出已有闭合记录。', '请读取原文件和记录；本次不会建立新任务。')
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
        if operation == 'novel_news_generate' and novel_generation:
            from novel_news_generation_recovery_v1 import head, current_identity, GenerationError
            admitted = head(settings.pipeline_root, request_id)
            if (not admitted or admitted['operation_id'] != novel_generation['operation_id']
                    or admitted['sha256'] != novel_generation['intent_sha256']):
                raise GenerationError('OPERATION_CONFLICT')
            current_identity(admitted['intent'], novel_generation['authorization_context'])
            state = {'stage': 'generation'}
        else:
            state = novel_news_state(settings, request_id)
        expected = "generation" if operation == "novel_news_generate" else "export"
        if state.get("stage") != expected:
            raise CanonicalOperationError(
                "NEWS_NOVEL_STAGE_INVALID", "当前新闻体阶段不允许此操作。",
                "请刷新创作进度，不会建立重复后台任务。",
            )
    task_type, stage = BACKGROUND_OPERATIONS[operation]
    if operation == 'novel_news_generate' and not novel_generation:
        raise CanonicalOperationError('NEWS_GENERATION_OPERATION_REQUIRED', '请从原新闻体页面确认生成。', '原操作记录会保留。')
    with _news_task_admission(settings,request_id,operation):
        return submit_task(
        settings.database_path,
        task_id_prefix=f"{operation}-{request_id}",
        task_type=task_type,
        subject_ref=request_id,
        operation_identity=(f"{operation}:{request_id}:" + novel_generation['operation_id']) if novel_generation else f"{operation}:{request_id}",
        execution_lane=STANDARD_BACKGROUND,
        payload={"operation": operation, "request_id": request_id,
            **({'export_context':export_context} if export_context else {}),
            **({'generation_recovery': generation_recovery} if generation_recovery else {}),
            **({'novel_generation': novel_generation} if novel_generation else {})},
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
        from .publish_copy_gateway import generate as publish_generate, export as publish_export
        self.handlers = handlers or {
            "content_plan": resolve_content_plan,
            "script_generation": generate_scripts,
            "mix_export": export_mix_excel,
            "news_plan": resolve_news_plan,
            "news_export": export_news_excel,
            "novel_news_generate": generate_novel_news,
            "novel_news_export": export_novel_news,
            "publish_copy_generate": publish_generate,
            "publish_copy_export": publish_export,
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
            if operation in {'publish_copy_generate', 'publish_copy_export'}:
                from .publish_copy_gateway import native
                state = native(self.settings, request_id, 'state')
                if operation == 'publish_copy_export':
                    result = native(self.settings, request_id, 'effective')
                    if result:
                        from profile_compatibility_decisions_v1_1 import read
                        receipt = read(self.settings.pipeline_root / result['receipt_ref']['path'])
                        confirmation = read(self.settings.pipeline_root / receipt['confirmation_ref']['path'])
                        if confirmation['draft_ref'] == (payload.get('publish_copy') or {}).get('expected_draft_ref'):
                            return 'completed'
                    return None
                execution = payload.get('publish_copy') or {}
                if state.get('operation_id') != execution.get('operation_id'): return 'failed'
                if state['state'] == 'draft_ready': return 'completed'
                if state['state'] in {'not_dispatched', 'validated_result_unpublished'}: return None
                update_task(self.settings.database_path, task_id, error_code='PUBLISH_COPY_OUTCOME_UNKNOWN'
                    if state['state'] == 'dispatched_outcome_unknown' else 'PUBLISH_COPY_SOURCE_CHANGED',
                    error_message='模型结果无法确认，系统不会自动重复调用。' if state['state'] == 'dispatched_outcome_unknown' else '来源或授权需要重新核对。')
                return 'failed'
            if operation in {"content_plan", "script_generation", "mix_export"}:
                state = get_content_delivery_state(self.settings, request_id)
                done = {
                    "content_plan": bool((state.get("content_plan") or {}).get("ready")),
                    "script_generation": bool((state.get("generation") or {}).get('generation_completed', (state.get("generation") or {}).get("ready"))),
                    "mix_export": bool(state.get("stop_point_reached")),
                }[operation]
                if operation == 'script_generation' and payload.get('generation_recovery'):
                    from generation_recovery_v1 import operation_root, read, file_sha
                    identity = payload['generation_recovery']
                    directory = operation_root(self.settings.pipeline_root, request_id, identity['operation_id'])
                    if file_sha(directory / 'intent.json') != identity['intent_sha256']:
                        return 'failed'
                    result = directory / 'result.json'
                    if result.is_file():
                        return 'completed' if read(result)['outcome'] == 'review_required' and done else 'failed'
                    return None
            elif operation in {"news_plan", "news_export"}:
                state = get_news_delivery_state(self.settings, request_id)
                done = (
                    state.get("next_action") != "RESOLVE_NEWS_PLAN"
                    if operation == "news_plan"
                    else bool(state.get("stop_point_reached"))
                )
            elif operation == 'novel_news_generate':
                identity = payload.get('novel_generation')
                projection = novel_news_state(self.settings, request_id)
                state = projection.get('generation') or {}
                if state.get('recovery_state') == 'source_or_authorization_conflict' and projection.get('stage') != 'completed':
                    update_task(self.settings.database_path, task_id,
                        error_code=state.get('native_code') or 'NEWS_GENERATION_SOURCE_CHANGED',
                        error_message='当前来源或授权已变化，原生成操作已阻断。')
                    return 'failed'
                if (not identity or identity.get('operation_id') != state.get('operation_id')
                        or identity.get('intent_sha256') != state.get('intent_sha256')):
                    update_task(self.settings.database_path, task_id, error_code='NEWS_GENERATION_OUTCOME_UNKNOWN',
                                error_message='模型执行结果无法确认，系统不会自动重复生成。')
                    return 'failed'
                native = state.get('recovery_state')
                if projection.get('stage') == 'completed':
                    return 'completed'
                if native == 'review_required':
                    if state.get('result_present'):
                        return 'completed'
                    generate_novel_news(self.settings, request_id, task_id=task_id, **identity)
                    return 'completed'
                if native in {'not_dispatched', 'validated_result_unpublished'}:
                    return None
                update_task(self.settings.database_path, task_id,
                    error_code='NEWS_GENERATION_OUTCOME_UNKNOWN' if native == 'dispatched_outcome_unknown' else 'NEWS_GENERATION_BLOCKED',
                    error_message='模型执行结果无法确认，系统不会自动重复生成。' if native == 'dispatched_outcome_unknown' else '来源、授权或生成结果需要核对。')
                return 'failed'
            elif operation == "novel_news_export":
                state = novel_news_state(self.settings, request_id)
                done = state.get("stage") in (
                    {"review", "export", "completed"}
                    if operation == "novel_news_generate" else {"completed"}
                )
            else:
                return "failed"
        except CanonicalOperationError:
            if operation in {'novel_news_generate', 'publish_copy_generate', 'publish_copy_export'}:
                return 'failed'
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
                if operation in {'publish_copy_generate', 'publish_copy_export'}:
                    # Native short fences and executor ownership do not hold a
                    # Console process lock across external model latency.
                    return self.handlers[operation](self.settings, request_id,
                        **payload['publish_copy'], **({'task_id': task_id} if operation == 'publish_copy_generate' else {}))
                if operation in {"novel_news_generate", "novel_news_export"}:
                    require_novel_news_task(self.settings, (task.get("created_by") or {}).get("user_id"))
                if operation == 'novel_news_generate':
                    if not payload.get('novel_generation'):
                        raise CanonicalOperationError('NEWS_GENERATION_OUTCOME_UNKNOWN',
                            '模型执行结果无法确认。', '系统不会自动重复生成。')
                    # The Native owner holds the existing backup/Authority gates
                    # for each mutation, never across external model latency.
                    return self.handlers[operation](self.settings, request_id, task_id=task_id, **payload['novel_generation'])
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
                    if operation == 'script_generation' and payload.get('generation_recovery'):
                        # Use the same real Gateway checks and Task runner.
                        return generate_scripts(self.settings, request_id, **payload['generation_recovery'])
                    if operation in {'mix_export','news_export','novel_news_export'} and payload.get('export_context'):
                        return self.handlers[operation](self.settings,request_id,**payload['export_context'])
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
