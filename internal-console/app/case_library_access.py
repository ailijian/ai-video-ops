"""Local principal, explicit Case permissions and exact submission access."""
from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .canonical_gateway import CanonicalOperationError, _find_case_path, _read_json, _sha256
from .database import connect, transaction
from .operation_lock import operation_lock
from .task_service import get_task


@lru_cache(maxsize=16)
def _owner(root):
    path = Path(root)/'scripts/case_console_authorization_v1.py'
    spec = importlib.util.spec_from_file_location('case_console_authorization_owner', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def principal(settings, user_id):
    db = connect(settings.database_path)
    try:
        node = db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
        user = db.execute('SELECT id,status FROM users WHERE id=?', (user_id,)).fetchone()
    finally:
        db.close()
    if not node or not user or user['status'] != 'active':
        raise CanonicalOperationError('CASE_REVIEWER_REQUIRED', '没有有效的案例操作身份。', '请重新登录。')
    return {'namespace':node['namespace'], 'user_id':int(user['id'])}


def reviewer_authorization(settings, actor, reviewer=None):
    try:
        return _owner(str(settings.pipeline_root)).validate_console_reviewer(
            settings.database_path, actor['user_id'], actor['namespace'], reviewer)
    except (RuntimeError, OSError, KeyError) as exc:
        raise CanonicalOperationError('CASE_REVIEWER_REQUIRED', '此账号未获得案例审核授权。', '请交由指定案例审核人处理。') from exc


def is_reviewer(settings, user_id):
    try:
        reviewer_authorization(settings, principal(settings, user_id))
        return True
    except CanonicalOperationError:
        return False


def reviewer_lock(settings, actor):
    return operation_lock(settings.pipeline_root, f"case-reviewer:{actor['namespace']}:{actor['user_id']}")


def manage_reviewer(settings, user_id, *, action, operator, reason):
    """Trusted local maintenance only. There is deliberately no HTTP endpoint."""
    if action not in {'grant','revoke'} or not operator.strip() or not reason.strip():
        raise ValueError('Explicit operator, grant/revoke and reason required')
    actor = principal(settings, user_id)
    owner = _owner(str(settings.pipeline_root))
    with reviewer_lock(settings, actor), transaction(settings.database_path, immediate=True) as db:
        previous = db.execute('SELECT record_json,event_sha256 FROM case_capability_events WHERE user_id=? ORDER BY event_id DESC LIMIT 1', (user_id,)).fetchone()
        record = {'schema_version':owner.VERSION, 'capability':owner.CAPABILITY,
                  **actor, 'sequence':json.loads(previous['record_json'])['sequence']+1 if previous else 1,
                  'action':action, 'operator':operator.strip(), 'reason':reason.strip(),
                  'at':datetime.now(timezone.utc).isoformat(),
                  'parent_sha256':previous['event_sha256'] if previous else None}
        receipt_sha = owner.digest(record)
        cursor = db.execute('INSERT INTO case_capability_events(user_id,action,record_json,event_sha256,occurred_at) VALUES (?,?,?,?,?)',
                            (user_id,action,json.dumps(record,ensure_ascii=False),receipt_sha,record['at']))
        return {'event_id':cursor.lastrowid,'event_sha256':receipt_sha,'action':action,**actor}


def not_visible():
    raise CanonicalOperationError('CASE_OBJECT_NOT_FOUND', '没有找到可访问的记录。', '请返回案例或任务列表。')


def submission_path(settings, kind, identity):
    if kind not in {'tasks','groups'} or not re.fullmatch(r'[A-Za-z0-9_-]{8,160}', identity):
        not_visible()
    return settings.pipeline_root/'data/case_governance/submissions'/kind/identity/'submission_receipt_v1.json'


def record_submission(settings, user_id, *, task=None, group=None):
    actor = principal(settings, user_id)
    kind, identity = ('tasks',task['task_id']) if task else ('groups',group['group_id'])
    if task and (task.get('created_by') or {}).get('user_id') != user_id:
        not_visible()
    if group and group.get('created_by_user_id') != user_id:
        not_visible()
    value = {'schema_version':'case-submission-v1.0', 'principal':actor, 'kind':kind,
             'identity':identity, 'at':task['created_at'] if task else group['created_at'],
             'sources':[{'case_id':task['subject_ref'],'source_url':task['payload']['source_url']}] if task else
                       [{'case_id':i.get('case_id'),'source_url':i.get('canonical_url') or i['source_url']} for i in group['items']]}
    path = submission_path(settings,kind,identity)
    if path.exists():
        if _read_json(path) != value: not_visible()
        return
    path.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create: never overwrite an original submission receipt.
    try:
        with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2)
    except FileExistsError:
        if _read_json(path) != value: not_visible()


def owns_task(settings, user_id, task):
    if not task or (task.get('created_by') or {}).get('user_id') != user_id:
        return False
    actor = principal(settings,user_id)
    path = submission_path(settings,'tasks',task['task_id'])
    if not path.exists():
        return True  # Original authenticated FK in this same DB, not inferred Case ownership.
    try:
        record = _read_json(path)
        return (record.get('schema_version') == 'case-submission-v1.0' and record.get('principal') == actor
                and record.get('kind') == 'tasks' and record.get('identity') == task['task_id']
                and record.get('sources') == [{'case_id':task['subject_ref'],'source_url':task['payload']['source_url']}])
    except CanonicalOperationError:
        return False


def can_read_task(settings, user_id, task):
    return bool(task and (task['task_type'] != 'case_analysis' or is_reviewer(settings,user_id) or owns_task(settings,user_id,task)))


def can_read_group(settings, user_id, group):
    if not group: return False
    if is_reviewer(settings,user_id): return True
    if group.get('created_by_user_id') != user_id: return False
    path = submission_path(settings,'groups',group['group_id'])
    if not path.exists(): return True  # Preserved original authenticated submission relation.
    try:
        record = _read_json(path)
        return (record.get('schema_version') == 'case-submission-v1.0' and record.get('principal') == principal(settings,user_id)
                and record.get('identity') == group['group_id'] and record.get('kind') == 'groups')
    except CanonicalOperationError:
        return False


def can_read_private_case(settings, user_id, case_id, attempt_id=None):
    if is_reviewer(settings,user_id): return True
    try:
        path, attempt = _find_case_path(settings,case_id,attempt_id=attempt_id)
        case = _read_json(path)
        if case.get('case_id') != case_id: return False
        identity = (attempt or {}).get('attempt_id') or (case.get('analysis_lineage') or {}).get('attempt_id')
        task = get_task(settings.database_path,str(identity or ''))
        return bool(task and task['subject_ref'] == case_id and owns_task(settings,user_id,task))
    except (CanonicalOperationError,ValueError):
        return False


def require_private_case(settings,user_id,case_id,attempt_id=None):
    if not can_read_private_case(settings,user_id,case_id,attempt_id): not_visible()


def require_task(settings,user_id,task):
    if not can_read_task(settings,user_id,task): not_visible()


def safe_case_task(settings,user_id,task):
    """One sanitizer for Task, Group, My Submissions and failure recovery."""
    require_task(settings,user_id,task)
    if task['task_type']!='case_analysis': return task
    result={**task,'payload':dict(task.get('payload') or {})}
    duplicate=result['payload'].get('duplicate') or {}
    if duplicate or result.get('error_code')=='MEDIA_DUPLICATE_CASE':
        target=str(duplicate.get('existing_case_id') or '')
        if not can_read_private_case(settings,user_id,target):
            from .case_shared_display import shared_projection
            shared=shared_projection(settings,target)
            if shared:
                result['payload']['duplicate']={'existing_case_id':target,'state':'approved'}
                result['error_message']='已有可浏览的共享案例，请查看允许访问的参考内容。'
            else:
                result['payload'].pop('duplicate',None)
                result['error_message']='该投稿已记录，当前没有可访问的处理结果。'
    return result
