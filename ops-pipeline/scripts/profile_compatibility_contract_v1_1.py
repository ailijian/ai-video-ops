"""Executable COMPAT C0 schemas, delegated by production_profile_v1.

This module defines structure only. Validation never creates an approval.
SHA references always identify actual artifact bytes, not normalized source text.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath

APPROVAL = 'production-profile-compatibility-approval-v1.1'
SNAPSHOT = 'profile-compatibility-source-snapshot-v1.1'
PREVIEW = 'profile-compatibility-preview-v1.1'
REGISTRY = 'production-profile-registry-v1.1'
COVERAGE = 'creative-coverage-report-v1.1'
RELEASE = 'creative-authority-release-v1.1'
ACTIVATION = 'creative-authority-activation-v1.1'
READER = 'profile-compatibility-reader-v1.1'
CAPABILITY = 'profile_compatibility_reviewer'
RULES = 'mix-compatibility-rules-v1.1'
CONTROL_LOCK = 'profile-compatibility-authority-v1.1'


class CompatibilityError(RuntimeError):
    code = 'PROFILE_COMPATIBILITY_BLOCKED'


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties,
            'required': list(properties) if required is None else required,
            'additionalProperties': False}


def array(items, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum}


TEXT = {'type': 'string', 'minLength': 1}
HASH = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
ID = {'type': 'string', 'pattern': '^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$'}
OPERATION = {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}
REF = obj({'path': TEXT, 'sha256': HASH})
SOURCE_REF = obj({'path': TEXT, 'git_blob_sha256': HASH, 'checkout_sha256': HASH})
NULL_REF = {'oneOf': [{'type': 'null'}, REF]}
ACTOR = obj({'namespace': OPERATION, 'user_id': {'type': 'integer', 'minimum': 1}})
GRANT = obj({'principal': ACTOR, 'capability': {'const': CAPABILITY},
             'event_sha256': HASH, 'events': array({'type': 'object'}, 1)})
TARGET = obj({'case_id': ID, 'pattern_id': ID, 'target_profile': {'const': 'mix'},
              'case_ref': REF, 'case_approval_ref': REF, 'fingerprint_ref': REF,
              'storyboard_ref': REF, 'pattern_ref': REF, 'pattern_approval_ref': REF,
              'profile_ref': REF, 'rules_ref': REF, 'audit_ref': REF})
DECISION = obj({'target_id': HASH, 'target': TARGET,
                'action': {'enum': ['approve', 'reject', 'withdraw']},
                'parent': NULL_REF, 'withdraws': NULL_REF, 'reason': TEXT})

SCHEMAS = {
    SNAPSHOT: obj({'schema_version': {'const': SNAPSHOT}, 'targets': array(TARGET, 1)}),
    PREVIEW: obj({'schema_version': {'const': PREVIEW}, 'operation_id': OPERATION,
                  'control_id': OPERATION,
                  'actor': ACTOR, 'authorization': GRANT, 'source_snapshot': REF,
                  'decisions': array(DECISION, 1), 'created_at': TEXT}),
    APPROVAL: obj({'schema_version': {'const': APPROVAL}, 'operation_id': OPERATION,
                   'control_id': OPERATION,
                   'actor': ACTOR, 'authorization': GRANT, 'source_snapshot': REF,
                   'preview_ref': REF, 'decisions': array(DECISION, 1),
                   'decided_at': TEXT, 'human_gate': {'const': True}}),
    REGISTRY: obj({'schema_version': {'const': REGISTRY}, 'reader_version': {'const': READER},
                   'target_profiles': {'const': ['mix']}, 'profiles': obj({'mix': {'type': 'object'}}),
                   'decision_head_sha256': HASH, 'approval_refs': array(REF),
                   'pattern_compatibility_records': array({'type': 'object'}),
                   'authority': obj({'derived_only': {'const': True}})}),
    COVERAGE: obj({'schema_version': {'const': COVERAGE}, 'source_registry_ref': REF,
                   'decision_head_sha256': HASH, 'case_profile_compatibility_audit': {'type': 'object'},
                   'authority': obj({'can_change_compatibility': {'const': False}})}),
    RELEASE: obj({'schema_version': {'const': RELEASE}, 'release_id': OPERATION,
                  'purpose': {'enum': ['isolated-validation', 'production']},
                  'profiles': {'const': ['mix']}, 'reader_version': {'const': READER},
                  'source_repo_commit': {'type': 'string', 'pattern': '^[a-f0-9]{40}$'},
                  'source_files': array(SOURCE_REF, 1), 'files': array(REF, 1),
                  'decision_head_sha256': HASH, 'registry_ref': REF, 'coverage_ref': REF,
                  'approval_refs': array(REF), 'parent_release': NULL_REF,
                  'control_id': OPERATION}),
    ACTIVATION: obj({'schema_version': {'const': ACTIVATION}, 'operation_id': OPERATION,
                     'release_ref': REF, 'parent_activation': NULL_REF,
                     'decision_head_sha256': HASH, 'control_id': OPERATION,
                     'purpose': {'enum': ['isolated-validation', 'production']}}),
}


def validate(value, schema, label='$'):
    """Validate the deliberately bounded schema vocabulary without dependencies."""
    if 'oneOf' in schema:
        matches = 0
        for option in schema['oneOf']:
            try:
                validate(value, option, label)
                matches += 1
            except CompatibilityError:
                pass
        if matches != 1:
            raise CompatibilityError(f'{label}: expected exactly one schema')
        return
    if 'const' in schema and (value != schema['const'] or type(value) is not type(schema['const'])):
        raise CompatibilityError(f'{label}: invalid constant')
    if 'enum' in schema and value not in schema['enum']:
        raise CompatibilityError(f'{label}: invalid enum')
    kind = schema.get('type')
    types = {'object': dict, 'array': list, 'string': str, 'integer': int, 'null': type(None)}
    if kind and type(value) is not types[kind]:
        raise CompatibilityError(f'{label}: expected {kind}')
    if kind == 'object' and 'properties' in schema:
        properties = schema['properties']
        if set(schema['required']) - value.keys():
            raise CompatibilityError(f'{label}: missing fields')
        if schema.get('additionalProperties') is False and value.keys() - properties.keys():
            raise CompatibilityError(f'{label}: unknown fields')
        for key, item in value.items():
            validate(item, properties[key], f'{label}.{key}')
    if kind == 'array':
        if len(value) < schema.get('minItems', 0):
            raise CompatibilityError(f'{label}: empty collection')
        if len(value) > schema.get('maxItems', len(value)):
            raise CompatibilityError(f'{label}: collection exceeds its bounded scope')
        for index, item in enumerate(value):
            validate(item, schema['items'], f'{label}[{index}]')
    if kind == 'string':
        if (len(value) < schema.get('minLength', 0) or (schema.get('minLength', 0) and not value.strip())
                or ('pattern' in schema and not re.fullmatch(schema['pattern'], value))):
            raise CompatibilityError(f'{label}: invalid string')
    if kind == 'integer' and value < schema.get('minimum', value):
        raise CompatibilityError(f'{label}: invalid integer')


def validate_contract(value, expected=None):
    version = value.get('schema_version') if isinstance(value, dict) else None
    if version not in SCHEMAS or (expected is not None and version != expected):
        raise CompatibilityError('Unknown or unexpected Compatibility schema')
    validate(value, SCHEMAS[version])
    return value


def safe_relative(path):
    candidate = PurePosixPath(path)
    if (not isinstance(path, str) or '\\' in path or ':' in path or candidate.is_absolute()
            or '..' in candidate.parts or str(candidate) != path or not candidate.parts):
        raise CompatibilityError('Artifact reference must be a canonical relative path')
    return path
