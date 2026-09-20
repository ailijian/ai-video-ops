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
    case_id: str = "1",
    status: str = "awaiting_review",
    updated_at: datetime | None = None,
) -> dict[str, Path]:
    attempt_id = "a"
    pipeline = tmp_path / "p"
    downloader = tmp_path / "d"
    attempt = pipeline / "data" / "case_analysis_attempts" / case_id / attempt_id
    source_dir = downloader / "Downloaded" / "a"
    source_dir.mkdir(parents=True)
    video = source_dir / f"clip_{case_id}.mp4"
    music = source_dir / f"clip_{case_id}_music.mp3"
    cover = source_dir / f"clip_{case_id}_cover.jpg"
    downloader_data = source_dir / f"clip_{case_id}_data.json"
    metadata = attempt / "source_metadata_v1.json"
    video.write_bytes(b"source-video")
    music.write_bytes(b"source-music")
    cover.write_bytes(b"source-cover")
    write_json(downloader_data, {"aweme_id": case_id, "retained": True})
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

    write_json(
        transcript,
        {
            "source_file": str(video),
            "model": "large-v3",
            "duration": 12.0,
            "discarded_segments": [],
            "segments": [
                {
                    "start": 0.0,
                    "end": 1.0,
                    "text": "structured",
                    "words": [{"start": 0.0, "end": 1.0, "word": "structured"}],
                }
            ],
        },
    )
    write_json(
        audio,
        {
            "case_id": case_id,
            "duration_seconds": 12.0,
            "speech_evidence_status": "detected",
            "transcript_raw": "structured",
            "segments": [{"segment_id": "A001"}],
            "words": [{"word_id": "W00001"}],
            "validation": {"passed": True},
        },
    )
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
            "speech_evidence_status": "detected",
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
        "downloader_data": downloader_data,
        "original_frame": original_frame,
        "proxy_frame": proxy_frame,
        "metadata": metadata,
        "acquisition": attempt / "source_acquisition_v1.json",
        "transcript": transcript,
        "audio": audio,
        "narration": narration,
        "candidate": candidate,
        "visual": visual,
    }


def make_speechless(paths: dict[str, Path]) -> None:
    transcript = module.read_json(paths["transcript"])
    transcript["segments"] = []
    transcript["discarded_segments"] = []
    write_json(paths["transcript"], transcript)
    write_json(
        paths["audio"],
        {
            "case_id": "1",
            "duration_seconds": 12.0,
            "speech_evidence_status": "not_detected",
            "transcript_raw": "",
            "segments": [],
            "words": [],
            "validation": {"passed": True},
        },
    )
    state_path = paths["attempt"] / "case_analysis_attempt_v1.json"
    state = module.read_json(state_path)
    state["speech_evidence_status"] = "not_detected"
    write_json(state_path, state)


def test_qiyun_transient_media_deleted_after_awaiting_review(tmp_path: Path):
    paths = build_attempt(tmp_path)
    provider_video = paths["attempt"] / "source_media" / "source.mp4"
    provider_video.parent.mkdir(parents=True)
    provider_video.write_bytes(b"provider-source-video")
    acquisition = module.read_json(paths["acquisition"])
    acquisition.update({
        "mode": "qiyun_resolved_media", "video": str(provider_video),
        "music": None, "cover": None,
        "source_video_sha256": hashlib.sha256(provider_video.read_bytes()).hexdigest(),
    })
    write_json(paths["acquisition"], acquisition)
    receipt = module.cleanup_successful_attempt(paths["attempt"], paths["downloader"])
    assert not provider_video.exists()
    assert paths["video"].exists()  # unrelated downloader media is not a cleanup target
    assert paths["acquisition"].exists()
    assert receipt["source_url_retained"] is True
    assert receipt["source_media_sha256_retained"] is True


def test_failed_qiyun_partial_media_retained_then_expired(tmp_path: Path):
    now = datetime.now(timezone.utc)
    paths = build_attempt(tmp_path, status="failed", updated_at=now - timedelta(hours=1))
    partial = paths["attempt"] / "source_media" / "source.mp4.part"
    partial.parent.mkdir(parents=True)
    partial.write_bytes(b"partial-download")
    module.run_storage_maintenance(paths["pipeline"], paths["downloader"], now=now)
    assert partial.exists()
    state_path = paths["attempt"] / "case_analysis_attempt_v1.json"
    state = module.read_json(state_path)
    state["updated_at"] = module.iso_utc(now - timedelta(hours=25))
    write_json(state_path, state)
    module.run_storage_maintenance(paths["pipeline"], paths["downloader"], now=now)
    assert not partial.exists()


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


def test_speechless_awaiting_review_cleanup_uses_canonical_speech_evidence(
    tmp_path: Path,
):
    paths = build_attempt(tmp_path)
    make_speechless(paths)

    receipt = module.cleanup_successful_attempt(
        paths["attempt"], paths["downloader"]
    )
    state = module.read_json(paths["attempt"] / "case_analysis_attempt_v1.json")
    stored_receipt = module.read_json(
        paths["attempt"] / "storage_cleanup_receipt_v1.json"
    )

    for name in ("video", "music", "cover", "original_frame", "proxy_frame"):
        assert not paths[name].exists()
    for name in (
        "downloader_data",
        "metadata",
        "acquisition",
        "transcript",
        "audio",
        "narration",
        "candidate",
        "visual",
    ):
        assert paths[name].is_file()
    assert state["status"] == "awaiting_review"
    assert state["artifacts"]["narration_review_v1"] == str(paths["narration"])
    assert receipt == stored_receipt
    assert receipt["cleanup_status"] == "completed"
    assert receipt["structured_evidence_retained"] is True
    assert set(receipt["deleted_categories"]) == {
        "original_frames",
        "qwen_proxy_frames",
        "source_cover_thumbnail",
        "source_music",
        "source_video",
    }


def test_uncertain_empty_transcription_is_not_cleanup_eligible(tmp_path: Path):
    paths = build_attempt(tmp_path)
    make_speechless(paths)
    raw = module.read_json(paths["transcript"])
    raw["discarded_segments"] = [{"reason": "implausible_speech_rate"}]
    write_json(paths["transcript"], raw)

    with pytest.raises(module.StorageCleanupError) as error:
        module.cleanup_successful_attempt(paths["attempt"], paths["downloader"])

    assert error.value.code == "CLEANUP_EVIDENCE_NOT_DURABLE"
    assert paths["video"].is_file()


@pytest.mark.parametrize(
    "malformation",
    [
        "missing-source-file",
        "missing-model",
        "missing-duration",
        "invalid-segments",
        "invalid-json",
    ],
)
def test_malformed_empty_transcription_is_not_cleanup_eligible(
    tmp_path: Path,
    malformation: str,
):
    paths = build_attempt(tmp_path)
    make_speechless(paths)
    raw = module.read_json(paths["transcript"])
    if malformation == "missing-source-file":
        raw.pop("source_file")
    elif malformation == "missing-model":
        raw.pop("model")
    elif malformation == "missing-duration":
        raw.pop("duration")
    elif malformation == "invalid-segments":
        raw["segments"] = {}
    else:
        paths["transcript"].write_text("{", encoding="utf-8")
    if malformation != "invalid-json":
        write_json(paths["transcript"], raw)

    with pytest.raises(module.StorageCleanupError) as error:
        module.cleanup_successful_attempt(paths["attempt"], paths["downloader"])

    assert error.value.code == "CLEANUP_EVIDENCE_NOT_DURABLE"
    assert paths["video"].is_file()


def test_raw_and_audio_speech_semantics_mismatch_fails_closed(tmp_path: Path):
    paths = build_attempt(tmp_path)
    make_speechless(paths)
    audio = module.read_json(paths["audio"])
    audio.update(
        {
            "speech_evidence_status": "detected",
            "transcript_raw": "structured",
            "segments": [{"segment_id": "A001"}],
            "words": [{"word_id": "W00001"}],
        }
    )
    write_json(paths["audio"], audio)

    with pytest.raises(module.StorageCleanupError) as error:
        module.cleanup_successful_attempt(paths["attempt"], paths["downloader"])

    assert error.value.code == "CLEANUP_EVIDENCE_NOT_DURABLE"
    assert paths["video"].is_file()


def test_narration_authority_is_resolved_from_attempt_state_and_retained(
    tmp_path: Path,
):
    paths = build_attempt(tmp_path)
    authoritative_narration = paths["attempt"] / "durable" / "narration.json"
    authoritative_narration.parent.mkdir(parents=True)
    paths["narration"].replace(authoritative_narration)
    state_path = paths["attempt"] / "case_analysis_attempt_v1.json"
    state = module.read_json(state_path)
    state["artifacts"]["narration_review_v1"] = str(authoritative_narration)
    write_json(state_path, state)

    receipt = module.cleanup_successful_attempt(
        paths["attempt"], paths["downloader"]
    )

    assert receipt["cleanup_status"] == "completed"
    assert authoritative_narration.is_file()


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
