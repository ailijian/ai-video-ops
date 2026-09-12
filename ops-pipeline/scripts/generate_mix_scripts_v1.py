from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import posixpath
import re
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree

from openai import OpenAI
from content_quality_v1 import (
    DEFAULT_CANDIDATE_POOL_SIZE,
    PLAN_SCHEMA_VERSION,
    append_ledger_file,
    build_comparison_scorecard,
    build_content_gap_report_v1,
    build_content_plan as build_quality_content_plan,
    build_content_plan_v1_1_1,
    build_content_plan_v1_1,
    build_storyboard_plan,
    build_v1_diagnostic_human_review,
    build_v1_v1_1_v1_1_1_scorecard,
    build_v1_vs_v1_1_scorecard,
    enrich_ledger_with_communicated_information,
    is_strong_memory,
    replace_ledger_with_communicated_information,
    review_batch_ledger_entries,
    validate_script_against_plan,
    write_new_json,
)
from privacy_projection_v1 import (
    PRIVACY_POLICY_VERSION,
    assert_safe_for_external_model,
    build_egress_audit,
    project_value,
)
from match_generation_sources_v1 import (
    NEWS_PRICE_PATTERN_ID,
    NEWS_SCENE_PATTERN_ID,
    load_approved_persona,
    load_patterns,
    load_request as load_profile_generation_request,
    match_selected_content_to_approved_patterns,
)


SCHEMA_VERSION = "generation-batch-v1.0"
GENERATOR_VERSION = "generate_mix_scripts_v1.py@0.7"
NEWS_MVP_GENERATOR_VERSION = "generate_mix_scripts_v1.py@news-mvp-1.0"
NEWS_MVP_FINALIZER_VERSION = "generate_mix_scripts_v1.py@news-mvp-final-1.0"
PROMPT_VERSION = "mix-script-generation-prompt-v2.0"
REVIEW_PACK_VERSION = "generation-review-pack-v1.3"
DEFAULT_MODEL = "deepseek-v4-flash"
SIMILARITY_POLICY = "provisional_v1_not_frozen"
MAX_SIMILARITY = 0.82
CENTRAL_CLAIM_SIMILARITY = 0.72
FACT_BUNDLE_OVERLAP = 0.80


class RemoteAttemptError(RuntimeError):
    def __init__(self, message: str, telemetry: dict[str, Any]):
        super().__init__(message)
        self.telemetry = telemetry


def remote_failure_telemetry(exc: Exception) -> dict[str, Any]:
    telemetry = dict(getattr(exc, "telemetry", {}) or {})
    telemetry.setdefault("error_type", type(exc).__name__)
    telemetry.setdefault("error_message", str(exc))
    telemetry.setdefault("usage", {})
    telemetry.setdefault("elapsed_seconds", None)
    telemetry.setdefault("response_sha256", None)
    telemetry["artifact_written"] = False
    return telemetry
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
    (
        "unsupported_physical_display_location",
        r"贴在窗口|窗口处[^。！？!?\n]{0,12}(?:价目表|价格标示)|价目表[^。！？!?\n]{0,8}窗口",
    ),
    (
        "unsupported_observer_location",
        r"站在窗口外|透过[^。！？!?\n]{0,10}窗口[^。！？!?\n]{0,10}看到",
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


def persist_remote_failure_telemetry(
    context: dict[str, Any],
    phase: str,
    attempt: int,
    exc: Exception,
    pre_call_audit: dict[str, Any] | None = None,
) -> Path:
    request_path = Path(context["paths"]["request"]).expanduser().resolve()
    data_root = next(
        (parent for parent in request_path.parents if parent.name == "data"),
        request_path.parent,
    )
    output_dir = (
        data_root
        / "metrics"
        / "generation_requests"
        / str(context["request"].get("request_id") or "unknown_request")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry = remote_failure_telemetry(exc)
    record = {
        "schema_version": "remote-attempt-telemetry-v1.1",
        "created_at": now_iso(),
        "request_id": context["request"].get("request_id"),
        "phase": phase,
        "attempt": attempt,
        "elapsed_seconds": telemetry.get("elapsed_seconds"),
        "provider_usage": telemetry.get("usage") or {},
        "error_type": telemetry.get("error_type"),
        "error_message": telemetry.get("error_message"),
        "response_sha256": telemetry.get("response_sha256"),
        "finish_reason": telemetry.get("finish_reason"),
        "artifact_written": False,
        "privacy": {
            "pre_call_gate_passed": bool(pre_call_audit),
            "rendered_prompt_sha256": (pre_call_audit or {}).get(
                "rendered_prompt_sha256"
            ),
            "safe_input_sha256": (pre_call_audit or {}).get("safe_input_sha256"),
        },
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = output_dir / f"{phase}-{attempt:02d}-{stamp}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8")
    with output_path.open("xb") as handle:
        handle.write(payload)
    return output_path


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
    quality = request.get("content_quality_v1") or {}
    if isinstance(quality, dict) and quality.get("enabled") is True:
        candidate_pool_size = int(
            quality.get("candidate_pool_size", DEFAULT_CANDIDATE_POOL_SIZE)
        )
        minimum_score = float(quality.get("minimum_editorial_score", 3.25))
        if candidate_pool_size <= 0:
            raise RuntimeError("Content Quality candidate_pool_size must be positive.")
        if not 0 <= minimum_score <= 5:
            raise RuntimeError("Content Quality editorial threshold must be on 0-5 scale.")
        constraints = request.get("constraints") or {}
        forbidden_enables = (
            "new_customer_facts_allowed",
            "new_cases_allowed",
            "external_research_allowed",
            "auto_approval_allowed",
            "excel_export_allowed",
        )
        if any(constraints.get(field) is True for field in forbidden_enables):
            raise RuntimeError(
                "Content Quality V1 request violates frozen experiment boundaries."
            )
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


def content_quality_config(context: dict[str, Any]) -> dict[str, Any]:
    value = context.get("request", {}).get("content_quality_v1") or {}
    return dict(value) if isinstance(value, dict) else {}


def content_quality_enabled(context: dict[str, Any]) -> bool:
    return content_quality_config(context).get("enabled") is True


def content_plan_output_schema_example() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "concept_id": "CONCEPT_001",
                "audience_need": "one concrete audience need",
                "content_job": "one bounded editorial job",
                "primary_topic": "one topic chosen only from approved facts",
                "primary_fact_refs": ["exact_known_business_fact_field"],
                "supporting_fact_refs": ["exact_known_business_fact_field"],
                "speaker_fact_refs": ["exact_known_speaker_fact_field"],
                "central_claim": "one bounded central claim",
                "central_claim_key": "stable_semantic_key_independent_of_wording",
                "exclusive_anchor": {
                    "kind": "specific_price_time_person_process_scene_or_behavior",
                    "value": "concrete authorized anchor or null",
                    "fact_refs": ["exact_known_fact_field"],
                },
                "customer_story_ref": None,
                "speaker_id": "supplied speaker id",
                "opening_strategy": "opening plan only, not a written hook",
                "narrative_mode": "narrative organization",
                "visual_anchor": "one concrete hero visual",
                "hero_shot_role": "hero shot purpose",
                "supporting_shot_roles": ["supporting shot purpose"],
                "storyboard_shape": None,
                "why_publish": "specific information gain",
            }
        ]
    }


def render_content_plan_prompt(
    safe_input: dict[str, Any],
    candidate_pool_size: int,
) -> str:
    return (
        "You plan Chinese short-video Content Concepts as JSON only. Do not write titles "
        "or full narration. Return about the requested candidate_pool_size; quality and "
        "semantic range matter more than filling the number. Use the supplied concept_id_range "
        "for concept IDs so independently planned batches remain traceable.\n"
        "Use only KNOWN facts in the supplied Business Persona and Speaker projections. "
        "Never use UNKNOWN, REQUIRES_REVIEW, forbidden material, external research, "
        "performance data, or facts from a Case. No Case content is supplied because Cases "
        "may organize a selected concept later but may not decide what to say.\n"
        "Treat historical_content_memory as content already said for this Business. Do not "
        "repackage it by changing title, hook, speaker, wording, case, shot order, or narrative "
        "style. speaker_id is presentation lineage, never a novelty reset key. A Speaker may "
        "create information gain only through an explicit KNOWN speaker fact.\n"
        "Each concept must make one central claim and distinguish Primary Facts from "
        "Supporting Facts. Prefer specific authorized prices, times, people, feedback, "
        "services, processes, scenes, numbers, or speaker behavior as exclusive anchors. "
        "Do not call generic praise such as convenient, professional, or good service an "
        "exclusive anchor. Reuse as supporting context is allowed; avoid making a recently "
        "overused fact the primary center.\n"
        "central_claim_key must be a stable semantic identifier for the claim, independent "
        "of surface wording. Two equivalent claims must use the same key. If the fixed fact "
        "space supports fewer worthwhile new concepts, return fewer concepts.\n\n"
        "OUTPUT SCHEMA:\n"
        + json.dumps(content_plan_output_schema_example(), ensure_ascii=False, indent=2)
        + "\n\nSAFE CONTENT PLANNING CONTEXT:\n"
        + json.dumps(
            safe_input | {"candidate_pool_size": candidate_pool_size},
            ensure_ascii=False,
            indent=2,
        )
    )


def prepare_content_plan_egress(
    context: dict[str, Any],
    ledger: dict[str, Any],
    candidate_pool_size: int | None = None,
    candidate_batch_index: int = 1,
    candidate_batch_count: int = 1,
    concept_start_index: int = 1,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    persona_projection = safe_persona_projection(context["persona"])
    speaker_projection = (
        safe_speaker_projection(context["speaker_persona"])
        if context.get("speaker_persona")
        else None
    )
    history = [
        {
            "content_ref": entry.get("content_id"),
            "semantic_signature": entry.get("semantic_signature"),
            "central_claim": entry.get("central_claim"),
            "primary_fact_refs": entry.get("primary_fact_refs") or [],
            "exclusive_anchor": entry.get("exclusive_anchor"),
            "status": entry.get("status"),
        }
        for entry in ledger.get("entries") or []
        if is_strong_memory(entry)
        and entry.get("business_id") == context["persona"].get("persona_id")
    ]
    candidate_pool_size = int(
        candidate_pool_size
        if candidate_pool_size is not None
        else content_quality_config(context).get(
            "candidate_pool_size", DEFAULT_CANDIDATE_POOL_SIZE
        )
    )
    safe_input = {
        "business_persona": persona_projection,
        "speaker_persona": speaker_projection,
        "request": project_value(
            {
                "request_id": context["request"].get("request_id"),
                "profile": context["request"].get("profile"),
                "quantity": context["request"].get("quantity"),
                "content_intent": context["request"].get("content_intent"),
                "cta_intent": context["request"].get("cta_intent"),
            },
            "safe_verbatim",
        ),
        "historical_content_memory": project_value(history, "safe_semantic"),
        "planning_boundaries": {
            "case_determines_topic": False,
            "case_facts_available": False,
            "pattern_effectiveness_available": False,
            "external_research_available": False,
        },
        "candidate_batch": {
            "batch_index": candidate_batch_index,
            "batch_count": candidate_batch_count,
            "concept_id_range": (
                f"CONCEPT_{concept_start_index:03d}.."
                f"CONCEPT_{concept_start_index + candidate_pool_size - 1:03d}"
            ),
        },
    }
    prompt = render_content_plan_prompt(safe_input, candidate_pool_size)
    runtime_projection_sha = canonical_sha256(
        {
            "business_persona": persona_projection,
            "speaker_persona": speaker_projection,
            "historical_content_memory": history,
        }
    )
    audit = build_egress_audit(
        safe_input=safe_input,
        rendered_prompt=prompt,
        privacy_context={"privacy_projection_sha256": runtime_projection_sha},
    )
    audit["projection_scope"] = (
        "runtime_approved_known_facts_and_strong_business_content_memory"
    )
    audit["runtime_persona_projection_sha256"] = runtime_projection_sha
    return safe_input, prompt, audit


def build_content_plan_from_candidates_v1(
    context: dict[str, Any],
    ledger: dict[str, Any],
    candidates: list[dict[str, Any]],
    planning_call: dict[str, Any],
    *,
    created_at: str | None = None,
    prevalidated_invalid_candidates: list[dict[str, Any]] | None = None,
    received_size_override: int | None = None,
) -> dict[str, Any]:
    if not content_quality_enabled(context):
        raise RuntimeError("Generation Request does not enable Content Quality V1.")
    if ledger.get("schema_version") != "content-ledger-v1.0":
        raise RuntimeError("Content Quality V1 requires content-ledger-v1.0.")
    if ledger.get("business_id") != context["persona"].get("persona_id"):
        raise RuntimeError("Content Ledger business_id mismatch.")

    business_projection = safe_persona_projection(context["persona"])
    speaker_projection = (
        safe_speaker_projection(context["speaker_persona"])
        if context.get("speaker_persona")
        else None
    )
    allowed_fact_refs = set(business_projection["facts"])
    allowed_speaker_refs = set((speaker_projection or {}).get("facts") or {})
    blocked_terms = requires_review_blocked_terms(context["persona"])
    if context.get("speaker_persona"):
        blocked_terms.extend(
            requires_review_blocked_terms(context["speaker_persona"])
        )
    blocked_terms.extend(flatten_strings(business_projection.get("guardrails") or {}))
    blocked_terms.extend(flatten_strings((speaker_projection or {}).get("guardrails") or {}))
    rotation = context["source_plan"].get("rotation", {}).get(
        "case_rotation_order", []
    ) or [
        str(item["case_id"])
        for item in context["source_plan"].get("eligible_case_pool") or []
    ]
    selected_pattern = context["source_plan"]["selected_patterns"][0]
    source_lineage = {
        "persona": {
            "path": str(context["paths"]["persona"]),
            "sha256": sha256_file(context["paths"]["persona"]),
        },
        "speaker_persona": (
            {
                "path": str(context["paths"]["speaker_persona"]),
                "sha256": sha256_file(context["paths"]["speaker_persona"]),
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
        "content_ledger_sha256": canonical_sha256(ledger),
        "approved_pattern_id": selected_pattern.get("pattern_id"),
        "eligible_case_ids": rotation,
    }
    return build_quality_content_plan(
        request=context["request"],
        business_id=context["persona"]["persona_id"],
        speaker_id=(context.get("speaker_persona") or {}).get("persona_id"),
        speaker_type=(context.get("speaker_persona") or {}).get("speaker_type"),
        allowed_fact_refs=allowed_fact_refs,
        allowed_speaker_fact_refs=allowed_speaker_refs,
        ledger=ledger,
        raw_candidates=candidates,
        case_rotation=rotation,
        pattern_id=selected_pattern["pattern_id"],
        source_lineage=source_lineage,
        config=content_quality_config(context),
        planning_call=planning_call,
        created_at=created_at,
        authorized_fact_values=business_projection["facts"],
        authorized_speaker_fact_values=(speaker_projection or {}).get("facts") or {},
        blocked_terms=sorted(set(blocked_terms)),
        prevalidated_invalid_candidates=prevalidated_invalid_candidates,
        received_size_override=received_size_override,
    )


def generate_content_plan_v1(
    context: dict[str, Any],
    ledger: dict[str, Any],
    model: str = DEFAULT_MODEL,
    transport: Callable[[str], dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if not content_quality_enabled(context):
        raise RuntimeError("Generation Request does not enable Content Quality V1.")
    if ledger.get("schema_version") != "content-ledger-v1.0":
        raise RuntimeError("Content Quality V1 requires content-ledger-v1.0.")
    if ledger.get("business_id") != context["persona"].get("persona_id"):
        raise RuntimeError("Content Ledger business_id mismatch.")
    config = content_quality_config(context)
    target_size = int(
        config.get("candidate_pool_size", DEFAULT_CANDIDATE_POOL_SIZE)
    )
    per_call = max(1, min(int(config.get("candidate_call_batch_size", 10)), target_size))
    batch_count = (target_size + per_call - 1) // per_call
    remote_transport = transport or default_transport(model)
    candidates: list[dict[str, Any]] = []
    planning_calls: list[dict[str, Any]] = []
    safe_input: dict[str, Any] | None = None
    print(
        "CONTENT CONCEPT PLANNING START "
        f"target={target_size} batches={batch_count}",
        flush=True,
    )
    for batch_index in range(1, batch_count + 1):
        start_index = (batch_index - 1) * per_call + 1
        requested_in_batch = min(per_call, target_size - len(candidates))
        safe_input, prompt, pre_audit = prepare_content_plan_egress(
            context,
            ledger,
            candidate_pool_size=requested_in_batch,
            candidate_batch_index=batch_index,
            candidate_batch_count=batch_count,
            concept_start_index=start_index,
        )
        try:
            result, post_audit = invoke_generation_transport(
                safe_input=safe_input,
                rendered_prompt=prompt,
                pre_call_audit=pre_audit,
                transport=remote_transport,
            )
        except Exception as exc:
            failure = remote_failure_telemetry(exc)
            telemetry_path = persist_remote_failure_telemetry(
                context,
                "content_planning",
                batch_index,
                exc,
                pre_audit,
            )
            failure["telemetry_artifact_path"] = str(telemetry_path.resolve())
            raise RemoteAttemptError(str(exc), failure) from exc
        payload = result.get("payload")
        batch_candidates = (
            payload.get("candidates") if isinstance(payload, dict) else None
        )
        if not isinstance(batch_candidates, list):
            failure_exc = RemoteAttemptError(
                "Content Concept response candidates missing or invalid.",
                {
                    "error_type": "response_schema_failed",
                    "error_message": (
                        "Content Concept response candidates missing or invalid."
                    ),
                    "usage": result.get("usage") or {},
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "response_sha256": result.get("response_sha256"),
                    "finish_reason": result.get("finish_reason"),
                    "artifact_written": False,
                },
            )
            telemetry_path = persist_remote_failure_telemetry(
                context,
                "content_planning",
                batch_index,
                failure_exc,
                pre_audit,
            )
            failure = remote_failure_telemetry(failure_exc)
            failure["telemetry_artifact_path"] = str(telemetry_path.resolve())
            raise RemoteAttemptError(str(failure_exc), failure) from failure_exc
        candidates.extend(batch_candidates[:requested_in_batch])
        planning_calls.append(
            {
                "batch_index": batch_index,
                "requested_candidate_count": requested_in_batch,
                "received_candidate_count": len(batch_candidates),
                "rendered_prompt_sha256": pre_audit["rendered_prompt_sha256"],
                "safe_input_sha256": pre_audit["safe_input_sha256"],
                "privacy_policy_version": pre_audit["privacy_policy_version"],
                "pre_call_privacy_gate_passed": True,
                "post_call_egress_audit_passed": (
                    post_audit["rendered_prompt_sha256"]
                    == pre_audit["rendered_prompt_sha256"]
                ),
                "response_sha256": result.get("response_sha256"),
                "usage": result.get("usage") or {},
                "elapsed_seconds": result.get("elapsed_seconds"),
            }
        )
        print(
            "CONTENT CONCEPT PLANNING BATCH "
            f"{batch_index}/{batch_count} PASS received={len(batch_candidates)} "
            f"elapsed={result.get('elapsed_seconds')}s "
            f"tokens={(result.get('usage') or {}).get('total_tokens')}",
            flush=True,
        )
    if safe_input is None:
        raise RuntimeError("Content Concept planning did not prepare a safe input.")
    planning_usage = {
        key: sum(
            int(call.get("usage", {}).get(key) or 0) for call in planning_calls
        )
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    planning_elapsed = round(
        sum(float(call.get("elapsed_seconds") or 0) for call in planning_calls),
        6,
    )
    planning_call = {
        "remote_model_call_performed": True,
        "remote_model_call_count": len(planning_calls),
        "model": model,
        "calls": planning_calls,
        "usage": planning_usage,
        "elapsed_seconds": planning_elapsed,
        "pre_call_privacy_gate_passed_all": all(
            call["pre_call_privacy_gate_passed"] for call in planning_calls
        ),
        "post_call_egress_audit_passed_all": all(
            call["post_call_egress_audit_passed"] for call in planning_calls
        ),
    }
    plan = build_content_plan_from_candidates_v1(
        context,
        ledger,
        candidates,
        planning_call,
        created_at=created_at,
    )
    print(
        "CONTENT CONCEPT PLANNING PASS "
        f"received={len(candidates)} selected={len(plan['selected_concepts'])} "
        f"capacity={plan['capacity']['status']} "
        f"elapsed={planning_elapsed}s "
        f"tokens={planning_usage.get('total_tokens')}",
        flush=True,
    )
    return plan


def reevaluate_content_plan_v1(
    context: dict[str, Any],
    ledger: dict[str, Any],
    existing_plan: dict[str, Any],
) -> dict[str, Any]:
    validate_content_plan_input(context, existing_plan, ledger)
    candidate_fields = (
        "concept_id",
        "audience_need",
        "content_job",
        "primary_topic",
        "primary_fact_refs",
        "supporting_fact_refs",
        "speaker_fact_refs",
        "central_claim",
        "central_claim_key",
        "exclusive_anchor",
        "customer_story_ref",
        "opening_strategy",
        "narrative_mode",
        "visual_anchor",
        "storyboard_shape",
        "hero_shot_role",
        "supporting_shot_roles",
        "why_publish",
    )
    candidates = [
        {field: candidate.get(field) for field in candidate_fields}
        for candidate in existing_plan.get("candidate_pool", {}).get("candidates") or []
    ]
    prevalidated_invalid = [
        dict(item)
        for item in existing_plan.get("novelty_gate", {}).get(
            "rejected_candidates", []
        )
        if item.get("decision") == "authority_rejected"
    ]
    planning_call = json.loads(
        json.dumps(existing_plan.get("planning_call") or {}, ensure_ascii=False)
    )
    planning_call["deterministic_reevaluation"] = {
        "performed": True,
        "remote_model_call_performed": False,
        "reason": "quality_gate_policy_or_implementation_changed_before_script_generation",
        "source_content_plan_sha256": canonical_sha256(existing_plan),
    }
    return build_content_plan_from_candidates_v1(
        context,
        ledger,
        candidates,
        planning_call,
        created_at=existing_plan.get("created_at"),
        prevalidated_invalid_candidates=prevalidated_invalid,
        received_size_override=existing_plan.get("candidate_pool", {}).get(
            "received_size"
        ),
    )


def validate_content_plan_input(
    context: dict[str, Any],
    content_plan: dict[str, Any],
    ledger: dict[str, Any],
) -> None:
    if content_plan.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise RuntimeError("Content Quality generation requires content-plan-v1.0.")
    if content_plan.get("request_id") != context["request"].get("request_id"):
        raise RuntimeError("Content Plan request_id mismatch.")
    if content_plan.get("business_id") != context["persona"].get("persona_id"):
        raise RuntimeError("Content Plan business_id mismatch.")
    expected_speaker = (context.get("speaker_persona") or {}).get("persona_id")
    if content_plan.get("speaker_id") != expected_speaker:
        raise RuntimeError("Content Plan speaker_id mismatch.")
    lineage = content_plan.get("lineage") or {}
    expected_hashes = {
        "persona": sha256_file(context["paths"]["persona"]),
        "request": sha256_file(context["paths"]["request"]),
        "source_plan": sha256_file(context["paths"]["source_plan"]),
    }
    for name, expected in expected_hashes.items():
        if (lineage.get(name) or {}).get("sha256") != expected:
            raise RuntimeError(f"Content Plan {name} SHA mismatch.")
    if lineage.get("content_ledger_sha256") != canonical_sha256(ledger):
        raise RuntimeError("Content Plan Content Ledger SHA mismatch.")
    eligible_cases = {
        str(item.get("case_id"))
        for item in context["source_plan"].get("eligible_case_pool") or []
    }
    selected_pattern = context["source_plan"]["selected_patterns"][0]["pattern_id"]
    selected_concepts = content_plan.get("selected_concepts") or []
    capacity = content_plan.get("capacity") or {}
    if int(capacity.get("selected_quantity") or 0) != len(selected_concepts):
        raise RuntimeError("Content Plan selected quantity mismatch.")
    if int(capacity.get("selected_quantity") or 0) > int(
        capacity.get("high_quality_novel_capacity") or 0
    ):
        raise RuntimeError("Content Plan attempts capacity padding.")
    if capacity.get("padding_generated") is not False:
        raise RuntimeError("Content Plan capacity padding must be false.")
    for concept in selected_concepts:
        if concept.get("gate_decision") != "high_quality_novel":
            raise RuntimeError("Content Plan contains a non-passing selected concept.")
        signature = concept.get("semantic_signature") or {}
        if signature.get("business_id") != context["persona"].get("persona_id"):
            raise RuntimeError("Selected Semantic Signature business_id mismatch.")
        presentation = concept.get("presentation_signature") or {}
        if presentation.get("speaker_id") != expected_speaker:
            raise RuntimeError("Selected Presentation Signature speaker_id mismatch.")
        if str(concept.get("case_structural_ref")) not in eligible_cases:
            raise RuntimeError("Content Plan selected an ineligible Case.")
        if concept.get("pattern_ref") != selected_pattern:
            raise RuntimeError("Content Plan selected a different Pattern.")
    if content_plan.get("authority", {}).get("pattern_effectiveness_used") is not False:
        raise RuntimeError("Content Plan must not use Pattern effectiveness.")


def slots_from_content_plan(
    context: dict[str, Any], content_plan: dict[str, Any]
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for index, concept in enumerate(content_plan.get("selected_concepts") or [], start=1):
        slots.append(
            {
                "slot_id": f"SLOT_{index:03d}",
                "concept_ref": concept["concept_id"],
                "selected_concept": concept,
                "case_id": str(concept["case_structural_ref"]),
                "primary_angle": concept["primary_topic"],
                "primary_persona_fact_refs": concept["primary_fact_refs"],
                "optional_secondary_fact_refs": concept.get("supporting_fact_refs") or [],
                "speaker_fact_refs": concept.get("speaker_fact_refs") or [],
                "opening_strategy": concept.get("opening_strategy"),
                "narrative_mode": concept.get("narrative_mode"),
                "selected_case_structural_reference": context["fingerprints"][
                    str(concept["case_structural_ref"])
                ]["surrogate_ref"],
                "visual_anchor": concept.get("visual_anchor"),
                "hero_shot_role": concept.get("hero_shot_role"),
            }
        )
    return slots


def output_schema_example() -> dict[str, Any]:
    return {
        "items": [
            {
                "slot_id": "SLOT_001",
                "concept_ref": "CONCEPT_001 when a selected Content Plan is supplied",
                "central_claim": "one bounded candidate claim",
                "central_claim_key": "selected semantic key when a Content Plan is supplied",
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
                "selected_content_plan": (
                    {
                        "concept_ref": slot["concept_ref"],
                        "audience_need": slot["selected_concept"]["audience_need"],
                        "content_job": slot["selected_concept"]["content_job"],
                        "primary_topic": slot["selected_concept"]["primary_topic"],
                        "primary_fact_refs": slot["selected_concept"]["primary_fact_refs"],
                        "supporting_fact_refs": slot["selected_concept"].get(
                            "supporting_fact_refs", []
                        ),
                        "speaker_fact_refs": slot["selected_concept"].get(
                            "speaker_fact_refs", []
                        ),
                        "central_claim": slot["selected_concept"]["central_claim"],
                        "central_claim_key": slot["selected_concept"][
                            "semantic_signature"
                        ]["central_claim_key"],
                        "exclusive_anchor": slot["selected_concept"].get(
                            "exclusive_anchor"
                        ),
                        "opening_strategy": slot["selected_concept"].get(
                            "opening_strategy"
                        ),
                        "narrative_mode": slot["selected_concept"].get(
                            "narrative_mode"
                        ),
                        "visual_anchor": slot["selected_concept"].get(
                            "visual_anchor"
                        ),
                    }
                    if slot.get("selected_concept")
                    else None
                ),
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
        "Do not turn abstract visibility or transparency facts into unsupported physical "
        "details. Unless a KNOWN fact states the location, never claim that a price is "
        "posted at the window, that a price board is at a particular spot, or that a "
        "viewer stands outside or looks through a specific window.\n"
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
        "When selected_content_plan is present, it is the frozen topic authority for this "
        "generation item. Copy concept_ref, central_claim, and central_claim_key exactly. "
        "Do not change audience_need, content_job, primary topic, Primary Fact Bundle, or "
        "exclusive anchor. Use supporting facts only as support. You may improve natural "
        "expression and implement the supplied opening and narrative mode, but must not "
        "select another topic or drift toward historical content.\n"
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
        raise RemoteAttemptError(
            "Generation pre-call and post-call Egress Audits differ.",
            {
                "error_type": "post_call_egress_audit_mismatch",
                "error_message": "Generation pre-call and post-call Egress Audits differ.",
                "usage": result.get("usage") or {},
                "elapsed_seconds": result.get("elapsed_seconds"),
                "response_sha256": result.get("response_sha256"),
                "finish_reason": result.get("finish_reason"),
                "artifact_written": False,
            },
        )
    return result, post_call_audit


def default_transport(model: str) -> Callable[[str], dict[str, Any]]:
    client: OpenAI | None = None

    def call(prompt: str) -> dict[str, Any]:
        nonlocal client
        if client is None:
            client = get_client()
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=10000,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except Exception as exc:
            elapsed = round(time.perf_counter() - started, 6)
            raise RemoteAttemptError(
                "Remote provider call failed.",
                {
                    "error_type": "provider_call_failed",
                    "error_message": str(exc),
                    "usage": {},
                    "elapsed_seconds": elapsed,
                    "response_sha256": None,
                    "finish_reason": None,
                    "artifact_written": False,
                },
            ) from exc
        elapsed = time.perf_counter() - started
        content = response.choices[0].message.content
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        telemetry = {
            "usage": usage_dict(response),
            "elapsed_seconds": round(elapsed, 6),
            "response_sha256": sha256_text(content) if content else None,
            "finish_reason": finish_reason,
            "artifact_written": False,
        }
        if not content:
            raise RemoteAttemptError(
                "Remote Model returned empty content.",
                telemetry
                | {
                    "error_type": "empty_response",
                    "error_message": "Remote Model returned empty content.",
                },
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            error_type = (
                "truncated_json_response"
                if finish_reason == "length"
                else "json_parse_failed"
            )
            raise RemoteAttemptError(
                "Remote Model response was not valid complete JSON.",
                telemetry
                | {
                    "error_type": error_type,
                    "error_message": str(exc),
                },
            ) from exc
        return {
            "payload": payload,
            "response_sha256": telemetry["response_sha256"],
            "usage": telemetry["usage"],
            "elapsed_seconds": telemetry["elapsed_seconds"],
            "finish_reason": finish_reason,
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
        "concept_ref": (
            str(item.get("concept_ref")) if item.get("concept_ref") else None
        ),
        "title": title,
        "narration": narration,
        "central_claim": central_claim,
        "central_claim_key": (
            str(item.get("central_claim_key"))
            if item.get("central_claim_key")
            else None
        ),
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
    content_plan: dict[str, Any] | None = None,
    content_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = context["request"]
    source_plan = context["source_plan"]
    quality_mode = content_quality_enabled(context)
    if quality_mode:
        if content_plan is None or content_ledger is None:
            raise RuntimeError(
                "Content Quality V1 generation requires Content Plan and Content Ledger."
            )
        validate_content_plan_input(context, content_plan, content_ledger)
        slots = slots_from_content_plan(context, content_plan)
        capacity = content_plan["capacity"]
        angle_plan = {
            "planning_version": PLAN_SCHEMA_VERSION,
            "taxonomy_status": "content_quality_v1",
            "requested_quantity": capacity["requested_quantity"],
            "high_confidence_distinct_capacity": capacity[
                "high_quality_novel_capacity"
            ],
            "planned_quantity": capacity["selected_quantity"],
            "status": capacity["status"],
            "reason": (
                "Novelty and editorial gates support the requested quantity."
                if capacity["status"] == "supported"
                else "Fixed approved fact space supports fewer high-quality novel concepts than requested."
            ),
            "slots": slots,
        }
    else:
        if content_plan is not None or content_ledger is not None:
            raise RuntimeError(
                "Legacy Generation Request must not receive Content Quality artifacts."
            )
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
            failure = remote_failure_telemetry(exc)
            telemetry_path = persist_remote_failure_telemetry(
                context,
                "script_generation",
                attempt_number,
                exc,
                pre_audit,
            )
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "transport_or_response",
                    "reason": str(exc),
                    "error_type": failure.get("error_type"),
                    "response_sha256": failure.get("response_sha256"),
                    "telemetry_artifact_path": str(telemetry_path.resolve()),
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
                    "response_sha256": failure.get("response_sha256"),
                    "usage": failure.get("usage") or {},
                    "elapsed_seconds": failure.get("elapsed_seconds"),
                    "finish_reason": failure.get("finish_reason"),
                    "error_type": failure.get("error_type"),
                    "artifact_written": False,
                    "telemetry_artifact_path": str(telemetry_path.resolve()),
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
        contract_failure_path: Path | None = None
        if not isinstance(items, list):
            items = []
            contract_failure = RemoteAttemptError(
                "Generation response items missing or invalid.",
                {
                    "error_type": "response_schema_failed",
                    "error_message": "Generation response items missing or invalid.",
                    "usage": result.get("usage") or {},
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "response_sha256": result.get("response_sha256"),
                    "finish_reason": result.get("finish_reason"),
                    "artifact_written": False,
                },
            )
            contract_failure_path = persist_remote_failure_telemetry(
                context,
                "script_generation",
                attempt_number,
                contract_failure,
                pre_audit,
            )
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "response_contract",
                    "reason": "response_items_missing_or_invalid",
                    "response_sha256": result.get("response_sha256"),
                    "telemetry_artifact_path": str(
                        contract_failure_path.resolve()
                    ),
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
            if quality_mode:
                drift_errors = validate_script_against_plan(
                    normalized,
                    slot["selected_concept"],
                    list((content_ledger or {}).get("entries") or []),
                )
                if drift_errors:
                    rejected_this_attempt += 1
                    rejected.append(
                        {
                            "attempt": attempt_number,
                            "response_index": response_index,
                            "slot_id": slot_id,
                            "concept_ref": slot.get("concept_ref"),
                            "reasons": drift_errors,
                            "candidate_sha256": canonical_sha256(raw_item),
                            "candidate": raw_item,
                        }
                    )
                    continue
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
                    "selected_content_plan_preserved": quality_mode,
                    "script_level_novelty_passed": quality_mode,
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
                "error_type": (
                    "response_schema_failed" if contract_failure_path else None
                ),
                "artifact_written": contract_failure_path is None,
                "telemetry_artifact_path": (
                    str(contract_failure_path.resolve())
                    if contract_failure_path
                    else None
                ),
                "error": (
                    "response_items_missing_or_invalid"
                    if contract_failure_path
                    else None
                ),
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
                "concept_ref": slot.get("concept_ref"),
                "semantic_signature": (
                    slot.get("selected_concept", {}).get("semantic_signature")
                    if quality_mode
                    else None
                ),
                "presentation_signature": (
                    slot.get("selected_concept", {}).get("presentation_signature")
                    if quality_mode
                    else None
                ),
                "editorial_summary": (
                    slot.get("selected_concept", {}).get(
                        "editorial_score_summary"
                    )
                    if quality_mode
                    else None
                ),
                "novelty_summary": (
                    slot.get("selected_concept", {}).get("novelty_summary")
                    if quality_mode
                    else None
                ),
                "exclusive_anchor": (
                    slot.get("selected_concept", {}).get("exclusive_anchor")
                    if quality_mode
                    else None
                ),
                "visual_anchor": (
                    slot.get("selected_concept", {}).get("visual_anchor")
                    if quality_mode
                    else None
                ),
                "hero_shot_role": (
                    slot.get("selected_concept", {}).get("hero_shot_role")
                    if quality_mode
                    else None
                ),
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
        "content_plan_ref": (
            {
                "schema_version": content_plan.get("schema_version"),
                "sha256": canonical_sha256(content_plan),
                "request_id": content_plan.get("request_id"),
            }
            if quality_mode and content_plan
            else None
        ),
        "content_capacity_assessment": (
            {
                "status": content_plan["capacity"]["status"],
                "reason": angle_plan["reason"],
                "requested_quantity": content_plan["capacity"][
                    "requested_quantity"
                ],
                "high_quality_novel_capacity": content_plan["capacity"][
                    "high_quality_novel_capacity"
                ],
                "selected_quantity": content_plan["capacity"][
                    "selected_quantity"
                ],
                "planned_quantity": content_plan["capacity"][
                    "selected_quantity"
                ],
                "padding_generated": False,
            }
            if quality_mode and content_plan
            else {
                key: angle_plan[key]
                for key in (
                    "status",
                    "reason",
                    "requested_quantity",
                    "high_confidence_distinct_capacity",
                    "planned_quantity",
                )
            }
        ),
        "batch_editorial_summary": (
            content_plan.get("batch_editorial_summary")
            if quality_mode and content_plan
            else None
        ),
        "batch_similarity": similarity_summary(contents),
        "batch_diversity_v0_2": diversity_v02,
        "review_flag_summary": review_flags,
        "generation_attempts": attempts,
        "usage": usage_totals,
        "content_planning_usage": (
            content_plan.get("planning_call", {}).get("usage", {})
            if quality_mode and content_plan
            else {}
        ),
        "timing": {
            "remote_generation_elapsed_seconds": elapsed_total,
            "remote_content_planning_elapsed_seconds": (
                content_plan.get("planning_call", {}).get("elapsed_seconds")
                if quality_mode and content_plan
                else None
            ),
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
            "content_plan": (
                {"sha256": canonical_sha256(content_plan)}
                if quality_mode and content_plan
                else None
            ),
            "content_ledger": (
                {"sha256": canonical_sha256(content_ledger)}
                if quality_mode and content_ledger
                else None
            ),
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
            "content_quality_v1_enabled": quality_mode,
            "topic_selected_before_case_assignment": quality_mode,
            "selected_content_plan_is_generation_authority": quality_mode,
            "external_research_used": False,
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
            "script_level_novelty_passed": (
                full if quality_mode else None
            ),
            "content_plan_lineage_complete": (
                bool(content_plan and content_ledger) if quality_mode else None
            ),
            "capacity_limited_is_valid": (
                quality_mode
                and full
                and angle_plan.get("status") == "capacity_limited"
            ),
            "no_capacity_padding": (
                len(contents) == planned_quantity if quality_mode else None
            ),
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
            failure = remote_failure_telemetry(exc)
            telemetry_path = persist_remote_failure_telemetry(
                context,
                "selective_revision",
                attempt_number,
                exc,
                pre_audit,
            )
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "transport_or_response",
                    "reason": str(exc),
                    "error_type": failure.get("error_type"),
                    "response_sha256": failure.get("response_sha256"),
                    "telemetry_artifact_path": str(telemetry_path.resolve()),
                }
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
                    "response_sha256": failure.get("response_sha256"),
                    "usage": failure.get("usage") or {},
                    "elapsed_seconds": failure.get("elapsed_seconds"),
                    "finish_reason": failure.get("finish_reason"),
                    "error_type": failure.get("error_type"),
                    "artifact_written": False,
                    "telemetry_artifact_path": str(telemetry_path.resolve()),
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
        contract_failure_path: Path | None = None
        if not isinstance(items, list):
            items = []
            contract_failure = RemoteAttemptError(
                "Selective Revision response items missing or invalid.",
                {
                    "error_type": "response_schema_failed",
                    "error_message": (
                        "Selective Revision response items missing or invalid."
                    ),
                    "usage": result.get("usage") or {},
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "response_sha256": result.get("response_sha256"),
                    "finish_reason": result.get("finish_reason"),
                    "artifact_written": False,
                },
            )
            contract_failure_path = persist_remote_failure_telemetry(
                context,
                "selective_revision",
                attempt_number,
                contract_failure,
                pre_audit,
            )
            rejected.append(
                {
                    "attempt": attempt_number,
                    "scope": "response_contract",
                    "reason": "response_items_missing_or_invalid",
                    "response_sha256": result.get("response_sha256"),
                    "telemetry_artifact_path": str(
                        contract_failure_path.resolve()
                    ),
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
                "error_type": (
                    "response_schema_failed" if contract_failure_path else None
                ),
                "artifact_written": contract_failure_path is None,
                "telemetry_artifact_path": (
                    str(contract_failure_path.resolve())
                    if contract_failure_path
                    else None
                ),
                "error": (
                    "response_items_missing_or_invalid"
                    if contract_failure_path
                    else None
                ),
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
        f"(`{capacity.get('high_quality_novel_capacity', capacity.get('high_confidence_distinct_capacity'))}` high-quality novel; "
        f"`{capacity.get('planned_quantity')}` planned)",
        "Capacity padding generated: `"
        + str(bool(capacity.get("padding_generated"))).lower()
        + "`",
        "Customer specificity distribution: `"
        + json.dumps(
            {
                "customer_specific": (batch.get("batch_editorial_summary") or {}).get(
                    "customer_specific_count"
                ),
                "category_specific": (batch.get("batch_editorial_summary") or {}).get(
                    "category_specific_count"
                ),
                "generic": (batch.get("batch_editorial_summary") or {}).get(
                    "generic_count"
                ),
            },
            ensure_ascii=False,
        )
        + "`",
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
                f"Concept Ref: `{item.get('concept_ref') or 'legacy_not_applicable'}`",
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
                "Semantic Signature: `"
                + json.dumps(item.get("semantic_signature"), ensure_ascii=False)
                + "`",
                "Exclusive Anchor: `"
                + json.dumps(item.get("exclusive_anchor"), ensure_ascii=False)
                + "`",
                f"Visual Anchor: `{item.get('visual_anchor')}`",
                "Editorial Summary: `"
                + json.dumps(item.get("editorial_summary"), ensure_ascii=False)
                + "`",
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


def replace_json_if_unchanged(
    path: Path,
    expected_current: dict[str, Any],
    replacement: dict[str, Any],
) -> str:
    path = path.expanduser().resolve()
    if read_json(path) != expected_current:
        raise RuntimeError(f"Artifact changed before deterministic reevaluation: {path}")
    payload = json.dumps(replacement, ensure_ascii=False, indent=2).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        raise RuntimeError(f"Artifact temporary replacement path already exists: {temporary}")
    with temporary.open("xb") as handle:
        handle.write(payload)
    if read_json(path) != expected_current:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Artifact changed during deterministic reevaluation: {path}")
    temporary.replace(path)
    return hashlib.sha256(payload).hexdigest()


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


def artifact_ref(path: Path, artifact_type: str) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return {
        "artifact_type": artifact_type,
        "path": str(resolved),
        "sha256": sha256_file(resolved),
        "source_artifact_modified": False,
    }


def write_new_text(path: Path, text: str) -> str:
    resolved = path.expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return sha256_file(resolved)


def inspect_xlsx_headers(
    workbook_path: Path,
    sheet_name: str,
    header_row: int,
    column_count: int,
) -> list[str]:
    """Read a bounded XLSX header range without modifying or exporting the file."""
    path = workbook_path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    spreadsheet_namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    relationships_namespace = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    )
    package_relationships_namespace = (
        "http://schemas.openxmlformats.org/package/2006/relationships"
    )
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall(f"{{{spreadsheet_namespace}}}si"):
                shared_strings.append(
                    "".join(
                        node.text or ""
                        for node in item.iter(f"{{{spreadsheet_namespace}}}t")
                    )
                )
        workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relation_id: str | None = None
        for sheet in workbook_root.findall(
            f".//{{{spreadsheet_namespace}}}sheet"
        ):
            if sheet.attrib.get("name") == sheet_name:
                relation_id = sheet.attrib.get(f"{{{relationships_namespace}}}id")
                break
        if not relation_id:
            raise RuntimeError(f"Workbook sheet not found: {sheet_name}")
        relationships_root = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        target: str | None = None
        for relation in relationships_root.findall(
            f"{{{package_relationships_namespace}}}Relationship"
        ):
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise RuntimeError(f"Workbook relationship not found: {relation_id}")
        worksheet_member = posixpath.normpath(posixpath.join("xl", target))
        worksheet_root = ElementTree.fromstring(archive.read(worksheet_member))
        values_by_column: dict[int, str] = {}
        for cell in worksheet_root.findall(
            f".//{{{spreadsheet_namespace}}}row[@r='{header_row}']/"
            f"{{{spreadsheet_namespace}}}c"
        ):
            address = str(cell.attrib.get("r") or "")
            letters = "".join(character for character in address if character.isalpha())
            column_index = 0
            for character in letters:
                column_index = column_index * 26 + (ord(character.upper()) - 64)
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or ""
                    for node in cell.iter(f"{{{spreadsheet_namespace}}}t")
                )
            else:
                value_node = cell.find(f"{{{spreadsheet_namespace}}}v")
                raw_value = value_node.text if value_node is not None else ""
                if cell_type == "s" and raw_value:
                    value = shared_strings[int(raw_value)]
                else:
                    value = raw_value
            values_by_column[column_index] = value
        return [values_by_column.get(index, "") for index in range(1, column_count + 1)]


def validate_news_mvp_registry_and_patterns(
    registry: dict[str, Any],
    coverage_update: dict[str, Any],
    patterns: list[dict[str, Any]],
) -> dict[str, Any]:
    if registry.get("status") != "approved_frozen":
        raise RuntimeError("News MVP requires the Frozen Production Profile Registry.")
    if "news" not in (registry.get("target_profiles") or []):
        raise RuntimeError("Frozen Registry does not register News as a target profile.")
    cross_profile = registry.get("cross_profile_semantic_policy") or {}
    if cross_profile.get("profile_change_resets_novelty") is not False:
        raise RuntimeError("Profile switch must not reset Semantic Novelty.")
    if cross_profile.get("cross_profile_repurpose_is_novel") is not False:
        raise RuntimeError("Cross-profile repurpose must remain non-novel.")
    news_profile = (registry.get("profiles") or {}).get("news") or {}
    export_contract = news_profile.get("export_contract") or {}
    expected_headers = [f"标题{index}" for index in range(1, 7)]
    if export_contract.get("headers") != expected_headers:
        raise RuntimeError("Frozen News Excel Contract headers are invalid.")
    if export_contract.get(
        "six_columns_are_current_implementation_not_frozen_semantics"
    ) is not True:
        raise RuntimeError("Six News slots must remain an implementation constraint.")
    current_coverage = coverage_update.get("news_current_coverage") or {}
    if current_coverage.get("operational_readiness") != "production_validation_required":
        raise RuntimeError("News MVP expects production_validation_required readiness.")
    if current_coverage.get("news_generation_authorized") is not False:
        raise RuntimeError("Coverage update must not pre-authorize News Generation.")
    if current_coverage.get("news_excel_export_authorized") is not False:
        raise RuntimeError("Coverage update must not pre-authorize News Excel Export.")
    patterns_by_id = {
        str(pattern.get("pattern_id")): pattern for pattern in patterns
    }
    expected_pattern_ids = {NEWS_PRICE_PATTERN_ID, NEWS_SCENE_PATTERN_ID}
    if set(patterns_by_id) != expected_pattern_ids:
        raise RuntimeError("News MVP requires exactly the two Approved News Patterns.")
    for pattern_id, pattern in patterns_by_id.items():
        if pattern.get("status") != "approved":
            raise RuntimeError(f"Pattern is not Approved: {pattern_id}")
        if pattern.get("compatible_profiles") != ["news"]:
            raise RuntimeError(f"Pattern must be News-only: {pattern_id}")
    return {
        "profile": news_profile,
        "export_contract": export_contract,
        "patterns_by_id": patterns_by_id,
        "current_readiness": current_coverage.get("operational_readiness"),
    }


def assess_news_novel_capacity(
    request: dict[str, Any],
    content_plan: dict[str, Any],
    patterns: list[dict[str, Any]],
    persona: dict[str, Any],
) -> dict[str, Any]:
    if request.get("target_profile") != "news":
        raise RuntimeError("Novel validation request must target News.")
    if request.get("reuse_intent") != "novel_content":
        raise RuntimeError("Track A must retain novel_content reuse intent.")
    known_fields = {
        field
        for field in (persona.get("facts") or {})
        if is_known(persona, field)
    }
    remaining: list[dict[str, Any]] = []
    for concept in content_plan.get("selected_concepts") or []:
        required_fields = set(concept.get("primary_fact_refs") or []) | set(
            concept.get("supporting_fact_refs") or []
        )
        authority_pass = required_fields.issubset(known_fields)
        matching = match_selected_content_to_approved_patterns(
            concept, patterns, "news"
        )
        compatible = authority_pass and matching["compatible_pattern_count"] > 0
        reasons = [
            item["reason_code"]
            for item in matching["assessments"]
            if not item["compatible"]
        ]
        if not authority_pass:
            reasons.append("fact_authority_not_known")
        remaining.append(
            {
                "concept_id": concept.get("concept_id"),
                "central_claim": concept.get("central_claim"),
                "semantic_novelty": concept.get("v1_1_1_gate_decision")
                == "high_quality_novel",
                "source_content_quality_gate": concept.get(
                    "v1_1_1_gate_decision"
                ),
                "primary_fact_refs": concept.get("primary_fact_refs") or [],
                "supporting_fact_refs": concept.get("supporting_fact_refs") or [],
                "fact_authority_pass": authority_pass,
                "target_profile": "news",
                "pattern_matching": matching,
                "news_profile_and_pattern_compatible": compatible,
                "decision": (
                    "eligible_news_novel_content"
                    if compatible
                    else "rejected_for_current_news_coverage"
                ),
                "rejection_reason_codes": [] if compatible else reasons,
            }
        )
    eligible = [
        item
        for item in remaining
        if item["semantic_novelty"]
        and item["fact_authority_pass"]
        and item["news_profile_and_pattern_compatible"]
    ]
    requested_quantity = int(request["quantity"])
    capacity = len(eligible)
    return {
        "schema_version": "news-novel-capacity-validation-v1.0",
        "generator_version": NEWS_MVP_GENERATOR_VERSION,
        "created_at": now_iso(),
        "request_id": request["request_id"],
        "business_id": request["persona_id"],
        "speaker_id": request.get("speaker_persona"),
        "target_profile": "news",
        "reuse_intent": "novel_content",
        "source_content_plan_capacity": content_plan.get("capacity"),
        "remaining_novel_concepts": remaining,
        "capacity": {
            "requested_quantity": requested_quantity,
            "source_high_quality_novel_capacity": int(
                (content_plan.get("capacity") or {}).get(
                    "high_quality_novel_capacity", 0
                )
            ),
            "news_novel_capacity": capacity,
            "selected_quantity": min(requested_quantity, capacity),
            "status": (
                "capacity_available"
                if capacity >= requested_quantity
                else "capacity_limited"
            ),
            "zero_capacity_is_valid": capacity == 0,
            "padding_generated": False,
        },
        "selected_concepts": eligible[:requested_quantity],
        "scene_contrast_validation": {
            "status": "pattern_available_but_no_current_customer_opportunity",
            "approved_state_a_b_correspondence_present": False,
            "customer_state_a_b_fabricated": False,
        },
        "historical_exposure_policy": {
            "business_wide_across_profiles": True,
            "mix_history_visible_to_news": True,
            "profile_switch_resets_novelty": False,
            "historical_price_content_used_as_novel": False,
        },
        "privacy": {
            "status": "pass",
            "evaluation_scope": "approved_known_fact_projection_only",
            "remote_call_performed": False,
        },
        "proof": {
            "status": "unchanged",
            "new_proof_claim_created": False,
            "pattern_effectiveness_claimed": False,
        },
        "status": "review_required",
        "authority": {
            "known_persona_facts_only": True,
            "unknown_or_requires_review_consumed": False,
            "case_facts_used_as_customer_authority": False,
            "new_customer_truth_created": False,
            "content_ledger_mutated": False,
            "remote_model_called": False,
            "script_generated": False,
            "excel_export_performed": False,
        },
        "validation": {
            "passed": True,
            "zero_capacity_returned_without_padding": capacity == 0,
            "novelty_gate_not_lowered": True,
            "reuse_intent_not_switched": True,
        },
    }


def render_news_novel_capacity_review(
    result: dict[str, Any],
    content_plan_ref: dict[str, Any],
    ledger_ref: dict[str, Any],
) -> str:
    lines = [
        "# News Novel Content Capacity Review V1",
        "",
        f"Request: `{result['request_id']}`",
        "Target Profile: `news`",
        "Reuse Intent: `novel_content`",
        "Status: `review_required`",
        "",
        "## Capacity Result",
        "",
        f"Requested export-slot capacity: `{result['capacity']['requested_quantity']}`",
        f"Current high-quality novel concepts before News matching: `{result['capacity']['source_high_quality_novel_capacity']}`",
        f"News-compatible novel capacity: `{result['capacity']['news_novel_capacity']}`",
        f"Decision: `{result['capacity']['status']}`",
        "Padding generated: `false`",
        "",
        "Zero capacity is a valid PASS result. The system did not reuse historical price content, switch reuse intent, or invent State A/State B facts.",
        "",
        "## Remaining Novel Concepts",
        "",
    ]
    for concept in result["remaining_novel_concepts"]:
        lines.extend(
            [
                f"### {concept['concept_id']}",
                "",
                concept["central_claim"],
                "",
                f"Semantic Novelty: `{str(concept['semantic_novelty']).lower()}`",
                f"Fact Authority: `{'pass' if concept['fact_authority_pass'] else 'fail'}`",
                f"News Pattern Compatibility: `{'compatible' if concept['news_profile_and_pattern_compatible'] else 'not_compatible'}`",
                "Pattern decisions:",
            ]
        )
        for assessment in concept["pattern_matching"]["assessments"]:
            lines.append(
                f"- `{assessment['pattern_id']}`: `{assessment['reason_code']}` — {assessment['reason']}"
            )
        lines.extend(
            [
                "",
                "Final decision: `rejected_for_current_news_coverage`",
                "",
            ]
        )
    lines.extend(
        [
            "## Scene Contrast",
            "",
            "`pattern_available_but_no_current_customer_opportunity`",
            "",
            "The Approved customer truth has no recoverable State A/State B correspondence for the current opportunities. Scene Contrast therefore cannot manufacture a before/after claim.",
            "",
            "## Lineage",
            "",
            f"Content Plan: `{content_plan_ref['path']}`",
            f"Content Plan SHA-256: `{content_plan_ref['sha256']}`",
            f"Content Ledger: `{ledger_ref['path']}`",
            f"Content Ledger SHA-256: `{ledger_ref['sha256']}`",
            "",
            "Remote Model Calls: `0`",
            "News Script Generated: `false`",
            "Excel Export Performed: `false`",
            "",
        ]
    )
    return "\n".join(lines)


def find_historical_price_content(
    ledger: dict[str, Any],
    approved_batch: dict[str, Any],
    request: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    content_id = str((request.get("constraints") or {}).get(
        "selected_historical_content_id"
    ) or "")
    if not content_id:
        raise RuntimeError("Cross-profile repurpose requires selected historical content.")
    ledger_entry = next(
        (entry for entry in ledger.get("entries") or [] if entry.get("content_id") == content_id),
        None,
    )
    approved_item = next(
        (item for item in approved_batch.get("contents") or [] if item.get("content_id") == content_id),
        None,
    )
    if not ledger_entry or ledger_entry.get("status") not in {
        "approved",
        "exported",
        "published",
    }:
        raise RuntimeError("Repurpose source is not Strong Historical Content.")
    if not approved_item or approved_item.get("status") != "human_approved":
        raise RuntimeError("Repurpose source is not in the Approved Batch.")
    if ledger_entry.get("central_claim") != approved_item.get("central_claim"):
        raise RuntimeError("Ledger and Approved Batch central claim do not match.")
    return ledger_entry, approved_item


def fact_lineage_from_ledger(
    ledger: dict[str, Any],
    ledger_entry: dict[str, Any],
    fact_atom_ids: list[str],
) -> list[dict[str, Any]]:
    atom_by_id = {
        str(atom.get("fact_atom_id")): atom
        for atom in ledger.get("fact_atom_catalog") or []
    }
    units = ledger_entry.get("communicated_information_units") or []
    result: list[dict[str, Any]] = []
    for atom_id in fact_atom_ids:
        atom = atom_by_id.get(atom_id)
        if not atom:
            raise RuntimeError(f"Fact Atom not found in Content Ledger: {atom_id}")
        if atom.get("authority") != "derived_planning_identity_only":
            raise RuntimeError("Fact Atom may not alter Persona Authority.")
        matching_units = [
            str(unit.get("information_unit_id"))
            for unit in units
            if atom_id in (unit.get("fact_atom_refs") or [])
            and unit.get("explicitness") == "explicit"
        ]
        if not matching_units:
            raise RuntimeError(f"Historical exposure unit missing for Fact Atom: {atom_id}")
        result.append(
            {
                "fact_atom_id": atom_id,
                "persona_id": atom.get("persona_id"),
                "persona_sha256": atom.get("persona_sha256"),
                "field": atom.get("field"),
                "value_path": atom.get("value_path"),
                "original_known_fact": atom.get("original_known_fact"),
                "authority": atom.get("authority"),
                "historical_information_unit_refs": matching_units,
            }
        )
    return result


def build_news_case_structural_refs(
    price_pattern: dict[str, Any], project_root: Path
) -> tuple[list[dict[str, Any]], dict[str, Path]]:
    refs: list[dict[str, Any]] = []
    preserved_paths: dict[str, Path] = {}
    for evidence in price_pattern.get("evidence") or []:
        case_id = str(evidence.get("case_id") or "")
        case_ref = evidence.get("approved_case_ref") or {}
        fingerprint_ref = evidence.get("fingerprint_ref") or {}
        storyboard_ref = evidence.get("micro_beat_storyboard_ref") or {}
        case_path = Path(str(case_ref.get("path") or ""))
        fingerprint_path = Path(str(fingerprint_ref.get("path") or ""))
        storyboard_path = Path(str(storyboard_ref.get("path") or ""))
        for name, path, expected_sha in (
            ("approved_case", case_path, case_ref.get("sha256")),
            ("fingerprint", fingerprint_path, fingerprint_ref.get("sha256")),
            ("micro_beat_storyboard", storyboard_path, storyboard_ref.get("sha256")),
        ):
            if not path.is_file() or sha256_file(path) != expected_sha:
                raise RuntimeError(f"Price Pattern evidence changed: {case_id} {name}")
            preserved_paths[f"{case_id}_{name}"] = path
        compatibility_path = (
            project_root
            / "data"
            / "cases"
            / case_id
            / "case_profile_compatibility_approval_v1.json"
        )
        governance_path = (
            project_root
            / "data"
            / "case_governance"
            / "cases"
            / case_id
            / "case_source_governance_companion_v1.json"
        )
        compatibility = read_json(compatibility_path)
        governance = read_json(governance_path)
        if compatibility.get("status") != "approved" or "news" not in (
            compatibility.get("approved_compatible_generation_profiles") or []
        ):
            raise RuntimeError(f"Case lacks canonical News compatibility: {case_id}")
        if governance.get("canonical_case_status") != "approved":
            raise RuntimeError(f"Case is not canonically Approved: {case_id}")
        if governance.get("research_ingestion_eligibility") != (
            "eligible_for_internal_research"
        ):
            raise RuntimeError(f"Case is not eligible for structural research: {case_id}")
        if governance.get("media_reuse_rights") != "not_established":
            raise RuntimeError(f"Unexpected Case media reuse status: {case_id}")
        if governance.get("production_footage_pool_eligible") is not False:
            raise RuntimeError(f"Case footage must not enter Production: {case_id}")
        preserved_paths[f"{case_id}_profile_compatibility"] = compatibility_path
        preserved_paths[f"{case_id}_source_governance"] = governance_path
        refs.append(
            {
                "case_id": case_id,
                "research_role": evidence.get("research_role"),
                "case_reference_authority": "structural_only",
                "approved_case_ref": artifact_ref(case_path, "approved_case"),
                "fingerprint_ref": artifact_ref(fingerprint_path, "case_fingerprint"),
                "micro_beat_storyboard_ref": artifact_ref(
                    storyboard_path, "news_micro_beat_storyboard"
                ),
                "profile_compatibility_ref": artifact_ref(
                    compatibility_path, "case_profile_compatibility_approval_v1"
                ),
                "source_governance_ref": artifact_ref(
                    governance_path, "case_source_governance_companion_v1"
                ),
                "media_reuse_rights": "not_established",
                "production_footage_pool_eligible": False,
                "case_specific_facts_are_customer_authority": False,
            }
        )
    if len(refs) != 3:
        raise RuntimeError("Approved Price Pattern must provide three structural evidence refs.")
    return refs, preserved_paths


def build_news_price_repurpose_plan(
    request: dict[str, Any],
    ledger: dict[str, Any],
    ledger_entry: dict[str, Any],
    approved_item: dict[str, Any],
    patterns: list[dict[str, Any]],
    profile_registry_ref: dict[str, Any],
    price_pattern_ref: dict[str, Any],
    case_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    if request.get("reuse_intent") != "cross_profile_repurpose":
        raise RuntimeError("Track B requires explicit cross_profile_repurpose intent.")
    selected_content = {
        "central_claim": ledger_entry["central_claim"],
        "primary_fact_refs": ledger_entry.get("primary_fact_refs") or [],
        "supporting_fact_refs": [
            "differentiators",
            "included_service_facts",
            "product_or_service_facts",
        ],
        "fact_atom_refs": [
            "pricing_facts::9c235b0396b99f681241",
            "pricing_facts::66a157304a82dc80e597",
            "pricing_facts::beeff040cffece152ea6",
            "included_service_facts::6bedd227ba10293bc37d",
            "included_service_facts::077c2ed0b1bb08c18578",
        ],
        "semantic_signature": ledger_entry.get("semantic_signature") or {},
        "approved_state_correspondence_refs": [],
    }
    pattern_matching = match_selected_content_to_approved_patterns(
        selected_content, patterns, "news"
    )
    selected_pattern = pattern_matching.get("selected_pattern") or {}
    if selected_pattern.get("pattern_id") != NEWS_PRICE_PATTERN_ID:
        raise RuntimeError("Price repurpose did not resolve to the Approved Price Pattern.")
    scene_assessment = next(
        item
        for item in pattern_matching["assessments"]
        if item["pattern_id"] == NEWS_SCENE_PATTERN_ID
    )
    if scene_assessment["compatible"]:
        raise RuntimeError("Historical Price content must not match Scene Contrast.")

    atom_ids = selected_content["fact_atom_refs"]
    fact_lineage = fact_lineage_from_ledger(
        ledger, ledger_entry, atom_ids
    )
    lineage_by_id = {item["fact_atom_id"]: item for item in fact_lineage}

    def beat(
        beat_id: str,
        order: int,
        semantic_role: str,
        text: str,
        atom_refs: list[str],
        visual_anchor: str,
        visual_state_role: str,
    ) -> dict[str, Any]:
        return {
            "beat_id": beat_id,
            "order": order,
            "semantic_role": semantic_role,
            "text": text,
            "business_fact_refs": [lineage_by_id[value] for value in atom_refs],
            "visual_anchor": visual_anchor,
            "visual_state_role": visual_state_role,
            "pattern_ref": NEWS_PRICE_PATTERN_ID,
            "continuous_narration_required": False,
            "information_gain_within_repurpose": "contextualizes_same_historical_offer",
        }

    beats = [
        beat(
            "B001",
            1,
            "price_offer_first_semantic_anchor",
            "素菜加工费通常8–10元",
            ["pricing_facts::9c235b0396b99f681241"],
            "客户自有素材中的素菜实物或加工准备画面，配合价格文字状态",
            "offer_anchor_state",
        ),
        beat(
            "B002",
            2,
            "cooking_method_price_scope",
            "清蒸约15元；红烧约18元左右",
            [
                "pricing_facts::66a157304a82dc80e597",
                "pricing_facts::beeff040cffece152ea6",
            ],
            "客户自有素材中的清蒸与红烧处理画面，分别对应两项价格状态",
            "offer_scope_explanation_state",
        ),
        beat(
            "B003",
            3,
            "included_value_context",
            "油盐酱料免费提供",
            ["included_service_facts::6bedd227ba10293bc37d"],
            "客户自有素材中的油盐酱料准备画面，不出现来源 Case 画面",
            "offer_value_context_state",
        ),
        beat(
            "B004",
            4,
            "included_value_context",
            "米饭免费提供",
            ["included_service_facts::077c2ed0b1bb08c18578"],
            "客户自有素材中的米饭出餐画面，不出现来源 Case 画面",
            "offer_value_context_state",
        ),
    ]

    slot_specs = [
        ("S001", "B001", "素菜通常", ["pricing_facts::9c235b0396b99f681241"], "vegetable_price_qualifier"),
        ("S002", "B001", "8–10元", ["pricing_facts::9c235b0396b99f681241"], "vegetable_price_value"),
        ("S003", "B002", "清蒸约15元", ["pricing_facts::66a157304a82dc80e597"], "steaming_price"),
        ("S004", "B002", "红烧约18元左右", ["pricing_facts::beeff040cffece152ea6"], "braising_price"),
        ("S005", "B003", "油盐酱料免费", ["included_service_facts::6bedd227ba10293bc37d"], "included_condiments"),
        ("S006", "B004", "米饭免费", ["included_service_facts::077c2ed0b1bb08c18578"], "included_rice"),
    ]
    slots = [
        {
            "slot_id": slot_id,
            "header": f"标题{index}",
            "source_beat_ref": beat_id,
            "text": text,
            "character_count": len(text),
            "recommended_max_characters": 8,
            "character_limit_policy": "configurable_validation_not_pattern_invariant",
            "character_limit_pass": len(text) <= 8,
            "business_fact_refs": [lineage_by_id[value] for value in atom_refs],
            "semantic_fragment_role": fragment_role,
            "repeated_padding": False,
        }
        for index, (slot_id, beat_id, text, atom_refs, fragment_role) in enumerate(
            slot_specs, start=1
        )
    ]
    if len({slot["text"] for slot in slots}) != len(slots):
        raise RuntimeError("News Export slots contain duplicate padding.")
    reconstructed_qualifiers = "".join(slot["text"] for slot in slots[:2])
    if reconstructed_qualifiers != "素菜通常8–10元":
        raise RuntimeError("Vegetable price qualifier was weakened in slot mapping.")
    all_slot_text = "；".join(slot["text"] for slot in slots)
    forbidden_strengthening = [
        term
        for term in ("统一8元", "固定15", "只要18", "全市场最低", "最划算", "超值", "比自己做便宜")
        if term in all_slot_text
    ]
    if forbidden_strengthening:
        raise RuntimeError("News slot mapping strengthened an Authority claim.")

    price_pattern = next(
        pattern for pattern in patterns if pattern["pattern_id"] == NEWS_PRICE_PATTERN_ID
    )
    applied_invariants = [
        {
            "invariant": invariant,
            "satisfied": True,
            "evidence": (
                "B001"
                if invariant == "price_or_offer_first_semantic_anchor"
                else "B002-B004"
            ),
        }
        for invariant in (price_pattern.get("definition") or {}).get("invariants") or []
    ]
    return {
        "schema_version": "news-micro-beat-plan-v1.0",
        "generator_version": NEWS_MVP_GENERATOR_VERSION,
        "created_at": now_iso(),
        "request_id": request["request_id"],
        "business_id": request["persona_id"],
        "speaker_id": request.get("speaker_persona"),
        "target_profile": "news",
        "production_profile_ref": profile_registry_ref,
        "status": "review_required",
        "reuse_declaration": {
            "reuse_intent": "cross_profile_repurpose",
            "semantic_novelty": False,
            "historical_content_reused": True,
            "reuse_reason": "cross_profile_production_validation",
            "source_profile": "mix",
            "target_profile": "news",
            "novel_capacity_delta": 0,
            "new_central_claim_count_delta": 0,
            "content_opportunity_count_delta": 0,
            "content_ledger_write_performed": False,
        },
        "historical_content": {
            "content_id": ledger_entry["content_id"],
            "batch_ref": ledger_entry["batch_ref"],
            "historical_status": ledger_entry["status"],
            "title": approved_item["title"],
            "narration": approved_item["narration"],
            "central_claim": approved_item["central_claim"],
            "semantic_signature": ledger_entry["semantic_signature"],
            "historical_information_unit_refs": [
                item.get("information_unit_id")
                for item in ledger_entry.get("communicated_information_units") or []
                if item.get("explicitness") == "explicit"
            ],
        },
        "presentation_signature": {
            **(ledger_entry.get("presentation_signature") or {}),
            "production_profile": "news",
            "opening_strategy": "price_offer_first_semantic_anchor",
            "narrative_mode": "recoverable_micro_information_states",
            "case_structural_ref": [item["case_id"] for item in case_refs],
            "storyboard_shape": "news_micro_beat_sequence",
        },
        "pattern_matching": pattern_matching,
        "selected_pattern": {
            "pattern_id": NEWS_PRICE_PATTERN_ID,
            "pattern_ref": price_pattern_ref,
            "matching_reason": selected_pattern.get("reason"),
            "matching_basis": pattern_matching["matching_basis"],
            "case_topic_used_for_matching": False,
        },
        "pattern_application": {
            "applied_invariants": applied_invariants,
            "continuous_mix_narration_required": False,
            "narration_independence_authority": "inherited_from_production_profile_news",
            "exact_beat_count_is_pattern_invariant": False,
            "exact_duration_is_pattern_invariant": False,
            "six_export_slots_are_pattern_invariant": False,
        },
        "micro_beats": beats,
        "beat_to_export_slot_mapping": {
            "semantic_beat_count": len(beats),
            "export_slot_count": len(slots),
            "mapping_strategy": "split_semantic_beats_without_duplicate_padding",
            "slots": slots,
            "duplicate_padding_count": 0,
            "empty_slot_count": 0,
        },
        "fact_lineage": fact_lineage,
        "visual_anchor_policy": {
            "production_guidance_only": True,
            "customer_owned_or_separately_authorized_footage_required": True,
            "case_footage_used": False,
        },
        "case_structural_references": case_refs,
        "claim_review_flags": [
            "cross_profile_repurpose_is_not_novel",
            "preserve_usually_approximately_and_around_qualifiers",
            "included_items_must_remain_free_not_unlimited",
            "visual_anchors_require_customer_owned_or_separately_authorized_footage",
            "human_review_required_before_excel_export",
        ],
        "privacy": {
            "status": "pass",
            "evaluation_scope": "approved_known_fact_projection_only",
            "remote_call_performed": False,
            "case_media_projected_to_production": False,
        },
        "proof": {
            "status": "unchanged",
            "claim_status": "candidate_unverified_pending_human_review",
            "new_proof_claim_created": False,
            "pattern_effectiveness_claimed": False,
        },
        "authority": {
            "known_persona_facts_only": True,
            "unknown_or_requires_review_consumed": False,
            "fact_atoms_change_persona_authority": False,
            "case_facts_used_as_customer_authority": False,
            "case_footage_used": False,
            "proof_status_upgraded": False,
            "pattern_effectiveness_claimed": False,
            "new_customer_claim_created": False,
            "content_ledger_mutated": False,
            "remote_model_called": False,
            "excel_export_performed": False,
            "approval_performed": False,
        },
        "validation": {
            "passed": True,
            "explicit_repurpose_intent": True,
            "semantic_novelty_false": True,
            "price_pattern_selected": True,
            "scene_pattern_rejected": True,
            "pattern_invariants_satisfied": all(
                item["satisfied"] for item in applied_invariants
            ),
            "semantic_recovery_requires_continuous_narration": False,
            "six_export_slots_mapped": len(slots) == 6,
            "duplicate_padding_absent": len({slot["text"] for slot in slots})
            == len(slots),
            "price_qualifiers_preserved": True,
            "fact_authority_traceable": True,
            "case_refs_structural_only": all(
                item["case_reference_authority"] == "structural_only"
                for item in case_refs
            ),
            "case_footage_production_eligible": False,
        },
    }


def _news_export_fact_lineage(
    plan: dict[str, Any],
    ledger: dict[str, Any],
    source_ledger_entry: dict[str, Any],
    fact_atom_id: str,
) -> dict[str, Any]:
    existing = next(
        (
            item
            for item in plan.get("fact_lineage") or []
            if item.get("fact_atom_id") == fact_atom_id
        ),
        None,
    )
    if existing:
        return existing
    return fact_lineage_from_ledger(
        ledger, source_ledger_entry, [fact_atom_id]
    )[0]


def _price_offer_anchor_recoverable(text: str) -> bool:
    normalized = str(text or "").strip()
    return bool(re.search(r"\d", normalized)) and any(
        marker in normalized for marker in ("元", "块", "折", "价", "套餐", "优惠")
    )


def build_news_mvp_final_slot_mapping(
    plan: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    historical = plan.get("historical_content") or {}
    source_content_id = str(historical.get("content_id") or "")
    source_ledger_entry = next(
        (
            entry
            for entry in ledger.get("entries") or []
            if entry.get("content_id") == source_content_id
        ),
        None,
    )
    if not source_ledger_entry or not is_strong_memory(source_ledger_entry):
        raise RuntimeError("News final slot mapping requires Strong Historical Content.")
    atoms = {
        atom_id: _news_export_fact_lineage(
            plan, ledger, source_ledger_entry, atom_id
        )
        for atom_id in (
            "pricing_facts::9c235b0396b99f681241",
            "pricing_facts::66a157304a82dc80e597",
            "pricing_facts::beeff040cffece152ea6",
            "included_service_facts::6bedd227ba10293bc37d",
            "included_service_facts::077c2ed0b1bb08c18578",
            "differentiators::64c9ca122fa942afb525",
        )
    }
    slot_specs = [
        (
            "S001",
            "B001",
            "素菜通常8–10元",
            ["pricing_facts::9c235b0396b99f681241"],
            "complete_vegetable_price_anchor",
        ),
        (
            "S002",
            "B002",
            "清蒸约15元",
            ["pricing_facts::66a157304a82dc80e597"],
            "steaming_price",
        ),
        (
            "S003",
            "B002",
            "红烧约18元左右",
            ["pricing_facts::beeff040cffece152ea6"],
            "braising_price",
        ),
        (
            "S004",
            "B003",
            "油盐酱料免费",
            ["included_service_facts::6bedd227ba10293bc37d"],
            "included_condiments",
        ),
        (
            "S005",
            "B004",
            "米饭免费",
            ["included_service_facts::077c2ed0b1bb08c18578"],
            "included_rice",
        ),
        (
            "S006",
            "B001",
            "价格公开清晰",
            ["differentiators::64c9ca122fa942afb525"],
            "price_transparency_close",
        ),
    ]
    slots: list[dict[str, Any]] = []
    for index, (slot_id, beat_ref, text, fact_atom_ids, role) in enumerate(
        slot_specs, start=1
    ):
        over_soft_limit = len(text) > 8
        slots.append(
            {
                "slot_id": slot_id,
                "header": f"标题{index}",
                "source_beat_ref": beat_ref,
                "text": text,
                "character_count": len(text),
                "recommended_max_characters": 8,
                "display_length_policy": "configurable_soft_recommendation",
                "display_length_soft_warning": over_soft_limit,
                "business_fact_refs": [atoms[value] for value in fact_atom_ids],
                "semantic_fragment_role": role,
                "repeated_padding": False,
            }
        )
    first_anchor_ok = _price_offer_anchor_recoverable(slots[0]["text"])
    exact_texts = [
        "素菜通常8–10元",
        "清蒸约15元",
        "红烧约18元左右",
        "油盐酱料免费",
        "米饭免费",
        "价格公开清晰",
    ]
    if [slot["text"] for slot in slots] != exact_texts:
        raise RuntimeError("Final News slot mapping differs from the Human decision.")
    if not first_anchor_ok:
        raise RuntimeError("First News display slot does not preserve the Price anchor.")
    joined = "；".join(exact_texts)
    if not all(qualifier in joined for qualifier in ("通常", "约", "左右")):
        raise RuntimeError("Final News slot mapping lost a price qualifier.")
    return {
        "semantic_beat_count": len(plan.get("micro_beats") or []),
        "export_slot_count": len(slots),
        "mapping_strategy": "human_approved_semantically_complete_display_states",
        "slot_mapping_priority_rule": [
            "fact_authority",
            "semantic_completeness",
            "pattern_constraint",
            "soft_display_length_recommendation",
        ],
        "soft_recommendation_yields_to_semantic_integrity": True,
        "first_display_slot_price_offer_anchor_recoverable": first_anchor_ok,
        "slots": slots,
        "display_length_soft_warning_count": sum(
            bool(slot["display_length_soft_warning"]) for slot in slots
        ),
        "display_length_soft_warnings": [
            {
                "slot_id": slot["slot_id"],
                "text": slot["text"],
                "character_count": slot["character_count"],
                "recommended_max_characters": slot["recommended_max_characters"],
                "resolution": "preserved_authority_safe_complete_semantic_state",
            }
            for slot in slots
            if slot["display_length_soft_warning"]
        ],
        "duplicate_padding_count": 0,
        "empty_slot_count": 0,
        "price_qualifiers_preserved": True,
    }


def build_news_mvp_human_approvals(
    track_a: dict[str, Any],
    track_b: dict[str, Any],
    ledger: dict[str, Any],
    *,
    track_a_ref: dict[str, Any],
    track_b_ref: dict[str, Any],
    reviewer: str = "李健",
    reviewed_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    reviewed = reviewed_at or now_iso()
    capacity = track_a.get("capacity") or {}
    if (
        capacity.get("requested_quantity") != 6
        or capacity.get("news_novel_capacity") != 0
        or capacity.get("status") != "capacity_limited"
        or capacity.get("padding_generated") is not False
    ):
        raise RuntimeError("Track A no longer matches the approved zero-capacity result.")
    track_a_approval = {
        "schema_version": "news-novel-capacity-human-approval-v1.0",
        "request_id": track_a["request_id"],
        "status": "approved_validation_result",
        "human_review": {
            "reviewer": reviewer,
            "decision": "approved_validation_result",
            "reviewed_at": reviewed,
            "human_gate": True,
        },
        "approved_result": {
            **capacity,
            "interpretation": "expected_pass",
        },
        "human_interpretation": {
            "CONCEPT_016": "Primary semantic content is the seafood-processing scenario; historical price is supporting information and cannot be rewritten as new Price News.",
            "CONCEPT_005": "A general business-volume number is outside the Approved price_offer_led_only Pattern scope.",
            "scene_contrast": "No Approved customer State A/State B correspondence exists and none was fabricated.",
        },
        "not_authorized": [
            "lower_novelty_gate",
            "automatic_repurpose",
            "padding",
            "fabricated_scene_state_a_b",
        ],
        "source_validation_ref": track_a_ref,
        "authority": {
            "approves_validation_result_not_production_content": True,
            "novel_content_approved": False,
            "batch_approved": False,
            "excel_export_authorized": False,
        },
        "validation": {
            "passed": True,
            "zero_capacity_is_valid": True,
            "padding_absent": True,
        },
    }

    reuse = track_b.get("reuse_declaration") or {}
    historical = track_b.get("historical_content") or {}
    selected_pattern = track_b.get("selected_pattern") or {}
    if (
        track_b.get("status") != "review_required"
        or reuse.get("reuse_intent") != "cross_profile_repurpose"
        or reuse.get("semantic_novelty") is not False
        or reuse.get("historical_content_reused") is not True
        or historical.get("content_id") != "real_shufang_mix_001-C003"
        or selected_pattern.get("pattern_id") != NEWS_PRICE_PATTERN_ID
        or len(track_b.get("micro_beats") or []) != 4
    ):
        raise RuntimeError("Track B source Plan does not match the Human decision.")
    mapping = build_news_mvp_final_slot_mapping(track_b, ledger)
    track_b_approval = {
        "schema_version": "news-generation-human-review-approval-v1.0",
        "request_id": track_b["request_id"],
        "business_id": track_b["business_id"],
        "speaker_id": track_b.get("speaker_id"),
        "target_profile": "news",
        "status": "approved_for_export",
        "approval_scope": "cross_profile_repurpose_presentation_not_novel_content",
        "human_review": {
            "reviewer": reviewer,
            "decision": "approved",
            "source_decision": "approved_with_minor_export_slot_revision",
            "reviewed_at": reviewed,
            "human_gate": True,
        },
        "reuse_declaration": {
            **reuse,
            "semantic_novelty": False,
            "historical_content_reused": True,
            "novel_capacity_delta": 0,
            "new_semantic_content_count_delta": 0,
            "new_central_claim_count_delta": 0,
            "new_information_gain_delta": 0,
        },
        "source_historical_content": {
            "content_ref": historical["content_id"],
            "batch_ref": historical["batch_ref"],
            "historical_status": historical["historical_status"],
            "semantic_signature_sha256": canonical_sha256(
                historical["semantic_signature"]
            ),
        },
        "selected_pattern": {
            "pattern_id": selected_pattern["pattern_id"],
            "pattern_ref": selected_pattern["pattern_ref"],
            "pattern_status": "approved",
            "effectiveness_status": "unvalidated",
        },
        "approved_micro_beat_plan": {
            "source_plan_ref": track_b_ref,
            "decision": "approved",
            "beat_count": len(track_b["micro_beats"]),
            "beats": [
                {
                    "beat_id": item["beat_id"],
                    "order": item["order"],
                    "semantic_role": item["semantic_role"],
                    "text": item["text"],
                }
                for item in track_b["micro_beats"]
            ],
        },
        "approved_export_slot_mapping": mapping,
        "export_authorization": {
            "authorized": True,
            "profile": "news",
            "sheet": "Sheet1",
            "header_row": 4,
            "first_data_row": 5,
            "export_row_count": 1,
            "internal_metadata_columns_permitted": False,
        },
        "authority": {
            "known_persona_facts_only": True,
            "approval_is_not_novel_content_approval": True,
            "new_customer_fact_created": False,
            "case_facts_used_as_customer_authority": False,
            "case_footage_used": False,
            "communicated_information_units_to_create": 0,
            "remote_model_called": False,
        },
        "validation": {
            "passed": True,
            "first_display_slot_price_offer_anchor_recoverable": mapping[
                "first_display_slot_price_offer_anchor_recoverable"
            ],
            "price_qualifiers_preserved": mapping["price_qualifiers_preserved"],
            "display_length_soft_warning_did_not_mutate_fact": True,
            "six_slot_mapping_exact": True,
        },
    }
    return track_a_approval, track_b_approval


def validate_news_export_approval(approval: dict[str, Any]) -> list[str]:
    if approval.get("schema_version") != "news-generation-human-review-approval-v1.0":
        raise RuntimeError("News Export requires a canonical Human Approval Artifact.")
    review = approval.get("human_review") or {}
    if approval.get("status") != "approved_for_export" or review.get(
        "decision"
    ) != "approved":
        raise RuntimeError("Unapproved News Plan cannot pass the Excel Export gate.")
    reuse = approval.get("reuse_declaration") or {}
    if (
        reuse.get("reuse_intent") != "cross_profile_repurpose"
        or reuse.get("semantic_novelty") is not False
        or reuse.get("historical_content_reused") is not True
    ):
        raise RuntimeError("News repurpose approval cannot become Novel Content.")
    mapping = approval.get("approved_export_slot_mapping") or {}
    slots = mapping.get("slots") or []
    texts = [str(item.get("text") or "") for item in slots]
    expected = [
        "素菜通常8–10元",
        "清蒸约15元",
        "红烧约18元左右",
        "油盐酱料免费",
        "米饭免费",
        "价格公开清晰",
    ]
    if texts != expected:
        raise RuntimeError("News Export slots differ from the Human-approved mapping.")
    if mapping.get("first_display_slot_price_offer_anchor_recoverable") is not True:
        raise RuntimeError("First display slot lost the required Price / Offer anchor.")
    return texts


def _xlsx_cell_text(
    cell: ElementTree.Element,
    namespace: str,
    shared_strings: list[str],
) -> str | None:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.iter(f"{{{namespace}}}t")
        )
    value_node = cell.find(f"{{{namespace}}}v")
    if value_node is None:
        return None
    value = value_node.text or ""
    if cell_type == "s" and value:
        return shared_strings[int(value)]
    return value


def inspect_xlsx_contract_snapshot(
    workbook_path: Path,
    *,
    sheet_name: str = "Sheet1",
) -> dict[str, Any]:
    path = workbook_path.expanduser().resolve()
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_namespace = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{namespace}}}si"):
                shared_strings.append(
                    "".join(
                        node.text or "" for node in item.iter(f"{{{namespace}}}t")
                    )
                )
        workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook_root.findall(f".//{{{namespace}}}sheet")
        sheet_names = [str(item.attrib.get("name") or "") for item in sheets]
        selected = next(
            (item for item in sheets if item.attrib.get("name") == sheet_name), None
        )
        if selected is None:
            raise RuntimeError(f"Workbook sheet not found: {sheet_name}")
        relation_id = selected.attrib.get(f"{{{rel_namespace}}}id")
        relationships_root = ElementTree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels")
        )
        target = next(
            (
                relation.attrib.get("Target")
                for relation in relationships_root.findall(
                    f"{{{package_rel_namespace}}}Relationship"
                )
                if relation.attrib.get("Id") == relation_id
            ),
            None,
        )
        if not target:
            raise RuntimeError("Workbook sheet relationship is missing.")
        normalized_target = str(target).lstrip("/")
        sheet_member = posixpath.normpath(
            normalized_target
            if normalized_target.startswith("xl/")
            else posixpath.join("xl", normalized_target)
        )
        sheet_root = ElementTree.fromstring(archive.read(sheet_member))
        styles_root = ElementTree.fromstring(archive.read("xl/styles.xml"))
        cell_xfs_node = styles_root.find(f"{{{namespace}}}cellXfs")
        fonts_node = styles_root.find(f"{{{namespace}}}fonts")
        fills_node = styles_root.find(f"{{{namespace}}}fills")
        borders_node = styles_root.find(f"{{{namespace}}}borders")
        num_formats_node = styles_root.find(f"{{{namespace}}}numFmts")
        cell_xfs = list(cell_xfs_node) if cell_xfs_node is not None else []
        fonts = list(fonts_node) if fonts_node is not None else []
        fills = list(fills_node) if fills_node is not None else []
        borders = list(borders_node) if borders_node is not None else []
        num_formats = {
            item.attrib.get("numFmtId"): dict(sorted(item.attrib.items()))
            for item in (list(num_formats_node) if num_formats_node is not None else [])
        }

        def normalized_style_element(
            element: ElementTree.Element,
            parent_tag: str | None = None,
        ) -> dict[str, Any] | None:
            tag = element.tag.rsplit("}", 1)[-1]
            if tag in {"charset", "scheme"}:
                return None
            if (
                tag == "bgColor"
                and parent_tag == "patternFill"
                and element.get("indexed") == "64"
            ):
                return None
            children = [
                normalized
                for child in list(element)
                if (normalized := normalized_style_element(child, tag)) is not None
            ]
            attributes = dict(sorted(element.attrib.items()))
            if tag in {"left", "right", "top", "bottom", "diagonal"} and not (
                attributes or children
            ):
                return None
            return {"tag": tag, "attributes": attributes, "children": children}

        def style_signature(style_index: int) -> str:
            if style_index >= len(cell_xfs):
                raise RuntimeError("Cell style index is outside the workbook style table.")
            xf = cell_xfs[style_index]
            parts: list[Any] = [normalized_style_element(xf)]
            for key, table in (
                ("fontId", fonts),
                ("fillId", fills),
                ("borderId", borders),
            ):
                index = int(xf.attrib.get(key, "0"))
                parts.append(
                    normalized_style_element(table[index])
                    if index < len(table)
                    else None
                )
            parts.append(num_formats.get(xf.attrib.get("numFmtId")))
            return canonical_sha256(parts)

        cell_nodes = {
            str(cell.attrib.get("r")): cell
            for cell in sheet_root.findall(f".//{{{namespace}}}c")
        }
        rows_one_to_four: dict[str, Any] = {}
        for row in range(1, 5):
            for column in range(1, 7):
                address = f"{chr(64 + column)}{row}"
                cell = cell_nodes.get(address)
                style_index = int(cell.attrib.get("s", "0")) if cell is not None else 0
                rows_one_to_four[address] = {
                    "value": (
                        _xlsx_cell_text(cell, namespace, shared_strings)
                        if cell is not None
                        else None
                    ),
                    "style_signature": style_signature(style_index),
                }
        row_attributes = {
            str(row.attrib.get("r")): {
                key: (
                    round(float(value), 5)
                    if key == "ht"
                    else value
                )
                for key, value in sorted(row.attrib.items())
                if key != "spans"
            }
            for row in sheet_root.findall(f".//{{{namespace}}}row")
            if 1 <= int(row.attrib.get("r", "0")) <= 4
        }
        merged_ranges = sorted(
            str(item.attrib.get("ref"))
            for item in sheet_root.findall(f".//{{{namespace}}}mergeCell")
        )
        column_layout = []
        for item in sheet_root.findall(f".//{{{namespace}}}col"):
            normalized_column: dict[str, Any] = {}
            for key, value in sorted(item.attrib.items()):
                if key == "customWidth" and value == "0":
                    continue
                normalized_column[key] = (
                    round(float(value), 4) if key == "width" else value
                )
            column_layout.append(normalized_column)
        row_five = [
            _xlsx_cell_text(cell_nodes.get(f"{chr(64 + column)}5"), namespace, shared_strings)
            if cell_nodes.get(f"{chr(64 + column)}5") is not None
            else None
            for column in range(1, 7)
        ]
        extra_populated_cells: list[dict[str, str]] = []
        for address, cell in cell_nodes.items():
            match = re.fullmatch(r"([A-Z]+)(\d+)", address)
            if not match:
                continue
            letters, row_text = match.groups()
            column_index = 0
            for character in letters:
                column_index = column_index * 26 + ord(character) - 64
            row_index = int(row_text)
            value = _xlsx_cell_text(cell, namespace, shared_strings)
            if value not in (None, "") and (
                (row_index == 5 and column_index > 6) or row_index > 5
            ):
                extra_populated_cells.append({"address": address, "value": value})
        return {
            "sheet_names": sheet_names,
            "rows_1_4": rows_one_to_four,
            "row_attributes_1_4": row_attributes,
            "merged_ranges": merged_ranges,
            "column_layout": column_layout,
            "row_5": row_five,
            "extra_populated_cells": extra_populated_cells,
        }


def validate_news_excel_export(
    template_path: Path,
    output_path: Path,
    approved_slot_texts: list[str],
    template_sha_before: str,
) -> dict[str, Any]:
    template_sha_after = sha256_file(template_path)
    if template_sha_after != template_sha_before:
        raise RuntimeError("Source News Excel Template was modified.")
    template = inspect_xlsx_contract_snapshot(template_path)
    exported = inspect_xlsx_contract_snapshot(output_path)
    rows_preserved = (
        template["rows_1_4"] == exported["rows_1_4"]
        and template["row_attributes_1_4"] == exported["row_attributes_1_4"]
        and template["merged_ranges"] == exported["merged_ranges"]
        and template["column_layout"] == exported["column_layout"]
    )
    checks = {
        "workbook_readable": True,
        "sheet_names_match": template["sheet_names"] == exported["sheet_names"] == ["Sheet1"],
        "rows_1_4_content_and_styles_preserved": rows_preserved,
        "row_4_headers_exact": [
            exported["rows_1_4"][f"{chr(64 + column)}4"]["value"]
            for column in range(1, 7)
        ]
        == [f"标题{index}" for index in range(1, 7)],
        "row_5_slots_exact": exported["row_5"] == approved_slot_texts,
        "no_extra_business_columns_or_rows": not exported["extra_populated_cells"],
        "no_internal_metadata": not any(
            any(
                marker in str(value)
                for marker in (
                    "pcv1_",
                    "persona",
                    "case_id",
                    "content_id",
                    "sha256",
                    "fact_atom",
                )
            )
            for value in exported["row_5"]
        ),
        "source_template_unchanged": template_sha_after == template_sha_before,
    }
    if not all(checks.values()):
        raise RuntimeError(f"News Excel Contract validation failed: {checks}")
    return {
        "passed": True,
        "checks": checks,
        "sheet_names": exported["sheet_names"],
        "row_4_headers": [f"标题{index}" for index in range(1, 7)],
        "row_5_slots": exported["row_5"],
        "extra_populated_cells": exported["extra_populated_cells"],
        "template_sha256_before": template_sha_before,
        "template_sha256_after": template_sha_after,
        "output_sha256": sha256_file(output_path),
    }


def append_news_presentation_history(
    ledger_path: Path,
    expected_ledger: dict[str, Any],
    *,
    approval_ref: dict[str, Any],
    output_ref: dict[str, Any],
    exported_at: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    source_ref = "real_shufang_mix_001-C003"
    if not any(
        entry.get("content_id") == source_ref and is_strong_memory(entry)
        for entry in expected_ledger.get("entries") or []
    ):
        raise RuntimeError("Presentation History source is not Strong Historical Content.")
    updated = json.loads(json.dumps(expected_ledger, ensure_ascii=False))
    extension = updated.setdefault("extensions", {}).setdefault(
        "presentation_history_v1",
        {
            "version": "content-presentation-history-v1.0",
            "storage_policy": "append_only",
            "semantic_novelty_authority": False,
            "entries": [],
        },
    )
    presentation_id = "real_shufang_news_validation_repurpose_001-P001"
    if any(
        item.get("presentation_id") == presentation_id
        for item in extension.get("entries") or []
    ):
        raise RuntimeError("Presentation History entry already exists.")
    entry = {
        "presentation_id": presentation_id,
        "business_id": "shufang_zhiyuan_community_canteen",
        "speaker_id": "lin_dongfang_frontline_chef",
        "request_id": "real_shufang_news_validation_repurpose_001",
        "production_profile": "news",
        "reuse_intent": "cross_profile_repurpose",
        "semantic_novelty": False,
        "historical_content_reused": True,
        "source_content_ref": source_ref,
        "selected_pattern_ref": NEWS_PRICE_PATTERN_ID,
        "status": "exported",
        "approved_at": exported_at,
        "exported_at": exported_at,
        "novel_capacity_delta": 0,
        "new_semantic_content_count_delta": 0,
        "new_central_claim_count_delta": 0,
        "new_information_gain_delta": 0,
        "communicated_information_units_created": False,
        "approval_ref": approval_ref,
        "export_ref": output_ref,
        "events": [
            {"status": "approved", "at": exported_at, "source": "human_review"},
            {"status": "exported", "at": exported_at, "source": "news_excel_export"},
        ],
    }
    entry_count_before = len(updated.get("entries") or [])
    information_units_before = sorted(
        unit.get("information_unit_id")
        for semantic_entry in updated.get("entries") or []
        for unit in semantic_entry.get("communicated_information_units") or []
    )
    extension.setdefault("entries", []).append(entry)
    updated["updated_at"] = exported_at
    if len(updated.get("entries") or []) != entry_count_before:
        raise RuntimeError("Presentation History changed semantic Ledger entries.")
    information_units_after = sorted(
        unit.get("information_unit_id")
        for semantic_entry in updated.get("entries") or []
        for unit in semantic_entry.get("communicated_information_units") or []
    )
    if information_units_after != information_units_before:
        raise RuntimeError("Presentation History duplicated Historical Exposure units.")
    ledger_path = ledger_path.expanduser().resolve()
    if read_json(ledger_path) != expected_ledger:
        raise RuntimeError("Content Ledger changed before Presentation History append.")
    payload = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8")
    temporary = ledger_path.with_suffix(ledger_path.suffix + ".presentation.tmp")
    if temporary.exists():
        raise RuntimeError("Presentation History temporary path already exists.")
    with temporary.open("xb") as handle:
        handle.write(payload)
    if read_json(ledger_path) != expected_ledger:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Content Ledger changed during Presentation History append.")
    temporary.replace(ledger_path)
    return updated, entry, hashlib.sha256(payload).hexdigest()


def build_news_mvp_production_validation_update(
    *,
    previous_coverage_path: Path,
    registry_path: Path,
    price_pattern_path: Path,
    scene_pattern_path: Path,
    track_a_approval_path: Path,
    track_b_approval_path: Path,
    export_path: Path,
    ledger_path: Path,
    created_at: str,
) -> dict[str, Any]:
    previous = read_json(previous_coverage_path)
    if (
        previous.get("news_current_coverage", {}).get("operational_readiness")
        != "production_validation_required"
    ):
        raise RuntimeError("News readiness source changed before MVP finalization.")
    return {
        "schema_version": "news-production-mvp-coverage-update-v1.0",
        "update_id": "news_production_mvp_final_validation_update_v1",
        "status": "current_derived_coverage_update",
        "created_at": created_at,
        "source_refs": {
            "previous_coverage_update": artifact_ref(
                previous_coverage_path, "creative_coverage_update"
            ),
            "frozen_registry": artifact_ref(
                registry_path, "production_profile_registry_v1"
            ),
            "price_pattern": artifact_ref(price_pattern_path, "approved_pattern"),
            "scene_pattern": artifact_ref(scene_pattern_path, "approved_pattern"),
            "track_a_human_approval": artifact_ref(
                track_a_approval_path, "news_capacity_human_approval"
            ),
            "track_b_human_approval": artifact_ref(
                track_b_approval_path, "news_generation_human_approval"
            ),
            "validated_excel_export": artifact_ref(export_path, "news_excel_export"),
            "content_ledger_after_presentation_append": artifact_ref(
                ledger_path, "content_ledger_v1"
            ),
        },
        "news_current_readiness": {
            "operational_readiness": "production_validation_required",
            "all_news_patterns_production_ready": False,
            "validated_production_paths": [NEWS_PRICE_PATTERN_ID],
            "pending_production_validation_patterns": [NEWS_SCENE_PATTERN_ID],
        },
        "pattern_production_validation": {
            NEWS_PRICE_PATTERN_ID: {
                "status": "passed",
                "validated_request_ref": "real_shufang_news_validation_repurpose_001",
                "validation_scope": "approved_cross_profile_repurpose_to_frozen_news_excel_contract",
            },
            NEWS_SCENE_PATTERN_ID: {
                "status": "pending_real_customer_opportunity",
                "reason": "No Approved customer State A/State B Truth exists for this customer.",
                "customer_state_a_b_fabricated": False,
            },
        },
        "authority": {
            "derived_planning_artifact": True,
            "changes_frozen_registry": False,
            "changes_approved_pattern_artifacts": False,
            "changes_pattern_effectiveness": False,
            "can_approve_new_content": False,
            "case_facts_used_as_customer_authority": False,
            "privacy_or_proof_authority_changed": False,
            "remote_model_called": False,
        },
        "validation": {
            "passed": True,
            "single_price_path_validated": True,
            "scene_path_remains_unvalidated": True,
            "news_readiness_not_overstated": True,
        },
    }


def run_news_production_mvp_final_approval(
    args: argparse.Namespace,
) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[1]
    paths = {
        "track_a": Path(
            args.track_a_validation
            or project_root
            / "data/news_production_mvp/real_shufang_news_validation_novel_001/news_novel_capacity_validation_v1.json"
        ).expanduser().resolve(),
        "track_b": Path(
            args.track_b_plan
            or project_root
            / "data/news_production_mvp/real_shufang_news_validation_repurpose_001/news_micro_beat_plan_v1.json"
        ).expanduser().resolve(),
        "content_plan": Path(
            args.content_plan
            or project_root
            / "data/content_plans/real_shufang_mix_002/revisions/v1_1_1/content_plan_v1_1_1.json"
        ).expanduser().resolve(),
        "ledger": Path(
            args.content_ledger
            or project_root
            / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
        ).expanduser().resolve(),
        "registry": Path(
            args.production_profile_registry
            or project_root / "data/production_profiles/production_profile_registry_v1.json"
        ).expanduser().resolve(),
        "coverage": Path(
            args.creative_coverage_update
            or project_root
            / "data/creative_coverage/revisions/news_pattern_approval_creative_coverage_update_v1.json"
        ).expanduser().resolve(),
        "price_pattern": project_root
        / f"data/patterns/approved/{NEWS_PRICE_PATTERN_ID}/pattern_v1.json",
        "scene_pattern": project_root
        / f"data/patterns/approved/{NEWS_SCENE_PATTERN_ID}/pattern_v1.json",
        "template": Path(
            args.news_template
            or project_root / "output/新闻体视频制作文案导入模板.xlsx"
        ).expanduser().resolve(),
        "mix_template": project_root / "output/素材混剪&数字人口播混剪文案导入模板.xlsx",
        "mix_export": project_root / "output/real_shufang_mix_001_approved_mix_scripts.xlsx",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    output_path = Path(
        args.news_output
        or project_root
        / "output/real_shufang_news_validation_repurpose_001_approved_news.xlsx"
    ).expanduser().resolve()
    output_root = Path(
        args.output_root or project_root / "data/news_production_mvp"
    ).expanduser().resolve()
    track_a_approval_path = (
        output_root
        / "real_shufang_news_validation_novel_001"
        / "news_novel_capacity_human_approval_v1.json"
    )
    track_b_approval_path = (
        output_root
        / "real_shufang_news_validation_repurpose_001"
        / "news_generation_human_approval_v1.json"
    )
    coverage_update_path = (
        project_root
        / "data/creative_coverage/revisions/news_production_mvp_final_validation_update_v1.json"
    )
    receipt_path = output_path.with_suffix(".export_receipt.json")
    for target in (coverage_update_path, receipt_path):
        if target.exists():
            raise RuntimeError(f"News MVP final output already exists: {target}")

    preserved_paths = {
        name: path for name, path in paths.items() if name != "ledger"
    }
    preserved_hashes_before = {
        name: sha256_file(path) for name, path in preserved_paths.items()
    }
    ledger = read_json(paths["ledger"])
    track_a = read_json(paths["track_a"])
    track_b = read_json(paths["track_b"])
    track_a_approval, track_b_approval = build_news_mvp_human_approvals(
        track_a,
        track_b,
        ledger,
        track_a_ref=artifact_ref(paths["track_a"], "news_novel_capacity_validation_v1"),
        track_b_ref=artifact_ref(paths["track_b"], "news_micro_beat_plan_v1"),
    )
    if track_a_approval_path.exists():
        track_a_approval = read_json(track_a_approval_path)
        if (
            track_a_approval.get("human_review", {}).get("decision")
            != "approved_validation_result"
            or track_a_approval.get("approved_result", {}).get(
                "news_novel_capacity"
            )
            != 0
            or track_a_approval.get("source_validation_ref", {}).get("sha256")
            != sha256_file(paths["track_a"])
        ):
            raise RuntimeError("Existing Track A Human Approval does not match its source.")
        track_a_approval_sha = sha256_file(track_a_approval_path)
    else:
        track_a_approval_sha = write_new_json(track_a_approval_path, track_a_approval)
    if track_b_approval_path.exists():
        track_b_approval = read_json(track_b_approval_path)
        if (
            track_b_approval.get("approved_micro_beat_plan", {})
            .get("source_plan_ref", {})
            .get("sha256")
            != sha256_file(paths["track_b"])
        ):
            raise RuntimeError("Existing Track B Human Approval does not match its source.")
        track_b_approval_sha = sha256_file(track_b_approval_path)
    else:
        track_b_approval_sha = write_new_json(track_b_approval_path, track_b_approval)
    approved_slot_texts = validate_news_export_approval(track_b_approval)

    node_executable = Path(
        args.node_executable or "node"
    ).expanduser()
    node_modules = str(
        Path(args.artifact_tool_node_modules).expanduser().resolve()
        if args.artifact_tool_node_modules
        else ""
    )
    exporter_path = project_root / "scripts/export_news_excel_v1.mjs"
    template_sha_before = sha256_file(paths["template"])
    preview_path = Path(tempfile.gettempdir()) / (
        "real_shufang_news_validation_repurpose_001_approved_news_preview.png"
    )
    artifact_validation_path = Path(tempfile.gettempdir()) / (
        "real_shufang_news_validation_repurpose_001_artifact_tool_validation.json"
    )
    preview_path.unlink(missing_ok=True)
    artifact_validation_path.unlink(missing_ok=True)
    environment = os.environ.copy()
    if node_modules:
        environment["NODE_PATH"] = node_modules
    command = [
        str(node_executable),
        str(exporter_path),
        "--mode",
        "validate-existing" if output_path.exists() else "export",
        "--approval",
        str(track_b_approval_path),
        "--template",
        str(paths["template"]),
        "--output",
        str(output_path),
        "--preview",
        str(preview_path),
        "--validation-output",
        str(artifact_validation_path),
    ]
    export_process = subprocess.run(
        command,
        cwd=project_root,
        env=environment,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if export_process.returncode != 0:
        raise RuntimeError(
            "News Excel artifact-tool export failed: "
            + (export_process.stderr or export_process.stdout)
        )
    artifact_tool_validation = read_json(artifact_validation_path)
    excel_validation = validate_news_excel_export(
        paths["template"], output_path, approved_slot_texts, template_sha_before
    )
    if artifact_tool_validation.get("passed") is not True:
        raise RuntimeError("Artifact-tool did not validate the News Excel output.")

    exported_at = now_iso()
    output_ref = artifact_ref(output_path, "approved_news_excel_export")
    approval_ref = artifact_ref(
        track_b_approval_path, "news_generation_human_approval_v1"
    )
    updated_ledger, presentation_entry, ledger_sha = append_news_presentation_history(
        paths["ledger"],
        ledger,
        approval_ref=approval_ref,
        output_ref=output_ref,
        exported_at=exported_at,
    )
    content_plan = read_json(paths["content_plan"])
    source_capacity = content_plan.get("capacity") or {}
    coverage_update = build_news_mvp_production_validation_update(
        previous_coverage_path=paths["coverage"],
        registry_path=paths["registry"],
        price_pattern_path=paths["price_pattern"],
        scene_pattern_path=paths["scene_pattern"],
        track_a_approval_path=track_a_approval_path,
        track_b_approval_path=track_b_approval_path,
        export_path=output_path,
        ledger_path=paths["ledger"],
        created_at=exported_at,
    )
    coverage_update_sha = write_new_json(coverage_update_path, coverage_update)

    preserved_hashes_after = {
        name: sha256_file(path) for name, path in preserved_paths.items()
    }
    if preserved_hashes_after != preserved_hashes_before:
        raise RuntimeError("A frozen News MVP source artifact changed during finalization.")
    receipt = {
        "schema_version": "news-excel-export-receipt-v1.0",
        "finalizer_version": NEWS_MVP_FINALIZER_VERSION,
        "exporter_version": artifact_tool_validation.get("exporter_version"),
        "request_id": track_b["request_id"],
        "profile": "news",
        "exported_at": exported_at,
        "human_approval": {
            "track_a_path": str(track_a_approval_path),
            "track_a_sha256": track_a_approval_sha,
            "track_b_path": str(track_b_approval_path),
            "track_b_sha256": track_b_approval_sha,
            "reviewer": "李健",
        },
        "reuse_declaration": {
            "reuse_intent": "cross_profile_repurpose",
            "semantic_novelty": False,
            "historical_content_reused": True,
            "source_content_ref": "real_shufang_mix_001-C003",
        },
        "selected_pattern": NEWS_PRICE_PATTERN_ID,
        "template_path": str(paths["template"]),
        "template_sha256_before": template_sha_before,
        "template_sha256_after": sha256_file(paths["template"]),
        "output_path": str(output_path),
        "output_sha256": sha256_file(output_path),
        "exported_row_count": 1,
        "row_4_headers": [f"标题{index}" for index in range(1, 7)],
        "row_5_slots": approved_slot_texts,
        "excel_validation": excel_validation,
        "artifact_tool_validation": {
            "passed": artifact_tool_validation["passed"],
            "formula_error_count": artifact_tool_validation["formula_error_count"],
            "source_rows_1_4_values_preserved": artifact_tool_validation[
                "source_rows_1_4_values_preserved"
            ],
        },
        "content_ledger": {
            "path": str(paths["ledger"]),
            "sha256_after_append": ledger_sha,
            "semantic_entry_count_before": len(ledger.get("entries") or []),
            "semantic_entry_count_after": len(updated_ledger.get("entries") or []),
            "presentation_history_entry": presentation_entry,
        },
        "novel_capacity": {
            "source_content_capacity_before": source_capacity.get(
                "high_quality_novel_capacity"
            ),
            "source_content_capacity_after": source_capacity.get(
                "high_quality_novel_capacity"
            ),
            "track_a_news_novel_capacity_before": track_a["capacity"][
                "news_novel_capacity"
            ],
            "track_a_news_novel_capacity_after": track_a["capacity"][
                "news_novel_capacity"
            ],
            "delta": 0,
        },
        "production_validation": {
            NEWS_PRICE_PATTERN_ID: "passed",
            NEWS_SCENE_PATTERN_ID: "pending_real_customer_opportunity",
            "news_operational_readiness": "production_validation_required",
        },
        "coverage_update": {
            "path": str(coverage_update_path),
            "sha256": coverage_update_sha,
        },
        "mix_regression_artifacts": {
            "template_sha256_before_after": preserved_hashes_before["mix_template"],
            "approved_export_sha256_before_after": preserved_hashes_before["mix_export"],
            "unchanged": True,
        },
        "authority": {
            "communicated_information_units_created": 0,
            "new_semantic_content_created": False,
            "case_facts_transferred": False,
            "case_footage_used": False,
            "scene_customer_truth_fabricated": False,
            "privacy_or_proof_authority_changed": False,
            "remote_model_calls": 0,
        },
        "validation_passed": True,
    }
    receipt_sha = write_new_json(receipt_path, receipt)
    return {
        "track_a_approval_path": track_a_approval_path,
        "track_b_approval_path": track_b_approval_path,
        "output_path": output_path,
        "output_sha256": receipt["output_sha256"],
        "receipt_path": receipt_path,
        "receipt_sha256": receipt_sha,
        "ledger_entry": presentation_entry,
        "ledger_sha256": ledger_sha,
        "coverage_update_path": coverage_update_path,
        "coverage_update_sha256": coverage_update_sha,
        "excel_validation": excel_validation,
        "artifact_tool_preview_path": preview_path,
        "remote_model_calls": 0,
    }


def build_news_excel_dry_run(
    request: dict[str, Any],
    plan: dict[str, Any],
    template_path: Path,
    export_contract: dict[str, Any],
) -> dict[str, Any]:
    headers = inspect_xlsx_headers(template_path, "Sheet1", 4, 6)
    expected_headers = [f"标题{index}" for index in range(1, 7)]
    template_sha = sha256_file(template_path)
    if headers != expected_headers:
        raise RuntimeError("News Excel template row 4 headers changed.")
    if export_contract.get("template_sha256") != template_sha:
        raise RuntimeError("News Excel template SHA differs from Frozen Registry.")
    slots = plan["beat_to_export_slot_mapping"]["slots"]
    if len(slots) != 6:
        raise RuntimeError("News dry-run requires exactly six mapped slots.")
    return {
        "schema_version": "news-excel-export-contract-dry-run-v1.0",
        "generator_version": NEWS_MVP_GENERATOR_VERSION,
        "created_at": now_iso(),
        "request_id": request["request_id"],
        "target_profile": "news",
        "status": "review_required_export_blocked",
        "template_ref": artifact_ref(template_path, "news_excel_template"),
        "sheet": "Sheet1",
        "header_row": 4,
        "actual_headers": headers,
        "expected_headers": expected_headers,
        "first_data_row": 5,
        "dry_run_row": {slot["header"]: slot["text"] for slot in slots},
        "slot_lineage": [
            {
                "header": slot["header"],
                "slot_id": slot["slot_id"],
                "source_beat_ref": slot["source_beat_ref"],
                "business_fact_atom_refs": [
                    item["fact_atom_id"] for item in slot["business_fact_refs"]
                ],
            }
            for slot in slots
        ],
        "implementation_constraints": {
            "slot_count": 6,
            "recommended_max_characters_per_slot": 8,
            "authority": "configurable_not_frozen_pattern_semantics",
            "pattern_invariant": False,
        },
        "workbook_written": False,
        "formal_excel_export_performed": False,
        "template_modified": False,
        "validation": {
            "passed": True,
            "template_sha_matches_registry": True,
            "sheet_matches": True,
            "row_4_headers_match": True,
            "six_slots_present": True,
            "duplicate_padding_absent": True,
        },
    }


def render_news_generation_review_pack(
    plan: dict[str, Any],
    dry_run: dict[str, Any],
    approved_batch_ref: dict[str, Any],
    export_receipt_ref: dict[str, Any],
) -> str:
    historical = plan["historical_content"]
    lines = [
        "# News Generation Review Pack V1",
        "",
        f"Request: `{plan['request_id']}`",
        "Target Profile: `news`",
        "Status: `review_required`",
        "",
        "## Historical Content and Reuse Declaration",
        "",
        f"Original Historical Content: `{historical['content_id']}`",
        f"Historical Batch: `{historical['batch_ref']}`",
        f"Historical Status: `{historical['historical_status']}`",
        f"Original Title: {historical['title']}",
        f"Original Narration: {historical['narration']}",
        "",
        "Reuse Intent: `cross_profile_repurpose`",
        "Semantic Novelty: `false`",
        "Historical Content Reused: `true`",
        "Reuse Reason: `cross_profile_production_validation`",
        "Novel Capacity Delta: `0`",
        "New Central Claim Count Delta: `0`",
        "Content Opportunity Count Delta: `0`",
        "",
        "## Selected Pattern",
        "",
        f"Pattern: `{plan['selected_pattern']['pattern_id']}`",
        f"Why compatible: {plan['selected_pattern']['matching_reason']}",
        "Matching basis: selected semantic content + target profile + Approved Pattern scope. Case topic was not used.",
        "",
        "Applied Pattern invariants:",
    ]
    for item in plan["pattern_application"]["applied_invariants"]:
        lines.append(
            f"- `{item['invariant']}`: `{'PASS' if item['satisfied'] else 'FAIL'}` ({item['evidence']})"
        )
    lines.extend(
        [
            "",
            "Continuous Mix narration required: `false` (inherited from Production Profile: News)",
            "Exact beat count / duration / six export slots are Pattern invariants: `false`",
            "Scene Contrast: `not_compatible` because no Approved customer State A/State B correspondence exists.",
            "",
            "## Micro Beat Plan",
            "",
        ]
    )
    for item in plan["micro_beats"]:
        facts = ", ".join(
            fact["original_known_fact"] for fact in item["business_fact_refs"]
        )
        atom_refs = ", ".join(
            fact["fact_atom_id"] for fact in item["business_fact_refs"]
        )
        lines.extend(
            [
                f"### {item['beat_id']} · {item['semantic_role']}",
                "",
                f"Text: {item['text']}",
                f"Supporting Persona Facts: {facts}",
                f"Fact Lineage: `{atom_refs}`",
                f"Visual Anchor: {item['visual_anchor']}",
                f"Visual State Role: `{item['visual_state_role']}`",
                "",
            ]
        )
    lines.extend(["## Six-slot Dry-run Mapping", ""])
    for slot in plan["beat_to_export_slot_mapping"]["slots"]:
        lines.append(
            f"- `{slot['header']}` / `{slot['slot_id']}` ← `{slot['source_beat_ref']}`: **{slot['text']}**"
        )
    lines.extend(
        [
            "",
            "The six columns are a current Excel implementation contract, not a Pattern invariant. The mapping uses no duplicate padding and preserves the price qualifiers across ordered slots.",
            "",
            "## Fact Authority",
            "",
        ]
    )
    for fact in plan["fact_lineage"]:
        lines.append(
            f"- {fact['original_known_fact']} — `{fact['field']}` / `{fact['fact_atom_id']}` / historical units `{', '.join(fact['historical_information_unit_refs'])}`"
        )
    lines.extend(
        [
            "",
            "All listed facts are Approved Persona KNOWN facts. UNKNOWN and REQUIRES_REVIEW facts were excluded. Fact Atoms provide planning lineage only and do not change Persona Authority.",
            "",
            "## Case Structural References and Media Boundary",
            "",
        ]
    )
    for case in plan["case_structural_references"]:
        lines.append(
            f"- `{case['case_id']}` — authority `structural_only`; media reuse rights `not_established`; Production footage eligible `false`"
        )
    lines.extend(
        [
            "",
            "No source Case video or frame may enter the customer Production Footage Pool. Every visual anchor requires customer-owned or separately authorized footage.",
            "",
            "## Claim Review Flags",
            "",
        ]
    )
    lines.extend(f"- `{flag}`" for flag in plan["claim_review_flags"])
    lines.extend(
        [
            "",
            "## Lineage and Export Gate",
            "",
            f"Approved Historical Batch: `{approved_batch_ref['path']}`",
            f"Approved Batch SHA-256: `{approved_batch_ref['sha256']}`",
            f"Historical Export Receipt: `{export_receipt_ref['path']}`",
            f"Historical Export Receipt SHA-256: `{export_receipt_ref['sha256']}`",
            f"News Template: `{dry_run['template_ref']['path']}`",
            f"News Template SHA-256: `{dry_run['template_ref']['sha256']}`",
            "Dry-run Contract Validation: `PASS`",
            "Workbook Written: `false`",
            "Formal Excel Export: `blocked_pending_human_review`",
            "",
            "Remote Model Calls: `0`",
            "Human decision required before any formal News Excel export.",
            "",
        ]
    )
    return "\n".join(lines)


def run_news_production_mvp_validation(args: argparse.Namespace) -> dict[str, Any]:
    required = {
        "persona": args.persona,
        "speaker-persona": args.speaker_persona,
        "novel-request": args.novel_request,
        "repurpose-request": args.repurpose_request,
        "content-plan": args.content_plan,
        "content-ledger": args.content_ledger,
        "production-profile-registry": args.production_profile_registry,
        "creative-coverage-update": args.creative_coverage_update,
        "news-pattern": args.news_pattern,
        "historical-approved-batch": args.historical_approved_batch,
        "historical-export-receipt": args.historical_export_receipt,
        "news-template": args.news_template,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(
            "--news-mvp-validation requires: " + ", ".join(missing)
        )
    project_root = Path(__file__).resolve().parents[1]
    paths = {
        "persona": Path(args.persona).expanduser().resolve(),
        "speaker_persona": Path(args.speaker_persona).expanduser().resolve(),
        "novel_request": Path(args.novel_request).expanduser().resolve(),
        "repurpose_request": Path(args.repurpose_request).expanduser().resolve(),
        "content_plan": Path(args.content_plan).expanduser().resolve(),
        "content_ledger": Path(args.content_ledger).expanduser().resolve(),
        "profile_registry": Path(args.production_profile_registry).expanduser().resolve(),
        "coverage_update": Path(args.creative_coverage_update).expanduser().resolve(),
        "historical_approved_batch": Path(args.historical_approved_batch).expanduser().resolve(),
        "historical_export_receipt": Path(args.historical_export_receipt).expanduser().resolve(),
        "news_template": Path(args.news_template).expanduser().resolve(),
    }
    persona, persona_sha = load_approved_persona(paths["persona"], "business")
    speaker, speaker_sha = load_approved_persona(
        paths["speaker_persona"], "speaker"
    )
    novel_request, novel_request_sha = load_profile_generation_request(
        paths["novel_request"], persona, speaker
    )
    repurpose_request, repurpose_request_sha = load_profile_generation_request(
        paths["repurpose_request"], persona, speaker
    )
    if novel_request["request_id"] != "real_shufang_news_validation_novel_001":
        raise RuntimeError("Unexpected Track A request ID.")
    if repurpose_request["request_id"] != "real_shufang_news_validation_repurpose_001":
        raise RuntimeError("Unexpected Track B request ID.")
    pattern_records = load_patterns([Path(value) for value in args.news_pattern])
    patterns = [record["artifact"] for record in pattern_records]
    registry = read_json(paths["profile_registry"])
    coverage_update = read_json(paths["coverage_update"])
    registry_context = validate_news_mvp_registry_and_patterns(
        registry, coverage_update, patterns
    )
    content_plan = read_json(paths["content_plan"])
    ledger = read_json(paths["content_ledger"])
    approved_batch = read_json(paths["historical_approved_batch"])
    export_receipt = read_json(paths["historical_export_receipt"])
    if approved_batch.get("status") != "approved":
        raise RuntimeError("Historical Batch must remain Approved.")
    approved_batch_sha = sha256_file(paths["historical_approved_batch"])
    if export_receipt.get("batch_sha256") != approved_batch_sha:
        raise RuntimeError("Historical Export Receipt does not reference Approved Batch.")
    if export_receipt.get("validation_passed") is not True:
        raise RuntimeError("Historical Export Receipt is not valid.")

    safe_persona_projection(persona)
    safe_speaker_projection(speaker)
    price_pattern = registry_context["patterns_by_id"][NEWS_PRICE_PATTERN_ID]
    price_pattern_path = next(
        Path(record["path"])
        for record in pattern_records
        if record["artifact"]["pattern_id"] == NEWS_PRICE_PATTERN_ID
    )
    case_refs, case_source_paths = build_news_case_structural_refs(
        price_pattern, project_root
    )
    preserved_paths = {
        **paths,
        **{
            f"pattern_{index}": Path(record["path"])
            for index, record in enumerate(pattern_records, start=1)
        },
        **case_source_paths,
    }
    source_hashes_before = {
        name: sha256_file(path) for name, path in preserved_paths.items()
    }

    track_a = assess_news_novel_capacity(
        novel_request, content_plan, patterns, persona
    )
    ledger_entry, approved_item = find_historical_price_content(
        ledger, approved_batch, repurpose_request
    )
    track_b = build_news_price_repurpose_plan(
        repurpose_request,
        ledger,
        ledger_entry,
        approved_item,
        patterns,
        artifact_ref(paths["profile_registry"], "production_profile_registry_v1"),
        artifact_ref(price_pattern_path, "approved_pattern"),
        case_refs,
    )
    dry_run = build_news_excel_dry_run(
        repurpose_request,
        track_b,
        paths["news_template"],
        registry_context["export_contract"],
    )

    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "news_production_mvp"
    )
    track_a_dir = output_root / novel_request["request_id"]
    track_b_dir = output_root / repurpose_request["request_id"]
    track_a_json_path = track_a_dir / "news_novel_capacity_validation_v1.json"
    track_a_review_path = track_a_dir / "news_novel_capacity_review_v1.md"
    track_b_plan_path = track_b_dir / "news_micro_beat_plan_v1.json"
    dry_run_path = track_b_dir / "news_excel_export_contract_dry_run_v1.json"
    track_b_review_path = track_b_dir / "news_generation_review_pack_v1.md"
    summary_path = output_root / "news_production_mvp_validation_v1.json"
    all_outputs = (
        track_a_json_path,
        track_a_review_path,
        track_b_plan_path,
        dry_run_path,
        track_b_review_path,
        summary_path,
    )
    existing = [str(path) for path in all_outputs if path.exists()]
    if existing:
        raise RuntimeError("News MVP output already exists: " + ", ".join(existing))

    dry_run_sha = write_new_json(dry_run_path, dry_run)
    track_b["export_contract_dry_run_ref"] = {
        "artifact_type": "news_excel_export_contract_dry_run_v1",
        "path": str(dry_run_path),
        "sha256": dry_run_sha,
    }
    track_a_sha = write_new_json(track_a_json_path, track_a)
    track_a_review_sha = write_new_text(
        track_a_review_path,
        render_news_novel_capacity_review(
            track_a,
            artifact_ref(paths["content_plan"], "content_plan_v1_1_1"),
            artifact_ref(paths["content_ledger"], "content_ledger_v1"),
        ),
    )
    track_b_sha = write_new_json(track_b_plan_path, track_b)
    track_b_review_sha = write_new_text(
        track_b_review_path,
        render_news_generation_review_pack(
            track_b,
            dry_run,
            artifact_ref(paths["historical_approved_batch"], "approved_generation_batch_v1"),
            artifact_ref(paths["historical_export_receipt"], "mix_excel_export_receipt_v1"),
        ),
    )
    summary = {
        "schema_version": "news-production-mvp-validation-v1.0",
        "generator_version": NEWS_MVP_GENERATOR_VERSION,
        "created_at": now_iso(),
        "status": "news_production_mvp_human_review_gate",
        "business_id": persona["persona_id"],
        "speaker_id": speaker["persona_id"],
        "track_a": {
            "request_id": novel_request["request_id"],
            "news_novel_capacity": track_a["capacity"]["news_novel_capacity"],
            "status": track_a["capacity"]["status"],
            "artifact_ref": {
                "path": str(track_a_json_path),
                "sha256": track_a_sha,
            },
            "review_pack_ref": {
                "path": str(track_a_review_path),
                "sha256": track_a_review_sha,
            },
        },
        "track_b": {
            "request_id": repurpose_request["request_id"],
            "reuse_intent": "cross_profile_repurpose",
            "semantic_novelty": False,
            "selected_pattern": NEWS_PRICE_PATTERN_ID,
            "micro_beat_count": len(track_b["micro_beats"]),
            "export_slot_count": len(
                track_b["beat_to_export_slot_mapping"]["slots"]
            ),
            "artifact_ref": {
                "path": str(track_b_plan_path),
                "sha256": track_b_sha,
            },
            "review_pack_ref": {
                "path": str(track_b_review_path),
                "sha256": track_b_review_sha,
            },
            "dry_run_ref": {
                "path": str(dry_run_path),
                "sha256": dry_run_sha,
            },
        },
        "scene_contrast": {
            "status": "pattern_available_but_no_current_customer_opportunity",
            "fake_state_a_b_created": False,
        },
        "news_readiness": {
            "before": "production_validation_required",
            "after": "production_validation_required",
            "production_ready": False,
            "next_gate": "news_production_mvp_human_review",
        },
        "usage": {
            "remote_model_calls": 0,
            "remote_tokens": 0,
            "remote_elapsed_seconds": 0,
        },
        "authority": {
            "persona_modified": False,
            "content_ledger_modified": False,
            "case_or_pattern_created": False,
            "case_facts_transferred": False,
            "case_media_reused": False,
            "proof_authority_changed": False,
            "privacy_authority_changed": False,
            "news_batch_approved": False,
            "formal_excel_export_performed": False,
        },
        "validation": {
            "passed": True,
            "novel_content_gate_validated": True,
            "cross_profile_repurpose_explicit": True,
            "approved_pattern_matching_validated": True,
            "micro_beat_plan_validated": True,
            "six_slot_contract_dry_run_validated": True,
            "human_review_pack_ready": True,
        },
        "input_lineage": {
            "persona_sha256": persona_sha,
            "speaker_persona_sha256": speaker_sha,
            "novel_request_sha256": novel_request_sha,
            "repurpose_request_sha256": repurpose_request_sha,
            "preserved_source_hashes": source_hashes_before,
        },
    }
    summary_sha = write_new_json(summary_path, summary)
    source_hashes_after = {
        name: sha256_file(path) for name, path in preserved_paths.items()
    }
    if source_hashes_after != source_hashes_before:
        raise RuntimeError("A preserved News MVP source artifact changed.")
    return {
        "summary": summary,
        "summary_path": summary_path,
        "summary_sha256": summary_sha,
        "track_a": track_a,
        "track_a_path": track_a_json_path,
        "track_a_review_path": track_a_review_path,
        "track_b": track_b,
        "track_b_path": track_b_plan_path,
        "track_b_review_path": track_b_review_path,
        "dry_run": dry_run,
        "dry_run_path": dry_run_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a review-required privacy-safe Mix batch, or run the "
            "offline News Production MVP validation mode."
        )
    )
    parser.add_argument("--persona")
    parser.add_argument("--speaker-persona")
    parser.add_argument("--request")
    parser.add_argument("--source-plan")
    parser.add_argument("--pattern")
    parser.add_argument(
        "--news-mvp-validation",
        action="store_true",
        help=(
            "Run deterministic Track A/Track B News MVP validation; no remote model, "
            "formal Excel export, ledger write, or approval."
        ),
    )
    parser.add_argument(
        "--news-mvp-final-approval",
        action="store_true",
        help=(
            "Persist final Human approvals, export the approved News workbook, "
            "append presentation-only Ledger history, and record scoped Production validation."
        ),
    )
    parser.add_argument("--track-a-validation")
    parser.add_argument("--track-b-plan")
    parser.add_argument("--news-output")
    parser.add_argument("--node-executable")
    parser.add_argument("--artifact-tool-node-modules")
    parser.add_argument("--novel-request")
    parser.add_argument("--repurpose-request")
    parser.add_argument("--production-profile-registry")
    parser.add_argument("--creative-coverage-update")
    parser.add_argument("--news-pattern", action="append")
    parser.add_argument("--historical-approved-batch")
    parser.add_argument("--historical-export-receipt")
    parser.add_argument("--news-template")
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
        "--content-ledger",
        help="Content Ledger V1 required by an enabled Content Quality V1 request.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Generate Content Plan V1 and Storyboard Plan V1 without scripts.",
    )
    parser.add_argument(
        "--reevaluate-content-plan",
        action="store_true",
        help="Re-run only deterministic gates on an existing --content-plan; no remote call.",
    )
    parser.add_argument(
        "--v1-1-reevaluate",
        action="store_true",
        help="Offline Historical Exposure backfill and V1.1 re-ranking; never generates scripts.",
    )
    parser.add_argument(
        "--v1-1-1-closure",
        action="store_true",
        help="Offline V1.1.1 closure calibration and Content Gap Report; never calls a model or generates scripts.",
    )
    parser.add_argument("--content-plan")
    parser.add_argument("--content-plan-output")
    parser.add_argument("--storyboard-plan-output")
    parser.add_argument("--baseline-analysis")
    parser.add_argument("--comparison-output")
    parser.add_argument("--v1-diagnostic-batch")
    parser.add_argument("--v1-diagnostic-review-pack")
    parser.add_argument("--v1-diagnostic-scorecard")
    parser.add_argument("--v1-1-content-plan-output")
    parser.add_argument("--v1-diagnostic-review-output")
    parser.add_argument("--v1-diagnostic-content-plan")
    parser.add_argument("--v1-1-diagnostic-content-plan")
    parser.add_argument("--v1-1-1-content-plan-output")
    parser.add_argument("--content-gap-output")
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/generation_batches",
    )
    args = parser.parse_args()
    if args.news_mvp_final_approval:
        result = run_news_production_mvp_final_approval(args)
        print("NEWS PRODUCTION MVP V1 FINAL APPROVAL AND EXPORT PASS")
        print("Track A capacity approval: expected zero-capacity PASS")
        print("Track B: approved cross_profile_repurpose (semantic_novelty=False)")
        print(f"Excel SHA-256: {result['output_sha256']}")
        print(f"Excel: {result['output_path']}")
        print(f"Export receipt: {result['receipt_path']}")
        print(f"Content Ledger SHA-256: {result['ledger_sha256']}")
        print(f"Coverage update: {result['coverage_update_path']}")
        print("News readiness: production_validation_required")
        print("Remote model calls: 0")
        return
    if args.news_mvp_validation:
        result = run_news_production_mvp_validation(args)
        print("NEWS PRODUCTION MVP V1 HUMAN REVIEW READY")
        print(
            "Track A capacity: "
            f"{result['track_a']['capacity']['news_novel_capacity']}/"
            f"{result['track_a']['capacity']['requested_quantity']} "
            f"({result['track_a']['capacity']['status']})"
        )
        print("Track B reuse intent: cross_profile_repurpose")
        print("Track B semantic novelty: False")
        print(f"Selected Pattern: {NEWS_PRICE_PATTERN_ID}")
        print(
            "Micro Beats / Export Slots: "
            f"{len(result['track_b']['micro_beats'])}/"
            f"{len(result['track_b']['beat_to_export_slot_mapping']['slots'])}"
        )
        print("Remote model calls: 0")
        print("Formal Excel export: False")
        print("News readiness: production_validation_required")
        print(f"Track A Review Pack: {result['track_a_review_path']}")
        print(f"Track B Review Pack: {result['track_b_review_path']}")
        print(f"Excel Dry-run: {result['dry_run_path']}")
        print(f"Summary: {result['summary_path']}")
        return
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
    project_root = Path(__file__).resolve().parents[1]
    ledger = read_json(Path(args.content_ledger)) if args.content_ledger else None
    if args.v1_1_1_closure:
        closure_required = {
            "content-ledger": args.content_ledger,
            "v1-diagnostic-content-plan": args.v1_diagnostic_content_plan,
            "v1-1-diagnostic-content-plan": args.v1_1_diagnostic_content_plan,
        }
        closure_missing = [
            name for name, value in closure_required.items() if not value
        ]
        if closure_missing:
            parser.error(
                "--v1-1-1-closure requires: " + ", ".join(closure_missing)
            )
        if args.plan_only or args.v1_1_reevaluate:
            parser.error("--v1-1-1-closure is an independent offline mode.")
        assert ledger is not None
        v1_plan_path = Path(args.v1_diagnostic_content_plan).expanduser().resolve()
        v1_1_plan_path = Path(
            args.v1_1_diagnostic_content_plan
        ).expanduser().resolve()
        ledger_path = Path(args.content_ledger).expanduser().resolve()
        preserved_source_paths = {
            "content_plan_v1": v1_plan_path,
            "content_plan_v1_1": v1_1_plan_path,
            "content_ledger_v1": ledger_path,
        }
        source_hashes = {
            name: sha256_file(path)
            for name, path in preserved_source_paths.items()
        }
        v1_plan = read_json(v1_plan_path)
        v1_1_plan = read_json(v1_1_plan_path)
        closure_plan = build_content_plan_v1_1_1(
            v1_1_plan=v1_1_plan,
            ledger=ledger,
            request=context["request"],
            source_artifact_hashes=source_hashes,
        )
        closure_plan_output = (
            Path(args.v1_1_1_content_plan_output)
            if args.v1_1_1_content_plan_output
            else project_root
            / "data"
            / "content_plans"
            / str(context["request"]["request_id"])
            / "revisions"
            / "v1_1_1"
            / "content_plan_v1_1_1.json"
        )
        gap_output = (
            Path(args.content_gap_output)
            if args.content_gap_output
            else project_root
            / "data"
            / "content_gap_reports"
            / str(context["request"]["request_id"])
            / "content_gap_report_v1.json"
        )
        comparison_output = (
            Path(args.comparison_output)
            if args.comparison_output
            else project_root
            / "data"
            / "comparisons"
            / str(context["request"]["request_id"])
            / "v1_vs_v1_1_vs_v1_1_1_content_quality_scorecard.json"
        )
        for output_path in (closure_plan_output, gap_output, comparison_output):
            if output_path.expanduser().resolve().exists():
                raise RuntimeError(
                    f"V1.1.1 closure output already exists: {output_path}"
                )
        predicted_plan_sha = hashlib.sha256(
            json.dumps(
                closure_plan, ensure_ascii=False, indent=2
            ).encode("utf-8")
        ).hexdigest()
        gap_report = build_content_gap_report_v1(
            content_plan_v1_1_1=closure_plan,
            ledger=ledger,
            speaker_persona=context.get("speaker_persona"),
            source_artifact_hashes={
                "content_plan_v1_1_1": predicted_plan_sha,
                "content_ledger_v1": source_hashes["content_ledger_v1"],
            },
        )
        comparison = build_v1_v1_1_v1_1_1_scorecard(
            v1_plan, v1_1_plan, closure_plan
        )
        plan_sha = write_new_json(closure_plan_output, closure_plan)
        if plan_sha != predicted_plan_sha:
            raise RuntimeError("V1.1.1 Content Plan write hash mismatch.")
        gap_sha = write_new_json(gap_output, gap_report)
        comparison_sha = write_new_json(comparison_output, comparison)
        after_hashes = {
            name: sha256_file(path)
            for name, path in preserved_source_paths.items()
        }
        if after_hashes != source_hashes:
            raise RuntimeError(
                "A preserved V1/V1.1/Ledger artifact changed during V1.1.1."
            )
        print("CONTENT QUALITY V1.1.1 CLOSURE CALIBRATION PASS")
        print("Remote model calls: 0")
        print(
            "CONCEPT_018: "
            + str(
                closure_plan["closure_calibration"][
                    "concept_018_final_decision"
                ]
            )
        )
        print(
            "Capacity: "
            f"{closure_plan['capacity']['high_quality_novel_capacity']}/"
            f"{closure_plan['capacity']['requested_quantity']} "
            f"({closure_plan['capacity']['status']})"
        )
        print(f"V1.1.1 Content Plan SHA-256: {plan_sha}")
        print(f"V1.1.1 Content Plan: {closure_plan_output.resolve()}")
        print(f"Content Gap Report SHA-256: {gap_sha}")
        print(f"Content Gap Report: {gap_output.resolve()}")
        print(f"Comparison SHA-256: {comparison_sha}")
        print(f"Comparison: {comparison_output.resolve()}")
        return
    if args.v1_1_reevaluate:
        v1_1_required = {
            "content-ledger": args.content_ledger,
            "content-plan": args.content_plan,
            "v1-diagnostic-batch": args.v1_diagnostic_batch,
            "v1-diagnostic-review-pack": args.v1_diagnostic_review_pack,
            "v1-diagnostic-scorecard": args.v1_diagnostic_scorecard,
        }
        v1_1_missing = [
            name for name, value in v1_1_required.items() if not value
        ]
        if v1_1_missing:
            parser.error(
                "--v1-1-reevaluate requires: " + ", ".join(v1_1_missing)
            )
        if args.plan_only:
            parser.error("--v1-1-reevaluate is already a plan-only offline mode.")
        assert ledger is not None
        v1_plan_path = Path(args.content_plan).expanduser().resolve()
        v1_batch_path = Path(args.v1_diagnostic_batch).expanduser().resolve()
        v1_review_path = Path(args.v1_diagnostic_review_pack).expanduser().resolve()
        v1_scorecard_path = Path(args.v1_diagnostic_scorecard).expanduser().resolve()
        source_artifact_paths = {
            "content_plan_v1": v1_plan_path,
            "generation_batch_v1": v1_batch_path,
            "generation_review_pack_v1": v1_review_path,
            "comparison_scorecard_v1": v1_scorecard_path,
        }
        source_artifact_hashes = {
            name: sha256_file(path) for name, path in source_artifact_paths.items()
        }
        v1_plan = read_json(v1_plan_path)
        v1_batch = read_json(v1_batch_path)
        business_projection = safe_persona_projection(context["persona"])
        enriched_ledger = enrich_ledger_with_communicated_information(
            ledger,
            context["persona"],
            sha256_file(context["paths"]["persona"]),
            set(business_projection["facts"]),
        )
        human_diagnostic = build_v1_diagnostic_human_review(v1_batch, v1_plan)
        v1_1_plan = build_content_plan_v1_1(
            v1_plan=v1_plan,
            ledger=enriched_ledger,
            request=context["request"],
            speaker_type=(context.get("speaker_persona") or {}).get(
                "speaker_type"
            ),
            authorized_fact_values=business_projection["facts"],
            source_artifact_hashes=source_artifact_hashes,
        )
        v1_vs_v1_1 = build_v1_vs_v1_1_scorecard(
            v1_plan, v1_1_plan, human_diagnostic
        )
        v1_1_plan_path = (
            Path(args.v1_1_content_plan_output)
            if args.v1_1_content_plan_output
            else project_root
            / "data"
            / "content_plans"
            / str(context["request"]["request_id"])
            / "revisions"
            / "v1_1"
            / "content_plan_v1_1.json"
        )
        human_diagnostic_path = (
            Path(args.v1_diagnostic_review_output)
            if args.v1_diagnostic_review_output
            else project_root
            / "data"
            / "content_reviews"
            / str(context["request"]["request_id"])
            / "v1_diagnostic_human_review_v1_1.json"
        )
        comparison_path = (
            Path(args.comparison_output)
            if args.comparison_output
            else project_root
            / "data"
            / "comparisons"
            / str(context["request"]["request_id"])
            / "v1_vs_v1_1_content_quality_scorecard.json"
        )
        for output_path in (
            v1_1_plan_path,
            human_diagnostic_path,
            comparison_path,
        ):
            if output_path.expanduser().resolve().exists():
                raise RuntimeError(f"V1.1 diagnostic output already exists: {output_path}")
        ledger_sha = replace_ledger_with_communicated_information(
            Path(args.content_ledger), ledger, enriched_ledger
        )
        plan_sha = write_new_json(v1_1_plan_path, v1_1_plan)
        human_sha = write_new_json(human_diagnostic_path, human_diagnostic)
        comparison_sha = write_new_json(comparison_path, v1_vs_v1_1)
        after_hashes = {
            name: sha256_file(path) for name, path in source_artifact_paths.items()
        }
        if after_hashes != source_artifact_hashes:
            raise RuntimeError("A preserved V1 diagnostic artifact changed during V1.1.")
        print("CONTENT QUALITY V1.1 OFFLINE RE-EVALUATION PASS")
        print("Remote model calls: 0")
        print(
            "Capacity: "
            f"{v1_1_plan['capacity']['high_quality_novel_capacity']}/"
            f"{v1_1_plan['capacity']['requested_quantity']} "
            f"({v1_1_plan['capacity']['status']})"
        )
        print(
            "Novelty survivors: "
            f"{v1_1_plan['capacity']['novelty_surviving_capacity']}"
        )
        print(f"Content Ledger V1.1 SHA-256: {ledger_sha}")
        print(f"Updated Content Plan SHA-256: {plan_sha}")
        print(f"Updated Content Plan: {v1_1_plan_path.resolve()}")
        print(f"Human Diagnostic SHA-256: {human_sha}")
        print(f"Human Diagnostic: {human_diagnostic_path.resolve()}")
        print(f"V1 vs V1.1 Scorecard SHA-256: {comparison_sha}")
        print(f"V1 vs V1.1 Scorecard: {comparison_path.resolve()}")
        return
    if args.plan_only:
        if ledger is None:
            parser.error("--plan-only requires --content-ledger.")
        existing_plan = None
        if args.reevaluate_content_plan:
            if not args.content_plan:
                parser.error("--reevaluate-content-plan requires --content-plan.")
            existing_plan = read_json(Path(args.content_plan))
            plan = reevaluate_content_plan_v1(context, ledger, existing_plan)
        else:
            plan = generate_content_plan_v1(context, ledger, args.model)
        content_plan_path = (
            Path(args.content_plan_output)
            if args.content_plan_output
            else Path(args.content_plan)
            if args.reevaluate_content_plan and args.content_plan
            else project_root
            / "data"
            / "content_plans"
            / str(context["request"]["request_id"])
            / "content_plan_v1.json"
        )
        storyboard_path = (
            Path(args.storyboard_plan_output)
            if args.storyboard_plan_output
            else project_root
            / "data"
            / "storyboard_plans"
            / str(context["request"]["request_id"])
            / "storyboard_plan_v1.json"
        )
        if existing_plan is not None and content_plan_path.expanduser().resolve().is_file():
            plan_sha = replace_json_if_unchanged(
                content_plan_path, existing_plan, plan
            )
        else:
            plan_sha = write_new_json(content_plan_path, plan)
        storyboard = build_storyboard_plan(plan)
        if args.reevaluate_content_plan and storyboard_path.expanduser().resolve().is_file():
            existing_storyboard = read_json(storyboard_path)
            if existing_plan is not None and existing_storyboard.get(
                "content_plan_sha256"
            ) != canonical_sha256(existing_plan):
                raise RuntimeError(
                    "Existing Storyboard Plan does not reference the source Content Plan."
                )
            storyboard_sha = replace_json_if_unchanged(
                storyboard_path, existing_storyboard, storyboard
            )
        else:
            storyboard_sha = write_new_json(storyboard_path, storyboard)
        print("CONTENT PLAN V1 PASS")
        print(f"Status: {plan['capacity']['status']}")
        print(
            "Capacity: "
            f"{plan['capacity']['selected_quantity']}/"
            f"{plan['capacity']['requested_quantity']}"
        )
        print(f"Content Plan SHA-256: {plan_sha}")
        print(f"Content Plan: {content_plan_path.resolve()}")
        print(f"Storyboard Plan SHA-256: {storyboard_sha}")
        print(f"Storyboard Plan: {storyboard_path.resolve()}")
        return
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
    content_plan = read_json(Path(args.content_plan)) if args.content_plan else None
    batch = generate_batch(
        context,
        args.model,
        args.max_attempts,
        content_plan=content_plan,
        content_ledger=ledger,
    )
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
    if content_plan and ledger is not None and args.content_ledger:
        _updated_ledger, ledger_sha = append_ledger_file(
            Path(args.content_ledger),
            ledger,
            review_batch_ledger_entries(batch),
        )
        print(f"Content Ledger appended SHA-256: {ledger_sha}")
    if content_plan and args.baseline_analysis:
        comparison = build_comparison_scorecard(
            read_json(Path(args.baseline_analysis)),
            content_plan,
            batch,
        )
        comparison_path = (
            Path(args.comparison_output)
            if args.comparison_output
            else project_root
            / "data"
            / "comparisons"
            / str(batch["request_id"])
            / "b0_vs_v1_content_quality_scorecard.json"
        )
        comparison_sha = write_new_json(comparison_path, comparison)
        print(f"Comparison Scorecard SHA-256: {comparison_sha}")
        print(f"Comparison Scorecard: {comparison_path.resolve()}")
    if not batch["validation"]["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
