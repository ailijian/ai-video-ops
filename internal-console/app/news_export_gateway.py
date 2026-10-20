"""Thin submission adapter. Native News owners determine delivery completion."""
from .canonical_gateway import CanonicalOperationError
from .database import connect
from .operation_lock import operation_lock, scoped_lock_key, OperationLockTimeout
from .task_service import get_task, update_task


def _state(settings, request_id, novel):
    if novel:
        from .novel_news_gateway import novel_news_state
        return novel_news_state(settings, request_id)
    from .news_delivery_gateway import get_news_delivery_state
    return get_news_delivery_state(settings, request_id)


def completed(settings, request_id, *, novel):
    state = _state(settings, request_id, novel)
    if not (state.get('stage') == 'completed' if novel else state.get('stop_point_reached')):
        return None
    operation = 'novel_news_export' if novel else 'news_export'
    with connect(settings.database_path) as db:
        row = db.execute("SELECT task_id FROM tasks WHERE task_type='excel_export' AND subject_ref=? "
            "AND operation_identity=? ORDER BY created_at DESC,task_id LIMIT 1", (request_id, operation+':'+request_id)).fetchone()
    task = get_task(settings.database_path,row['task_id']) if row else None
    if task and task['status'] != 'completed':
        # Reconcile an existing execution only after strict Native completion.
        update_task(settings.database_path, task['task_id'], status='completed', progress=100,
                    stage='导出已完成', error_code='', error_message='')
        task = get_task(settings.database_path,task['task_id'])
    return {'response_version':'content-operation-response-v1.1', 'accepted':False, 'recovered':True,
        'task':task, 'canonical_result':state}


def submit(settings, request_id, user_id, authorization_context, *, novel):
    from .background_task_service import create_background_task
    state = _state(settings,request_id,novel)
    try:
        with operation_lock(settings.pipeline_root, scoped_lock_key('business',state['business_id']), timeout_seconds=0):
            result = completed(settings,request_id,novel=novel)
            if result is not None:
                return result
            if state.get('export_recovery_state') == 'legacy_unbound_orphan':
                raise CanonicalOperationError('NEWS_EXPORT_LEGACY_UNBOUND_ORPHAN',
                    '导出结果需要重新核对。','请保留原文件，交由有权人员核对；本次不会建立任务。')
            operation = 'novel_news_export' if novel else 'news_export'
            with connect(settings.database_path) as db:
                row = db.execute("SELECT task_id FROM tasks WHERE task_type='excel_export' AND subject_ref=? "
                    "AND operation_identity=? ORDER BY rowid DESC LIMIT 1", (request_id, operation+':'+request_id)).fetchone()
            task = get_task(settings.database_path, row['task_id']) if row else None
            if task and task['status'] == 'failed':
                from news_export_recovery_v1 import identity, paths, read, check, INTENT, NewsExportError
                from .task_service import resume_news_export_task
                from .background_task_service import _news_task_admission
                old = (task['payload'].get('export_context') or {}).get('authorization_context') or {}
                if ((task.get('created_by') or {}).get('user_id') != user_id or old.get('actor') != authorization_context['actor']
                        or old.get('authorization', {}).get('user_state_sha256') != authorization_context['authorization']['user_state_sha256']):
                    raise CanonicalOperationError('NEWS_EXPORT_AUTHORIZATION_CHANGED', '原导出身份或授权已变化。',
                        '请保留原操作并交由有权人员核对，本次不会创建替代任务。')
                directory = settings.pipeline_root / ('data/generation_batches' if novel else 'data/news_deliveries') / request_id
                intent_path = paths(directory)['intent']
                try:
                    intent = check(read(intent_path), INTENT) if intent_path.is_file() else None
                    identity(authorization_context, intent)
                    if intent and (intent['request_id'] != request_id or intent['business_id'] != state['business_id']):
                        raise NewsExportError('NEWS_EXPORT_PUBLICATION_CONFLICT')
                except NewsExportError as exc:
                    raise CanonicalOperationError(exc.code, '原导出需要重新核对。', '来源或授权已变化，原文件与记录会保留。') from exc
                with _news_task_admission(settings, request_id, operation):
                    task = resume_news_export_task(settings.database_path, task['task_id'], authorization_context,
                        queue_max=settings.task_queue_max)
                return {'response_version':'content-operation-response-v1.1','accepted':True,'task':task,'recovered':True}
            task = create_background_task(settings,operation='novel_news_export' if novel else 'news_export',
                request_id=request_id,created_by_user_id=user_id,
                export_context={'authorization_context':authorization_context})
            return {'response_version':'content-operation-response-v1.1','accepted':True,'task':task}
    except OperationLockTimeout as exc:
        raise CanonicalOperationError('NEWS_EXPORT_OPERATION_BUSY','原导出正在进行中。','请稍后查看原操作进度。') from exc
