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
NEWS_PRICE_PATTERN_ID = "pcv1_news_price_offer_led_micro_information"
NEWS_SCENE_PATTERN_ID = "pcv1_news_scene_contrast"
NEWS_PATTERN_IDS = (NEWS_PRICE_PATTERN_ID, NEWS_SCENE_PATTERN_ID)
NEWS_APPROVAL_PROFILE = "news-pattern-deletion-normalization-v1"
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


def _validated_ref(ref: dict[str, Any], label: str) -> tuple[Path, str]:
    path = Path(str(ref.get("path") or "")).expanduser().resolve()
    expected_sha = str(ref.get("sha256") or "").lower()
    if not path.is_file():
        raise FileNotFoundError(f"{label}: {path}")
    actual_sha = sha256_file(path)
    if not expected_sha or actual_sha != expected_sha:
        raise RuntimeError(f"{label} SHA lineage does not match its source artifact.")
    return path, actual_sha


def validate_news_pattern_candidate_for_approval(
    candidate_path: Path,
    registry_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Validate a News Candidate and every frozen source ref without mutating it."""
    candidate_path = candidate_path.expanduser().resolve()
    registry_path = registry_path.expanduser().resolve()
    if not candidate_path.is_file():
        raise FileNotFoundError(candidate_path)
    if not registry_path.is_file():
        raise FileNotFoundError(registry_path)

    candidate_sha = sha256_file(candidate_path)
    registry_sha = sha256_file(registry_path)
    candidate = read_json(candidate_path)
    registry = read_json(registry_path)
    errors: list[str] = []

    pattern_id = candidate.get("pattern_id")
    if pattern_id not in NEWS_PATTERN_IDS:
        errors.append("Candidate is not one of the Human-approved News Pattern IDs.")
    if candidate.get("schema_version") != "pattern-candidate-v1.0":
        errors.append("Candidate schema is not pattern-candidate-v1.0.")
    if candidate.get("status") != "review_required":
        errors.append("News Candidate must be review_required before approval.")
    if candidate.get("candidate_state") != "candidate":
        errors.append("News Candidate state is not candidate.")
    if candidate.get("compatible_profile_candidate") != ["news"]:
        errors.append("News Candidate compatibility must be [news].")
    authority = candidate.get("authority") or {}
    if authority.get("candidate_only") is not True:
        errors.append("Candidate does not declare candidate-only authority.")
    if authority.get("human_review_required") is not True:
        errors.append("Candidate did not stop at its Human Review gate.")
    effectiveness = candidate.get("effectiveness") or {}
    if effectiveness.get("status") != "unvalidated":
        errors.append("Candidate Effectiveness must remain unvalidated.")
    if effectiveness.get("performance_data_available") is not False:
        errors.append("Candidate unexpectedly declares Performance Data.")
    if effectiveness.get("performance_data_used") is not False:
        errors.append("Candidate unexpectedly used Performance Data.")

    scope = candidate.get("scope") or {}
    case_ids = [str(value) for value in scope.get("supported_case_ids") or []]
    evidence = candidate.get("evidence") or []
    if scope.get("supported_case_count") != 3 or len(case_ids) != 3:
        errors.append("News Pattern Approval requires exactly three Evidence Cases.")
    if sorted(str(item.get("case_id")) for item in evidence) != sorted(case_ids):
        errors.append("Candidate Evidence does not match the three supporting Case IDs.")

    registry_news = (registry.get("profiles") or {}).get("news") or {}
    if registry.get("status") != "approved_frozen":
        errors.append("Production Profile Registry is not Approved / Frozen.")
    if registry_news.get("profile_id") != "news":
        errors.append("Frozen Registry does not contain the News Profile.")
    if registry_news.get("storyboard_contract", {}).get(
        "narration_many_to_many_required"
    ) is not False:
        errors.append("Frozen News Profile does not own narration independence.")

    lineage = candidate.get("lineage") or {}
    comparison_ref = lineage.get("comparison_ref") or {}
    approval_ref = lineage.get("comparison_human_approval_ref") or {}
    try:
        comparison_path, comparison_sha = _validated_ref(
            comparison_ref, "Cross-case Comparison"
        )
        approval_path, _approval_sha = _validated_ref(
            approval_ref, "Comparison Human Approval"
        )
        comparison = read_json(comparison_path)
        comparison_approval = read_json(approval_path)
        if comparison.get("status") != "review_required":
            errors.append("Source Comparison status changed unexpectedly.")
        if comparison.get("validation", {}).get("passed") is not True:
            errors.append("Source Comparison validation is not passed.")
        if comparison.get("authority", {}).get("remote_model_used") is not False:
            errors.append("Source Comparison has unexpected Remote Model authority.")
        if comparison_approval.get("status") != "approved":
            errors.append("Comparison Human Approval is not approved.")
        if comparison_approval.get("decision") != "approve_research_comparison":
            errors.append("Comparison Human Approval decision is invalid.")
        if (
            comparison_approval.get("approval_scope")
            != "research_comparison_only_not_pattern_approval"
        ):
            errors.append("Comparison approval scope was expanded unexpectedly.")
        if (
            comparison_approval.get("comparison_ref", {}).get("sha256")
            != comparison_sha
        ):
            errors.append("Comparison Human Approval does not bind the Comparison SHA.")
    except (FileNotFoundError, RuntimeError) as exc:
        errors.append(str(exc))

    for item in evidence:
        case_id = str(item.get("case_id"))
        for field, label in (
            ("approved_case_ref", "Approved Case"),
            ("fingerprint_ref", "Fingerprint"),
            ("micro_beat_storyboard_ref", "Micro Beat Storyboard"),
        ):
            try:
                source_path, source_sha = _validated_ref(
                    item.get(field) or {}, f"{label} {case_id}"
                )
                expected_map = {
                    "approved_case_ref": "case_sha256",
                    "fingerprint_ref": "fingerprint_sha256",
                    "micro_beat_storyboard_ref": "micro_beat_storyboard_sha256",
                }[field]
                if (lineage.get(expected_map) or {}).get(case_id) != source_sha:
                    errors.append(f"{label} {case_id} does not match Candidate lineage.")
                if field == "approved_case_ref":
                    source_case = read_json(source_path)
                    lifecycle = source_case.get("lifecycle") or {}
                    if lifecycle.get("status") != "approved" or lifecycle.get(
                        "approved"
                    ) is not True:
                        errors.append(f"Case {case_id} is not canonically Approved.")
            except (FileNotFoundError, RuntimeError) as exc:
                errors.append(str(exc))

    if errors:
        raise RuntimeError("News Pattern Human Review blocked: " + " ".join(errors))
    return candidate, registry, candidate_sha, registry_sha


def news_pattern_definition(candidate: dict[str, Any]) -> dict[str, Any]:
    pattern_id = candidate["pattern_id"]
    if pattern_id == NEWS_PRICE_PATTERN_ID:
        return {
            "summary": (
                "A price or offer is the first semantic anchor. Later recoverable "
                "micro-information states remain semantically tied to that offer and "
                "help contextualize, explain, scope, situate, or clarify its use/value context."
            ),
            "invariants": [
                "price_or_offer_first_semantic_anchor",
                "multiple_recoverable_micro_information_states_follow_the_anchor",
                "later_states_materially_contextualize_scope_explain_or_situate_the_offer",
            ],
            "semantic_relation_guard": {
                "required": True,
                "minimum_supported_function_count": 1,
                "supported_functions": [
                    "contextualize",
                    "explain",
                    "scope",
                    "situate",
                    "understand_use_or_value_context",
                ],
                "unrelated_b_roll_plus_persistent_price_text": "out_of_scope",
            },
            "variants": copy.deepcopy(candidate["definition"]["variants"]),
            "non_invariants": copy.deepcopy(
                candidate["definition"]["explicitly_not_frozen"]
            ),
        }
    if pattern_id == NEWS_SCENE_PATTERN_ID:
        return {
            "summary": (
                "Meaningful, comparable State A and State B form a recoverable visual "
                "information relationship whose difference materially changes understanding."
            ),
            "invariants": [
                "meaningful_comparable_state_a_and_state_b",
                "state_difference_materially_changes_understanding",
                "visual_information_state_is_primary_semantic_carrier",
            ],
            "variants": copy.deepcopy(candidate["definition"]["variants"]),
            "non_invariants": copy.deepcopy(
                candidate["definition"]["explicitly_not_frozen"]
            ),
        }
    raise RuntimeError(f"Unsupported News Pattern Candidate: {pattern_id}")


def build_news_approved_pattern(
    candidate_path: Path,
    registry_path: Path,
    reviewer: str,
    approved_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    candidate_path = candidate_path.expanduser().resolve()
    registry_path = registry_path.expanduser().resolve()
    candidate, _registry, candidate_sha, registry_sha = (
        validate_news_pattern_candidate_for_approval(candidate_path, registry_path)
    )
    timestamp = approved_at or now_iso()
    pattern_id = candidate["pattern_id"]
    definition = news_pattern_definition(candidate)
    evidence = copy.deepcopy(candidate["evidence"])
    lineage = candidate["lineage"]

    profile_constraint = {
        "constraint_id": "continuous_mix_narration_not_required_for_semantic_recovery",
        "owner": "production_profile:news",
        "authority": "inherited_profile_constraint",
        "pattern_owned_invariant": False,
        "registry_ref": {
            "path": str(registry_path),
            "sha256": registry_sha,
        },
    }
    scope = copy.deepcopy(candidate["scope"])
    if pattern_id == NEWS_PRICE_PATTERN_ID:
        scope.update(
            {
                "scope_limitation": "price_offer_led_only",
                "explicitly_not_supported": "generic_number_led",
            }
        )
    else:
        scope["production_scope_guard"] = {
            "explicit_recoverable_state_correspondence": "required",
            "same_subject_identity_requirement": "unresolved",
            "arbitrary_cross_subject_contrast": "out_of_scope",
            "same_person_identity_frozen": False,
            "same_object_identity_frozen": False,
            "same_place_identity_frozen": False,
        }

    pattern = {
        "schema_version": "pattern-v1.0",
        "pattern_id": pattern_id,
        "status": "approved",
        "working_name": candidate["working_name"],
        "compatible_profiles": ["news"],
        "profile_compatibility": {
            "status": "human_approved",
            "compatible_profiles": ["news"],
            "cross_profile_compatibility_is_automatic": False,
        },
        "definition": definition,
        "inherited_profile_constraints": [profile_constraint],
        "scope": scope,
        "evidence": evidence,
        "boundary_evidence": copy.deepcopy(candidate.get("boundary_evidence") or []),
        "unresolved_questions": copy.deepcopy(
            candidate.get("unresolved_questions") or []
        ),
        "transformation_action": (
            {
                "status": "optional_enhancer",
                "pattern_invariant": False,
                "allowed_variants": [
                    "actual_operation",
                    "overlay",
                    "transition",
                    "direct_state_a_b",
                    "repeated_comparison_catalogue",
                    "single_transformation",
                    "multiple_paired_comparisons",
                ],
            }
            if pattern_id == NEWS_SCENE_PATTERN_ID
            else None
        ),
        "proof_boundary": copy.deepcopy(candidate.get("proof_boundary") or {}),
        "effectiveness": {
            "status": "unvalidated",
            "performance_data_available": False,
            "performance_data_used": False,
            "causal_or_performance_claims_permitted": False,
        },
        "lineage": {
            "source_candidate": {
                "path": str(candidate_path),
                "sha256": candidate_sha,
            },
            "source_comparison": copy.deepcopy(lineage["comparison_ref"]),
            "source_comparison_human_approval": copy.deepcopy(
                lineage["comparison_human_approval_ref"]
            ),
            "supporting_case_ids": copy.deepcopy(scope["supported_case_ids"]),
            "supporting_case_sha256": copy.deepcopy(lineage["case_sha256"]),
            "supporting_fingerprint_sha256": copy.deepcopy(
                lineage["fingerprint_sha256"]
            ),
            "supporting_micro_beat_storyboard_sha256": copy.deepcopy(
                lineage["micro_beat_storyboard_sha256"]
            ),
        },
        "approval": {
            "decision": "approved_after_deletion_oriented_normalization",
            "reviewer": reviewer,
            "approved_at": timestamp,
            "human_gate": True,
            "normalization_profile": NEWS_APPROVAL_PROFILE,
            "removed_from_pattern_owned_invariants": [
                "continuous_mix_narration_not_required_for_semantic_recovery"
                if pattern_id == NEWS_PRICE_PATTERN_ID
                else "continuous_narration_not_required_for_semantic_recovery"
            ],
        },
        "authority_constraints": {
            "case_specific_facts_are_not_customer_authority": True,
            "proof_authority_unchanged": True,
            "profile_constraint_not_duplicated_as_pattern_authority": True,
            "pattern_approval_does_not_enable_news_generation": True,
            "pattern_approval_does_not_enable_news_export": True,
            "remote_model_used": False,
        },
        "validation": {
            "passed": True,
            "pattern_owned_invariant_count": 3,
            "supporting_case_count": 3,
            "source_candidate_sha_frozen": True,
            "source_comparison_sha_frozen": True,
            "source_comparison_approval_sha_frozen": True,
            "case_fingerprint_storyboard_lineage_verified": True,
            "effectiveness_unvalidated": True,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
            "remote_model_call_performed": False,
        },
    }
    if pattern_id == NEWS_SCENE_PATTERN_ID:
        pattern["proof_boundary"].update(
            {
                "observable_state_difference_is_not_verified_proof": True,
                "transformation_attribution_proven": False,
                "product_effect_attribution_proven": False,
            }
        )

    receipt = {
        "schema_version": "pattern-approval-receipt-v1.0",
        "pattern_id": pattern_id,
        "decision": "approved_after_deletion_oriented_normalization",
        "reviewer": reviewer,
        "approved_at": timestamp,
        "human_gate": True,
        "compatible_profiles": ["news"],
        "normalization_profile": NEWS_APPROVAL_PROFILE,
        "source_candidate": copy.deepcopy(pattern["lineage"]["source_candidate"]),
        "source_comparison": copy.deepcopy(pattern["lineage"]["source_comparison"]),
        "source_comparison_human_approval": copy.deepcopy(
            pattern["lineage"]["source_comparison_human_approval"]
        ),
        "supporting_case_ids": copy.deepcopy(scope["supported_case_ids"]),
        "supporting_evidence": [
            {
                "case_id": item["case_id"],
                "case_ref": copy.deepcopy(item["approved_case_ref"]),
                "fingerprint_ref": copy.deepcopy(item["fingerprint_ref"]),
                "micro_beat_storyboard_ref": copy.deepcopy(
                    item["micro_beat_storyboard_ref"]
                ),
            }
            for item in evidence
        ],
        "approved_pattern": None,
        "effectiveness_status": "unvalidated",
        "performance_data_used": False,
        "news_generation_enabled": False,
        "news_excel_export_performed": False,
        "remote_model_call_performed": False,
    }
    validate_news_approved_pattern(pattern)
    return pattern, receipt


def validate_news_approved_pattern(pattern: dict[str, Any]) -> None:
    pattern_id = pattern.get("pattern_id")
    if pattern_id not in NEWS_PATTERN_IDS or pattern.get("status") != "approved":
        raise ValueError("News Approved Pattern identity/status is invalid.")
    if pattern.get("compatible_profiles") != ["news"]:
        raise ValueError("News Approved Pattern compatibility must remain [news].")
    invariants = pattern.get("definition", {}).get("invariants") or []
    if len(invariants) != 3:
        raise ValueError("News Approved Pattern must have exactly three owned invariants.")
    profile_constraints = pattern.get("inherited_profile_constraints") or []
    if len(profile_constraints) != 1 or profile_constraints[0].get(
        "pattern_owned_invariant"
    ) is not False:
        raise ValueError("Narration independence must be inherited from News Profile.")
    if any("narration" in str(value) for value in invariants):
        raise ValueError("News Profile narration constraint was duplicated as an invariant.")
    if pattern_id == NEWS_PRICE_PATTERN_ID:
        scope = pattern.get("scope") or {}
        if scope.get("scope_limitation") != "price_offer_led_only":
            raise ValueError("Price Pattern scope expanded beyond price_offer_led_only.")
        if scope.get("explicitly_not_supported") != "generic_number_led":
            raise ValueError("Price Pattern must explicitly reject generic_number_led.")
        guard = pattern.get("definition", {}).get("semantic_relation_guard") or {}
        if guard.get("required") is not True or guard.get(
            "unrelated_b_roll_plus_persistent_price_text"
        ) != "out_of_scope":
            raise ValueError("Price post-anchor semantic relation guard is missing.")
    else:
        scope_guard = pattern.get("scope", {}).get("production_scope_guard") or {}
        if scope_guard.get("explicit_recoverable_state_correspondence") != "required":
            raise ValueError("Scene Pattern requires recoverable State A/B correspondence.")
        if scope_guard.get("same_subject_identity_requirement") != "unresolved":
            raise ValueError("Scene same-subject identity question must remain unresolved.")
        if scope_guard.get("arbitrary_cross_subject_contrast") != "out_of_scope":
            raise ValueError("Arbitrary cross-subject contrast must remain out of scope.")
        transformation = pattern.get("transformation_action") or {}
        if transformation.get("status") != "optional_enhancer" or transformation.get(
            "pattern_invariant"
        ) is not False:
            raise ValueError("Scene transformation action must remain optional_enhancer.")
        proof = pattern.get("proof_boundary") or {}
        if proof.get("state_difference_is_automatically_verified_proof") is not False:
            raise ValueError("Scene contrast cannot become Verified Proof.")
    effectiveness = pattern.get("effectiveness") or {}
    if effectiveness.get("status") != "unvalidated" or effectiveness.get(
        "performance_data_used"
    ) is not False:
        raise ValueError("News Pattern cannot claim Effectiveness.")


def approve_news_pattern(
    candidate_path: Path,
    registry_path: Path,
    output_root: Path,
    reviewer: str,
    approved_at: str | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    pattern, receipt = build_news_approved_pattern(
        candidate_path, registry_path, reviewer, approved_at
    )
    pattern_dir = output_root.expanduser().resolve() / pattern["pattern_id"]
    pattern_path = pattern_dir / "pattern_v1.json"
    receipt_path = pattern_dir / "approval_receipt.json"
    if pattern_path.exists() or receipt_path.exists():
        raise RuntimeError(
            "Approved Pattern or receipt already exists; repeated approval cannot overwrite it."
        )
    pattern_sha = write_new_json(pattern_path, pattern)
    receipt["approved_pattern"] = {
        "path": str(pattern_path),
        "sha256": pattern_sha,
    }
    write_new_json(receipt_path, receipt)
    return pattern_path, receipt_path, pattern, receipt


def build_news_pattern_coverage_update(
    pattern_paths: list[Path],
    receipt_paths: list[Path],
    registry_path: Path,
    coverage_baseline_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    if len(pattern_paths) != 2 or len(receipt_paths) != 2:
        raise ValueError("Coverage update requires exactly two News Patterns and receipts.")
    registry_path = registry_path.expanduser().resolve()
    coverage_baseline_path = coverage_baseline_path.expanduser().resolve()
    if not registry_path.is_file() or not coverage_baseline_path.is_file():
        raise FileNotFoundError("Registry and approved Coverage baseline are required.")

    approved_refs: list[dict[str, Any]] = []
    supporting_case_ids: set[str] = set()
    for pattern_path, receipt_path in zip(pattern_paths, receipt_paths):
        pattern_path = pattern_path.expanduser().resolve()
        receipt_path = receipt_path.expanduser().resolve()
        pattern = read_json(pattern_path)
        receipt = read_json(receipt_path)
        validate_news_approved_pattern(pattern)
        pattern_sha = sha256_file(pattern_path)
        receipt_sha = sha256_file(receipt_path)
        if receipt.get("pattern_id") != pattern.get("pattern_id"):
            raise RuntimeError("Pattern Approval receipt identity mismatch.")
        if receipt.get("decision") != "approved_after_deletion_oriented_normalization":
            raise RuntimeError("Pattern Approval receipt decision is invalid.")
        if receipt.get("approved_pattern", {}).get("sha256") != pattern_sha:
            raise RuntimeError("Pattern Approval receipt does not bind the Pattern SHA.")
        supporting_case_ids.update(pattern.get("scope", {}).get("supported_case_ids") or [])
        approved_refs.append(
            {
                "pattern_id": pattern["pattern_id"],
                "pattern_ref": {"path": str(pattern_path), "sha256": pattern_sha},
                "approval_receipt_ref": {
                    "path": str(receipt_path),
                    "sha256": receipt_sha,
                },
                "compatible_profiles": ["news"],
                "effectiveness_status": "unvalidated",
            }
        )
    if {item["pattern_id"] for item in approved_refs} != set(NEWS_PATTERN_IDS):
        raise RuntimeError("Coverage update did not receive both Approved News Patterns.")

    registry = read_json(registry_path)
    baseline = read_json(coverage_baseline_path)
    if registry.get("status") != "approved_frozen":
        raise RuntimeError("Production Profile Registry is not frozen.")
    if baseline.get("authority", {}).get("derived_planning_artifact") is not True:
        raise RuntimeError("Creative Coverage source is not the canonical derived baseline.")

    approved_refs.sort(key=lambda item: item["pattern_id"])
    return {
        "schema_version": "news-pattern-approval-creative-coverage-update-v1.0",
        "update_id": "news_pattern_approval_creative_coverage_update_v1",
        "status": "current_derived_coverage_update",
        "created_at": created_at or now_iso(),
        "source_refs": {
            "frozen_registry": {
                "path": str(registry_path),
                "sha256": sha256_file(registry_path),
                "source_artifact_modified": False,
            },
            "approved_coverage_baseline": {
                "path": str(coverage_baseline_path),
                "sha256": sha256_file(coverage_baseline_path),
                "source_artifact_modified": False,
            },
            "approved_news_patterns": approved_refs,
        },
        "news_current_coverage": {
            "operational_readiness": "production_validation_required",
            "creative_pattern_coverage": "available_narrow",
            "approved_news_pattern_count": 2,
            "approved_news_pattern_ids": [
                NEWS_PRICE_PATTERN_ID,
                NEWS_SCENE_PATTERN_ID,
            ],
            "approved_pattern_structural_directions": [
                "price_offer_led_micro_information",
                "scene_contrast",
            ],
            "approved_pattern_supporting_case_ids": sorted(supporting_case_ids),
            "coverage_only_direction": "event_or_campaign_information_progression",
            "coverage_only_case_id": "7582922932108774691",
            "news_production_ready": False,
            "next_gate": "news_production_mvp_validation",
            "news_generation_authorized": False,
            "news_excel_export_authorized": False,
        },
        "changes_canonical_registry": False,
        "changes_approved_coverage_baseline": False,
        "authority": {
            "derived_planning_artifact": True,
            "can_approve_pattern": False,
            "can_change_profile_contract": False,
            "can_claim_effectiveness": False,
            "can_enable_news_generation": False,
            "can_enable_news_export": False,
            "case_facts_used_as_customer_authority": False,
            "privacy_or_proof_authority_changed": False,
            "remote_model_called": False,
        },
        "validation": {
            "passed": True,
            "approved_news_pattern_count_is_two": True,
            "news_not_automatically_production_ready": True,
            "event_explanation_pattern_not_created": True,
            "effectiveness_unvalidated": True,
            "remote_model_call_performed": False,
        },
    }


def render_news_pattern_coverage_update(update: dict[str, Any]) -> str:
    news = update["news_current_coverage"]
    lines = [
        "# News Pattern Approval｜Creative Coverage Update V1",
        "",
        f"Status: **{update['status']}**",
        "",
        "## Approved News Patterns",
        "",
    ]
    for item in update["source_refs"]["approved_news_patterns"]:
        lines.append(f"- `{item['pattern_id']}` — compatible with `news`; Effectiveness `unvalidated`")
    lines.extend(
        [
            "",
            "## Current Readiness",
            "",
            f"- Approved News Pattern count: **{news['approved_news_pattern_count']}**",
            f"- Operational readiness: **{news['operational_readiness']}**",
            f"- Creative Pattern coverage: **{news['creative_pattern_coverage']}**",
            f"- Next gate: **{news['next_gate']}**",
            "- News Production ready: **No**",
            "- News Generation authorized: **No**",
            "- News Excel Export authorized: **No**",
            "",
            "## Boundary",
            "",
            "Pattern Approval establishes reusable structural authority only. It does not validate effectiveness, change the frozen Profile Registry, create an Event Explanation Pattern, or authorize News Production.",
            "",
        ]
    )
    return "\n".join(lines)


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

    news_parser = subparsers.add_parser(
        "approve-news-final",
        help=(
            "Approve the two Human-reviewed News Candidates after deletion-oriented "
            "normalization and write a derived Creative Coverage update."
        ),
    )
    news_parser.add_argument("--candidate", action="append", required=True)
    news_parser.add_argument("--registry", required=True)
    news_parser.add_argument("--coverage-baseline", required=True)
    news_parser.add_argument("--reviewer", required=True)
    news_parser.add_argument("--approved-at", default=None)
    news_parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/patterns/approved",
    )
    news_parser.add_argument(
        "--coverage-output-dir",
        default=None,
        help="Default: <project>/data/creative_coverage/revisions",
    )

    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    if args.command == "approve-news-final":
        if len(args.candidate) != 2:
            raise ValueError("News final approval requires exactly two --candidate values.")
        registry_path = Path(args.registry).expanduser().resolve()
        coverage_baseline_path = Path(args.coverage_baseline).expanduser().resolve()
        approved_root = (
            Path(args.output_root).expanduser().resolve()
            if args.output_root
            else project_root / "data" / "patterns" / "approved"
        )
        coverage_output_dir = (
            Path(args.coverage_output_dir).expanduser().resolve()
            if args.coverage_output_dir
            else project_root / "data" / "creative_coverage" / "revisions"
        )
        candidate_paths = [Path(value).expanduser().resolve() for value in args.candidate]
        validated = [
            validate_news_pattern_candidate_for_approval(path, registry_path)[0]
            for path in candidate_paths
        ]
        if {item["pattern_id"] for item in validated} != set(NEWS_PATTERN_IDS):
            raise ValueError("News final approval requires Price and Scene Candidates.")
        for item in validated:
            pattern_dir = approved_root / item["pattern_id"]
            if (pattern_dir / "pattern_v1.json").exists() or (
                pattern_dir / "approval_receipt.json"
            ).exists():
                raise RuntimeError(
                    f"Approved Pattern or receipt already exists: {item['pattern_id']}"
                )

        timestamp = args.approved_at or now_iso()
        outputs = [
            approve_news_pattern(
                path,
                registry_path,
                approved_root,
                args.reviewer,
                timestamp,
            )
            for path in candidate_paths
        ]
        pattern_paths = [item[0] for item in outputs]
        receipt_paths = [item[1] for item in outputs]
        coverage = build_news_pattern_coverage_update(
            pattern_paths,
            receipt_paths,
            registry_path,
            coverage_baseline_path,
            timestamp,
        )
        coverage_json = (
            coverage_output_dir
            / "news_pattern_approval_creative_coverage_update_v1.json"
        )
        coverage_markdown = (
            coverage_output_dir
            / "news_pattern_approval_creative_coverage_update_v1.md"
        )
        write_new_json(coverage_json, coverage)
        coverage_markdown.parent.mkdir(parents=True, exist_ok=True)
        with coverage_markdown.open("x", encoding="utf-8") as handle:
            handle.write(render_news_pattern_coverage_update(coverage))

        print("NEWS PATTERN FINAL HUMAN APPROVAL PASS")
        for pattern_path, receipt_path, pattern, _receipt in outputs:
            print(f"Pattern: {pattern['pattern_id']} / approved / [news]")
            print(f"Approved artifact: {pattern_path}")
            print(f"Approval receipt: {receipt_path}")
        print("Approved News Pattern count: 2")
        print("News readiness: production_validation_required")
        print("News Generation / Excel Export: False / False")
        print("Remote Model Calls: 0")
        print(f"Coverage JSON: {coverage_json}")
        print(f"Coverage Markdown: {coverage_markdown}")
        return

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
