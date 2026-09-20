"""Fixture-only checks that submission intent never grants profile compatibility."""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from production_profile_v1 import audit_case_profile_compatibility_v1


def write_json(path: Path, value: dict) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_operator_news_hint_does_not_override_observed_mix_or_approve_compatibility(
    tmp_path: Path,
):
    case_id = "7999999999999999991"
    case_path = tmp_path / "case_v1.json"
    case_sha = write_json(
        case_path,
        {
            "case_id": case_id,
            "operator_profile_hint": "news",
            "lifecycle": {"status": "approved", "approved": True},
        },
    )
    receipt_path = tmp_path / "approval_receipt.json"
    write_json(
        receipt_path,
        {
            "decision": "approved",
            "human_gate": True,
            "case_sha256_after_approval": case_sha,
        },
    )
    fingerprint_path = tmp_path / "case_fingerprint_v1.json"
    write_json(
        fingerprint_path,
        {
            "case_id": case_id,
            "source_case": {"sha256": case_sha},
            "narration_features": {"speech_to_video_ratio": 0.8},
            "visual_shot_features": {"shot_count": 10},
            "audio_visual_features": {
                "narration_and_shots_are_separate_tracks": True,
                "shot_to_narration_cardinality": "many_to_many",
                "text_relation_counts": {"independent": 0},
            },
        },
    )
    storyboard_path = tmp_path / "reverse_storyboard_v1.json"
    write_json(storyboard_path, {"case_id": case_id})

    result = audit_case_profile_compatibility_v1(
        case_path=case_path,
        case_approval_receipt_path=receipt_path,
        fingerprint_path=fingerprint_path,
        storyboard_path=storyboard_path,
        legacy_mix_case_ids=set(),
    )
    assert result["operator_profile_hint"] == "news"
    assert result["observed_source_profile"] == "mix"
    assert result["approved_compatible_generation_profiles"] == []
    assert result["authority"]["operator_hint_used_as_eligibility"] is False
