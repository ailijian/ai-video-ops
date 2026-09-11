from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from privacy_projection_v1 import (
    PRIVACY_POLICY_VERSION,
    assert_safe_for_external_model,
    build_egress_audit,
    project_value,
)


SCHEMA_VERSION = "generation-batch-v1.0"
GENERATOR_VERSION = "generate_mix_scripts_v1.py@0.6.4"
PROMPT_VERSION = "mix-script-generation-prompt-v1.9"
REVIEW_PACK_VERSION = "generation-review-pack-v1.2"
DEFAULT_MODEL = "deepseek-v4-flash"
SIMILARITY_POLICY = "provisional_v1_not_frozen"
MAX_SIMILARITY = 0.82
CENTRAL_CLAIM_SIMILARITY = 0.72
FACT_BUNDLE_OVERLAP = 0.80
GENERATION_FACT_FIELDS = (
    "public_display_name",
    "company_short_name",
    "industry",
    "years_in_business",
    "service_area",
    "location_public_area",
    "primary_products_or_services",
    "secondary_products_or_services",
    "core_audience",
    "customer_use_cases",
    "customer_pains",
    "differentiators",
    "selection_reasons",
    "brand_story",
    "founder_or_operator_story",
    "important_turning_points",
    "product_or_service_facts",
    "pricing_facts",
    "included_service_facts",
    "process_facts",
    "service_process",
    "service_time_facts",
    "business_volume_fact",
    "time_efficiency_fact",
    "authorized_customer_cases_or_feedback",
    "values",
    "business_principles",
    "beliefs",
    "tone_preferences",
)
GUARDRAIL_FACT_FIELDS = (
    "unknown_facts",
    "forbidden_claims",
    "prohibited_topics",
)
SPEAKER_GENERATION_FACT_FIELDS = (
    "public_display_name",
    "public_role",
    "speaker_role_facts",
    "first_person_allowed_topics",
)
SPEAKER_GUARDRAIL_FACT_FIELDS = (
    "unknown_facts",
    "first_person_forbidden_claims",
    "role_scope_constraints",
)
NEVER_EGRESS_FACT_FIELDS = {
    "business_address",
    "information_requiring_human_review",
}
STRONG_PROOF_TERMS = (
    "证明",
    "证实",
    "数据表明",
    "结果表明",
    "事实证明",
    "客户都说",
)
UNSUPPORTED_ASSERTION_TERMS = (
    "第一",
    "最好",
    "绝对",
    "百分百",
    "保证",
    "承诺",
    "所有客户",
    "客户都",
    "复购率",
    "销量",
    "销售额",
    "排名",
    "好评率",
    "资质认证",
    "一定会",
)
CLAIM_REVIEW_TERMS = (
    "往往是",
    "都是因为",
    "才是关键",
    "一定",
    "最重要",
    "比什么都重要",
    "保证",
    "必然",
    "大多数客户",
    "客户都",
)
CLAIM_SUPPORT_RISK_TERMS = (
    "很多人",
    "更常见",
    "往往",
    "才是关键",
    "更省心",
    "很多做法",
    "我经常看到",
    "我常在",
    "我参与",
    "看得多了",
    "一定",
    "最重要",
)
GROUNDING_PATTERNS = (
    (
        "empirical_frequency_claim",
        r"很多人|不少(?:人|企业|客户)|有人会|有人以为|有些人|大多数|更常见|往往|通常|常常|很多同行|很多做法|看得多了|我经常|我常|(?:客户|企业客户)会(?:提到|遇到)",
    ),
    (
        "causal_effect_claim",
        r"导致|让[^。！？!?\n]{0,16}更稳定|使[^。！？!?\n]{0,16}更稳定|(?:和|与)[^。！？!?\n]{1,20}(?:有关|相关)|更省心|容易[^。！？!?\n]{0,12}",
    ),
    (
        "comparative_or_key_claim",
        r"才是关键|最重要|效果更好|不是[^。！？!?\n]{1,30}而是[^。！？!?\n]{1,30}|比[^。！？!?\n]{1,20}更[^。！？!?\n]{1,20}",
    ),
    (
        "service_bundle_expansion",
        r"(?:绿植)?租赁(?:套餐)?(?:包含|包括|就是|等于|自带|必然)[^。！？!?\n]{0,24}养护|租的是[^。！？!?\n]{0,24}养护|租赁[^。！？!?\n]{0,16}养护[^。！？!?\n]{0,8}一起",
    ),
    (
        "assumed_customer_behavior",
        r"反复调整[^。！？!?\n]{0,20}|与其[^。！？!?\n]{1,30}(?:不如|可以)",
    ),
)
SERVICE_PROCESS_TERMS = (
    "了解需求",
    "现场勘测",
    "确认方案",
    "制定方案",
    "实施布置",
    "绿植布置",
    "定期养护",
    "持续养护",
    "上门养护",
)
ANGLE_SPECS = (
    {
        "primary_angle": "pain",
        "primary_candidates": ("customer_pains",),
        "secondary_candidates": ("differentiators", "customer_use_cases"),
        "opening_strategy": "pain_led_question",
        "narrative_mode": "single_problem_explanation",
    },
    {
        "primary_angle": "misconception",
        "primary_candidates": ("customer_pains", "differentiators"),
        "secondary_candidates": ("primary_products_or_services",),
        "opening_strategy": "misconception_correction",
        "narrative_mode": "contrast_without_absolute_claim",
    },
    {
        "primary_angle": "selection_criteria",
        "primary_candidates": ("selection_reasons", "differentiators"),
        "secondary_candidates": ("customer_pains",),
        "opening_strategy": "selection_question",
        "narrative_mode": "criteria_explanation",
    },
    {
        "primary_angle": "process",
        "primary_candidates": ("process_facts", "service_process"),
        "secondary_candidates": ("primary_products_or_services",),
        "opening_strategy": "process_entry",
        "narrative_mode": "focused_process_walkthrough",
    },
    {
        "primary_angle": "differentiator",
        "primary_candidates": ("differentiators",),
        "secondary_candidates": ("selection_reasons", "customer_pains"),
        "opening_strategy": "difference_first",
        "narrative_mode": "one_difference_explained",
    },
    {
        "primary_angle": "service_philosophy",
        "primary_candidates": ("values", "beliefs"),
        "secondary_candidates": ("differentiators",),
        "opening_strategy": "principle_statement",
        "narrative_mode": "operator_principle",
    },
    {
        "primary_angle": "customer_question",
        "primary_candidates": ("customer_pains", "customer_use_cases"),
        "secondary_candidates": ("primary_products_or_services",),
        "opening_strategy": "customer_question",
        "narrative_mode": "question_and_bounded_answer",
    },
    {
        "primary_angle": "operator_viewpoint",
        "primary_candidates": ("values", "founder_or_operator_story"),
        "secondary_candidates": ("differentiators",),
        "opening_strategy": "operator_observation",
        "narrative_mode": "first_person_viewpoint",
    },
    {
        "primary_angle": "use_case",
        "primary_candidates": ("customer_use_cases", "core_audience"),
        "secondary_candidates": ("primary_products_or_services", "customer_pains"),
        "opening_strategy": "specific_situation",
        "narrative_mode": "use_case_focus",
    },
    {
        "primary_angle": "product_or_service",
        "primary_candidates": (
            "primary_products_or_services",
            "product_or_service_facts",
        ),
        "secondary_candidates": ("core_audience",),
        "opening_strategy": "service_definition",
        "narrative_mode": "single_service_explanation",
    },
    {
        "primary_angle": "trust",
        "primary_candidates": (
            "selection_reasons",
            "process_facts",
            "differentiators",
        ),
        "secondary_candidates": ("values",),
        "opening_strategy": "trust_question",
        "narrative_mode": "traceable_fact_explanation",
    },
    {
        "primary_angle": "story",
        "primary_candidates": (
            "brand_story",
            "founder_or_operator_story",
            "important_turning_points",
        ),
        "secondary_candidates": ("values",),
        "opening_strategy": "story_moment",
        "narrative_mode": "bounded_known_story",
    },
)
FRONTLINE_EXPERT_ANGLE_SPECS = (
    {
        "primary_angle": "service_explanation",
        "primary_candidates": ("primary_products_or_services",),
        "secondary_candidates": ("included_service_facts",),
        "speaker_candidates": ("speaker_role_facts",),
        "opening_strategy": "service_definition_question",
        "narrative_mode": "frontline_service_explanation",
    },
    {
        "primary_angle": "use_case",
        "primary_candidates": ("customer_use_cases",),
        "secondary_candidates": ("primary_products_or_services",),
        "speaker_candidates": ("first_person_allowed_topics",),
        "opening_strategy": "specific_market_purchase_situation",
        "narrative_mode": "single_use_case",
    },
    {
        "primary_angle": "price_explanation",
        "primary_candidates": ("pricing_facts",),
        "secondary_candidates": ("product_or_service_facts",),
        "speaker_candidates": ("first_person_allowed_topics",),
        "opening_strategy": "price_question",
        "narrative_mode": "qualified_price_explanation",
    },
    {
        "primary_angle": "customization",
        "primary_candidates": ("product_or_service_facts", "differentiators"),
        "secondary_candidates": ("customer_pains",),
        "speaker_candidates": ("speaker_role_facts",),
        "opening_strategy": "taste_preference_question",
        "narrative_mode": "bounded_customization_explanation",
    },
    {
        "primary_angle": "process",
        "primary_candidates": ("service_process",),
        "secondary_candidates": ("process_facts",),
        "speaker_candidates": ("speaker_role_facts",),
        "opening_strategy": "ingredients_arrive_at_window",
        "narrative_mode": "focused_process_walkthrough",
    },
    {
        "primary_angle": "service_time",
        "primary_candidates": ("service_time_facts",),
        "secondary_candidates": ("time_efficiency_fact",),
        "speaker_candidates": ("first_person_allowed_topics",),
        "opening_strategy": "waiting_time_question",
        "narrative_mode": "qualified_time_explanation",
    },
    {
        "primary_angle": "convenience",
        "primary_candidates": ("customer_pains",),
        "secondary_candidates": ("customer_use_cases",),
        "speaker_candidates": (),
        "opening_strategy": "bounded_convenience_question",
        "narrative_mode": "single_convenience_point",
    },
    {
        "primary_angle": "frontline_viewpoint",
        "primary_candidates": ("service_process",),
        "secondary_candidates": ("differentiators",),
        "speaker_candidates": ("speaker_role_facts", "first_person_allowed_topics"),
        "opening_strategy": "first_person_window_view",
        "narrative_mode": "authorized_frontline_first_person",
    },
    {
        "primary_angle": "customer_story",
        "primary_candidates": ("authorized_customer_cases_or_feedback",),
        "secondary_candidates": ("customer_use_cases",),
        "speaker_candidates": (),
        "opening_strategy": "authorized_quote",
        "narrative_mode": "quote_with_provenance",
    },
    {
        "primary_angle": "service_detail",
        "primary_candidates": ("included_service_facts",),
        "secondary_candidates": ("product_or_service_facts",),
        "speaker_candidates": ("first_person_allowed_topics",),
        "opening_strategy": "included_service_detail",
        "narrative_mode": "one_service_detail",
    },
)


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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(payload)


def get_client() -> OpenAI:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is required. Interactive secret prompts are disabled "
            "for deterministic production runs."
        )
    return OpenAI(
        api_key=key,
        base_url="https://api.deepseek.com",
        timeout=180.0,
        max_retries=0,
    )


def usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
        "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
    }


def is_known(persona: dict[str, Any], field: str) -> bool:
    fact = persona.get("facts", {}).get(field, {})
    value = fact.get("value")
    return fact.get("state") == "known" and value not in (None, "", [], {})


def safe_persona_projection(
    persona: dict[str, Any],
    fact_fields: tuple[str, ...] = GENERATION_FACT_FIELDS,
    guardrail_fields: tuple[str, ...] = GUARDRAIL_FACT_FIELDS,
) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for field in fact_fields:
        if field in NEVER_EGRESS_FACT_FIELDS or not is_known(persona, field):
            continue
        facts[field] = project_value(
            persona["facts"][field]["value"], "safe_verbatim"
        )
    guardrails = {
        field: project_value(persona["facts"][field]["value"], "safe_verbatim")
        for field in guardrail_fields
        if is_known(persona, field)
    }
    projection = {
        "facts": facts,
        "guardrails": guardrails,
        "omitted_private_or_review_fields": sorted(NEVER_EGRESS_FACT_FIELDS),
        "fact_authority": "known_only",
    }
    assert_safe_for_external_model(
        json.dumps(projection, ensure_ascii=False, sort_keys=True)
    )
    return projection


def safe_speaker_projection(persona: dict[str, Any]) -> dict[str, Any]:
    projection = safe_persona_projection(
        persona,
        SPEAKER_GENERATION_FACT_FIELDS,
        SPEAKER_GUARDRAIL_FACT_FIELDS,
    )
    projection.update(
        {
            "persona_id": persona.get("persona_id"),
            "speaker_type": persona.get("speaker_type"),
            "business_persona_id": persona.get("business_persona_ref", {}).get(
                "persona_id"
            ),
            "authority": "first_person_only_with_speaker_known_fact_or_allowed_topic",
        }
    )
    return projection


def structural_fingerprint_projection(
    fingerprint: dict[str, Any], surrogate_ref: str
) -> dict[str, Any]:
    narration = fingerprint.get("narration_features", {})
    visual = fingerprint.get("visual_shot_features", {})
    structure = fingerprint.get("structure_features", {})
    audio_visual = fingerprint.get("audio_visual_features", {})
    return {
        "structural_ref": surrogate_ref,
        "narration": {
            "segment_count": narration.get("segment_count"),
            "speech_to_video_ratio": narration.get("speech_to_video_ratio"),
            "segment_duration_stats": narration.get("segment_duration_stats", {}),
        },
        "visual_rhythm": {
            "shot_count": visual.get("shot_count"),
            "shot_duration_stats": visual.get("shot_duration_stats", {}),
            "shots_under_1s_ratio": visual.get("shots_under_1s_ratio"),
            "primary_role_sequence": visual.get("primary_role_sequence", []),
            "primary_role_counts": visual.get("primary_role_counts", {}),
            "secondary_role_counts": visual.get("secondary_role_counts", {}),
            "onscreen_text_shot_ratio": visual.get("onscreen_text_shot_ratio"),
        },
        "narrative_structure": {
            "structure_signature": structure.get("structure_signature"),
            "stage_sequence": [
                item.get("stage")
                for item in structure.get("structure_sequence", [])
                if item.get("stage")
            ],
            "hook_modalities": structure.get("hook_modalities", []),
        },
        "audio_visual_relation": {
            "text_relation_counts": audio_visual.get("text_relation_counts", {}),
            "scene_relation_counts": audio_visual.get("scene_relation_counts", {}),
            "shot_to_narration_cardinality": audio_visual.get(
                "shot_to_narration_cardinality"
            ),
        },
        "forbidden_case_payloads_omitted": [
            "claims",
            "content_goal_candidate",
            "hook_candidate_text",
            "structure_descriptions",
            "source_narration",
            "source_ocr",
            "creator_or_business_name",
        ],
    }


def validate_generation_inputs(
    persona_path: Path,
    request_path: Path,
    source_plan_path: Path,
    pattern_path: Path,
    fingerprint_paths: list[Path],
    speaker_persona_path: Path | None = None,
) -> dict[str, Any]:
    resolved = {
        "persona": persona_path.expanduser().resolve(),
        "request": request_path.expanduser().resolve(),
        "source_plan": source_plan_path.expanduser().resolve(),
        "pattern": pattern_path.expanduser().resolve(),
    }
    for path in resolved.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    persona = read_json(resolved["persona"])
    request = read_json(resolved["request"])
    source_plan = read_json(resolved["source_plan"])
    pattern = read_json(resolved["pattern"])
    lifecycle = persona.get("lifecycle", {})
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        raise RuntimeError("Mix Generation requires an Approved Persona.")
    if persona.get("persona_scope", "business") != "business":
        raise RuntimeError("Mix Generation --persona must be a Business Persona.")
    speaker_persona: dict[str, Any] | None = None
    if speaker_persona_path is not None:
        speaker_path = speaker_persona_path.expanduser().resolve()
        if not speaker_path.is_file():
            raise FileNotFoundError(speaker_path)
        speaker_persona = read_json(speaker_path)
        speaker_lifecycle = speaker_persona.get("lifecycle", {})
        if (
            speaker_persona.get("persona_scope") != "speaker"
            or speaker_lifecycle.get("status") != "approved"
            or speaker_lifecycle.get("approved") is not True
        ):
            raise RuntimeError("Mix Generation requires an Approved Speaker Persona.")
        requested_speaker = request.get("speaker_persona")
        if requested_speaker != speaker_persona.get("persona_id"):
            raise RuntimeError("Generation Request Speaker Persona mismatch.")
        if int(request.get("speaker_persona_revision") or 0) != int(
            speaker_persona.get("revision") or 0
        ):
            raise RuntimeError("Generation Request Speaker revision mismatch.")
        reference = speaker_persona.get("business_persona_ref") or {}
        if (
            reference.get("persona_id") != persona.get("persona_id")
            or int(reference.get("revision") or 0) != int(persona.get("revision") or 0)
            or reference.get("sha256") != sha256_file(resolved["persona"])
        ):
            raise RuntimeError("Speaker Persona Business Persona lineage mismatch.")
        plan_speaker = source_plan.get("speaker_persona") or {}
        if plan_speaker.get("speaker_sha") != sha256_file(speaker_path):
            raise RuntimeError("Generation Source Plan Speaker Persona SHA mismatch.")
        resolved["speaker_persona"] = speaker_path
    elif request.get("speaker_persona"):
        raise RuntimeError("Generation Request requires --speaker-persona.")
    if request.get("profile") != "mix":
        raise RuntimeError("Mix Generator rejects non-mix Generation Requests.")
    if request.get("constraints", {}).get("generation_must_not_start") is True:
        raise RuntimeError("Generation Request explicitly forbids generation.")
    if source_plan.get("coverage", {}).get("status") != "supported":
        raise RuntimeError("Generation Source Plan coverage is not supported.")
    if source_plan.get("request_id") != request.get("request_id"):
        raise RuntimeError("Generation Source Plan request_id mismatch.")
    if source_plan.get("persona", {}).get("persona_sha") != sha256_file(
        resolved["persona"]
    ):
        raise RuntimeError("Generation Source Plan Persona SHA mismatch.")
    if source_plan.get("request", {}).get("request_sha") != sha256_file(
        resolved["request"]
    ):
        raise RuntimeError("Generation Source Plan Request SHA mismatch.")
    if pattern.get("status") != "approved":
        raise RuntimeError("Mix Generation requires an Approved Pattern.")
    if pattern.get("effectiveness", {}).get("status") != "unvalidated":
        raise RuntimeError("Unexpected Pattern effectiveness authority.")
    selected_patterns = source_plan.get("selected_patterns", [])
    if len(selected_patterns) != 1:
        raise RuntimeError("Source Plan must select exactly one V1 Pattern.")
    selected_pattern = selected_patterns[0]
    if selected_pattern.get("pattern_id") != pattern.get("pattern_id"):
        raise RuntimeError("Selected Pattern ID mismatch.")
    if selected_pattern.get("approved_pattern_sha") != sha256_file(
        resolved["pattern"]
    ):
        raise RuntimeError("Selected Pattern SHA mismatch.")
    if any(
        item.get("source_type") in {"pattern_candidate", "research_hypothesis"}
        and item.get("source_id") == pattern.get("pattern_id")
        for item in source_plan.get("excluded_sources", [])
    ):
        raise RuntimeError("Rejected or research-only source cannot be selected.")

    pool = source_plan.get("eligible_case_pool", [])
    if not pool:
        raise RuntimeError("Source Plan has no eligible Case pool.")
    expected_by_hash = {
        str(item.get("fingerprint_sha")): item for item in pool
    }
    fingerprint_records: dict[str, dict[str, Any]] = {}
    for index, raw_path in enumerate(fingerprint_paths, start=1):
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256_file(path)
        if digest not in expected_by_hash:
            raise RuntimeError("Fingerprint is not in the Source Plan eligible Case pool.")
        fingerprint = read_json(path)
        case_id = str(fingerprint.get("case_id") or "")
        if expected_by_hash[digest].get("case_id") != case_id:
            raise RuntimeError("Fingerprint Case ID does not match Source Plan lineage.")
        fingerprint_records[case_id] = {
            "path": str(path),
            "sha256": digest,
            "surrogate_ref": f"CASE_REF_{index:03d}",
            "projection": structural_fingerprint_projection(
                fingerprint, f"CASE_REF_{index:03d}"
            ),
        }
    if set(fingerprint_records) != {
        str(item.get("case_id")) for item in pool
    }:
        raise RuntimeError("Every eligible Case requires one Fingerprint input.")
    return {
        "paths": resolved,
        "persona": persona,
        "request": request,
        "source_plan": source_plan,
        "pattern": pattern,
        "speaker_persona": speaker_persona,
        "fingerprints": fingerprint_records,
    }


def build_content_angle_plan(context: dict[str, Any]) -> dict[str, Any]:
    request = context["request"]
    rotation = context["source_plan"].get("rotation", {}).get(
        "case_rotation_order", []
    )
    if not rotation:
        rotation = [
            item["case_id"]
            for item in context["source_plan"].get("eligible_case_pool", [])
        ]
    requested_quantity = int(request.get("quantity") or 0)
    speaker = context.get("speaker_persona")
    specs = (
        FRONTLINE_EXPERT_ANGLE_SPECS
        if speaker and speaker.get("speaker_type") == "frontline_expert"
        else ANGLE_SPECS
    )
    supported: list[dict[str, Any]] = []
    for spec in specs:
        primary_refs = [
            field
            for field in spec["primary_candidates"]
            if is_known(context["persona"], field)
        ]
        if not primary_refs:
            continue
        secondary_refs = [
            field
            for field in spec["secondary_candidates"]
            if is_known(context["persona"], field) and field not in primary_refs
        ][:2]
        speaker_refs = [
            field
            for field in spec.get("speaker_candidates", ())
            if speaker and is_known(speaker, field)
        ][:2]
        supported.append(
            {
                "primary_angle": spec["primary_angle"],
                "primary_persona_fact_refs": primary_refs[:2],
                "optional_secondary_fact_refs": secondary_refs,
                "speaker_fact_refs": speaker_refs,
                "opening_strategy": spec["opening_strategy"],
                "narrative_mode": spec["narrative_mode"],
            }
        )
    capacity = len(supported)
    planned_quantity = min(requested_quantity, capacity)
    slots: list[dict[str, Any]] = []
    for index, angle in enumerate(supported[:planned_quantity], start=1):
        case_id = str(rotation[(index - 1) % len(rotation)])
        slots.append(
            {
                "slot_id": f"SLOT_{index:03d}",
                "case_id": case_id,
                **angle,
                "selected_case_structural_reference": context["fingerprints"][
                    case_id
                ]["surrogate_ref"],
            }
        )
    status = "supported" if capacity >= requested_quantity else "diversity_capacity_limited"
    return {
        "planning_version": "content-angle-plan-v0.2",
        "taxonomy_status": SIMILARITY_POLICY,
        "requested_quantity": requested_quantity,
        "high_confidence_distinct_capacity": capacity,
        "planned_quantity": planned_quantity,
        "status": status,
        "reason": (
            "distinct supported angle capacity meets request"
            if status == "supported"
            else "KNOWN Fact coverage and Approved Pattern scope support fewer distinct angles than requested"
        ),
        "slots": slots,
    }


def generation_slots(context: dict[str, Any]) -> list[dict[str, Any]]:
    return build_content_angle_plan(context)["slots"]


def output_schema_example() -> dict[str, Any]:
    return {
        "items": [
            {
                "slot_id": "SLOT_001",
                "central_claim": "one bounded candidate claim",
                "title": "Chinese title",
                "narration": "Chinese narration",
                "persona_fact_refs_used": ["known_fact_field"],
                "speaker_fact_refs_used": ["known_speaker_fact_field"],
                "claim_candidates": [
                    {
                        "text": "candidate claim",
                        "persona_fact_refs": ["known_fact_field"],
                        "speaker_fact_refs": ["known_speaker_fact_field"],
                    }
                ],
                "customer_feedback_provenance": [
                    {
                        "fact_ref": "authorized_customer_cases_or_feedback",
                        "quote": "exact authorized quote",
                    }
                ],
                "cta": {"present": False, "text": None},
            }
        ]
    }


def render_generation_prompt(
    safe_input: dict[str, Any],
    remaining_slots: list[dict[str, Any]],
    avoid_titles: list[str],
) -> str:
    prompt_context = {
        "persona": safe_input["persona"],
        "speaker": safe_input.get("speaker"),
        "request": safe_input["request"],
        "approved_pattern": safe_input["approved_pattern"],
        "slots": [
            {
                "slot_id": slot["slot_id"],
                "primary_angle": slot.get("primary_angle"),
                "primary_persona_fact_refs": slot.get(
                    "primary_persona_fact_refs", []
                ),
                "optional_secondary_fact_refs": slot.get(
                    "optional_secondary_fact_refs", []
                ),
                "speaker_fact_refs": slot.get("speaker_fact_refs", []),
                "opening_strategy": slot.get("opening_strategy"),
                "narrative_mode": slot.get("narrative_mode"),
                "selected_case_structural_reference": slot.get(
                    "selected_case_structural_reference"
                ),
                "case_structure": safe_input["case_structures"][slot["case_id"]],
            }
            for slot in remaining_slots
        ],
        "avoid_existing_titles": avoid_titles,
    }
    return (
        "You generate Chinese short-video Mix scripts as JSON only.\n"
        "Use only KNOWN Persona facts in the supplied safe Persona projection. "
        "Never invent years, numbers, prices, locations, customer counts, repeat rates, "
        "rankings, qualifications, customer feedback, outcomes, guarantees, or effects.\n"
        "Case structures are abstract references only. Never infer or copy any source "
        "Case client fact, narration, OCR, name, city, product, or claim.\n"
        "Apply the Approved Pattern as a flexible structural constraint, not a fixed "
        "sentence template. Narration is the semantic spine; real process scenes may "
        "reinforce, supplement, or contextualize it.\n"
        "Process is not proof. Do not use strong proof, superlative, absolute, guaranteed, "
        "performance, or universal-customer language.\n"
        "Follow each Content Angle Slot. Build one primary point only, and use the "
        "slot's primary Persona fact refs as its factual center. Optional secondary facts "
        "may supplement but must not replace the primary angle. Do not repeat the full "
        "service-process sequence outside the dedicated process slot. Return a concise "
        "central_claim for deterministic diversity review.\n"
        "Make every title, opening, central claim, and ending materially distinct. Write "
        "natural Chinese. Keep each narration concise enough for a short video.\n"
        "persona_fact_refs_used and each claim persona_fact_refs must contain exact field "
        "names from persona.facts. Do not cite guardrail fields as content facts.\n"
        "CTA follows request.cta_intent. Never add phone, address, account, or strong sales "
        "language.\n"
        "Distinguish Persona-specific facts, low-risk framing, and empirical/causal/"
        "comparative claims. Low-risk questions and transitions may be freely phrased. "
        "Customer facts require KNOWN support. Frequency, causality, comparison, operator "
        "experience, outcomes, and service-bundle claims must be neutralized when the "
        "Persona does not directly support them.\n"
        "When a Speaker overlay is supplied, Business Persona facts remain Business "
        "authority and Speaker facts control who is speaking and what may be said in first "
        "person. A frontline_expert must not claim founder, owner, business-decision, rent-"
        "policy, business-volume, career-length, or industry-authority experience unless an "
        "explicit Speaker KNOWN fact permits it. Do not copy Business facts into Speaker facts.\n"
        "Preserve every price range and qualifier such as 通常, 多在, 约, and 左右. Preserve "
        "time qualifiers and queue limitations; never convert them into no-wait or universal "
        "time guarantees. Authorized customer feedback may only be quoted exactly with "
        "customer_feedback_provenance. Never use requires-review material.\n"
        "Return one item for every requested slot_id and no extra items.\n\n"
        "OUTPUT SCHEMA:\n"
        + json.dumps(output_schema_example(), ensure_ascii=False, indent=2)
        + "\n\nSAFE GENERATION CONTEXT:\n"
        + json.dumps(prompt_context, ensure_ascii=False, indent=2)
    )


def prepare_generation_egress(
    context: dict[str, Any],
    remaining_slots: list[dict[str, Any]],
    avoid_titles: list[str],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    persona_projection = safe_persona_projection(context["persona"])
    speaker_projection = (
        safe_speaker_projection(context["speaker_persona"])
        if context.get("speaker_persona")
        else None
    )
    request_projection = project_value(
        {
            "profile": context["request"].get("profile"),
            "platform": context["request"].get("platform"),
            "content_intent": context["request"].get("content_intent"),
            "cta_intent": context["request"].get("cta_intent"),
            "constraints": context["request"].get("constraints", {}),
        },
        "safe_verbatim",
    )
    pattern_projection = project_value(
        {
            "working_name": context["pattern"].get("working_name"),
            "definition": context["pattern"].get("definition", {}),
            "scope_limit": context["pattern"].get("scope", {}).get(
                "current_generalization_limit"
            ),
            "effectiveness": "unvalidated",
        },
        "safe_verbatim",
    )
    case_structures = {
        case_id: project_value(record["projection"], "safe_semantic")
        for case_id, record in context["fingerprints"].items()
    }
    safe_input = {
        "persona": persona_projection,
        "speaker": speaker_projection,
        "request": request_projection,
        "approved_pattern": pattern_projection,
        "case_structures": case_structures,
    }
    prompt = render_generation_prompt(safe_input, remaining_slots, avoid_titles)
    runtime_projection_sha = canonical_sha256(
        {"business_persona": persona_projection, "speaker_persona": speaker_projection}
    )
    audit = build_egress_audit(
        safe_input=safe_input,
        rendered_prompt=prompt,
        privacy_context={"privacy_projection_sha256": runtime_projection_sha},
    )
    audit["projection_scope"] = "runtime_approved_persona_known_facts"
    audit["runtime_persona_projection_sha256"] = runtime_projection_sha
    return safe_input, prompt, audit


def render_revision_prompt(
    safe_input: dict[str, Any],
    revision_slots: list[dict[str, Any]],
    avoid_titles: list[str],
) -> str:
    prompt_context = {
        "persona": safe_input["persona"],
        "speaker": safe_input.get("speaker"),
        "request": safe_input["request"],
        "approved_pattern": safe_input["approved_pattern"],
        "revision_slots": [
            {
                "slot_id": slot["slot_id"],
                "primary_angle": slot["primary_angle"],
                "primary_persona_fact_refs": slot["primary_persona_fact_refs"],
                "optional_secondary_fact_refs": slot[
                    "optional_secondary_fact_refs"
                ],
                "opening_strategy": slot["opening_strategy"],
                "narrative_mode": slot["narrative_mode"],
                "selected_case_structural_reference": slot[
                    "selected_case_structural_reference"
                ],
                "case_structure": safe_input["case_structures"][slot["case_id"]],
                "original_generated_item": slot["original_generated_item"],
                "human_revision_instructions": slot["revision_instructions"],
                "deterministic_slot_constraints": (
                    [
                        "State each approved pain and service fact independently.",
                        "Do not claim or imply that one pain causes, explains, relates to, or is solved by another fact.",
                        "Do not add population frequency or assumed customer behavior.",
                        "A safe structure is a non-empirical question followed by separate direct KNOWN fact statements.",
                    ]
                    if slot["primary_angle"] == "pain"
                    else [
                        "Express the misconception as a non-empirical question, not as a belief held by people, customers, or enterprises.",
                        "Answer with direct KNOWN service facts only.",
                        "Do not use 有人以为, 很多人觉得, 客户认为, or equivalent population claims.",
                    ]
                    if slot["primary_angle"] == "misconception"
                    else []
                ),
            }
            for slot in revision_slots
        ],
        "approved_carried_forward_titles_to_avoid": avoid_titles,
    }
    return (
        "You revise only the supplied Chinese Mix-script slots and return JSON only.\n"
        "Preserve every slot_id, primary_angle, Approved Pattern constraint, Persona "
        "authority, and Case structural reference. Do not create or re-plan angles.\n"
        "Apply each human_revision_instructions literally and conservatively. Use only "
        "KNOWN Persona facts from the safe projection. Never transfer Case facts.\n"
        "Grounding classes:\n"
        "A. Persona-specific facts about services, experience, products, processes, "
        "values, or results require direct KNOWN Persona support.\n"
        "B. Low-risk framing such as questions, transitions, and non-empirical openings "
        "may be freely phrased without pretending to be a customer fact.\n"
        "C. Empirical, causal, comparative, frequency, operator-experience, outcome, "
        "or service-bundle claims require direct KNOWN support. If support is absent, "
        "replace them with a neutral description, a genuine question, or an existing "
        "customer service fact.\n"
        "Do not assert many people, most people, common frequency, often, more common, "
        "someone thinks, customers mention or encounter, some people or enterprises, "
        "often/usually language, unsupported related-to "
        "causality, assumed customer behavior, industry practice, "
        "repeated operator observation, key causality, greater ease, "
        "better effects, X-not-Y contrasts, or that separate services form one bundle "
        "unless the Persona facts explicitly say so.\n"
        "Softening words such as 可能, 也许, or 或许 do not make an unsupported causal "
        "claim acceptable. Never connect two independently KNOWN facts with 原因, 因为, "
        "导致, 有关, 相关, 所以, 回应痛点, or 解决 unless that exact relationship is a "
        "KNOWN Persona fact. Present independent facts in separate neutral sentences.\n"
        "Keep one primary point per script. Do not repeat the full service process outside "
        "the process slot. Process is not proof. Avoid guarantees and unsupported effects.\n"
        "persona_fact_refs_used and claim refs must use exact KNOWN fact field names.\n"
        "Return one item for every requested revision slot and no other slots.\n\n"
        "OUTPUT SCHEMA:\n"
        + json.dumps(output_schema_example(), ensure_ascii=False, indent=2)
        + "\n\nSAFE SELECTIVE REVISION CONTEXT:\n"
        + json.dumps(prompt_context, ensure_ascii=False, indent=2)
    )


def prepare_revision_egress(
    context: dict[str, Any],
    revision_slots: list[dict[str, Any]],
    avoid_titles: list[str],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    persona_projection = safe_persona_projection(context["persona"])
    speaker_projection = (
        safe_speaker_projection(context["speaker_persona"])
        if context.get("speaker_persona")
        else None
    )
    safe_input = {
        "persona": persona_projection,
        "speaker": speaker_projection,
        "request": project_value(
            {
                "profile": context["request"].get("profile"),
                "platform": context["request"].get("platform"),
                "content_intent": context["request"].get("content_intent"),
                "cta_intent": context["request"].get("cta_intent"),
                "constraints": context["request"].get("constraints", {}),
            },
            "safe_verbatim",
        ),
        "approved_pattern": project_value(
            {
                "working_name": context["pattern"].get("working_name"),
                "definition": context["pattern"].get("definition", {}),
                "scope_limit": context["pattern"].get("scope", {}).get(
                    "current_generalization_limit"
                ),
                "effectiveness": "unvalidated",
            },
            "safe_verbatim",
        ),
        "case_structures": {
            case_id: project_value(record["projection"], "safe_semantic")
            for case_id, record in context["fingerprints"].items()
        },
    }
    prompt = render_revision_prompt(safe_input, revision_slots, avoid_titles)
    runtime_projection_sha = canonical_sha256(
        {"business_persona": persona_projection, "speaker_persona": speaker_projection}
    )
    audit = build_egress_audit(
        safe_input=safe_input,
        rendered_prompt=prompt,
        privacy_context={"privacy_projection_sha256": runtime_projection_sha},
    )
    audit["projection_scope"] = "runtime_approved_persona_known_facts_selective_revision"
    audit["runtime_persona_projection_sha256"] = runtime_projection_sha
    return safe_input, prompt, audit


def invoke_generation_transport(
    *,
    safe_input: dict[str, Any],
    rendered_prompt: str,
    pre_call_audit: dict[str, Any],
    transport: Callable[[str], dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    assert_safe_for_external_model(rendered_prompt)
    result = transport(rendered_prompt)
    post_call_audit = build_egress_audit(
        safe_input=safe_input,
        rendered_prompt=rendered_prompt,
        privacy_context={
            "privacy_projection_sha256": pre_call_audit.get(
                "runtime_persona_projection_sha256"
            )
        },
    )
    comparable_keys = (
        "privacy_state",
        "privacy_policy_version",
        "privacy_projection_sha256",
        "safe_input_sha256",
        "rendered_prompt_sha256",
    )
    if any(
        post_call_audit.get(key) != pre_call_audit.get(key)
        for key in comparable_keys
    ):
        raise RuntimeError("Generation pre-call and post-call Egress Audits differ.")
    return result, post_call_audit


def default_transport(model: str) -> Callable[[str], dict[str, Any]]:
    client: OpenAI | None = None

    def call(prompt: str) -> dict[str, Any]:
        nonlocal client
        if client is None:
            client = get_client()
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=10000,
            extra_body={"thinking": {"type": "disabled"}},
        )
        elapsed = time.perf_counter() - started
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("Remote Model returned empty content.")
        return {
            "payload": json.loads(content),
            "response_sha256": sha256_text(content),
            "usage": usage_dict(response),
            "elapsed_seconds": round(elapsed, 6),
        }

    return call


def normalize_text(value: str) -> str:
    return "".join(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", value.lower()))


def text_similarity(left: str, right: str) -> float:
    return round(
        difflib.SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio(),
        6,
    )


def flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(flatten_strings(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(flatten_strings(item))
        return values
    return [str(value)] if value is not None else []


def extract_service_process_sequence(value: str) -> list[str]:
    positions = [
        (value.find(term), term) for term in SERVICE_PROCESS_TERMS if term in value
    ]
    return [term for _position, term in sorted(positions)]


def detect_grounding_risks(
    value: str,
    fact_refs: list[str],
    safe_persona: dict[str, Any],
) -> list[str]:
    referenced_fact_text = "\n".join(
        text
        for ref in fact_refs
        if ref in safe_persona.get("facts", {})
        for text in flatten_strings(safe_persona["facts"][ref])
    )
    flags: list[str] = []
    for sentence in re.findall(r"[^。！？!?\n]+[。！？!?]?", value):
        stripped = sentence.strip()
        if not stripped:
            continue
        question = stripped.endswith(("？", "?")) and bool(
            re.search(r"为什么|是不是|有没有|可以|怎么|什么|吗|呢", stripped)
        )
        for category, pattern in GROUNDING_PATTERNS:
            if question:
                continue
            for match in re.finditer(pattern, stripped):
                phrase = match.group(0)
                if phrase and phrase in referenced_fact_text:
                    continue
                flags.append(f"{category}:{phrase}")
    return sorted(set(flags))


def normalize_claims(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if value is None:
        return [], []
    if not isinstance(value, list):
        return [], ["claim_candidates_must_be_list"]
    claims: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            claims.append(
                {
                    "claim": item.strip(),
                    "status": "candidate_unverified",
                    "persona_fact_refs": [],
                    "speaker_fact_refs": [],
                }
            )
            continue
        if not isinstance(item, dict):
            errors.append(f"claim_{index}_invalid")
            continue
        text = str(item.get("text") or item.get("claim") or "").strip()
        refs = item.get("persona_fact_refs") or []
        speaker_refs = item.get("speaker_fact_refs") or []
        if not text or not isinstance(refs, list) or not isinstance(speaker_refs, list):
            errors.append(f"claim_{index}_invalid")
            continue
        claims.append(
            {
                "claim": text,
                "status": "candidate_unverified",
                "persona_fact_refs": [str(ref) for ref in refs],
                "speaker_fact_refs": [str(ref) for ref in speaker_refs],
            }
        )
    return claims, errors


def apply_metadata_fact_lineage_fix(
    source_item: dict[str, Any],
    metadata_patch: Any,
    allowed_fact_refs: set[str],
    source_batch_sha: str,
    review_sha: str,
    batch_revision: int,
) -> dict[str, Any]:
    if not isinstance(metadata_patch, dict):
        raise RuntimeError("metadata_fix requires metadata_patch.")
    additions = metadata_patch.get("add_persona_fact_refs_used") or []
    if not isinstance(additions, list):
        raise RuntimeError("metadata_fix fact refs must be a list.")
    additions = [str(ref) for ref in additions]
    invalid_refs = sorted(set(additions) - allowed_fact_refs)
    if invalid_refs:
        raise RuntimeError(
            "metadata_fix references non-KNOWN facts: " + ", ".join(invalid_refs)
        )
    appended_claims = metadata_patch.get("append_claim_candidates") or []
    if not isinstance(appended_claims, list):
        raise RuntimeError("metadata_fix claim additions must be a list.")
    normalized_claims, claim_errors = normalize_claims(appended_claims)
    if claim_errors:
        raise RuntimeError("metadata_fix claim additions are invalid.")
    source_text = "\n".join(
        str(source_item.get(field) or "")
        for field in ("title", "narration", "central_claim")
    )
    for claim in normalized_claims:
        if claim["claim"] not in source_text:
            raise RuntimeError("metadata_fix claim must already exist in source text.")
        invalid_claim_refs = sorted(
            set(claim["persona_fact_refs"]) - allowed_fact_refs
        )
        if invalid_claim_refs:
            raise RuntimeError(
                "metadata_fix claim references non-KNOWN facts: "
                + ", ".join(invalid_claim_refs)
            )
        if claim["speaker_fact_refs"]:
            raise RuntimeError("metadata_fix cannot add Speaker fact authority.")
    text_projection = {
        field: source_item.get(field)
        for field in ("title", "narration", "central_claim", "cta")
    }
    text_sha = canonical_sha256(text_projection)
    revised_item = json.loads(json.dumps(source_item, ensure_ascii=False))
    revised_item["persona_fact_refs_used"] = sorted(
        set(revised_item.get("persona_fact_refs_used") or []) | set(additions)
    )
    existing_claims = list(revised_item.get("claim_candidates") or [])
    existing_claim_keys = {
        (
            str(claim.get("claim") or claim.get("text") or ""),
            tuple(sorted(str(ref) for ref in claim.get("persona_fact_refs") or [])),
        )
        for claim in existing_claims
        if isinstance(claim, dict)
    }
    for claim in normalized_claims:
        key = (claim["claim"], tuple(sorted(claim["persona_fact_refs"])))
        if key not in existing_claim_keys:
            existing_claims.append(claim)
    revised_item["claim_candidates"] = existing_claims
    revised_item["status"] = "content_human_approved_metadata_fixed"
    revised_item["item_revision"] = batch_revision
    revised_item["revision_lineage"] = {
        "source_batch_sha256": source_batch_sha,
        "source_item_sha256": canonical_sha256(source_item),
        "human_decision": "metadata_fix",
        "human_review_sha256": review_sha,
        "content_text_unchanged": True,
        "source_text_sha256": text_sha,
        "revised_text_sha256": text_sha,
    }
    if canonical_sha256(
        {
            field: revised_item.get(field)
            for field in ("title", "narration", "central_claim", "cta")
        }
    ) != text_sha:
        raise RuntimeError("metadata_fix changed immutable content text.")
    return revised_item


def requires_review_blocked_terms(persona: dict[str, Any]) -> list[str]:
    fact = persona.get("facts", {}).get("information_requiring_human_review", {})
    if fact.get("state") != "requires_review":
        return []
    terms: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            blocked = value.get("blocked_terms")
            if isinstance(blocked, list):
                terms.extend(str(item) for item in blocked if str(item).strip())
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(fact.get("value"))
    return sorted(set(terms))


def authorized_feedback(persona_projection: dict[str, Any]) -> tuple[list[str], list[str]]:
    value = persona_projection.get("facts", {}).get(
        "authorized_customer_cases_or_feedback"
    )
    quotes: list[str] = []
    labels: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key in {"quote", "public_quote"} and isinstance(child, str):
                    quotes.append(child)
                elif key in {"customer", "customer_label", "source_label"} and isinstance(child, str):
                    labels.append(child)
                else:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return sorted(set(quotes)), sorted(set(labels))


def bounded_fact_violations(value: str, safe_persona: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if re.search(r"无需等待|不需要排队|不用等|零等待|随到随炒", value):
        errors.append("waiting_limit_removed")
    if re.search(r"比自己做(?:饭)?更便宜|一定比自己做(?:饭)?省钱|最划算|全上海最便宜", value):
        errors.append("unsupported_price_comparison")
    for sentence in re.findall(r"[^。！？!?\n]+[。！？!?]?", value):
        if "素菜" in sentence and re.search(r"(?:8|八).{0,5}(?:元|块)|(?:10|十).{0,5}(?:元|块)", sentence):
            if not re.search(r"(?:通常|多在|一般).{0,8}(?:8|八).{0,5}(?:-|–|—|到|至).{0,5}(?:10|十)", sentence):
                errors.append("vegetable_price_range_or_qualifier_lost")
        if "清蒸" in sentence and re.search(r"15|十五", sentence) and "约" not in sentence:
            errors.append("steaming_price_qualifier_lost")
        if "红烧" in sentence and re.search(r"18|十八", sentence) and not re.search(r"约|左右", sentence):
            errors.append("braising_price_qualifier_lost")
        if re.search(r"30\s*分钟|三十\s*分钟", sentence):
            if "约" not in sentence or re.search(r"任何|所有|都能|保证|一定", sentence):
                errors.append("thirty_minute_scope_or_qualifier_lost")
        if re.search(r"5\s*分钟|五\s*分钟", sentence):
            if "约" not in sentence or not re.search(r"部分|快速", sentence):
                errors.append("five_minute_scope_or_qualifier_lost")
        if re.search(r"15\s*分钟|十五\s*分钟|一刻钟", sentence) and "鱼" in sentence:
            if "约" not in sentence:
                errors.append("complex_dish_time_qualifier_lost")
        if re.search(r"每天.{0,8}20|稳定.{0,8}20|节假日.{0,8}(?:爆满|爆单)", sentence):
            errors.append("business_volume_scope_expanded")
    return sorted(set(errors))


def validate_generated_item(
    item: Any,
    allowed_fact_refs: set[str],
    safe_persona: dict[str, Any],
    accepted: list[dict[str, Any]],
    cta_intent: Any,
    slot: dict[str, Any] | None = None,
    enforce_grounding: bool = False,
    allowed_speaker_fact_refs: set[str] | None = None,
    safe_speaker: dict[str, Any] | None = None,
    local_blocked_terms: list[str] | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    if not isinstance(item, dict):
        return None, ["item_not_object"], []
    title = str(item.get("title") or "").strip()
    narration = str(item.get("narration") or "").strip()
    refs = item.get("persona_fact_refs_used") or []
    errors: list[str] = []
    flags: list[str] = []
    if not title:
        errors.append("title_empty")
    if not narration:
        errors.append("narration_empty")
    if not isinstance(refs, list):
        errors.append("persona_fact_refs_used_must_be_list")
        refs = []
    refs = [str(ref) for ref in refs]
    invalid_refs = sorted(set(refs) - allowed_fact_refs)
    if invalid_refs:
        errors.append("invalid_or_non_known_persona_fact_refs:" + ",".join(invalid_refs))
    if not refs:
        errors.append("persona_fact_refs_used_empty")
    speaker_refs = item.get("speaker_fact_refs_used") or []
    if not isinstance(speaker_refs, list):
        errors.append("speaker_fact_refs_used_must_be_list")
        speaker_refs = []
    speaker_refs = [str(ref) for ref in speaker_refs]
    allowed_speaker_fact_refs = allowed_speaker_fact_refs or set()
    invalid_speaker_refs = sorted(set(speaker_refs) - allowed_speaker_fact_refs)
    if invalid_speaker_refs:
        errors.append("invalid_or_non_known_speaker_fact_refs:" + ",".join(invalid_speaker_refs))
    combined = f"{title}\n{narration}"
    if "[" in combined or "]" in combined or "【" in combined or "】" in combined:
        errors.append("placeholder_detected")
    if re.search(r"(?:XX+|某某|待补充|placeholder)", combined, re.IGNORECASE):
        errors.append("placeholder_detected")
    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", combined))
    if combined and chinese_count / max(1, len(combined.replace("\n", ""))) < 0.35:
        errors.append("natural_chinese_check_failed")

    known_corpus = "\n".join(flatten_strings(safe_persona.get("facts", {})))
    normalized_known_corpus = re.sub(r"\s+", "", known_corpus)
    numeric_claims = re.findall(
        r"(?:\d+(?:\.\d+)?%?|[一二三四五六七八九十百千万]+)\s*(?:年|元|位|家|单|名|倍|%|％)",
        combined,
    )
    for claim in numeric_claims:
        if re.sub(r"\s+", "", claim) not in normalized_known_corpus:
            errors.append("unsupported_numeric_fact:" + claim)
    for term in STRONG_PROOF_TERMS:
        if term in combined:
            errors.append("process_or_claim_upgraded_to_proof:" + term)
    for term in UNSUPPORTED_ASSERTION_TERMS:
        if term in combined:
            errors.append("unsupported_assertion:" + term)
    for term in CLAIM_REVIEW_TERMS:
        if term in combined and term not in known_corpus:
            flags.append("claim_language_requires_human_review:" + term)
    contrast_match = re.search(r"不是[^。！？\n]{1,30}而是[^。！？\n]{1,30}", combined)
    if contrast_match and contrast_match.group(0) not in known_corpus:
        flags.append("claim_language_requires_human_review:不是X而是Y")
    process_sequence = extract_service_process_sequence(narration)
    if slot and slot.get("primary_angle") != "process" and len(process_sequence) >= 3:
        flags.append("service_process_sequence_overloaded_for_non_process_angle")
    location_scan = combined
    for generic_business_term in ("菜市场", "市集", "社区"):
        location_scan = location_scan.replace(generic_business_term, "")
    location_mentions = re.findall(
        r"[\u4e00-\u9fff]{2,12}(?:市|区|县|镇|路|街|号)(?![\u4e00-\u9fff])",
        location_scan,
    )
    if location_mentions:
        approved_location_corpus = "\n".join(
            flatten_strings(safe_persona.get("facts", {}).get("service_area"))
            + flatten_strings(
                safe_persona.get("facts", {}).get("location_public_area")
            )
        )
        if not approved_location_corpus or any(
            mention not in approved_location_corpus
            and approved_location_corpus not in mention
            for mention in location_mentions
        ):
            errors.append("unsupported_location_fact")
    for guardrail in flatten_strings(safe_persona.get("guardrails", {})):
        if guardrail and guardrail in combined:
            errors.append("prohibited_persona_guardrail_repeated")
    for blocked_term in local_blocked_terms or []:
        if blocked_term and blocked_term in combined:
            errors.append("requires_review_material_used:" + blocked_term)
    if safe_speaker:
        for guardrail in flatten_strings(safe_speaker.get("guardrails", {})):
            if guardrail and guardrail in combined:
                errors.append("prohibited_speaker_guardrail_repeated")
        if re.search(
            r"我(?:创办|创立|经营).{0,12}(?:食堂|店)|我是(?:老板|创始人)|我(?:决定|负责).{0,8}(?:免租|租金)|我每天.{0,12}(?:100|一百).{0,4}(?:单|人)|我的客户复购率|我研究行业多年",
            combined,
        ):
            errors.append("frontline_speaker_authority_exceeded")
    errors.extend(bounded_fact_violations(combined, safe_persona))

    cta = item.get("cta") or {"present": False, "text": None}
    if not isinstance(cta, dict) or not isinstance(cta.get("present"), bool):
        errors.append("cta_contract_invalid")
        cta = {"present": False, "text": None}
    if cta.get("present") and not str(cta.get("text") or "").strip():
        errors.append("cta_text_missing")
    if cta_intent in (None, "none", "absent", False) and cta.get("present"):
        errors.append("cta_not_allowed_by_request")
    cta_text = str(cta.get("text") or "")
    if re.search(r"(?:电话|手机号|微信|地址|私信我|加我)", cta_text):
        errors.append("strong_or_private_cta_disallowed")

    claims, claim_errors = normalize_claims(item.get("claim_candidates"))
    errors.extend(claim_errors)
    for claim in claims:
        invalid_claim_refs = sorted(
            set(claim["persona_fact_refs"]) - allowed_fact_refs
        )
        if invalid_claim_refs:
            errors.append("claim_invalid_fact_refs:" + ",".join(invalid_claim_refs))
        invalid_claim_speaker_refs = sorted(
            set(claim["speaker_fact_refs"]) - allowed_speaker_fact_refs
        )
        if invalid_claim_speaker_refs:
            errors.append(
                "claim_invalid_speaker_fact_refs:"
                + ",".join(invalid_claim_speaker_refs)
            )
    if claims:
        flags.append("claim_candidates_require_human_review")

    central_claim = str(item.get("central_claim") or "").strip()
    if not central_claim:
        central_claim = claims[0]["claim"] if claims else title
    grounding_flags = detect_grounding_risks(
        "\n".join(
            [title, narration, central_claim]
            + [claim["claim"] for claim in claims]
        ),
        refs,
        safe_persona,
    )
    flags.extend("grounding_requires_human_review:" + flag for flag in grounding_flags)
    if enforce_grounding:
        errors.extend("unsupported_grounding_claim:" + flag for flag in grounding_flags)

    feedback_provenance = item.get("customer_feedback_provenance") or []
    if not isinstance(feedback_provenance, list):
        errors.append("customer_feedback_provenance_must_be_list")
        feedback_provenance = []
    authorized_quotes, feedback_labels = authorized_feedback(safe_persona)
    used_quotes = [quote for quote in authorized_quotes if quote and quote in combined]
    if slot and slot.get("primary_angle") == "customer_story" and not used_quotes:
        errors.append("customer_story_requires_exact_authorized_quote")
    for label in feedback_labels:
        if label in combined and not used_quotes:
            errors.append("customer_feedback_requires_exact_authorized_quote")
    normalized_provenance: list[dict[str, str]] = []
    for record in feedback_provenance:
        if not isinstance(record, dict):
            errors.append("customer_feedback_provenance_invalid")
            continue
        fact_ref = str(record.get("fact_ref") or "")
        quote = str(record.get("quote") or "")
        if (
            fact_ref != "authorized_customer_cases_or_feedback"
            or quote not in authorized_quotes
            or quote not in combined
        ):
            errors.append("customer_feedback_provenance_invalid")
            continue
        normalized_provenance.append({"fact_ref": fact_ref, "quote": quote})
    if used_quotes and not all(
        any(record["quote"] == quote for record in normalized_provenance)
        for quote in used_quotes
    ):
        errors.append("authorized_quote_provenance_missing")

    candidate_text = f"{title}\n{narration}"
    for previous in accepted:
        previous_text = f"{previous['title']}\n{previous['narration']}"
        similarity = text_similarity(candidate_text, previous_text)
        if similarity >= MAX_SIMILARITY:
            errors.append(f"batch_duplicate_similarity:{similarity}")
        if normalize_text(title) == normalize_text(previous["title"]):
            errors.append("duplicate_title")
        opening = normalize_text(narration)[:12]
        previous_opening = normalize_text(previous["narration"])[:12]
        if len(opening) >= 10 and opening == previous_opening:
            errors.append("duplicate_opening")
        ending = normalize_text(narration)[-12:]
        previous_ending = normalize_text(previous["narration"])[-12:]
        if len(ending) >= 10 and ending == previous_ending:
            errors.append("duplicate_ending")

    normalized = {
        "title": title,
        "narration": narration,
        "central_claim": central_claim,
        "persona_fact_refs_used": sorted(set(refs)),
        "speaker_fact_refs_used": sorted(set(speaker_refs)),
        "claim_candidates": claims,
        "customer_feedback_provenance": normalized_provenance,
        "cta": {
            "present": bool(cta.get("present")),
            "text": str(cta.get("text")).strip() if cta.get("present") else None,
        },
    }
    return normalized if not errors else None, sorted(set(errors)), sorted(set(flags))


def similarity_summary(contents: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for left_index, left in enumerate(contents):
        for right in contents[left_index + 1 :]:
            score = text_similarity(
                f"{left['title']}\n{left['narration']}",
                f"{right['title']}\n{right['narration']}",
            )
            pairs.append(
                {
                    "left": left["content_id"],
                    "right": right["content_id"],
                    "similarity": score,
                }
            )
    maximum = max((item["similarity"] for item in pairs), default=0.0)
    mean = round(
        sum(item["similarity"] for item in pairs) / len(pairs), 6
    ) if pairs else 0.0
    return {
        "policy": SIMILARITY_POLICY,
        "method": "normalized_sequence_matcher",
        "rejection_threshold": MAX_SIMILARITY,
        "pair_count": len(pairs),
        "maximum_similarity": maximum,
        "mean_similarity": mean,
        "pairs_at_or_above_threshold": [
            item for item in pairs if item["similarity"] >= MAX_SIMILARITY
        ],
        "distinct_titles": len({normalize_text(item["title"]) for item in contents})
        == len(contents),
    }


def review_flag_summary(contents: list[dict[str, Any]]) -> dict[str, Any]:
    by_flag: dict[str, int] = {}
    item_count = 0
    total = 0
    claim_count = 0
    for item in contents:
        flags = sorted(set(item.get("potential_review_flags") or []))
        if flags:
            item_count += 1
        for flag in flags:
            total += 1
            by_flag[flag] = by_flag.get(flag, 0) + 1
            if flag.startswith("claim_"):
                claim_count += 1
    return {
        "items_with_review_flags": item_count,
        "total_review_flag_count": total,
        "claim_review_flag_count": claim_count,
        "by_flag": dict(sorted(by_flag.items())),
    }


def semantic_diversity_summary(contents: list[dict[str, Any]]) -> dict[str, Any]:
    angle_distribution: dict[str, int] = {}
    bundle_distribution: dict[str, int] = {}
    central_pairs: list[dict[str, Any]] = []
    fact_overlap_pairs: list[dict[str, Any]] = []
    process_sequences: dict[str, list[str]] = {}
    for item in contents:
        angle = str(item.get("primary_angle") or "unspecified")
        angle_distribution[angle] = angle_distribution.get(angle, 0) + 1
        bundle = tuple(sorted(set(item.get("persona_fact_refs_used") or [])))
        bundle_key = ",".join(bundle)
        bundle_distribution[bundle_key] = bundle_distribution.get(bundle_key, 0) + 1
        sequence = extract_service_process_sequence(str(item.get("narration") or ""))
        if len(sequence) >= 2:
            process_sequences[item["content_id"]] = sequence
    for left_index, left in enumerate(contents):
        for right in contents[left_index + 1 :]:
            central_score = text_similarity(
                str(left.get("central_claim") or ""),
                str(right.get("central_claim") or ""),
            )
            if central_score >= CENTRAL_CLAIM_SIMILARITY:
                central_pairs.append(
                    {
                        "left": left["content_id"],
                        "right": right["content_id"],
                        "similarity": central_score,
                    }
                )
            left_refs = set(left.get("persona_fact_refs_used") or [])
            right_refs = set(right.get("persona_fact_refs_used") or [])
            union = left_refs | right_refs
            overlap = round(len(left_refs & right_refs) / len(union), 6) if union else 0.0
            if overlap >= FACT_BUNDLE_OVERLAP:
                fact_overlap_pairs.append(
                    {
                        "left": left["content_id"],
                        "right": right["content_id"],
                        "overlap": overlap,
                    }
                )
    repeated_sequences: list[dict[str, Any]] = []
    sequence_groups: dict[tuple[str, ...], list[str]] = {}
    for content_id, sequence in process_sequences.items():
        sequence_groups.setdefault(tuple(sequence), []).append(content_id)
    for sequence, content_ids in sequence_groups.items():
        if len(content_ids) > 1:
            repeated_sequences.append(
                {"sequence": list(sequence), "content_ids": sorted(content_ids)}
            )
    angle_reuse = {
        angle: count for angle, count in angle_distribution.items() if count > 1
    }
    flags: list[str] = []
    if angle_reuse:
        flags.append("primary_angle_reuse")
    if fact_overlap_pairs:
        flags.append("primary_fact_bundle_high_overlap")
    if central_pairs:
        flags.append("central_claim_overlap")
    if repeated_sequences:
        flags.append("service_process_sequence_repetition")
    return {
        "policy": SIMILARITY_POLICY,
        "primary_angle_distribution": dict(sorted(angle_distribution.items())),
        "primary_angle_reuse": angle_reuse,
        "fact_bundle_distribution": dict(sorted(bundle_distribution.items())),
        "fact_bundle_high_overlap_pairs": fact_overlap_pairs,
        "central_claim_overlap_threshold": CENTRAL_CLAIM_SIMILARITY,
        "central_claim_overlap_pairs": central_pairs,
        "service_process_sequence_repetition": repeated_sequences,
        "semantic_diversity_flags": flags,
        "passed_without_flags": not flags,
    }


def load_approved_persona_for_review(batch: dict[str, Any]) -> dict[str, Any]:
    persona_lineage = batch.get("lineage", {}).get("persona", {})
    path = Path(str(persona_lineage.get("path") or "")).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("Review Pack Persona lineage path is missing.")
    if sha256_file(path) != persona_lineage.get("sha256"):
        raise RuntimeError("Review Pack Persona SHA lineage mismatch.")
    persona = read_json(path)
    lifecycle = persona.get("lifecycle", {})
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        raise RuntimeError("Review Pack requires the lineaged Approved Persona.")
    return persona


def load_approved_speaker_for_review(
    batch: dict[str, Any], business_persona: dict[str, Any]
) -> dict[str, Any] | None:
    speaker_lineage = batch.get("lineage", {}).get("speaker_persona")
    if not speaker_lineage:
        return None
    path = Path(str(speaker_lineage.get("path") or "")).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("Review Pack Speaker Persona lineage path is missing.")
    if sha256_file(path) != speaker_lineage.get("sha256"):
        raise RuntimeError("Review Pack Speaker Persona SHA lineage mismatch.")
    speaker = read_json(path)
    lifecycle = speaker.get("lifecycle", {})
    if (
        speaker.get("persona_scope") != "speaker"
        or lifecycle.get("status") != "approved"
        or lifecycle.get("approved") is not True
    ):
        raise RuntimeError("Review Pack requires the lineaged Approved Speaker Persona.")
    business_ref = speaker.get("business_persona_ref") or {}
    if (
        business_ref.get("persona_id") != business_persona.get("persona_id")
        or business_ref.get("sha256") != batch["lineage"]["persona"]["sha256"]
    ):
        raise RuntimeError("Review Pack Speaker Business Persona lineage mismatch.")
    return speaker


def build_supporting_fact_projection(
    batch: dict[str, Any], persona: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, str]]:
    referenced = set()
    for item in batch.get("contents", []):
        referenced.update(str(ref) for ref in item.get("persona_fact_refs_used") or [])
        for claim in item.get("claim_candidates") or []:
            referenced.update(
                str(ref) for ref in claim.get("persona_fact_refs") or []
            )
    safe_known: dict[str, Any] = {}
    non_known: dict[str, str] = {}
    persona_facts = persona.get("facts", {})
    for ref in sorted(referenced):
        fact = persona_facts.get(ref, {})
        state = str(fact.get("state") or "missing").lower()
        value = fact.get("value")
        if (
            state == "known"
            and value not in (None, "", [], {})
            and ref not in NEVER_EGRESS_FACT_FIELDS
        ):
            safe_known[ref] = project_value(value, "safe_verbatim")
        else:
            non_known[ref] = state
    assert_safe_for_external_model(
        json.dumps(safe_known, ensure_ascii=False, sort_keys=True)
    )
    return safe_known, non_known


def build_supporting_speaker_fact_projection(
    batch: dict[str, Any], speaker: dict[str, Any] | None
) -> tuple[dict[str, Any], dict[str, str]]:
    if speaker is None:
        return {}, {}
    referenced = set()
    for item in batch.get("contents", []):
        referenced.update(str(ref) for ref in item.get("speaker_fact_refs_used") or [])
        for claim in item.get("claim_candidates") or []:
            referenced.update(str(ref) for ref in claim.get("speaker_fact_refs") or [])
    safe_known: dict[str, Any] = {}
    non_known: dict[str, str] = {}
    speaker_facts = speaker.get("facts", {})
    for ref in sorted(referenced):
        fact = speaker_facts.get(ref, {})
        state = str(fact.get("state") or "missing").lower()
        value = fact.get("value")
        if (
            state == "known"
            and value not in (None, "", [], {})
            and ref in SPEAKER_GENERATION_FACT_FIELDS
        ):
            safe_known[ref] = project_value(value, "safe_verbatim")
        else:
            non_known[ref] = state
    assert_safe_for_external_model(
        json.dumps(safe_known, ensure_ascii=False, sort_keys=True)
    )
    return safe_known, non_known


def fact_excerpts(value: Any) -> list[str]:
    if isinstance(value, list):
        return [
            item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
            for item in value
        ]
    if isinstance(value, str):
        return [value]
    return [json.dumps(value, ensure_ascii=False, sort_keys=True)]


def assess_claim_support(
    claim: str,
    fact_refs: list[str],
    safe_known_facts: dict[str, Any],
) -> dict[str, Any]:
    excerpts = [
        excerpt
        for ref in fact_refs
        if ref in safe_known_facts
        for excerpt in fact_excerpts(safe_known_facts[ref])
    ]
    unavailable_refs = sorted(set(fact_refs) - set(safe_known_facts))
    risk_markers = [term for term in CLAIM_SUPPORT_RISK_TERMS if term in claim]
    if re.search(r"不是[^。！？\n]{1,30}而是[^。！？\n]{1,30}", claim):
        risk_markers.append("不是X而是Y")
    normalized_claim = normalize_text(claim)
    similarities = [text_similarity(claim, excerpt) for excerpt in excerpts]
    exact_support = any(
        normalized_claim == normalize_text(excerpt)
        or (
            len(normalize_text(excerpt)) >= 6
            and normalize_text(excerpt) in normalized_claim
            and len(normalized_claim) <= len(normalize_text(excerpt)) + 6
        )
        for excerpt in excerpts
    )
    maximum_similarity = max(similarities, default=0.0)
    if unavailable_refs or not excerpts:
        status = "unresolved"
    elif risk_markers:
        status = "partial" if maximum_similarity >= 0.15 else "unresolved"
    elif exact_support:
        status = "direct"
    elif maximum_similarity >= 0.18:
        status = "partial"
    else:
        status = "unresolved"
    return {
        "status": status,
        "supporting_fact_refs": fact_refs,
        "supporting_fact_excerpts": excerpts,
        "unavailable_fact_refs": unavailable_refs,
        "risk_markers": sorted(set(risk_markers)),
        "maximum_text_similarity": maximum_similarity,
        "method": "deterministic_conservative_v1",
    }


def build_review_projection(batch: dict[str, Any]) -> dict[str, Any]:
    persona = load_approved_persona_for_review(batch)
    speaker = load_approved_speaker_for_review(batch, persona)
    safe_known, non_known = build_supporting_fact_projection(batch, persona)
    safe_speaker_known, speaker_non_known = build_supporting_speaker_fact_projection(
        batch, speaker
    )
    merged_safe_known = {**safe_known, **safe_speaker_known}
    item_projections: dict[str, Any] = {}
    support_counts = {"direct": 0, "partial": 0, "unresolved": 0}
    for item in batch.get("contents", []):
        used_refs = [str(ref) for ref in item.get("persona_fact_refs_used") or []]
        used_speaker_refs = [
            str(ref) for ref in item.get("speaker_fact_refs_used") or []
        ]
        claims = []
        for claim in item.get("claim_candidates") or []:
            claim_text = str(claim.get("claim") or claim.get("text") or "").strip()
            claim_refs = [str(ref) for ref in claim.get("persona_fact_refs") or []]
            claim_speaker_refs = [
                str(ref) for ref in claim.get("speaker_fact_refs") or []
            ]
            assessment = assess_claim_support(
                claim_text, claim_refs + claim_speaker_refs, merged_safe_known
            )
            support_counts[assessment["status"]] += 1
            claims.append({"claim": claim_text, **assessment})
        item_projections[item["content_id"]] = {
            "supporting_known_facts": {
                ref: safe_known[ref] for ref in used_refs if ref in safe_known
            },
            "supporting_business_facts": {
                ref: safe_known[ref] for ref in used_refs if ref in safe_known
            },
            "supporting_speaker_facts": {
                ref: safe_speaker_known[ref]
                for ref in used_speaker_refs
                if ref in safe_speaker_known
            },
            "non_known_or_ineligible_refs": {
                ref: non_known[ref] for ref in used_refs if ref in non_known
            },
            "non_known_speaker_refs": {
                ref: speaker_non_known[ref]
                for ref in used_speaker_refs
                if ref in speaker_non_known
            },
            "customer_feedback_provenance": item.get(
                "customer_feedback_provenance", []
            ),
            "claim_support": claims,
        }
    return {
        "review_pack_version": REVIEW_PACK_VERSION,
        "persona_ref": {
            "persona_id": persona.get("persona_id"),
            "revision": persona.get("revision"),
            "sha256": batch["lineage"]["persona"]["sha256"],
        },
        "speaker_ref": (
            {
                "persona_id": speaker.get("persona_id"),
                "revision": speaker.get("revision"),
                "sha256": batch["lineage"]["speaker_persona"]["sha256"],
            }
            if speaker
            else None
        ),
        "items": item_projections,
        "claim_support_summary": {
            **support_counts,
            "total": sum(support_counts.values()),
        },
        "privacy": {
            "shared_safe_verbatim_projection_used": True,
            "private_or_review_fields_omitted": sorted(NEVER_EGRESS_FACT_FIELDS),
        },
        "remote_model_used": False,
    }


def generate_batch(
    context: dict[str, Any],
    model: str = DEFAULT_MODEL,
    max_attempts: int = 3,
    transport: Callable[[str], dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    request = context["request"]
    source_plan = context["source_plan"]
    angle_plan = build_content_angle_plan(context)
    slots = angle_plan["slots"]
    slot_by_id = {slot["slot_id"]: slot for slot in slots}
    accepted_by_slot: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    remote_transport = transport or default_transport(model)
    allowed_fact_refs = {
        field for field in GENERATION_FACT_FIELDS if is_known(context["persona"], field)
    } - NEVER_EGRESS_FACT_FIELDS
    allowed_speaker_fact_refs = {
        field
        for field in SPEAKER_GENERATION_FACT_FIELDS
        if context.get("speaker_persona")
        and is_known(context["speaker_persona"], field)
    }
    local_blocked_terms = requires_review_blocked_terms(context["persona"])
    if context.get("speaker_persona"):
        local_blocked_terms.extend(
            requires_review_blocked_terms(context["speaker_persona"])
        )
    local_blocked_terms = sorted(set(local_blocked_terms))

    for attempt_number in range(1, max_attempts + 1):
        remaining = [
            slot for slot in slots if slot["slot_id"] not in accepted_by_slot
        ]
        if not remaining:
            break
        safe_input, prompt, pre_audit = prepare_generation_egress(
            context,
            remaining,
            [item["title"] for item in accepted_by_slot.values()],
        )
        print(
            f"GENERATION ATTEMPT {attempt_number}/{max_attempts} START "
            f"slots={len(remaining)}",
            flush=True,
        )
        try:
            result, post_audit = invoke_generation_transport(
                safe_input=safe_input,
                rendered_prompt=prompt,
                pre_call_audit=pre_audit,
                transport=remote_transport,
            )
        except Exception as exc:
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "transport_or_response",
                    "reason": str(exc),
                }
            )
            attempts.append(
                {
                    "attempt": attempt_number,
                    "requested_slots": [slot["slot_id"] for slot in remaining],
                    "accepted_count": 0,
                    "rejected_count": len(remaining),
                    "rendered_prompt_sha256": pre_audit[
                        "rendered_prompt_sha256"
                    ],
                    "safe_input_sha256": pre_audit["safe_input_sha256"],
                    "privacy_policy_version": PRIVACY_POLICY_VERSION,
                    "pre_call_privacy_gate_passed": True,
                    "post_call_egress_audit_passed": False,
                    "usage": {},
                    "elapsed_seconds": None,
                    "error": str(exc),
                }
            )
            print(
                f"GENERATION ATTEMPT {attempt_number}/{max_attempts} INVALID: {exc}",
                flush=True,
            )
            continue

        payload = result.get("payload")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            items = []
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "response_contract",
                    "reason": "response_items_missing_or_invalid",
                    "response_sha256": result.get("response_sha256"),
                }
            )
        seen_slots: set[str] = set()
        accepted_this_attempt = 0
        rejected_this_attempt = 0
        for response_index, raw_item in enumerate(items, start=1):
            slot_id = str(raw_item.get("slot_id") or "") if isinstance(raw_item, dict) else ""
            if (
                slot_id not in slot_by_id
                or slot_id in accepted_by_slot
                or slot_id in seen_slots
                or slot_id not in {slot["slot_id"] for slot in remaining}
            ):
                rejected_this_attempt += 1
                rejected.append(
                    {
                        "attempt": attempt_number,
                        "response_index": response_index,
                        "slot_id": slot_id or None,
                        "reason": "invalid_extra_or_duplicate_slot_id",
                        "candidate_sha256": canonical_sha256(raw_item),
                    }
                )
                continue
            seen_slots.add(slot_id)
            normalized, errors, flags = validate_generated_item(
                raw_item,
                allowed_fact_refs,
                safe_input["persona"],
                list(accepted_by_slot.values()),
                request.get("cta_intent"),
                slot_by_id[slot_id],
                False,
                allowed_speaker_fact_refs,
                safe_input.get("speaker"),
                local_blocked_terms,
            )
            if normalized is None:
                rejected_this_attempt += 1
                rejected.append(
                    {
                        "attempt": attempt_number,
                        "response_index": response_index,
                        "slot_id": slot_id,
                        "reasons": errors,
                        "candidate_sha256": canonical_sha256(raw_item),
                        "candidate": raw_item,
                    }
                )
                continue
            slot = slot_by_id[slot_id]
            case_record = context["fingerprints"][slot["case_id"]]
            accepted_by_slot[slot_id] = normalized | {
                "slot_id": slot_id,
                "case_id": slot["case_id"],
                "case_surrogate_ref": case_record["surrogate_ref"],
                "potential_review_flags": flags,
                "machine_validation": {
                    "passed": True,
                    "unsupported_fact_guard_passed": True,
                    "proof_language_guard_passed": True,
                    "persona_fact_refs_valid": True,
                    "privacy_egress_gate_passed_before_generation": True,
                    "batch_duplicate_check_passed": True,
                },
            }
            accepted_this_attempt += 1

        missing_response_slots = {
            slot["slot_id"] for slot in remaining
        } - seen_slots
        for slot_id in sorted(missing_response_slots):
            rejected_this_attempt += 1
            rejected.append(
                {
                    "attempt": attempt_number,
                    "slot_id": slot_id,
                    "reason": "model_omitted_requested_slot",
                }
            )
        attempts.append(
            {
                "attempt": attempt_number,
                "requested_slots": [slot["slot_id"] for slot in remaining],
                "accepted_count": accepted_this_attempt,
                "rejected_count": rejected_this_attempt,
                "rendered_prompt_sha256": pre_audit["rendered_prompt_sha256"],
                "safe_input_sha256": pre_audit["safe_input_sha256"],
                "runtime_persona_projection_sha256": pre_audit[
                    "runtime_persona_projection_sha256"
                ],
                "privacy_policy_version": pre_audit["privacy_policy_version"],
                "pre_call_privacy_gate_passed": True,
                "post_call_egress_audit_passed": (
                    post_audit["rendered_prompt_sha256"]
                    == pre_audit["rendered_prompt_sha256"]
                ),
                "response_sha256": result.get("response_sha256"),
                "usage": result.get("usage", {}),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "error": None,
            }
        )
        print(
            f"GENERATION ATTEMPT {attempt_number}/{max_attempts} PASS "
            f"accepted={accepted_this_attempt} rejected={rejected_this_attempt} "
            f"elapsed={result.get('elapsed_seconds')}s "
            f"tokens={result.get('usage', {}).get('total_tokens')}",
            flush=True,
        )

    contents: list[dict[str, Any]] = []
    selected_pattern = source_plan["selected_patterns"][0]
    pool_by_id = {
        str(item["case_id"]): item
        for item in source_plan.get("eligible_case_pool", [])
    }
    for index, slot in enumerate(slots, start=1):
        generated = accepted_by_slot.get(slot["slot_id"])
        if generated is None:
            continue
        case_pool_item = pool_by_id[slot["case_id"]]
        contents.append(
            {
                "content_id": f"{request['request_id']}-C{index:03d}",
                "request_id": request["request_id"],
                "persona_ref": {
                    "persona_id": context["persona"]["persona_id"],
                    "revision": context["persona"]["revision"],
                    "persona_sha": sha256_file(context["paths"]["persona"]),
                },
                "speaker_ref": (
                    {
                        "persona_id": context["speaker_persona"]["persona_id"],
                        "revision": context["speaker_persona"]["revision"],
                        "speaker_type": context["speaker_persona"].get("speaker_type"),
                        "public_display_name": context["speaker_persona"]
                        .get("facts", {})
                        .get("public_display_name", {})
                        .get("value"),
                        "public_role": context["speaker_persona"]
                        .get("facts", {})
                        .get("public_role", {})
                        .get("value"),
                        "persona_sha": sha256_file(
                            context["paths"]["speaker_persona"]
                        ),
                    }
                    if context.get("speaker_persona")
                    else None
                ),
                "pattern_ref": {
                    "pattern_id": context["pattern"]["pattern_id"],
                    "pattern_sha": sha256_file(context["paths"]["pattern"]),
                },
                "case_reference": {
                    "case_id": slot["case_id"],
                    "fingerprint_sha": case_pool_item["fingerprint_sha"],
                    "reference_authority": "structural_abstraction_only",
                },
                "content_intent": request["content_intent"],
                "slot_id": slot["slot_id"],
                "primary_angle": slot["primary_angle"],
                "primary_persona_fact_refs": slot["primary_persona_fact_refs"],
                "optional_secondary_fact_refs": slot[
                    "optional_secondary_fact_refs"
                ],
                "speaker_fact_refs": slot.get("speaker_fact_refs", []),
                "opening_strategy": slot["opening_strategy"],
                "narrative_mode": slot["narrative_mode"],
                "title": generated["title"],
                "narration": generated["narration"],
                "central_claim": generated["central_claim"],
                "persona_fact_refs_used": generated["persona_fact_refs_used"],
                "speaker_fact_refs_used": generated["speaker_fact_refs_used"],
                "claim_candidates": generated["claim_candidates"],
                "customer_feedback_provenance": generated[
                    "customer_feedback_provenance"
                ],
                "cta": generated["cta"],
                "validation": generated["machine_validation"],
                "potential_review_flags": generated["potential_review_flags"],
                "status": "generated",
            }
        )

    requested_quantity = int(request["quantity"])
    planned_quantity = int(angle_plan["planned_quantity"])
    full = len(contents) == planned_quantity
    requested_quantity_met = len(contents) == requested_quantity
    usage_totals = {
        key: sum(
            int(attempt.get("usage", {}).get(key) or 0) for attempt in attempts
        )
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    elapsed_total = round(
        sum(float(attempt.get("elapsed_seconds") or 0) for attempt in attempts), 6
    )
    prompt_hashes = [attempt["rendered_prompt_sha256"] for attempt in attempts]
    diversity_v02 = semantic_diversity_summary(contents)
    review_flags = review_flag_summary(contents)
    batch = {
        "schema_version": SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "prompt_version": PROMPT_VERSION,
        "request_id": request["request_id"],
        "profile": request["profile"],
        "status": (
            "review_required"
            if full and planned_quantity > 0
            else "diversity_capacity_limited"
            if full
            else "generation_incomplete"
        ),
        "fixture_only": bool(context["persona"].get("fixture_only")),
        "created_at": created_at or now_iso(),
        "model": model,
        "requested_quantity": requested_quantity,
        "generated_count": len(contents),
        "machine_pass_count": len(contents),
        "rejected_generation_count": len(rejected),
        "contents": contents,
        "rejected_generations": rejected,
        "content_angle_plan": angle_plan,
        "content_capacity_assessment": {
            key: angle_plan[key]
            for key in (
                "status",
                "reason",
                "requested_quantity",
                "high_confidence_distinct_capacity",
                "planned_quantity",
            )
        },
        "batch_similarity": similarity_summary(contents),
        "batch_diversity_v0_2": diversity_v02,
        "review_flag_summary": review_flags,
        "generation_attempts": attempts,
        "usage": usage_totals,
        "timing": {
            "remote_generation_elapsed_seconds": elapsed_total,
            "attempt_count": len(attempts),
            "retry_count": max(0, len(attempts) - 1),
        },
        "lineage": {
            "persona": {
                "path": str(context["paths"]["persona"]),
                "sha256": sha256_file(context["paths"]["persona"]),
                "content_sha256": context["persona"].get("provenance", {}).get(
                    "content_sha256"
                ),
            },
            "speaker_persona": (
                {
                    "path": str(context["paths"]["speaker_persona"]),
                    "sha256": sha256_file(context["paths"]["speaker_persona"]),
                    "content_sha256": context["speaker_persona"]
                    .get("provenance", {})
                    .get("content_sha256"),
                    "business_persona_sha256": context["speaker_persona"]
                    .get("business_persona_ref", {})
                    .get("sha256"),
                }
                if context.get("speaker_persona")
                else None
            ),
            "request": {
                "path": str(context["paths"]["request"]),
                "sha256": sha256_file(context["paths"]["request"]),
            },
            "source_plan": {
                "path": str(context["paths"]["source_plan"]),
                "sha256": sha256_file(context["paths"]["source_plan"]),
            },
            "approved_pattern": {
                "path": str(context["paths"]["pattern"]),
                "sha256": sha256_file(context["paths"]["pattern"]),
            },
            "fingerprints": {
                case_id: {
                    "path": record["path"],
                    "sha256": record["sha256"],
                }
                for case_id, record in sorted(context["fingerprints"].items())
            },
            "combined_prompt_sha256": canonical_sha256(prompt_hashes),
            "rendered_prompt_sha256": prompt_hashes,
        },
        "privacy": {
            "privacy_policy_version": PRIVACY_POLICY_VERSION,
            "approved_persona_known_facts_only": True,
            "runtime_shared_projection_used": True,
            "pre_network_gate_passed_all_attempts": all(
                attempt.get("pre_call_privacy_gate_passed") is True
                for attempt in attempts
            ),
            "raw_persona_sent": False,
            "raw_speaker_persona_sent": False,
            "private_or_review_fields_omitted": sorted(NEVER_EGRESS_FACT_FIELDS),
        },
        "authority": {
            "generation_completed": full,
            "generation_completed_for_planned_capacity": full,
            "human_review_required": True,
            "auto_approved": False,
            "raw_case_narration_read": False,
            "raw_case_visual_text_read": False,
            "case_specific_claims_sent_to_model": False,
            "case_facts_transferred": False,
            "speaker_overlay_applied": context.get("speaker_persona") is not None,
            "speaker_business_facts_copied": False,
            "pattern_effectiveness_used": False,
            "proof_reinterpreted": False,
        },
        "validation": {
            "passed": full,
            "contract_valid": True,
            "requested_quantity_met": requested_quantity_met,
            "content_capacity_respected": len(contents) <= planned_quantity,
            "all_contents_machine_passed": full,
            "persona_fact_refs_known_only": full,
            "speaker_fact_refs_known_only": full,
            "speaker_business_lineage_valid": context.get("speaker_persona") is None
            or context["speaker_persona"].get("business_persona_ref", {}).get(
                "sha256"
            )
            == sha256_file(context["paths"]["persona"]),
            "unsupported_fact_guard_passed": full,
            "proof_guard_passed": full,
            "batch_similarity_passed": not bool(
                similarity_summary(contents)["pairs_at_or_above_threshold"]
            ),
            "semantic_diversity_flags_present": bool(
                diversity_v02["semantic_diversity_flags"]
            ),
            "review_flags_aggregated": review_flags["total_review_flag_count"]
            == sum(
                len(set(item.get("potential_review_flags") or []))
                for item in contents
            ),
            "source_plan_supported": True,
            "profile_mix": True,
            "approved_pattern_only": True,
            "sha_lineage_complete": True,
            "privacy_gate_before_network": True,
        },
    }
    return batch


def generate_selective_revision_batch(
    context: dict[str, Any],
    source_batch_path: Path,
    human_review_path: Path,
    batch_revision: int = 2,
    model: str = DEFAULT_MODEL,
    max_attempts: int = 3,
    transport: Callable[[str], dict[str, Any]] | None = None,
    created_at: str | None = None,
    carried_revision_path: Path | None = None,
) -> dict[str, Any]:
    source_batch_path = source_batch_path.expanduser().resolve()
    human_review_path = human_review_path.expanduser().resolve()
    if not source_batch_path.is_file():
        raise FileNotFoundError(source_batch_path)
    if not human_review_path.is_file():
        raise FileNotFoundError(human_review_path)
    source_batch = read_json(source_batch_path)
    review = read_json(human_review_path)
    source_batch_sha = sha256_file(source_batch_path)
    review_sha = sha256_file(human_review_path)
    if review.get("schema_version") != "generation-batch-content-review-v1.0":
        raise RuntimeError("Selective Revision Human Review schema is invalid.")
    if review.get("decision") != "partial_revision_required":
        raise RuntimeError("Selective Revision requires partial_revision_required.")
    if review.get("source_batch_sha256") != source_batch_sha:
        raise RuntimeError("Selective Revision source Batch SHA mismatch.")
    if review.get("request_id") != source_batch.get("request_id"):
        raise RuntimeError("Selective Revision request_id mismatch.")
    if source_batch.get("request_id") != context["request"].get("request_id"):
        raise RuntimeError("Selective Revision context Request mismatch.")
    lineage = source_batch.get("lineage", {})
    for name, path_key in (
        ("persona", "persona"),
        ("request", "request"),
        ("source_plan", "source_plan"),
        ("approved_pattern", "pattern"),
    ):
        expected = lineage.get(name, {}).get("sha256")
        actual = sha256_file(context["paths"][path_key])
        if expected != actual:
            raise RuntimeError(f"Selective Revision {name} SHA lineage mismatch.")

    source_items = {
        item["content_id"]: item for item in source_batch.get("contents", [])
    }
    review_items = review.get("items") or []
    review_by_id = {str(item.get("content_id")): item for item in review_items}
    if len(review_by_id) != len(review_items) or set(review_by_id) != set(source_items):
        raise RuntimeError("Selective Revision must decide every source Item exactly once.")
    decisions = {
        content_id: str(item.get("decision") or "")
        for content_id, item in review_by_id.items()
    }
    if any(
        value not in {"approved", "metadata_fix", "revise", "rejected"}
        for value in decisions.values()
    ):
        raise RuntimeError("Selective Revision contains an invalid Item decision.")
    if any(value == "rejected" for value in decisions.values()):
        raise RuntimeError("This Selective Revision run requires no rejected Items.")

    carried_revision: dict[str, Any] | None = None
    carried_revision_sha: str | None = None
    carried_by_id: dict[str, dict[str, Any]] = {}
    if carried_revision_path:
        carried_revision_path = carried_revision_path.expanduser().resolve()
        if not carried_revision_path.is_file():
            raise FileNotFoundError(carried_revision_path)
        carried_revision = read_json(carried_revision_path)
        carried_revision_sha = sha256_file(carried_revision_path)
        if carried_revision.get("status") not in {
            "generation_incomplete",
            "review_required",
        }:
            raise RuntimeError(
                "Selective Revision resume requires a non-approved revision Batch."
            )
        if carried_revision.get("lineage", {}).get("source_generation_batch", {}).get(
            "sha256"
        ) != source_batch_sha:
            raise RuntimeError("Selective Revision resume source lineage mismatch.")
        carried_by_id = {
            item["content_id"]: item for item in carried_revision.get("contents", [])
        }
        if not set(carried_by_id).issubset(source_items):
            raise RuntimeError("Selective Revision resume contains an unknown Item.")
    else:
        carried_by_id = {
            item["content_id"]: item
            for item in source_batch["contents"]
            if decisions[item["content_id"]] == "approved"
        }
    carried_revalidation_records: list[dict[str, Any]] = []
    if carried_revision:
        for content_id, item in list(carried_by_id.items()):
            if decisions.get(content_id) != "revise":
                continue
            if review_by_id[content_id].get("force_regenerate") is True:
                carried_revalidation_records.append(
                    {
                        "attempt": 0,
                        "response_index": 0,
                        "slot_id": item.get("slot_id"),
                        "source": "carried_revision_forced_regeneration",
                        "reasons": ["human_review_force_regenerate"],
                        "candidate_sha256": canonical_sha256(item),
                    }
                )
                del carried_by_id[content_id]
                continue
            claim_texts = [
                str(claim.get("claim") or claim.get("text") or "")
                for claim in item.get("claim_candidates", [])
                if isinstance(claim, dict)
            ]
            grounding_flags = detect_grounding_risks(
                "\n".join(
                    [
                        str(item.get("title") or ""),
                        str(item.get("narration") or ""),
                        str(item.get("central_claim") or ""),
                    ]
                    + claim_texts
                ),
                list(item.get("persona_fact_refs_used") or []),
                context["persona"],
            )
            if grounding_flags:
                carried_revalidation_records.append(
                    {
                        "attempt": 0,
                        "response_index": 0,
                        "slot_id": item.get("slot_id"),
                        "source": "carried_revision_revalidation",
                        "reasons": [
                            "unsupported_grounding_claim:" + flag
                            for flag in grounding_flags
                        ],
                        "grounding_flags": grounding_flags,
                        "candidate_sha256": canonical_sha256(item),
                    }
                )
                del carried_by_id[content_id]
    target_content_ids = {
        content_id
        for content_id, decision in decisions.items()
        if decision == "revise" and content_id not in carried_by_id
    }

    revision_slots: list[dict[str, Any]] = []
    for source_item in source_batch["contents"]:
        content_id = source_item["content_id"]
        if decisions[content_id] != "revise" or content_id not in target_content_ids:
            continue
        case_id = str(source_item["case_reference"]["case_id"])
        revision_slots.append(
            {
                "slot_id": source_item["slot_id"],
                "content_id": content_id,
                "case_id": case_id,
                "primary_angle": source_item["primary_angle"],
                "primary_persona_fact_refs": source_item.get(
                    "primary_persona_fact_refs", []
                ),
                "optional_secondary_fact_refs": source_item.get(
                    "optional_secondary_fact_refs", []
                ),
                "speaker_fact_refs": source_item.get("speaker_fact_refs", []),
                "opening_strategy": source_item.get("opening_strategy"),
                "narrative_mode": source_item.get("narrative_mode"),
                "selected_case_structural_reference": context["fingerprints"][case_id][
                    "surrogate_ref"
                ],
                "original_generated_item": {
                    key: source_item.get(key)
                    for key in (
                        "title",
                        "narration",
                        "central_claim",
                        "persona_fact_refs_used",
                        "speaker_fact_refs_used",
                        "claim_candidates",
                        "customer_feedback_provenance",
                        "cta",
                    )
                },
                "revision_instructions": review_by_id[content_id].get(
                    "revision_instructions"
                ),
            }
        )
    if not revision_slots:
        raise RuntimeError("Selective Revision has no revise Items.")

    slot_by_id = {slot["slot_id"]: slot for slot in revision_slots}
    accepted_by_slot: dict[str, dict[str, Any]] = {}
    rejected: list[dict[str, Any]] = list(carried_revalidation_records)
    attempts: list[dict[str, Any]] = []
    remote_transport = transport or default_transport(model)
    allowed_fact_refs = {
        field for field in GENERATION_FACT_FIELDS if is_known(context["persona"], field)
    } - NEVER_EGRESS_FACT_FIELDS
    allowed_speaker_fact_refs = {
        field
        for field in SPEAKER_GENERATION_FACT_FIELDS
        if context.get("speaker_persona")
        and is_known(context["speaker_persona"], field)
    }
    local_blocked_terms = requires_review_blocked_terms(context["persona"])
    if context.get("speaker_persona"):
        local_blocked_terms.extend(
            requires_review_blocked_terms(context["speaker_persona"])
        )
    local_blocked_terms = sorted(set(local_blocked_terms))
    carried_items = list(carried_by_id.values())
    human_approved_source_items = [
        item
        for item in source_batch["contents"]
        if decisions[item["content_id"]] == "approved"
    ]

    for attempt_number in range(1, max_attempts + 1):
        remaining = [
            slot for slot in revision_slots if slot["slot_id"] not in accepted_by_slot
        ]
        if not remaining:
            break
        safe_input, prompt, pre_audit = prepare_revision_egress(
            context,
            remaining,
            [item["title"] for item in carried_items]
            + [item["title"] for item in accepted_by_slot.values()],
        )
        print(
            f"SELECTIVE REVISION ATTEMPT {attempt_number}/{max_attempts} START "
            f"slots={len(remaining)}",
            flush=True,
        )
        try:
            result, post_audit = invoke_generation_transport(
                safe_input=safe_input,
                rendered_prompt=prompt,
                pre_call_audit=pre_audit,
                transport=remote_transport,
            )
        except Exception as exc:
            rejected.append(
                {"attempt": attempt_number, "scope": "transport_or_response", "reason": str(exc)}
            )
            attempts.append(
                {
                    "attempt": attempt_number,
                    "requested_slots": [slot["slot_id"] for slot in remaining],
                    "accepted_count": 0,
                    "rejected_count": len(remaining),
                    "rendered_prompt_sha256": pre_audit["rendered_prompt_sha256"],
                    "safe_input_sha256": pre_audit["safe_input_sha256"],
                    "privacy_policy_version": PRIVACY_POLICY_VERSION,
                    "pre_call_privacy_gate_passed": True,
                    "post_call_egress_audit_passed": False,
                    "usage": {},
                    "elapsed_seconds": None,
                    "error": str(exc),
                }
            )
            print(
                f"SELECTIVE REVISION ATTEMPT {attempt_number}/{max_attempts} INVALID: {exc}",
                flush=True,
            )
            continue

        payload = result.get("payload")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            items = []
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "response_contract",
                    "reason": "response_items_missing_or_invalid",
                    "response_sha256": result.get("response_sha256"),
                }
            )
        seen_slots: set[str] = set()
        accepted_this_attempt = 0
        rejected_this_attempt = 0
        remaining_ids = {slot["slot_id"] for slot in remaining}
        previous_items = carried_items + list(accepted_by_slot.values())
        for response_index, raw_item in enumerate(items, start=1):
            slot_id = str(raw_item.get("slot_id") or "") if isinstance(raw_item, dict) else ""
            if (
                slot_id not in slot_by_id
                or slot_id in accepted_by_slot
                or slot_id in seen_slots
                or slot_id not in remaining_ids
            ):
                rejected_this_attempt += 1
                rejected.append(
                    {
                        "attempt": attempt_number,
                        "response_index": response_index,
                        "slot_id": slot_id or None,
                        "reason": "invalid_extra_or_duplicate_revision_slot_id",
                        "candidate_sha256": canonical_sha256(raw_item),
                    }
                )
                continue
            seen_slots.add(slot_id)
            slot = slot_by_id[slot_id]
            normalized, errors, flags = validate_generated_item(
                raw_item,
                allowed_fact_refs,
                safe_input["persona"],
                previous_items,
                context["request"].get("cta_intent"),
                slot,
                True,
                allowed_speaker_fact_refs,
                safe_input.get("speaker"),
                local_blocked_terms,
            )
            if normalized is None:
                rejected_this_attempt += 1
                rejected.append(
                    {
                        "attempt": attempt_number,
                        "response_index": response_index,
                        "slot_id": slot_id,
                        "reasons": errors,
                        "grounding_flags": [
                            error for error in errors if "grounding_claim" in error
                        ],
                        "candidate_sha256": canonical_sha256(raw_item),
                        "candidate": raw_item,
                    }
                )
                continue
            normalized.update(
                {
                    "slot_id": slot_id,
                    "case_id": slot["case_id"],
                    "potential_review_flags": flags,
                    "machine_validation": {
                        "passed": True,
                        "unsupported_fact_guard_passed": True,
                        "grounding_guard_passed": True,
                        "proof_language_guard_passed": True,
                        "persona_fact_refs_valid": True,
                        "speaker_fact_refs_valid": True,
                        "privacy_egress_gate_passed_before_generation": True,
                        "batch_duplicate_check_passed": True,
                    },
                }
            )
            accepted_by_slot[slot_id] = normalized
            previous_items.append(normalized)
            accepted_this_attempt += 1
        for slot_id in sorted(remaining_ids - seen_slots):
            rejected_this_attempt += 1
            rejected.append(
                {
                    "attempt": attempt_number,
                    "slot_id": slot_id,
                    "reason": "model_omitted_requested_revision_slot",
                }
            )
        attempts.append(
            {
                "attempt": attempt_number,
                "requested_slots": [slot["slot_id"] for slot in remaining],
                "accepted_count": accepted_this_attempt,
                "rejected_count": rejected_this_attempt,
                "rendered_prompt_sha256": pre_audit["rendered_prompt_sha256"],
                "safe_input_sha256": pre_audit["safe_input_sha256"],
                "runtime_persona_projection_sha256": pre_audit[
                    "runtime_persona_projection_sha256"
                ],
                "privacy_policy_version": pre_audit["privacy_policy_version"],
                "pre_call_privacy_gate_passed": True,
                "post_call_egress_audit_passed": (
                    post_audit["rendered_prompt_sha256"]
                    == pre_audit["rendered_prompt_sha256"]
                ),
                "response_sha256": result.get("response_sha256"),
                "usage": result.get("usage", {}),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "error": None,
            }
        )
        print(
            f"SELECTIVE REVISION ATTEMPT {attempt_number}/{max_attempts} PASS "
            f"accepted={accepted_this_attempt} rejected={rejected_this_attempt} "
            f"elapsed={result.get('elapsed_seconds')}s "
            f"tokens={result.get('usage', {}).get('total_tokens')}",
            flush=True,
        )

    revised_contents: list[dict[str, Any]] = []
    for source_item in source_batch["contents"]:
        content_id = source_item["content_id"]
        decision = decisions[content_id]
        revised_item = json.loads(json.dumps(source_item, ensure_ascii=False))
        source_item_sha = canonical_sha256(source_item)
        if content_id in carried_by_id:
            revised_item = json.loads(
                json.dumps(carried_by_id[content_id], ensure_ascii=False)
            )
        elif decision == "metadata_fix":
            revised_item = apply_metadata_fact_lineage_fix(
                source_item,
                review_by_id[content_id].get("metadata_patch"),
                allowed_fact_refs,
                source_batch_sha,
                review_sha,
                batch_revision,
            )
        elif decision == "approved":
            revised_item["status"] = "human_approved_carried_forward"
            revised_item["item_revision"] = int(source_item.get("item_revision") or 1)
            revised_item["revision_lineage"] = {
                "source_batch_sha256": source_batch_sha,
                "source_item_sha256": source_item_sha,
                "human_decision": "approved",
                "content_unchanged": True,
            }
        else:
            generated = accepted_by_slot.get(source_item["slot_id"])
            if generated is None:
                continue
            revised_item.update(
                {
                    "title": generated["title"],
                    "narration": generated["narration"],
                    "central_claim": generated["central_claim"],
                    "persona_fact_refs_used": generated["persona_fact_refs_used"],
                    "speaker_fact_refs_used": generated["speaker_fact_refs_used"],
                    "claim_candidates": generated["claim_candidates"],
                    "customer_feedback_provenance": generated[
                        "customer_feedback_provenance"
                    ],
                    "cta": generated["cta"],
                    "validation": generated["machine_validation"],
                    "potential_review_flags": generated["potential_review_flags"],
                    "status": "revised_pending_human_review",
                    "item_revision": batch_revision,
                    "revision_lineage": {
                        "source_batch_sha256": source_batch_sha,
                        "source_item_sha256": source_item_sha,
                        "human_decision": "revise",
                        "human_review_sha256": review_sha,
                    },
                }
            )
        revised_contents.append(revised_item)

    revision_complete = (
        len(accepted_by_slot) == len(revision_slots)
        and len(revised_contents) == len(source_items)
    )
    carried_unchanged = all(
        all(
            next(item for item in revised_contents if item["content_id"] == source["content_id"])[key]
            == source[key]
            for key in ("slot_id", "primary_angle", "title", "narration", "central_claim")
        )
        for source in human_approved_source_items
    )
    metadata_text_unchanged = all(
        all(
            next(
                item
                for item in revised_contents
                if item["content_id"] == source["content_id"]
            ).get(key)
            == source.get(key)
            for key in ("title", "narration", "central_claim", "cta")
        )
        for source in source_batch["contents"]
        if decisions[source["content_id"]] == "metadata_fix"
    )
    usage_totals = {
        key: sum(int(attempt.get("usage", {}).get(key) or 0) for attempt in attempts)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    elapsed_total = round(
        sum(float(attempt.get("elapsed_seconds") or 0) for attempt in attempts), 6
    )
    revised_batch = json.loads(
        json.dumps(carried_revision or source_batch, ensure_ascii=False)
    )
    revised_batch.update(
        {
            "generator_version": GENERATOR_VERSION,
            "prompt_version": PROMPT_VERSION,
            "batch_revision": batch_revision,
            "revision_type": (
                "selective_human_content_revision_topup"
                if carried_revision
                else "selective_human_content_revision"
            ),
            "status": "review_required" if revision_complete else "generation_incomplete",
            "created_at": created_at or now_iso(),
            "contents": revised_contents,
            "generated_count": len(revised_contents),
            "machine_pass_count": len(revised_contents),
            "rejected_generation_count": len(rejected),
            "rejected_generations": rejected,
            "generation_attempts": attempts,
            "source_generation_usage": source_batch.get("usage", {}),
            "usage": usage_totals,
            "timing": {
                "remote_generation_elapsed_seconds": elapsed_total,
                "attempt_count": len(attempts),
                "retry_count": max(0, len(attempts) - 1),
            },
            "human_content_review": {
                "decision": "partial_revision_required",
                "reviewer": review.get("reviewer"),
                "approved_carried_forward_count": len(human_approved_source_items),
                "metadata_fix_count": sum(
                    decision == "metadata_fix" for decision in decisions.values()
                ),
                "revised_item_count": sum(
                    decision == "revise" for decision in decisions.values()
                ) if revision_complete else sum(
                    item.get("status") == "revised_pending_human_review"
                    for item in revised_contents
                ),
                "topup_generated_count": len(accepted_by_slot),
                "rejected_item_count": 0,
            },
        }
    )
    revised_batch["batch_similarity"] = similarity_summary(revised_contents)
    revised_batch["batch_diversity_v0_2"] = semantic_diversity_summary(
        revised_contents
    )
    revised_batch["review_flag_summary"] = review_flag_summary(revised_contents)
    revised_batch["lineage"] = dict(source_batch.get("lineage", {}))
    revised_batch["lineage"].update(
        {
            "source_generation_batch": {
                "path": str(source_batch_path),
                "sha256": source_batch_sha,
            },
            "human_content_review": {
                "path": str(human_review_path),
                "sha256": review_sha,
            },
            "revision_rendered_prompt_sha256": [
                attempt["rendered_prompt_sha256"] for attempt in attempts
            ],
            "item_revision_lineage": [
                {
                    "content_id": source["content_id"],
                    "human_decision": decisions[source["content_id"]],
                    "source_item_sha256": canonical_sha256(source),
                    "revised_item_sha256": canonical_sha256(
                        next(
                            item
                            for item in revised_contents
                            if item["content_id"] == source["content_id"]
                        )
                    ),
                    "content_text_unchanged": all(
                        next(
                            item
                            for item in revised_contents
                            if item["content_id"] == source["content_id"]
                        ).get(key)
                        == source.get(key)
                        for key in ("title", "narration", "central_claim", "cta")
                    ),
                }
                for source in source_batch["contents"]
                if source["content_id"]
                in {item["content_id"] for item in revised_contents}
            ],
        }
    )
    if carried_revision_path and carried_revision_sha:
        revised_batch["lineage"]["source_incomplete_revision"] = {
            "path": str(carried_revision_path),
            "sha256": carried_revision_sha,
        }
    revised_batch["privacy"] = dict(source_batch.get("privacy", {}))
    revised_batch["privacy"]["pre_network_gate_passed_all_revision_attempts"] = all(
        attempt.get("pre_call_privacy_gate_passed") is True for attempt in attempts
    )
    revised_batch["authority"] = dict(source_batch.get("authority", {}))
    revised_batch["authority"].update(
        {
            "selective_revision_only": True,
            "selective_revision_resume": carried_revision is not None,
            "content_angles_replanned": False,
            "approved_items_carried_forward_unchanged": carried_unchanged,
            "human_review_required": True,
            "auto_approved": False,
            "case_facts_transferred": False,
            "proof_reinterpreted": False,
        }
    )
    revised_batch["validation"] = {
        "passed": revision_complete and carried_unchanged and metadata_text_unchanged,
        "selective_revision_complete": revision_complete,
        "approved_items_unchanged": carried_unchanged,
        "metadata_fix_content_text_unchanged": metadata_text_unchanged,
        "slot_ids_preserved": all(
            item.get("slot_id") == source_items[item["content_id"]].get("slot_id")
            for item in revised_contents
        ),
        "primary_angles_preserved": all(
            item.get("primary_angle")
            == source_items[item["content_id"]].get("primary_angle")
            for item in revised_contents
        ),
        "grounding_guard_passed": revision_complete,
        "persona_fact_refs_known_only": revision_complete,
        "speaker_fact_refs_known_only": revision_complete,
        "proof_guard_passed": revision_complete,
        "privacy_gate_before_network": True,
        "source_sha_lineage_complete": True,
        "human_review_required": True,
    }
    return revised_batch


def write_revision_batch(
    batch: dict[str, Any], output_dir: Path
) -> tuple[Path, Path, str]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_path = output_dir / "generation_batch_v1.json"
    review_path = output_dir / "generation_review_pack_v1.md"
    if batch_path.exists() or review_path.exists():
        raise RuntimeError("Selective Revision output already exists and cannot be overwritten.")
    payload = json.dumps(batch, ensure_ascii=False, indent=2).encode("utf-8")
    batch_sha = hashlib.sha256(payload).hexdigest()
    with batch_path.open("xb") as handle:
        handle.write(payload)
    with review_path.open("x", encoding="utf-8") as handle:
        handle.write(render_review_pack(batch, batch_sha))
    return batch_path, review_path, batch_sha


def render_review_pack(
    batch: dict[str, Any], source_batch_sha: str | None = None
) -> str:
    capacity = batch.get("content_capacity_assessment", {})
    diversity = batch.get("batch_diversity_v0_2", {})
    review_flags = batch.get("review_flag_summary", {})
    projection = build_review_projection(batch)
    claim_summary = projection["claim_support_summary"]
    lines = [
        "# Generation Review Pack V1 / Generator V0.2",
        "",
        f"Review Pack Version: `{REVIEW_PACK_VERSION}`",
        f"Source Batch SHA-256: `{source_batch_sha or 'unavailable'}`",
        f"Request: `{batch['request_id']}`",
        f"Status: `{batch['status']}`",
        f"Model: `{batch['model']}`",
        "Speaker: `"
        + (
            str(batch["contents"][0].get("speaker_ref", {}).get("public_display_name"))
            + " / "
            + str(batch["contents"][0].get("speaker_ref", {}).get("public_role"))
            if batch.get("contents") and batch["contents"][0].get("speaker_ref")
            else "none"
        )
        + "`",
        f"Machine pass: `{batch['machine_pass_count']}/{batch['requested_quantity']}`",
        f"Rejected generation records: `{batch['rejected_generation_count']}`",
        f"Content capacity: `{capacity.get('status')}` "
        f"(`{capacity.get('high_confidence_distinct_capacity')}` distinct angles; "
        f"`{capacity.get('planned_quantity')}` planned)",
        "Angle distribution: `"
        + json.dumps(diversity.get("primary_angle_distribution", {}), ensure_ascii=False)
        + "`",
        "Fact bundle reuse: `"
        + str(len(diversity.get("fact_bundle_high_overlap_pairs", [])))
        + " high-overlap pairs`",
        "Semantic diversity flags: "
        + (", ".join(diversity.get("semantic_diversity_flags", [])) or "none"),
        f"Claim review flag count: `{review_flags.get('claim_review_flag_count', 0)}`",
        f"All review flags: `{review_flags.get('total_review_flag_count', 0)}`",
        "Claim support summary: "
        f"`direct={claim_summary['direct']}, partial={claim_summary['partial']}, "
        f"unresolved={claim_summary['unresolved']}`",
        "Remote model used for review projection: `false`",
        "",
        "Human review is required. This pack is not an Approved Script Batch.",
        "",
    ]
    for item in batch["contents"]:
        item_projection = projection["items"][item["content_id"]]
        lines.extend(
            [
                f"## {item['content_id']}",
                "",
                f"Content Intent: `{item['content_intent']}`",
                f"Primary Angle: `{item.get('primary_angle')}`",
                "Speaker: `"
                + (
                    str(item.get("speaker_ref", {}).get("public_display_name"))
                    + " / "
                    + str(item.get("speaker_ref", {}).get("public_role"))
                    + " / "
                    + str(item.get("speaker_ref", {}).get("speaker_type"))
                    if item.get("speaker_ref")
                    else "none"
                )
                + "`",
                f"Title: {item['title']}",
                "",
                "Narration:",
                "",
                item["narration"],
                "",
                f"Central Claim: {item.get('central_claim')}",
                "Business Facts Used: "
                + ", ".join(f"`{value}`" for value in item["persona_fact_refs_used"]),
                "Speaker Facts Used: "
                + (
                    ", ".join(
                        f"`{value}`"
                        for value in item.get("speaker_fact_refs_used", [])
                    )
                    or "none"
                ),
                "",
                (
                    "### Supporting Business Facts"
                    if item.get("speaker_ref")
                    else "### Supporting Persona Facts"
                ),
                "",
            ]
        )
        if item_projection["supporting_business_facts"]:
            for ref, value in item_projection["supporting_business_facts"].items():
                lines.append(f"`{ref}` (`KNOWN`):")
                for excerpt in fact_excerpts(value):
                    lines.append(f"> {excerpt}")
                lines.append("")
        else:
            lines.extend(["No eligible KNOWN supporting facts.", ""])
        for ref, state in item_projection["non_known_or_ineligible_refs"].items():
            label = "REQUIRES_REVIEW" if state == "requires_review" else state.upper()
            lines.extend(
                [
                    f"`{ref}`: `[{label}: not eligible as supporting fact]`",
                    "",
                ]
            )
        if item.get("speaker_ref"):
            lines.extend(["### Supporting Speaker Facts", ""])
            if item_projection["supporting_speaker_facts"]:
                for ref, value in item_projection["supporting_speaker_facts"].items():
                    lines.append(f"`{ref}` (`KNOWN`):")
                    for excerpt in fact_excerpts(value):
                        lines.append(f"> {excerpt}")
                    lines.append("")
            else:
                lines.extend(["No eligible KNOWN Speaker facts.", ""])
            for ref, state in item_projection["non_known_speaker_refs"].items():
                label = "REQUIRES_REVIEW" if state == "requires_review" else state.upper()
                lines.extend(
                    [f"`{ref}`: `[{label}: not eligible as supporting fact]`", ""]
                )
        lines.extend(["### Customer Feedback Provenance", ""])
        if item_projection["customer_feedback_provenance"]:
            for record in item_projection["customer_feedback_provenance"]:
                lines.extend(
                    [
                        f"Fact Ref: `{record.get('fact_ref')}`",
                        f"> {record.get('quote')}",
                        "",
                    ]
                )
        else:
            lines.extend(["Not used.", ""])
        lines.extend(["### Claim to Fact Mapping", ""])
        if item_projection["claim_support"]:
            for index, claim in enumerate(item_projection["claim_support"], start=1):
                lines.extend(
                    [
                        f"#### Claim {index}",
                        "",
                        f"Claim: {claim['claim']}",
                        "Supporting Fact Refs: "
                        + (
                            ", ".join(
                                f"`{ref}`" for ref in claim["supporting_fact_refs"]
                            )
                            or "none"
                        ),
                        "Supporting Fact Excerpts:",
                    ]
                )
                if claim["supporting_fact_excerpts"]:
                    lines.extend(
                        f"> {excerpt}"
                        for excerpt in claim["supporting_fact_excerpts"]
                    )
                else:
                    lines.append("none")
                lines.extend(
                    [
                        f"Support Status: `{claim['status']}`",
                        "Risk Markers: "
                        + (", ".join(claim["risk_markers"]) or "none"),
                        "",
                    ]
                )
        else:
            lines.extend(["No claim candidates.", ""])
        lines.extend(
            [
                f"Pattern: `{item['pattern_ref']['pattern_id']}`",
                f"Case Structural Reference: `{item['case_reference']['case_id']}`",
                "Machine Validation: `PASS`",
                "Potential Review Flags: "
                + (", ".join(item["potential_review_flags"]) or "none"),
                "",
            ]
        )
    return "\n".join(lines)


def write_batch(batch: dict[str, Any], output_root: Path) -> tuple[Path, Path, str]:
    output_dir = output_root.expanduser().resolve() / str(batch["request_id"])
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_path = output_dir / "generation_batch_v1.json"
    review_path = output_dir / "generation_review_pack_v1.md"
    if batch_path.exists() or review_path.exists():
        raise RuntimeError("Generation Batch output already exists and cannot be overwritten.")
    payload = json.dumps(batch, ensure_ascii=False, indent=2).encode("utf-8")
    batch_sha = hashlib.sha256(payload).hexdigest()
    with batch_path.open("xb") as handle:
        handle.write(payload)
    with review_path.open("x", encoding="utf-8") as handle:
        handle.write(render_review_pack(batch, batch_sha))
    return batch_path, review_path, batch_sha


def write_review_pack_for_existing_batch(
    batch_path: Path, output_path: Path | None = None
) -> tuple[Path, str, dict[str, Any]]:
    batch_path = batch_path.expanduser().resolve()
    if not batch_path.is_file():
        raise FileNotFoundError(batch_path)
    batch_bytes = batch_path.read_bytes()
    batch_sha = hashlib.sha256(batch_bytes).hexdigest()
    batch = json.loads(batch_bytes.decode("utf-8"))
    review_path = (
        output_path.expanduser().resolve()
        if output_path
        else batch_path.parent / "generation_review_pack_v1.md"
    )
    review_text = render_review_pack(batch, batch_sha)
    temp_path = review_path.with_suffix(review_path.suffix + ".tmp")
    temp_path.write_text(review_text, encoding="utf-8")
    temp_path.replace(review_path)
    if hashlib.sha256(batch_path.read_bytes()).hexdigest() != batch_sha:
        raise RuntimeError("Generation Batch changed during Review Pack projection.")
    projection = build_review_projection(batch)
    return review_path, batch_sha, projection


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a review-required batch of privacy-safe Mix scripts."
    )
    parser.add_argument("--persona")
    parser.add_argument("--speaker-persona")
    parser.add_argument("--request")
    parser.add_argument("--source-plan")
    parser.add_argument("--pattern")
    parser.add_argument("--fingerprint", action="append")
    parser.add_argument(
        "--review-pack-only",
        help="Rebuild only the local Human Review Pack for an immutable Batch.",
    )
    parser.add_argument("--review-pack-output")
    parser.add_argument("--selective-revision-batch")
    parser.add_argument("--human-content-review")
    parser.add_argument("--batch-revision", type=int, default=2)
    parser.add_argument("--resume-revision-batch")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/generation_batches",
    )
    args = parser.parse_args()
    if args.review_pack_only:
        review_path, batch_sha, projection = write_review_pack_for_existing_batch(
            Path(args.review_pack_only),
            Path(args.review_pack_output) if args.review_pack_output else None,
        )
        summary = projection["claim_support_summary"]
        print("GENERATION REVIEW PACK V1 PASS")
        print(f"Source Batch SHA-256: {batch_sha}")
        print(
            "Claim support: "
            f"direct={summary['direct']} partial={summary['partial']} "
            f"unresolved={summary['unresolved']}"
        )
        print("Remote model used: False")
        print(f"Review Pack: {review_path}")
        return
    required = {
        "persona": args.persona,
        "request": args.request,
        "source-plan": args.source_plan,
        "pattern": args.pattern,
        "fingerprint": args.fingerprint,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        parser.error("Generation mode requires: " + ", ".join(missing))
    context = validate_generation_inputs(
        Path(args.persona),
        Path(args.request),
        Path(args.source_plan),
        Path(args.pattern),
        [Path(value) for value in args.fingerprint],
        Path(args.speaker_persona) if args.speaker_persona else None,
    )
    if args.selective_revision_batch:
        if not args.human_content_review:
            parser.error("Selective Revision requires --human-content-review.")
        source_batch_path = Path(args.selective_revision_batch)
        revised_batch = generate_selective_revision_batch(
            context,
            source_batch_path,
            Path(args.human_content_review),
            batch_revision=args.batch_revision,
            model=args.model,
            max_attempts=args.max_attempts,
            carried_revision_path=(
                Path(args.resume_revision_batch)
                if args.resume_revision_batch
                else None
            ),
        )
        output_dir = (
            Path(args.output_root).expanduser().resolve()
            if args.output_root
            else source_batch_path.expanduser().resolve().parent
            / "revisions"
            / f"revision_{args.batch_revision:04d}"
        )
        batch_path, review_path, batch_sha = write_revision_batch(
            revised_batch, output_dir
        )
        print(
            "MIX SCRIPT SELECTIVE REVISION PASS"
            if revised_batch["validation"]["passed"]
            else "MIX SCRIPT SELECTIVE REVISION INCOMPLETE"
        )
        print(f"Request: {revised_batch['request_id']}")
        print(f"Batch revision: {revised_batch['batch_revision']}")
        print(f"Status: {revised_batch['status']}")
        print(
            "Carried approved: "
            f"{revised_batch['human_content_review']['approved_carried_forward_count']}"
        )
        print(
            "Revised: "
            f"{revised_batch['human_content_review']['revised_item_count']}"
        )
        print(f"Rejected generation records: {revised_batch['rejected_generation_count']}")
        print(f"Batch SHA-256: {batch_sha}")
        print(f"Batch: {batch_path}")
        print(f"Review Pack: {review_path}")
        if not revised_batch["validation"]["passed"]:
            raise SystemExit(2)
        return
    batch = generate_batch(context, args.model, args.max_attempts)
    project_root = Path(__file__).resolve().parents[1]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "generation_batches"
    )
    batch_path, review_path, batch_sha = write_batch(batch, output_root)
    print("MIX SCRIPT GENERATION V1 PASS" if batch["validation"]["passed"] else "MIX SCRIPT GENERATION V1 INCOMPLETE")
    print(f"Request: {batch['request_id']}")
    print(f"Status: {batch['status']}")
    print(f"Machine pass: {batch['machine_pass_count']}/{batch['requested_quantity']}")
    print(f"Rejected generation records: {batch['rejected_generation_count']}")
    print(f"Attempts: {batch['timing']['attempt_count']}")
    print(f"Tokens: {batch['usage']['total_tokens']}")
    print(f"Remote elapsed: {batch['timing']['remote_generation_elapsed_seconds']}s")
    print(f"Batch SHA-256: {batch_sha}")
    print(f"Batch: {batch_path}")
    print(f"Review Pack: {review_path}")
    if not batch["validation"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
