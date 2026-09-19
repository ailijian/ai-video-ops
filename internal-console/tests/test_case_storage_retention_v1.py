from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.canonical_gateway import (
    _governance_companion,
    get_case_detail,
    record_case_review_decision,
)
from app.config import Settings
from app.task_service import CaseTaskRunner


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def retention_settings(tmp_path: Path) -> Settings:
    repo = tmp_path / "repo"
    return Settings(
        repo_root=repo,
        console_root=repo / "internal-console",
        pipeline_root=repo / "ops-pipeline",
        database_path=tmp_path / "console.sqlite3",
        python_executable=sys.executable,
        pipeline_python_executable=sys.executable,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
    )


def candidate_fixture(settings: Settings) -> tuple[str, Path, Path]:
    case_id = "7682442957798161531"
    attempt_id = "attempt-storage-review"
    attempt_root = (
        settings.pipeline_root
        / "data"
        / "case_analysis_attempts"
        / case_id
        / attempt_id
    )
    candidate = attempt_root / "candidate_cases" / case_id / "case_v1.json"
    write_json(
        candidate,
        {
            "case_id": case_id,
            "lifecycle": {"status": "review_required", "approved": False},
            "identity": {
                "platform": "douyin",
                "source_url": f"https://www.douyin.com/video/{case_id}",
                "analysis_profile": "mix",
                "industry": "local_service",
                "duration_seconds": 30,
            },
            "source_evidence": {
                "video": {"path": str(tmp_path_missing(settings) / "source.mp4")}
            },
            "storyboard": {
                "shots": [],
                "video_understanding": {"content_goal_candidate": "测试案例结构"},
            },
            "audio_evidence": {"transcript_safe_semantic": "测试口播"},
        },
    )
    state_path = attempt_root / "case_analysis_attempt_v1.json"
    write_json(
        state_path,
        {
            "case_id": case_id,
            "attempt_id": attempt_id,
            "status": "awaiting_review",
            "artifacts": {"case_candidate_v1": str(candidate)},
        },
    )
    return case_id, candidate, state_path


def tmp_path_missing(settings: Settings) -> Path:
    return settings.repo_root / "missing-transient-media"


def test_case_review_uses_douyin_embed_after_local_media_cleanup(tmp_path: Path):
    settings = retention_settings(tmp_path)
    case_id, _, _ = candidate_fixture(settings)

    detail = get_case_detail(settings, case_id)

    assert detail["review_media"]["local_available"] is False
    assert detail["review_media"]["local_url"] is None
    assert detail["review_media"]["remote_embed_url"] == (
        f"https://open.douyin.com/player/video?vid={case_id}"
    )
    assert detail["review_media"]["source_url"] == (
        f"https://www.douyin.com/video/{case_id}"
    )
    assert detail["review_media"]["remote_player_is_authority"] is False
    assert detail["review_media"]["source_width"] is None
    assert detail["review_media"]["source_height"] is None
    assert detail["review_media"]["aspect_ratio"] == 9 / 16


def test_case_review_uses_local_video_when_transient_media_is_available(tmp_path: Path):
    settings = retention_settings(tmp_path)
    case_id, candidate, _ = candidate_fixture(settings)
    local_video = (
        settings.repo_root
        / "douyin-downloader"
        / "Downloaded"
        / "author"
        / f"clip_{case_id}.mp4"
    )
    local_video.parent.mkdir(parents=True)
    local_video.write_bytes(b"available-review-media")
    case = json.loads(candidate.read_text(encoding="utf-8"))
    case["source_evidence"]["video"]["path"] = str(local_video)
    write_json(candidate, case)

    detail = get_case_detail(settings, case_id)

    assert detail["review_media"]["local_available"] is True
    assert detail["review_media"]["local_url"] == f"/api/cases/{case_id}/media"


def test_governance_traceability_does_not_require_local_video(tmp_path: Path):
    settings = retention_settings(tmp_path)
    case_id = "7682442957798161531"
    case_path = settings.pipeline_root / "data" / "cases" / case_id / "case_v1.json"
    recorded_sha = "a" * 64
    write_json(
        case_path,
        {
            "case_id": case_id,
            "identity": {
                "platform": "douyin",
                "source_url": f"https://www.douyin.com/video/{case_id}",
            },
            "source_evidence": {
                "video": {
                    "path": str(tmp_path / "cleaned.mp4"),
                    "sha256": recorded_sha,
                }
            },
            "approval": {
                "source_traceability": {
                    "stable_video_id": case_id,
                    "recorded_source_sha256": recorded_sha,
                    "acquisition_lineage_valid": True,
                    "source_acquisition_path": str(tmp_path / "source_acquisition_v1.json"),
                    "source_metadata_path": str(tmp_path / "source_metadata_v1.json"),
                    "source_metadata_valid": True,
                }
            },
        },
    )
    write_json(case_path.parent / "approval_receipt.json", {"decision": "approved"})
    policy = (
        settings.pipeline_root
        / "data"
        / "case_governance"
        / "case_source_governance_policy_v1.json"
    )
    write_json(policy, {"status": "approved_frozen"})

    companion = _governance_companion(settings, case_path)

    provenance = companion["source_provenance"]
    assert provenance["traceable"] is True
    assert provenance["local_source_exists"] is False
    assert provenance["recorded_source_sha256"] == recorded_sha
    assert provenance["acquisition_lineage_valid"] is True
    assert companion["media_reuse_rights"] == "not_established"
    assert companion["production_footage_pool_eligible"] is False


def test_human_reject_requests_immediate_cleanup(
    tmp_path: Path,
    monkeypatch,
):
    settings = retention_settings(tmp_path)
    case_id, _, state_path = candidate_fixture(settings)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "{}", "")

    monkeypatch.setattr("app.canonical_gateway.subprocess.run", fake_run)

    receipt = record_case_review_decision(
        settings,
        case_id,
        reviewer="13800000000",
        decision="reject",
        reason="测试不收录",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert receipt["decision"] == "reject"
    assert state["status"] == "rejected"
    assert len(commands) == 1
    assert "storage_retention_v1.py" in " ".join(commands[0])
    assert commands[0][-1] == "human_reject"


def test_authority_backup_excludes_case_transient_pixels_and_media():
    script = Path(__file__).resolve().parents[1] / "scripts" / "backup_local_node_v1.py"
    spec = importlib.util.spec_from_file_location("backup_retention_contract", script)
    assert spec and spec.loader
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)

    assert backup._excluded(
        Path("case_analysis_attempts/case/attempt/evidence/visual/case/frames/frame.jpg")
    )
    assert backup._excluded(
        Path("case_analysis_attempts/case/attempt/evidence/visual/case/visual_v1/proxies/edge_960/frames/frame.jpg")
    )
    assert backup._excluded(Path("case_analysis_attempts/case/attempt/source.mp4"))
    assert not backup._excluded(
        Path("case_analysis_attempts/case/attempt/source_acquisition_v1.json")
    )
    assert not backup._excluded(
        Path("case_analysis_attempts/case/attempt/evidence/visual/case/visual_v1/visual_timeline_v1.json")
    )


def test_case_review_frontend_exposes_remote_source_review_surface():
    static_root = Path(__file__).resolve().parents[1] / "static"
    component = (static_root / "assets" / "case-components.js").read_text(
        encoding="utf-8"
    )
    assert "https://open.douyin.com/player/video?vid=" not in component
    assert "reviewMedia.remote_embed_url" in component
    assert "在抖音打开原视频" in component
    assert "当前通过抖音原视频进行审核。" in component
    assert "批准不会改变原视频素材使用权。" in component


def test_case_runner_invokes_storage_maintenance_at_hourly_cadence(
    tmp_path: Path,
    monkeypatch,
):
    settings = retention_settings(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    ticks = iter([100.0, 101.0, 3701.0])
    monkeypatch.setattr("app.task_service.subprocess.run", fake_run)
    monkeypatch.setattr("app.task_service.time.monotonic", lambda: next(ticks))
    runner = CaseTaskRunner(settings)
    runner._run_storage_maintenance_if_due()
    runner._run_storage_maintenance_if_due()
    runner._run_storage_maintenance_if_due()
    runner.close()

    assert len(commands) == 2
    assert all("--maintenance" in command for command in commands)
