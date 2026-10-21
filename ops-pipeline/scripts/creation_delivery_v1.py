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
    root = Path(root).resolve(); src = source(root, rid); proof = identity(context)
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
