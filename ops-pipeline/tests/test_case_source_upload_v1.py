from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from case_source_upload_v1 import inspect_video, read_upload, sha256_file, upload_directory, RECEIPT
from case_analysis_v1 import Orchestrator, CaseAnalysisError
from storage_retention_v1 import _transient_targets, cleanup_rejected_attempt

CASE_ID = "7999999999999999811"
URL = f"https://www.douyin.com/video/{CASE_ID}"
UPLOAD = "a" * 32


def make_upload(pipeline: Path):
    directory = upload_directory(pipeline, UPLOAD)
    directory.mkdir(parents=True)
    video = directory / f"{CASE_ID}.mp4"
    video.write_bytes(b"test-media")
    receipt = {
        "schema_version": "case-source-upload-v1.0", "upload_id": UPLOAD, "case_id": CASE_ID,
        "source_url": URL, "filename": video.name, "size_bytes": video.stat().st_size,
        "source_video_sha256": sha256_file(video), "uploaded_by_user_id": 7,
        "uploaded_by_phone": "13800000000", "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "rights_confirmed": True, "source_match_confirmed": True, "binding_method": "operator_attestation",
        "platform_original_verified": False, "media_rights_granted": False,
        "production_footage_pool_eligible": False,
    }
    receipt_path = directory / RECEIPT
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return video, receipt_path


def orchestrator(pipeline, receipt):
    return Orchestrator(pipeline_root=pipeline, repo_root=pipeline.parent,
                        downloader_root=pipeline.parent / "absent-downloader", source_url=URL,
                        attempt_id="upload_attempt_0001", profile=None, operator_profile_hint="news",
                        industry="待分类", reanalyze=False, source_upload_id=UPLOAD,
                        source_upload_receipt_sha256=sha256_file(receipt))


def test_upload_acquisition_no_downloader_no_models_and_retention(tmp_path, monkeypatch):
    pipeline = tmp_path / "pipeline"
    video, receipt = make_upload(pipeline)
    op = orchestrator(pipeline, receipt)
    monkeypatch.setattr(op, "run_command", lambda *args: pytest.fail("No model or downloader may run"))
    acquisition = op.acquire()
    assert acquisition["source_video_sha256"] == sha256_file(video)
    assert acquisition["mode"] == "operator_uploaded_file"
    assert acquisition["media_rights_granted"] is False
    assert acquisition["production_footage_pool_eligible"] is False
    assert json.loads(Path(acquisition["metadata"]).read_text())["uploaded_by_user_id"] == 7
    targets, unsafe = _transient_targets(op.attempt_root, op.downloader_root)
    assert not unsafe
    assert ("source_video", video) in targets
    op.state["status"] = "rejected"
    op.save()
    cleanup_rejected_attempt(op.attempt_root, op.downloader_root)
    assert not video.exists()
    assert receipt.exists()
    assert Path(acquisition["metadata"]).exists()


@pytest.mark.parametrize("tamper", ["missing", "media", "receipt"])
def test_invalid_upload_never_falls_back_to_downloader(tmp_path, monkeypatch, tamper):
    pipeline = tmp_path / "pipeline"
    video, receipt = make_upload(pipeline)
    op = orchestrator(pipeline, receipt)
    if tamper == "missing":
        video.unlink()
    elif tamper == "media":
        video.write_bytes(b"changed")
    else:
        receipt.write_text("{}")
    monkeypatch.setattr(op, "run_command", lambda *args: pytest.fail("Must fail closed"))
    with pytest.raises(CaseAnalysisError, match="上传文件"):
        op.acquire()


@pytest.mark.parametrize("identifier", ["../outside", "", "A" * 32])
def test_upload_reference_cannot_escape_root(tmp_path, identifier):
    with pytest.raises(ValueError):
        upload_directory(tmp_path, identifier)


def test_uploaded_media_success_cleanup_keeps_recorded_sha_and_receipt(tmp_path):
    from test_storage_retention_v1 import build_attempt, write_json
    from storage_retention_v1 import cleanup_successful_attempt

    paths = build_attempt(tmp_path, case_id=CASE_ID)
    video, receipt = make_upload(paths["pipeline"])
    acquisition = json.loads(paths["acquisition"].read_text())
    acquisition.update(mode="operator_uploaded_file", upload_id=UPLOAD, video=str(video),
                       upload_receipt_sha256=sha256_file(receipt), source_video_sha256=sha256_file(video))
    write_json(paths["acquisition"], acquisition)
    paths["metadata"].write_bytes(receipt.read_bytes())
    before = sha256_file(paths["metadata"])
    result = cleanup_successful_attempt(paths["attempt"], paths["downloader"])
    assert result["cleanup_status"] == "completed"
    assert result["source_media_sha256_retained"] is True
    assert not video.exists()
    assert sha256_file(paths["metadata"]) == before
    assert receipt.exists()


def test_real_cpu_media_probe_and_spoof_rejection(tmp_path):
    import av
    import numpy as np

    video = tmp_path / "fixture.mp4"
    with av.open(str(video), "w") as container:
        stream = container.add_stream("mpeg4", rate=24)
        stream.width = stream.height = 64
        stream.pix_fmt = "yuv420p"
        audio = container.add_stream("aac", rate=48000)
        audio.layout = "stereo"
        for index in range(24):
            frame = av.VideoFrame.from_ndarray(np.full((64, 64, 3), index * 10, dtype=np.uint8), format="rgb24")
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
            sound = av.AudioFrame.from_ndarray(np.zeros((2, 2000), dtype=np.float32), format="fltp", layout="stereo")
            sound.sample_rate = 48000
            sound.pts = index * 2000
            for packet in audio.encode(sound):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        for packet in audio.encode():
            container.mux(packet)
    result = inspect_video(video)
    assert result["width"] == 64
    assert result["audio_present"] is True
    assert 0.9 <= result["duration_seconds"] <= 1.1
    video.write_bytes(b"#EXTM3U\nhttp://127.0.0.1/private\n")
    with pytest.raises(ValueError, match="containers"):
        inspect_video(video)
