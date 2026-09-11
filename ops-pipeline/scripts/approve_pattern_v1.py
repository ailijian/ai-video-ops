from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APPROVABLE_PATTERN_ID = "pcv1_narration_led_process_projection"
REJECTED_PATTERN_ID = "pcv1_multimodal_hook_no_explicit_cta"
AMENDMENT_PROFILE = "narration-led-process-projection-v1"
APPROVAL_NOTE = (
    "Human review confirmed that the cross-case structure is supported by all "
    "three Approved Cases after removing analysis-architecture and Proof-authority "
    "rules from the creative Pattern definition."
)
REJECTION_REASON = (
    "The current evidence shows co-occurrence but does not establish a stable "
    "structural relationship between the multimodal hook and the absence of an "
    "explicit CTA."
)
FORBIDDEN_DEFINITION_TERMS = (
    "many-to-many",
    "many_to_many",
    "verified proof",
    "verified-proof",
    "proof authority",
    "process != proof",
    "process != proof",
    "track representation",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    payload = json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    return sha256_bytes(payload)


def replace_json(path: Path, value: dict[str, Any]) -> str:
    payload = json_bytes(value)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return sha256_bytes(payload)


def validate_candidate_and_research(
    candidate_path: Path,
    research_path: Path,
    expected_pattern_id: str,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    candidate_path = candidate_path.expanduser().resolve()
    research_path = research_path.expanduser().resolve()
    if not candidate_path.is_file():
        raise FileNotFoundError(candidate_path)
    if not research_path.is_file():
        raise FileNotFoundError(research_path)

    candidate_sha = sha256_file(candidate_path)
    research_sha = sha256_file(research_path)
    candidate = read_json(candidate_path)
    research = read_json(research_path)
    errors: list[str] = []

    if candidate.get("pattern_id") != expected_pattern_id:
        errors.append("Candidate Pattern ID does not match the requested decision.")
    if candidate.get("status") != "candidate":
        errors.append(f"Expected Candidate status, got {candidate.get('status')!r}.")
    if candidate.get("authority", {}).get("candidate_only") is not True:
        errors.append("Source artifact does not declare candidate-only authority.")
    if candidate.get("authority", {}).get("human_review_required") is not True:
        errors.append("Source Candidate does not require Human Review.")
    if candidate.get("effectiveness", {}).get("status") != "unvalidated":
        errors.append("Candidate effectiveness must remain unvalidated.")
    if candidate.get("effectiveness", {}).get("performance_data_used") is not False:
        errors.append("Candidate unexpectedly used performance data.")

    scope = candidate.get("scope", {})
    case_ids = sorted(str(value) for value in scope.get("supported_case_ids", []))
    if scope.get("supported_case_count") != 3 or len(case_ids) != 3:
        errors.append("Pattern Human Review requires exactly three supporting Cases.")
    evidence_ids = sorted(
        str(item.get("case_id")) for item in candidate.get("evidence", [])
    )
    if evidence_ids != case_ids:
        errors.append("Candidate evidence does not cover each supporting Case exactly once.")

    if research.get("validation", {}).get("passed") is not True:
        errors.append("Source Pattern Research validation is not passed.")
    if research.get("authority", {}).get("remote_model_used") is not False:
        errors.append("Source Pattern Research has unexpected Remote Model authority.")
    if expected_pattern_id not in research.get("pattern_candidate_ids", []):
        errors.append("Source Pattern Research does not reference this Candidate.")
    if sorted(str(value) for value in research.get("case_ids", [])) != case_ids:
        errors.append("Candidate and Pattern Research supporting Case IDs do not match.")

    research_fingerprints = {
        str(item.get("case_id")): str(item.get("fingerprint_sha") or "").lower()
        for item in research.get("case_sources", [])
    }
    candidate_fingerprints = {
        str(case_id): str(value).lower()
        for case_id, value in candidate.get("lineage", {})
        .get("fingerprint_sha256", {})
        .items()
    }
    if candidate_fingerprints != research_fingerprints:
        errors.append("Candidate Fingerprint SHA lineage does not match Pattern Research.")

    if errors:
        raise RuntimeError("Pattern Human Review blocked: " + " ".join(errors))
    return candidate, research, candidate_sha, research_sha


def approved_definition() -> dict[str, Any]:
    return {
        "summary": (
            "Narration forms the primary semantic spine while real operating, service, "
            "or making-process scenes continuously project concrete context, persona, "
            "process, and product information. Visual scenes need not repeat narration "
            "line by line and may add business context and specificity beyond it."
        ),
        "invariants": [
            "Narration is the primary semantic spine.",
            "Real operating, service, or making-process scenes carry the primary visual projection.",
            "The audio semantic line and visual scenes do not require sentence-by-sentence or one-to-one correspondence; visuals may reinforce, supplement, or contextualize narration.",
            "Real process scenes give abstract viewpoints, lived experience, or service narratives concrete settings and specificity.",
        ],
        "variants": [
            "The industry and the specific operating, service, or making process shown.",
            "The balance among context, persona, process, action, and product imagery.",
            "How tightly each scene corresponds to the nearby narration.",
            "Duration, shot rhythm, narrative stages, and payoff wording.",
            "On-screen-text coverage and whether text repeats or supplements narration.",
        ],
        "non_defining_traits": [
            "A particular food or plant-service category.",
            "A fixed duration or cutting speed.",
            "A specific owner persona or product share.",
            "The presence of narration or process footage considered separately.",
        ],
    }


def assert_clean_definition(definition: dict[str, Any]) -> None:
    serialized = json.dumps(definition, ensure_ascii=False).lower()
    found = [term for term in FORBIDDEN_DEFINITION_TERMS if term in serialized]
    if found:
        raise RuntimeError(
            "Approved Pattern definition contains architecture or Proof terms: "
            + ", ".join(found)
        )


def creative_evidence(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for item in candidate.get("evidence", []):
        observed = item.get("observed", {})
        evidence.append(
            {
                "case_id": item.get("case_id"),
                "fingerprint_sha": item.get("fingerprint_sha"),
                "supporting_features": [
                    "narration_semantic_lead",
                    "visual_process_context_or_product_projection",
                    "visual_reinforcement_supplement_or_contextualization",
                ],
                "observed": {
                    "speech_ratio": observed.get("speech_ratio"),
                    "primary_role_counts": observed.get("primary_role_counts", {}),
                    "scene_relation_counts": observed.get("scene_relation_counts", {}),
                },
            }
        )
    return evidence


def approve_pattern(
    candidate_path: Path,
    research_path: Path,
    output_root: Path,
    reviewer: str,
    note: str = APPROVAL_NOTE,
    approved_at: str | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    candidate_path = candidate_path.expanduser().resolve()
    research_path = research_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    candidate, _research, candidate_sha, research_sha = validate_candidate_and_research(
        candidate_path, research_path, APPROVABLE_PATTERN_ID
    )
    pattern_dir = output_root / APPROVABLE_PATTERN_ID
    pattern_path = pattern_dir / "pattern_v1.json"
    receipt_path = pattern_dir / "approval_receipt.json"
    if pattern_path.exists() or receipt_path.exists():
        raise RuntimeError(
            "Approved Pattern or receipt already exists; repeated approval cannot overwrite it."
        )

    definition = approved_definition()
    assert_clean_definition(definition)
    timestamp = approved_at or now_iso()
    scope = copy.deepcopy(candidate.get("scope", {}))
    scope["current_generalization_limit"] = (
        "Supported only by the current three Approved operator/business-story style "
        "Cases across food and plant-service contexts. It is not generalized to all "
        "local businesses, commercial short videos, or service industries."
    )
    pattern = {
        "schema_version": "pattern-v1.0",
        "pattern_id": APPROVABLE_PATTERN_ID,
        "status": "approved",
        "working_name": "Narration-led Process Projection",
        "definition": definition,
        "scope": scope,
        "evidence": creative_evidence(candidate),
        "contradicting_evidence": copy.deepcopy(
            candidate.get("contradicting_evidence", [])
        ),
        "analysis_notes": [
            "Human Review removed internal track representation and Proof-authority rules from the creative Pattern definition.",
            "The amendment changes definition authority only and does not rerun or reinterpret the source Cases.",
        ],
        "authority_constraints": {
            "internal_audio_visual_track_representation_is_not_a_pattern_invariant": True,
            "proof_authority_is_not_a_creative_pattern_invariant": True,
            "source_proof_state_inherited_without_reinterpretation": True,
            "remote_model_used": False,
        },
        "effectiveness": {
            "status": "unvalidated",
            "performance_data_used": False,
            "causal_or_performance_claims_permitted": False,
        },
        "lineage": {
            "source_candidate": {
                "path": str(candidate_path),
                "sha256": candidate_sha,
            },
            "source_research": {
                "path": str(research_path),
                "sha256": research_sha,
            },
            "supporting_case_ids": scope.get("supported_case_ids", []),
            "supporting_approved_case_sha256": copy.deepcopy(
                candidate.get("lineage", {}).get("approved_case_sha256", {})
            ),
            "supporting_fingerprint_sha256": copy.deepcopy(
                candidate.get("lineage", {}).get("fingerprint_sha256", {})
            ),
        },
        "approval": {
            "decision": "approved_after_definition_amendment",
            "reviewer": reviewer,
            "approved_at": timestamp,
            "note": note,
            "human_gate": True,
            "amendment_applied": True,
            "amendment_profile": AMENDMENT_PROFILE,
            "removed_from_creative_invariants": [
                "internal many-to-many track representation",
                "Process versus Proof system authority",
                "Verified Proof authority",
            ],
        },
        "validation": {
            "passed": True,
            "supporting_case_count": scope.get("supported_case_count"),
            "supporting_case_count_is_three": scope.get("supported_case_count") == 3,
            "definition_architecture_terms_absent": True,
            "definition_proof_authority_terms_absent": True,
            "effectiveness_unvalidated": True,
            "source_candidate_sha_frozen": True,
            "source_research_sha_frozen": True,
            "human_approval_required_and_completed": True,
            "remote_model_call_performed": False,
        },
    }
    pattern_sha = write_new_json(pattern_path, pattern)
    receipt = {
        "schema_version": "pattern-approval-receipt-v1.0",
        "pattern_id": APPROVABLE_PATTERN_ID,
        "decision": "approved_after_definition_amendment",
        "reviewer": reviewer,
        "approved_at": timestamp,
        "note": note,
        "human_gate": True,
        "amendment_applied": True,
        "amendment_profile": AMENDMENT_PROFILE,
        "source_candidate": {
            "path": str(candidate_path),
            "sha256": candidate_sha,
        },
        "source_research": {
            "path": str(research_path),
            "sha256": research_sha,
        },
        "supporting_case_ids": scope.get("supported_case_ids", []),
        "supporting_fingerprint_sha256": copy.deepcopy(
            candidate.get("lineage", {}).get("fingerprint_sha256", {})
        ),
        "approved_pattern": {
            "path": str(pattern_path),
            "sha256": pattern_sha,
        },
        "remote_model_call_performed": False,
    }
    write_new_json(receipt_path, receipt)
    return pattern_path, receipt_path, pattern, receipt


def reject_candidate(
    candidate_path: Path,
    research_path: Path,
    approved_root: Path,
    reviewer: str,
    reason: str = REJECTION_REASON,
    reviewed_at: str | None = None,
) -> tuple[dict[str, Any], str, str]:
    candidate_path = candidate_path.expanduser().resolve()
    research_path = research_path.expanduser().resolve()
    approved_root = approved_root.expanduser().resolve()
    candidate, _research, candidate_sha, research_sha = validate_candidate_and_research(
        candidate_path, research_path, REJECTED_PATTERN_ID
    )
    approved_path = approved_root / REJECTED_PATTERN_ID / "pattern_v1.json"
    if approved_path.exists():
        raise RuntimeError("Rejected Candidate already has an Approved Pattern artifact.")

    timestamp = reviewed_at or now_iso()
    reviewed = copy.deepcopy(candidate)
    reviewed["status"] = "review_rejected"
    reviewed["human_review"] = {
        "decision": "not_approved",
        "reviewer": reviewer,
        "reviewed_at": timestamp,
        "reason": reason,
        "human_gate": True,
        "source_candidate_sha256_before_review": candidate_sha,
        "source_research_path": str(research_path),
        "source_research_sha256": research_sha,
    }
    reviewed["research_disposition"] = {
        "rejected_relationship": (
            "multimodal_hook_plus_absence_of_explicit_cta_as_one_pattern"
        ),
        "retained_hypothesis": {
            "hypothesis_id": "H002A",
            "working_name": "Multimodal Hook Hypothesis",
            "status": "research_hypothesis",
            "statement": (
                "Operator/business-story style content may combine audio hook, visual "
                "text hook, and visual scene hook to establish the opening."
            ),
            "supporting_case_ids": copy.deepcopy(
                candidate.get("scope", {}).get("supported_case_ids", [])
            ),
            "human_review_required_for_future_candidate": True,
        },
        "observed_traits": [
            {
                "trait": "no_explicit_cta",
                "status": "observed_trait",
                "supporting_case_ids": copy.deepcopy(
                    candidate.get("scope", {}).get("supported_case_ids", [])
                ),
                "pattern_invariant": False,
            }
        ],
        "case_4_selection_target": {
            "operator_or_service_style": True,
            "narration_present": True,
            "real_operating_process_present": True,
            "explicit_cta_present": True,
            "research_goals": [
                "Attack the generalization boundary of Narration-led Process Projection.",
                "Test whether the Multimodal Hook Hypothesis stands independently.",
                "Use an Explicit CTA contrast to test whether no Explicit CTA is only a sample trait.",
            ],
            "auto_start_case_4": False,
        },
    }
    reviewed.setdefault("authority", {})
    reviewed["authority"].update(
        {
            "candidate_only": True,
            "human_review_required": False,
            "human_review_completed": True,
            "approved_pattern_created": False,
            "remote_model_used": False,
        }
    )
    reviewed.setdefault("validation", {})
    reviewed["validation"].update(
        {
            "status_is_candidate": False,
            "human_review_terminal_status": True,
            "approved_pattern_created": False,
            "source_candidate_sha_frozen": True,
            "source_research_sha_frozen": True,
            "source_research_retained": research_path.is_file(),
            "remote_model_call_performed": False,
        }
    )
    reviewed_sha = replace_json(candidate_path, reviewed)
    return reviewed, candidate_sha, reviewed_sha


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply an explicit Human Review decision to a Pattern Candidate without "
            "rerunning Pattern Research or using a Remote Model."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    approve_parser = subparsers.add_parser(
        "approve-amended",
        help="Approve Narration-led Process Projection with its reviewed definition.",
    )
    approve_parser.add_argument("--candidate", required=True)
    approve_parser.add_argument("--research", required=True)
    approve_parser.add_argument("--reviewer", required=True)
    approve_parser.add_argument("--note", default=APPROVAL_NOTE)
    approve_parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/patterns/approved",
    )

    reject_parser = subparsers.add_parser(
        "reject",
        help="Record terminal Human Review rejection while retaining research lineage.",
    )
    reject_parser.add_argument("--candidate", required=True)
    reject_parser.add_argument("--research", required=True)
    reject_parser.add_argument("--reviewer", required=True)
    reject_parser.add_argument("--reason", default=REJECTION_REASON)
    reject_parser.add_argument(
        "--approved-root",
        default=None,
        help="Default: <project>/data/patterns/approved",
    )

    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    approved_root = (
        Path(args.output_root if args.command == "approve-amended" else args.approved_root)
        .expanduser()
        .resolve()
        if (args.output_root if args.command == "approve-amended" else args.approved_root)
        else project_root / "data" / "patterns" / "approved"
    )

    if args.command == "approve-amended":
        pattern_path, receipt_path, pattern, receipt = approve_pattern(
            Path(args.candidate),
            Path(args.research),
            approved_root,
            args.reviewer,
            args.note,
        )
        print("PATTERN APPROVAL PASS")
        print(f"Pattern ID: {pattern['pattern_id']}")
        print("Status: approved")
        print(f"Reviewer: {args.reviewer}")
        print(f"Approved at: {pattern['approval']['approved_at']}")
        print(f"Pattern SHA-256: {receipt['approved_pattern']['sha256']}")
        print(f"Pattern: {pattern_path}")
        print(f"Receipt: {receipt_path}")
    else:
        reviewed, before_sha, after_sha = reject_candidate(
            Path(args.candidate),
            Path(args.research),
            approved_root,
            args.reviewer,
            args.reason,
        )
        print("PATTERN CANDIDATE REVIEW PASS")
        print(f"Pattern ID: {reviewed['pattern_id']}")
        print("Status: review_rejected")
        print(f"Reviewer: {args.reviewer}")
        print(f"Candidate SHA-256 before review: {before_sha}")
        print(f"Candidate SHA-256 after review: {after_sha}")
        print("Approved Pattern created: False")


if __name__ == "__main__":
    main()
