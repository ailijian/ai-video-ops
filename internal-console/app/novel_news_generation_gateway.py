"""Thin local Session admission; Native Novel News owns attempt semantics."""
from .canonical_gateway import CanonicalOperationError
from .database import connect
from .task_service import get_task, resume_novel_generation_task


def submit(settings, request_id, user_id, authorization_context, *, expected_parent=None):
    from novel_news_v1 import prepare_novel_news_generation
    from novel_news_generation_recovery_v1 import commit_lock, head, record, GenerationError, mutation_fence
    from .novel_news_gateway import novel_news_state
    from .background_task_service import create_background_task
    from news_export_recovery_v1 import current_authority
    try:
        state = novel_news_state(settings, request_id)
        if state.get('generation', {}).get('ready_for_human_review') or state.get('stage') == 'completed':
            with connect(settings.database_path) as db:
                row = db.execute("SELECT task_id FROM tasks WHERE subject_ref=? AND "
                    "json_extract(payload_json,'$.operation')='novel_news_generate' ORDER BY rowid DESC LIMIT 1",
                    (request_id,)).fetchone()
            return {'accepted': False, 'canonical_result': state,
                    'task': get_task(settings.database_path, row['task_id']) if row else None}
        # A pre-protocol execution cannot be inferred to have never called.
        with connect(settings.database_path) as db:
            legacy = db.execute("SELECT task_id FROM tasks WHERE subject_ref=? AND "
                "json_extract(payload_json,'$.operation')='novel_news_generate' AND "
                "json_extract(payload_json,'$.novel_generation') IS NULL AND (attempt_count>0 OR status='running')",
                (request_id,)).fetchone()
        if legacy and head(settings.pipeline_root, request_id) is None:
            raise GenerationError('LEGACY_OUTCOME_UNKNOWN')
        attempt = prepare_novel_news_generation(pipeline_root=settings.pipeline_root, request_id=request_id,
            authorization_context=authorization_context, expected_parent=expected_parent)
        # Same lock order as Native admission/publication. Never spawn a status
        # child while holding these Windows cross-process fences.
        with mutation_fence(settings.pipeline_root), current_authority(settings.pipeline_root,
            attempt['intent']['snapshot']['authority_binding']), commit_lock(settings.pipeline_root, request_id):
            if head(settings.pipeline_root, request_id)['sha256'] != attempt['sha256']:
                raise GenerationError('SUPERSEDED')
            with connect(settings.database_path) as db:
                row = db.execute('SELECT task_id FROM tasks WHERE operation_identity=? ORDER BY rowid DESC LIMIT 1',
                                 (attempt['intent']['task_operation_identity'],)).fetchone()
            if row:
                task = get_task(settings.database_path, row['task_id'])
                record(settings.pipeline_root, request_id, attempt, 'task', task_id=task['task_id'],
                       task_operation_identity=attempt['intent']['task_operation_identity'])
                generation = state['generation']
                if task['status'] == 'failed' and generation['recovery_state'] in {'not_dispatched', 'validated_result_unpublished'}:
                    task = resume_novel_generation_task(settings.database_path, task['task_id'],
                        authorization_context, queue_max=settings.task_queue_max)
                return {'accepted': task['status'] in {'queued', 'running'}, 'task': task}
            identity = {'operation_id': attempt['operation_id'], 'intent_sha256': attempt['sha256'],
                        'authorization_context': authorization_context}
            task = create_background_task(settings, operation='novel_news_generate', request_id=request_id,
                created_by_user_id=user_id, novel_generation=identity)
            record(settings.pipeline_root, request_id, attempt, 'task', task_id=task['task_id'],
                   task_operation_identity=attempt['intent']['task_operation_identity'])
            return {'accepted': True, 'task': task}
    except RuntimeError as exc:
        if isinstance(exc, CanonicalOperationError):
            raise
        code = getattr(exc, 'code', 'NEWS_GENERATION_SOURCE_CHANGED')
        unknown = code in {'NEWS_GENERATION_OUTCOME_UNKNOWN', 'NEWS_GENERATION_LEGACY_OUTCOME_UNKNOWN'}
        raise CanonicalOperationError(code, '当前新闻体生成不能继续原执行。',
            '模型执行结果无法确认，系统不会自动重复生成。重新尝试需要明确确认，可能产生额外费用。' if unknown
            else '请核对当前客户、创作参考、权限与原操作进度；原记录会保留。') from exc
