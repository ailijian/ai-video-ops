from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "storage_retention_v1.py"
if str(SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("storage_retention_v1", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_attempt(
    tmp_path: Path,
    *,
    status: str = "awaiting_review",
    updated_at: datetime | None = None,
) -> dict[str, Path]:
    case_id = "1"
    attempt_id = "a"
    pipeline = tmp_path / "p"
    downloader = tmp_path / "d"
    attempt = pipeline / "data" / "case_analysis_attempts" / case_id / attempt_id
    source_dir = downloader / "Downloaded" / "a"
    source_dir.mkdir(parents=True)
    video = source_dir / f"clip_{case_id}.mp4"
    music = source_dir / f"clip_{case_id}_music.mp3"
    cover = source_dir / f"clip_{case_id}_cover.jpg"
    metadata = attempt / "source_metadata_v1.json"
    video.write_bytes(b"source-video")
    music.write_bytes(b"source-music")
    cover.write_bytes(b"source-cover")
    write_json(metadata, {"aweme_id": case_id, "desc": "retained metadata"})
    source_sha = hashlib.sha256(video.read_bytes()).hexdigest()

    transcript = attempt / "evidence" / "transcription" / "transcript_segments.json"
    audio = attempt / "evidence" / "audio_v1" / "audio_word_timeline_v1.json"
    visual_root = attempt / "evidence" / "visual" / case_id
    manifest = visual_root / "visual_evidence_manifest.json"
    original_frame = visual_root / "frames" / "f.jpg"
    visual = visual_root / "visual_v1" / "visual_timeline_v1.json"
    proxy_frame = (
        visual_root
        / "visual_v1"
        / "proxies"
        / "edge_960"
        / "frames"
        / original_frame.name
    )
    privacy = attempt / "evidence" / "privacy" / "privacy_projection_v1.json"
    narration = attempt / "evidence" / "narration" / "narration_review_v1.json"
    shots = attempt / "evidence" / "shots" / "shot_boundaries_v1_1.json"
    storyboard = attempt / "evidence" / "storyboard" / "reverse_storyboard_v1.json"
    candidate = attempt / "candidate_cases" / case_id / "case_v1.json"

    write_json(transcript, {"segments": [{"text": "structured"}]})
    write_json(audio, {"case_id": case_id, "validation": {"passed": True}})
    write_json(
        manifest,
        {"case_id": case_id, "frames": [{"filename": original_frame.name}]},
    )
    original_frame.parent.mkdir(parents=True)
    original_frame.write_bytes(b"original-frame")
    write_json(
        visual,
        {"case_id": case_id, "coverage": {"coverage_label": "candidate_complete"}},
    )
    proxy_frame.parent.mkdir(parents=True)
    proxy_frame.write_bytes(b"proxy-frame")
    write_json(
        privacy,
        {"case_id": case_id, "privacy_policy_version": "privacy-policy-v1.0"},
    )
    write_json(
        narration,
        {
            "case_id": case_id,
            "validation": {"passed": True},
            "manual_review": {"required": False},
        },
    )
    write_json(shots, {"case_id": case_id, "validation": {"passed": True}})
    write_json(storyboard, {"case_id": case_id, "validation": {"passed": True}})
    write_json(
        candidate,
        {
            "case_id": case_id,
            "lifecycle": {"status": "review_required"},
            "validation": {"passed": True},
        },
    )
    write_json(
        attempt / "source_acquisition_v1.json",
        {
            "case_id": case_id,
            "stable_video_id": case_id,
            "source_url": f"https://www.douyin.com/video/{case_id}",
            "platform": "douyin",
            "video": str(video),
            "music": str(music),
            "cover": str(cover),
            "metadata": str(metadata),
            "source_video_sha256": source_sha,
        },
    )
    write_json(
        attempt / "case_analysis_attempt_v1.json",
        {
            "case_id": case_id,
            "attempt_id": attempt_id,
            "status": status,
            "updated_at": module.iso_utc(updated_at),
            "source": {
                "canonical_url": f"https://www.douyin.com/video/{case_id}",
                "platform": "douyin",
            },
            "artifacts": {
                "transcript_segments": str(transcript),
                "audio_v1": str(audio),
                "visual_manifest": str(manifest),
                "visual_v1": str(visual),
                "privacy_projection_v1": str(privacy),
                "narration_review_v1": str(narration),
                "shot_boundaries_v1": str(shots),
                "reverse_storyboard_v1": str(storyboard),
                "case_candidate_v1": str(candidate),
            },
        },
    )
    return {
        "pipeline": pipeline,
        "downloader": downloader,
        "attempt": attempt,
        "video": video,
        "music": music,
        "cover": cover,
        "original_frame": original_frame,
        "proxy_frame": proxy_frame,
        "metadata": metadata,
        "candidate": candidate,
        "visual": visual,
    }


@pytest.mark.parametrize(
    "target_name",
    ["video", "music", "cover", "original_frame", "proxy_frame"],
    ids=[
        "source-video",
        "source-music",
        "source-cover",
        "original-frames",
        "qwen-proxies",
    ],
)
def test_successful_awaiting_review_deletes_transient_media(
    tmp_path: Path,
    target_name: str,
):
    paths = build_attempt(tmp_path)

    receipt = module.cleanup_successful_attempt(
        paths["attempt"], paths["downloader"]
    )

    assert not paths[target_name].exists()
    assert receipt["cleanup_status"] == "completed"
    assert receipt["source_url_retained"] is True
    assert receipt["source_media_sha256_retained"] is True
    assert receipt["structured_evidence_retained"] is True
    assert paths["metadata"].is_file()
    assert paths["candidate"].is_file()
    assert paths["visual"].is_file()


def test_failed_attempt_younger_than_24_hours_keeps_transient_media(tmp_path: Path):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    paths = build_attempt(tmp_path, status="failed", updated_at=now - timedelta(hours=23))

    assert module.run_storage_maintenance(
        paths["pipeline"], paths["downloader"], now=now
    ) == []
    assert paths["video"].is_file()
    assert paths["original_frame"].is_file()


def test_failed_attempt_older_than_24_hours_deletes_transient_media(tmp_path: Path):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    paths = build_attempt(tmp_path, status="failed", updated_at=now - timedelta(hours=25))

    results = module.run_storage_maintenance(
        paths["pipeline"], paths["downloader"], now=now
    )

    assert len(results) == 1
    assert results[0]["trigger"] == "failed_retention_expired_24h"
    assert not paths["video"].exists()
    assert not paths["original_frame"].exists()


def test_rejected_attempt_is_cleaned_immediately(tmp_path: Path):
    paths = build_attempt(tmp_path, status="rejected")

    receipt = module.cleanup_rejected_attempt(paths["attempt"], paths["downloader"])

    assert receipt["trigger"] == "human_reject"
    assert not paths["video"].exists()
    assert not paths["proxy_frame"].exists()


@pytest.mark.parametrize("status", ["queued", "running"])
def test_active_attempt_is_never_cleaned(tmp_path: Path, status: str):
    paths = build_attempt(tmp_path, status=status)

    with pytest.raises(module.StorageCleanupError) as error:
        module.cleanup_attempt_transient_media(
            paths["attempt"],
            paths["downloader"],
            trigger="test",
            require_success_evidence=False,
        )

    assert error.value.code == "CLEANUP_ACTIVE_ATTEMPT"
    assert paths["video"].is_file()


def test_cleanup_failure_keeps_business_success_and_marks_retry_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    paths = build_attempt(tmp_path)
    original_unlink = Path.unlink

    def fail_video_unlink(path: Path, *args, **kwargs):
        if path == paths["video"]:
            raise PermissionError("test file is busy")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_video_unlink)
    receipt = module.cleanup_successful_attempt(
        paths["attempt"], paths["downloader"]
    )
    state = module.read_json(paths["attempt"] / "case_analysis_attempt_v1.json")

    assert state["status"] == "awaiting_review"
    assert state["cleanup_status"] == "retry_required"
    assert receipt["cleanup_status"] == "retry_required"
    assert paths["video"].is_file()
    assert (paths["attempt"] / "storage_cleanup_receipt_v1.json").is_file()


def test_cleanup_exception_records_retry_receipt_without_changing_business_status(
    tmp_path: Path,
):
    paths = build_attempt(tmp_path)

    module.mark_cleanup_retry_required(
        paths["attempt"],
        trigger="analysis_awaiting_review",
        error="simulated cleanup exception",
    )

    state = module.read_json(paths["attempt"] / "case_analysis_attempt_v1.json")
    receipt = module.read_json(
        paths["attempt"] / "storage_cleanup_receipt_v1.json"
    )
    assert state["status"] == "awaiting_review"
    assert state["cleanup_status"] == "retry_required"
    assert receipt["cleanup_status"] == "retry_required"
    assert receipt["source_url_retained"] is True
    assert receipt["source_media_sha256_retained"] is True
    assert receipt["structured_evidence_retained"] is True
