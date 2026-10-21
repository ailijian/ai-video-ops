"""PC0 R2 executable contracts. Derivation never grants production authority."""
from __future__ import annotations

import re
from profile_compatibility_contract_v1_1 import obj, array, REF, HASH, ACTOR, TEXT, OPERATION
from profile_compatibility_contract_v1_1 import validate as _validate

VERSION = 'publish-copy-v1.0'
HEADLINE = obj({'order': {'type': 'integer', 'minimum': 1}, 'text': TEXT, 'source_unit_ids': array(TEXT, 1),
                'mapping_kind': {'enum': ['extract', 'condense', 'merge']}})
COMMON = {'target_id': TEXT, 'source_version_sha256': HASH, 'publish_title': TEXT,
          'publish_body': TEXT, 'topics': array(TEXT, 1)}
ITEM = {'oneOf': [obj(COMMON), obj({**COMMON, 'production_headlines': array(HEADLINE)})]}
PAYLOAD = obj({'items': array(ITEM, 1)})
PARENT = {'oneOf': [REF, {'type': 'null'}]}
BASE = {'request_id': TEXT, 'operation_id': OPERATION}
SCHEMAS = {
 'publish-copy-generation-intent-v1.0': obj({'schema_version': {'const': 'publish-copy-generation-intent-v1.0'},
    **BASE, 'parent': PARENT, 'source_sha256': HASH, 'source_refs': array(REF, 1),
    'source_snapshot_ref': REF, 'prompt_sha256': HASH, 'parameters': obj({'version': {'const': VERSION}, 'model': TEXT, 'transport': TEXT,
        'owner_sha256': HASH, 'memory_sha256': {'oneOf': [HASH, {'type': 'null'}]},
        'target_ids': array(TEXT, 1)}), 'actor': ACTOR, 'authorization': {'type': 'object'}, 'created_at': TEXT}),
 'publish-copy-generation-dispatch-v1.0': obj({'schema_version': {'const': 'publish-copy-generation-dispatch-v1.0'},
    **BASE, 'intent_ref': REF, 'dispatched_at': TEXT}),
 'publish-copy-generation-response-v1.0': obj({'schema_version': {'const': 'publish-copy-generation-response-v1.0'},
    **BASE, 'intent_ref': REF, 'payload': {'type': 'object'}, 'received_at': TEXT}),
 'publish-copy-generation-result-v1.0': obj({'schema_version': {'const': 'publish-copy-generation-result-v1.0'},
    **BASE, 'intent_ref': REF, 'response_ref': REF, 'draft_ref': REF}),
 'publish-copy-generation-task-v1.0': obj({'schema_version': {'const': 'publish-copy-generation-task-v1.0'},
    **BASE, 'intent_ref': REF, 'task_id': TEXT, 'task_operation_identity': TEXT}),
 'publish-copy-draft-v1.0': obj({'schema_version': {'const': 'publish-copy-draft-v1.0'},
    'request_id': TEXT, 'draft_id': OPERATION, 'parent': PARENT, 'source_sha256': HASH,
    'source_refs': array(REF, 1), 'source_snapshot_ref': REF, 'payload': PAYLOAD,
    'derived_targets': array({'type': 'object'}, 1), 'actor': ACTOR, 'created_at': TEXT}),
 'publish-copy-confirmation-v1.0': obj({'schema_version': {'const': 'publish-copy-confirmation-v1.0'},
    'request_id': TEXT, 'operation_id': OPERATION, 'parent_confirmation_ref': PARENT,
    'targets': array({'type': 'object'}, 1), 'decision': {'const': 'confirm'},
    'draft_ref': REF, 'source_sha256': HASH, 'payload_sha256': HASH,
    'headline_mapping_sha256': HASH, 'actor': ACTOR, 'authorization': {'type': 'object'},
    'human_gate': {'const': True}, 'confirmed_at': TEXT}),
}

class PublishCopyError(RuntimeError):
    def __init__(self, code, message='发布信息需要重新核对，原制作稿会保留。'):
        self.code = 'PUBLISH_COPY_' + code
        super().__init__(message)

def check(value, version):
    try:
        _validate(value, SCHEMAS[version])
    except (RuntimeError, ValueError, KeyError, TypeError) as exc:
        raise PublishCopyError('CONTRACT_INVALID') from exc
    return value

def identifier(value, pattern=r'(gen|news)_[A-Za-z0-9]+'):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise PublishCopyError('IDENTITY_INVALID')
    return value
