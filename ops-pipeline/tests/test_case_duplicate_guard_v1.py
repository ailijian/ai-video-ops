from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "case_duplicate_guard_v1.py"

SPEC = importlib.util.spec_from_file_location(
    "case_duplicate_guard_v1",
    SCRIPT,
)
assert SPEC and SPEC.loader

module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_approved_case_media_identity_is_hard_duplicate(
    tmp_path: Path,
):
    pipeline = tmp_path / "ops-pipeline"

    companion = (
        pipeline
        / "data"
        / "case_governance"
        / "cases"
        / "1111111111111111111"
        / "case_source_governance_companion_v1.json"
    )

    write_json(
        companion,
        {
            "case_id": "1111111111111111111",
            "canonical_case_status": "approved",
            "source_provenance": {
                "local_source_exists": False,
                "local_source_sha256": None,
                "recorded_source_sha256": "abc123",
            },
        },
    )

    result = module.find_media_identity_duplicate(
        pipeline,
        current_case_id="2222222222222222222",
        current_attempt_id="attempt-current",
        media_sha256="abc123",
    )

    assert result is not None
    assert result["kind"] == "media_identity"
    assert result["existing_case_id"] == "1111111111111111111"
    assert result["existing_status"] == "approved"
    assert result["matched_sha256"] == "abc123"


def test_approved_case_duplicate_guard_accepts_historical_local_sha_field(
    tmp_path: Path,
):
    pipeline = tmp_path / "ops-pipeline"
    companion = (
        pipeline
        / "data"
        / "case_governance"
        / "cases"
        / "1111111111111111111"
        / "case_source_governance_companion_v1.json"
    )
    write_json(
        companion,
        {
            "case_id": "1111111111111111111",
            "canonical_case_status": "approved",
            "source_provenance": {"local_source_sha256": "legacy123"},
        },
    )

    result = module.find_media_identity_duplicate(
        pipeline,
        current_case_id="2222222222222222222",
        current_attempt_id="attempt-current",
        media_sha256="legacy123",
    )

    assert result is not None
    assert result["existing_case_id"] == "1111111111111111111"


def test_same_case_lineage_is_not_media_duplicate(
    tmp_path: Path,
):
    pipeline = tmp_path / "ops-pipeline"

    acquisition = (
        pipeline
        / "data"
        / "case_analysis_attempts"
        / "1111111111111111111"
        / "attempt-old"
        / "source_acquisition_v1.json"
    )

    write_json(
        acquisition,
        {
            "case_id": "1111111111111111111",
            "source_video_sha256": "abc123",
        },
    )

    write_json(
        acquisition.parent / "case_analysis_attempt_v1.json",
        {
            "case_id": "1111111111111111111",
            "attempt_id": "attempt-old",
            "status": "awaiting_review",
        },
    )

    result = module.find_media_identity_duplicate(
        pipeline,
        current_case_id="1111111111111111111",
        current_attempt_id="attempt-new",
        media_sha256="abc123",
    )

    assert result is None


def test_review_ready_different_case_is_hard_duplicate(
    tmp_path: Path,
):
    pipeline = tmp_path / "ops-pipeline"

    acquisition = (
        pipeline
        / "data"
        / "case_analysis_attempts"
        / "1111111111111111111"
        / "attempt-existing"
        / "source_acquisition_v1.json"
    )

    write_json(
        acquisition,
        {
            "case_id": "1111111111111111111",
            "source_video_sha256": "abc123",
        },
    )

    write_json(
        acquisition.parent / "case_analysis_attempt_v1.json",
        {
            "case_id": "1111111111111111111",
            "attempt_id": "attempt-existing",
            "status": "awaiting_review",
        },
    )

    result = module.find_media_identity_duplicate(
        pipeline,
        current_case_id="2222222222222222222",
        current_attempt_id="attempt-current",
        media_sha256="abc123",
    )

    assert result is not None
    assert result["existing_status"] == "awaiting_review"


def test_rejected_attempt_does_not_create_cross_source_hard_block(
    tmp_path: Path,
):
    pipeline = tmp_path / "ops-pipeline"

    acquisition = (
        pipeline
        / "data"
        / "case_analysis_attempts"
        / "1111111111111111111"
        / "attempt-rejected"
        / "source_acquisition_v1.json"
    )

    write_json(
        acquisition,
        {
            "case_id": "1111111111111111111",
            "source_video_sha256": "abc123",
        },
    )

    write_json(
        acquisition.parent / "case_analysis_attempt_v1.json",
        {
            "case_id": "1111111111111111111",
            "attempt_id": "attempt-rejected",
            "status": "rejected",
        },
    )

    result = module.find_media_identity_duplicate(
        pipeline,
        current_case_id="2222222222222222222",
        current_attempt_id="attempt-current",
        media_sha256="abc123",
    )

    assert result is None
