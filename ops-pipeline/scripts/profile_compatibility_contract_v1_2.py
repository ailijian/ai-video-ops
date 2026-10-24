"""Additive NC0 News contract, delegated by the Production Profile owner.

These schemas do not authorize a run. Native owners must verify sources,
current grants and the activated decision graph. Legacy v1.1 is unchanged.
"""
from __future__ import annotations

from copy import deepcopy

from profile_compatibility_contract_v1_1 import (
    ACTOR, HASH, ID, NULL_REF, OPERATION, REF, SOURCE_REF, TEXT,
    CompatibilityError, array, obj, validate,
)

APPROVAL = 'production-profile-compatibility-approval-v1.2'
SNAPSHOT = 'profile-compatibility-source-snapshot-v1.2'
PREVIEW = 'profile-compatibility-preview-v1.2'
PROFILE = 'news-production-profile-definition-v1.2'
RULES = 'news-compatibility-rules-v1.2'
REGISTRY = 'production-profile-registry-v1.2'
COVERAGE = 'creative-coverage-report-v1.2'
RELEASE = 'creative-authority-release-v1.2'
ACTIVATION = 'creative-authority-activation-v1.2'
READER = 'profile-compatibility-reader-v1.2'
CONFIG = 'compatibility-runtime-config-v1.2'
BINDING = 'profile-compatibility-runtime-binding-v1.2'
EVIDENCE = 'news-isolated-path-validation-evidence-v1.0'
CAPABILITY = 'news_profile_compatibility_reviewer'
PATTERN_CAPABILITY = 'news_pattern_reviewer'
CAPABILITY_EVENT = 'profile-compatibility-capability-v1.1'
PATTERN_INTENT = 'news-pattern-human-intent-v1.1'
PATTERN_RECEIPT = 'pattern-approval-receipt-v1.1'
RESEARCH_RECEIPT = 'news-research-human-approval-v1.1'
QUALIFICATION = 'human_authorized_isolated_qualification'
VALIDATED = 'native_validation_evidence_completed'
FOUNDER = 'founder_isolated_runtime_eligibility'
STAGES = [QUALIFICATION, VALIDATED, FOUNDER]
INTENT = {'enum': ['novel_content', 'cross_profile_repurpose']}
# New isolated roots may include the exact existing Mix contract for preparing
# legitimate history. Existing v1.1 roots are never migrated or rewritten.
PROFILE_SET = {'enum': [['news'], ['mix','news']]}


def grant_schema(capability):
    return obj({'principal': ACTOR, 'capability': {'const': capability},
                'event_sha256': HASH, 'events': array({'type': 'object'}, 1)})


GRANT = grant_schema(CAPABILITY)
PATTERN_GRANT = grant_schema(PATTERN_CAPABILITY)
TARGET = obj({'case_id': ID, 'pattern_id': ID, 'target_profile': {'const': 'news'},
              **{name: REF for name in (
                  'case_ref', 'case_approval_ref', 'fingerprint_ref', 'storyboard_ref',
                  'pattern_ref', 'pattern_approval_ref', 'profile_ref', 'rules_ref', 'audit_ref')}})
DECISION = obj({'target_id': HASH, 'target': TARGET,
                'action': {'enum': ['approve', 'reject', 'withdraw']},
                'parent': NULL_REF, 'withdraws': NULL_REF, 'reason': TEXT})
EVIDENCE_CASE = obj({'case_id': ID, 'case_ref': REF, 'case_approval_ref': REF,
                     'fingerprint_ref': REF, 'storyboard_ref': REF})
ELIGIBILITY = obj({'stage': {'enum': STAGES},
                   'purpose': {'const': 'isolated-validation'},
                   'validation_refs': array(REF)})
PATTERN_SOURCES = {
    'candidate_ref': REF, 'comparison_ref': REF, 'research_approval_ref': REF,
    'profile_ref': REF, 'rules_ref': REF, 'supporting_cases': array(EVIDENCE_CASE, 3),
}

SCHEMAS = {
    PROFILE: obj({'schema_version': {'const': PROFILE}, 'profile_id': {'const': 'news'},
        'profile_version': {'const': '1.2'}, 'status': {'const': 'definition_only'},
        'script_contract': obj({'shape': {'const': 'micro_information_beats'},
            'minimum_beats': {'const': 4}, 'maximum_beats': {'const': 8},
            'required_fields': {'const': ['semantic_role','text','visual_anchor','order','duration_guidance','evidence_lineage']}}),
        'storyboard_contract': obj({'shape': {'const': 'micro_beat_sequence'},
            'narration_many_to_many_required': {'const': False}}),
        'ordinary_scope': {'const': 'price_offer_led_only'},
        'export_contract': obj({'writer': {'const': 'export_dynamic_news_xlsx'},
            'template_ref': REF, 'header_row': {'const': 4}, 'first_data_row': {'const': 5},
            'headers': {'const': '标题1..标题N'}, 'minimum_titles': {'const':4},'maximum_titles': {'const':8}}),
        'allowed_purposes': {'const': ['isolated-validation']},
        'automatic_production_promotion': {'const': False}}),
    SNAPSHOT: obj({'schema_version': {'const': SNAPSHOT}, 'targets': array(TARGET, 1)}),
    PREVIEW: obj({'schema_version': {'const': PREVIEW}, 'operation_id': OPERATION,
                  'control_id': OPERATION, 'actor': ACTOR, 'authorization': GRANT,
                  'source_snapshot': REF, 'decisions': array(DECISION, 1), 'created_at': TEXT}),
    APPROVAL: obj({'schema_version': {'const': APPROVAL}, 'operation_id': OPERATION,
                   'control_id': OPERATION, 'actor': ACTOR, 'authorization': GRANT,
                   'source_snapshot': REF, 'preview_ref': REF, 'decisions': array(DECISION, 1),
                   'decided_at': TEXT, 'human_gate': {'const': True}}),
    RULES: obj({'schema_version': {'const': RULES}, 'target_profile': {'const': 'news'},
                'profile_sha256': HASH, 'pattern_scope_required': {'const': True},
                'rule_version': {'const': '1.2'}, 'automatic_approval': {'const': False},
                'ordinary_pattern_ids': {'const': ['pcv1_news_price_offer_led_micro_information']},
                'scope_limitation': {'const': 'price_offer_led_only'},
                'allowed_purposes': {'const': ['isolated-validation']},
                'eligibility_stages': {'const': STAGES},
                'automatic_production_promotion': {'const': False}}),
    CONFIG: obj({'schema_version': {'const': CONFIG}, 'purpose': {'const': 'isolated-validation'},
                 'control_root': TEXT, 'control_id': OPERATION,
                 'reader_version': {'const': READER}, 'profiles': PROFILE_SET}),
    REGISTRY: obj({'schema_version': {'const': REGISTRY}, 'reader_version': {'const': READER},
                   'target_profiles': PROFILE_SET, 'profiles': {'type': 'object'},
                   'eligibility': ELIGIBILITY, 'decision_head_sha256': HASH,
                   'approval_refs': array(REF, 1),
                   'pattern_compatibility_records': array({'type': 'object'}, 1),
                   'authority': obj({'derived_only': {'const': True}})}),
    COVERAGE: obj({'schema_version': {'const': COVERAGE}, 'source_registry_ref': REF,
                   'decision_head_sha256': HASH, 'approval_refs': array(REF, 1),
                   'eligibility': ELIGIBILITY, 'case_profile_compatibility_audit': {'type': 'object'},
                   'authority': obj({'can_change_compatibility': {'const': False}})}),
    RELEASE: obj({'schema_version': {'const': RELEASE}, 'release_id': OPERATION,
                  'purpose': {'const': 'isolated-validation'}, 'profiles': PROFILE_SET,
                  'reader_version': {'const': READER}, 'eligibility': ELIGIBILITY,
                  'source_repo_commit': {'type': 'string', 'pattern': '^[a-f0-9]{40}$'},
                  'source_files': array(SOURCE_REF, 1), 'files': array(REF, 1),
                  'control_id': OPERATION, 'decision_head_sha256': HASH,
                  'registry_ref': REF, 'coverage_ref': REF, 'approval_refs': array(REF, 1),
                  'parent_release': NULL_REF}),
    ACTIVATION: obj({'schema_version': {'const': ACTIVATION}, 'operation_id': OPERATION,
                     'release_ref': REF, 'parent_activation': NULL_REF,
                     'decision_head_sha256': HASH, 'control_id': OPERATION,
                     'purpose': {'const': 'isolated-validation'}, 'eligibility': ELIGIBILITY}),
    BINDING: obj({'schema_version': {'const': BINDING},
                  'target_profile': {'enum': ['mix','news']}, 'reuse_intent': INTENT,
                  'usage_scope': {'enum': [QUALIFICATION, FOUNDER]},
                  'control_id': OPERATION, 'activation_ref': REF, 'release_ref': REF,
                  'decision_head_sha256': HASH, 'approval_refs': array(REF, 1),
                  'target_refs': array(REF, 1), 'profile_ref': REF, 'rules_ref': REF,
                  'coverage_ref': REF, 'pattern_ref': REF, 'pattern_approval_ref': REF,
                  'structural_sources': array(EVIDENCE_CASE, 1)}),
    PATTERN_INTENT: obj({'schema_version': {'const': PATTERN_INTENT}, 'operation_id': OPERATION,
                         'actor': ACTOR, 'authorization': PATTERN_GRANT, 'pattern_id': ID,
                         'decision': {'const': 'approve'}, 'human_gate': {'const': True},
                         'decided_at': TEXT, **PATTERN_SOURCES}),
    PATTERN_RECEIPT: obj({'schema_version': {'const': PATTERN_RECEIPT},
                          'operation_id': OPERATION, 'intent_ref': REF,
                          'actor': ACTOR, 'authorization': PATTERN_GRANT,
                          'pattern_id': ID, 'decision': {'const': 'approve'},
                          'human_gate': {'const': True}, 'decided_at': TEXT,
                          'approved_pattern': REF, **PATTERN_SOURCES}),
    RESEARCH_RECEIPT: obj({'schema_version': {'const': RESEARCH_RECEIPT},
                           'operation_id': OPERATION, 'actor': ACTOR,
                           'authorization': PATTERN_GRANT, 'comparison_ref': REF,
                           'profile_ref': REF, 'rules_ref': REF,
                           'supporting_cases': array(EVIDENCE_CASE, 3),
                           'decision': {'const': 'approve_research_comparison'},
                           'approval_scope': {'const': 'research_comparison_only_not_pattern_approval'},
                           'human_gate': {'const': True}, 'decided_at': TEXT,
                           'native_review': {'type': 'object'}}),
    EVIDENCE: obj({'schema_version': {'const': EVIDENCE},
                   'purpose': {'const': 'isolated-validation'}, 'reuse_intent': INTENT,
                   'origin_runtime': obj({'pipeline_root':TEXT,'configuration_ref':REF}),
                   'eligibility_binding': {'type': 'object'},
                   **{name: REF for name in ('request_ref', 'source_plan_or_native_repurpose_plan_ref',
                       'generated_plan_ref', 'human_review_ref', 'approved_ref', 'export_receipt_ref',
                       'output_ref', 'closure_ref', 'ledger_result_ref')},
                   'validation_results': obj({name: {'const': True} for name in (
                       'source_lineage', 'human_approval', 'xlsx_crc', 'xlsx_exact_content',
                       'receipt_lineage', 'closure_lineage', 'ledger_semantics')}),
                   'owner_version': TEXT}),
}


def validate_contract(value, expected=None):
    version = value.get('schema_version') if isinstance(value, dict) else None
    if version not in SCHEMAS or (expected is not None and version != expected):
        raise CompatibilityError('Unknown or unexpected News Compatibility schema')
    validate(value, SCHEMAS[version])
    if version == EVIDENCE:
        validate_contract(value['eligibility_binding'], BINDING)
    eligibility = value.get('eligibility')
    if eligibility:
        refs = eligibility['validation_refs']
        if eligibility['stage'] == QUALIFICATION and refs:
            raise CompatibilityError('Qualification cannot claim completed native evidence')
        if eligibility['stage'] != QUALIFICATION and len(refs) != 2:
            raise CompatibilityError('Both independent native News paths require exact validation evidence')
    if version in (PATTERN_INTENT, PATTERN_RECEIPT, RESEARCH_RECEIPT):
        cases = value['supporting_cases']
        if len(cases) != 3 or len({case['case_id'] for case in cases}) != 3:
            raise CompatibilityError('News Pattern requires exactly three distinct supporting Cases')
    if version == REGISTRY and sorted(value['profiles']) != value['target_profiles']:
        raise CompatibilityError('Registry profile set mismatch')
    return value


def schema_documents():
    """Detached schema copies for evidence tooling; never a permission writer."""
    return deepcopy(SCHEMAS)
