"""Versioned history evidence delegated by Content Ledger / Closure owners.

Snapshots are actual Native bytes. Every transition is replayed in full from
immutable Native sources. This is neither a second Ledger nor an approval API.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json

from operation_lock_v1 import operation_lock
from profile_compatibility_contract_v1_1 import obj, REF, HASH, TEXT, ID, OPERATION, validate
from profile_compatibility_decisions_v1_1 import read, ref, resolve_ref, file_sha, write_once, write_bytes_once, digest

ANCHOR = 'generation-export-anchor-evidence-v1.0'
EVENT = 'content-ledger-native-transition-v1.0'
SEAL = 'content-ledger-native-transition-receipt-v1.0'
READER = 'content-ledger-history-reader-v1.0'
NULL = {'oneOf': [REF, {'type': 'null'}]}
KINDS = ['mix_semantic', 'novel_semantic', 'novel_presentation', 'news_presentation']
SCHEMAS = {
 EVENT: obj({'schema_version': {'const': EVENT}, 'validator_version': {'const': READER},
    'event_id': OPERATION, 'business_id': ID, 'request_id': ID, 'kind': {'enum': KINDS},
    'parent': NULL, 'before_ref': REF, 'after_ref': REF, 'before_file_exists': {'enum':[True,False]},
    'before_canonical_sha256': HASH, 'after_canonical_sha256': HASH,
    'source_refs': {'type':'object'}, 'exported_at': TEXT}),
 SEAL: obj({'schema_version': {'const': SEAL}, 'event_ref': REF, 'native_receipt_ref': REF,
    'native_closure_ref': REF}),
 ANCHOR: obj({'schema_version': {'const': ANCHOR}, 'validator_version': {'const': READER},
    'request_id': ID, 'business_id': ID, 'closure_ref': REF, 'approved_ref': REF,
    'approval_receipt_ref': REF, 'xlsx_ref': REF, 'export_receipt_ref': REF,
    'ledger_snapshot_ref': REF, 'ledger_canonical_sha256': HASH,
    'semantic_prefix_sha256': HASH, 'presentation_prefix_sha256': HASH,
    'baseline_event_ref': NULL}),
}

class LedgerHistoryError(RuntimeError):
    def __init__(self, code, message='历史交付证据不足或已变化，请保留原记录并核对。'):
        self.code = 'LEDGER_HISTORY_' + code
        super().__init__(message)

def check(value, version):
    try:
        validate(value, SCHEMAS[version])
        if version==EVENT and type(value['before_file_exists']) is not bool:raise ValueError('Boolean required')
    except (RuntimeError, KeyError, ValueError, TypeError) as exc:
        raise LedgerHistoryError('SCHEMA_INVALID') from exc
    return value

def home(root, business):
    validate(business, ID)
    return Path(root) / 'data/content_ledgers' / business / 'history_v1'

def ledger_path(root, business): return home(root,business).parent / 'content_ledger_v1.json'
def anchor_path(root, rid): return Path(root) / 'data/generation_batches' / rid / 'generation_export_anchor_evidence_v1.json'
def history_lock(root, business): return operation_lock(root, 'content-ledger-history:' + business)
def presentations(value): return value.get('extensions',{}).get('presentation_history_v1',{}).get('entries',[])
def bytes_for(value): return json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')

def snapshot(root, business, data):
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    path = home(root,business) / 'snapshots' / (sha + '.json')
    write_bytes_once(path,data)
    return ref(root,path)

def graph(root, business):
    records = {}
    for path in home(root,business).glob('events/*/event.json'):
        value = check(read(path), EVENT)
        if value['business_id'] != business or value['event_id'] != path.parent.name:
            raise LedgerHistoryError('IDENTITY_CONFLICT')
        material = {k:v for k,v in value.items() if k not in {'schema_version','validator_version','event_id'}}
        if digest(material)[:32] != value['event_id']: raise LedgerHistoryError('IDENTITY_CONFLICT')
        records[file_sha(path)] = (path,value)
    if not records: return []
    parents = set()
    for _,value in records.values():
        parent = value['parent']
        if parent:
            if parent['sha256'] not in records or ref(root,records[parent['sha256']][0]) != parent:
                raise LedgerHistoryError('PARENT_MISSING')
            previous = records[parent['sha256']][1]
            if previous['after_ref'] != value['before_ref']:
                raise LedgerHistoryError('STATE_CHAIN_CONFLICT')
            parents.add(parent['sha256'])
    leaves = set(records) - parents
    if len(leaves) != 1 or sum(v['parent'] is None for _,v in records.values()) != 1:
        raise LedgerHistoryError('FORK_OR_ROLLBACK')
    result=[]; cursor=next(iter(leaves)); visited=set()
    while cursor not in visited:
        visited.add(cursor); node=records[cursor];result.append(node)
        if node[1]['parent'] is None: break
        cursor=node[1]['parent']['sha256']
    if len(visited)!=len(records):raise LedgerHistoryError('FORK_OR_ROLLBACK')
    return list(reversed(result))

def material(root, kind, rid, exported_at):
    if kind == 'mix_semantic':
        from close_generation_export_v1 import historical_ledger_material
    else:
        from news_delivery_v1 import historical_ledger_material
    return historical_ledger_material(Path(root),rid,kind,exported_at)

def replay(before, recipe):
    if recipe['kind'].endswith('_semantic'):
        from content_quality_v1 import build_exported_semantic_ledger_update, STRONG_MEMORY_STATUSES
        result=build_exported_semantic_ledger_update(before,recipe['entries'],recipe['fact_atoms'],exported_at=recipe['exported_at'])
        result['validation']={'passed':True,'entry_count':len(result['entries']),
            'strong_memory_count':sum(v.get('status') in STRONG_MEMORY_STATUSES for v in result['entries']),
            'latest_export_request_id':recipe['request_id']}
        if recipe['kind']=='mix_semantic':result['validation']['baseline_not_mutated']=True
        return result
    from news_delivery_v1 import _project_presentation_history
    result,recovered=_project_presentation_history(before,recipe['source_content_id'],recipe['entry'])
    if recovered:raise LedgerHistoryError('DUPLICATE_EVENT')
    return result

def validate_transition(root, path, event, *, require_seal=True):
    before=read(resolve_ref(root,event['before_ref']));after=read(resolve_ref(root,event['after_ref']))
    if (before.get('business_id')!=event['business_id'] or after.get('business_id')!=event['business_id']
        or digest(before)!=event['before_canonical_sha256'] or digest(after)!=event['after_canonical_sha256']):
        raise LedgerHistoryError('SNAPSHOT_INVALID')
    recipe=material(root,event['kind'],event['request_id'],event['exported_at'])
    if recipe['source_refs']!=event['source_refs'] or replay(before,recipe)!=after:
        raise LedgerHistoryError('UNAUTHORIZED_STATE_CHANGE')
    if require_seal:
        seal=check(read(path.with_name('receipt.json')),SEAL)
        if seal['event_ref']!=ref(root,path):raise LedgerHistoryError('RECEIPT_CONFLICT')
        if (seal['native_receipt_ref']!=ref(root,recipe['receipt_path'])
            or seal['native_closure_ref']!=ref(root,recipe['closure_path'])):raise LedgerHistoryError('RECEIPT_CONFLICT')
        receipt=read(resolve_ref(root,seal['native_receipt_ref']))
        closure=read(resolve_ref(root,seal['native_closure_ref']))
        validate_native_terminal(root,event,after,receipt,closure,recipe)
    return before,after

def validate_native_terminal(root,event,after,receipt,closure,recipe):
    rid=event['request_id'];kind=event['kind']
    if closure.get('request_id')!=rid or closure.get('validation',{}).get('passed') is not True:
        raise LedgerHistoryError('NATIVE_CLOSURE_INVALID')
    if kind=='mix_semantic':
        from close_generation_export_v1 import _validate_recovered_closure
        source=recipe['source_refs']
        _validate_recovered_closure(closure=closure,request_id=rid,
            approved_batch_path=resolve_ref(root,source['approved']),excel_path=resolve_ref(root,source['output']),
            ledger_path=resolve_ref(root,event['after_ref']))
        if (closure['approval_receipt']['sha256']!=source['human']['sha256']
            or closure['excel_export']['receipt_sha256']!=source['receipt']['sha256']):
            raise LedgerHistoryError('NATIVE_CLOSURE_INVALID')
    else:
        from news_export_recovery_v1 import validate_ledger_prefix
        # Novel has two Native steps and one original closure. Its final
        # presentation event owns the terminal prefix; semantic step shares it.
        native_final=after
        if kind=='novel_semantic':
            nodes=[v for _,v in graph(root,event['business_id']) if v['request_id']==rid and v['kind']=='novel_presentation']
            if len(nodes)!=1:raise LedgerHistoryError('NATIVE_CLOSURE_INVALID')
            native_final=read(resolve_ref(root,nodes[0]['after_ref']))
        validate_ledger_prefix(native_final,closure['ledger_prefix'])
        if (closure.get('receipt_ref',{}).get('sha256')!=file_sha(recipe['receipt_path'])
            or receipt.get('output_sha256')!=recipe['source_refs']['output']['sha256']):
            raise LedgerHistoryError('NATIVE_CLOSURE_INVALID')
        if kind=='news_presentation':
            if receipt['content_ledger']['presentation_history_entry']!=presentations(after)[-1]:
                raise LedgerHistoryError('NATIVE_CLOSURE_INVALID')

@contextmanager
def transition(root,business,rid,kind,before,after,*,exported_at,after_bytes):
    """Native owner calls this around its existing atomic file publication."""
    root=Path(root).resolve()
    with history_lock(root,business):
        current=ledger_path(root,business)
        before_bytes=current.read_bytes() if current.is_file() else bytes_for(before)
        if current.is_file() and read(current)!=before:raise LedgerHistoryError('CONCURRENT_CHANGE')
        nodes=graph(root,business)
        if nodes:
            pending_path,pending=nodes[-1]
            if (not pending_path.with_name('receipt.json').is_file() and pending['request_id']==rid
                and pending['kind']==kind and pending['before_ref']['sha256']==__import__('hashlib').sha256(before_bytes).hexdigest()):
                validate_transition(root,pending_path,pending,require_seal=False)
                if (pending['after_ref']['sha256']!=__import__('hashlib').sha256(after_bytes).hexdigest()
                    or pending['exported_at']!=exported_at):raise LedgerHistoryError('REPLAY_CONFLICT')
                yield
                if not current.is_file() or file_sha(current)!=pending['after_ref']['sha256']:
                    raise LedgerHistoryError('PUBLICATION_CONFLICT')
                return
        if nodes and nodes[-1][1]['after_ref']['sha256']!=__import__('hashlib').sha256(before_bytes).hexdigest():
            raise LedgerHistoryError('UNTRACKED_CHANGE')
        for p,v in nodes:
            # Only the same original Native request can finish its multi-step
            # commit before sealing; unrelated operations cannot adopt it.
            pending=not p.with_name('receipt.json').is_file()
            validate_transition(root,p,v,require_seal=not pending)
            if pending and v['request_id']!=rid:raise LedgerHistoryError('NATIVE_COMMIT_PENDING')
        _capture_eligible_legacy(root,business)
        recipe=material(root,kind,rid,exported_at)
        if replay(before,recipe)!=after:raise LedgerHistoryError('UNAUTHORIZED_STATE_CHANGE')
        fields={'business_id':business,'request_id':rid,'kind':kind,
            'parent':ref(root,nodes[-1][0]) if nodes else None,
            'before_ref':snapshot(root,business,before_bytes), 'after_ref':snapshot(root,business,after_bytes),
            'before_file_exists':current.is_file(),'before_canonical_sha256':digest(before),
            'after_canonical_sha256':digest(after),'source_refs':recipe['source_refs'],'exported_at':exported_at}
        event={'schema_version':EVENT,'validator_version':READER,'event_id':digest(fields)[:32],**fields}
        target=home(root,business)/'events'/event['event_id']/'event.json'
        write_once(target,check(event,EVENT))
        yield
        if not current.is_file() or file_sha(current)!=event['after_ref']['sha256']:
            raise LedgerHistoryError('PUBLICATION_CONFLICT')

def finish_request(root,business,rid,receipt_path,closure_path):
    with history_lock(root,business):
        for path,event in graph(root,business):
            if event['request_id']!=rid:continue
            recipe=material(root,event['kind'],rid,event['exported_at'])
            _,after=validate_transition(root,path,event,require_seal=False)
            validate_native_terminal(root,event,after,read(receipt_path),read(closure_path),recipe)
            value={'schema_version':SEAL,'event_ref':ref(root,path),'native_receipt_ref':ref(root,receipt_path),
                   'native_closure_ref':ref(root,closure_path)}
            write_once(path.with_name('receipt.json'),check(value,SEAL))

def finish_completed_news_request(root,business,rid,directory,receipt_path,closure_path,context):
    """Only the original authorized Native operation may seal a crash window."""
    nodes=[(p,v) for p,v in graph(root,business) if v['request_id']==rid]
    if not any(not p.with_name('receipt.json').is_file() for p,_ in nodes):return
    from news_export_recovery_v1 import identity, paths, check as export_check, INTENT
    original=export_check(read(paths(directory)['intent']),INTENT)
    identity(context,original)
    finish_request(root,business,rid,receipt_path,closure_path)

def _capture_eligible_legacy(root,business):
    current=ledger_path(root,business)
    if not current.is_file():return
    for path in (Path(root)/'data/generation_batches').glob('*/generation_export_closure_v1.json'):
        if anchor_path(root,path.parent.name).is_file():continue
        closure=read(path)
        if closure.get('content_ledger',{}).get('sha256_after')==file_sha(current):
            if not path.with_name('generation_export_intent_v1.json').is_file():
                # Unbound offline legacy exports retain their own reader. A
                # missing trusted Native source bundle grants no new anchor.
                continue
            capture_anchor_locked(root,path.parent.name,business)

def capture_anchor_locked(root,rid,business):
    from close_generation_export_v1 import validate_historical_core_bundle
    path=anchor_path(root,rid)
    if path.is_file():return ref(root,path)
    current=ledger_path(root,business)
    closure_path=path.with_name('generation_export_closure_v1.json');closure=read(closure_path)
    if not current.is_file() or file_sha(current)!=closure.get('content_ledger',{}).get('sha256_after'):
        raise LedgerHistoryError('EVIDENCE_INSUFFICIENT')
    refs=validate_historical_core_bundle(Path(root),rid,current)
    value=read(current)
    if value['business_id']!=business or digest(value)!=closure['content_ledger']['canonical_sha256_after']:
        raise LedgerHistoryError('SNAPSHOT_INVALID')
    nodes=graph(root,business)
    if nodes and nodes[-1][1]['after_ref']['sha256']!=file_sha(current):raise LedgerHistoryError('UNTRACKED_CHANGE')
    for p,v in nodes:validate_transition(root,p,v)
    evidence={'schema_version':ANCHOR,'validator_version':READER,'request_id':rid,'business_id':business,
        **refs,'ledger_snapshot_ref':snapshot(root,business,current.read_bytes()),'ledger_canonical_sha256':digest(value),
        'semantic_prefix_sha256':digest(value.get('entries',[])),'presentation_prefix_sha256':digest(presentations(value)),
        'baseline_event_ref':ref(root,nodes[-1][0]) if nodes else None}
    write_once(path,check(evidence,ANCHOR));return ref(root,path)

def ensure_anchor(root,rid):
    req=read(Path(root)/'data/generation_requests'/rid/'generation_request_v1.json');business=req['persona_id']
    with history_lock(root,business):
        return capture_anchor_locked(root,rid,business)

def validate_anchor(root,rid):
    from close_generation_export_v1 import validate_historical_core_bundle
    path=anchor_path(root,rid)
    if not path.is_file():raise LedgerHistoryError('EVIDENCE_INSUFFICIENT')
    value=check(read(path),ANCHOR);business=value['business_id']
    if value['request_id']!=rid:raise LedgerHistoryError('IDENTITY_CONFLICT')
    original=resolve_ref(root,value['ledger_snapshot_ref']);snapshot_value=read(original)
    refs=validate_historical_core_bundle(Path(root),rid,original)
    if (any(value[k]!=v for k,v in refs.items()) or snapshot_value.get('business_id')!=business
        or digest(snapshot_value)!=value['ledger_canonical_sha256']
        or digest(snapshot_value.get('entries',[]))!=value['semantic_prefix_sha256']
        or digest(presentations(snapshot_value))!=value['presentation_prefix_sha256']):
        raise LedgerHistoryError('ANCHOR_INVALID')
    nodes=graph(root,business);baseline=value['baseline_event_ref'];start=0
    if baseline:
        found=[i for i,(p,_) in enumerate(nodes) if ref(root,p)==baseline]
        if len(found)!=1:raise LedgerHistoryError('PARENT_MISSING')
        index=found[0]
        if nodes[index][1]['after_ref']!=value['ledger_snapshot_ref']:raise LedgerHistoryError('ANCHOR_INVALID')
        start=index+1
    state_ref=value['ledger_snapshot_ref']
    for p,event in nodes[start:]:
        if event['before_ref']!=state_ref:raise LedgerHistoryError('STATE_CHAIN_CONFLICT')
        validate_transition(root,p,event);state_ref=event['after_ref']
    _completed_native_coverage(root,business,snapshot_value,nodes[start:])
    current=ledger_path(root,business)
    if not current.is_file() or file_sha(current)!=state_ref['sha256'] or read(current).get('business_id')!=business:
        raise LedgerHistoryError('UNTRACKED_CHANGE')
    return {'anchor_ref':ref(root,path),'closure_ref':value['closure_ref'],
            'ledger_ref':ref(root,current),'event_head':ref(root,nodes[-1][0]) if nodes else None}


def _completed_native_coverage(root,business,baseline,nodes):
    """A removed tail plus Ledger rollback cannot erase existing Native results."""
    semantic_ids={v.get('content_id') for v in baseline.get('entries',[])}
    presentation_ids={v.get('presentation_id') for v in presentations(baseline)}
    covered={(v['request_id'],v['kind']) for _,v in nodes}
    for path in (Path(root)/'data/generation_requests').glob('*/generation_request_v1.json'):
        request=read(path)
        if request.get('persona_id')!=business:continue
        rid=request['request_id'];directory=Path(root)/'data/generation_batches'/rid
        if request.get('target_profile')=='news':
            closure=directory/'novel_news_export_closure_v1.json'
            if not closure.is_file():continue
            required=[]
            if rid+'-N001' not in semantic_ids:required.append('novel_semantic')
            if rid+'-P001' not in presentation_ids:required.append('novel_presentation')
        else:
            closure=directory/'generation_export_closure_v1.json'
            if not closure.is_file():continue
            ids=read(closure).get('content_ledger',{}).get('appended_content_ids')
            if not ids:raise LedgerHistoryError('NATIVE_CLOSURE_INVALID')
            required=[] if set(ids)<=semantic_ids else ['mix_semantic']
        if any((rid,kind) not in covered for kind in required):raise LedgerHistoryError('NATIVE_EVENT_MISSING')
    for path in (Path(root)/'data/news_deliveries').glob('*/news_delivery_request_v1.json'):
        request=read(path)
        if request.get('business_id')!=business:continue
        rid=request['request_id']
        if path.with_name('news_delivery_export_closure_v1.json').is_file():
            if rid+'-P001' not in presentation_ids and (rid,'news_presentation') not in covered:
                raise LedgerHistoryError('NATIVE_EVENT_MISSING')


def prohibit_unversioned_ledger_write(path):
    path=Path(path).resolve()
    if path.name=='content_ledger_v1.json' and path.parent.parent.name=='content_ledgers':
        if home(path.parents[3],path.parent.name).is_dir():
            raise LedgerHistoryError('NATIVE_WRITER_REQUIRED')
