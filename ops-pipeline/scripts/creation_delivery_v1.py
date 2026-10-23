"""Append-only delivery mechanics delegated by the three original Native writers.

No Content Ledger or Presentation writer is called here. The original closure
is completed once by its owner before any supplemental delivery is admitted.
"""
from __future__ import annotations
import os
from pathlib import Path

from profile_compatibility_contract_v1_1 import obj, REF, HASH, TEXT, ACTOR, OPERATION, array
from profile_compatibility_decisions_v1_1 import read, ref, resolve_ref, digest, file_sha, write_once
from publish_copy_contract_v1 import SCHEMAS, check, PublishCopyError, identifier
from publish_copy_sources_v1 import source, current_authority
from publish_copy_v1 import draft, confirmation, validate_payload, verify_draft, now
from novel_news_generation_recovery_v1 import identity, mutation_fence
from news_export_recovery_v1 import identity as validate_identity
from operation_lock_v1 import operation_lock
import publish_copy_excel_v1 as excel

PREFIX = 'creation-supplemental-delivery-'
NULL = {'oneOf': [REF, {'type': 'null'}]}
IDENTITY_FIELDS = {'delivery_id': OPERATION, 'request_ref': REF, 'request_kind': TEXT, 'business_id': TEXT,
    'actor': ACTOR, 'authorization': {'type':'object'}, 'production_targets': array({'type':'object'}, 1),
    'derived_payload_sha256': HASH, 'production_headlines_sha256': HASH,
    'original_receipt_ref': REF, 'original_anchor_ref': NULL, 'layout_version': TEXT, 'exporter_version': TEXT,
    'row_targets': array(TEXT, 1)}
SCHEMAS.update({
 PREFIX + 'intent-v1.0': obj({'schema_version': {'const': PREFIX + 'intent-v1.0'},
    'delivery_id': OPERATION, 'request_id': TEXT, 'business_id': TEXT, 'mode': TEXT, 'native_owner': TEXT,
    'source_sha256': HASH, 'source_refs': array(REF, 1), 'draft_ref': REF, 'confirmation_ref': REF,
    'payload_sha256': HASH, 'template_ref': REF, 'expected_head': NULL, 'original_receipt_ref': REF,
    'original_closure_ref': REF, 'output_path': TEXT, 'exporter_version': {'const': 'publish-copy-excel-v1.0'},
    **{k:v for k,v in IDENTITY_FIELDS.items() if k not in {'delivery_id','business_id','actor','authorization','exporter_version','original_receipt_ref'}},
    'operation_id': OPERATION, 'parent_delivery_ref': NULL,
    'actor': ACTOR, 'authorization': {'type': 'object'}, 'created_at': TEXT}),
 PREFIX + 'prepared-v1.0': obj({'schema_version': {'const': PREFIX + 'prepared-v1.0'},
    'intent_ref': REF, 'staged_ref': REF, 'output_ref': REF, 'workbook_parts_sha256': HASH}),
 PREFIX + 'receipt-v1.0': obj({'schema_version': {'const': PREFIX + 'receipt-v1.0'},
    'intent_ref': REF, 'prepared_ref': REF, 'output_ref': REF, 'source_sha256': HASH,
    'confirmation_ref': REF, 'template_ref': REF, 'original_closure_ref': REF,
    **IDENTITY_FIELDS, 'row_count': {'type': 'integer', 'minimum': 1}, 'created_at': TEXT}),
 PREFIX + 'completion-v1.0': obj({'schema_version': {'const': PREFIX + 'completion-v1.0'},
    'receipt_ref': REF, 'original_closure_ref': REF, 'semantic_delta': {'const': 0},
    'exposure_delta': {'const': 0}, 'presentation_delta': {'const': 0},
    'delivery_id': OPERATION, 'created_at': TEXT, 'expected_head': NULL}),
 'creation-delivery-effective-version-event-v1.0': obj({
    'schema_version': {'const': 'creation-delivery-effective-version-event-v1.0'},
    'request_id': TEXT, 'business_id': TEXT, 'parent': NULL, 'parent_delivery': NULL,
    'event_id': OPERATION, 'operation_id': OPERATION, 'actor': ACTOR, 'created_at': TEXT,
    'delivery_id': OPERATION, 'receipt_ref': REF, 'completion_ref': REF,
    'source_sha256': HASH, 'original_closure_ref': REF}),
})

def directory(src): return src['_directory'] / 'deliveries'
def event_head(root, src):
    from publish_copy_v1 import chain
    current = chain(root, directory(src).glob('effective/*.json'))
    for path in directory(src).glob('effective/*.json'):
        event = _load(path, 'creation-delivery-effective-version-event-v1.0')
        parent = read(resolve_ref(root, event['parent'])) if event['parent'] else None
        expected_parent_delivery = parent['receipt_ref'] if parent else None
        result = validate_completed(root, src, event['delivery_id'])
        intent=read(directory(src)/event['delivery_id']/'intent.json')
        if (event['parent_delivery'] != expected_parent_delivery or event['receipt_ref'] != result['receipt_ref']
            or event['completion_ref'] != result['completion_ref'] or event['source_sha256'] != src['source_sha256']
            or event['parent']!=intent['expected_head'] or event['parent_delivery']!=intent['parent_delivery_ref']
            or event['actor']!=intent['actor'] or event['operation_id']!=intent['operation_id']
            or event['event_id']!=event['delivery_id'] or path.stem!=event['event_id']):
            raise PublishCopyError('DELIVERY_CHAIN_INVALID')
    if current:
        value = current[1]
        if value['request_id'] != src['request_id'] or value['business_id'] != src['business_id']:
            raise PublishCopyError('DELIVERY_CHAIN_INVALID')
        validate_completed(root, src, value['delivery_id'])
    return current

def _load(path, version): return check(read(path), version)

def validate_completed(root, src, delivery_id):
    identifier(delivery_id, r'[a-f0-9]{32}')
    base = directory(src) / delivery_id
    intent = _load(base / 'intent.json', PREFIX + 'intent-v1.0')
    receipt = _load(base / 'receipt.json', PREFIX + 'receipt-v1.0')
    prepared = _load(base / 'prepared.json', PREFIX + 'prepared-v1.0')
    complete = _load(base / 'completion.json', PREFIX + 'completion-v1.0')
    dpath = resolve_ref(root, intent['draft_ref']); dvalue = _load(dpath, 'publish-copy-draft-v1.0')
    cpath = resolve_ref(root, intent['confirmation_ref']); cvalue = _load(cpath, 'publish-copy-confirmation-v1.0')
    output = resolve_ref(root, receipt['output_ref'])
    template_path = resolve_ref(root, intent['template_ref'])
    material={k:v for k,v in intent.items() if k not in {'schema_version','delivery_id','operation_id','parent_delivery_ref',
        'expected_head','output_path','created_at'}}
    expected_id=digest({**material,'expected_head':intent['expected_head']})[:32]
    expected_owner={'mix':'export_mix_excel_v1','novel_content':'novel_news_v1','cross_profile_repurpose':'news_delivery_v1'}[src['mode']]
    if (expected_id!=delivery_id or intent['operation_id']!=delivery_id or intent['native_owner']!=expected_owner
        or intent['source_refs']!=src['refs']):raise PublishCopyError('DELIVERY_IDENTITY_CONFLICT')
    if (intent['request_id'] != src['request_id'] or intent['business_id'] != src['business_id']
        or intent['delivery_id'] != delivery_id or intent['mode'] != src['mode']
        or intent['source_sha256'] != src['source_sha256'] or dvalue['source_sha256'] != src['source_sha256']
        or intent['payload_sha256'] != digest(dvalue['payload']) or cvalue['draft_ref'] != intent['draft_ref']
        or cvalue['payload_sha256'] != intent['payload_sha256']
        or cvalue['headline_mapping_sha256'] != digest([i.get('production_headlines') for i in dvalue['payload']['items']])
        or prepared['intent_ref'] != ref(root, base / 'intent.json') or receipt['intent_ref'] != prepared['intent_ref']
        or receipt['prepared_ref'] != ref(root, base / 'prepared.json')
        or receipt['output_ref'] != prepared['output_ref'] or receipt['output_ref']['path'] != intent['output_path']
        or receipt['source_sha256'] != intent['source_sha256'] or receipt['confirmation_ref'] != intent['confirmation_ref']
        or receipt['template_ref'] != intent['template_ref'] or complete['receipt_ref'] != ref(root, base / 'receipt.json')
        or any(v['original_closure_ref'] != intent['original_closure_ref'] for v in (receipt, complete))
        or receipt['row_count'] != len(src['items'])):
        raise PublishCopyError('DELIVERY_RECEIPT_INVALID')
    for key in IDENTITY_FIELDS:
        if receipt[key] != intent[key]: raise PublishCopyError('DELIVERY_RECEIPT_INVALID')
    if src['mode']=='mix':
        from close_generation_export_v1 import verify_generation_export_anchor
        anchor=verify_generation_export_anchor(pipeline_root=root,request_id=src['request_id'])
        if (intent['original_anchor_ref']!=anchor['anchor_ref'] or intent['original_closure_ref']!=anchor['closure_ref']):
            raise PublishCopyError('DELIVERY_ANCHOR_INVALID')
    elif intent['original_anchor_ref'] is not None:raise PublishCopyError('DELIVERY_ANCHOR_INVALID')
    if (intent['production_targets'] != dvalue['derived_targets'] or intent['row_targets'] != [i['target_id'] for i in src['items']]
        or intent['derived_payload_sha256'] != digest(dvalue['payload']) or intent['request_ref'] != src['snapshot']['request_ref']
        or intent['production_headlines_sha256'] != cvalue['headline_mapping_sha256']
        or complete['delivery_id'] != delivery_id or complete['expected_head'] != intent['expected_head']):
        raise PublishCopyError('DELIVERY_RECEIPT_INVALID')
    for value in (intent['original_receipt_ref'], intent['original_closure_ref'], prepared['staged_ref']):
        resolve_ref(root, value)
    validate_payload(dvalue['payload'], src)
    verify_draft(root, src, dvalue)
    if excel.validate_workbook(output, template_path, excel.rows(src, dvalue['payload'])) != prepared['workbook_parts_sha256']:
        raise PublishCopyError('WORKBOOK_INVALID')
    return {'request_id': src['request_id'], 'delivery_id': delivery_id, 'state': 'completed',
            'draft_ref': intent['draft_ref'],
            'output_path': str(output), 'output_sha256': receipt['output_ref']['sha256'],
            'receipt_ref': ref(root, base / 'receipt.json'), 'completion_ref': ref(root, base / 'completion.json')}

def export(root, rid, context, *, native_owner, ensure_core, expected_draft_ref=None):
    from publish_copy_v1 import delivery_fence
    with delivery_fence(root, rid):
        return _export_fenced(root, rid, context, native_owner=native_owner,
            ensure_core=ensure_core, expected_draft_ref=expected_draft_ref)


def _export_fenced(root, rid, context, *, native_owner, ensure_core, expected_draft_ref):
    root = Path(root).resolve(); src = source(root, rid); proof = identity(context)
    # Reject an unconfirmed/stale or differently authorized Publish version
    # before the delegated core writer can create Receipt/Closure/Ledger state.
    current=draft(root,rid)
    if (not current or current[1]['source_sha256']!=src['source_sha256']
            or expected_draft_ref is not None and ref(root,current[0])!=expected_draft_ref):
        raise PublishCopyError('CONFIRMED_DRAFT_REQUIRED')
    validate_payload(current[1]['payload'],src);verify_draft(root,src,current[1])
    confirmed=confirmation(root,rid,current[1])
    if not confirmed:raise PublishCopyError('CONFIRMED_DRAFT_REQUIRED')
    validate_identity(context,confirmed[1])
    # Original writers retain sole ownership of the core Export/Closure/Ledger.
    original_receipt, original_closure = ensure_core(src)
    src = source(root, rid)
    from news_qualification_v1_2 import prohibit_write
    prohibit_write(root)
    with mutation_fence(root), current_authority(root, src), operation_lock(root, 'business:' + src['business_id']):
        from ledger_history_v1 import history_lock
        with history_lock(root,src['business_id']):
            return _export_locked(root,rid,context,native_owner,original_receipt,original_closure,expected_draft_ref,proof)


def _export_locked(root,rid,context,native_owner,original_receipt,original_closure,expected_draft_ref,proof):
        src = source(root, rid); current = draft(root, rid)
        original_anchor=None
        if src['mode']=='mix':
            from close_generation_export_v1 import verify_generation_export_anchor
            anchor=verify_generation_export_anchor(pipeline_root=root,request_id=rid)
            if anchor['closure_ref']!=ref(root,original_closure):raise PublishCopyError('DELIVERY_ANCHOR_INVALID')
            original_anchor=anchor['anchor_ref']
        if expected_draft_ref is not None and (not current or ref(root, current[0]) != expected_draft_ref):
            raise PublishCopyError('DRAFT_CHANGED')
        if not current or current[1]['source_sha256'] != src['source_sha256']:
            raise PublishCopyError('CONFIRMED_DRAFT_REQUIRED', '请先核对并确认当前发布信息。')
        validate_payload(current[1]['payload'], src)
        verify_draft(root, src, current[1])
        confirmed = confirmation(root, rid, current[1])
        if not confirmed: raise PublishCopyError('CONFIRMED_DRAFT_REQUIRED')
        validate_identity(context, confirmed[1])
        template_path = excel.template(src['mode'], root)
        material = {'request_id': rid, 'business_id': src['business_id'], 'mode': src['mode'], 'native_owner': native_owner,
            'source_sha256': src['source_sha256'], 'source_refs': src['refs'], 'draft_ref': ref(root, current[0]),
            'confirmation_ref': ref(root, confirmed[0]), 'payload_sha256': digest(current[1]['payload']),
            'template_ref': ref(root, template_path), 'original_receipt_ref': ref(root, original_receipt),
            'original_anchor_ref': original_anchor,
            'original_closure_ref': ref(root, original_closure), 'exporter_version': 'publish-copy-excel-v1.0',
            'request_ref': src['snapshot']['request_ref'], 'request_kind': src['mode'],
            'production_targets': current[1]['derived_targets'], 'derived_payload_sha256': digest(current[1]['payload']),
            'production_headlines_sha256': confirmed[1]['headline_mapping_sha256'],
            'layout_version': 'mix-publish-5col-v1.0' if src['mode'] == 'mix' else 'news-publish-4col-v1.0',
            'row_targets': [i['target_id'] for i in src['items']],
            'actor': context['actor'], 'authorization': proof}
        head = event_head(root, src)
        existing = []
        for path in directory(src).glob('*/intent.json'):
            old = _load(path, PREFIX + 'intent-v1.0')
            if all(old[k] == v for k, v in material.items()): existing.append((path, old))
        if len(existing) > 1: raise PublishCopyError('DELIVERY_IDENTITY_CONFLICT')
        if existing:
            intent_path, intent = existing[0]; did = intent['delivery_id']
            if (intent_path.parent / 'completion.json').is_file():
                result = validate_completed(root, src, did)
                # A completed but not selected version still needs its original CAS.
                if head and head[1]['delivery_id'] == did: return result
                _select(root, src, intent_path, intent, head)
                return result
            validate_identity(context, intent)
        else:
            expected_head = ref(root, head[0]) if head else None
            did = digest({**material, 'expected_head': expected_head})[:32]
            intent = {'schema_version': PREFIX + 'intent-v1.0', 'delivery_id': did, **material,
                'operation_id': did, 'parent_delivery_ref': head[1]['receipt_ref'] if head else None,
                'expected_head': expected_head, 'output_path': 'output/deliveries/' + rid + '/' + did + '.xlsx', 'created_at': now()}
            intent_path = directory(src) / did / 'intent.json'
            write_once(intent_path, check(intent, intent['schema_version']))
        if intent['expected_head'] != (ref(root, head[0]) if head else None):
            raise PublishCopyError('DELIVERY_HEAD_CONFLICT', '已有另一份交付完成，请核对版本后继续。')
        base = intent_path.parent; staged = base / 'staged.xlsx'; prepared_path = base / 'prepared.json'
        output = root / intent['output_path']; data_rows = excel.rows(src, current[1]['payload'])
        if output.exists() and not prepared_path.is_file(): raise PublishCopyError('LEGACY_UNBOUND_ORPHAN')
        if not prepared_path.is_file():
            if not staged.is_file(): excel.render(staged, template_path, data_rows)
            parts_sha = excel.validate_workbook(staged, template_path, data_rows)
            prepared = {'schema_version': PREFIX + 'prepared-v1.0', 'intent_ref': ref(root, intent_path),
                'staged_ref': ref(root, staged), 'output_ref': {'path': intent['output_path'], 'sha256': file_sha(staged)},
                'workbook_parts_sha256': parts_sha}
            write_once(prepared_path, check(prepared, prepared['schema_version']))
        prepared = _load(prepared_path, PREFIX + 'prepared-v1.0')
        if (prepared['intent_ref'] != ref(root, intent_path) or prepared['staged_ref'] != ref(root, staged)
            or prepared['output_ref'] != {'path': intent['output_path'], 'sha256': file_sha(staged)}
            or prepared['workbook_parts_sha256'] != excel.validate_workbook(staged, template_path, data_rows)):
            raise PublishCopyError('DELIVERY_PUBLICATION_CONFLICT')
        if source(root, rid)['source_sha256'] != src['source_sha256']: raise PublishCopyError('SOURCE_CHANGED')
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            try: os.link(staged, output)
            except FileExistsError: pass
        if file_sha(output) != prepared['output_ref']['sha256']: raise PublishCopyError('DELIVERY_PUBLICATION_CONFLICT')
        excel.validate_workbook(output, template_path, data_rows)
        receipt_path = base / 'receipt.json'
        receipt = {'schema_version': PREFIX + 'receipt-v1.0', 'intent_ref': ref(root, intent_path),
            **{key:intent[key] for key in IDENTITY_FIELDS},
            'prepared_ref': ref(root, prepared_path), 'output_ref': prepared['output_ref'],
            'source_sha256': src['source_sha256'], 'confirmation_ref': intent['confirmation_ref'],
            'template_ref': intent['template_ref'], 'original_closure_ref': intent['original_closure_ref'],
            'row_count': len(data_rows), 'created_at': read(receipt_path)['created_at'] if receipt_path.is_file() else now()}
        write_once(receipt_path, check(receipt, receipt['schema_version']))
        complete = {'schema_version': PREFIX + 'completion-v1.0', 'receipt_ref': ref(root, receipt_path),
            'delivery_id': did, 'created_at': intent['created_at'], 'expected_head': intent['expected_head'],
            'original_closure_ref': intent['original_closure_ref'], 'semantic_delta': 0, 'exposure_delta': 0, 'presentation_delta': 0}
        write_once(base / 'completion.json', check(complete, complete['schema_version']))
        result = validate_completed(root, src, did)
        _select(root, src, intent_path, intent, head)
        return result

def _select(root, src, intent_path, intent, head):
    if intent['expected_head'] != (ref(root, head[0]) if head else None):
        raise PublishCopyError('DELIVERY_HEAD_CONFLICT')
    parent = head[1] if head else None; base = intent_path.parent
    value = {'schema_version': 'creation-delivery-effective-version-event-v1.0',
        'event_id': intent['delivery_id'], 'operation_id': intent['operation_id'],
        'actor': intent['actor'], 'created_at': intent['created_at'],
        'request_id': src['request_id'], 'business_id': src['business_id'], 'parent': intent['expected_head'],
        'parent_delivery': head[1]['receipt_ref'] if parent else None,
        'delivery_id': intent['delivery_id'], 'receipt_ref': ref(root, base / 'receipt.json'),
        'completion_ref': ref(root, base / 'completion.json'), 'source_sha256': src['source_sha256'],
        'original_closure_ref': intent['original_closure_ref']}
    write_once(directory(src) / 'effective' / (intent['delivery_id'] + '.json'), check(value, value['schema_version']))

def effective(root, rid):
    return _effective(root, source(root, rid))

def _effective(root, src):
    head = event_head(root, src)
    if not head: return None
    return validate_completed(root, src, head[1]['delivery_id'])


def read_version(root,rid,delivery_id):
    identifier(delivery_id,r'[a-f0-9]{32}')
    src=source(root,rid);head=event_head(root,src)
    path=directory(src)/'effective'/(delivery_id+'.json')
    if not path.is_file():raise PublishCopyError('DELIVERY_NOT_SELECTED')
    result=validate_completed(root,src,delivery_id)
    result['is_current']=bool(head and head[1]['delivery_id']==delivery_id)
    return result


def _composite_home(root, batch_id):
    from native_batch_v1 import directory as batch_directory
    return batch_directory(root, batch_id) / 'deliveries'


def _composite_qualification(root):
    from native_batch_v1 import policy_qualification
    active = policy_qualification(root)
    declared = {v['path']: v['checkout_sha256'] for v in active['manifest']['source_files']}
    for name in ('creation_delivery_v1.py', 'publish_copy_excel_v1.py', 'publish_copy_sources_v1.py'):
        if declared.get('ops-pipeline/scripts/' + name) != file_sha(Path(__file__).with_name(name)):
            raise PublishCopyError('COMPOSITE_QUALIFICATION_REQUIRED')
    return active


def _composite_material(root, batch_id, scope, slot_ids, *, parent_refs=None):
    """Original Delivery owner validates parents and rebuilds rows, never XLSX copies."""
    import native_batch_v1 as batch_owner
    from creative_style_v1 import artifact
    _, batch = batch_owner.intent(root, batch_id)
    if (scope not in ('complete_target', 'explicit_legal_subset') or not isinstance(slot_ids, list)
            or not slot_ids or len(set(slot_ids)) != len(slot_ids)):
        raise PublishCopyError('COMPOSITE_SCOPE_INVALID')
    slots = {s['slot_id']: s for s in batch['slots']}
    if set(slot_ids) - slots.keys() or scope == 'complete_target' and set(slot_ids) != slots.keys():
        raise PublishCopyError('COMPOSITE_SCOPE_INVALID')
    ordered = [s['slot_id'] for s in batch['slots'] if s['slot_id'] in slot_ids]
    if slot_ids != ordered: raise PublishCopyError('COMPOSITE_SCOPE_INVALID')
    rows, data, parents, sources = {}, {}, [], []
    def converted(value, owner, item_id):
        path = resolve_ref(root, value)
        return artifact(path, owner, item_id, read(path)['schema_version'])
    for group in batch_owner.groups(root, batch_id):
        selected = {s['slot_id'] for s in group['slots']} & set(slot_ids)
        if not selected: continue
        rid = group['request_id']; src = source(root, rid)
        if src['business_id'] != batch['business_id']: raise PublishCopyError('COMPOSITE_BUSINESS_CONFLICT')
        if parent_refs is None:
            parent = _effective(root, src)
        else:
            candidates = [r for r in parent_refs if Path(r['path']).name == 'receipt.json'
                and Path(r['path']).parent.parent == directory(src)]
            if len(candidates) != 1: raise PublishCopyError('COMPOSITE_PARENT_REQUIRED')
            parent = validate_completed(root, src, Path(candidates[0]['path']).parent.name)
        if parent is None: raise PublishCopyError('COMPOSITE_PARENT_REQUIRED')
        parent_intent = read(directory(src) / parent['delivery_id'] / 'intent.json')
        if parent_refs is None:
            current = draft(root, rid)
            confirmed = confirmation(root, rid, current[1]) if current else None
            if (not current or not confirmed or ref(root, current[0]) != parent_intent['draft_ref']
                    or ref(root, confirmed[0]) != parent_intent['confirmation_ref']):
                raise PublishCopyError('COMPOSITE_PARENT_VERSION_CHANGED')
        else:
            current = (resolve_ref(root, parent_intent['draft_ref']), read(resolve_ref(root, parent_intent['draft_ref'])))
        approved = read(resolve_ref(root, src['snapshot']['approved_ref']))
        by_content = {c['content_id']: c for c in approved.get('contents', [])}
        parent_rows = excel.rows(src, current[1]['payload'])
        parent_ref = converted(parent['receipt_ref'], 'native-supplemental-delivery', parent['delivery_id'])
        completion_ref = converted(parent['completion_ref'], 'native-supplemental-delivery', parent['delivery_id'])
        parents.extend([parent_ref, completion_ref]); sources.append(src)
        for item, values in zip(src['items'], parent_rows):
            if group['profile'] == 'mix':
                content = by_content.get(item['target_id']) or {}
                sid = content.get('logical_slot_id')
                if content.get('creative_style') != group['creative_style']:
                    raise PublishCopyError('COMPOSITE_STYLE_IDENTITY_INVALID')
            else:
                if len(group['slots']) != 1: raise PublishCopyError('COMPOSITE_SLOT_INVALID')
                sid = group['slots'][0]['slot_id']
                suffix = '-N001' if group['source_kind'] == 'novel_content' else '-P001'
                if item['target_id'] != rid + suffix: raise PublishCopyError('COMPOSITE_SLOT_INVALID')
            if sid not in selected: continue
            if sid in rows: raise PublishCopyError('COMPOSITE_SLOT_INVALID')
            slot = slots[sid]
            row = {'row_number': 5, 'slot_id': sid, 'style': slot['creative_style'],
                'source_kind': slot['source_kind'], 'business_type_id': slot['business_type_id'],
                'native_content_ref': converted(src['snapshot']['approved_ref'], 'native-approved-content', item['target_id']),
                'native_approved_ref': converted(src['snapshot']['approved_ref'], 'native-human-review', rid),
                'publish_draft_ref': converted(parent_intent['draft_ref'], 'native-publish-copy', rid),
                'publish_confirmation_ref': converted(parent_intent['confirmation_ref'], 'native-publish-confirmation', rid),
                'parent_receipt_ref': parent_ref, 'parent_completion_ref': completion_ref,
                'closure_ref': converted(parent_intent['original_closure_ref'], 'native-export-closure', rid)}
            if parent_intent['original_anchor_ref']:
                row['history_anchor_ref'] = converted(parent_intent['original_anchor_ref'], 'native-ledger-anchor', rid)
            rows[sid], data[sid] = row, values
    if set(rows) != set(slot_ids): raise PublishCopyError('COMPOSITE_APPROVED_SLOT_REQUIRED')
    if parent_refs is not None and parent_refs != parents: raise PublishCopyError('COMPOSITE_PARENT_VERSION_CHANGED')
    files, rendered = [], {}
    for profile in ('news', 'mix'):
        selected = [s for s in batch['slots'] if s['production_profile'] == profile and s['slot_id'] in rows]
        if not selected: continue
        records = [{**rows[s['slot_id']], 'row_number': i} for i, s in enumerate(selected, 5)]
        template_path = excel.template(profile, root)
        files.append({'production_profile': profile,
            'template_ref': artifact(template_path, 'native-delivery-template', profile, 'publish-v1'), 'ordered_rows': records})
        rendered[profile] = [data[s['slot_id']] for s in selected]
    return batch, {'business_id': batch['business_id'], 'batch_intent_ref': batch_owner.batch_ref(root, batch_id),
        'scope': scope, 'ordered_parent_refs': parents, 'files': files}, rendered, sources


def composite_preview(root, batch_id, context, *, scope, slot_ids):
    import native_batch_v1 as batch_owner
    batch_owner.assert_principal(root, batch_id, context)
    _composite_qualification(root)
    batch, material, _, _ = _composite_material(root, batch_id, scope, slot_ids)
    return {'source_sha256': digest(material), 'scope': scope, 'slot_ids': slot_ids,
        'target': batch['actual_target'], 'delivered': len(slot_ids), 'shortfall': batch['actual_target'] - len(slot_ids),
        'files': [{'profile': f['production_profile'], 'rows': len(f['ordered_rows']),
            'template_sha256': f['template_ref']['sha256']} for f in material['files']]}


def _composite_result(root, batch_id, base, expected=None):
    """Strict complete-set reader; any missing/corrupt file fails the entire set."""
    root = Path(root).resolve()
    from creation_batch_contract_v1 import check as batch_check
    from creative_style_v1 import artifact, pinned
    intent_path = base / 'intent.json'; value = batch_check(read(intent_path), 'C08')
    complete_path = base / 'completion.json'; complete = batch_check(read(complete_path), 'C08')
    declared = {r['slot_id'] for f in value['files'] for r in f['ordered_rows']}
    batch = __import__('native_batch_v1').intent(root, batch_id)[1]
    slot_ids = [s['slot_id'] for s in batch['slots'] if s['slot_id'] in declared]
    batch, material, rendered, sources = _composite_material(root, batch_id, value['scope'], slot_ids,
        parent_refs=value['ordered_parent_refs'])
    if expected is not None and material != expected: raise PublishCopyError('COMPOSITE_SOURCE_CHANGED')
    if ({k: v for k, v in value.items() if k not in ('schema_version', 'actor_intent')} != material
            or value['actor_intent']['payload_sha256'] != digest(material)
            or base.name != digest({'material': material, 'actor': value['actor_intent']})[:32]):
        raise PublishCopyError('COMPOSITE_IDENTITY_INVALID')
    permission = pinned(value['actor_intent']['permission_snapshot'])
    original = pinned(batch['actor_intent']['permission_snapshot'])
    __import__('native_batch_v1').identifier(value['actor_intent']['operation_id'])
    op = _composite_home(root, batch_id) / 'operations' / digest({'actor': permission['actor'],
        'operation_id': value['actor_intent']['operation_id']})
    binding = read(op / 'binding.json')
    if (value['actor_intent']['permission_snapshot'] != artifact(op / 'permission.json', 'console-authorization',
            permission['actor']['user_id'], '1') or binding != {'schema_version': 'creation-composite-operation-v1.0',
            'batch_id': batch_id, 'operation_id': value['actor_intent']['operation_id'], 'intent': value, 'delivery_id': base.name}):
        raise PublishCopyError('COMPOSITE_IDENTITY_INVALID')
    if (value['actor_intent']['actor_id'] != str(permission['actor']['user_id'])
            or permission['actor'] != original['actor'] or any(permission['authorization'][k] != original['authorization'][k]
            for k in ('database_path', 'user_state_sha256'))): raise PublishCopyError('COMPOSITE_ACTOR_INVALID')
    iref = artifact(intent_path, 'native-composite-delivery', base.name, value['schema_version'])
    receipts, outputs = [], []
    for f in material['files']:
        profile = f['production_profile']; path = base / (profile + '.receipt.json')
        receipt = batch_check(read(path), 'C08'); prepared_path = base / (profile + '.prepared.json')
        prepared = batch_check(read(prepared_path), 'C08')
        manifest_path = base / (profile + '.rows.json'); manifest = read(manifest_path)
        expected_manifest = {'schema_version': 'creation-composite-row-manifest-v1.0', 'intent_ref': iref,
            'production_profile': profile, 'ordered_rows': f['ordered_rows'], 'data_rows_sha256': digest(rendered[profile])}
        if manifest != expected_manifest: raise PublishCopyError('COMPOSITE_ROWS_INVALID')
        mref = artifact(manifest_path, 'native-composite-rows', profile, manifest['schema_version'])
        output = Path(root) / 'output/deliveries' / batch_id / base.name / (profile + '.xlsx')
        staged = base / (profile + '.xlsx')
        if (receipt['intent_ref'] != iref or prepared['intent_ref'] != iref
                or receipt['business_id'] != batch['business_id'] or prepared['business_id'] != batch['business_id']
                or receipt['production_profile'] != profile or prepared['production_profile'] != profile
                or receipt['actor_intent'] != value['actor_intent'] or prepared['actor_intent'] != value['actor_intent']
                or receipt['prepared_ref'] != artifact(prepared_path, 'native-composite-prepared', profile, prepared['schema_version'])
                or receipt['row_manifest_ref'] != mref or prepared['row_manifest_ref'] != mref
                or receipt['published_file_path'] != str(output) or prepared['prepared_file_path'] != str(staged)
                or prepared['template_ref'] != f['template_ref'] or prepared['output_bytes'] != staged.stat().st_size
                or file_sha(staged) != prepared['output_sha256'] or file_sha(output) != receipt['output_sha256']
                or receipt['output_sha256'] != prepared['output_sha256']): raise PublishCopyError('COMPOSITE_RECEIPT_INVALID')
        excel.validate_workbook(output, Path(f['template_ref']['path']), rendered[profile])
        excel.validate_workbook(staged, Path(f['template_ref']['path']), rendered[profile])
        receipts.append(artifact(path, 'native-composite-receipt', profile, receipt['schema_version']))
        outputs.append({'profile': profile, 'rows': len(f['ordered_rows']), 'path': str(output),
            'sha256': receipt['output_sha256'], 'receipt_ref': receipts[-1]})
    if complete != {'schema_version': 'creation-composite-delivery-completion-v1.0', 'business_id': batch['business_id'],
            'intent_ref': iref, 'ordered_file_receipt_refs': receipts, 'scope': value['scope'], 'delivered_slot_ids': slot_ids,
            'semantic_delta': 0, 'exposure_delta': 0, 'presentation_delta': 0, 'actor_intent': value['actor_intent']}:
        raise PublishCopyError('COMPOSITE_COMPLETION_INVALID')
    current_version = True
    for src in sources:
        head = _effective(root, src); current = draft(root, src['request_id'])
        parent_refs = [r for r in material['ordered_parent_refs'] if Path(r['path']).name == 'receipt.json'
            and Path(r['path']).parent.parent == directory(src)]
        if len(parent_refs) != 1 or head is None or current is None:
            current_version = False; continue
        parent = read(resolve_ref(root, head['receipt_ref']))
        parent_intent = read(directory(src) / head['delivery_id'] / 'intent.json')
        confirmed = confirmation(root, src['request_id'], current[1])
        if (str(resolve_ref(root, head['receipt_ref'])) != parent_refs[0]['path']
                or head['receipt_ref']['sha256'] != parent_refs[0]['sha256']
                or parent_intent['draft_ref'] != ref(root, current[0]) or confirmed is None
                or confirmed is not None and parent['confirmation_ref'] != ref(root, confirmed[0])):
            current_version = False
    return {'delivery_id': base.name, 'batch_id': batch_id, 'scope': value['scope'], 'slot_ids': slot_ids,
        'target': batch['actual_target'], 'delivered': len(slot_ids), 'shortfall': batch['actual_target'] - len(slot_ids),
        'source_sha256': digest(material), 'is_current': current_version, 'files': outputs,
        'completion_ref': artifact(complete_path, 'native-composite-completion', base.name, complete['schema_version'])}


def composite_export(root, batch_id, context, *, scope, slot_ids, operation_id, source_sha256):
    """A04 delegation: original multi-parent supplemental writer, zero ledger delta."""
    from contextlib import ExitStack
    import native_batch_v1 as batch_owner
    from creation_batch_contract_v1 import check as batch_check
    from creative_style_v1 import artifact
    root = Path(root).resolve(); batch_owner.identifier(operation_id)
    batch_owner.assert_principal(root, batch_id, context); _composite_qualification(root)
    home = _composite_home(root, batch_id)
    op = home / 'operations' / digest({'actor': context['actor'], 'operation_id': operation_id})
    if (op / 'binding.json').is_file():
        original = read(op / 'binding.json'); previous = original['intent']
        if (home / original['delivery_id'] / 'completion.json').is_file():
            old_material = {k: v for k, v in previous.items() if k not in ('schema_version', 'actor_intent')}
            result = _composite_result(root, batch_id, home / original['delivery_id'])
            if scope != previous['scope'] or slot_ids != result['slot_ids'] or source_sha256 != digest(old_material):
                raise PublishCopyError('COMPOSITE_IDENTITY_INVALID')
            return result
    batch, material, rendered, sources = _composite_material(root, batch_id, scope, slot_ids)
    if digest(material) != source_sha256: raise PublishCopyError('COMPOSITE_PREFLIGHT_STALE')
    from news_qualification_v1_2 import prohibit_write
    prohibit_write(root)
    from ledger_history_v1 import history_lock
    with mutation_fence(root), ExitStack() as stack:
        for src in sources: stack.enter_context(current_authority(root, src))
        stack.enter_context(operation_lock(root, 'business:' + batch['business_id']))
        stack.enter_context(history_lock(root, batch['business_id']))
        current_batch, current, rendered, _ = _composite_material(root, batch_id, scope, slot_ids)
        if current != material: raise PublishCopyError('COMPOSITE_SOURCE_CHANGED')
        saved_path = op / 'permission.json'
        if saved_path.is_file():
            saved = read(saved_path)
            identity(context)
            if (saved['actor'] != context['actor'] or any(saved['authorization'][k] != context['authorization'][k]
                    for k in ('database_path', 'user_state_sha256'))): raise PublishCopyError('COMPOSITE_ACTOR_INVALID')
        else: write_once(saved_path, context)
        actor = {'actor_id': str(context['actor']['user_id']), 'operation_id': operation_id,
            'permission_snapshot': artifact(saved_path, 'console-authorization', context['actor']['user_id'], '1'),
            'payload_sha256': digest(material)}
        value = batch_check({'schema_version': 'creation-composite-delivery-intent-v1.0', **material, 'actor_intent': actor}, 'C08')
        did = digest({'material': material, 'actor': actor})[:32]; base = home / did
        binding = {'schema_version': 'creation-composite-operation-v1.0', 'batch_id': batch_id,
            'operation_id': operation_id, 'intent': value, 'delivery_id': did}
        write_once(op / 'binding.json', binding)
        write_once(base / 'intent.json', value)
        if (base / 'completion.json').is_file(): return _composite_result(root, batch_id, base, material)
        iref = artifact(base / 'intent.json', 'native-composite-delivery', did, value['schema_version'])
        receipts = []
        for f in material['files']:
            profile = f['production_profile']; staged = base / (profile + '.xlsx')
            prepared_path = base / (profile + '.prepared.json'); receipt_path = base / (profile + '.receipt.json')
            output = root / 'output/deliveries' / batch_id / did / (profile + '.xlsx')
            if output.exists() and not prepared_path.is_file(): raise PublishCopyError('COMPOSITE_UNBOUND_ORPHAN')
            manifest = {'schema_version': 'creation-composite-row-manifest-v1.0', 'intent_ref': iref,
                'production_profile': profile, 'ordered_rows': f['ordered_rows'], 'data_rows_sha256': digest(rendered[profile])}
            manifest_path = base / (profile + '.rows.json'); write_once(manifest_path, manifest)
            if not staged.is_file(): excel.render(staged, Path(f['template_ref']['path']), rendered[profile])
            excel.validate_workbook(staged, Path(f['template_ref']['path']), rendered[profile])
            prepared = {'schema_version': 'creation-composite-delivery-prepared-v1.0', 'business_id': batch['business_id'],
                'intent_ref': iref, 'production_profile': profile, 'template_ref': f['template_ref'],
                'row_manifest_ref': artifact(manifest_path, 'native-composite-rows', profile, manifest['schema_version']),
                'output_sha256': file_sha(staged), 'output_bytes': staged.stat().st_size,
                'prepared_file_path': str(staged), 'actor_intent': actor}
            write_once(prepared_path, batch_check(prepared, 'C08'))
            output.parent.mkdir(parents=True, exist_ok=True)
            if not output.exists():
                try: os.link(staged, output)
                except FileExistsError: pass
            if file_sha(output) != prepared['output_sha256']: raise PublishCopyError('COMPOSITE_PUBLICATION_CONFLICT')
            excel.validate_workbook(output, Path(f['template_ref']['path']), rendered[profile])
            receipt = {'schema_version': 'creation-composite-delivery-receipt-v1.0', 'business_id': batch['business_id'],
                'intent_ref': iref, 'prepared_ref': artifact(prepared_path, 'native-composite-prepared', profile, prepared['schema_version']),
                'production_profile': profile, 'published_file_path': str(output), 'output_sha256': prepared['output_sha256'],
                'row_manifest_ref': prepared['row_manifest_ref'], 'actor_intent': actor}
            write_once(receipt_path, batch_check(receipt, 'C08'))
            receipts.append(artifact(receipt_path, 'native-composite-receipt', profile, receipt['schema_version']))
        complete = {'schema_version': 'creation-composite-delivery-completion-v1.0', 'business_id': batch['business_id'],
            'intent_ref': iref, 'ordered_file_receipt_refs': receipts, 'scope': scope, 'delivered_slot_ids': slot_ids,
            'semantic_delta': 0, 'exposure_delta': 0, 'presentation_delta': 0, 'actor_intent': actor}
        write_once(base / 'completion.json', batch_check(complete, 'C08'))
        return _composite_result(root, batch_id, base, material)


def composite_version(root, batch_id, delivery_id, context):
    import native_batch_v1 as batch_owner
    batch_owner.assert_principal(root, batch_id, context)
    identifier(delivery_id, r'[a-f0-9]{32}')
    return _composite_result(Path(root), batch_id, _composite_home(root, batch_id) / delivery_id)


def composite_operation(root, batch_id, *, operation_id, expected_actor):
    """Original Task owner's read-only completion proof, including expired Sessions."""
    import native_batch_v1 as batch_owner
    from creative_style_v1 import pinned
    batch_owner.identifier(operation_id)
    batch = batch_owner.intent(root, batch_id)[1]
    if pinned(batch['actor_intent']['permission_snapshot'])['actor'] != expected_actor:
        raise PublishCopyError('COMPOSITE_ACTOR_INVALID')
    home = _composite_home(root, batch_id)
    op = home / 'operations' / digest({'actor': expected_actor, 'operation_id': operation_id})
    if not (op / 'binding.json').is_file(): return None
    binding = read(op / 'binding.json')
    if (binding.get('schema_version')!='creation-composite-operation-v1.0' or binding.get('batch_id')!=batch_id
            or binding.get('operation_id')!=operation_id or binding['intent']['actor_intent']['operation_id']!=operation_id
            or pinned(binding['intent']['actor_intent']['permission_snapshot'])['actor']!=expected_actor):
        raise PublishCopyError('COMPOSITE_IDENTITY_INVALID')
    base = home / identifier(binding['delivery_id'], r'[a-f0-9]{32}')
    if not (base / 'completion.json').is_file(): return None
    return _composite_result(Path(root), batch_id, base)


def composite_list(root, batch_id, context):
    import native_batch_v1 as batch_owner
    batch_owner.assert_principal(root, batch_id, context)
    completed, blocked = [], []
    for path in sorted(_composite_home(root, batch_id).glob('*/completion.json')):
        try: completed.append(_composite_result(Path(root), batch_id, path.parent))
        except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
            blocked.append({'delivery_id': path.parent.name, 'code': getattr(exc, 'code', 'COMPOSITE_RECEIPT_INVALID')})
    return {'completed': completed, 'blocked': blocked}


if __name__ == '__main__':
    import argparse, json, sys
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('composite-preview', 'composite-export', 'composite-version', 'composite-operation', 'composite-list'))
    parser.add_argument('--pipeline-root', type=Path, required=True)
    parser.add_argument('--batch-id', required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin); context = payload.pop('authorization_context', None)
        action = {'composite-preview': composite_preview, 'composite-export': composite_export,
                  'composite-version': composite_version, 'composite-operation': composite_operation, 'composite-list': composite_list}[args.command]
        result = action(args.pipeline_root, args.batch_id, **({'context': context} if args.command != 'composite-operation' else {}), **payload)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'code': getattr(exc, 'code', 'COMPOSITE_DELIVERY_INVALID')}, ensure_ascii=False))
        sys.exit(1)
