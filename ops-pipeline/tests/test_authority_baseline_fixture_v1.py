from __future__ import annotations

import hashlib
import json
from pathlib import Path

from authority_test_support import FIXTURE_ROOT


def read_json(relative: str) -> dict:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_is_explicitly_synthetic_and_manifest_is_complete() -> None:
    manifest = read_json("fixture_manifest_v1.json")
    assert manifest["synthetic"] is True
    assert manifest["contains_production_truth"] is False
    assert all(value.startswith("fixture_") for value in manifest["identities"].values() if not value.isdigit())

    recorded = {item["path"]: item["sha256"] for item in manifest["files"]}
    actual = {
        path.relative_to(FIXTURE_ROOT).as_posix(): sha256(path)
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file() and path.name not in {"README.md", "fixture_manifest_v1.json"}
    }
    assert actual == recorded


def test_personas_require_explicit_human_approval_and_preserve_scope() -> None:
    business = read_json(
        "data/personas/fixture_business_001/revision_0001/persona_v1.json"
    )
    speaker = read_json(
        "data/personas/fixture_speaker_001/revision_0001/persona_v1.json"
    )
    assert business["persona_scope"] == "business"
    assert speaker["persona_scope"] == "speaker"
    assert business["approval"]["human_gate"] is True
    assert speaker["approval"]["human_gate"] is True
    assert speaker["business_persona_ref"]["sha256"] == sha256(
        FIXTURE_ROOT
        / "data/personas/fixture_business_001/revision_0001/persona_v1.json"
    )


def test_case_approval_does_not_grant_production_media_rights() -> None:
    case = read_json("data/cases/7999999999999999901/case_v1.json")
    receipt = read_json("data/cases/7999999999999999901/approval_receipt.json")
    companion = read_json(
        "data/case_governance/cases/7999999999999999901/case_source_governance_companion_v1.json"
    )
    assert case["lifecycle"]["status"] == "approved"
    assert receipt["decision"] == "approved"
    assert receipt["human_gate"] is True
    assert companion["media_reuse_rights"] == "not_established"
    assert companion["production_footage_pool_eligible"] is False
    assert companion["recorded_source_media_sha256"]
    assert companion["local_source_exists"] is False


def test_content_ledger_preserves_cross_profile_novelty_and_no_padding() -> None:
    ledger = read_json(
        "data/content_ledgers/fixture_business_001/content_ledger_v1.json"
    )
    presentation = ledger["extensions"]["presentation_history_v1"]["entries"][0]
    capacity = read_json(
        "data/content_plans/fixture_mix_request_001/post_export_remaining_capacity_v1.json"
    )
    assert ledger["validation"]["append_only"] is True
    assert presentation["reuse_intent"] == "cross_profile_repurpose"
    assert presentation["semantic_novelty"] is False
    assert presentation["new_semantic_content_count_delta"] == 0
    assert capacity["post_export_remaining_capacity"] == 7
    assert capacity["padding"] is False


def test_approved_batch_and_export_closure_preserve_human_gate() -> None:
    batch_path = (
        FIXTURE_ROOT
        / "data/generation_batches/fixture_mix_request_001/revisions/revision_0001/approved_generation_batch_v1.json"
    )
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    receipt = read_json(
        "data/generation_batches/fixture_mix_request_001/revisions/revision_0001/generation_batch_approval_receipt.json"
    )
    closure = read_json(
        "data/export_closures/fixture_mix_request_001/export_closure_v1.json"
    )
    assert receipt["approved_batch"]["sha256"] == sha256(batch_path)
    assert batch["human_gate"] is True
    assert all(item["case_media_used"] is False for item in batch["items"])
    assert closure["human_gate_preserved"] is True
    assert closure["regeneration_performed"] is False


def test_pattern_snapshot_binds_candidate_case_and_unvalidated_effectiveness() -> None:
    pattern = read_json("data/patterns/approved/fixture_pattern_001/pattern_v1.json")
    candidate_path = (
        FIXTURE_ROOT
        / "data/patterns/candidates/fixture_pattern_candidate_001/pattern_candidate_v1.json"
    )
    case_path = FIXTURE_ROOT / "data/cases/7999999999999999901/case_v1.json"
    assert pattern["approval"]["human_gate"] is True
    assert pattern["effectiveness"] == {
        "performance_data_used": False,
        "status": "unvalidated",
    }
    assert pattern["lineage"]["candidate"]["sha256"] == sha256(candidate_path)
    assert pattern["lineage"]["case_refs"][0]["sha256"] == sha256(case_path)


def test_creative_coverage_keeps_scene_contrast_pending() -> None:
    coverage = read_json(
        "data/creative_coverage/revisions/news_production_mvp_final_validation_update_v1.json"
    )
    validation = coverage["pattern_production_validation"]
    assert validation["pcv1_news_price_offer_led_micro_information"]["status"] == "passed"
    assert validation["pcv1_news_scene_contrast"]["status"] == "pending"


def test_operational_hold_is_explicit_and_read_only_fixture_evidence() -> None:
    control_path = (
        FIXTURE_ROOT
        / "data/operations/fixture_business_001/operational_controls_v1.json"
    )
    before = sha256(control_path)
    control = json.loads(control_path.read_text(encoding="utf-8"))
    assert control["operational_hold"]["active"] is True
    assert control["operational_hold"]["release_requires"] == "explicit_operator_release"
    assert sha256(control_path) == before
