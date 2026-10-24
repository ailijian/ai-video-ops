"""Authenticated derived read adapter; source readers retain all authority."""
import hashlib
import json

from creative_capacity_read_v1 import read_inventory
from .canonical_gateway import CanonicalOperationError
from .database import connect


def authorization_scope(settings, user_id, session_token_hash):
    from .auth_service import iso_utc
    with connect(settings.database_path) as db:
        row = db.execute('SELECT u.id,u.status,u.must_change_password,u.updated_at,s.expires_at FROM users u JOIN sessions s ON s.user_id=u.id WHERE u.id=? AND s.token_hash=?', (user_id,session_token_hash)).fetchone()
    if row is None or row['status'] != 'active' or row['must_change_password'] or row['expires_at'] <= iso_utc():
        raise CanonicalOperationError('CAPACITY_READ_ACCESS_CHANGED', '当前读取权限已变化。', '请重新登录后核对。')
    return hashlib.sha256(json.dumps(dict(row), sort_keys=True).encode()).hexdigest()


def projection(settings, session, business_id, speaker_id, novel_target):
    from .novel_news_rollout import require_novel_news_task
    user_id=int(session.user['id'])
    require_novel_news_task(settings, user_id)
    before = authorization_scope(settings, user_id, session.token_hash)
    try:
        result = read_inventory(pipeline_root=settings.pipeline_root, business_id=business_id,
            speaker_id=speaker_id, novel_target=novel_target, authorization_scope_sha256=before)
    except (RuntimeError, ValueError, OSError) as exc:
        raise CanonicalOperationError(getattr(exc, 'code', 'CAPACITY_READ_UNAVAILABLE'),
            '当前容量说明需要重新读取。', '请核对当前客户、出镜人与来源资格后刷新；不会改变已有任务或历史。') from exc
    if before != authorization_scope(settings, user_id, session.token_hash):
        raise CanonicalOperationError('CAPACITY_READ_ACCESS_CHANGED', '当前读取权限已变化。', '请重新登录后核对。')
    return result
