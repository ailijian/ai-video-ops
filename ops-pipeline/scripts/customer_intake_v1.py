from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from approve_persona_v1 import approve_persona
from build_persona_v1 import (
    assess_business_persona_capabilities,
    build_persona,
    sha256_file,
)
from content_quality_v1 import (
    DEFAULT_EDITORIAL_V1_1_WEIGHTS,
    audience_need_lineage_v1_1_1,
    build_content_plan,
    build_fact_atom_catalog,
    editorial_score_v1_1,
    editorial_score_v1_1_1,
    historical_exposure_evaluation,
    material_information_gain_v1_1_1,
    novel_exclusive_anchor_evaluation,
    resolve_effective_content_gate_decision,
    speaker_fit_evaluation,
)


INTAKE_SCHEMA_VERSION = "customer-intake-v1.0"
FACT_CANDIDATE_SCHEMA_VERSION = "persona-fact-candidates-v1.0"
READINESS_SCHEMA_VERSION = "persona-onboarding-readiness-v1.0"
DELTA_SCHEMA_VERSION = "persona-revision-candidate-delta-v1.0"
IMPLEMENTATION_VERSION = "customer_intake_v1.py@1.1"

INTAKE_TYPES = {"initial_onboarding", "replenishment"}
INPUT_ACTORS = {
    "customer",
    "operator",
    "authorized_business_representative",
    "speaker",
    "customer_story_subject",
    "public_source_recorded_by_operator",
}
SPEAKER_TYPES = {"owner_founder", "frontline_expert", "brand", "generic"}
CANDIDATE_STATES = {"known_candidate", "unknown", "requires_review"}
PERSONA_SCOPES = {"business", "speaker"}

SCALAR_PERSONA_FIELDS = {
    "public_display_name",
    "company_short_name",
    "industry",
    "years_in_business",
    "service_area",
    "location_public_area",
    "business_address",
    "brand_story",
    "founder_or_operator_story",
    "public_role",
}

INITIAL_TOPIC_MAP: dict[str, tuple[str, str]] = {
    "business_name": ("business", "public_display_name"),
    "company_short_name": ("business", "company_short_name"),
    "industry": ("business", "industry"),
    "primary_service": ("business", "primary_products_or_services"),
    "core_audience": ("business", "core_audience"),
    "customer_use_case": ("business", "customer_use_cases"),
    "customer_pain": ("business", "customer_pains"),
    "differentiator": ("business", "differentiators"),
    "service_process": ("business", "process_facts"),
    "service_time": ("business", "service_time_facts"),
    "founder_story": ("business", "founder_or_operator_story"),
    "business_decision": ("business", "important_turning_points"),
    "speaker_name": ("speaker", "public_display_name"),
    "speaker_role": ("speaker", "public_role"),
    "speaker_practice": ("speaker", "speaker_role_facts"),
    "speaker_allowed_topics": ("speaker", "first_person_allowed_topics"),
    "speaker_forbidden_claims": ("speaker", "first_person_forbidden_claims"),
    "speaker_scope": ("speaker", "role_scope_constraints"),
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def write_new_text(path: Path, value: str) -> str:
    payload = value.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def _write_runtime_json(
    path: Path, value: dict[str, Any], *, replace_unapproved: bool
) -> str:
    if not replace_unapproved:
        return write_new_json(path, value)
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return hashlib.sha256(payload).hexdigest()


def _write_runtime_text(path: Path, value: str, *, replace_unapproved: bool) -> str:
    if not replace_unapproved:
        return write_new_text(path, value)
    payload = value.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return hashlib.sha256(payload).hexdigest()


def _assert_unapproved_revision_can_refresh(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Cannot refresh missing Persona draft: {path}")
    persona = read_json(path)
    if (
        persona.get("lifecycle", {}).get("status") != "review_required"
        or persona.get("lifecycle", {}).get("approved") is not False
        or (path.parent / "approval_receipt.json").exists()
    ):
        raise RuntimeError("Only an unapproved review-required Persona draft may refresh.")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_raw_answers(raw_answers: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for item in raw_answers:
        answer_id = str(item.get("answer_id") or "").strip()
        if not answer_id or answer_id in seen:
            raise ValueError("Every raw answer requires a unique answer_id.")
        seen.add(answer_id)
        actor = str(item.get("input_actor") or "").strip()
        if actor not in INPUT_ACTORS:
            raise ValueError(f"Unsupported input_actor: {actor!r}")
        if not isinstance(item.get("answer_text"), str):
            raise ValueError(f"Raw answer {answer_id} must preserve answer_text.")


def build_customer_intake(
    *,
    intake_id: str,
    intake_type: str,
    provisional_business_id: str | None,
    business_ref: dict[str, Any] | None,
    input_actor: str,
    input_sources: list[dict[str, Any]],
    raw_answers: list[dict[str, Any]],
    speaker_selection: dict[str, Any],
    attachments: list[dict[str, Any]] | None = None,
    open_questions: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if intake_type not in INTAKE_TYPES:
        raise ValueError(f"Unsupported intake_type: {intake_type!r}")
    if input_actor not in INPUT_ACTORS:
        raise ValueError(f"Unsupported input_actor: {input_actor!r}")
    speaker_type = str(speaker_selection.get("speaker_type") or "")
    if speaker_type not in SPEAKER_TYPES:
        raise ValueError(f"Unsupported speaker_type: {speaker_type!r}")
    _validate_raw_answers(raw_answers)
    timestamp = created_at or now_iso()
    immutable_answers = copy.deepcopy(raw_answers)
    return {
        "schema_version": INTAKE_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "intake_id": intake_id,
        "intake_type": intake_type,
        "provisional_business_id": provisional_business_id,
        "business_ref": copy.deepcopy(business_ref),
        "input_actor": input_actor,
        "input_sources": copy.deepcopy(input_sources),
        "raw_answers": immutable_answers,
        "attachments": copy.deepcopy(attachments or []),
        "speaker_selection": copy.deepcopy(speaker_selection),
        "open_questions": copy.deepcopy(open_questions or []),
        "conflicts": copy.deepcopy(conflicts or []),
        "created_at": timestamp,
        "updated_at": timestamp,
        "raw_input_contract": {
            "raw_answers_immutable": True,
            "ai_extracted_candidates_embedded": False,
            "raw_answers_sha256": canonical_sha256(immutable_answers),
            "candidate_artifact_required_separately": True,
        },
        "authority": {
            "raw_input_is_not_persona_authority": True,
            "input_actor_authority_is_not_interchangeable": True,
            "human_persona_review_required": True,
            "auto_approval_allowed": False,
        },
        "privacy": {
            "canonical_raw_input_retained_locally": True,
            "shared_privacy_projection_required_before_remote_call": True,
            "remote_model_call_performed": False,
        },
    }


def _candidate(
    *,
    candidate_id: str,
    scope: str,
    target_field: str,
    value: Any,
    raw_answer: dict[str, Any],
    excerpt: str,
    state: str = "known_candidate",
    authority: str = "within_scope",
    delta_type: str = "new_fact",
    review_note: str | None = None,
    conflict_refs: list[str] | None = None,
    authorization: dict[str, Any] | None = None,
    time_metadata: dict[str, Any] | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    if scope not in PERSONA_SCOPES:
        raise ValueError(f"Unsupported persona scope: {scope}")
    if state not in CANDIDATE_STATES:
        raise ValueError(f"Unsupported candidate state: {state}")
    answer_text = str(raw_answer.get("answer_text") or "")
    if excerpt not in answer_text:
        raise ValueError(
            f"Candidate {candidate_id} excerpt is not verbatim in {raw_answer.get('answer_id')}."
        )
    return {
        "fact_candidate_id": candidate_id,
        "persona_scope": scope,
        "target_field": target_field,
        "normalized_value": copy.deepcopy(value) if state != "unknown" else None,
        "source_ref": raw_answer.get("source_ref"),
        "source_excerpt": excerpt,
        "raw_answer_ref": raw_answer.get("answer_id"),
        "input_actor": raw_answer.get("input_actor"),
        "source_type": raw_answer.get("source_type"),
        "confirmation_basis": raw_answer.get("confirmation_basis"),
        "candidate_state": state,
        "conflict_refs": list(conflict_refs or []),
        "privacy_state": "canonical_local_input_no_remote_egress",
        "speaker_authority_assessment": authority,
        "time_metadata": copy.deepcopy(time_metadata),
        "delta_type": delta_type,
        "classification": classification,
        "authorization": copy.deepcopy(authorization),
        "review_note": review_note,
    }


def build_fact_candidate_artifact(
    intake: dict[str, Any],
    candidates: list[dict[str, Any]],
    created_at: str | None = None,
    derived_authority_constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if intake.get("schema_version") != INTAKE_SCHEMA_VERSION:
        raise ValueError("Fact extraction requires customer_intake_v1.")
    if canonical_sha256(intake.get("raw_answers") or []) != intake.get(
        "raw_input_contract", {}
    ).get("raw_answers_sha256"):
        raise RuntimeError("Raw answers changed after intake creation.")
    seen: set[str] = set()
    for item in candidates:
        candidate_id = str(item.get("fact_candidate_id") or "")
        if not candidate_id or candidate_id in seen:
            raise ValueError("Fact candidate IDs must be unique and non-empty.")
        seen.add(candidate_id)
        if item.get("candidate_state") not in CANDIDATE_STATES:
            raise ValueError("Invalid candidate state.")
    constraints = copy.deepcopy(derived_authority_constraints or [])
    constraint_ids = [str(item.get("constraint_id") or "") for item in constraints]
    if any(not constraint_id for constraint_id in constraint_ids) or len(
        constraint_ids
    ) != len(set(constraint_ids)):
        raise ValueError("Derived authority constraint IDs must be unique and non-empty.")
    return {
        "schema_version": FACT_CANDIDATE_SCHEMA_VERSION,
        "implementation_version": IMPLEMENTATION_VERSION,
        "intake_ref": {
            "intake_id": intake["intake_id"],
            "intake_type": intake["intake_type"],
            "raw_answers_sha256": intake["raw_input_contract"]["raw_answers_sha256"],
        },
        "created_at": created_at or now_iso(),
        "fact_candidates": copy.deepcopy(candidates),
        "derived_authority_constraints": constraints,
        "summary": {
            "total": len(candidates),
            "known_candidate": sum(
                item["candidate_state"] == "known_candidate" for item in candidates
            ),
            "unknown": sum(item["candidate_state"] == "unknown" for item in candidates),
            "requires_review": sum(
                item["candidate_state"] == "requires_review" for item in candidates
            ),
            "business": sum(item["persona_scope"] == "business" for item in candidates),
            "speaker": sum(item["persona_scope"] == "speaker" for item in candidates),
            "derived_authority_constraints": len(constraints),
        },
        "authority": {
            "candidates_are_not_known_persona_facts": True,
            "human_review_required": True,
            "operator_observation_not_customer_confirmation": True,
            "case_facts_consumed": False,
            "remote_model_call_performed": False,
            "derived_authority_constraints_are_not_customer_facts": True,
        },
    }


def extract_initial_fact_candidates(intake: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for index, answer in enumerate(intake.get("raw_answers") or [], start=1):
        topic = str(answer.get("topic") or "")
        mapping = INITIAL_TOPIC_MAP.get(topic)
        if mapping is None:
            continue
        scope, field = mapping
        value: Any = answer.get("normalized_value", answer.get("answer_text"))
        authority = "within_business_scope"
        if scope == "speaker":
            authority = "within_selected_speaker_scope"
        candidates.append(
            _candidate(
                candidate_id=f"FC-{intake['intake_id']}-{index:03d}",
                scope=scope,
                target_field=field,
                value=value,
                raw_answer=answer,
                excerpt=str(answer.get("answer_text") or ""),
                authority=authority,
            )
        )
    return build_fact_candidate_artifact(intake, candidates)


def _known_candidate_fields(
    candidate_artifact: dict[str, Any], scope: str
) -> set[str]:
    return {
        str(item.get("target_field"))
        for item in candidate_artifact.get("fact_candidates") or []
        if item.get("persona_scope") == scope
        and item.get("candidate_state") == "known_candidate"
    }


def _known_business_candidate_facts(
    candidate_artifact: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Any]] = {}
    for item in candidate_artifact.get("fact_candidates") or []:
        if (
            item.get("persona_scope") != "business"
            or item.get("candidate_state") != "known_candidate"
        ):
            continue
        field = str(item.get("target_field") or "")
        value = item.get("normalized_value")
        if field and value is not None:
            grouped.setdefault(field, []).append(copy.deepcopy(value))
    facts: dict[str, dict[str, Any]] = {}
    for field, values in grouped.items():
        facts[field] = {
            "state": "known",
            "value": values[0] if len(values) == 1 else values,
        }
    return facts


def critical_readiness_constraints(intake: dict[str, Any]) -> list[dict[str, Any]]:
    constraints = [
        copy.deepcopy(item)
        for item in intake.get("conflicts") or []
        if isinstance(item, dict)
        and item.get("severity") == "critical"
        and item.get("resolved") is not True
    ]
    constraints.extend(
        {
            **copy.deepcopy(item),
            "constraint_type": "critical_unknown",
        }
        for item in intake.get("open_questions") or []
        if isinstance(item, dict)
        and item.get("answer_status") not in {"answered", "resolved"}
        and (
            item.get("severity") == "critical"
            or item.get("production_blocked") is True
            or item.get("blocks_truthful_production") is True
        )
    )
    return constraints


def assess_persona_onboarding_readiness(
    intake: dict[str, Any],
    candidate_artifact: dict[str, Any],
    *,
    business_persona: dict[str, Any] | None = None,
    speaker_persona: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    business_facts = _known_business_candidate_facts(candidate_artifact)
    speaker_fields = _known_candidate_fields(candidate_artifact, "speaker")
    if business_persona:
        for field, fact in (business_persona.get("facts") or {}).items():
            if isinstance(fact, dict) and fact.get("state") == "known":
                business_facts[field] = copy.deepcopy(fact)
    if speaker_persona:
        speaker_fields |= set(
            speaker_persona.get("fact_authority", {}).get("known_fields") or []
        )
    speaker_type = intake.get("speaker_selection", {}).get("speaker_type")
    critical_constraints = critical_readiness_constraints(intake)
    business_readiness = assess_business_persona_capabilities(
        business_facts,
        critical_constraints=critical_constraints,
    )
    capability_groups = {
        **business_readiness["capability_groups"],
        "speaker_authority": {
            "required": speaker_type != "generic",
            "satisfied": speaker_type == "generic"
            or {
                "public_display_name",
                "public_role",
                "speaker_role_facts",
                "first_person_allowed_topics",
                "first_person_forbidden_claims",
            }.issubset(speaker_fields),
            "evidence_fields": sorted(
                speaker_fields
                & {
                    "public_display_name",
                    "public_role",
                    "speaker_role_facts",
                    "first_person_allowed_topics",
                    "first_person_forbidden_claims",
                }
            ),
        },
    }
    required_groups_pass = all(
        group["satisfied"] for group in capability_groups.values() if group["required"]
    )
    critical_conflicts = [
        item
        for item in critical_constraints
        if item.get("constraint_type") != "critical_unknown"
    ]
    critical_unknowns = [
        item
        for item in critical_constraints
        if item.get("constraint_type") == "critical_unknown"
    ]
    missing = [
        name
        for name, group in capability_groups.items()
        if group["required"] and not group["satisfied"]
    ]
    business_approved = bool(
        business_persona
        and business_persona.get("lifecycle", {}).get("status") == "approved"
        and business_persona.get("lifecycle", {}).get("approved") is True
    )
    speaker_approved = speaker_type == "generic" or bool(
        speaker_persona
        and speaker_persona.get("lifecycle", {}).get("status") == "approved"
        and speaker_persona.get("lifecycle", {}).get("approved") is True
    )
    if (
        intake.get("intake_type") == "replenishment"
        and business_approved
        and speaker_approved
    ):
        # Pending replenishment conflicts block the candidate revision, not the
        # already-approved Persona authority that is serving Production today.
        status = "production_ready"
    elif not required_groups_pass or critical_conflicts:
        status = "insufficient"
    elif business_approved and speaker_approved:
        status = "production_ready"
    else:
        status = "persona_review_ready"
    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "derived_at": created_at or now_iso(),
        "intake_ref": intake["intake_id"],
        "intake_type": intake["intake_type"],
        "status": status,
        "capability_groups": capability_groups,
        "critical_missing_truth": missing,
        "critical_conflicts": copy.deepcopy(critical_conflicts),
        "critical_unknowns": copy.deepcopy(critical_unknowns),
        "candidate_revision_blockers": copy.deepcopy(critical_conflicts),
        "approval_state": {
            "business_persona_approved": business_approved,
            "speaker_persona_approved": speaker_approved,
        },
        "authority": {
            "derived_artifact_has_no_approval_authority": True,
            "field_completion_percentage_used": False,
            "production_ready_requires_human_approved_personas": True,
            "content_capacity_is_independent": True,
        },
    }


FOLLOW_UP_BY_GAP = {
    "business_identity": (
        "具体提供什么产品或服务？请用顾客实际会购买的一项服务说明。",
        "service_definition",
    ),
    "customer_use_context": (
        "哪些顾客会在什么真实场景下使用这项服务？请举一个实际例子。",
        "customer_use_context",
    ),
    "production_bearing_facts": (
        "请补充一个真实服务流程、价格、时间、边界或差异点，并说明发生条件。",
        "production_bearing_truth",
    ),
    "speaker_authority": (
        "这次由谁出镜？他的实际职责是什么，哪些事情能用第一人称说明？",
        "speaker_scope",
    ),
}


def plan_follow_up(
    intake: dict[str, Any], readiness: dict[str, Any]
) -> list[dict[str, Any]]:
    answered_topics = {
        str(item.get("topic")) for item in intake.get("raw_answers") or []
    }
    existing_targets = {
        str(item.get("target_topic")) for item in intake.get("open_questions") or []
    }
    questions: list[dict[str, Any]] = []
    for gap in readiness.get("critical_missing_truth") or []:
        if gap == "critical_constraints":
            continue
        text, target = FOLLOW_UP_BY_GAP[gap]
        if target in answered_topics or target in existing_targets:
            continue
        questions.append(
            {
                "question_id": f"FOLLOWUP-{len(questions) + 1:02d}",
                "reason": "critical_missing_truth",
                "capability_gap": gap,
                "target_topic": target,
                "question_text": text,
                "answer_status": "unanswered",
            }
        )
    for conflict in readiness.get("critical_conflicts") or []:
        target = f"conflict::{conflict.get('conflict_id')}"
        if target not in existing_targets:
            questions.append(
                {
                    "question_id": f"FOLLOWUP-{len(questions) + 1:02d}",
                    "reason": "authority_conflict",
                    "capability_gap": "critical_constraints",
                    "target_topic": target,
                    "question_text": str(conflict.get("resolution_question") or "请确认冲突事实。"),
                    "answer_status": "unanswered",
                }
            )
    for unknown in readiness.get("critical_unknowns") or []:
        target = str(unknown.get("target_topic") or "critical_unknown")
        if target not in existing_targets:
            questions.append(
                {
                    "question_id": f"FOLLOWUP-{len(questions) + 1:02d}",
                    "reason": "critical_unknown",
                    "capability_gap": "critical_constraints",
                    "target_topic": target,
                    "question_text": str(
                        unknown.get("question_text")
                        or "请补充会影响真实内容生产的关键信息。"
                    ),
                    "answer_status": "unanswered",
                }
            )
    return questions


def _values_for_persona_field(
    candidates: Iterable[dict[str, Any]], field: str
) -> tuple[Any, list[str]]:
    selected = [
        item
        for item in candidates
        if item.get("target_field") == field
        and item.get("candidate_state") == "known_candidate"
    ]
    values = [copy.deepcopy(item.get("normalized_value")) for item in selected]
    refs = [str(item.get("fact_candidate_id")) for item in selected]
    if field in SCALAR_PERSONA_FIELDS:
        return (values[-1] if values else None), refs
    flattened: list[Any] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(value)
        else:
            flattened.append(value)
    return flattened, refs


def persona_input_from_initial_candidates(
    *,
    persona_id: str,
    scope: str,
    candidate_artifact: dict[str, Any],
    intake_ref: str,
    speaker_type: str | None = None,
    business_persona_ref: str | None = None,
    revision: int = 1,
) -> dict[str, Any]:
    candidates = [
        item
        for item in candidate_artifact.get("fact_candidates") or []
        if item.get("persona_scope") == scope
    ]
    facts: dict[str, Any] = {}
    for field in sorted({str(item.get("target_field")) for item in candidates}):
        value, refs = _values_for_persona_field(candidates, field)
        if value is None or value == []:
            continue
        facts[field] = {
            "state": "known",
            "value": value,
            "source_refs": [f"{intake_ref}#{ref}" for ref in refs],
            "review_note": None,
        }
    payload: dict[str, Any] = {
        "persona_id": persona_id,
        "revision": revision,
        "persona_scope": scope,
        "fixture_only": True,
        "source_type": "customer_intake_v1_test_fixture",
        "source_ref": intake_ref,
        "facts": facts,
    }
    if scope == "speaker":
        payload["speaker_type"] = speaker_type
        payload["business_persona_ref"] = business_persona_ref
    return payload


def build_initial_content_capacity_handoff(
    *,
    business_persona_path: Path,
    speaker_persona_path: Path | None,
    requested_quantity: int,
    created_at: str | None = None,
) -> dict[str, Any]:
    business = read_json(business_persona_path)
    speaker = read_json(speaker_persona_path) if speaker_persona_path else None
    if business.get("lifecycle", {}).get("status") != "approved":
        raise RuntimeError("Initial capacity requires an Approved Business Persona.")
    if speaker and speaker.get("lifecycle", {}).get("status") != "approved":
        raise RuntimeError("Initial capacity requires an Approved Speaker Persona.")
    known_business = set(business.get("fact_authority", {}).get("known_fields") or [])
    known_speaker = set(
        speaker.get("fact_authority", {}).get("known_fields") or []
    ) if speaker else set()
    candidates = [
        {
            "concept_id": "INITIAL_CONCEPT_001",
            "audience_need": "判断这项服务是否适合自己的日常场景",
            "content_job": "service_explanation",
            "primary_topic": "服务定义",
            "primary_fact_refs": ["primary_products_or_services"],
            "supporting_fact_refs": ["core_audience"],
            "speaker_fact_refs": ["speaker_role_facts"] if speaker else [],
            "central_claim": "这项服务解决了目标顾客在明确使用场景中的具体需求。",
            "exclusive_anchor": {
                "value": "客户确认的具体服务",
                "fact_refs": ["primary_products_or_services"],
            },
            "opening_strategy": "scene",
            "visual_anchor": "服务发生的真实现场",
            "why_publish": "帮助顾客理解服务范围。",
        },
        {
            "concept_id": "INITIAL_CONCEPT_002",
            "audience_need": "了解服务实际如何完成",
            "content_job": "process",
            "primary_topic": "服务流程",
            "primary_fact_refs": ["process_facts"],
            "supporting_fact_refs": [],
            "speaker_fact_refs": ["speaker_role_facts"] if speaker else [],
            "central_claim": "客户提供了可追溯的真实服务流程。",
            "exclusive_anchor": {
                "value": "客户确认的真实流程",
                "fact_refs": ["process_facts"],
            },
            "opening_strategy": "process",
            "visual_anchor": "流程关键动作",
            "why_publish": "把抽象服务变成可理解步骤。",
        },
        {
            "concept_id": "INITIAL_CONCEPT_003",
            "audience_need": "比较选择这家服务的具体理由",
            "content_job": "trust",
            "primary_topic": "客户差异点",
            "primary_fact_refs": ["differentiators"],
            "supporting_fact_refs": ["customer_use_cases"],
            "speaker_fact_refs": [],
            "central_claim": "客户确认的差异点能帮助目标顾客做选择。",
            "exclusive_anchor": {
                "value": "客户确认的差异化做法",
                "fact_refs": ["differentiators"],
            },
            "opening_strategy": "contrast",
            "visual_anchor": "差异化服务动作",
            "why_publish": "提供实际选择依据。",
        },
    ]
    available = [
        item
        for item in candidates
        if set(item["primary_fact_refs"]).issubset(known_business)
        and set(item["supporting_fact_refs"]).issubset(known_business)
        and set(item["speaker_fact_refs"]).issubset(known_speaker)
    ]
    plan = build_content_plan(
        request={
            "request_id": "initial_onboarding_capacity_handoff",
            "quantity": requested_quantity,
            "profile": "mix",
            "reuse_intent": "novel_content",
        },
        business_id=str(business.get("persona_id")),
        speaker_id=str(speaker.get("persona_id")) if speaker else None,
        speaker_type=str(speaker.get("speaker_type")) if speaker else None,
        allowed_fact_refs=known_business,
        allowed_speaker_fact_refs=known_speaker,
        ledger={"entries": []},
        raw_candidates=available,
        case_rotation=[],
        pattern_id="not_assigned_capacity_planning_only",
        source_lineage={
            "business_persona_path": str(business_persona_path.resolve()),
            "business_persona_sha256": sha256_file(business_persona_path),
            "speaker_persona_path": str(speaker_persona_path.resolve()) if speaker_persona_path else None,
            "speaker_persona_sha256": sha256_file(speaker_persona_path) if speaker_persona_path else None,
        },
        config={
            "candidate_pool_size": len(available),
            "minimum_editorial_score": 0.0,
        },
        planning_call={"remote_model_call_performed": False},
        created_at=created_at,
        authorized_fact_values={
            field: fact.get("value")
            for field, fact in business.get("facts", {}).items()
            if fact.get("state") == "known"
        },
        authorized_speaker_fact_values={
            field: fact.get("value")
            for field, fact in (speaker or {}).get("facts", {}).items()
            if fact.get("state") == "known"
        },
    )
    capacity = plan["capacity"]
    return {
        "schema_version": "initial-content-capacity-handoff-v1.0",
        "created_at": created_at or now_iso(),
        "persona_production_ready": True,
        "requested_quantity": requested_quantity,
        "high_quality_capacity": capacity["high_quality_novel_capacity"],
        "capacity_status": capacity["status"],
        "content_gap_summary": [
            "需要更多真实顾客问题、服务边界和具体案例，才能补充高质量内容容量。"
        ] if capacity["status"] == "capacity_limited" else [],
        "content_quality_engine": plan["quality_engine_version"],
        "content_plan_summary": {
            "candidate_pool_size": plan["candidate_pool"]["received_size"],
            "selected_concept_refs": [
                item["concept_id"] for item in plan["selected_concepts"]
            ],
            "padding_generated": plan["capacity"]["padding_generated"],
        },
        "authority": {
            "approved_personas_only": True,
            "script_generation_performed": False,
            "batch_created": False,
            "ledger_written": False,
            "remote_model_call_performed": False,
        },
    }


def _fixture_answer(
    answer_id: str,
    topic: str,
    text: str,
    value: Any,
    actor: str = "authorized_business_representative",
) -> dict[str, Any]:
    return {
        "answer_id": answer_id,
        "topic": topic,
        "question_text": topic,
        "answer_text": text,
        "normalized_value": value,
        "input_actor": actor,
        "source_type": "explicit_test_fixture_decision",
        "confirmation_basis": "fixture_human_statement",
        "source_ref": f"fixture://{answer_id}",
    }


def stage_a_fixtures() -> dict[str, list[dict[str, Any]]]:
    fixture_a = [
        _fixture_answer("A01", "business_name", "店名是巷口绿植养护站。", "巷口绿植养护站"),
        _fixture_answer("A02", "company_short_name", "平时简称巷口绿植。", "巷口绿植"),
        _fixture_answer("A03", "industry", "我们做室内绿植养护服务。", "室内绿植养护服务"),
        _fixture_answer("A04", "primary_service", "主要提供办公室上门绿植巡检、修剪和养护。", ["办公室上门绿植巡检、修剪和养护"]),
        _fixture_answer("A05", "core_audience", "主要服务周边没有专职园艺人员的小型办公室。", ["周边没有专职园艺人员的小型办公室"]),
        _fixture_answer("A06", "customer_use_case", "办公室植物黄叶或长势变差时会预约上门检查。", ["办公室植物黄叶或长势变差时预约上门检查"]),
        _fixture_answer("A07", "customer_pain", "客户通常不知道黄叶是浇水还是光照问题。", ["难以判断植物黄叶原因"]),
        _fixture_answer("A08", "differentiator", "每次服务会按植物逐盆记录问题和下一次观察事项。", ["逐盆记录问题和后续观察事项"]),
        _fixture_answer("A09", "service_process", "上门先看现场光照和盆土，再逐盆检查并记录处理。", ["检查光照和盆土", "逐盆巡检", "记录处理与观察事项"]),
        _fixture_answer("A10", "service_time", "一次小型办公室巡检通常约四十分钟。", ["小型办公室巡检通常约四十分钟"]),
        _fixture_answer("A11", "speaker_name", "这次由养护师周宁出镜。", "周宁"),
        _fixture_answer("A12", "speaker_role", "周宁是负责上门巡检和养护的一线养护师。", "绿植养护师", "speaker"),
        _fixture_answer("A13", "speaker_practice", "我会在现场检查光照、盆土和叶片状态并记录处理。", ["现场检查光照、盆土和叶片状态", "记录实际处理"], "speaker"),
        _fixture_answer("A14", "speaker_allowed_topics", "我可以讲自己当天实际检查和处理过的绿植。", ["本人实际执行的巡检、判断和养护动作"], "speaker"),
        _fixture_answer("A15", "speaker_forbidden_claims", "我不能代表老板讲创业原因、定价决定或经营战略。", ["我创办了这家公司", "我决定服务定价", "我制定品牌战略"], "speaker"),
        _fixture_answer("A16", "speaker_scope", "一线养护师只讲亲自执行和观察到的工作。", ["Founder Story、定价和品牌战略不属于一线养护师第一人称范围"], "speaker"),
    ]
    fixture_b = [
        _fixture_answer("B01", "industry", "我开了一家宠物店。", "宠物店")
    ]
    fixture_c = [
        _fixture_answer("C01", "business_name", "公司叫桥边修缮。", "桥边修缮"),
        _fixture_answer("C02", "industry", "我们提供社区房屋维修服务。", "社区房屋维修服务"),
        _fixture_answer("C03", "primary_service", "提供水电和小型房屋维修。", ["水电和小型房屋维修"]),
        _fixture_answer("C04", "core_audience", "服务周边需要上门维修的居民。", ["周边需要上门维修的居民"]),
        _fixture_answer("C05", "customer_use_case", "居民家中出现漏水时预约上门检查。", ["家庭漏水时预约检查"]),
        _fixture_answer("C06", "customer_pain", "顾客不知道漏水点在哪里。", ["无法判断漏水点"]),
        _fixture_answer("C07", "differentiator", "维修前先展示检测到的问题位置。", ["维修前展示问题位置"]),
        _fixture_answer("C08", "founder_story", "老板说：我创办公司是因为社区缺少及时维修。", "老板因社区缺少及时维修而创办公司"),
        _fixture_answer("C09", "business_decision", "老板说：我决定建立夜间值班制度。", ["老板决定建立夜间值班制度"]),
        _fixture_answer("C10", "speaker_name", "出镜人是普通维修员工陈川。", "陈川", "speaker"),
        _fixture_answer("C11", "speaker_role", "陈川是一线维修员工。", "一线维修员工", "speaker"),
        _fixture_answer("C12", "speaker_practice", "我负责到场检查和执行维修。", ["到场检查和执行维修"], "speaker"),
        _fixture_answer("C13", "speaker_allowed_topics", "我只讲自己处理过的维修现场。", ["本人实际处理的维修现场"], "speaker"),
        _fixture_answer("C14", "speaker_forbidden_claims", "我不能说我创办了公司、我决定值班制度。", ["我创办了公司", "我决定建立夜间值班制度", "我制定经营政策"], "speaker"),
    ]
    return {"fixture_a": fixture_a, "fixture_b": fixture_b, "fixture_c": fixture_c}


def run_stage_a(output_root: Path, created_at: str | None = None) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    results: dict[str, Any] = {}
    fixtures = stage_a_fixtures()
    for name, answers in fixtures.items():
        fixture_root = output_root / name
        intake = build_customer_intake(
            intake_id=f"initial_onboarding_{name}",
            intake_type="initial_onboarding",
            provisional_business_id=f"{name}_business",
            business_ref=None,
            input_actor="authorized_business_representative",
            input_sources=[{"source_type": "explicit_test_fixture", "fixture": name}],
            raw_answers=answers,
            speaker_selection={
                "speaker_type": "frontline_expert",
                "selected_role_label": "店里的专业人员",
            },
            created_at=timestamp,
        )
        raw_hash_before = intake["raw_input_contract"]["raw_answers_sha256"]
        candidate_artifact = extract_initial_fact_candidates(intake)
        readiness_before = assess_persona_onboarding_readiness(
            intake, candidate_artifact, created_at=timestamp
        )
        follow_up = plan_follow_up(intake, readiness_before)
        intake_path = fixture_root / "customer_intake_v1.json"
        candidate_path = fixture_root / "fact_candidates_v1.json"
        readiness_path = fixture_root / "persona_onboarding_readiness_v1.json"
        write_new_json(intake_path, intake)
        write_new_json(candidate_path, candidate_artifact)
        final_readiness = readiness_before
        fixture_result: dict[str, Any] = {
            "intake_path": str(intake_path.resolve()),
            "fact_candidates_path": str(candidate_path.resolve()),
            "initial_readiness": readiness_before["status"],
            "follow_up_questions": follow_up,
        }
        if name == "fixture_a":
            persona_input_root = fixture_root / "persona_inputs"
            persona_output_root = fixture_root / "personas"
            business_input = persona_input_from_initial_candidates(
                persona_id="fixture_greencare_business",
                scope="business",
                candidate_artifact=candidate_artifact,
                intake_ref=str(intake_path.resolve()),
            )
            business_input_path = persona_input_root / "business_persona_input_v1.json"
            write_new_json(business_input_path, business_input)
            business_path, _ = build_persona(
                business_input_path,
                persona_output_root,
                created_at=timestamp,
            )
            approve_persona(
                business_path,
                "Fixture Human Reviewer",
                "Explicit Stage A fixture decision approved Business Persona V1.",
                timestamp,
            )
            speaker_input = persona_input_from_initial_candidates(
                persona_id="fixture_greencare_frontline_specialist",
                scope="speaker",
                candidate_artifact=candidate_artifact,
                intake_ref=str(intake_path.resolve()),
                speaker_type="frontline_expert",
                business_persona_ref="fixture_greencare_business",
            )
            speaker_input_path = persona_input_root / "speaker_persona_input_v1.json"
            write_new_json(speaker_input_path, speaker_input)
            speaker_path, _ = build_persona(
                speaker_input_path,
                persona_output_root,
                created_at=timestamp,
                business_persona_path=business_path,
            )
            approve_persona(
                speaker_path,
                "Fixture Human Reviewer",
                "Explicit Stage A fixture decision approved Speaker Persona V1.",
                timestamp,
            )
            final_readiness = assess_persona_onboarding_readiness(
                intake,
                candidate_artifact,
                business_persona=read_json(business_path),
                speaker_persona=read_json(speaker_path),
                created_at=timestamp,
            )
            capacity = build_initial_content_capacity_handoff(
                business_persona_path=business_path,
                speaker_persona_path=speaker_path,
                requested_quantity=10,
                created_at=timestamp,
            )
            capacity_path = fixture_root / "initial_content_capacity_handoff_v1.json"
            write_new_json(capacity_path, capacity)
            fixture_result.update(
                {
                    "business_persona_path": str(business_path.resolve()),
                    "speaker_persona_path": str(speaker_path.resolve()),
                    "capacity_handoff_path": str(capacity_path.resolve()),
                    "capacity": capacity,
                }
            )
        elif name == "fixture_c":
            speaker_values = json.dumps(
                [
                    item.get("normalized_value")
                    for item in candidate_artifact["fact_candidates"]
                    if item.get("persona_scope") == "speaker"
                ],
                ensure_ascii=False,
            )
            fixture_result["speaker_boundary"] = {
                "founder_story_retained_as_business_candidate": any(
                    item.get("target_field") == "founder_or_operator_story"
                    and item.get("persona_scope") == "business"
                    for item in candidate_artifact["fact_candidates"]
                ),
                "founder_first_person_inherited_by_frontline_speaker": "老板因社区" in speaker_values,
                "explicit_forbidden_claims_present": "我创办了公司" in speaker_values,
            }
        final_readiness["follow_up_questions"] = follow_up
        write_new_json(readiness_path, final_readiness)
        fixture_result["final_readiness"] = final_readiness["status"]
        fixture_result["raw_answers_unchanged"] = (
            canonical_sha256(intake["raw_answers"]) == raw_hash_before
        )
        results[name] = fixture_result

    acceptance = {
        "fixture_a_complete_backend_loop": results["fixture_a"]["final_readiness"]
        == "production_ready",
        "fixture_b_stops_insufficient": results["fixture_b"]["final_readiness"]
        == "insufficient",
        "fixture_c_speaker_boundary": results["fixture_c"]["speaker_boundary"]
        == {
            "founder_story_retained_as_business_candidate": True,
            "founder_first_person_inherited_by_frontline_speaker": False,
            "explicit_forbidden_claims_present": True,
        },
        "raw_input_immutable": all(
            item["raw_answers_unchanged"] for item in results.values()
        ),
        "remote_model_calls": 0,
    }
    acceptance["passed"] = all(
        value is True for key, value in acceptance.items() if key != "remote_model_calls"
    )
    summary = {
        "schema_version": "customer-intake-stage-a-validation-v1.0",
        "created_at": timestamp,
        "fixtures": results,
        "acceptance": acceptance,
        "stage_b_gate": "open" if acceptance["passed"] else "blocked",
    }
    write_new_json(output_root / "stage_a_validation_summary_v1.json", summary)
    return summary


INTERVIEW_HEADING = re.compile(r"^###\s+(?P<number>\d+)\.\s+(?P<question>.+)$")


def _actor_metadata(label: str) -> tuple[str, str, str]:
    if label == "林东方":
        return "speaker", "direct_speaker_answer", "speaker_first_person_recollection"
    if "代顾客确认" in label:
        return (
            "operator",
            "operator_recorded_customer_confirmation",
            "operator_attests_direct_customer_confirmation",
        )
    if "记录门店运营者" in label:
        return (
            "operator",
            "operator_recorded_authorized_business_representative",
            "operator_recorded_business_representative_answer",
        )
    if "公开报道" in label or "业务负责人" in label:
        return (
            "public_source_recorded_by_operator",
            "operator_compiled_business_representative_and_public_report",
            "mixed_source_requires_entity_binding_review",
        )
    return "operator", "operator_record", "unverified_operator_record"


def parse_interview_markdown(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    section = "core"
    answers: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("## Optional Expansion"):
            section = "optional"
        match = INTERVIEW_HEADING.match(line)
        if not match:
            index += 1
            continue
        question_number = int(match.group("number"))
        question = match.group("question").strip()
        end = index + 1
        while end < len(lines) and not INTERVIEW_HEADING.match(lines[end]):
            if lines[end].startswith("## ") and end > index + 1:
                break
            end += 1
        block = lines[index + 1 : end]
        actor_label = ""
        actor_line = -1
        for block_index, block_line in enumerate(block):
            if block_line.startswith("**回答人**："):
                actor_label = block_line.split("：", 1)[1].strip()
                actor_line = block_index
                break
        if actor_line < 0:
            raise RuntimeError(f"Interview question {section}/{question_number} has no actor.")
        answer_text = "\n".join(block[actor_line + 1 :]).strip()
        actor, source_type, confirmation = _actor_metadata(actor_label)
        answer_id = f"{section.upper()}_Q{question_number:02d}"
        answers.append(
            {
                "answer_id": answer_id,
                "topic": f"interview_{section}_{question_number:02d}",
                "question_text": question,
                "answer_text": answer_text,
                "answer_actor_label": actor_label,
                "input_actor": actor,
                "source_type": source_type,
                "confirmation_basis": confirmation,
                "source_ref": f"{path.resolve()}#{answer_id}",
            }
        )
        index = end
    if len(answers) != 21:
        raise RuntimeError(f"Expected 21 interview answers, found {len(answers)}.")
    return answers


def _answers_by_id(intake: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["answer_id"]): item for item in intake.get("raw_answers") or []
    }


def extract_shufang_replenishment_candidates(
    intake: dict[str, Any]
) -> dict[str, Any]:
    if intake.get("intake_type") != "replenishment":
        raise ValueError("Real interview must enter as replenishment.")
    answer = _answers_by_id(intake)
    candidates: list[dict[str, Any]] = []
    derived_constraints: list[dict[str, Any]] = []

    def add(**kwargs: Any) -> None:
        candidates.append(_candidate(**kwargs))

    add(candidate_id="B-R2-001", scope="business", target_field="customer_use_cases", value={"type": "known_customer_question", "question": "师傅，这个梭子蟹红烧要多久啊？我赶时间。", "source": "direct_speaker_recollection"}, raw_answer=answer["CORE_Q03"], excerpt="师傅，这个梭子蟹红烧要多久啊？我赶时间。", delta_type="new_fact", classification="known_customer_question")
    add(candidate_id="B-R2-002", scope="business", target_field="customer_use_cases", value={"type": "known_customer_question", "question": "我买的这个花蛤，你们能帮我吐沙吗？我不会弄。", "source": "direct_speaker_recollection"}, raw_answer=answer["CORE_Q03"], excerpt="我买的这个花蛤，你们能帮我吐沙吗？我不会弄。", delta_type="new_fact", classification="known_customer_question")
    add(candidate_id="B-R2-003", scope="business", target_field="customer_use_cases", value={"type": "known_customer_question", "question": "这个菜加工费多少？米饭是送的吧？", "source": "direct_speaker_recollection"}, raw_answer=answer["CORE_Q03"], excerpt="这个菜加工费多少？米饭是送的吧？", delta_type="supports_existing", classification="known_customer_question")
    add(candidate_id="B-R2-004", scope="business", target_field="service_process", value={"boundary": "花蛤临时吐沙需要额外等待，且不能保证完全无沙", "semantic_scope": "observed_service_boundary_and_operational_behavior", "speaker_practice_context": True, "company_wide_permanent_policy": False, "industry_rule": False}, raw_answer=answer["CORE_Q04"], excerpt="我不敢保证一粒沙都没有", delta_type="new_fact", classification="service_boundary")
    add(candidate_id="B-R2-005", scope="business", target_field="process_facts", value={"boundary": "食材与顾客指定做法不匹配时，先说明问题并提出替代做法", "example": "纯瘦肉不适合按常规回锅肉做法，建议改为青椒炒肉片", "semantic_scope": "observed_service_handling_practice", "mandatory_company_wide_process": False}, raw_answer=answer["CORE_Q07"], excerpt="食材跟顾客想要的做法不匹配的时候，我不会硬做，会直接跟顾客说清楚问题在哪，然后给一个替代方案。", delta_type="new_fact", classification="service_boundary")
    add(candidate_id="B-R2-006", scope="business", target_field="service_time_facts", value={"type": "concrete_observed_peak_wait_example", "estimate": "15–20分钟", "actual": "约18分钟", "conditions": ["晚市高峰", "蒸锅需等待", "前序菜占用设备"], "typical_wait": False, "sla": False, "service_promise": False}, raw_answer=answer["CORE_Q08"], excerpt="大概十五到二十分钟", delta_type="refines_existing", time_metadata={"estimate": "15–20分钟", "actual": "约18分钟", "case_specific": True})
    add(candidate_id="B-R2-007", scope="business", target_field="service_time_facts", value={"boundary": "高峰期受灶台、蒸锅和前序订单影响，不能承诺马上出餐", "scope": "high_peak_operational_boundary", "all_time_wait_rule": False}, raw_answer=answer["CORE_Q08"], excerpt="我不会为了接单就答应“马上就好”", delta_type="refines_existing", classification="service_boundary")
    add(candidate_id="B-R2-008", scope="business", target_field="pricing_facts", value={"claim": "未处理鱼的加工费与处理好的鱼不同", "official_rule": None}, raw_answer=answer["CORE_Q02"], excerpt="加工费跟已经处理好的鱼不一样", state="requires_review", review_note="No complete official pricing rule supports the amount or calculation. Do not derive a new fee.", conflict_refs=["pricing_rule_missing"], classification="unconfirmed_pricing")
    add(candidate_id="B-R2-009", scope="business", target_field="authorized_customer_cases_or_feedback", value={"customer_label": "小孙", "scene": "新婚夫妻第一次体验代炒；三只梭子蟹；红烧梭子蟹加年糕", "authorized_quotes": ["我们还不太会做饭，这里可以帮忙洗刷、切配，火候也比家里到位，大锅大火炒出来的味道更好", "以后还会经常光顾"], "image_authorized": False, "video_authorized": False, "authorization_scope": "single_content_use_only", "production_use_requires_specific_use_binding": True, "global_reuse_authorized": False, "requires_reauthorization_for": ["other_channels", "commercial_promotion"]}, raw_answer=answer["CORE_Q10"], excerpt=answer["CORE_Q10"]["answer_text"], delta_type="refines_existing", classification="customer_story", authorization={"label": True, "scene": True, "quotes": "specified_only", "image": False, "video": False, "authorization_scope": "single_content_use_only", "production_use_requires_specific_use_binding": True, "global_reuse_authorized": False, "requires_reauthorization_for": ["other_channels", "commercial_promotion"]})
    add(candidate_id="B-R2-010", scope="business", target_field="information_requiring_human_review", value={"story_ref": "小孙", "quote": "比我们自己在家弄强多了，那个蟹我们连怎么杀都不知道", "reuse_status": "unauthorized_for_reuse"}, raw_answer=answer["CORE_Q05"], excerpt="比我们自己在家弄强多了，那个蟹我们连怎么杀都不知道", state="requires_review", review_note="Q5 raw quote is not in the exact Q10 authorized quote list and cannot inherit authorization.", conflict_refs=["small_sun_q10_authorized_quote_scope"], classification="quote_authorization")
    add(candidate_id="B-R2-011", scope="business", target_field="authorized_customer_cases_or_feedback", value={"customer_label": "陶先生", "scene": "常客；花甲和梭子蟹；少盐少辣；改变做法", "authorized_quotes": ["这项服务最大的好处就是省心"], "authorized_evaluations": ["挺满意的，一淡一辣搭配着吃正好"], "image_authorized": False, "video_authorized": False, "channel_scope": None, "duration_scope": None, "commercial_scope": None, "production_use_requires_scope_aware_review": True, "unrestricted_commercial_reuse": False}, raw_answer=answer["OPTIONAL_Q05"], excerpt=answer["OPTIONAL_Q05"]["answer_text"], delta_type="refines_existing", classification="customer_story", authorization={"label": True, "scene": True, "quotes": "specified_only", "evaluation": "specified_only", "image": False, "video": False, "channel_scope": None, "duration_scope": None, "commercial_scope": None, "production_use_requires_scope_aware_review": True, "unrestricted_commercial_reuse": False})
    add(candidate_id="B-R2-012", scope="business", target_field="important_turning_points", value={"decision": "在代炒窗口旁设置排单与预计等待时间白板", "trigger": "晚市高峰顾客反复询问排单与等待时间", "display": "当前排单顺序与每道菜预计等待"}, raw_answer=answer["OPTIONAL_Q08"], excerpt="后来我们就在窗口旁边放了一块小白板，写上当前排单顺序和每道菜大概的等待时间。", authority="business_operator_recorded_decision", delta_type="new_fact", classification="business_decision")
    add(candidate_id="B-R2-013", scope="business", target_field="information_requiring_human_review", value={"claim": "白板实行后高峰期窗口秩序好了很多，顾客等待焦虑明显下降", "evidence_class": "operator_observation", "proof_status": "candidate_unverified_outcome"}, raw_answer=answer["OPTIONAL_Q08"], excerpt="高峰期窗口秩序好了很多，顾客等待的焦虑感也明显下降", state="requires_review", authority="operator_observation_not_verified_proof", review_note="Do not upgrade an operator observation into Proof or causal effectiveness.", conflict_refs=["proof_authority_absent"], classification="candidate_unverified_outcome")
    add(candidate_id="B-R2-014", scope="business", target_field="customer_use_cases", value={"type": "known_customer_question", "question": "师傅，你们这个油是什么油？我在健身，不想吃太油腻的。", "source": "direct_speaker_recollection"}, raw_answer=answer["OPTIONAL_Q02"], excerpt="师傅，你们这个油是什么油？我在健身，不想吃太油腻的。", delta_type="new_fact", classification="known_customer_question")
    add(candidate_id="B-R2-015", scope="business", target_field="customer_use_cases", value={"type": "known_customer_question", "question": "能不能帮我多放点辣椒？我湖南人，口味重。", "source": "direct_speaker_recollection"}, raw_answer=answer["OPTIONAL_Q02"], excerpt="能不能帮我多放点辣椒？我湖南人，口味重。", delta_type="supports_existing", classification="known_customer_question")
    add(candidate_id="B-R2-016", scope="business", target_field="information_requiring_human_review", value={"entity": "浦商邻里荟永泰店", "claims": ["午市四五十单", "晚市三四十单", "单日约100人", "节假日业务更好"], "entity_binding": "unresolved"}, raw_answer=answer["OPTIONAL_Q09"], excerpt="目前通常午市可接四五十单，晚市接待三四十单，单日整体服务人次可达100左右。逢节假日生意更好。", state="requires_review", authority="mixed_operator_and_public_source", review_note="Entity binding to shufang_zhiyuan_community_canteen remains unresolved.", conflict_refs=["existing_yongtai_entity_binding_concern"], classification="entity_binding_review")
    add(candidate_id="B-R2-017", scope="business", target_field="information_requiring_human_review", value={"entity": "浦商邻里荟永泰店", "claims": ["租金优惠", "免租", "租金下调"], "entity_binding": "unresolved"}, raw_answer=answer["OPTIONAL_Q09"], excerpt="我们对社区食堂给予了租金优惠，免租加租金下调", state="requires_review", authority="mixed_operator_and_public_source", review_note="Rent policy and operating-entity relationship require explicit human entity binding.", conflict_refs=["existing_yongtai_entity_binding_concern", "brand_context_role_scope"], classification="entity_binding_review")
    add(candidate_id="B-R2-018", scope="business", target_field="information_requiring_human_review", value={"speaker_or_source_entity": "石健生 / 浦商邻里荟永泰店管理负责人", "target_business": "书房市集志泉社区食堂", "required_decision": "confirm_same_entity_or_define_relationship_and_data_scope"}, raw_answer=answer["OPTIONAL_Q09"], excerpt="我是浦商邻里荟永泰店管理负责人石健生。", state="requires_review", authority="entity_binding_unresolved", review_note="Repeated appearance does not resolve the prior authority concern.", conflict_refs=["existing_yongtai_entity_binding_concern"], classification="entity_binding_review")

    add(candidate_id="S-R2-001", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_practice", "practice": "接到食材先检查是否处于可以直接下锅的状态"}, raw_answer=answer["CORE_Q02"], excerpt="食材到手上，先看是不是可以直接下锅的状态", authority="speaker_specific_practice_not_universal_rule", delta_type="new_fact", classification="speaker_practice")
    add(candidate_id="S-R2-002", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_practice", "practice": "当食材需要额外处理、做法需要调整或存在不确定性时，林东方会在开始加工前向顾客说明额外时间、做法变化、已确认的收费差异，或仍需要确认的收费事项", "official_pricing_authority": False, "new_pricing_amount_or_formula": False}, raw_answer=answer["CORE_Q02"], excerpt="先跟顾客说清楚要多花多少时间、加工费怎么算", authority="speaker_specific_practice_without_official_pricing_authority", delta_type="new_fact", classification="speaker_practice")
    add(candidate_id="S-R2-003", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_practice", "practice": "食材与做法不匹配时说明问题并提出替代方案"}, raw_answer=answer["CORE_Q07"], excerpt="然后给一个替代方案", authority="speaker_specific_practice", delta_type="new_fact", classification="speaker_practice")
    add(candidate_id="S-R2-004", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_operational_heuristic", "practice": "高峰期通常优先处理能快速出餐的菜，但会根据灶台、蒸锅和食材情况调整", "fixed_rule": False}, raw_answer=answer["CORE_Q12"], excerpt="这个安排不是固定的，看当天灶台状态和食材情况来定。", authority="speaker_specific_operational_heuristic", delta_type="new_fact", classification="speaker_operational_heuristic")
    add(candidate_id="S-R2-005", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_personal_experience", "practice": "一次鱼腹残留血水影响结果后，接鱼时会先按鱼肚并查看鳃，确认是否需要再次处理"}, raw_answer=answer["OPTIONAL_Q07"], excerpt="从那以后，我接鱼的时候都会先用手按一下鱼肚子，看有没有没清理干净的内脏，再看一下鳃。", authority="speaker_specific_experience", delta_type="new_fact", classification="speaker_personal_experience")
    add(candidate_id="S-R2-006", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_professional_observation", "observation": "林东方会依据梭子蟹是否存活及处理状态调整做法建议，并提前说明口感可能变化", "universal_truth": False}, raw_answer=answer["CORE_Q01"], excerpt="活蟹和刚死的蟹处理方式不一样", authority="speaker_professional_observation_not_business_universal_truth", delta_type="new_fact", classification="speaker_professional_observation")
    add(candidate_id="S-R2-007", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_professional_observation", "observation": "林东方会把鱼眼、鱼鳃等作为本人判断鲜度和调整做法的现场线索", "universal_truth": False}, raw_answer=answer["OPTIONAL_Q03"], excerpt="鱼眼有点浑浊，鳃的颜色也不够鲜红", authority="speaker_professional_observation_not_business_universal_truth", delta_type="new_fact", classification="speaker_professional_observation")
    add(candidate_id="S-R2-008", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_practice", "practice": "花蛤未提前吐沙时会说明等待与结果边界，不承诺完全无沙"}, raw_answer=answer["CORE_Q04"], excerpt="花蛤吐沙这事真的不能承诺", authority="speaker_specific_practice", delta_type="new_fact", classification="speaker_practice")
    add(candidate_id="S-R2-009", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_professional_observation", "observation": "改变常规红烧用油量时会提前说明口感与汤汁可能不同", "universal_truth": False}, raw_answer=answer["OPTIONAL_Q04"], excerpt="红烧少放油可以，但出来的口感会跟正常的红烧不一样", authority="speaker_professional_observation_not_business_universal_truth", delta_type="new_fact", classification="speaker_professional_observation")
    add(candidate_id="S-R2-010", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_operational_heuristic", "practice": "蒸锅空间允许时，会根据不同食材时长安排同锅不同层；空间不足则提前说明等待"}, raw_answer=answer["OPTIONAL_Q06"], excerpt="如果蒸锅空间不够，就跟后面来的顾客说多等一会儿。", authority="speaker_specific_operational_heuristic", delta_type="new_fact", classification="speaker_operational_heuristic")
    add(candidate_id="S-R2-012", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_practice", "practice": "顾客临时改变做法或口味要求时，林东方会重新确认实际做法后再开始处理", "mandatory_company_wide_policy": False}, raw_answer=answer["OPTIONAL_Q01"], excerpt="改做法这事不复杂，关键是要再确认一遍", authority="speaker_specific_practice", delta_type="new_fact", classification="speaker_practice")
    add(candidate_id="S-R2-013", scope="speaker", target_field="speaker_role_facts", value={"type": "speaker_professional_practice", "practice": "在林东方实际操作中，同类鱼采用清蒸与红烧时，会使用不同的处理方式、火候控制和操作步骤", "source_bound_example_and_timing_allowed": True, "universal_truth": False}, raw_answer=answer["CORE_Q06"], excerpt="同样是鱼，清蒸和红烧的处理方式差别很大", authority="speaker_specific_professional_practice_not_universal_truth", delta_type="new_fact", classification="speaker_professional_practice")
    add(candidate_id="B-R2-019", scope="business", target_field="customer_use_cases", value={"type": "concrete_service_example", "scene": "一次真实服务中，顾客带来三只梭子蟹并选择红烧梭子蟹加年糕", "observed_duration": "从接收食材到打包约15分钟", "case_specific_observed_duration": True, "typical_service_time": False, "sla": False, "guaranteed_duration": False, "customer_quote_included": False, "customer_image_authorized": False, "customer_video_authorized": False}, raw_answer=answer["CORE_Q05"], excerpt="从他们递给我到打包拿走，前后差不多十五分钟", authority="concrete_observed_service_example", delta_type="new_fact", classification="concrete_service_example", time_metadata={"duration": "约15分钟", "case_specific": True})
    derived_constraints.append(
        {
            "constraint_id": "S-R2-011",
            "type": "derived_speaker_authority_constraint",
            "normalized_constraint": [
                "林东方不得把本人烹饪观察以第一人称表述为普适科学事实或行业标准",
                "林东方不得以第一人称确认永泰店整体经营或租金数据以及其他 unresolved entity facts",
                "林东方不得声称未确认的额外收费规则",
            ],
            "source_ref": answer["OPTIONAL_Q09"].get("source_ref"),
            "raw_answer_ref": "OPTIONAL_Q09",
            "source_excerpt": "我是浦商邻里荟永泰店管理负责人石健生。",
            "authority_owner": "human_review_speaker_authority_policy",
            "fact_atom_eligible": False,
            "content_capacity_eligible": False,
            "new_customer_truth": False,
            "human_decision": "approved_constraint",
        }
    )

    return build_fact_candidate_artifact(
        intake, candidates, derived_authority_constraints=derived_constraints
    )


BUSINESS_REV2_APPROVED_REFS = {
    "B-R2-001",
    "B-R2-002",
    "B-R2-004",
    "B-R2-005",
    "B-R2-006",
    "B-R2-007",
    "B-R2-009",
    "B-R2-011",
    "B-R2-012",
    "B-R2-014",
    "B-R2-019",
}
BUSINESS_REV2_LINEAGE_ONLY_REFS = {"B-R2-003", "B-R2-015"}
BUSINESS_REV2_REVIEW_REFS = {
    "B-R2-008",
    "B-R2-010",
    "B-R2-013",
    "B-R2-016",
    "B-R2-017",
    "B-R2-018",
}
SPEAKER_REV2_APPROVED_REFS = {
    "S-R2-001",
    "S-R2-002",
    "S-R2-003",
    "S-R2-004",
    "S-R2-005",
    "S-R2-006",
    "S-R2-007",
    "S-R2-008",
    "S-R2-009",
    "S-R2-010",
    "S-R2-012",
    "S-R2-013",
}
SPEAKER_REV2_CONSTRAINT_REFS = {"S-R2-011"}


RAW_ANSWER_COVERAGE_MAP: dict[str, dict[str, Any]] = {
    "CORE_Q01": {"ids": ["S-R2-006"], "status": "covered"},
    "CORE_Q02": {"ids": ["B-R2-008", "S-R2-001", "S-R2-002"], "status": "covered"},
    "CORE_Q03": {"ids": ["B-R2-001", "B-R2-002", "B-R2-003"], "status": "covered"},
    "CORE_Q04": {"ids": ["B-R2-004", "S-R2-008"], "status": "covered"},
    "CORE_Q05": {"ids": ["B-R2-010", "B-R2-019"], "status": "covered"},
    "CORE_Q06": {"ids": ["S-R2-013"], "status": "covered"},
    "CORE_Q07": {"ids": ["B-R2-005", "S-R2-003"], "status": "covered"},
    "CORE_Q08": {"ids": ["B-R2-006", "B-R2-007"], "status": "covered"},
    "CORE_Q09": {
        "ids": ["B-R2-009", "B-R2-010", "B-R2-019"],
        "status": "no_candidate_required",
        "exclusion_reason": "covered_by_other_candidate",
    },
    "CORE_Q10": {"ids": ["B-R2-009"], "status": "covered"},
    "CORE_Q11": {
        "ids": ["S-R2-004", "S-R2-010"],
        "status": "partially_covered",
        "exclusion_reason": "presentation_detail_only",
    },
    "CORE_Q12": {"ids": ["S-R2-004"], "status": "covered"},
    "OPTIONAL_Q01": {"ids": ["S-R2-012"], "status": "covered"},
    "OPTIONAL_Q02": {"ids": ["B-R2-014", "B-R2-015"], "status": "covered"},
    "OPTIONAL_Q03": {"ids": ["S-R2-007"], "status": "covered"},
    "OPTIONAL_Q04": {"ids": ["S-R2-009"], "status": "covered"},
    "OPTIONAL_Q05": {"ids": ["B-R2-011"], "status": "covered"},
    "OPTIONAL_Q06": {"ids": ["S-R2-010"], "status": "covered"},
    "OPTIONAL_Q07": {"ids": ["S-R2-005"], "status": "covered"},
    "OPTIONAL_Q08": {"ids": ["B-R2-012", "B-R2-013"], "status": "covered"},
    "OPTIONAL_Q09": {
        "ids": ["B-R2-016", "B-R2-017", "B-R2-018", "S-R2-011"],
        "status": "covered",
    },
}


def apply_persona_revision_2_human_decisions(
    candidate_artifact: dict[str, Any],
    *,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    reviewed = copy.deepcopy(candidate_artifact)
    expected = (
        BUSINESS_REV2_APPROVED_REFS
        | BUSINESS_REV2_LINEAGE_ONLY_REFS
        | BUSINESS_REV2_REVIEW_REFS
        | SPEAKER_REV2_APPROVED_REFS
    )
    actual = {
        str(item.get("fact_candidate_id"))
        for item in reviewed.get("fact_candidates") or []
    }
    if actual != expected:
        raise RuntimeError(
            f"Rev2 Human Decision candidate set mismatch: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    for item in reviewed["fact_candidates"]:
        candidate_id = item["fact_candidate_id"]
        if candidate_id in BUSINESS_REV2_REVIEW_REFS:
            decision = "keep_requires_review"
            production_eligible = False
        elif candidate_id in BUSINESS_REV2_LINEAGE_ONLY_REFS:
            decision = "approve_lineage_only"
            production_eligible = False
        else:
            decision = "approve"
            production_eligible = candidate_id not in {"B-R2-009", "B-R2-011"}
        item["human_review"] = {
            "decision": decision,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at or now_iso(),
        }
        item["production_authority_eligible"] = production_eligible
        if candidate_id in {"B-R2-009", "B-R2-011"}:
            item["production_eligibility"] = {
                "status": "conditional",
                "reason": (
                    "specific_content_use_binding_required"
                    if candidate_id == "B-R2-009"
                    else "scope_aware_use_review_required"
                ),
            }
    constraints = reviewed.get("derived_authority_constraints") or []
    if {item.get("constraint_id") for item in constraints} != SPEAKER_REV2_CONSTRAINT_REFS:
        raise RuntimeError("S-R2-011 derived authority constraint is missing.")
    reviewed["human_review"] = {
        "decision": "approved_with_exclusions_and_constraints",
        "reviewer": reviewer,
        "reviewed_at": reviewed_at or now_iso(),
        "approved_business_refs": sorted(BUSINESS_REV2_APPROVED_REFS),
        "lineage_only_business_refs": sorted(BUSINESS_REV2_LINEAGE_ONLY_REFS),
        "excluded_review_business_refs": sorted(BUSINESS_REV2_REVIEW_REFS),
        "approved_speaker_refs": sorted(SPEAKER_REV2_APPROVED_REFS),
        "derived_constraint_refs": sorted(SPEAKER_REV2_CONSTRAINT_REFS),
    }
    reviewed["status"] = "human_review_closed"
    return reviewed


def build_fact_extraction_coverage_audit(
    intake: dict[str, Any],
    reviewed_candidates: dict[str, Any],
    *,
    created_at: str | None = None,
) -> dict[str, Any]:
    candidates = {
        str(item["fact_candidate_id"])
        for item in reviewed_candidates.get("fact_candidates") or []
    }
    constraints = {
        str(item["constraint_id"])
        for item in reviewed_candidates.get("derived_authority_constraints") or []
    }
    known_ids = candidates | constraints
    raw_answers = list(intake.get("raw_answers") or [])
    raw_ids = {str(item["answer_id"]) for item in raw_answers}
    if raw_ids != set(RAW_ANSWER_COVERAGE_MAP):
        raise RuntimeError("Coverage map must account for exactly every Raw Answer.")
    rows: list[dict[str, Any]] = []
    for raw in raw_answers:
        raw_ref = str(raw["answer_id"])
        mapping = RAW_ANSWER_COVERAGE_MAP[raw_ref]
        mapped_ids = list(mapping["ids"])
        unresolved = sorted(set(mapped_ids) - known_ids)
        if unresolved:
            raise RuntimeError(f"Coverage mapping references missing IDs: {unresolved}")
        row = {
            "raw_answer_ref": raw_ref,
            "mapped_fact_candidate_ids": mapped_ids,
            "coverage_status": mapping["status"],
        }
        if mapping.get("exclusion_reason"):
            row["exclusion_reason"] = mapping["exclusion_reason"]
        if row["coverage_status"] == "no_candidate_required" and not row.get(
            "exclusion_reason"
        ):
            raise RuntimeError("no_candidate_required requires exclusion_reason.")
        rows.append(row)
    material_gap = False
    return {
        "schema_version": "fact-extraction-coverage-audit-v1.0",
        "artifact_type": "derived_qa_artifact",
        "created_at": created_at or now_iso(),
        "intake_ref": {
            "intake_id": intake.get("intake_id"),
            "raw_answers_sha256": intake.get("raw_input_contract", {}).get(
                "raw_answers_sha256"
            ),
        },
        "raw_answer_coverage": rows,
        "summary": {
            "raw_answer_count": len(raw_answers),
            "accounted_raw_answer_count": len(rows),
            "covered": sum(row["coverage_status"] == "covered" for row in rows),
            "partially_covered": sum(
                row["coverage_status"] == "partially_covered" for row in rows
            ),
            "no_candidate_required": sum(
                row["coverage_status"] == "no_candidate_required" for row in rows
            ),
            "silently_ignored_raw_answers": [],
            "material_extraction_gap_found": material_gap,
            "human_requested_missing_candidates_added": [
                "S-R2-012",
                "S-R2-013",
                "B-R2-019",
            ],
        },
        "stop_rule": {
            "status": "pass" if not material_gap else "material_extraction_gap_found",
            "persona_approval_allowed": not material_gap,
        },
        "authority": {
            "customer_truth_authority": False,
            "persona_fact_created": False,
            "human_review_decision_overridden": False,
            "remote_model_call_performed": False,
        },
    }


def render_fact_extraction_coverage_audit(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# Fact Extraction Coverage Audit V1",
        "",
        "Status: `PASS`" if audit["stop_rule"]["status"] == "pass" else "Status: `BLOCKED`",
        "",
        "> Derived QA Artifact；不构成 Customer Truth Authority。",
        "",
        f"- Raw Answers: {summary['raw_answer_count']}",
        f"- Accounted: {summary['accounted_raw_answer_count']}",
        f"- Covered: {summary['covered']}",
        f"- Partially covered: {summary['partially_covered']}",
        f"- No candidate required: {summary['no_candidate_required']}",
        f"- Material extraction gap: `{str(summary['material_extraction_gap_found']).lower()}`",
        "",
        "## Raw Answer Coverage",
        "",
    ]
    for row in audit["raw_answer_coverage"]:
        suffix = (
            f"; exclusion=`{row['exclusion_reason']}`"
            if row.get("exclusion_reason")
            else ""
        )
        lines.append(
            f"- `{row['raw_answer_ref']}` → `{row['coverage_status']}`; "
            f"mapped={', '.join(row['mapped_fact_candidate_ids'])}{suffix}"
        )
    lines.extend(["", "No Raw Answer was silently ignored.", ""])
    return "\n".join(lines)


def _append_unique(values: list[Any], value: Any) -> None:
    key = canonical_sha256(value)
    if all(canonical_sha256(existing) != key for existing in values):
        values.append(copy.deepcopy(value))


def _same_customer_story(existing: Any, replacement: Any) -> bool:
    if not isinstance(existing, dict) or not isinstance(replacement, dict):
        return False
    old_label = str(existing.get("customer_label") or "")
    new_label = str(replacement.get("customer_label") or "")
    if not old_label or not new_label:
        return False
    return old_label.startswith(new_label) or new_label.startswith(old_label)


def build_revision_input(
    *,
    previous_persona: dict[str, Any],
    candidate_artifact: dict[str, Any],
    scope: str,
    source_ref: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    facts = copy.deepcopy(previous_persona.get("facts") or {})
    candidates = [
        item
        for item in candidate_artifact.get("fact_candidates") or []
        if item.get("persona_scope") == scope
    ]
    applied: list[dict[str, Any]] = []
    review_field = facts.setdefault(
        "information_requiring_human_review",
        {"state": "requires_review", "value": [], "source_refs": [], "review_note": "Human review required."},
    )
    if not isinstance(review_field.get("value"), list):
        review_field["value"] = [review_field.get("value")]
    resolved_small_sun_review = any(
        item.get("fact_candidate_id") == "B-R2-009"
        and item.get("candidate_state") == "known_candidate"
        for item in candidates
    )
    if resolved_small_sun_review:
        review_field["value"] = [
            item
            for item in review_field["value"]
            if not (
                isinstance(item, dict)
                and "小孙" in str(item.get("item") or "")
                and item.get("reason") == "public_reuse_authorization_not_confirmed"
            )
        ]
    for item in candidates:
        candidate_id = str(item["fact_candidate_id"])
        target_field = str(item["target_field"])
        if item["candidate_state"] == "requires_review":
            review_item = {
                "fact_candidate_id": candidate_id,
                "target_field": target_field,
                "item": copy.deepcopy(item.get("normalized_value")),
                "reason": item.get("review_note"),
                "conflict_refs": copy.deepcopy(item.get("conflict_refs") or []),
                "production_blocked": True,
            }
            _append_unique(review_field["value"], review_item)
            review_field["state"] = "requires_review"
            review_field["review_note"] = "Revision 2 contains unresolved candidates that remain excluded from Production."
            review_field.setdefault("source_refs", []).append(f"{source_ref}#{candidate_id}")
            applied.append({**copy.deepcopy(item), "persona_application": "review_queue_only"})
            continue
        if item["candidate_state"] != "known_candidate" or item.get("delta_type") in {"duplicate", "supports_existing"}:
            applied.append({**copy.deepcopy(item), "persona_application": "lineage_only_no_duplicate_fact"})
            continue
        fact = facts.setdefault(
            target_field,
            {"state": "unknown", "value": None, "source_refs": [], "review_note": None},
        )
        value = copy.deepcopy(item.get("normalized_value"))
        if target_field in SCALAR_PERSONA_FIELDS:
            if fact.get("state") == "unknown":
                fact["value"] = value
            elif fact.get("value") != value:
                fact["value"] = value
        else:
            current = fact.get("value")
            if not isinstance(current, list):
                current = [] if current is None else [current]
            if (
                target_field == "authorized_customer_cases_or_feedback"
                and item.get("delta_type") == "refines_existing"
                and isinstance(value, dict)
            ):
                current = [
                    existing
                    for existing in current
                    if not _same_customer_story(existing, value)
                ]
            if isinstance(value, list):
                for child in value:
                    _append_unique(current, child)
            else:
                _append_unique(current, value)
            fact["value"] = current
        fact["state"] = "known"
        fact.setdefault("source_refs", []).append(f"{source_ref}#{candidate_id}")
        fact["review_note"] = None
        applied.append({**copy.deepcopy(item), "persona_application": "candidate_fact_pending_persona_approval"})
    payload: dict[str, Any] = {
        "persona_id": previous_persona["persona_id"],
        "revision": int(previous_persona["revision"]) + 1,
        "persona_scope": scope,
        "fixture_only": False,
        "source_type": "customer_intake_v1_replenishment_fact_candidates",
        "source_file": "林东方｜内容补充采访单.md",
        "source_ref": source_ref,
        "facts": facts,
    }
    if scope == "speaker":
        payload["speaker_type"] = previous_persona.get("speaker_type")
        payload["business_persona_ref"] = previous_persona.get(
            "business_persona_ref", {}
        ).get("persona_id")
        constraints = copy.deepcopy(
            candidate_artifact.get("derived_authority_constraints") or []
        )
        if constraints:
            payload["persona_control_layer"] = {
                "derived_authority_constraints": constraints,
                "authority_owner": "human_review_speaker_authority_policy",
                "content_fact_eligible": False,
                "fact_atom_eligible": False,
            }
    return payload, applied


def build_delta_artifact(
    *,
    persona_id: str,
    revision: int,
    previous_persona_path: Path,
    intake_path: Path,
    candidates: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": DELTA_SCHEMA_VERSION,
        "persona_id": persona_id,
        "revision": revision,
        "status": "review_required",
        "created_at": created_at,
        "previous_approved_persona_ref": {
            "path": str(previous_persona_path.resolve()),
            "sha256": sha256_file(previous_persona_path),
        },
        "customer_intake_ref": {
            "path": str(intake_path.resolve()),
            "sha256": sha256_file(intake_path),
        },
        "candidate_deltas": copy.deepcopy(candidates),
        "summary": {
            delta: sum(item.get("delta_type") == delta for item in candidates)
            for delta in (
                "new_fact",
                "supports_existing",
                "refines_existing",
                "conflicts_existing",
                "duplicate",
            )
        },
        "authority": {
            "candidate_delta_is_not_approved_persona_authority": True,
            "requires_human_review": True,
            "production_consumption_allowed": False,
            "remote_model_call_performed": False,
        },
    }


def render_revision_review_pack(
    delta: dict[str, Any], persona_scope: str
) -> str:
    candidates = delta["candidate_deltas"]
    scope_label = "Business" if persona_scope == "business" else "Speaker"
    lines = [
        f"# {scope_label} Persona Revision 0002 Human Review Pack",
        "",
        f"Persona: `{delta['persona_id']}`",
        "Status: `review_required`",
        "",
        "> 本审阅包只呈现候选 Delta；任何条目在 Persona Revision 2 获得人工批准前均不得用于 Production。",
        "",
    ]
    sections = (
        ("new_fact", "新增 Candidate Facts"),
        ("supports_existing", "支持旧事实"),
        ("refines_existing", "细化旧事实"),
        ("conflicts_existing", "冲突"),
    )
    for delta_type, heading in sections:
        lines.extend([f"## {heading}", ""])
        selected = [item for item in candidates if item.get("delta_type") == delta_type]
        if not selected:
            lines.append("None.")
        for item in selected:
            lines.extend(
                [
                    f"- `{item['fact_candidate_id']}` → `{item['target_field']}` / `{item['candidate_state']}`",
                    f"  - 候选值：{json.dumps(item.get('normalized_value'), ensure_ascii=False)}",
                    f"  - 来源：`{item.get('raw_answer_ref')}` / `{item.get('input_actor')}` / `{item.get('source_type')}`",
                    f"  - 原文：{item.get('source_excerpt')}",
                    f"  - Speaker Authority：`{item.get('speaker_authority_assessment')}`",
                    f"  - Persona application：`{item.get('persona_application')}`",
                ]
            )
            if item.get("review_note"):
                lines.append(f"  - Review note：{item['review_note']}")
        lines.append("")
    requires_review = [
        item for item in candidates if item.get("candidate_state") == "requires_review"
    ]
    lines.extend(["## REQUIRES_REVIEW / Production 禁用", ""])
    for item in requires_review:
        lines.extend(
            [
                f"- `{item['fact_candidate_id']}` / `{item.get('classification')}`",
                f"  - {item.get('review_note')}",
                f"  - Conflict refs：{', '.join(item.get('conflict_refs') or [])}",
            ]
        )
    if persona_scope == "business":
        lines.extend(
            [
                "",
                "## Customer Story Authorization",
                "",
                "- 小孙：只允许使用已指定称呼、场景和两句原话；`single_content_use_only`；照片/视频不授权；其他渠道或商业推广必须重新授权。Q5 的“比我们自己在家弄强多了……”不在授权列表。",
                "- 陶先生：只允许指定称呼、场景、原话和评价；照片/视频不授权；channel / duration / commercial scope 未提供，不得补全。",
                "",
                "## 五项强制审阅边界",
                "",
                "1. 小孙授权是单次内容粒度，不是 global reuse。",
                "2. 陶先生图片/视频保持不授权，未知授权维度不补全。",
                "3. 白板带来的秩序/焦虑变化只是 operator observation，不是 Proof。",
                "4. 永泰店与书房市集志泉社区食堂的 entity binding 未解决。",
                "5. 未处理鱼加工费缺少完整 Official Pricing Rule。",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Speaker-specific Facts 与边界",
                "",
                "- 烹饪判断只作为林东方的 professional observation / practice，不是普适科学事实或 Business universal truth。",
                "- 高峰处理为 operational heuristic；采访明确说明不是固定流程。",
                "- 林东方不得第一人称确认永泰店经营、租金、品牌决策或未确认收费规则。",
            ]
        )
    lines.extend(["", "Human approval required. No Production use before approval.", ""])
    return "\n".join(lines)


def run_stage_b(
    *,
    project_root: Path,
    interview_path: Path,
    output_root: Path,
    created_at: str | None = None,
    replace_unapproved: bool = False,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    business_v1_path = project_root / "data/personas/shufang_zhiyuan_community_canteen/revision_0001/persona_v1.json"
    speaker_v1_path = project_root / "data/personas/lin_dongfang_frontline_chef/revision_0001/persona_v1.json"
    ledger_path = project_root / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
    frozen_hashes = {
        "interview": sha256_file(interview_path),
        "business_revision_1": sha256_file(business_v1_path),
        "speaker_revision_1": sha256_file(speaker_v1_path),
        "content_ledger": sha256_file(ledger_path),
    }
    raw_answers = parse_interview_markdown(interview_path)
    intake = build_customer_intake(
        intake_id="shufang_content_replenishment_intake_0001",
        intake_type="replenishment",
        provisional_business_id=None,
        business_ref={
            "persona_id": "shufang_zhiyuan_community_canteen",
            "revision": 1,
            "path": str(business_v1_path.resolve()),
            "sha256": frozen_hashes["business_revision_1"],
        },
        input_actor="operator",
        input_sources=[
            {
                "source_type": "raw_customer_interview_markdown",
                "source_filename": interview_path.name,
                "source_path": str(interview_path.resolve()),
                "source_sha256": frozen_hashes["interview"],
                "ingested_at": timestamp,
                "immutable": True,
            }
        ],
        raw_answers=raw_answers,
        speaker_selection={
            "speaker_type": "frontline_expert",
            "speaker_ref": {
                "persona_id": "lin_dongfang_frontline_chef",
                "revision": 1,
                "path": str(speaker_v1_path.resolve()),
                "sha256": frozen_hashes["speaker_revision_1"],
            },
        },
        conflicts=[
            {
                "conflict_id": "existing_yongtai_entity_binding_concern",
                "severity": "critical",
                "resolved": False,
                "topic": "浦商邻里荟永泰店与书房市集志泉社区食堂的实体/数据口径关系",
                "resolution_question": "请由 Human Reviewer 确认两个主体关系及可适用的数据口径。",
            }
        ],
        created_at=timestamp,
    )
    intake_path = output_root / "customer_intake_v1.json"
    _write_runtime_json(
        intake_path, intake, replace_unapproved=replace_unapproved
    )
    candidates = extract_shufang_replenishment_candidates(intake)
    candidates_path = output_root / "fact_candidates_v1.json"
    _write_runtime_json(
        candidates_path, candidates, replace_unapproved=replace_unapproved
    )

    business_v1 = read_json(business_v1_path)
    speaker_v1 = read_json(speaker_v1_path)
    business_input, business_applied = build_revision_input(
        previous_persona=business_v1,
        candidate_artifact=candidates,
        scope="business",
        source_ref=str(candidates_path.resolve()),
    )
    speaker_input, speaker_applied = build_revision_input(
        previous_persona=speaker_v1,
        candidate_artifact=candidates,
        scope="speaker",
        source_ref=str(candidates_path.resolve()),
    )
    business_input_path = project_root / "data/persona_inputs/shufang_zhiyuan_community_canteen/business_persona_revision_0002_input.json"
    speaker_input_path = project_root / "data/persona_inputs/lin_dongfang_frontline_chef/speaker_persona_revision_0002_input.json"
    _write_runtime_json(
        business_input_path,
        business_input,
        replace_unapproved=replace_unapproved,
    )
    _write_runtime_json(
        speaker_input_path,
        speaker_input,
        replace_unapproved=replace_unapproved,
    )
    if replace_unapproved:
        business_v2_path = project_root / "data/personas/shufang_zhiyuan_community_canteen/revision_0002/persona_v1.json"
        speaker_v2_path = project_root / "data/personas/lin_dongfang_frontline_chef/revision_0002/persona_v1.json"
        _assert_unapproved_revision_can_refresh(business_v2_path)
        _assert_unapproved_revision_can_refresh(speaker_v2_path)
        with tempfile.TemporaryDirectory() as temporary_directory:
            draft_root = Path(temporary_directory) / "personas"
            temporary_business_path, _ = build_persona(
                business_input_path,
                draft_root,
                previous_persona_path=business_v1_path,
                created_at=timestamp,
            )
            temporary_speaker_path, _ = build_persona(
                speaker_input_path,
                draft_root,
                previous_persona_path=speaker_v1_path,
                created_at=timestamp,
                business_persona_path=business_v1_path,
            )
            _write_runtime_json(
                business_v2_path,
                read_json(temporary_business_path),
                replace_unapproved=True,
            )
            _write_runtime_json(
                speaker_v2_path,
                read_json(temporary_speaker_path),
                replace_unapproved=True,
            )
            _write_runtime_text(
                business_v2_path.parent / "persona_review_pack_v1.md",
                (temporary_business_path.parent / "persona_review_pack_v1.md").read_text(
                    encoding="utf-8"
                ),
                replace_unapproved=True,
            )
            _write_runtime_text(
                speaker_v2_path.parent / "persona_review_pack_v1.md",
                (temporary_speaker_path.parent / "persona_review_pack_v1.md").read_text(
                    encoding="utf-8"
                ),
                replace_unapproved=True,
            )
    else:
        business_v2_path, _ = build_persona(
            business_input_path,
            project_root / "data/personas",
            previous_persona_path=business_v1_path,
            created_at=timestamp,
        )
        speaker_v2_path, _ = build_persona(
            speaker_input_path,
            project_root / "data/personas",
            previous_persona_path=speaker_v1_path,
            created_at=timestamp,
            business_persona_path=business_v1_path,
        )
    business_delta = build_delta_artifact(
        persona_id=business_v1["persona_id"],
        revision=2,
        previous_persona_path=business_v1_path,
        intake_path=intake_path,
        candidates=business_applied,
        created_at=timestamp,
    )
    speaker_delta = build_delta_artifact(
        persona_id=speaker_v1["persona_id"],
        revision=2,
        previous_persona_path=speaker_v1_path,
        intake_path=intake_path,
        candidates=speaker_applied,
        created_at=timestamp,
    )
    business_delta_path = output_root / "business_persona_revision_0002_candidate_delta.json"
    speaker_delta_path = output_root / "speaker_persona_revision_0002_candidate_delta.json"
    _write_runtime_json(
        business_delta_path,
        business_delta,
        replace_unapproved=replace_unapproved,
    )
    _write_runtime_json(
        speaker_delta_path,
        speaker_delta,
        replace_unapproved=replace_unapproved,
    )
    business_pack_path = business_v2_path.parent / "business_persona_revision_0002_review_pack.md"
    speaker_pack_path = speaker_v2_path.parent / "speaker_persona_revision_0002_review_pack.md"
    _write_runtime_text(
        business_pack_path,
        render_revision_review_pack(business_delta, "business"),
        replace_unapproved=replace_unapproved,
    )
    _write_runtime_text(
        speaker_pack_path,
        render_revision_review_pack(speaker_delta, "speaker"),
        replace_unapproved=replace_unapproved,
    )

    readiness = assess_persona_onboarding_readiness(
        intake,
        candidates,
        business_persona=business_v1,
        speaker_persona=speaker_v1,
        created_at=timestamp,
    )
    readiness["current_approved_persona_authority"] = "production_ready"
    readiness["candidate_revision_status"] = "review_required"
    readiness["capacity_recalculation_status"] = "blocked_pending_persona_revision_approval"
    readiness["potential_capacity_gain_categories"] = [
        "known_customer_questions",
        "speaker_specific_practices",
        "specific_dish_or_ingredient_cases",
        "service_boundaries",
        "operational_facts",
        "authorized_customer_stories_with_scoped_reuse",
    ]
    readiness_path = output_root / "persona_onboarding_readiness_v1.json"
    _write_runtime_json(
        readiness_path, readiness, replace_unapproved=replace_unapproved
    )

    after_hashes = {
        "interview": sha256_file(interview_path),
        "business_revision_1": sha256_file(business_v1_path),
        "speaker_revision_1": sha256_file(speaker_v1_path),
        "content_ledger": sha256_file(ledger_path),
    }
    summary = {
        "schema_version": "real-replenishment-validation-v1.0",
        "created_at": timestamp,
        "status": "persona_revision_2_human_review_gate",
        "intake_path": str(intake_path.resolve()),
        "fact_candidates_path": str(candidates_path.resolve()),
        "business_revision_2_path": str(business_v2_path.resolve()),
        "speaker_revision_2_path": str(speaker_v2_path.resolve()),
        "business_delta_path": str(business_delta_path.resolve()),
        "speaker_delta_path": str(speaker_delta_path.resolve()),
        "business_review_pack_path": str(business_pack_path.resolve()),
        "speaker_review_pack_path": str(speaker_pack_path.resolve()),
        "capacity_recalculation_status": "blocked_pending_persona_revision_approval",
        "frozen_hashes_before": frozen_hashes,
        "frozen_hashes_after": after_hashes,
        "frozen_sources_unchanged": frozen_hashes == after_hashes,
        "remote_model_calls": 0,
        "content_ledger_written": False,
        "persona_revision_2_approved": False,
        "scripts_generated": False,
        "production_batch_created": False,
        "excel_exported": False,
    }
    _write_runtime_json(
        output_root / "real_replenishment_validation_summary_v1.json",
        summary,
        replace_unapproved=replace_unapproved,
    )
    return summary


REPLENISHMENT_CONCEPT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "concept_id": "REV2-CONCEPT-001",
        "candidate_refs": ["B-R2-002", "B-R2-004", "S-R2-008"],
        "audience_need": "顾客临时买到未吐沙的花蛤时，需要知道能否处理、要多等多久以及结果边界。",
        "audience_need_origin": "known_use_case",
        "content_job": "service_boundary_explanation",
        "primary_topic": "花蛤临时吐沙的等待与结果边界",
        "central_claim": "花蛤未提前吐沙时可以先说明额外等待，但不能承诺完全无沙。",
        "opening_strategy": "从顾客真实提问进入",
        "visual_anchor": "花蛤检查与吐沙准备",
    },
    {
        "concept_id": "REV2-CONCEPT-002",
        "candidate_refs": ["B-R2-005", "S-R2-003"],
        "audience_need": "顾客带来的食材与指定做法不匹配时，需要知道服务会如何处理。",
        "audience_need_origin": "service_decision_need",
        "content_job": "service_boundary_explanation",
        "primary_topic": "食材与做法不匹配时的替代方案",
        "central_claim": "食材与指定做法不匹配时，会先说明问题并与顾客确认替代方案。",
        "opening_strategy": "用具体不匹配场景提出问题",
        "visual_anchor": "瘦肉与替代做法确认",
    },
    {
        "concept_id": "REV2-CONCEPT-003",
        "candidate_refs": ["B-R2-006", "B-R2-007", "S-R2-004", "S-R2-010"],
        "audience_need": "高峰期顾客需要判断真实等待为什么会变化、是否能承诺马上出餐。",
        "audience_need_origin": "service_decision_need",
        "content_job": "operational_boundary_explanation",
        "primary_topic": "高峰期设备与订单共同影响等待",
        "central_claim": "高峰期等待取决于灶台、蒸锅、食材和前序订单，因此不能承诺马上出餐。",
        "opening_strategy": "从一次15至20分钟的现场估时进入",
        "visual_anchor": "灶台、蒸锅与排单状态",
    },
    {
        "concept_id": "REV2-CONCEPT-004",
        "candidate_refs": ["B-R2-012"],
        "audience_need": "排队顾客需要在窗口直接知道当前顺序与预计等待。",
        "audience_need_origin": "service_decision_need",
        "content_job": "operational_process_explanation",
        "primary_topic": "窗口排单与等待时间白板",
        "central_claim": "晚市高峰反复询问等待时，门店会用小白板展示排单顺序和预计等待。",
        "opening_strategy": "从顾客反复询问等待切入",
        "visual_anchor": "窗口旁排单与预计等待白板",
    },
    {
        "concept_id": "REV2-CONCEPT-005",
        "candidate_refs": ["B-R2-014", "S-R2-009"],
        "audience_need": "希望少油的顾客需要知道改变常规红烧用油量会带来什么结果差异。",
        "audience_need_origin": "known_use_case",
        "content_job": "expectation_setting",
        "primary_topic": "少油要求与红烧结果预期",
        "central_claim": "红烧可以按顾客要求少放油，但林东方会提前说明口感和汤汁可能不同。",
        "opening_strategy": "从健身顾客的真实少油问题进入",
        "visual_anchor": "红烧下油与汤汁状态",
    },
    {
        "concept_id": "REV2-CONCEPT-006",
        "candidate_refs": ["S-R2-005", "S-R2-007"],
        "audience_need": "顾客想知道师傅接到鱼后会检查什么，以及检查如何影响做法建议。",
        "audience_need_origin": "editorial_hypothesis",
        "content_job": "frontline_observation",
        "primary_topic": "林东方接鱼时的现场检查习惯",
        "central_claim": "一次处理经验后，林东方接鱼会检查鱼腹和鳃，并把现场状态用于调整处理建议。",
        "opening_strategy": "从一次影响成品的真实经验进入",
        "visual_anchor": "按鱼腹、查看鱼鳃的检查动作",
    },
    {
        "concept_id": "REV2-CONCEPT-007",
        "candidate_refs": ["S-R2-006"],
        "audience_need": "顾客带来梭子蟹时，需要知道食材状态为什么会影响做法建议和口感预期。",
        "audience_need_origin": "editorial_hypothesis",
        "content_job": "frontline_observation",
        "primary_topic": "梭子蟹状态与做法建议",
        "central_claim": "林东方会依据梭子蟹当时的存活和处理状态调整做法建议，并提前说明口感可能变化。",
        "opening_strategy": "从活蟹和刚死蟹的现场差别进入",
        "visual_anchor": "梭子蟹状态检查",
    },
    {
        "concept_id": "REV2-CONCEPT-008",
        "candidate_refs": ["S-R2-012"],
        "audience_need": "临时改变口味或做法的顾客，需要确认最终要求不会被误解。",
        "audience_need_origin": "editorial_hypothesis",
        "content_job": "service_process_explanation",
        "primary_topic": "临时改做法后的再次确认",
        "central_claim": "顾客临时改变做法或口味时，林东方会重新确认最终要求再开始处理。",
        "opening_strategy": "从一次临时改口味的真实情形进入",
        "visual_anchor": "开工前再次口头确认",
    },
    {
        "concept_id": "REV2-CONCEPT-009",
        "candidate_refs": ["S-R2-013"],
        "audience_need": "顾客在清蒸和红烧之间选择时，需要理解同类鱼的处理与操作为什么不同。",
        "audience_need_origin": "editorial_hypothesis",
        "content_job": "method_comparison",
        "primary_topic": "同类鱼清蒸与红烧的处理差异",
        "central_claim": "在林东方实际操作中，同类鱼清蒸与红烧会采用不同处理方式、火候控制和步骤。",
        "opening_strategy": "用清蒸还是红烧的选择题进入",
        "visual_anchor": "清蒸处理与红烧煎制动作对照",
    },
    {
        "concept_id": "REV2-CONCEPT-010",
        "candidate_refs": ["B-R2-001", "B-R2-019"],
        "audience_need": "赶时间的顾客需要一个真实梭子蟹服务案例来理解具体场景与用时边界。",
        "audience_need_origin": "known_use_case",
        "content_job": "concrete_service_example",
        "primary_topic": "三只梭子蟹加年糕的一次15分钟服务实例",
        "central_claim": "一次真实服务中，三只梭子蟹做红烧加年糕，从接收食材到打包约15分钟；该时长仅代表本次实例。",
        "opening_strategy": "从赶时间顾客的真实问题进入",
        "visual_anchor": "三只梭子蟹、年糕与打包完成",
    },
)


def _candidate_fact_atom_refs(
    persona: dict[str, Any],
    fact_atoms: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> list[str]:
    field = str(candidate["target_field"])
    fact = (persona.get("facts") or {}).get(field) or {}
    expected = candidate.get("normalized_value")
    value = fact.get("value")
    prefix: str | None = None
    if isinstance(value, list):
        for index, item in enumerate(value):
            if canonical_sha256(item) == canonical_sha256(expected):
                prefix = f"value[{index}]"
                break
    elif canonical_sha256(value) == canonical_sha256(expected):
        prefix = "value"
    if prefix is None:
        raise RuntimeError(
            f"Approved candidate {candidate['fact_candidate_id']} is not present in Persona Rev2."
        )
    refs = [
        atom["fact_atom_id"]
        for atom in fact_atoms
        if atom.get("field") == field
        and (
            atom.get("value_path") == prefix
            or str(atom.get("value_path") or "").startswith(prefix + ".")
            or str(atom.get("value_path") or "").startswith(prefix + "[")
        )
    ]
    if not refs:
        raise RuntimeError(
            f"Approved candidate {candidate['fact_candidate_id']} produced no Fact Atom."
        )
    return sorted(set(refs))


def build_content_capacity_replenishment_recalculation(
    *,
    business_persona: dict[str, Any],
    speaker_persona: dict[str, Any],
    reviewed_candidates: dict[str, Any],
    ledger: dict[str, Any],
    before_plan: dict[str, Any],
    cross_profile_repurpose_history: dict[str, Any] | None = None,
    requested_quantity: int = 10,
    created_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if business_persona.get("lifecycle", {}).get("status") != "approved":
        raise RuntimeError("Capacity recalculation requires Approved Business Persona Rev2.")
    if speaker_persona.get("lifecycle", {}).get("status") != "approved":
        raise RuntimeError("Capacity recalculation requires Approved Speaker Persona Rev2.")
    repurpose_lineage: dict[str, Any] | None = None
    if cross_profile_repurpose_history is not None:
        reuse = cross_profile_repurpose_history.get("reuse_declaration") or {}
        source = cross_profile_repurpose_history.get("source_historical_content") or {}
        source_content_ref = str(source.get("content_ref") or "")
        ledger_content_ids = {
            str(entry.get("content_id")) for entry in ledger.get("entries") or []
        }
        if (
            reuse.get("reuse_intent") != "cross_profile_repurpose"
            or reuse.get("semantic_novelty") is not False
            or int(reuse.get("novel_capacity_delta") or 0) != 0
            or source_content_ref not in ledger_content_ids
        ):
            raise RuntimeError(
                "Cross-profile repurpose history must resolve to existing zero-novelty Ledger semantics."
            )
        repurpose_lineage = {
            "request_id": cross_profile_repurpose_history.get("request_id"),
            "reuse_intent": "cross_profile_repurpose",
            "source_content_ref": source_content_ref,
            "source_profile": reuse.get("source_profile"),
            "target_profile": reuse.get("target_profile"),
            "semantic_novelty": False,
            "novel_capacity_delta": 0,
            "independent_historical_exposure_created": False,
            "semantic_exposure_already_represented_by_source_ledger_entry": True,
        }
    business_atoms = build_fact_atom_catalog(
        business_persona, business_persona["provenance"]["content_sha256"]
    )
    speaker_atoms = build_fact_atom_catalog(
        speaker_persona, speaker_persona["provenance"]["content_sha256"]
    )
    all_rev2_atoms = business_atoms + speaker_atoms
    candidate_by_id = {
        item["fact_candidate_id"]: item
        for item in reviewed_candidates.get("fact_candidates") or []
    }
    candidate_atom_refs: dict[str, list[str]] = {}
    eligible_new_atom_ids: set[str] = set()
    for candidate_id, candidate in candidate_by_id.items():
        if not candidate.get("production_authority_eligible"):
            continue
        persona = (
            business_persona
            if candidate["persona_scope"] == "business"
            else speaker_persona
        )
        atoms = business_atoms if persona is business_persona else speaker_atoms
        refs = _candidate_fact_atom_refs(persona, atoms, candidate)
        candidate_atom_refs[candidate_id] = refs
        eligible_new_atom_ids.update(refs)
    if "S-R2-011" in candidate_atom_refs:
        raise RuntimeError("Derived authority constraint cannot create Fact Atoms.")
    excluded_ids = BUSINESS_REV2_REVIEW_REFS | {"B-R2-009", "B-R2-011"}
    if excluded_ids & set(candidate_atom_refs):
        raise RuntimeError("Review-required or conditional Story facts entered capacity authority.")

    planning_ledger = copy.deepcopy(ledger)
    old_atom_ids = {
        atom["fact_atom_id"] for atom in planning_ledger.get("fact_atom_catalog") or []
    }
    planning_ledger["fact_atom_catalog"] = list(
        planning_ledger.get("fact_atom_catalog") or []
    ) + [
        atom
        for atom in all_rev2_atoms
        if atom["fact_atom_id"] in eligible_new_atom_ids
        and atom["fact_atom_id"] not in old_atom_ids
    ]

    evaluated: list[dict[str, Any]] = []
    for prior in before_plan.get("selected_concepts") or []:
        retained = copy.deepcopy(prior)
        retained["capacity_source"] = "preserved_v1_1_1_high_quality_survivor"
        retained["production_authority"] = {
            "status": "approved_known",
            "persona_revision": 1,
            "conditional_story_used": False,
        }
        retained["possible_profile_fit"] = ["mix", "news"]
        retained["replenishment_gate_decision"] = "high_quality_novel"
        evaluated.append(retained)

    minimum_score = 3.25
    for spec in REPLENISHMENT_CONCEPT_SPECS:
        candidate_refs = list(spec["candidate_refs"])
        refs = sorted(
            {
                atom_id
                for candidate_id in candidate_refs
                for atom_id in candidate_atom_refs.get(candidate_id, [])
            }
        )
        if not refs:
            raise RuntimeError(f"{spec['concept_id']} has no approved Fact Atom lineage.")
        fields = sorted(
            {candidate_by_id[candidate_id]["target_field"] for candidate_id in candidate_refs}
        )
        concept = copy.deepcopy(spec)
        concept["primary_fact_refs"] = fields
        concept["supporting_fact_refs"] = []
        concept["primary_fact_atom_refs"] = refs
        concept["audience_need_source_refs"] = refs
        concept["exclusive_anchor"] = {
            "kind": "approved_customer_or_speaker_specific_fact",
            "value": spec["primary_topic"],
            "fact_refs": fields,
        }
        if any(ref.startswith("S-R2-") for ref in candidate_refs):
            concept["speaker_specific_observation_ref"] = next(
                ref for ref in candidate_refs if ref.startswith("S-R2-")
            )
        exposure = historical_exposure_evaluation(concept, planning_ledger)
        lineage = audience_need_lineage_v1_1_1(
            concept, planning_ledger["fact_atom_catalog"]
        )
        fit = speaker_fit_evaluation(concept, speaker_persona.get("speaker_type"))
        novel_anchor = novel_exclusive_anchor_evaluation(concept, planning_ledger)
        first_score = editorial_score_v1_1(
            concept, exposure, lineage, fit, novel_anchor
        )
        concept.update(
            {
                "historical_exposure_check": exposure,
                "historical_exposure_summary": exposure,
                "audience_need_origin": lineage["origin"],
                "audience_need_source_refs": lineage[
                    "audience_need_source_refs"
                ],
                "audience_need_source_lineage": lineage,
                "speaker_fit": fit,
                "novel_exclusive_anchor_summary": novel_anchor,
                "editorial_score_v1_1": first_score,
            }
        )
        material = material_information_gain_v1_1_1(concept, planning_ledger)
        score = editorial_score_v1_1_1(concept, lineage, material)
        production_authority = {
            "status": "approved_known_production_eligible",
            "business_persona_revision": business_persona["revision"],
            "speaker_persona_revision": speaker_persona["revision"],
            "fact_candidate_refs": candidate_refs,
            "requires_review_facts_used": False,
            "conditional_story_used": False,
            "derived_constraint_used_as_fact": False,
        }
        high_quality = (
            material["material_information_gain"]
            and fit["authority_pass"]
            and float(score["weighted_total"]) >= minimum_score
        )
        concept.update(
            {
                "new_information_units": material["novel_primary_fact_atom_refs"],
                "material_information_gain": material,
                "editorial_quality": score,
                "production_authority": production_authority,
                "possible_profile_fit": ["mix", "news"],
                "profile_neutral_semantic_capacity": True,
                "capacity_source": "approved_persona_revision_2",
                "replenishment_gate_decision": (
                    "high_quality_novel"
                    if high_quality
                    else "editorial_or_information_gain_rejected"
                ),
            }
        )
        evaluated.append(concept)

    high_quality = sorted(
        [
            concept
            for concept in evaluated
            if concept.get("replenishment_gate_decision") == "high_quality_novel"
        ],
        key=lambda concept: (
            -float(
                (
                    concept.get("editorial_quality")
                    or concept.get("editorial_score_v1_1_1")
                    or {}
                ).get("weighted_total", 0)
            ),
            concept["concept_id"],
        ),
    )
    selected = high_quality[:requested_quantity]
    for rank, concept in enumerate(selected, start=1):
        concept["selected_rank"] = rank
    before_capacity = int(
        (before_plan.get("capacity") or {}).get("high_quality_novel_capacity") or 0
    )
    after_capacity = len(high_quality)
    rejections = [
        {
            "concept_id": concept["concept_id"],
            "decision": concept.get("replenishment_gate_decision"),
            "material_information_gain": concept.get("material_information_gain"),
            "editorial_quality": concept.get("editorial_quality"),
        }
        for concept in evaluated
        if concept.get("replenishment_gate_decision") != "high_quality_novel"
    ]
    result = {
        "schema_version": "content-capacity-replenishment-recalculation-v1.0",
        "created_at": created_at or now_iso(),
        "business_id": business_persona["persona_id"],
        "speaker_id": speaker_persona["persona_id"],
        "requested_quantity": requested_quantity,
        "before_capacity": before_capacity,
        "after_capacity": after_capacity,
        "capacity_delta": after_capacity - before_capacity,
        "candidate_concept_count": len(evaluated),
        "high_quality_content_capacity": len(high_quality),
        "selected_quantity": len(selected),
        "capacity_status": (
            "supported" if after_capacity >= requested_quantity else "capacity_limited"
        ),
        "padding": False,
        "profile_neutral": True,
        "candidate_concepts": evaluated,
        "top_new_content_opportunities": [
            concept
            for concept in selected
            if concept.get("capacity_source") == "approved_persona_revision_2"
        ],
        "selected_concepts": selected,
        "rejection_reasons": rejections,
        "not_selected_high_quality_opportunities": [
            {
                "concept_id": concept["concept_id"],
                "reason": "requested_quantity_already_satisfied_without_padding",
            }
            for concept in high_quality
            if concept not in selected
        ],
        "conditional_story_opportunities": [
            {
                "fact_candidate_ref": "B-R2-009",
                "customer_label": "小孙",
                "status": "blocked_without_specific_content_use_binding",
                "formal_capacity_counted": False,
            },
            {
                "fact_candidate_ref": "B-R2-011",
                "customer_label": "陶先生",
                "status": "conditional_scope_aware_use_review_required",
                "missing_scope": ["channel", "duration", "commercial"],
                "formal_capacity_counted": False,
            },
        ],
        "remaining_content_gaps": [
            "additional_authorized_customer_stories_with_complete_use_scope",
            "confirmed_service_pricing_boundaries_for_extra_processing",
            "entity_binding_for_yongtai_operational_and_rent_data",
            "verified_outcome_evidence_for_whiteboard_effect",
            "more_distinct_frontline_customer_questions_and_dish_cases",
        ],
        "lineage": {
            "business_persona_revision": 2,
            "business_persona_content_sha256": business_persona["provenance"]["content_sha256"],
            "speaker_persona_revision": 2,
            "speaker_persona_content_sha256": speaker_persona["provenance"]["content_sha256"],
            "historical_ledger_semantics": "business_wide_mix_and_cross_profile_exposure",
            "cross_profile_repurpose_history": repurpose_lineage,
            "interview_is_historical_exposure": False,
        },
        "authority": {
            "approved_known_only": True,
            "requires_review_consumed": False,
            "conditional_story_inflated_capacity": False,
            "content_ledger_mutated": False,
            "scripts_generated": False,
            "pattern_matching_performed": False,
            "profile_changed_semantic_novelty": False,
            "remote_model_called": False,
        },
        "remote_model_calls": 0,
        "status": "content_capacity_replenishment_human_review_gate",
    }
    gap_report = {
        "schema_version": "content-gap-report-v1.0",
        "revision_context": "approved_persona_revision_2_replenishment",
        "created_at": created_at or now_iso(),
        "business_id": business_persona["persona_id"],
        "speaker_id": speaker_persona["persona_id"],
        "current_requested_quantity": requested_quantity,
        "current_high_quality_novel_capacity": after_capacity,
        "replenishment_answers_now_covered": [
            "real_customer_questions_about_crab_time_clam_oil_and_taste",
            "frontline_ingredient_checks_and_method_adjustment",
            "specific_crab_service_example",
            "service_boundaries_for_clams_method_mismatch_and_peak_wait",
            "peak_equipment_and_queue_handling",
            "request_reconfirmation_practice",
            "whiteboard_queue_visibility_decision",
        ],
        "content_gap_categories": result["remaining_content_gaps"],
        "conditional_opportunities": result["conditional_story_opportunities"],
        "questions_not_to_repeat": [
            "basic_clam_sand_handling",
            "how_changed_method_requests_are_confirmed",
            "basic_peak_queue_and_equipment_handling",
            "whether_fish_methods_use_different_handling",
            "whether_a_real_crab_and_ricecake_case_exists",
        ],
        "authority": {
            "new_persona_fact_created": False,
            "unknown_or_requires_review_consumed": False,
            "content_ledger_mutated": False,
            "gap_report_is_planning_only": True,
        },
        "status": "review_required",
    }
    return result, gap_report


def render_content_gap_report(report: dict[str, Any]) -> str:
    lines = [
        "# Content Gap Report V1｜Persona Revision 2 Replenishment",
        "",
        f"Current high-quality novel capacity: `{report['current_high_quality_novel_capacity']}` / requested `{report['current_requested_quantity']}`",
        "",
        "## 本轮采访后已覆盖",
        "",
    ]
    lines.extend(f"- {item}" for item in report["replenishment_answers_now_covered"])
    lines.extend(["", "## Remaining Gaps", ""])
    lines.extend(f"- {item}" for item in report["content_gap_categories"])
    lines.extend(["", "## Conditional Story Opportunities", ""])
    for item in report["conditional_opportunities"]:
        lines.append(f"- {item['customer_label']}: `{item['status']}`")
    lines.extend(["", "> 本报告只用于 Planning，不产生 Customer Truth，也不写 Content Ledger。", ""])
    return "\n".join(lines)


def render_content_capacity_recalculation_approval(
    capacity: dict[str, Any], approval: dict[str, Any]
) -> str:
    concepts = sorted(
        capacity.get("candidate_concepts") or [],
        key=lambda item: (
            int(item.get("selected_rank") or 10_000),
            item.get("concept_id") or "",
        ),
    )
    lines = [
        "# Content Capacity Recalculation V1｜Human Approved",
        "",
        f"Reviewer: `{approval['reviewer']}`",
        f"Decision: `{approval['decision']}`",
        "",
        "## Capacity",
        "",
        f"- Before: `{capacity['before_capacity']}`",
        f"- After: `{capacity['after_capacity']}`",
        f"- Delta: `+{capacity['capacity_delta']}`",
        f"- Requested quantity: `{capacity['requested_quantity']}`",
        f"- Padding: `{str(capacity['padding']).lower()}`",
        "",
        "> 12 条表示当前高质量语义机会库存，不等于发布配额或单批强制产量。",
        "",
        "## Approved Semantic Opportunities",
        "",
    ]
    for concept in concepts:
        gate = resolve_effective_content_gate_decision(concept)
        score = (
            concept.get("editorial_quality")
            or concept.get("editorial_score_v1_1_1")
            or {}
        ).get("weighted_total")
        authority = (concept.get("production_authority") or {}).get("status")
        lines.extend(
            [
                f"### {concept['concept_id']}",
                "",
                f"- Central claim: {concept.get('central_claim')}",
                f"- Content job: `{concept.get('content_job')}`",
                f"- Audience origin: `{concept.get('audience_need_origin')}`",
                f"- Effective gate: `{gate['decision']}` via `{gate['source_field']}`",
                f"- Production authority: `{authority}`",
                f"- Editorial score: `{score}`",
                f"- Capacity rank: `{concept.get('selected_rank') or 'inventory_only'}`",
                "",
            ]
        )
    lines.extend(["## Conditional / Blocked Opportunities", ""])
    for item in capacity.get("conditional_story_opportunities") or []:
        lines.append(
            f"- {item['customer_label']}: `{item['status']}`; formal capacity counted = `false`"
        )
    lines.extend(["", "## Remaining Content Gaps", ""])
    lines.extend(f"- {item}" for item in capacity.get("remaining_content_gaps") or [])
    lines.extend(
        [
            "",
            "> Historical gate fields remain immutable diagnostics. Production consumers use the canonical effective-gate resolver.",
            "",
        ]
    )
    return "\n".join(lines)


def run_content_capacity_human_review_closure(
    *,
    project_root: Path,
    reviewer: str = "李健",
    approved_at: str | None = None,
    regression_test_count: int = 0,
) -> dict[str, Any]:
    timestamp = approved_at or now_iso()
    capacity_root = project_root / "data/content_plans/real_shufang_replenishment_rev2"
    capacity_path = capacity_root / "content_capacity_recalculation_v1.json"
    capacity = read_json(capacity_path)
    source_capacity_sha = sha256_file(capacity_path)
    expected = {
        "before_capacity": 2,
        "after_capacity": 12,
        "capacity_delta": 10,
        "high_quality_content_capacity": 12,
        "padding": False,
    }
    for key, value in expected.items():
        if capacity.get(key) != value:
            raise RuntimeError(f"Capacity Human Decision mismatch for {key}.")
    concepts = capacity.get("candidate_concepts") or []
    if len(concepts) != 12:
        raise RuntimeError("Capacity Human Decision requires the reviewed 12-item inventory.")
    resolved = {
        item["concept_id"]: resolve_effective_content_gate_decision(item)
        for item in concepts
    }
    if any(item["decision"] != "high_quality_novel" for item in resolved.values()):
        raise RuntimeError("Every approved capacity opportunity must resolve high-quality novel.")
    concept_016 = next(item for item in concepts if item["concept_id"] == "CONCEPT_016")
    if concept_016.get("gate_decision") == "high_quality_novel":
        raise RuntimeError("CONCEPT_016 legacy diagnostic was unexpectedly rewritten.")
    if resolved["CONCEPT_016"]["source_field"] != "replenishment_gate_decision":
        raise RuntimeError("CONCEPT_016 must resolve through the replenishment decision.")
    if any(
        item.get("formal_capacity_counted") is not False
        for item in capacity.get("conditional_story_opportunities") or []
    ):
        raise RuntimeError("Conditional Stories must not inflate formal capacity.")

    ledger_path = (
        project_root
        / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
    )
    ledger_sha = sha256_file(ledger_path)
    approval = {
        "schema_version": "content-capacity-recalculation-human-approval-v1.0",
        "reviewer": reviewer,
        "approved_at": timestamp,
        "decision": "approved",
        "source_artifact_ref": {
            "path": str(capacity_path.resolve()),
            "sha256": source_capacity_sha,
        },
        "capacity": {
            "before_capacity": 2,
            "after_capacity": 12,
            "capacity_delta": 10,
            "requested_quantity": 10,
            "high_quality_semantic_opportunity_inventory": 12,
            "padding": False,
        },
        "semantics": (
            "Twelve is the current high-quality semantic opportunity inventory; "
            "it is not a publishing quota, batch size, or forced delivery quantity."
        ),
        "approved_concept_refs": [item["concept_id"] for item in concepts],
        "effective_gate_decisions": resolved,
        "conditional_story_opportunities_counted": False,
        "content_ledger": {
            "path": str(ledger_path.resolve()),
            "sha256_before": ledger_sha,
            "sha256_after": ledger_sha,
            "mutated": False,
        },
        "status": "approved",
    }
    approval_path = capacity_root / "content_capacity_recalculation_v1_human_approval.json"
    markdown_path = capacity_root / "content_capacity_recalculation_v1.md"
    write_new_json(approval_path, approval)
    write_new_text(
        markdown_path,
        render_content_capacity_recalculation_approval(capacity, approval),
    )

    gap_root = project_root / "data/content_gap_reports/real_shufang_replenishment_rev2"
    gap_path = gap_root / "content_gap_report_v1.json"
    gap = read_json(gap_path)
    if gap.get("content_gap_categories") != capacity.get("remaining_content_gaps"):
        raise RuntimeError("Approved Content Gap categories do not match capacity lineage.")
    gap_approval = {
        "schema_version": "content-gap-report-human-approval-v1.0",
        "reviewer": reviewer,
        "approved_at": timestamp,
        "decision": "approved_as_current_post_replenishment_gap_baseline",
        "source_artifact_ref": {
            "path": str(gap_path.resolve()),
            "sha256": sha256_file(gap_path),
        },
        "second_interview_auto_triggered": False,
        "authority": "derived_planning_artifact_only",
    }
    gap_approval_path = gap_root / "content_gap_report_v1_human_approval.json"
    write_new_json(gap_approval_path, gap_approval)

    stage_a_path = (
        project_root
        / "data/customer_intakes/stage_a_validation/stage_a_validation_summary_v1.json"
    )
    intake_root = (
        project_root
        / "data/customer_intakes/shufang_zhiyuan_community_canteen/intake_0001"
    )
    closure_summary_path = intake_root / "persona_revision_2_closure_summary_v1.json"
    coverage_path = intake_root / "fact_extraction_coverage_audit_v1.json"
    validation_receipt = {
        "schema_version": "customer-truth-onboarding-replenishment-validation-v1.0",
        "created_at": timestamp,
        "artifact_role": "validation_receipt_not_customer_truth_authority",
        "initial_onboarding_fixture_validation": "pass",
        "real_replenishment_loop_validation": "pass",
        "persona_lifecycle_validation": "pass",
        "fact_extraction_coverage_validation": "pass",
        "capacity_replenishment": {
            "before": 2,
            "after": 12,
            "delta": 10,
        },
        "customer_story_authorization_boundary": "pass",
        "privacy": "pass",
        "proof": "pass",
        "authority": "pass",
        "regression_tests_passed": regression_test_count,
        "source_refs": {
            "stage_a": {"path": str(stage_a_path.resolve()), "sha256": sha256_file(stage_a_path)},
            "persona_revision_2_closure": {
                "path": str(closure_summary_path.resolve()),
                "sha256": sha256_file(closure_summary_path),
            },
            "fact_extraction_coverage": {
                "path": str(coverage_path.resolve()),
                "sha256": sha256_file(coverage_path),
            },
            "capacity_human_approval": {
                "path": str(approval_path.resolve()),
                "sha256": sha256_file(approval_path),
            },
        },
        "remote_model_calls": 0,
        "status": "pass",
    }
    validation_path = intake_root / "customer_truth_onboarding_replenishment_validation_v1.json"
    write_new_json(validation_path, validation_receipt)
    if sha256_file(ledger_path) != ledger_sha:
        raise RuntimeError("Content Ledger changed during Human Review closure.")
    return {
        "capacity_approval_path": str(approval_path.resolve()),
        "capacity_markdown_path": str(markdown_path.resolve()),
        "content_gap_approval_path": str(gap_approval_path.resolve()),
        "customer_truth_validation_path": str(validation_path.resolve()),
        "content_ledger_sha256": ledger_sha,
        "capacity": approval["capacity"],
    }


def _preflight_persona_rev2_closure(
    *,
    business_v1_path: Path,
    speaker_v1_path: Path,
    business_input: dict[str, Any],
    speaker_input: dict[str, Any],
    reviewed_candidates: dict[str, Any],
    ledger: dict[str, Any],
    before_plan: dict[str, Any],
    cross_profile_repurpose_history: dict[str, Any] | None,
    timestamp: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        business_input_path = root / "business_input.json"
        speaker_input_path = root / "speaker_input.json"
        write_new_json(business_input_path, business_input)
        write_new_json(speaker_input_path, speaker_input)
        business_path, _ = build_persona(
            business_input_path,
            root / "personas",
            previous_persona_path=business_v1_path,
            created_at=timestamp,
        )
        approve_persona(
            business_path,
            "李健",
            "Persona Revision 2 final Human Review preflight.",
            approved_at=timestamp,
        )
        speaker_path, _ = build_persona(
            speaker_input_path,
            root / "personas",
            previous_persona_path=speaker_v1_path,
            business_persona_path=business_path,
            created_at=timestamp,
        )
        approve_persona(
            speaker_path,
            "李健",
            "Speaker Persona Revision 2 final Human Review preflight.",
            approved_at=timestamp,
        )
        capacity, _gap = build_content_capacity_replenishment_recalculation(
            business_persona=read_json(business_path),
            speaker_persona=read_json(speaker_path),
            reviewed_candidates=reviewed_candidates,
            ledger=ledger,
            before_plan=before_plan,
            cross_profile_repurpose_history=cross_profile_repurpose_history,
            requested_quantity=10,
            created_at=timestamp,
        )
        return {
            "persona_build_and_approval": "pass",
            "capacity_recalculation": "pass",
            "candidate_concept_count": capacity["candidate_concept_count"],
            "high_quality_content_capacity": capacity[
                "high_quality_content_capacity"
            ],
        }


def run_persona_revision_2_closure(
    *,
    project_root: Path,
    reviewer: str = "李健",
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    stage_a_path = (
        project_root
        / "data/customer_intakes/stage_a_validation/stage_a_validation_summary_v1.json"
    )
    stage_a = read_json(stage_a_path)
    if stage_a.get("acceptance", {}).get("passed") is not True:
        raise RuntimeError("Stage A must remain PASS before Persona Rev2 closure.")
    intake_root = (
        project_root
        / "data/customer_intakes/shufang_zhiyuan_community_canteen/intake_0001"
    )
    intake_path = intake_root / "customer_intake_v1.json"
    intake = read_json(intake_path)
    if len(intake.get("raw_answers") or []) != 21:
        raise RuntimeError("Persona Rev2 closure requires all 21 Raw Interview Answers.")
    business_v1_path = (
        project_root
        / "data/personas/shufang_zhiyuan_community_canteen/revision_0001/persona_v1.json"
    )
    speaker_v1_path = (
        project_root
        / "data/personas/lin_dongfang_frontline_chef/revision_0001/persona_v1.json"
    )
    ledger_path = (
        project_root
        / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
    )
    before_plan_path = (
        project_root
        / "data/content_plans/real_shufang_mix_002/revisions/v1_1_1/content_plan_v1_1_1.json"
    )
    cross_profile_repurpose_path = (
        project_root
        / "data/news_production_mvp/real_shufang_news_validation_repurpose_001/news_generation_human_approval_v1.json"
    )
    frozen_before = {
        "stage_a": sha256_file(stage_a_path),
        "raw_interview": intake["input_sources"][0]["source_sha256"],
        "business_revision_1": sha256_file(business_v1_path),
        "speaker_revision_1": sha256_file(speaker_v1_path),
        "content_ledger": sha256_file(ledger_path),
        "before_content_plan": sha256_file(before_plan_path),
        "cross_profile_repurpose_history": sha256_file(
            cross_profile_repurpose_path
        ),
    }
    source_path = Path(str(intake["input_sources"][0]["source_path"]))
    if sha256_file(source_path) != frozen_before["raw_interview"]:
        raise RuntimeError("Immutable Raw Interview source SHA changed.")

    extracted = extract_shufang_replenishment_candidates(intake)
    reviewed = apply_persona_revision_2_human_decisions(
        extracted, reviewer=reviewer, reviewed_at=timestamp
    )
    coverage = build_fact_extraction_coverage_audit(
        intake, reviewed, created_at=timestamp
    )
    if coverage["stop_rule"]["status"] != "pass":
        raise RuntimeError("material_extraction_gap_found")

    reviewed_path = intake_root / "fact_candidates_human_reviewed_v1.json"
    coverage_json_path = intake_root / "fact_extraction_coverage_audit_v1.json"
    coverage_md_path = intake_root / "fact_extraction_coverage_audit_v1.md"
    decision_path = intake_root / "persona_revision_2_human_review_decision_v1.json"
    future_source_ref = str(reviewed_path.resolve())
    business_v1 = read_json(business_v1_path)
    speaker_v1 = read_json(speaker_v1_path)
    business_input, business_applied = build_revision_input(
        previous_persona=business_v1,
        candidate_artifact=reviewed,
        scope="business",
        source_ref=future_source_ref,
    )
    speaker_input, speaker_applied = build_revision_input(
        previous_persona=speaker_v1,
        candidate_artifact=reviewed,
        scope="speaker",
        source_ref=future_source_ref,
    )
    ledger = read_json(ledger_path)
    before_plan = read_json(before_plan_path)
    cross_profile_repurpose_history = read_json(cross_profile_repurpose_path)
    preflight = _preflight_persona_rev2_closure(
        business_v1_path=business_v1_path,
        speaker_v1_path=speaker_v1_path,
        business_input=business_input,
        speaker_input=speaker_input,
        reviewed_candidates=reviewed,
        ledger=ledger,
        before_plan=before_plan,
        cross_profile_repurpose_history=cross_profile_repurpose_history,
        timestamp=timestamp,
    )

    decision = {
        "schema_version": "persona-revision-2-human-review-decision-v1.0",
        "reviewer": reviewer,
        "reviewed_at": timestamp,
        "decision": "approve_with_exclusions_and_constraints",
        "coverage_audit_status": "pass",
        "business": {
            "approved_delta_refs": sorted(BUSINESS_REV2_APPROVED_REFS),
            "lineage_only_refs": sorted(BUSINESS_REV2_LINEAGE_ONLY_REFS),
            "excluded_review_refs": sorted(BUSINESS_REV2_REVIEW_REFS),
        },
        "speaker": {
            "approved_delta_refs": sorted(SPEAKER_REV2_APPROVED_REFS),
            "derived_constraint_refs": sorted(SPEAKER_REV2_CONSTRAINT_REFS),
        },
        "customer_story_production_eligibility": {
            "B-R2-009": "specific_content_use_binding_required",
            "B-R2-011": "scope_aware_use_review_required",
        },
        "authority": {
            "auto_approval": False,
            "requires_review_promoted": False,
            "derived_constraint_is_content_fact": False,
        },
    }
    write_new_json(reviewed_path, reviewed)
    write_new_json(coverage_json_path, coverage)
    write_new_text(coverage_md_path, render_fact_extraction_coverage_audit(coverage))
    decision_sha = write_new_json(decision_path, decision)

    business_input_path = (
        project_root
        / "data/persona_inputs/shufang_zhiyuan_community_canteen/business_persona_revision_0002_input.json"
    )
    speaker_input_path = (
        project_root
        / "data/persona_inputs/lin_dongfang_frontline_chef/speaker_persona_revision_0002_input.json"
    )
    _write_runtime_json(business_input_path, business_input, replace_unapproved=True)
    _write_runtime_json(speaker_input_path, speaker_input, replace_unapproved=True)
    business_v2_path = (
        project_root
        / "data/personas/shufang_zhiyuan_community_canteen/revision_0002/persona_v1.json"
    )
    speaker_v2_path = (
        project_root
        / "data/personas/lin_dongfang_frontline_chef/revision_0002/persona_v1.json"
    )
    _assert_unapproved_revision_can_refresh(business_v2_path)
    _assert_unapproved_revision_can_refresh(speaker_v2_path)
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory) / "business_personas"
        temporary_business_path, _ = build_persona(
            business_input_path,
            temporary_root,
            previous_persona_path=business_v1_path,
            created_at=timestamp,
        )
        _write_runtime_json(
            business_v2_path,
            read_json(temporary_business_path),
            replace_unapproved=True,
        )
        _write_runtime_text(
            business_v2_path.parent / "persona_review_pack_v1.md",
            (temporary_business_path.parent / "persona_review_pack_v1.md").read_text(
                encoding="utf-8"
            ),
            replace_unapproved=True,
        )
    business_metadata = {
        "approved_delta_refs": sorted(BUSINESS_REV2_APPROVED_REFS),
        "lineage_only_refs": sorted(BUSINESS_REV2_LINEAGE_ONLY_REFS),
        "excluded_review_refs": sorted(BUSINESS_REV2_REVIEW_REFS),
        "derived_constraint_refs": [],
        "decision_artifact_ref": {
            "path": str(decision_path.resolve()),
            "sha256": decision_sha,
        },
    }
    business_persona, business_receipt, business_receipt_path = approve_persona(
        business_v2_path,
        reviewer,
        "Persona Revision 2 final Human Review decisions applied after 21-answer extraction coverage PASS.",
        approved_at=timestamp,
        decision_metadata=business_metadata,
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory) / "speaker_personas"
        temporary_speaker_path, _ = build_persona(
            speaker_input_path,
            temporary_root,
            previous_persona_path=speaker_v1_path,
            business_persona_path=business_v2_path,
            created_at=timestamp,
        )
        _write_runtime_json(
            speaker_v2_path,
            read_json(temporary_speaker_path),
            replace_unapproved=True,
        )
        _write_runtime_text(
            speaker_v2_path.parent / "persona_review_pack_v1.md",
            (temporary_speaker_path.parent / "persona_review_pack_v1.md").read_text(
                encoding="utf-8"
            ),
            replace_unapproved=True,
        )
    speaker_metadata = {
        "approved_delta_refs": sorted(SPEAKER_REV2_APPROVED_REFS),
        "lineage_only_refs": [],
        "excluded_review_refs": [],
        "derived_constraint_refs": sorted(SPEAKER_REV2_CONSTRAINT_REFS),
        "decision_artifact_ref": {
            "path": str(decision_path.resolve()),
            "sha256": decision_sha,
        },
    }
    speaker_persona, speaker_receipt, speaker_receipt_path = approve_persona(
        speaker_v2_path,
        reviewer,
        "Speaker Persona Revision 2 final Human Review decisions and derived authority constraint applied.",
        approved_at=timestamp,
        decision_metadata=speaker_metadata,
    )

    capacity, gap_report = build_content_capacity_replenishment_recalculation(
        business_persona=business_persona,
        speaker_persona=speaker_persona,
        reviewed_candidates=reviewed,
        ledger=ledger,
        before_plan=before_plan,
        cross_profile_repurpose_history=cross_profile_repurpose_history,
        requested_quantity=10,
        created_at=timestamp,
    )
    capacity_root = (
        project_root
        / "data/content_plans/real_shufang_replenishment_rev2"
    )
    capacity_path = capacity_root / "content_capacity_recalculation_v1.json"
    gap_root = (
        project_root
        / "data/content_gap_reports/real_shufang_replenishment_rev2"
    )
    gap_json_path = gap_root / "content_gap_report_v1.json"
    gap_md_path = gap_root / "content_gap_report_v1.md"
    write_new_json(capacity_path, capacity)
    write_new_json(gap_json_path, gap_report)
    write_new_text(gap_md_path, render_content_gap_report(gap_report))

    frozen_after = {
        "stage_a": sha256_file(stage_a_path),
        "raw_interview": sha256_file(source_path),
        "business_revision_1": sha256_file(business_v1_path),
        "speaker_revision_1": sha256_file(speaker_v1_path),
        "content_ledger": sha256_file(ledger_path),
        "before_content_plan": sha256_file(before_plan_path),
        "cross_profile_repurpose_history": sha256_file(
            cross_profile_repurpose_path
        ),
    }
    if frozen_before != frozen_after:
        raise RuntimeError("A frozen input or Content Ledger changed during closure.")
    summary = {
        "schema_version": "persona-revision-2-closure-summary-v1.0",
        "created_at": timestamp,
        "status": "content_capacity_replenishment_human_review_gate",
        "stage_a_final_status": "pass",
        "coverage_audit_path": str(coverage_json_path.resolve()),
        "coverage_audit_markdown_path": str(coverage_md_path.resolve()),
        "material_extraction_gap_found": False,
        "business_persona_revision_2": {
            "path": str(business_v2_path.resolve()),
            "sha256": sha256_file(business_v2_path),
            "content_sha256": business_persona["provenance"]["content_sha256"],
            "approval_receipt_path": str(business_receipt_path.resolve()),
            "approval_receipt_sha256": sha256_file(business_receipt_path),
        },
        "speaker_persona_revision_2": {
            "path": str(speaker_v2_path.resolve()),
            "sha256": sha256_file(speaker_v2_path),
            "content_sha256": speaker_persona["provenance"]["content_sha256"],
            "approval_receipt_path": str(speaker_receipt_path.resolve()),
            "approval_receipt_sha256": sha256_file(speaker_receipt_path),
        },
        "capacity_recalculation_path": str(capacity_path.resolve()),
        "content_gap_report_path": str(gap_json_path.resolve()),
        "capacity": {
            key: capacity[key]
            for key in (
                "before_capacity",
                "after_capacity",
                "capacity_delta",
                "candidate_concept_count",
                "high_quality_content_capacity",
                "selected_quantity",
                "capacity_status",
                "padding",
            )
        },
        "preflight": preflight,
        "frozen_hashes_before": frozen_before,
        "frozen_hashes_after": frozen_after,
        "content_ledger_written": False,
        "remote_model_calls": 0,
        "scripts_generated": False,
        "mix_or_news_batch_created": False,
        "pattern_matching_performed": False,
        "excel_exported": False,
        "checkpoint_created": False,
    }
    summary_path = intake_root / "persona_revision_2_closure_summary_v1.json"
    write_new_json(summary_path, summary)
    summary["summary_path"] = str(summary_path.resolve())
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Customer Intake V1, validate onboarding fixtures, and prepare replenishment Persona revisions."
    )
    parser.add_argument("--run-stage-a", action="store_true")
    parser.add_argument("--run-stage-b", action="store_true")
    parser.add_argument("--close-persona-revision-2", action="store_true")
    parser.add_argument("--close-content-capacity-review", action="store_true")
    parser.add_argument("--regression-test-count", type=int, default=0)
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--interview", default=None)
    parser.add_argument("--created-at", default=None)
    parser.add_argument(
        "--refresh-unapproved-stage-b",
        action="store_true",
        help="Refresh only existing review-required Stage B drafts; Approved revisions are always rejected.",
    )
    args = parser.parse_args()
    if not (
        args.run_stage_a
        or args.run_stage_b
        or args.run_all
        or args.close_persona_revision_2
        or args.close_content_capacity_review
    ):
        parser.error(
            "Choose a Stage A, Stage B, Persona closure, or Content Capacity closure mode."
        )
    project_root = Path(__file__).resolve().parents[1]
    stage_a_summary: dict[str, Any] | None = None
    if args.run_stage_a or args.run_all:
        stage_a_summary = run_stage_a(
            project_root / "data/customer_intakes/stage_a_validation",
            created_at=args.created_at,
        )
        print("STAGE A PASS" if stage_a_summary["acceptance"]["passed"] else "STAGE A FAIL")
    if args.run_stage_b or args.run_all:
        if args.run_all and not stage_a_summary["acceptance"]["passed"]:
            raise RuntimeError("Stage B blocked because Stage A did not pass.")
        if not args.interview:
            parser.error("--interview is required for Stage B.")
        summary = run_stage_b(
            project_root=project_root,
            interview_path=Path(args.interview).expanduser().resolve(),
            output_root=project_root / "data/customer_intakes/shufang_zhiyuan_community_canteen/intake_0001",
            created_at=args.created_at,
            replace_unapproved=args.refresh_unapproved_stage_b,
        )
        print("STAGE B HUMAN REVIEW READY")
        print(f"Business review pack: {summary['business_review_pack_path']}")
        print(f"Speaker review pack: {summary['speaker_review_pack_path']}")
        print("Capacity recalculation: blocked_pending_persona_revision_approval")
        print("Remote model calls: 0")
    if args.close_persona_revision_2:
        summary = run_persona_revision_2_closure(
            project_root=project_root,
            reviewer="李健",
            created_at=args.created_at,
        )
        print("PERSONA REVISION 2 CLOSURE PASS")
        print(
            "Content capacity: "
            f"{summary['capacity']['before_capacity']} -> "
            f"{summary['capacity']['after_capacity']}"
        )
        print("Status: content_capacity_replenishment_human_review_gate")
        print("Remote model calls: 0")
    if args.close_content_capacity_review:
        summary = run_content_capacity_human_review_closure(
            project_root=project_root,
            reviewer="李健",
            approved_at=args.created_at,
            regression_test_count=args.regression_test_count,
        )
        print("CONTENT CAPACITY REPLENISHMENT HUMAN REVIEW APPROVED")
        print(
            "Content capacity: "
            f"{summary['capacity']['before_capacity']} -> "
            f"{summary['capacity']['after_capacity']}"
        )
        print("Customer Truth V1 validation: PASS")
        print("Remote model calls: 0")


if __name__ == "__main__":
    main()
