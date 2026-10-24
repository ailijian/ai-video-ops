"""Regression: a native opaque material SHA must not become apparent phone PII."""
import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from generate_mix_scripts_v1 import render_generation_prompt
from privacy_projection_v1 import assert_safe_for_external_model, detect_sensitive_spans

OPAQUE = 'process_facts::8fb89ac0795719935b0c'


def prompt(ref=OPAQUE, fact='先核对忌口，再按单配菜，制作后标记餐盒'):
    safe = {'persona': {'facts': {'process_facts': fact}}, 'speaker': None, 'request': {},
            'approved_pattern': {}, 'case_structures': {'case': {}}}
    concept = {key: '已核实的处理流程' for key in ('audience_need', 'content_job', 'primary_topic', 'central_claim')}
    concept.update(primary_fact_refs=['process_facts'], semantic_signature={'central_claim_key': 'dietary_process'},
        generation_constraints={'must_express_selected_material_centers': [{'fact_atom_ref': ref,
            'original_known_fact': fact, 'normalized_meaning': fact}],
            'must_not_absorb_other_selected_material_centers': [{'fact_atom_ref': ref}]})
    slot = {'slot_id':'SLOT_001', 'case_id':'case', 'concept_ref':'CONCEPT_001', 'selected_concept':concept}
    before=copy.deepcopy(slot)
    text=render_generation_prompt(safe,[slot],[])
    assert slot==before
    return text


def test_exact_observed_hash_aliases_only_model_copy_and_retains_material_fact():
    assert any(x['confidence']=='high' for x in detect_sensitive_spans(OPAQUE))
    text=prompt()
    assert OPAQUE not in text and text.count('MATERIAL_CENTER_001')==2
    assert '先核对忌口，再按单配菜，制作后标记餐盒' in text
    assert_safe_for_external_model(text)


def test_real_phone_in_facts_is_still_blocked():
    with pytest.raises(RuntimeError,match='PII'):
        assert_safe_for_external_model(prompt(fact='请联系13812345678'))


def test_untrusted_phone_shaped_ref_is_not_an_opaque_native_hash():
    with pytest.raises(RuntimeError,match='PII'):
        assert_safe_for_external_model(prompt(ref='13812345678'))
