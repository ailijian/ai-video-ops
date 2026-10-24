"""C3-05 append-only attempts, delegated by the native Generation owner.

These companions authorize retry execution only. They never approve content.
All public references are exact-byte, runtime-relative identities.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from human_review_operations_v1 import digest, file_sha, read, write_once
from profile_compatibility_contract_v1_1 import (
    ACTOR, HASH, ID, NULL_REF, OPERATION, REF, TEXT, array, obj, validate,
)

INTENT = 'generation-recovery-intent-v1.0'
RESULT = 'generation-recovery-result-v1.0'
DISPATCH = 'generation-recovery-dispatch-v1.0'
READER = 'generation-recovery-reader-v1.0'
ACCEPTED_SUBSET = 'native-mix-accepted-subset-v1.0'
MARKER_SCHEMA = obj({'reader_version': {'const': READER}, 'intent_ref': REF})
SCHEMAS = {
    ACCEPTED_SUBSET: obj({'schema_version': {'const': ACCEPTED_SUBSET},
        'request_ref': REF, 'final_plan_ref': REF,
        'selected_concept_ids': array(TEXT, 1), 'accepted_concept_ids': array(TEXT, 1),
        'missing_concept_ids': array(TEXT, 1), 'content_ids': array(TEXT, 1),
        'logical_slot_ids': array(TEXT, 1), 'accepted_contents_sha256': HASH}),
    INTENT: obj({'schema_version': {'const': INTENT}, 'request_id': ID,
        'operation_id': OPERATION, 'parent_ref': REF, 'anchor_ref': REF,
        'bindings': obj({'request_ref': REF, 'source_plan_ref': REF, 'final_plan_ref': REF,
            'generation_projection_sha256': HASH, 'content_memory_sha256': HASH,
            'source_context_sha256': HASH,
            'current_authority_sha256': HASH, 'live_content_ledger_ref': NULL_REF,
            'selected_concept_ids': array(TEXT, 1), 'compatibility_binding_sha256': HASH}),
        'actor': ACTOR, 'authorization': obj({'database_path': TEXT,
            'session_fingerprint': HASH, 'user_state_sha256': HASH}),
        'authorization_context_digest': HASH}),
    DISPATCH: obj({'schema_version': {'const': DISPATCH}, 'intent_ref': REF}),
    RESULT: obj({'schema_version': {'const': RESULT}, 'intent_ref': REF, 'parent_ref': REF,
        'outcome': {'enum': ['transport_failed', 'review_required', 'outcome_unknown', 'blocked']},
        'candidate_ref': NULL_REF, 'batch_ref': NULL_REF, 'review_pack_ref': NULL_REF,
        'validation': obj({'ready_for_human_review': {'oneOf': [{'const': True}, {'const': False}]}})}),
}
ERROR_CODES = (
    'GENERATION_RECOVERY_SCHEMA_INVALID', 'GENERATION_RECOVERY_CONFLICT',
    'GENERATION_RECOVERY_GRAPH_INVALID', 'GENERATION_RECOVERY_SOURCE_CHANGED',
    'GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'GENERATION_RECOVERY_AUTHORIZATION_REQUIRED',
    'GENERATION_RECOVERY_OUTCOME_UNKNOWN', 'GENERATION_RECOVERY_PENDING',
    'GENERATION_BATCH_NOT_REVIEWABLE',
)


class RecoveryError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def check(value, version):
    try:
        validate(value, SCHEMAS[version])
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        raise RecoveryError('GENERATION_RECOVERY_SCHEMA_INVALID', 'Invalid recovery schema') from exc
    return value


def request_root(root, request_id):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', request_id):
        raise RecoveryError('GENERATION_RECOVERY_SCHEMA_INVALID', 'Invalid Request identity')
    path = Path(root).resolve() / 'data/generation_batches' / request_id
    if not path.resolve().is_relative_to(Path(root).resolve()):
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Request escapes runtime')
    return path


def operation_root(root, request_id, operation_id):
    if not re.fullmatch(r'[a-f0-9]{32}', operation_id):
        raise RecoveryError('GENERATION_RECOVERY_SCHEMA_INVALID', 'Invalid operation identity')
    path = request_root(root, request_id) / 'recovery' / operation_id
    if not path.resolve().is_relative_to(request_root(root, request_id).resolve()):
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Operation escapes Request')
    return path


def ref(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Artifact escapes runtime or is missing')
    return {'path': path.relative_to(root).as_posix(), 'sha256': file_sha(path)}


def resolve_ref(root, value):
    try:
        validate(value, REF)
        name = value['path']
        if '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('Unsafe reference')
        path = Path(root).resolve() / name
        if ref(root, path) != value:
            raise ValueError('SHA mismatch')
        return path
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Invalid artifact reference') from exc


def publish(path, value, version):
    check(value, version)
    try:
        write_once(path, value)
    except RuntimeError as exc:
        raise RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Recovery operation payload conflicts') from exc


def publish_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode('utf-8')
    if path.is_file():
        if path.read_bytes() != payload:
            raise RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Derived Review Pack differs')
        return
    temporary = path.parent / ('.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise RecoveryError('GENERATION_RECOVERY_CONFLICT', 'Concurrent Review Pack differs')
    finally:
        temporary.unlink(missing_ok=True)


def authorization(database_path, actor, session_fingerprint):
    """Same trusted local Session/principal; no new reviewer capability or token storage."""
    try:
        validate(actor, ACTOR)
        with sqlite3.connect(Path(database_path).resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            node = db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
            user = db.execute('SELECT status,must_change_password,updated_at FROM users WHERE id=?', (actor['user_id'],)).fetchone()
            sessions = db.execute('SELECT token_hash,expires_at FROM sessions WHERE user_id=?', (actor['user_id'],)).fetchall()
            now = datetime.now(timezone.utc)
            active = any(hashlib.sha256(s['token_hash'].encode()).hexdigest() == session_fingerprint
                and datetime.fromisoformat(s['expires_at'].replace('Z', '+00:00')) > now for s in sessions)
            if not node or node['namespace'] != actor['namespace'] or not user or user['status'] != 'active' or user['must_change_password'] or not active:
                raise ValueError('Inactive caller')
            return {'database_path': str(Path(database_path).resolve()), 'session_fingerprint': session_fingerprint,
                    'user_state_sha256': digest(dict(user))}
    except (sqlite3.Error, OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise RecoveryError('GENERATION_RECOVERY_AUTHORIZATION_REQUIRED', 'Active trusted Console Session required') from exc


def verify_authorization(intent):
    proof = intent['authorization']
    current = authorization(proof['database_path'], intent['actor'], proof['session_fingerprint'])
    if current != proof or digest({'actor': intent['actor'], 'authorization': proof}) != intent['authorization_context_digest']:
        raise RecoveryError('GENERATION_RECOVERY_AUTHORIZATION_REQUIRED', 'Caller authorization changed')


def transport_failure(batch):
    rejected = batch.get('rejected_generations') or []
    return (batch.get('profile') == 'mix' and batch.get('status') == 'generation_incomplete'
        and batch.get('contents') == [] and batch.get('generated_count') == 0
        and batch.get('validation', {}).get('passed') is False
        and bool(rejected) and all(x.get('scope') == 'transport_or_response' for x in rejected)
        and bool(batch.get('generation_attempts'))
        and all(x.get('accepted_count') == 0 for x in batch['generation_attempts']))


def ready_for_review(batch, selected_ids):
    ids = [str(x.get('concept_ref') or '') for x in batch.get('contents') or []]
    full = bool(selected_ids and batch.get('status') == 'review_required'
        and ids == selected_ids and len(ids) == len(set(ids))
        and batch.get('validation', {}).get('passed') is True
        and batch.get('validation', {}).get('material_centers_preserved') is True
        and batch.get('script_generation_contract', {}).get('material_center_validation', {}).get('passed') is True)
    if full:
        return True
    if batch.get('accepted_subset') is None:
        return False
    expected = accepted_subset(batch, selected_ids)
    check(batch['accepted_subset'], ACCEPTED_SUBSET)
    if expected is None or batch['accepted_subset'] != expected:
        raise RecoveryError('GENERATION_BATCH_NOT_REVIEWABLE', 'Accepted subset differs from Native content/selection/Slot identity')
    return True


def accepted_subset(batch, selected_ids):
    """Original Mix owner: reviewable accepted items, never quantity completion.

    Only the versioned Batch Request may review a machine-passed subset. Legacy
    full-count validation and its overall failed quantity result stay intact.
    """
    contents = batch.get('contents') or []
    ids = [str(x.get('concept_ref') or '') for x in contents]
    if not (0 < len(ids) < len(selected_ids)):
        return None
    source = batch.get('lineage', {}).get('request') or {}
    path = Path(source.get('path') or '').resolve()
    if not path.is_file() or file_sha(path) != source.get('sha256'):
        raise RecoveryError('GENERATION_BATCH_NOT_REVIEWABLE', 'Subset Request source changed')
    request = read(path)
    if request.get('schema_version') != 'generation-request-v1.2' or not request.get('batch_admission_ref'):
        return None
    from creative_style_v1 import validate_batch, pinned
    validate_batch(batch)
    final_ref = batch.get('script_generation_contract', {}).get('final_content_plan_ref') or {}
    final = pinned(final_ref)
    actual = [x['concept_id'] for x in final.get('selected_concepts') or []]
    flags = batch.get('validation') or {}
    content_ids = [str(x.get('content_id') or '') for x in contents]
    slots = [str(x.get('logical_slot_id') or '') for x in contents]
    if (actual != selected_ids or len(set(actual)) != len(actual)
            or ids != [c for c in actual if c in ids] or len(set(ids)) != len(ids)
            or not all(content_ids) or len(set(content_ids)) != len(content_ids)
            or not all(slots) or len(set(slots)) != len(slots)
            or batch.get('status') != 'generation_incomplete' or flags.get('passed') is not False
            or batch.get('generated_count') != len(ids) or batch.get('machine_pass_count') != len(ids)
            or batch.get('requested_quantity') != request['quantity']
            or flags.get('material_centers_preserved') is not True
            or flags.get('contract_valid') is not True or flags.get('batch_similarity_passed') is not True
            or batch.get('script_generation_contract', {}).get('material_center_validation', {}).get('passed') is not True
            or any(c.get('validation', {}).get('passed') is not True for c in contents)):
        raise RecoveryError('GENERATION_BATCH_NOT_REVIEWABLE', 'Subset is not an exact machine-passed Native selection')
    return check({'schema_version': ACCEPTED_SUBSET,
        'request_ref': {'path': str(path), 'sha256': file_sha(path)},
        'final_plan_ref': {'path': final_ref['path'], 'sha256': final_ref['sha256']},
        'selected_concept_ids': actual, 'accepted_concept_ids': ids,
        'missing_concept_ids': [c for c in actual if c not in ids],
        'content_ids': content_ids, 'logical_slot_ids': slots,
        'accepted_contents_sha256': digest(contents)}, ACCEPTED_SUBSET)


def require_unreviewed(root, request_id):
    directory = request_root(root, request_id)
    forbidden = ('generation_human_review_v1.json', 'generation_human_review_v2.json',
        'approved_generation_batch_v1.json', 'reviewed_generation_batch_v1.json',
        'generation_batch_approval_receipt.json', 'generation_export_closure_v1.json')
    if any((directory / name).exists() for name in forbidden):
        raise RecoveryError('GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'Human/approved/closed generation cannot be retried')
    for path in (Path(root) / 'output').glob('*.export_receipt.json'):
        receipt = read(path)
        if receipt.get('batch_path') and Path(receipt['batch_path']).resolve().is_relative_to(directory.resolve()):
            raise RecoveryError('GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'Exported generation cannot be retried')


def validate_approved_source(root, request_id, approved, receipt):
    from creative_style_v1 import validate_batch
    validate_batch(approved)
    if not (request_root(root, request_id) / 'recovery').exists():
        return  # Original legacy interpretation.
    state = graph(root, request_id)
    if state['pending'] or not state['result'] or state['result']['outcome'] != 'review_required':
        raise RecoveryError('GENERATION_BATCH_NOT_REVIEWABLE', 'Recovery source has not been published')
    expected = state['result']['batch_ref']
    selected = resolve_ref(root, expected)
    for value in [receipt.get('source_batch') or {}, (approved.get('lineage') or {}).get('source_generation_batch') or {}]:
        if not value.get('path') or Path(value['path']).resolve() != selected or value.get('sha256') != expected['sha256']:
            raise RecoveryError('GENERATION_RECOVERY_SOURCE_CHANGED', 'Human-approved output does not bind the effective recovery source')


def runtime_for_generation(path, batch):
    """Resolve known native lineage only; a copied recovery file is not legacy."""
    request_id = str(batch.get('request_id') or '')
    roots = set()
    def paths(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str):
                yield Path(value['path']).resolve()
            for child in value.values():
                yield from paths(child)
        elif isinstance(value, list):
            for child in value:
                yield from paths(child)
    for source in [Path(path).resolve(), *paths(batch.get('lineage') or {}), *paths(batch.get('script_generation_contract') or {})]:
        for parent in source.parents:
            if parent.name == 'data' and (parent.parent / 'data/generation_requests' / request_id / 'generation_request_v1.json').is_file():
                roots.add(parent.parent)
    if len(roots) > 1 or (batch.get('generation_recovery_v1') and len(roots) != 1):
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Recovery lineage does not have one native runtime')
    if batch.get('generation_recovery_v1'):
        try:
            validate(batch['generation_recovery_v1'], MARKER_SCHEMA)
        except RuntimeError as exc:
            raise RecoveryError('GENERATION_RECOVERY_SCHEMA_INVALID', 'Unknown recovery Batch reader') from exc
    return next(iter(roots), None)


def graph(root, request_id):
    """One deterministic chain; an intent with no result is an explicit pending head."""
    directory = request_root(root, request_id)
    anchor = directory / 'generation_batch_v1.json'
    if not (directory / 'recovery').exists():
        return {'anchor': anchor, 'batch': anchor, 'head_ref': ref(root, anchor) if anchor.is_file() else None,
                'pending': None, 'result': None}
    if not anchor.is_file():
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Recovery has no legacy anchor')
    anchor_ref = ref(root, anchor)
    nodes, children = {}, {}
    for op in (directory / 'recovery').iterdir():
        if not op.is_dir():
            raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Unknown recovery entry')
        expected = operation_root(root, request_id, op.name)
        intent_path = expected / 'intent.json'
        if not intent_path.is_file():
            # An unpublished atomic temporary file is not an admitted intent.
            if all(re.fullmatch(r'\.[a-f0-9]{32}\.tmp', p.name) and p.is_file() for p in op.iterdir()):
                continue
            raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Recovery intent is missing')
        intent = check(read(intent_path), INTENT)
        if intent['operation_id'] != op.name or intent['request_id'] != request_id or intent['anchor_ref'] != anchor_ref:
            raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Recovery identity/anchor mismatch')
        resolve_ref(root, intent['anchor_ref'])
        if not transport_failure(read(anchor)):
            raise RecoveryError('GENERATION_RECOVERY_SCOPE_UNSUPPORTED', 'Invalid original recovery anchor')
        for key, relative in [('request_ref', 'data/generation_requests'), ('source_plan_ref', 'data/production_plans'), ('final_plan_ref', 'data/content_plans')]:
            source = resolve_ref(root, intent['bindings'][key])
            if source.parent != (Path(root).resolve() / relative / request_id):
                raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Recovery source belongs to a different Request')
        intent_ref = ref(root, intent_path)
        if (expected / 'dispatch.json').is_file():
            dispatch = check(read(expected / 'dispatch.json'), DISPATCH)
            if dispatch['intent_ref'] != intent_ref:
                raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Dispatch intent mismatch')
        result_path = expected / 'result.json'
        result = check(read(result_path), RESULT) if result_path.is_file() else None
        if result:
            if result['intent_ref'] != intent_ref or result['parent_ref'] != intent['parent_ref']:
                raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Result does not bind intent and parent')
            for key in ('candidate_ref', 'batch_ref', 'review_pack_ref'):
                if result[key] is not None:
                    path = resolve_ref(root, result[key])
                    if not path.is_relative_to(expected.resolve()):
                        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Result points outside its operation')
                    if key == 'batch_ref' and read(path).get('generation_recovery_v1') != {'reader_version': READER, 'intent_ref': intent_ref}:
                        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Batch does not bind its immutable intent')
            if (result['outcome'] == 'review_required') != result['validation']['ready_for_human_review']:
                raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Result readiness conflicts')
            if result['outcome'] == 'review_required' and (not result['batch_ref'] or not result['review_pack_ref']):
                raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Ready result is incomplete')
        parent = intent['parent_ref']['sha256']
        children.setdefault(parent, []).append(op.name)
        nodes[op.name] = (intent, result, ref(root, result_path) if result else None)
    head, pending, terminal, effective = anchor_ref, None, None, anchor
    visited = set()
    while head['sha256'] in children:
        options = children[head['sha256']]
        if len(options) != 1:
            raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Recovery parent chain forks')
        op_id = options[0]
        intent, result, result_ref = nodes[op_id]
        if op_id in visited or intent['parent_ref'] != head:
            raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Invalid recovery parent chain')
        visited.add(op_id)
        if terminal and terminal['outcome'] == 'review_required':
            raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Successful generation cannot be superseded')
        if not result:
            pending = intent
            break
        terminal = result
        head = result_ref
        if result['batch_ref'] and result['outcome'] in {'review_required', 'transport_failed'}:
            effective = resolve_ref(root, result['batch_ref'])
    if len(visited) != len(nodes):
        raise RecoveryError('GENERATION_RECOVERY_GRAPH_INVALID', 'Missing parent or disconnected recovery node')
    return {'anchor': anchor, 'batch': effective, 'head_ref': head, 'pending': pending, 'result': terminal}
