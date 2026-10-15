"""Independent Case Approval Owner authorization for the Console entry point.

The existing no-Console-context CLI is trusted offline maintenance. HTTP callers
must use the explicit Console context; login or a reviewer string grants nothing.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

CAPABILITY = 'case_library_reviewer'
VERSION = 'case-library-capability-v1.0'


class CaseAuthorizationError(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def validate_console_reviewer(database_path, user_id, namespace, reviewer=None):
    if (isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1
            or not re.fullmatch(r'[a-f0-9]{32}', str(namespace))):
        raise CaseAuthorizationError('Invalid local principal')
    try:
        with sqlite3.connect(Path(database_path).resolve().as_uri()+'?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            node = db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
            user = db.execute('SELECT id,phone,status,must_change_password FROM users WHERE id=?', (user_id,)).fetchone()
            rows = db.execute('SELECT * FROM case_capability_events WHERE user_id=? ORDER BY event_id', (user_id,)).fetchall()
            if not node or node['namespace'] != namespace or not user or user['status'] != 'active' or user['must_change_password']:
                raise CaseAuthorizationError('Principal is not active on this node')
            if reviewer is not None and reviewer != user['phone']:
                raise CaseAuthorizationError('Reviewer does not match authenticated principal')
            previous = None
            for sequence, row in enumerate(rows, 1):
                record = json.loads(row['record_json'])
                if (set(record) != {'schema_version','capability','namespace','user_id','sequence','action','operator','reason','at','parent_sha256'}
                        or record['schema_version'] != VERSION or record['capability'] != CAPABILITY
                        or record['namespace'] != namespace or record['user_id'] != user_id
                        or record['sequence'] != sequence or record['action'] != row['action']
                        or record['at'] != row['occurred_at'] or not record['operator'] or not record['reason']
                        or record['parent_sha256'] != previous or digest(record) != row['event_sha256']):
                    raise CaseAuthorizationError('Capability history cannot be validated')
                previous = row['event_sha256']
            if not rows or rows[-1]['action'] != 'grant':
                raise CaseAuthorizationError('Explicit reviewer capability required')
            return {'namespace':namespace, 'user_id':user_id, 'capability':CAPABILITY,
                    'event_id':rows[-1]['event_id'], 'event_sha256':previous}
    except (sqlite3.Error, OSError, ValueError, TypeError, KeyError) as exc:
        raise CaseAuthorizationError('Capability authority unavailable') from exc


def validate_authorization_evidence(database_path, evidence):
    """Validate an immutable grant at decision time, even after a later revoke."""
    try:
        if set(evidence) != {'namespace','user_id','capability','event_id','event_sha256'} or evidence['capability'] != CAPABILITY:
            return False
        with sqlite3.connect(Path(database_path).resolve().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory=sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            node=db.execute('SELECT namespace FROM console_principal_namespace WHERE singleton=1').fetchone()
            if not node or node['namespace']!=evidence['namespace']: return False
            rows=db.execute('SELECT * FROM case_capability_events WHERE user_id=? AND event_id<=? ORDER BY event_id',
                            (evidence['user_id'],evidence['event_id'])).fetchall()
            parent=None
            for sequence,row in enumerate(rows,1):
                record=json.loads(row['record_json'])
                if (record['schema_version']!=VERSION or record['capability']!=CAPABILITY
                        or record['namespace']!=evidence['namespace'] or record['user_id']!=evidence['user_id']
                        or record['sequence']!=sequence or record['parent_sha256']!=parent
                        or record['action']!=row['action'] or digest(record)!=row['event_sha256']): return False
                parent=row['event_sha256']
            return bool(rows and rows[-1]['event_id']==evidence['event_id'] and rows[-1]['action']=='grant' and parent==evidence['event_sha256'])
    except (sqlite3.Error,OSError,ValueError,TypeError,KeyError):
        return False
