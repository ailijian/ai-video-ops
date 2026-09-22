"""Resolve the deterministic Generation Source Plan for one Generation Request.

This wrapper is orchestration-only. It consumes the canonical
match_generation_sources_v1 matcher and never re-implements Pattern / Case /
Fingerprint matching. It performs no remote model call, generates no script,
creates no Generation Batch and writes no Content Ledger.

STOP boundary: Generation Source Plan ready.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from match_generation_sources_v1 import (
    build_source_plan,
    write_source_plan,
)

REQUEST_SCHEMA_VERSION = "generation-request-v1.0"
HANDOFF_SCHEMA_VERSION = "generation-source-planning-handoff-v1.0"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

DEFAULT_PATTERN_ROOT = "data/patterns/approved"
DEFAULT_CASE_ROOT = "data/cases"
DEFAULT_FINGERPRINT_ROOT = "data/fingerprints"
DEFAULT_PRODUCTION_PLAN_ROOT = "data/production_plans"
DEFAULT_COVERAGE_REPORT = ("data/creative_coverage/" "creative_coverage_report_v1.json")
DEFAULT_COMPATIBILITY_APPROVAL = (
    "data/production_profiles/approvals/"
    "production_profile_compatibility_approval_v1.json"
)


class SourcePlanError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise SourcePlanError(
            "SOURCE_PLAN_ARTIFACT_INVALID",
            (
                "Canonical artifact "
                f"is unreadable: {path}"
            ),
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise SourcePlanError(
            "SOURCE_PLAN_ARTIFACT_INVALID",
            (
                "Canonical artifact must "
                f"be a JSON object: {path}"
            ),
        )

    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_recorded_path(pipeline_root: Path, raw_path: Any) -> Path:
    candidate = Path(str(raw_path or ""))
    if not candidate.is_absolute():
        candidate = pipeline_root / candidate
    candidate = candidate.expanduser().resolve()
    if not candidate.is_file():
        raise SourcePlanError(
            "SOURCE_PLAN_AUTHORITY_MISSING",
            f"Required canonical authority is missing: {candidate}",
        )
    return candidate


def load_request_and_handoff(
    pipeline_root: Path,
    request_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    if not REQUEST_ID_RE.match(request_id or ""):
        raise SourcePlanError(
            "GENERATION_REQUEST_ID_INVALID",
            f"Generation Request id is not machine-safe: {request_id!r}",
        )

    request_dir = pipeline_root / "data" / "generation_requests" / request_id
    request_path = request_dir / "generation_request_v1.json"
    handoff_path = request_dir / "generation_source_planning_handoff_v1.json"

    if not request_path.is_file():
        raise SourcePlanError(
            "GENERATION_REQUEST_NOT_FOUND",
            f"Generation Request does not exist: {request_id}",
        )
    if not handoff_path.is_file():
        raise SourcePlanError(
            "SOURCE_PLANNING_HANDOFF_REQUIRED",
            ("Source Planning Handoff is missing for " f"{request_id}."),
        )

    request = read_json(request_path)
    handoff = read_json(handoff_path)

    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise SourcePlanError(
            "GENERATION_REQUEST_INVALID",
            "Generation Request schema_version is invalid.",
        )
    if str(request.get("request_id") or "") != request_id:
        raise SourcePlanError(
            "GENERATION_REQUEST_LINEAGE_MISMATCH",
            "Generation Request directory and request_id disagree.",
        )
    if handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        raise SourcePlanError(
            "GENERATION_HANDOFF_INVALID",
            "Source Planning Handoff schema_version is invalid.",
        )
    if str(handoff.get("request_id") or "") != request_id:
        raise SourcePlanError(
            "GENERATION_HANDOFF_LINEAGE_MISMATCH",
            "Source Planning Handoff request_id does not match the Request.",
        )

    request_ref = handoff.get("generation_request_ref") or {}
    if request_ref.get("file_sha256") != sha256_file(request_path):
        raise SourcePlanError(
            "GENERATION_HANDOFF_LINEAGE_MISMATCH",
            ("Source Planning Handoff does not reference the " "current immutable Request."),
        )

    lifecycle = request.get("lifecycle") or {}
    authority = request.get("authority") or {}

    lifecycle_status = str(
        lifecycle.get("status")
        or ""
    )

    if lifecycle_status != "created":
        raise SourcePlanError(
            "SOURCE_PLANNING_LIFECYCLE_CLOSED",
            (
                "Generation Request is not "
                "in the created lifecycle "
                "state; Source Planning is "
                "not allowed."
            ),
        )

    if (
        lifecycle.get("generation_started") is True
        or authority.get("script_generation_performed") is True
    ):
        raise SourcePlanError(
            "GENERATION_ALREADY_STARTED",
            ("Generation Request already entered script " "generation; Source Planning is closed."),
        )

    return request_path, request, handoff


def _verify_ref_file(
    pipeline_root: Path,
    reference: dict[str, Any],
    label: str,
) -> Path:
    if not isinstance(
        reference,
        dict,
    ):
        raise SourcePlanError(
            "SOURCE_PLAN_LINEAGE_MISMATCH",
            (
                f"{label} lineage "
                "reference is invalid."
            ),
        )

    raw_path = str(
        reference.get("path")
        or ""
    )

    recorded_sha = str(
        reference.get(
            "file_sha256"
        )
        or ""
    )

    if (
        not raw_path
        or not recorded_sha
    ):
        raise SourcePlanError(
            "SOURCE_PLAN_LINEAGE_MISMATCH",
            (
                f"{label} lineage requires "
                "both path and file_sha256."
            ),
        )

    path = resolve_recorded_path(
        pipeline_root,
        raw_path,
    )

    if (
        sha256_file(path)
        != recorded_sha
    ):
        raise SourcePlanError(
            "SOURCE_PLAN_LINEAGE_MISMATCH",
            (
                f"{label} SHA-256 does not "
                "match the immutable "
                "Request/Handoff lineage."
            ),
        )

    return path


def _request_lineage_ref(
    request: dict[str, Any],
    handoff: dict[str, Any],
    key: str,
    label: str,
) -> dict[str, Any]:
    request_lineage = (
        request.get("lineage")
        or {}
    )

    request_ref = (
        request_lineage.get(key)
        or {}
    )

    handoff_ref = (
        handoff.get(key)
        or {}
    )

    if (
        not isinstance(
            request_ref,
            dict,
        )
        or not request_ref
        or not isinstance(
            handoff_ref,
            dict,
        )
        or not handoff_ref
        or handoff_ref
        != request_ref
    ):
        raise SourcePlanError(
            "SOURCE_PLAN_LINEAGE_MISMATCH",
            (
                f"{label} reference in "
                "Source Planning Handoff "
                "does not exactly match "
                "the immutable Generation "
                "Request lineage."
            ),
        )

    return handoff_ref


def resolve_authority_inputs(
    pipeline_root: Path,
    request: dict[str, Any],
    handoff: dict[str, Any],
) -> dict[str, Any]:
    business_ref = (
        _request_lineage_ref(
            request,
            handoff,
            "business_persona_ref",
            "Approved Business Persona",
        )
    )

    speaker_ref = (
        _request_lineage_ref(
            request,
            handoff,
            "speaker_persona_ref",
            "Approved Speaker Persona",
        )
    )

    registry_ref = (
        _request_lineage_ref(
            request,
            handoff,
            (
                "production_profile_"
                "registry_ref"
            ),
            "Production Profile Registry",
        )
    )

    persona_path = _verify_ref_file(pipeline_root, business_ref, "Approved Business Persona")
    speaker_path = _verify_ref_file(pipeline_root, speaker_ref, "Approved Speaker Persona")
    registry_path = _verify_ref_file(
        pipeline_root, registry_ref, "Production Profile Registry"
    )

    authority_roots = handoff.get("authority_roots") or {}
    universe = resolve_matching_universe(
        pipeline_root,
        authority_roots=authority_roots,
    )
    return {
        "persona_path": persona_path,
        "speaker_persona_path": speaker_path,
        "profile_registry_path": registry_path,
        **universe,
    }


def resolve_matching_universe(
    pipeline_root: Path,
    *,
    authority_roots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve the current canonical Pattern / Case matching universe.

    The function is read-only and request-independent so both feasibility
    preview and formal Source Plan resolution consume identical authorities.
    """

    pipeline_root = pipeline_root.expanduser().resolve()
    authority_roots = authority_roots or {}
    pattern_root = pipeline_root / str(
        authority_roots.get("approved_pattern_root") or DEFAULT_PATTERN_ROOT
    )
    case_root = pipeline_root / str(authority_roots.get("case_root") or DEFAULT_CASE_ROOT)
    plan_root = pipeline_root / str(
        authority_roots.get("production_plan_root") or DEFAULT_PRODUCTION_PLAN_ROOT
    )
    fingerprint_root = pipeline_root / DEFAULT_FINGERPRINT_ROOT

    pattern_paths = sorted(pattern_root.glob("*/pattern_v1.json"))
    if not pattern_paths:
        raise SourcePlanError(
            "SOURCE_PLAN_AUTHORITY_MISSING",
            f"No Approved Pattern inputs under {pattern_root}.",
        )

    # Canonical matching universe: an Approved Case enters deterministic
    # matching only together with its one-to-one Fingerprint when the
    # Fingerprint declares a complete Approved-Case binding (status approved,
    # approved flag true, SHA-256 matching the current Case artifact). A
    # Fingerprint without any source_case binding is a draft and its Case is
    # not a matching source yet; a claimed binding that fails verification is
    # broken lineage and fails closed.
    case_paths: list[Path] = []
    fingerprint_paths: list[Path] = []
    for case_path in sorted(case_root.glob("*/case_v1.json")):
        case_id = str(read_json(case_path).get("case_id") or "")
        if not case_id:
            raise SourcePlanError(
                "SOURCE_PLAN_AUTHORITY_INVALID",
                f"Approved Case has no case_id: {case_path}",
            )
        fingerprint_path = fingerprint_root / case_id / "case_fingerprint_v1.json"
        if not fingerprint_path.is_file():
            continue
        fingerprint = read_json(fingerprint_path)
        if str(fingerprint.get("case_id") or "") != case_id:
            raise SourcePlanError(
                "SOURCE_PLAN_LINEAGE_MISMATCH",
                (f"Fingerprint {fingerprint_path} does not belong to " f"Case {case_id}."),
            )
        source_case = fingerprint.get("source_case")
        if source_case is None:
            # Earlier News fingerprints use a draft schema but were later
            # explicitly bound by a Human-approved, SHA-pinned compatibility
            # sidecar. That sidecar is the binding authority, not the operator
            # hint or observed source profile.
            sidecar_path = case_path.with_name("case_profile_compatibility_approval_v1.json")
            if not sidecar_path.is_file():
                continue
            sidecar = read_json(sidecar_path)
            if (
                sidecar.get("status") != "approved"
                or sidecar.get("case_id") != case_id
                or (sidecar.get("source_approved_case_ref") or {}).get("sha256") != sha256_file(case_path)
                or (sidecar.get("fingerprint_ref") or {}).get("sha256") != sha256_file(fingerprint_path)
                or fingerprint.get("source_case_sha256") != sha256_file(case_path)
            ):
                raise SourcePlanError(
                    "SOURCE_PLAN_LINEAGE_MISMATCH",
                    f"Legacy Fingerprint {case_id} has invalid Human-approved binding.",
                )
            case_paths.append(case_path)
            fingerprint_paths.append(fingerprint_path)
            continue
        if (
            source_case.get("status") != "approved"
            or source_case.get("approved") is not True
        ):
            raise SourcePlanError(
                "SOURCE_PLAN_LINEAGE_MISMATCH",
                (
                    f"Fingerprint {case_id} claims a Source Case binding "
                    "that is not Approved."
                ),
            )
        if str(source_case.get("sha256") or "").lower() != sha256_file(case_path):
            raise SourcePlanError(
                "SOURCE_PLAN_LINEAGE_MISMATCH",
                (
                    f"Fingerprint {case_id} Source Case SHA-256 does not "
                    "match the current Approved Case artifact."
                ),
            )
        case_paths.append(case_path)
        fingerprint_paths.append(fingerprint_path)

    if not case_paths:
        raise SourcePlanError(
            "SOURCE_PLAN_AUTHORITY_MISSING",
            (
                "No Approved Case with a bound one-to-one Fingerprint under "
                f"{case_root}."
            ),
        )

    coverage_report_path = resolve_recorded_path(pipeline_root, DEFAULT_COVERAGE_REPORT)
    compatibility_approval_path = resolve_recorded_path(
        pipeline_root, DEFAULT_COMPATIBILITY_APPROVAL
    )

    return {
        "pattern_paths": pattern_paths,
        "case_paths": case_paths,
        "fingerprint_paths": fingerprint_paths,
        "creative_coverage_report_path": coverage_report_path,
        "profile_compatibility_approval_path": compatibility_approval_path,
        "production_plan_root": plan_root,
    }


def resolve_generation_source_plan(
    *,
    pipeline_root: Path,
    request_id: str,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()

    request_path, request, handoff = load_request_and_handoff(pipeline_root, request_id)
    inputs = resolve_authority_inputs(pipeline_root, request, handoff)

    try:
        plan = build_source_plan(
            persona_path=inputs["persona_path"],
            request_path=request_path,
            pattern_paths=inputs["pattern_paths"],
            case_paths=inputs["case_paths"],
            fingerprint_paths=inputs["fingerprint_paths"],
            speaker_persona_path=inputs["speaker_persona_path"],
            profile_registry_path=inputs["profile_registry_path"],
            creative_coverage_report_path=inputs["creative_coverage_report_path"],
            profile_compatibility_approval_path=inputs[
                "profile_compatibility_approval_path"
            ],
        )
    except (RuntimeError, FileNotFoundError) as exc:
        raise SourcePlanError(
            "SOURCE_MATCHING_FAILED",
            f"Canonical source matching failed closed: {exc}",
        ) from exc

    if str(plan.get("request_id") or "") != request_id:
        raise SourcePlanError(
            "SOURCE_PLAN_LINEAGE_MISMATCH",
            "Built Source Plan request_id does not match the Request.",
        )

    plan_root = inputs["production_plan_root"]
    plan_path = plan_root / request_id / "generation_source_plan_v1.json"
    existed = plan_path.is_file()

    try:
        output_path, output_sha = write_source_plan(plan, plan_root)
    except RuntimeError as exc:
        raise SourcePlanError(
            "SOURCE_PLAN_CONFLICT",
            (
                "Existing Generation Source Plan differs from the "
                "current deterministic result; refusing to overwrite."
            ),
        ) from exc

    coverage = plan.get("coverage") or {}
    feasibility = plan.get("feasibility") or {}

    return {
        "ok": True,
        "request_id": request_id,
        "source_plan_path": str(output_path),
        "source_plan_sha256": output_sha,
        "coverage_status": coverage.get("status"),
        "coverage_code": coverage.get("code"),
        "selected_pattern_count": len(plan.get("selected_patterns") or []),
        "eligible_case_count": len(plan.get("eligible_case_pool") or []),
        "blocker_type": feasibility.get("blocker_type"),
        "blocker_codes": feasibility.get("blocker_codes") or [],
        "humanized_reason": feasibility.get("humanized_reason"),
        "optional_customer_truth_route": feasibility.get(
            "optional_customer_truth_route"
        ),
        "remote_model_called": False,
        "script_generation_performed": False,
        "generation_batch_created": False,
        "content_ledger_written": False,
        "recovered": existed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the deterministic Generation Source Plan "
            "for one Generation Request without generating content."
        )
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--pipeline-root", default=".")
    args = parser.parse_args()

    try:
        result = resolve_generation_source_plan(
            pipeline_root=Path(args.pipeline_root),
            request_id=str(args.request_id).strip(),
        )
    except SourcePlanError as exc:
        print(
            json.dumps(
                {"ok": False, "code": exc.code, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
