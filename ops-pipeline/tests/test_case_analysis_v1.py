from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
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
