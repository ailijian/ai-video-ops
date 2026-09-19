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


def test_human_approval_is_explicit_and_does_not_grant_media_rights(tmp_path: Path):
    pipeline = Path(__file__).resolve().parents[1]
    source_case = pipeline / "data" / "cases" / "7683027343636542565" / "case_v1.json"
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
    case["quality"]["human_review_required"] = True
    case["quality"]["human_review_completed"] = False
    case["validation"]["human_approval_completed"] = False
    case["validation"]["auto_approved"] = False
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
    assert receipt["human_gate"] is True
    assert receipt.get("case_approval_grants_media_reuse") is not True
