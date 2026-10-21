"""Native second-stage derivation. Original production approvals remain immutable.

Durability, identity and short mutation fences use the REC-01 primitives. This
typed adapter never invents a Novel Request or changes its 4--8 Beat validator.
"""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager

from profile_compatibility_decisions_v1_1 import read, ref, file_sha, digest, write_once, resolve_ref
from operation_lock_v1 import operation_lock
from novel_news_generation_recovery_v1 import identity, mutation_fence
from news_export_recovery_v1 import identity as validate_identity
from publish_copy_sources_v1 import source, current_authority
from publish_copy_contract_v1 import VERSION, PAYLOAD, check, identifier, PublishCopyError
from profile_compatibility_contract_v1_1 import validate

def now(): return datetime.now(timezone.utc).isoformat()

def base(root, rid):
    identifier(rid)
    kind = 'news_deliveries' if rid.startswith('news_') else 'generation_batches'
    return Path(root) / 'data' / kind / rid / 'publish_copy_v1'

def lock(root, rid): return operation_lock(root, 'publish-copy:' + identifier(rid))

@contextmanager
def _write_locks(root, rid, src):
    from news_qualification_v1_2 import prohibit_write
    prohibit_write(root)
    with mutation_fence(root), current_authority(root, src), operation_lock(root, 'business:' + src['business_id']), lock(root, rid):
        yield

@contextmanager
def write_scope(root, rid, src):
    with _write_locks(root, rid, src):
        if source(root, rid)['source_sha256'] != src['source_sha256']:
            raise PublishCopyError('SOURCE_CHANGED')
        yield

def chain(root, paths, *, parent_key='parent'):
    """One immutable parent chain; missing nodes, cycles and forks fail closed."""
    records = {}
    for path in paths:
        value = read(path); check(value, value['schema_version'])
        records[file_sha(path)] = (path, value)
    if not records: return None
    parents = set()
    for _, value in records.values():
        parent = value[parent_key]
        if parent:
            if parent['sha256'] not in records or ref(root, records[parent['sha256']][0]) != parent:
                raise PublishCopyError('PARENT_MISSING')
            parents.add(parent['sha256'])
    leaves = set(records) - parents
    if len(leaves) != 1 or sum(v[parent_key] is None for _, v in records.values()) != 1:
        raise PublishCopyError('CHAIN_CONFLICT')
    cursor = next(iter(leaves)); head = records[cursor]; visited = set()
    while cursor not in visited:
        visited.add(cursor); parent = records[cursor][1][parent_key]
        if parent is None: break
        cursor = parent['sha256']
    if len(visited) != len(records): raise PublishCopyError('CHAIN_CONFLICT')
    return head

def attempt(root, rid): return chain(root, base(root, rid).glob('attempts/*/intent.json'))
def draft(root, rid): return chain(root, base(root, rid).glob('drafts/*.json'))

def _clean(text): return re.sub(r'[\W_]+', '', text, flags=re.UNICODE)

def grounded(text, corpus):
    """Conservative fact projection plus native numeric/qualifier safeguards.

    Human confirmation remains mandatory; lexical similarity grants no approval.
    Unsupported substantive fragments are rejected instead of padded marketing.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise PublishCopyError('TEXT_INVALID')
    from privacy_projection_v1 import assert_safe_for_external_model
    assert_safe_for_external_model(text)
    from news_delivery_v1 import FORBIDDEN_STRENGTHENING
    if any(term in text and term not in corpus for term in FORBIDDEN_STRENGTHENING):
        raise PublishCopyError('UNGROUNDED_CLAIM')
    if not set(re.findall(r'\d+(?:\.\d+)?', text)) <= set(re.findall(r'\d+(?:\.\d+)?', corpus)):
        raise PublishCopyError('UNGROUNDED_NUMBER')
    neutral = set('本期视频介绍了解看看有关内容分享大家可以一起关注的了与和及是为在这让你我我们他们它就将从到请按以作对有更并')
    if not set(_clean(text)) <= set(_clean(corpus)) | neutral:
        raise PublishCopyError('UNGROUNDED_TEXT', '发布表达包含来源以外的信息，请按已审核内容修改。')
    # Preserve factual phrases, not merely their vocabulary. In particular,
    # "A29元、B39元" cannot be rearranged into "A39元" using the same characters.
    for clause in re.split(r'[，。！？；\n:：#]+', text):
        normalized = _clean(clause)
        for prefix in ('本期视频介绍', '本期介绍', '本期分享', '了解', '看看', '关于'):
            if normalized.startswith(prefix): normalized = normalized[len(prefix):]
        if normalized and normalized not in _clean(corpus):
            raise PublishCopyError('UNGROUNDED_RELATION', '表达与已核实事实的对应关系需要重新核对。')

def validate_payload(payload, src, *, target_ids=None):
    try: validate(payload, PAYLOAD)
    except (RuntimeError, ValueError, TypeError) as exc: raise PublishCopyError('PAYLOAD_INVALID') from exc
    wanted = target_ids or [i['target_id'] for i in src['items']]
    actual = [i['target_id'] for i in payload['items']]
    if len(actual) != len(set(actual)) or set(actual) != set(wanted):
        raise PublishCopyError('TARGET_SET_INVALID')
    available = {i['target_id']: i for i in src['items']}
    for item in payload['items']:
        if item['source_version_sha256'] != src['source_sha256']: raise PublishCopyError('SOURCE_CHANGED')
        original = available[item['target_id']]
        units = {u['unit_id']: u['text'] for u in original['units']}
        production = '\n'.join(units.values()) if units else original['title'] + '\n' + original['narration']
        headlines = item.get('production_headlines')
        if src['mode'] == 'mix':
            if headlines is not None: raise PublishCopyError('HEADLINE_MODE_INVALID')
        else:
            if headlines is None: raise PublishCopyError('HEADLINE_MODE_INVALID')
            if not 1 <= len(headlines) <= 6: raise PublishCopyError('HEADLINE_COUNT_INVALID')
            covered = set()
            previous_first = -1
            texts = []
            for order, headline in enumerate(headlines, 1):
                if headline['order'] != order: raise PublishCopyError('HEADLINE_ORDER_INVALID')
                ids = headline['source_unit_ids']
                if len(ids) != len(set(ids)) or not set(ids) <= set(units):
                    raise PublishCopyError('HEADLINE_MAPPING_INVALID')
                if ids != sorted(ids, key=list(units).index): raise PublishCopyError('HEADLINE_ORDER_INVALID')
                first = list(units).index(ids[0])
                if first < previous_first: raise PublishCopyError('HEADLINE_ORDER_INVALID')
                previous_first = first
                if headline['mapping_kind'] == 'merge' and len(ids) < 2:
                    raise PublishCopyError('HEADLINE_MAPPING_INVALID')
                text = headline['text']; mapped = '，'.join(units[i] for i in ids)
                if any(ord(c)<32 for c in text):raise PublishCopyError('HEADLINE_SEPARATOR_INVALID')
                if _clean(text) in texts: raise PublishCopyError('HEADLINE_DUPLICATE')
                texts.append(_clean(text))
                grounded(text, mapped)
                from news_delivery_v1 import PRESERVED_QUALIFIERS
                if (set(re.findall(r'\d+(?:\.\d+)?', mapped)) != set(re.findall(r'\d+(?:\.\d+)?', text))
                    or any(term in mapped and term not in text for term in PRESERVED_QUALIFIERS)):
                    raise PublishCopyError('HEADLINE_FACT_LOSS')
                # A merge must represent every mapped unit, not just list its ID.
                for unit_id in ids:
                    if len(set(_clean(units[unit_id])) & set(_clean(text))) / max(1, len(set(_clean(units[unit_id])))) < .65:
                        raise PublishCopyError('HEADLINE_FACT_LOSS')
                covered.update(ids)
            if covered != set(units): raise PublishCopyError('HEADLINE_COVERAGE_INCOMPLETE')
        def values(value):
            if isinstance(value, str): yield value
            elif isinstance(value, dict):
                for child in value.values(): yield from values(child)
            elif isinstance(value, list):
                for child in value: yield from values(child)
        corpus = production + '\n' + '\n'.join(values(src['safe_business'].get('facts', {})))
        for text in [item['publish_title'], item['publish_body'], *item['topics']]: grounded(text, corpus)
        if (len(item['topics']) > 10 or len(set(item['topics'])) != len(item['topics'])
            or any(not re.fullmatch(r'#?[\w-]+',t,flags=re.UNICODE) for t in item['topics'])):
            raise PublishCopyError('TOPICS_INVALID')
        from customer_constraints_v1 import assert_publication_allowed
        assert_publication_allowed(read(src['_business_path']), src['_business_path'],
            [item['publish_title'] + '\n' + item['publish_body'] + '\n' + ' '.join(item['topics'])])
    return payload

def prompt_for(src, targets):
    # Request-local aliases, exactly as REC-01 does for Fact Atoms. Internal
    # digest digit runs are not linguistic input and can resemble private phones.
    aliases = {item['target_id']: 'CONTENT_' + letters(n) for n, item in enumerate(src['items'])}
    public_items = []
    for item in src['items']:
        if item['target_id'] not in targets: continue
        public_items.append({'target_id': aliases[item['target_id']], 'target_kind': item['target_kind'],
            **{key:item[key] for key in ('title','narration') if key in item},
            'units':[{'unit_id':'UNIT_' + letters(n), 'order': unit['order'], 'text': unit['text']}
                     for n,unit in enumerate(item['units'])]})
    public = {'mode': src['mode'], 'source_version_sha256': 'VERSION_A',
              'items': public_items, 'safe_facts': src['safe_business']}
    prompt = ('仅从以下已审核内容与安全事实派生发布标题、正文、话题，不增加事实或承诺。'
      '返回JSON items，每项包含target_id,source_version_sha256,publish_title,publish_body,topics。'
      'Mix禁止production_headlines字段。News在同一次响应中另返回production_headlines，提炼1至6条制作短标题，建议3至6条、每条12字以内；'
      '事实不足不得凑数或机械截断。每个制作标题含order(从1连续),text,source_unit_ids,mapping_kind(extract/condense/merge)，'
      '完整覆盖所有原段，保留主体、数字和适用条件，7至8段须合法合并。不得填写审核状态或路径。\n'
      + json.dumps(public, ensure_ascii=False, sort_keys=True))
    from privacy_projection_v1 import assert_safe_for_external_model
    assert_safe_for_external_model(prompt)
    return prompt

def letters(number):
    result = ''
    while True:
        result = chr(65 + number % 26) + result; number = number // 26 - 1
        if number < 0: return result

def restore_response(payload, src):
    import copy
    payload = copy.deepcopy(payload)
    targets = {'CONTENT_' + letters(n): item for n,item in enumerate(src['items'])}
    actual = {item['target_id']: item for item in src['items']}
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list): return payload
    for item in payload['items']:
        if not isinstance(item, dict): continue
        original = targets.get(item.get('target_id')) or actual.get(item.get('target_id'))
        if not original: continue
        item['target_id'] = original['target_id']
        if item.get('source_version_sha256') == 'VERSION_A': item['source_version_sha256'] = src['source_sha256']
        units = {'UNIT_' + letters(n): unit['unit_id'] for n,unit in enumerate(original['units'])}
        for headline in item.get('production_headlines', []):
            if isinstance(headline, dict) and isinstance(headline.get('source_unit_ids'), list):
                headline['source_unit_ids'] = [units.get(value, value) for value in headline['source_unit_ids']]
    return payload

def configured_model():
    import os
    return os.getenv('DEEPSEEK_MODEL') or 'deepseek-chat'

def prepare(root, rid, context, *, target_ids=None, expected_parent=None):
    model=configured_model()
    src = source(root, rid); proof = identity(context)
    targets = target_ids or [i['target_id'] for i in src['items']][:5]
    if not targets or len(targets) > 5 or len(set(targets)) != len(targets) or not set(targets) <= {i['target_id'] for i in src['items']}:
        raise PublishCopyError('TARGET_SET_INVALID')
    prompt = prompt_for(src, targets)
    material = {'source_sha256': src['source_sha256'], 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
        'parameters': {'version': VERSION, 'model': model, 'transport': 'deepseek-json-0.7-10000-v1',
            'owner_sha256': file_sha(Path(__file__)), 'memory_sha256': memory_sha(root, src['business_id']), 'target_ids': targets},
        'actor': context['actor'], 'authorization': proof}
    with write_scope(root, rid, src):
        current = attempt(root, rid)
        if current:
            previous = {key: current[1][key] for key in material}
            if expected_parent is None:
                if previous == material: return current
                raise PublishCopyError('EXPLICIT_RETRY_REQUIRED')
            if expected_parent != ref(root, current[0]):
                if current[1]['parent'] == expected_parent and previous == material: return current
                raise PublishCopyError('PARENT_CONFLICT')
        elif expected_parent is not None: raise PublishCopyError('PARENT_MISSING')
        parent = ref(root, current[0]) if current else None
        op = digest({'request_id': rid, 'parent': parent, **material})[:32]
        source_ref = save_source_snapshot(root, rid, src)
        value = {'schema_version': 'publish-copy-generation-intent-v1.0', 'request_id': rid,
                 'operation_id': op, 'parent': parent, 'source_refs': src['refs'],
                 'source_snapshot_ref': source_ref, **material, 'created_at': now()}
        path = base(root, rid) / 'attempts' / op / 'intent.json'
        write_once(path, check(value, value['schema_version']))
        return path, value

def _evidence(root, intent_path, value, kind):
    path = intent_path.with_name(kind + '.json')
    if not path.is_file(): return None
    evidence = read(path); check(evidence, 'publish-copy-generation-' + kind + '-v1.0')
    if evidence['intent_ref'] != ref(root, intent_path) or evidence['operation_id'] != value['operation_id']:
        raise PublishCopyError('EVIDENCE_INVALID')
    return path, evidence

def _record(root, path, intent, kind, **fields):
    value = {'schema_version': 'publish-copy-generation-' + kind + '-v1.0',
        'request_id': intent['request_id'], 'operation_id': intent['operation_id'],
        'intent_ref': ref(root, path), **fields}
    target = path.with_name(kind + '.json'); write_once(target, check(value, value['schema_version']))
    return target

def validated_result(root, rid, path, intent, src):
    completed=_evidence(root,path,intent,'result')
    if not completed:return None
    response=_evidence(root,path,intent,'response')
    if not response or completed[1]['response_ref']!=ref(root,response[0]):raise PublishCopyError('EVIDENCE_INVALID')
    generated=read(resolve_ref(root,completed[1]['draft_ref']))
    check(generated,'publish-copy-draft-v1.0');verify_draft(root,src,generated)
    selected=validate_payload(restore_response(response[1]['payload'],src),src,target_ids=intent['parameters']['target_ids'])
    rows={v['target_id']:v for v in generated['payload']['items']}
    expected_id=digest({'source':src['source_sha256'],'payload':generated['payload'],'identity':intent['operation_id']})[:32]
    if (generated['draft_id']!=expected_id or generated['actor']!=intent['actor'] or
        any(rows.get(item['target_id'])!=item for item in selected['items'])):raise PublishCopyError('EVIDENCE_INVALID')
    return completed

def _current(root, rid, path, intent, context):
    latest = attempt(root, rid)
    if not latest or ref(root, latest[0]) != ref(root, path): raise PublishCopyError('SUPERSEDED')
    validate_identity(context, intent)
    src = source(root, rid)
    if src['source_sha256'] != intent['source_sha256']: raise PublishCopyError('SOURCE_CHANGED')
    if (intent['parameters']['owner_sha256'] != file_sha(Path(__file__))
        or intent['parameters']['model'] != configured_model()
        or intent['parameters']['memory_sha256'] != memory_sha(root, src['business_id'])):
        raise PublishCopyError('SOURCE_CHANGED')
    if hashlib.sha256(prompt_for(src, intent['parameters']['target_ids']).encode()).hexdigest() != intent['prompt_sha256']:
        raise PublishCopyError('SOURCE_CHANGED')
    return src

def memory_sha(root, business_id):
    path = Path(root) / 'data/content_ledgers' / business_id / 'content_ledger_v1.json'
    return file_sha(path) if path.is_file() else None

def bind_task(root, rid, operation_id, task_id, context):
    path = base(root, rid) / 'attempts' / identifier(operation_id, r'[a-f0-9]{32}') / 'intent.json'
    intent = check(read(path), 'publish-copy-generation-intent-v1.0')
    src = _current(root, rid, path, intent, context)
    # _current performs the complete source, authorization, owner, memory and
    # prompt checks under these same locks. An additional source-only scan just
    # before it would duplicate work without strengthening the commit fence.
    with _write_locks(root, rid, src):
        _current(root, rid, path, intent, context)
        return _record(root, path, intent, 'task', task_id=task_id, task_operation_identity='publish-copy:' + rid + ':' + operation_id)

def run(root, rid, operation_id, context, *, transport=None, task_id=None):
    identifier(operation_id, r'[a-f0-9]{32}')
    path = base(root, rid) / 'attempts' / operation_id / 'intent.json'
    intent = check(read(path), 'publish-copy-generation-intent-v1.0')
    with operation_lock(root, 'publish-copy-executor:' + operation_id, timeout_seconds=0):
        src = _current(root, rid, path, intent, context)
        if task_id:
            bound = _evidence(root, path, intent, 'task')
            if not bound or bound[1]['task_id'] != task_id: raise PublishCopyError('TASK_BINDING_INVALID')
        completed = validated_result(root,rid,path,intent,src)
        if completed:
            dpath = resolve_ref(root, completed[1]['draft_ref'])
            validate_payload(read(dpath)['payload'], src)
            return {'draft_ref': ref(root, dpath), 'state': 'draft_ready'}
        response = _evidence(root, path, intent, 'response')
        if not response:
            with _write_locks(root, rid, src):
                _current(root, rid, path, intent, context)
                if _evidence(root, path, intent, 'dispatch'):
                    raise PublishCopyError('OUTCOME_UNKNOWN', '模型调用结果无法确认，系统不会自动重复生成；重新尝试可能产生额外费用。')
                _record(root, path, intent, 'dispatch', dispatched_at=now())
            if transport is None:
                from generate_mix_scripts_v1 import default_transport
                transport = default_transport(intent['parameters']['model'])
            returned = transport(prompt_for(src, intent['parameters']['target_ids']))
            payload = returned.get('payload', returned)
            # Save privately before validation/publication. No raw response is exposed in projections.
            _record(root, path, intent, 'response', payload=payload, received_at=now())
            response = _evidence(root, path, intent, 'response')
        src = _current(root, rid, path, intent, context)
        payload = validate_payload(restore_response(response[1]['payload'], src), src, target_ids=intent['parameters']['target_ids'])
        with _write_locks(root, rid, src):
            _current(root, rid, path, intent, context)
            current = draft(root, rid)
            merged = {i['target_id']: i for i in current[1]['payload']['items']} if current and current[1]['source_sha256'] == src['source_sha256'] else {}
            merged.update({i['target_id']: i for i in payload['items']})
            draft_payload = {'items': [merged[i['target_id']] for i in src['items'] if i['target_id'] in merged]}
            dpath = _save_draft(root, rid, src, draft_payload, context, current, operation_id)
            _record(root, path, intent, 'result', response_ref=ref(root, response[0]), draft_ref=ref(root, dpath))
            return {'draft_ref': ref(root, dpath), 'state': 'draft_ready'}

def _save_draft(root, rid, src, payload, context, parent, identity_value):
    did = digest({'source': src['source_sha256'], 'payload': payload, 'identity': identity_value})[:32]
    path = base(root, rid) / 'drafts' / (did + '.json')
    if path.is_file():
        previous = check(read(path), 'publish-copy-draft-v1.0')
        if (previous['payload'] != payload or previous['source_sha256'] != src['source_sha256']
            or previous['actor'] != context['actor'] or previous['request_id'] != rid or previous['draft_id'] != did):
            raise PublishCopyError('DRAFT_CONFLICT')
        return path
    value = {'schema_version': 'publish-copy-draft-v1.0', 'request_id': rid, 'draft_id': did,
        'parent': ref(root, parent[0]) if parent else None, 'source_sha256': src['source_sha256'],
        'source_refs': src['refs'], 'source_snapshot_ref': save_source_snapshot(root, rid, src),
        'payload': payload, 'derived_targets': canonical_targets(src, payload),
        'actor': context['actor'], 'created_at': now()}
    write_once(path, check(value, value['schema_version'])); return path

def edit(root, rid, draft_ref, payload, context):
    src = source(root, rid); identity(context)
    with write_scope(root, rid, src):
        current = draft(root, rid)
        if not current or ref(root, current[0]) != draft_ref or current[1]['source_sha256'] != src['source_sha256']:
            raise PublishCopyError('DRAFT_CHANGED')
        validate_payload(payload,src,target_ids=[item['target_id'] for item in current[1]['payload']['items']])
        if payload == current[1]['payload']: return ref(root, current[0])
        path = _save_draft(root, rid, src, payload, context, current, digest({'parent': draft_ref, 'payload': payload}))
        return ref(root, path)

def confirmation(root, rid, draft_value):
    path = base(root, rid) / 'confirmations' / (draft_value['draft_id'] + '.json')
    if not path.is_file(): return None
    value = check(read(path), 'publish-copy-confirmation-v1.0')
    expected = base(root, rid) / 'drafts' / (draft_value['draft_id'] + '.json')
    if (value['draft_ref'] != ref(root, expected) or value['source_sha256'] != draft_value['source_sha256']
        or value['payload_sha256'] != digest(draft_value['payload'])
        or value['targets'] != draft_value['derived_targets']
        or value['headline_mapping_sha256'] != digest([i.get('production_headlines') for i in draft_value['payload']['items']])):
        raise PublishCopyError('CONFIRMATION_INVALID')
    return path, value

def confirm(root, rid, draft_ref, context):
    src = source(root, rid); proof = identity(context)
    with write_scope(root, rid, src):
        current = draft(root, rid)
        if not current or ref(root, current[0]) != draft_ref or current[1]['source_sha256'] != src['source_sha256']:
            raise PublishCopyError('DRAFT_CHANGED')
        validate_payload(current[1]['payload'], src)
        verify_draft(root, src, current[1])
        old = confirmation(root, rid, current[1])
        if old:
            validate_identity(context, old[1]); return ref(root, old[0])
        prior = None; parent = current[1]['parent']
        while parent:
            previous = read(resolve_ref(root, parent)); prior = confirmation(root, rid, previous)
            if prior: break
            parent = previous['parent']
        value = {'schema_version': 'publish-copy-confirmation-v1.0', 'request_id': rid,
            'operation_id': digest({'draft_ref': draft_ref, 'actor': context['actor']})[:32],
            'parent_confirmation_ref': ref(root, prior[0]) if prior else None,
            'targets': current[1]['derived_targets'], 'decision': 'confirm', 'draft_ref': draft_ref,
            'source_sha256': src['source_sha256'], 'payload_sha256': digest(current[1]['payload']),
            'headline_mapping_sha256': digest([i.get('production_headlines') for i in current[1]['payload']['items']]),
            'actor': context['actor'], 'authorization': proof, 'human_gate': True, 'confirmed_at': now()}
        path = base(root, rid) / 'confirmations' / (current[1]['draft_id'] + '.json')
        write_once(path, check(value, value['schema_version'])); return ref(root, path)

def state(root, rid):
    return _state(root, rid, source(root, rid))

def _state(root, rid, src):
    current = draft(root, rid); latest = attempt(root, rid)
    result = {'request_id': rid, 'mode': src['mode'], 'source_sha256': src['source_sha256'],
              'production': src['items'], 'state': 'not_started', 'draft': None, 'confirmed': False}
    if current:
        stale = current[1]['source_sha256'] != src['source_sha256']
        if not stale: verify_draft(root, src, current[1])
        result.update(draft={'ref': ref(root, current[0]), 'payload': current[1]['payload']},
            state='stale' if stale else 'draft_ready', confirmed=False if stale else bool(confirmation(root, rid, current[1])))
    if latest:
        path, intent = latest; result['attempt_ref'] = ref(root, path); result['operation_id'] = intent['operation_id']
        if intent['source_sha256'] != src['source_sha256']: result['state'] = 'stale'
        elif not validated_result(root,rid,path,intent,src):
            response = _evidence(root, path, intent, 'response')
            if response:
                try:
                    validate_payload(restore_response(response[1]['payload'], src), src, target_ids=intent['parameters']['target_ids'])
                    result['state'] = 'validated_result_unpublished'
                except RuntimeError: result['state'] = 'confirmed_failure'
            else: result['state'] = 'dispatched_outcome_unknown' if _evidence(root, path, intent, 'dispatch') else 'not_dispatched'
    return result

def project(root, rid):
    """One fresh Native source snapshot for the read-only delivery page.

    Reuse lasts only for this read. Export and all mutation fences still load
    current sources independently; no cached approval or TTL grants authority.
    """
    from creation_delivery_v1 import _effective
    src = source(root, rid)
    result = _state(root, rid, src)
    result['delivery'] = _effective(root, src) if result['state'] != 'stale' else None
    return result

def save_source_snapshot(root, rid, src):
    """A derived evidence snapshot, not an approval or new Customer Truth."""
    safe_path = base(root, rid) / 'sources' / (src['source_sha256'] + '-safe.json')
    write_once(safe_path, {'schema_version': 'publish-copy-safe-projection-v1.0', 'business_id': src['business_id'],
        'production': src['items'], 'safe_business': src['safe_business']})
    value = {'schema_version': 'publish-copy-source-snapshot-v1.0', 'request_id': rid, 'request_kind': src['mode'],
        'business_id': src['business_id'], 'approved_ref': src['snapshot']['approved_ref'],
        'source_version_sha256': src['source_sha256'], 'source_refs': src['refs'], 'targets': src['items'],
        'safe_projection_ref': ref(root, safe_path), 'authority_binding': src['binding']}
    path = base(root, rid) / 'sources' / (src['source_sha256'] + '.json')
    write_once(path, value)
    return ref(root, path)

def canonical_targets(src, payload):
    originals = {i['target_id']: i for i in src['items']}
    result = []
    for item in payload['items']:
        original = originals[item['target_id']]; units = {u['unit_id']: u for u in original['units']}
        headlines = []
        for headline in item.get('production_headlines', []):
            headlines.append({'headline_id': digest({'target_id': item['target_id'], **headline})[:32], **headline,
                'source_units': [units[i] for i in headline['source_unit_ids']],
                'source_approved_ref': src['snapshot']['approved_ref'],
                'preserved_claim_refs': [{'unit_id': i, 'fragment_sha256': units[i]['fragment_sha256']} for i in headline['source_unit_ids']]})
        result.append({'target_id': item['target_id'], 'target_kind': original['target_kind'],
            'source_version_sha256': src['source_sha256'], 'source_approved_ref': src['snapshot']['approved_ref'],
            'payload_sha256': digest(item), 'production_headlines': headlines,
            'grounding_refs': {'production': src['snapshot']['approved_ref'], 'safe_facts_sha256': digest(src['safe_business'])}})
    return result

def verify_draft(root, src, value):
    snapshot = read(resolve_ref(root, value['source_snapshot_ref']))
    safe = read(resolve_ref(root, snapshot['safe_projection_ref']))
    if (value['request_id'] != src['request_id'] or value['source_sha256'] != src['source_sha256'] or value['source_refs'] != src['refs']
        or value['derived_targets'] != canonical_targets(src, value['payload'])
        or snapshot['targets'] != src['items'] or snapshot['source_version_sha256'] != src['source_sha256']
        or snapshot['source_refs'] != src['refs'] or safe['production'] != src['items']
        or safe['safe_business'] != src['safe_business']):
        raise PublishCopyError('DRAFT_SOURCE_INVALID')
    validate_payload(value['payload'], src, target_ids=[i['target_id'] for i in value['payload']['items']])

def export_delivery(root, rid, context, expected_draft_ref=None):
    current = draft(root, rid)
    if expected_draft_ref is not None and (not current or ref(root, current[0]) != expected_draft_ref):
        raise PublishCopyError('DRAFT_CHANGED')
    src = source(root, rid)
    if src['mode'] == 'mix': from export_mix_excel_v1 import export_supplemental_delivery as writer
    elif src['mode'] == 'novel_content': from novel_news_v1 import export_supplemental_delivery as writer
    else: from news_delivery_v1 import export_supplemental_delivery as writer
    return writer(pipeline_root=root, request_id=rid, authorization_context=context, expected_draft_ref=expected_draft_ref)

def delivery_version(root,rid,delivery_id):
    from creation_delivery_v1 import read_version
    return read_version(root,rid,delivery_id)

def main():
    import argparse, sys
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['state', 'project', 'prepare', 'bind-task', 'run', 'edit', 'confirm', 'export', 'effective','version'])
    parser.add_argument('--pipeline-root', required=True)
    parser.add_argument('--request-id', required=True)
    args = parser.parse_args(); root = Path(args.pipeline_root).resolve(); rid = args.request_id
    try:
        payload = json.load(sys.stdin) if args.command not in {'state', 'project', 'effective'} else {}
        context = payload.get('authorization_context')
        if args.command == 'state': result = state(root, rid)
        elif args.command == 'project': result = project(root, rid)
        elif args.command == 'prepare':
            path, value = prepare(root, rid, context, target_ids=payload.get('target_ids'), expected_parent=payload.get('expected_parent'))
            result = {'operation_id': value['operation_id'], 'intent_ref': ref(root, path)}
        elif args.command == 'bind-task': result = {'task_ref': ref(root, bind_task(root, rid, payload['operation_id'], payload['task_id'], context))}
        elif args.command == 'run': result = run(root, rid, payload['operation_id'], context, task_id=payload.get('task_id'))
        elif args.command == 'edit': result = edit(root, rid, payload['draft_ref'], payload['payload'], context)
        elif args.command == 'confirm': result = confirm(root, rid, payload['draft_ref'], context)
        elif args.command == 'export': result = export_delivery(root, rid, context, payload.get('expected_draft_ref'))
        elif args.command == 'version': result = delivery_version(root,rid,payload['delivery_id'])
        else:
            from creation_delivery_v1 import effective
            result = effective(root, rid)
        print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False))
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'ok': False, 'code': getattr(exc, 'code', 'PUBLISH_COPY_SOURCE_INVALID')}, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__': main()
