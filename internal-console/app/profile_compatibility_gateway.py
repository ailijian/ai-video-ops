"""Thin gateway; canonical decisions remain owned by Production Profile."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .case_library_access import principal
from .database import transaction
from .operation_lock import operation_lock


def manage_reviewer(settings, user_id, *, action, operator, reason, capability='profile_compatibility_reviewer'):
    """Trusted local grant/revoke only; deliberately not an HTTP endpoint."""
    from profile_compatibility_authorization_v1 import TABLE, VERSION, digest
    from profile_compatibility_contract_v1_1 import CAPABILITY
    from profile_compatibility_contract_v1_2 import CAPABILITY as NEWS, PATTERN_CAPABILITY, CAPABILITY_EVENT
    if capability not in {CAPABILITY, NEWS, PATTERN_CAPABILITY}:
        raise ValueError('Unknown independent reviewer capability')
    version = VERSION if capability == CAPABILITY else CAPABILITY_EVENT
    actor = principal(settings, user_id)
    if action not in {'grant', 'revoke'} or not operator.strip() or not reason.strip():
        raise ValueError('Explicit grant/revoke, operator and reason required')
    with operation_lock(settings.pipeline_root, f"profile-reviewer:{actor['namespace']}:{actor['user_id']}"), transaction(settings.database_path, immediate=True) as db:
        row = db.execute(f'SELECT record_json,event_sha256 FROM {TABLE} WHERE user_id=? AND capability=? ORDER BY event_id DESC LIMIT 1',
                         (user_id, capability)).fetchone()
        record = {'schema_version': version, 'capability': capability, **actor,
                  'sequence': json.loads(row['record_json'])['sequence'] + 1 if row else 1,
                  'action': action, 'operator': operator.strip(), 'reason': reason.strip(),
                  'at': datetime.now(timezone.utc).isoformat(),
                  'parent_sha256': row['event_sha256'] if row else None}
        event_sha = digest(record)
        db.execute(f'INSERT INTO {TABLE}(user_id,capability,action,record_json,event_sha256,occurred_at) VALUES (?,?,?,?,?,?)',
                   (user_id, capability, action, json.dumps(record, ensure_ascii=False), event_sha, record['at']))
        return {'actor': actor, 'action': action, 'event_sha256': event_sha}


def preview(settings, user_id, operation_id, decisions):
    from production_profile_v1 import preview_compatibility_v1_1
    return preview_compatibility_v1_1(settings.pipeline_root, settings.database_path,
                                    principal(settings, user_id), operation_id, decisions)


def confirm(settings, user_id, operation_id, preview_sha256):
    from production_profile_v1 import decide_compatibility_v1_1
    return decide_compatibility_v1_1(settings.pipeline_root, settings.database_path,
                                   principal(settings, user_id), operation_id, preview_sha256)
