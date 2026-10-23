"""Session/Task adapters to original C07 Human and C08 Delivery owners."""
from .canonical_gateway import CanonicalOperationError
from .novel_news_gateway import _run
from .database import connect
from .task_service import get_task,submit_task,STANDARD_BACKGROUND
from .creation_batch_gateway import translated
import native_batch_v1 as batch_owner


def _allowed(settings,batch_id,context,*,slot_ids=None,require_publish=True):
    if require_publish and not settings.publish_copy_enabled:
        raise CanonicalOperationError('PUBLISH_COPY_DISABLED','发布与完整交付暂未开放。','已有原生创作与审核会保留。')
    batch_owner.assert_principal(settings.pipeline_root,batch_id,context)
    if slot_ids and any(g['source_kind']=='novel_content' and g['profile']=='news' and
            any(s['slot_id'] in slot_ids for s in g['slots']) for g in batch_owner.groups(settings.pipeline_root,batch_id)):
        from .novel_news_rollout import require_novel_news_task
        require_novel_news_task(settings,context['actor']['user_id'])


@translated
def owner(settings,batch_id,command,context=None,**payload):
    selected=payload.get('slot_ids') or [v['slot_id'] for v in payload.get('items',[])]
    if context is not None:_allowed(settings,batch_id,context,slot_ids=selected,
        require_publish=command!='commands' and payload.get('scope')!='native_content_review')
    script='creation_batch_review_v1.py' if command in {'options','execute','commands'} else 'creation_delivery_v1.py'
    # Forty-item reads revalidate every Native parent (observed >60s). Export
    # repeats that work before, inside and after the original publication fence.
    # Only this bounded local adapter gets extra time: no model credentials,
    # larger mutation budget, concurrency or approval bypass is granted.
    local_seconds = 600 if command=='composite-export' else 180
    deadline={'local_timeout_seconds':local_seconds} if command=='execute' or command.startswith('composite-') else {}
    result=_run(settings,script,[command,'--pipeline-root',str(settings.pipeline_root),'--batch-id',batch_owner.identifier(batch_id)],
        payload={**({'authorization_context':context} if context is not None else {}),**payload},**deadline)['result']
    if context is not None and command=='composite-version':_allowed(settings,batch_id,context,slot_ids=result['slot_ids'])
    if context is not None and command=='composite-list':
        visible=[]
        for delivery in result['completed']:
            try:_allowed(settings,batch_id,context,slot_ids=delivery['slot_ids'])
            except CanonicalOperationError as exc:result['blocked'].append({'delivery_id':delivery['delivery_id'],'code':exc.code})
            else:visible.append(delivery)
        result['completed']=visible
    if context is not None and command=='options':
        from .novel_news_rollout import require_novel_news_task
        try:require_novel_news_task(settings,context['actor']['user_id'])
        except CanonicalOperationError:
            lookup={s['slot_id']:g for g in batch_owner.groups(settings.pipeline_root,batch_id) for s in g['slots']}
            blocked=[v for v in result['items'] if lookup[v['slot_id']]['profile']=='news' and lookup[v['slot_id']]['source_kind']=='novel_content']
            result['items']=[v for v in result['items'] if v not in blocked]
            result['excluded'].extend({'request_id':lookup[v['slot_id']]['request_id'],'code':'NOVEL_NEWS_NOT_AVAILABLE'} for v in blocked)
            # Preserve Native source_sha256: the selected visible subset is
            # still bound to that exact full Native preview, never re-signed.
    return result


@translated
def submit_export(settings,batch_id,context,*,scope,slot_ids,operation_id,source_sha256):
    _allowed(settings,batch_id,context,slot_ids=slot_ids);batch_owner.identifier(operation_id)
    execution={'scope':scope,'slot_ids':slot_ids,'operation_id':operation_id,'source_sha256':source_sha256}
    key='creation-batch-delivery:'+batch_owner.digest({'batch_id':batch_id,'actor':context['actor'],
        'scope':scope,'slot_ids':slot_ids,'source_sha256':source_sha256})
    with connect(settings.database_path) as db:
        rows=db.execute("SELECT task_id FROM tasks WHERE operation_identity=? OR (subject_ref=? AND created_by_user_id=? "
            "AND json_extract(payload_json,'$.operation')='creation_batch_export' AND json_extract(payload_json,'$.creation_batch_delivery.operation_id')=?) "
            "ORDER BY rowid DESC",(key,batch_id,context['actor']['user_id'],operation_id)).fetchall()
    for item in rows:
        existing=get_task(settings.database_path,item['task_id'])
        saved=existing['payload'].get('creation_batch_delivery') or {}
        if (any(saved.get(k)!=execution[k] for k in ('scope','slot_ids','source_sha256'))
                or existing['subject_ref']!=batch_id or existing['created_by']['user_id']!=context['actor']['user_id']
                or (saved.get('authorization_context') or {}).get('actor')!=context['actor']):
            raise CanonicalOperationError('CREATION_BATCH_DELIVERY_CONFLICT','原交付操作的范围或来源已变化。','请核对已有交付；修改范围需要明确新操作。')
    row=rows[0] if rows else None
    if row:
        task=get_task(settings.database_path,row['task_id']);original=task['payload'].get('creation_batch_delivery') or {}
        completed=task_completion(settings,batch_id,original)
        if completed:
            if task['status']=='failed':
                from .task_service import update_task
                update_task(settings.database_path,task['task_id'],status='completed',progress=100,stage='原生交付已核对完成')
                task=get_task(settings.database_path,task['task_id'])
            return {'accepted':False,'task':task,'canonical_result':completed}
        if task['status'] in {'queued','running'}:return {'accepted':True,'task':task}
    preview=owner(settings,batch_id,'composite-preview',context,scope=scope,slot_ids=slot_ids)
    if preview['source_sha256']!=source_sha256:
        raise CanonicalOperationError('CREATION_BATCH_DELIVERY_PREFLIGHT_STALE','交付来源已变化。','请重新核对准确的已批准内容与发布版本。')
    if row:
        if task['status']!='failed':
            raise CanonicalOperationError('CREATION_BATCH_DELIVERY_RECOVERY_REQUIRED','原任务缺少完整交付证明。','请保留原任务和文件，核对原发布与交付记录。')
        from .task_service import resume_creation_batch_delivery_task
        task=resume_creation_batch_delivery_task(settings.database_path,task['task_id'],context,queue_max=settings.task_queue_max)
    else:
        task=submit_task(settings.database_path,task_id_prefix='creation_batch_export',task_type='excel_export',subject_ref=batch_id,
            operation_identity=key,execution_lane=STANDARD_BACKGROUND,payload={'operation':'creation_batch_export','request_id':batch_id,
                'creation_batch_delivery':{**execution,'authorization_context':context}},stage='汇总本批已确认交付',
            created_by_user_id=context['actor']['user_id'],queue_max=settings.task_queue_max,gpu_pending_per_user_max=settings.gpu_pending_per_user_max)
    return {'accepted':True,'task':task}


def export(settings,batch_id,**payload):
    context=payload.pop('authorization_context')
    return owner(settings,batch_id,'composite-export',context,**payload)


def task_completion(settings,batch_id,execution):
    result=owner(settings,batch_id,'composite-operation',operation_id=execution['operation_id'],expected_actor=execution['authorization_context']['actor'])
    if result and any(result[k]!=execution[k] for k in ('scope','slot_ids','source_sha256')):
        raise CanonicalOperationError('CREATION_BATCH_DELIVERY_CONFLICT','交付证明与原任务范围不一致。','请保留原任务及交付记录，核对准确来源。')
    return result
