"""Immutable attempt evidence delegated by the original Novel News owner.

No model calls, Human approval, Task truth or output delivery live here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

from operation_lock_v1 import operation_lock
from profile_compatibility_decisions_v1_1 import read, file_sha, write_once, digest
from human_review_operations_v1 import io_path
from profile_compatibility_contract_v1_1 import (validate as validate_schema, CompatibilityError,
    obj, HASH, ACTOR, TEXT, REF)

INTENT = 'novel-news-generation-intent-v1.0'
PREFIX = 'novel-news-generation-'
OPERATION = {'type': 'string', 'pattern': '[a-f0-9]{32}'}
BASE = {'operation_id': OPERATION, 'request_id': {'type': 'string', 'pattern': 'gen_[a-zA-Z0-9]+'},
        'intent_sha256': HASH}
SCHEMAS = {kind: obj({'schema_version': {'const': PREFIX + kind + '-v1.0'}, **BASE, **fields})
    for kind, fields in {
        'dispatch': {'dispatched_at': TEXT},
        'response': {'received_at': TEXT, 'response': obj({'payload': {'type': 'object'},
            'response_sha256': {'oneOf': [TEXT, {'type': 'null'}]}, 'usage': {'type': 'object'},
            'transport_mode': {'enum': ['native-remote', 'explicit-transport-boundary']}})},
        'result': {'outcome': {'const': 'review_required'}, 'plan_sha256': HASH, 'prepared_response_sha256': HASH},
        'task': {'task_id': TEXT, 'task_operation_identity': TEXT},
    }.items()}
SCHEMAS['intent'] = obj({'schema_version': {'const': INTENT}, 'operation_id': OPERATION,
    'request_id': BASE['request_id'], 'created_at': TEXT,
    'parent': {'oneOf': [obj({'operation_id': OPERATION, 'sha256': HASH}), {'type': 'null'}]},
    'snapshot': obj({'refs': obj({name: REF for name in (
        'request', 'source_plan', 'business_persona_ref', 'speaker_persona_ref')}),
        'fact_atoms_sha256': HASH, 'selected_opportunity_sha256': HASH,
        'authority_binding': {'oneOf': [{'type': 'object'}, {'type': 'null'}]},
        'memory_sha256': {'oneOf': [HASH, {'type': 'null'}]}}),
    'prompt_sha256': HASH, 'parameters': obj({'prompt_version': TEXT, 'model': TEXT, 'transport': TEXT,
        'generator_owner_sha256': HASH, 'transport_owner_sha256': HASH,
        'minimum_beats': {'const': 4}, 'maximum_beats': {'const': 8}}), 'actor': ACTOR,
    'authorization': obj({'principal': ACTOR, 'database_identity_sha256': HASH, 'user_state_sha256': HASH}),
    'task_operation_identity': TEXT})


class GenerationError(RuntimeError):
    def __init__(self, code, message='新闻体生成需要核对原操作。'):
        super().__init__(message)
        self.code = 'NEWS_GENERATION_' + code


def now():
    return datetime.now(timezone.utc).isoformat()


def directory(root, rid, operation_id=None):
    if not re.fullmatch(r'gen_[a-zA-Z0-9]+', rid):
        raise GenerationError('IDENTITY_INVALID')
    base = Path(root) / 'data/metrics' / rid / 'novel_news_generation_v1'
    if operation_id is None:
        return base
    if not re.fullmatch(r'[a-f0-9]{32}', operation_id):
        raise GenerationError('IDENTITY_INVALID')
    return base / operation_id


def commit_lock(root, rid):
    return operation_lock(root, 'novel-news-generation-commit:' + rid)


@contextmanager
def mutation_fence(root):
    """Existing Console backup gate, held only for Native file mutations."""
    with operation_lock(root, 'authority_backup_gate', shared=True):
        yield


def validate(value, kind):
    schema = SCHEMAS[kind]
    try:
        validate_schema(value, schema)
    except (CompatibilityError, ValueError, KeyError) as exc:
        raise GenerationError('EVIDENCE_INVALID') from exc
    return value


def head(root, rid):
    records = {}
    for path in directory(root, rid).glob('*/intent.json'):
        value = validate(read(path), 'intent')
        if value['request_id'] != rid or value['operation_id'] != path.parent.name:
            raise GenerationError('EVIDENCE_INVALID')
        records[file_sha(path)] = value
    if not records:
        return None
    parents = set()
    for sha, value in records.items():
        parent = value['parent']
        if parent:
            if (set(parent) != {'operation_id', 'sha256'} or parent['sha256'] not in records
                    or records[parent['sha256']]['operation_id'] != parent['operation_id']):
                raise GenerationError('PARENT_MISSING')
            parents.add(parent['sha256'])
    leaves = set(records) - parents
    if len(leaves) != 1 or sum(v['parent'] is None for v in records.values()) != 1:
        raise GenerationError('CHAIN_CONFLICT')
    sha = next(iter(leaves))
    visited = set()
    cursor = sha
    while cursor not in visited:
        visited.add(cursor)
        parent = records[cursor]['parent']
        if parent is None:
            break
        cursor = parent['sha256']
    if len(visited) != len(records):
        raise GenerationError('CHAIN_CONFLICT')
    return {'operation_id': records[sha]['operation_id'], 'sha256': sha, 'intent': records[sha]}


def identity(context):
    from news_export_recovery_v1 import identity as trusted_identity
    try:
        return trusted_identity(context)
    except RuntimeError as exc:
        raise GenerationError('AUTHORIZATION_REQUIRED') from exc


def current_identity(intent, context):
    current = identity(context)
    if intent['actor'] != context['actor'] or intent['authorization'] != current:
        raise GenerationError('AUTHORIZATION_CHANGED')


def snapshot(root, context):
    """Original source reader plus exact immutable source/memory references."""
    from news_runtime_v1_2 import configured, current
    paths, request = context['paths'], context['request']
    binding = request.get('profile_compatibility_v1_2')
    if configured(root):
        current(root, reuse_intent='novel_content', pinned=binding)
    lineage = request['lineage']
    refs = {key: {'path': str(paths[key].relative_to(root)), 'sha256': file_sha(paths[key])}
            for key in ('request', 'source_plan')}
    for key in ('business_persona_ref', 'speaker_persona_ref'):
        path = Path(lineage[key]['path'])
        refs[key] = {'path': str(path.relative_to(root)), 'sha256': file_sha(path)}
    business = request['persona_id']
    memory = Path(root) / 'data/content_ledgers' / business / 'content_ledger_v1.json'
    return {'refs': refs, 'fact_atoms_sha256': digest(context['usable_atoms']),
            'selected_opportunity_sha256': digest(context['selected']),
            'authority_binding': binding,
            'memory_sha256': file_sha(memory) if memory.is_file() else None}


def assert_current(root, rid, expected, source, authorization_context):
    latest = head(root, rid)
    if not latest or latest['operation_id'] != expected['operation_id'] or latest['sha256'] != expected['sha256']:
        raise GenerationError('SUPERSEDED')
    if latest['intent']['snapshot'] != source:
        raise GenerationError('SOURCE_CHANGED')
    current_identity(latest['intent'], authorization_context)
    return latest


def append(root, rid, *, source, prompt, parameters, authorization_context, expected_parent=None):
    """Caller holds commit lock and has checked original Task admission/fencing."""
    auth = identity(authorization_context)
    current = head(root, rid)
    material = {'snapshot': source, 'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                'parameters': parameters, 'actor': authorization_context['actor'], 'authorization': auth}
    if current:
        if expected_parent:
            # Double click of the same explicit confirmation returns its child.
            parent = current['intent']['parent']
            if parent and parent['sha256'] == expected_parent:
                if any(current['intent'][k] != v for k, v in material.items()):
                    raise GenerationError('OPERATION_CONFLICT')
                return current
            if current['sha256'] != expected_parent:
                raise GenerationError('OPERATION_CONFLICT')
        else:
            if any(current['intent'][k] != v for k, v in material.items()):
                raise GenerationError('OPERATION_CONFLICT')
            return current
    elif expected_parent:
        raise GenerationError('PARENT_MISSING')
    parent = {k: current[k] for k in ('operation_id', 'sha256')} if current else None
    operation = digest({'request_id': rid, 'parent': parent, **material})[:32]
    value = {'schema_version': INTENT, 'operation_id': operation, 'request_id': rid,
             'created_at': now(), 'parent': parent, **material,
             'task_operation_identity': f'novel_news_generate:{rid}:{operation}'}
    validate(value, 'intent')
    path = directory(root, rid, operation) / 'intent.json'
    write_once(path, value)
    return {'operation_id': operation, 'sha256': file_sha(path), 'intent': value}


def record(root, rid, attempt, kind, **fields):
    value = {'schema_version': PREFIX + kind + '-v1.0', 'operation_id': attempt['operation_id'],
             'request_id': rid, 'intent_sha256': attempt['sha256'], **fields}
    validate(value, kind)
    path = directory(root, rid, attempt['operation_id']) / (kind + '.json')
    write_once(path, value)
    return value


def evidence(root, rid, attempt, kind):
    path = directory(root, rid, attempt['operation_id']) / (kind + '.json')
    if not path.is_file():
        return None
    value = validate(read(path), kind)
    if (value['intent_sha256'] != attempt['sha256'] or value['request_id'] != rid
            or value['operation_id'] != attempt['operation_id']):
        raise GenerationError('EVIDENCE_INVALID')
    return value


def task_running(database_path, operation_identity):
    with sqlite3.connect(Path(database_path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        row = db.execute('SELECT status,lease_expires_at FROM tasks WHERE operation_identity=? ORDER BY rowid DESC LIMIT 1',
                         (operation_identity,)).fetchone()
    return bool(row and (row[0] == 'queued' or (row[0] == 'running' and row[1]
        and datetime.fromisoformat(row[1].replace('Z', '+00:00')) > datetime.now(timezone.utc))))


def project_task_execution(root, rid, generation, task):
    """Native projection of execution evidence; never Human/business authority."""
    value = dict(generation)
    if task:
        payload = json.loads(task['payload_json'])
        if (not payload.get('novel_generation') and (task['attempt_count'] or task['status'] == 'running')
                and not value.get('ready_for_human_review')):
            value.update(recovery_state='dispatched_outcome_unknown', legacy_unbound=True)
        admitted = payload.get('novel_generation')
        if admitted and not value.get('legacy_completed'):
            attempt = head(root, rid)
            if attempt and attempt['operation_id'] == admitted['operation_id']:
                # Revoke/regrant is a new user-state epoch. A plain Session
                # expiry is different: re-login can resume the same operation.
                try:
                    context = admitted['authorization_context']
                    db_path = Path(context['authorization']['database_path']).resolve()
                    stored = attempt['intent']['authorization']
                    if digest(str(db_path)) != stored['database_identity_sha256']:
                        raise ValueError('Database identity')
                    with sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True) as db:
                        db.row_factory = sqlite3.Row
                        db.execute('PRAGMA query_only=ON')
                        namespace = db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
                        user = db.execute('SELECT status,must_change_password,updated_at FROM users WHERE id=?',
                                          (attempt['intent']['actor']['user_id'],)).fetchone()
                    if (not namespace or namespace['namespace'] != attempt['intent']['actor']['namespace'] or not user
                            or user['status'] != 'active' or user['must_change_password']
                            or digest(dict(user)) != stored['user_state_sha256']):
                        raise ValueError('User permission state')
                except (sqlite3.Error, KeyError, TypeError, ValueError, OSError):
                    value.update(recovery_state='source_or_authorization_conflict',
                        native_code='NEWS_GENERATION_AUTHORIZATION_CHANGED', ready_for_human_review=False)
        value['task_running'] = bool(task['status'] == 'queued' or (task['status'] == 'running'
            and task['lease_expires_at'] and datetime.fromisoformat(task['lease_expires_at'].replace('Z', '+00:00'))
            > datetime.now(timezone.utc)))
    return value
