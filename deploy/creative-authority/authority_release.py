"""Package and verify immutable, shared creative production authorities.

Only approved structural assets are portable. Customer runtime state and media
are deliberately outside this release format. No approval is generated here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "creative-authority-release-v1"
SINGLETONS = (
    "production_profiles/production_profile_registry_v1.json",
    "creative_coverage/creative_coverage_report_v1.json",
    "production_profiles/approvals/production_profile_compatibility_approval_v1.json",
)
FORBIDDEN_PARTS = {
    "customer_intakes", "personas", "content_ledgers", "generation_requests",
    "production_plans", "generation_batches", "news_delivery_requests",
    "tasks", "exports", "downloads", "download_cache", "media", "frames",
    "audio", "covers", "privacy", "case_attempts", "uploads", "credentials",
}
FORBIDDEN_SUFFIXES = {".mp4", ".mov", ".mp3", ".wav", ".m4a", ".xlsx", ".xls", ".db", ".sqlite", ".sqlite3", ".env"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class AuthorityReleaseError(RuntimeError):
    def __init__(self, message: str, *, code: str = "AUTHORITY_RELEASE_ERROR", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AuthorityReleaseError(f"Expected JSON object: {path}")
    return value


def safe_relative(value: str) -> str:
    posix = value.replace("\\", "/")
    parts = PurePosixPath(posix).parts
    if not parts or any(part in ("", ".", "..") for part in parts) or posix.startswith("/") or ":" in posix:
        raise AuthorityReleaseError(f"Unsafe release path: {value}")
    if parts[0] != "data":
        raise AuthorityReleaseError(f"Release file must live under data/: {value}")
    if any(part.lower() in FORBIDDEN_PARTS for part in parts) or Path(posix).suffix.lower() in FORBIDDEN_SUFFIXES:
        raise AuthorityReleaseError(f"Forbidden release file: {value}")
    if Path(posix).name.lower() == ".env" or Path(posix).suffix.lower() != ".json":
        raise AuthorityReleaseError(f"Only approved JSON authority files may ship: {value}")
    return posix


def classify(relative: str) -> str:
    parts = PurePosixPath(relative).parts
    if relative == "data/" + SINGLETONS[0]:
        return "production_profile_registry"
    if relative == "data/" + SINGLETONS[1]:
        return "creative_coverage_report"
    if relative == "data/" + SINGLETONS[2]:
        return "production_profile_compatibility_approval"
    if len(parts) == 4 and parts[1] == "cases":
        return {
            "case_v1.json": "approved_case",
            "approval_receipt.json": "case_approval_receipt",
            "case_profile_compatibility_approval_v1.json": "case_profile_compatibility_approval",
            "reverse_storyboard_news_micro_beat_v1.json": "structural_companion",
        }.get(parts[3], "")
    if len(parts) == 4 and parts[1] == "fingerprints" and parts[3] == "case_fingerprint_v1.json":
        return "case_fingerprint"
    if len(parts) == 5 and parts[1:3] == ("patterns", "approved") and parts[4] in ("pattern_v1.json", "approval_receipt.json"):
        return "approved_pattern" if parts[4] == "pattern_v1.json" else "pattern_approval_receipt"
    if parts[1] == "storyboards" and parts[-1] == "reverse_storyboard_v1.json":
        return "structural_companion"
    if parts[1:3] == ("patterns", "candidates") and parts[-1] == "pattern_candidate_v1.json":
        return "structural_companion"
    if parts[1] == "cross_case_research":
        return "structural_companion"
    if parts[1] == "pattern_research":
        return "structural_companion"
    if parts[1] == "creative_coverage" and parts[-1].endswith(".json"):
        return "structural_companion"
    return ""


def relative_ref(path_text: str) -> str | None:
    """Map recorded source absolute paths to the portable data namespace.

    The immutable artifact's recorded path is provenance, not an instruction to
    read the development host. Its SHA is checked against the bundled bytes.
    """
    normalized = path_text.replace("\\", "/")
    marker = "/ops-pipeline/data/"
    if marker in normalized.lower():
        index = normalized.lower().index(marker)
        return "data/" + normalized[index + len(marker):]
    if normalized.startswith("data/"):
        return normalized
    return None


def references(value: Any):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            yield value["path"], value["sha256"]
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def root_files(data_root: Path) -> set[str]:
    selected: set[str] = {"data/" + item for item in SINGLETONS}
    for directory, filename in (("cases", "case_v1.json"), ("fingerprints", "case_fingerprint_v1.json"), ("patterns/approved", "pattern_v1.json")):
        for path in (data_root / directory).glob(f"*/{filename}"):
            selected.add("data/" + path.relative_to(data_root).as_posix())
            receipt = path.with_name("approval_receipt.json")
            if directory != "fingerprints":
                if not receipt.is_file():
                    raise AuthorityReleaseError(f"Missing Human approval receipt: {receipt}")
                selected.add("data/" + receipt.relative_to(data_root).as_posix())
            if directory == "cases":
                sidecar = path.with_name("case_profile_compatibility_approval_v1.json")
                if sidecar.is_file():
                    selected.add("data/" + sidecar.relative_to(data_root).as_posix())
    for relative in selected:
        if not (data_root.parent / relative).is_file():
            raise AuthorityReleaseError(f"Required Shared Authority is missing: {relative}")
    return selected


def collect_graph(data_root: Path) -> set[str]:
    selected = root_files(data_root)
    pending = list(selected)
    while pending:
        current = pending.pop()
        artifact = read(data_root.parent / current)
        for recorded_path, recorded_sha in references(artifact):
            relative = relative_ref(recorded_path)
            if relative is None:
                continue  # external media/template provenance is never portable
            try:
                relative = safe_relative(relative)
            except AuthorityReleaseError:
                continue  # customer/raw provenance is explicitly excluded
            if not classify(relative):
                continue  # non-production research/raw provenance is excluded
            candidate = data_root.parent / relative
            if not candidate.is_file() or sha(candidate) != recorded_sha.lower():
                raise AuthorityReleaseError(f"Structural lineage is missing or changed: {relative}")
            if relative not in selected:
                selected.add(relative)
                pending.append(relative)
    return selected


def _formal_validation(bundle_root: Path, repo_root: Path) -> dict[str, Any]:
    scripts = repo_root / "ops-pipeline" / "scripts"
    sys.path.insert(0, str(scripts))
    from match_generation_sources_v1 import (  # type: ignore
        load_cases_and_fingerprints, load_compatibility_report,
        load_patterns, load_profile_compatibility_approval, load_profile_registry,
    )
    from resolve_generation_source_plan_v1 import resolve_matching_universe  # type: ignore

    data = bundle_root / "data"
    registry_path = data / SINGLETONS[0]
    coverage_path = data / SINGLETONS[1]
    compatibility_path = data / SINGLETONS[2]
    registry, registry_sha = load_profile_registry(registry_path)
    coverage, coverage_sha = load_compatibility_report(coverage_path, registry_sha)
    approval, approval_sha = load_profile_compatibility_approval(compatibility_path, registry_sha, coverage_sha)
    universe = resolve_matching_universe(bundle_root)
    patterns = load_patterns(universe["pattern_paths"])
    cases = load_cases_and_fingerprints(universe["case_paths"], universe["fingerprint_paths"])
    for case_id, source in cases.items():
        case_path = Path(source["case"]["path"])
        receipt = read(case_path.with_name("approval_receipt.json"))
        if receipt.get("decision") != "approved" or receipt.get("human_gate") is not True or receipt.get("case_id") != case_id or receipt.get("case_sha256_after_approval") != source["case"]["sha256"]:
            raise AuthorityReleaseError(f"Invalid Case Human approval: {case_id}")
    for pattern in patterns:
        pattern_id = pattern["artifact"]["pattern_id"]
        pattern_path = Path(pattern["path"])
        receipt = read(pattern_path.with_name("approval_receipt.json"))
        if receipt.get("schema_version") != "pattern-approval-receipt-v1.0" or receipt.get("human_gate") is not True or receipt.get("pattern_id") != pattern_id or (receipt.get("approved_pattern") or {}).get("sha256") != pattern["sha256"]:
            raise AuthorityReleaseError(f"Invalid Pattern Human approval: {pattern_id}")
        if pattern_id != "pcv1_narration_led_process_projection" and not pattern["profile_approval"]:
            raise AuthorityReleaseError(f"Invalid Pattern Profile approval: {pattern_id}")
        for case_id in (pattern["artifact"].get("scope") or {}).get("supported_case_ids") or []:
            if case_id not in cases:
                raise AuthorityReleaseError(f"Pattern support Case missing: {case_id}")
    mix_approvals = {item["case_id"] for item in approval["case_profile_compatibility_approvals"] if "mix" in item.get("approved_compatible_generation_profiles", [])}
    mix_approval = approval.get("pattern_profile_compatibility_approval") or {}
    mix = [pattern for pattern in patterns if pattern["artifact"]["pattern_id"] == mix_approval.get("pattern_id") and "mix" in mix_approval.get("compatible_profiles", []) and set(pattern["artifact"].get("scope", {}).get("supported_case_ids", [])) & mix_approvals]
    price = [pattern for pattern in patterns if pattern["artifact"]["pattern_id"] == "pcv1_news_price_offer_led_micro_information" and "news" in pattern["profile_approval"]["compatible_profiles"]]
    if not mix or not price:
        raise AuthorityReleaseError("Minimum Mix/News Price production graph is unavailable")
    for pattern in price:
        if not any("news" in read(data / "cases" / case_id / "case_profile_compatibility_approval_v1.json").get("approved_compatible_generation_profiles", []) for case_id in pattern["artifact"].get("scope", {}).get("supported_case_ids", [])):
            raise AuthorityReleaseError("News Price Pattern has no Human-approved compatible Case")
    return {"approved_cases": len(cases), "valid_fingerprints": len(cases), "approved_patterns": len(patterns), "mix_patterns": len(mix), "news_price_patterns": len(price), "registry_sha": registry_sha, "coverage_sha": coverage_sha, "compatibility_sha": approval_sha}


def validate_tree(bundle_root: Path, repo_root: Path, expected_files: set[str] | None = None) -> dict[str, Any]:
    actual = {"data/" + path.relative_to(bundle_root / "data").as_posix() for path in (bundle_root / "data").rglob("*") if path.is_file()}
    if expected_files is not None and actual != expected_files:
        raise AuthorityReleaseError("Release file inventory differs from manifest")
    for relative in actual:
        safe_relative(relative)
        if not classify(relative):
            raise AuthorityReleaseError(f"Unclassified file in Shared Authority: {relative}")
        if (bundle_root / relative).is_symlink():
            raise AuthorityReleaseError(f"Symlink is not permitted in release: {relative}")
        read(bundle_root / relative)
    for relative in actual:
        for recorded_path, recorded_sha in references(read(bundle_root / relative)):
            referenced = relative_ref(recorded_path)
            if referenced and referenced in actual and sha(bundle_root / referenced) != recorded_sha.lower():
                raise AuthorityReleaseError(f"Bundled lineage SHA mismatch: {relative} -> {referenced}")
            if referenced and classify(referenced) and referenced not in actual:
                raise AuthorityReleaseError(f"Bundled structural companion missing: {relative} -> {referenced}")
    return _formal_validation(bundle_root, repo_root)


def manifest_authority_rows(bundle: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cases = []
    for path in sorted((bundle / "data" / "cases").glob("*/case_v1.json")):
        case_id = path.parent.name
        sidecar = path.with_name("case_profile_compatibility_approval_v1.json")
        cases.append({"case_id": case_id, "case_sha": sha(path), "fingerprint_sha": sha(bundle / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"), "approval_sha": sha(path.with_name("approval_receipt.json")), "compatibility_status": read(sidecar).get("status") if sidecar.is_file() else "not_approved"})
    patterns = []
    mix_approval = read(bundle / "data" / SINGLETONS[2]).get("pattern_profile_compatibility_approval") or {}
    for path in sorted((bundle / "data" / "patterns" / "approved").glob("*/pattern_v1.json")):
        pattern = read(path)
        profiles = read(path.with_name("approval_receipt.json")).get("compatible_profiles", [])
        if pattern["pattern_id"] == mix_approval.get("pattern_id"):
            profiles = mix_approval.get("compatible_profiles", [])
        patterns.append({"pattern_id": pattern["pattern_id"], "pattern_sha": sha(path), "approval_sha": sha(path.with_name("approval_receipt.json")), "compatible_profiles": profiles, "supported_case_ids": (pattern.get("scope") or {}).get("supported_case_ids", [])})
    return cases, patterns


def build_release(pipeline_root: Path, release_parent: Path, repo_root: Path) -> Path:
    data_root = pipeline_root.resolve() / "data"
    selected = collect_graph(data_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    release = release_parent.resolve() / "releases" / f"creative-authority-{timestamp}"
    if release.exists():
        raise AuthorityReleaseError(f"Release already exists: {release}")
    release.mkdir(parents=True)
    bundle = release / "bundle"
    for relative in sorted(selected):
        source = data_root.parent / relative
        if source.is_symlink():
            raise AuthorityReleaseError(f"Source symlink is not a canonical artifact: {relative}")
        destination = bundle / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    inventory = validate_tree(bundle, repo_root, selected)
    commit = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True).strip()
    files = [{"relative_path": relative, "artifact_type": classify(relative), "sha256": sha(bundle / relative), "size": (bundle / relative).stat().st_size} for relative in sorted(selected)]
    cases, patterns = manifest_authority_rows(bundle)
    manifest = {"schema_version": SCHEMA, "release_id": release.name, "created_at": datetime.now(timezone.utc).isoformat(), "source_repo_commit": commit, "source_machine_role": "development_authority_source", "source_data_root": str(data_root), "files": files, "cases": cases, "patterns": patterns, "production_profile_registry_sha256": inventory["registry_sha"], "creative_coverage_report_sha256": inventory["coverage_sha"], "compatibility_approval_sha256": inventory["compatibility_sha"], "authority": {"customer_runtime_data_included": False, "raw_media_included": False, "credentials_included": False, "human_approval_reexecuted": False, "canonical_artifacts_modified": False}, "validation": inventory}
    (release / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (release / "RELEASE_NOTES.md").write_text(f"# Shared Creative Authority {release.name}\n\nSource commit: `{commit}`. Immutable approved Cases, Fingerprints, Patterns, Profile Registry, Coverage and approval evidence only. Customer runtime state, media and credentials are excluded. This is infrastructure deployment, not customer migration.\n", encoding="utf-8")
    verify_release(release, repo_root)
    return release


def verify_release(release: Path, repo_root: Path) -> dict[str, Any]:
    release = release.resolve()
    manifest = read(release / "manifest.json")
    if manifest.get("schema_version") != SCHEMA or manifest.get("source_machine_role") != "development_authority_source":
        raise AuthorityReleaseError("Invalid Authority Release manifest")
    if manifest.get("release_id") != release.name or not re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("source_repo_commit", ""))):
        raise AuthorityReleaseError("Release identity or source commit is invalid")
    if manifest.get("authority") != {"customer_runtime_data_included": False, "raw_media_included": False, "credentials_included": False, "human_approval_reexecuted": False, "canonical_artifacts_modified": False}:
        raise AuthorityReleaseError("Authority release boundary flags are invalid")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise AuthorityReleaseError("Authority Release is empty")
    paths: set[str] = set()
    for entry in entries:
        relative = safe_relative(entry["relative_path"])
        if relative in paths or entry.get("artifact_type") != classify(relative):
            raise AuthorityReleaseError("Duplicate or misclassified manifest entry")
        paths.add(relative)
        path = release / "bundle" / relative
        if not path.is_file() or path.is_symlink() or not SHA_RE.fullmatch(str(entry.get("sha256", ""))) or sha(path) != entry["sha256"] or path.stat().st_size != entry["size"]:
            raise AuthorityReleaseError(f"Manifest SHA/size mismatch: {relative}")
    result = validate_tree(release / "bundle", repo_root, paths)
    if (manifest.get("cases"), manifest.get("patterns")) != manifest_authority_rows(release / "bundle"):
        raise AuthorityReleaseError("Manifest Case/Pattern Authority inventory mismatch")
    for key, inventory_key in (("production_profile_registry_sha256", "registry_sha"), ("creative_coverage_report_sha256", "coverage_sha"), ("compatibility_approval_sha256", "compatibility_sha")):
        if manifest.get(key) != result[inventory_key]:
            raise AuthorityReleaseError(f"Manifest {key} mismatch")
    return result


def preflight(pipeline_root: Path, repo_root: Path, receipt_path: Path | None = None) -> dict[str, Any]:
    root = pipeline_root.resolve()
    data = root / "data"
    for relative in SINGLETONS:
        if not (data / relative).is_file():
            raise AuthorityReleaseError(f"Shared Creative Authority missing: {relative}")
    result = _formal_validation(root, repo_root)
    if receipt_path and not receipt_path.is_file():
        raise AuthorityReleaseError("Shared Creative Authority installation receipt is missing")
    if receipt_path:
        receipt = read(receipt_path)
        for item in receipt.get("installed_files", []):
            relative = safe_relative(item["relative_path"])
            if not (root / relative).is_file() or sha(root / relative) != item["sha256"]:
                raise AuthorityReleaseError(f"Installed Authority differs from receipt: {relative}")
        for item in receipt.get("local_authority_preserved", []):
            case_id = str(item.get("case_id") or "")
            case_path = root / "data" / "cases" / case_id / "case_v1.json"
            fingerprint_path = root / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"
            if (
                not case_id
                or not case_path.is_file()
                or not fingerprint_path.is_file()
                or sha(case_path) != item.get("production_case_sha")
                or sha(fingerprint_path) != item.get("production_fingerprint_sha")
                or item.get("compatibility_inherited") is not False
            ):
                raise AuthorityReleaseError(f"Preserved local Authority differs from receipt: {case_id}")
    return result


def _case_source_identity(case: dict[str, Any], receipt: dict[str, Any]) -> dict[str, str]:
    provenance = case.get("source_provenance") or {}
    receipt_provenance = receipt.get("source_provenance") or {}
    approval_trace = ((case.get("approval") or {}).get("source_traceability") or {})
    stable_video_id = str(
        provenance.get("stable_video_id")
        or receipt_provenance.get("stable_video_id")
        or approval_trace.get("stable_video_id")
        or ""
    )
    recorded_source_sha256 = str(
        provenance.get("recorded_source_media_sha256")
        or provenance.get("recorded_source_sha256")
        or receipt_provenance.get("recorded_source_sha256")
        or approval_trace.get("recorded_source_sha256")
        or ""
    ).lower()
    return {
        "stable_video_id": stable_video_id,
        "recorded_source_sha256": recorded_source_sha256,
    }


def _source_identity_is_internally_consistent(case: dict[str, Any], receipt: dict[str, Any]) -> bool:
    provenance = case.get("source_provenance") or {}
    receipt_provenance = receipt.get("source_provenance") or {}
    approval_trace = ((case.get("approval") or {}).get("source_traceability") or {})
    stable_values = {
        str(value)
        for value in (
            provenance.get("stable_video_id"),
            receipt_provenance.get("stable_video_id"),
            approval_trace.get("stable_video_id"),
        )
        if value
    }
    sha_values = {
        str(value).lower()
        for value in (
            provenance.get("recorded_source_media_sha256"),
            provenance.get("recorded_source_sha256"),
            receipt_provenance.get("recorded_source_sha256"),
            approval_trace.get("recorded_source_sha256"),
        )
        if value
    }
    return len(stable_values) == 1 and len(sha_values) == 1 and bool(next(iter(stable_values), "")) and bool(SHA_RE.fullmatch(next(iter(sha_values), "")))


def _approved_case_and_receipt_valid(case_path: Path, receipt_path: Path) -> tuple[bool, dict[str, Any], dict[str, Any], str]:
    try:
        case, receipt = read(case_path), read(receipt_path)
    except (OSError, json.JSONDecodeError, AuthorityReleaseError) as exc:
        return False, {}, {}, str(exc)
    case_sha = sha(case_path)
    lifecycle = case.get("lifecycle") or {}
    valid = bool(
        str(case.get("case_id") or "")
        and lifecycle.get("status") == "approved"
        and lifecycle.get("approved") is True
        and receipt.get("case_id") == case.get("case_id")
        and receipt.get("decision") == "approved"
        and receipt.get("human_gate") is True
        and str(receipt.get("case_sha256_after_approval") or "").lower() == case_sha
    )
    return valid, case, receipt, "" if valid else "Case or Human approval receipt is invalid"


def _fingerprint_binds_case(fingerprint_path: Path, case_id: str, case_sha: str) -> tuple[bool, str]:
    try:
        fingerprint = read(fingerprint_path)
    except (OSError, json.JSONDecodeError, AuthorityReleaseError) as exc:
        return False, str(exc)
    source = fingerprint.get("source_case") or {}
    bound_sha = str(
        source.get("sha256")
        or (fingerprint.get("provenance") or {}).get("approved_case_sha256")
        or fingerprint.get("source_case_sha256")
        or ""
    ).lower()
    if source:
        approved_binding = source.get("status") == "approved" and source.get("approved") is True
    else:
        approved_binding = bool(bound_sha)
    valid = bool(
        fingerprint.get("case_id") == case_id
        and approved_binding
        and bound_sha == case_sha.lower()
    )
    return valid, "" if valid else "Fingerprint does not bind the exact Approved Case SHA"


def _case_release_paths(manifest: dict[str, Any], case_id: str) -> set[str]:
    case_prefix = f"data/cases/{case_id}/"
    fingerprint_prefix = f"data/fingerprints/{case_id}/"
    return {
        str(entry["relative_path"])
        for entry in manifest["files"]
        if str(entry["relative_path"]).startswith(case_prefix)
        or str(entry["relative_path"]).startswith(fingerprint_prefix)
    }


def _release_downstream_dependencies(release: Path, manifest: dict[str, Any], case_id: str) -> list[str]:
    dependencies: list[str] = []
    for pattern in manifest.get("patterns") or []:
        if case_id in (pattern.get("supported_case_ids") or []):
            dependencies.append(f"APPROVED_PATTERN_SUPPORT:{pattern.get('pattern_id')}")
    global_approval = read(release / "bundle" / "data" / SINGLETONS[2])
    for item in global_approval.get("case_profile_compatibility_approvals") or []:
        if item.get("case_id") == case_id and item.get("approved_compatible_generation_profiles"):
            dependencies.append("PRODUCTION_PROFILE_COMPATIBILITY_APPROVAL")
    sidecar = release / "bundle" / "data" / "cases" / case_id / "case_profile_compatibility_approval_v1.json"
    if sidecar.is_file():
        value = read(sidecar)
        if value.get("status") == "approved" and value.get("approved_compatible_generation_profiles"):
            dependencies.append("CASE_PROFILE_COMPATIBILITY_APPROVAL")
    return sorted(set(dependencies))


def _same_source_reanalysis(
    release: Path,
    pipeline_root: Path,
    case_id: str,
) -> dict[str, Any]:
    release_case = release / "bundle" / "data" / "cases" / case_id / "case_v1.json"
    release_receipt = release_case.with_name("approval_receipt.json")
    release_fingerprint = release / "bundle" / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"
    production_case = pipeline_root / "data" / "cases" / case_id / "case_v1.json"
    production_receipt = production_case.with_name("approval_receipt.json")
    production_fingerprint = pipeline_root / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"
    if not all(path.is_file() for path in (release_case, release_receipt, release_fingerprint, production_case, production_receipt, production_fingerprint)):
        return {"same_source_reanalysis": False, "reason": "Case/receipt/fingerprint trio is incomplete"}
    release_valid, release_case_value, release_receipt_value, release_error = _approved_case_and_receipt_valid(release_case, release_receipt)
    production_valid, production_case_value, production_receipt_value, production_error = _approved_case_and_receipt_valid(production_case, production_receipt)
    release_case_sha, production_case_sha = sha(release_case), sha(production_case)
    release_fp_valid, release_fp_error = _fingerprint_binds_case(release_fingerprint, case_id, release_case_sha)
    production_fp_valid, production_fp_error = _fingerprint_binds_case(production_fingerprint, case_id, production_case_sha)
    release_identity = _case_source_identity(release_case_value, release_receipt_value)
    production_identity = _case_source_identity(production_case_value, production_receipt_value)
    same_identity = bool(
        _source_identity_is_internally_consistent(release_case_value, release_receipt_value)
        and _source_identity_is_internally_consistent(production_case_value, production_receipt_value)
        and release_case_value.get("case_id") == case_id
        and production_case_value.get("case_id") == case_id
        and release_identity["stable_video_id"]
        and release_identity["stable_video_id"] == production_identity["stable_video_id"]
        and SHA_RE.fullmatch(release_identity["recorded_source_sha256"])
        and release_identity["recorded_source_sha256"] == production_identity["recorded_source_sha256"]
    )
    valid = release_valid and production_valid and release_fp_valid and production_fp_valid and same_identity
    errors = [item for item in (release_error, production_error, release_fp_error, production_fp_error) if item]
    if not same_identity:
        errors.append("Stable video identity or recorded source media SHA differs")
    return {
        "same_source_reanalysis": valid,
        "case_id": case_id,
        "source_identity": release_identity if same_identity else {
            "release": release_identity,
            "production": production_identity,
        },
        "production_case_sha": production_case_sha,
        "release_case_sha": release_case_sha,
        "production_fingerprint_sha": sha(production_fingerprint),
        "release_fingerprint_sha": sha(release_fingerprint),
        "reason": "; ".join(errors) if errors else "Independent Approved analysis forks bind the same stable source media",
    }


def audit_merge(release: Path, pipeline_root: Path, repo_root: Path) -> dict[str, Any]:
    release, pipeline_root = release.resolve(), pipeline_root.resolve()
    verify_release(release, repo_root)
    manifest = read(release / "manifest.json")
    file_results: dict[str, dict[str, Any]] = {}
    for entry in manifest["files"]:
        relative = safe_relative(entry["relative_path"])
        target = pipeline_root / relative
        production_sha = sha(target) if target.is_file() and not target.is_symlink() else None
        if target.is_symlink():
            category = "OTHER_SHARED_AUTHORITY_COLLISION"
        elif not target.exists():
            category = "MISSING_ADD"
        elif target.is_file() and not target.is_symlink() and production_sha == entry["sha256"]:
            category = "IDENTICAL"
        else:
            artifact_type = classify(relative)
            if artifact_type == "case_fingerprint":
                category = "FINGERPRINT_CONFLICT"
            elif artifact_type in ("approved_pattern", "pattern_approval_receipt"):
                category = "PATTERN_COLLISION"
            elif artifact_type in (
                "production_profile_registry",
                "creative_coverage_report",
                "production_profile_compatibility_approval",
            ):
                category = "SINGLETON_COLLISION"
            elif artifact_type == "approved_case":
                category = "TRUE_CASE_IDENTITY_CONFLICT"
            else:
                category = "OTHER_SHARED_AUTHORITY_COLLISION"
        file_results[relative] = {
            "relative_path": relative,
            "artifact_type": entry["artifact_type"],
            "category": category,
            "release_sha": entry["sha256"],
            "production_sha": production_sha,
        }

    local_preserved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    release_case_ids = {str(item.get("case_id")) for item in manifest.get("cases") or []}
    for case_id in sorted(release_case_ids):
        case_relative = f"data/cases/{case_id}/case_v1.json"
        case_result = file_results.get(case_relative)
        if not case_result or case_result["category"] != "TRUE_CASE_IDENTITY_CONFLICT":
            continue
        fork = _same_source_reanalysis(release, pipeline_root, case_id)
        related_paths = _case_release_paths(manifest, case_id)
        if not fork["same_source_reanalysis"]:
            for relative in related_paths:
                file_results[relative]["category"] = "TRUE_CASE_IDENTITY_CONFLICT"
            unresolved.append({"code": "TRUE_CASE_IDENTITY_CONFLICT", **fork})
            continue
        dependencies = _release_downstream_dependencies(release, manifest, case_id)
        for relative in related_paths:
            file_results[relative]["category"] = "SAME_SOURCE_REANALYSIS_COLLISION"
        if dependencies:
            unresolved.append({
                "code": "DOWNSTREAM_APPROVED_AUTHORITY_DEPENDENCY",
                **fork,
                "downstream_dependencies": dependencies,
                "recommended_resolution": "HUMAN_AUTHORITY_RESOLUTION_REQUIRED",
            })
            continue
        local_preserved.append({
            "case_id": case_id,
            "source_identity": fork["source_identity"],
            "production_case_sha": fork["production_case_sha"],
            "release_case_sha": fork["release_case_sha"],
            "production_fingerprint_sha": fork["production_fingerprint_sha"],
            "release_fingerprint_sha": fork["release_fingerprint_sha"],
            "release_version_installed": False,
            "production_version_preserved": True,
            "compatibility_inherited": False,
            "skipped_release_paths": sorted(related_paths),
            "reason": "Same source was independently reanalysed and the Release fork has no Approved downstream production dependency.",
            "recommended_resolution": "PRESERVE_PRODUCTION_LOCAL_VERSION",
        })

    for result in file_results.values():
        if result["category"] not in {"IDENTICAL", "MISSING_ADD", "SAME_SOURCE_REANALYSIS_COLLISION"}:
            unresolved.append({
                "code": result["category"],
                "relative_path": result["relative_path"],
                "release_sha": result["release_sha"],
                "production_sha": result["production_sha"],
            })
    # Case-level conflicts supersede the related per-file conflicts.
    unresolved_case_ids = {str(item.get("case_id")) for item in unresolved if item.get("case_id")}
    unresolved = [
        item for item in unresolved
        if not item.get("relative_path")
        or not any(item["relative_path"].startswith(f"data/cases/{case_id}/") or item["relative_path"].startswith(f"data/fingerprints/{case_id}/") for case_id in unresolved_case_ids)
    ]
    categories: dict[str, int] = {}
    for result in file_results.values():
        categories[result["category"]] = categories.get(result["category"], 0) + 1
    return {
        "release_id": manifest["release_id"],
        "file_results": [file_results[key] for key in sorted(file_results)],
        "category_counts": categories,
        "local_authority_preserved": local_preserved,
        "unresolved_collisions": unresolved,
        "unresolved_collision_count": len(unresolved),
        "ready": not unresolved,
        "production_data_modified": False,
    }


def plan_merge(release: Path, pipeline_root: Path, repo_root: Path) -> dict[str, Any]:
    audit = audit_merge(release, pipeline_root, repo_root)
    if not audit["ready"]:
        raise AuthorityReleaseError(
            "Creative Authority merge plan has unresolved collisions",
            code="CREATIVE_AUTHORITY_MERGE_PLAN_BLOCKED",
            details=audit,
        )
    locally_preserved_paths = {
        relative
        for item in audit["local_authority_preserved"]
        for relative in item["skipped_release_paths"]
    }
    added = [item["relative_path"] for item in audit["file_results"] if item["category"] == "MISSING_ADD"]
    skipped = [item["relative_path"] for item in audit["file_results"] if item["category"] == "IDENTICAL"]
    return {
        "added": added,
        "skipped_identical": skipped,
        "local_authority_preserved": audit["local_authority_preserved"],
        "local_preserved_release_paths": sorted(locally_preserved_paths),
        "collisions": audit["category_counts"].get("SAME_SOURCE_REANALYSIS_COLLISION", 0),
        "unresolved_collisions": 0,
        "audit": audit,
    }


def install_release(release: Path, pipeline_root: Path, repo_root: Path, expected_commit: str, backup_parent: Path, receipt_path: Path) -> dict[str, Any]:
    release, pipeline_root = release.resolve(), pipeline_root.resolve()
    actual_commit = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True).strip()
    if actual_commit != expected_commit or pipeline_root != repo_root / "ops-pipeline":
        raise AuthorityReleaseError("Production checkout/pipeline root is not the expected commit/path")
    plan = plan_merge(release, pipeline_root, repo_root)
    if receipt_path.exists() and plan["added"]:
        raise AuthorityReleaseError("Existing installation receipt requires Human review before a different release")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = backup_parent.resolve() / f"creative-authority-pre-bootstrap-{timestamp}"
    if backup.exists():
        raise AuthorityReleaseError("Backup path already exists")
    backup.mkdir(parents=True)
    backup_files = []
    for relative in plan["skipped_identical"]:
        target = pipeline_root / relative
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        backup_files.append({"relative_path": relative, "sha256": sha(destination)})
    (backup / "manifest.json").write_text(json.dumps({"files": backup_files, "source_release": read(release / "manifest.json")["release_id"]}, indent=2) + "\n", encoding="utf-8")
    staged = Path(tempfile.mkdtemp(prefix=".creative-authority-stage-", dir=pipeline_root))
    installed: list[str] = []
    try:
        for relative in plan["added"]:
            staged_path = staged / relative
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(release / "bundle" / relative, staged_path)
        # Re-check collisions after staging; caller must keep Console/tasks stopped.
        for relative in plan["added"]:
            if (pipeline_root / relative).exists():
                raise AuthorityReleaseError(f"Concurrent Shared Authority write: {relative}")
        for relative in plan["added"]:
            target = pipeline_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Same-volume hard-link creation is atomic and fails if a concurrent
            # writer created the target after our collision check. Never replace.
            os.link(staged / relative, target)
            installed.append(relative)
        inventory = preflight(pipeline_root, repo_root)
        manifest = read(release / "manifest.json")
        locally_preserved_paths = set(plan["local_preserved_release_paths"])
        receipt = {
            "release_id": manifest["release_id"],
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "bundle_manifest_sha256": sha(release / "manifest.json"),
            "repo_commit": actual_commit,
            "installed_files": [
                {"relative_path": item["relative_path"], "sha256": item["sha256"]}
                for item in manifest["files"]
                if item["relative_path"] not in locally_preserved_paths
            ],
            "local_authority_preserved": plan["local_authority_preserved"],
            "preinstall_backup_path": str(backup),
            "validation_passed": True,
        }
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        if receipt_path.exists():
            existing = read(receipt_path)
            if existing.get("bundle_manifest_sha256") != receipt["bundle_manifest_sha256"]:
                raise AuthorityReleaseError("Different installation receipt already exists")
        else:
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"release_id": manifest["release_id"], "repo_commit": actual_commit, "backup": str(backup), "receipt": str(receipt_path), "merge": plan, "inventory": inventory}
    except Exception:
        for relative in reversed(installed):
            target = pipeline_root / relative
            if target.is_file() and sha(target) == sha(release / "bundle" / relative):
                target.unlink()
        raise
    finally:
        shutil.rmtree(staged, ignore_errors=True)
