import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from profile_compatibility_contract_v1_1 import (
    APPROVAL, ACTOR, CAPABILITY, REF, SCHEMAS, CompatibilityError,
    safe_relative, validate, validate_contract,
)


def test_contract_has_explicit_versioned_stages_and_no_unknown_version_fallback():
    assert len(SCHEMAS) == 7
    assert CAPABILITY == 'profile_compatibility_reviewer'
    with pytest.raises(CompatibilityError):
        validate_contract({'schema_version': 'production-profile-compatibility-approval-v9'})


@pytest.mark.parametrize('value', [
    {'path': 'data/case.json', 'sha256': 'a' * 63},
    {'path': 'data/case.json', 'sha256': 'a' * 64, 'approved': True},
    {'sha256': 'a' * 64},
])
def test_strict_ref_fields(value):
    with pytest.raises(CompatibilityError):
        validate(value, REF)


@pytest.mark.parametrize('path', ['../data/x', '/data/x', 'C:/data/x', 'data\\x', 'data//x', '.'])
def test_reference_paths_do_not_escape_or_alias(path):
    with pytest.raises(CompatibilityError):
        safe_relative(path)


def test_actor_rejects_boolean_identity():
    with pytest.raises(CompatibilityError):
        validate({'namespace': 'a' * 32, 'user_id': True}, ACTOR)


def test_snapshot_input_cannot_depend_on_derived_registry():
    schema = SCHEMAS['profile-compatibility-source-snapshot-v1.1']
    assert 'registry_ref' not in schema['properties']
    assert 'coverage_ref' not in schema['properties']
    assert schema['additionalProperties'] is False


def test_human_gate_cannot_be_numeric_true():
    field = copy.deepcopy(SCHEMAS[APPROVAL]['properties']['human_gate'])
    with pytest.raises(CompatibilityError):
        validate(1, field)


def test_native_preview_and_receipt_bind_control_identity_and_separate_source_hashes():
    from profile_compatibility_contract_v1_1 import PREVIEW, RELEASE
    assert 'control_id' in SCHEMAS[PREVIEW]['required']
    assert 'control_id' in SCHEMAS[APPROVAL]['required']
    source = SCHEMAS[RELEASE]['properties']['source_files']['items']
    assert 'git_blob_sha256' in source['required'] and 'checkout_sha256' in source['required']
    assert 'sha256' not in source['properties']
