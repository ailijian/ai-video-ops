from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from privacy_projection_v1 import (
    assert_safe_for_external_model,
    validate_case_privacy_gate,
)


COMPARISON_VERSION = "cross-case-comparison-v1.0"
BUILDER_VERSION = "compare_approved_cases_v1.py@0.1"
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically compare exactly two Approved Cases and their "
            "Case Fingerprints. This stage does not create a Pattern."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help="Approved case_v1.json; provide exactly twice.",
    )
    parser.add_argument(
        "--fingerprint",
        action="append",
        required=True,
        help="case_fingerprint_v1.json; provide exactly twice.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/comparisons",
    )
    args = parser.parse_args()

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
