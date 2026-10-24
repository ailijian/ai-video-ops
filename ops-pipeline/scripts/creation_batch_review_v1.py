"""C07 source-bound commands delegate to the original Human/Publish owners.

A command records an explicit user intent, never an approval receipt. Every
completion/replay below is established again by the corresponding Native owner.
"""
from pathlib import Path
from creation_batch_contract_v1 import BatchError, check
from creative_style_v1 import artifact, digest, file_sha, pinned
from human_review_operations_v1 import read, write_once, io_path
from operation_lock_v1 import operation_lock
import native_batch_v1 as batch_owner


def qualification(root):
    active = batch_owner.policy_qualification(root)
    declared = {v['path']: v['checkout_sha256'] for v in active['manifest']['source_files']}
    for name in ('creation_batch_review_v1.py', 'review_generation_batch_v2.py', 'novel_news_v1.py',
                 'news_delivery_v1.py', 'publish_copy_v1.py'):
        if declared.get('ops-pipeline/scripts/' + name) != file_sha(Path(__file__).with_name(name)):
            raise BatchError('CREATION_BATCH_REVIEW_QUALIFICATION_REQUIRED', 'Exact original Human consumers require qualification')


def _groups(root, batch_id):
    return {s['slot_id']: g for g in batch_owner.groups(root, batch_id) for s in g['slots']}


def options(root, batch_id, context, scope):
    batch_owner.assert_principal(root, batch_id, context); qualification(root)
    if scope not in ('native_content_review', 'publish_copy_confirmation'):
        raise BatchError('CREATION_BATCH_REVIEW_SCOPE_INVALID', 'Unknown Human scope')
    root = Path(root); _, batch = batch_owner.intent(root, batch_id)
    items, excluded = [], []
    for group in batch_owner.groups(root, batch_id):
        rid = group['request_id']
        try:
            request_path = batch_owner.request_path(root,rid)
            if not io_path(request_path).is_file(): continue
            request = read(request_path)
            batch_owner.validate_admission(request['batch_admission_ref'], root=root, context=context, request=request)
            if scope == 'publish_copy_confirmation':
                from publish_copy_sources_v1 import source
                from publish_copy_v1 import draft, verify_draft
                src = source(root, rid); current = draft(root, rid)
                if not current: continue
                verify_draft(root, src, current[1])
                if {i['target_id'] for i in current[1]['payload']['items']} != {i['target_id'] for i in src['items']}:
                    raise BatchError('CREATION_BATCH_PUBLISH_DRAFT_INCOMPLETE', 'The Native draft does not yet cover every approved target')
                from publish_copy_v1 import confirmation
                if confirmation(root, rid, current[1]): continue
                approved = Path(src['snapshot']['approved_ref']['path'])
                if not approved.is_absolute(): approved = root / approved
                approved_value = read(approved)
                by_id = {c['content_id']: c for c in approved_value.get('contents', [])}
                for item in src['items']:
                    sid = by_id[item['target_id']]['logical_slot_id'] if group['profile'] == 'mix' else group['slots'][0]['slot_id']
                    draft_ref = artifact(current[0], 'native-publish-copy', rid, current[1]['schema_version'])
                    items.append({'slot_id': sid, 'native_kind': src['mode'],
                        'native_approved_source_ref': artifact(approved, 'native-human-review', rid, approved_value['schema_version']),
                        'draft_ref': draft_ref, 'expected_head_ref': draft_ref,
                        'display': next(v for v in current[1]['payload']['items'] if v['target_id'] == item['target_id'])})
            elif group['profile'] == 'mix':
                from resolve_generation_batch_v1 import generation_snapshot
                from generation_recovery_v1 import graph
                from delivery_receipt_recovery_v1 import human_state
                human = human_state(root / 'data/generation_batches' / rid)
                if human['state'] != 'no_human_review': continue
                if not generation_snapshot(root, rid).get('ready_for_human_review'): continue
                path = graph(root, rid)['batch']; value = read(path)
                for content in value['contents']:
                    reference = artifact(path, 'native-mix-generation', content['content_id'], value['schema_version'])
                    items.append({'slot_id': content['logical_slot_id'], 'native_kind': 'mix',
                        'native_source_ref': reference, 'expected_head_ref': reference,
                        'display': {'title': content['title'], 'narration': content['narration'],
                            'style_id': group['creative_style']['style_id']}})
            elif group['source_kind']=='cross_profile_repurpose':
                from news_delivery_v1 import _request_root,_review_path
                if io_path(_review_path(root,rid)).is_file() or not batch_owner.known_local_outcome(root,rid):continue
                path=_request_root(root,rid)/'news_delivery_plan_v1.json';value=read(path)
                reference=artifact(path,'native-repurpose-generation',rid,value['schema_version'])
                items.append({'slot_id':group['slots'][0]['slot_id'],'native_kind':'cross_profile_repurpose',
                    'native_source_ref':reference,'expected_head_ref':reference,
                    'display':{'source_content_id':request['source_content_id'],'source_title':request['source_content']['title'],
                        'beats':[{'beat_id':s['slot_id'],'text':s['proposed_text']} for s in value['slots']]}})
            else:
                from novel_news_v1 import _paths, novel_generation_state
                paths = _paths(root, rid)
                if io_path(paths['review']).is_file(): continue
                if not novel_generation_state(root, rid).get('ready_for_human_review'): continue
                value = read(paths['plan']); reference = artifact(paths['plan'], 'native-novel-generation', rid, value['schema_version'])
                items.append({'slot_id': group['slots'][0]['slot_id'], 'native_kind': 'novel_content',
                    'native_source_ref': reference, 'expected_head_ref': reference,
                    'display': {'beats': value['micro_information_beats']}})
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            excluded.append({'request_id': rid, 'code': getattr(exc, 'code', 'NATIVE_REVIEW_SOURCE_UNAVAILABLE')})
    return {'batch_id': batch_id, 'scope': scope, 'items': items, 'excluded': excluded,
        'source_sha256': digest({'batch': batch_owner.batch_ref(root, batch_id), 'scope': scope, 'items': items})}


def write_or_reuse_mix_review_input(path, expected):
    """Preserve valid prior submission order; compare decisions canonically."""
    if not io_path(path).is_file():
        write_once(path, expected)
        return
    saved = read(path)
    order = {v['content_id']: i for i, v in enumerate(expected['items'])}
    items = saved.get('items')
    if (set(saved) != set(expected) or any(saved[k] != expected[k] for k in expected if k != 'items')
            or not isinstance(items, list) or any(not isinstance(v, dict) or v.get('content_id') not in order for v in items)
            or sorted(items, key=lambda v: order[v['content_id']]) != expected['items']):
        raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Original Native review input differs from this explicit command')


def commands(root, batch_id, context):
    """Recover original explicit intents; a saved command proves no approval."""
    batch_owner.assert_principal(root, batch_id, context)
    current = batch_owner.batch_ref(root, batch_id)
    records, blocked = [], []
    for path in sorted((batch_owner.directory(root, batch_id) / 'human_commands').glob('*/command.json')):
        try:
            value = check(read(path), 'C07'); actor = value['actor_intent']
            permission = pinned(actor['permission_snapshot'])
            if (permission['actor'] != context['actor'] or actor['actor_id'] != str(context['actor']['user_id'])
                    or any(permission['authorization'][k] != context['authorization'][k] for k in ('database_path','user_state_sha256'))
                    or value['batch_intent_ref'] != current or value['business_id'] != pinned(current)['business_id']
                    or path.parent.name != digest({'actor': context['actor'], 'operation': actor['operation_id']})[:32]
                    or actor['permission_snapshot'] != artifact(path.parent / 'permission.json', 'console-authorization', context['actor']['user_id'], '1')):
                raise BatchError('CREATION_BATCH_REVIEW_COMMAND_CONFLICT', 'Stored command does not bind this principal/batch')
            batch_owner.identifier(actor['operation_id'])
            records.append({'command_ref': artifact(path, 'native-human-command', path.parent.name, value['schema_version']),
                'review_state': 'command_saved_not_approval', 'scope': value['scope'], 'items': value['items'],
                'operation_id': actor['operation_id'], 'source_sha256': actor['payload_sha256']})
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            blocked.append({'command_id': path.parent.name, 'code': getattr(exc, 'code', 'NATIVE_REVIEW_COMMAND_UNREADABLE')})
    return {'batch_id': batch_id, 'commands': records, 'blocked': blocked, 'read_only': True}


def _owner_result(root, group, items, scope, context, base):
    """Original writers alone create/validate their original immutable receipts."""
    from delivery_receipt_recovery_v1 import actor_phone
    rid = group['request_id']; root = Path(root)
    if scope == 'publish_copy_confirmation':
        from publish_copy_v1 import confirm, verify_draft
        from publish_copy_sources_v1 import source
        from profile_compatibility_decisions_v1_1 import ref
        draft_ref = items[0]['draft_ref']
        if any(i['draft_ref'] != draft_ref for i in items): raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Draft versions differ')
        value = pinned(draft_ref); src = source(root, rid); verify_draft(root, src, value)
        approved_path = Path(src['snapshot']['approved_ref']['path'])
        if not approved_path.is_absolute(): approved_path = root / approved_path
        expected = artifact(approved_path, 'native-human-review', rid, read(approved_path)['schema_version'])
        if any(i['native_approved_source_ref'] != expected or i['expected_head_ref'] != draft_ref for i in items):
            raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Native approved source/head differs')
        return {'request_id': rid, 'native': confirm(root, rid, ref(root, Path(draft_ref['path'])), context)}
    for item in items:
        if item['decision'] == 'revise':
            raise BatchError('CREATION_BATCH_NATIVE_REVISION_REQUIRED', 'Use the original Native editor for a guarded content revision')
        pinned(item['native_source_ref'])
    if group['profile'] == 'mix':
        from review_generation_batch_v2 import review_generation_batch_v2
        from delivery_receipt_recovery_v1 import human_state
        from generation_recovery_v1 import graph
        path = graph(root, rid)['batch']; raw = read(path)
        by_id = {c['logical_slot_id']: c['content_id'] for c in raw['contents']}
        for item in items:
            expected = artifact(path, 'native-mix-generation', by_id[item['slot_id']], raw['schema_version'])
            if item['native_source_ref'] != expected or item['expected_head_ref'] != expected:
                raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Effective Native Mix source/head differs')
        selected = {i['slot_id']: i for i in items}
        decisions = [{'content_id': c['content_id'], 'decision': 'approved' if selected[c['logical_slot_id']]['decision'] == 'approve' else 'rejected', 'note': ''}
            for c in raw['contents'] if c['logical_slot_id'] in selected]
        review_input = {'schema_version': 'generation-batch-review-input-v2.0', 'reviewer': actor_phone(context),
            'note': 'Explicit batch content review ' + base.name, 'items': decisions}
        input_path = base / (rid + '.native-input.json'); write_or_reuse_mix_review_input(input_path, review_input)
        directory = root / 'data/generation_batches' / rid
        if human_state(directory)['completed']:
            from generation_recovery_v1 import validate_approved_source
            receipt = read(directory / 'generation_batch_approval_receipt.json')
            reviewed = directory / ('approved_generation_batch_v1.json' if receipt['status'] == 'approved' else 'reviewed_generation_batch_v1.json')
            validate_approved_source(root, rid, read(reviewed), receipt)
            actual = read(directory / 'generation_human_review_v2.json')
            if actual['items'] != decisions or actual['reviewer'] != review_input['reviewer'] or actual.get('note', '') != review_input['note']:
                raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Native Human decision differs from this command')
            return {'request_id': rid, 'recovered': True}
        result = review_generation_batch_v2(batch_path=path, review_input_path=input_path, authorization_context=context)
        return {'request_id': rid, 'native': result}
    if group['source_kind']=='cross_profile_repurpose':
        from news_delivery_v1 import _request_root,_review_path,_approved_path,approve_news_delivery,REVIEW_SCHEMA_V1_1
        path=_request_root(root,rid)/'news_delivery_plan_v1.json';plan=read(path)
        expected=artifact(path,'native-repurpose-generation',rid,plan['schema_version'])
        if (len(items)!=1 or items[0]['decision']!='approve' or items[0]['native_source_ref']!=expected
                or items[0]['expected_head_ref']!=expected):
            raise BatchError('CREATION_BATCH_NATIVE_REVIEW_REQUIRED','Use the original Native presentation editor for beat changes/rejection')
        incoming={'schema_version':REVIEW_SCHEMA_V1_1,'request_id':rid,'reviewer':actor_phone(context),
            'decision':'approve_items','items':[{'slot_id':s['slot_id'],'decision':'approved'} for s in plan['slots']]}
        target=base/(rid+'.native-input.json');write_once(target,incoming)
        result=approve_news_delivery(pipeline_root=root,request_id=rid,review_path=target,
            verify_only=io_path(_approved_path(root,rid)).is_file())
        from news_export_recovery_v1 import verify_native_human_bundle
        verify_native_human_bundle(root,request=batch_owner.request_path(root,rid),plan=path,
            review=_review_path(root,rid),approved=_approved_path(root,rid),kind='repurpose')
        return {'request_id':rid,'native':result}
    from novel_news_v1 import _paths, review_novel_news_plan
    from news_export_recovery_v1 import verify_native_human_bundle
    paths = _paths(root, rid); plan = read(paths['plan'])
    expected = artifact(paths['plan'], 'native-novel-generation', rid, plan['schema_version'])
    if any(i['native_source_ref'] != expected or i['expected_head_ref'] != expected for i in items):
        raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Effective Native News source/head differs')
    if len(items) != 1 or items[0]['decision'] != 'approve':
        raise BatchError('CREATION_BATCH_NATIVE_REVIEW_REQUIRED', 'Use the original Native News review for beat decisions')
    decisions = [{'beat_id': b['beat_id'], 'decision': 'approved'} for b in plan['micro_information_beats']]
    if io_path(paths['approved']).is_file():
        verify_native_human_bundle(root, request=paths['request'], plan=paths['plan'], review=paths['review'], approved=paths['approved'], kind='novel')
        actual = read(paths['review'])
        if actual['decisions'] != decisions or actual['reviewed_by'] != actor_phone(context):
            raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Native News Human decision differs')
        return {'request_id': rid, 'recovered': True}
    return {'request_id': rid, 'native': review_novel_news_plan(pipeline_root=root, request_id=rid, decisions=decisions, reviewer=actor_phone(context))}


def _completion_hint(root, group, items, scope):
    """Scheduling hint only; _owner_result still verifies every Native proof."""
    rid=group['request_id'];root=Path(root)
    if scope=='publish_copy_confirmation':
        from publish_copy_v1 import base
        value=pinned(items[0]['draft_ref'])
        return io_path(base(root,rid)/'confirmations'/(value['draft_id']+'.json')).is_file()
    if group['profile']=='mix':
        return io_path(root/'data/generation_batches'/rid/'generation_batch_approval_receipt.json').is_file()
    if group['source_kind']=='cross_profile_repurpose':
        from news_delivery_v1 import _approved_path
        return io_path(_approved_path(root,rid)).is_file()
    from novel_news_v1 import _paths
    return io_path(_paths(root,rid)['approved']).is_file()


def execute(root, batch_id, context, *, scope, items, operation_id, source_sha256, maximum_mutations=4):
    from novel_news_generation_recovery_v1 import mutation_fence
    batch_owner.assert_principal(root, batch_id, context); qualification(root)
    batch_owner.identifier(operation_id); root = Path(root); _, batch = batch_owner.intent(root, batch_id)
    if type(maximum_mutations) is not int or not 1<=maximum_mutations<=4:
        raise BatchError('CREATION_BATCH_REVIEW_SCOPE_INVALID','A bounded Native mutation budget is required')
    base = batch_owner.directory(root, batch_id) / 'human_commands' / digest({'actor': context['actor'], 'operation': operation_id})[:32]
    with operation_lock(root, 'creation-batch-human:' + batch_id):
        # A later pause/resume/end must retain precedence over this submission,
        # including when another session commits it during Native review.
        control_head=batch_owner._control_head_ref(root,batch_id)
        path = base / 'command.json'
        if io_path(path).is_file():
            command = check(read(path), 'C07')
            original = pinned(command['actor_intent']['permission_snapshot'])
            if (command['scope'] != scope or command['items'] != items or command['actor_intent']['payload_sha256'] != source_sha256
                    or command['actor_intent']['operation_id'] != operation_id or original['actor'] != context['actor']
                    or command['business_id'] != batch['business_id'] or command['actor_intent']['actor_id'] != str(context['actor']['user_id'])
                    or command['actor_intent']['permission_snapshot'] != artifact(base / 'permission.json', 'console-authorization', context['actor']['user_id'], '1')
                    or command['batch_intent_ref'] != batch_owner.batch_ref(root, batch_id)
                    or any(original['authorization'][k] != context['authorization'][k] for k in ('database_path', 'user_state_sha256'))):
                raise BatchError('CREATION_BATCH_REVIEW_COMMAND_CONFLICT', 'Original Human command is immutable')
        else:
            preview = options(root, batch_id, context, scope)
            if preview['source_sha256'] != source_sha256:
                raise BatchError('CREATION_BATCH_REVIEW_PREFLIGHT_STALE', 'Review sources changed; recheck explicitly')
            offered = {record['slot_id']: {k: v for k, v in record.items() if k != 'display'} for record in preview['items']}
            if not items or len({v['slot_id'] for v in items}) != len(items): raise BatchError('CREATION_BATCH_REVIEW_SCOPE_INVALID', 'Duplicate or empty Human scope')
            selected = {i['slot_id'] for i in items}; lookup = _groups(root, batch_id)
            for item in items:
                offered_item = offered.get(item['slot_id'])
                action_fields = {'decision', 'revision_ref'} if scope == 'native_content_review' else {'action'}
                if offered_item is None or {k: v for k, v in item.items() if k not in action_fields} != offered_item:
                    raise BatchError('CREATION_BATCH_REVIEW_SOURCE_CHANGED', 'Item does not bind the exact Native source/head')
                members = {sid for sid in offered if lookup[sid]['request_id'] == lookup[item['slot_id']]['request_id']}
                if not members <= selected:
                    raise BatchError('CREATION_BATCH_NATIVE_REVIEW_INCOMPLETE', 'Every generated item in a Native Request needs an explicit decision')
            with mutation_fence(root):
                permission = base / 'permission.json'
                if io_path(permission).is_file():
                    saved = read(permission)
                    if saved['actor'] != context['actor'] or any(saved['authorization'][k] != context['authorization'][k]
                            for k in ('database_path', 'user_state_sha256')):
                        raise BatchError('CREATION_BATCH_REVIEW_COMMAND_CONFLICT', 'Interrupted command belongs to another principal')
                else: write_once(permission, context)
                command = check({'schema_version': 'creation-batch-review-command-v1.0', 'business_id': batch['business_id'],
                    'batch_intent_ref': batch_owner.batch_ref(root, batch_id), 'scope': scope, 'items': items,
                    'actor_intent': {'actor_id': str(context['actor']['user_id']), 'operation_id': operation_id,
                        'permission_snapshot': artifact(permission, 'console-authorization', context['actor']['user_id'], '1'),
                        'payload_sha256': source_sha256}}, 'C07')
                write_once(path, command)
        lookup = _groups(root, batch_id); result = [];mutations=0
        for group in batch_owner.groups(root, batch_id):
            grouped = [v for v in items if lookup[v['slot_id']]['request_id'] == group['request_id']]
            if not grouped: continue
            try:
                completed_hint=_completion_hint(root,group,grouped,scope)
                if not completed_hint and mutations>=maximum_mutations:
                    result.append({'request_id':group['request_id'],'deferred':True})
                    continue
                if not completed_hint:mutations+=1
                from contextlib import ExitStack
                with ExitStack() as fences:
                    if scope == 'native_content_review':
                        fences.enter_context(mutation_fence(root))
                        fences.enter_context(operation_lock(root, 'request:' + group['request_id'], timeout_seconds=0.0))
                    # Pinned current sources are checked by both the command
                    # coordinator and original writer. Nothing may be rebound.
                    for item in grouped:
                        for key in ('native_source_ref', 'native_approved_source_ref', 'draft_ref', 'expected_head_ref'):
                            if key in item: pinned(item[key])
                    result.append(_owner_result(root, group, grouped, scope, context, base))
            except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
                result.append({'request_id': group['request_id'], 'blocked': True, 'code': getattr(exc, 'code', 'NATIVE_REVIEW_SOURCE_UNAVAILABLE')})
        command_ref=artifact(path, 'native-human-command', base.name, command['schema_version'])
        batch_owner.refresh_execution_context(root,batch_id,context,command_ref,control_head=control_head)
        return {'command_ref': command_ref,
            'results': result, 'continuation_needed':any(r.get('deferred') for r in result),
            'all_native_completed': all(not r.get('blocked') and not r.get('deferred') for r in result)}


if __name__ == '__main__':
    import argparse, json, sys
    parser = argparse.ArgumentParser(); parser.add_argument('command', choices=('options', 'execute', 'commands'))
    parser.add_argument('--pipeline-root', type=Path, required=True); parser.add_argument('--batch-id', required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin); context = payload.pop('authorization_context')
        result = globals()[args.command](args.pipeline_root, args.batch_id, context=context, **payload)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'code': getattr(exc, 'code', 'CREATION_BATCH_REVIEW_INVALID')}, ensure_ascii=False)); sys.exit(1)
