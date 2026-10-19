"""Independent capability using the existing local principal/event-chain model."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from case_console_authorization_v1 import digest
from profile_compatibility_contract_v1_1 import ACTOR, CAPABILITY, GRANT, CompatibilityError, validate

VERSION = 'profile-compatibility-capability-v1.0'
TABLE = 'profile_compatibility_capability_events'
FIELDS = {'schema_version', 'capability', 'namespace', 'user_id', 'sequence',
          'action', 'operator', 'reason', 'at', 'parent_sha256'}


def validate_grant_proof(proof):
    validate(proof, GRANT)
    parent = None
    for sequence, event in enumerate(proof['events'], 1):
        record = event.get('record')
        if (set(event) != {'record', 'sha256'} or not isinstance(record, dict)
                or set(record) != FIELDS or record['schema_version'] != VERSION
                or record['capability'] != CAPABILITY or type(record['sequence']) is not int or record['sequence'] != sequence
                or type(record['user_id']) is not int
                or record['parent_sha256'] != parent
                or {k: record[k] for k in ('namespace', 'user_id')} != proof['principal']
                or record['action'] not in {'grant', 'revoke'}
                or any(not isinstance(record[k], str) or not record[k].strip() for k in ('operator', 'reason', 'at'))
                or digest(record) != event['sha256']):
            raise CompatibilityError('Compatibility capability history is invalid')
        parent = event['sha256']
    if proof['events'][-1]['record']['action'] != 'grant' or parent != proof['event_sha256']:
        raise CompatibilityError('Explicit Compatibility reviewer grant required')
    return proof


def authorization(database_path, actor):
    validate(actor, ACTOR)
    try:
        with sqlite3.connect(Path(database_path).resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            node = db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
            user = db.execute('SELECT status,must_change_password FROM users WHERE id=?', (actor['user_id'],)).fetchone()
            if not node or node['namespace'] != actor['namespace'] or not user or user['status'] != 'active' or user['must_change_password']:
                raise CompatibilityError('Compatibility principal is not active')
            rows = db.execute(f'SELECT * FROM {TABLE} WHERE user_id=? ORDER BY event_id', (actor['user_id'],)).fetchall()
            events = []
            for row in rows:
                record = json.loads(row['record_json'])
                if record.get('action') != row['action'] or record.get('at') != row['occurred_at']:
                    raise CompatibilityError('Capability event projection mismatch')
                events.append({'record': record, 'sha256': row['event_sha256']})
            proof = {'principal': actor, 'capability': CAPABILITY,
                     'event_sha256': events[-1]['sha256'] if events else '', 'events': events}
            return validate_grant_proof(proof)
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as exc:
        raise CompatibilityError('Compatibility authorization unavailable') from exc
