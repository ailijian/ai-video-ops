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

from openai import OpenAI

from customer_intake_v1 import (
    INITIAL_TOPIC_MAP,
    assess_persona_onboarding_readiness,
    build_customer_intake,
    build_fact_candidate_artifact,
    extract_initial_fact_candidates,
)
from privacy_projection_v1 import (
    PRIVACY_POLICY_VERSION,
    assert_safe_for_external_model,
    build_egress_audit,
    detect_sensitive_spans,
    project_safe_semantic,
    sha256_json,
)

SCHEMA_VERSION = "customer-onboarding-analysis-v1.0"
OPERATION_VERSION = "customer_onboarding_analysis_v1.py@1.0"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,127}$")

AI_BUSINESS_TOPICS = {
    "primary_service",
    "core_audience",
    "customer_use_case",
    "customer_pain",
    "differentiator",
    "service_process",
    "service_time",
    "founder_story",
    "business_decision",
}


class CustomerOnboardingError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CustomerOnboardingError(
            "INVALID_JSON",
            f"Expected JSON object: {path}",
        )
    return value


def write_atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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

    os.replace(temporary, path)


def write_new_or_same(
    path: Path,
    value: dict[str, Any],
) -> None:
    """
    Recoverable but never silently changes an existing canonical attempt artifact.
    """

    if path.exists():
        existing = read_json(path)

        if sha256_json(existing) != sha256_json(value):
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                f"Existing onboarding artifact differs: {path}",
            )
        return

    write_atomic_json(path, value)


def validate_request(request: dict[str, Any]) -> dict[str, Any]:
    business_id = str(request.get("business_id") or "").strip()
    intake_id = str(request.get("intake_id") or "").strip()
    customer_name = str(request.get("customer_name") or "").strip()
    industry = str(request.get("industry") or "").strip()
    intake_type = str(request.get("intake_type") or "initial_onboarding").strip()
    gap_answers = request.get("gap_answers") or []
    reviewed_context = request.get("reviewed_context") or {}
    created_by = request.get("created_by") or {}
    source_lineage = request.get("source_lineage") or {}

    if intake_type == "gap_supplement":
        if not isinstance(gap_answers, list) or not gap_answers:
            raise CustomerOnboardingError(
                "GAP_ANSWERS_REQUIRED",
                "At least one gap supplement answer is required.",
            )
        normalized_gap_answers: list[dict[str, str]] = []
        for item in gap_answers:
            if not isinstance(item, dict):
                raise CustomerOnboardingError(
                    "GAP_ANSWER_INVALID",
                    "Every gap supplement answer must be an object.",
                )
            target_gap = str(item.get("target_gap") or "").strip()
            raw_answer = str(item.get("raw_answer") or "").strip()
            if not target_gap or not raw_answer:
                raise CustomerOnboardingError(
                    "GAP_ANSWER_INVALID",
                    "Every gap supplement requires target_gap and raw_answer.",
                )
            normalized_gap_answers.append(
                {"target_gap": target_gap, "raw_answer": raw_answer}
            )
        gap_answers = normalized_gap_answers
        materials = "\n\n".join(item["raw_answer"] for item in gap_answers)
    elif intake_type == "initial_onboarding":
        materials = str(request.get("materials") or "").strip()
        gap_answers = []
        reviewed_context = {}
        created_by = {}
        source_lineage = {}
    else:
        raise CustomerOnboardingError(
            "INTAKE_TYPE_INVALID",
            "Unsupported Customer Intake type.",
        )

    if not ID_RE.fullmatch(business_id):
        raise CustomerOnboardingError(
            "INVALID_BUSINESS_ID",
            "business_id must be machine-safe.",
        )

    if not ID_RE.fullmatch(intake_id):
        raise CustomerOnboardingError(
            "INVALID_INTAKE_ID",
            "intake_id must be machine-safe.",
        )

    if not customer_name:
        raise CustomerOnboardingError(
            "CUSTOMER_NAME_REQUIRED",
            "Customer name is required.",
        )

    if not industry:
        raise CustomerOnboardingError(
            "INDUSTRY_REQUIRED",
            "Industry is required.",
        )

    if not materials:
        raise CustomerOnboardingError(
            "CUSTOMER_MATERIALS_REQUIRED",
            "Existing customer materials are required.",
        )

    if len(materials) > 50000:
        raise CustomerOnboardingError(
            "CUSTOMER_MATERIALS_TOO_LONG",
            "Customer materials exceed the V1 input limit.",
        )

    return {
        "business_id": business_id,
        "intake_id": intake_id,
        "intake_type": intake_type,
        "customer_name": customer_name,
        "industry": industry,
        "materials": materials,
        "gap_answers": gap_answers,
        "reviewed_context": reviewed_context if isinstance(reviewed_context, dict) else {},
        "created_by": created_by if isinstance(created_by, dict) else {},
        "source_lineage": source_lineage if isinstance(source_lineage, dict) else {},
    }


def build_raw_answers(
    request: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Raw input remains local Customer Input Authority.

    AI output never gets embedded here.
    """

    business_id = request["business_id"]
    intake_id = request["intake_id"]

    if request["intake_type"] == "gap_supplement":
        return [
            {
                "answer_id": f"{intake_id}_gap_{index:02d}",
                "topic": "gap_supplement",
                "target_gap": item["target_gap"],
                "answer_text": item["raw_answer"],
                "input_actor": "operator",
                "source_type": "operator_entered_gap_supplement",
                "source_ref": (
                    f"{business_id}:{intake_id}:gap:{item['target_gap']}"
                ),
                "confirmation_basis": "operator_explicit_input",
            }
            for index, item in enumerate(request["gap_answers"], start=1)
        ]

    return [
        {
            "answer_id": f"{intake_id}_business_name",
            "topic": "business_name",
            "answer_text": request["customer_name"],
            "normalized_value": request["customer_name"],
            "input_actor": "authorized_business_representative",
            "source_type": "operator_entered_customer_identity",
            "source_ref": f"{business_id}:{intake_id}:customer_name",
            "confirmation_basis": "operator_explicit_input",
        },
        {
            "answer_id": f"{intake_id}_industry",
            "topic": "industry",
            "answer_text": request["industry"],
            "normalized_value": request["industry"],
            "input_actor": "authorized_business_representative",
            "source_type": "operator_entered_customer_identity",
            "source_ref": f"{business_id}:{intake_id}:industry",
            "confirmation_basis": "operator_explicit_input",
        },
        {
            "answer_id": f"{intake_id}_materials",
            "topic": "freeform_customer_materials",
            "answer_text": request["materials"],
            "input_actor": "authorized_business_representative",
            "source_type": "operator_entered_customer_materials",
            "source_ref": f"{business_id}:{intake_id}:materials",
            "confirmation_basis": "raw_customer_materials",
        },
    ]


def build_privacy_projection(
    request: dict[str, Any],
    *,
    created_at: str,
) -> dict[str, Any]:
    raw_materials = request["materials"]
    safe_materials = project_safe_semantic(raw_materials)

    annotations = detect_sensitive_spans(raw_materials)

    safe_context = {
        str(field): project_safe_semantic(
            json.dumps(value, ensure_ascii=False)
            if not isinstance(value, str)
            else value
        )
        for field, value in request.get("reviewed_context", {}).items()
    }
    rendered_probe = (
        f"客户名称：{project_safe_semantic(request['customer_name'])}\n"
        f"行业：{project_safe_semantic(request['industry'])}\n"
        f"已确认信息：{json.dumps(safe_context, ensure_ascii=False)}\n"
        f"资料：{safe_materials}"
    )

    # Final deterministic remote-egress gate.
    assert_safe_for_external_model(rendered_probe)

    return {
        "schema_version": "customer-intake-privacy-projection-v1.0",
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "business_id": request["business_id"],
        "intake_id": request["intake_id"],
        "intake_type": request["intake_type"],
        "target_gaps": [
            item["target_gap"] for item in request.get("gap_answers", [])
        ],
        "created_at": created_at,
        "source": {
            "raw_materials_sha256": sha256_text(raw_materials),
        },
        "projection": {
            "customer_name_safe_semantic": project_safe_semantic(
                request["customer_name"]
            ),
            "industry_safe_semantic": project_safe_semantic(request["industry"]),
            "materials_safe_semantic": safe_materials,
            "reviewed_context_safe_semantic": safe_context,
        },
        "annotations": annotations,
        "validation": {
            "passed": True,
            "raw_source_modified": False,
            "external_model_gate_passed": True,
        },
    }


def build_prompt(
    privacy_projection: dict[str, Any],
) -> str:
    projection = privacy_projection["projection"]

    if privacy_projection.get("intake_type") == "gap_supplement":
        return f"""
你是 Customer Truth 补充信息提取器。

你的唯一任务：从“本次补充回答”中提取明确存在的新业务事实候选。

严格规则：

1. 只能提取本次补充回答明确支持的信息。
2. 已确认信息只用于理解上下文，不得从中重复生成候选。
3. evidence_quote 必须逐字来自本次补充回答。
4. 不得补全常识、推测画像或创造价格、流程、痛点。
5. 这里只生成 Fact Candidate，仍需 Human Review。
6. 不提取 Speaker 第一人称事实。

只允许以下 topic：

- primary_service
- core_audience
- customer_use_case
- customer_pain
- differentiator
- service_process
- service_time
- founder_story
- business_decision

输出严格 JSON：

{{
  "facts": [
    {{
      "topic": "customer_use_case",
      "value": ["明确事实"],
      "evidence_quote": "本次回答中的原文片段"
    }}
  ]
}}

如果本次补充回答没有任何可安全提取的信息：

{{"facts": []}}

客户名称：
{projection["customer_name_safe_semantic"]}

行业：
{projection["industry_safe_semantic"]}

已确认信息（只作上下文，不得重复输出）：
{json.dumps(projection.get("reviewed_context_safe_semantic", {}), ensure_ascii=False)}

本次补充回答：
{projection["materials_safe_semantic"]}
""".strip()

    return f"""
你是 Customer Truth Fact Extraction Engine。

你的唯一任务：
从用户已经提供的客户资料中提取明确存在的业务事实候选。

严格规则：

1. 只能提取原文明确支持的信息。
2. 不得补全常识。
3. 不得推测客户画像。
4. 不得把营销语气升级成事实。
5. 不得根据行业常识创造服务、价格、流程、客户痛点。
6. 没有明确证据的字段直接省略。
7. 这里只生成 Fact Candidate，不代表 Customer Truth。
8. 所有结果都必须等待 Human Review。
9. 不提取 Speaker 第一人称事实。
10. evidence_quote 必须来自下面提供的隐私安全资料，尽量短。

只允许以下 topic：

- primary_service
- core_audience
- customer_use_case
- customer_pain
- differentiator
- service_process
- service_time
- founder_story
- business_decision

输出严格 JSON：

{{
  "facts": [
    {{
      "topic": "primary_service",
      "value": ["明确事实1", "明确事实2"],
      "evidence_quote": "原文中的支持片段"
    }}
  ]
}}

如果没有任何可安全提取的信息：

{{
  "facts": []
}}

客户名称：
{projection["customer_name_safe_semantic"]}

行业：
{projection["industry_safe_semantic"]}

客户资料：
{projection["materials_safe_semantic"]}
""".strip()


def load_runtime_env(
    path: Path = ENV_PATH,
) -> dict[str, str]:
    if not path.is_file():
        raise CustomerOnboardingError(
            "PIPELINE_ENV_NOT_FOUND",
            f"Pipeline env file not found: {path}",
        )

    values: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[7:].lstrip()

        if "=" not in line:
            continue

        key, value = line.split(
            "=",
            1,
        )

        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
            value = value[1:-1]

        if key:
            values[key] = value

    return values


def load_deepseek_runtime_config() -> tuple[str, str]:
    values = load_runtime_env()

    api_key = str(values.get("DEEPSEEK_API_KEY") or "").strip()

    model = str(values.get("DEEPSEEK_MODEL") or "").strip()

    if not api_key:
        raise CustomerOnboardingError(
            "DEEPSEEK_API_KEY_REQUIRED",
            ("DEEPSEEK_API_KEY is missing " "from ops-pipeline/.env."),
        )

    if not model:
        raise CustomerOnboardingError(
            "DEEPSEEK_MODEL_REQUIRED",
            ("DEEPSEEK_MODEL is missing " "from ops-pipeline/.env."),
        )

    return api_key, model


def get_client(
    api_key: str,
) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        timeout=180.0,
        max_retries=0,
    )


def extract_remote_facts(
    safe_payload: dict[str, Any],
) -> dict[str, Any]:
    prompt = build_prompt(safe_payload)

    assert_safe_for_external_model(prompt)

    api_key, model = load_deepseek_runtime_config()

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
        max_tokens=5000,
        extra_body={
            "thinking": {
                "type": "disabled",
            }
        },
    )

    content = response.choices[0].message.content or ""

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CustomerOnboardingError(
            "FACT_EXTRACTION_INVALID_JSON",
            "Fact extraction returned invalid JSON.",
        ) from exc

    if not isinstance(payload, dict):
        raise CustomerOnboardingError(
            "FACT_EXTRACTION_INVALID_RESULT",
            "Fact extraction result must be an object.",
        )

    facts = payload.get("facts")

    if not isinstance(facts, list):
        raise CustomerOnboardingError(
            "FACT_EXTRACTION_INVALID_RESULT",
            "Fact extraction facts must be a list.",
        )

    if len(facts) > 30:
        raise CustomerOnboardingError(
            "FACT_EXTRACTION_TOO_MANY_FACTS",
            "Fact extraction returned too many candidates.",
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
) -> tuple[str, Any, str] | None:
    if not isinstance(fact, dict):
        return None

    topic = str(fact.get("topic") or "").strip()

    if topic not in AI_BUSINESS_TOPICS:
        return None

    mapping = INITIAL_TOPIC_MAP.get(topic)

    if mapping is None:
        return None

    scope, target_field = mapping

    if scope != "business":
        return None

    value = fact.get("value")

    if value in (None, "", []):
        return None

    evidence_quote = str(fact.get("evidence_quote") or "").strip()

    return target_field, value, evidence_quote


def build_ai_candidates(
    *,
    intake: dict[str, Any],
    deterministic_candidates: dict[str, Any],
    extracted: dict[str, Any],
    raw_materials: str,
    safe_materials: str,
) -> dict[str, Any]:
    candidates = list(deterministic_candidates.get("fact_candidates") or [])

    supplement = intake.get("intake_type") == "gap_supplement"
    source_answers = [
        item
        for item in intake["raw_answers"]
        if item["topic"]
        in {"freeform_customer_materials", "gap_supplement"}
    ]
    if not source_answers:
        raise CustomerOnboardingError(
            "CUSTOMER_MATERIALS_REQUIRED",
            "Customer materials are required for Fact Candidate extraction.",
        )

    existing_fields = {str(item.get("target_field") or "") for item in candidates}

    candidate_number = len(candidates) + 1

    for raw_fact in extracted.get("facts") or []:
        validated = validate_model_fact(raw_fact)

        if validated is None:
            continue

        target_field, value, safe_quote = validated

        # One initial candidate per target field keeps Human Review simple.
        if target_field in existing_fields:
            continue

        matching_answer = next(
            (
                item
                for item in source_answers
                if safe_quote and safe_quote in str(item.get("answer_text") or "")
            ),
            None,
        )
        if supplement and (
            not safe_quote
            or safe_quote not in safe_materials
            or matching_answer is None
        ):
            continue
        materials_answer = matching_answer or source_answers[0]
        if safe_quote and safe_quote in safe_materials and safe_quote in raw_materials:
            source_excerpt = safe_quote
        else:
            # Never invent an excerpt. The whole immutable raw input is a valid
            # verbatim authority reference when the privacy-safe quote cannot
            # be mapped byte-for-byte back to the raw input.
            source_excerpt = raw_materials

        candidates.append(
            {
                "fact_candidate_id": (
                    f"FC-{intake['intake_id']}-{candidate_number:03d}"
                ),
                "persona_scope": "business",
                "target_field": target_field,
                "normalized_value": value,
                "source_ref": materials_answer.get("source_ref"),
                "source_excerpt": source_excerpt,
                "raw_answer_ref": materials_answer["answer_id"],
                "input_actor": materials_answer["input_actor"],
                "source_type": materials_answer["source_type"],
                "confirmation_basis": ("ai_extracted_from_privacy_safe_projection"),
                "candidate_state": "requires_review",
                "conflict_refs": [],
                "privacy_state": "safe_for_external_model",
                "speaker_authority_assessment": ("business_candidate_only"),
                "time_metadata": None,
                "delta_type": "new_fact",
                "classification": (
                    "ai_extracted_gap_supplement"
                    if supplement
                    else "ai_extracted_initial_onboarding"
                ),
                "authorization": None,
                "review_note": (
                    "AI 从客户原始资料中提取；"
                    "必须由人工确认后才能成为 Persona Fact。"
                    + (f" 依据提示：{safe_quote}" if safe_quote else "")
                ),
            }
        )

        existing_fields.add(target_field)
        candidate_number += 1

    return build_fact_candidate_artifact(
        intake,
        candidates,
        created_at=str(intake.get("created_at") or now_iso()),
    )


def analyze_customer_onboarding(
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

    root = (
        pipeline_root
        / "data"
        / "customer_intakes"
        / request["business_id"]
        / request["intake_id"]
    )

    intake_path = root / "customer_intake_v1.json"
    privacy_path = root / "customer_intake_privacy_projection_v1.json"
    candidates_path = root / "persona_fact_candidates_v1.json"
    readiness_path = root / "persona_onboarding_readiness_v1.json"
    audit_path = root / "egress_audit_v1.json"
    summary_path = root / "customer_onboarding_analysis_v1.json"

    raw_answers = build_raw_answers(request)

    # ---------------------------------------------------------
    # Stage 1 — immutable Raw Customer Intake
    #
    # A real retry must reuse the original intake timestamp and
    # lineage instead of creating a logically different artifact.
    # ---------------------------------------------------------

    if intake_path.is_file():
        intake = read_json(intake_path)

        if (
            intake.get("intake_id") != request["intake_id"]
            or intake.get("provisional_business_id") != request["business_id"]
        ):
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                ("Existing Customer Intake identity " "does not match this request."),
            )

        expected_raw_sha = sha256_json(raw_answers)

        actual_raw_sha = intake.get(
            "raw_input_contract",
            {},
        ).get("raw_answers_sha256")

        if actual_raw_sha != expected_raw_sha:
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                (
                    "The same intake_id cannot "
                    "silently replace its immutable "
                    "Customer Input."
                ),
            )

        timestamp = str(intake.get("created_at") or "")

        if not timestamp:
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_INVALID",
                ("Existing Customer Intake " "has no created_at."),
            )

    else:
        timestamp = created_at or now_iso()

        intake = build_customer_intake(
            intake_id=request["intake_id"],
            intake_type=request["intake_type"],
            provisional_business_id=(request["business_id"]),
            business_ref=None,
            input_actor=(
                "operator"
                if request["intake_type"] == "gap_supplement"
                else "authorized_business_representative"
            ),
            input_sources=[
                {
                    "source_type": (
                        "internal_console_customer_gap_supplement"
                        if request["intake_type"] == "gap_supplement"
                        else "internal_console_customer_materials"
                    ),
                    "source_ref": (
                        f"{request['business_id']}:" f"{request['intake_id']}"
                    ),
                }
            ],
            raw_answers=raw_answers,
            speaker_selection={
                "speaker_type": "generic",
                "selection_status": "deferred",
            },
            target_gaps=(
                [
                    {"target_gap": item["target_gap"]}
                    for item in request["gap_answers"]
                ]
                if request["intake_type"] == "gap_supplement"
                else None
            ),
            created_by=(request.get("created_by") or None),
            source_lineage=(request.get("source_lineage") or None),
            created_at=timestamp,
        )

        write_new_or_same(
            intake_path,
            intake,
        )

    # A completed immutable operation is directly recoverable.
    # The raw-input lineage above was validated first, so changed
    # input can never use this fast path.
    if summary_path.is_file():
        summary = read_json(summary_path)

        if (
            summary.get("business_id") != request["business_id"]
            or summary.get("intake_id") != request["intake_id"]
        ):
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                ("Existing onboarding summary " "does not match this request."),
            )

        return summary

    # ---------------------------------------------------------
    # Stage 2 — Privacy Projection
    # ---------------------------------------------------------

    if privacy_path.is_file():
        privacy = read_json(privacy_path)

        if (
            privacy.get("business_id") != request["business_id"]
            or privacy.get("intake_id") != request["intake_id"]
            or (privacy.get("source") or {}).get("raw_materials_sha256")
            != sha256_text(request["materials"])
        ):
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                (
                    "Existing privacy projection "
                    "does not match the immutable "
                    "Customer Input."
                ),
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

    prompt = build_prompt(privacy)

    egress_audit = build_egress_audit(
        safe_input=privacy["projection"],
        rendered_prompt=prompt,
        privacy_context={"privacy_projection_sha256": (sha256_json(privacy))},
    )

    deterministic = extract_initial_fact_candidates(intake)

    # ---------------------------------------------------------
    # Stage 3 — AI Fact Candidates
    #
    # This is the important recovery checkpoint:
    # once the candidate artifact exists, never call the remote
    # model again merely because the process/app restarted.
    # ---------------------------------------------------------

    candidates_preexisting = candidates_path.is_file()

    if candidates_preexisting:
        candidates = read_json(candidates_path)

        candidate_intake_ref = candidates.get("intake_ref") or {}

        if candidate_intake_ref.get("intake_id") != request[
            "intake_id"
        ] or candidate_intake_ref.get("raw_answers_sha256") != (
            intake.get(
                "raw_input_contract",
                {},
            ).get("raw_answers_sha256")
        ):
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                (
                    "Existing Fact Candidates "
                    "do not match this immutable "
                    "Customer Intake."
                ),
            )

        extracted = {
            "model": ("recovered_existing_candidates"),
            "usage": {},
        }

    else:
        if extractor is None:
            extracted = extract_remote_facts(
                privacy,
            )
        else:
            extracted = extractor(privacy)

        if not isinstance(
            extracted,
            dict,
        ):
            raise CustomerOnboardingError(
                "FACT_EXTRACTION_INVALID_RESULT",
                ("Extractor must return " "a JSON object."),
            )

        candidates = build_ai_candidates(
            intake=intake,
            deterministic_candidates=(deterministic),
            extracted=extracted,
            raw_materials=(request["materials"]),
            safe_materials=(privacy["projection"]["materials_safe_semantic"]),
        )

        write_new_or_same(
            candidates_path,
            candidates,
        )

    # ---------------------------------------------------------
    # Stage 4 — Readiness
    # ---------------------------------------------------------

    if readiness_path.is_file():
        readiness = read_json(readiness_path)
    else:
        reviewed_context = request.get("reviewed_context") or {}
        context_persona = (
            {
                "facts": {
                    str(field): {"state": "known", "value": value}
                    for field, value in reviewed_context.items()
                }
            }
            if reviewed_context
            else None
        )
        readiness = assess_persona_onboarding_readiness(
            intake,
            candidates,
            business_persona=context_persona,
            created_at=timestamp,
        )

        write_new_or_same(
            readiness_path,
            readiness,
        )

    # ---------------------------------------------------------
    # Stage 5 — Egress Audit
    #
    # If a crash happened after the Candidate checkpoint but
    # before this audit was written, recovery records that the
    # existing Candidate artifact was reused instead of claiming
    # a second remote call.
    # ---------------------------------------------------------

    if not audit_path.is_file():
        audit = {
            "schema_version": ("customer-intake-" "egress-audit-v1.0"),
            "business_id": (request["business_id"]),
            "intake_id": (request["intake_id"]),
            "created_at": timestamp,
            "privacy_policy_version": (PRIVACY_POLICY_VERSION),
            **egress_audit,
            "model": extracted.get(
                "model",
                "test-extractor",
            ),
            "usage": extracted.get(
                "usage",
                {},
            ),
            "raw_customer_input_sent_directly": (False),
            "recovered_from_existing_candidates": (candidates_preexisting),
        }

        write_new_or_same(
            audit_path,
            audit,
        )

    # ---------------------------------------------------------
    # Stage 6 — Completed Operation Summary
    # ---------------------------------------------------------

    summary = {
        "schema_version": SCHEMA_VERSION,
        "operation_version": (OPERATION_VERSION),
        "business_id": (request["business_id"]),
        "intake_id": (request["intake_id"]),
        "intake_type": request["intake_type"],
        "target_gaps": [
            item["target_gap"] for item in request.get("gap_answers", [])
        ],
        "status": ("awaiting_fact_review"),
        "created_at": timestamp,
        "artifacts": {
            "customer_intake_v1": str(intake_path.resolve()),
            "privacy_projection_v1": str(privacy_path.resolve()),
            "fact_candidates_v1": str(candidates_path.resolve()),
            "readiness_v1": str(readiness_path.resolve()),
            "egress_audit_v1": str(audit_path.resolve()),
        },
        "candidate_summary": (candidates["summary"]),
        "readiness": {
            "status": readiness.get("status"),
            "critical_missing_truth": (
                readiness.get(
                    "critical_missing_truth",
                    [],
                )
            ),
        },
        "authority": {
            "raw_input_is_customer_truth": (False),
            "fact_candidates_are_customer_truth": (False),
            "persona_created": False,
            "persona_approved": False,
            "human_review_required": True,
            "case_sources_consumed": False,
        },
        "next_action": ("REVIEW_CUSTOMER_FACTS"),
    }

    write_new_or_same(
        summary_path,
        summary,
    )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Analyze initial free-form customer materials into "
            "privacy-safe, Human-review-required Persona fact candidates."
        )
    )

    parser.add_argument(
        "--request",
        required=True,
        help="JSON request file.",
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
        summary = analyze_customer_onboarding(
            request=request,
            pipeline_root=pipeline_root,
        )
    except CustomerOnboardingError as exc:
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
                "business_id": summary["business_id"],
                "intake_id": summary["intake_id"],
                "status": summary["status"],
                "next_action": summary["next_action"],
                "candidate_summary": summary["candidate_summary"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
