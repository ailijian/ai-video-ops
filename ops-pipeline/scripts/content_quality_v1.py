from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SIGNATURE_VERSION = "content-signature-v1.0"
LEDGER_SCHEMA_VERSION = "content-ledger-v1.0"
PLAN_SCHEMA_VERSION = "content-plan-v1.0"
STORYBOARD_SCHEMA_VERSION = "storyboard-plan-v1.0"
ANALYSIS_SCHEMA_VERSION = "baseline-content-quality-v1.0"
QUALITY_ENGINE_VERSION = "content-uniqueness-editorial-quality-v1.0"
QUALITY_ENGINE_V1_1_VERSION = "content-uniqueness-editorial-quality-v1.1"
PLAN_V1_1_SCHEMA_VERSION = "content-plan-v1.1"
QUALITY_ENGINE_V1_1_1_VERSION = "content-uniqueness-editorial-quality-v1.1.1"
PLAN_V1_1_1_SCHEMA_VERSION = "content-plan-v1.1.1"
CONTENT_GAP_REPORT_SCHEMA_VERSION = "content-gap-report-v1.0"
CONTENT_REPLENISHMENT_INTAKE_SCHEMA_VERSION = (
    "content-capacity-replenishment-intake-v1.0"
)
FACT_ATOM_VERSION = "fact-atom-v1.1"
COMMUNICATED_INFORMATION_VERSION = "communicated-information-units-v1.1"

LEDGER_STATUSES = {
    "generated",
    "review_required",
    "approved",
    "exported",
    "published",
    "retired",
}
STRONG_MEMORY_STATUSES = {"approved", "exported", "published"}

DEFAULT_CANDIDATE_POOL_SIZE = 30
DEFAULT_MINIMUM_EDITORIAL_SCORE = 3.25
DEFAULT_EDITORIAL_WEIGHTS = {
    "audience_relevance": 1.0,
    "specificity": 1.0,
    "business_distinctiveness": 1.0,
    "speaker_authenticity": 0.8,
    "information_gain": 1.2,
    "hook_potential": 0.7,
    "visualizability": 0.8,
    "single_focus": 1.0,
}
DEFAULT_EDITORIAL_V1_1_WEIGHTS = {
    "audience_relevance": 1.0,
    "specificity": 1.0,
    "business_distinctiveness": 1.0,
    "speaker_fit": 0.8,
    "information_gain": 1.2,
    "hook_potential": 0.7,
    "visualizability": 0.8,
    "single_focus": 1.0,
}
GENERIC_ANCHORS = {
    "",
    "服务很好",
    "很方便",
    "很专业",
    "方便",
    "专业",
    "省心",
    "省心省力",
}
SEMANTIC_BOILERPLATE_PHRASES = {
    "代炒菜窗口",
    "代炒窗口",
    "窗口现场加工",
    "代炒窗口现场加工",
    "顾客可以",
    "菜市场",
    "在菜市场",
    "送到窗口",
    "加工过程",
    "代炒的加工",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    replacements = (
        ("多少钱", "价格"),
        ("收费", "价格"),
        ("贵不贵", "价格"),
        ("代炒菜", "代炒"),
        ("加工烹饪", "加工"),
        ("打包装盒", "打包"),
        ("拿走", "带走"),
        ("拎走", "带走"),
        ("大约", "约"),
        ("左右", "约"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def text_similarity(left: Any, right: Any) -> float:
    return round(
        difflib.SequenceMatcher(
            None,
            normalize_text(left),
            normalize_text(right),
        ).ratio(),
        6,
    )


def _anchor_value(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value") or "").strip()
    return str(value or "").strip()


def _anchor_fact_refs(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    refs = value.get("fact_refs") or []
    return sorted({str(ref) for ref in refs if str(ref)})


def normalize_exclusive_anchor(value: Any) -> dict[str, Any] | None:
    anchor = _anchor_value(value)
    if not anchor:
        return None
    kind = str(value.get("kind") or "specific_fact") if isinstance(value, dict) else "specific_fact"
    return {
        "kind": kind,
        "value": anchor,
        "fact_refs": _anchor_fact_refs(value),
    }


def central_claim_key(concept: dict[str, Any]) -> str:
    explicit = normalize_text(concept.get("central_claim_key"))
    if explicit:
        return explicit
    return normalize_text(concept.get("central_claim"))


def semantic_signature(
    concept: dict[str, Any],
    business_id: str,
) -> dict[str, Any]:
    primary_refs = concept.get("primary_fact_refs")
    if primary_refs is None:
        primary_refs = concept.get("primary_persona_fact_refs") or []
    return {
        "signature_version": SIGNATURE_VERSION,
        "business_id": business_id,
        "audience_need": str(concept.get("audience_need") or "unspecified"),
        "content_job": str(concept.get("content_job") or "unspecified"),
        "primary_topic": str(
            concept.get("primary_topic")
            or concept.get("primary_angle")
            or "unspecified"
        ),
        "primary_fact_bundle": sorted({str(ref) for ref in primary_refs}),
        "central_claim_key": central_claim_key(concept),
        "exclusive_anchor": normalize_exclusive_anchor(
            concept.get("exclusive_anchor")
        ),
        "customer_story_ref": (
            str(concept.get("customer_story_ref"))
            if concept.get("customer_story_ref")
            else None
        ),
    }


def presentation_signature(
    concept: dict[str, Any],
    speaker_id: str | None,
    speaker_type: str | None,
) -> dict[str, Any]:
    return {
        "signature_version": SIGNATURE_VERSION,
        "speaker_id": speaker_id,
        "speaker_type": speaker_type,
        "opening_strategy": concept.get("opening_strategy"),
        "narrative_mode": concept.get("narrative_mode"),
        "case_structural_ref": concept.get("case_structural_ref"),
        "visual_anchor": concept.get("visual_anchor"),
        "storyboard_shape": concept.get("storyboard_shape"),
    }


def _baseline_taxonomy(item: dict[str, Any]) -> dict[str, Any]:
    angle = str(item.get("primary_angle") or "unspecified")
    taxonomy = {
        "service_explanation": (
            "understand_service_availability",
            "service_definition",
            "market_ingredients_can_use_processing_window",
            "顾客自选食材，代炒菜窗口现场加工",
            "食材从菜市场递入代炒菜窗口",
        ),
        "use_case": (
            "understand_how_service_is_used",
            "service_process_explanation",
            "market_purchase_to_window_processing_takeaway_flow",
            "少盐少辣要求与加工后打包带走",
            "买菜、递菜、打包装盒",
        ),
        "price_explanation": (
            "know_processing_price",
            "price_explanation",
            "processing_price_by_cooking_method",
            "素菜8-10元、清蒸约15元、红烧约18元",
            "公开加工价目与价格数字",
        ),
        "customization": (
            "confirm_taste_customization",
            "objection_resolution",
            "taste_preference_can_be_requested",
            "少盐少辣可在送食材时提出",
            "顾客与师傅沟通调味",
        ),
        "process": (
            "understand_how_service_is_used",
            "service_process_explanation",
            "market_purchase_to_window_processing_takeaway_flow",
            "买菜、送窗口、报口味、加工、打包、带走",
            "完整六步服务流程",
        ),
        "service_time": (
            "estimate_service_time",
            "time_expectation_setting",
            "processing_time_varies_and_peak_queue",
            "快菜约5分钟、复杂鱼类约一刻钟、高峰可能排队",
            "炒制过程与等待时间",
        ),
        "convenience": (
            "solve_cooking_difficulty",
            "problem_solution",
            "processing_service_reduces_cooking_burden",
            "",
            "不会做饭场景与现场加工",
        ),
        "frontline_viewpoint": (
            "understand_how_service_is_used",
            "service_process_explanation",
            "market_purchase_to_window_processing_takeaway_flow",
            "林东方在明厨亮灶窗口按少盐少辣要求加工",
            "林东方窗口工作与明厨亮灶",
        ),
        "customer_story": (
            "seek_real_customer_evidence",
            "customer_story",
            "tao_family_says_service_saves_effort",
            "陶先生一家常买两三样食材，评价最大好处是省心",
            "常客、食材与评价文字",
        ),
        "service_detail": (
            "know_what_is_included",
            "included_service_explanation",
            "condiments_and_rice_are_free",
            "免费提供油盐酱料和米饭",
            "油盐酱料与米饭",
        ),
    }
    audience_need, content_job, claim_key, anchor, visual = taxonomy.get(
        angle,
        (
            f"need:{angle}",
            f"job:{angle}",
            normalize_text(item.get("central_claim")),
            "",
            angle,
        ),
    )
    return {
        "audience_need": audience_need,
        "content_job": content_job,
        "primary_topic": angle,
        "central_claim_key": claim_key,
        "exclusive_anchor": (
            {
                "kind": "authorized_customer_fact",
                "value": anchor,
                "fact_refs": sorted(
                    set(item.get("persona_fact_refs_used") or [])
                ),
            }
            if anchor
            else None
        ),
        "visual_anchor": visual,
        "customer_story_ref": (
            "authorized_customer_feedback:陶先生一家"
            if angle == "customer_story"
            else None
        ),
    }


def infer_baseline_concept(item: dict[str, Any], business_id: str) -> dict[str, Any]:
    taxonomy = _baseline_taxonomy(item)
    primary_refs = list(
        item.get("primary_persona_fact_refs")
        or item.get("persona_fact_refs_used")
        or []
    )
    all_refs = list(item.get("persona_fact_refs_used") or [])
    supporting_refs = sorted(set(all_refs) - set(primary_refs))
    speaker = item.get("speaker_ref") or {}
    concept = {
        "concept_id": f"B0-{item['content_id']}",
        "audience_need": taxonomy["audience_need"],
        "content_job": taxonomy["content_job"],
        "primary_topic": taxonomy["primary_topic"],
        "primary_fact_refs": primary_refs,
        "supporting_fact_refs": supporting_refs,
        "central_claim": item.get("central_claim"),
        "central_claim_key": taxonomy["central_claim_key"],
        "exclusive_anchor": taxonomy["exclusive_anchor"],
        "customer_story_ref": taxonomy["customer_story_ref"],
        "speaker_id": speaker.get("persona_id"),
        "speaker_type": speaker.get("speaker_type"),
        "speaker_fact_refs": list(item.get("speaker_fact_refs_used") or []),
        "opening_strategy": item.get("opening_strategy"),
        "narrative_mode": item.get("narrative_mode"),
        "case_structural_ref": (item.get("case_reference") or {}).get("case_id"),
        "visual_anchor": taxonomy["visual_anchor"],
        "storyboard_shape": None,
    }
    concept["semantic_signature"] = semantic_signature(concept, business_id)
    concept["presentation_signature"] = presentation_signature(
        concept,
        concept["speaker_id"],
        concept["speaker_type"],
    )
    concept["customer_specificity_class"] = classify_customer_specificity(concept)
    return concept


def _signature(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("semantic_signature") or record


def _claims_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_signature = _signature(left)
    right_signature = _signature(right)
    left_key = normalize_text(left_signature.get("central_claim_key"))
    right_key = normalize_text(right_signature.get("central_claim_key"))
    if left_key and left_key == right_key:
        return True
    left_claim = left.get("central_claim") or left_signature.get("central_claim")
    right_claim = right.get("central_claim") or right_signature.get("central_claim")
    return bool(left_claim and right_claim and text_similarity(left_claim, right_claim) >= 0.88)


def _record_semantic_text(record: dict[str, Any]) -> str:
    signature = _signature(record)
    return normalize_text(
        " ".join(
            str(value or "")
            for value in (
                record.get("central_claim"),
                record.get("title"),
                record.get("narration"),
                _anchor_value(
                    record.get("exclusive_anchor")
                    or signature.get("exclusive_anchor")
                ),
            )
        )
    )


def _record_numeric_tokens(record: dict[str, Any]) -> set[str]:
    signature = _signature(record)
    raw_text = " ".join(
        str(value or "")
        for value in (
            record.get("central_claim"),
            record.get("title"),
            record.get("narration"),
            _anchor_value(
                record.get("exclusive_anchor")
                or signature.get("exclusive_anchor")
            ),
        )
    )
    return set(re.findall(r"\d+(?:\.\d+)?", raw_text))


def _same_bundle_takeaway_already_covered(
    left: dict[str, Any],
    right: dict[str, Any],
) -> bool:
    """Catch a narrower repaint of a takeaway already covered by the same facts."""
    left_signature = _signature(left)
    right_signature = _signature(right)
    left_bundle = set(left_signature.get("primary_fact_bundle") or [])
    right_bundle = set(right_signature.get("primary_fact_bundle") or [])
    if not left_bundle or left_bundle != right_bundle:
        return False

    left_text = _record_semantic_text(left)
    right_text = _record_semantic_text(right)
    left_claim = normalize_text(
        left.get("central_claim") or left_signature.get("central_claim")
    )
    right_claim = normalize_text(
        right.get("central_claim") or right_signature.get("central_claim")
    )
    left_anchor = normalize_text(
        _anchor_value(
            left.get("exclusive_anchor") or left_signature.get("exclusive_anchor")
        )
    )
    right_anchor = normalize_text(
        _anchor_value(
            right.get("exclusive_anchor") or right_signature.get("exclusive_anchor")
        )
    )

    claim_containment = (
        len(left_claim) >= 8
        and len(right_claim) >= 8
        and (left_claim in right_text or right_claim in left_text)
    )
    anchor_containment = (
        len(left_anchor) >= 6
        and len(right_anchor) >= 6
        and (left_anchor in right_text or right_anchor in left_text)
    )
    left_numbers = _record_numeric_tokens(left)
    right_numbers = _record_numeric_tokens(right)
    def numeric_descriptor(anchor: str) -> str:
        descriptor = re.sub(r"\d+(?:\.\d+)?", "", anchor)
        for generic in (
            "代炒",
            "加工费",
            "加工",
            "价格",
            "收费",
            "通常",
            "大约",
            "左右",
            "约",
            "元",
            "块",
        ):
            descriptor = descriptor.replace(generic, "")
        return descriptor

    left_descriptor = numeric_descriptor(left_anchor)
    right_descriptor = numeric_descriptor(right_anchor)
    descriptor_overlap = bool(
        (len(left_descriptor) >= 2 and left_descriptor in right_text)
        or (len(right_descriptor) >= 2 and right_descriptor in left_text)
    )
    numeric_takeaway_covered = bool(
        left_numbers
        and right_numbers
        and (left_numbers <= right_numbers or right_numbers <= left_numbers)
        and descriptor_overlap
    )
    return claim_containment or anchor_containment or numeric_takeaway_covered


def semantic_duplicate_reasons(
    left: dict[str, Any],
    right: dict[str, Any],
) -> list[str]:
    left_signature = _signature(left)
    right_signature = _signature(right)
    if left_signature.get("business_id") != right_signature.get("business_id"):
        return []
    reasons: list[str] = []
    claims_equal = _claims_equivalent(left, right)
    left_bundle = set(left_signature.get("primary_fact_bundle") or [])
    right_bundle = set(right_signature.get("primary_fact_bundle") or [])
    if claims_equal and left_bundle == right_bundle:
        reasons.append("equivalent_central_claim_and_same_primary_fact_bundle")
    if _same_bundle_takeaway_already_covered(left, right):
        reasons.append("same_primary_fact_takeaway_already_covered")
    if (
        claims_equal
        and left_signature.get("audience_need") == right_signature.get("audience_need")
        and left_signature.get("content_job") == right_signature.get("content_job")
    ):
        reasons.append("same_audience_need_content_job_and_equivalent_claim")
    left_story = left_signature.get("customer_story_ref")
    right_story = right_signature.get("customer_story_ref")
    if left_story and left_story == right_story and claims_equal:
        reasons.append("same_customer_story_or_quote_and_takeaway")
    return sorted(set(reasons))


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    return round(len(left_set & right_set) / len(union), 6) if union else 0.0


def _distinctive_common_claim_phrase(left: Any, right: Any) -> str | None:
    left_text = normalize_text(left)
    right_text = normalize_text(right)
    matches = sorted(
        difflib.SequenceMatcher(None, left_text, right_text).get_matching_blocks(),
        key=lambda item: item.size,
        reverse=True,
    )
    for match in matches:
        if match.size < 5:
            break
        phrase = left_text[match.a : match.a + match.size]
        if any(
            normalize_text(boilerplate) in phrase
            for boilerplate in SEMANTIC_BOILERPLATE_PHRASES
        ):
            continue
        return phrase
    return None


def is_strong_memory(record: dict[str, Any]) -> bool:
    return str(record.get("status")) in STRONG_MEMORY_STATUSES


def fact_usage_state(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    strong = [entry for entry in entries if is_strong_memory(entry)]
    historical = Counter()
    primary = Counter()
    supporting = Counter()
    for entry in strong:
        primary_refs = set(entry.get("primary_fact_refs") or [])
        supporting_refs = set(entry.get("supporting_fact_refs") or [])
        for ref in primary_refs | supporting_refs:
            historical[ref] += 1
        for ref in primary_refs:
            primary[ref] += 1
        for ref in supporting_refs:
            supporting[ref] += 1
    return {
        ref: {
            "historical_usage_count": historical[ref],
            "recent_primary_usage_count": primary[ref],
            "recent_supporting_usage_count": supporting[ref],
        }
        for ref in sorted(historical)
    }


def classify_customer_specificity(concept: dict[str, Any]) -> str:
    anchor = normalize_exclusive_anchor(concept.get("exclusive_anchor"))
    anchor_value = _anchor_value(anchor)
    anchor_refs = set(_anchor_fact_refs(anchor))
    primary_refs = set(concept.get("primary_fact_refs") or [])
    speaker_refs = set(concept.get("speaker_fact_refs") or [])
    concrete_refs = {
        "pricing_facts",
        "included_service_facts",
        "service_time_facts",
        "business_volume_fact",
        "time_efficiency_fact",
        "authorized_customer_cases_or_feedback",
        "service_process",
        "customer_use_cases",
        "differentiators",
        "product_or_service_facts",
        "speaker_role_facts",
    }
    if (
        anchor_value
        and anchor_value not in GENERIC_ANCHORS
        and (
            bool((anchor_refs | primary_refs | speaker_refs) & concrete_refs)
            or bool(concept.get("customer_story_ref"))
            or bool(speaker_refs)
        )
    ):
        return "customer_specific"
    category_grounded_refs = {
        "primary_products_or_services",
        "customer_use_cases",
        "product_or_service_facts",
        "pricing_facts",
        "included_service_facts",
        "service_process",
        "service_time_facts",
        "time_efficiency_fact",
        "differentiators",
        "authorized_customer_cases_or_feedback",
    }
    if primary_refs & category_grounded_refs:
        return "category_specific"
    return "generic"


def novelty_evaluation(
    concept: dict[str, Any],
    historical_entries: list[dict[str, Any]],
    selected_concepts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    candidates = [entry for entry in historical_entries if is_strong_memory(entry)]
    candidates.extend(selected_concepts or [])
    duplicate_matches: list[dict[str, Any]] = []
    strong_penalties: list[dict[str, Any]] = []
    soft_penalties: list[dict[str, Any]] = []
    uncertain_matches: list[dict[str, Any]] = []
    signature = _signature(concept)
    for previous in candidates:
        reasons = semantic_duplicate_reasons(concept, previous)
        previous_id = previous.get("content_id") or previous.get("concept_id")
        if reasons:
            duplicate_matches.append(
                {"ref": previous_id, "reasons": reasons}
            )
            continue
        previous_signature = _signature(previous)
        overlap = _jaccard(
            signature.get("primary_fact_bundle") or [],
            previous_signature.get("primary_fact_bundle") or [],
        )
        if overlap >= 0.5:
            strong_penalties.append(
                {
                    "code": "primary_fact_bundle_high_overlap",
                    "ref": previous_id,
                    "overlap": overlap,
                    "penalty": 0.45 if overlap < 1 else 0.7,
                }
            )
        claim_similarity = text_similarity(
            concept.get("central_claim"), previous.get("central_claim")
        )
        concept_anchor = _anchor_value(
            concept.get("exclusive_anchor")
            or signature.get("exclusive_anchor")
        )
        previous_anchor = _anchor_value(
            previous.get("exclusive_anchor")
            or previous_signature.get("exclusive_anchor")
        )
        anchor_similarity = text_similarity(concept_anchor, previous_anchor)
        if overlap >= 0.5 and (
            0.58 <= claim_similarity < 0.88
            or 0.58 <= anchor_similarity < 0.88
        ):
            uncertain_matches.append(
                {
                    "ref": previous_id,
                    "reason": "structured_fields_cannot_safely_resolve_semantic_distance",
                    "central_claim_lexical_similarity_secondary": claim_similarity,
                    "exclusive_anchor_lexical_similarity_secondary": anchor_similarity,
                    "primary_fact_bundle_overlap": overlap,
                }
            )
            strong_penalties.append(
                {
                    "code": "semantic_duplicate_uncertain_conservative_penalty",
                    "ref": previous_id,
                    "penalty": 0.65,
                }
            )
        concept_all_refs = set(signature.get("primary_fact_bundle") or []) | set(
            concept.get("supporting_fact_refs") or []
        )
        previous_all_refs = set(
            previous_signature.get("primary_fact_bundle") or []
        ) | set(previous.get("supporting_fact_refs") or [])
        all_fact_overlap = _jaccard(concept_all_refs, previous_all_refs)
        distinctive_phrase = _distinctive_common_claim_phrase(
            concept.get("central_claim"), previous.get("central_claim")
        )
        already_uncertain = any(
            item.get("ref") == previous_id for item in uncertain_matches
        )
        if all_fact_overlap >= 0.5 and distinctive_phrase and not already_uncertain:
            uncertain_matches.append(
                {
                    "ref": previous_id,
                    "reason": "distinctive_claim_phrase_and_authority_facts_overlap",
                    "distinctive_common_phrase": distinctive_phrase,
                    "all_fact_refs_overlap": all_fact_overlap,
                    "central_claim_lexical_similarity_secondary": claim_similarity,
                }
            )
            strong_penalties.append(
                {
                    "code": "semantic_duplicate_uncertain_conservative_penalty",
                    "ref": previous_id,
                    "penalty": 0.65,
                }
            )
        if (
            signature.get("audience_need")
            == previous_signature.get("audience_need")
        ):
            strong_penalties.append(
                {
                    "code": "audience_need_reuse_with_different_claim",
                    "ref": previous_id,
                    "penalty": 0.2,
                }
            )
        visual = str((concept.get("presentation_signature") or {}).get("visual_anchor") or concept.get("visual_anchor") or "")
        previous_visual = str((previous.get("presentation_signature") or {}).get("visual_anchor") or previous.get("visual_anchor") or "")
        if visual and previous_visual and normalize_text(visual) == normalize_text(previous_visual):
            soft_penalties.append(
                {
                    "code": "visual_anchor_reuse",
                    "ref": previous_id,
                    "penalty": 0.12,
                }
            )
    usage = fact_usage_state(historical_entries)
    for ref in signature.get("primary_fact_bundle") or []:
        primary_count = usage.get(ref, {}).get("recent_primary_usage_count", 0)
        if primary_count:
            strong_penalties.append(
                {
                    "code": "recent_primary_fact_overuse",
                    "fact_ref": ref,
                    "count": primary_count,
                    "penalty": min(1.2, 0.3 * primary_count),
                }
            )
    penalty_total = round(
        sum(float(item["penalty"]) for item in strong_penalties)
        + sum(float(item["penalty"]) for item in soft_penalties),
        4,
    )
    return {
        "decision": (
            "hard_duplicate"
            if duplicate_matches
            else "uncertain"
            if uncertain_matches
            else "novel"
        ),
        "hard_duplicate": bool(duplicate_matches),
        "duplicate_matches": duplicate_matches,
        "strong_penalties": strong_penalties,
        "soft_diversity_penalties": soft_penalties,
        "semantic_judge": (
            "independent_judge_not_invoked_human_reviewable"
            if uncertain_matches
            else "not_required_deterministic"
        ),
        "uncertain": bool(uncertain_matches),
        "uncertain_matches": uncertain_matches,
        "penalty_total": penalty_total,
    }


def editorial_score(
    concept: dict[str, Any],
    novelty: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = dict(DEFAULT_EDITORIAL_WEIGHTS if weights is None else weights)
    specificity_class = classify_customer_specificity(concept)
    primary_refs = list(concept.get("primary_fact_refs") or [])
    anchor = _anchor_value(concept.get("exclusive_anchor"))
    speaker_refs = list(concept.get("speaker_fact_refs") or [])
    dimensions = {
        "audience_relevance": 5.0 if concept.get("audience_need") else 1.0,
        "specificity": 5.0 if anchor and anchor not in GENERIC_ANCHORS else 3.0 if primary_refs else 1.0,
        "business_distinctiveness": {
            "customer_specific": 5.0,
            "category_specific": 3.0,
            "generic": 1.0,
        }[specificity_class],
        "speaker_authenticity": 5.0 if speaker_refs else 4.0 if concept.get("speaker_id") else 3.0,
        "information_gain": max(0.0, 5.0 - float(novelty.get("penalty_total") or 0)),
        "hook_potential": 4.5 if concept.get("opening_strategy") else 3.0,
        "visualizability": 5.0 if concept.get("visual_anchor") else 2.0,
        "single_focus": 5.0 if len(primary_refs) == 1 else 4.0 if len(primary_refs) == 2 else 2.5,
    }
    denominator = sum(float(weights.get(key, 0)) for key in dimensions)
    weighted = sum(
        value * float(weights.get(key, 0))
        for key, value in dimensions.items()
    )
    total = round(weighted / denominator, 4) if denominator else 0.0
    return {
        "scale": "0-5",
        "policy": "provisional_configurable_v1",
        "weights": weights,
        "dimensions": dimensions,
        "weighted_total": total,
        "customer_specificity_class": specificity_class,
    }


def validate_candidate_authority(
    candidate: Any,
    allowed_fact_refs: set[str],
    allowed_speaker_fact_refs: set[str],
    authorized_fact_values: dict[str, Any] | None = None,
    authorized_speaker_fact_values: dict[str, Any] | None = None,
    blocked_terms: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not isinstance(candidate, dict):
        return None, ["candidate_not_object"]
    normalized = dict(candidate)
    required_text = (
        "concept_id",
        "audience_need",
        "content_job",
        "primary_topic",
        "central_claim",
        "opening_strategy",
        "visual_anchor",
        "why_publish",
    )
    errors = [
        f"{field}_missing"
        for field in required_text
        if not str(candidate.get(field) or "").strip()
    ]
    primary_refs = candidate.get("primary_fact_refs") or []
    supporting_refs = candidate.get("supporting_fact_refs") or []
    speaker_refs = candidate.get("speaker_fact_refs") or []
    if not isinstance(primary_refs, list) or not primary_refs:
        errors.append("primary_fact_refs_missing_or_invalid")
        primary_refs = []
    if not isinstance(supporting_refs, list):
        errors.append("supporting_fact_refs_invalid")
        supporting_refs = []
    if not isinstance(speaker_refs, list):
        errors.append("speaker_fact_refs_invalid")
        speaker_refs = []
    primary_refs = sorted({str(ref) for ref in primary_refs})
    supporting_refs = sorted({str(ref) for ref in supporting_refs} - set(primary_refs))
    speaker_refs = sorted({str(ref) for ref in speaker_refs})
    invalid_business = sorted(
        (set(primary_refs) | set(supporting_refs)) - allowed_fact_refs
    )
    invalid_speaker = sorted(set(speaker_refs) - allowed_speaker_fact_refs)
    if invalid_business:
        errors.append("non_known_or_ineligible_fact_refs:" + ",".join(invalid_business))
    if invalid_speaker:
        errors.append("non_known_or_ineligible_speaker_fact_refs:" + ",".join(invalid_speaker))
    anchor = normalize_exclusive_anchor(candidate.get("exclusive_anchor"))
    if anchor:
        invalid_anchor_refs = sorted(set(anchor["fact_refs"]) - allowed_fact_refs - allowed_speaker_fact_refs)
        if invalid_anchor_refs:
            errors.append("exclusive_anchor_unauthorized_refs:" + ",".join(invalid_anchor_refs))
    story_ref = candidate.get("customer_story_ref")
    if story_ref and "authorized_customer_cases_or_feedback" not in (
        set(primary_refs) | set(supporting_refs)
    ):
        errors.append("customer_story_ref_without_authorized_feedback_fact")
    serialized_candidate = json.dumps(candidate, ensure_ascii=False, sort_keys=True)
    for term in blocked_terms or []:
        if term and term in serialized_candidate:
            errors.append("requires_review_or_forbidden_material_used:" + term)
    authorized_corpus = json.dumps(
        {
            "business": authorized_fact_values or {},
            "speaker": authorized_speaker_fact_values or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    numeric_claims = re.findall(
        r"(?:\d+(?:\.\d+)?%?|[一二三四五六七八九十百千万]+)\s*(?:年|元|块|分钟|小时|位|家|单|名|倍|%|％)",
        serialized_candidate,
    )
    for numeric_claim in numeric_claims:
        if authorized_fact_values is None and authorized_speaker_fact_values is None:
            break
        if re.sub(r"\s+", "", numeric_claim) not in re.sub(
            r"\s+", "", authorized_corpus
        ):
            errors.append("unsupported_numeric_fact:" + numeric_claim)
    normalized.update(
        {
            "concept_id": str(candidate.get("concept_id") or ""),
            "primary_fact_refs": primary_refs,
            "supporting_fact_refs": supporting_refs,
            "speaker_fact_refs": speaker_refs,
            "exclusive_anchor": anchor,
            "central_claim_key": central_claim_key(candidate),
            "storyboard_shape": candidate.get("storyboard_shape"),
        }
    )
    return (normalized if not errors else None), sorted(set(errors))


def build_content_plan(
    *,
    request: dict[str, Any],
    business_id: str,
    speaker_id: str | None,
    speaker_type: str | None,
    allowed_fact_refs: set[str],
    allowed_speaker_fact_refs: set[str],
    ledger: dict[str, Any],
    raw_candidates: list[dict[str, Any]],
    case_rotation: list[str],
    pattern_id: str,
    source_lineage: dict[str, Any],
    config: dict[str, Any] | None = None,
    planning_call: dict[str, Any] | None = None,
    created_at: str | None = None,
    authorized_fact_values: dict[str, Any] | None = None,
    authorized_speaker_fact_values: dict[str, Any] | None = None,
    blocked_terms: list[str] | None = None,
    prevalidated_invalid_candidates: list[dict[str, Any]] | None = None,
    received_size_override: int | None = None,
) -> dict[str, Any]:
    config = dict(config or {})
    minimum_score = float(
        config.get("minimum_editorial_score", DEFAULT_MINIMUM_EDITORIAL_SCORE)
    )
    weights = config.get("editorial_weights") or DEFAULT_EDITORIAL_WEIGHTS
    requested = int(request.get("quantity") or 0)
    entries = list(ledger.get("entries") or [])
    invalid_candidates: list[dict[str, Any]] = [
        dict(item) for item in (prevalidated_invalid_candidates or [])
    ]
    normalized_candidates: list[dict[str, Any]] = []
    seen_concept_ids: set[str] = set()
    for index, candidate in enumerate(raw_candidates, start=1):
        normalized, errors = validate_candidate_authority(
            candidate,
            allowed_fact_refs,
            allowed_speaker_fact_refs,
            authorized_fact_values,
            authorized_speaker_fact_values,
            blocked_terms,
        )
        concept_id = str(
            candidate.get("concept_id") if isinstance(candidate, dict) else ""
        )
        if concept_id in seen_concept_ids:
            errors.append("duplicate_concept_id")
            normalized = None
        if concept_id:
            seen_concept_ids.add(concept_id)
        if normalized is None:
            invalid_candidates.append(
                {
                    "candidate_index": index,
                    "concept_id": concept_id or None,
                    "decision": "authority_rejected",
                    "reasons": sorted(set(errors)),
                    "candidate_sha256": canonical_sha256(candidate),
                }
            )
            continue
        normalized["speaker_id"] = speaker_id
        normalized["speaker_type"] = speaker_type
        normalized["semantic_signature"] = semantic_signature(normalized, business_id)
        normalized["presentation_signature"] = presentation_signature(
            normalized,
            speaker_id,
            speaker_type,
        )
        history_only_novelty = novelty_evaluation(normalized, entries)
        normalized["novelty_summary"] = history_only_novelty
        normalized["editorial_score_summary"] = editorial_score(
            normalized,
            history_only_novelty,
            weights,
        )
        normalized_candidates.append(normalized)

    normalized_candidates.sort(
        key=lambda item: (
            -float(item["editorial_score_summary"]["weighted_total"]),
            item["concept_id"],
        )
    )
    ranked_unique: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = list(invalid_candidates)
    for candidate in normalized_candidates:
        novelty = novelty_evaluation(candidate, entries, ranked_unique)
        candidate["novelty_summary"] = novelty
        candidate["editorial_score_summary"] = editorial_score(
            candidate,
            novelty,
            weights,
        )
        if novelty["hard_duplicate"]:
            candidate["gate_decision"] = "hard_duplicate_rejected"
            rejected_candidates.append(candidate)
            continue
        if novelty["uncertain"]:
            candidate["gate_decision"] = "semantic_uncertain_review_required"
            candidate["editorial_rejection_reason"] = (
                "deterministic_fields_could_not_establish_material_difference"
            )
            rejected_candidates.append(candidate)
            continue
        score = float(candidate["editorial_score_summary"]["weighted_total"])
        if score < minimum_score:
            candidate["gate_decision"] = "editorial_quality_rejected"
            candidate["editorial_rejection_reason"] = (
                f"weighted_total_below_{minimum_score}"
            )
            rejected_candidates.append(candidate)
            continue
        candidate["gate_decision"] = "high_quality_novel"
        ranked_unique.append(candidate)

    selected = ranked_unique[:requested]
    for index, concept in enumerate(selected, start=1):
        case_id = case_rotation[(index - 1) % len(case_rotation)] if case_rotation else None
        concept["selected_rank"] = index
        concept["selected_reason"] = (
            "Top editorial-ranked deterministic-novel concept within current fact authority."
        )
        concept["case_structural_ref"] = case_id
        concept["pattern_ref"] = pattern_id
        concept["presentation_signature"] = presentation_signature(
            concept,
            speaker_id,
            speaker_type,
        )
        concept["hero_shot_role"] = concept.get("hero_shot_role") or "exclusive_anchor"
        concept["supporting_shot_roles"] = concept.get("supporting_shot_roles") or [
            "speaker_action",
            "service_context",
        ]
        historical_visuals = {
            str((entry.get("presentation_signature") or {}).get("visual_anchor") or "")
            for entry in entries
            if is_strong_memory(entry)
        }
        concept["avoid_recent_visual_anchor"] = (
            concept.get("visual_anchor") in historical_visuals
        )

    capacity = len(ranked_unique)
    capacity_status = "supported" if capacity >= requested else "capacity_limited"
    classes = Counter(
        item["editorial_score_summary"]["customer_specificity_class"]
        for item in selected
    )
    anchors = sum(bool(_anchor_value(item.get("exclusive_anchor"))) for item in selected)
    plan = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "quality_engine_version": QUALITY_ENGINE_VERSION,
        "created_at": created_at or now_iso(),
        "request_id": request.get("request_id"),
        "business_id": business_id,
        "speaker_id": speaker_id,
        "speaker_type": speaker_type,
        "profile": request.get("profile"),
        "candidate_pool": {
            "configured_size": int(
                config.get("candidate_pool_size", DEFAULT_CANDIDATE_POOL_SIZE)
            ),
            "received_size": (
                int(received_size_override)
                if received_size_override is not None
                else len(raw_candidates)
            ),
            "authority_valid_size": len(normalized_candidates),
            "candidates": normalized_candidates,
        },
        "opportunity_structure": {
            "type": "derived_planning_structure_not_graph_database",
            "sequence": [
                "audience",
                "need",
                "fact",
                "speaker_authority",
                "content_job",
                "exclusive_anchor",
                "visual_anchor",
            ],
            "case_determines_topic": False,
            "case_authority": "structural_abstraction_only_after_selection",
        },
        "fact_usage_pressure": fact_usage_state(entries),
        "novelty_gate": {
            "method": "deterministic_structured_comparison_v1",
            "semantic_judge_fallback": "duplicate_materially_different_uncertain_only",
            "hard_duplicate_count": sum(
                item.get("gate_decision") == "hard_duplicate_rejected"
                for item in rejected_candidates
            ),
            "semantic_uncertain_count": sum(
                item.get("gate_decision") == "semantic_uncertain_review_required"
                for item in rejected_candidates
            ),
            "rejected_candidates": rejected_candidates,
        },
        "editorial_ranking": {
            "policy": "provisional_configurable_v1",
            "minimum_editorial_score": minimum_score,
            "weights": weights,
            "ranked_high_quality_novel_candidates": ranked_unique,
        },
        "capacity": {
            "requested_quantity": requested,
            "high_quality_novel_capacity": capacity,
            "selected_quantity": len(selected),
            "status": capacity_status,
            "padding_generated": False,
        },
        "selected_concepts": selected,
        "batch_editorial_summary": {
            "selected_count": len(selected),
            "exclusive_anchor_count": anchors,
            "exclusive_anchor_coverage": round(anchors / len(selected), 4) if selected else 0.0,
            "customer_specific_count": classes["customer_specific"],
            "category_specific_count": classes["category_specific"],
            "generic_count": classes["generic"],
            "customer_specific_ratio": round(classes["customer_specific"] / len(selected), 4) if selected else 0.0,
            "generic_ratio": round(classes["generic"] / len(selected), 4) if selected else 0.0,
            "initial_targets": {
                "exclusive_anchor_coverage": 0.8,
                "customer_specific_ratio": 0.7,
                "generic_ratio_max": 0.2,
                "authority": "provisional_configurable_not_frozen",
            },
        },
        "planning_call": planning_call or {"remote_model_call_performed": False},
        "lineage": source_lineage,
        "authority": {
            "known_business_facts_only": True,
            "known_speaker_facts_only": True,
            "unknown_and_requires_review_excluded": True,
            "case_facts_transferred": False,
            "pattern_effectiveness_used": False,
            "external_research_used": False,
            "persona_fact_usage_counts_mutated": False,
            "human_approval_performed": False,
        },
        "validation": {
            "passed": bool(selected),
            "selected_not_greater_than_requested": len(selected) <= requested,
            "no_padding": len(selected) <= capacity,
            "all_selected_high_quality_novel": all(
                item.get("gate_decision") == "high_quality_novel"
                for item in selected
            ),
            "case_assignment_after_selection": True,
        },
    }
    return plan


def build_storyboard_plan(content_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": STORYBOARD_SCHEMA_VERSION,
        "created_at": content_plan.get("created_at"),
        "request_id": content_plan.get("request_id"),
        "content_plan_sha256": canonical_sha256(content_plan),
        "items": [
            {
                "concept_ref": concept["concept_id"],
                "visual_anchor": concept.get("visual_anchor"),
                "hero_shot_role": concept.get("hero_shot_role"),
                "supporting_shot_roles": concept.get("supporting_shot_roles") or [],
                "avoid_recent_visual_anchor": bool(
                    concept.get("avoid_recent_visual_anchor")
                ),
                "storyboard_shape": concept.get("storyboard_shape"),
            }
            for concept in content_plan.get("selected_concepts") or []
        ],
        "authority": {
            "planning_only": True,
            "video_editing_performed": False,
            "excel_contract_changed": False,
        },
    }


def validate_script_against_plan(
    generated_item: dict[str, Any],
    selected_concept: dict[str, Any],
    ledger_entries: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if generated_item.get("concept_ref") != selected_concept.get("concept_id"):
        errors.append("selected_concept_ref_changed")
    planned_claim = normalize_text(selected_concept.get("central_claim"))
    generated_claim = normalize_text(generated_item.get("central_claim"))
    if planned_claim != generated_claim:
        errors.append("selected_concept_central_claim_drift")
    planned_key = normalize_text(
        (selected_concept.get("semantic_signature") or {}).get("central_claim_key")
    )
    generated_key = normalize_text(generated_item.get("central_claim_key"))
    if not generated_key or generated_key != planned_key:
        errors.append("selected_concept_central_claim_key_drift")
    used_refs = set(generated_item.get("persona_fact_refs_used") or [])
    required_primary = set(selected_concept.get("primary_fact_refs") or [])
    if not required_primary.issubset(used_refs):
        errors.append("selected_primary_fact_bundle_changed")
    drift_signature = dict(selected_concept.get("semantic_signature") or {})
    drift_signature["central_claim_key"] = generated_key
    drift_candidate = {
        "semantic_signature": drift_signature,
        "central_claim": generated_item.get("central_claim"),
    }
    for entry in ledger_entries:
        if not is_strong_memory(entry):
            continue
        if semantic_duplicate_reasons(drift_candidate, entry):
            errors.append(
                "script_drifted_to_historical_semantic_duplicate:"
                + str(entry.get("content_id"))
            )
    generated_text = (
        str(generated_item.get("title") or "")
        + "\n"
        + str(generated_item.get("narration") or "")
    )
    for entry in ledger_entries:
        historical_text = str(entry.get("title") or "") + "\n" + str(entry.get("narration") or "")
        if historical_text.strip() and text_similarity(generated_text, historical_text) >= 0.82:
            errors.append(
                "script_lexically_reproduces_historical_content:"
                + str(entry.get("content_id"))
            )
    return sorted(set(errors))


def build_baseline_analysis(
    approved_batch: dict[str, Any],
    *,
    approved_batch_sha: str,
    source_batch_sha: str,
    exported_excel_sha: str,
    export_receipt: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    business_id = str(
        (approved_batch.get("contents") or [{}])[0]
        .get("persona_ref", {})
        .get("persona_id")
        or ""
    )
    concepts = [
        infer_baseline_concept(item, business_id)
        for item in approved_batch.get("contents") or []
    ]
    duplicate_pairs: list[dict[str, Any]] = []
    high_overlap_pairs: list[dict[str, Any]] = []
    lexical_pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(concepts):
        left_source = approved_batch["contents"][left_index]
        for right_index, right in enumerate(concepts[left_index + 1 :], start=left_index + 1):
            right_source = approved_batch["contents"][right_index]
            reasons = semantic_duplicate_reasons(left, right)
            if reasons:
                duplicate_pairs.append(
                    {
                        "left": left_source["content_id"],
                        "right": right_source["content_id"],
                        "reasons": reasons,
                    }
                )
            overlap = _jaccard(
                left["primary_fact_refs"],
                right["primary_fact_refs"],
            )
            if overlap >= 0.8:
                high_overlap_pairs.append(
                    {
                        "left": left_source["content_id"],
                        "right": right_source["content_id"],
                        "overlap": overlap,
                    }
                )
            lexical_pairs.append(
                {
                    "left": left_source["content_id"],
                    "right": right_source["content_id"],
                    "similarity": text_similarity(
                        str(left_source.get("title") or "") + "\n" + str(left_source.get("narration") or ""),
                        str(right_source.get("title") or "") + "\n" + str(right_source.get("narration") or ""),
                    ),
                }
            )
    cluster_map: dict[str, list[str]] = {}
    for source, concept in zip(approved_batch.get("contents") or [], concepts):
        cluster_map.setdefault(
            concept["semantic_signature"]["central_claim_key"], []
        ).append(source["content_id"])
    semantic_clusters = [
        {"central_claim_key": key, "content_ids": values}
        for key, values in sorted(cluster_map.items())
    ]
    primary_usage = Counter(
        ref for concept in concepts for ref in concept["primary_fact_refs"]
    )
    audience_usage = Counter(concept["audience_need"] for concept in concepts)
    job_usage = Counter(concept["content_job"] for concept in concepts)
    specificity = Counter(
        concept["customer_specificity_class"] for concept in concepts
    )
    anchor_count = sum(
        bool(_anchor_value(concept.get("exclusive_anchor"))) for concept in concepts
    )
    max_lexical = max((item["similarity"] for item in lexical_pairs), default=0.0)
    mean_lexical = round(
        sum(item["similarity"] for item in lexical_pairs) / len(lexical_pairs),
        6,
    ) if lexical_pairs else 0.0
    unique_visuals = {
        normalize_text(concept.get("visual_anchor"))
        for concept in concepts
        if concept.get("visual_anchor")
    }
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "created_at": created_at or now_iso(),
        "baseline_request_id": approved_batch.get("request_id"),
        "business_id": business_id,
        "read_only_analysis": True,
        "frozen_hashes": {
            "source_batch_sha256": source_batch_sha,
            "approved_batch_sha256": approved_batch_sha,
            "exported_excel_sha256": exported_excel_sha,
        },
        "content_count": len(concepts),
        "content_analysis": [
            {
                "content_id": source["content_id"],
                "title": source.get("title"),
                "narration": source.get("narration"),
                "central_claim": source.get("central_claim"),
                **concept,
            }
            for source, concept in zip(approved_batch.get("contents") or [], concepts)
        ],
        "summary": {
            "unique_central_claims": len(cluster_map),
            "semantic_duplicate_pair_count": len(duplicate_pairs),
            "semantic_duplicate_pairs": duplicate_pairs,
            "semantic_clusters": semantic_clusters,
            "repeated_fact_bundles": high_overlap_pairs,
            "high_overlap_primary_fact_bundle_pair_count": len(high_overlap_pairs),
            "repeated_primary_facts": {
                key: value for key, value in sorted(primary_usage.items()) if value > 1
            },
            "primary_fact_usage": dict(sorted(primary_usage.items())),
            "repeated_audience_needs": {
                key: value for key, value in sorted(audience_usage.items()) if value > 1
            },
            "unique_audience_needs": len(audience_usage),
            "repeated_content_jobs": {
                key: value for key, value in sorted(job_usage.items()) if value > 1
            },
            "unique_content_jobs": len(job_usage),
            "exclusive_anchor_count": anchor_count,
            "exclusive_anchor_coverage": round(anchor_count / len(concepts), 4) if concepts else 0.0,
            "customer_specificity_distribution": {
                "customer_specific": specificity["customer_specific"],
                "category_specific": specificity["category_specific"],
                "generic": specificity["generic"],
            },
            "customer_specific_ratio": round(specificity["customer_specific"] / len(concepts), 4) if concepts else 0.0,
            "generic_ratio": round(specificity["generic"] / len(concepts), 4) if concepts else 0.0,
            "visual_anchor_estimate": {
                "unique_count": len(unique_visuals),
                "values": sorted(
                    {str(concept["visual_anchor"]) for concept in concepts if concept.get("visual_anchor")}
                ),
            },
            "lexical_similarity_secondary_only": {
                "method": "normalized_sequence_matcher",
                "maximum": max_lexical,
                "mean": mean_lexical,
                "pairs": lexical_pairs,
            },
        },
        "historical_review": {
            "human_first_pass_approval": False,
            "revision_rate": 0.8,
            "basis": "revision_0001 through revision_0005; final approval occurred at revision_0005",
        },
        "export_receipt_sha256": (
            canonical_sha256(export_receipt) if export_receipt else None
        ),
        "authority": {
            "baseline_mutated": False,
            "approved_artifact_mutated": False,
            "excel_mutated": False,
            "approval_performed": False,
            "generation_performed": False,
        },
    }


def build_ledger_seed(
    baseline_analysis: dict[str, Any],
    approved_batch: dict[str, Any],
    *,
    approved_batch_path: Path,
    export_receipt: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    source_by_id = {
        item["content_id"]: item for item in approved_batch.get("contents") or []
    }
    exported_at = None
    if export_receipt:
        exported_at = (
            export_receipt.get("exported_at")
            or export_receipt.get("created_at")
        )
    entries: list[dict[str, Any]] = []
    for analysis in baseline_analysis.get("content_analysis") or []:
        source = source_by_id[analysis["content_id"]]
        approved_at = (source.get("human_review") or {}).get("reviewed_at")
        created = approved_batch.get("created_at")
        status = "exported" if export_receipt else "approved"
        events = [
            {"status": "approved", "at": approved_at, "source": "approved_batch"}
        ]
        if export_receipt:
            events.append(
                {"status": "exported", "at": exported_at, "source": "export_receipt"}
            )
        entries.append(
            {
                "content_id": analysis["content_id"],
                "business_id": baseline_analysis["business_id"],
                "speaker_id": analysis.get("speaker_id"),
                "batch_ref": approved_batch.get("request_id"),
                "semantic_signature": analysis["semantic_signature"],
                "presentation_signature": analysis["presentation_signature"],
                "central_claim": source.get("central_claim"),
                "title": source.get("title"),
                "narration": source.get("narration"),
                "primary_fact_refs": analysis.get("primary_fact_refs") or [],
                "supporting_fact_refs": analysis.get("supporting_fact_refs") or [],
                "exclusive_anchor": analysis.get("exclusive_anchor"),
                "customer_specificity_class": analysis.get(
                    "customer_specificity_class"
                ),
                "status": status,
                "created_at": created,
                "approved_at": approved_at,
                "exported_at": exported_at,
                "published_at": None,
                "events": events,
            }
        )
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "created_at": created_at or now_iso(),
        "business_id": baseline_analysis["business_id"],
        "storage_policy": "append_only_entries_v1",
        "novelty_authority": {
            "strong_memory_statuses": sorted(STRONG_MEMORY_STATUSES),
            "generated_or_rejected_drafts_permanently_reserve_semantic_space": False,
        },
        "entries": entries,
        "fact_usage_pressure": fact_usage_state(entries),
        "lineage": {
            "baseline_analysis_sha256": canonical_sha256(baseline_analysis),
            "approved_batch_path": str(approved_batch_path.resolve()),
            "approved_batch_sha256": sha256_file(approved_batch_path),
        },
        "validation": {
            "passed": len(entries) == len(approved_batch.get("contents") or []),
            "entry_count": len(entries),
            "strong_memory_count": sum(is_strong_memory(entry) for entry in entries),
            "baseline_not_mutated": True,
        },
    }


def append_ledger_entries(
    ledger: dict[str, Any],
    new_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    updated = json.loads(json.dumps(ledger, ensure_ascii=False))
    existing_ids = {entry["content_id"] for entry in updated.get("entries") or []}
    for entry in new_entries:
        if entry.get("status") not in LEDGER_STATUSES:
            raise ValueError("Unsupported Content Ledger status.")
        if entry.get("business_id") != updated.get("business_id"):
            raise ValueError("Content Ledger business_id mismatch.")
        if entry.get("content_id") in existing_ids:
            raise ValueError("Content Ledger entries are append-only and IDs cannot repeat.")
        existing_ids.add(entry["content_id"])
        updated.setdefault("entries", []).append(entry)
    updated["fact_usage_pressure"] = fact_usage_state(updated.get("entries") or [])
    updated["updated_at"] = now_iso()
    return updated


def review_batch_ledger_entries(
    generation_batch: dict[str, Any],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in generation_batch.get("contents") or []:
        entries.append(
            {
                "content_id": item["content_id"],
                "business_id": item.get("persona_ref", {}).get("persona_id"),
                "speaker_id": item.get("speaker_ref", {}).get("persona_id"),
                "batch_ref": generation_batch.get("request_id"),
                "semantic_signature": item.get("semantic_signature"),
                "presentation_signature": item.get("presentation_signature"),
                "central_claim": item.get("central_claim"),
                "title": item.get("title"),
                "narration": item.get("narration"),
                "primary_fact_refs": item.get("primary_persona_fact_refs") or [],
                "supporting_fact_refs": item.get("optional_secondary_fact_refs") or [],
                "exclusive_anchor": item.get("exclusive_anchor"),
                "customer_specificity_class": (
                    item.get("editorial_summary") or {}
                ).get("customer_specificity_class"),
                "status": "review_required",
                "created_at": generation_batch.get("created_at"),
                "approved_at": None,
                "exported_at": None,
                "published_at": None,
                "events": [
                    {
                        "status": "generated",
                        "at": generation_batch.get("created_at"),
                        "source": "generation_batch_v1",
                    },
                    {
                        "status": "review_required",
                        "at": generation_batch.get("created_at"),
                        "source": "content_human_review_gate",
                    },
                ],
            }
        )
    return entries


def append_ledger_file(
    path: Path,
    expected_current: dict[str, Any],
    new_entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    path = path.expanduser().resolve()
    if read_json(path) != expected_current:
        raise RuntimeError("Content Ledger changed before append.")
    updated = append_ledger_entries(expected_current, new_entries)
    payload = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise RuntimeError("Content Ledger temporary append path already exists.")
    with temporary.open("xb") as handle:
        handle.write(payload)
    if read_json(path) != expected_current:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Content Ledger changed during append.")
    temporary.replace(path)
    return updated, hashlib.sha256(payload).hexdigest()


def _flatten_atomic_known_values(value: Any, path: str = "value") -> list[tuple[str, Any]]:
    if isinstance(value, list):
        atoms: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            atoms.extend(_flatten_atomic_known_values(item, f"{path}[{index}]"))
        return atoms
    if isinstance(value, dict):
        atoms = []
        for key in sorted(value):
            atoms.extend(_flatten_atomic_known_values(value[key], f"{path}.{key}"))
        return atoms
    if value in (None, "", [], {}) or isinstance(value, bool):
        return []
    return [(path, value)]


def semantic_markers(value: Any) -> list[str]:
    raw = re.sub(r"\s+", "", str(value or ""))
    compact = normalize_text(raw)
    markers: set[str] = set()
    rules = (
        ("total_time_30_minutes", r"(?:30|三十)分钟"),
        ("quick_dish_5_minutes", r"(?:5|五)分钟"),
        ("complex_dish_15_minutes", r"一刻钟|(?:15|十五)分钟"),
        ("peak_queue_possible", r"高峰期?.*可能排队|高峰可能排队"),
        ("open_kitchen_process_visible", r"明厨亮灶|加工过程(?:可见|看得见)"),
        ("customer_selects_ingredients", r"食材.*(?:顾客.*(?:自行|自己).*选|你自己选)"),
        ("processing_price_transparent", r"加工价格.*(?:公开|清晰)|价格公开清晰"),
        ("free_condiments", r"免费提供.*油盐酱料|油盐酱料.*免费"),
        ("free_rice", r"免费提供.*米饭|米饭.*免费"),
        ("taste_less_salt_spicy", r"少盐少辣|少盐.*少辣"),
        ("seafood_processing", r"梭子蟹|水产.*(?:直接|现场)?加工"),
        ("weekday_meal_20_plus", r"(?:平日)?一餐.*20余位|20余位客人"),
        ("holiday_business_better", r"节假日.*(?:生意)?通常更好"),
        ("pack_and_take_away", r"打包(?:装盒)?.*带走|打包装盒"),
        ("customer_taste_request", r"告知口味偏好|口味偏好"),
        ("market_ingredient_purchase", r"菜市场.*(?:购买|买好|买到|买完).*食材"),
        ("window_delivery", r"(?:食材)?送到.*代炒菜?窗口|送至代炒菜?窗口"),
        ("onsite_processing", r"现场加工"),
        ("cooking_burden", r"不太会做饭|不想.*处理食材|省心省力"),
        ("young_couples", r"年轻夫妻"),
        ("nearby_residents", r"周边居民"),
        ("market_convenience", r"提升市集便民属性|菜场配套服务|便民服务导向"),
    )
    for marker, pattern in rules:
        if re.search(pattern, raw):
            markers.add(marker)
    if re.search(r"素菜.*(?:8\s*[-到至]\s*10|八\s*[到至]\s*十).*(?:元|块)", raw):
        markers.add("vegetable_price_8_10")
    if re.search(r"清蒸.*(?:15|十五).*(?:元|块)", raw):
        markers.add("steaming_price_15")
    if re.search(r"红烧.*(?:18|十八).*(?:元|块)", raw):
        markers.add("braising_price_18")
    if "顾客自行选择" in compact or "食材你自己选" in compact:
        markers.add("customer_selects_ingredients")
    return sorted(markers)


def build_fact_atom_catalog(
    persona: dict[str, Any],
    persona_sha256: str,
    allowed_fact_fields: set[str] | None = None,
) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for field in sorted(persona.get("facts") or {}):
        if allowed_fact_fields is not None and field not in allowed_fact_fields:
            continue
        fact = persona["facts"][field]
        if fact.get("state") != "known":
            continue
        for value_path, original in _flatten_atomic_known_values(fact.get("value")):
            normalized = normalize_text(original)
            identity = {
                "version": FACT_ATOM_VERSION,
                "persona_sha256": persona_sha256,
                "field": field,
                "value_path": value_path,
                "normalized_value": normalized,
            }
            digest = canonical_sha256(identity)
            atoms.append(
                {
                    "fact_atom_id": f"{field}::{digest[:20]}",
                    "fact_atom_version": FACT_ATOM_VERSION,
                    "persona_id": persona.get("persona_id"),
                    "persona_sha256": persona_sha256,
                    "field": field,
                    "value_path": value_path,
                    "original_known_fact": original,
                    "normalized_meaning": normalized,
                    "semantic_markers": semantic_markers(original),
                    "authority": "derived_planning_identity_only",
                }
            )
    return atoms


def fact_atom_matches_text(
    atom: dict[str, Any], text: Any
) -> tuple[bool, str | None]:
    atom_text = str(atom.get("normalized_meaning") or "")
    target = normalize_text(text)
    if atom_text and len(atom_text) >= 4 and (
        atom_text in target or (len(target) >= 4 and target in atom_text)
    ):
        return True, "explicit"
    atom_markers = set(atom.get("semantic_markers") or [])
    target_markers = set(semantic_markers(text))
    if atom_markers and atom_markers <= target_markers:
        return True, "explicit"
    if atom_text and len(atom_text) >= 5 and text_similarity(atom_text, target) >= 0.62:
        return True, "implied"
    return False, None


def _narration_sentences(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [
        item.strip()
        for item in re.split(r"(?<=[。！？!?])\s*|\n+", text)
        if item.strip()
    ]


def communicated_units_for_entry(
    entry: dict[str, Any], fact_atoms: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    primary_fields = set(entry.get("primary_fact_refs") or [])
    supporting_fields = set(entry.get("supporting_fact_refs") or [])
    grouped: dict[str, dict[str, Any]] = {}
    role_rank = {"incidental": 0, "supporting": 1, "primary": 2}
    explicit_rank = {"implied": 0, "explicit": 1}
    for sentence in _narration_sentences(entry.get("narration")):
        for atom in fact_atoms:
            matched, explicitness = fact_atom_matches_text(atom, sentence)
            if not matched or explicitness is None:
                continue
            field = str(atom["field"])
            role = (
                "primary"
                if field in primary_fields
                else "supporting"
                if field in supporting_fields
                else "incidental"
            )
            meaning_key = str(
                atom.get("normalized_meaning") or atom["fact_atom_id"]
            )
            current = grouped.get(meaning_key)
            if current is None:
                current = {
                    "meaning_key": meaning_key,
                    "normalized_meaning": atom.get("normalized_meaning"),
                    "fact_atom_refs": [],
                    "source_text_excerpt": sentence,
                    "communication_role": role,
                    "explicitness": explicitness,
                    "source_content_id": entry.get("content_id"),
                }
                grouped[meaning_key] = current
            current["fact_atom_refs"].append(atom["fact_atom_id"])
            if role_rank[role] > role_rank[current["communication_role"]]:
                current["communication_role"] = role
                current["source_text_excerpt"] = sentence
            if explicit_rank[explicitness] > explicit_rank[current["explicitness"]]:
                current["explicitness"] = explicitness
                current["source_text_excerpt"] = sentence
    units: list[dict[str, Any]] = []
    for meaning_key, unit in sorted(grouped.items()):
        unit["fact_atom_refs"] = sorted(set(unit["fact_atom_refs"]))
        unit["information_unit_id"] = (
            "ciu::"
            + canonical_sha256(
                {
                    "version": COMMUNICATED_INFORMATION_VERSION,
                    "source_content_id": entry.get("content_id"),
                    "meaning_key": meaning_key,
                    "fact_atom_refs": unit["fact_atom_refs"],
                }
            )[:20]
        )
        unit.pop("meaning_key")
        units.append(unit)
    return units


def enrich_ledger_with_communicated_information(
    ledger: dict[str, Any],
    persona: dict[str, Any],
    persona_sha256: str,
    allowed_fact_fields: set[str] | None = None,
    migrated_at: str | None = None,
) -> dict[str, Any]:
    if ledger.get("business_id") != persona.get("persona_id"):
        raise ValueError("Content Ledger and Persona business_id mismatch.")
    updated = json.loads(json.dumps(ledger, ensure_ascii=False))
    atoms = build_fact_atom_catalog(persona, persona_sha256, allowed_fact_fields)
    for entry in updated.get("entries") or []:
        if is_strong_memory(entry):
            entry["communicated_information_units"] = communicated_units_for_entry(
                entry, atoms
            )
    explicit_units = [
        unit
        for entry in updated.get("entries") or []
        if is_strong_memory(entry)
        for unit in entry.get("communicated_information_units") or []
        if unit.get("explicitness") == "explicit"
    ]
    extension = {
        "version": COMMUNICATED_INFORMATION_VERSION,
        "migrated_at": migrated_at or now_iso(),
        "migration_type": "authorized_strong_history_backfill",
        "strong_content_count": sum(
            is_strong_memory(entry) for entry in updated.get("entries") or []
        ),
        "communicated_information_unit_count": len(explicit_units),
        "unique_explicit_meaning_count": len(
            {unit.get("normalized_meaning") for unit in explicit_units}
        ),
        "persona_sha256": persona_sha256,
        "persona_authority_mutated": False,
    }
    updated.setdefault("extensions", {})[
        "communicated_information_units_v1_1"
    ] = extension
    updated["fact_atom_catalog"] = atoms
    updated["historical_exposure_summary"] = {
        "explicit_fact_atom_refs": sorted(
            {
                ref
                for unit in explicit_units
                for ref in unit.get("fact_atom_refs") or []
            }
        ),
        "communication_role_distribution": dict(
            sorted(Counter(unit["communication_role"] for unit in explicit_units).items())
        ),
    }
    updated["updated_at"] = extension["migrated_at"]
    return updated


def replace_ledger_with_communicated_information(
    path: Path,
    expected_current: dict[str, Any],
    replacement: dict[str, Any],
) -> str:
    path = path.expanduser().resolve()
    if read_json(path) != expected_current:
        raise RuntimeError("Content Ledger changed before V1.1 backfill.")
    payload = json.dumps(replacement, ensure_ascii=False, indent=2).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".v1_1.tmp")
    if temporary.exists():
        raise RuntimeError("Content Ledger V1.1 temporary path already exists.")
    with temporary.open("xb") as handle:
        handle.write(payload)
    if read_json(path) != expected_current:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Content Ledger changed during V1.1 backfill.")
    temporary.replace(path)
    return hashlib.sha256(payload).hexdigest()


def infer_audience_need_origin(concept: dict[str, Any]) -> dict[str, Any]:
    primary_refs = set(concept.get("primary_fact_refs") or [])
    if "authorized_customer_cases_or_feedback" in primary_refs:
        origin = "authorized_feedback"
        evidence = ["authorized_customer_cases_or_feedback"]
    elif "customer_pains" in primary_refs:
        origin = "known_customer_pain"
        evidence = ["customer_pains"]
    elif "customer_questions" in primary_refs:
        origin = "known_customer_question"
        evidence = ["customer_questions"]
    elif "customer_use_cases" in primary_refs:
        origin = "known_use_case"
        evidence = ["customer_use_cases"]
    elif primary_refs & {
        "pricing_facts",
        "included_service_facts",
        "service_time_facts",
        "time_efficiency_fact",
        "primary_products_or_services",
        "service_process",
    }:
        origin = "service_decision_need"
        evidence = sorted(
            primary_refs
            & {
                "pricing_facts",
                "included_service_facts",
                "service_time_facts",
                "time_efficiency_fact",
                "primary_products_or_services",
                "service_process",
            }
        )
    else:
        origin = "editorial_hypothesis"
        evidence = sorted(primary_refs)
    return {
        "origin": origin,
        "evidence_fact_refs": evidence,
        "customer_need_claimed_as_known": origin
        in {
            "known_customer_pain",
            "known_customer_question",
            "known_use_case",
            "authorized_feedback",
        },
    }


def speaker_fit_evaluation(
    concept: dict[str, Any], speaker_type: str | None
) -> dict[str, Any]:
    refs = set(concept.get("primary_fact_refs") or [])
    if speaker_type != "frontline_expert":
        return {
            "score": 3.5,
            "authority_pass": True,
            "reason": "speaker_type_has_no_v1_1_specialized_fit_policy",
        }
    if refs & {"business_principles", "values", "founder_or_operator_story"}:
        score = 2.0
        reason = "frontline_expert_is_not_the_natural_owner_of_business_strategy"
    elif "business_volume_fact" in refs:
        score = 4.0
        reason = "frontline_window_role_can_naturally_describe_bounded_service_volume"
    elif refs & {"pricing_facts", "included_service_facts"}:
        score = 3.5
        reason = "frontline_role_can_explain_approved_prices_but_does_not_own_pricing_policy"
    elif refs & {"core_audience", "customer_pains"}:
        score = 3.5
        reason = "frontline_role_can_describe_service_users_without_claiming_market_research"
    else:
        score = 5.0
        reason = "frontline_execution_or_service_use_case_is_role_natural"
    return {"score": score, "authority_pass": True, "reason": reason}


def _explicit_exposure_index(ledger: dict[str, Any]) -> tuple[set[str], list[dict[str, Any]]]:
    units = [
        unit
        for entry in ledger.get("entries") or []
        if is_strong_memory(entry)
        for unit in entry.get("communicated_information_units") or []
        if unit.get("explicitness") == "explicit"
    ]
    refs = {ref for unit in units for ref in unit.get("fact_atom_refs") or []}
    return refs, units


def _concept_atom_refs(
    concept: dict[str, Any],
    fact_atoms: list[dict[str, Any]],
    fields: set[str],
    text_fields: tuple[str, ...],
    fallback_single: bool = True,
) -> list[str]:
    text = " ".join(str(concept.get(field) or "") for field in text_fields)
    matched = [
        atom["fact_atom_id"]
        for atom in fact_atoms
        if atom.get("field") in fields and fact_atom_matches_text(atom, text)[0]
    ]
    if matched:
        return sorted(set(matched))
    if not fallback_single:
        return []
    fallback: list[str] = []
    for field in fields:
        field_atoms = [
            atom["fact_atom_id"] for atom in fact_atoms if atom.get("field") == field
        ]
        if len(field_atoms) == 1:
            fallback.extend(field_atoms)
    return sorted(set(fallback))


def historical_exposure_evaluation(
    concept: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    fact_atoms = list(ledger.get("fact_atom_catalog") or [])
    exposed_refs, explicit_units = _explicit_exposure_index(ledger)
    primary_fields = set(concept.get("primary_fact_refs") or []) | set(
        _anchor_fact_refs(concept.get("exclusive_anchor"))
    )
    core_refs = _concept_atom_refs(
        concept,
        fact_atoms,
        primary_fields,
        ("exclusive_anchor",),
    )
    if not core_refs:
        core_refs = _concept_atom_refs(
            concept,
            fact_atoms,
            primary_fields,
            ("central_claim", "primary_topic"),
        )
    supporting_fields = set(concept.get("supporting_fact_refs") or [])
    supporting_refs = set(
        _concept_atom_refs(
            concept,
            fact_atoms,
            supporting_fields,
            ("central_claim", "primary_topic", "why_publish"),
            fallback_single=False,
        )
    )
    historical_supporting = supporting_refs & exposed_refs
    supporting_ratio = (
        round(len(historical_supporting) / len(supporting_refs), 4)
        if supporting_refs
        else 0.0
    )
    exposed_core = sorted(set(core_refs) & exposed_refs)
    novel_core = sorted(set(core_refs) - exposed_refs)
    matched_units = [
        {
            "information_unit_id": unit.get("information_unit_id"),
            "source_content_id": unit.get("source_content_id"),
            "normalized_meaning": unit.get("normalized_meaning"),
            "communication_role": unit.get("communication_role"),
            "fact_atom_refs": unit.get("fact_atom_refs") or [],
        }
        for unit in explicit_units
        if set(unit.get("fact_atom_refs") or []) & set(core_refs)
    ]
    if not core_refs:
        return {
            "decision": "uncertain",
            "material_information_gain": False,
            "reason": "candidate_primary_information_could_not_be_resolved_to_fact_atoms",
            "core_fact_atom_refs": [],
            "historically_exposed_core_fact_atom_refs": [],
            "novel_core_fact_atom_refs": [],
            "historical_unit_matches": [],
            "historical_supporting_fact_reuse_ratio": supporting_ratio,
            "historical_supporting_fact_atom_refs": sorted(historical_supporting),
        }
    material_gain = bool(novel_core)
    return {
        "decision": "materially_different" if material_gain else "duplicate",
        "material_information_gain": material_gain,
        "reason": (
            "authority_supported_uncommunicated_core_fact_atom"
            if material_gain
            else "core_information_was_explicitly_communicated_in_strong_history"
        ),
        "core_fact_atom_refs": core_refs,
        "historically_exposed_core_fact_atom_refs": exposed_core,
        "novel_core_fact_atom_refs": novel_core,
        "historical_unit_matches": matched_units,
        "historical_supporting_fact_reuse_ratio": supporting_ratio,
        "historical_supporting_fact_atom_refs": sorted(historical_supporting),
    }


def unsupported_detail_flags_v1_1(
    concept: dict[str, Any], authorized_fact_values: dict[str, Any]
) -> list[str]:
    text = "\n".join(
        str(value or "")
        for value in (
            concept.get("central_claim"),
            _anchor_value(concept.get("exclusive_anchor")),
            concept.get("visual_anchor"),
            concept.get("why_publish"),
        )
    )
    authorized = json.dumps(authorized_fact_values, ensure_ascii=False)
    flags: list[str] = []
    rules = (
        ("unsupported_price_display_location", r"贴在窗口|窗口处.*(?:价目表|价格标示)|价目表.*窗口"),
        ("unsupported_observer_location", r"站在窗口外|透过.*窗口.*看到"),
    )
    for code, pattern in rules:
        if re.search(pattern, text) and not re.search(pattern, authorized):
            flags.append(code)
    return flags


def novel_exclusive_anchor_evaluation(
    concept: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    fact_atoms = list(ledger.get("fact_atom_catalog") or [])
    exposed_refs, _units = _explicit_exposure_index(ledger)
    fields = set(_anchor_fact_refs(concept.get("exclusive_anchor")))
    anchor_refs = _concept_atom_refs(
        concept,
        fact_atoms,
        fields,
        ("exclusive_anchor",),
    )
    atom_by_id = {atom["fact_atom_id"]: atom for atom in fact_atoms}
    customer_specific_fields = {
        "pricing_facts",
        "included_service_facts",
        "business_volume_fact",
        "time_efficiency_fact",
        "authorized_customer_cases_or_feedback",
        "business_principles",
        "differentiators",
        "customer_use_cases",
    }
    current_customer_specific = bool(anchor_refs) and any(
        atom_by_id[ref].get("field") in customer_specific_fields
        for ref in anchor_refs
        if ref in atom_by_id
    )
    novel = bool(anchor_refs) and current_customer_specific and not bool(
        set(anchor_refs) & exposed_refs
    )
    return {
        "novel_exclusive_anchor": novel,
        "current_customer_specific": current_customer_specific,
        "anchor_fact_atom_refs": anchor_refs,
        "historically_exposed_anchor_fact_atom_refs": sorted(
            set(anchor_refs) & exposed_refs
        ),
    }


def editorial_score_v1_1(
    concept: dict[str, Any],
    exposure: dict[str, Any],
    audience_origin: dict[str, Any],
    speaker_fit: dict[str, Any],
    novel_anchor: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = dict(DEFAULT_EDITORIAL_V1_1_WEIGHTS if weights is None else weights)
    audience_scores = {
        "known_customer_pain": 5.0,
        "known_customer_question": 5.0,
        "known_use_case": 4.5,
        "authorized_feedback": 5.0,
        "service_decision_need": 3.5,
        "editorial_hypothesis": 2.5,
    }
    supporting_ratio = float(
        exposure.get("historical_supporting_fact_reuse_ratio") or 0
    )
    supporting_field_count = len(concept.get("supporting_fact_refs") or [])
    single_focus = max(
        1.0,
        round(
            5.0
            - 2.0 * supporting_ratio
            - 0.35 * max(0, supporting_field_count - 1),
            4,
        ),
    )
    anchor_value = _anchor_value(concept.get("exclusive_anchor"))
    specificity = 4.5 if novel_anchor["anchor_fact_atom_refs"] else 2.5 if anchor_value else 1.0
    business_distinctiveness = (
        5.0
        if novel_anchor["novel_exclusive_anchor"]
        else 3.0
        if exposure.get("novel_core_fact_atom_refs")
        else 1.0
    )
    information_gain = (
        5.0
        if exposure.get("material_information_gain")
        and exposure.get("novel_core_fact_atom_refs")
        else 0.0
    )
    dimensions = {
        "audience_relevance": audience_scores[audience_origin["origin"]],
        "specificity": specificity,
        "business_distinctiveness": business_distinctiveness,
        "speaker_fit": float(speaker_fit["score"]),
        "information_gain": information_gain,
        "hook_potential": 4.0 if concept.get("opening_strategy") else 2.5,
        "visualizability": 4.5 if concept.get("visual_anchor") else 2.0,
        "single_focus": single_focus,
    }
    denominator = sum(float(weights.get(key, 0)) for key in dimensions)
    weighted = sum(
        value * float(weights.get(key, 0)) for key, value in dimensions.items()
    )
    return {
        "scale": "0-5",
        "policy": "provisional_configurable_v1_1",
        "weights": weights,
        "dimensions": dimensions,
        "weighted_total": round(weighted / denominator, 4) if denominator else 0.0,
        "historical_supporting_fact_reuse_ratio": supporting_ratio,
        "single_focus_dilution": round(1.0 - single_focus / 5.0, 4),
    }


def build_content_plan_v1_1(
    *,
    v1_plan: dict[str, Any],
    ledger: dict[str, Any],
    request: dict[str, Any],
    speaker_type: str | None,
    authorized_fact_values: dict[str, Any],
    source_artifact_hashes: dict[str, str],
    created_at: str | None = None,
) -> dict[str, Any]:
    minimum_score = float(
        (request.get("content_quality_v1") or {}).get(
            "minimum_editorial_score", DEFAULT_MINIMUM_EDITORIAL_SCORE
        )
    )
    raw_candidates = list(v1_plan.get("candidate_pool", {}).get("candidates") or [])
    authority_rejected_source_candidates = [
        json.loads(json.dumps(item, ensure_ascii=False))
        for item in v1_plan.get("novelty_gate", {}).get("rejected_candidates") or []
        if item.get("decision") == "authority_rejected"
    ]
    evaluated: list[dict[str, Any]] = []
    for source in raw_candidates:
        candidate = json.loads(json.dumps(source, ensure_ascii=False))
        candidate["v1_diagnostic"] = {
            "gate_decision": source.get("gate_decision"),
            "editorial_score_summary": source.get("editorial_score_summary"),
            "novelty_summary": source.get("novelty_summary"),
        }
        audience_origin = infer_audience_need_origin(candidate)
        exposure = historical_exposure_evaluation(candidate, ledger)
        fit = speaker_fit_evaluation(candidate, speaker_type)
        novel_anchor = novel_exclusive_anchor_evaluation(candidate, ledger)
        unsupported = unsupported_detail_flags_v1_1(
            candidate, authorized_fact_values
        )
        score = editorial_score_v1_1(
            candidate, exposure, audience_origin, fit, novel_anchor
        )
        candidate.update(
            {
                "audience_need_origin": audience_origin["origin"],
                "audience_need_provenance": audience_origin,
                "historical_exposure_summary": exposure,
                "speaker_fit": fit,
                "novel_exclusive_anchor": novel_anchor[
                    "novel_exclusive_anchor"
                ],
                "novel_exclusive_anchor_summary": novel_anchor,
                "editorial_score_v1_1": score,
                "unsupported_detail_flags": unsupported,
            }
        )
        evaluated.append(candidate)

    evaluated.sort(
        key=lambda item: (
            -float(item["editorial_score_v1_1"]["weighted_total"]),
            item.get("concept_id") or "",
        )
    )
    accepted_atomic_sets: list[tuple[str, set[str]]] = []
    rejected: list[dict[str, Any]] = []
    novelty_survivors: list[dict[str, Any]] = []
    high_quality: list[dict[str, Any]] = []
    revision_required: list[dict[str, Any]] = []
    for candidate in evaluated:
        exposure = candidate["historical_exposure_summary"]
        if not exposure.get("material_information_gain"):
            candidate["v1_1_gate_decision"] = "historical_exposure_rejected"
            rejected.append(candidate)
            continue
        core = set(exposure.get("core_fact_atom_refs") or [])
        duplicate_of = next(
            (
                concept_id
                for concept_id, accepted_core in accepted_atomic_sets
                if core and core & accepted_core
            ),
            None,
        )
        if duplicate_of:
            candidate["v1_1_gate_decision"] = "candidate_pool_atomic_duplicate_rejected"
            candidate["candidate_pool_duplicate_of"] = duplicate_of
            rejected.append(candidate)
            continue
        accepted_atomic_sets.append((candidate["concept_id"], core))
        novelty_survivors.append(candidate)
        if candidate["unsupported_detail_flags"]:
            candidate["v1_1_gate_decision"] = "unsupported_detail_revision_required"
            revision_required.append(candidate)
            continue
        if float(candidate["speaker_fit"]["score"]) < 3.0:
            candidate["v1_1_gate_decision"] = "speaker_fit_revision_required"
            revision_required.append(candidate)
            continue
        if float(candidate["editorial_score_v1_1"]["weighted_total"]) < minimum_score:
            candidate["v1_1_gate_decision"] = "editorial_quality_rejected"
            rejected.append(candidate)
            continue
        candidate["v1_1_gate_decision"] = "high_quality_novel"
        high_quality.append(candidate)

    requested = int(request.get("quantity") or 0)
    selected = high_quality[:requested]
    for rank, candidate in enumerate(selected, start=1):
        candidate["selected_rank_v1_1"] = rank
        candidate["selected_reason_v1_1"] = (
            "Uncommunicated authority-supported Fact Atom with calibrated editorial score."
        )
    origin_all = Counter(item["audience_need_origin"] for item in evaluated)
    origin_selected = Counter(item["audience_need_origin"] for item in selected)
    novel_anchor_count = sum(item["novel_exclusive_anchor"] for item in selected)
    return {
        "schema_version": PLAN_V1_1_SCHEMA_VERSION,
        "quality_engine_version": QUALITY_ENGINE_V1_1_VERSION,
        "created_at": created_at or now_iso(),
        "request_id": request.get("request_id"),
        "business_id": ledger.get("business_id"),
        "speaker_id": v1_plan.get("speaker_id"),
        "speaker_type": speaker_type,
        "diagnostic_stage": "historical_exposure_and_v1_1_reranking_only",
        "remote_model_call": {
            "performed": False,
            "call_count": 0,
            "tokens": 0,
            "elapsed_seconds": 0,
        },
        "candidate_pool": {
            "source": "preserved_v1_candidate_pool",
            "configured_size": v1_plan.get("candidate_pool", {}).get(
                "configured_size"
            ),
            "received_size": v1_plan.get("candidate_pool", {}).get("received_size"),
            "authority_valid_size": len(evaluated),
            "authority_rejected_size": len(authority_rejected_source_candidates),
            "authority_rejected_candidates": authority_rejected_source_candidates,
            "source_pool_fully_accounted_for": (
                len(evaluated) + len(authority_rejected_source_candidates)
                == int(v1_plan.get("candidate_pool", {}).get("received_size") or 0)
            ),
            "candidates": evaluated,
        },
        "historical_exposure_gate": {
            "communicated_information_version": COMMUNICATED_INFORMATION_VERSION,
            "fact_atom_version": FACT_ATOM_VERSION,
            "historical_exposure_rejected_count": sum(
                item.get("v1_1_gate_decision") == "historical_exposure_rejected"
                for item in rejected
            ),
            "candidate_pool_atomic_duplicate_count": sum(
                item.get("v1_1_gate_decision")
                == "candidate_pool_atomic_duplicate_rejected"
                for item in rejected
            ),
            "rejected_candidates": rejected,
        },
        "editorial_ranking_v1_1": {
            "minimum_editorial_score": minimum_score,
            "weights": DEFAULT_EDITORIAL_V1_1_WEIGHTS,
            "novelty_surviving_concepts": novelty_survivors,
            "revision_required_concepts": revision_required,
            "ranked_high_quality_novel_candidates": high_quality,
        },
        "capacity": {
            "requested_quantity": requested,
            "novelty_surviving_capacity": len(novelty_survivors),
            "revision_required_capacity": len(revision_required),
            "high_quality_novel_capacity": len(high_quality),
            "selected_quantity": len(selected),
            "status": "supported" if len(high_quality) >= requested else "capacity_limited",
            "padding_generated": False,
            "script_generation_performed": False,
        },
        "selected_concepts": selected,
        "audience_need_provenance_distribution": {
            "candidate_pool": dict(sorted(origin_all.items())),
            "selected": dict(sorted(origin_selected.items())),
        },
        "batch_editorial_summary": {
            "novel_exclusive_anchor_count": novel_anchor_count,
            "novel_exclusive_anchor_coverage": (
                round(novel_anchor_count / len(selected), 4) if selected else 0.0
            ),
            "average_editorial_score": (
                round(
                    sum(
                        item["editorial_score_v1_1"]["weighted_total"]
                        for item in selected
                    )
                    / len(selected),
                    4,
                )
                if selected
                else 0.0
            ),
        },
        "lineage": {
            "source_v1_content_plan_sha256": source_artifact_hashes[
                "content_plan_v1"
            ],
            "content_ledger_sha256": canonical_sha256(ledger),
            "preserved_v1_artifacts": source_artifact_hashes,
        },
        "authority": {
            "persona_authority_mutated": False,
            "case_facts_transferred": False,
            "pattern_effectiveness_used": False,
            "external_research_used": False,
            "speaker_authority_changed": False,
            "speaker_fit_is_non_authoritative_editorial_signal": True,
            "human_approval_performed": False,
            "excel_export_performed": False,
        },
        "status": "review_required",
    }


def build_v1_diagnostic_human_review(
    v1_batch: dict[str, Any], v1_plan: dict[str, Any]
) -> dict[str, Any]:
    decisions = {
        "real_shufang_mix_002-C001": (
            "novelty_rejected",
            "30-minute total time was explicitly communicated in B0 C006.",
        ),
        "real_shufang_mix_002-C002": (
            "concept_approved",
            "Service-volume Fact Atom was not communicated in B0.",
        ),
        "real_shufang_mix_002-C003": (
            "concept_revision_required",
            "Business-purpose concept is novel, but frontline-chef speaker fit is weak.",
        ),
        "real_shufang_mix_002-C004": (
            "novelty_rejected",
            "Open-kitchen process visibility was explicitly communicated in B0 C008.",
        ),
        "real_shufang_mix_002-C005": (
            "novelty_rejected",
            "Customer-selected ingredients were explicitly communicated in B0 C001.",
        ),
        "real_shufang_mix_002-C006": (
            "novelty_rejected",
            "Price transparency was explicitly communicated in B0 C003.",
        ),
        "real_shufang_mix_002-C007": (
            "concept_approved",
            "Specific seafood use-case Fact Atom was not communicated in B0.",
        ),
    }
    concept_by_id = {
        item.get("concept_id"): item
        for item in v1_plan.get("candidate_pool", {}).get("candidates") or []
    }
    items: list[dict[str, Any]] = []
    for content in v1_batch.get("contents") or []:
        decision, reason = decisions[content["content_id"]]
        concept = concept_by_id.get(content.get("concept_ref")) or {}
        items.append(
            {
                "content_id": content["content_id"],
                "concept_ref": content.get("concept_ref"),
                "decision": decision,
                "reason": reason,
                "production_approval": False,
                "v1_central_claim": content.get("central_claim"),
                "v1_editorial_score": (
                    concept.get("editorial_score_summary") or {}
                ).get("weighted_total"),
            }
        )
    return {
        "schema_version": "v1-diagnostic-human-review-v1.1",
        "request_id": v1_batch.get("request_id"),
        "status": "diagnostic_only_not_production_approval",
        "system_reported_high_quality_capacity": 7,
        "human_corrected_novel_concept_capacity": 3,
        "current_directly_usable": 2,
        "items": items,
        "approval_performed": False,
        "excel_export_performed": False,
    }


def build_v1_vs_v1_1_scorecard(
    v1_plan: dict[str, Any],
    v1_1_plan: dict[str, Any],
    human_diagnostic: dict[str, Any],
) -> dict[str, Any]:
    v1_selected = list(v1_plan.get("selected_concepts") or [])
    v1_1_selected = list(v1_1_plan.get("selected_concepts") or [])
    current_v1_ids = {item.get("concept_id") for item in v1_selected}
    current_rejections = [
        item
        for item in v1_1_plan["historical_exposure_gate"]["rejected_candidates"]
        if item.get("concept_id") in current_v1_ids
        and item.get("v1_1_gate_decision") == "historical_exposure_rejected"
    ]
    v1_average = (
        round(
            sum(
                float(item["editorial_score_summary"]["weighted_total"])
                for item in v1_selected
            )
            / len(v1_selected),
            4,
        )
        if v1_selected
        else 0.0
    )
    return {
        "schema_version": "content-quality-v1-vs-v1.1-scorecard-v1.0",
        "request_id": v1_plan.get("request_id"),
        "metrics": {
            "candidate_pool_size": {"v1": 30, "v1_1": 30},
            "system_high_quality_novel_capacity": {
                "v1": v1_plan.get("capacity", {}).get(
                    "high_quality_novel_capacity"
                ),
                "v1_1": v1_1_plan.get("capacity", {}).get(
                    "high_quality_novel_capacity"
                ),
            },
            "novelty_surviving_capacity": {
                "v1": v1_plan.get("capacity", {}).get(
                    "high_quality_novel_capacity"
                ),
                "v1_1": v1_1_plan.get("capacity", {}).get(
                    "novelty_surviving_capacity"
                ),
            },
            "current_seven_historical_exposure_rejections": {
                "v1": 0,
                "v1_1": len(current_rejections),
            },
            "average_selected_editorial_score": {
                "v1": v1_average,
                "v1_1": v1_1_plan.get("batch_editorial_summary", {}).get(
                    "average_editorial_score"
                ),
            },
            "novel_exclusive_anchor_coverage": {
                "v1": None,
                "v1_1": v1_1_plan.get("batch_editorial_summary", {}).get(
                    "novel_exclusive_anchor_coverage"
                ),
            },
            "human_corrected_novel_concept_capacity": {
                "v1": human_diagnostic[
                    "human_corrected_novel_concept_capacity"
                ],
                "v1_1": None,
            },
            "human_confirmed_directly_usable": {
                "v1": human_diagnostic["current_directly_usable"],
                "v1_1": None,
            },
            "system_selected_pending_human_review": {
                "v1_1": len(v1_1_selected)
            },
            "historical_exposure_rejected_candidates": {
                "v1": None,
                "v1_1": v1_1_plan.get("historical_exposure_gate", {}).get(
                    "historical_exposure_rejected_count"
                ),
            },
            "speaker_fit_revision_required": {
                "v1": None,
                "v1_1": v1_1_plan.get("capacity", {}).get(
                    "revision_required_capacity"
                ),
            },
            "remote_model_calls_for_diagnostic": {"v1_1": 0},
            "script_generation_performed": {"v1_1": False},
            "capacity_padding": {"v1": False, "v1_1": False},
        },
        "current_v1_historical_exposure_rejected_concepts": [
            item.get("concept_id") for item in current_rejections
        ],
        "v1_1_selected_concepts": [
            item.get("concept_id") for item in v1_1_selected
        ],
        "status": "review_required",
    }


def _fact_atom_lineage(
    atom_ids: Iterable[str], fact_atoms: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    atom_by_id = {atom["fact_atom_id"]: atom for atom in fact_atoms}
    return [
        {
            "source_ref": atom_id,
            "fact_atom_id": atom_id,
            "field": atom_by_id[atom_id].get("field"),
            "persona_sha256": atom_by_id[atom_id].get("persona_sha256"),
            "fact_atom_version": atom_by_id[atom_id].get("fact_atom_version"),
            "authority": "approved_persona_known_fact",
        }
        for atom_id in sorted(set(atom_ids))
        if atom_id in atom_by_id
    ]


def _matching_fact_atom_ids(
    concept: dict[str, Any],
    fact_atoms: list[dict[str, Any]],
    fields: set[str],
    text_fields: tuple[str, ...] = (
        "audience_need",
        "central_claim",
        "primary_topic",
        "exclusive_anchor",
        "why_publish",
    ),
) -> list[str]:
    text = " ".join(str(concept.get(field) or "") for field in text_fields)
    return sorted(
        {
            atom["fact_atom_id"]
            for atom in fact_atoms
            if atom.get("field") in fields and fact_atom_matches_text(atom, text)[0]
        }
    )


def audience_need_lineage_v1_1_1(
    concept: dict[str, Any], fact_atoms: list[dict[str, Any]]
) -> dict[str, Any]:
    primary_fields = set(concept.get("primary_fact_refs") or [])
    supporting_fields = set(concept.get("supporting_fact_refs") or [])
    direct_origins = (
        ("authorized_feedback", {"authorized_customer_cases_or_feedback"}),
        ("known_customer_question", {"customer_questions"}),
        ("known_customer_pain", {"customer_pains"}),
        ("known_use_case", {"customer_use_cases"}),
    )
    origin: str | None = None
    source_refs: list[str] = []
    for candidate_origin, fields in direct_origins:
        eligible_fields = primary_fields & fields
        if not eligible_fields:
            continue
        source_refs = _matching_fact_atom_ids(
            concept, fact_atoms, eligible_fields
        )
        if source_refs:
            origin = candidate_origin
            break

    decision_fields = {
        "pricing_facts",
        "included_service_facts",
        "service_time_facts",
        "time_efficiency_fact",
        "primary_products_or_services",
        "product_or_service_facts",
        "service_process",
        "differentiators",
        "service_boundaries",
        "service_limitations",
    }
    decision_cue = re.search(
        r"价格|收费|多少钱|多久|多长时间|等待|排队|能不能|是否|可不可以|"
        r"怎么|如何|免费|口味|加工|流程|带走|看见|看到|限制",
        str(concept.get("audience_need") or ""),
    )
    if origin is None and decision_cue:
        eligible_fields = primary_fields & decision_fields
        source_refs = _matching_fact_atom_ids(
            concept, fact_atoms, eligible_fields
        )
        if source_refs:
            origin = "service_decision_need"

    basis_refs = _matching_fact_atom_ids(
        concept,
        fact_atoms,
        primary_fields | supporting_fields,
    )
    if origin is None or not source_refs:
        return {
            "origin": "editorial_hypothesis",
            "audience_need_source_refs": [],
            "source_type": "hypothesis",
            "authority": "editorial_only",
            "source_lineage": [],
            "hypothesis_basis_fact_atom_refs": basis_refs,
            "customer_need_claimed_as_known": False,
            "service_decision_need_source_valid": False,
        }
    return {
        "origin": origin,
        "audience_need_source_refs": source_refs,
        "source_type": "fact_atom",
        "authority": "approved_persona_known_fact_lineage",
        "source_lineage": _fact_atom_lineage(source_refs, fact_atoms),
        "hypothesis_basis_fact_atom_refs": [],
        "customer_need_claimed_as_known": origin
        in {
            "known_customer_pain",
            "known_customer_question",
            "known_use_case",
            "authorized_feedback",
        },
        "service_decision_need_source_valid": (
            origin != "service_decision_need" or bool(source_refs)
        ),
    }


def material_information_gain_v1_1_1(
    concept: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    fact_atoms = list(ledger.get("fact_atom_catalog") or [])
    atom_by_id = {atom["fact_atom_id"]: atom for atom in fact_atoms}
    exposed_refs, _units = _explicit_exposure_index(ledger)
    base = concept.get("historical_exposure_summary") or (
        historical_exposure_evaluation(concept, ledger)
    )
    primary_fields = set(concept.get("primary_fact_refs") or []) | set(
        _anchor_fact_refs(concept.get("exclusive_anchor"))
    )
    primary_atom_refs = _matching_fact_atom_ids(
        concept, fact_atoms, primary_fields
    )
    if not primary_atom_refs:
        primary_atom_refs = list(base.get("core_fact_atom_refs") or [])
    novel_atom_refs = sorted(set(primary_atom_refs) - exposed_refs)
    novel_fields = {
        atom_by_id[atom_id].get("field")
        for atom_id in novel_atom_refs
        if atom_id in atom_by_id
    }
    audience_only_fields = {"core_audience"}
    only_new_audience_labels = bool(novel_fields) and novel_fields <= audience_only_fields

    candidate_markers = set(
        semantic_markers(
            " ".join(
                str(concept.get(field) or "")
                for field in ("audience_need", "central_claim", "primary_topic")
            )
        )
    )
    historical_markers = {
        marker
        for atom_id in exposed_refs
        if atom_id in atom_by_id
        for marker in atom_by_id[atom_id].get("semantic_markers") or []
    }
    audience_markers = {"young_couples", "nearby_residents"}
    functional_markers = candidate_markers - audience_markers
    historical_functional_coverage = bool(functional_markers) and (
        functional_markers <= historical_markers
    )

    novel_anchor = concept.get("novel_exclusive_anchor_summary") or (
        novel_exclusive_anchor_evaluation(concept, ledger)
    )
    decision_fields = {
        "pricing_facts",
        "included_service_facts",
        "service_time_facts",
        "time_efficiency_fact",
        "service_boundaries",
        "service_limitations",
    }
    use_case_fields = {"customer_use_cases"}
    behavior_fields = {
        "service_process",
        "product_or_service_facts",
        "differentiators",
        "process_facts",
        "operational_facts",
        "peak_handling_facts",
    }
    story_fields = {"authorized_customer_cases_or_feedback"}
    non_audience_novel = novel_fields - audience_only_fields
    value_signals = {
        "new_user_decision_information": bool(novel_fields & decision_fields),
        "new_specific_use_case": bool(novel_fields & use_case_fields),
        "new_specific_behavior_or_process": bool(novel_fields & behavior_fields),
        "new_exclusive_fact_atom": bool(
            novel_anchor.get("novel_exclusive_anchor") and non_audience_novel
        ),
        "new_authorized_customer_story": bool(
            novel_fields & story_fields or concept.get("customer_story_ref")
        ),
        "new_speaker_specific_observation": bool(
            concept.get("speaker_specific_observation_ref")
        ),
        "new_interpretation_or_action_value": bool(
            non_audience_novel
            and re.search(
                r"判断|选择|安排|避免|准备|比较|决策|怎么做",
                str(concept.get("content_job") or ""),
            )
        ),
    }
    base_gain = bool(base.get("material_information_gain"))
    has_material_value = base_gain and any(value_signals.values())
    audience_relabel_rejection = bool(
        base_gain
        and only_new_audience_labels
        and historical_functional_coverage
        and not any(value_signals.values())
    )
    if audience_relabel_rejection:
        decision = "insufficient_material_information_gain"
        reason = (
            "new_audience_label_reuses_historically_communicated_pain_and_use_case"
        )
    elif not base_gain:
        decision = "insufficient_material_information_gain"
        reason = "core_information_already_exposed_or_unresolved"
    elif has_material_value:
        decision = "materially_different"
        reason = "new_fact_atom_adds_independent_editorial_or_decision_value"
    else:
        decision = "insufficient_material_information_gain"
        reason = "new_fact_atom_does_not_add_independent_publishable_value"
    return {
        "decision": decision,
        "material_information_gain": decision == "materially_different",
        "reason": reason,
        "base_v1_1_material_information_gain": base_gain,
        "primary_fact_atom_refs": primary_atom_refs,
        "novel_primary_fact_atom_refs": novel_atom_refs,
        "novel_primary_fact_fields": sorted(field for field in novel_fields if field),
        "only_new_audience_labels": only_new_audience_labels,
        "historical_functional_information_covered": historical_functional_coverage,
        "candidate_functional_markers": sorted(functional_markers),
        "historical_matching_functional_markers": sorted(
            functional_markers & historical_markers
        ),
        "value_signals": value_signals,
    }


def editorial_score_v1_1_1(
    concept: dict[str, Any],
    audience_lineage: dict[str, Any],
    material_gain: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = dict(DEFAULT_EDITORIAL_V1_1_WEIGHTS if weights is None else weights)
    prior = concept.get("editorial_score_v1_1") or {}
    dimensions = dict(prior.get("dimensions") or {})
    origin = audience_lineage["origin"]
    source_count = len(audience_lineage.get("audience_need_source_refs") or [])
    if origin in {
        "known_customer_pain",
        "known_customer_question",
        "authorized_feedback",
    }:
        relevance = 5.0
    elif origin == "known_use_case":
        relevance = 4.5
    elif origin == "service_decision_need" and source_count:
        relevance = min(4.0, 3.5 + 0.25 * max(0, source_count - 1))
    else:
        relevance = 2.5
    dimensions["audience_relevance"] = relevance
    dimensions["information_gain"] = (
        5.0 if material_gain.get("material_information_gain") else 0.0
    )
    if not material_gain.get("material_information_gain"):
        dimensions["specificity"] = min(
            float(dimensions.get("specificity") or 0), 2.5
        )
        dimensions["business_distinctiveness"] = 1.0
    denominator = sum(float(weights.get(key, 0)) for key in dimensions)
    weighted = sum(
        float(value) * float(weights.get(key, 0))
        for key, value in dimensions.items()
    )
    return {
        "scale": "0-5",
        "policy": "provisional_configurable_v1_1_1_closure",
        "weights": weights,
        "dimensions": dimensions,
        "weighted_total": round(weighted / denominator, 4) if denominator else 0.0,
        "audience_need_source_ref_count": source_count,
        "material_information_gain_required": True,
        "historical_supporting_fact_reuse_ratio": prior.get(
            "historical_supporting_fact_reuse_ratio", 0.0
        ),
        "single_focus_dilution": prior.get("single_focus_dilution", 0.0),
    }


def build_content_plan_v1_1_1(
    *,
    v1_1_plan: dict[str, Any],
    ledger: dict[str, Any],
    request: dict[str, Any],
    source_artifact_hashes: dict[str, str],
    created_at: str | None = None,
) -> dict[str, Any]:
    minimum_score = float(
        (request.get("content_quality_v1") or {}).get(
            "minimum_editorial_score", DEFAULT_MINIMUM_EDITORIAL_SCORE
        )
    )
    fact_atoms = list(ledger.get("fact_atom_catalog") or [])
    evaluated: list[dict[str, Any]] = []
    for source in v1_1_plan.get("candidate_pool", {}).get("candidates") or []:
        candidate = json.loads(json.dumps(source, ensure_ascii=False))
        lineage = audience_need_lineage_v1_1_1(candidate, fact_atoms)
        material = material_information_gain_v1_1_1(candidate, ledger)
        score = editorial_score_v1_1_1(candidate, lineage, material)
        candidate.update(
            {
                "audience_need_origin": lineage["origin"],
                "audience_need_source_refs": lineage[
                    "audience_need_source_refs"
                ],
                "audience_need_source_lineage": lineage,
                "material_information_gain_v1_1_1": material,
                "editorial_score_v1_1_1": score,
            }
        )
        prior_decision = candidate.get("v1_1_gate_decision")
        if prior_decision == "historical_exposure_rejected":
            decision = "historical_exposure_rejected"
        elif prior_decision == "candidate_pool_atomic_duplicate_rejected":
            decision = "candidate_pool_atomic_duplicate_rejected"
        elif not material["material_information_gain"]:
            decision = "insufficient_material_information_gain"
        elif candidate.get("unsupported_detail_flags"):
            decision = "unsupported_detail_revision_required"
        elif float((candidate.get("speaker_fit") or {}).get("score") or 0) < 3.0:
            decision = "speaker_fit_revision_required"
        elif float(score["weighted_total"]) < minimum_score:
            decision = "editorial_quality_rejected"
        else:
            decision = "high_quality_novel"
        candidate["v1_1_1_gate_decision"] = decision
        evaluated.append(candidate)

    novelty_survivors = [
        item
        for item in evaluated
        if item["material_information_gain_v1_1_1"]["material_information_gain"]
        and item.get("v1_1_gate_decision")
        not in {
            "historical_exposure_rejected",
            "candidate_pool_atomic_duplicate_rejected",
        }
    ]
    revision_required = [
        item
        for item in novelty_survivors
        if item["v1_1_1_gate_decision"].endswith("revision_required")
    ]
    high_quality = sorted(
        [
            item
            for item in novelty_survivors
            if item["v1_1_1_gate_decision"] == "high_quality_novel"
        ],
        key=lambda item: (
            -float(item["editorial_score_v1_1_1"]["weighted_total"]),
            item.get("concept_id") or "",
        ),
    )
    requested = int(request.get("quantity") or 0)
    selected = high_quality[:requested]
    for rank, item in enumerate(selected, start=1):
        item["selected_rank_v1_1_1"] = rank
        item["selected_reason_v1_1_1"] = (
            "Independent material information gain with sourced audience-need lineage."
        )
    origins = Counter(item["audience_need_origin"] for item in evaluated)
    sourced = sum(bool(item["audience_need_source_refs"]) for item in evaluated)
    service_decisions = [
        item for item in evaluated if item["audience_need_origin"] == "service_decision_need"
    ]
    concept_018 = next(
        (item for item in evaluated if item.get("concept_id") == "CONCEPT_018"),
        None,
    )
    return {
        "schema_version": PLAN_V1_1_1_SCHEMA_VERSION,
        "quality_engine_version": QUALITY_ENGINE_V1_1_1_VERSION,
        "created_at": created_at or now_iso(),
        "request_id": request.get("request_id"),
        "business_id": v1_1_plan.get("business_id"),
        "speaker_id": v1_1_plan.get("speaker_id"),
        "speaker_type": v1_1_plan.get("speaker_type"),
        "diagnostic_stage": "closure_calibration_offline_only",
        "remote_model_call": {
            "performed": False,
            "call_count": 0,
            "tokens": 0,
            "elapsed_seconds": 0,
        },
        "candidate_pool": {
            "source": "preserved_v1_1_candidate_pool",
            "configured_size": v1_1_plan.get("candidate_pool", {}).get(
                "configured_size"
            ),
            "received_size": v1_1_plan.get("candidate_pool", {}).get(
                "received_size"
            ),
            "authority_valid_size": len(evaluated),
            "authority_rejected_size": v1_1_plan.get("candidate_pool", {}).get(
                "authority_rejected_size", 0
            ),
            "authority_rejected_candidates": v1_1_plan.get(
                "candidate_pool", {}
            ).get("authority_rejected_candidates", []),
            "source_pool_fully_accounted_for": (
                len(evaluated)
                + int(
                    v1_1_plan.get("candidate_pool", {}).get(
                        "authority_rejected_size", 0
                    )
                    or 0
                )
                == int(
                    v1_1_plan.get("candidate_pool", {}).get("received_size", 0)
                    or 0
                )
            ),
            "candidates": evaluated,
        },
        "closure_calibration": {
            "material_information_gain_rule": (
                "audience_label_or_known_audience_bound_to_historical_use_case_is_not_novel"
            ),
            "concept_018_final_decision": (
                concept_018.get("v1_1_1_gate_decision") if concept_018 else None
            ),
            "concept_018_reasoning": (
                concept_018.get("material_information_gain_v1_1_1")
                if concept_018
                else None
            ),
        },
        "audience_need_lineage_summary": {
            "origin_distribution": dict(sorted(origins.items())),
            "sourced_count": sourced,
            "hypothesis_count": len(evaluated) - sourced,
            "service_decision_need_count": len(service_decisions),
            "service_decision_need_without_source_refs": sum(
                not item.get("audience_need_source_refs")
                for item in service_decisions
            ),
        },
        "novelty_gate_v1_1_1": {
            "historical_exposure_rejected_count": sum(
                item["v1_1_1_gate_decision"] == "historical_exposure_rejected"
                for item in evaluated
            ),
            "candidate_pool_atomic_duplicate_count": sum(
                item["v1_1_1_gate_decision"]
                == "candidate_pool_atomic_duplicate_rejected"
                for item in evaluated
            ),
            "insufficient_material_information_gain_count": sum(
                item["v1_1_1_gate_decision"]
                == "insufficient_material_information_gain"
                for item in evaluated
            ),
            "insufficient_material_information_gain_candidates": [
                item
                for item in evaluated
                if item["v1_1_1_gate_decision"]
                == "insufficient_material_information_gain"
            ],
        },
        "editorial_ranking_v1_1_1": {
            "minimum_editorial_score": minimum_score,
            "weights": DEFAULT_EDITORIAL_V1_1_WEIGHTS,
            "novelty_surviving_concepts": novelty_survivors,
            "revision_required_concepts": revision_required,
            "ranked_high_quality_novel_candidates": high_quality,
        },
        "capacity": {
            "requested_quantity": requested,
            "novelty_surviving_capacity": len(novelty_survivors),
            "revision_required_capacity": len(revision_required),
            "high_quality_novel_capacity": len(high_quality),
            "selected_quantity": len(selected),
            "status": "supported" if len(high_quality) >= requested else "capacity_limited",
            "padding_generated": False,
            "script_generation_performed": False,
        },
        "selected_concepts": selected,
        "lineage": {
            "source_v1_1_content_plan_sha256": source_artifact_hashes[
                "content_plan_v1_1"
            ],
            "content_ledger_sha256": source_artifact_hashes["content_ledger_v1"],
            "preserved_source_artifacts": source_artifact_hashes,
        },
        "authority": {
            "persona_mutated": False,
            "content_ledger_mutated": False,
            "fact_atom_catalog_mutated": False,
            "pattern_or_case_used_to_create_facts": False,
            "unknown_or_requires_review_consumed": False,
            "remote_model_called": False,
            "script_generation_performed": False,
            "approval_performed": False,
            "excel_export_performed": False,
        },
        "status": "review_required",
    }


def build_content_gap_report_v1(
    *,
    content_plan_v1_1_1: dict[str, Any],
    ledger: dict[str, Any],
    speaker_persona: dict[str, Any] | None,
    source_artifact_hashes: dict[str, str],
    created_at: str | None = None,
) -> dict[str, Any]:
    fact_atoms = list(ledger.get("fact_atom_catalog") or [])
    atom_by_id = {atom["fact_atom_id"]: atom for atom in fact_atoms}
    exposure: dict[str, set[str]] = {}
    for entry in ledger.get("entries") or []:
        if not is_strong_memory(entry):
            continue
        for unit in entry.get("communicated_information_units") or []:
            if unit.get("explicitness") != "explicit":
                continue
            for atom_id in unit.get("fact_atom_refs") or []:
                exposure.setdefault(atom_id, set()).add(str(entry.get("content_id")))
    exposed_refs = set(exposure)
    coverage_rules = (
        (
            "service_definition",
            {"primary_products_or_services", "customer_use_cases", "service_process"},
            set(),
        ),
        (
            "pricing",
            {"pricing_facts", "product_or_service_facts"},
            {"vegetable_price_8_10", "steaming_price_15", "braising_price_18"},
        ),
        (
            "taste_customization",
            {"product_or_service_facts", "customer_pains"},
            {"taste_less_salt_spicy", "customer_taste_request"},
        ),
        ("service_process", {"service_process"}, {"window_delivery", "onsite_processing"}),
        (
            "waiting_time",
            {"service_time_facts", "time_efficiency_fact"},
            {"quick_dish_5_minutes", "complex_dish_15_minutes", "total_time_30_minutes", "peak_queue_possible"},
        ),
        ("open_kitchen_visibility", {"differentiators"}, {"open_kitchen_process_visible"}),
        ("free_included_items", {"included_service_facts"}, {"free_condiments", "free_rice"}),
        ("customer_selected_ingredients", {"differentiators"}, {"customer_selects_ingredients"}),
        (
            "authorized_customer_story",
            {"authorized_customer_cases_or_feedback"},
            set(),
        ),
    )
    historical_coverage: list[dict[str, Any]] = []
    for coverage_id, fields, markers in coverage_rules:
        matching = [
            atom_id
            for atom_id in exposed_refs
            if atom_id in atom_by_id
            and (
                atom_by_id[atom_id].get("field") in fields
                or bool(set(atom_by_id[atom_id].get("semantic_markers") or []) & markers)
            )
        ]
        if matching:
            historical_coverage.append(
                {
                    "coverage_id": coverage_id,
                    "status": "covered",
                    "fact_atom_refs": sorted(matching),
                    "source_content_refs": sorted(
                        {
                            content_id
                            for atom_id in matching
                            for content_id in exposure.get(atom_id, set())
                        }
                    ),
                }
            )

    exhausted = [
        {
            "fact_atom_id": atom_id,
            "field": atom_by_id[atom_id].get("field"),
            "normalized_meaning": atom_by_id[atom_id].get("normalized_meaning"),
            "historical_content_refs": sorted(exposure[atom_id]),
            "historical_content_count": len(exposure[atom_id]),
            "status": "explicitly_communicated",
        }
        for atom_id in sorted(exposed_refs)
        if atom_id in atom_by_id
    ]
    selected_refs = {
        atom_id
        for item in content_plan_v1_1_1.get("selected_concepts") or []
        for atom_id in item.get("material_information_gain_v1_1_1", {}).get(
            "novel_primary_fact_atom_refs", []
        )
    }
    revision_refs = {
        atom_id
        for item in content_plan_v1_1_1.get("editorial_ranking_v1_1_1", {}).get(
            "revision_required_concepts", []
        )
        for atom_id in item.get("material_information_gain_v1_1_1", {}).get(
            "novel_primary_fact_atom_refs", []
        )
    }
    insufficient_refs = {
        atom_id
        for item in content_plan_v1_1_1.get("novelty_gate_v1_1_1", {}).get(
            "insufficient_material_information_gain_candidates", []
        )
        for atom_id in item.get("material_information_gain_v1_1_1", {}).get(
            "novel_primary_fact_atom_refs", []
        )
    }
    content_fields = {
        "primary_products_or_services",
        "core_audience",
        "customer_use_cases",
        "customer_pains",
        "differentiators",
        "product_or_service_facts",
        "pricing_facts",
        "included_service_facts",
        "service_process",
        "service_time_facts",
        "business_volume_fact",
        "time_efficiency_fact",
        "authorized_customer_cases_or_feedback",
        "values",
        "business_principles",
        "process_facts",
    }
    remaining = []
    for atom in fact_atoms:
        atom_id = atom["fact_atom_id"]
        if atom_id in exposed_refs or atom.get("field") not in content_fields:
            continue
        if atom_id in selected_refs:
            planning_status = "selected_pending_human_review"
        elif atom_id in revision_refs:
            planning_status = "revision_required"
        elif atom_id in insufficient_refs:
            planning_status = "insufficient_as_standalone_content"
        else:
            planning_status = "unallocated_authority_fact_not_automatically_novel"
        remaining.append(
            {
                "fact_atom_id": atom_id,
                "field": atom.get("field"),
                "normalized_meaning": atom.get("normalized_meaning"),
                "planning_status": planning_status,
            }
        )

    known_fields = {atom.get("field") for atom in fact_atoms}
    speaker_known_fields = {
        field
        for field, fact in (speaker_persona or {}).get("facts", {}).items()
        if fact.get("state") == "known"
    }
    story_roots = {
        str(atom.get("value_path") or "").split(".", 1)[0]
        for atom in fact_atoms
        if atom.get("field") == "authorized_customer_cases_or_feedback"
    }
    novel_use_case_count = sum(
        atom.get("field") == "customer_use_cases"
        and atom["fact_atom_id"] not in exposed_refs
        for atom in fact_atoms
    )
    category_specs: list[dict[str, Any]] = []

    def recommend(
        category: str,
        priority: str,
        reason: str,
        collection_request: str,
        requested_units: int,
        low: int,
        high: int,
    ) -> None:
        category_specs.append(
            {
                "category": category,
                "priority": priority,
                "reason": reason,
                "collection_request": collection_request,
                "answer_must_come_from": "customer_or_authorized_human_source",
                "requested_evidence_units": requested_units,
                "expected_capacity_gain": {
                    "estimate_type": "heuristic",
                    "estimated_additional_concepts_min": low,
                    "estimated_additional_concepts_max": high,
                    "disclaimer": "heuristic_not_performance_prediction",
                },
            }
        )

    if "customer_questions" not in known_fields:
        recommend(
            "customer_questions",
            "high",
            "No approved Customer Question Fact Atoms are available.",
            "Ask for five real questions customers repeatedly ask, with the customer's approved factual answer to each.",
            5,
            2,
            5,
        )
    if (speaker_persona or {}).get("speaker_type") == "frontline_expert" and not (
        speaker_known_fields
        & {"frontline_observations", "speaker_observations", "observed_customer_questions"}
    ):
        recommend(
            "frontline_observations",
            "high",
            "The frontline speaker has role authority but no approved observation set.",
            "Ask the speaker for five recurring, directly observed customer actions, questions, or decision moments; collect only events personally observed.",
            5,
            3,
            5,
        )
    if len(story_roots) <= 1:
        recommend(
            "customer_stories",
            "high",
            "The authorized story space contains at most one customer record and it is already substantially communicated.",
            "Collect three additional customer stories or quotes with explicit publication authorization and a concrete situation or takeaway.",
            3,
            2,
            3,
        )
    if novel_use_case_count <= 1:
        recommend(
            "specific_product_or_dish_cases",
            "high",
            "Only a narrow uncommunicated product or ingredient use case remains.",
            "Ask for five real ingredient or dish cases, including what was brought in, what processing was requested, and any verified constraint.",
            5,
            3,
            5,
        )
    if not (known_fields & {"service_boundaries", "service_limitations"}):
        recommend(
            "service_boundaries",
            "high",
            "No approved service-boundary facts are available.",
            "Ask what cannot be accepted, what takes materially longer, and which requests require advance confirmation.",
            3,
            2,
            3,
        )
    if not (known_fields & {"operational_facts", "peak_handling_facts", "process_facts"}):
        recommend(
            "new_operational_facts",
            "high",
            "Existing timing and queue facts do not explain the real peak-handling method.",
            "Ask for three verified peak-period handling actions, sequencing rules, or observable operating constraints.",
            3,
            2,
            4,
        )
    if not (
        speaker_known_fields
        & {"speaker_personal_experience", "work_experience", "years_in_business"}
    ):
        recommend(
            "speaker_personal_experience",
            "medium",
            "No approved personal experience or judgment facts exist for the speaker.",
            "Ask the speaker for three true work experiences or bounded judgments, then submit them through Persona review.",
            3,
            1,
            3,
        )
    if "business_principles" in known_fields:
        recommend(
            "business_decisions",
            "medium",
            "Business-purpose facts exist, but the current frontline speaker is not their natural owner.",
            "Ask an authorized operator to explain three real business decisions, their context, and what may be published.",
            3,
            1,
            3,
        )
    if not (known_fields & {"brand_story", "founder_or_operator_story"}):
        recommend(
            "brand_context",
            "medium",
            "No approved brand or operator story Fact Atoms are available.",
            "Ask an authorized operator for three factual brand-context moments without inferring motives or outcomes.",
            3,
            1,
            3,
        )

    return {
        "schema_version": CONTENT_GAP_REPORT_SCHEMA_VERSION,
        "created_at": created_at or now_iso(),
        "business_id": content_plan_v1_1_1.get("business_id"),
        "speaker_id": content_plan_v1_1_1.get("speaker_id"),
        "current_requested_quantity": content_plan_v1_1_1.get("capacity", {}).get(
            "requested_quantity"
        ),
        "current_high_quality_novel_capacity": content_plan_v1_1_1.get(
            "capacity", {}
        ).get("high_quality_novel_capacity"),
        "historical_coverage_summary": historical_coverage,
        "exhausted_or_highly_used_fact_atoms": exhausted,
        "remaining_novel_fact_atoms": remaining,
        "content_gap_categories": category_specs,
        "expected_capacity_gain": {
            "estimate_type": "heuristic",
            "disclaimer": "heuristic_not_performance_prediction",
            "recommendations": [
                {
                    "category": item["category"],
                    **item["expected_capacity_gain"],
                }
                for item in category_specs
            ],
        },
        "collection_boundary": {
            "artifact_purpose": "tell_operations_what_to_ask_not_supply_answers",
            "automatic_answer_completion": False,
            "external_research_substitution": False,
            "case_fact_transfer": False,
            "industry_common_knowledge_promoted_to_known": False,
            "persona_writeback": False,
            "required_future_lifecycle": [
                "human_input",
                "persona_review",
                "approval",
            ],
        },
        "lineage": {
            "source_content_plan_v1_1_1_sha256": source_artifact_hashes[
                "content_plan_v1_1_1"
            ],
            "content_ledger_sha256": source_artifact_hashes["content_ledger_v1"],
            "fact_atom_version": FACT_ATOM_VERSION,
            "communicated_information_version": COMMUNICATED_INFORMATION_VERSION,
            "source_fact_states_consumed": ["known"],
        },
        "authority": {
            "new_persona_facts_created": False,
            "unknown_or_requires_review_values_consumed": False,
            "recommendations_are_authority": False,
            "remote_model_called": False,
        },
        "status": "diagnostic_only",
    }


def approved_persona_ref(
    *,
    persona_path: Path,
    approval_receipt_path: Path,
    expected_scope: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load an approved Persona and return a verified, immutable lineage ref."""
    persona_path = persona_path.expanduser().resolve()
    approval_receipt_path = approval_receipt_path.expanduser().resolve()
    persona = read_json(persona_path)
    receipt = read_json(approval_receipt_path)
    persona_sha = sha256_file(persona_path)
    if persona.get("persona_scope") != expected_scope:
        raise RuntimeError(
            f"Expected {expected_scope} Persona, got {persona.get('persona_scope')!r}."
        )
    lifecycle = persona.get("lifecycle") or {}
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        raise RuntimeError(f"Persona is not approved: {persona_path}")
    if receipt.get("decision") != "approved" or receipt.get("human_gate") is not True:
        raise RuntimeError(f"Persona approval receipt is invalid: {approval_receipt_path}")
    if (
        receipt.get("persona_id") != persona.get("persona_id")
        or receipt.get("revision") != persona.get("revision")
    ):
        raise RuntimeError("Persona approval receipt identity mismatch.")
    if receipt.get("persona_sha256_after_approval") != persona_sha:
        raise RuntimeError("Approved Persona SHA does not match its approval receipt.")
    return persona, {
        "persona_id": persona.get("persona_id"),
        "revision": persona.get("revision"),
        "persona_scope": expected_scope,
        "speaker_type": persona.get("speaker_type"),
        "path": str(persona_path),
        "sha256": persona_sha,
        "approval_receipt_path": str(approval_receipt_path),
        "approval_receipt_sha256": sha256_file(approval_receipt_path),
        "status": "approved",
    }


def _intake_expected_gain(
    minimum: int,
    maximum: int,
    *,
    unit: str = "potential_high_quality_novel_concepts",
) -> dict[str, Any]:
    return {
        "estimate_type": "heuristic_not_performance_prediction",
        "estimated_min": minimum,
        "estimated_max": maximum,
        "unit": unit,
        "guaranteed": False,
        "disclaimer": (
            "A completed answer does not guarantee a publishable concept; all answers "
            "must pass fact extraction, Persona review, approval, novelty, and editorial gates."
        ),
    }


def _build_intake_question(
    *,
    question_id: str,
    gap_category: str,
    priority: str,
    target_role: str,
    question_text: str,
    objective: str,
    target_fact_type: str,
    related_fact_atoms: list[str],
    historical_coverage: list[dict[str, Any]],
    possible_content_jobs: list[str],
    expected_gain: tuple[int, int],
    reuse_authorization_required: bool = False,
) -> dict[str, Any]:
    question: dict[str, Any] = {
        "question_id": question_id,
        "gap_category": gap_category,
        "priority": priority,
        "recommended_target_role": target_role,
        "question_text": question_text,
        "information_objective": objective,
        "target_fact_type": target_fact_type,
        "related_existing_fact_atoms": related_fact_atoms,
        "historical_coverage_to_avoid": historical_coverage,
        "possible_content_jobs": possible_content_jobs,
        "expected_capacity_gain": _intake_expected_gain(*expected_gain),
        "answer_status": "unanswered",
        "authority_state": "raw_input_pending_review",
        "future_answer_first_state": "raw_customer_input",
        "creates_persona_fact": False,
        "reuse_authorization_required": reuse_authorization_required,
    }
    if reuse_authorization_required:
        question["reuse_authorization_fields"] = {
            "name": "pending",
            "form_of_address": "pending",
            "scenario": "pending",
            "verbatim_quote": "pending",
            "image": "pending",
            "video": "pending",
            "review_or_evaluation": "pending",
        }
    return question


def build_content_capacity_replenishment_intake_v1(
    *,
    intake_id: str,
    business_persona: dict[str, Any],
    business_persona_ref: dict[str, Any],
    speaker_persona: dict[str, Any],
    speaker_persona_ref: dict[str, Any],
    ledger: dict[str, Any],
    ledger_ref: dict[str, Any],
    gap_report: dict[str, Any],
    gap_report_ref: str,
    gap_report_sha256: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic, gap-driven interview intake without creating facts."""
    business_id = str(business_persona.get("persona_id") or "")
    speaker_id = str(speaker_persona.get("persona_id") or "")
    if ledger.get("business_id") != business_id:
        raise RuntimeError("Content Ledger business does not match approved Business Persona.")
    if gap_report.get("business_id") != business_id:
        raise RuntimeError("Content Gap Report business does not match approved Business Persona.")
    if gap_report.get("speaker_id") != speaker_id:
        raise RuntimeError("Content Gap Report speaker does not match approved Speaker Persona.")
    if speaker_persona.get("speaker_type") != "frontline_expert":
        raise RuntimeError("This deterministic intake template requires a frontline_expert.")

    gap_specs = {
        item["category"]: item for item in gap_report.get("content_gap_categories") or []
    }
    high_priority_categories = {
        category
        for category, spec in gap_specs.items()
        if spec.get("priority") == "high"
    }
    required_high = {
        "customer_questions",
        "frontline_observations",
        "customer_stories",
        "specific_product_or_dish_cases",
        "service_boundaries",
        "new_operational_facts",
    }
    if not required_high.issubset(high_priority_categories):
        missing = sorted(required_high - high_priority_categories)
        raise RuntimeError(f"Content Gap Report is missing required high-priority gaps: {missing}")

    atom_by_id = {
        atom.get("fact_atom_id"): atom for atom in ledger.get("fact_atom_catalog") or []
    }
    exhausted = gap_report.get("exhausted_or_highly_used_fact_atoms") or []
    exhausted_refs_by_field: dict[str, list[str]] = {}
    for item in exhausted:
        atom_id = item.get("fact_atom_id")
        atom = atom_by_id.get(atom_id) or item
        exhausted_refs_by_field.setdefault(str(atom.get("field") or ""), []).append(
            str(atom_id)
        )

    coverage_by_id = {
        item.get("coverage_id"): item
        for item in gap_report.get("historical_coverage_summary") or []
    }

    category_fields = {
        "customer_questions": ["customer_pains", "customer_use_cases", "pricing_facts", "service_time_facts"],
        "frontline_observations": ["service_process", "differentiators", "customer_pains"],
        "specific_product_or_dish_cases": ["customer_use_cases", "product_or_service_facts", "service_process"],
        "service_boundaries": ["primary_products_or_services", "service_process", "service_time_facts"],
        "customer_stories": ["authorized_customer_cases_or_feedback"],
        "new_operational_facts": ["business_volume_fact", "service_time_facts", "service_process"],
        "speaker_personal_experience": [],
        "business_decisions": ["business_principles"],
        "brand_context": ["values", "business_principles"],
    }
    category_coverage = {
        "customer_questions": ["pricing", "taste_customization", "waiting_time", "free_included_items"],
        "frontline_observations": ["service_process", "open_kitchen_visibility", "customer_selected_ingredients"],
        "specific_product_or_dish_cases": ["service_definition", "service_process", "taste_customization"],
        "service_boundaries": ["service_definition", "waiting_time", "taste_customization"],
        "customer_stories": ["authorized_customer_story"],
        "new_operational_facts": ["service_process", "waiting_time"],
        "speaker_personal_experience": ["service_process"],
        "business_decisions": ["service_definition"],
        "brand_context": ["service_definition"],
    }
    category_jobs = {
        "customer_questions": ["answer_real_customer_question", "reduce_decision_uncertainty"],
        "frontline_observations": ["show_frontline_judgment", "explain_service_decision"],
        "specific_product_or_dish_cases": ["demonstrate_specific_use_case", "explain_processing_difference"],
        "service_boundaries": ["set_service_expectations", "prevent_misunderstanding"],
        "customer_stories": ["show_authorized_customer_scenario", "provide_social_proof"],
        "new_operational_facts": ["explain_real_operation", "set_waiting_expectations"],
        "speaker_personal_experience": ["share_frontline_experience", "explain_bounded_judgment"],
        "business_decisions": ["explain_business_decision", "clarify_service_design"],
        "brand_context": ["explain_verified_brand_context"],
    }

    def atoms_for(category: str) -> list[str]:
        return sorted(
            {
                atom_id
                for field in category_fields[category]
                for atom_id in exhausted_refs_by_field.get(field, [])
                if atom_id and atom_id != "None"
            }
        )

    def coverage_for(category: str) -> list[dict[str, Any]]:
        return [
            {
                "coverage_id": coverage_id,
                "fact_atom_refs": list(
                    (coverage_by_id.get(coverage_id) or {}).get("fact_atom_refs") or []
                ),
                "source_content_refs": list(
                    (coverage_by_id.get(coverage_id) or {}).get("source_content_refs") or []
                ),
            }
            for coverage_id in category_coverage[category]
            if coverage_id in coverage_by_id
        ]

    core_specs = [
        ("Q-C01", "frontline_observations", "frontline_chef", "请回想最近一次在窗口工作：哪位顾客带了什么食材，你当时先做了什么判断或提醒？", "收集一条由林东方亲自观察并作出判断的真实工作片段。", "speaker_specific_fact", (0, 1), False),
        ("Q-C02", "frontline_observations", "frontline_chef", "你实际遇到过哪些需要先确认再开始加工的情况？请选一个真实例子，说清当时看到了什么、怎么判断。", "收集可核验的一线观察、确认动作与判断依据。", "speaker_specific_fact", (0, 1), False),
        ("Q-C03", "customer_questions", "frontline_chef", "请回忆最近一周或最近几个工作日，顾客在窗口实际问过哪些问题？请列出三个接近原话的问题。", "取得真实发生的顾客问题，而不是推测顾客会问什么。", "known_customer_question", (0, 2), False),
        ("Q-C04", "customer_questions", "frontline_chef", "这些真实问题里，哪一个曾让顾客犹豫是否加工？请讲一次具体对话和你当时的实际回答。", "取得带决策情境、真实问法和真实回答的顾客问题。", "known_customer_question", (0, 1), False),
        ("Q-C05", "specific_product_or_dish_cases", "frontline_chef", "请举一个最近接到的具体食材例子：顾客带了什么、想怎么做、你实际怎么处理？", "收集食材、请求和实际处理动作完整的具体案例。", "specific_use_case", (0, 1), False),
        ("Q-C06", "specific_product_or_dish_cases", "frontline_chef", "请再举一个处理方式明显不同的食材或菜品，说明不同发生在哪个环节。", "收集另一种具有实质处理差异的菜品或食材案例。", "specific_use_case", (0, 1), False),
        ("Q-C07", "service_boundaries", "frontline_chef", "你实际遇到过哪些食材送来后不能直接接，或必须先向顾客确认？请讲一个真实例子和原因；如果没有，请明确说没有。", "识别真实服务边界、确认事项或不能承诺的情况。", "service_boundary_fact", (0, 1), False),
        ("Q-C08", "service_boundaries", "frontline_chef", "有没有真实案例需要提前说明会等得更久或不能承诺时间？如果有，请说当时是什么食材和现场条件；如果没有，请明确说没有。", "识别由食材或现场条件触发的真实时间边界。", "service_boundary_fact", (0, 1), False),
        ("Q-C09", "customer_stories", "frontline_chef", "最近有没有一位让你印象较深的真实顾客？先不填写完整姓名：他带了什么、为什么来代炒、最后怎么说？如果没有，请明确说没有。", "收集待授权的真实顾客、场景、行为与原话。", "authorized_customer_story_candidate", (0, 1), True),
        ("Q-C10", "customer_stories", "customer", "对于上一条真实故事，请由运营人员向当事顾客逐项确认：称呼、场景、原话、照片或视频、评价中哪些允许公开使用？", "单独取得顾客故事各信息元素的公开复用授权。", "customer_story_reuse_authorization", (0, 0), True),
        ("Q-C11", "new_operational_facts", "frontline_chef", "请回想一次真实忙碌时段：窗口收到多份食材后，实际按什么顺序处理？当时有哪些现场约束？", "收集真实高峰排单动作与可观察的运营约束。", "operational_fact", (0, 1), False),
        ("Q-C12", "new_operational_facts", "frontline_chef", "忙碌时如果同时出现快菜和处理更复杂的食材，你实际如何安排？请讲一次发生过的例子；如果没有，请明确说没有。", "收集真实复杂度差异下的处理方式，不预设固定规则。", "operational_fact", (0, 1), False),
    ]
    optional_specs = [
        ("Q-O01", "frontline_observations", "frontline_chef", "有没有一次顾客临时改变做法或口味要求，你需要现场重新确认？请讲真实经过；如果没有，请明确说没有。", "补充一条现场沟通与判断的真实观察。", "speaker_specific_fact", (0, 1), False),
        ("Q-O02", "customer_questions", "frontline_chef", "除已经讲过的价格、基本等待时间、免费项目和少盐少辣之外，顾客还实际问过什么？请尽量复述一次原话。", "补充不重复已覆盖基础信息的真实顾客问题。", "known_customer_question", (0, 1), False),
        ("Q-O03", "specific_product_or_dish_cases", "frontline_chef", "请回忆一次食材状态影响处理方式的真实案例：你看到了什么，随后做了什么？如果没有，请明确说没有。", "补充由真实食材状态触发的具体处理案例。", "specific_use_case", (0, 1), False),
        ("Q-O04", "service_boundaries", "frontline_chef", "顾客提出哪些具体做法时，你需要先说明不能保证结果或需要调整？请只讲实际发生过的例子。", "补充与结果承诺相关的真实服务边界。", "service_boundary_fact", (0, 1), False),
        ("Q-O05", "customer_stories", "customer", "如果还有另一位顾客愿意分享，请记录他带来的食材、来代炒的原因、实际评价，并逐项确认可公开范围。", "补充另一条具有独立场景且获得复用授权的顾客故事。", "authorized_customer_story_candidate", (0, 1), True),
        ("Q-O06", "new_operational_facts", "frontline_chef", "请举一次设备、人员或现场空间影响处理顺序的真实情况，并说明当时实际怎么处理；如果没有，请明确说没有。", "补充可核验的现场运营约束与应对动作。", "operational_fact", (0, 1), False),
        ("Q-O07", "speaker_personal_experience", "frontline_chef", "在你本人实际做过的工作里，哪一次经历改变了你接到食材时会先检查或先询问的事项？请讲具体经过。", "收集林东方本人可核验的工作经历及其行动价值。", "speaker_personal_experience", (0, 1), False),
        ("Q-O08", "business_decisions", "brand_operator", "请由门店运营者回忆一个真实服务决定：当时要解决什么具体问题、最终采用了什么做法、哪些内容允许公开？", "向自然拥有该信息的运营角色收集真实业务决定。", "business_decision_fact", (0, 1), False),
        ("Q-O09", "brand_context", "business_owner", "请由业务负责人提供一个可核验的品牌背景事件：发生了什么、谁参与、哪些内容允许公开？", "向业务负责人收集可核验、可授权的品牌背景。", "brand_context_fact", (0, 1), False),
    ]

    def materialize(spec: tuple[Any, ...], priority: str) -> dict[str, Any]:
        question_id, category, role, text, objective, fact_type, gain, reuse = spec
        return _build_intake_question(
            question_id=question_id,
            gap_category=category,
            priority=priority,
            target_role=role,
            question_text=text,
            objective=objective,
            target_fact_type=fact_type,
            related_fact_atoms=atoms_for(category),
            historical_coverage=coverage_for(category),
            possible_content_jobs=category_jobs[category],
            expected_gain=gain,
            reuse_authorization_required=reuse,
        )

    core_questions = [materialize(spec, "core") for spec in core_specs]
    optional_questions = [
        materialize(spec, "optional")
        for spec in optional_specs
        if spec[1] in gap_specs
    ]
    all_questions = core_questions + optional_questions
    category_order = [
        "frontline_observations",
        "customer_questions",
        "specific_product_or_dish_cases",
        "service_boundaries",
        "customer_stories",
        "new_operational_facts",
        "speaker_personal_experience",
        "business_decisions",
        "brand_context",
    ]
    gap_coverage_matrix = [
        {
            "gap_category": category,
            "gap_priority": gap_specs[category].get("priority"),
            "core_question_refs": [
                item["question_id"]
                for item in core_questions
                if item["gap_category"] == category
            ],
            "optional_question_refs": [
                item["question_id"]
                for item in optional_questions
                if item["gap_category"] == category
            ],
        }
        for category in category_order
        if category in gap_specs
    ]
    role_distribution = dict(
        sorted(Counter(item["recommended_target_role"] for item in all_questions).items())
    )
    requested = int(gap_report.get("current_requested_quantity") or 0)
    current_capacity = int(gap_report.get("current_high_quality_novel_capacity") or 0)
    expected_recommendations = []
    for category in category_order:
        spec = gap_specs.get(category)
        if not spec:
            continue
        gain = spec.get("expected_capacity_gain") or {}
        expected_recommendations.append(
            {
                "gap_category": category,
                "requested_evidence_units": spec.get("requested_evidence_units"),
                "estimated_additional_concepts_min": gain.get(
                    "estimated_additional_concepts_min"
                ),
                "estimated_additional_concepts_max": gain.get(
                    "estimated_additional_concepts_max"
                ),
                "estimate_type": "heuristic_not_performance_prediction",
                "guaranteed": False,
            }
        )

    return {
        "schema_version": CONTENT_REPLENISHMENT_INTAKE_SCHEMA_VERSION,
        "intake_id": intake_id,
        "business_ref": {
            "business_id": business_id,
            "approved_persona_ref": business_persona_ref,
        },
        "speaker_ref": {
            "speaker_id": speaker_id,
            "speaker_type": speaker_persona.get("speaker_type"),
            "approved_persona_ref": speaker_persona_ref,
        },
        "source_gap_report_ref": gap_report_ref,
        "source_gap_report_sha": gap_report_sha256,
        "persona_refs": {
            "business": business_persona_ref,
            "speaker": speaker_persona_ref,
        },
        "ledger_ref": ledger_ref,
        "historical_coverage_summary": gap_report.get(
            "historical_coverage_summary"
        )
        or [],
        "current_high_quality_novel_capacity": current_capacity,
        "target_replenishment_goal": {
            "current_requested_quantity": requested,
            "current_high_quality_novel_capacity": current_capacity,
            "desired_additional_high_quality_capacity": max(
                requested - current_capacity, 0
            ),
            "goal_type": "collection_target_not_delivery_commitment",
            "capacity_stop_rule_preserved": True,
        },
        "question_groups": [
            {
                "group_id": "core_interview",
                "purpose": "highest_information_gain_gap_coverage",
                "recommended_order": 1,
                "question_count": len(core_questions),
                "questions": core_questions,
            },
            {
                "group_id": "optional_expansion",
                "purpose": "continue_only_when_core_answers_are_insufficient",
                "recommended_order": 2,
                "question_count": len(optional_questions),
                "questions": optional_questions,
            },
        ],
        "gap_coverage_matrix": gap_coverage_matrix,
        "target_role_distribution": role_distribution,
        "expected_capacity_gain": {
            "estimate_type": "heuristic_not_performance_prediction",
            "guaranteed": False,
            "recommendations": expected_recommendations,
            "disclaimer": (
                "Ranges are collection heuristics, not performance predictions or a promise "
                "of one video per answer."
            ),
        },
        "answer_contract": {
            "initial_answer_status": "unanswered",
            "initial_authority_state": "raw_input_pending_review",
            "first_state_after_answer": "raw_customer_input",
            "required_future_lifecycle": [
                "raw_answer",
                "fact_extraction",
                "known_unknown_or_requires_review_classification",
                "human_review",
                "persona_revision",
                "approval",
            ],
            "answer_never_becomes_known_automatically": True,
        },
        "authority_notice": {
            "artifact_purpose": "ask_for_missing_information_not_supply_answers",
            "new_persona_facts_created": False,
            "persona_writeback": False,
            "ledger_writeback": False,
            "unknown_or_requires_review_consumed_as_known": False,
            "external_research_substitution": False,
            "case_fact_transfer": False,
            "industry_common_knowledge_promoted_to_known": False,
            "remote_model_called": False,
            "script_generation_performed": False,
            "production_batch_created_or_approved": False,
            "excel_export_performed": False,
        },
        "remote_model_telemetry": {
            "calls": 0,
            "tokens": 0,
            "elapsed_seconds": 0,
        },
        "created_at": created_at or now_iso(),
        "status": "interview_ready_unanswered",
    }


def render_content_capacity_replenishment_intake_markdown(
    intake: dict[str, Any],
    *,
    business_persona: dict[str, Any],
    speaker_persona: dict[str, Any],
) -> str:
    """Render the intake as an operator-facing interview sheet without internal IDs."""
    coverage_labels = {
        "service_definition": "代炒服务的基本定义与使用方式",
        "pricing": "已经公开的加工价格",
        "taste_customization": "少盐、少辣等口味沟通能力",
        "service_process": "代炒服务的基本流程",
        "waiting_time": "已经说明的常规时间与高峰排队情况",
        "open_kitchen_visibility": "明厨亮灶与加工过程可见",
        "free_included_items": "免费油盐酱料与米饭",
        "customer_selected_ingredients": "顾客自行选择并送来食材",
        "authorized_customer_story": "已经使用过的授权顾客评价",
    }
    gap_labels = {
        "customer_questions": "真实顾客问题",
        "frontline_observations": "一线观察与判断",
        "customer_stories": "新的授权顾客故事",
        "specific_product_or_dish_cases": "具体菜品或食材案例",
        "service_boundaries": "服务边界与不能承诺的情况",
        "new_operational_facts": "真实运营动作与现场约束",
        "speaker_personal_experience": "林东方本人的工作经验",
        "business_decisions": "由运营者说明的业务决定",
        "brand_context": "由业务负责人说明的品牌背景",
    }
    role_labels = {
        "frontline_chef": "林东方（现场回答）",
        "customer": "相关顾客（由运营人员另行确认）",
        "brand_operator": "门店运营者",
        "business_owner": "业务负责人",
    }

    def known_fact_value(persona: dict[str, Any], field: str, fallback: str) -> str:
        fact = (persona.get("facts") or {}).get(field) or {}
        if fact.get("state") != "known":
            return fallback
        return str(fact.get("value") or fallback)

    business_name = known_fact_value(
        business_persona, "public_display_name", "当前业务"
    )
    speaker_name = known_fact_value(
        speaker_persona, "public_display_name", "当前讲述人"
    )
    covered = [
        coverage_labels.get(item.get("coverage_id"), str(item.get("coverage_id")))
        for item in intake.get("historical_coverage_summary") or []
    ]
    matrix = intake.get("gap_coverage_matrix") or []
    high_gaps = [
        gap_labels.get(item.get("gap_category"), str(item.get("gap_category")))
        for item in matrix
        if item.get("gap_priority") == "high"
    ]
    lines = [
        f"# {speaker_name}｜内容补充采访单",
        "",
        f"采访对象：{speaker_name}（{business_name}一线工作人员）",
        "",
        "这份工作单用于补充下一轮内容所需的真实资料。本次只记录亲历、亲见、可以核实的情况；不确定时可以直接写“不知道”或“没有遇到”。",
        "",
        "## 当前我们已经了解",
        "",
    ]
    lines.extend(f"- {label}" for label in covered)
    lines.extend(
        [
            "",
            "以上内容已经在正式内容中充分讲过，不需要重复回答。除非出现新的真实例子、新边界或新的处理动作，否则不要换一种说法再讲一遍。",
            "",
            "## 这次最希望补充",
            "",
        ]
    )
    lines.extend(f"- {label}" for label in high_gaps)
    lines.extend(
        [
            "",
            "## 推荐采访顺序",
            "",
            "先从最近真实工作开始，再问顾客真实问题、具体食材或菜品、服务边界、印象深刻的顾客，最后补本人经验或判断。",
            "",
        ]
    )
    groups = {item.get("group_id"): item for item in intake.get("question_groups") or []}

    def append_questions(title: str, group_id: str, introductory_text: str) -> None:
        lines.extend([f"## {title}", "", introductory_text, ""])
        for index, question in enumerate(
            (groups.get(group_id) or {}).get("questions") or [], start=1
        ):
            lines.extend(
                [
                    f"### {index}. {question['question_text']}",
                    "",
                    f"回答人：{role_labels.get(question['recommended_target_role'], question['recommended_target_role'])}",
                    "",
                    f"【为什么问】{question['information_objective']}",
                    "",
                ]
            )
            if question.get("reuse_authorization_required"):
                lines.extend(
                    [
                        "【公开授权确认】请分别确认称呼、场景、原话、图片、视频和评价是否允许公开；未确认的部分不要用于内容。",
                        "",
                    ]
                )
            lines.extend(["【客户回答】", "", "", ""])

    append_questions(
        "Core Interview｜核心采访",
        "core_interview",
        "建议优先完成以下问题。一个真实、具体、可核实的例子，比多个笼统判断更有价值。",
    )
    append_questions(
        "Optional Expansion｜补充追问",
        "optional_expansion",
        "当核心采访信息仍不足，或受访者确有新的真实经历时，再继续以下问题。",
    )
    lines.extend(
        [
            "## 资料使用说明",
            "",
            "本采访单中的回答只是原始客户输入，不会自动成为已批准事实。后续仍需经过事实提取、人工复核、Persona 修订与批准，才能进入内容生成。顾客故事若没有逐项确认公开复用范围，只能进入待复核状态。",
            "",
        ]
    )
    return "\n".join(lines)


def build_v1_v1_1_v1_1_1_scorecard(
    v1_plan: dict[str, Any],
    v1_1_plan: dict[str, Any],
    v1_1_1_plan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "content-quality-v1-vs-v1.1-vs-v1.1.1-scorecard-v1.0",
        "request_id": v1_1_1_plan.get("request_id"),
        "metrics": {
            "candidate_pool_size": {"v1": 30, "v1_1": 30, "v1_1_1": 30},
            "high_quality_novel_capacity": {
                "v1": v1_plan.get("capacity", {}).get("high_quality_novel_capacity"),
                "v1_1": v1_1_plan.get("capacity", {}).get("high_quality_novel_capacity"),
                "v1_1_1": v1_1_1_plan.get("capacity", {}).get("high_quality_novel_capacity"),
            },
            "novelty_surviving_capacity": {
                "v1": v1_plan.get("capacity", {}).get("high_quality_novel_capacity"),
                "v1_1": v1_1_plan.get("capacity", {}).get("novelty_surviving_capacity"),
                "v1_1_1": v1_1_1_plan.get("capacity", {}).get("novelty_surviving_capacity"),
            },
            "concept_018_decision": {
                "v1": "semantic_uncertain_review_required",
                "v1_1": "high_quality_novel",
                "v1_1_1": v1_1_1_plan.get("closure_calibration", {}).get(
                    "concept_018_final_decision"
                ),
            },
            "audience_need_source_lineage_required": {
                "v1": False,
                "v1_1": False,
                "v1_1_1": True,
            },
            "service_decision_need_without_source_refs": {
                "v1_1_1": v1_1_1_plan.get("audience_need_lineage_summary", {}).get(
                    "service_decision_need_without_source_refs"
                )
            },
            "capacity_padding": {"v1": False, "v1_1": False, "v1_1_1": False},
            "remote_model_calls_for_closure": {"v1_1_1": 0},
            "script_generation_performed": {"v1_1_1": False},
        },
        "v1_1_1_selected_concepts": [
            item.get("concept_id")
            for item in v1_1_1_plan.get("selected_concepts") or []
        ],
        "status": "review_required",
    }


def build_comparison_scorecard(
    baseline_analysis: dict[str, Any],
    content_plan: dict[str, Any],
    generation_batch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    baseline = baseline_analysis["summary"]
    selected = content_plan.get("selected_concepts") or []
    selected_claims = {
        (item.get("semantic_signature") or {}).get("central_claim_key")
        for item in selected
    }
    selected_audiences = {item.get("audience_need") for item in selected}
    selected_jobs = {item.get("content_job") for item in selected}
    selected_visuals = {item.get("visual_anchor") for item in selected}
    high_overlap = 0
    duplicate_pairs = 0
    for left_index, left in enumerate(selected):
        for right in selected[left_index + 1 :]:
            duplicate_pairs += bool(semantic_duplicate_reasons(left, right))
            high_overlap += _jaccard(
                left.get("primary_fact_refs") or [],
                right.get("primary_fact_refs") or [],
            ) >= 0.8
    editorial = content_plan.get("batch_editorial_summary") or {}
    batch_similarity = (generation_batch or {}).get("batch_similarity") or {}
    return {
        "schema_version": "content-quality-comparison-scorecard-v1.0",
        "request_ids": {
            "baseline": baseline_analysis.get("baseline_request_id"),
            "v1": content_plan.get("request_id"),
        },
        "metrics": {
            "semantic_duplicate_pairs": {"b0": baseline["semantic_duplicate_pair_count"], "v1": duplicate_pairs},
            "unique_central_claims": {"b0": baseline["unique_central_claims"], "v1": len(selected_claims)},
            "exclusive_anchor_coverage": {"b0": baseline["exclusive_anchor_coverage"], "v1": editorial.get("exclusive_anchor_coverage")},
            "customer_specific_ratio": {"b0": baseline["customer_specific_ratio"], "v1": editorial.get("customer_specific_ratio")},
            "generic_content_ratio": {"b0": baseline["generic_ratio"], "v1": editorial.get("generic_ratio")},
            "high_overlap_primary_fact_bundles": {"b0": baseline["high_overlap_primary_fact_bundle_pair_count"], "v1": high_overlap},
            "unique_audience_needs": {"b0": baseline["unique_audience_needs"], "v1": len(selected_audiences)},
            "unique_content_jobs": {"b0": baseline["unique_content_jobs"], "v1": len(selected_jobs)},
            "unique_visual_anchors": {"b0": baseline["visual_anchor_estimate"]["unique_count"], "v1": len(selected_visuals)},
            "lexical_similarity_secondary_only": {"b0": baseline["lexical_similarity_secondary_only"]["maximum"], "v1": batch_similarity.get("maximum_similarity")},
            "human_first_pass_approval": {"b0": baseline_analysis["historical_review"]["human_first_pass_approval"], "v1": None},
            "revision_rate": {"b0": baseline_analysis["historical_review"]["revision_rate"], "v1": None},
            "capacity_padding": {"b0": "historical_risk_present", "v1": bool(content_plan.get("capacity", {}).get("padding_generated"))},
        },
        "v1_human_metrics_pending": True,
    }


def verify_frozen_hashes(
    source_batch_path: Path,
    approved_batch_path: Path,
    excel_path: Path,
    expected_source_sha: str,
    expected_approved_sha: str,
    expected_excel_sha: str,
) -> dict[str, str]:
    actual = {
        "source_batch_sha256": sha256_file(source_batch_path),
        "approved_batch_sha256": sha256_file(approved_batch_path),
        "exported_excel_sha256": sha256_file(excel_path),
    }
    expected = {
        "source_batch_sha256": expected_source_sha.lower(),
        "approved_batch_sha256": expected_approved_sha.lower(),
        "exported_excel_sha256": expected_excel_sha.lower(),
    }
    if actual != expected:
        raise RuntimeError(
            "Frozen B0 artifact hash mismatch: "
            + json.dumps({"expected": expected, "actual": actual}, ensure_ascii=False)
        )
    return actual


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def write_new_text(path: Path, value: str) -> str:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def _require_cli_args(args: argparse.Namespace, names: Iterable[str]) -> None:
    missing = [name for name in names if not getattr(args, name, None)]
    if missing:
        rendered = ", ".join("--" + name.replace("_", "-") for name in missing)
        raise SystemExit(f"Missing required arguments for selected mode: {rendered}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build Content Quality V1 artifacts, including the read-only B0 backfill "
            "or the deterministic Content Capacity Replenishment Intake V1."
        )
    )
    parser.add_argument("--build-replenishment-intake", action="store_true")
    parser.add_argument("--source-batch")
    parser.add_argument("--approved-batch")
    parser.add_argument("--exported-excel")
    parser.add_argument("--export-receipt")
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-approved-sha")
    parser.add_argument("--expected-excel-sha")
    parser.add_argument("--analysis-output")
    parser.add_argument("--ledger-output")
    parser.add_argument("--business-persona")
    parser.add_argument("--business-approval")
    parser.add_argument("--speaker-persona")
    parser.add_argument("--speaker-approval")
    parser.add_argument("--content-ledger")
    parser.add_argument("--content-gap-report")
    parser.add_argument("--intake-id", default="intake_0001")
    parser.add_argument("--json-output")
    parser.add_argument("--markdown-output")
    args = parser.parse_args()

    if args.build_replenishment_intake:
        _require_cli_args(
            args,
            (
                "business_persona",
                "business_approval",
                "speaker_persona",
                "speaker_approval",
                "content_ledger",
                "content_gap_report",
                "json_output",
                "markdown_output",
            ),
        )
        business_persona_path = Path(args.business_persona).expanduser().resolve()
        business_approval_path = Path(args.business_approval).expanduser().resolve()
        speaker_persona_path = Path(args.speaker_persona).expanduser().resolve()
        speaker_approval_path = Path(args.speaker_approval).expanduser().resolve()
        ledger_path = Path(args.content_ledger).expanduser().resolve()
        gap_report_path = Path(args.content_gap_report).expanduser().resolve()
        guarded_paths = [
            business_persona_path,
            business_approval_path,
            speaker_persona_path,
            speaker_approval_path,
            ledger_path,
            gap_report_path,
        ]
        hashes_before = {str(path): sha256_file(path) for path in guarded_paths}
        business_persona, business_ref = approved_persona_ref(
            persona_path=business_persona_path,
            approval_receipt_path=business_approval_path,
            expected_scope="business",
        )
        speaker_persona, speaker_ref = approved_persona_ref(
            persona_path=speaker_persona_path,
            approval_receipt_path=speaker_approval_path,
            expected_scope="speaker",
        )
        ledger = read_json(ledger_path)
        gap_report = read_json(gap_report_path)
        gap_capacity = gap_report.get("current_high_quality_novel_capacity")
        intake = build_content_capacity_replenishment_intake_v1(
            intake_id=args.intake_id,
            business_persona=business_persona,
            business_persona_ref=business_ref,
            speaker_persona=speaker_persona,
            speaker_persona_ref=speaker_ref,
            ledger=ledger,
            ledger_ref={
                "path": str(ledger_path),
                "sha256": hashes_before[str(ledger_path)],
                "schema_version": ledger.get("schema_version"),
            },
            gap_report=gap_report,
            gap_report_ref=str(gap_report_path),
            gap_report_sha256=hashes_before[str(gap_report_path)],
        )
        markdown = render_content_capacity_replenishment_intake_markdown(
            intake,
            business_persona=business_persona,
            speaker_persona=speaker_persona,
        )
        json_sha = write_new_json(Path(args.json_output), intake)
        markdown_sha = write_new_text(Path(args.markdown_output), markdown)
        hashes_after = {str(path): sha256_file(path) for path in guarded_paths}
        if hashes_after != hashes_before:
            raise RuntimeError("An immutable Intake source artifact changed during build.")
        group_counts = {
            group["group_id"]: group["question_count"]
            for group in intake["question_groups"]
        }
        print("CONTENT CAPACITY REPLENISHMENT INTAKE V1 PASS")
        print(f"Current high-quality novel capacity: {gap_capacity}")
        print(f"Core questions: {group_counts['core_interview']}")
        print(f"Optional questions: {group_counts['optional_expansion']}")
        print("Remote model calls: 0")
        print(f"JSON SHA-256: {json_sha}")
        print(f"Markdown SHA-256: {markdown_sha}")
        print("Immutable sources unchanged: True")
        return

    _require_cli_args(
        args,
        (
            "source_batch",
            "approved_batch",
            "exported_excel",
            "expected_source_sha",
            "expected_approved_sha",
            "expected_excel_sha",
            "analysis_output",
            "ledger_output",
        ),
    )

    source_path = Path(args.source_batch).expanduser().resolve()
    approved_path = Path(args.approved_batch).expanduser().resolve()
    excel_path = Path(args.exported_excel).expanduser().resolve()
    frozen = verify_frozen_hashes(
        source_path,
        approved_path,
        excel_path,
        args.expected_source_sha,
        args.expected_approved_sha,
        args.expected_excel_sha,
    )
    approved_batch = read_json(approved_path)
    receipt = read_json(Path(args.export_receipt)) if args.export_receipt else None
    analysis = build_baseline_analysis(
        approved_batch,
        approved_batch_sha=frozen["approved_batch_sha256"],
        source_batch_sha=frozen["source_batch_sha256"],
        exported_excel_sha=frozen["exported_excel_sha256"],
        export_receipt=receipt,
    )
    ledger = build_ledger_seed(
        analysis,
        approved_batch,
        approved_batch_path=approved_path,
        export_receipt=receipt,
    )
    analysis_sha = write_new_json(Path(args.analysis_output), analysis)
    ledger_sha = write_new_json(Path(args.ledger_output), ledger)
    frozen_after = verify_frozen_hashes(
        source_path,
        approved_path,
        excel_path,
        args.expected_source_sha,
        args.expected_approved_sha,
        args.expected_excel_sha,
    )
    print("CONTENT QUALITY V1 B0 BACKFILL PASS")
    print(f"Baseline content count: {analysis['content_count']}")
    print(f"Semantic duplicate pairs: {analysis['summary']['semantic_duplicate_pair_count']}")
    print(f"Strong Ledger memory: {ledger['validation']['strong_memory_count']}")
    print(f"Analysis SHA-256: {analysis_sha}")
    print(f"Ledger SHA-256: {ledger_sha}")
    print("Frozen hashes unchanged: " + str(frozen_after == frozen))


if __name__ == "__main__":
    main()
