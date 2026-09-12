from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from privacy_projection_v1 import (
    assert_safe_for_external_model,
    validate_case_privacy_gate,
)
from compare_approved_cases_v1 import (
    validate_comparison_human_approval,
    validate_generalized_research_comparison,
)


RESEARCH_VERSION = "pattern-research-v1.0"
BUILDER_VERSION = "mine_pattern_candidates_v1.py@0.1"
NEWS_CANDIDATE_BUILDER_VERSION = "mine_pattern_candidates_v1.py@1.0"
EXPECTED_PRIOR_HYPOTHESES = {"H001", "H002"}
CLAIMS_SEMANTICS = "candidate_unverified_unless_supported_by_verified_proofs"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def claim_statuses(fingerprint: dict[str, Any]) -> list[str]:
    claims = fingerprint.get("content_features", {}).get("claims") or []
    statuses: list[str] = []
    for claim in claims:
        if isinstance(claim, dict):
            statuses.append(str(claim.get("status") or "candidate"))
        else:
            statuses.append("candidate")
    return statuses


def safe_research_projection(fingerprint: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": fingerprint.get("case_id"),
        "identity": fingerprint.get("identity", {}),
        "narration_features": fingerprint.get("narration_features", {}),
        "visual_shot_features": fingerprint.get("visual_shot_features", {}),
        "content_features": fingerprint.get("content_features", {}),
        "structure_features": fingerprint.get("structure_features", {}),
        "audio_visual_features": fingerprint.get("audio_visual_features", {}),
        "pattern_mining_contract": fingerprint.get("pattern_mining_contract", {}),
    }


def validate_and_load_inputs(
    case_paths: list[Path],
    fingerprint_paths: list[Path],
    comparison_path: Path,
) -> tuple[
    list[str],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    if len(case_paths) < 3 or len(fingerprint_paths) < 3:
        raise RuntimeError("At least three Approved Cases are required for a Pattern Candidate.")
    if len(case_paths) != 3 or len(fingerprint_paths) != 3:
        raise RuntimeError("Pattern Research V1 requires exactly three Cases and Fingerprints.")

    cases: dict[str, dict[str, Any]] = {}
    case_meta: dict[str, dict[str, Any]] = {}
    for raw_path in case_paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        case = read_json(path)
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in cases:
            raise RuntimeError("Case IDs must be present and distinct.")
        lifecycle = case.get("lifecycle", {})
        if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
            raise RuntimeError(f"Case {case_id} is not Approved.")
        if case.get("validation", {}).get("passed") is not True:
            raise RuntimeError(f"Case {case_id} validation is not passed.")
        if case.get("quality", {}).get("human_review_completed") is not True:
            raise RuntimeError(f"Case {case_id} lacks completed human review.")
        if case.get("pattern_state", {}).get("pattern_mining_performed") is not False:
            raise RuntimeError(f"Case {case_id} has unexpected Pattern state.")

        privacy_status = "legacy_approved_case_gate_not_recorded"
        if isinstance(case.get("privacy_gate"), dict):
            validate_case_privacy_gate(case)
            privacy_status = "passed"

        cases[case_id] = case
        case_meta[case_id] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "status": "approved",
            "privacy_gate_status": privacy_status,
        }

    fingerprints: dict[str, dict[str, Any]] = {}
    fingerprint_meta: dict[str, dict[str, Any]] = {}
    for raw_path in fingerprint_paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        fingerprint = read_json(path)
        case_id = str(fingerprint.get("case_id") or "")
        if case_id not in cases or case_id in fingerprints:
            raise RuntimeError("Fingerprint must map one-to-one to an input Case.")
        source_case = fingerprint.get("source_case", {})
        if source_case.get("status") != "approved" or source_case.get("approved") is not True:
            raise RuntimeError(f"Fingerprint {case_id} is not bound to an Approved Case.")
        expected_case_hash = case_meta[case_id]["sha256"]
        if str(source_case.get("sha256") or "").lower() != expected_case_hash:
            raise RuntimeError(f"Fingerprint {case_id} source Case SHA-256 mismatch.")
        if (
            str(fingerprint.get("provenance", {}).get("approved_case_sha256") or "").lower()
            != expected_case_hash
        ):
            raise RuntimeError(f"Fingerprint {case_id} provenance SHA-256 mismatch.")
        contract = fingerprint.get("pattern_mining_contract", {})
        if contract.get("eligible_for_pattern_mining") is not True:
            raise RuntimeError(f"Fingerprint {case_id} is not eligible for Pattern Research.")
        if contract.get("this_artifact_is_not_a_pattern") is not True:
            raise RuntimeError(f"Fingerprint {case_id} violates Pattern authority.")

        assert_safe_for_external_model(
            json.dumps(
                safe_research_projection(fingerprint),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        fingerprints[case_id] = fingerprint
        fingerprint_meta[case_id] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "source_case_sha256": expected_case_hash,
            "privacy_egress_gate": "passed",
        }

    case_ids = sorted(cases)
    if sorted(fingerprints) != case_ids:
        raise RuntimeError("Every Case must have exactly one Fingerprint.")

    comparison_path = comparison_path.expanduser().resolve()
    if not comparison_path.is_file():
        raise FileNotFoundError(comparison_path)
    comparison = read_json(comparison_path)
    comparison_ids = sorted(str(value) for value in comparison.get("case_ids", []))
    if len(comparison_ids) != 2 or not set(comparison_ids).issubset(case_ids):
        raise RuntimeError("Prior Comparison must cover exactly two input Cases.")
    if comparison.get("validation", {}).get("passed") is not True:
        raise RuntimeError("Prior Cross-case Comparison validation is not passed.")
    if comparison.get("authority", {}).get("remote_model_used") is not False:
        raise RuntimeError("Prior Comparison has unexpected model authority.")
    prior_hypotheses = {
        str(item.get("id"))
        for item in comparison.get("pattern_assessment", {}).get("hypotheses", [])
    }
    if not EXPECTED_PRIOR_HYPOTHESES.issubset(prior_hypotheses):
        raise RuntimeError("Prior Comparison does not contain H001 and H002.")

    case_sources = [
        {
            "case_id": case_id,
            "approved_case_path": case_meta[case_id]["path"],
            "approved_case_sha": case_meta[case_id]["sha256"],
            "fingerprint_path": fingerprint_meta[case_id]["path"],
            "fingerprint_sha": fingerprint_meta[case_id]["sha256"],
            "privacy_gate_status": case_meta[case_id]["privacy_gate_status"],
        }
        for case_id in case_ids
    ]
    return case_ids, cases, fingerprints, comparison, case_sources


def build_case_profile(case_id: str, fingerprint: dict[str, Any]) -> dict[str, Any]:
    identity = fingerprint.get("identity", {})
    narration = fingerprint.get("narration_features", {})
    visual = fingerprint.get("visual_shot_features", {})
    content = fingerprint.get("content_features", {})
    structure = fingerprint.get("structure_features", {})
    audio_visual = fingerprint.get("audio_visual_features", {})
    roles = visual.get("primary_role_counts", {})
    shot_count = int(visual.get("shot_count") or 0)
    scene_relations = audio_visual.get("scene_relation_counts", {})
    supportive_scene_count = sum(
        int(scene_relations.get(name) or 0) for name in ("supplement", "reinforce")
    )
    process_context_product_count = sum(
        int(roles.get(name) or 0) for name in ("action", "context", "product", "persona")
    )
    statuses = claim_statuses(fingerprint)
    narration_leads_semantics = bool(
        str(structure.get("audio_role") or "").strip()
        and str(content.get("content_goal_candidate") or "").strip()
        and float(narration.get("speech_to_video_ratio") or 0) >= 0.5
    )
    visual_carries_process_context = bool(
        shot_count
        and int(roles.get("action") or 0) > 0
        and ratio(process_context_product_count, shot_count) >= 0.5
        and ratio(supportive_scene_count, shot_count) >= 0.5
    )
    stable_audio_visual_division = bool(
        audio_visual.get("narration_and_shots_are_separate_tracks") is True
        and audio_visual.get("shot_to_narration_cardinality") == "many_to_many"
        and supportive_scene_count > 0
    )
    proof_authority_preserved = bool(
        int(content.get("verified_proof_count") or 0) == 0
        and not (content.get("proof_shot_refs") or [])
        and all(status in {"candidate", "unverified"} for status in statuses)
    )
    hook_modalities = sorted(str(value) for value in structure.get("hook_modalities", []))
    has_multimodal_hook = {"audio", "visual_scene", "visual_text"}.issubset(
        hook_modalities
    )
    has_explicit_cta = bool(content.get("has_explicit_cta"))

    return {
        "case_id": case_id,
        "industry": identity.get("industry"),
        "duration_seconds": identity.get("duration_seconds"),
        "speech_ratio": narration.get("speech_to_video_ratio"),
        "shot_count": shot_count,
        "shot_mean_seconds": visual.get("shot_duration_stats", {}).get("mean"),
        "shot_median_seconds": visual.get("shot_duration_stats", {}).get("median"),
        "shots_under_1s_ratio": visual.get("shots_under_1s_ratio"),
        "onscreen_text_shot_ratio": visual.get("onscreen_text_shot_ratio"),
        "primary_role_counts": roles,
        "primary_role_ratios": {
            role: ratio(float(count), shot_count)
            for role, count in sorted(roles.items())
        },
        "scene_relation_counts": scene_relations,
        "structure_signature": structure.get("structure_signature"),
        "hook_modalities": hook_modalities,
        "cta": {
            "explicit": has_explicit_cta,
            "implicit": "not_encoded_in_case_fingerprint_v1",
            "effective_classification": (
                "explicit_cta" if has_explicit_cta else "no_explicit_cta"
            ),
        },
        "claim_count": len(statuses),
        "claim_statuses": statuses,
        "effective_verified_proof_count": int(
            content.get("verified_proof_count") or 0
        ),
        "h001_checks": {
            "narration_leads_semantics": narration_leads_semantics,
            "visual_carries_process_context_product": visual_carries_process_context,
            "stable_audio_visual_division": stable_audio_visual_division,
            "process_not_upgraded_to_proof": proof_authority_preserved,
        },
        "h002_checks": {
            "multimodal_hook_audio_text_scene": has_multimodal_hook,
            "no_explicit_cta": not has_explicit_cta,
        },
    }


def hypothesis_status(support_count: int, case_count: int, complete: bool = True) -> str:
    if not complete:
        return "insufficient"
    if support_count == case_count:
        return "supported"
    if support_count >= 2:
        return "weakened"
    return "rejected"


def review_hypotheses(
    case_ids: list[str],
    profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    h001_support: list[dict[str, Any]] = []
    h001_contradictions: list[dict[str, Any]] = []
    h002_support: list[dict[str, Any]] = []
    h002_contradictions: list[dict[str, Any]] = []

    for case_id in case_ids:
        profile = profiles[case_id]
        h001_passed = all(profile["h001_checks"].values())
        h001_item = {
            "case_id": case_id,
            "supported": h001_passed,
            "checks": profile["h001_checks"],
            "visual_roles": profile["primary_role_counts"],
            "scene_relations": profile["scene_relation_counts"],
            "verified_proof_count": profile["effective_verified_proof_count"],
        }
        (h001_support if h001_passed else h001_contradictions).append(h001_item)

        h002_passed = all(profile["h002_checks"].values())
        h002_item = {
            "case_id": case_id,
            "supported": h002_passed,
            "hook_modalities": profile["hook_modalities"],
            "cta": profile["cta"],
        }
        (h002_support if h002_passed else h002_contradictions).append(h002_item)

    h001_status = hypothesis_status(len(h001_support), len(case_ids))
    h002_status = hypothesis_status(len(h002_support), len(case_ids))
    return {
        "H001": {
            "statement": (
                "Narration carries the semantic claims while observable operating or "
                "service scenes carry context, persona, process, and product roles without "
                "being promoted to verified proof."
            ),
            "status": h001_status,
            "case_support": h001_support,
            "case_contradictions": h001_contradictions,
            "reason": (
                f"{len(h001_support)}/{len(case_ids)} Cases satisfy the frozen semantic-lead, "
                "visual-role, track-separation, and proof-authority checks."
            ),
        },
        "H002": {
            "statement": (
                "Audio, visual text, and visual scene jointly form the hook while the "
                "video contains no explicit CTA."
            ),
            "status": h002_status,
            "case_support": h002_support,
            "case_contradictions": h002_contradictions,
            "reason": (
                f"{len(h002_support)}/{len(case_ids)} Cases have the three frozen hook "
                "modalities and no explicit CTA; implicit CTA is not encoded by Fingerprint V1."
            ),
        },
    }


def candidate_gate(
    hypothesis: dict[str, Any],
    case_ids: list[str],
    profiles: dict[str, dict[str, Any]],
) -> dict[str, bool]:
    industries = {
        str(profiles[case_id].get("industry") or "unknown") for case_id in case_ids
    }
    return {
        "three_or_more_approved_cases_support": (
            hypothesis.get("status") == "supported"
            and len(hypothesis.get("case_support", [])) >= 3
        ),
        "cross_case_structural_relation": True,
        "invariant_defined": True,
        "variants_defined": True,
        "no_major_contradicting_evidence": not hypothesis.get("case_contradictions"),
        "not_industry_name_dependent": len(industries) >= 2,
        "fingerprint_lineage_complete": True,
        "no_effectiveness_claim": True,
    }


def candidate_evidence(
    case_ids: list[str],
    profiles: dict[str, dict[str, Any]],
    case_sources: list[dict[str, Any]],
    hypothesis_id: str,
) -> list[dict[str, Any]]:
    source_by_id = {item["case_id"]: item for item in case_sources}
    evidence: list[dict[str, Any]] = []
    for case_id in case_ids:
        profile = profiles[case_id]
        if hypothesis_id == "H001":
            supporting_features = [
                "narration_semantic_lead",
                "visual_process_context_or_product_role",
                "many_to_many_separate_audio_visual_tracks",
                "effective_verified_proof_count_preserved",
            ]
            observed = {
                "speech_ratio": profile["speech_ratio"],
                "primary_role_counts": profile["primary_role_counts"],
                "scene_relation_counts": profile["scene_relation_counts"],
                "verified_proof_count": profile["effective_verified_proof_count"],
            }
        else:
            supporting_features = [
                "audio_visual_text_visual_scene_hook",
                "no_explicit_cta",
            ]
            observed = {
                "hook_modalities": profile["hook_modalities"],
                "cta": profile["cta"],
            }
        evidence.append(
            {
                "case_id": case_id,
                "fingerprint_sha": source_by_id[case_id]["fingerprint_sha"],
                "supporting_features": supporting_features,
                "observed": observed,
            }
        )
    return evidence


def build_candidate(
    pattern_id: str,
    working_name: str,
    hypothesis_id: str,
    case_ids: list[str],
    profiles: dict[str, dict[str, Any]],
    case_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    if hypothesis_id == "H001":
        definition = {
            "invariants": [
                "Narration carries the primary semantic claim line.",
                "Observable business or service scenes carry context, persona, process, or product roles that correspond to the narration.",
                "Narration and shots remain separate many-to-many tracks rather than identical evidence units.",
                "Process imagery remains below verified-proof authority unless inherited effective proof exists.",
            ],
            "variants": [
                "Industry and service category.",
                "Duration, shot count, and cutting speed.",
                "Relative shares of action, context, persona, and product roles.",
                "On-screen-text coverage and whether text repeats or supplements narration.",
                "Narrative stage sequence and payoff wording.",
            ],
            "non_defining_traits": [
                "Food-business setting.",
                "A specific owner persona.",
                "Having narration by itself.",
                "Having process footage by itself.",
                "Zero verified proofs as a pipeline policy outcome by itself.",
            ],
        }
        generalization_limit = (
            "Observed only in three Approved operator/business-story Cases across food "
            "and plant-service contexts; it is not established for creator-led, product-only, "
            "institutional, or non-narrated videos."
        )
    else:
        definition = {
            "invariants": [
                "The opening hook combines audio, visual text, and visual scene.",
                "The video reaches its closing payoff without an explicit CTA.",
            ],
            "variants": [
                "Hook rhetoric may be a thesis, contextual setup, or customer-value question.",
                "On-screen-text coverage after the hook may range from continuous to sparse.",
                "The closing payoff may be motivational, quality-oriented, or service-value-oriented.",
                "Implicit engagement language is outside Fingerprint V1 and may vary.",
            ],
            "non_defining_traits": [
                "Vertical format.",
                "Local-business category.",
                "Subtitles outside the hook.",
                "Any claim that the configuration improves conversion or reach.",
            ],
        }
        generalization_limit = (
            "Observed only in the current three Approved operator/business-story Cases. "
            "Fingerprint V1 confirms no explicit CTA but does not encode implicit CTA, so "
            "the Candidate cannot claim a universal no-CTA strategy."
        )

    source_by_id = {item["case_id"]: item for item in case_sources}
    industries = sorted(
        {str(profiles[case_id].get("industry") or "unknown") for case_id in case_ids}
    )
    return {
        "schema_version": "pattern-candidate-v1.0",
        "pattern_id": pattern_id,
        "status": "candidate",
        "working_name": working_name,
        "definition": definition,
        "scope": {
            "supported_case_count": len(case_ids),
            "supported_case_ids": case_ids,
            "industry_scope": industries,
            "current_generalization_limit": generalization_limit,
        },
        "evidence": candidate_evidence(
            case_ids, profiles, case_sources, hypothesis_id
        ),
        "contradicting_evidence": [],
        "origin_hypotheses": [hypothesis_id],
        "effectiveness": {
            "status": "unvalidated",
            "performance_data_used": False,
        },
        "authority": {
            "candidate_only": True,
            "human_review_required": True,
            "auto_approval_performed": False,
            "proof_reinterpreted": False,
        },
        "lineage": {
            "approved_case_sha256": {
                case_id: source_by_id[case_id]["approved_case_sha"]
                for case_id in case_ids
            },
            "fingerprint_sha256": {
                case_id: source_by_id[case_id]["fingerprint_sha"]
                for case_id in case_ids
            },
        },
        "validation": {
            "passed": True,
            "supporting_case_count_at_least_three": len(case_ids) >= 3,
            "status_is_candidate": True,
            "human_review_required": True,
            "effectiveness_unvalidated": True,
            "process_not_promoted_to_proof": True,
        },
    }


def build_pattern_research(
    case_paths: list[Path],
    fingerprint_paths: list[Path],
    comparison_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_ids, _cases, fingerprints, comparison, case_sources = validate_and_load_inputs(
        case_paths, fingerprint_paths, comparison_path
    )
    profiles = {
        case_id: build_case_profile(case_id, fingerprints[case_id])
        for case_id in case_ids
    }
    hypothesis_review = review_hypotheses(case_ids, profiles)

    candidate_specs = {
        "H001": (
            "pcv1_narration_led_process_projection",
            "Narration-led process projection",
        ),
        "H002": (
            "pcv1_multimodal_hook_no_explicit_cta",
            "Multimodal hook without explicit CTA",
        ),
    }
    candidate_assessment: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for hypothesis_id in sorted(candidate_specs):
        gate = candidate_gate(
            hypothesis_review[hypothesis_id], case_ids, profiles
        )
        eligible = all(gate.values())
        pattern_id, working_name = candidate_specs[hypothesis_id]
        candidate_assessment.append(
            {
                "origin_hypothesis": hypothesis_id,
                "eligible": eligible,
                "pattern_id": pattern_id if eligible else None,
                "gate": gate,
                "reason": (
                    "All frozen Pattern Candidate gates passed."
                    if eligible
                    else "At least one frozen Pattern Candidate gate did not pass."
                ),
            }
        )
        if eligible:
            candidates.append(
                build_candidate(
                    pattern_id,
                    working_name,
                    hypothesis_id,
                    case_ids,
                    profiles,
                    case_sources,
                )
            )

    proof_counts = {
        case_id: profiles[case_id]["effective_verified_proof_count"]
        for case_id in case_ids
    }
    comparison_path = comparison_path.expanduser().resolve()
    research = {
        "schema_version": RESEARCH_VERSION,
        "research_version": RESEARCH_VERSION,
        "builder_version": BUILDER_VERSION,
        "case_ids": case_ids,
        "case_sources": case_sources,
        "prior_comparison": {
            "path": str(comparison_path),
            "sha256": sha256_file(comparison_path),
            "case_ids": sorted(comparison.get("case_ids", [])),
            "hypotheses_consumed": sorted(EXPECTED_PRIOR_HYPOTHESES),
        },
        "authority": {
            "approved_cases_only": True,
            "approved_fingerprints_only": True,
            "prior_comparison_consumed": True,
            "raw_whisper_read": False,
            "raw_visual_evidence_read": False,
            "storyboard_raw_interpretation_read": False,
            "narration_reinterpreted": False,
            "proof_reinterpreted": False,
            "process_promoted_to_proof": False,
            "remote_model_used": False,
            "privacy_safe_projection_checked": True,
            "authority_ceiling": "pattern_candidate",
        },
        "hypothesis_review": hypothesis_review,
        "case_profiles": profiles,
        "cross_case_findings": [
            {
                "classification": "structural_relation",
                "finding": "Narration leads semantic claims while process/context/product scenes visually correspond without becoming verified proof.",
                "case_ids": case_ids,
                "candidate_origin": "H001",
            },
            {
                "classification": "structural_configuration",
                "finding": "All three openings combine audio, visual text, and visual scene, and all three omit an explicit CTA.",
                "case_ids": case_ids,
                "candidate_origin": "H002",
            },
            {
                "classification": "general_video_property_not_pattern",
                "finding": "Narration, business activity, and vertical short-video conventions are insufficient Pattern definitions by themselves.",
                "case_ids": case_ids,
            },
            {
                "classification": "authority_invariant_not_content_pattern",
                "finding": "All three have zero effective verified proofs, but this is treated as inherited Proof authority rather than proof of a creative Pattern.",
                "case_ids": case_ids,
            },
            {
                "classification": "important_difference",
                "finding": "Duration, rhythm, on-screen-text coverage, role distribution, narrative sequence, and payoff rhetoric vary materially.",
                "case_ids": case_ids,
            },
        ],
        "independent_discovery": {
            "additional_candidate_count": 0,
            "findings": [
                "Narration density is high in all Cases but is an attribute, not a cross-modal relation independent of H001.",
                "Hook-to-development-to-payoff progression is too general to qualify as a Candidate.",
                "Text repetition, product share, process share, and information-release sequence vary too much for another invariant.",
                "Zero verified proofs reflects inherited evidence authority and cannot be mined as effectiveness evidence.",
            ],
        },
        "candidate_assessment": candidate_assessment,
        "pattern_candidate_count": len(candidates),
        "pattern_candidate_ids": [item["pattern_id"] for item in candidates],
        "research_limitations": [
            "Only three Approved Cases are available, two of which are food-related.",
            "Fingerprint V1 records explicit CTA but does not formally classify implicit CTA.",
            "No unified performance data was consumed, so effectiveness remains unvalidated.",
            "The sample does not cover non-narrated, product-only, institutional, or creator-led formats.",
            "Human Pattern Review is required before any Candidate can become an Approved Pattern.",
        ],
        "effectiveness_authority": {
            "status": "unvalidated",
            "performance_data_used": False,
            "causal_claims_permitted": False,
        },
        "validation": {
            "passed": True,
            "approved_case_count": len(case_ids),
            "approved_cases_only": True,
            "fingerprints_bound_to_case_sha256": True,
            "input_order_canonicalized": True,
            "candidate_supporting_case_count_minimum": 3,
            "candidate_status_ceiling_enforced": True,
            "candidate_auto_approval_performed": False,
            "proof_not_upgraded": all(value == 0 for value in proof_counts.values()),
            "effective_verified_proof_counts": proof_counts,
            "claims_semantics": CLAIMS_SEMANTICS,
            "effectiveness_unvalidated": True,
            "raw_authority_not_read": True,
            "sha_lineage_complete": True,
            "privacy_egress_gate_passed": True,
            "remote_model_call_performed": False,
        },
    }
    return research, candidates


def render_markdown(research: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    lines = [
        "# Three-Case Pattern Research V1",
        "",
        f"Cases: {', '.join(research['case_ids'])}",
        "",
        "## Hypothesis Review",
        "",
    ]
    for hypothesis_id in ("H001", "H002"):
        item = research["hypothesis_review"][hypothesis_id]
        lines.extend(
            [
                f"### {hypothesis_id}: {item['status']}",
                "",
                item["statement"],
                "",
                item["reason"],
                "",
            ]
        )
    lines.extend(
        [
            "## Pattern Candidate Assessment",
            "",
            f"Candidate count: {research['pattern_candidate_count']}",
            "",
        ]
    )
    for candidate in candidates:
        lines.extend(
            [
                f"### {candidate['pattern_id']}",
                "",
                f"Working name: {candidate['working_name']}",
                "",
                "Invariants:",
            ]
        )
        lines.extend(f"- {value}" for value in candidate["definition"]["invariants"])
        lines.extend(["", "Variants:"])
        lines.extend(f"- {value}" for value in candidate["definition"]["variants"])
        lines.extend(
            [
                "",
                f"Scope limit: {candidate['scope']['current_generalization_limit']}",
                "",
                "Effectiveness: unvalidated",
                "",
                "Human review required: true",
                "",
            ]
        )
    lines.extend(
        [
            "## Independent Discovery",
            "",
            "No additional Candidate passed the frozen gate.",
            "",
            "## Authority",
            "",
            "No remote model was used. No Raw Whisper, Raw Visual, Storyboard raw interpretation, or unapproved artifact was read.",
            "",
            "Process remained distinct from verified proof. Effectiveness remains unvalidated.",
            "",
        ]
    )
    return "\n".join(lines)


def current_artifact_ref(reference: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    path = Path(str(reference.get("path") or "")).expanduser().resolve()
    expected_sha = str(reference.get("sha256") or "").lower()
    if not path.is_file() or len(expected_sha) != 64:
        raise RuntimeError(f"{artifact_type} lineage is incomplete: {path}")
    if sha256_file(path) != expected_sha:
        raise RuntimeError(f"{artifact_type} lineage changed: {path}")
    return {
        "artifact_type": artifact_type,
        "path": str(path),
        "sha256": expected_sha,
    }


def validate_news_candidate_inputs(
    comparison_path: Path,
    approval_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    comparison_path = comparison_path.expanduser().resolve()
    approval_path = approval_path.expanduser().resolve()
    if not comparison_path.is_file():
        raise FileNotFoundError(comparison_path)
    if not approval_path.is_file():
        raise FileNotFoundError(approval_path)
    comparison = read_json(comparison_path)
    approval = read_json(approval_path)
    validate_generalized_research_comparison(comparison)
    validate_comparison_human_approval(
        approval,
        expected_comparison_sha256=sha256_file(comparison_path),
    )
    if approval.get("research_direction") != comparison.get("research_direction"):
        raise RuntimeError("Comparison and Human Approval directions differ.")
    if comparison.get("case_count") != 3:
        raise RuntimeError("News Pattern Candidate V1 requires three Approved Cases.")
    if comparison.get("candidate_research_readiness") != (
        "ready_for_pattern_candidate_human_review"
    ):
        raise RuntimeError("Comparison is not ready for Pattern Candidate research.")
    if comparison.get("pattern_candidate_eligibility", {}).get(
        "creates_pattern_candidate"
    ) is not False:
        raise RuntimeError("Source Comparison crosses Pattern Candidate authority.")

    evidence: list[dict[str, Any]] = []
    inputs = comparison.get("input_artifacts") or {}
    rows = (comparison.get("evidence_matrix") or {}).get("case_rows") or {}
    for case_id in comparison.get("case_ids") or []:
        item = inputs.get(case_id) or {}
        case_ref = current_artifact_ref(
            item.get("approved_case_ref") or {}, "approved_case"
        )
        fingerprint_ref = current_artifact_ref(
            item.get("fingerprint_ref") or {}, "case_fingerprint"
        )
        storyboard_ref = current_artifact_ref(
            item.get("storyboard_ref") or {}, "news_micro_beat_storyboard"
        )
        case = read_json(Path(case_ref["path"]))
        if (
            case.get("lifecycle", {}).get("status") != "approved"
            or case.get("pattern_state", {}).get("pattern_mining_performed") is not False
        ):
            raise RuntimeError(f"Case {case_id} is not valid Approved Pattern evidence.")
        evidence.append(
            {
                "case_id": case_id,
                "research_role": (rows.get(case_id) or {}).get("research_role"),
                "approved_case_ref": case_ref,
                "fingerprint_ref": fingerprint_ref,
                "micro_beat_storyboard_ref": storyboard_ref,
                "structural_observation": rows.get(case_id) or {},
                "case_specific_business_facts_are_customer_authority": False,
            }
        )
    return comparison, approval, evidence


def build_news_pattern_candidate(
    comparison_path: Path,
    approval_path: Path,
) -> dict[str, Any]:
    comparison, approval, evidence = validate_news_candidate_inputs(
        comparison_path, approval_path
    )
    direction = str(comparison["research_direction"])
    if direction == "price_offer_led_micro_information":
        pattern_id = "pcv1_news_price_offer_led_micro_information"
        working_name = "News Price / Offer-led Micro-information"
        summary = (
            "Price or Offer forms the first principal information anchor. Multiple "
            "recoverable micro-information states then contextualize, scope, explain, "
            "or situate the offer without requiring continuous Mix narration."
        )
        invariants = [
            "price_or_offer_first_semantic_anchor",
            "multiple_recoverable_micro_information_states_follow_the_anchor",
            "later_states_materially_contextualize_scope_explain_or_situate_the_offer_without_requiring_a_fixed_scope_beat",
            "continuous_mix_narration_not_required_for_semantic_recovery",
        ]
        variants = [
            "persistent_vs_changing_offer_display",
            "package_vs_discount_vs_bundle",
            "explicit_vs_implicit_scope",
            "number_of_beats",
            "duration",
            "visual_state_style",
            "close",
            "industry",
            "product_or_service_category",
        ]
        scope = {
            "supported": "price_offer_led_micro_information",
            "scope_limitation": "price_offer_led_only",
            "explicitly_not_supported": "generic_number_led",
        }
        unresolved = list(approval.get("unresolved_questions") or [])
        proof_boundary = {
            "offer_or_price_visibility_is_verified_proof": False,
            "commercial_effectiveness_claimed": False,
            "semantics": "observable_offer_information_not_performance_proof",
        }
        production_implications = [
            "If later Approved, may guide News script and micro-beat planning around an offer-first information hierarchy.",
            "If later Approved, may guide creative matching and storyboard planning without requiring continuous narration.",
        ]
        explicitly_not_frozen = [
            "persistent_price_text",
            "changing_price_state",
            "independent_explicit_scope_beat",
            "explicit_close",
            "exact_beat_count",
            "exact_duration",
            "specific_industry",
            "specific_offer_type",
            "generic_number_led_scope",
        ]
    elif direction == "scene_contrast":
        pattern_id = "pcv1_news_scene_contrast"
        working_name = "News Scene Contrast"
        summary = (
            "Directly observable, semantically meaningful State A and State B form the "
            "information core. Their difference changes viewer understanding, with visual "
            "information states carrying the primary semantics without continuous narration."
        )
        invariants = [
            "meaningful_comparable_state_a_and_state_b",
            "state_difference_materially_changes_understanding",
            "visual_information_state_is_primary_semantic_carrier",
            "continuous_narration_not_required_for_semantic_recovery",
        ]
        variants = [
            "transformation_action_optional_enhancer",
            "actual_operation",
            "visual_transition",
            "overlay",
            "direct_state_a_b",
            "repeated_comparison_catalogue",
            "single_transformation",
            "multiple_paired_comparisons",
            "supporting_text_labels_or_no_labels",
            "explicit_or_implicit_close",
            "duration",
            "beat_count",
        ]
        scope = {"supported": "scene_contrast"}
        unresolved = [
            {
                "question_id": "same_subject_identity_requirement",
                "status": "unresolved",
                "question": (
                    "Must State A and State B preserve the same subject, place, object, "
                    "or person identity, or is recoverable semantic correspondence sufficient?"
                ),
                "frozen_answer": None,
            }
        ]
        proof_boundary = {
            "observable_state_difference": True,
            "state_difference_is_automatically_verified_proof": False,
            "causality_proven": False,
            "service_effect_proven": False,
            "commercial_result_proven": False,
            "transformation_attribution_proven": False,
            "product_effect_attribution_proven": False,
        }
        production_implications = [
            "If later Approved, may guide News beat planning around recoverable State A/State B correspondence.",
            "If later Approved, may guide visual-first creative matching and storyboard planning without requiring narration.",
        ]
        explicitly_not_frozen = [
            "transformation_action",
            "transition_animation",
            "overlay",
            "single_continuous_transformation",
            "repeated_comparison_catalogue",
            "location_label",
            "before_after_wording",
            "explicit_result_close",
            "exact_beat_count",
            "exact_duration",
            "industry_or_topic",
            "same_subject_identity_requirement",
        ]
    else:
        raise RuntimeError(f"Unsupported News Pattern Candidate direction: {direction}")

    comparison_path = comparison_path.expanduser().resolve()
    approval_path = approval_path.expanduser().resolve()
    candidate = {
        "schema_version": "pattern-candidate-v1.0",
        "builder_version": NEWS_CANDIDATE_BUILDER_VERSION,
        "pattern_id": pattern_id,
        "status": "review_required",
        "candidate_state": "candidate",
        "working_name": working_name,
        "compatible_profile_candidate": ["news"],
        "candidate_summary": summary,
        "definition": {
            "candidate_invariants": invariants,
            "variants": variants,
            "explicitly_not_frozen": explicitly_not_frozen,
        },
        "scope": {
            **scope,
            "supported_case_count": len(evidence),
            "supported_case_ids": [item["case_id"] for item in evidence],
        },
        "evidence": evidence,
        "boundary_evidence": (
            comparison.get("boundary_conditions")
            or comparison.get("boundary_variant_findings")
            or []
        ),
        "counterexamples_and_attacks": (
            comparison.get("counterexamples")
            or comparison.get("contradictions")
            or []
        ),
        "unresolved_questions": unresolved,
        "transformation_action": (
            {
                "status": "optional_enhancer",
                "candidate_invariant": False,
                "evidence": comparison.get("transformation_action_status"),
            }
            if direction == "scene_contrast"
            else None
        ),
        "proof_boundary": proof_boundary,
        "production_implications": {
            "only_if_future_human_approved": True,
            "may_guide": production_implications,
            "news_generation_enabled_now": False,
            "news_export_enabled_now": False,
        },
        "effectiveness": {
            "status": "unvalidated",
            "performance_data_available": False,
            "performance_data_used": False,
            "causal_or_performance_claims_permitted": False,
        },
        "lineage": {
            "comparison_ref": current_artifact_ref(
                {
                    "path": str(comparison_path),
                    "sha256": sha256_file(comparison_path),
                },
                "cross_case_comparison",
            ),
            "comparison_human_approval_ref": current_artifact_ref(
                {
                    "path": str(approval_path),
                    "sha256": sha256_file(approval_path),
                },
                "comparison_human_approval",
            ),
            "case_sha256": {
                item["case_id"]: item["approved_case_ref"]["sha256"]
                for item in evidence
            },
            "fingerprint_sha256": {
                item["case_id"]: item["fingerprint_ref"]["sha256"]
                for item in evidence
            },
            "micro_beat_storyboard_sha256": {
                item["case_id"]: item["micro_beat_storyboard_ref"]["sha256"]
                for item in evidence
            },
        },
        "authority": {
            "candidate_only": True,
            "human_review_required": True,
            "auto_approved": False,
            "approved_pattern": False,
            "profile_compatibility_approved": False,
            "effectiveness_claimed": False,
            "performance_authority_created": False,
            "proof_reinterpreted_or_upgraded": False,
            "case_specific_facts_used_as_customer_authority": False,
            "remote_model_used": False,
            "local_model_used": False,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
            "new_case_acquisition_performed": False,
        },
        "validation": {
            "passed": True,
            "three_approved_cases_bound": len(evidence) == 3,
            "comparison_human_approved": True,
            "status_is_review_required": True,
            "pattern_approval_not_performed": True,
            "effectiveness_unvalidated": True,
            "news_readiness_unchanged": True,
        },
    }
    validate_news_pattern_candidate(candidate)
    return candidate


def validate_news_pattern_candidate(candidate: dict[str, Any]) -> None:
    if candidate.get("schema_version") != "pattern-candidate-v1.0":
        raise ValueError("News Pattern Candidate schema is invalid.")
    if candidate.get("status") != "review_required":
        raise ValueError("News Pattern Candidate must stop at review_required.")
    if candidate.get("candidate_state") != "candidate":
        raise ValueError("News Pattern Candidate state is invalid.")
    if candidate.get("compatible_profile_candidate") != ["news"]:
        raise ValueError("News Pattern Candidate compatibility must remain candidate-only News.")
    if candidate.get("scope", {}).get("supported_case_count") != 3:
        raise ValueError("News Pattern Candidate requires three Approved Evidence Cases.")
    if len(candidate.get("evidence") or []) != 3:
        raise ValueError("News Pattern Candidate Evidence lineage is incomplete.")
    definition = candidate.get("definition") or {}
    invariants = set(definition.get("candidate_invariants") or [])
    if candidate.get("pattern_id") == "pcv1_news_price_offer_led_micro_information":
        if candidate.get("scope", {}).get("scope_limitation") != "price_offer_led_only":
            raise ValueError("Price Candidate scope must remain price_offer_led_only.")
        if candidate.get("scope", {}).get("explicitly_not_supported") != "generic_number_led":
            raise ValueError("Price Candidate must reject generic_number_led scope.")
        if any("explicit_scope" in value for value in invariants):
            raise ValueError("Explicit scope beat cannot become a Price invariant.")
        if any("close" in value for value in invariants):
            raise ValueError("Close cannot become a Price invariant.")
    elif candidate.get("pattern_id") == "pcv1_news_scene_contrast":
        if any("transformation" in value for value in invariants):
            raise ValueError("Transformation action cannot become a Scene invariant.")
        if candidate.get("transformation_action", {}).get("status") != "optional_enhancer":
            raise ValueError("Scene transformation action must remain optional_enhancer.")
        questions = candidate.get("unresolved_questions") or []
        if not any(
            item.get("question_id") == "same_subject_identity_requirement"
            and item.get("status") == "unresolved"
            and item.get("frozen_answer") is None
            for item in questions
            if isinstance(item, dict)
        ):
            raise ValueError("Scene same-subject identity requirement must remain unresolved.")
        if candidate.get("proof_boundary", {}).get(
            "state_difference_is_automatically_verified_proof"
        ) is not False:
            raise ValueError("Scene contrast cannot automatically become Verified Proof.")
    else:
        raise ValueError("Unknown News Pattern Candidate ID.")
    effectiveness = candidate.get("effectiveness") or {}
    if (
        effectiveness.get("status") != "unvalidated"
        or effectiveness.get("performance_data_available") is not False
        or effectiveness.get("performance_data_used") is not False
    ):
        raise ValueError("News Pattern Candidate cannot claim Effectiveness.")
    authority = candidate.get("authority") or {}
    if authority.get("candidate_only") is not True or authority.get(
        "human_review_required"
    ) is not True:
        raise ValueError("News Pattern Candidate authority is invalid.")
    for field in (
        "auto_approved",
        "approved_pattern",
        "profile_compatibility_approved",
        "effectiveness_claimed",
        "performance_authority_created",
        "proof_reinterpreted_or_upgraded",
        "case_specific_facts_used_as_customer_authority",
        "remote_model_used",
        "local_model_used",
        "news_generation_performed",
        "news_excel_export_performed",
        "new_case_acquisition_performed",
    ):
        if authority.get(field) is not False:
            raise ValueError("News Pattern Candidate crosses an Authority boundary.")


def render_news_candidate_review_pack(candidate: dict[str, Any]) -> str:
    lines = [
        f"# Pattern Candidate Human Review｜{candidate['pattern_id']}",
        "",
        "Status: **Review Required / Not Approved**",
        "",
        "## A. Pattern ID",
        "",
        f"`{candidate['pattern_id']}`",
        "",
        "## B. Compatible Profile Candidate",
        "",
        "`[news]` — candidate only; profile compatibility is not yet approved.",
        "",
        "## C. Evidence Cases",
        "",
        "| Case | Research role | Case SHA | Fingerprint SHA | Storyboard SHA |",
        "|---|---|---|---|---|",
    ]
    for item in candidate["evidence"]:
        lines.append(
            f"| {item['case_id']} | {item['research_role']} | "
            f"`{item['approved_case_ref']['sha256']}` | "
            f"`{item['fingerprint_ref']['sha256']}` | "
            f"`{item['micro_beat_storyboard_ref']['sha256']}` |"
        )
    lineage = candidate["lineage"]
    lines.extend(
        [
            "",
            "## D. Comparison Source",
            "",
            f"- Comparison: `{lineage['comparison_ref']['path']}`",
            f"- Comparison SHA: `{lineage['comparison_ref']['sha256']}`",
            f"- Human Approval: `{lineage['comparison_human_approval_ref']['path']}`",
            f"- Human Approval SHA: `{lineage['comparison_human_approval_ref']['sha256']}`",
            "",
            "## E. Candidate Summary",
            "",
            candidate["candidate_summary"],
            "",
            "## F. Candidate Invariants",
            "",
        ]
    )
    lines.extend(f"- `{value}`" for value in candidate["definition"]["candidate_invariants"])
    lines.extend(["", "## G. Variants", ""])
    lines.extend(f"- `{value}`" for value in candidate["definition"]["variants"])
    lines.extend(["", "## H. Boundary Evidence", ""])
    for item in candidate.get("boundary_evidence") or []:
        lines.append(f"- `{item['case_id']}` — {item['finding']}")
    lines.extend(["", "## I. Counterexamples / Attacks", ""])
    for item in candidate.get("counterexamples_and_attacks") or []:
        lines.append(
            f"- `{item.get('status')}` {item.get('claim')} — "
            + ", ".join(item.get("case_ids") or [])
        )
    lines.extend(
        [
            "",
            "## J. Scope",
            "",
            "```json",
            json.dumps(candidate["scope"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## K. Scope Limitations",
            "",
        ]
    )
    lines.extend(f"- `{value}`" for value in candidate["definition"]["explicitly_not_frozen"])
    lines.extend(["", "## L. Unresolved Questions", ""])
    for item in candidate.get("unresolved_questions") or []:
        if isinstance(item, dict):
            lines.append(f"- `{item['status']}` — {item['question']}")
        else:
            lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## M. Proof / Effectiveness Boundary",
            "",
            "```json",
            json.dumps(candidate["proof_boundary"], ensure_ascii=False, indent=2),
            "```",
            "",
            "Effectiveness remains `unvalidated`; no Performance Data was available or used.",
            "",
            "## N. Production Implications",
            "",
        ]
    )
    lines.extend(f"- {value}" for value in candidate["production_implications"]["may_guide"])
    lines.extend(
        [
            "",
            "These implications apply only after future Human Pattern Approval. News Generation and Export remain disabled.",
            "",
            "## O. Explicitly NOT Frozen",
            "",
        ]
    )
    lines.extend(f"- `{value}`" for value in candidate["definition"]["explicitly_not_frozen"])
    lines.extend(
        [
            "",
            "This Candidate is not an Approved Pattern and does not establish Effectiveness, causality, Proof, or customer Fact Authority.",
            "",
        ]
    )
    return "\n".join(lines)


def write_candidate_artifact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Pattern Candidate Artifact differs: {path}")
        return
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically create review-required Pattern Candidates from Human-approved "
            "Cross-case research, while retaining the legacy three-Case H001/H002 workflow."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Legacy mode: Approved case_v1.json; provide exactly three times.",
    )
    parser.add_argument(
        "--fingerprint",
        action="append",
        help="Legacy mode: case_fingerprint_v1.json; provide exactly three times.",
    )
    parser.add_argument(
        "--comparison",
        help="Legacy mode: existing two-Case comparison containing H001/H002.",
    )
    parser.add_argument(
        "--news-comparison",
        default=None,
        help="News mode: Human-reviewed generalized Cross-case Comparison.",
    )
    parser.add_argument(
        "--comparison-approval",
        default=None,
        help="News mode: matching Comparison Human Approval receipt.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Default: <project>/data/pattern_research/three_case_v1",
    )
    parser.add_argument(
        "--candidate-root",
        default=None,
        help="Default: <project>/data/patterns/candidates",
    )
    args = parser.parse_args()

    if args.news_comparison or args.comparison_approval:
        if not args.news_comparison or not args.comparison_approval:
            raise ValueError(
                "News Candidate mode requires --news-comparison and --comparison-approval."
            )
        if args.case or args.fingerprint or args.comparison:
            raise ValueError("News Candidate mode cannot be combined with legacy inputs.")
        candidate = build_news_pattern_candidate(
            Path(args.news_comparison),
            Path(args.comparison_approval),
        )
        project_root = Path(__file__).resolve().parents[1]
        candidate_root = (
            Path(args.candidate_root).expanduser().resolve()
            if args.candidate_root
            else project_root / "data" / "patterns" / "candidates"
        )
        candidate_dir = candidate_root / candidate["pattern_id"]
        candidate_path = candidate_dir / "pattern_candidate_v1.json"
        review_pack_path = candidate_dir / "pattern_candidate_human_review_pack_v1.md"
        write_candidate_artifact(
            candidate_path,
            json.dumps(candidate, ensure_ascii=False, indent=2),
        )
        write_candidate_artifact(
            review_pack_path,
            render_news_candidate_review_pack(candidate),
        )
        print("NEWS PATTERN CANDIDATE V1 PASS")
        print(f"Pattern ID: {candidate['pattern_id']}")
        print(f"Status: {candidate['status']}")
        print("Approved Pattern: False")
        print("Effectiveness: unvalidated")
        print("Remote/local model used: False / False")
        print(f"Candidate: {candidate_path}")
        print(f"Review pack: {review_pack_path}")
        return

    if not args.case or not args.fingerprint or not args.comparison:
        raise ValueError(
            "Legacy mode requires three --case, three --fingerprint, and --comparison."
        )

    research, candidates = build_pattern_research(
        [Path(value) for value in args.case],
        [Path(value) for value in args.fingerprint],
        Path(args.comparison),
    )
    project_root = Path(__file__).resolve().parents[1]
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else project_root / "data" / "pattern_research" / "three_case_v1"
    )
    candidate_root = (
        Path(args.candidate_root).expanduser().resolve()
        if args.candidate_root
        else project_root / "data" / "patterns" / "candidates"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "pattern_research_v1.json"
    markdown_path = output_dir / "pattern_research_v1.md"
    json_path.write_text(
        json.dumps(research, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    markdown_path.write_text(render_markdown(research, candidates), encoding="utf-8")

    candidate_paths: list[Path] = []
    for candidate in candidates:
        candidate_dir = candidate_root / candidate["pattern_id"]
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = candidate_dir / "pattern_candidate_v1.json"
        candidate_path.write_text(
            json.dumps(candidate, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        candidate_paths.append(candidate_path)

    print("PATTERN RESEARCH V1 PASS")
    print(f"Cases: {' x '.join(research['case_ids'])}")
    print(f"H001: {research['hypothesis_review']['H001']['status']}")
    print(f"H002: {research['hypothesis_review']['H002']['status']}")
    print(f"Pattern Candidates: {len(candidates)}")
    print("Remote model used: False")
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    for candidate_path in candidate_paths:
        print(f"Candidate: {candidate_path}")


if __name__ == "__main__":
    main()
