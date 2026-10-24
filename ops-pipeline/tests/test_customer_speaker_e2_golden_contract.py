"""Layer A preset semantics: does not establish real model extraction quality."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from test_customer_constraints_e2_v1 import analysis, review, contract, review_request, forbid_network

ROOT = Path(__file__).resolve().parents[2] / "internal-console/tests/fixtures/customer_speaker_e2"
PRESET = json.loads((ROOT / "synthetic_outputs.json").read_text(encoding="utf-8"))
MATERIAL = (ROOT / "GOLDEN_INPUT_FICTIONAL.md").read_text(encoding="utf-8")


def seed(root, data=None):
    result = analysis.analyze_customer_onboarding(request={"business_id": "golden_fictional_business", "intake_id": "intake_0001",
        "customer_name": "澄禾小馆（完全虚构）", "industry": "", "materials": MATERIAL}, pipeline_root=root,
        extractor=lambda _: copy.deepcopy(data or PRESET["business"]),
        speaker_discovery_extractor=lambda _: copy.deepcopy(PRESET["discovery"]))
    return result, analysis.read_json(Path(result["artifacts"]["fact_candidates_v1"]))


def human(result, candidates):
    req = review_request(result, candidates)
    for decision, item in zip(req["constraint_decisions"], candidates["derived_authority_constraints"]):
        if item["constraint_type"] == "unverified_claim":
            decision["decision"] = "exclude"
        elif item["constraint_type"] == "identity_conflict":
            decision.update(decision="resolve", note="虚构人审明确不同品牌不能继承荣誉", resolution_quote="本品牌不等于示例合作餐厅，不自动继承其荣誉或评价。")
    return req


def test_golden_all_capabilities_source_quotes_human_restrictions_and_persona_input(tmp_path):
    result, candidates = seed(tmp_path)
    assert {v["target_field"] for v in candidates["fact_candidates"]} == {
        "public_display_name", "industry", "primary_products_or_services", "core_audience", "process_facts"}
    assert {v["constraint_type"] for v in candidates["derived_authority_constraints"]} == contract.CONSTRAINT_TYPES
    assert len(candidates["source_coverage"]) == 4
    assert contract.policy(contract.collect(tmp_path, result["business_id"]))["blockers"]
    req = human(result, candidates)
    reviewed = review.review_customer_facts(request=req, pipeline_root=tmp_path)
    assert reviewed["status"] == "completed_persona_review_required"
    persona = analysis.read_json(Path(reviewed["artifacts"]["business_persona_v1"]))
    assert persona["lifecycle"]["approved"] is False
    assert "城市餐饮奖" not in json.dumps(persona["facts"], ensure_ascii=False)
    assert not contract.policy(contract.collect(tmp_path, result["business_id"]))["blockers"]
    discovery = analysis.read_json(Path(result["artifacts"]["speaker_discovery_candidates_v1"]))
    assert discovery["speaker_candidates"][0]["speaker_type_hint"] == "owner_founder"
    assert not list(tmp_path.rglob("speaker_draft_v1.json"))


@pytest.mark.parametrize("topic,blocker", [("primary_service", "business_identity"), ("core_audience", "customer_use_context"), ("service_process", "production_bearing_facts")])
def test_missing_candidate_does_not_lower_business_readiness(tmp_path, topic, blocker):
    data = copy.deepcopy(PRESET["business"])
    data["facts"] = [v for v in data["facts"] if v["topic"] != topic]
    result, candidates = seed(tmp_path, data)
    reviewed = review.review_customer_facts(request=human(result, candidates), pipeline_root=tmp_path)
    assert reviewed["status"] == "completed_persona_blocked"
    assert blocker in reviewed["business_persona_blockers"]
    assert not list(tmp_path.rglob("approval_receipt.json"))


def test_unreviewed_important_restrictions_fail_closed_before_persona(tmp_path):
    result, candidates = seed(tmp_path)
    req = human(result, candidates)
    req["constraint_decisions"] = []
    with pytest.raises(RuntimeError, match="explicit typed"):
        review.review_customer_facts(request=req, pipeline_root=tmp_path)
    assert not list(tmp_path.rglob("persona_v1.json"))
