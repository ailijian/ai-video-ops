from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from privacy_projection_v1 import validate_case_privacy_gate


DOUYIN_VIDEO_ID_RE = re.compile(r"(?:/video/|video_id=)(\d{10,24})")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_deferred_evidence_review(
    case: dict[str, Any], candidate_sha256: str, receipt_path: Path | None,
    reviewer: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    pending = case.get("review_pending") or {}
    if pending.get("requires_explicit_confirmation") is not True:
        validation = case.get("validation") or {}
        if validation.get("narration_review_closed") is False or validation.get("boundary_review_closed") is False:
            return None, ["Unresolved evidence review cannot be approved without final confirmation."]
        return None, (["Unexpected evidence review receipt."] if receipt_path else [])
    errors: list[str] = []
    if pending.get("mode") != "deferred_to_final_case_review":
        errors.append("Deferred evidence review mode is invalid.")
    if receipt_path is None or not receipt_path.is_file():
        return None, errors + ["Deferred evidence review receipt is required."]
    try:
        receipt = read_json(receipt_path)
        narration_path = Path(case["source_artifacts"]["narration_review_v1"])
        shot_path = Path(case["source_artifacts"]["shot_boundaries"])
        narration = read_json(narration_path)
        shots = read_json(shot_path)
    except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return None, errors + ["Deferred evidence review artifacts are unavailable."]
    expected_narration = {
        str(item.get("segment_id") or "") for item in
        (narration.get("manual_review") or {}).get("items", [])
        if isinstance(item, dict)
    }
    expected_shots = {
        str(item.get("frame_id") or item.get("boundary_frame_id") or "") for item in
        (shots.get("manual_review") or {}).get("items", [])
        if isinstance(item, dict)
    }
    if "" in expected_narration or "" in expected_shots:
        errors.append("Pending evidence item identity is invalid.")
    if narration.get("case_id") != case.get("case_id") or shots.get("case_id") != case.get("case_id"):
        errors.append("Pending evidence Case identity mismatch.")
    if receipt.get("schema_version") != "case-evidence-final-review-v1":
        errors.append("Evidence review receipt schema is invalid.")
    if not expected_narration and not expected_shots:
        errors.append("Deferred review has no pending evidence.")
    if pending.get("narration_item_count") != len((narration.get("manual_review") or {}).get("items", [])):
        errors.append("Narration pending count differs from source evidence.")
    if pending.get("shot_item_count") != len((shots.get("manual_review") or {}).get("items", [])):
        errors.append("Shot pending count differs from source evidence.")
    if pending.get("narration_sha256") != sha256_file(narration_path) or receipt.get("narration_sha256") != pending.get("narration_sha256"):
        errors.append("Narration evidence hash mismatch.")
    if pending.get("shot_sha256") != sha256_file(shot_path) or receipt.get("shot_sha256") != pending.get("shot_sha256"):
        errors.append("Shot evidence hash mismatch.")
    if receipt.get("case_id") != case.get("case_id") or receipt.get("candidate_sha256") != candidate_sha256:
        errors.append("Evidence review is not bound to this Case candidate.")
    if receipt.get("reviewed_by") != reviewer or not receipt.get("reviewed_at"):
        errors.append("Evidence review attribution is invalid.")
    for key, expected in (("narration_decisions", expected_narration), ("shot_decisions", expected_shots)):
        decisions = receipt.get(key)
        if not isinstance(decisions, list) or len(decisions) != len(expected):
            errors.append(f"{key} must cover every pending item exactly once.")
            continue
        found = [str(item.get("item_id")) for item in decisions if isinstance(item, dict) and item.get("action") == "keep"]
        if len(found) != len(expected) or len(set(found)) != len(found) or set(found) != expected:
            errors.append(f"{key} contains an invalid or missing decision.")
    return receipt, errors


def write_atomic_json(path: Path, data: dict[str, Any]) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(payload)
    temp_path.replace(path)

    return sha256_bytes(payload)


def validate_source_provenance(
    case: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    case_id = str(case.get("case_id") or "")
    identity = case.get("identity") or {}
    source_url = str(identity.get("source_url") or "").strip()
    platform = str(identity.get("platform") or "").strip().lower()
    provenance = case.get("source_provenance") or {}
    source_artifacts = case.get("source_artifacts") or {}
    source_evidence = case.get("source_evidence") or {}
    video = source_evidence.get("video") or {}
    video_path = Path(str(video.get("path") or "")).expanduser()
    local_exists = video_path.is_file()

    match = DOUYIN_VIDEO_ID_RE.search(source_url)
    source_video_id = match.group(1) if match else ""
    stable_video_id = str(
        provenance.get("stable_video_id") or source_video_id or case_id
    )
    if platform != "douyin" or not source_url:
        errors.append("Source platform or canonical source URL is missing.")
    if not case_id or stable_video_id != case_id or source_video_id != case_id:
        errors.append("Stable source video identity does not match Case identity.")

    acquisition_ref = provenance.get("source_acquisition_ref") or {}
    acquisition_path = Path(
        str(
            acquisition_ref.get("path")
            or source_artifacts.get("source_acquisition_v1")
            or ""
        )
    ).expanduser()
    acquisition: dict[str, Any] = {}
    acquisition_valid = False
    if acquisition_path.is_file():
        try:
            acquisition = read_json(acquisition_path)
        except (OSError, json.JSONDecodeError):
            errors.append("Source acquisition lineage is unreadable.")
        else:
            recorded_ref_sha = str(acquisition_ref.get("sha256") or "").lower()
            acquisition_sha = sha256_file(acquisition_path)
            if recorded_ref_sha and recorded_ref_sha != acquisition_sha:
                errors.append("Source acquisition lineage SHA-256 changed.")
            acquisition_valid = (
                str(acquisition.get("case_id") or "") == case_id
                and str(
                    acquisition.get("stable_video_id")
                    or acquisition.get("case_id")
                    or ""
                )
                == case_id
                and str(acquisition.get("source_url") or "") == source_url
                and str(acquisition.get("platform") or "").lower() == "douyin"
            )
            if not acquisition_valid:
                errors.append("Source acquisition lineage does not match the Case.")

    recorded_sha = str(
        provenance.get("recorded_source_media_sha256")
        or video.get("sha256")
        or acquisition.get("source_video_sha256")
        or ""
    ).strip().lower()

    if not acquisition_path.is_file():
        errors.append("Source acquisition lineage is missing.")

    if not re.fullmatch(r"[0-9a-f]{64}", recorded_sha):
        errors.append("Recorded source media SHA-256 is missing or invalid.")
    if (
        acquisition
        and str(acquisition.get("source_video_sha256") or "").lower()
        != recorded_sha
    ):
        errors.append("Recorded source media SHA-256 does not match acquisition lineage.")
    if local_exists and sha256_file(video_path) != recorded_sha:
        errors.append("Available local source bytes do not match recorded SHA-256.")

    metadata_ref = provenance.get("source_metadata_ref") or {}
    metadata_path = Path(
        str(
            metadata_ref.get("path")
            or source_artifacts.get("source_metadata_v1")
            or (source_evidence.get("metadata") or {}).get("path")
            or acquisition.get("metadata")
            or ""
        )
    ).expanduser()
    metadata_valid = metadata_path.is_file()
    if not metadata_valid:
        errors.append("Retained source metadata is missing.")
    elif metadata_ref.get("sha256") and sha256_file(metadata_path) != str(
        metadata_ref["sha256"]
    ).lower():
        errors.append("Retained source metadata SHA-256 changed.")

    normalized = {
        "status": "traceable" if not errors else "invalid",
        "traceable": not errors,
        "platform": platform,
        "source_url": source_url,
        "source_url_present": bool(source_url),
        "stable_video_id": stable_video_id,
        "stable_identity_present": bool(stable_video_id),
        "recorded_source_sha256": recorded_sha or None,
        "source_acquisition_path": str(acquisition_path),
        "acquisition_lineage_valid": acquisition_valid,
        "source_metadata_path": str(metadata_path),
        "source_metadata_valid": metadata_valid,
        "local_source_path": str(video_path),
        "local_source_exists": local_exists,
        "local_source_sha256": sha256_file(video_path) if local_exists else None,
        "recorded_sha_matches": (
            sha256_file(video_path) == recorded_sha if local_exists and recorded_sha else None
        ),
        "compatibility_mode": None,
        "semantics": "identity_and_acquisition_lineage_not_reuse_permission",
    }
    return normalized, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Explicitly approve a reviewed Canonical Case V1. "
            "This is a human gate; the script never auto-approves."
        )
    )
    parser.add_argument(
        "--case",
        required=True,
        help="Path to case_v1.json",
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Human reviewer name/identifier",
    )
    parser.add_argument(
        "--note",
        default=(
            "Human review passed against retained source provenance, the Douyin "
            "original source, and Reverse Storyboard V1.1."
        ),
    )
    parser.add_argument(
        "--governance-policy",
        default=None,
        help=(
            "Approved/Frozen Case Source Governance V1 policy. Required for Cases "
            "that contain the legacy source_rights_gate field."
        ),
    )
    parser.add_argument(
        "--evidence-review-receipt",
        default=None,
        help="Explicit final human confirmation bound to a provisional Case candidate and its evidence hashes.",
    )
    args = parser.parse_args()

    case_path = Path(args.case).expanduser().resolve()
    if not case_path.exists():
        raise FileNotFoundError(case_path)

    original_bytes = case_path.read_bytes()
    original_sha256 = sha256_bytes(original_bytes)
    case = json.loads(original_bytes.decode("utf-8"))

    errors: list[str] = []

    lifecycle = case.get("lifecycle", {})
    validation = case.get("validation", {})
    visual = case.get("visual_evidence", {})
    storyboard = case.get("storyboard", {})
    quality = case.get("quality", {})
    pattern_state = case.get("pattern_state", {})
    privacy_gate = case.get("privacy_gate", {})
    source_artifacts = case.get("source_artifacts", {})
    governance_context: dict[str, Any] | None = None
    source_provenance, source_provenance_errors = validate_source_provenance(case)
    errors.extend(source_provenance_errors)
    evidence_receipt, evidence_errors = validate_deferred_evidence_review(
        case,
        original_sha256,
        Path(args.evidence_review_receipt).expanduser().resolve() if args.evidence_review_receipt else None,
        args.reviewer,
    )
    errors.extend(evidence_errors)

    if lifecycle.get("status") != "review_required":
        errors.append(
            f"Expected lifecycle.status='review_required', got {lifecycle.get('status')!r}"
        )

    if lifecycle.get("approved") is True:
        errors.append("Case is already approved.")

    if validation.get("passed") is not True:
        errors.append("Case validation.passed is not true.")

    try:
        validate_case_privacy_gate(case)
    except RuntimeError as exc:
        errors.append(str(exc))

    if visual.get("coverage_label") != "candidate_complete":
        errors.append(
            "Visual coverage is not candidate_complete."
        )

    shots = storyboard.get("shots") or []
    if not shots:
        errors.append("Storyboard contains no shots.")

    if quality.get("human_review_required") is not True:
        errors.append(
            "Case does not declare human_review_required=true."
        )

    video_understanding = storyboard.get("video_understanding", {})
    verified_proofs = video_understanding.get("verified_proofs")
    if not isinstance(verified_proofs, list):
        errors.append("Storyboard verified_proofs is not a list.")
        verified_proofs = []
    if quality.get("verified_proof_count") != len(verified_proofs):
        errors.append(
            "quality.verified_proof_count does not match effective Storyboard proofs."
        )

    expected_claims_semantics = (
        "candidate_unverified_unless_supported_by_verified_proofs"
    )
    if storyboard.get("claims_semantics") != expected_claims_semantics:
        errors.append("Storyboard claims semantics is not candidate/unverified.")

    strong_claim_statuses = {
        "verified",
        "evidence_backed",
        "evidence-backed",
        "proved",
        "proven",
    }
    claims = list(video_understanding.get("claims") or [])
    if not verified_proofs:
        for index, claim in enumerate(claims, start=1):
            status = str(claim.get("status") or "").strip().lower()
            if status in strong_claim_statuses:
                errors.append(
                    f"Claim {index} is marked {status!r} without a verified proof."
                )

    if pattern_state.get("pattern_mining_performed") is not False:
        errors.append("Pattern mining must remain not_performed at Case approval.")

    frozen_paths: dict[str, Path] = {}
    artifact_keys = {
        "reverse_storyboard_v1": "storyboard_v1",
        "privacy_projection_v1": "privacy_projection_v1",
    }
    for receipt_name, source_key in artifact_keys.items():
        value = source_artifacts.get(source_key)
        if not value:
            errors.append(f"Missing source_artifacts.{source_key}.")
            continue
        path = Path(str(value)).expanduser().resolve()
        if not path.is_file():
            errors.append(f"Approval source artifact does not exist: {path}")
            continue
        frozen_paths[receipt_name] = path

    if case.get("source_rights_gate") is not None:
        if not args.governance_policy:
            errors.append(
                "Case has a legacy source_rights_gate field; approved/frozen "
                "Case Source Governance V1 policy is required."
            )
        else:
            policy_path = Path(args.governance_policy).expanduser().resolve()
            if not policy_path.is_file():
                errors.append(f"Governance policy does not exist: {policy_path}")
            else:
                policy = read_json(policy_path)
                if (
                    policy.get("schema_version")
                    != "case-source-governance-policy-v1.0"
                    or policy.get("status") != "approved_frozen"
                    or policy.get("version") != "V1.0"
                ):
                    errors.append("Case Source Governance policy is not Approved/Frozen V1.0.")
                if policy.get("reviewer") != args.reviewer:
                    errors.append("Case reviewer does not match Governance policy reviewer.")
                decisions = policy.get("pending_case_human_governance_decisions") or []
                decision = next(
                    (
                        item
                        for item in decisions
                        if str(item.get("case_id")) == str(case.get("case_id"))
                    ),
                    None,
                )
                if not decision:
                    errors.append("Governance policy has no Human decision for this Case.")
                elif (
                    decision.get("canonical_case_decision") != "approve"
                    or decision.get("research_ingestion_eligibility")
                    != "eligible_for_internal_research"
                    or decision.get("media_reuse_rights") != "not_established"
                    or decision.get("human_structural_profile_decision") != "pass"
                ):
                    errors.append("Governance policy decision is not eligible for Case approval.")
                governance_context = {
                    "policy_path": str(policy_path),
                    "policy_sha256": sha256_file(policy_path),
                    "policy_version": policy.get("version"),
                    "research_ingestion_eligibility": (
                        (decision or {}).get("research_ingestion_eligibility")
                    ),
                    "media_reuse_rights": (decision or {}).get("media_reuse_rights"),
                    "case_approval_scope": (
                        (policy.get("canonical_case_approval") or {}).get(
                            "authorization_scope"
                        )
                    ),
                }

    privacy_path = frozen_paths.get("privacy_projection_v1")
    if privacy_path is not None:
        privacy_projection = read_json(privacy_path)
        projection_policy = str(
            privacy_projection.get("privacy_policy_version")
            or privacy_projection.get("policy_version")
            or ""
        )
        gate_policy = str(
            privacy_gate.get("privacy_policy_version")
            or privacy_gate.get("policy_version")
            or ""
        )
        if not projection_policy or gate_policy != projection_policy:
            errors.append(
                "Case privacy policy version does not match Privacy Projection."
            )
        projection_sha256 = sha256_file(privacy_path)
        recorded_projection_sha256 = str(
            privacy_gate.get("source_projection_sha256") or ""
        ).lower()
        if recorded_projection_sha256 != projection_sha256:
            errors.append(
                "Case privacy projection SHA-256 does not match the source artifact."
            )

    if errors:
        print("\nCASE APPROVAL BLOCKED")
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(2)

    approved_at = now_iso()

    lifecycle["status"] = "approved"
    lifecycle["approved"] = True
    lifecycle["approved_at"] = approved_at
    lifecycle["approved_by"] = args.reviewer
    lifecycle["approval_note"] = args.note

    case["lifecycle"] = lifecycle

    case["approval"] = {
        "decision": "approved",
        "reviewer": args.reviewer,
        "approved_at": approved_at,
        "note": args.note,
        "review_basis": [
            "source_provenance",
            "douyin_original_source",
            "reverse_storyboard_v1_1",
            "audio_evidence",
            "visual_evidence",
            "shot_roles",
            "proof_boundary",
        ],
        "human_gate": True,
        "source_traceability": source_provenance,
    }
    if governance_context is not None:
        case["approval"]["source_governance"] = governance_context
        case["approval"]["media_reuse_authorized"] = False
    if evidence_receipt is not None:
        case["approval"]["evidence_review"] = {
            "receipt_sha256": sha256_file(Path(args.evidence_review_receipt)),
            "narration_decision_count": len(evidence_receipt["narration_decisions"]),
            "shot_decision_count": len(evidence_receipt["shot_decisions"]),
            "reviewed_by": evidence_receipt["reviewed_by"],
            "reviewed_at": evidence_receipt["reviewed_at"],
            "policy": "source_asr_and_current_shot_boundaries_explicitly_confirmed",
        }
        case["review_pending"]["status"] = "confirmed_at_final_case_review"
        case.setdefault("narration_evidence", {})["manual_review_closed"] = True
        case["validation"]["narration_review_closed"] = True
        case["validation"]["boundary_review_closed"] = True

    case.setdefault("quality", {})
    case["quality"]["human_review_required"] = False
    case["quality"]["human_review_completed"] = True

    case.setdefault("validation", {})
    case["validation"]["human_approval_completed"] = True
    case["validation"]["auto_approved"] = False

    approved_sha256 = write_atomic_json(
        case_path,
        case,
    )

    receipt = {
        "case_id": case.get("case_id"),
        "decision": "approved",
        "reviewer": args.reviewer,
        "approved_at": approved_at,
        "note": args.note,
        "human_gate": True,
        "case_path": str(case_path),
        "case_sha256_before_approval": original_sha256,
        "case_sha256_after_approval": approved_sha256,
        "frozen_artifacts": {
            name: {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for name, path in frozen_paths.items()
        },
        "source_provenance": source_provenance,
    }
    if governance_context is not None:
        receipt["source_governance"] = governance_context
        receipt["case_approval_grants_media_reuse"] = False

    receipt_path = case_path.parent / "approval_receipt.json"
    write_atomic_json(receipt_path, receipt)

    print()
    print("CASE APPROVAL PASS")
    print(f"Case ID: {case.get('case_id')}")
    print("Status: approved")
    print("Approved: True")
    print(f"Reviewer: {args.reviewer}")
    print(f"Approved at: {approved_at}")
    print(f"Case: {case_path}")
    print(f"Receipt: {receipt_path}")


if __name__ == "__main__":
    main()
