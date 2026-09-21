from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from customer_intake_v1 import (
    INITIAL_TOPIC_MAP,
    assess_persona_onboarding_readiness,
    build_customer_intake,
    build_fact_candidate_artifact,
    extract_initial_fact_candidates,
)
from customer_onboarding_analysis_v1 import (
    get_client,
    load_deepseek_runtime_config,
)
from privacy_projection_v1 import (
    PRIVACY_POLICY_VERSION,
    assert_safe_for_external_model,
    build_egress_audit,
    detect_sensitive_spans,
    project_safe_semantic,
    sha256_json,
)

SCHEMA_VERSION = "speaker-onboarding-analysis-v1.0"
OPERATION_VERSION = "speaker_onboarding_analysis_v1.py@1.0"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,127}$")

SPEAKER_TYPES = {
    "owner_founder",
    "frontline_expert",
    "brand",
    "generic",
}

AI_SPEAKER_TOPICS = {
    "speaker_practice",
    "speaker_allowed_topics",
    "speaker_scope",
}


class SpeakerOnboardingError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ):
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha256(
    value: Any,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(
    path: Path,
) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(
        value,
        dict,
    ):
        raise SpeakerOnboardingError(
            "INVALID_JSON",
            f"Expected JSON object: {path}",
        )

    return value


def write_atomic_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)

    os.replace(
        temporary,
        path,
    )


def write_new_or_same(
    path: Path,
    value: dict[str, Any],
) -> None:
    if path.exists():
        existing = read_json(path)

        if canonical_sha256(existing) != canonical_sha256(value):
            raise SpeakerOnboardingError(
                "SPEAKER_ARTIFACT_CONFLICT",
                ("Existing Speaker artifact " f"differs: {path}"),
            )

        return

    write_atomic_json(
        path,
        value,
    )


def split_forbidden_claims(
    value: Any,
) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value or "").strip()

        result = [
            item.strip()
            for item in re.split(
                r"[\r\n]+",
                text,
            )
            if item.strip()
        ]

    return result


def machine_speaker_id(
    business_id: str,
    speaker_name: str,
    public_role: str,
) -> str:
    raw = (
        f"{business_id}|"
        f"{speaker_name.strip().casefold()}|"
        f"{public_role.strip().casefold()}"
    )

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:14]

    return f"speaker_{digest}"


def validate_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    business_id = str(request.get("business_id") or "").strip()

    speaker_name = str(request.get("speaker_name") or "").strip()

    public_role = str(request.get("public_role") or "").strip()

    speaker_type = str(request.get("speaker_type") or "").strip()

    materials = str(request.get("materials") or "").strip()

    forbidden_claims = split_forbidden_claims(request.get("forbidden_claims"))
    source_type = str(
        request.get("source_type") or "internal_console_speaker_materials"
    ).strip()
    source_lineage = request.get("source_lineage") or {}
    human_confirmed_identity = request.get("human_confirmed_identity") or {}

    if not ID_RE.fullmatch(business_id):
        raise SpeakerOnboardingError(
            "INVALID_BUSINESS_ID",
            "business_id must be machine-safe.",
        )

    if not speaker_name:
        raise SpeakerOnboardingError(
            "SPEAKER_NAME_REQUIRED",
            "Speaker name is required.",
        )

    if not public_role:
        raise SpeakerOnboardingError(
            "SPEAKER_ROLE_REQUIRED",
            "Speaker public role is required.",
        )

    if speaker_type not in SPEAKER_TYPES:
        raise SpeakerOnboardingError(
            "INVALID_SPEAKER_TYPE",
            (
                "speaker_type must be "
                "owner_founder, frontline_expert, "
                "brand or generic."
            ),
        )

    if not materials:
        raise SpeakerOnboardingError(
            "SPEAKER_MATERIALS_REQUIRED",
            ("Existing Speaker materials " "are required."),
        )

    if len(materials) > 50000:
        raise SpeakerOnboardingError(
            "SPEAKER_MATERIALS_TOO_LONG",
            ("Speaker materials exceed " "the V1 input limit."),
        )

    if source_type not in {
        "internal_console_speaker_materials",
        "customer_intake_speaker_discovery",
    }:
        raise SpeakerOnboardingError(
            "SPEAKER_SOURCE_TYPE_INVALID",
            "Speaker source type is invalid.",
        )

    if not isinstance(source_lineage, dict) or not isinstance(
        human_confirmed_identity, dict
    ):
        raise SpeakerOnboardingError(
            "SPEAKER_SOURCE_LINEAGE_INVALID",
            "Speaker source lineage is invalid.",
        )

    speaker_id = str(
        request.get("speaker_id")
        or machine_speaker_id(
            business_id,
            speaker_name,
            public_role,
        )
    ).strip()

    intake_id = str(request.get("intake_id") or "intake_0001").strip()

    if not ID_RE.fullmatch(speaker_id):
        raise SpeakerOnboardingError(
            "INVALID_SPEAKER_ID",
            "speaker_id must be machine-safe.",
        )

    if not ID_RE.fullmatch(intake_id):
        raise SpeakerOnboardingError(
            "INVALID_INTAKE_ID",
            "intake_id must be machine-safe.",
        )

    return {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "intake_id": intake_id,
        "speaker_name": speaker_name,
        "public_role": public_role,
        "speaker_type": speaker_type,
        "materials": materials,
        "forbidden_claims": (forbidden_claims),
        "source_type": source_type,
        "source_lineage": source_lineage,
        "human_confirmed_identity": human_confirmed_identity,
    }


def load_approved_business_persona(
    pipeline_root: Path,
    business_id: str,
) -> tuple[
    Path,
    dict[str, Any],
]:
    root = pipeline_root / "data" / "personas" / business_id

    candidates = sorted(
        root.glob("revision_*/persona_v1.json"),
        reverse=True,
    )

    for path in candidates:
        persona = read_json(path)

        lifecycle = persona.get("lifecycle") or {}

        if (
            persona.get(
                "persona_scope",
                "business",
            )
            == "business"
            and lifecycle.get("status") == "approved"
            and lifecycle.get("approved") is True
        ):
            return (
                path,
                persona,
            )

    raise SpeakerOnboardingError(
        "APPROVED_BUSINESS_PERSONA_REQUIRED",
        ("Speaker onboarding requires " "an Approved Business Persona."),
    )


def build_raw_answers(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    base = (
        f"{request['business_id']}:"
        f"{request['speaker_id']}:"
        f"{request['intake_id']}"
    )

    discovered = request["source_type"] == "customer_intake_speaker_discovery"
    identity_source_type = (
        "human_confirmed_customer_intake_speaker_identity"
        if discovered
        else "operator_entered_speaker_identity"
    )
    identity_basis = (
        "human_confirmed_discovery_identity"
        if discovered
        else "operator_explicit_input"
    )
    answers = [
        {
            "answer_id": (f"{request['intake_id']}" "_speaker_name"),
            "topic": "speaker_name",
            "answer_text": (request["speaker_name"]),
            "normalized_value": (request["speaker_name"]),
            "input_actor": "operator",
            "source_type": identity_source_type,
            "source_ref": (f"{base}:speaker_name"),
            "confirmation_basis": identity_basis,
        },
        {
            "answer_id": (f"{request['intake_id']}" "_speaker_role"),
            "topic": "speaker_role",
            "answer_text": (request["public_role"]),
            "normalized_value": (request["public_role"]),
            "input_actor": "operator",
            "source_type": identity_source_type,
            "source_ref": (f"{base}:speaker_role"),
            "confirmation_basis": identity_basis,
        },
        {
            "answer_id": (f"{request['intake_id']}" "_speaker_materials"),
            "topic": ("freeform_speaker_materials"),
            "answer_text": (request["materials"]),
            "input_actor": "operator",
            "source_type": request["source_type"],
            "source_ref": (f"{base}:materials"),
            "confirmation_basis": (
                "human_confirmed_customer_intake_evidence"
                if discovered
                else "raw_speaker_materials"
            ),
        },
    ]
    if request["forbidden_claims"]:
        answers.insert(
            2,
            {
                "answer_id": (f"{request['intake_id']}" "_speaker_forbidden"),
                "topic": ("speaker_forbidden_claims"),
                "answer_text": "\n".join(request["forbidden_claims"]),
                "normalized_value": list(request["forbidden_claims"]),
                "input_actor": "operator",
                "source_type": (
                    "customer_intake_explicit_speaker_boundary"
                    if discovered
                    else "operator_entered_speaker_authority_boundary"
                ),
                "source_ref": (f"{base}:" "speaker_forbidden_claims"),
                "confirmation_basis": identity_basis,
            },
        )
    return answers


def build_privacy_projection(
    request: dict[str, Any],
    *,
    created_at: str,
) -> dict[str, Any]:
    raw_materials = request["materials"]

    safe_materials = project_safe_semantic(raw_materials)

    safe_name = project_safe_semantic(request["speaker_name"])

    safe_role = project_safe_semantic(request["public_role"])

    rendered_probe = (
        f"出镜人：{safe_name}\n" f"身份：{safe_role}\n" f"资料：{safe_materials}"
    )

    assert_safe_for_external_model(rendered_probe)

    return {
        "schema_version": ("speaker-intake-" "privacy-projection-v1.0"),
        "privacy_policy_version": (PRIVACY_POLICY_VERSION),
        "business_id": (request["business_id"]),
        "speaker_id": (request["speaker_id"]),
        "intake_id": (request["intake_id"]),
        "created_at": created_at,
        "source": {
            "raw_materials_sha256": (sha256_text(raw_materials)),
        },
        "projection": {
            "speaker_name_safe_semantic": (safe_name),
            "public_role_safe_semantic": (safe_role),
            "materials_safe_semantic": (safe_materials),
        },
        "annotations": (detect_sensitive_spans(raw_materials)),
        "validation": {
            "passed": True,
            "raw_source_modified": False,
            "external_model_gate_passed": (True),
        },
    }


def build_prompt(
    privacy_projection: dict[
        str,
        Any,
    ],
) -> str:
    projection = privacy_projection["projection"]

    return f"""
你是 Speaker Persona Fact Extraction Engine。

你的唯一任务：
从已经提供的出镜人资料中，提取能够由这个人本人承担的第一人称事实候选。

严格规则：

1. 只能使用下面资料明确支持的信息。
2. 不得把 Business Persona 的经营事实自动变成这个人的第一人称经历。
3. 不得把创始人经历赋给普通员工。
4. 不得把团队能力自动变成本人的能力。
5. 不得创造学历、资质、专业身份、结果数据或个人经历。
6. 没有明确支持的内容直接省略。
7. 这里只生成 Speaker Fact Candidate，不代表 Speaker Truth。
8. 所有 AI 候选都必须等待 Human Review。
9. 不生成 first_person_forbidden_claims；该边界由运营人员显式输入。
10. evidence_quote 必须来自下面提供的隐私安全资料。

只允许以下 topic：

- speaker_practice
  本人明确承担的职责、亲自做过的事情、真实经验。

- speaker_allowed_topics
  基于资料中本人职责或本人经验，可以由本人用第一人称讲述的主题。

- speaker_scope
  资料明确体现的角色范围、职责边界或第一人称表达范围。

输出严格 JSON：

{{
  "facts": [
    {{
      "topic": "speaker_practice",
      "value": ["明确事实1"],
      "evidence_quote": "原文支持片段"
    }}
  ]
}}

没有可提取信息时：

{{
  "facts": []
}}

出镜人：
{projection["speaker_name_safe_semantic"]}

公开身份：
{projection["public_role_safe_semantic"]}

已有资料：
{projection["materials_safe_semantic"]}
""".strip()


def extract_remote_facts(
    safe_payload: dict[
        str,
        Any,
    ],
) -> dict[str, Any]:
    prompt = build_prompt(safe_payload)

    assert_safe_for_external_model(prompt)

    try:
        (
            api_key,
            model,
        ) = load_deepseek_runtime_config()

        client = get_client(api_key)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=4000,
            extra_body={
                "thinking": {
                    "type": "disabled",
                }
            },
        )
    except Exception as exc:
        raise SpeakerOnboardingError(
            "SPEAKER_FACT_EXTRACTION_REMOTE_FAILED",
            ("Speaker fact extraction failed: " f"{type(exc).__name__}"),
        ) from exc

    content = response.choices[0].message.content or ""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SpeakerOnboardingError(
            "SPEAKER_FACT_EXTRACTION_INVALID_JSON",
            ("Speaker fact extraction " "returned invalid JSON."),
        ) from exc

    facts = payload.get("facts")

    if not isinstance(
        facts,
        list,
    ):
        raise SpeakerOnboardingError(
            "SPEAKER_FACT_EXTRACTION_INVALID_RESULT",
            "facts must be a list.",
        )

    if len(facts) > 20:
        raise SpeakerOnboardingError(
            "SPEAKER_FACT_EXTRACTION_TOO_MANY_FACTS",
            ("Speaker extraction returned " "too many candidates."),
        )

    return {
        "facts": facts,
        "model": model,
        "usage": {
            "prompt_tokens": getattr(
                response.usage,
                "prompt_tokens",
                None,
            ),
            "completion_tokens": getattr(
                response.usage,
                "completion_tokens",
                None,
            ),
            "total_tokens": getattr(
                response.usage,
                "total_tokens",
                None,
            ),
        },
    }


def validate_model_fact(
    fact: dict[str, Any],
) -> (
    tuple[
        str,
        Any,
        str,
    ]
    | None
):
    if not isinstance(
        fact,
        dict,
    ):
        return None

    topic = str(fact.get("topic") or "").strip()

    if topic not in AI_SPEAKER_TOPICS:
        return None

    mapping = INITIAL_TOPIC_MAP.get(topic)

    if mapping is None:
        return None

    scope, field = mapping

    if scope != "speaker":
        return None

    value = fact.get("value")

    if value in (
        None,
        "",
        [],
    ):
        return None

    quote = str(fact.get("evidence_quote") or "").strip()

    return (
        field,
        value,
        quote,
    )


def build_ai_candidates(
    *,
    intake: dict[str, Any],
    deterministic: dict[
        str,
        Any,
    ],
    extracted: dict[
        str,
        Any,
    ],
    raw_materials: str,
    safe_materials: str,
) -> dict[str, Any]:
    candidates = list(deterministic.get("fact_candidates") or [])

    materials_answer = next(
        item
        for item in intake["raw_answers"]
        if item["topic"] == "freeform_speaker_materials"
    )

    existing_fields = {str(item.get("target_field") or "") for item in candidates}

    number = len(candidates) + 1

    for raw_fact in extracted.get("facts") or []:
        validated = validate_model_fact(raw_fact)

        if validated is None:
            continue

        (
            target_field,
            value,
            safe_quote,
        ) = validated

        if target_field in existing_fields:
            continue

        if safe_quote and safe_quote in safe_materials and safe_quote in raw_materials:
            source_excerpt = safe_quote
        else:
            source_excerpt = raw_materials

        candidates.append(
            {
                "fact_candidate_id": (f"SF-{intake['intake_id']}" f"-{number:03d}"),
                "persona_scope": ("speaker"),
                "target_field": (target_field),
                "normalized_value": (value),
                "source_ref": (materials_answer.get("source_ref")),
                "source_excerpt": (source_excerpt),
                "raw_answer_ref": (materials_answer["answer_id"]),
                "input_actor": (materials_answer["input_actor"]),
                "source_type": (materials_answer["source_type"]),
                "confirmation_basis": ("ai_extracted_from_" "privacy_safe_projection"),
                "candidate_state": ("requires_review"),
                "conflict_refs": [],
                "privacy_state": (
                    "canonical_local_source_" "with_safe_remote_projection"
                ),
                "speaker_authority_assessment": ("speaker_candidate_only"),
                "time_metadata": None,
                "delta_type": ("new_fact"),
                "classification": ("ai_extracted_" "speaker_onboarding"),
                "authorization": None,
                "review_note": (
                    "AI 从出镜人资料中提取；"
                    "必须由人工确认后才能成为 "
                    "Speaker Persona Fact。"
                ),
            }
        )

        existing_fields.add(target_field)

        number += 1

    return build_fact_candidate_artifact(
        intake,
        candidates,
        created_at=str(intake.get("created_at") or now_iso()),
    )


def analyze_speaker_onboarding(
    *,
    request: dict[str, Any],
    pipeline_root: Path,
    extractor: (
        Callable[
            [dict[str, Any]],
            dict[str, Any],
        ]
        | None
    ) = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    request = validate_request(request)

    (
        business_path,
        business_persona,
    ) = load_approved_business_persona(
        pipeline_root,
        request["business_id"],
    )

    root = (
        pipeline_root
        / "data"
        / "speaker_intakes"
        / request["business_id"]
        / request["speaker_id"]
        / request["intake_id"]
    )

    intake_path = root / "speaker_intake_v1.json"

    privacy_path = root / ("speaker_intake_" "privacy_projection_v1.json")

    candidates_path = root / ("speaker_fact_" "candidates_v1.json")

    readiness_path = root / ("speaker_onboarding_" "readiness_v1.json")

    audit_path = root / "egress_audit_v1.json"

    summary_path = root / ("speaker_onboarding_" "analysis_v1.json")

    raw_answers = build_raw_answers(request)

    if intake_path.is_file():
        intake = read_json(intake_path)

        expected_sha = canonical_sha256(raw_answers)

        actual_sha = intake.get(
            "raw_input_contract",
            {},
        ).get("raw_answers_sha256")

        if (
            expected_sha != actual_sha
            or intake.get(
                "business_ref",
                {},
            ).get("persona_id")
            != request["business_id"]
        ):
            raise SpeakerOnboardingError(
                "SPEAKER_INTAKE_CONFLICT",
                ("Existing Speaker Intake " "differs from this request."),
            )

        timestamp = str(intake.get("created_at") or "")

        if not timestamp:
            raise SpeakerOnboardingError(
                "SPEAKER_INTAKE_INVALID",
                ("Existing Speaker Intake " "has no created_at."),
            )

    else:
        timestamp = created_at or now_iso()

        intake = build_customer_intake(
            intake_id=(request["intake_id"]),
            intake_type=("initial_onboarding"),
            provisional_business_id=None,
            business_ref={
                "persona_id": (business_persona["persona_id"]),
                "revision": (business_persona["revision"]),
                "content_sha256": (
                    business_persona.get(
                        "provenance",
                        {},
                    ).get("content_sha256")
                ),
            },
            input_actor="operator",
            input_sources=[
                {
                    "source_type": request["source_type"],
                    "source_ref": (
                        request["source_lineage"].get("candidate_ref")
                        or request["speaker_id"]
                    ),
                }
            ],
            raw_answers=raw_answers,
            speaker_selection={
                "speaker_type": (request["speaker_type"]),
                "speaker_ref": {
                    "persona_id": (request["speaker_id"]),
                    "revision": 1,
                },
            },
            source_lineage=(request["source_lineage"] or None),
            created_at=timestamp,
        )

        write_new_or_same(
            intake_path,
            intake,
        )

    if summary_path.is_file():
        return read_json(summary_path)

    if privacy_path.is_file():
        privacy = read_json(privacy_path)

        if privacy.get(
            "source",
            {},
        ).get(
            "raw_materials_sha256"
        ) != sha256_text(request["materials"]):
            raise SpeakerOnboardingError(
                "SPEAKER_PRIVACY_PROJECTION_CONFLICT",
                ("Existing privacy projection " "does not match Speaker input."),
            )

    else:
        privacy = build_privacy_projection(
            request,
            created_at=timestamp,
        )

        write_new_or_same(
            privacy_path,
            privacy,
        )

    deterministic = extract_initial_fact_candidates(intake)

    candidates_preexisting = candidates_path.is_file()

    if candidates_preexisting:
        candidates = read_json(candidates_path)

    else:
        if extractor is None:
            extracted = extract_remote_facts(privacy)
        else:
            extracted = extractor(privacy)

        if not isinstance(
            extracted,
            dict,
        ):
            raise SpeakerOnboardingError(
                "SPEAKER_EXTRACTOR_INVALID",
                ("Speaker extractor must " "return an object."),
            )

        candidates = build_ai_candidates(
            intake=intake,
            deterministic=(deterministic),
            extracted=extracted,
            raw_materials=(request["materials"]),
            safe_materials=(privacy["projection"]["materials_safe_semantic"]),
        )

        write_new_or_same(
            candidates_path,
            candidates,
        )

    if readiness_path.is_file():
        readiness = read_json(readiness_path)

    else:
        readiness = assess_persona_onboarding_readiness(
            intake,
            candidates,
            business_persona=(business_persona),
            created_at=timestamp,
        )

        write_new_or_same(
            readiness_path,
            readiness,
        )

    if not audit_path.is_file():
        prompt = build_prompt(privacy)

        audit = {
            "schema_version": ("speaker-egress-audit-v1.0"),
            "business_id": (request["business_id"]),
            "speaker_id": (request["speaker_id"]),
            "intake_id": (request["intake_id"]),
            "created_at": timestamp,
            **build_egress_audit(
                safe_input=(privacy["projection"]),
                rendered_prompt=prompt,
                privacy_context={"privacy_projection_sha256": (sha256_json(privacy))},
            ),
            "recovered_from_existing_candidates": (candidates_preexisting),
        }

        write_new_or_same(
            audit_path,
            audit,
        )

    summary = {
        "schema_version": (SCHEMA_VERSION),
        "operation_version": (OPERATION_VERSION),
        "business_id": (request["business_id"]),
        "speaker_id": (request["speaker_id"]),
        "intake_id": (request["intake_id"]),
        "speaker_name": (request["speaker_name"]),
        "public_role": (request["public_role"]),
        "speaker_type": (request["speaker_type"]),
        "source_type": request["source_type"],
        "source_lineage": request["source_lineage"],
        "human_confirmed_identity": request["human_confirmed_identity"],
        "status": ("awaiting_speaker_fact_review"),
        "created_at": timestamp,
        "business_persona_ref": {
            "persona_id": (business_persona["persona_id"]),
            "revision": (business_persona["revision"]),
            "path": str(business_path.resolve()),
        },
        "artifacts": {
            "speaker_intake_v1": str(intake_path.resolve()),
            "privacy_projection_v1": (str(privacy_path.resolve())),
            "speaker_fact_candidates_v1": (str(candidates_path.resolve())),
            "readiness_v1": (str(readiness_path.resolve())),
            "egress_audit_v1": (str(audit_path.resolve())),
        },
        "candidate_summary": (candidates["summary"]),
        "readiness": {
            "status": (readiness.get("status")),
            "critical_missing_truth": (
                readiness.get(
                    "critical_missing_truth",
                    [],
                )
            ),
        },
        "authority": {
            "business_persona_approved": (True),
            "speaker_raw_input_is_persona": (False),
            "speaker_fact_candidates_are_persona_facts": (False),
            "speaker_persona_created": (False),
            "speaker_persona_approved": (False),
            "media_rights_established": (False),
            "business_facts_copied_into_speaker": (False),
            "universal_first_person_guardrail_active": True,
            "human_review_required": (True),
        },
        "next_action": ("REVIEW_SPEAKER_FACTS"),
    }

    write_new_or_same(
        summary_path,
        summary,
    )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze raw Speaker materials "
            "into Human-review-required "
            "Speaker Fact Candidates."
        )
    )

    parser.add_argument(
        "--request",
        required=True,
    )

    parser.add_argument(
        "--pipeline-root",
        default=None,
    )

    args = parser.parse_args()

    pipeline_root = (
        Path(args.pipeline_root).expanduser().resolve()
        if args.pipeline_root
        else Path(__file__).resolve().parents[1]
    )

    request = read_json(Path(args.request).expanduser().resolve())

    try:
        result = analyze_speaker_onboarding(
            request=request,
            pipeline_root=(pipeline_root),
        )

    except SpeakerOnboardingError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )

        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "ok": True,
                "business_id": (result["business_id"]),
                "speaker_id": (result["speaker_id"]),
                "intake_id": (result["intake_id"]),
                "status": (result["status"]),
                "next_action": (result["next_action"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
