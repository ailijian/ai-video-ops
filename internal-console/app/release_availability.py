"""Deployment availability only; never a production qualification or approval."""
from .canonical_gateway import CanonicalOperationError


def require_creation_batch(settings):
    if not settings.creation_batch_enabled:
        raise CanonicalOperationError(
            'CREATION_BATCH_NOT_ENABLED', '批量创作当前未开放。',
            '已有内容与交付记录仍可查看；开放前需完成相应验收及正式资格核对。')


def batch_task_disabled(settings, task):
    """Leave unclaimed batch work intact when the deployment switch is closed."""
    if settings.creation_batch_enabled:
        return False
    payload = task.get('payload') or {}
    if str(payload.get('operation') or '').startswith('creation_batch_'):
        return True
    request_id = str(payload.get('request_id') or task.get('subject_ref') or '')
    if not request_id.startswith(('gen_', 'news_')):
        return False
    from human_review_operations_v1 import io_path, read
    from native_batch_v1 import request_path
    try:
        path = io_path(request_path(settings.pipeline_root, request_id))
        return bool(path.is_file() and read(path).get('batch_admission_ref'))
    except (OSError, RuntimeError, ValueError):
        return True
