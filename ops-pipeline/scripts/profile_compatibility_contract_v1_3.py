"""Explicit production-purpose extension; v1.1/v1.2 schemas remain immutable."""
from copy import deepcopy
from profile_compatibility_contract_v1_1 import *

REGISTRY = 'production-profile-registry-v1.3'
COVERAGE = 'creative-coverage-report-v1.3'
RELEASE = 'creative-authority-release-v1.3'
ACTIVATION = 'creative-authority-activation-v1.3'
READER = 'profile-compatibility-reader-v1.3'
CONFIG = 'compatibility-runtime-config-v1.3'
BINDING = 'profile-compatibility-runtime-binding-v1.3'
PROFILES = {'enum': [['mix'], ['news'], ['mix','news']]}
SCHEMAS = {
    CONFIG: obj({'schema_version': {'const': CONFIG}, 'purpose': {'const': 'production'},
        'control_root': TEXT, 'control_id': OPERATION, 'reader_version': {'const': READER}, 'profiles': PROFILES}),
    REGISTRY: obj({'schema_version': {'const': REGISTRY}, 'reader_version': {'const': READER},
        'target_profiles': PROFILES, 'profiles': {'type': 'object'}, 'production_admission_ref': REF,
        'decision_head_sha256': HASH, 'approval_refs': array(REF,1),
        'pattern_compatibility_records': array({'type': 'object'},1),
        'authority': obj({'derived_only': {'const': True}})}),
    COVERAGE: obj({'schema_version': {'const': COVERAGE}, 'source_registry_ref': REF,
        'production_admission_ref': REF, 'decision_head_sha256': HASH, 'approval_refs': array(REF,1),
        'case_profile_compatibility_audit': {'type': 'object'},
        'authority': obj({'can_change_compatibility': {'const': False}})}),
    RELEASE: obj({'schema_version': {'const': RELEASE}, 'release_id': OPERATION,
        'purpose': {'const': 'production'}, 'profiles': PROFILES, 'reader_version': {'const': READER},
        'source_repo_commit': {'type': 'string', 'pattern': '^[a-f0-9]{40}$'},
        'source_files': array(SOURCE_REF,1), 'files': array(REF,1), 'control_id': OPERATION,
        'decision_head_sha256': HASH, 'registry_ref': REF, 'coverage_ref': REF,
        'approval_refs': array(REF,1), 'parent_release': NULL_REF, 'production_admission_ref': REF}),
    ACTIVATION: obj({'schema_version': {'const': ACTIVATION}, 'operation_id': OPERATION,
        'release_ref': REF, 'parent_activation': NULL_REF, 'decision_head_sha256': HASH,
        'control_id': OPERATION, 'purpose': {'const': 'production'}, 'production_admission_ref': REF}),
    BINDING: obj({'schema_version': {'const': BINDING}, 'target_profile': {'const': 'news'},
        'reuse_intent': {'enum': ['novel_content','cross_profile_repurpose']},
        'usage_scope': {'const': 'human_approved_production_scope'},
        'production_admission_ref': REF, 'control_id': OPERATION, 'activation_ref': REF, 'release_ref': REF,
        'decision_head_sha256': HASH, 'approval_refs': array(REF,1), 'target_refs': array(REF,1),
        'profile_ref': REF, 'rules_ref': REF, 'coverage_ref': REF, 'pattern_ref': REF,
        'pattern_approval_ref': REF,
        'structural_sources': array(obj({'case_id': ID, 'case_ref': REF, 'case_approval_ref': REF,
            'fingerprint_ref': REF, 'storyboard_ref': REF}),1)}),
}


def validate_contract(value, expected=None):
    version = value.get('schema_version') if isinstance(value,dict) else None
    if version not in SCHEMAS or expected is not None and version != expected:
        raise CompatibilityError('Unknown or unexpected production Compatibility schema')
    validate(value,SCHEMAS[version])
    if version == REGISTRY and sorted(value['profiles']) != value['target_profiles']:
        raise CompatibilityError('Production Registry profile set differs')
    return value


def schema_documents():
    return deepcopy(SCHEMAS)
