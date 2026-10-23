"""C05 companion of Content Quality: pending intentions are NOT exposure history.

There is no TTL release. Only explicit, source-validated Native evidence may
settle an intention. Existing Content Ledger owners still communicate once.
"""
from pathlib import Path
import copy

from creation_batch_contract_v1 import BatchError, check
from creative_style_v1 import artifact, digest, file_sha, pinned
from human_review_operations_v1 import io_path, read, write_once
from profile_compatibility_contract_v1_1 import obj, array, TEXT, validate
from creation_batch_contract_v1 import CONTRACTS

SETTLEMENT = 'content-intent-settlement-v1.0'
ARTIFACT = read(CONTRACTS)['C05']['$defs']['ArtifactRef']
NULL_ARTIFACT = {'oneOf':[ARTIFACT,{'type':'null'}]}
SETTLEMENT_SCHEMA = obj({'schema_version':{'const':SETTLEMENT}, 'business_id':TEXT,
    'native_request_id':TEXT, 'batch_intent_ref':ARTIFACT, 'parent_reservation_ref':ARTIFACT,
    'request_ref':NULL_ARTIFACT, 'end_ref':NULL_ARTIFACT,
    'kind':{'enum':['cancelled_unissued','cancelled_known_zero','human_rejected','native_closed']},
    'native_evidence_refs':array(ARTIFACT,0)})


def directory(root, business_id, request_id):
    from native_batch_v1 import identifier
    return Path(root).resolve() / 'data/content_intent_reservations' / identifier(business_id) / identifier(request_id)


def events(root, business_id, request_id):
    result = []
    previous = None
    for path in sorted((directory(root, business_id, request_id) / 'events').glob('*.json')):
        value = check(read(path), 'C05')
        if (value['business_id'] != business_id or value['native_request_id'] != request_id
                or value.get('parent_event_ref') != previous):
            raise BatchError('CONTENT_RESERVATION_INVALID', 'Pending intention chain differs')
        for reference in [value['memory_ref'], *value['source_refs'], *value['native_evidence_refs']]:
            pinned(reference)
        if value['event'] in ('safely_released','consumed_by_native_closure'):
            validate_settlement(root,value,previous)
        elif result and result[-1][1]['event'] in ('safely_released','consumed_by_native_closure'):
            raise BatchError('CONTENT_RESERVATION_INVALID','A settled Native intention cannot be reopened')
        result.append((path, value))
        previous = artifact(path, 'native-content-quality', request_id, value['schema_version'])
    return result


def assert_executable(root,business_id,request_id):
    chain=events(root,business_id,request_id)
    if chain and chain[-1][1]['event'] in ('safely_released','consumed_by_native_closure'):
        raise BatchError('CONTENT_INTENT_SETTLED','Settled Native work cannot publish or reserve again')


def _admission_sources(root,business_id,request_id,batch_intent_ref,request):
    """Pinned Native sources only; never recurse from C05 back into its reader."""
    import native_batch_v1 as native
    batch=pinned(batch_intent_ref)
    if (batch_intent_ref != native.batch_ref(root,batch['batch_id']) or batch['business_id']!=business_id
            or request_id not in {g['request_id'] for g in native.groups(root,batch['batch_id'])}):
        raise BatchError('CONTENT_SETTLEMENT_INVALID','Settlement is outside its canonical Batch')
    admission_path=native.directory(root,batch['batch_id'])/'admissions'/(request_id+'.json')
    raw=read(admission_path)
    reference=artifact(admission_path,'native-request-admission',request_id,raw['schema_version'])
    admission=native.admission_binding(reference,root=root,request=request)
    if admission['batch_intent_ref']!=batch_intent_ref or admission['business_id']!=business_id:
        raise BatchError('CONTENT_SETTLEMENT_INVALID','Settlement lost its original Native admission')
    if request is not None and request.get('batch_admission_ref')!=reference:
        raise BatchError('CONTENT_SETTLEMENT_INVALID','Settlement Request does not bind this canonical admission')
    return admission,batch


def _sealed_closure_evidence(root,business_id,request_id):
    from ledger_history_v1 import graph,validate_sealed_transition,ledger_path
    nodes=graph(root,business_id)
    own=[(p,v) for p,v in nodes if v['request_id']==request_id]
    if not own or any(not p.with_name('receipt.json').is_file() for p,_ in own):return None
    kinds={v['kind'] for _,v in own}
    if len(own)!=len(kinds) or kinds not in ({'mix_semantic'},{'novel_semantic','novel_presentation'},{'news_presentation'}):return None
    # The original Ledger owner checks replay, Human, Receipt and Closure. No
    # current planning reader or second semantic/history writer is involved.
    for path,event in nodes:validate_sealed_transition(root,path,event)
    live=ledger_path(root,business_id)
    if not live.is_file() or file_sha(live)!=nodes[-1][1]['after_ref']['sha256']:
        raise BatchError('CONTENT_SETTLEMENT_INVALID','Live Ledger differs from its sealed Native history')
    refs=[]
    for path,event in own:
        seal=read(path.with_name('receipt.json'))
        refs.extend([artifact(path,'native-ledger-history',request_id,event['schema_version']),
            artifact(path.with_name('receipt.json'),'native-ledger-history',request_id,seal['schema_version'])])
    return refs


def _cancellation_state(root,business_id,request_id,admission,batch,request):
    base=(Path(root)/'data/news_deliveries'/request_id if request_id.startswith('news_')
          else Path(root)/'data/generation_batches'/request_id)
    if request is None:
        if base.exists() or any((__import__('native_batch_v1').directory(root,batch['batch_id'])/'provider_stages'/request_id).rglob('intent.json')):
            raise BatchError('CONTENT_SETTLEMENT_INVALID','An unpublished Request has unexpected execution artifacts')
        return 'cancelled_unissued'
    if request.get('reuse_intent')=='cross_profile_repurpose':
        if (any((base/name).is_file() for name in ('news_delivery_plan_v1.json','news_delivery_human_review_v1.json',
                'approved_news_delivery_v1.json','news_dynamic_excel_export_receipt_v1.json','news_delivery_export_closure_v1.json'))
                or any((base/'publish_copy_v1').rglob('intent.json'))):return None
        return 'cancelled_unissued'
    if request.get('target_profile')=='news':
        from novel_news_generation_recovery_v1 import head,directory as attempt_directory
        head(root,request_id)  # Validate the complete REC-01 chain, including ancestors.
        # An unissued retry does not resolve its issued parent. All issued
        # attempts remain with REC-01 until original Native closure consumes
        # the semantic reservation; End cannot release that uncertainty.
        if any(attempt_directory(root,request_id).glob('*/dispatch.json')):return None
        if (base/'novel_news_beat_plan_v1.json').is_file():return None
        return 'cancelled_unissued'
    from batch_provider_recovery_v1 import read_phase_evidence
    phase=read_phase_evidence(root,request,admission,batch)
    if phase['unknown']:return None
    import generation_recovery_v1 as recovery
    graph=recovery.graph(Path(root),request_id)
    if (graph['result'] or {}).get('outcome')=='outcome_unknown':return None
    if graph['pending'] and (recovery.operation_root(root,request_id,graph['pending']['operation_id'])/'dispatch.json').is_file():return None
    if graph['batch'].is_file():
        result=read(graph['batch'])
        if result.get('request_id')!=request_id:raise BatchError('CONTENT_SETTLEMENT_INVALID','Native result identity changed')
        if result.get('contents'):return None
        from generate_mix_scripts_v1 import SCHEMA_VERSION
        if (result.get('schema_version')!=SCHEMA_VERSION or result.get('profile')!='mix'
                or result.get('status')!='generation_incomplete' or result.get('generated_count')!=0
                or result.get('machine_pass_count')!=0 or result.get('validation',{}).get('passed') is not False):
            raise BatchError('CONTENT_SETTLEMENT_INVALID','Native zero-output disposition is not valid')
    elif phase['stages']['script_generation']['dispatches']:
        return None  # Received-but-unpublished script may still contain output.
    return 'cancelled_known_zero' if phase['stages']['script_generation']['dispatches'] else 'cancelled_unissued'


def _end_context(root,batch,end_ref):
    """Validate the entire persisted negative command BEFORE any Native write."""
    import native_batch_v1 as native
    from delivery_receipt_recovery_v1 import CONTEXT
    chain=native.controls(root,batch['batch_id'])
    if not chain or chain[-1]['action']!='end':
        raise BatchError('CONTENT_SETTLEMENT_INVALID','No canonical explicit End')
    end=chain[-1];actor=end.get('actor_intent') or {}
    path=native.directory(root,batch['batch_id'])/'controls'/f'{len(chain):06d}.json'
    if (end_ref!=artifact(path,'native-request-batch',batch['batch_id'],'native-batch-control-v1.0')
            or set(actor)!={'actor_id','operation_id','permission_snapshot','payload_sha256'}
            or actor['actor_id']!=batch['actor_intent']['actor_id']
            or actor['payload_sha256']!=digest({'batch_id':batch['batch_id'],'action':'end'})):
        raise BatchError('CONTENT_SETTLEMENT_INVALID','End is not bound to its original principal/action')
    native.identifier(actor['operation_id'])
    original=pinned(batch['actor_intent']['permission_snapshot'])
    context=pinned(actor['permission_snapshot']);validate(context,CONTEXT)
    if (actor['permission_snapshot']!=artifact(path.with_suffix('.permission.json'),'console-authorization',
            context['actor']['user_id'],'1') or context['actor']!=original['actor']
            or any(context['authorization'][key]!=original['authorization'][key]
                for key in ('database_path','user_state_sha256'))):
        raise BatchError('CONTENT_SETTLEMENT_INVALID','End lost its original stable permission snapshot')
    return context


def validate_settlement(root,value,parent_ref):
    references=[r for r in value['native_evidence_refs'] if r['owner']=='native-quality-settlement']
    if len(references)!=1:raise BatchError('CONTENT_SETTLEMENT_INVALID','Terminal reservation needs its Native evidence')
    reference=references[0];proof=pinned(reference)
    try:validate(proof,SETTLEMENT_SCHEMA)
    except (RuntimeError,ValueError,TypeError) as exc:raise BatchError('CONTENT_SETTLEMENT_INVALID','Invalid settlement schema') from exc
    expected=directory(root,value['business_id'],value['native_request_id'])/'settlements'/(digest(proof)+'.json')
    if (reference!=artifact(expected,'native-quality-settlement',value['native_request_id'],SETTLEMENT)
            or proof['business_id']!=value['business_id'] or proof['native_request_id']!=value['native_request_id']
            or proof['parent_reservation_ref']!=parent_ref):
        raise BatchError('CONTENT_SETTLEMENT_INVALID','Settlement scope or canonical path changed')
    request_path=__import__('native_batch_v1').request_path(root,value['native_request_id'])
    request=read(request_path) if request_path.is_file() else None
    expected_request=artifact(request_path,'native-request',value['native_request_id'],request['schema_version']) if request else None
    if proof['request_ref']!=expected_request:raise BatchError('CONTENT_SETTLEMENT_INVALID','Settlement Request source changed')
    admission,batch=_admission_sources(root,value['business_id'],value['native_request_id'],proof['batch_intent_ref'],request)
    for ref in proof['native_evidence_refs']:pinned(ref)
    if proof['kind']=='native_closed':
        if value['event']!='consumed_by_native_closure' or _sealed_closure_evidence(root,value['business_id'],value['native_request_id'])!=proof['native_evidence_refs']:
            raise BatchError('CONTENT_SETTLEMENT_INVALID','Native closure evidence changed')
    elif proof['kind']=='human_rejected':
        from delivery_receipt_recovery_v1 import human_state
        base=Path(root)/'data/generation_batches'/value['native_request_id']
        human=human_state(base)
        if value['event']!='safely_released' or not human['completed'] or human['approved']:
            raise BatchError('CONTENT_SETTLEMENT_INVALID','Native Human rejection is incomplete')
        expected_refs=[artifact(base/name,'native-mix-review',value['native_request_id'],read(base/name)['schema_version']) for name in
                       ('generation_human_review_v2.json','reviewed_generation_batch_v1.json','generation_batch_approval_receipt.json')]
        if proof['native_evidence_refs']!=expected_refs:raise BatchError('CONTENT_SETTLEMENT_INVALID','Native rejection source changed')
    else:
        _end_context(root,batch,proof['end_ref'])
        if (value['event']!='safely_released'
                or _cancellation_state(root,value['business_id'],value['native_request_id'],admission,batch,request)!=proof['kind']):
            raise BatchError('CONTENT_SETTLEMENT_INVALID','End/cancellation is not a safe Native disposition')
        if request:
            if request.get('reuse_intent')=='cross_profile_repurpose':
                from news_delivery_v1 import request_cancelled
                resolution=request_cancelled(root,value['native_request_id'])
                if not resolution:raise BatchError('CONTENT_SETTLEMENT_INVALID','Original presentation Request is not cancelled')
                expected_refs=[artifact(request_path.with_name('news_delivery_cancellation_v1.json'),'native-news-request-resolution',
                    value['native_request_id'],resolution['schema_version'])]
            else:
                from generation_request_effective_lifecycle_v1 import _validate_resolution_sidecar
                resolution=_validate_resolution_sidecar(pipeline_root=Path(root),request_path=request_path,request=request)
                if resolution is None or resolution['disposition']!='cancelled':raise BatchError('CONTENT_SETTLEMENT_INVALID','Original Request is not cancelled')
                expected_refs=[artifact(resolution['path'],'native-request-resolution',value['native_request_id'],resolution['artifact']['schema_version'])]
        else:expected_refs=[]
        if proof['kind']=='cancelled_known_zero':
            import generation_recovery_v1 as recovery
            zero=recovery.graph(Path(root),value['native_request_id'])['batch']
            expected_refs.append(artifact(zero,'native-generation-result',value['native_request_id'],read(zero)['schema_version']))
        if proof['native_evidence_refs']!=expected_refs:raise BatchError('CONTENT_SETTLEMENT_INVALID','Cancellation evidence changed')
    return proof


def settle_request(root,business_id,request_id,batch_intent_ref,*,end_ref=None):
    """Original Request/Quality caller holds short Business + provider fences."""
    chain=events(root,business_id,request_id)
    if not chain:return None
    previous,head=chain[-1]
    if head['event'] in ('safely_released','consumed_by_native_closure'):
        proof=next(pinned(r) for r in head['native_evidence_refs'] if r['owner']=='native-quality-settlement')
        return {'request_id':request_id,'event':head['event'],'kind':proof['kind'],'recovered':True}
    path=__import__('native_batch_v1').request_path(root,request_id)
    request=read(path) if path.is_file() else None
    admission,batch=_admission_sources(root,business_id,request_id,batch_intent_ref,request)
    refs=_sealed_closure_evidence(root,business_id,request_id)
    kind='native_closed' if refs else None
    if kind is None and request and request.get('target_profile')=='mix':
        from delivery_receipt_recovery_v1 import human_state
        base=Path(root)/'data/generation_batches'/request_id;human=human_state(base)
        if human['completed'] and not human['approved']:
            kind='human_rejected'
            refs=[artifact(base/name,'native-mix-review',request_id,read(base/name)['schema_version']) for name in
                  ('generation_human_review_v2.json','reviewed_generation_batch_v1.json','generation_batch_approval_receipt.json')]
    if kind is None and end_ref is not None:
        context=_end_context(root,batch,end_ref)
        kind=_cancellation_state(root,business_id,request_id,admission,batch,request)
        refs=[]
        if kind=='cancelled_known_zero':
            from batch_provider_recovery_v1 import validated_local_outcome
            outcome=validated_local_outcome(root,request)
            if not outcome or outcome['kind']!='generation_rejected' or outcome['generated_count']!=0:
                return {'request_id':request_id,'event':'retained','recovered':False}
        if kind and request:
            if request.get('reuse_intent')=='cross_profile_repurpose':
                from news_delivery_v1 import cancel_unissued_batch_request
                refs=[cancel_unissued_batch_request(root,request_id,end_ref)]
            else:
                from generation_request_effective_lifecycle_v1 import _validate_resolution_sidecar
                from resolve_generation_request_v1 import resolve_generation_request
                resolution=_validate_resolution_sidecar(pipeline_root=Path(root),request_path=path,request=request)
                if resolution is None:
                # The already authenticated, canonical End is a persisted
                # negative command. Finishing this exact unissued-work
                # cancellation after logout grants no new model/Human approval.
                    resolve_generation_request(pipeline_root=Path(root),request_id=request_id,disposition='cancelled',
                        reviewer='console_actor:'+context['actor']['namespace']+':'+str(context['actor']['user_id']),
                        reason='Explicit batch end '+end_ref['sha256'],human_approved=True)
                    resolution=_validate_resolution_sidecar(pipeline_root=Path(root),request_path=path,request=request)
                if resolution['disposition']!='cancelled':return None
                refs=[artifact(resolution['path'],'native-request-resolution',request_id,resolution['artifact']['schema_version'])]
        if kind=='cancelled_known_zero':
            import generation_recovery_v1 as recovery
            zero=recovery.graph(Path(root),request_id)['batch']
            refs.append(artifact(zero,'native-generation-result',request_id,read(zero)['schema_version']))
    if kind is None:return {'request_id':request_id,'event':'retained','recovered':False}
    proof={'schema_version':SETTLEMENT,'business_id':business_id,'native_request_id':request_id,
        'batch_intent_ref':batch_intent_ref,'parent_reservation_ref':artifact(previous,'native-content-quality',request_id,head['schema_version']),
        'request_ref':artifact(path,'native-request',request_id,request['schema_version']) if request else None,
        'end_ref':end_ref if kind.startswith('cancelled_') else None,'kind':kind,'native_evidence_refs':refs}
    validate(proof,SETTLEMENT_SCHEMA)
    proof_path=directory(root,business_id,request_id)/'settlements'/(digest(proof)+'.json')
    write_once(proof_path,proof)
    value={k:v for k,v in head.items() if k!='parent_event_ref'}
    value.update(event='consumed_by_native_closure' if kind=='native_closed' else 'safely_released',
        native_evidence_refs=[*head['native_evidence_refs'],artifact(proof_path,'native-quality-settlement',request_id,SETTLEMENT)])
    # Validate against the current Native sources before appending the event.
    validate_settlement(root,value,proof['parent_reservation_ref'])
    _append(root,business_id,request_id,value)
    return {'request_id':request_id,'event':value['event'],'kind':kind,'recovered':False}


def memory(root, business_id):
    path = Path(root) / 'data/content_ledgers' / business_id / 'content_ledger_v1.json'
    return {'schema_version': 'native-pending-memory-snapshot-v1.0', 'business_id': business_id,
            'ledger_sha256': file_sha(path) if io_path(path).is_file() else None}


def _append(root, business_id, request_id, value):
    old = events(root, business_id, request_id)
    path = directory(root, business_id, request_id) / 'events' / f'{len(old) + 1:06d}.json'
    if old:
        value['parent_event_ref'] = artifact(old[-1][0], 'native-content-quality', request_id, old[-1][1]['schema_version'])
    write_once(path, check(value, 'C05'))
    return artifact(path, 'native-content-quality', request_id, value['schema_version'])


def semantic_scope(concept):
    """Same material atom normalization used by the Native generation view."""
    value = copy.deepcopy(concept)
    material = value.get('material_information_gain_v1_1_1') or {}
    atoms = (material['primary_fact_atom_refs'] if 'primary_fact_atom_refs' in material
             else value.get('primary_fact_atom_refs') or value.get('source_fact_atom_refs') or [])
    value['primary_fact_atom_refs'] = list(atoms)
    return value


def legacy_novel_is_pending(root, path, request):
    """Original Request/terminal resolution and Ledger own this disposition.

    Do not call Novel status here: its source reader itself checks pending
    intentions. The canonical Ledger is already the communicated authority.
    """
    from generation_request_effective_lifecycle_v1 import DIRECT_TERMINAL_STATUSES, _validate_resolution_sidecar
    from creative_style_v1 import request_schema_supported
    from content_quality_v1 import STRONG_MEMORY_STATUSES
    if not request_schema_supported(request):
        raise BatchError('CONTENT_RESERVATION_INVALID', 'Unsupported pending Novel Request schema')
    if ((request.get('lifecycle') or {}).get('status') in DIRECT_TERMINAL_STATUSES
            or _validate_resolution_sidecar(pipeline_root=Path(root), request_path=path, request=request) is not None):
        return False
    ledger_path = Path(root) / 'data/content_ledgers' / request['persona_id'] / 'content_ledger_v1.json'
    if io_path(ledger_path).is_file():
        ledger = read(ledger_path)
        if ledger.get('schema_version') != 'content-ledger-v1.0' or ledger.get('business_id') != request['persona_id']:
            raise BatchError('CONTENT_RESERVATION_INVALID', 'Canonical communicated Ledger identity differs')
        if any(e.get('content_id') == request['request_id'] + '-N001' and e.get('status') in STRONG_MEMORY_STATUSES
               and (e.get('source_request_ref') or {}).get('sha256') == file_sha(path) for e in ledger.get('entries') or []):
            return False
    if not isinstance(request.get('selected_content'), dict) or not request['selected_content'].get('concept_id'):
        raise BatchError('CONTENT_RESERVATION_INVALID', 'Pending Novel Request has no canonical selected opportunity')
    source = Path(root) / 'data/production_plans' / request['request_id'] / 'generation_source_plan_v1.json'
    if io_path(source).is_file():
        from resolve_generation_content_plan_v1 import read_request_and_source_plan
        read_request_and_source_plan(Path(root), request['request_id'])
    return True


def pending(root, business_id, *, exclude_request_id=None):
    base = directory(root, business_id, 'unused').parent
    result = []
    for item in sorted(base.iterdir()) if io_path(base).is_dir() else []:
        if not item.is_dir() or item.name == exclude_request_id:
            continue
        chain = events(root, business_id, item.name)
        if not chain:
            continue
        head = chain[-1][1]
        if head['event'] in ('safely_released', 'consumed_by_native_closure'):
            continue
        claims = next((pinned(ref) for ref in reversed(head['native_evidence_refs'])
                       if ref['owner'] == 'native-quality-selected-concepts'), None)
        if claims:
            if claims['business_id'] != business_id or claims['native_request_id'] != item.name:
                raise BatchError('CONTENT_RESERVATION_INVALID', 'Pending semantic source belongs to another business or Request')
            result.extend(semantic_scope(c) for c in claims['concepts'])
    # Legacy selections predate C05, but remain pending semantic work.
    # Read the original final-plan consumer rather than creating synthetic
    # reservations or treating unexported selections as communicated history.
    from generation_request_effective_lifecycle_v1 import classify_request
    from resolve_generation_batch_v1 import generation_inputs
    from delivery_receipt_recovery_v1 import human_state, source_snapshot
    for request_path in sorted((Path(root) / 'data/generation_requests').glob('*/generation_request_v1.json')):
        request = read(request_path)
        rid = request.get('request_id')
        if (rid == exclude_request_id or request.get('persona_id') != business_id
                or request.get('batch_admission_ref')):
            continue
        if not isinstance(rid, str) or request_path.parent.name != rid:
            raise BatchError('CONTENT_RESERVATION_INVALID', 'Legacy pending Request identity differs from its canonical directory')
        profile = request.get('target_profile') or request.get('profile')
        if profile == 'news' and request.get('reuse_intent') == 'novel_content':
            if legacy_novel_is_pending(root, request_path, request):
                result.append(semantic_scope(request['selected_content']))
            continue
        if profile != 'mix':
            continue
        final_path = Path(root) / 'data/content_plans' / rid / 'content_plan_v1_1_1.json'
        if not io_path(final_path).is_file() or not read(final_path).get('selected_concepts'):
            continue
        state = classify_request(pipeline_root=Path(root), request_path=request_path)
        if state['effective_terminal']:
            continue
        human = human_state(Path(root) / 'data/generation_batches' / rid)
        if human['completed'] and not human['approved']:
            continue
        if human['completed']:
            # Completed Human source is historical; never rebind it to today's
            # planning memory after another legal export. The original native
            # Human reader and source snapshot still verify its exact lineage.
            base = Path(root) / 'data/generation_batches' / rid
            receipt = read(base / 'generation_batch_approval_receipt.json')
            raw = Path(receipt['source_batch']['path'])
            source_snapshot(Path(root), raw)
            batch = read(raw)
            if batch.get('request_id') != rid:
                raise BatchError('CONTENT_RESERVATION_INVALID', 'Native Human source belongs to another Request')
            final = pinned(batch['script_generation_contract']['final_content_plan_ref'])
            result.extend(semantic_scope(c) for c in final['selected_concepts'])
        else:
            result.extend(generation_inputs(Path(root), rid)['projection']['selected_concepts'])
    return result


def assert_available(root, business_id, concepts, request_id):
    from content_quality_v1 import novelty_evaluation
    held = pending(root, business_id, exclude_request_id=request_id)
    selected = []
    for original in concepts:
        concept = semantic_scope(original)
        # Pending concepts use the original semantic equivalence rules as
        # contemporaneous selections, never as Strong/communicated Memory.
        result = novelty_evaluation(concept, [], held + selected)
        atoms = set(concept.get('primary_fact_atom_refs') or concept.get('source_fact_atom_refs') or [])
        collision = any(atoms & set(p.get('primary_fact_atom_refs') or p.get('source_fact_atom_refs') or []) for p in held + selected)
        if result.get('hard_duplicate') or collision:
            raise BatchError('CONTENT_INTENT_ALREADY_RESERVED', 'This semantic opportunity is held by another pending Native intention')
        selected.append(concept)


def reserve_admission(root, business_id, group, source_refs):
    """Original Request owner calls this under its short Business lock."""
    request_id = group['request_id']
    if group['source_kind']=='cross_profile_repurpose':
        from news_delivery_v1 import preview_news_delivery,batch_source_snapshot
        selected=next(r for r in source_refs if r['owner']=='native-repurpose-source')
        speaker_id=next(r['id'] for r in source_refs if r['owner']=='native-speaker')
        available=preview_news_delivery(pipeline_root=Path(root),business_id=business_id,speaker_id=speaker_id,
            reservation_request_id=request_id)
        if (selected['id'] not in {v['source_content_id'] for v in available['eligible_sources']}
                or batch_source_snapshot(root,business_id,selected['id'])!=selected):
            raise BatchError('CONTENT_PRESENTATION_ALREADY_RESERVED','Historical presentation source is unavailable')
    old = events(root, business_id, request_id)
    if old:
        first = old[0][1]
        if first['slot_ids'] != [s['slot_id'] for s in group['slots']] or first['source_refs'] != source_refs:
            raise BatchError('CONTENT_RESERVATION_CONFLICT', 'Admission intention differs')
        reference = artifact(old[0][0], 'native-content-quality', request_id, first['schema_version'])
    else:
        base = directory(root, business_id, request_id)
        snapshot = base / 'memory.json'
        write_once(snapshot, memory(root, business_id))
        # Before Mix selects a Concept, this is only a Request allocation token.
        # It does not pretend that any fact has been reserved or communicated.
        value = {'schema_version': 'content-intent-reservation-v1.0', 'business_id': business_id,
            'reservation_id': request_id, 'native_request_id': request_id,
            'slot_ids': [s['slot_id'] for s in group['slots']],
            'semantic_owner_keys': ['native-intent:' + request_id], 'source_refs': source_refs,
            'memory_ref': artifact(snapshot, 'native-content-quality-memory', business_id, '1'),
            'attempt_id': group['operation_id'], 'fence_token': digest(memory(root, business_id)),
            'event': 'reserved', 'native_evidence_refs': []}
        reference = _append(root, business_id, request_id, value)
    if group['profile'] == 'news' and group['source_kind'] == 'novel_content':
        from novel_news_opportunity_v1 import project_novel_news_opportunities
        speaker_id = next(r['id'] for r in source_refs if r['owner'] == 'native-speaker')
        selected_id = next(r['id'] for r in source_refs if r['owner'] == 'native-novel-opportunity')
        options = project_novel_news_opportunities(pipeline_root=Path(root), business_id=business_id,
            speaker_id=speaker_id, reservation_request_id=request_id)['opportunities']
        selected = next((c for c in options if c['concept_id'] == selected_id and c['novelty_status'] == 'novel'), None)
        if selected is None:
            raise BatchError('CONTENT_INTENT_ALREADY_RESERVED', 'Novel opportunity is no longer available')
        reserve_concepts(root, business_id, request_id, [selected], reference)
    return reference


def reserve_concepts(root, business_id, request_id, concepts, source_ref):
    """Caller holds original Business lock; retries reuse the same exact claims."""
    concepts = [semantic_scope(c) for c in concepts]
    old = events(root, business_id, request_id)
    if old and old[-1][1]['event'] in ('safely_released','consumed_by_native_closure'):
        raise BatchError('CONTENT_INTENT_SETTLED','A settled Native semantic scope cannot be reclaimed')
    if not old:
        # A legacy Request has no new admission, but must still respect holds.
        assert_available(root, business_id, concepts, request_id)
        return None
    first = old[0][1]
    if pinned(first['memory_ref']) != memory(root, business_id):
        raise BatchError('CONTENT_RESERVATION_MEMORY_CHANGED', 'Original pending memory changed; it cannot be rebound')
    assert_available(root, business_id, concepts, request_id)
    if not concepts:
        # No semantic claim exists. Keep the original allocation token and let
        # the Native evaluator publish its truthful zero-capacity outcome.
        return artifact(old[-1][0], 'native-content-quality', request_id, old[-1][1]['schema_version'])
    last = old[-1][1]
    previous_claim = next((r for r in last['native_evidence_refs'] if r['owner'] == 'native-quality-selected-concepts'), None)
    if previous_claim is not None:
        previous = pinned(previous_claim)
        if ([semantic_scope(c) for c in previous['concepts']] != concepts
                or source_ref not in last['native_evidence_refs']):
            raise BatchError('CONTENT_RESERVATION_CONFLICT', 'Selected pending semantic scope or original source is immutable')
        return previous_claim
    payload = {'schema_version': 'native-quality-pending-concepts-v1.0', 'business_id': business_id,
               'native_request_id': request_id, 'concepts': concepts}
    path = directory(root, business_id, request_id) / 'claims' / (digest(payload) + '.json')
    write_once(path, payload)
    reference = artifact(path, 'native-quality-selected-concepts', request_id, payload['schema_version'])
    claims_refs = [r for r in last['native_evidence_refs'] if r['owner'] != 'native-quality-selected-concepts']
    value = {k: v for k, v in last.items() if k != 'parent_event_ref'}
    value.update(semantic_owner_keys=sorted({digest(c.get('semantic_signature') or {
        'central_claim': c.get('central_claim'), 'primary_fact_refs': c.get('primary_fact_refs')}) for c in concepts}),
        native_evidence_refs=[*claims_refs, source_ref, reference], event='reserved')
    _append(root, business_id, request_id, value)
    return reference
