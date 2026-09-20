from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "case_analysis_v1.py"
SCRIPTS_DIR = SCRIPT.parent

# case_analysis_v1.py is also an executable script and imports sibling
# canonical script modules. When this test loads it through importlib instead
# of running it as a script, Python does not automatically add scripts/ to
# sys.path, so mirror the real script execution environment explicitly.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location("case_analysis_v1", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

APPROVE_SPEC = importlib.util.spec_from_file_location(
    "approve_case_v1",
    SCRIPTS_DIR / "approve_case_v1.py",
)
assert APPROVE_SPEC and APPROVE_SPEC.loader
approve_module = importlib.util.module_from_spec(APPROVE_SPEC)
APPROVE_SPEC.loader.exec_module(approve_module)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    pipeline = repo / "ops-pipeline"
    downloader = repo / "douyin-downloader"
    pipeline.mkdir(parents=True)
    downloader.mkdir(parents=True)
    return repo, pipeline, downloader


def test_whisper_model_defaults_to_large_v3(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("AIVO_WHISPER_MODEL", raising=False)

    assert module.resolve_whisper_model() == "large-v3"


def test_whisper_model_accepts_model_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AIVO_WHISPER_MODEL", "large-v3")

    assert module.resolve_whisper_model() == "large-v3"


def test_whisper_model_accepts_exact_absolute_local_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    model_dir = tmp_path / "faster-whisper-large-v3"
    model_dir.mkdir()
    configured = str(model_dir)
    monkeypatch.setenv("AIVO_WHISPER_MODEL", configured)

    assert module.resolve_whisper_model() == configured


def test_whisper_model_rejects_missing_absolute_local_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    missing_model_dir = (tmp_path / "missing-whisper-model").resolve()
    monkeypatch.setenv("AIVO_WHISPER_MODEL", str(missing_model_dir))

    with pytest.raises(module.CaseAnalysisError) as error:
        module.resolve_whisper_model()

    assert error.value.code == "WHISPER_MODEL_PATH_INVALID"


def test_stable_source_identity_accepts_full_douyin_url_only():
    case_id, canonical = module.stable_source_identity(
        "https://www.douyin.com/video/7682442957798161531?share=1"
    )
    assert case_id == "7682442957798161531"
    assert canonical == "https://www.douyin.com/video/7682442957798161531"
    with pytest.raises(module.CaseAnalysisError) as error:
        module.stable_source_identity("https://v.douyin.com/short-code/")
    assert error.value.code == "UNSUPPORTED_SOURCE"


def test_duplicate_canonical_case_fails_closed(tmp_path: Path):
    repo, pipeline, downloader = roots(tmp_path)
    canonical = pipeline / "data" / "cases" / "7682442957798161531" / "case_v1.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_text("{}", encoding="utf-8")
    with pytest.raises(module.CaseAnalysisError) as error:
        module.Orchestrator(
            pipeline_root=pipeline,
            repo_root=repo,
            downloader_root=downloader,
            source_url="https://www.douyin.com/video/7682442957798161531",
            attempt_id="attempt_0001",
            profile="mix",
            industry="待分类",
            reanalyze=False,
        )
    assert error.value.code == "DUPLICATE_CASE"


@pytest.mark.parametrize("hint", ["mix", "news", "hybrid", "uncertain"])
def test_operator_hint_persists_in_attempt_without_legacy_analysis_profile(tmp_path: Path, hint: str):
    repo, pipeline, downloader = roots(tmp_path)
    operation = module.Orchestrator(
        pipeline_root=pipeline, repo_root=repo, downloader_root=downloader,
        source_url="https://www.douyin.com/video/7682442957798161531",
        attempt_id="attempt_hint_001", profile=None, operator_profile_hint=hint,
        industry="待分类", reanalyze=False,
    )
    assert operation.state["request"]["operator_profile_hint"] == hint
    assert "profile" not in operation.state["request"]
    assert not (operation.attempt_root / "candidate_cases").exists()


def test_reanalysis_lineage_never_overwrites_approved_case(tmp_path: Path):
    repo, pipeline, downloader = roots(tmp_path)
    canonical = pipeline / "data" / "cases" / "7682442957798161531" / "case_v1.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_text(
        json.dumps(
            {"case_id": "7682442957798161531", "lifecycle": {"status": "approved"}}
        ),
        encoding="utf-8",
    )
    before = sha256(canonical)
    operation = module.Orchestrator(
        pipeline_root=pipeline,
        repo_root=repo,
        downloader_root=downloader,
        source_url="https://www.douyin.com/video/7682442957798161531",
        attempt_id="attempt_0002",
        profile="mix",
        industry="待分类",
        reanalyze=True,
    )
    assert operation.state["lineage"]["canonical_case_existed_at_start"] is True
    assert operation.state["lineage"]["canonical_case_sha256_at_start"] == before
    assert sha256(canonical) == before
    assert not (operation.attempt_root / "candidate_cases").exists()


def test_attempt_progress_is_durable_and_resumable(tmp_path: Path):
    repo, pipeline, downloader = roots(tmp_path)
    kwargs = dict(
        pipeline_root=pipeline,
        repo_root=repo,
        downloader_root=downloader,
        source_url="https://www.douyin.com/video/7682442957798161531",
        attempt_id="attempt_0003",
        profile="mix",
        industry="待分类",
        reanalyze=False,
    )
    first = module.Orchestrator(**kwargs)
    first.start_stage("acquire")
    first.complete_stage("acquire")
    second = module.Orchestrator(**kwargs)
    assert second.state["progress"] == 12
    assert second.stage_record("acquire")["status"] == "completed"


def test_source_acquisition_preserves_privacy_and_media_rights_boundary(tmp_path: Path):
    repo, pipeline, downloader = roots(tmp_path)
    case_id = "7682442957798161531"
    source_dir = downloader / "Downloaded" / "author" / "post" / case_id
    source_dir.mkdir(parents=True)
    (source_dir / f"clip_{case_id}.mp4").write_bytes(b"real-source-placeholder")
    (source_dir / f"clip_{case_id}_data.json").write_text(
        json.dumps(
            {
                "aweme_id": case_id,
                "desc": "公开来源视频",
                "author": {"nickname": "作者"},
            }
        ),
        encoding="utf-8",
    )
    operation = module.Orchestrator(
        pipeline_root=pipeline,
        repo_root=repo,
        downloader_root=downloader,
        source_url=f"https://www.douyin.com/video/{case_id}",
        attempt_id="attempt_0004",
        profile="mix",
        industry="待分类",
        reanalyze=False,
    )
    source = operation.acquire()
    assert source["media_rights_granted"] is False
    assert source["production_footage_pool_eligible"] is False
    assert source["source_video_sha256"] == sha256(Path(source["video"]))


def test_qiyun_acquisition_keeps_canonical_identity_and_no_signed_url(tmp_path: Path, monkeypatch):
    repo, pipeline, downloader = roots(tmp_path)
    case_id = "7682442957798161531"
    calls = []

    def fake_acquire(**kwargs):
        calls.append(kwargs)
        video = kwargs["attempt_root"] / "source_media" / "source.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"transient-media")
        return {
            "video": str(video), "source_video_sha256": sha256(video),
            "source_description": "标题", "source_author": "作者",
            "metadata": {"provider": "qiyun", "stable_video_id": case_id},
        }

    monkeypatch.setattr(module, "acquire_qiyun_media", fake_acquire)
    operation = module.Orchestrator(
        pipeline_root=pipeline, repo_root=repo, downloader_root=downloader,
        source_url=f"https://www.douyin.com/video/{case_id}",
        attempt_id="attempt_qiyun_001", profile="news", industry="待分类",
        reanalyze=False, acquisition_provider="qiyun",
        provider_source_url="https://v.douyin.com/short123/",
    )
    source = operation.acquire()
    assert calls[0]["source_url"] == f"https://www.douyin.com/video/{case_id}"
    assert calls[0]["provider_source_url"] == "https://v.douyin.com/short123/"
    assert source["source_url"] == f"https://www.douyin.com/video/{case_id}"
    assert source["stable_video_id"] == case_id
    assert source["media_rights_granted"] is False
    assert source["production_footage_pool_eligible"] is False
    assert "video_url" not in (operation.attempt_root / "source_acquisition_v1.json").read_text(encoding="utf-8")
    assert not (downloader / "Downloaded").exists()


def seed_failed_qiyun_attempt(tmp_path: Path, monkeypatch):
    repo, pipeline, downloader = roots(tmp_path)
    case_id = "7682442957798161531"
    source_url = f"https://www.douyin.com/video/{case_id}"
    calls = []

    def fake_acquire(**kwargs):
        calls.append(kwargs["attempt_root"].name)
        video = kwargs["attempt_root"] / "source_media" / "source.mp4"
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b"verified-qiyun-media")
        return {
            "video": str(video), "source_video_sha256": sha256(video),
            "source_description": "标题", "source_author": "作者",
            "metadata": {
                "provider": "qiyun", "stable_video_id": case_id,
                "canonical_source_url": source_url,
            },
        }

    monkeypatch.setattr(module, "acquire_qiyun_media", fake_acquire)
    kwargs = dict(
        pipeline_root=pipeline, repo_root=repo, downloader_root=downloader,
        source_url=source_url, profile="news", industry="待分类",
        reanalyze=True, acquisition_provider="qiyun",
    )
    first = module.Orchestrator(attempt_id="attempt_qiyun_failed_001", **kwargs)
    first_acquisition = first.acquire()
    first.state["status"] = "failed"
    first.save()
    return first, first_acquisition, kwargs, calls


def test_qiyun_failed_reanalysis_reuses_verified_media_without_api_call(tmp_path: Path, monkeypatch):
    first, first_acquisition, kwargs, calls = seed_failed_qiyun_attempt(tmp_path, monkeypatch)
    prior_state = first.state_path.read_bytes()
    prior_receipt = (first.attempt_root / "source_acquisition_v1.json").read_bytes()
    resumed = module.Orchestrator(attempt_id=first.attempt_id, **kwargs)
    assert resumed.acquire()["source_video_sha256"] == first_acquisition["source_video_sha256"]
    assert calls == [first.attempt_id]

    second = module.Orchestrator(attempt_id="attempt_qiyun_failed_002", **kwargs)
    reused = second.acquire()
    assert calls == [first.attempt_id]
    assert reused["provider_api_called_this_attempt"] is False
    assert reused["reused_from_attempt_id"] == first.attempt_id
    assert reused["source_video_sha256"] == first_acquisition["source_video_sha256"]
    assert Path(reused["video"]) != Path(first_acquisition["video"])
    assert sha256(Path(reused["video"])) == sha256(Path(first_acquisition["video"]))
    assert Path(reused["metadata"]).is_relative_to(second.attempt_root)
    assert first.state_path.read_bytes() == prior_state
    assert (first.attempt_root / "source_acquisition_v1.json").read_bytes() == prior_receipt
    assert "video_url" not in (second.attempt_root / "source_acquisition_v1.json").read_text(encoding="utf-8")
    from storage_retention_v1 import _transient_targets
    targets, unsafe = _transient_targets(second.attempt_root, kwargs["downloader_root"])
    assert unsafe == []
    assert ("source_video", Path(reused["video"]).resolve()) in targets


def test_qiyun_case_run_hands_off_canonical_manifest_without_models(tmp_path: Path, monkeypatch):
    first, _, kwargs, calls = seed_failed_qiyun_attempt(tmp_path, monkeypatch)
    operation = module.Orchestrator(attempt_id="attempt_qiyun_visual_002", **kwargs)
    stages = []

    def fake_run_command(label, command, stage_id, timeout, **_kwargs):
        stages.append(label)
        if label == "transcribe":
            transcript = operation.attempt_root / "evidence" / "transcription" / "source" / "transcript_segments.json"
            module.write_atomic_json(transcript, {
                "source_file": str(operation.attempt_root / "source_media" / "source.mp4"),
                "segments": [], "discarded_segments": [], "duration": 1, "model": "fixture",
            })
        elif label == "audio-timeline":
            audio = operation.attempt_root / "evidence" / "audio_v1" / "audio_word_timeline_v1.json"
            module.write_atomic_json(audio, {
                "case_id": operation.case_id, "validation": {"passed": True},
                "segments": [], "words": [], "transcript_raw": "",
                "speech_evidence_status": "not_detected",
            })
        elif label == "extract-visual":
            assert command[command.index("--case-id") + 1] == operation.case_id
            manifest = operation.attempt_root / "evidence" / "visual" / operation.case_id / "visual_evidence_manifest.json"
            module.write_atomic_json(manifest, {"case_id": operation.case_id, "frames": [{"frame_id": "fixture"}]})
        elif label == "analyze-visual":
            manifest = Path(command[command.index("--manifest") + 1])
            assert manifest.is_file()
            assert command[command.index("--max-image-edge") + 1] == "960"
            raise module.CaseAnalysisError("EXPECTED_TEST_STOP", "Stop before model invocation")
        else:
            pytest.fail(f"Unexpected stage: {label}")

    monkeypatch.setattr(operation, "run_command", fake_run_command)
    with pytest.raises(module.CaseAnalysisError) as error:
        operation.run()
    assert error.value.code == "EXPECTED_TEST_STOP"
    assert stages == ["transcribe", "audio-timeline", "extract-visual", "analyze-visual"]
    assert calls == [first.attempt_id]
    assert operation.state["artifacts"]["source_acquisition_v1"]


def test_boundary_review_pauses_before_storyboard_then_resumes_from_checkpoints(tmp_path: Path, monkeypatch):
    first, _, kwargs, provider_calls = seed_failed_qiyun_attempt(tmp_path, monkeypatch)
    operation = module.Orchestrator(attempt_id="attempt_boundary_review_002", **kwargs)
    source = operation.acquire()
    root = operation.attempt_root / "evidence"
    video = Path(source["video"])
    artifacts = {
        root / "transcription" / video.stem / "transcript_segments.json": {
            "source_file": str(video), "segments": [], "discarded_segments": [], "duration": 1, "model": "fixture",
        },
        root / "audio_v1" / "audio_word_timeline_v1.json": {
            "case_id": operation.case_id, "validation": {"passed": True},
            "segments": [], "words": [], "transcript_raw": "", "speech_evidence_status": "not_detected",
        },
        root / "visual" / operation.case_id / "visual_evidence_manifest.json": {
            "case_id": operation.case_id, "frames": [{"frame_id": "fixture"}],
        },
        root / "visual" / operation.case_id / "visual_v1" / "visual_timeline_v1.json": {
            "case_id": operation.case_id, "coverage": {"coverage_label": "candidate_complete"},
        },
        root / "privacy" / "privacy_projection_v1.json": {
            "case_id": operation.case_id, "privacy_policy_version": "privacy-policy-v1.0",
        },
        root / "narration" / "narration_review_v1.json": {
            "case_id": operation.case_id, "manual_review": {"required": False},
        },
        root / "shots" / "shot_boundaries_v1_1.json": {
            "case_id": operation.case_id, "validation": {"passed": True},
            "manual_review": {"required": True, "items": [{"type": "short_shot"}]},
        },
        root / "storyboard" / "reverse_storyboard_v1.json": {
            "case_id": operation.case_id, "validation": {"passed": True},
        },
    }
    for path, value in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        module.write_atomic_json(path, value)
    first_pass_calls = []
    def first_pass_command(label, command, _stage_id, _timeout, **_kwargs):
        first_pass_calls.append(label)
        assert label == "shot-boundaries"
        assert "--review-file" not in command
    monkeypatch.setattr(operation, "run_command", first_pass_command)
    with pytest.raises(module.CaseAnalysisError) as error:
        operation.run()
    assert error.value.code == "SHOT_BOUNDARY_REVIEW_REQUIRED"
    assert first_pass_calls == ["shot-boundaries"]
    assert provider_calls == [first.attempt_id]

    review = root / "shots" / "boundary_review_001.json"
    module.write_atomic_json(review, {"case_id": operation.case_id, "decisions": [
        {"frame_id": "frame_000003000ms.jpg", "action": "keep"},
    ]})
    resumed = module.Orchestrator(attempt_id=operation.attempt_id, **kwargs)
    called = []

    def resume_command(label, command, _stage_id, _timeout, **_kwargs):
        called.append(label)
        if label == "shot-boundaries":
            assert command[command.index("--review-file") + 1] == str(review)
            module.write_atomic_json(root / "shots" / "shot_boundaries_v1_1.json", {
                "case_id": operation.case_id, "validation": {"passed": True},
                "manual_review": {"required": False, "items": []},
            })
        elif label == "reverse-storyboard":
            assert (root / "shots" / "shot_boundaries_v1_1.json").is_file()
        elif label == "build-case":
            raise module.CaseAnalysisError("EXPECTED_TEST_STOP", "No Case candidate in fixture")
        else:
            pytest.fail(f"Unexpected repeated stage: {label}")

    monkeypatch.setattr(resumed, "run_command", resume_command)
    with pytest.raises(module.CaseAnalysisError) as error:
        resumed.run()
    assert error.value.code == "EXPECTED_TEST_STOP"
    assert called == ["shot-boundaries", "reverse-storyboard", "build-case"]
    assert provider_calls == [first.attempt_id]


@pytest.mark.parametrize("invalidity", [
    "expired", "tampered_media", "wrong_metadata", "not_failed", "cleaned", "missing_media",
])
def test_qiyun_reanalysis_reacquires_when_prior_media_not_eligible(tmp_path: Path, monkeypatch, invalidity: str):
    first, _, kwargs, calls = seed_failed_qiyun_attempt(tmp_path, monkeypatch)
    if invalidity == "expired":
        first.state["updated_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        module.write_atomic_json(first.state_path, first.state)
    elif invalidity == "tampered_media":
        (first.attempt_root / "source_media" / "source.mp4").write_bytes(b"tampered")
    elif invalidity == "wrong_metadata":
        metadata_path = first.attempt_root / "source_metadata_v1.json"
        metadata = module.read_json(metadata_path)
        metadata["canonical_source_url"] = "https://www.douyin.com/video/7666666666666666666"
        module.write_atomic_json(metadata_path, metadata)
    elif invalidity == "cleaned":
        first.state["cleanup_status"] = "completed"
        first.save()
    elif invalidity == "missing_media":
        (first.attempt_root / "source_media" / "source.mp4").unlink()
    else:
        first.state["status"] = "awaiting_review"
        first.save()
    second = module.Orchestrator(attempt_id="attempt_qiyun_failed_002", **kwargs)
    acquired = second.acquire()
    assert calls == [first.attempt_id, second.attempt_id]
    assert acquired["provider_api_called_this_attempt"] is True
    assert acquired["reused_from_attempt_id"] is None


def test_reanalysis_after_cleanup_reacquires_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, pipeline, downloader = roots(tmp_path)
    case_id = "7682442957798161531"
    source_dir = downloader / "Downloaded" / "author" / case_id
    source_dir.mkdir(parents=True)
    metadata = source_dir / f"clip_{case_id}_data.json"
    metadata.write_text(
        json.dumps({"aweme_id": case_id, "desc": "retained metadata"}),
        encoding="utf-8",
    )
    video = source_dir / f"clip_{case_id}.mp4"
    downloader_python = downloader / ".venv" / "Scripts" / "python.exe"
    downloader_python.parent.mkdir(parents=True)
    downloader_python.write_bytes(b"test-runtime-placeholder")

    operation = module.Orchestrator(
        pipeline_root=pipeline,
        repo_root=repo,
        downloader_root=downloader,
        source_url=f"https://www.douyin.com/video/{case_id}",
        attempt_id="attempt_reanalysis_after_cleanup",
        profile="mix",
        industry="待分类",
        reanalyze=True,
    )
    download_calls: list[str] = []

    def fake_download(*args, **kwargs):
        download_calls.append("download")
        video.write_bytes(b"reacquired-source")

    monkeypatch.setattr(operation, "run_command", fake_download)

    source = operation.acquire()

    assert download_calls == ["download"]
    assert source["mode"] == "downloaded_from_canonical_source_url"
    assert Path(source["video"]).is_file()
    assert Path(source["metadata"]).is_relative_to(operation.attempt_root)


@pytest.mark.parametrize("new_hint", [False, True])
def test_human_approval_is_explicit_and_does_not_grant_media_rights(tmp_path: Path, new_hint: bool):
    pipeline = Path(__file__).resolve().parents[1]
    source_case = (
        pipeline
        / "tests"
        / "fixtures"
        / "authority_baseline_v1"
        / "data"
        / "cases"
        / "7999999999999999901"
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
    case.setdefault("quality", {})["human_review_required"] = True
    case["quality"]["human_review_completed"] = False
    case.setdefault("validation", {})["human_approval_completed"] = False
    case["validation"]["auto_approved"] = False
    case["validation"]["passed"] = True
    case["visual_evidence"] = {"coverage_label": "candidate_complete"}
    case["privacy_gate"] = {
        "library_safe": True,
        "unresolved_sensitive_items": 0,
        "derived_artifact_scan_passed": True,
        "policy_version": "privacy-policy-v1.0",
    }
    case["storyboard"]["video_understanding"]["verified_proofs"] = []
    case["storyboard"]["claims_semantics"] = (
        "candidate_unverified_unless_supported_by_verified_proofs"
    )
    case["quality"]["verified_proof_count"] = 0
    case["pattern_state"] = {"pattern_mining_performed": False}
    case_id = str(case["case_id"])
    source_url = f"https://www.douyin.com/video/{case_id}"
    recorded_sha = hashlib.sha256(b"source-media-was-cleaned").hexdigest()
    missing_video = tmp_path / "already-cleaned-source.mp4"
    metadata = tmp_path / "source_metadata_v1.json"
    metadata.write_text(
        json.dumps({"aweme_id": case_id, "desc": "retained metadata"}),
        encoding="utf-8",
    )
    storyboard_artifact = tmp_path / "reverse_storyboard_v1.json"
    storyboard_artifact.write_text(
        json.dumps({"case_id": case_id, "synthetic": True}), encoding="utf-8"
    )
    privacy_artifact = tmp_path / "privacy_projection_v1.json"
    privacy_artifact.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "library_safe": True,
                "privacy_policy_version": "privacy-policy-v1.0",
            }
        ),
        encoding="utf-8",
    )
    case["privacy_gate"]["source_projection_sha256"] = sha256(privacy_artifact)
    acquisition = tmp_path / "source_acquisition_v1.json"
    acquisition.write_text(
        json.dumps(
            {
                "case_id": case_id,
                "stable_video_id": case_id,
                "source_url": source_url,
                "platform": "douyin",
                "video": str(missing_video),
                "metadata": str(metadata),
                "source_video_sha256": recorded_sha,
            }
        ),
        encoding="utf-8",
    )
    case["identity"]["platform"] = "douyin"
    case["identity"]["source_url"] = source_url
    if new_hint:
        case["identity"].pop("analysis_profile", None)
        case["operator_profile_hint"] = "news"
    case["source_evidence"]["video"] = {
        "path": str(missing_video),
        "sha256": recorded_sha,
    }
    case["source_evidence"]["metadata"] = {"path": str(metadata)}
    case["source_provenance"] = {
        "platform": "douyin",
        "canonical_source_url": source_url,
        "stable_video_id": case_id,
        "recorded_source_media_sha256": recorded_sha,
        "source_acquisition_ref": {
            "path": str(acquisition),
            "sha256": sha256(acquisition),
        },
        "source_metadata_ref": {
            "path": str(metadata),
            "sha256": sha256(metadata),
        },
    }
    case.setdefault("source_artifacts", {})["video"] = str(missing_video)
    case["source_artifacts"]["source_acquisition_v1"] = str(acquisition)
    case["source_artifacts"]["source_metadata_v1"] = str(metadata)
    case["source_artifacts"]["storyboard_v1"] = str(storyboard_artifact)
    case["source_artifacts"]["privacy_projection_v1"] = str(privacy_artifact)
    candidate = tmp_path / "case_v1.json"
    candidate.write_text(
        json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    before = json.loads(candidate.read_text(encoding="utf-8"))
    assert before["lifecycle"]["approved"] is False
    result = subprocess.run(
        [
            sys.executable,
            str(pipeline / "scripts" / "approve_case_v1.py"),
            "--case",
            str(candidate),
            "--reviewer",
            "test-human-reviewer",
            "--note",
            "Explicit test review only.",
        ],
        cwd=pipeline.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    approved = json.loads(candidate.read_text(encoding="utf-8"))
    receipt = json.loads(
        (tmp_path / "approval_receipt.json").read_text(encoding="utf-8")
    )
    assert approved["lifecycle"]["approved"] is True
    assert approved["validation"]["auto_approved"] is False
    if new_hint:
        assert approved["operator_profile_hint"] == "news"
        assert "analysis_profile" not in approved["identity"]
    assert approved["approval"]["source_traceability"]["local_source_exists"] is False
    assert approved["approval"]["source_traceability"]["traceable"] is True
    assert (
        approved["approval"]["source_traceability"]["recorded_source_sha256"]
        == recorded_sha
    )
    assert receipt["human_gate"] is True
    assert receipt.get("case_approval_grants_media_reuse") is not True


def test_approval_does_not_substitute_local_media_for_acquisition_lineage(
    tmp_path: Path,
):
    case_id = "7682442957798161531"
    source_video = tmp_path / "still-local.mp4"
    source_video.write_bytes(b"local-media-is-not-lineage")
    recorded_sha = sha256(source_video)
    metadata = tmp_path / "source_metadata_v1.json"
    metadata.write_text(
        json.dumps({"aweme_id": case_id}),
        encoding="utf-8",
    )

    provenance, errors = approve_module.validate_source_provenance(
        {
            "case_id": case_id,
            "identity": {
                "platform": "douyin",
                "source_url": f"https://www.douyin.com/video/{case_id}",
            },
            "source_evidence": {
                "video": {"path": str(source_video), "sha256": recorded_sha},
                "metadata": {"path": str(metadata)},
            },
            "source_provenance": {
                "stable_video_id": case_id,
                "recorded_source_media_sha256": recorded_sha,
                "source_metadata_ref": {
                    "path": str(metadata),
                    "sha256": sha256(metadata),
                },
            },
        }
    )

    assert provenance["local_source_exists"] is True
    assert provenance["acquisition_lineage_valid"] is False
    assert provenance["traceable"] is False
    assert "Source acquisition lineage is missing." in errors
