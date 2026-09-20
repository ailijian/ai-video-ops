from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.canonical_gateway import (
    CanonicalOperationError,
    _source_dimensions,
    approve_case_candidate,
    get_case_detail,
)
from app.config import Settings


CASE_ID = "7999999999999999901"
ATTEMPT_ID = "case-7999999999999999901-fresh-approval"
REVIEWER = "13800000000"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def approval_fixture(tmp_path: Path) -> tuple[Settings, Path, Path]:
    project = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repo"
    pipeline = repo / "ops-pipeline"
    shutil.copytree(project / "ops-pipeline" / "scripts", pipeline / "scripts")
    settings = Settings(
        repo_root=repo,
        console_root=repo / "internal-console",
        pipeline_root=pipeline,
        database_path=tmp_path / "console.sqlite3",
        python_executable=sys.executable,
        pipeline_python_executable=sys.executable,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
    )
    source_case = (
        project
        / "ops-pipeline"
        / "tests"
        / "fixtures"
        / "authority_baseline_v1"
        / "data"
        / "cases"
        / CASE_ID
        / "case_v1.json"
    )
    case = json.loads(source_case.read_text(encoding="utf-8"))
    case["lifecycle"].update(
        {
            "status": "review_required",
            "approved": False,
            "approved_at": None,
            "approved_by": None,
        }
    )
    case.pop("approval", None)
    case.pop("source_rights_gate", None)
    case["analysis_lineage"] = {
        "operation": "case_analysis_v1",
        "attempt_id": ATTEMPT_ID,
        "previous_attempt_id": None,
        "reanalysis": False,
    }
    case.setdefault("quality", {}).update(
        {
            "human_review_required": True,
            "human_review_completed": False,
            "verified_proof_count": 0,
        }
    )
    case.setdefault("validation", {}).update(
        {
            "passed": True,
            "human_approval_completed": False,
            "auto_approved": False,
        }
    )
    case["visual_evidence"] = {"coverage_label": "candidate_complete"}
    case["privacy_gate"] = {
        "library_safe": True,
        "unresolved_sensitive_items": 0,
        "derived_artifact_scan_passed": True,
        "privacy_policy_version": "privacy-policy-v1.0",
        "policy_version": "privacy-policy-v1.0",
    }
    case["storyboard"]["video_understanding"]["verified_proofs"] = []
    case["storyboard"]["video_understanding"]["claims"] = []
    case["storyboard"]["claims_semantics"] = (
        "candidate_unverified_unless_supported_by_verified_proofs"
    )
    case["pattern_state"] = {"pattern_mining_performed": False}

    attempt_root = (
        pipeline / "data" / "case_analysis_attempts" / CASE_ID / ATTEMPT_ID
    )
    missing_video = attempt_root / "transient-source-already-cleaned.mp4"
    metadata = attempt_root / "source_metadata_v1.json"
    acquisition = attempt_root / "source_acquisition_v1.json"
    storyboard = attempt_root / "reverse_storyboard_v1.json"
    privacy = attempt_root / "privacy_projection_v1.json"
    recorded_sha = hashlib.sha256(b"source-media-was-cleaned").hexdigest()
    source_url = f"https://www.douyin.com/video/{CASE_ID}"
    write_json(
        metadata,
        {"aweme_id": CASE_ID, "desc": "用于审批测试的公开来源", "video": {"width": 1080, "height": 1920}},
    )
    write_json(
        acquisition,
        {
            "case_id": CASE_ID,
            "stable_video_id": CASE_ID,
            "source_url": source_url,
            "platform": "douyin",
            "video": str(missing_video),
            "metadata": str(metadata),
            "source_video_sha256": recorded_sha,
        },
    )
    write_json(storyboard, {"case_id": CASE_ID, "synthetic_fixture": True})
    write_json(
        privacy,
        {
            "case_id": CASE_ID,
            "library_safe": True,
            "privacy_policy_version": "privacy-policy-v1.0",
        },
    )
    case["privacy_gate"]["source_projection_sha256"] = sha256(privacy)
    case["identity"].update({"platform": "douyin", "source_url": source_url})
    case["source_evidence"]["video"] = {
        "path": str(missing_video),
        "sha256": recorded_sha,
    }
    case["source_evidence"]["metadata"] = {"path": str(metadata)}
    case["source_provenance"] = {
        "platform": "douyin",
        "canonical_source_url": source_url,
        "stable_video_id": CASE_ID,
        "recorded_source_media_sha256": recorded_sha,
        "source_acquisition_ref": {"path": str(acquisition), "sha256": sha256(acquisition)},
        "source_metadata_ref": {"path": str(metadata), "sha256": sha256(metadata)},
    }
    case.setdefault("source_artifacts", {}).update(
        {
            "video": str(missing_video),
            "source_acquisition_v1": str(acquisition),
            "source_metadata_v1": str(metadata),
            "storyboard_v1": str(storyboard),
            "privacy_projection_v1": str(privacy),
        }
    )
    candidate = attempt_root / "candidate_cases" / CASE_ID / "case_v1.json"
    write_json(candidate, case)
    state_path = attempt_root / "case_analysis_attempt_v1.json"
    write_json(
        state_path,
        {
            "schema_version": "case-analysis-attempt-v1.0",
            "case_id": CASE_ID,
            "attempt_id": ATTEMPT_ID,
            "status": "awaiting_review",
            "artifacts": {"case_candidate_v1": str(candidate)},
        },
    )
    return settings, candidate, state_path


def approve(settings: Settings):
    return approve_case_candidate(
        settings,
        CASE_ID,
        reviewer=REVIEWER,
        note="已对照公开来源完成测试审核。",
    )


def test_fresh_production_approval_is_complete_without_legacy_policy(tmp_path: Path):
    settings, candidate, state_path = approval_fixture(tmp_path)
    assert not (settings.pipeline_root / "data" / "case_governance" / "case_source_governance_policy_v1.json").exists()
    assert not Path(json.loads(candidate.read_text(encoding="utf-8"))["source_evidence"]["video"]["path"]).exists()

    detail = approve(settings)

    canonical = settings.pipeline_root / "data" / "cases" / CASE_ID / "case_v1.json"
    receipt = canonical.parent / "approval_receipt.json"
    companion_path = settings.pipeline_root / "data" / "case_governance" / "cases" / CASE_ID / "case_source_governance_companion_v1.json"
    approved = json.loads(canonical.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))
    companion = json.loads(companion_path.read_text(encoding="utf-8"))
    assert detail["status"] == "approved"
    assert approved["lifecycle"]["approved"] is True
    assert approved["approval"]["reviewer"] == REVIEWER
    assert receipt.is_file()
    assert state["status"] == "approved"
    assert companion["governance_policy_ref"]["applicable"] is False
    assert companion["media_reuse_rights"] == "not_established"
    assert companion["production_footage_pool_eligible"] is False
    assert companion["source_provenance"]["local_source_exists"] is False


def test_legacy_case_without_policy_fails_closed(tmp_path: Path):
    settings, candidate, state_path = approval_fixture(tmp_path)
    value = json.loads(candidate.read_text(encoding="utf-8"))
    value["source_rights_gate"] = {"status": "legacy_review_required"}
    write_json(candidate, value)

    with pytest.raises(CanonicalOperationError) as error:
        approve(settings)

    assert error.value.code == "CASE_SOURCE_GOVERNANCE_BLOCKED"
    assert not (settings.pipeline_root / "data" / "cases" / CASE_ID).exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "awaiting_review"


def test_invalid_source_lineage_fails_without_partial_canonical(tmp_path: Path):
    settings, candidate, state_path = approval_fixture(tmp_path)
    value = json.loads(candidate.read_text(encoding="utf-8"))
    value["source_provenance"]["stable_video_id"] = "7000000000000000000"
    write_json(candidate, value)

    with pytest.raises(CanonicalOperationError) as error:
        approve(settings)

    assert error.value.code == "CASE_APPROVAL_BLOCKED"
    assert not (settings.pipeline_root / "data" / "cases" / CASE_ID).exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "awaiting_review"


def test_companion_build_failure_does_not_publish_approved_case(tmp_path: Path, monkeypatch):
    settings, _, state_path = approval_fixture(tmp_path)

    def fail_companion(*args, **kwargs):
        raise CanonicalOperationError("CASE_SOURCE_GOVERNANCE_BLOCKED", "fixture failure", "retry")

    monkeypatch.setattr("app.canonical_gateway._governance_companion", fail_companion)
    with pytest.raises(CanonicalOperationError):
        approve(settings)

    assert not (settings.pipeline_root / "data" / "cases" / CASE_ID).exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "awaiting_review"


def test_mandatory_validation_failure_does_not_publish_approved_case(tmp_path: Path, monkeypatch):
    settings, _, state_path = approval_fixture(tmp_path)

    def fail_validation(*args, **kwargs):
        raise CanonicalOperationError("CASE_APPROVAL_BLOCKED", "fixture failure", "retry")

    monkeypatch.setattr("app.canonical_gateway._validate_approved_case_artifacts", fail_validation)
    with pytest.raises(CanonicalOperationError):
        approve(settings)

    assert not (settings.pipeline_root / "data" / "cases" / CASE_ID).exists()
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "awaiting_review"


def test_same_attempt_partial_approval_reconciles_without_second_approval(tmp_path: Path):
    settings, _, state_path = approval_fixture(tmp_path)
    approve(settings)
    canonical = settings.pipeline_root / "data" / "cases" / CASE_ID / "case_v1.json"
    receipt = canonical.parent / "approval_receipt.json"
    companion = settings.pipeline_root / "data" / "case_governance" / "cases" / CASE_ID / "case_source_governance_companion_v1.json"
    before_case = canonical.read_bytes()
    before_receipt = receipt.read_bytes()
    companion.unlink()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "awaiting_review"
    write_json(state_path, state)

    detail = approve(settings)

    recovered = json.loads(state_path.read_text(encoding="utf-8"))
    assert detail["status"] == "approved"
    assert canonical.read_bytes() == before_case
    assert receipt.read_bytes() == before_receipt
    assert companion.is_file()
    assert recovered["approval_reconciliation"]["second_human_approval_performed"] is False
    assert recovered["approval_reconciliation"]["original_reviewer"] == REVIEWER


def test_partial_approval_from_different_attempt_fails_closed(tmp_path: Path):
    settings, _, state_path = approval_fixture(tmp_path)
    approve(settings)
    canonical = settings.pipeline_root / "data" / "cases" / CASE_ID / "case_v1.json"
    companion = settings.pipeline_root / "data" / "case_governance" / "cases" / CASE_ID / "case_source_governance_companion_v1.json"
    companion.unlink()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "awaiting_review"
    state["attempt_id"] = "case-7999999999999999901-different"
    write_json(state_path, state)

    with pytest.raises(CanonicalOperationError) as error:
        approve(settings)

    assert error.value.code == "CASE_APPROVAL_RECOVERY_REQUIRED"
    assert json.loads(canonical.read_text(encoding="utf-8"))["lifecycle"]["approved"] is True
    assert not companion.exists()


def test_second_normal_approval_is_immutable(tmp_path: Path):
    settings, _, _ = approval_fixture(tmp_path)
    approve(settings)

    with pytest.raises(CanonicalOperationError) as error:
        approve(settings)

    assert error.value.code == "CASE_ALREADY_APPROVED"


def test_review_media_projects_portrait_dimensions_and_keeps_official_source(tmp_path: Path):
    settings, _, _ = approval_fixture(tmp_path)
    detail = get_case_detail(settings, CASE_ID)
    assert detail["review_media"]["source_width"] == 1080
    assert detail["review_media"]["source_height"] == 1920
    assert detail["review_media"]["aspect_ratio"] == pytest.approx(9 / 16)
    assert detail["review_media"]["local_available"] is False
    assert detail["review_media"]["remote_embed_url"] == f"https://open.douyin.com/player/video?vid={CASE_ID}"
    assert detail["review_media"]["source_url"] == f"https://www.douyin.com/video/{CASE_ID}"
    assert _source_dimensions({}) == (None, None)


def test_case_submit_state_projection_runs_in_node():
    script = Path(__file__).parent / "js" / "case-submit-state.test.mjs"
    result = subprocess.run(
        ["node", str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_review_player_uses_compact_orientation_layout_without_source_ratio_geometry():
    static = Path(__file__).resolve().parents[1] / "static" / "assets"
    css = (static / "styles.css").read_text(encoding="utf-8")
    component = (static / "case-components.js").read_text(encoding="utf-8")
    assert "aspect-ratio: var(--source-aspect-ratio" not in css
    assert "--source-aspect-ratio" not in component
    assert ".review-media-player.portrait { width: min(100%, 300px, calc(60dvh * .5625)); aspect-ratio: 9 / 16; }" in css
    assert ".review-media-shell.portrait { grid-template-columns: minmax(0, 300px) minmax(0, 1fr); }" in css
    assert ".review-media-player.landscape { width: min(100%, 640px); max-height: 52dvh; aspect-ratio: 16 / 9; }" in css
    assert "review-media-shell ${orientation}" in component
    assert 'review-media-player ${orientation}${isRemotePlayer ? " remote" : ""}' in component
    assert "${reviewSurfaceNote}" in component
    assert "当前通过抖音原视频进行审核。" in component
    assert "reviewMedia.remote_embed_url" in component
    assert 'scrolling="no"' in component
    assert "allowfullscreen" in component
    assert "在抖音打开原视频" in component


def test_official_player_resizes_the_whole_frame_including_bottom_controls():
    script = Path(__file__).parent / "js" / "case-media-preview.test.mjs"
    result = subprocess.run(
        ["node", str(script)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
