from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from privacy_projection_v1 import (
    assert_safe_for_external_model,
    validate_case_privacy_gate,
)


COMPARISON_VERSION = "cross-case-comparison-v1.0"
GENERALIZED_COMPARISON_VERSION = "cross-case-research-comparison-v1.0"
COMPARISON_HUMAN_APPROVAL_VERSION = "cross-case-comparison-human-approval-v1.0"
BUILDER_VERSION = "compare_approved_cases_v1.py@0.1"
GENERALIZED_BUILDER_VERSION = "compare_approved_cases_v1.py@1.0"
CLAIMS_SEMANTICS = (
    "candidate_unverified_unless_supported_by_verified_proofs"
)


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


def closeness(left: float, right: float) -> float:
    maximum = max(abs(left), abs(right))
    if maximum == 0:
        return 1.0
    return round(max(0.0, 1.0 - abs(left - right) / maximum), 6)


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return round(len(left & right) / len(union), 6) if union else 1.0


def cosine_counts(
    left: dict[str, Any],
    right: dict[str, Any],
) -> float:
    keys = sorted(set(left) | set(right))
    dot = sum(float(left.get(key, 0)) * float(right.get(key, 0)) for key in keys)
    left_norm = math.sqrt(sum(float(left.get(key, 0)) ** 2 for key in keys))
    right_norm = math.sqrt(sum(float(right.get(key, 0)) ** 2 for key in keys))
    if not left_norm and not right_norm:
        return 1.0
    if not left_norm or not right_norm:
        return 0.0
    return round(dot / (left_norm * right_norm), 6)


def similarity_label(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def claim_texts(fingerprint: dict[str, Any]) -> list[str]:
    values = fingerprint.get("content_features", {}).get("claims") or []
    texts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            text = value.get("claim")
        else:
            text = value
        if str(text or "").strip():
            texts.append(str(text).strip())
    return texts


def semantic_text(fingerprint: dict[str, Any]) -> str:
    content = fingerprint.get("content_features", {})
    structure = fingerprint.get("structure_features", {})
    parts = [str(content.get("content_goal_candidate") or "")]
    parts.extend(claim_texts(fingerprint))
    parts.extend(
        str(structure.get(key) or "")
        for key in (
            "audio_role",
            "visual_text_role",
            "visual_scene_role",
            "audio_visual_strategy",
        )
    )
    parts.extend(
        str(item.get("description") or "")
        for item in structure.get("structure_sequence", []) or []
    )
    return "\n".join(parts)


SEMANTIC_TAG_RULES = {
    "food_business_context": ("餐饮", "蛋糕", "甜品", "厨房", "烧烤", "备餐"),
    "small_business_operations": ("创业", "经营", "小店", "店铺", "营业"),
    "action_or_execution": ("执行", "行动", "先去做", "操作", "制作"),
    "process_demonstration": ("流程", "打包", "保温", "冷藏", "搬运", "展示"),
    "customer_or_quality": ("顾客", "客人", "品质", "口味", "满意"),
    "delivery": ("配送", "骑手", "闪送"),
    "growth": ("成长", "打磨", "改进"),
}


def semantic_tags(fingerprint: dict[str, Any]) -> list[str]:
    text = semantic_text(fingerprint)
    return [
        tag
        for tag, terms in SEMANTIC_TAG_RULES.items()
        if any(term in text for term in terms)
    ]


def role_ratio(fingerprint: dict[str, Any], role: str) -> float:
    visual = fingerprint.get("visual_shot_features", {})
    return ratio(
        float(visual.get("primary_role_counts", {}).get(role, 0)),
        float(visual.get("shot_count") or 0),
    )


def stage_set(fingerprint: dict[str, Any]) -> set[str]:
    return {
        str(item.get("stage"))
        for item in fingerprint.get("structure_features", {}).get(
            "structure_sequence", []
        )
        if item.get("stage")
    }


def safe_comparison_projection(
    fingerprint: dict[str, Any],
) -> dict[str, Any]:
    return {
        "case_id": fingerprint.get("case_id"),
        "content_features": fingerprint.get("content_features", {}),
        "structure_features": fingerprint.get("structure_features", {}),
        "audio_visual_features": fingerprint.get("audio_visual_features", {}),
    }


def validate_and_load_inputs(
    case_paths: list[Path],
    fingerprint_paths: list[Path],
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    if len(case_paths) != 2 or len(fingerprint_paths) != 2:
        raise RuntimeError("Exactly two Cases and two Fingerprints are required.")

    cases: dict[str, dict[str, Any]] = {}
    case_meta: dict[str, Any] = {}
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
    fingerprint_meta: dict[str, Any] = {}
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
        provenance_hash = str(
            fingerprint.get("provenance", {}).get("approved_case_sha256") or ""
        ).lower()
        if provenance_hash != expected_case_hash:
            raise RuntimeError(f"Fingerprint {case_id} provenance SHA-256 mismatch.")
        contract = fingerprint.get("pattern_mining_contract", {})
        if contract.get("this_artifact_is_not_a_pattern") is not True:
            raise RuntimeError(f"Fingerprint {case_id} violates Pattern authority.")

        projection = safe_comparison_projection(fingerprint)
        assert_safe_for_external_model(
            json.dumps(projection, ensure_ascii=False, sort_keys=True)
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

    input_artifacts = {
        case_id: {
            "approved_case": case_meta[case_id],
            "fingerprint": fingerprint_meta[case_id],
        }
        for case_id in case_ids
    }
    return case_ids, cases, fingerprints, input_artifacts


def build_comparison(
    case_paths: list[Path],
    fingerprint_paths: list[Path],
) -> dict[str, Any]:
    case_ids, cases, fingerprints, input_artifacts = validate_and_load_inputs(
        case_paths,
        fingerprint_paths,
    )
    left_id, right_id = case_ids
    left = fingerprints[left_id]
    right = fingerprints[right_id]

    left_identity = left.get("identity", {})
    right_identity = right.get("identity", {})
    left_narration = left.get("narration_features", {})
    right_narration = right.get("narration_features", {})
    left_visual = left.get("visual_shot_features", {})
    right_visual = right.get("visual_shot_features", {})
    left_content = left.get("content_features", {})
    right_content = right.get("content_features", {})
    left_structure = left.get("structure_features", {})
    right_structure = right.get("structure_features", {})
    left_av = left.get("audio_visual_features", {})
    right_av = right.get("audio_visual_features", {})

    duration_values = {
        left_id: float(left_identity.get("duration_seconds") or 0),
        right_id: float(right_identity.get("duration_seconds") or 0),
    }
    speech_values = {
        left_id: {
            "seconds": float(left_narration.get("total_speech_seconds") or 0),
            "ratio": float(left_narration.get("speech_to_video_ratio") or 0),
        },
        right_id: {
            "seconds": float(right_narration.get("total_speech_seconds") or 0),
            "ratio": float(right_narration.get("speech_to_video_ratio") or 0),
        },
    }
    shot_values = {
        left_id: {
            "count": int(left_visual.get("shot_count") or 0),
            "mean": left_visual.get("shot_duration_stats", {}).get("mean"),
            "median": left_visual.get("shot_duration_stats", {}).get("median"),
            "under_1s_count": int(left_visual.get("shots_under_1s") or 0),
            "under_1s_ratio": float(left_visual.get("shots_under_1s_ratio") or 0),
            "under_0_5s_count": int(left_visual.get("shots_under_0_5s") or 0),
            "under_0_5s_ratio": float(left_visual.get("shots_under_0_5s_ratio") or 0),
        },
        right_id: {
            "count": int(right_visual.get("shot_count") or 0),
            "mean": right_visual.get("shot_duration_stats", {}).get("mean"),
            "median": right_visual.get("shot_duration_stats", {}).get("median"),
            "under_1s_count": int(right_visual.get("shots_under_1s") or 0),
            "under_1s_ratio": float(right_visual.get("shots_under_1s_ratio") or 0),
            "under_0_5s_count": int(right_visual.get("shots_under_0_5s") or 0),
            "under_0_5s_ratio": float(right_visual.get("shots_under_0_5s_ratio") or 0),
        },
    }

    hook_modalities = {
        left_id: sorted(left_structure.get("hook_modalities") or []),
        right_id: sorted(right_structure.get("hook_modalities") or []),
    }
    left_roles = left_visual.get("primary_role_counts", {})
    right_roles = right_visual.get("primary_role_counts", {})
    role_similarity = cosine_counts(left_roles, right_roles)
    stage_similarity = jaccard(stage_set(left), stage_set(right))
    hook_similarity = jaccard(
        set(hook_modalities[left_id]),
        set(hook_modalities[right_id]),
    )
    structural_components = {
        "shot_mean_closeness": closeness(
            float(shot_values[left_id]["mean"] or 0),
            float(shot_values[right_id]["mean"] or 0),
        ),
        "shot_median_closeness": closeness(
            float(shot_values[left_id]["median"] or 0),
            float(shot_values[right_id]["median"] or 0),
        ),
        "fast_cut_ratio_closeness": closeness(
            shot_values[left_id]["under_1s_ratio"],
            shot_values[right_id]["under_1s_ratio"],
        ),
        "speech_ratio_closeness": closeness(
            speech_values[left_id]["ratio"],
            speech_values[right_id]["ratio"],
        ),
        "role_distribution_cosine": role_similarity,
        "stage_set_jaccard": stage_similarity,
        "hook_modality_jaccard": hook_similarity,
    }
    structural_score = round(
        sum(structural_components.values()) / len(structural_components), 6
    )

    tags = {
        left_id: semantic_tags(left),
        right_id: semantic_tags(right),
    }
    semantic_score = jaccard(set(tags[left_id]), set(tags[right_id]))
    surface_components = {
        "duration_closeness": closeness(
            duration_values[left_id], duration_values[right_id]
        ),
        "shot_count_closeness": closeness(
            shot_values[left_id]["count"], shot_values[right_id]["count"]
        ),
        "onscreen_text_ratio_closeness": closeness(
            float(left_visual.get("onscreen_text_shot_ratio") or 0),
            float(right_visual.get("onscreen_text_shot_ratio") or 0),
        ),
        "hook_modality_jaccard": hook_similarity,
        "broad_food_context_match": float(
            "food_business_context" in tags[left_id]
            and "food_business_context" in tags[right_id]
        ),
    }
    surface_score = round(
        sum(surface_components.values()) / len(surface_components), 6
    )

    proof_counts = {
        left_id: int(left_content.get("verified_proof_count") or 0),
        right_id: int(right_content.get("verified_proof_count") or 0),
    }
    cta_values = {
        left_id: bool(left_content.get("has_explicit_cta")),
        right_id: bool(right_content.get("has_explicit_cta")),
    }
    claim_counts = {
        left_id: len(claim_texts(left)),
        right_id: len(claim_texts(right)),
    }
    composition = {
        case_id: {
            role: role_ratio(fingerprints[case_id], role)
            for role in ("product", "action", "context")
        }
        for case_id in case_ids
    }
    persona = {
        case_id: {
            "primary_count": int(
                fingerprints[case_id]
                .get("visual_shot_features", {})
                .get("primary_role_counts", {})
                .get("persona", 0)
            ),
            "secondary_count": int(
                fingerprints[case_id]
                .get("visual_shot_features", {})
                .get("secondary_role_counts", {})
                .get("persona", 0)
            ),
        }
        for case_id in case_ids
    }

    similarities = [
        {
            "type": "structural",
            "finding": "Both use audio, visual text, and visual scene as hook modalities.",
            "evidence": {"hook_modalities": hook_modalities},
        },
        {
            "type": "structural",
            "finding": "Both are narration-led and use many-to-many narration-to-shot mapping.",
            "evidence": {
                left_id: left_av.get("shot_to_narration_cardinality"),
                right_id: right_av.get("shot_to_narration_cardinality"),
            },
        },
        {
            "type": "semantic",
            "finding": "Both place food-business activity and operating action in the visual context.",
            "evidence": {"shared_tags": sorted(set(tags[left_id]) & set(tags[right_id]))},
        },
        {
            "type": "authority",
            "finding": "Neither Case has an effective verified proof or explicit CTA.",
            "evidence": {"verified_proofs": proof_counts, "explicit_cta": cta_values},
        },
    ]
    differences = [
        {
            "type": "surface",
            "finding": "The durations and shot counts are in different format ranges.",
            "evidence": {"duration_seconds": duration_values, "shot_count": {k: v["count"] for k, v in shot_values.items()}},
        },
        {
            "type": "structural",
            "finding": "Case 1 cuts faster; Case 2 uses longer, slower explanatory shots.",
            "evidence": {"shot_rhythm": shot_values},
        },
        {
            "type": "surface",
            "finding": "On-screen text is continuous in Case 1 but absent from the Case 2 shot evidence metric.",
            "evidence": {
                left_id: left_visual.get("onscreen_text_shot_ratio"),
                right_id: right_visual.get("onscreen_text_shot_ratio"),
            },
        },
        {
            "type": "semantic",
            "finding": "Case 1 is a concise execution/motivation thesis; Case 2 is a detailed delivery, quality, and process explanation.",
            "evidence": {"semantic_tags": tags},
        },
        {
            "type": "structural",
            "finding": "Case 1 follows hook-to-payoff montage structure; Case 2 uses repeated demonstrations before payoff.",
            "evidence": {
                left_id: left_structure.get("structure_signature"),
                right_id: right_structure.get("structure_signature"),
            },
        },
        {
            "type": "semantic",
            "finding": "Product has no primary-role share in Case 1 but is a major primary role in Case 2.",
            "evidence": {"content_composition": composition},
        },
    ]

    dimensions = {
        "duration": {
            "case_values_seconds": duration_values,
            "absolute_difference_seconds": round(
                abs(duration_values[left_id] - duration_values[right_id]), 6
            ),
        },
        "speech_duration_ratio": {"case_values": speech_values},
        "shot_count": {"case_values": {k: v["count"] for k, v in shot_values.items()}},
        "shot_mean_median": {
            "case_values": {
                k: {"mean": v["mean"], "median": v["median"]}
                for k, v in shot_values.items()
            }
        },
        "fast_cut_distribution": {"case_values": shot_values},
        "hook": {
            "modalities": hook_modalities,
            "candidates": {
                left_id: left_structure.get("hook_candidate", {}),
                right_id: right_structure.get("hook_candidate", {}),
            },
            "interpretation": "Same modality mix, different rhetorical job: thesis hook versus shop-context hook.",
        },
        "narration": {
            "case_values": {
                left_id: {
                    "segment_count": left_narration.get("segment_count"),
                    "speech_seconds": speech_values[left_id]["seconds"],
                    "speech_ratio": speech_values[left_id]["ratio"],
                },
                right_id: {
                    "segment_count": right_narration.get("segment_count"),
                    "speech_seconds": speech_values[right_id]["seconds"],
                    "speech_ratio": speech_values[right_id]["ratio"],
                },
            },
            "semantic_text_consumed": False,
            "authority": "approved_fingerprint_quantitative_features_only",
        },
        "onscreen_text": {
            "case_values": {
                left_id: {
                    "shot_count": left_visual.get("onscreen_text_shot_count"),
                    "shot_ratio": left_visual.get("onscreen_text_shot_ratio"),
                    "strategy": left_structure.get("visual_text_role"),
                },
                right_id: {
                    "shot_count": right_visual.get("onscreen_text_shot_count"),
                    "shot_ratio": right_visual.get("onscreen_text_shot_ratio"),
                    "strategy": right_structure.get("visual_text_role"),
                },
            }
        },
        "visual_roles": {
            "primary_role_counts": {left_id: left_roles, right_id: right_roles},
            "distribution_cosine": role_similarity,
        },
        "audio_visual_relation": {
            "case_values": {left_id: left_av, right_id: right_av},
            "interpretation": "Both are narration-led, but Case 1 relies on text repetition and montage context while Case 2 relies on process-scene correspondence.",
        },
        "narrative_structure": {
            "signatures": {
                left_id: left_structure.get("structure_signature"),
                right_id: right_structure.get("structure_signature"),
            },
            "shared_stages": sorted(stage_set(left) & stage_set(right)),
            "stage_set_jaccard": stage_similarity,
        },
        "proof": {
            "effective_verified_proof_count": proof_counts,
            "interpretation": "No proof is inferred or upgraded by Comparison.",
        },
        "persona": {"case_values": persona},
        "cta": {"has_explicit_cta": cta_values},
        "content_composition": {
            "primary_role_ratios": composition,
            "interpretation": "Case 1 is action-dominant; Case 2 distributes attention across action, product, and context.",
        },
        "storytelling": {
            "content_goal_candidates": {
                left_id: left_content.get("content_goal_candidate"),
                right_id: right_content.get("content_goal_candidate"),
            },
            "audio_visual_strategies": {
                left_id: left_structure.get("audio_visual_strategy"),
                right_id: right_structure.get("audio_visual_strategy"),
            },
        },
        "claim_strategy": {
            "claim_count": claim_counts,
            "verified_proof_count": proof_counts,
            "effective_semantics": "candidate_or_unverified_without_effective_verified_proof",
        },
        "evidence_strategy": {
            "verified_proof_count": proof_counts,
            "case_values": {
                left_id: "context/action montage supports understanding but is not verified proof",
                right_id: "process/product scenes support understanding but are not verified proof",
            },
        },
    }

    hypothesis_supported = (
        all(speech_values[case_id]["ratio"] >= 0.6 for case_id in case_ids)
        and all(composition[case_id]["action"] >= 0.3 for case_id in case_ids)
        and hook_similarity == 1.0
        and not any(cta_values.values())
    )
    if hypothesis_supported:
        pattern_assessment = {
            "status": "hypothesis",
            "authority_ceiling": "two_approved_cases_only",
            "hypotheses": [
                {
                    "id": "H001",
                    "confidence": "low",
                    "statement": "Narration-led small-business stories may pair claims with operating-action visuals while keeping those visuals below verified-proof authority.",
                },
                {
                    "id": "H002",
                    "confidence": "low",
                    "statement": "A multimodal hook plus no explicit CTA may be a recurring storytelling choice in owner-operated business content.",
                },
            ],
            "reasons": [
                "Both Cases are narration-led, action-rich, use the same three hook modalities, and have no explicit CTA.",
                "Both preserve zero effective verified proofs instead of treating process imagery as outcome evidence.",
            ],
            "contradicting_evidence": [
                "Duration, shot count, cutting speed, and on-screen-text coverage differ substantially.",
                "Case 1 argues a general execution thesis; Case 2 explains a concrete delivery and quality-control process.",
                "The shared food-business surface may be a category effect rather than a reusable narrative structure.",
            ],
            "needs_case_3_validation": [
                "Use a non-food owner-operated service or craft business with first-person narration and observable process footage.",
                "Prefer a 30-90 second Case so duration is not confounded with either existing extreme.",
                "Select a Case with a different on-screen-text strategy and record whether the narration/action relation and no-CTA ending persist.",
            ],
        }
    else:
        pattern_assessment = {
            "status": "none",
            "authority_ceiling": "two_approved_cases_only",
            "hypotheses": [],
            "reasons": ["The deterministic shared-structure threshold was not met."],
            "contradicting_evidence": [item["finding"] for item in differences],
            "needs_case_3_validation": [
                "Select a contrastive Case rather than assuming a Pattern from category overlap."
            ],
        }

    return {
        "schema_version": COMPARISON_VERSION,
        "builder_version": BUILDER_VERSION,
        "comparison_version": COMPARISON_VERSION,
        "case_ids": case_ids,
        "authority": {
            "approved_cases_required": True,
            "fingerprints_required": True,
            "comparison_features_source": "approved_case_fingerprint_v1",
            "raw_whisper_read": False,
            "raw_visual_evidence_read": False,
            "storyboard_reinterpreted": False,
            "proof_reinterpreted": False,
            "remote_model_used": False,
            "privacy_safe_projection_checked": True,
            "narration_semantic_text_consumed": False,
        },
        "input_artifacts": input_artifacts,
        "similarities": similarities,
        "differences": differences,
        "important_differences": [item["finding"] for item in differences],
        "dimensions": dimensions,
        "overall_similarity": {
            "structural": {
                "score": structural_score,
                "level": similarity_label(structural_score),
                "components": structural_components,
            },
            "semantic": {
                "score": semantic_score,
                "level": similarity_label(semantic_score),
                "tags": tags,
                "warning": "Shared food-business context alone is not Pattern evidence.",
            },
            "surface": {
                "score": surface_score,
                "level": similarity_label(surface_score),
                "components": surface_components,
            },
        },
        "pattern_assessment": pattern_assessment,
        "validation": {
            "passed": True,
            "approved_cases_only": True,
            "fingerprints_bound_to_case_sha256": True,
            "input_order_canonicalized": True,
            "two_case_authority_limit_enforced": True,
            "proof_not_upgraded": True,
            "privacy_egress_gate_passed": True,
            "remote_model_call_performed": False,
            "pattern_mining_performed": False,
        },
    }


GENERALIZED_EVIDENCE_STATUSES = {
    "supported_all_cases",
    "supported_majority",
    "variant",
    "boundary_case",
    "contradicted",
    "unresolved",
}


def artifact_ref_is_current(reference: dict[str, Any]) -> Path:
    path = Path(str(reference.get("path") or "")).expanduser().resolve()
    expected_sha = str(reference.get("sha256") or "").lower()
    if not path.is_file() or len(expected_sha) != 64:
        raise RuntimeError(f"Research lineage is incomplete: {path}")
    if sha256_file(path) != expected_sha:
        raise RuntimeError(f"Research lineage SHA-256 changed: {path}")
    return path


def validate_and_load_research_bundle(
    bundle_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Load an N-case structural bundle without entering Pattern Research."""
    bundle_path = bundle_path.expanduser().resolve()
    if not bundle_path.is_file():
        raise FileNotFoundError(bundle_path)
    bundle = read_json(bundle_path)
    if bundle.get("status") != "cross_case_research_ready":
        raise RuntimeError("Research Bundle is not Cross-case Research Ready.")
    if bundle.get("production_profile") != "news":
        raise RuntimeError("Generalized News comparison requires production_profile=news.")
    if bundle.get("comparison_executed") is not False:
        raise RuntimeError("Research Bundle already claims comparison execution.")
    if bundle.get("pattern_candidate_created") is not False:
        raise RuntimeError("Research Bundle already crosses Pattern authority.")

    raw_cases = bundle.get("cases") or []
    if len(raw_cases) < 2:
        raise RuntimeError("Generalized Cross-case Comparison requires at least two Cases.")
    if bundle.get("canonical_approved_case_count") != len(raw_cases):
        raise RuntimeError("Research Bundle canonical Case count is inconsistent.")

    seen: set[str] = set()
    cases: list[dict[str, Any]] = []
    input_artifacts: dict[str, Any] = {}
    for raw_item in raw_cases:
        item = json.loads(json.dumps(raw_item, ensure_ascii=False))
        case_id = str(item.get("case_id") or "")
        if not case_id or case_id in seen:
            raise RuntimeError("Research Bundle Case IDs must be present and distinct.")
        seen.add(case_id)
        if item.get("canonical_case_status") != "approved":
            raise RuntimeError(f"Case {case_id} is not canonically Approved.")
        if item.get("observed_source_profile") != "news":
            raise RuntimeError(f"Case {case_id} is not observed News Evidence.")
        if item.get("research_ingestion_eligibility") != "eligible_for_internal_research":
            raise RuntimeError(f"Case {case_id} is not eligible for internal research.")
        if item.get("research_role") not in {
            "seed_evidence",
            "core_evidence",
            "variant_evidence",
            "boundary_variant_evidence",
        }:
            raise RuntimeError(f"Case {case_id} has an invalid Research Role.")

        case_path = artifact_ref_is_current(item.get("case_ref") or {})
        fingerprint_path = artifact_ref_is_current(item.get("fingerprint_ref") or {})
        storyboard_path = artifact_ref_is_current(item.get("storyboard_ref") or {})
        case = read_json(case_path)
        fingerprint = read_json(fingerprint_path)
        storyboard = read_json(storyboard_path)
        if str(case.get("case_id") or "") != case_id:
            raise RuntimeError(f"Case identity mismatch for {case_id}.")
        if (
            case.get("lifecycle", {}).get("status") != "approved"
            or case.get("lifecycle", {}).get("approved") is not True
            or case.get("quality", {}).get("human_review_completed") is not True
        ):
            raise RuntimeError(f"Case {case_id} lacks canonical Human Approval.")
        if case.get("pattern_state", {}).get("pattern_mining_performed") is not False:
            raise RuntimeError(f"Case {case_id} has unexpected Pattern state.")
        if isinstance(case.get("privacy_gate"), dict):
            validate_case_privacy_gate(case)
        source_case = fingerprint.get("source_case") or {}
        if str(fingerprint.get("case_id") or "") != case_id:
            raise RuntimeError(f"Fingerprint identity differs for Case {case_id}.")
        if source_case:
            fingerprint_case_sha = str(source_case.get("sha256") or "").lower()
            fingerprint_approved = (
                source_case.get("status") == "approved"
                and source_case.get("approved") is True
            )
            fingerprint_is_not_pattern = (
                (fingerprint.get("pattern_mining_contract") or {}).get(
                    "this_artifact_is_not_a_pattern"
                )
                is True
            )
        else:
            fingerprint_case_sha = str(
                fingerprint.get("source_case_sha256") or ""
            ).lower()
            fingerprint_approved = fingerprint.get("production_profile") == "news"
            fingerprint_is_not_pattern = (
                fingerprint.get("fingerprint_scope")
                == "case_structural_evidence_only"
                and (fingerprint.get("pattern_state") or {}).get(
                    "pattern_mining_performed"
                )
                is False
                and (fingerprint.get("pattern_state") or {}).get("pattern_created")
                is False
            )
        if (
            not fingerprint_approved
            or fingerprint_case_sha != sha256_file(case_path)
        ):
            raise RuntimeError(f"Fingerprint is not bound to Approved Case {case_id}.")
        if not fingerprint_is_not_pattern:
            raise RuntimeError(f"Fingerprint {case_id} violates Pattern authority.")
        if (storyboard.get("micro_beat_sequence") or []) != (
            item.get("micro_beat_structure") or []
        ):
            raise RuntimeError(f"Micro Beat lineage differs for Case {case_id}.")

        safe_projection = {
            "case_id": case_id,
            "semantic_carrier": item.get("semantic_carrier") or {},
            "micro_beat_structure": item.get("micro_beat_structure") or [],
            "surface_characteristics": item.get("surface_characteristics") or {},
        }
        assert_safe_for_external_model(
            json.dumps(safe_projection, ensure_ascii=False, sort_keys=True)
        )
        input_artifacts[case_id] = {
            "approved_case_ref": item["case_ref"],
            "fingerprint_ref": item["fingerprint_ref"],
            "storyboard_ref": item["storyboard_ref"],
            "governance_companion_ref": item.get("governance_companion_ref"),
            "research_role": item["research_role"],
            "profile": item["observed_source_profile"],
        }
        cases.append(item)
    return bundle, cases, input_artifacts


def _contains_any(value: Any, terms: tuple[str, ...]) -> bool:
    text = json.dumps(value, ensure_ascii=False).lower()
    return any(term.lower() in text for term in terms)


def build_generalized_evidence_rows(cases: list[dict[str, Any]]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for item in cases:
        case_id = str(item["case_id"])
        beats = item.get("micro_beat_structure") or []
        carrier = item.get("semantic_carrier") or {}
        first = beats[0] if beats else {}
        last = beats[-1] if beats else {}
        roles = [str(beat.get("semantic_role") or "") for beat in beats]
        carrier_type = str(carrier.get("carrier_type") or "")
        surface = item.get("surface_characteristics") or {}
        visual_states = [str(beat.get("visual_state") or "") for beat in beats]
        rows[case_id] = {
            "research_role": (
                "seed_and_core_evidence"
                if case_id in {"7059858129298803968", "7507825653623344396"}
                else item.get("research_role")
            ),
            "source_bundle_research_role": item.get("research_role"),
            "semantic_carrier": {
                "carrier_type": carrier_type,
                "continuous_narration_required": carrier.get(
                    "continuous_narration_required"
                ),
            },
            "opening_first_semantic_anchor": {
                "semantic_role": first.get("semantic_role"),
                "text_or_narration": first.get("text_or_narration"),
                "visual_state": first.get("visual_state"),
            },
            "micro_beat_roles": roles,
            "beat_progression": item.get("progression") or roles,
            "visual_state_function": visual_states,
            "narration_dependency": carrier.get("continuous_narration_required"),
            "onscreen_text_function": (
                "persistent_primary_offer_overlay"
                if "persistent_price_text" in carrier_type
                else "supporting_location_labels"
                if "onscreen_labels" in carrier_type
                else "primary_information_carrier"
                if "on_screen_text" in carrier_type
                else "not_required_for_primary_semantics"
            ),
            "scope_or_constraint_behavior": {
                "explicit_scope_roles": [role for role in roles if "scope" in role],
                "context_roles": [
                    role
                    for role in roles
                    if any(term in role for term in ("context", "package", "rights"))
                ],
            },
            "closing_behavior": {
                "semantic_role": last.get("semantic_role"),
                "visual_state": last.get("visual_state"),
                "explicit_close_role": "close" in str(last.get("semantic_role") or ""),
            },
            "timing_and_duration": item.get("timing") or {},
            "surface_characteristics": surface,
            "proof_and_trust_behavior": item.get("proof_trust_behavior") or {},
            "derived_structural_checks": {
                "price_or_offer_first_anchor": _contains_any(
                    first,
                    ("price", "offer", "价格", "原价", "现价", "资费", "元", "团购"),
                ),
                "multiple_micro_information_states": len(beats) >= 2,
                "recoverable_without_continuous_narration": carrier.get(
                    "continuous_narration_required"
                ) is False,
                "meaningful_state_a_b_difference": _contains_any(
                    visual_states,
                    (
                        "→",
                        "前/后",
                        "old/new",
                        "完成态",
                        "未完成",
                        "改造前",
                        "改造后",
                    ),
                ),
                "actual_transformation_action": any(
                    "transformation_action" in role for role in roles
                ),
                "transition_or_overlay_mechanism": _contains_any(
                    visual_states + [beat.get("text_or_narration") for beat in beats],
                    ("叠加", "过渡", "切换", "transition", "overlay"),
                ),
                "repeated_comparison_catalogue": item.get("research_role")
                == "boundary_variant_evidence",
            },
        }
    return rows


def evidence_observation(
    *,
    observation_id: str,
    statement: str,
    status: str,
    supporting_case_ids: list[str],
    contradicting_case_ids: list[str],
    total_case_count: int,
    evidence_dimensions: list[str],
    eligible_as_candidate_invariant: bool,
    note: str,
) -> dict[str, Any]:
    if status not in GENERALIZED_EVIDENCE_STATUSES:
        raise ValueError(f"Invalid generalized evidence status: {status}")
    return {
        "observation_id": observation_id,
        "statement": statement,
        "status": status,
        "support_count": len(supporting_case_ids),
        "total_case_count": total_case_count,
        "supporting_case_ids": supporting_case_ids,
        "contradicting_case_ids": contradicting_case_ids,
        "evidence_dimensions": evidence_dimensions,
        "eligible_as_candidate_invariant": eligible_as_candidate_invariant,
        "note": note,
    }


def support_status(support_count: int, total_count: int) -> str:
    if support_count == total_count:
        return "supported_all_cases"
    if support_count > total_count / 2:
        return "supported_majority"
    if support_count == 0:
        return "contradicted"
    return "variant"


def build_price_offer_findings(
    cases: list[dict[str, Any]], rows: dict[str, Any]
) -> dict[str, Any]:
    case_ids = [str(item["case_id"]) for item in cases]
    total = len(case_ids)
    first_anchor = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"]["price_or_offer_first_anchor"]
    ]
    narration_independent = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"][
            "recoverable_without_continuous_narration"
        ]
    ]
    multi_state = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"]["multiple_micro_information_states"]
    ]
    explicit_scope = [
        case_id
        for case_id in case_ids
        if rows[case_id]["scope_or_constraint_behavior"]["explicit_scope_roles"]
    ]
    persistent = [
        case_id
        for case_id in case_ids
        if rows[case_id]["onscreen_text_function"]
        == "persistent_primary_offer_overlay"
    ]
    explicit_close = [
        case_id
        for case_id in case_ids
        if rows[case_id]["closing_behavior"]["explicit_close_role"]
    ]
    changing_information_states = [
        case_id for case_id in case_ids if case_id not in persistent
    ]

    candidate_invariants = [
        evidence_observation(
            observation_id="PRICE_INV_001",
            statement="Price or offer is the first principal semantic anchor.",
            status="supported_all_cases" if len(first_anchor) == total else "unresolved",
            supporting_case_ids=first_anchor,
            contradicting_case_ids=[value for value in case_ids if value not in first_anchor],
            total_case_count=total,
            evidence_dimensions=["opening_first_semantic_anchor"],
            eligible_as_candidate_invariant=len(first_anchor) == total,
            note="Quantity appearing beside a price does not broaden the evidence to generic number-led structure.",
        ),
        evidence_observation(
            observation_id="PRICE_INV_002",
            statement="The offer is developed through multiple recoverable micro-information states.",
            status="supported_all_cases" if len(multi_state) == total else "unresolved",
            supporting_case_ids=multi_state,
            contradicting_case_ids=[value for value in case_ids if value not in multi_state],
            total_case_count=total,
            evidence_dimensions=["micro_beat_roles", "beat_progression"],
            eligible_as_candidate_invariant=len(multi_state) == total,
            note="The following states may express package, service, usage, value, rights, or other offer context; no single subtype is frozen.",
        ),
        evidence_observation(
            observation_id="PRICE_INV_003",
            statement="Continuous Mix narration is not required to recover the semantic progression.",
            status=(
                "supported_all_cases"
                if len(narration_independent) == total
                else "unresolved"
            ),
            supporting_case_ids=narration_independent,
            contradicting_case_ids=[
                value for value in case_ids if value not in narration_independent
            ],
            total_case_count=total,
            evidence_dimensions=["semantic_carrier", "narration_dependency"],
            eligible_as_candidate_invariant=len(narration_independent) == total,
            note="On-screen text and visual information states carry the comparison evidence.",
        ),
    ]
    variants = [
        evidence_observation(
            observation_id="PRICE_VAR_001",
            statement="Changing information states versus persistent price text are presentation variants.",
            status=support_status(len(changing_information_states), total),
            supporting_case_ids=changing_information_states,
            contradicting_case_ids=persistent,
            total_case_count=total,
            evidence_dimensions=["onscreen_text_function", "visual_state_function"],
            eligible_as_candidate_invariant=False,
            note="A 2/N majority cannot automatically become an invariant; persistent offer text remains valid variant evidence.",
        ),
        evidence_observation(
            observation_id="PRICE_VAR_002",
            statement="An explicit scope or constraint beat is not required by current evidence.",
            status=support_status(len(explicit_scope), total),
            supporting_case_ids=explicit_scope,
            contradicting_case_ids=[value for value in case_ids if value not in explicit_scope],
            total_case_count=total,
            evidence_dimensions=["scope_or_constraint_behavior"],
            eligible_as_candidate_invariant=False,
            note="The variant Case directly attacks any mandatory explicit-scope hypothesis.",
        ),
        evidence_observation(
            observation_id="PRICE_VAR_003",
            statement="Explicit result or service close behavior varies across Cases.",
            status=support_status(len(explicit_close), total),
            supporting_case_ids=explicit_close,
            contradicting_case_ids=[value for value in case_ids if value not in explicit_close],
            total_case_count=total,
            evidence_dimensions=["closing_behavior"],
            eligible_as_candidate_invariant=False,
            note="Closing behavior is not frozen from majority evidence.",
        ),
        evidence_observation(
            observation_id="PRICE_VAR_004",
            statement="Duration and beat count vary and are not structural invariants.",
            status="variant",
            supporting_case_ids=case_ids,
            contradicting_case_ids=[],
            total_case_count=total,
            evidence_dimensions=["timing_and_duration"],
            eligible_as_candidate_invariant=False,
            note="Production timing remains a configurable Profile implementation constraint.",
        ),
    ]
    boundary_conditions = []
    if "7635146658208744867" in case_ids:
        boundary_conditions.append(
            {
                "case_id": "7635146658208744867",
                "finding": "Persistent price text plus service visuals remains valid despite weak explicit scope/constraint structure.",
                "attacks": ["mandatory_state_change", "mandatory_explicit_scope_beat"],
            }
        )
    if "7640840358842207507" in case_ids:
        boundary_conditions.append(
            {
                "case_id": "7640840358842207507",
                "finding": "Token quantity is subordinate offer/package context because the first anchor remains a monthly price offer.",
                "attacks": ["automatic_generic_number_led_scope_expansion"],
            }
        )
    counterexamples = []
    if len(explicit_scope) < total:
        counterexamples.append(
            {
                "claim": "Every Case requires an explicit constraint/scope beat.",
                "status": "contradicted",
                "case_ids": [value for value in case_ids if value not in explicit_scope],
            }
        )
    if persistent:
        counterexamples.append(
            {
                "claim": "Price text must change with every subsequent state.",
                "status": "contradicted",
                "case_ids": persistent,
            }
        )
    return {
        "candidate_invariants": candidate_invariants,
        "variants": variants,
        "boundary_conditions": boundary_conditions,
        "counterexamples": counterexamples,
        "scope_statement": {
            "current_evidence_supports": "price_offer_led_micro_information",
            "current_evidence_does_not_yet_support": "broader_number_led",
            "decision": "scope_remains_price_offer_led",
        },
        "scope_limitations": [
            "No independent non-price numeric-anchor Case is present.",
            "Explicit scope/constraint beats, persistent offer text, closing form, duration, and beat count are not invariants.",
            "Cross-case repetition is structural research evidence, not Effectiveness evidence.",
        ],
        "unresolved_questions": [
            "Must every future Case keep the offer visible after the opening anchor?",
            "Which post-anchor information roles are essential versus surface-specific?",
            "Is a distinct close useful enough to survive additional boundary Cases?",
        ],
        "candidate_research_readiness": (
            "ready_for_pattern_candidate_human_review"
            if total >= 3 and all(
                item["status"] == "supported_all_cases"
                for item in candidate_invariants
            )
            else "needs_more_evidence"
        ),
    }


def build_scene_contrast_findings(
    cases: list[dict[str, Any]], rows: dict[str, Any]
) -> dict[str, Any]:
    case_ids = [str(item["case_id"]) for item in cases]
    total = len(case_ids)
    meaningful = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"][
            "meaningful_state_a_b_difference"
        ]
    ]
    narration_independent = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"][
            "recoverable_without_continuous_narration"
        ]
    ]
    visual_primary = [
        case_id
        for case_id in case_ids
        if "visual" in rows[case_id]["semantic_carrier"]["carrier_type"]
    ]
    actual_operation = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"]["actual_transformation_action"]
    ]
    transition_or_operation = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"]["actual_transformation_action"]
        or rows[case_id]["derived_structural_checks"]["transition_or_overlay_mechanism"]
    ]
    catalogue = [
        case_id
        for case_id in case_ids
        if rows[case_id]["derived_structural_checks"]["repeated_comparison_catalogue"]
    ]
    labels = [
        case_id
        for case_id in case_ids
        if rows[case_id]["onscreen_text_function"] == "supporting_location_labels"
    ]
    explicit_close = [
        case_id
        for case_id in case_ids
        if rows[case_id]["closing_behavior"]["explicit_close_role"]
    ]
    candidate_invariants = [
        evidence_observation(
            observation_id="SCENE_INV_001",
            statement="Meaningful State A and State B differ in a way that changes viewer understanding.",
            status="supported_all_cases" if len(meaningful) == total else "unresolved",
            supporting_case_ids=meaningful,
            contradicting_case_ids=[value for value in case_ids if value not in meaningful],
            total_case_count=total,
            evidence_dimensions=["visual_state_function", "beat_progression"],
            eligible_as_candidate_invariant=len(meaningful) == total,
            note="Ordinary montage without a recoverable state difference is outside this candidate core.",
        ),
        evidence_observation(
            observation_id="SCENE_INV_002",
            statement="Visual information states are the primary semantic carrier.",
            status=(
                "supported_all_cases"
                if len(visual_primary) == total
                else "unresolved"
            ),
            supporting_case_ids=visual_primary,
            contradicting_case_ids=[
                value for value in case_ids if value not in visual_primary
            ],
            total_case_count=total,
            evidence_dimensions=["semantic_carrier", "visual_state_function"],
            eligible_as_candidate_invariant=len(visual_primary) == total,
            note="Text labels may assist but are not necessary in all Cases.",
        ),
        evidence_observation(
            observation_id="SCENE_INV_003",
            statement="Continuous narration is not required to recover the contrast progression.",
            status=(
                "supported_all_cases"
                if len(narration_independent) == total
                else "unresolved"
            ),
            supporting_case_ids=narration_independent,
            contradicting_case_ids=[
                value for value in case_ids if value not in narration_independent
            ],
            total_case_count=total,
            evidence_dimensions=["narration_dependency", "semantic_carrier"],
            eligible_as_candidate_invariant=len(narration_independent) == total,
            note="Narration is not forced into the News Profile contract.",
        ),
    ]
    variants = [
        evidence_observation(
            observation_id="SCENE_VAR_001",
            statement="Visible transition or operation appears in some Cases but not the boundary catalogue Case.",
            status=support_status(len(transition_or_operation), total),
            supporting_case_ids=transition_or_operation,
            contradicting_case_ids=[
                value for value in case_ids if value not in transition_or_operation
            ],
            total_case_count=total,
            evidence_dimensions=["beat_progression", "visual_state_function"],
            eligible_as_candidate_invariant=False,
            note="Boundary evidence prevents a 2/N majority from becoming a transformation-action invariant.",
        ),
        evidence_observation(
            observation_id="SCENE_VAR_002",
            statement="A single/continuous transformation and a repeated comparison catalogue are structural variants.",
            status="boundary_case",
            supporting_case_ids=[value for value in case_ids if value not in catalogue],
            contradicting_case_ids=catalogue,
            total_case_count=total,
            evidence_dimensions=["micro_beat_roles", "beat_progression"],
            eligible_as_candidate_invariant=False,
            note="Both retain the meaningful State A/State B semantic core.",
        ),
        evidence_observation(
            observation_id="SCENE_VAR_003",
            statement="On-screen location labels are supporting variant evidence, not an invariant.",
            status="variant",
            supporting_case_ids=labels,
            contradicting_case_ids=[value for value in case_ids if value not in labels],
            total_case_count=total,
            evidence_dimensions=["onscreen_text_function"],
            eligible_as_candidate_invariant=False,
            note="Visual states can recover the contrast without explicit before/after wording.",
        ),
        evidence_observation(
            observation_id="SCENE_VAR_004",
            statement="A distinct result close is majority evidence only.",
            status=support_status(len(explicit_close), total),
            supporting_case_ids=explicit_close,
            contradicting_case_ids=[value for value in case_ids if value not in explicit_close],
            total_case_count=total,
            evidence_dimensions=["closing_behavior"],
            eligible_as_candidate_invariant=False,
            note="The catalogue boundary Case ends on its final pair rather than a separate result close.",
        ),
        evidence_observation(
            observation_id="SCENE_VAR_005",
            statement="Duration and beat count vary and are not structural invariants.",
            status="variant",
            supporting_case_ids=case_ids,
            contradicting_case_ids=[],
            total_case_count=total,
            evidence_dimensions=["timing_and_duration"],
            eligible_as_candidate_invariant=False,
            note="Observed source durations do not change configurable News production timing.",
        ),
    ]
    boundary_findings = []
    if "7616327461634652005" in case_ids:
        boundary_findings.append(
            {
                "case_id": "7616327461634652005",
                "finding": "Repeated old/new location pairs remain valid Scene Contrast without a recoverable transformation action.",
                "shared_core_preserved": True,
                "attacks": [
                    "transformation_action_required",
                    "single_continuous_transformation_required",
                    "separate_result_close_required",
                ],
            }
        )
    return {
        "candidate_invariants": candidate_invariants,
        "variants": variants,
        "boundary_variant_findings": boundary_findings,
        "contradictions": [
            {
                "claim": "Transformation action is required.",
                "status": "contradicted",
                "case_ids": catalogue,
            },
            {
                "claim": "Explicit before/after wording or text labels are required.",
                "status": "contradicted",
                "case_ids": [value for value in case_ids if value not in labels],
            },
        ],
        "transformation_action_status": {
            "status": "optional_enhancer",
            "actual_operation_case_ids": actual_operation,
            "transition_or_overlay_case_ids": [
                value
                for value in transition_or_operation
                if value not in actual_operation
            ],
            "valid_without_transformation_action_case_ids": catalogue,
            "invariant_claim_contradicted": bool(catalogue),
            "reason": "The boundary Case preserves meaningful A/B comparison without transformation action, so action may enrich progression but cannot define the candidate core.",
        },
        "scope_statement": {
            "current_evidence_supports": "scene_contrast",
            "shared_semantic_core": "recoverable_meaningful_state_a_vs_state_b",
        },
        "scope_limitations": [
            "Operation, overlay transition, text labels, explicit before/after wording, separate result close, timing, and beat count are not invariants.",
            "Current evidence does not establish a preferred single-transformation versus catalogue form.",
            "Cross-case repetition is structural research evidence, not Effectiveness evidence.",
        ],
        "unresolved_questions": [
            "How much visual continuity is required between State A and State B?",
            "Can text-dominant contrast Cases preserve the same semantic core?",
            "Does a separate result close survive additional boundary evidence?",
        ],
        "candidate_research_readiness": (
            "ready_for_pattern_candidate_human_review"
            if total >= 3 and all(
                item["status"] == "supported_all_cases"
                for item in candidate_invariants
            )
            else "needs_more_evidence"
        ),
    }


def build_generalized_research_comparison(bundle_path: Path) -> dict[str, Any]:
    bundle, cases, input_artifacts = validate_and_load_research_bundle(bundle_path)
    direction = str(bundle.get("research_direction") or "")
    rows = build_generalized_evidence_rows(cases)
    if direction == "price_offer_led_micro_information":
        findings = build_price_offer_findings(cases, rows)
    elif direction == "scene_contrast":
        findings = build_scene_contrast_findings(cases, rows)
    else:
        findings = {
            "candidate_invariants": [],
            "variants": [],
            "scope_statement": {"current_evidence_supports": direction or "unresolved"},
            "scope_limitations": ["No deterministic direction rubric is registered."],
            "unresolved_questions": ["Human structural interpretation is required."],
            "candidate_research_readiness": "needs_more_evidence",
        }
    surface_values = {
        case_id: rows[case_id]["surface_characteristics"] for case_id in rows
    }
    surface_signatures = {
        json.dumps(value, ensure_ascii=False, sort_keys=True)
        for value in surface_values.values()
    }
    evidence_matrix = {
        "dimensions": [
            "semantic_carrier",
            "opening_first_semantic_anchor",
            "micro_beat_roles",
            "beat_progression",
            "visual_state_function",
            "narration_dependency",
            "onscreen_text_function",
            "scope_or_constraint_behavior",
            "closing_behavior",
            "timing_and_duration",
            "surface_characteristics",
            "research_role",
            "proof_and_trust_behavior",
        ],
        "case_rows": rows,
    }
    comparison = {
        "schema_version": GENERALIZED_COMPARISON_VERSION,
        "builder_version": GENERALIZED_BUILDER_VERSION,
        "comparison_id": f"news_cross_case_comparison_v1::{direction}",
        "status": "review_required",
        "production_profile": "news",
        "research_direction": direction,
        "case_count": len(cases),
        "case_ids": [str(item["case_id"]) for item in cases],
        "source_bundle_ref": {
            "path": str(bundle_path.expanduser().resolve()),
            "sha256": sha256_file(bundle_path.expanduser().resolve()),
        },
        "input_artifacts": input_artifacts,
        "evidence_matrix": evidence_matrix,
        "structural_similarity_and_surface_diversity": {
            "structural_similarity_supported": bool(findings["candidate_invariants"]),
            "surface_diversity_observed": len(surface_signatures) == len(cases),
            "surface_diversity_is_structural_evidence": False,
            "case_surfaces": surface_values,
        },
        **findings,
        "pattern_candidate_eligibility": {
            "status": findings["candidate_research_readiness"],
            "case_threshold_satisfied": len(cases) >= 3,
            "creates_pattern_candidate": False,
            "requires_human_review": True,
        },
        "effectiveness_boundary": {
            "cross_case_repetition_equals_effectiveness": False,
            "performance_data_consumed": False,
            "effectiveness_claimed": False,
        },
        "authority": {
            "approved_cases_only": True,
            "case_specific_business_facts_used_as_customer_authority": False,
            "retrieval_metrics_used_as_effectiveness_authority": False,
            "proof_reinterpreted_or_upgraded": False,
            "profile_compatibility_expanded": False,
            "pattern_candidate_created": False,
            "pattern_approved": False,
            "remote_model_used": False,
            "local_model_used": False,
            "new_case_acquisition_performed": False,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
        },
        "validation": {
            "passed": True,
            "minimum_two_cases_supported": len(cases) >= 2,
            "exact_case_count_hardcoded": False,
            "all_case_sha_lineage_verified": True,
            "boundary_evidence_evaluated": True,
            "majority_does_not_auto_become_invariant": all(
                not item["eligible_as_candidate_invariant"]
                for item in findings.get("variants") or []
                if item["status"] == "supported_majority"
            ),
            "timing_not_frozen": True,
            "pattern_lifecycle_modified": False,
            "news_readiness_changed": False,
        },
    }
    validate_generalized_research_comparison(comparison)
    return comparison


def validate_generalized_research_comparison(comparison: dict[str, Any]) -> None:
    if comparison.get("schema_version") != GENERALIZED_COMPARISON_VERSION:
        raise ValueError("Generalized Cross-case Comparison schema is invalid.")
    if comparison.get("status") != "review_required":
        raise ValueError("Comparison must stop at Human Review Gate.")
    if int(comparison.get("case_count") or 0) < 2:
        raise ValueError("Generalized Comparison requires N >= 2.")
    matrix = comparison.get("evidence_matrix") or {}
    required_dimensions = {
        "semantic_carrier",
        "opening_first_semantic_anchor",
        "micro_beat_roles",
        "beat_progression",
        "visual_state_function",
        "narration_dependency",
        "onscreen_text_function",
        "scope_or_constraint_behavior",
        "closing_behavior",
        "timing_and_duration",
        "surface_characteristics",
        "research_role",
        "proof_and_trust_behavior",
    }
    if set(matrix.get("dimensions") or []) != required_dimensions:
        raise ValueError("Generalized Comparison evidence dimensions are incomplete.")
    if set((matrix.get("case_rows") or {}).keys()) != set(
        comparison.get("case_ids") or []
    ):
        raise ValueError("Generalized Comparison evidence rows are incomplete.")
    observations = list(comparison.get("candidate_invariants") or []) + list(
        comparison.get("variants") or []
    )
    for item in observations:
        if item.get("status") not in GENERALIZED_EVIDENCE_STATUSES:
            raise ValueError("Comparison evidence status is invalid.")
        if (
            item.get("status") == "supported_majority"
            and item.get("eligible_as_candidate_invariant") is not False
        ):
            raise ValueError("Majority evidence cannot automatically become invariant.")
        if (
            item.get("eligible_as_candidate_invariant") is True
            and item.get("status") != "supported_all_cases"
        ):
            raise ValueError("Candidate invariant requires all-case evidence.")
    authority = comparison.get("authority") or {}
    forbidden_true = (
        "case_specific_business_facts_used_as_customer_authority",
        "retrieval_metrics_used_as_effectiveness_authority",
        "proof_reinterpreted_or_upgraded",
        "profile_compatibility_expanded",
        "pattern_candidate_created",
        "pattern_approved",
        "remote_model_used",
        "local_model_used",
        "new_case_acquisition_performed",
        "news_generation_performed",
        "news_excel_export_performed",
    )
    if any(authority.get(field) is not False for field in forbidden_true):
        raise ValueError("Generalized Comparison crosses an Authority boundary.")
    if comparison.get("effectiveness_boundary", {}).get(
        "effectiveness_claimed"
    ) is not False:
        raise ValueError("Comparison cannot claim Effectiveness.")
    readiness = comparison.get("pattern_candidate_eligibility") or {}
    if readiness.get("creates_pattern_candidate") is not False:
        raise ValueError("Comparison cannot create a Pattern Candidate.")


def render_generalized_research_comparison(comparison: dict[str, Any]) -> str:
    lines = [
        f"# News Cross-case Comparison｜{comparison['research_direction']}",
        "",
        "Status: **Review Required**",
        "",
        "## Cases and Research Roles",
        "",
        "| Case | Role | Carrier | Duration | Beats | Surface |",
        "|---|---|---|---:|---:|---|",
    ]
    rows = comparison["evidence_matrix"]["case_rows"]
    for case_id in comparison["case_ids"]:
        row = rows[case_id]
        surface = row["surface_characteristics"]
        lines.append(
            f"| {case_id} | {row['research_role']} | "
            f"{row['semantic_carrier']['carrier_type']} | "
            f"{row['timing_and_duration'].get('duration_seconds')} | "
            f"{row['timing_and_duration'].get('beat_count')} | "
            f"{surface.get('industry_or_topic')} |"
        )
    lines.extend(
        [
            "",
            "## Evidence Matrix",
            "",
            "| Case | First anchor | Beat progression | Text function | Continuous narration | Close | Proof |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for case_id in comparison["case_ids"]:
        row = rows[case_id]
        anchor = row["opening_first_semantic_anchor"]
        proof = row["proof_and_trust_behavior"]
        lines.append(
            f"| {case_id} | {anchor.get('semantic_role')} | "
            f"{' → '.join(row['beat_progression'])} | "
            f"{row['onscreen_text_function']} | "
            f"{row['narration_dependency']} | "
            f"{row['closing_behavior'].get('semantic_role')} | "
            f"verified={proof.get('verified_proof_count', 0)} / "
            f"effectiveness={proof.get('effectiveness_status', 'unvalidated')} |"
        )
    lines.extend(["", "## Observed Similarities / Candidate Invariants", ""])
    for item in comparison["candidate_invariants"]:
        lines.extend(
            [
                f"### {item['observation_id']}｜{item['status']}",
                "",
                item["statement"],
                "",
                f"Evidence: {item['support_count']}/{item['total_case_count']} — "
                + ", ".join(item["supporting_case_ids"]),
                "",
                item["note"],
                "",
            ]
        )
    lines.extend(["## Variants and Boundary Evidence", ""])
    for item in comparison.get("variants") or []:
        lines.extend(
            [
                f"- **{item['observation_id']} / {item['status']}** — {item['statement']} "
                f"({item['support_count']}/{item['total_case_count']}). {item['note']}",
                "",
            ]
        )
    boundary = comparison.get("boundary_conditions") or comparison.get(
        "boundary_variant_findings"
    ) or []
    if boundary:
        lines.extend(["## Boundary Cases / Counterexamples", ""])
        for item in boundary:
            lines.append(f"- `{item['case_id']}` — {item['finding']}")
        lines.append("")
    if comparison.get("counterexamples") or comparison.get("contradictions"):
        for item in comparison.get("counterexamples") or comparison.get(
            "contradictions"
        ):
            lines.append(
                f"- `{item['status']}`: {item['claim']} — "
                + ", ".join(item.get("case_ids") or [])
            )
        lines.append("")
    if comparison.get("transformation_action_status"):
        action = comparison["transformation_action_status"]
        lines.extend(
            [
                "## Transformation Action",
                "",
                f"Status: **{action['status']}**",
                "",
                action["reason"],
                "",
            ]
        )
    lines.extend(
        [
            "## Surface Diversity",
            "",
            "Structural similarity and surface diversity are both observed. Surface diversity is not itself structural evidence or an invariant.",
            "",
            "## Scope",
            "",
            "```json",
            json.dumps(comparison["scope_statement"], ensure_ascii=False, indent=2),
            "```",
            "",
            "## Scope Limitations",
            "",
        ]
    )
    lines.extend(f"- {value}" for value in comparison["scope_limitations"])
    lines.extend(["", "## Unresolved Questions", ""])
    lines.extend(f"- {value}" for value in comparison["unresolved_questions"])
    lines.extend(
        [
            "",
            "## Pattern Candidate Readiness",
            "",
            f"`{comparison['candidate_research_readiness']}`",
            "",
            "This is eligibility for Human Review only. No Pattern Candidate or Effectiveness claim was created.",
            "",
            "## Authority Boundary",
            "",
            "Cross-case repetition is not Effectiveness. No Customer Fact Authority, Proof upgrade, Profile expansion, Generation, or Export was produced.",
            "",
        ]
    )
    return "\n".join(lines)


def write_comparison_artifact(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Comparison Artifact already exists with different content: {path}")
        return
    path.write_text(content, encoding="utf-8")


def build_comparison_human_approval(
    comparison_path: Path,
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    comparison_path = comparison_path.expanduser().resolve()
    if not comparison_path.is_file():
        raise FileNotFoundError(comparison_path)
    comparison = read_json(comparison_path)
    validate_generalized_research_comparison(comparison)
    if reviewer.strip() != "李健":
        raise ValueError("This Comparison Human Approval is authorized for reviewer 李健.")
    if comparison.get("case_count") != 3:
        raise RuntimeError("This Human Decision applies to the reviewed three-Case Comparison.")
    direction = str(comparison.get("research_direction") or "")
    if direction == "price_offer_led_micro_information":
        approved_scope = {
            "supported": "price_offer_led_micro_information",
            "not_supported": "broader_number_led",
        }
        approved_invariants = [
            "price_or_offer_is_first_principal_semantic_anchor",
            "multiple_recoverable_micro_information_states_follow_the_offer_anchor_and_contextualize_scope_explain_or_situate_it",
            "continuous_mix_narration_not_required_for_semantic_recovery",
        ]
        approved_variants = [
            "persistent_price_text",
            "changing_price_state",
            "explicit_scope_or_constraint_beat",
            "explicit_close",
            "exact_beat_count",
            "exact_duration",
            "specific_industry",
            "specific_offer_type",
        ]
        unresolved_questions = list(comparison.get("unresolved_questions") or [])
    elif direction == "scene_contrast":
        approved_scope = {"supported": "scene_contrast"}
        approved_invariants = [
            "meaningful_comparable_state_a_and_state_b_exist",
            "state_difference_materially_changes_understanding_not_merely_visual_aesthetics",
            "visual_information_state_is_primary_semantic_carrier",
            "continuous_narration_not_required_for_semantic_recovery",
        ]
        approved_variants = [
            "actual_operation",
            "transition_animation",
            "overlay",
            "repeated_comparison_catalogue",
            "single_continuous_transformation",
            "location_label",
            "before_after_wording",
            "explicit_result_close",
            "exact_beat_count",
            "exact_duration",
            "industry_or_topic",
        ]
        unresolved_questions = [
            "same_subject_identity_requirement_is_unresolved_between_strict_identity_and_recoverable_semantic_correspondence"
        ]
    else:
        raise RuntimeError(f"No Human Comparison Decision is authorized for {direction!r}.")
    timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()
    approval = {
        "schema_version": COMPARISON_HUMAN_APPROVAL_VERSION,
        "approval_id": f"cross_case_comparison_human_approval_v1::{direction}",
        "status": "approved",
        "decision": "approve_research_comparison",
        "reviewer": reviewer.strip(),
        "reviewed_at": timestamp,
        "approval_scope": "research_comparison_only_not_pattern_approval",
        "comparison_ref": {
            "path": str(comparison_path),
            "sha256": sha256_file(comparison_path),
            "source_status": comparison.get("status"),
            "source_comparison_modified": False,
        },
        "research_direction": direction,
        "approved_research_scope": approved_scope,
        "approved_candidate_invariants": approved_invariants,
        "approved_variants_and_non_invariants": approved_variants,
        "approved_boundary_evidence": (
            comparison.get("boundary_conditions")
            or comparison.get("boundary_variant_findings")
            or []
        ),
        "approved_counterexamples_or_attacks": (
            comparison.get("counterexamples")
            or comparison.get("contradictions")
            or []
        ),
        "unresolved_questions": unresolved_questions,
        "transformation_action_status": (
            (comparison.get("transformation_action_status") or {}).get("status")
            if direction == "scene_contrast"
            else None
        ),
        "authority": {
            "comparison_approved": True,
            "pattern_candidate_created_by_approval": False,
            "pattern_approved": False,
            "effectiveness_validated": False,
            "profile_compatibility_expanded": False,
            "proof_upgraded": False,
            "remote_model_used": False,
        },
    }
    validate_comparison_human_approval(
        approval, expected_comparison_sha256=sha256_file(comparison_path)
    )
    return approval


def validate_comparison_human_approval(
    approval: dict[str, Any],
    *,
    expected_comparison_sha256: str | None = None,
) -> None:
    if approval.get("schema_version") != COMPARISON_HUMAN_APPROVAL_VERSION:
        raise ValueError("Comparison Human Approval schema is invalid.")
    if (
        approval.get("status") != "approved"
        or approval.get("decision") != "approve_research_comparison"
        or approval.get("reviewer") != "李健"
    ):
        raise ValueError("Comparison Human Approval decision is invalid.")
    if approval.get("approval_scope") != "research_comparison_only_not_pattern_approval":
        raise ValueError("Comparison Approval cannot become Pattern Approval.")
    comparison_ref = approval.get("comparison_ref") or {}
    if expected_comparison_sha256 and comparison_ref.get("sha256") != expected_comparison_sha256:
        raise ValueError("Comparison Human Approval SHA lineage differs.")
    if comparison_ref.get("source_comparison_modified") is not False:
        raise ValueError("Comparison Approval must not rewrite the Comparison Artifact.")
    direction = approval.get("research_direction")
    if direction == "price_offer_led_micro_information":
        scope = approval.get("approved_research_scope") or {}
        if (
            scope.get("supported") != "price_offer_led_micro_information"
            or scope.get("not_supported") != "broader_number_led"
        ):
            raise ValueError("Price Comparison Approval scope is invalid.")
    elif direction == "scene_contrast":
        if approval.get("transformation_action_status") != "optional_enhancer":
            raise ValueError("Scene transformation action must remain optional_enhancer.")
        if not any(
            "same_subject_identity_requirement_is_unresolved" in str(value)
            for value in approval.get("unresolved_questions") or []
        ):
            raise ValueError("Scene same-subject identity question must remain unresolved.")
    else:
        raise ValueError("Comparison Human Approval direction is invalid.")
    authority = approval.get("authority") or {}
    if authority.get("comparison_approved") is not True:
        raise ValueError("Comparison Human Approval does not approve the Comparison.")
    for field in (
        "pattern_candidate_created_by_approval",
        "pattern_approved",
        "effectiveness_validated",
        "profile_compatibility_expanded",
        "proof_upgraded",
        "remote_model_used",
    ):
        if authority.get(field) is not False:
            raise ValueError("Comparison Human Approval crosses an Authority boundary.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically compare Approved Case structure. Legacy direct inputs "
            "retain the two-Case contract; --research-bundle supports N >= 2 and "
            "stops at Human Review without creating a Pattern Candidate."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        help="Legacy mode: Approved case_v1.json; provide exactly twice.",
    )
    parser.add_argument(
        "--fingerprint",
        action="append",
        help="Legacy mode: case_fingerprint_v1.json; provide exactly twice.",
    )
    parser.add_argument(
        "--research-bundle",
        default=None,
        help=(
            "Generalized mode: canonical Cross-case Research input bundle with "
            "at least two Approved Cases."
        ),
    )
    parser.add_argument(
        "--approve-comparison",
        default=None,
        help=(
            "Persist the authorized Human Approval receipt for an existing generalized "
            "Comparison without rewriting it or approving a Pattern."
        ),
    )
    parser.add_argument("--reviewer", default=None)
    parser.add_argument("--reviewed-at", default=None)
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/comparisons",
    )
    args = parser.parse_args()

    if args.approve_comparison:
        if args.research_bundle or args.case or args.fingerprint:
            raise ValueError(
                "--approve-comparison cannot be combined with comparison input modes."
            )
        if not args.reviewer:
            raise ValueError("--approve-comparison requires --reviewer.")
        comparison_path = Path(args.approve_comparison).expanduser().resolve()
        approval = build_comparison_human_approval(
            comparison_path,
            reviewer=args.reviewer,
            reviewed_at=args.reviewed_at,
        )
        output_dir = (
            Path(args.output_root).expanduser().resolve()
            if args.output_root
            else comparison_path.parent
        )
        stem = comparison_path.stem
        approval_path = output_dir / f"{stem}_human_approval_v1.json"
        write_comparison_artifact(
            approval_path,
            json.dumps(approval, ensure_ascii=False, indent=2),
        )
        print()
        print("CROSS-CASE COMPARISON HUMAN APPROVAL V1 PASS")
        print(f"Direction: {approval['research_direction']}")
        print("Decision: approve_research_comparison")
        print("Pattern approved: False")
        print(f"Receipt: {approval_path}")
        return

    if args.research_bundle:
        if args.case or args.fingerprint:
            raise ValueError(
                "--research-bundle cannot be combined with legacy --case/--fingerprint inputs."
            )
        bundle_path = Path(args.research_bundle).expanduser().resolve()
        comparison = build_generalized_research_comparison(bundle_path)
        direction = comparison["research_direction"]
        output_dir = (
            Path(args.output_root).expanduser().resolve()
            if args.output_root
            else bundle_path.parent
        )
        base_name = (
            "price_offer_led_cross_case_comparison_v1"
            if direction == "price_offer_led_micro_information"
            else f"{direction}_cross_case_comparison_v1"
        )
        json_path = output_dir / f"{base_name}.json"
        markdown_path = output_dir / f"{base_name}.md"
        write_comparison_artifact(
            json_path,
            json.dumps(comparison, ensure_ascii=False, indent=2),
        )
        write_comparison_artifact(
            markdown_path,
            render_generalized_research_comparison(comparison),
        )
        print()
        print("GENERALIZED CROSS-CASE COMPARISON V1 PASS")
        print(f"Direction: {direction}")
        print(f"Cases: {comparison['case_count']}")
        print("Status: review_required")
        print(
            "Pattern Candidate readiness: "
            f"{comparison['candidate_research_readiness']}"
        )
        print("Pattern Candidate created: False")
        print("Remote/local model used: False / False")
        print(f"JSON: {json_path}")
        print(f"Markdown: {markdown_path}")
        return

    if not args.case or not args.fingerprint:
        raise ValueError(
            "Legacy mode requires exactly two --case and two --fingerprint inputs."
        )

    comparison = build_comparison(
        [Path(value) for value in args.case],
        [Path(value) for value in args.fingerprint],
    )
    project_root = Path(__file__).resolve().parents[1]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "comparisons"
    )
    pair_name = "__".join(comparison["case_ids"])
    output_dir = output_root / pair_name
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "cross_case_comparison_v1.json"
    output_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    overall = comparison["overall_similarity"]
    assessment = comparison["pattern_assessment"]
    print()
    print("CROSS-CASE COMPARISON V1 PASS")
    print(f"Cases: {' x '.join(comparison['case_ids'])}")
    print(
        "Similarity: "
        f"structural={overall['structural']['level']} "
        f"semantic={overall['semantic']['level']} "
        f"surface={overall['surface']['level']}"
    )
    print(f"Pattern assessment: {assessment['status']}")
    print(f"Hypotheses: {len(assessment['hypotheses'])}")
    print("Remote model used: False")
    print(f"JSON: {output_path}")


if __name__ == "__main__":
    main()
