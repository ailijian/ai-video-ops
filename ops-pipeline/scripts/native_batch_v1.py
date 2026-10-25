"""C03/C04 bounded intent and admission, delegated to the original Request owner.

These artifacts coordinate Native owners. They never mean generated, approved,
exported or communicated. Every such fact is read from its original owner.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from creation_batch_contract_v1 import BatchError, check
from creative_style_v1 import artifact, digest, file_sha, pinned
from human_review_operations_v1 import io_path, read, write_once
from operation_lock_v1 import operation_lock

POLICY = Path(__file__).with_name('creation_batch_policy_v2.json')
LEGACY_POLICY = POLICY.with_name('creation_batch_policy_v1.json')
TYPES = ('novel', 'repurpose', 'persona', 'story', 'conversion')
REQUEST_VERSION = 'generation-request-v1.2'
REPURPOSE_REQUEST_VERSION = 'news-delivery-request-v1.2'


def request_path(root, request_id):
    identifier(request_id)
    if request_id.startswith('news_'):
        return Path(root) / 'data/news_deliveries' / request_id / 'news_delivery_request_v1.json'
    return Path(root) / 'data/generation_requests' / request_id / 'generation_request_v1.json'


def validate_policy(value):
    """Only the two attributable engineering scopes; neither grants production."""
    if value.get('schema_version')=='native-batch-admission-policy-v1.1':
        expected={'schema_version':'native-batch-admission-policy-v1.1','policy_version':'production-1',
            'maximum_logical_slots':value.get('maximum_logical_slots'),
            'maximum_pending_native_requests':value.get('maximum_logical_slots'),
            'dispatch_per_business':1,'mix_style_quantities':[1,2],
            'allowed_profiles':value.get('allowed_profiles'),'maximum_explicit_cycles':1,
            'production_admission_ref':value.get('production_admission_ref'),
            'production_qualification_granted':True,'unknown_retry':'explicit-native-only','legacy_active_exception':False}
        from profile_compatibility_contract_v1_1 import REF,validate
        validate(value.get('production_admission_ref'),REF)
        count=value.get('maximum_logical_slots')
        if (type(count) is not int or not 1<=count<=5
                or value.get('allowed_profiles') not in [['mix'],['news'],['mix','news']]
                or digest(value)!=digest(expected)):
            raise BatchError('CREATION_BATCH_POLICY_INVALID','Invalid bounded production policy')
        return value
    version = value.get('policy_version')
    if version not in ('1', '2'):
        raise BatchError('CREATION_BATCH_POLICY_INVALID', 'Unknown Native admission policy')
    expected = {'schema_version': 'native-batch-admission-policy-v1.0', 'policy_version': version,
        'maximum_logical_slots': 5 if version == '1' else 40,
        'maximum_pending_native_requests': 5 if version == '1' else 40,
        'dispatch_per_business': 1, 'mix_style_quantities': [1, 2], 'allowed_profiles': ['mix', 'news'],
        'approval_scope_sha256': ('f50730536917c7460fca5a77c2c4a849cfa14e747bfc515d80d1e6ea2a758b53' if version == '1'
            else 'bf427221b72c8c88d18ffd106d96b47395273167bdd0d9e5f66ddd75b3c40caf'),
        'production_qualification_granted': False, 'unknown_retry': 'explicit-native-only', 'legacy_active_exception': False}
    if version == '2': expected['maximum_explicit_cycles'] = 5
    if digest(value) != digest(expected):
        raise BatchError('CREATION_BATCH_POLICY_INVALID', 'Policy differs from its approved exact engineering scope')
    return value


def batch_policy(root, batch_id):
    saved = read(directory(root, batch_id) / 'configuration.json')
    return validate_policy(saved['source_snapshot'].get('admission_policy') or read(LEGACY_POLICY))


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Invalid batch identity')
    return value


def directory(root, batch_id):
    return Path(root).resolve() / 'data/creation_batches' / identifier(batch_id)


def batch_id_for(business_id, context, operation_id):
    identifier(operation_id)
    return 'batch_' + digest({'business': business_id, 'actor': context['actor'], 'operation': operation_id})[:24]


def confirmation_for_operation(root, business_id, context, operation_id, *, configuration_value=None, speaker_id=None):
    """Read an actual C03 confirmation, never infer one from a saved draft."""
    from delivery_receipt_recovery_v1 import identity
    identity(context)
    batch_id=batch_id_for(business_id,context,operation_id)
    if not io_path(directory(root,batch_id)/'intent.json').is_file():return None
    assert_principal(root,batch_id,context)
    saved=read(directory(root,batch_id)/'configuration.json')
    if (saved['business_id']!=business_id or speaker_id is not None and saved['speaker_id']!=speaker_id
            or configuration_value is not None and saved['configuration']!=configuration(configuration_value,policy=batch_policy(root,batch_id))):
        raise BatchError('CREATION_BATCH_IDEMPOTENCY_CONFLICT','Stored draft does not match the actual confirmed intent')
    _,value=intent(root,batch_id)
    return {'batch_id':batch_id,'actual_target':value['actual_target'],'intent_ref':batch_ref(root,batch_id)}


def list_for_business(root, business_id, context):
    from delivery_receipt_recovery_v1 import identity
    identity(context);identifier(business_id)
    entries=[];blocked=[]
    paths=sorted((Path(root)/'data/creation_batches').glob('*/intent.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    for path in paths:
        try:raw=read(path)
        except (RuntimeError,OSError,ValueError):continue  # Cannot attribute corrupt foreign data to this caller.
        actor=raw.get('actor_intent')
        if raw.get('business_id')!=business_id or not isinstance(actor,dict) or actor.get('actor_id')!=str(context['actor']['user_id']):continue
        try:
            actual=confirmation_for_operation(root,business_id,context,raw['actor_intent']['operation_id'])
            if not actual or actual['batch_id']!=path.parent.name:
                raise BatchError('CREATION_BATCH_IDENTITY_INVALID','History must bind its original canonical operation')
            events=controls(root,actual['batch_id'])
            entries.append({**actual,'mode':raw['mode'],'operating_stage':raw['operating_stage'],
                'control':events[-1]['action'] if events else 'resume'})
        except (RuntimeError,OSError,ValueError,KeyError,TypeError) as exc:
            blocked.append({'batch_id':path.parent.name,'code':getattr(exc,'code','CREATION_BATCH_IDENTITY_INVALID')})
    return {'business_id':business_id,'batches':entries,'blocked':blocked}


def configuration(value, *, policy=None):
    if not isinstance(value, dict):
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Explicit configuration required')
    quantities = value.get('quantities')
    if (not isinstance(quantities, dict) or set(quantities) != set(TYPES)
            or any(type(n) is not int or n < 0 for n in quantities.values())):
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Each type needs an explicit non-negative integer')
    total = sum(quantities.values())
    policy = validate_policy(read(POLICY) if policy is None else policy)
    if not 1 <= total <= policy['maximum_logical_slots']:
        if policy.get('policy_version')=='production-1':
            raise BatchError('CREATION_BATCH_PRODUCTION_CAPACITY','Target exceeds the exact production batch admission')
        raise BatchError('CREATION_BATCH_CAPACITY_NOT_APPROVED', 'Current approved isolated batch scope is 1..40 videos')
    mode, stage = value.get('mode'), value.get('stage')
    if mode not in ('free', 'stage') or mode == 'stage' and stage not in ('launch', 'trust', 'steady'):
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Unknown creation mode or stage')
    if mode == 'stage' and stage != 'steady':
        target = value.get('combinedTarget')
        if type(target) is not int or target != quantities['persona'] + quantities['story']:
            raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Explicit persona/story allocation must match the actual target')
    cycles = value.get('cycles') if mode == 'stage' and stage == 'steady' else None
    if cycles is not None and (type(cycles) is not int or cycles < 1
            or policy.get('maximum_explicit_cycles') is not None and cycles > policy['maximum_explicit_cycles']
            or value.get('cyclesConfirmed') is not True):
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Confirm a finite number of cycles')
    if mode == 'stage' and stage == 'steady' and cycles is None:
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'A finite cycle count is required')
    if quantities['repurpose'] and value.get('repurposeEnabled') is not True:
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Repurpose must be selected explicitly')
    revision = value.get('revision')
    if type(revision) is not int or revision < 0:
        raise BatchError('CREATION_BATCH_CONFIGURATION_INVALID', 'Invalid draft revision')
    result = {'mode': mode, 'operating_stage': stage if mode == 'stage' else None,
            'explicit_cycles': cycles, 'draft_revision': revision + 1, 'quantities': dict(quantities)}
    selected = value.get('repurposeSourceIds', [])
    if (not isinstance(selected,list) or len(selected)!=quantities['repurpose'] or any(not isinstance(v,str) for v in selected)
            or len(set(selected))!=len(selected)):
        raise BatchError('CREATION_BATCH_REPURPOSE_SELECTION_REQUIRED','Explicit distinct historical source IDs must match the Repurpose quantity')
    for source_id in selected: identifier(source_id)
    if selected: result['repurpose_source_ids'] = list(selected)
    return result


def preview(root, business_id, speaker_id, value, context, operation_id):
    """No writes or remote calls. Native owners establish every qualification."""
    from delivery_receipt_recovery_v1 import identity as principal
    from show_customer_status_v1 import resolve_current_persona, resolve_speaker_persona
    from content_creation_entry_v1 import build_content_creation_entry
    from creative_style_v1 import catalog_snapshot, validate_style_facts, definition
    principal(context)
    identifier(operation_id)
    root = Path(root).resolve()
    payload = configuration(value)
    active = policy_qualification(root)
    policy = validate_policy(read(POLICY))
    if active['manifest'].get('schema_version')=='creative-authority-release-v1.3':
        from production_admission_v1 import batch_policy,require_selection
        policy=batch_policy(active)
        payload=configuration(value,policy=policy)
        for kind,count in payload['quantities'].items():
            if count:
                require_selection(active,style=kind if kind in ('persona','story','conversion') else None,
                    profile='news' if kind in ('novel','repurpose') else 'mix',
                    reuse_intent='cross_profile_repurpose' if kind=='repurpose' else 'novel_content',execution=True)
    business = resolve_current_persona(root, business_id, 'business')
    speaker = resolve_speaker_persona(root, business, speaker_id)
    business_ref = artifact(business['path'], 'native-business', business_id, business['revision'])
    speaker_ref = artifact(speaker['path'], 'native-speaker', speaker_id, speaker['revision'])
    has_mix = any(payload['quantities'][k] for k in ('persona', 'story', 'conversion'))
    catalog_ref, catalog = catalog_snapshot(root, publish=False) if has_mix else (None, {'styles': []})
    release = active['binding']['release_ref']
    release_ref = artifact(root / release['path'], 'native-release', active['manifest']['release_id'], active['manifest']['schema_version'])
    batch_id = batch_id_for(business_id, context, operation_id)
    slots = []
    for kind in TYPES:
        quantity = payload['quantities'][kind]
        if not quantity:
            continue
        choices = [None] * quantity
        style = None
        sources = [business_ref, speaker_ref, release_ref]
        if kind in ('persona', 'story', 'conversion'):
            rule = next(r for r in catalog['styles'] if r['style_id'] == kind)
            native_quantity = min(max(validate_policy(read(POLICY))['mix_style_quantities']), quantity)
            if native_quantity not in rule['allowed_quantities'] or (quantity % native_quantity and 1 not in rule['allowed_quantities']):
                raise BatchError('CREATION_BATCH_STYLE_QUANTITY_UNSUPPORTED', 'This exact Style quantity has not passed its Native qualification')
            validate_style_facts(kind, definition(kind), read(business['path']), read(speaker['path']))
            entry = build_content_creation_entry(pipeline_root=root, business_id=business_id,
                speaker_id=speaker_id, profile='mix', requested_quantity=native_quantity)
            recommendation = entry.get('recommendation') or {}
            if not recommendation.get('can_continue') or recommendation.get('recommended_quantity') != native_quantity:
                raise BatchError('CREATION_BATCH_SOURCE_CAPACITY', 'Native capacity cannot satisfy this Style target; no silent quantity/type replacement')
            style = {'style_id': kind, 'style_version': rule['style_version'], 'catalog_ref': catalog_ref,
                     'definition_sha256': digest(rule)}
            sources += [*rule['pattern_scope_refs'], *rule['compatibility_scope_refs'], rule['release_ref']]
        elif kind == 'novel':
            from novel_news_opportunity_v1 import project_novel_news_opportunities
            options = project_novel_news_opportunities(pipeline_root=root, business_id=business_id, speaker_id=speaker_id)
            choices = [c for c in options['opportunities'] if c['novelty_status'] == 'novel'
                       and c['production_feasibility'].get('status') == 'supported'][:quantity]
            if len(choices) != quantity:
                raise BatchError('CREATION_BATCH_SOURCE_CAPACITY', 'Not enough distinct qualified Novel opportunities; Repurpose cannot fill the gap')
        else:
            from news_delivery_v1 import preview_news_delivery
            available = preview_news_delivery(pipeline_root=root,business_id=business_id,speaker_id=speaker_id)
            eligible = {c['source_content_id']:c for c in available['eligible_sources']}
            selected = payload['repurpose_source_ids']
            if any(source_id not in eligible for source_id in selected):
                raise BatchError('CREATION_BATCH_REPURPOSE_SOURCE_UNAVAILABLE','Selected historical source is unavailable; no Novel/Repurpose replacement')
            choices = [eligible[source_id] for source_id in selected]
        for choice in choices:
            source_refs = list(sources)
            if kind == 'repurpose':
                from news_delivery_v1 import batch_source_snapshot
                source_refs.append(batch_source_snapshot(root,business_id,choice['source_content_id']))
            elif choice:
                source_refs.append({**business_ref, 'owner': 'native-novel-opportunity', 'id': choice['concept_id']})
            slots.append({'slot_id': batch_id + f'-S{len(slots) + 1:03d}', 'production_profile': 'mix' if style else 'news',
                          'creative_style': copy.deepcopy(style), 'source_kind': 'cross_profile_repurpose' if kind == 'repurpose' else 'novel_content',
                          'source_refs': source_refs, 'business_type_id': kind if style else 'news'})
    snapshot = {'business_id': business_id, 'speaker_id': speaker_id, 'configuration': payload,
                'slots': slots, 'qualification': active['binding'],
                'memory': __import__('content_intent_reservations_v1').memory(root, business_id),
                'admission_policy': policy}
    return {'schema_version': 'native-batch-preflight-v1.0', 'batch_id': batch_id, 'actual_target': len(slots),
            'new_content_target': len(slots) - payload['quantities']['repurpose'], 'can_confirm': True,
            'source_configuration_sha256': digest(snapshot), 'snapshot': snapshot, 'no_mutation': True}


def confirm(root, business_id, speaker_id, value, context, operation_id, expected_sha256):
    from delivery_receipt_recovery_v1 import identity as principal
    from creative_style_v1 import catalog_snapshot, check as check_style
    principal(context)
    identifier(operation_id)
    batch_id = batch_id_for(business_id, context, operation_id)
    base = directory(root, batch_id)
    from generation_request_handoff_v1 import _business_generation_lock
    with _business_generation_lock(Path(root), business_id):
        if io_path(base / 'intent.json').is_file():
            assert_principal(root, batch_id, context)
            payload = configuration(value, policy=batch_policy(root, batch_id))
            saved = read(base / 'configuration.json')
            if (saved['business_id'] != business_id or saved['speaker_id'] != speaker_id
                    or saved['configuration'] != payload or saved['preflight_sha256'] != expected_sha256):
                raise BatchError('CREATION_BATCH_IDEMPOTENCY_CONFLICT', 'Confirmed batch payload or original preflight differs')
            return {'batch_id': batch_id, 'recovered': True}
        payload = configuration(value)
        checked = preview(root, business_id, speaker_id, value, context, operation_id)
        if checked['source_configuration_sha256'] != expected_sha256:
            raise BatchError('CREATION_BATCH_PREFLIGHT_STALE', 'Configuration, qualification, sources or memory changed; recheck explicitly')
        if any(payload['quantities'][k] for k in ('persona', 'story', 'conversion')):
            catalog_snapshot(root, publish=True)
        if payload['quantities']['repurpose']:
            from news_delivery_v1 import batch_source_snapshot
            for slot in checked['snapshot']['slots']:
                for reference in slot['source_refs']:
                    if reference['owner']=='native-repurpose-source':
                        if batch_source_snapshot(root,business_id,reference['id'],publish=True)!=reference:
                            raise BatchError('CREATION_BATCH_PREFLIGHT_STALE','Historical source snapshot changed before confirmation')
        permission = base / 'permission.json'
        if io_path(permission).is_file():
            original = read(permission)
            if original['actor'] != context['actor'] or any(original['authorization'][k] != context['authorization'][k]
                    for k in ('database_path', 'user_state_sha256')):
                raise BatchError('CREATION_BATCH_ACTOR_CONFLICT', 'Interrupted confirmation belongs to another stable principal')
        else:
            write_once(permission, context)
        saved = {'schema_version': 'native-batch-configuration-snapshot-v1.0', 'business_id': business_id,
            'speaker_id': speaker_id, 'configuration': payload, 'preflight_sha256': expected_sha256,
            'source_snapshot': checked['snapshot']}
        write_once(base / 'configuration.json', saved)
        slots = checked['snapshot']['slots']
        sources = list({r['path'] + r['sha256'] + r['owner'] + r['id']: r
                        for s in slots for r in s['source_refs']}.values())
        actor = {'actor_id': str(context['actor']['user_id']), 'operation_id': operation_id,
                 'permission_snapshot': artifact(permission, 'console-authorization', context['actor']['user_id'], '1'),
                 'payload_sha256': digest(checked['snapshot'])}
        record = check_style({'schema_version': 'creation-batch-intent-v1.0', 'batch_id': batch_id,
            'business_id': business_id, 'draft_revision': payload['draft_revision'], 'mode': payload['mode'],
            'operating_stage': payload['operating_stage'], 'explicit_cycles': payload['explicit_cycles'],
            'slots': slots, 'actual_target': len(slots), 'context_refs': sources,
            'explicit_confirmation': True, 'actor_intent': actor}, 'C03')
        write_once(base / 'intent.json', record)
        return {'batch_id': batch_id, 'recovered': False}


def intent(root, batch_id):
    from creative_style_v1 import check as check_style
    path = directory(root, batch_id) / 'intent.json'
    value = check_style(read(path), 'C03')
    saved = read(directory(root, batch_id) / 'configuration.json')
    snapshot = saved['source_snapshot']
    if (digest(snapshot) != value['actor_intent']['payload_sha256'] or saved['preflight_sha256'] != digest(snapshot)
            or saved['business_id'] != value['business_id'] or snapshot['business_id'] != value['business_id']
            or snapshot['configuration'] != saved['configuration'] or snapshot['slots'] != value['slots']):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Original confirmed configuration and source snapshot differ')
    if (value['batch_id'] != batch_id or value['actual_target'] != len(value['slots'])
            or not 1 <= value['actual_target'] <= batch_policy(root, batch_id)['maximum_logical_slots']
            or len({s['slot_id'] for s in value['slots']}) != len(value['slots'])):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Batch intent or Slot identity differs')
    for slot in value['slots']:
        if not slot['slot_id'].startswith(batch_id + '-S'):
            raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Slot belongs to a different batch')
        if slot['production_profile'] == 'mix':
            if slot['source_kind'] != 'novel_content' or not slot['creative_style'] or slot['business_type_id'] != slot['creative_style']['style_id']:
                raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Mix Style identity differs')
        elif (slot['production_profile'] != 'news' or slot['creative_style'] is not None
              or slot['business_type_id'] != 'news'):
            raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'News is a profile, never a fabricated Mix Style')
    return path, value


def batch_ref(root, batch_id):
    path, value = intent(root, batch_id)
    return artifact(path, 'native-request-batch', batch_id, value['schema_version'])


def current_context(root, batch_id):
    _, value = intent(root, batch_id)
    events = controls(root, batch_id)
    reference = events[-1]['actor_intent']['permission_snapshot'] if events else value['actor_intent']['permission_snapshot']
    refreshed=execution_contexts(root,batch_id)
    if refreshed and refreshed[-1]['control_head_ref']==_control_head_ref(root,batch_id):
        reference=refreshed[-1]['permission_ref']
    context = pinned(reference)
    assert_principal(root, batch_id, context)
    return context


def _control_head_ref(root,batch_id):
    chain=controls(root,batch_id)
    return (artifact(directory(root,batch_id)/'controls'/f'{len(chain):06d}.json',
        'native-request-batch',batch_id,'native-batch-control-v1.0') if chain else None)


def _execution_command(root,batch_id,reference):
    """An attributable explicit C07 intent, never proof of a Human approval."""
    command=check(pinned(reference),'C07');_,batch=intent(root,batch_id)
    original=pinned(batch['actor_intent']['permission_snapshot']);actor=command['actor_intent']
    key=digest({'actor':original['actor'],'operation':actor['operation_id']})[:32]
    base=directory(root,batch_id)/'human_commands'/key
    permission=pinned(actor['permission_snapshot'])
    if (reference!=artifact(base/'command.json','native-human-command',key,command['schema_version'])
            or command['batch_intent_ref']!=batch_ref(root,batch_id) or command['business_id']!=batch['business_id']
            or actor['actor_id']!=str(original['actor']['user_id']) or permission['actor']!=original['actor']
            or actor['permission_snapshot']!=artifact(base/'permission.json','console-authorization',original['actor']['user_id'],'1')
            or any(permission['authorization'][k]!=original['authorization'][k] for k in ('database_path','user_state_sha256'))):
        raise BatchError('CREATION_BATCH_EXECUTION_CONTEXT_INVALID','Explicit command principal/source differs')
    identifier(actor['operation_id'])
    return command


def execution_contexts(root,batch_id):
    from delivery_receipt_recovery_v1 import CONTEXT
    from profile_compatibility_contract_v1_1 import validate
    _,batch=intent(root,batch_id);original=pinned(batch['actor_intent']['permission_snapshot'])
    home=directory(root,batch_id)/'execution_contexts';entries=[];parent=None
    for path in sorted((home/'events').glob('*.json')):
        value=read(path)
        if (set(value)!={'schema_version','batch_id','sequence','parent_ref','permission_ref','command_ref','control_head_ref'}
                or value['schema_version']!='native-batch-execution-context-v1.0' or value['batch_id']!=batch_id
                or value['sequence']!=len(entries)+1 or path.name!=f'{len(entries)+1:06d}.json' or value['parent_ref']!=parent):
            raise BatchError('CREATION_BATCH_EXECUTION_CONTEXT_INVALID','Execution context chain changed')
        _execution_command(root,batch_id,value['command_ref'])
        permission=pinned(value['permission_ref']);validate(permission,CONTEXT)
        expected=artifact(home/'permissions'/(digest(permission)+'.json'),'console-authorization',original['actor']['user_id'],'1')
        if (value['permission_ref']!=expected or permission['actor']!=original['actor']
                or any(permission['authorization'][k]!=original['authorization'][k] for k in ('database_path','user_state_sha256'))):
            raise BatchError('CREATION_BATCH_EXECUTION_CONTEXT_INVALID','Execution permission lost its original stable principal')
        if value['control_head_ref'] is not None:
            control_value=pinned(value['control_head_ref'])
            sequence=control_value.get('sequence')
            chain=controls(root,batch_id)
            if (type(sequence) is not int or not 1<=sequence<=len(chain) or control_value!=chain[sequence-1]
                    or value['control_head_ref']!=artifact(directory(root,batch_id)/'controls'/f'{sequence:06d}.json',
                        'native-request-batch',batch_id,'native-batch-control-v1.0')):
                raise BatchError('CREATION_BATCH_EXECUTION_CONTEXT_INVALID','Context control ancestry changed')
        entries.append(value)
        parent=artifact(path,'native-batch-execution-context',batch_id,value['schema_version'])
    return entries


def refresh_execution_context(root,batch_id,context,command_ref,*,control_head):
    """Persist a fresh authorized execution context after an explicit C07 action.

    C03, control history, C07 intent and Native approvals remain immutable.
    Session validity is rechecked at every subsequent Native operation.
    """
    from novel_news_generation_recovery_v1 import mutation_fence
    with mutation_fence(root),operation_lock(root,'creation-batch-context:'+identifier(batch_id)):
        assert_principal(root,batch_id,context);_execution_command(root,batch_id,command_ref)
        entries=execution_contexts(root,batch_id);home=directory(root,batch_id)/'execution_contexts'
        permission=home/'permissions'/(digest(context)+'.json')
        write_once(permission,context)
        reference=artifact(permission,'console-authorization',context['actor']['user_id'],'1')
        if (entries and entries[-1]['permission_ref']==reference and entries[-1]['command_ref']==command_ref
                and entries[-1]['control_head_ref']==control_head):return entries[-1]
        parent=(artifact(home/'events'/f'{len(entries):06d}.json','native-batch-execution-context',batch_id,
            'native-batch-execution-context-v1.0') if entries else None)
        value={'schema_version':'native-batch-execution-context-v1.0','batch_id':batch_id,'sequence':len(entries)+1,
            'parent_ref':parent,'permission_ref':artifact(permission,'console-authorization',context['actor']['user_id'],'1'),
            'command_ref':command_ref,'control_head_ref':control_head}
        write_once(home/'events'/f'{len(entries)+1:06d}.json',value)
        return value


def assert_principal(root, batch_id, context):
    from delivery_receipt_recovery_v1 import identity
    identity(context)
    _, value = intent(root, batch_id)
    original = pinned(value['actor_intent']['permission_snapshot'])
    if (context['actor'] != original['actor'] or any(context['authorization'][k] != original['authorization'][k]
            for k in ('database_path', 'user_state_sha256'))):
        raise BatchError('CREATION_BATCH_ACTOR_CONFLICT', 'The original stable principal and permissions are required')


def controls(root, batch_id):
    entries = []
    parent = None
    for path in sorted((directory(root, batch_id) / 'controls').glob('[0-9][0-9][0-9][0-9][0-9][0-9].json')):
        value = read(path)
        if (set(value) != {'schema_version', 'batch_id', 'sequence', 'action', 'parent', 'actor_intent'}
                or value['schema_version'] != 'native-batch-control-v1.0' or value['batch_id'] != batch_id
                or value['sequence'] != len(entries) + 1 or value['parent'] != parent
                or value['action'] not in ('pause', 'resume', 'end')):
            raise BatchError('CREATION_BATCH_CONTROL_INVALID', 'Batch control chain differs')
        entries.append(value)
        parent = artifact(path, 'native-request-batch', batch_id, value['schema_version'])
    return entries


def control(root, batch_id, action, context, operation_id):
    from novel_news_generation_recovery_v1 import mutation_fence
    from generation_request_handoff_v1 import _business_generation_lock
    _, value = intent(root, batch_id)
    # Same short provider fence as dispatch: after this event is committed,
    # no new automatic model call can pass an earlier pause/end check.
    with mutation_fence(root), _business_generation_lock(Path(root), value['business_id']), \
            operation_lock(root, 'creation-batch-provider:' + value['business_id']):
        return _control_locked(root, batch_id, action, context, operation_id)


def _control_locked(root, batch_id, action, context, operation_id):
    identifier(operation_id)
    if action not in ('pause', 'resume', 'end'):
        raise BatchError('CREATION_BATCH_CONTROL_INVALID', 'Unknown batch control')
    with operation_lock(root, 'creation-batch:' + identifier(batch_id)):
        assert_principal(root, batch_id, context)
        events = controls(root, batch_id)
        for old in events:
            if old['actor_intent']['operation_id'] == operation_id:
                if old['action'] != action:
                    raise BatchError('CREATION_BATCH_CONTROL_CONFLICT', 'Control replay differs')
                return old
        if events and events[-1]['action'] == 'end':
            raise BatchError('CREATION_BATCH_ENDED', 'An ended batch cannot restart; existing Native work remains reviewable')
        path = directory(root, batch_id) / 'controls' / f'{len(events) + 1:06d}.json'
        permission = path.with_suffix('.permission.json')
        write_once(permission, context)
        parent_path = directory(root, batch_id) / 'controls' / f'{len(events):06d}.json'
        value = {'schema_version': 'native-batch-control-v1.0', 'batch_id': batch_id,
                 'sequence': len(events) + 1, 'action': action,
                 'parent': artifact(parent_path, 'native-request-batch', batch_id, 'native-batch-control-v1.0') if events else None,
                 'actor_intent': {'actor_id': str(context['actor']['user_id']), 'operation_id': operation_id,
                     'permission_snapshot': artifact(permission, 'console-authorization', context['actor']['user_id'], '1'),
                     'payload_sha256': digest({'batch_id': batch_id, 'action': action})}}
        write_once(path, value)
        return value


def running(root, batch_id):
    values = controls(root, batch_id)
    return not values or values[-1]['action'] == 'resume'


def issue_local_delivery(root, batch_id, context, *, phase, subject_id, operation_id, source_sha256):
    """Native C06 dispatch evidence, never Human approval or an Export receipt.

    End stops work without this record. An already issued local operation may
    finish after End, under its original Owner's unchanged source/Human gates.
    """
    if phase not in ('publish_parent_export', 'composite_export') or not re.fullmatch(r'[a-f0-9]{64}', source_sha256):
        raise BatchError('CREATION_BATCH_DISPATCH_INVALID', 'Invalid local delivery phase/source')
    identifier(operation_id); identifier(subject_id)
    from novel_news_generation_recovery_v1 import mutation_fence
    from generation_request_handoff_v1 import _business_generation_lock
    _, batch = intent(root, batch_id)
    if (phase == 'composite_export' and subject_id != batch_id or phase == 'publish_parent_export'
            and subject_id not in {g['request_id'] for g in groups(root, batch_id)}):
        raise BatchError('CREATION_BATCH_DISPATCH_INVALID', 'Local delivery is outside the confirmed batch')
    key = digest({'phase': phase, 'subject_id': subject_id, 'operation_id': operation_id})
    base = directory(root, batch_id) / 'local_delivery_dispatch' / key
    with mutation_fence(root), _business_generation_lock(Path(root), batch['business_id']), \
            operation_lock(root, 'creation-batch-provider:' + batch['business_id']):
        assert_principal(root, batch_id, context); policy_qualification(root)
        path = base / 'dispatch.json'; permission = base / 'permission.json'
        if io_path(permission).is_file():
            original = read(permission)
            if original['actor'] != context['actor'] or any(original['authorization'][k] != context['authorization'][k]
                    for k in ('database_path', 'user_state_sha256')):
                raise BatchError('CREATION_BATCH_DISPATCH_INVALID', 'Original local dispatch principal differs')
        if not io_path(path).is_file() and not running(root, batch_id):
            raise BatchError('CREATION_BATCH_PAUSED', 'No new automatic local delivery after pause/end')
        write_once(permission, read(permission) if io_path(permission).is_file() else context)
        value = {'schema_version': 'native-batch-local-delivery-dispatch-v1.0',
            'batch_intent_ref': batch_ref(root, batch_id), 'phase': phase, 'subject_id': subject_id,
            'operation_id': operation_id, 'source_sha256': source_sha256,
            'permission_ref': artifact(permission, 'console-authorization', context['actor']['user_id'], '1')}
        write_once(path, value)
        return artifact(path, 'native-batch-local-dispatch', operation_id, value['schema_version'])


def settle(root,batch_id):
    """Original Request/Quality terminal bookkeeping, with no model/approval."""
    from novel_news_generation_recovery_v1 import mutation_fence
    from generation_request_handoff_v1 import _business_generation_lock
    from content_intent_reservations_v1 import settle_request
    from profile_compatibility_release_v1_1 import _control,control_read
    from profile_compatibility_contract_v1_1 import CONTROL_LOCK
    from operation_lock_v1 import OperationLockTimeout
    _,value=intent(root,batch_id)
    # End has already committed. Qualification held by an issued Native
    # producer must not make the HTTP command wait across its external call.
    # Keep all holds and finish bookkeeping later; no write bypasses the gate.
    with mutation_fence(root):
        try:
            with control_read(_control(root)[1],timeout_seconds=0.0):
                policy_qualification(root)
                return _settle_qualified(root,batch_id,value)
        except OperationLockTimeout as exc:
            if exc.key!=CONTROL_LOCK:raise
            return [{'request_id':g['request_id'],'event':'retained','code':'CREATION_BATCH_SETTLEMENT_DEFERRED'}
                for g in groups(root,batch_id) if io_path(directory(root,batch_id)/'admissions'/(g['request_id']+'.json')).is_file()]


def _settle_qualified(root,batch_id,value):
    from generation_request_handoff_v1 import _business_generation_lock
    from content_intent_reservations_v1 import settle_request
    result=[]
    with _business_generation_lock(Path(root),value['business_id']), \
            operation_lock(root,'creation-batch-provider:'+value['business_id']):
        chain=controls(root,batch_id)
        end_ref=(artifact(directory(root,batch_id)/'controls'/f"{len(chain):06d}.json",
            'native-request-batch',batch_id,'native-batch-control-v1.0') if chain and chain[-1]['action']=='end' else None)
        for group in groups(root,batch_id):
            path=directory(root,batch_id)/'admissions'/(group['request_id']+'.json')
            if not io_path(path).is_file():continue
            try:
                item=settle_request(root,value['business_id'],group['request_id'],batch_ref(root,batch_id),end_ref=end_ref)
                if item:result.append(item)
            except (RuntimeError,OSError,ValueError,KeyError,TypeError) as exc:
                # End remains an immutable operator action. A damaged or
                # uncertain Native source keeps its hold and needs recovery.
                result.append({'request_id':group['request_id'],'event':'retained',
                    'code':getattr(exc,'code','CONTENT_SETTLEMENT_INVALID')})
    return result


def novel_dispatch_allowed(root, request, attempt, context):
    """Automatic unissued work stops; original explicit issued-slot recovery
    keeps its Native Human/source/cost authority and cannot restart the batch.
    Caller holds the shared short provider fence and original REC-01 fences.
    """
    if not request.get('batch_admission_ref'):
        return True
    admission = validate_admission(request['batch_admission_ref'], root=root, context=context, request=request)
    from content_intent_reservations_v1 import assert_executable
    assert_executable(root,request['persona_id'],request['request_id'])
    batch_id = pinned(admission['batch_intent_ref'])['batch_id']
    if running(root, batch_id):
        return True
    parent = attempt['intent'].get('parent')
    if not parent:
        return False
    from novel_news_generation_recovery_v1 import directory as recovery_directory, validate, evidence
    parent_path = recovery_directory(root, request['request_id'], parent['operation_id']) / 'intent.json'
    previous = validate(read(parent_path), 'intent')
    if (file_sha(parent_path) != parent['sha256'] or previous['request_id'] != request['request_id']
            or previous['actor'] != attempt['intent']['actor']):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Explicit Native recovery parent differs')
    return evidence(root, request['request_id'], {**parent, 'intent':previous}, 'dispatch') is not None


def groups(root, batch_id):
    _, value = intent(root, batch_id)
    policy = batch_policy(root, batch_id)
    result = []
    for slot in value['slots']:
        style = slot['creative_style']
        key = style['style_id'] if style else slot['slot_id']
        same = [g for g in result if g.get('style_key') == key]
        group = same[-1] if same else None
        if style and policy['policy_version'] in ('2','production-1') and group and len(group['slots']) >= max(policy['mix_style_quantities']):
            group = None
        if group is None:
            group = {'group_id': key if not same else key + '-' + str(len(same)+1).zfill(3),
                     'style_key': key, 'profile': slot['production_profile'], 'creative_style': style,
                     'source_kind': slot['source_kind'], 'slots': []}
            result.append(group)
        group['slots'].append(slot)
    for group in result:
        group['operation_id'] = digest({'batch': batch_id, 'slots': [s['slot_id'] for s in group['slots']]})
        from generation_request_handoff_v1 import request_id_for
        if group['source_kind'] == 'cross_profile_repurpose':
            from news_delivery_v1 import request_id_for as repurpose_id
            source_id=next(r['id'] for s in group['slots'] for r in s['source_refs'] if r['owner']=='native-repurpose-source')
            speaker_id=next(r['id'] for r in value['context_refs'] if r['owner']=='native-speaker')
            group['request_id']=repurpose_id(value['business_id'],speaker_id,source_id,group['operation_id'])
        else:
            group['request_id'] = request_id_for(value['business_id'], group['operation_id'])
    return result


def policy_qualification(root):
    from creative_style_v1 import active_qualification
    active = active_qualification(root)
    if active['manifest'].get('schema_version')=='creative-authority-release-v1.3':
        from production_admission_v1 import validate_active
        validate_active(active)
    elif active['manifest'].get('purpose')!='isolated-validation':
        raise BatchError('CREATION_BATCH_ISOLATED_SCOPE_REQUIRED', 'The approved engineering policy grants no production batch eligibility')
    declared = {v['path']: v for v in active['manifest']['source_files']}
    for name in ('native_batch_v1.py', 'creation_batch_contract_v1.py', 'creation_batch_contracts_v1.json',
                 'creation_batch_policy_v1.json', 'creation_batch_policy_v2.json', 'content_intent_reservations_v1.py', 'batch_provider_recovery_v1.py'):
        key = 'ops-pipeline/scripts/' + name
        if key not in declared or declared[key]['checkout_sha256'] != file_sha(POLICY.with_name(name)):
            raise BatchError('CREATION_BATCH_QUALIFICATION_REQUIRED', 'The exact executing batch owners and bounded policy require an activated Native release')
    return active


def admission(root, batch_id, group_id, context):
    """Called in a short original Business lock; never around a remote call."""
    assert_principal(root, batch_id, context)
    path, value = intent(root, batch_id)
    group = next((g for g in groups(root, batch_id) if g['group_id'] == group_id), None)
    if group is None:
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Group is outside the confirmed batch')
    target = directory(root, batch_id) / 'admissions' / (group['request_id'] + '.json')
    existing_reference = None
    if io_path(target).is_file():
        current = check(read(target), 'C04')
        reference = artifact(target, 'native-request-admission', group['request_id'], current['schema_version'])
        validate_admission(reference, root=root, context=context)
        path = request_path(root, group['request_id'])
        if io_path(path).is_file():
            validate_admission(reference, root=root, context=context, request=read(path))
            return reference
        existing_reference = reference
    if not running(root, batch_id):
        raise BatchError('CREATION_BATCH_PAUSED', 'This batch no longer admits undispatched work')
    active = policy_qualification(root)
    original_snapshot = read(directory(root, batch_id) / 'configuration.json')['source_snapshot']
    from content_intent_reservations_v1 import memory
    if original_snapshot['memory'] != memory(root, value['business_id']):
        raise BatchError('CREATION_BATCH_MEMORY_CHANGED', 'Original confirmed batch memory changed; no automatic rebinding')
    if original_snapshot['qualification'] != active['binding']:
        raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Original confirmed qualification changed; re-confirmation is required')
    from show_customer_status_v1 import resolve_current_persona, resolve_speaker_persona
    business = resolve_current_persona(Path(root), value['business_id'], 'business')
    speaker_id = next(r['id'] for r in value['context_refs'] if r['owner'] == 'native-speaker')
    speaker = resolve_speaker_persona(Path(root), business, speaker_id)
    current_refs = [artifact(business['path'], 'native-business', value['business_id'], business['revision']),
                    artifact(speaker['path'], 'native-speaker', speaker_id, speaker['revision'])]
    if any(reference not in value['context_refs'] for reference in current_refs):
        raise BatchError('CREATION_BATCH_SOURCE_CHANGED', 'Current Business/Speaker differs before semantic admission')
    from generation_request_handoff_v1 import _request_is_in_flight
    for existing_path in (Path(root) / 'data/generation_requests').glob('*/generation_request_v1.json'):
        existing = read(existing_path)
        if existing.get('persona_id') != value['business_id'] or existing.get('request_id') == group['request_id']:
            continue
        if _request_is_in_flight(root, existing_path):
            if (existing.get('target_profile') or existing.get('profile')) == group['profile']:
                previous = (validate_admission(existing['batch_admission_ref'], root=root, request=existing)
                            if existing.get('batch_admission_ref') else None)
                if previous is None or previous['batch_intent_ref'] != batch_ref(root, batch_id):
                    raise BatchError('CREATION_BATCH_ACTIVE_REQUEST_CONFLICT', 'The original same-Profile Request gate still excludes legacy or another batch')
            if not known_local_outcome(root, existing['request_id']):
                raise BatchError('CREATION_BATCH_DISPATCH_OCCUPIED', 'Another Native Request has not produced a trustworthy local outcome')
    assert_no_unpublished_admissions(root, value['business_id'], group['profile'], group['request_id'])
    for path in (Path(root)/'data/news_deliveries').glob('*/news_delivery_request_v1.json'):
        existing=read(path);rid=existing.get('request_id')
        if existing.get('business_id')!=value['business_id'] or rid==group['request_id']:continue
        from news_delivery_v1 import request_cancelled,validate_news_delivery_export
        if path.with_name('news_delivery_export_closure_v1.json').is_file():
            validate_news_delivery_export(pipeline_root=Path(root),request_id=rid)
            continue
        if request_cancelled(root,rid):continue
        previous=admission_binding(existing['batch_admission_ref'],root=root,request=existing) if existing.get('batch_admission_ref') else None
        if group['profile']=='news' and (previous is None or previous['batch_intent_ref']!=batch_ref(root,batch_id)):
            raise BatchError('CREATION_BATCH_ACTIVE_REQUEST_CONFLICT','An original News Request is still active outside this batch')
        if not known_local_outcome(root,rid):
            raise BatchError('CREATION_BATCH_DISPATCH_OCCUPIED','A Native presentation Request has no trustworthy local result')
    if existing_reference is not None:
        return existing_reference
    sources = list({s['owner'] + s['id'] + s['path'] + s['sha256']: s
                    for slot in group['slots'] for s in slot['source_refs']}.values())
    from content_intent_reservations_v1 import reserve_admission
    reservation = reserve_admission(root, value['business_id'], group, sources)
    record = check({'schema_version': 'native-batch-admission-v1.1', 'business_id': value['business_id'],
        'batch_intent_ref': batch_ref(root, batch_id), 'native_request_id': group['request_id'],
        'style_ref': group['creative_style'], 'ordered_slots': [s['slot_id'] for s in group['slots']],
        'source_refs': sources, 'admission_policy_ref': retain_policy(root, batch_policy(root, batch_id)),
        'reservation_intent_ref': reservation, 'actor_intent': value['actor_intent']}, 'C04')
    write_once(target, record)
    return artifact(target, 'native-request-admission', group['request_id'], record['schema_version'])


def retain_policy(root, value=None):
    value = validate_policy(read(POLICY) if value is None else value)
    path = Path(root) / 'data/creation_batch_policies' / (digest(value) + '.json')
    write_once(path, value)
    return artifact(path, 'native-request-policy', 'batch', value['policy_version'])


def assert_no_unpublished_admissions(root, business_id, profile, request_id):
    """Original Request owner calls this inside its Business lock.

    An owner-issued admission survives a crash before Request publication.
    Legacy/foreign operations cannot overtake that journal window. Existing
    published Requests and exact-key recovery retain their original readers.
    """
    for path in sorted((Path(root) / 'data/creation_batches').glob('*/admissions/*.json')):
        value = read(path)
        rid = value.get('native_request_id')
        if value.get('business_id') != business_id or rid == request_id:
            continue
        reference = artifact(path, 'native-request-admission', rid, value['schema_version'])
        admission = validate_admission(reference, root=root)
        original = pinned(admission['batch_intent_ref'])
        group = next(g for g in groups(root, original['batch_id']) if g['request_id'] == rid)
        if group['profile'] == profile and not io_path(request_path(root, rid)).is_file():
            from content_intent_reservations_v1 import events
            chain=events(root,business_id,rid)
            if chain and chain[-1][1]['event']=='safely_released':
                continue  # Only a verified explicit Native cancellation.
            raise BatchError('CREATION_BATCH_ADMISSION_IN_FLIGHT', 'Recover the original admitted Request; another operation cannot take its place')


def validate_admission(reference, *, root=None, context=None, request=None):
    value=admission_binding(reference,root=root,request=request)
    batch=pinned(value['batch_intent_ref'])
    if root is None:root=Path(value['batch_intent_ref']['path']).parents[3]
    from content_intent_reservations_v1 import events
    if not events(root,value['business_id'],value['native_request_id']):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID','Original Native allocation is missing')
    if context is not None:assert_principal(root,batch['batch_id'],context)
    return value


def admission_binding(reference, *, root=None, request=None):
    """Original C04 immutable binding, without a recursive C05 head read.

    Public validate_admission additionally checks the complete reservation
    chain and current caller. C05's terminal reader reuses this same binding.
    """
    value = check(pinned(reference), 'C04')
    batch = pinned(value['batch_intent_ref'])
    if root is None:
        root = Path(value['batch_intent_ref']['path']).parents[3]
    expected = batch_ref(root, batch['batch_id'])
    group = next((g for g in groups(root, batch['batch_id']) if g['request_id'] == value['native_request_id']), None)
    if (value['batch_intent_ref'] != expected or value['business_id'] != batch['business_id'] or group is None
            or value['ordered_slots'] != [s['slot_id'] for s in group['slots']]
            or value['style_ref'] != group['creative_style']
            or value['actor_intent'] != batch['actor_intent']):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Admission differs from its confirmed scope')
    canonical = directory(root, batch['batch_id']) / 'admissions' / (group['request_id'] + '.json')
    if reference != artifact(canonical, 'native-request-admission', group['request_id'], value['schema_version']):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Only the canonical owner-issued admission is accepted')
    sources = list({s['owner'] + s['id'] + s['path'] + s['sha256']: s
                    for slot in group['slots'] for s in slot['source_refs']}.values())
    from content_intent_reservations_v1 import directory as reservation_directory
    first_path=reservation_directory(root,value['business_id'],group['request_id'])/'events/000001.json'
    if not io_path(first_path).is_file():
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Original Native semantic allocation is missing')
    first=check(read(first_path),'C05')
    original_memory = read(directory(root, batch['batch_id']) / 'configuration.json')['source_snapshot']['memory']
    if (first['business_id']!=value['business_id'] or first['native_request_id']!=group['request_id']
            or first.get('parent_event_ref') is not None or first['event']!='reserved'
            or value['source_refs'] != sources or first['source_refs'] != sources
            or first['slot_ids'] != value['ordered_slots'] or first['attempt_id'] != group['operation_id']
            or pinned(first['memory_ref']) != original_memory or first['fence_token'] != digest(original_memory)
            or value['reservation_intent_ref'] != artifact(first_path, 'native-content-quality', group['request_id'], first['schema_version'])):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Admission source or original reservation binding differs')
    policy = validate_policy(pinned(value['admission_policy_ref']))
    if (policy != batch_policy(root, batch['batch_id']) or len(batch['slots']) > policy['maximum_logical_slots']
            or len(groups(root, batch['batch_id'])) > policy['maximum_pending_native_requests']):
        raise BatchError('CREATION_BATCH_POLICY_INVALID', 'Unknown or unapproved Native admission policy')
    pinned(value['reservation_intent_ref'])
    if request is not None and group['source_kind']=='cross_profile_repurpose':
        speaker_id=next(r['id'] for r in batch['context_refs'] if r['owner']=='native-speaker')
        source_id=next(r['id'] for r in sources if r['owner']=='native-repurpose-source')
        if (request.get('schema_version')!=REPURPOSE_REQUEST_VERSION or request.get('business_id')!=value['business_id']
                or request.get('speaker_id')!=speaker_id or request.get('request_id')!=value['native_request_id']
                or request.get('source_content_id')!=source_id or request.get('reuse_intent')!='cross_profile_repurpose'
                or request.get('target_profile')!='news' or len(value['ordered_slots'])!=1
                or request.get('batch_admission_ref')!=reference):
            raise BatchError('CREATION_BATCH_IDENTITY_INVALID','Native Repurpose Request differs from its exact presentation admission')
    elif request is not None and (request.get('schema_version') != REQUEST_VERSION
            or request.get('persona_id') != value['business_id'] or request.get('request_id') != value['native_request_id']
            or request.get('quantity') != len(value['ordered_slots'])
            or request.get('target_profile') != group['profile']
            or request.get('creative_style') != value['style_ref']):
        raise BatchError('CREATION_BATCH_IDENTITY_INVALID', 'Native Request differs from admission')
    return value


def request_supported(request):
    if request.get('schema_version') != REQUEST_VERSION or not request.get('batch_admission_ref'):
        return False
    validate_admission(request['batch_admission_ref'], request=request)
    return True


def known_local_outcome(root, request_id):
    """Unknown remote execution never earns an active-request exception."""
    if request_id.startswith('news_'):
        from news_delivery_v1 import _request_root, _validate_plan_binding
        path=_request_root(Path(root),request_id)/'news_delivery_plan_v1.json'
        if not io_path(path).is_file():return False
        value=read(path);_validate_plan_binding(root,request_id,value)
        if (value.get('request_sha256')!=file_sha(request_path(root,request_id)) or value.get('request_id')!=request_id
                or value.get('status')!='review_required' or (value.get('validation') or {}).get('passed') is not True):
            raise BatchError('CREATION_BATCH_NATIVE_RESULT_INVALID','Native presentation plan/source differs')
        return True
    base = Path(root) / 'data/generation_batches' / request_id
    if io_path(base / 'generation_batch_v1.json').is_file():
        from resolve_generation_batch_v1 import generation_snapshot
        if generation_snapshot(Path(root), request_id).get('ready_for_human_review') is True:
            return True
    if io_path(base / 'novel_news_beat_plan_v1.json').is_file():
        from novel_news_v1 import novel_generation_state
        return novel_generation_state(Path(root), request_id).get('ready_for_human_review') is True
    path = Path(root) / 'data/generation_requests' / request_id / 'generation_request_v1.json'
    if io_path(path).is_file():
        request = read(path)
        if request.get('batch_admission_ref') and request.get('target_profile') == 'mix':
            from batch_provider_recovery_v1 import validated_local_outcome
            return validated_local_outcome(root, request) is not None
    return False


def active_exception(root, existing, reference):
    if not reference or not existing.get('batch_admission_ref'):
        return False
    current = validate_admission(reference, root=root)
    previous = validate_admission(existing['batch_admission_ref'], root=root, request=existing)
    return (current['batch_intent_ref'] == previous['batch_intent_ref']
            and current['business_id'] == previous['business_id']
            and known_local_outcome(root, existing['request_id']))
