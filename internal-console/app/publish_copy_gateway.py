"""Thin Session/Task adapter. All publish and delivery truth stays Native."""
from .canonical_gateway import CanonicalOperationError
from .novel_news_gateway import _run
from .database import connect
from .task_service import get_task, submit_task, STANDARD_BACKGROUND

def native(settings, rid, command, **payload):
    if not settings.publish_copy_enabled:
        raise CanonicalOperationError('PUBLISH_COPY_DISABLED', '发布信息暂未开放。', '原制作稿和导出仍可使用。')
    try:
        return _run(settings, 'publish_copy_v1.py', [command, '--pipeline-root', str(settings.pipeline_root),
            '--request-id', rid], payload=payload, remote=command == 'run')['result']
    except CanonicalOperationError as exc:
        if exc.code.startswith('LEDGER_HISTORY_'):
            raise CanonicalOperationError(exc.code,'历史交付证据不足或已变化。','请保留原交付并核对历史证据，系统不会改写旧收据。') from exc
        if exc.code.startswith('PUBLISH_COPY_'):
            message='发布信息尚未完成，请核对原操作。'
            action='请检查发布表达、制作短标题及来源对应；原制作稿和历史交付会保留。'
            if exc.code.endswith('OUTCOME_UNKNOWN'):
                message='模型执行结果无法确认。';action='系统不会自动重复生成；明确重新尝试可能产生额外费用。'
            elif any(x in exc.code for x in ('SOURCE','AUTHORIZATION','SUPERSEDED')):
                message='来源、权限或内容历史已变化。';action='旧操作不会自动改绑，请重新核对后明确发起新尝试。'
            elif exc.code.endswith('TARGET_SET_INVALID'):
                message='发布信息尚未齐全或与制作稿不对应。';action='请补齐每条制作稿的发布信息，再统一核对并确认；原稿会保留。'
            raise CanonicalOperationError(exc.code,message,action) from exc
        raise

def project(settings, rid):
    # A terminal Task must be observed BEFORE Native truth is read. Reading
    # Tasks afterwards could pair completion with an older Native snapshot and
    # force the browser to repeat the entire expensive source validation.
    with connect(settings.database_path) as db:
        rows = db.execute("SELECT task_id FROM tasks WHERE subject_ref=? AND json_extract(payload_json,'$.operation') "
            "IN ('publish_copy_generate','publish_copy_export') ORDER BY rowid DESC LIMIT 2", (rid,)).fetchall()
    tasks = [get_task(settings.database_path, r['task_id']) for r in rows]
    result = native(settings, rid, 'project')
    result['tasks'] = tasks
    result['task_snapshot_before_native'] = True
    return result

def submit(settings, rid, operation, user_id, context, **arguments):
    from .task_service import resume_publish_copy_task
    if operation == 'publish_copy_generate':
        with connect(settings.database_path) as db:
            unbound=db.execute("SELECT task_id FROM tasks WHERE subject_ref=? AND json_extract(payload_json,'$.operation')='publish_copy_generate' "
                "AND json_extract(payload_json,'$.publish_copy.operation_id') IS NULL LIMIT 1",(rid,)).fetchone()
        if unbound:
            raise CanonicalOperationError('PUBLISH_COPY_LEGACY_OUTCOME_UNKNOWN','旧生成操作的执行结果无法确认。',
                '已保留原任务，不能推断模型从未调用；请先核对原操作证据。')
        prepared = native(settings, rid, 'prepare', authorization_context=context, **arguments)
        identity = 'publish-copy:' + rid + ':' + prepared['operation_id']
        execution = {'operation_id': prepared['operation_id'], 'authorization_context': context}
        state = native(settings, rid, 'state')
        if state['state'] == 'draft_ready': return {'accepted': False, 'canonical_result': state, 'task': existing_task(settings, identity)}
        if state['state'] == 'dispatched_outcome_unknown':
            raise CanonicalOperationError('PUBLISH_COPY_OUTCOME_UNKNOWN', '模型执行结果无法确认。',
                '系统不会自动重复调用；重新尝试可能产生额外费用。')
    else:
        state = native(settings, rid, 'project')
        if not state['confirmed']: raise CanonicalOperationError('PUBLISH_COPY_CONFIRMATION_REQUIRED', '请先确认发布信息。', '原制作稿会保留。')
        completed = state['delivery']
        if completed:
            from profile_compatibility_decisions_v1_1 import read
            receipt = read(settings.pipeline_root / completed['receipt_ref']['path'])
            confirmed = settings.pipeline_root / receipt['confirmation_ref']['path']
            if read(confirmed)['draft_ref'] == state['draft']['ref']:
                key = 'publish-delivery:' + rid + ':' + state['draft']['ref']['sha256']
                return {'accepted': False, 'canonical_result': completed, 'task': existing_task(settings, key)}
        identity = 'publish-delivery:' + rid + ':' + state['draft']['ref']['sha256']
        execution = {'authorization_context': context, 'expected_draft_ref': state['draft']['ref']}
        if arguments.get('automatic_batch_ref') is not None:
            execution['automatic_batch_ref'] = arguments['automatic_batch_ref']
    with connect(settings.database_path) as db:
        row = db.execute('SELECT task_id FROM tasks WHERE operation_identity=? ORDER BY rowid DESC LIMIT 1', (identity,)).fetchone()
    if row:
        task = get_task(settings.database_path, row['task_id'])
        if operation == 'publish_copy_generate':
            native(settings, rid, 'bind-task', operation_id=prepared['operation_id'], task_id=task['task_id'], authorization_context=context)
        if task['status'] == 'failed':
            task = resume_publish_copy_task(settings.database_path, task['task_id'], context, queue_max=settings.task_queue_max)
        return {'accepted': task['status'] in {'queued', 'running'}, 'task': task}
    task = submit_task(settings.database_path, task_id_prefix=operation, task_type='content_generation' if operation.endswith('generate') else 'excel_export',
        subject_ref=rid, operation_identity=identity, execution_lane=STANDARD_BACKGROUND,
        payload={'operation': operation, 'request_id': rid, 'publish_copy': execution},
        stage='生成发布信息' if operation.endswith('generate') else '导出完整交付', created_by_user_id=user_id,
        queue_max=settings.task_queue_max, gpu_pending_per_user_max=settings.gpu_pending_per_user_max)
    if operation == 'publish_copy_generate':
        native(settings, rid, 'bind-task', operation_id=prepared['operation_id'], task_id=task['task_id'], authorization_context=context)
    return {'accepted': True, 'task': task}

def existing_task(settings, operation_identity):
    with connect(settings.database_path) as db:
        row = db.execute('SELECT task_id FROM tasks WHERE operation_identity=? ORDER BY rowid DESC LIMIT 1', (operation_identity,)).fetchone()
    return get_task(settings.database_path, row['task_id']) if row else None

def generate(settings, rid, **execution):
    # A queued Task can be claimed before the submitting HTTP request has
    # finished publishing its Native binding. The claimed executor binds the
    # same immutable Task identity before dispatch; both writers use the Native
    # authorization/source fence and write-once binding, never a bypass flag.
    native(settings, rid, 'bind-task', operation_id=execution['operation_id'],
        task_id=execution['task_id'], authorization_context=execution['authorization_context'])
    return native(settings, rid, 'run', **execution)
def export(settings, rid, **execution): return native(settings, rid, 'export', **execution)
