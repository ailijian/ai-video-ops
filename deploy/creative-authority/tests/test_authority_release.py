from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import authority_release as release  # noqa: E402


INVENTORY = {
    "approved_cases": 1,
    "valid_fingerprints": 1,
    "approved_patterns": 1,
    "mix_patterns": 1,
    "news_price_patterns": 1,
    "registry_sha": "a" * 64,
    "coverage_sha": "b" * 64,
    "compatibility_sha": "c" * 64,
}


def put(root: Path, relative: str, value: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def approved_case(data: Path, case_id: str, *, media_sha: str = "d" * 64) -> None:
    case_path = put(
        data,
        f"cases/{case_id}/case_v1.json",
        {
            "case_id": case_id,
            "lifecycle": {"status": "approved", "approved": True},
            "source_provenance": {
                "stable_video_id": case_id,
                "recorded_source_media_sha256": media_sha,
            },
        },
    )
    case_sha = release.sha(case_path)
    put(
        data,
        f"cases/{case_id}/approval_receipt.json",
        {
            "case_id": case_id,
            "decision": "approved",
            "human_gate": True,
            "case_sha256_after_approval": case_sha,
            "source_provenance": {
                "stable_video_id": case_id,
                "recorded_source_sha256": media_sha,
            },
        },
    )
    put(
        data,
        f"fingerprints/{case_id}/case_fingerprint_v1.json",
        {
            "case_id": case_id,
            "source_case": {
                "status": "approved",
                "approved": True,
                "sha256": case_sha,
            },
        },
    )


def fork_local_case(data: Path, case_id: str, *, media_sha: str = "d" * 64) -> None:
    case_path = data / "cases" / case_id / "case_v1.json"
    case = release.read(case_path)
    case["independent_analysis_attempt"] = "production-local"
    case["source_provenance"]["recorded_source_media_sha256"] = media_sha
    case_path.write_text(json.dumps(case), encoding="utf-8")
    case_sha = release.sha(case_path)
    receipt_path = case_path.with_name("approval_receipt.json")
    receipt = release.read(receipt_path)
    receipt["case_sha256_after_approval"] = case_sha
    receipt["note"] = "independent production review"
    receipt["source_provenance"]["recorded_source_sha256"] = media_sha
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    fingerprint_path = data / "fingerprints" / case_id / "case_fingerprint_v1.json"
    fingerprint = release.read(fingerprint_path)
    fingerprint["source_case"]["sha256"] = case_sha
    fingerprint["independent_analysis_attempt"] = "production-local"
    fingerprint_path.write_text(json.dumps(fingerprint), encoding="utf-8")


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "--allow-empty", "-m", "fixture"], check=True, capture_output=True)
    pipeline = repo / "ops-pipeline"
    data = pipeline / "data"
    for singleton in release.SINGLETONS:
        put(data, singleton, {"schema_version": "fixture"})
    approved_case(data, "case-a")
    approved_case(data, "case-safe")
    approved_case(data, "case-compatible")
    put(
        data,
        "cases/case-compatible/case_profile_compatibility_approval_v1.json",
        {
            "status": "approved",
            "case_id": "case-compatible",
            "approved_compatible_generation_profiles": ["mix"],
        },
    )
    put(data, "patterns/approved/pattern-a/pattern_v1.json", {"pattern_id": "pattern-a", "scope": {"supported_case_ids": ["case-a"]}})
    put(data, "patterns/approved/pattern-a/approval_receipt.json", {"human_gate": True, "compatible_profiles": ["mix"]})
    put(data, "customer_intakes/customer-a/private.json", {"secret": "TEST_SECRET_DO_NOT_SHIP"})
    put(data, "personas/customer-a/revision_0001/persona.json", {"secret": "TEST_SECRET_DO_NOT_SHIP"})
    put(data, "content_ledgers/customer-a/content_ledger_v1.json", {"secret": "TEST_SECRET_DO_NOT_SHIP"})
    put(data, "generation_requests/request-a/request.json", {"secret": "TEST_SECRET_DO_NOT_SHIP"})
    put(data, "downloads/video.mp4", {"secret": "TEST_SECRET_DO_NOT_SHIP"})
    put(data, ".env", {"secret": "TEST_SECRET_DO_NOT_SHIP"})
    monkeypatch.setattr(release, "_formal_validation", lambda *_: INVENTORY)
    parent = tmp_path / "external-release"
    built = release.build_release(pipeline, parent, repo)
    return repo, pipeline, built


def test_builder_excludes_customer_runtime_media_and_secrets(source):
    _, _, built = source
    manifest_text = (built / "manifest.json").read_text(encoding="utf-8")
    assert "TEST_SECRET_DO_NOT_SHIP" not in manifest_text
    assert release.verify_release(built, source[0]) == INVENTORY
    paths = [entry["relative_path"] for entry in release.read(built / "manifest.json")["files"]]
    assert all("customer_intakes" not in path and "personas" not in path and "content_ledgers" not in path and "generation_requests" not in path for path in paths)
    assert not any(path.endswith((".env", ".mp4")) for path in paths)


def test_tamper_and_missing_registry_fail(source):
    repo, _, built = source
    registry = built / "bundle" / "data" / release.SINGLETONS[0]
    registry.write_text("{}", encoding="utf-8")
    with pytest.raises(release.AuthorityReleaseError, match="Manifest SHA"):
        release.verify_release(built, repo)
    registry.unlink()
    with pytest.raises(release.AuthorityReleaseError, match="Manifest SHA"):
        release.verify_release(built, repo)


def test_idempotent_case_and_pattern_collision(source, tmp_path: Path):
    repo, _, built = source
    target = tmp_path / "target"
    case = "data/cases/case-a/case_v1.json"
    pattern = "data/patterns/approved/pattern-a/pattern_v1.json"
    for relative in (case, pattern):
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((built / "bundle" / relative).read_bytes())
    plan = release.plan_merge(built, target, repo)
    assert case in plan["skipped_identical"]
    assert pattern in plan["skipped_identical"]
    (target / pattern).write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(release.AuthorityReleaseError) as exc:
        release.plan_merge(built, target, repo)
    assert any(item["code"] == "PATTERN_COLLISION" for item in exc.value.details["unresolved_collisions"])
    (target / pattern).write_bytes((built / "bundle" / pattern).read_bytes())
    (target / case).write_text('{"changed": true}', encoding="utf-8")
    with pytest.raises(release.AuthorityReleaseError) as exc:
        release.plan_merge(built, target, repo)
    assert any(item["code"] == "TRUE_CASE_IDENTITY_CONFLICT" for item in exc.value.details["unresolved_collisions"])


def test_install_preserves_new_cases_and_does_not_grant_compatibility(source, tmp_path: Path):
    repo, pipeline, built = source
    new_case = put(pipeline / "data", "cases/new-production-case/case_v1.json", {"case_id": "new-production-case"})
    original = new_case.read_bytes()
    expected_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    receipt = tmp_path / "config" / "creative-authority-installation.json"
    result = release.install_release(built, pipeline, repo, expected_commit, tmp_path / "backups", receipt)
    assert result["merge"]["collisions"] == 0
    assert new_case.read_bytes() == original
    assert not new_case.with_name("case_profile_compatibility_approval_v1.json").exists()
    assert release.preflight(pipeline, repo, receipt) == INVENTORY
    for runtime_dir in ("customer_intakes", "personas", "content_ledgers", "generation_requests"):
        shutil.rmtree(pipeline / "data" / runtime_dir)
    assert release.preflight(pipeline, repo, receipt) == INVENTORY
    assert "TEST_SECRET_DO_NOT_SHIP" not in receipt.read_text(encoding="utf-8")
    second = release.plan_merge(built, pipeline, repo)
    assert not second["added"]
    assert len(second["skipped_identical"]) == len(release.read(built / "manifest.json")["files"])


def test_preflight_requires_authority_and_receipt(source, tmp_path: Path):
    repo, pipeline, _ = source
    receipt = tmp_path / "missing.json"
    with pytest.raises(release.AuthorityReleaseError, match="installation receipt is missing"):
        release.preflight(pipeline, repo, receipt)
    (pipeline / "data" / release.SINGLETONS[0]).unlink()
    with pytest.raises(release.AuthorityReleaseError, match="Shared Creative Authority missing"):
        release.preflight(pipeline, repo)


def test_rejects_customer_paths_and_symlinks():
    with pytest.raises(release.AuthorityReleaseError, match="Forbidden release file"):
        release.safe_relative("data/customer_intakes/customer-a/intake.json")
    with pytest.raises(release.AuthorityReleaseError, match="Unsafe release path"):
        release.safe_relative("data/cases/../personas/customer-a.json")


def test_same_source_independent_reanalysis_is_local_preserve_candidate(source):
    repo, pipeline, built = source
    fork_local_case(pipeline / "data", "case-safe")
    audit = release.audit_merge(built, pipeline, repo)
    assert audit["ready"] is True
    assert audit["unresolved_collision_count"] == 0
    preserved = audit["local_authority_preserved"]
    assert len(preserved) == 1
    assert preserved[0]["case_id"] == "case-safe"
    assert preserved[0]["compatibility_inherited"] is False
    assert preserved[0]["production_version_preserved"] is True
    assert preserved[0]["release_version_installed"] is False
    assert audit["category_counts"]["SAME_SOURCE_REANALYSIS_COLLISION"] == 3


def test_same_source_reanalysis_with_pattern_dependency_stops(source):
    repo, pipeline, built = source
    fork_local_case(pipeline / "data", "case-a")
    audit = release.audit_merge(built, pipeline, repo)
    assert audit["ready"] is False
    blocker = next(item for item in audit["unresolved_collisions"] if item["code"] == "DOWNSTREAM_APPROVED_AUTHORITY_DEPENDENCY")
    assert blocker["case_id"] == "case-a"
    assert blocker["downstream_dependencies"] == ["APPROVED_PATTERN_SUPPORT:pattern-a"]
    with pytest.raises(release.AuthorityReleaseError) as exc:
        release.plan_merge(built, pipeline, repo)
    assert exc.value.code == "CREATIVE_AUTHORITY_MERGE_PLAN_BLOCKED"


def test_same_source_reanalysis_with_approved_compatibility_stops(source):
    repo, pipeline, built = source
    fork_local_case(pipeline / "data", "case-compatible")
    audit = release.audit_merge(built, pipeline, repo)
    blocker = next(item for item in audit["unresolved_collisions"] if item["code"] == "DOWNSTREAM_APPROVED_AUTHORITY_DEPENDENCY")
    assert blocker["case_id"] == "case-compatible"
    assert "CASE_PROFILE_COMPATIBILITY_APPROVAL" in blocker["downstream_dependencies"]


def test_same_case_id_with_different_source_media_is_true_identity_conflict(source):
    repo, pipeline, built = source
    fork_local_case(pipeline / "data", "case-safe", media_sha="e" * 64)
    audit = release.audit_merge(built, pipeline, repo)
    assert audit["ready"] is False
    blocker = next(item for item in audit["unresolved_collisions"] if item["code"] == "TRUE_CASE_IDENTITY_CONFLICT")
    assert blocker["case_id"] == "case-safe"


def test_singleton_collision_still_stops(source):
    repo, pipeline, built = source
    singleton = pipeline / "data" / release.SINGLETONS[0]
    singleton.write_text('{"changed": true}', encoding="utf-8")
    audit = release.audit_merge(built, pipeline, repo)
    assert audit["ready"] is False
    assert any(item["code"] == "SINGLETON_COLLISION" for item in audit["unresolved_collisions"])


def test_installation_receipt_records_local_preserved_fork(source, tmp_path: Path):
    repo, pipeline, built = source
    fork_local_case(pipeline / "data", "case-safe")
    expected_commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    receipt_path = tmp_path / "receipt.json"
    result = release.install_release(built, pipeline, repo, expected_commit, tmp_path / "backups", receipt_path)
    receipt = release.read(receipt_path)
    assert result["merge"]["unresolved_collisions"] == 0
    assert receipt["local_authority_preserved"][0]["case_id"] == "case-safe"
    assert receipt["local_authority_preserved"][0]["compatibility_inherited"] is False
    installed_paths = {item["relative_path"] for item in receipt["installed_files"]}
    assert not installed_paths.intersection(receipt["local_authority_preserved"][0]["skipped_release_paths"])
    assert release.preflight(pipeline, repo, receipt_path) == INVENTORY
