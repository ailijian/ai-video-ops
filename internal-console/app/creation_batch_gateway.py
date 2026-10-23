"""Console orchestration of original Native owners; no new business Authority."""
from __future__ import annotations

from functools import wraps
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import native_batch_v1 as native
from creation_batch_contract_v1 import BatchError
from creative_style_v1 import CreativeStyleError
from human_review_operations_v1 import io_path, read, file_sha
from generation_request_handoff_v1 import GenerationRequestError

from .canonical_gateway import CanonicalOperationError
from .content_delivery_gateway import get_content_delivery_state
from .novel_news_gateway import novel_news_state
from .database import connect
from .task_service import get_task
from operation_lock_v1 import operation_lock, OperationLockTimeout


def translated(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except CanonicalOperationError:
            raise
        except OperationLockTimeout as exc:
            if function.__name__ == 'advance' and exc.key.startswith('creation-batch-coordinator:'):
                return {'advanced': False, 'reason': 'coordinator_in_progress'}
            raise CanonicalOperationError(exc.code, '当前操作正在进行。', '请稍后刷新已有任务。') from exc
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            code = getattr(exc, 'code', 'CREATION_BATCH_OPERATION_INVALID')
            message = {
                'CREATION_BATCH_PREFLIGHT_STALE':'客户资料、所选来源或批准版本已变化，请重新核对创作资格。',
                'CREATION_BATCH_REPURPOSE_SELECTION_REQUIRED':'改编数量与已选历史内容不一致，请明确选择相同数量的不同内容。',
                'NEWS_DELIVERY_CONTENT_LEDGER_MISSING':'当前客户还没有已交付、可供改编的历史内容。',
            }.get(code,'本批创作需要重新核对配置、来源或原生资格。')
            raise CanonicalOperationError(code, message,
                '已有成果和原操作会保留；未知模型结果不会自动重发。') from exc
    return call


def task_for(settings, request_id, operation):
    with connect(settings.database_path) as db:
        row = db.execute("SELECT task_id FROM tasks WHERE subject_ref=? AND json_extract(payload_json,'$.operation')=? ORDER BY rowid DESC LIMIT 1",
                         (request_id, operation)).fetchone()
    return get_task(settings.database_path, row['task_id']) if row else None


def require_batch_channels(settings, configuration, context):
    if configuration.get('quantities', {}).get('novel'):
        from .novel_news_rollout import require_novel_news_task
        require_novel_news_task(settings, context['actor']['user_id'])


@translated
def preview(settings, business_id, speaker_id, configuration, context, operation_id):
    require_batch_channels(settings, configuration, context)
    try:
        return native.preview(settings.pipeline_root, business_id, speaker_id, configuration, context, operation_id)
    except BatchError as exc:
        # Explain a rejected Native preflight using only its existing readers.
        # This projection never changes the selected count, source, or approval.
        quantities = configuration.get('quantities', {})
        if exc.code == 'CREATION_BATCH_SOURCE_CAPACITY' and quantities.get('novel', 0) > 0:
            from novel_news_opportunity_v1 import project_novel_news_opportunities
            options = project_novel_news_opportunities(pipeline_root=settings.pipeline_root,
                business_id=business_id, speaker_id=speaker_id)
            count = sum(item['novelty_status'] == 'novel' and item['production_feasibility'].get('status') == 'supported'
                        for item in options['opportunities'])
            if count < quantities['novel']:
                raise CanonicalOperationError(exc.code,
                    f"当前仅有 {count} 个符合条件的新主题，本次填写 {quantities['novel']} 条，请调整数量。",
                    '不会减少目标或自动改用已有内容；调整后请重新核对创作资格。') from exc
        if exc.code == 'CREATION_BATCH_REPURPOSE_SOURCE_UNAVAILABLE':
            from news_delivery_v1 import preview_news_delivery
            options = preview_news_delivery(pipeline_root=settings.pipeline_root,business_id=business_id,speaker_id=speaker_id)
            eligible = {item['source_content_id'] for item in options['eligible_sources']}
            missing = [str(index+1) for index,source_id in enumerate(configuration.get('repurposeSourceIds', [])) if source_id not in eligible]
            raise CanonicalOperationError(exc.code,
                '所选已有内容第 ' + '、'.join(missing) + ' 项当前不符合改编资格，请重新选择。' if missing else '已有内容资格已变化，请重新核对。',
                '请重新读取当前客户的合法历史来源，不会替换为其他内容。') from exc
        raise


@translated
def history(settings,business_id,context):
    from .customer_gateway import get_customer_detail
    get_customer_detail(settings,business_id)
    return native.list_for_business(settings.pipeline_root,business_id,context)


@translated
def confirmed_configuration(settings,business_id,context,operation_id,draft):
    return native.confirmation_for_operation(settings.pipeline_root,business_id,context,operation_id,
        configuration_value=draft['configuration'],speaker_id=draft['speaker_id'])


@translated
def confirm(settings, business_id, speaker_id, configuration, context, operation_id, preflight_sha256):
    require_batch_channels(settings, configuration, context)
    return native.confirm(settings.pipeline_root, business_id, speaker_id, configuration, context, operation_id, preflight_sha256)


@translated
def control(settings, batch_id, action, context, operation_id):
    event = native.control(settings.pipeline_root, batch_id, action, context, operation_id)
    latest = native.controls(settings.pipeline_root, batch_id)[-1]
    resumed = (resume_local_tasks(settings, batch_id, context, operation_id)
               if action == 'resume' and latest['action'] == 'resume'
               and latest['actor_intent']['operation_id'] == operation_id else [])
    settled=[]
    if latest['action']=='end':
        try:settled=native.settle(settings.pipeline_root,batch_id)
        except (RuntimeError,OSError,ValueError) as exc:
            settled=[{'request_id':g['request_id'],'event':'retained','code':getattr(exc,'code','CONTENT_SETTLEMENT_INVALID')}
                     for g in native.groups(settings.pipeline_root,batch_id)]
    from .task_service import end_unissued_batch_tasks
    ended=end_unissued_batch_tasks(settings.database_path,
        [s['request_id'] for s in settled if s.get('kind','').startswith('cancelled_')],user_id=context['actor']['user_id']) if settled else []
    return {'control':event, 'local_continuations':resumed,'settlements':settled,'ended_unissued_tasks':ended}


def resume_local_tasks(settings, batch_id, context, operation_id):
    root = settings.pipeline_root
    resumed = []
    for group in native.groups(root, batch_id):
        rid = group['request_id']
        path = native.request_path(root,rid)
        if not io_path(path).is_file():
            continue
        request = read(path)
        native.validate_admission(request['batch_admission_ref'], root=root, context=context, request=request)
        if group['source_kind']=='cross_profile_repurpose':
            from news_delivery_v1 import request_cancelled
            task=task_for(settings,rid,'news_plan')
            if task and task['status']=='failed' and not request_cancelled(root,rid) and not native.known_local_outcome(root,rid):
                from .task_service import resume_creation_batch_task
                resumed.append({'task':resume_creation_batch_task(settings.database_path,task['task_id'],context,
                    operation_id,queue_max=settings.task_queue_max)})
            continue
        if group['profile'] == 'news':
            task = task_for(settings, rid, 'novel_news_generate')
            if task and task['status'] == 'failed':
                actual = novel_news_state(settings, rid)
                if actual['generation']['recovery_state'] in {'not_dispatched', 'validated_result_unpublished'}:
                    from .novel_news_generation_gateway import submit
                    resumed.append(submit(settings, rid, context['actor']['user_id'], context))
            continue
        from batch_provider_recovery_v1 import phase_state, read_native_result, assert_current, snapshot
        provider = phase_state(root, request)
        if provider['unknown']:
            continue
        for stage in ('content_plan', 'script_generation'):
            task = task_for(settings, rid, stage)
            if not task or task['status'] != 'failed':
                continue
            outcome = read_native_result(root, request, stage)
            if outcome and outcome['kind'] in {'generation_rejected', 'quality_capacity_zero'}:
                continue
            assert_current(root, request, stage)
            snapshot(root, request)
            recovery_identity = task['payload'].get('generation_recovery')
            if recovery_identity:
                # C3-05 compares its entire immutable submission payload. Use
                # its original continuation rather than adding Batch metadata.
                import generation_recovery_v1 as recovery
                intent_path = recovery.operation_root(root, rid, recovery_identity['operation_id'])/'intent.json'
                original = recovery.check(read(intent_path), recovery.INTENT)
                if (recovery.file_sha(intent_path) != recovery_identity['intent_sha256']
                        or original['request_id'] != rid or original['actor'] != context['actor']
                        or task['payload'].get('request_id') != rid
                        or task['created_by']['user_id'] != context['actor']['user_id']):
                    raise BatchError('CREATION_BATCH_TASK_INVALID', 'Native retry does not bind the original Batch principal/Request')
                recovery.verify_authorization(original)
                from .task_service import resume_generation_recovery_task
                continued = resume_generation_recovery_task(settings.database_path, task['task_id'], queue_max=settings.task_queue_max)
            else:
                from .task_service import resume_creation_batch_task
                continued = resume_creation_batch_task(settings.database_path, task['task_id'], context,
                    operation_id, queue_max=settings.task_queue_max)
            resumed.append({'task':continued})
    if settings.publish_copy_enabled:
        from .publish_copy_gateway import project, submit
        for group in native.groups(root, batch_id):
            task = task_for(settings, group['request_id'], 'publish_copy_generate')
            if not task or task['status'] != 'failed': continue
            actual = project(settings, group['request_id'])
            if actual['state'] in {'not_dispatched', 'validated_result_unpublished'}:
                from profile_compatibility_decisions_v1_1 import resolve_ref
                original=read(resolve_ref(root,actual['attempt_ref']))
                if (original.get('batch_intent_ref')!=native.batch_ref(root,batch_id)
                        or original.get('actor')!=context['actor']
                        or original.get('operation_id')!=(task['payload'].get('publish_copy') or {}).get('operation_id')):
                    continue  # Preserve the unchanged manual/legacy recovery.
                resumed.append(submit(settings, group['request_id'], 'publish_copy_generate',
                    context['actor']['user_id'], context, automatic_batch_ref=native.batch_ref(root, batch_id)))
    return resumed


@translated
def admit_group(settings, batch_id, group_id, context):
    """Short coordinator admission, then original writer lock, never a nested child lock."""
    root = settings.pipeline_root
    _, batch = native.intent(root, batch_id)
    group = next((g for g in native.groups(root, batch_id) if g['group_id'] == group_id), None)
    if group is None:
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Unknown confirmed group')
    if group['profile'] == 'news' and group['source_kind'] == 'novel_content':
        from .novel_news_rollout import require_novel_news_task
        require_novel_news_task(settings, context['actor']['user_id'])
    from generation_request_handoff_v1 import _business_generation_lock, create_generation_request_handoff
    from .operation_lock import authority_mutation_barrier
    with authority_mutation_barrier(settings), _business_generation_lock(root, batch['business_id']):
        reference = native.admission(root, batch_id, group_id, context)
    # This direct call is still the original Console gateway/Native writer and
    # acquires its own original Business/Compatibility fences after release.
    speaker = next(r['id'] for r in batch['context_refs'] if r['owner'] == 'native-speaker')
    kind = (group['creative_style'] or {}).get('style_id')
    quantity = len(group['slots'])
    config = {'mode': 'free', 'revision': 0, 'quantities': {k: quantity if k == kind else 0 for k in native.TYPES}}
    choice = next((r['id'] for s in group['slots'] for r in s['source_refs'] if r['owner'] == 'native-novel-opportunity'), None)
    from delivery_receipt_recovery_v1 import actor_phone
    with authority_mutation_barrier(settings):
        if group['source_kind']=='cross_profile_repurpose':
            from news_delivery_v1 import create_news_delivery_request
            source_id=next(r['id'] for s in group['slots'] for r in s['source_refs'] if r['owner']=='native-repurpose-source')
            request,recovered=create_news_delivery_request(pipeline_root=root,business_id=batch['business_id'],speaker_id=speaker,
                source_content_id=source_id,idempotency_key=group['operation_id'],created_by_user_id=context['actor']['user_id'],
                created_by_phone=actor_phone(context),batch_admission_ref=reference,authorization_context=context)
            return {'request':request,'recovered':recovered}
        return create_generation_request_handoff(pipeline_root=root, business_id=batch['business_id'],
            speaker_id=speaker, profile=group['profile'], requested_quantity=quantity, confirmed_quantity=quantity,
            idempotency_key=group['operation_id'], creative_style_id=kind, configuration=config if kind else None,
            selected_opportunity_id=choice, authorization_context=context,
            created_by_user_id=context['actor']['user_id'], created_by_phone=actor_phone(context), batch_admission_ref=reference)


def _group_entry(group):
    return {'group_id':group['group_id'],'request_id':group['request_id'],'profile':group['profile'],
        'source_kind':group['source_kind'],'style_id':(group['creative_style'] or {}).get('style_id'),
        'slot_ids':[s['slot_id'] for s in group['slots']], 'target':len(group['slots']),
        'stage':'not_admitted','native':None,'generated':0,'approved':0,'rejected':0,'unknown':False,
        'slots':[{'slot_id':s['slot_id'],'business_type_id':s['business_type_id'],'source_kind':s['source_kind'],
            'generated':False,'approved':False,'rejected':False,'native_exported':False,'delivered':False,
            'status':'not_admitted'} for s in group['slots']]}


def _active_task(task):
    if task['status']=='queued':return True
    if task['status']!='running' or not task.get('lease_expires_at'):return False
    from datetime import datetime,timezone
    return datetime.fromisoformat(task['lease_expires_at'].replace('Z','+00:00'))>datetime.now(timezone.utc)


def _execution_attention(group):
    if group.get('cancelled'):return False
    publish=group.get('publish') or {}
    for task in group.get('tasks',[]):
        if task['status']!='failed':continue
        operation=task['payload']['operation']
        if operation in {'content_plan','script_generation','novel_news_generate','news_plan'}:
            if not (group.get('review_ready') or group.get('review_complete') or group.get('local_outcome')):return True
        elif operation=='publish_copy_generate':
            if publish.get('state')!='draft_ready':return True
        elif operation=='publish_copy_export':
            expected=(task['payload'].get('publish_copy') or {}).get('expected_draft_ref')
            current=(publish.get('draft') or {}).get('ref')
            delivered=(publish.get('delivery') or {}).get('draft_ref')
            if delivered is not None and delivered==(expected or current):continue
            # A new explicit draft supersedes an earlier failed version; its
            # readiness is still determined from its own confirmation/parent.
            if expected is not None and current is not None and expected!=current:continue
            return True
    return False


def _mix_review_source(root, rid):
    """Full original Human/source proof, local to one state read."""
    from delivery_receipt_recovery_v1 import human_state
    from generation_recovery_v1 import validate_approved_source
    base=root/'data/generation_batches'/rid
    if not human_state(base)['completed']:
        return None
    receipt_path=base/'generation_batch_approval_receipt.json'
    receipt_sha=file_sha(receipt_path);receipt=read(receipt_path)
    reviewed=base/('approved_generation_batch_v1.json' if receipt['status']=='approved' else 'reviewed_generation_batch_v1.json')
    reviewed_sha=file_sha(reviewed)
    validate_approved_source(root,rid,read(reviewed),receipt)
    if file_sha(receipt_path)!=receipt_sha or file_sha(reviewed)!=reviewed_sha:
        raise CanonicalOperationError('CREATION_BATCH_REVIEW_SOURCE_CHANGED','审核来源正在变化。','请刷新核对原审核结果。')
    source=Path(receipt['source_batch']['path'])
    return {'receipt':receipt,'receipt_path':receipt_path,'receipt_sha':receipt_sha,
        'reviewed':reviewed,'reviewed_sha':reviewed_sha,'source':source if source.is_absolute() else root/source}


def _current_mix_review_source(root, rid, review, proof):
    # A concurrently completed Human operation may not have existed when the
    # independent reader started. Re-enter the original proof in that case.
    proof=proof or _mix_review_source(root,rid)
    if (not proof or review.get('sha256')!=proof['reviewed_sha']
            or bool(review['approved'])!=(proof['receipt']['status']=='approved')
            or file_sha(proof['receipt_path'])!=proof['receipt_sha']
            or file_sha(proof['reviewed'])!=proof['reviewed_sha']):
        raise CanonicalOperationError('CREATION_BATCH_REVIEW_SOURCE_CHANGED','审核来源正在变化。','请刷新核对原审核结果。')
    return proof['source']


@translated
def _native_group_projection(settings, batch_id, context, group, *, defer_results=False):
    root = settings.pipeline_root
    request_path = native.request_path(root, group['request_id'])
    entry = _group_entry(group)
    if io_path(request_path).is_file():
        request = read(request_path)
        if defer_results:
            native.admission_binding(request['batch_admission_ref'], root=root, request=request)
        else:
            native.validate_admission(request['batch_admission_ref'], root=root, request=request)
        if group['profile'] == 'news' and group['source_kind'] == 'novel_content':
            from .novel_news_rollout import require_novel_news_task
            require_novel_news_task(settings, context['actor']['user_id'])
        entry['admitted']=True
        entry['tasks']=[t for op in ('content_plan','script_generation','novel_news_generate','news_plan')
            if (t:=task_for(settings,group['request_id'],op)) is not None]
        if defer_results or any(_active_task(t) for t in entry['tasks']):
            # Native generation may hold its Compatibility read fence
            # across RPC latency. Task progress is an execution projection,
            # not proof of output, Human approval or delivery.
            in_flight=any(_active_task(t) for t in entry['tasks'])
            entry.update(stage='generating' if in_flight else 'verifying_results',in_flight=in_flight,review_ready=False,review_complete=False)
            for slot in entry['slots']:slot.update(status=entry['stage'],verification_pending=True)
            return entry
        mix_review=None
        if group['profile']=='mix':
            # Both readers retain all original validation. Overlap only their
            # read-only work, then bind exact Receipt/approved bytes below.
            # The outer state pool bounds this to two groups (four readers).
            with ThreadPoolExecutor(max_workers=1,thread_name_prefix='batch-human-read') as reader:
                proof=reader.submit(_mix_review_source,root,group['request_id'])
                entry['native']=get_content_delivery_state(settings,group['request_id'])
                mix_review=proof.result()
        elif group['source_kind']=='cross_profile_repurpose':
            from .news_delivery_gateway import get_news_delivery_state
            entry['native']=get_news_delivery_state(settings,group['request_id'])
            entry['cancelled']=entry['native'].get('cancelled',False)
        else:entry['native']=novel_news_state(settings,group['request_id'])
        entry['stage'] = entry['native'].get('next_action') or entry['native'].get('stage')
        ns = entry['native']
        if group['profile'] == 'mix':
            from batch_provider_recovery_v1 import phase_state, validated_local_outcome
            provider = phase_state(root, request)
            entry['provider'] = provider
            generated = int(ns['generation']['generated_count']) if ns['generation']['ready'] else 0
            reviewed_source=None
            if ns['review']['completed']:
                reviewed_source=_current_mix_review_source(root,group['request_id'],ns['review'],mix_review)
                generated=len(read(reviewed_source)['contents'])
            outcome = (validated_local_outcome(root, request)
                       if not ns['generation']['ready'] and not ns['review']['completed'] and not provider['unknown'] else None)
            if outcome:
                generated = outcome['generated_count']
                entry['local_outcome'] = outcome
            approved = int(ns['review'].get('approved_item_count') or 0) if ns['review']['completed'] else 0
            rejected = int(ns['review'].get('rejected_item_count') or 0) if ns['review']['completed'] else 0
            entry['review_complete'] = ns['review']['completed']
            entry['review_ready'] = ns['generation']['ready']
            entry['unknown'] = provider['unknown']
        elif group['source_kind']=='cross_profile_repurpose':
            from news_delivery_v1 import _request_root,_review_path,_approved_path
            from news_export_recovery_v1 import verify_native_human_bundle
            base=_request_root(root,group['request_id'])
            human=io_path(_approved_path(root,group['request_id'])).is_file()
            if human:verify_native_human_bundle(root,request=request_path,plan=base/'news_delivery_plan_v1.json',
                review=_review_path(root,group['request_id']),approved=_approved_path(root,group['request_id']),kind='repurpose')
            generated=int(native.known_local_outcome(root,group['request_id']))
            approved,rejected=int(human),0
            entry.update(review_complete=human,review_ready=bool(generated),unknown=False)
        else:
            from news_export_recovery_v1 import verify_native_human_bundle
            from novel_news_v1 import _paths
            paths = _paths(root, group['request_id'])
            human = io_path(paths['approved']).is_file()
            if human:
                verify_native_human_bundle(root, request=paths['request'], plan=paths['plan'],
                    review=paths['review'], approved=paths['approved'], kind='novel')
            generated = int(ns['generation']['ready_for_human_review'])
            approved, rejected = int(human), 0
            entry['review_complete'] = human
            entry['review_ready'] = ns['generation']['ready_for_human_review']
            entry['unknown'] = ns['generation']['recovery_state'] in {'dispatched_outcome_unknown', 'legacy_outcome_unknown'}
        entry.update(generated=generated, approved=approved, rejected=rejected,
                     native_exported=approved if ns.get('stop_point_reached') or ns.get('stage') == 'completed' else 0)
        entry['tasks'] = [t for op in ('content_plan', 'script_generation', 'novel_news_generate','news_plan')
                          if (t := task_for(settings, group['request_id'], op)) is not None]
        if group['profile']=='mix':
            from generation_recovery_v1 import graph
            from creative_style_v1 import artifact
            path=reviewed_source or graph(root,group['request_id'])['batch']
            raw=read(path) if generated else {'contents':[]}
            contents={c['logical_slot_id']:c for c in raw['contents']}
            base=root/'data/generation_batches'/group['request_id']
            accepted={c['content_id'] for c in read(base/'approved_generation_batch_v1.json')['contents']} if approved else set()
            rejected_ids={c['content_id'] for c in read(base/'generation_human_review_v2.json')['items'] if c['decision']=='rejected'} if rejected else set()
            for slot in entry['slots']:
                content=contents.get(slot['slot_id'])
                if content:
                    slot.update(generated=True,content_id=content['content_id'],final_concept_id=content['concept_ref'],
                        native_content_ref=artifact(path,'native-generation-result',content['content_id'],raw['schema_version']),
                        approved=content['content_id'] in accepted,rejected=content['content_id'] in rejected_ids)
        else:
            slot=entry['slots'][0]
            if generated:
                slot.update(generated=True,content_id=group['request_id']+('-P001' if group['source_kind']=='cross_profile_repurpose' else '-N001'),
                    final_concept_id=request['source_content_id'] if group['source_kind']=='cross_profile_repurpose' else request['selected_content']['concept_id'])
            slot.update(approved=bool(approved),rejected=bool(rejected))
        for slot in entry['slots']:
            slot['native_exported']=slot['approved'] and entry['native_exported']>0
            slot['unknown']=entry['unknown']
            slot['generation_failed']=entry.get('local_outcome',{}).get('kind')=='generation_rejected' and not slot['generated']
            slot['status']=('cancelled' if entry.get('cancelled') else 'unknown' if slot['unknown'] else 'human_approved' if slot['approved'] else 'human_rejected' if slot['rejected']
                else 'awaiting_review' if slot['generated'] else 'failed' if slot['generation_failed'] else 'missing')
    return entry


@translated
def state(settings,batch_id,context):
    root=settings.pipeline_root;native.assert_principal(root,batch_id,context)
    _,batch=native.intent(root,batch_id);controls=native.controls(root,batch_id)
    groups=native.groups(root,batch_id)
    defer_results=any(_active_task(t) for g in groups for op in ('content_plan','script_generation','novel_news_generate','news_plan')
        if (t:=task_for(settings,g['request_id'],op)) is not None)
    def project_group(group):
        try:entry=_native_group_projection(settings,batch_id,context,group,defer_results=defer_results)
        except CanonicalOperationError as exc:
            entry=_group_entry(group);entry.update(stage='source_blocked',error_code=exc.code,verification_pending=True)
            for slot in entry['slots']:slot.update(status='source_blocked',verification_pending=True)
        if entry['approved'] and settings.publish_copy_enabled:
            try:
                from .publish_copy_gateway import project
                tasks=[t for op in ('publish_copy_generate','publish_copy_export') if (t:=task_for(settings,group['request_id'],op)) is not None]
                entry['tasks']=[*entry.get('tasks',[]),*tasks]
                if any(_active_task(t) for t in tasks):entry['publish']={'state':'executing','confirmed':False,'delivery':None}
                else:entry['publish']=project(settings,group['request_id'])
                if entry['publish'].get('delivery'):
                    # The original supplemental reader validates its exact
                    # core Receipt/Closure/Anchor. Legacy Mix's display-name
                    # filename projection may differ from that Native path.
                    entry['native_exported']=entry['approved']
                    for slot in entry['slots']:
                        if slot['approved']:slot['native_exported']=True
                if entry['publish']['state']=='dispatched_outcome_unknown':
                    entry['unknown']=True
                    for slot in entry['slots']:
                        if slot['approved']:slot.update(unknown=True,status='publish_outcome_unknown')
            except CanonicalOperationError as exc:entry['publish']={'state':'blocked','confirmed':False,'code':exc.code}
        return entry
    def project_deliveries():
        deliveries={'completed':[],'blocked':[]}
        if not settings.publish_copy_enabled or defer_results:
            return deliveries
        from .creation_batch_delivery_gateway import owner
        try:deliveries=owner(settings,batch_id,'composite-list',context)
        except CanonicalOperationError as exc:deliveries['blocked'].append({'code':exc.code})
        return deliveries
    # Only independent, read-only Native projections overlap. Each still runs
    # its original validation; no cached approval, model dispatch or writer is
    # introduced. Preserve configured Slot/group order, including failures.
    with ThreadPoolExecutor(max_workers=2,thread_name_prefix='batch-read') as readers:
        group_futures=[readers.submit(project_group,group) for group in groups]
        projected=[future.result() for future in group_futures]
    # Keep final C08 proof after all group reads: an earlier valid receipt must
    # never overwrite a later source-withdrawal/block observed by a group.
    deliveries=project_deliveries()
    current={s for d in deliveries['completed'] if d['is_current'] for s in d['slot_ids']}
    historical={s for d in deliveries['completed'] for s in d['slot_ids']}
    all_slots=[s for g in projected for s in g['slots']]
    for slot in all_slots:
        if slot['slot_id'] in current:
            # This is the original Delivery owner's complete Native Human +
            # parent Export/Closure proof, not a Task/status inference.
            slot.update(generated=True,approved=True,native_exported=True,delivered=True,status='delivered',verification_pending=False,
                unknown=False,generation_failed=False)
    for group in projected:
        for key in ('generated','approved','rejected','native_exported'):group[key]=sum(s[key] for s in group['slots'])
    counts={'target':len(all_slots),'generated':sum(s['generated'] for s in all_slots),'approved':sum(s['approved'] for s in all_slots),
        'rejected':sum(s['rejected'] for s in all_slots),'delivered':len(current),'historically_delivered':len(historical),
        'native_exported':sum(s['native_exported'] for s in all_slots),'failed':sum(s.get('generation_failed',False) for s in all_slots),
        'unknown':sum(s.get('unknown',False) for s in all_slots),'unverified':sum(s.get('verification_pending',False) for s in all_slots),
        'not_admitted':sum(g['target'] for g in projected if g['stage']=='not_admitted'),
        'new_content_target':sum(s['source_kind']=='novel_content' for s in all_slots),
        'new_semantic_count':sum(s['source_kind']=='novel_content' and s['native_exported'] for s in all_slots),
        'repurpose_presentation_count':sum(s['source_kind']=='cross_profile_repurpose' and s['native_exported'] for s in all_slots)}
    counts['missing_generation']=counts['target']-counts['generated']
    counts['review_pending']=sum(s['generated'] and not s['approved'] and not s['rejected'] for s in all_slots)
    counts['capacity_shortfall']=sum(g['target'] for g in projected if g.get('local_outcome',{}).get('kind')=='quality_capacity_zero')
    control=controls[-1]['action'] if controls else 'resume'
    generation_active=any(_active_task(t) and t['payload']['operation'] in {'content_plan','script_generation','novel_news_generate','news_plan'}
        for g in projected for t in g.get('tasks',[]))
    publish_active=any(_active_task(t) and t['payload']['operation']=='publish_copy_generate' for g in projected for t in g.get('tasks',[]))
    delivery_task=task_for(settings,batch_id,'creation_batch_export')
    delivery_active=_active_task(delivery_task) if delivery_task else False
    delivery_failed=False
    if delivery_task and delivery_task['status']=='failed' and not defer_results:
        from .creation_batch_delivery_gateway import task_completion
        try:delivery_failed=not task_completion(settings,batch_id,delivery_task['payload']['creation_batch_delivery'])
        except CanonicalOperationError:delivery_failed=True
    failed_execution=delivery_failed or any(_execution_attention(g) for g in projected)
    ready=all(g.get('review_ready') or g.get('review_complete') or g.get('local_outcome',{}).get('kind') in
        ('generation_rejected','quality_capacity_zero') for g in projected)
    full=any(d['scope']=='complete_target' and d['is_current'] for d in deliveries['completed'])
    complete=full and control!='end' and counts['unknown']==counts['failed']==counts['unverified']==0
    publishing=[g.get('publish') or {} for g in projected if g['approved']]
    publish_pending=publishing and any(not p.get('confirmed') for p in publishing)
    parent_pending=publishing and any(not p.get('delivery') or p['delivery'].get('draft_ref')!=(p.get('draft') or {}).get('ref') for p in publishing)
    status=('ended_partial' if control=='end' else 'completed' if complete else 'paused' if control=='pause'
        else 'generating' if generation_active or defer_results else 'needs_recovery' if counts['unknown'] else 'needs_attention' if counts['unverified'] or failed_execution
        else 'in_progress' if not ready
        else 'generation_finished_with_gaps' if counts['generated']<counts['target'] else 'awaiting_review' if counts['review_pending']
        else 'preparing_delivery' if delivery_active else 'preparing_publish_copy' if publish_active
        else 'awaiting_publish_confirmation' if publish_pending and all(p.get('draft') for p in publishing)
        else 'preparing_publish_copy' if publish_pending else 'preparing_delivery' if parent_pending
        else 'ready_for_delivery' if counts['approved'] else 'in_progress')
    return {'schema_version':'creation-batch-projection-v1.1','batch_id':batch_id,'business_id':batch['business_id'],
        'control':control,'groups':projected,'counts':counts,'status':status,'completion_proven':complete,
        'delivery_set_complete_proven':full,'deliveries':deliveries,'delivery_task':delivery_task,
        'verification_deferred':defer_results,'execution_needs_attention':failed_execution,
        'generation_quiescent':ready,
        'review_is_native':True,'publish_copy_enabled':settings.publish_copy_enabled}


def _submit_once(settings, rid, operation, context):
    """Completed/failed original Tasks are never replaced by an automatic kick."""
    task = task_for(settings, rid, operation)
    if task is not None:
        return task
    from .background_task_service import create_background_task
    return create_background_task(settings, operation=operation, request_id=rid,
                                  created_by_user_id=context['actor']['user_id'])


def _advance_publishing(settings, batch_id, context):
    """Advance original Publish/parent owners only after content Human gates.

    Failed or unknown operations require explicit Native recovery. A Task is
    never replaced by a maintenance tick and no confirmation is synthesized.
    """
    if not settings.publish_copy_enabled:
        return {'advanced': False, 'reason': 'native_human_review_required'}
    # A missing Native Approved artifact can only stop scheduling. It never
    # proves approval: once any exists, the full Native readers below validate
    # all Human, source, version and Publish gates before another task is issued.
    def approved_path(group):
        rid = group['request_id']
        if group['profile'] == 'mix':
            return settings.pipeline_root / 'data/generation_batches' / rid / 'approved_generation_batch_v1.json'
        if group['source_kind'] == 'novel_content':
            from novel_news_v1 import _paths
            return _paths(settings.pipeline_root, rid)['approved']
        from news_delivery_v1 import _approved_path
        return _approved_path(settings.pipeline_root, rid)
    if not any(io_path(approved_path(g)).is_file() for g in native.groups(settings.pipeline_root, batch_id)):
        return {'advanced': False, 'reason': 'native_human_review_required'}
    current = state(settings, batch_id, context)
    if (not current['generation_quiescent'] or current['verification_deferred']
            or current['counts']['unknown'] or current['counts']['unverified']):
        return {'advanced': False, 'reason': 'native_recovery_required'}
    if current['counts']['review_pending']:
        return {'advanced': False, 'reason': 'native_human_review_required'}
    from .publish_copy_gateway import submit
    reference = native.batch_ref(settings.pipeline_root, batch_id)
    approved = [g for g in current['groups'] if g['approved']]
    if any(_active_task(t) for g in current['groups'] for t in g.get('tasks', [])):
        return {'advanced': False, 'reason': 'native_task_already_exists'}
    blocked = []
    for group in approved:
        publish = group.get('publish') or {}
        if publish.get('draft') or publish.get('confirmed'): continue
        rid = group['request_id']
        if task_for(settings, rid, 'publish_copy_generate') is not None:
            blocked.append(rid); continue
        if publish.get('state') not in ('not_started', 'not_dispatched', 'validated_result_unpublished'):
            blocked.append(rid); continue
        result = submit(settings, rid, 'publish_copy_generate', context['actor']['user_id'], context,
                        automatic_batch_ref=reference)
        return {'advanced': bool(result.get('accepted')), **result, 'phase': 'publish_copy'}
    # Ledger-writing parent exports wait until every generated item has been
    # reviewed and every approved source has its exact Publish confirmation.
    if any(not (g.get('publish') or {}).get('confirmed') for g in approved):
        return {'advanced': False, 'reason': 'native_recovery_required' if blocked else 'publish_confirmation_required'}
    for group in approved:
        publish = group['publish']; rid = group['request_id']
        expected = publish['draft']['ref']
        if (publish.get('delivery') or {}).get('draft_ref') == expected: continue
        previous = task_for(settings, rid, 'publish_copy_export')
        if previous and (previous['payload'].get('publish_copy') or {}).get('expected_draft_ref') == expected:
            blocked.append(rid); continue
        result = submit(settings, rid, 'publish_copy_export', context['actor']['user_id'], context,
                        automatic_batch_ref=reference)
        return {'advanced': bool(result.get('accepted')), **result, 'phase': 'native_parent_delivery'}
    return {'advanced': False, 'reason': 'native_recovery_required' if blocked else 'ready_for_delivery'}


def _human_record_hint(root, group):
    """Select the post-review reader, never prove a Human decision.

    The publishing reader still validates every source and Native review. A
    corrupt/stale hint therefore blocks there and cannot authorize dispatch.
    """
    rid = group['request_id']
    if group['profile'] == 'mix':
        path = root / 'data/generation_batches' / rid / 'generation_batch_approval_receipt.json'
    elif group['source_kind'] == 'novel_content':
        from novel_news_v1 import _paths
        path = _paths(root, rid)['review']
    else:
        from news_delivery_v1 import _review_path
        path = _review_path(root, rid)
    return io_path(path).is_file()


@translated
def advance(settings, batch_id):
    """One local advancement; external calls run only in the existing worker.

    The coordination lock never spans an external RPC or a wait on another
    Task. Every result, permission and source is read from its original owner.
    """
    root = settings.pipeline_root
    _, batch = native.intent(root, batch_id)
    with operation_lock(root, 'creation-batch-coordinator:' + batch['business_id'], timeout_seconds=0.0):
        # Execution state is only a reason to wait, never evidence of content
        # completion. Avoid repeated source scans beside an already queued or
        # running Native operation; the completion path re-enters every gate.
        if native.running(root, batch_id):
            for group in native.groups(root, batch_id):
                for operation in ('content_plan', 'script_generation', 'novel_news_generate', 'news_plan',
                                  'publish_copy_generate', 'publish_copy_export'):
                    task = task_for(settings, group['request_id'], operation)
                    if task and _active_task(task):
                        return {'advanced': False, 'task': task, 'reason': 'native_task_already_exists'}
        settled=native.settle(root,batch_id)
        if settled:
            from .task_service import end_unissued_batch_tasks
            end_unissued_batch_tasks(settings.database_path,
                [s['request_id'] for s in settled if s.get('kind','').startswith('cancelled_')],user_id=int(batch['actor_intent']['actor_id']))
        if not native.running(root, batch_id):
            return {'advanced': False, 'reason': 'paused_or_ended'}
        context = native.current_context(root, batch_id)
        native.policy_qualification(root)
        groups = native.groups(root, batch_id)
        if groups and all(_human_record_hint(root, group) for group in groups):
            # The original post-review state validates these same Native
            # results. Avoid validating the generation projection twice.
            return _advance_publishing(settings, batch_id, context)
        for group in groups:
            rid = group['request_id']
            request = native.request_path(root, rid)
            if not io_path(request).is_file():
                admit_group(settings, batch_id, group['group_id'], context)
            if group['profile'] == 'mix':
                current = get_content_delivery_state(settings, rid)
                if current['next_action'] == 'RESOLVE_GENERATION_SOURCES':
                    from .content_gateway import resolve_generation_sources
                    from .operation_lock import authority_operation_lock
                    with authority_operation_lock(settings, 'request', rid, timeout_seconds=0.0):
                        resolve_generation_sources(settings, rid)
                    current = get_content_delivery_state(settings, rid)
                if current['generation']['ready'] or current['review']['completed'] or current.get('stop_point_reached'):
                    continue
                if native.known_local_outcome(root, rid):
                    continue
                operation = {'CREATE_CONTENT_PLAN':'content_plan', 'GENERATE_SCRIPTS':'script_generation'}.get(current['next_action'])
                if operation:
                    return {'advanced': True, 'task': _submit_once(settings, rid, operation, context)}
                return {'advanced': False, 'reason': 'native_recovery_required', 'request_id': rid}
            if group['source_kind']=='cross_profile_repurpose':
                from .news_delivery_gateway import get_news_delivery_state
                current=get_news_delivery_state(settings,rid)
                if current['plan']['ready'] or current['review']['completed']:continue
                existing=task_for(settings,rid,'news_plan')
                if existing is not None:return {'advanced':False,'task':existing,'reason':'native_task_already_exists'}
                return {'advanced':True,'task':_submit_once(settings,rid,'news_plan',context)}
            from .novel_news_rollout import require_novel_news_task
            require_novel_news_task(settings, context['actor']['user_id'])
            current = novel_news_state(settings, rid)
            if current['stage'] == 'source_plan':
                from .content_gateway import resolve_generation_sources
                from .operation_lock import authority_operation_lock
                with authority_operation_lock(settings, 'request', rid, timeout_seconds=0.0):
                    resolve_generation_sources(settings, rid)
                current = novel_news_state(settings, rid)
            if current['generation']['ready_for_human_review']:
                continue
            existing = task_for(settings, rid, 'novel_news_generate')
            if existing is not None:
                return {'advanced': False, 'task': existing, 'reason': 'native_task_already_exists'}
            from .novel_news_generation_gateway import submit
            return {'advanced': True, **submit(settings, rid, context['actor']['user_id'], context)}
        return _advance_publishing(settings, batch_id, context)


def advance_batches(settings, *, skip_batches=frozenset()):
    """Recover confirmed intents after restart; observations never grant gates."""
    for path in sorted((settings.pipeline_root / 'data/creation_batches').glob('*/intent.json')):
        if path.parent.name in skip_batches:
            continue  # Stop idle maintenance, never prove a business state.
        try:
            advance(settings, path.parent.name)
        except (CanonicalOperationError, OperationLockTimeout):
            # A revoked source/session, occupied lane or unknown operation must
            # remain blocked. Other Businesses can still make legal progress.
            continue
