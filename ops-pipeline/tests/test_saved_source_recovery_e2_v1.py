"""E2-B: repair omissions without rewriting immutable source or Human decisions."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from test_customer_constraints_e2_v1 import (analysis, review, contract, request, output,
    review_request, STAMP, forbid_network, seed, approve_persona)


def historical(root):
    original = request()
    directory = root / "data/customer_intakes" / original["business_id"] / original["intake_id"]
    directory.mkdir(parents=True)
    (directory / "customer_onboarding_request_v1.json").write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    summary = analysis.analyze_customer_onboarding(request=original, pipeline_root=root,
        extractor=lambda _: {"facts": [], "model": "synthetic-historical-omission"},
        speaker_discovery_extractor=lambda _: {"speaker_candidates": []}, created_at=STAMP)
    candidates = analysis.read_json(Path(summary["artifacts"]["fact_candidates_v1"]))
    result = review.review_customer_facts(request=review_request(summary, candidates), pipeline_root=root, reviewed_at=STAMP)
    assert result["status"] == "completed_persona_blocked"
    return original, directory


def recovery_request(original, source, targets=None):
    targets = sorted(targets or ["business_identity", "customer_use_context", "production_bearing_facts", "industry"])
    raw_path = source / "customer_intake_v1.json"
    privacy_path = source / "customer_intake_privacy_projection_v1.json"
    raw = analysis.read_json(raw_path)
    identity = {"source_intake_id": source.name, "raw_sha256": contract.file_sha(raw_path),
        "projection_sha256": contract.file_sha(privacy_path), "targets": targets, "execution_identity": "fictional-recovery-one"}
    return {"business_id": original["business_id"], "intake_id": "intake_0002", "intake_type": "gap_supplement",
        "customer_name": original["customer_name"], "industry": "", "reviewed_context": {"public_display_name": original["customer_name"]},
        "gap_answers": [{"target_gap": "additional_materials", "raw_answer": original["materials"]}],
        "source_lineage": {"operation": "saved_source_recovery", "source_intake_id": source.name,
            "source_raw_sha256": identity["raw_sha256"], "source_projection_sha256": identity["projection_sha256"],
            "source_raw_answers_sha256": raw["raw_input_contract"]["raw_answers_sha256"], "recovery_targets": targets,
            "execution_identity": identity["execution_identity"], "recovery_identity": analysis.sha256_json(identity),
            "already_reviewed_fields": ["public_display_name"], "customer_submitted_new_materials": False}}


def test_omission_recovery_only_new_review_and_immutable_history(tmp_path):
    original, source = historical(tmp_path)
    protected = {p: contract.file_sha(p) for p in source.glob("*.json")}
    req = recovery_request(original, source)
    calls = []
    def extractor(privacy):
        calls.append(privacy)
        assert privacy["recovery_targets"] == req["source_lineage"]["recovery_targets"]
        assert "历史资料的遗漏恢复" in analysis.build_prompt(privacy)
        return output()
    def no_speaker(_):
        raise AssertionError("Recovery must not run Speaker discovery")
    result = analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path,
        extractor=extractor, speaker_discovery_extractor=no_speaker, created_at=STAMP)
    candidate = analysis.read_json(Path(result["artifacts"]["fact_candidates_v1"]))
    assert "public_display_name" not in {v["target_field"] for v in candidate["fact_candidates"]}
    assert all(v["candidate_state"] == "requires_review" for v in candidate["fact_candidates"])
    reviewed = review.review_customer_facts(request=review_request(result, candidate), pipeline_root=tmp_path, reviewed_at=STAMP)
    assert reviewed["status"] == "completed_persona_review_required"
    assert reviewed["authority"]["persona_approved"] is False
    persona = analysis.read_json(Path(reviewed["artifacts"]["business_persona_v1"]))
    assert persona["facts"]["public_display_name"]["value"] == original["customer_name"]
    assert all(contract.file_sha(p) == sha for p, sha in protected.items())
    assert len(calls) == 1
    replay = analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path,
        extractor=lambda _: pytest.fail("Completed extraction must not rerun"), speaker_discovery_extractor=no_speaker)
    assert replay["intake_id"] == result["intake_id"]
    assert not list(tmp_path.rglob("speaker_draft_v1.json"))


def test_targets_filter_other_fields_and_failure_reuses_raw_checkpoint(tmp_path):
    original, source = historical(tmp_path)
    req = recovery_request(original, source, ["business_identity"])
    def failed(_):
        raise RuntimeError("synthetic failure; no provider")
    with pytest.raises(RuntimeError, match="synthetic failure"):
        analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path, extractor=failed)
    target = source.parent / "intake_0002"
    checkpoints = {p: contract.file_sha(p) for p in target.glob("*.json")}
    result = analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path, extractor=lambda _: output())
    candidate = analysis.read_json(Path(result["artifacts"]["fact_candidates_v1"]))
    assert {v["target_field"] for v in candidate["fact_candidates"]} == {"primary_products_or_services"}
    assert all(contract.file_sha(p) == sha for p, sha in checkpoints.items())


def test_no_new_facts_does_not_create_empty_r2_or_change_approved_r1(tmp_path):
    summary, candidate = seed(tmp_path)
    original = request()
    source = Path(summary["artifacts"]["customer_intake_v1"]).parent
    (source / "customer_onboarding_request_v1.json").write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    reviewed = review.review_customer_facts(request=review_request(summary, candidate), pipeline_root=tmp_path, reviewed_at=STAMP)
    path = Path(reviewed["artifacts"]["business_persona_v1"])
    approve_persona(path, "fictional_authenticated_operator", "Explicit offline human", STAMP)
    protected = {p: contract.file_sha(p) for p in source.glob("*.json")}
    req = recovery_request(original, source, ["industry"])
    recovered = analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path, extractor=lambda _: output())
    candidates = analysis.read_json(Path(recovered["artifacts"]["fact_candidates_v1"]))
    result = review.review_customer_facts(request=review_request(recovered, candidates), pipeline_root=tmp_path, reviewed_at=STAMP)
    assert result["status"] == "completed_no_new_facts"
    assert not (source.parent / "intake_0002/business_persona_v1.json").exists()
    assert all(contract.file_sha(p) == sha for p, sha in protected.items())


@pytest.mark.parametrize("field", ["source_raw_sha256", "source_projection_sha256", "source_raw_answers_sha256", "recovery_identity"])
def test_source_lineage_mismatch_stops_before_model_or_new_artifact(tmp_path, field):
    original, source = historical(tmp_path)
    req = recovery_request(original, source)
    req["source_lineage"][field] = "0" * 64
    with pytest.raises(analysis.CustomerOnboardingError) as exc:
        analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path, extractor=lambda _: pytest.fail("No model"))
    assert exc.value.code == "RECOVERY_SOURCE_SHA_MISMATCH"
    assert not (source.parent / "intake_0002").exists()


def test_source_coverage_is_exact_observation_not_fact_approval(tmp_path):
    extracted = {"facts": [], "source_coverage": [{"capability_group": "business_identity", "evidence_quote": "提供地方菜堂食"}]}
    result = analysis.analyze_customer_onboarding(request=request(), pipeline_root=tmp_path, extractor=lambda _: extracted)
    artifact = analysis.read_json(Path(result["artifacts"]["fact_candidates_v1"]))
    assert artifact["source_coverage"][0]["observation_is_human_approval"] is False
    assert not any(v["target_field"] == "primary_products_or_services" for v in artifact["fact_candidates"])
    bad = copy.deepcopy(extracted); bad["source_coverage"][0]["evidence_quote"] = "虚构但原文不存在"
    with pytest.raises(analysis.CustomerOnboardingError) as exc:
        analysis.analyze_customer_onboarding(request=request("intake_0002"), pipeline_root=tmp_path, extractor=lambda _: bad)
    assert exc.value.code == "SOURCE_COVERAGE_INVALID"


def test_tampered_saved_request_cannot_be_misrepresented_as_historical_raw_source(tmp_path):
    original, source = historical(tmp_path)
    path = source / "customer_onboarding_request_v1.json"
    original["materials"] += "伪造的新主张，原Raw未提供。"
    path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    req = recovery_request(original, source)
    with pytest.raises(analysis.CustomerOnboardingError) as exc:
        analysis.analyze_customer_onboarding(request=req, pipeline_root=tmp_path, extractor=lambda _: pytest.fail("No model"))
    assert exc.value.code == "RECOVERY_SOURCE_SHA_MISMATCH"
    assert not (source.parent / "intake_0002").exists()
