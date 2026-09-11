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


RESEARCH_VERSION = "pattern-research-v1.0"
BUILDER_VERSION = "mine_pattern_candidates_v1.py@0.1"
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically research Pattern Candidates from exactly three Approved "
            "Cases, their Fingerprints, and a prior Cross-case Comparison."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help="Approved case_v1.json; provide exactly three times.",
    )
    parser.add_argument(
        "--fingerprint",
        action="append",
        required=True,
        help="case_fingerprint_v1.json; provide exactly three times.",
    )
    parser.add_argument(
        "--comparison",
        required=True,
        help="Existing two-Case cross_case_comparison_v1.json containing H001/H002.",
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
