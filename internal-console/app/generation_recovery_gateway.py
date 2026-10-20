"""Thin authenticated retry adapter; native Generation owns every artifact."""
import hashlib

from resolve_generation_batch_v1 import preview_generation_recovery, confirm_generation_recovery
from .background_task_service import create_background_task
from .canonical_gateway import CanonicalOperationError
from .case_library_access import principal


def invoke(function, **kwargs):
    try:
        return function(**kwargs)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        code = getattr(exc, 'code', '')
        if not code.startswith('GENERATION_RECOVERY_') and code not in {'GENERATION_BATCH_NOT_REVIEWABLE','PROFILE_COMPATIBILITY_BLOCKED'}:
            code = 'GENERATION_RECOVERY_SOURCE_CHANGED'
        next_action = '原始内容和记录已保留。请刷新检查当前操作；结果不确定时，需要明确发起下一次重试。'
        if code in {'GENERATION_RECOVERY_SOURCE_CHANGED','PROFILE_COMPATIBILITY_BLOCKED'}:
            next_action = '请先核对客户、出镜人和创作参考的当前版本，再从客户重新检查创作条件。本次创作和失败记录会保留。'
        elif code == 'GENERATION_RECOVERY_AUTHORIZATION_REQUIRED':
            next_action = '请重新登录后检查当前操作；失效的确认不会继续生成，原始记录会保留。'
        elif code == 'GENERATION_RECOVERY_SCOPE_UNSUPPORTED':
            next_action = '当前情况不能直接重新生成。已有部分内容请按原审核或修改流程处理，也可以保留记录并联系维护人员检查。'
        raise CanonicalOperationError(code, '当前不能继续这次文案生成。', next_action,
            details={'native_code': getattr(exc, 'code', None)}) from exc


def preview(settings, request_id, session, operation_id):
    return invoke(preview_generation_recovery, pipeline_root=settings.pipeline_root,
        request_id=request_id, operation_id=operation_id,
        actor=principal(settings, int(session.user['id'])), database_path=settings.database_path,
        session_fingerprint=hashlib.sha256(session.token_hash.encode()).hexdigest())


def confirm(settings, request_id, session, operation_id, preview_sha256):
    identity = invoke(confirm_generation_recovery, pipeline_root=settings.pipeline_root,
        request_id=request_id, operation_id=operation_id, preview_sha256=preview_sha256,
        actor=principal(settings, int(session.user['id'])))
    task = create_background_task(settings, operation='script_generation', request_id=request_id,
        created_by_user_id=int(session.user['id']),
        generation_recovery={'operation_id': operation_id, 'intent_sha256': identity['sha256']})
    from generation_recovery_v1 import operation_root, read
    from resolve_generation_batch_v1 import generation_snapshot
    from .task_service import resume_generation_recovery_task, update_task, get_task
    if task['status'] == 'failed':
        result = operation_root(settings.pipeline_root, request_id, operation_id) / 'result.json'
        if not result.exists():
            return resume_generation_recovery_task(settings.database_path, task['task_id'], queue_max=settings.task_queue_max)
        state = generation_snapshot(settings.pipeline_root, request_id)
        record = read(result)
        if record['outcome'] == 'review_required' and state['ready_for_human_review'] and record['batch_ref'] == state['batch_ref']:
            update_task(settings.database_path, task['task_id'], status='completed', progress=100, stage='已恢复原生生成结果')
            return get_task(settings.database_path, task['task_id'])
    return task
