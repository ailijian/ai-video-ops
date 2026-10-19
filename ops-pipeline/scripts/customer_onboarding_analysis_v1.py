from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import OpenAI

from customer_constraints_v1 import extract_constraints
from build_persona_v1 import recovery_target_fields

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
from speaker_discovery_v1 import (
    SpeakerDiscoveryError,
    build_candidate_artifact as build_speaker_discovery_artifact,
    build_failed_artifact as build_failed_speaker_discovery_artifact,
    build_prompt as build_speaker_discovery_prompt,
)

SCHEMA_VERSION = "customer-onboarding-analysis-v1.0"
OPERATION_VERSION = "customer_onboarding_analysis_v1.py@1.0"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,127}$")

from customer_intake_v1 import CUSTOMER_INDUSTRIES

AI_BUSINESS_TOPICS = {
    "industry",
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


def validate_saved_source_recovery(request: dict[str, Any], pipeline_root: Path) -> None:
    lineage = request.get("source_lineage") or {}
    if lineage.get("operation") != "saved_source_recovery":
        return
    source_id = str(lineage.get("source_intake_id") or "")
    targets = lineage.get("recovery_targets")
    if (request["intake_type"] != "gap_supplement" or not re.fullmatch(r"intake_\d{4}", source_id)
            or source_id == request["intake_id"] or not isinstance(targets, list) or not targets
            or set(targets) - set(recovery_target_fields()) or not lineage.get("execution_identity")):
        raise CustomerOnboardingError("RECOVERY_SOURCE_INVALID", "Recovery identity or targets are invalid.")
    source = pipeline_root / "data/customer_intakes" / request["business_id"] / source_id
    raw_path = source / "customer_intake_v1.json"
    projection_path = source / "customer_intake_privacy_projection_v1.json"
    original_path = source / "customer_onboarding_request_v1.json"
    if not all(p.is_file() for p in (raw_path, projection_path, original_path)):
        raise CustomerOnboardingError("RECOVERY_SOURCE_MISSING", "Immutable saved source is unavailable.")
    raw = read_json(raw_path)
    source_projection = read_json(projection_path)
    original_materials = str(read_json(original_path).get("materials") or "").strip()
    raw_sha = sha256_json(raw.get("raw_answers") or [])
    expected = sha256_json({"source_intake_id": source_id,
        "raw_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "projection_sha256": hashlib.sha256(projection_path.read_bytes()).hexdigest(),
        "targets": sorted(set(targets)), "execution_identity": lineage["execution_identity"]})
    if (raw.get("provisional_business_id") != request["business_id"] or raw.get("intake_id") != source_id
            or raw_sha != raw.get("raw_input_contract", {}).get("raw_answers_sha256")
            or raw_sha != lineage.get("source_raw_answers_sha256")
            or hashlib.sha256(raw_path.read_bytes()).hexdigest() != lineage.get("source_raw_sha256")
            or hashlib.sha256(projection_path.read_bytes()).hexdigest() != lineage.get("source_projection_sha256")
            or source_projection.get("business_id") != request["business_id"]
            or source_projection.get("intake_id") != source_id
            or source_projection.get("source", {}).get("raw_materials_sha256") != sha256_text(original_materials)
            or not any(v.get("topic") == "freeform_customer_materials" and v.get("answer_text") == original_materials
                for v in raw.get("raw_answers") or [])
            or expected != lineage.get("recovery_identity")
            or request["materials"] != original_materials):
        raise CustomerOnboardingError("RECOVERY_SOURCE_SHA_MISMATCH", "Saved source lineage changed; extraction was not performed.")


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
        recovery = (request.get("source_lineage") or {}).get("operation") == "saved_source_recovery"
        return [
            {
                "answer_id": f"{intake_id}_gap_{index:02d}",
                "topic": "gap_supplement",
                "target_gap": item["target_gap"],
                "answer_text": item["raw_answer"],
                "input_actor": "operator",
                "source_type": "saved_source_extraction_recovery" if recovery else "operator_entered_gap_supplement",
                "source_ref": (
                    f"{business_id}:{intake_id}:gap:{item['target_gap']}"
                ),
                "confirmation_basis": "operator_requested_saved_source_recovery" if recovery else "operator_explicit_input",
            }
            for index, item in enumerate(request["gap_answers"], start=1)
        ]

    answers = [
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
    return [item for item in answers if str(item.get("answer_text") or "").strip()]



def build_privacy_projection(
    request: dict[str, Any],
    *,
    created_at: str,
) -> dict[str, Any]:
    raw_materials = request["materials"]
    from privacy_projection_v1 import project_task_materials
    safe_materials = project_task_materials(raw_materials, task="customer")

    annotations = detect_sensitive_spans(raw_materials)

    safe_context = {
        str(field): project_task_materials(
            json.dumps(value, ensure_ascii=False)
            if not isinstance(value, str)
            else value, task="customer"
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
        "recovery_targets": (request.get("source_lineage") or {}).get("recovery_targets", []),
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
    restriction_contract = """
同时提取有逐字来源的重要限制，在 constraints 数组中返回。限制不是可宣传事实，绝不能重复写入 facts。
constraint_type 仅允许 publication_prohibition（明确宣传禁用）、unverified_claim（未核实主张）、identity_conflict（主体/核心身份冲突）、conditional_fact（附条件事实）。
scope：identity_conflict 必须为 business，其余为 claim。
每项包含 evidence_quote、affected_fields（正式事实字段数组）、blocked_terms（原文中不得使用的短语数组）、related_fact_refs（关联事实引用数组）、condition（附条件事实的逐字条件，其余 null）。
无法可靠指向来源/作用对象时不要创造限制或事实；所有限制仍需独立人工检查，不能将待核实奖项作为已获奖事实。
另外返回 source_coverage 数组，逐项引用资料中明确覆盖的能力组及逐字 evidence_quote。
capability_group 仅允许 business_identity、customer_use_context、production_bearing_facts、critical_constraints。
这是来源覆盖观察，不能批准事实。没有逐字来源就不输出该组，不能凭空断定客户未提供资料。
""".strip()

    if privacy_projection.get("recovery_targets"):
        restriction_contract += "\n此次为已保存历史资料的遗漏恢复，不是客户新增回答。只提取这些未覆盖领域：" + ", ".join(privacy_projection["recovery_targets"]) + "。已审核字段不得重复生成候选。"
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
{restriction_contract}

只允许以下 topic：

- industry（只在资料足够时推荐；使用正式行业选项：餐饮、本地生活、零售、烘焙甜品、美容、教培、服装、饰品、通用行业；不足时不要输出）
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
{restriction_contract}

只允许以下 topic：

- industry（只在资料足够时推荐；使用正式行业选项：餐饮、本地生活、零售、烘焙甜品、美容、教培、服装、饰品、通用行业；不足时不要输出）
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
    # Pure proposal derivation is also used by the Console. The paid-model SDK
    # belongs only to the external extraction boundary.
    from openai import OpenAI
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
        "constraints": payload.get("constraints", []),
        "source_coverage": payload.get("source_coverage", []),
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


def extract_remote_speaker_candidates(
    safe_payload: dict[str, Any],
) -> dict[str, Any]:
    prompt = build_speaker_discovery_prompt(safe_payload)
    assert_safe_for_external_model(prompt)

    api_key, model = load_deepseek_runtime_config()
    client = get_client(api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=4000,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = response.choices[0].message.content or ""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_INVALID_JSON",
            "Speaker Discovery returned invalid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_RESULT_INVALID",
            "Speaker Discovery result must be an object.",
        )
    payload["model"] = model
    payload["usage"] = {
        "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
        "completion_tokens": getattr(response.usage, "completion_tokens", None),
        "total_tokens": getattr(response.usage, "total_tokens", None),
    }
    return payload


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
    if topic == "industry" and value not in CUSTOMER_INDUSTRIES:
        return None

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
    recovery = (intake.get("source_lineage") or {}).get("operation") == "saved_source_recovery"
    allowed_fields = None
    if recovery:
        targets = intake["source_lineage"]["recovery_targets"]
        mapping = recovery_target_fields()
        allowed_fields = set().union(*(mapping[target] for target in targets))
        existing_fields.update(intake["source_lineage"].get("already_reviewed_fields", []))

    candidate_number = len(candidates) + 1

    for raw_fact in extracted.get("facts") or []:
        validated = validate_model_fact(raw_fact)

        if validated is None:
            continue

        target_field, value, safe_quote = validated
        if allowed_fields is not None and target_field not in allowed_fields:
            continue
        if target_field == "industry" and (not safe_quote or safe_quote not in safe_materials):
            continue

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

    artifact = build_fact_candidate_artifact(
        intake,
        candidates,
        created_at=str(intake.get("created_at") or now_iso()),
        derived_authority_constraints=extract_constraints(
            intake, extracted if not recovery or "critical_constraints" in targets else {"constraints": []}, safe_materials),
    )
    coverage = extracted.get("source_coverage") or []
    if not isinstance(coverage, list) or len(coverage) > 8:
        raise CustomerOnboardingError("SOURCE_COVERAGE_INVALID", "Source observations must be a bounded list.")
    observations = []
    for item in coverage:
        group = item.get("capability_group") if isinstance(item, dict) else None
        quote = str(item.get("evidence_quote") or "") if isinstance(item, dict) else ""
        answer = next((v for v in source_answers if quote and quote in v["answer_text"]), None)
        if group not in recovery_target_fields() or group == "industry" or not quote or quote not in safe_materials or answer is None:
            raise CustomerOnboardingError("SOURCE_COVERAGE_INVALID", "Source observation lacks exact safe evidence.")
        observations.append({"capability_group": group, "evidence_quote": quote,
            "raw_answer_ref": answer["answer_id"], "raw_answers_sha256": intake["raw_input_contract"]["raw_answers_sha256"],
            "observation_is_human_approval": False})
    if observations:
        artifact["source_coverage"] = observations
    return artifact


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
    speaker_discovery_extractor: (
        Callable[[dict[str, Any]], dict[str, Any]] | None
    ) = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    request = validate_request(request)

    validate_saved_source_recovery(request, pipeline_root)

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
    speaker_discovery_path = root / "speaker_discovery_candidates_v1.json"
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
    # Stage 3b — Speaker Discovery Candidates
    #
    # This is an independent, fail-soft remote extraction. It never
    # promotes Business Facts into Speaker Truth and can never make the
    # Customer analysis fail. An existing artifact is always reused.
    # ---------------------------------------------------------

    if speaker_discovery_path.is_file():
        speaker_discovery = read_json(speaker_discovery_path)
        if (
            speaker_discovery.get("business_id") != request["business_id"]
            or speaker_discovery.get("intake_id") != request["intake_id"]
        ):
            raise CustomerOnboardingError(
                "ONBOARDING_ARTIFACT_CONFLICT",
                "Existing Speaker Discovery artifact has different identity.",
            )
    else:
        try:
            if (request.get("source_lineage") or {}).get("operation") == "saved_source_recovery":
                # Business recovery preserves existing Speaker discovery and Drafts.
                speaker_extracted = {"speaker_candidates": [], "model": "saved-source-business-recovery", "usage": {}}
            elif speaker_discovery_extractor is not None:
                speaker_extracted = speaker_discovery_extractor(privacy)
            elif extractor is None:
                speaker_extracted = extract_remote_speaker_candidates(privacy)
            else:
                # Existing unit callers inject only the Business extractor.
                # Keep them network-free; focused discovery tests inject the
                # independent extractor explicitly.
                speaker_extracted = {
                    "speaker_candidates": [],
                    "model": "test-discovery-not-provided",
                    "usage": {},
                }
            speaker_discovery = build_speaker_discovery_artifact(
                business_id=request["business_id"],
                intake_id=request["intake_id"],
                created_at=timestamp,
                extracted=speaker_extracted,
                privacy_projection=privacy,
                customer_intake_path=intake_path,
                privacy_projection_path=privacy_path,
            )
        except Exception as exc:
            speaker_discovery = build_failed_speaker_discovery_artifact(
                business_id=request["business_id"],
                intake_id=request["intake_id"],
                created_at=timestamp,
                failure_code=str(
                    getattr(exc, "code", "SPEAKER_DISCOVERY_FAILED")
                ),
                customer_intake_path=intake_path,
                privacy_projection_path=privacy_path,
            )
        write_new_or_same(speaker_discovery_path, speaker_discovery)

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
            "speaker_discovery_candidates_v1": str(
                speaker_discovery_path.resolve()
            ),
            "readiness_v1": str(readiness_path.resolve()),
            "egress_audit_v1": str(audit_path.resolve()),
        },
        "candidate_summary": (candidates["summary"]),
        "speaker_discovery": {
            "status": speaker_discovery.get("speaker_discovery_status"),
            "candidate_count": len(
                speaker_discovery.get("speaker_candidates") or []
            ),
        },
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
            "speaker_discovery_is_speaker_truth": False,
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


def retry_speaker_discovery(*, request_path: Path, pipeline_root: Path, extractor=None) -> dict[str, Any]:
    """Retry only fail-soft person discovery from the saved safe projection.

    Each admitted retry has immutable request/result artifacts. Customer facts,
    readiness, original discovery and Human decisions are never rewritten.
    """
    retry = read_json(request_path)
    business_id, intake_id = retry["business_id"], retry["intake_id"]
    if not ID_RE.fullmatch(business_id) or not re.fullmatch(r"intake_\d{4}", intake_id):
        raise CustomerOnboardingError("INVALID_DISCOVERY_RETRY", "Invalid intake identity.")
    intake = pipeline_root / "data/customer_intakes" / business_id / intake_id
    expected_root = intake / "speaker_discovery_retries"
    if request_path.resolve().parent.parent != expected_root.resolve():
        raise CustomerOnboardingError("INVALID_DISCOVERY_RETRY", "Retry must belong to the intake.")
    output = request_path.parent / "speaker_discovery_candidates_v1.json"
    if output.is_file():
        return read_json(output)
    privacy_path = intake / "customer_intake_privacy_projection_v1.json"
    privacy = read_json(privacy_path)
    # This is the same privacy-projected extraction and candidate validator as
    # the original pipeline; no new Customer fact extractor is invoked.
    try:
        extracted = (extractor or extract_remote_speaker_candidates)(privacy)
        artifact = build_speaker_discovery_artifact(business_id=business_id, intake_id=intake_id,
            created_at=now_iso(), extracted=extracted, privacy_projection=privacy,
            customer_intake_path=intake / "customer_intake_v1.json", privacy_projection_path=privacy_path)
    except Exception as exc:
        artifact = build_failed_speaker_discovery_artifact(business_id=business_id, intake_id=intake_id,
            created_at=now_iso(), failure_code=str(getattr(exc, "code", "SPEAKER_DISCOVERY_FAILED")),
            customer_intake_path=intake / "customer_intake_v1.json", privacy_projection_path=privacy_path)
    write_new_or_same(output, artifact)
    return artifact


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

    parser.add_argument("--discovery-retry", action="store_true")
    args = parser.parse_args()

    pipeline_root = (
        Path(args.pipeline_root).expanduser().resolve()
        if args.pipeline_root
        else Path(__file__).resolve().parents[1]
    )

    if args.discovery_retry:
        artifact = retry_speaker_discovery(request_path=Path(args.request).expanduser().resolve(), pipeline_root=pipeline_root)
        ok = artifact.get("speaker_discovery_status") != "failed"
        print(json.dumps({"ok": ok, "code": "SPEAKER_DISCOVERY_FAILED" if not ok else "OK", "message": "人物发现暂未完成，请稍后重试。" if not ok else "人物发现已完成。"}, ensure_ascii=False))
        raise SystemExit(0 if ok else 2)

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
