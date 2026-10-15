from __future__ import annotations

import base64
import hmac
import secrets
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .persona_authority import resolve_persona_authority, validate_speaker_business_binding
from .speaker_gateway import prepare_discovered_speaker_draft
from .subprocess_env import pipeline_subprocess_env

_REVIEW_CONTEXT_KEY = secrets.token_bytes(32)


def _review_snapshot(settings, business_id):
    from customer_constraints_v1 import digest, file_sha
    directory = _latest_intake_dir(settings, business_id)
    if directory is None or not (directory / "persona_fact_candidates_v1.json").is_file():
        return None
    paths = []
    for base in (settings.pipeline_root / "data" / "customer_intakes" / business_id,
            settings.pipeline_root / "data" / "personas" / business_id):
        paths.extend(base.rglob("*.json"))
    return {"intake_id": directory.name,
        "node_sha256": digest([str(settings.pipeline_root.resolve()), str(settings.database_path.resolve())]),
        "candidate_sha256": file_sha(directory / "persona_fact_candidates_v1.json"),
        "state_sha256": digest({str(p.relative_to(settings.pipeline_root)): file_sha(p) for p in sorted(paths)})}


def customer_review_context(settings, business_id, actor_id, actor):
    snapshot = _review_snapshot(settings, business_id)
    if not snapshot:
        return None
    payload = {"version": "customer-review-context-v1.0", "business_id": business_id,
        "actor_id": actor_id, "actor": actor, "operation_id": secrets.token_hex(16), **snapshot}
    body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode()
    signature = hmac.new(_REVIEW_CONTEXT_KEY, body.encode(), "sha256").hexdigest()
    return {"token": body + "." + signature, "operation_id": payload["operation_id"],
        "candidate_sha256": snapshot["candidate_sha256"], "state_sha256": snapshot["state_sha256"]}


def validate_customer_review_context(settings, business_id, token, actor_id, actor, payload):
    """Called inside Business Lock, before any mutation. Exact committed replay survives restart."""
    from customer_constraints_v1 import digest
    from customer_fact_review_v1 import read_review_progress, validate_review_request, canonical_sha256
    try:
        body, signature = token.split(".")
        context = json.loads(base64.urlsafe_b64decode(body))
        if (set(context) != {"version", "business_id", "actor_id", "actor", "operation_id", "intake_id", "candidate_sha256", "state_sha256", "node_sha256"}
                or context["version"] != "customer-review-context-v1.0" or context["business_id"] != business_id
                or not re.fullmatch(r"[a-z0-9_-]{1,128}", context["intake_id"])
                or not re.fullmatch(r"[a-f0-9]{32}", context["operation_id"])):
            raise ValueError()
    except Exception as exc:
        raise CanonicalOperationError("INVALID_REVIEW_CONTEXT", "审核上下文无效。", "请刷新后重新核对。") from exc
    if context.get("actor_id") != actor_id or context.get("actor") != actor:
        raise CanonicalOperationError("REVIEW_ACTOR_MISMATCH", "不能使用其他同事的审核身份。", "请刷新后使用自己的审核页面。")
    directory = settings.pipeline_root / "data" / "customer_intakes" / business_id / context["intake_id"]
    progress = read_review_progress(directory)
    if payload.get("resume_review"):
        if (not progress["complete"] or not progress["receipts"] or progress["receipts"][-1]["reviewer"] != actor
                or payload.get("decisions") or payload.get("constraint_decisions") or payload.get("industry_review") or payload.get("speaker_confirmations")
                or not hmac.compare_digest(signature, hmac.new(_REVIEW_CONTEXT_KEY, body.encode(), "sha256").hexdigest())
                or _review_snapshot(settings, business_id) != {k: context[k] for k in ("intake_id", "candidate_sha256", "state_sha256", "node_sha256")}):
            raise CanonicalOperationError("REVIEW_CONTEXT_STALE", "保存恢复身份或状态已变化。", "请由原提交同事刷新并继续保存。")
        return {"review_mode": "resume", "intake_id": context["intake_id"]}
    context_sha = digest({"token": token, "speaker_confirmations": payload.get("speaker_confirmations", [])})
    replay = next((v for v in progress["receipts"] if v["operation_id"] == context["operation_id"]), None)
    version = replay["request"]["context_version"] if replay else progress["version"]
    intent = {**validate_review_request({**payload, "business_id": business_id,
        "intake_id": context["intake_id"], "reviewer": actor}), "operation_id": context["operation_id"],
        "context_version": version, "context_sha256": context_sha}
    if replay:
        if replay["request_sha256"] != canonical_sha256(intent) or replay["reviewer"] != actor:
            raise CanonicalOperationError("REVIEW_REPLAY_CONFLICT", "本次提交身份已经用于其他内容。", "请刷新后重新核对。")
    elif (not hmac.compare_digest(signature, hmac.new(_REVIEW_CONTEXT_KEY, body.encode(), "sha256").hexdigest())
            or _review_snapshot(settings, business_id) != {k: context[k] for k in ("intake_id", "candidate_sha256", "state_sha256", "node_sha256")}):
        raise CanonicalOperationError("REVIEW_CONTEXT_STALE", "信息已更新，需要重新核对。", "请刷新页面；已保存的决定会继续保留。")
    return {"operation_id": context["operation_id"], "context_version": version,
        "context_sha256": context_sha, "review_mode": "progress", "intake_id": context["intake_id"]}

BUSINESS_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,127}$")


def _safe_review_selection(candidate, intake, constraints):
    """Conservative UI suggestion; never grants Human authority or model-confidence trust."""
    from customer_constraints_v1 import digest
    if candidate.get("candidate_state") != "requires_review":
        return None, None
    quote = candidate.get("source_excerpt")
    answer = next((v for v in intake.get("raw_answers", []) if v.get("answer_id") == candidate.get("raw_answer_ref")), None)
    if (digest(intake.get("raw_answers", [])) != intake.get("raw_input_contract", {}).get("raw_answers_sha256")
            or not answer or not isinstance(quote, str) or not quote.strip() or len(quote) > 1000
            or quote not in answer.get("answer_text", "") or candidate.get("conflict_refs")):
        return None, "来源或冲突需要重点核对"
    if candidate.get("persona_scope") != "business" or candidate.get("target_field") not in {
            "industry", "primary_products_or_services", "secondary_products_or_services", "core_audience",
            "customer_use_cases", "customer_pains", "service_process", "process_facts", "service_area", "location_public_area"}:
        return None, "这类信息需要明确选择处理方式"
    value = candidate.get("normalized_value")
    rendered = json.dumps(value, ensure_ascii=False)
    if re.search(r"[0-9]|获奖|奖项|认证|第一|最好|保证|本人|我曾|我从|授权|荣誉|营业额|增长", quote + rendered):
        return None, "宣传、数字或本人归属需要进一步核对"
    if any(v.get("state") != "resolved" and (v.get("scope") == "business"
            or candidate["target_field"] in v.get("affected_fields", [])
            or any(term in rendered for term in v.get("blocked_terms", []))) for v in constraints):
        return None, "相关信息受重要限制影响"
    parts = value if isinstance(value, list) else [value]
    if candidate["target_field"] == "industry":
        evidence_words = {"餐饮": ("菜", "餐", "宴"), "本地生活": ("本地生活",), "零售": ("零售",),
            "烘焙甜品": ("烘焙", "甜品"), "美容": ("美容",), "教培": ("培训", "教育"),
            "服装": ("服装",), "饰品": ("饰品",), "通用行业": ("通用行业",)}
        supported = value in evidence_words and any(v in quote for v in evidence_words[value])
    else:
        supported = bool(parts) and all(isinstance(v, str) and v.strip() and v in quote for v in parts)
    return ("approve", None) if supported else (None, "整理后的表达需要与原文进一步核对")

REQUEST_SCHEMA_VERSION = "customer-onboarding-request-v1.0"
GAP_SUPPLEMENT_SCHEMA_VERSION = "customer-gap-supplement-request-v1.0"

READINESS_CAPABILITY_GAPS = {
    "business_identity",
    "customer_use_context",
    "production_bearing_facts",
    "critical_constraints",
}

LEGACY_BLOCKER_CAPABILITY = {
    "public_display_name": "business_identity",
    "company_short_name": "business_identity",
    "industry": "business_identity",
    "primary_products_or_services": "business_identity",
    "core_audience": "customer_use_context",
    "customer_use_cases": "customer_use_context",
    "customer_pains": "customer_use_context",
    "differentiators": "production_bearing_facts",
}

GAP_QUESTIONS = {
    "business_identity": {
        "label": "主要产品或服务",
        "question": "还有哪些主要产品或服务？",
    },
    "customer_use_context": {
        "label": "顾客和使用场景",
        "question": (
            "什么样的顾客通常会来？他们一般在什么情况下会使用你们的服务？"
        ),
    },
    "production_bearing_facts": {
        "label": "具体业务信息",
        "question": (
            "再告诉我们一些具体业务信息，例如价格、流程、服务内容、营业规则或真实案例。"
        ),
    },
}

OPTIONAL_PRODUCTION_GAP_QUESTIONS = {
    "additional_materials": {"label": "新增真实资料", "question": "请粘贴新增的真实业务资料。已有已批准事实会保留。"},
    "process_material": {
        "label": "真实服务流程",
        "question": (
            "这项服务从开始到结束通常如何完成？请只填写已经确认的真实步骤，"
            "以及出镜人本人实际参与的部分。"
        ),
    },
}


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


def _read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise CanonicalOperationError(
            "CUSTOMER_ARTIFACT_INVALID",
            "客户 Authority artifact 无法读取。",
            "请检查该客户的数据文件后重试。",
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise CanonicalOperationError(
            "CUSTOMER_ARTIFACT_INVALID",
            "客户 Authority artifact 格式无效。",
            "请检查该客户的数据文件后重试。",
        )

    return value


def _write_json_atomic(
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


def _known_fact_value(
    persona: dict[str, Any] | None,
    field: str,
) -> Any:
    if not persona:
        return None

    fact = persona.get("facts", {}).get(field, {})

    if fact.get("state") != "known":
        return None

    return fact.get("value")


def _latest_business_persona(
    settings: Settings,
    business_id: str,
) -> (
    tuple[
        Path,
        dict[str, Any],
    ]
    | None
):
    resolved = resolve_persona_authority(
        settings,
        business_id,
        "business",
    )
    projected = resolved.projected
    if projected is None:
        return None
    return projected["path"], projected["artifact"]


def _latest_intake_dir(
    settings: Settings,
    business_id: str,
) -> Path | None:
    root = settings.pipeline_root / "data" / "customer_intakes" / business_id

    if not root.exists():
        return None

    directories = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        reverse=True,
    )

    return directories[0] if directories else None


def _intake_dirs(
    settings: Settings,
    business_id: str,
) -> list[Path]:
    root = settings.pipeline_root / "data" / "customer_intakes" / business_id
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def _latest_full_intake_dir(
    settings: Settings,
    business_id: str,
) -> Path | None:
    for directory in reversed(_intake_dirs(settings, business_id)):
        request_path = directory / "customer_onboarding_request_v1.json"
        if not request_path.is_file():
            continue
        request = _read_json(request_path)
        if request.get("intake_type") != "gap_supplement" and request.get(
            "materials"
        ) is not None:
            return directory
    return None


def _reviewed_business_context(
    settings: Settings,
    business_id: str,
) -> dict[str, Any]:
    grouped: dict[str, list[Any]] = {}
    current = resolve_persona_authority(settings, business_id, "business").current
    if current:
        for field, fact in (current["artifact"].get("facts") or {}).items():
            if fact.get("state") == "known" and fact.get("value") not in (None, "", []):
                grouped.setdefault(field, []).append(copy.deepcopy(fact["value"]))
    for directory in _intake_dirs(settings, business_id):
        path = directory / "reviewed_persona_fact_candidates_v1.json"
        if not path.is_file():
            continue
        artifact = _read_json(path)
        for item in artifact.get("fact_candidates") or []:
            if not isinstance(item, dict) or (
                item.get("persona_scope") != "business"
                or item.get("candidate_state") != "known_candidate"
            ):
                continue
            field = str(item.get("target_field") or "")
            value = item.get("normalized_value")
            if field and value not in (None, "", []):
                grouped.setdefault(field, []).append(copy.deepcopy(value))
    context: dict[str, Any] = {}
    for field, values in grouped.items():
        unique: list[Any] = []
        seen: set[str] = set()
        for value in values:
            fingerprint = canonical_sha256(value)
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique.append(value)
        context[field] = unique[0] if len(unique) == 1 else unique
    return context


def _normalized_readiness_blockers(
    blockers: list[Any],
) -> list[str]:
    normalized: list[str] = []
    for blocker in blockers:
        value = LEGACY_BLOCKER_CAPABILITY.get(str(blocker), str(blocker))
        if value in READINESS_CAPABILITY_GAPS and value not in normalized:
            normalized.append(value)
    return normalized


def _critical_gap_details(
    settings: Settings,
    business_id: str,
) -> list[dict[str, str]]:
    from customer_constraints_v1 import collect, policy, unresolved_legacy_constraints
    values: list[dict[str, str]] = []
    records = collect(settings.pipeline_root, business_id)
    for source in unresolved_legacy_constraints(settings.pipeline_root, business_id, records):
        item = source["record"]
        values.append({"gap_id": f"critical_constraints:{source['constraint_id']}:{source['source_intake_id']}", "label": "关键冲突确认",
            "question": str(item.get("question") or item.get("message") or item.get("description") or "请说明这项关键信息的真实情况。")})
    for item in policy(records)["blockers"]:
        values.append({"gap_id": f"critical_constraints:{item['constraint_id']}", "label": "重要限制核对",
            "question": item["source"]["evidence_quote"]})
    return values


def _readiness_gap_projection(
    settings: Settings,
    business_id: str,
    fact_review: dict[str, Any] | None,
) -> list[dict[str, str]]:
    blockers = _normalized_readiness_blockers(
        list((fact_review or {}).get("business_persona_blockers") or [])
    )
    result: list[dict[str, str]] = []
    for blocker in blockers:
        if blocker == "critical_constraints":
            details = _critical_gap_details(settings, business_id)
            result.extend(
                details
                or [
                    {
                        "gap_id": "critical_constraints",
                        "label": "关键冲突确认",
                        "question": "请说明当前冲突信息中哪一项准确，以及真实情况是什么。",
                    }
                ]
            )
            continue
        question = GAP_QUESTIONS.get(blocker)
        if question:
            result.append({"gap_id": blocker, **question})
    explanations = {item["capability_group"]: item for item in _business_gap_explanations(settings, business_id)}
    for gap in result:
        reason = explanations.get(gap["gap_id"].split(":", 1)[0])
        if reason:
            gap.update(reason=reason["reason"], explanation=reason["message"])
    return result


def _business_gap_explanations(settings: Settings, business_id: str) -> list[dict[str, Any]]:
    """Read-only explanation of canonical sources/candidates/reviews; not a new Gate."""
    from build_persona_v1 import recovery_target_fields, assess_business_persona_capabilities
    from customer_constraints_v1 import collect, policy
    from customer_fact_review_v1 import combined_critical_constraints
    mapping = recovery_target_fields()
    known = _reviewed_business_context(settings, business_id)
    readiness = assess_business_persona_capabilities({k: {"state": "known", "value": v} for k, v in known.items()})
    candidates: list[tuple[str, dict[str, Any], bool]] = []
    coverage: dict[str, list[dict[str, Any]]] = {}
    source_exists = False
    for directory in _intake_dirs(settings, business_id):
        raw_path = directory / "customer_intake_v1.json"
        if raw_path.is_file():
            source_exists |= any(v.get("topic") in {"freeform_customer_materials", "gap_supplement"} and v.get("answer_text")
                for v in _read_json(raw_path).get("raw_answers", []))
        path = directory / "persona_fact_candidates_v1.json"
        if not path.is_file():
            continue
        artifact = _read_json(path)
        reviewed_path = directory / "reviewed_persona_fact_candidates_v1.json"
        reviewed = _read_json(reviewed_path) if reviewed_path.is_file() else None
        for item in (reviewed or artifact).get("fact_candidates", []):
            candidates.append((directory.name, item, reviewed is not None))
        for item in artifact.get("source_coverage") or []:
            # Check exact local source identity again before explaining an omission.
            raw = _read_json(raw_path)
            if (item.get("raw_answers_sha256") != raw.get("raw_input_contract", {}).get("raw_answers_sha256")
                    or not any(v.get("answer_id") == item.get("raw_answer_ref") and item.get("evidence_quote")
                        and item["evidence_quote"] in v.get("answer_text", "") for v in raw.get("raw_answers", []))):
                raise CanonicalOperationError("SOURCE_COVERAGE_INVALID", "来源覆盖校验失败。", "请保留资料并联系维护人员。")
            coverage.setdefault(item["capability_group"], []).append({"source_intake_id": directory.name, "evidence_quote": item["evidence_quote"]})
    controls = collect(settings.pipeline_root, business_id)
    rules = policy(controls)
    result = []
    for group in READINESS_CAPABILITY_GAPS:
        rows = [(source, item, reviewed) for source, item, reviewed in candidates if item.get("target_field") in mapping[group]]
        pending = [item for _, item, reviewed in rows if not reviewed and item.get("candidate_state") == "requires_review"]
        if group == "critical_constraints":
            if combined_critical_constraints(settings.pipeline_root, business_id):
                pending_controls = any(v.get("state") == "pending_review" for v in controls)
                reason, message = ("review_pending", "以下重要限制等待核对。") if pending_controls else ("conflict", "以下内容需要进一步核实；限制未被解除。")
            else:
                reason, message = "satisfied", "已知限制检查未发现当前阻断；这不表示未经核实的宣传已获准使用。"
        elif group not in readiness["blockers"]:
            reason, message = "satisfied", "客户信息已核对完成。"
        elif pending:
            reason, message = "review_pending", "以下信息等待核对。"
        elif rows:
            reason, message = "not_adopted", "这部分信息曾被提取，但尚无可采用的已核对事实。请核实来源或补充。"
        elif coverage.get(group):
            reason, message = "extraction_omission", "资料已经提供，系统尚未成功整理。"
        elif not source_exists:
            reason, message = "source_missing", "还需要客户补充这部分信息。"
        else:
            reason, message = "source_coverage_unknown", "资料已经保存，但尚未找到这部分信息的可验证来源。可以查看原文或补齐识别。"
        result.append({"capability_group": group, "reason": reason, "message": message,
            "source_evidence": coverage.get(group, []), "candidate_refs": [item.get("fact_candidate_id") for _, item, _ in rows],
            "projection_is_authority": False})
    return sorted(result, key=lambda item: item["capability_group"])


def _intake_identity(
    intake_dir: Path | None,
) -> dict[str, Any]:
    if intake_dir is None:
        return {}

    request_path = intake_dir / ("customer_onboarding_" "request_v1.json")

    if request_path.is_file():
        request = _read_json(request_path)

        return {
            "customer_name": (request.get("customer_name")),
            "industry": (request.get("industry")),
            "intake_id": (request.get("intake_id")),
            "intake_type": (request.get("intake_type") or "initial_onboarding"),
            "save_only": request.get("save_only", False),
            "created_by": request.get("created_by"),
            "created_at": request.get("created_at"),
        }

    intake_path = intake_dir / "customer_intake_v1.json"

    if not intake_path.is_file():
        return {}

    intake = _read_json(intake_path)

    identity: dict[
        str,
        Any,
    ] = {
        "intake_id": (intake.get("intake_id")),
    }

    for answer in intake.get("raw_answers") or []:
        if not isinstance(
            answer,
            dict,
        ):
            continue

        topic = str(answer.get("topic") or "")

        value = (
            answer.get("normalized_value")
            if answer.get("normalized_value") is not None
            else answer.get("answer_text")
        )

        if topic == "business_name":
            identity["customer_name"] = value

        elif topic == "industry":
            identity["industry"] = value

    return identity


def _approved_speaker_count(
    settings: Settings,
    business_id: str,
) -> int:
    root = settings.pipeline_root / "data" / "personas"

    if not root.exists():
        return 0

    business = resolve_persona_authority(
        settings,
        business_id,
        "business",
    ).current
    if business is None:
        return 0

    count = 0

    for persona_root in (path for path in root.iterdir() if path.is_dir()):
        paths = list(persona_root.glob("revision_*/persona_v1.json"))
        if not paths:
            continue
        personas = [_read_json(path) for path in paths]
        if not any(
            persona.get("persona_scope", "business") == "speaker"
            and (persona.get("business_persona_ref") or {}).get("persona_id")
            == business_id
            for persona in personas
        ):
            continue
        resolved = resolve_persona_authority(
            settings,
            persona_root.name,
            "speaker",
        )
        speaker = resolved.current
        if speaker is None:
            continue
        reference = speaker["artifact"].get("business_persona_ref") or {}
        if reference.get("persona_id") != business_id:
            continue
        if int(reference.get("revision") or 0) < int(business["revision"]):
            continue
        validate_speaker_business_binding(speaker, business)
        count += 1

    return count


def _project_persona(
    persona_path: Path,
    persona: dict[str, Any],
) -> dict[str, Any]:
    lifecycle = persona.get("lifecycle") or {}

    facts: list[dict[str, Any]] = []

    for field, fact in (persona.get("facts") or {}).items():
        if not isinstance(
            fact,
            dict,
        ):
            continue

        facts.append(
            {
                "field": field,
                "state": (fact.get("state")),
                "value": (fact.get("value")),
                "review_note": (fact.get("review_note")),
            }
        )

    return {
        "persona_id": (persona.get("persona_id")),
        "revision": (persona.get("revision")),
        "status": (lifecycle.get("status")),
        "approved": (lifecycle.get("approved") is True),
        "approved_at": (lifecycle.get("approved_at")),
        "facts": facts,
        "path": str(persona_path.resolve()),
    }


def _customer_projection(
    settings: Settings,
    business_id: str,
    *,
    approved_speaker_count: int | None = None,
) -> dict[str, Any]:
    intake_dir = _latest_intake_dir(
        settings,
        business_id,
    )

    intake_identity = _intake_identity(intake_dir)

    latest_persona = _latest_business_persona(
        settings,
        business_id,
    )

    persona_path: Path | None = None
    persona: dict[str, Any] | None = None

    if latest_persona:
        (
            persona_path,
            persona,
        ) = latest_persona

    display_name = (
        _known_fact_value(
            persona,
            "public_display_name",
        )
        or _known_fact_value(
            persona,
            "company_short_name",
        )
        or intake_identity.get("customer_name")
        or business_id
    )

    industry = (
        _known_fact_value(
            persona,
            "industry",
        )
        or intake_identity.get("industry")
        or "待确认"
    )
    industry_classification = None
    for directory in reversed(_intake_dirs(settings, business_id)):
        path = directory / "reviewed_persona_fact_candidates_v1.json"
        if (directory / "review_progress").is_dir():
            from customer_fact_review_v1 import read_review_progress
            reviewed = read_review_progress(directory)["artifact"]
        elif path.is_file():
            reviewed = _read_json(path)
        else:
            continue
        selected = next((v for v in reversed(reviewed.get("fact_candidates") or [])
            if v.get("target_field") == "industry" and
            (v.get("candidate_state") == "known_candidate" or (v.get("human_review") or {}).get("decision") in {"uncertain", "reject"})), None)
        if selected:
            industry_classification = {"value": selected.get("normalized_value"),
                "decision": (selected.get("human_review") or {}).get("decision") or next((v.get("decision") for v in (reviewed.get("review") or {}).get("decisions", []) if v.get("candidate_id") == selected.get("fact_candidate_id")), None),
                "source_type": selected.get("source_type"), "source_intake_id": directory.name,
                "reviewer": (selected.get("human_review") or {}).get("reviewer") or (reviewed.get("review") or {}).get("reviewer"),
                "reviewed_at": (selected.get("human_review") or {}).get("reviewed_at") or (reviewed.get("review") or {}).get("reviewed_at"),
                "persona_approved_by_classification": False}
            industry = selected.get("normalized_value") or "暂不确定"
            break

    status = "draft"

    review: dict[str, Any] | None = None

    candidate_path: Path | None = None

    request_exists = False

    if intake_dir:
        request_exists = (
            intake_dir / ("customer_onboarding_" "request_v1.json")
        ).is_file()

        candidate_path = intake_dir / ("persona_fact_" "candidates_v1.json")

        review_path = intake_dir / ("customer_fact_" "review_v1.json")

        if review_path.is_file():
            review = _read_json(review_path)

    review_status = str((review or {}).get("status") or "")

    if (
        candidate_path
        and candidate_path.is_file()
        and not review_status.startswith("completed_")
    ):
        status = "fact_review_required"

    elif review_status == ("completed_" "persona_blocked"):
        status = "needs_more_info"

    elif persona:
        lifecycle = persona.get("lifecycle") or {}

        if lifecycle.get("status") == "review_required":
            status = "persona_review_required"

        elif (
            lifecycle.get("status") == "approved" and lifecycle.get("approved") is True
        ):
            status = "approved"

    elif request_exists:
        status = "draft" if intake_identity.get("save_only") else "analysis_pending"

    current_entry = resolve_persona_authority(settings, business_id, "business").current
    return {
        "business_id": business_id,
        "current_business_persona": _project_persona(current_entry["path"], current_entry["artifact"]) if current_entry else None,
        "display_name": str(display_name),
        "submitted_by": intake_identity.get("created_by"),
        "submitted_at": intake_identity.get("created_at"),
        "industry": str(industry),
        "industry_classification": industry_classification,
        "status": status,
        "speaker_count": approved_speaker_count if approved_speaker_count is not None else (
            _approved_speaker_count(
                settings,
                business_id,
            )
        ),
        "latest_intake_id": (intake_identity.get("intake_id")),
        "latest_intake_type": (
            intake_identity.get("intake_type") or "initial_onboarding"
        ),
        "business_persona": (
            _project_persona(
                persona_path,
                persona,
            )
            if (persona_path and persona)
            else None
        ),
    }


def list_customers(
    settings: Settings,
) -> list[dict[str, Any]]:
    business_ids: set[str] = set()

    persona_root = settings.pipeline_root / "data" / "personas"

    if persona_root.exists():
        for directory in (path for path in (persona_root.iterdir()) if path.is_dir()):
            paths = list(directory.glob("revision_*/persona_v1.json"))
            if not paths:
                continue
            if any(
                _read_json(path).get("persona_scope", "business") == "business"
                for path in paths
            ):
                business_ids.add(directory.name)

    intake_root = settings.pipeline_root / "data" / "customer_intakes"

    if intake_root.exists():
        for directory in (path for path in (intake_root.iterdir()) if path.is_dir()):
            if BUSINESS_ID_RE.fullmatch(directory.name):
                business_ids.add(directory.name)

    customers = [
        _customer_projection(
            settings,
            business_id,
        )
        for business_id in sorted(business_ids)
    ]

    customers.sort(
        key=lambda item: (
            item["status"] != "fact_review_required",
            item["status"] != "persona_review_required",
            item["display_name"],
        )
    )

    return customers


def customer_attention_count(
    settings: Settings,
) -> int:
    return sum(
        customer["status"]
        in {
            "fact_review_required",
            "persona_review_required",
        }
        for customer in (list_customers(settings))
    )


def _candidate_projection(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    excerpt = str(candidate.get("source_excerpt") or "")

    if len(excerpt) > 600:
        excerpt = excerpt[:599] + "…"

    return {
        "candidate_id": (candidate.get("fact_candidate_id")),
        "scope": (candidate.get("persona_scope")),
        "field": (candidate.get("target_field")),
        "state": (candidate.get("candidate_state")),
        "value": (candidate.get("normalized_value")),
        "source_excerpt": excerpt,
        "review_note": (candidate.get("review_note")),
        "human_review": (candidate.get("human_review")),
    }


def _speaker_discovery_path(intake_dir: Path) -> Path:
    retries = sorted((intake_dir / "speaker_discovery_retries").glob("retry_*/speaker_discovery_candidates_v1.json"))
    return retries[-1] if retries else intake_dir / "speaker_discovery_candidates_v1.json"


def prepare_speaker_discovery_retry(settings: Settings, business_id: str, *, actor: str) -> dict[str, Any]:
    root = _latest_intake_dir(settings, business_id)
    if root is None:
        raise CanonicalOperationError("CUSTOMER_INTAKE_NOT_FOUND", "没有找到客户资料。", "请打开客户资料后继续。")
    source = _speaker_discovery_path(root)
    previous = _read_json(source) if source.is_file() else {}
    retryable = previous.get("speaker_discovery_status") == "failed" or (
        previous.get("speaker_discovery_status") == "completed"
        and not previous.get("speaker_candidates")
    )
    if not retryable:
        return {"already_available": True}
    if not (root / "customer_intake_privacy_projection_v1.json").is_file():
        raise CanonicalOperationError("PRIVACY_PROJECTION_MISSING", "暂时无法安全查找人物。", "请检查原分析任务，客户事实仍然保留。")
    retries = root / "speaker_discovery_retries"
    existing = sorted(retries.glob("retry_*/speaker_discovery_retry_request_v1.json"))
    if existing and not (existing[-1].parent / "speaker_discovery_candidates_v1.json").exists():
        request_path = existing[-1]
    else:
        request_path = retries / f"retry_{len(existing) + 1:04d}" / "speaker_discovery_retry_request_v1.json"
        _write_json_atomic(request_path, {"business_id": business_id, "intake_id": root.name,
            "created_by": actor, "created_at": now_iso(), "operation": "retry_speaker_discovery_only"})
    original = _read_json(root / "customer_onboarding_request_v1.json")
    return {"business_id": business_id, "intake_id": root.name,
        "request_path": str((root / "customer_onboarding_request_v1.json").resolve()),
        "discovery_retry_request": str(request_path.resolve()),
        "customer_name": original["customer_name"], "industry": original.get("industry") or ""}


def _speaker_discovery_projection(
    intake_dir: Path | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    if intake_dir is None:
        return None, []
    path = _speaker_discovery_path(intake_dir)
    if not path.is_file():
        return None, []
    artifact = _read_json(path)
    confirmation_path = intake_dir / "speaker_discovery_confirmation_v1.json"
    confirmed_ids: set[str] = set()
    if confirmation_path.is_file():
        confirmation = _read_json(confirmation_path)
        confirmed_ids = {
            str(item.get("candidate_id") or "")
            for item in confirmation.get("decisions") or []
            if isinstance(item, dict)
            and item.get("outcome") in {"draft_created", "existing_speaker"}
        }
    candidates = []
    for item in artifact.get("speaker_candidates") or []:
        if not isinstance(item, dict) or not item.get("evidence_quotes"):
            continue
        candidate_id = str(item.get("candidate_id") or "")
        candidates.append(
            {
                "candidate_id": candidate_id,
                "name": item.get("name"),
                "public_role": item.get("public_role"),
                "speaker_type_hint": item.get("speaker_type_hint"),
                "candidate_status": item.get("candidate_status"),
                "evidence_quotes": list(item.get("evidence_quotes") or []),
                "personal_material_quotes": list(
                    item.get("personal_material_quotes") or []
                ),
                "default_selected": False,
                "confirmed": candidate_id in confirmed_ids,
                "confirmation": (
                    next(
                        (
                            decision
                            for decision in (confirmation.get("decisions") or [])
                            if decision.get("candidate_id") == candidate_id
                        ),
                        None,
                    )
                    if confirmation_path.is_file()
                    else None
                ),
            }
        )
    return str(artifact.get("speaker_discovery_status") or ""), candidates


def get_customer_detail(
    settings: Settings,
    business_id: str,
) -> dict[str, Any]:
    if not BUSINESS_ID_RE.fullmatch(business_id):
        raise CanonicalOperationError(
            "INVALID_BUSINESS_ID",
            "客户引用格式无效。",
            "请返回客户列表重新选择。",
        )

    persona_root = settings.pipeline_root / "data" / "personas" / business_id

    intake_root = settings.pipeline_root / "data" / "customer_intakes" / business_id

    if not persona_root.exists() and not intake_root.exists():
        raise CanonicalOperationError(
            "CUSTOMER_NOT_FOUND",
            "没有找到这个客户。",
            "请返回客户列表重新选择。",
        )

    projection = _customer_projection(
        settings,
        business_id,
    )

    intake_dir = _latest_intake_dir(
        settings,
        business_id,
    )

    candidates: list[dict[str, Any]] = []
    constraint_candidates: list[dict[str, Any]] = []

    reviewed_candidates: list[dict[str, Any]] = []

    fact_review: dict[str, Any] | None = None
    review_progress = None

    if intake_dir:
        candidate_path = intake_dir / ("persona_fact_" "candidates_v1.json")

        if candidate_path.is_file():
            artifact = _read_json(candidate_path)
            if (intake_dir / "review_progress").is_dir():
                from customer_fact_review_v1 import read_review_progress
                review_progress = read_review_progress(intake_dir)
                artifact = review_progress["artifact"]
            constraint_candidates = copy.deepcopy(artifact.get("derived_authority_constraints") or [])
            from customer_constraints_v1 import digest
            for control in constraint_candidates:
                control["original_constraint_sha256"] = digest(control)

            candidates = [
                _candidate_projection(item)
                for item in (artifact.get("fact_candidates") or [])
                if isinstance(
                    item,
                    dict,
                )
            ]
            for original, projected in zip(artifact.get("fact_candidates", []), candidates):
                projected["default_review_selection"], projected["review_exception_reason"] = _safe_review_selection(
                    original, _read_json(intake_dir / "customer_intake_v1.json"), constraint_candidates)

        review_path = intake_dir / ("customer_fact_" "review_v1.json")

        if review_path.is_file():
            fact_review = _read_json(review_path)

    speaker_discovery_status, speaker_candidates = (
        _speaker_discovery_projection(intake_dir)
    )

    for directory in _intake_dirs(settings, business_id):
        reviewed_path = directory / ("reviewed_persona_" "fact_candidates_v1.json")
        if not reviewed_path.is_file():
            continue
        artifact = _read_json(reviewed_path)
        reviewed_candidates.extend(
            _candidate_projection(item)
            for item in (artifact.get("fact_candidates") or [])
            if isinstance(item, dict)
        )

    status = projection["status"]
    completion_pending = bool(review_progress and review_progress["complete"] and not str((fact_review or {}).get("status", "")).startswith("completed_"))
    if review_progress and (not review_progress["complete"] or completion_pending):
        status = "fact_review_required"

    next_action = {
        "analysis_pending": ("WAIT_FOR_CUSTOMER_ANALYSIS"),
        "fact_review_required": ("REVIEW_CUSTOMER_FACTS"),
        "needs_more_info": ("COLLECT_MORE_CUSTOMER_TRUTH"),
        "persona_review_required": ("REVIEW_BUSINESS_PERSONA"),
        "approved": ("ADD_OR_SELECT_SPEAKER"),
    }.get(
        status,
        "NONE",
    )

    current = resolve_persona_authority(settings, business_id, "business").current
    raw_blockers = list((fact_review or {}).get("business_persona_blockers") or [])
    from customer_constraints_v1 import resolution_targets
    targets = resolution_targets(settings.pipeline_root, business_id, intake_dir.name) if intake_dir else []
    return {
        **projection,
        "status": status,
        "review_progress": ({"version": review_progress["version"],
            "pending_count": len(review_progress["pending_ids"]) + len(review_progress["pending_constraint_ids"]),
            "saved_count": len(review_progress["decisions"]) + len(review_progress["constraint_decisions"]),
            "complete": review_progress["complete"], "completion_retry_required": completion_pending,
            "completion_actor": review_progress["receipts"][-1]["reviewer"] if review_progress["receipts"] else None}
            if review_progress else None),
        "fact_candidates": (candidates),
        "constraint_candidates": constraint_candidates,
        "saved_source_recovery": saved_source_recovery_projection(settings, business_id),
        "gap_explanations": _business_gap_explanations(settings, business_id),
        "constraint_resolution_targets": targets,
        "reviewed_fact_candidates": (reviewed_candidates),
        "fact_review": fact_review,
        "current_business_persona": _project_persona(current["path"], current["artifact"]) if current else None,
        "production_constraint_blocked": bool(current and (current.get("production_constraints") or {}).get("blockers")),
        "speaker_discovery_status": speaker_discovery_status,
        "speaker_candidates": speaker_candidates,
        "speaker_confirmation": (
            _read_json(intake_dir / "speaker_discovery_confirmation_v1.json")
            if intake_dir
            and (intake_dir / "speaker_discovery_confirmation_v1.json").is_file()
            else None
        ),
        "readiness_gaps": _readiness_gap_projection(
            settings,
            business_id,
            fact_review,
        ),
        "legacy_readiness_recheck_available": any(
            str(item) not in READINESS_CAPABILITY_GAPS for item in raw_blockers
        ),
        "next_action": next_action,
        "authority": {
            "raw_input_is_persona": False,
            "fact_candidate_is_persona_fact": False,
            "fact_review_is_persona_approval": False,
            "business_persona_is_speaker_persona": False,
        },
    }


def _normalize_name(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        "",
        value,
    ).casefold()


def _machine_business_id(
    customer_name: str,
    industry: str,
) -> str:
    # Allocate once. Industry and later display-label corrections are not identity.
    return f"customer_{uuid.uuid4().hex}"



def get_customer_input(
    settings: Settings,
    business_id: str,
) -> dict[str, Any]:
    if not BUSINESS_ID_RE.fullmatch(business_id):
        raise CanonicalOperationError(
            "INVALID_BUSINESS_ID",
            "客户引用格式无效。",
            "请返回客户列表重新选择。",
        )

    intake_dir = _latest_full_intake_dir(
        settings,
        business_id,
    )

    if intake_dir is None:
        raise CanonicalOperationError(
            "CUSTOMER_INTAKE_NOT_FOUND",
            "没有找到这个客户的录入资料。",
            "请重新建立客户。",
        )

    request_path = intake_dir / "customer_onboarding_request_v1.json"

    if not request_path.is_file():
        raise CanonicalOperationError(
            "CUSTOMER_REQUEST_NOT_FOUND",
            "没有找到这个客户的原始分析请求。",
            "请检查客户录入 artifact。",
        )

    request = _read_json(request_path)

    return {
        "business_id": business_id,
        "intake_id": request.get("intake_id"),
        "customer_name": request.get("customer_name"),
        "industry": request.get("industry"),
        "materials": request.get("materials"),
        "request_path": str(request_path.resolve()),
    }


def prepare_customer_gap_supplement_request(
    settings: Settings,
    *,
    business_id: str,
    answers: list[dict[str, Any]],
    created_by_user_id: int,
    created_by_phone: str,
) -> dict[str, Any]:
    if not BUSINESS_ID_RE.fullmatch(business_id):
        raise CanonicalOperationError(
            "INVALID_BUSINESS_ID",
            "客户引用格式无效。",
            "请返回客户列表重新选择。",
        )
    detail = get_customer_detail(settings, business_id)
    requested_gap_ids = {
        str(item.get("target_gap") or "").strip()
        for item in answers
        if str(item.get("target_gap") or "").strip()
    }
    readiness_supplement = detail["status"] == "needs_more_info"
    optional_production_supplement = (
        detail["status"] == "approved"
        and bool(requested_gap_ids)
        and requested_gap_ids.issubset(set(OPTIONAL_PRODUCTION_GAP_QUESTIONS) | {"additional_materials"})
    )
    if not readiness_supplement and not optional_production_supplement:
        raise CanonicalOperationError(
            "CUSTOMER_GAP_SUPPLEMENT_NOT_REQUIRED",
            "当前客户不需要补充这些信息。",
            "请刷新客户详情并按当前状态继续。",
        )
    available = (
        {
            str(item["gap_id"]): item
            for item in detail.get("readiness_gaps") or []
        }
        if readiness_supplement
        else OPTIONAL_PRODUCTION_GAP_QUESTIONS
    )
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in answers:
        target_gap = str(item.get("target_gap") or "").strip()
        raw_answer = str(item.get("raw_answer") or "").strip()
        if target_gap not in available:
            raise CanonicalOperationError(
                "CUSTOMER_GAP_INVALID",
                "补充问题已经变化。",
                "请刷新页面后按当前缺失信息重新填写。",
            )
        if not raw_answer:
            continue
        if len(raw_answer) > 12000:
            raise CanonicalOperationError(
                "CUSTOMER_GAP_ANSWER_TOO_LONG",
                "单项补充内容过长。",
                "请将这项回答精简到 12000 字以内。",
            )
        if target_gap in seen:
            raise CanonicalOperationError(
                "CUSTOMER_GAP_DUPLICATE",
                "同一项缺失信息只能提交一次回答。",
                "请合并回答后重新提交。",
            )
        seen.add(target_gap)
        normalized.append(
            {
                "target_gap": target_gap,
                "raw_answer": raw_answer,
            }
        )
    if not normalized:
        raise CanonicalOperationError(
            "CUSTOMER_GAP_ANSWER_REQUIRED",
            "请至少补充一项缺失信息。",
            "填写真实信息后再继续。",
        )

    directories = _intake_dirs(settings, business_id)
    numbers = []
    for directory in directories:
        match = re.fullmatch(r"intake_(\d{4})", directory.name)
        if match:
            numbers.append(int(match.group(1)))
    intake_id = f"intake_{max(numbers, default=0) + 1:04d}"
    root = (
        settings.pipeline_root
        / "data"
        / "customer_intakes"
        / business_id
        / intake_id
    )
    request_path = root / "customer_onboarding_request_v1.json"
    reviewed_sources: list[dict[str, Any]] = []
    for directory in directories:
        path = directory / "reviewed_persona_fact_candidates_v1.json"
        if path.is_file():
            reviewed_sources.append(
                {
                    "intake_id": directory.name,
                    "path": str(path.resolve()),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    created_at = now_iso()
    request = {
        "schema_version": GAP_SUPPLEMENT_SCHEMA_VERSION,
        "intake_type": "gap_supplement",
        "business_id": business_id,
        "intake_id": intake_id,
        "customer_name": detail["display_name"],
        "industry": detail["industry"],
        "target_gaps": [item["target_gap"] for item in normalized],
        "supplement_purpose": (
            "persona_readiness"
            if readiness_supplement
            else "optional_production_capability"
        ),
        "gap_answers": normalized,
        "input_actor": "operator",
        "created_by": {
            "user_id": created_by_user_id,
            "phone": created_by_phone,
        },
        "created_at": created_at,
        "reviewed_context": _reviewed_business_context(settings, business_id),
        "source_lineage": {
            "previous_intake_ids": [path.name for path in directories],
            "reviewed_fact_artifacts": reviewed_sources,
            "old_human_decisions_preserved": True,
        },
        "authority": {
            "ui_request_is_customer_truth": False,
            "supplement_only": True,
            "full_materials_reanalysis_allowed": False,
            "previous_intakes_preserved": True,
            "human_review_required": True,
            "business_persona_approved_status_preserved_until_new_revision": True,
        },
    }
    _write_json_atomic(request_path, request)
    return {
        "business_id": business_id,
        "intake_id": intake_id,
        "customer_name": detail["display_name"],
        "industry": detail["industry"],
        "request_path": str(request_path.resolve()),
        "target_gaps": request["target_gaps"],
    }


def saved_source_recovery_projection(settings: Settings, business_id: str) -> dict[str, Any]:
    from build_persona_v1 import recovery_target_fields
    from build_persona_v1 import assess_business_persona_capabilities
    source = _latest_full_intake_dir(settings, business_id)
    if source is None or not all((source / name).is_file() for name in
            ("customer_intake_v1.json", "customer_intake_privacy_projection_v1.json")):
        return {"available": False, "reason": "saved_source_not_ready", "targets": []}
    context = _reviewed_business_context(settings, business_id)
    readiness = assess_business_persona_capabilities({k: {"state": "known", "value": v} for k, v in context.items()})
    targets = [name for name in recovery_target_fields() if name in readiness["blockers"]]
    if "industry" not in context:
        targets.append("industry")
    candidate_path = source / "persona_fact_candidates_v1.json"
    if candidate_path.is_file() and not _read_json(candidate_path).get("derived_authority_constraints"):
        targets.append("critical_constraints")
    # Existing unreviewed candidates are handled by their own Human Review,
    # never treated as extraction omissions that justify a second task.
    pending_fields: set[str] = set()
    pending_constraints = False
    for directory in _intake_dirs(settings, business_id):
        path = directory / "persona_fact_candidates_v1.json"
        if path.is_file() and not (directory / "reviewed_persona_fact_candidates_v1.json").is_file():
            artifact = _read_json(path)
            pending_fields.update(str(v.get("target_field")) for v in artifact.get("fact_candidates", []) if v.get("candidate_state") == "requires_review")
            pending_constraints |= bool(artifact.get("derived_authority_constraints"))
    mapping = recovery_target_fields()
    targets = [name for name in targets if not (mapping[name] & pending_fields)
        and not (name == "critical_constraints" and pending_constraints)]
    targets = sorted(set(targets))
    return {"available": bool(targets), "source_intake_id": source.name, "targets": targets,
        "raw_sha256": hashlib.sha256((source / "customer_intake_v1.json").read_bytes()).hexdigest(),
        "projection_sha256": hashlib.sha256((source / "customer_intake_privacy_projection_v1.json").read_bytes()).hexdigest(),
        "source_presence_is_not_fact_approval": True}


def prepare_saved_source_recovery(settings: Settings, *, business_id: str, source_intake_id: str,
        targets: list[str], execution_identity: str, created_by_user_id: int, created_by_phone: str) -> dict[str, Any]:
    from build_persona_v1 import recovery_target_fields
    if not BUSINESS_ID_RE.fullmatch(business_id) or not re.fullmatch(r"intake_\d{4}", source_intake_id):
        raise CanonicalOperationError("RECOVERY_SOURCE_INVALID", "已保存资料引用无效。", "请刷新客户页面。")
    targets = sorted(set(targets))
    if not targets or set(targets) - set(recovery_target_fields()) or not execution_identity.strip():
        raise CanonicalOperationError("RECOVERY_TARGET_INVALID", "请明确需要补齐识别的领域。", "请从现有缺口中选择。")
    root = settings.pipeline_root / "data/customer_intakes" / business_id
    source = root / source_intake_id
    intake_path = source / "customer_intake_v1.json"
    privacy_path = source / "customer_intake_privacy_projection_v1.json"
    original_request = source / "customer_onboarding_request_v1.json"
    if not all(p.is_file() for p in (intake_path, privacy_path, original_request)):
        raise CanonicalOperationError("RECOVERY_SOURCE_MISSING", "原资料尚未形成可验证来源。", "请查看原分析任务；不需要重新粘贴完整材料。")
    source_raw_sha = hashlib.sha256(intake_path.read_bytes()).hexdigest()
    projection_sha = hashlib.sha256(privacy_path.read_bytes()).hexdigest()
    identity = canonical_sha256({"source_intake_id": source_intake_id, "raw_sha256": source_raw_sha,
        "projection_sha256": projection_sha, "targets": targets, "execution_identity": execution_identity})
    for directory in _intake_dirs(settings, business_id):
        path = directory / "customer_onboarding_request_v1.json"
        if path.is_file() and (_read_json(path).get("source_lineage") or {}).get("recovery_identity") == identity:
            return {"replayed": True, "business_id": business_id, "intake_id": directory.name,
                "request_path": str(path.resolve()), "customer_name": _read_json(path)["customer_name"],
                "industry": _read_json(path).get("industry") or ""}
    projection = saved_source_recovery_projection(settings, business_id)
    if source_intake_id != projection.get("source_intake_id") or set(targets) - set(projection["targets"]):
        raise CanonicalOperationError("RECOVERY_NOT_REQUIRED", "这些信息已有候选或已完成审核。", "请先处理现有候选；已确认的信息不会重新审核。")
    original = _read_json(original_request)
    intake = _read_json(intake_path)
    if canonical_sha256(intake.get("raw_answers") or []) != intake.get("raw_input_contract", {}).get("raw_answers_sha256"):
        raise CanonicalOperationError("RECOVERY_SOURCE_SHA_MISMATCH", "原资料来源校验未通过。", "请保留现有数据并联系维护人员。")
    materials = str(original.get("materials") or "").strip()
    if not materials:
        raise CanonicalOperationError("RECOVERY_SOURCE_EMPTY", "这份已保存资料没有可重新识别的正文。", "请补充真实业务资料。")
    privacy = _read_json(privacy_path)
    if (not any(v.get("topic") == "freeform_customer_materials" and v.get("answer_text") == materials for v in intake.get("raw_answers", []))
            or privacy.get("business_id") != business_id or privacy.get("intake_id") != source_intake_id
            or privacy.get("source", {}).get("raw_materials_sha256") != hashlib.sha256(materials.encode("utf-8")).hexdigest()):
        raise CanonicalOperationError("RECOVERY_SOURCE_SHA_MISMATCH", "保存的请求与原始资料来源不一致。", "请保留现有资料并联系维护人员。")
    numbers = [int(directory.name.split("_")[-1]) for directory in _intake_dirs(settings, business_id)
        if re.fullmatch(r"intake_\d{4}", directory.name)]
    intake_id = f"intake_{max(numbers, default=0) + 1:04d}"
    path = root / intake_id / "customer_onboarding_request_v1.json"
    context = _reviewed_business_context(settings, business_id)
    request = {"schema_version": GAP_SUPPLEMENT_SCHEMA_VERSION, "intake_type": "gap_supplement",
        "business_id": business_id, "intake_id": intake_id, "customer_name": original["customer_name"],
        "industry": original.get("industry") or "", "gap_answers": [{"target_gap": "additional_materials", "raw_answer": materials}],
        "supplement_purpose": "saved_source_extraction_recovery", "reviewed_context": context,
        "created_by": {"user_id": created_by_user_id, "phone": created_by_phone}, "created_at": now_iso(),
        "source_lineage": {"operation": "saved_source_recovery", "source_intake_id": source_intake_id,
            "source_raw_sha256": source_raw_sha, "source_raw_answers_sha256": intake["raw_input_contract"]["raw_answers_sha256"],
            "source_projection_sha256": projection_sha, "recovery_targets": targets,
            "execution_identity": execution_identity, "recovery_identity": identity,
            "already_reviewed_fields": sorted(context), "old_human_decisions_preserved": True,
            "customer_submitted_new_materials": False},
        "authority": {"human_review_required": True, "approved_truth_changed": False,
            "existing_candidates_replaced": False, "speaker_discovery_requested": False}}
    _write_json_atomic(path, request)
    return {"replayed": False, "business_id": business_id, "intake_id": intake_id,
        "customer_name": request["customer_name"], "industry": request["industry"], "request_path": str(path.resolve())}


def prepare_customer_reanalysis_request(
    settings: Settings,
    *,
    business_id: str,
    customer_name: str,
    industry: str,
    materials: str,
) -> dict[str, Any]:
    if not BUSINESS_ID_RE.fullmatch(business_id):
        raise CanonicalOperationError(
            "INVALID_BUSINESS_ID",
            "客户引用格式无效。",
            "请返回客户列表重新选择。",
        )

    customer_name = customer_name.strip()
    industry = (industry or "").strip()
    materials = materials.strip()

    if not customer_name:
        raise CanonicalOperationError(
            "CUSTOMER_NAME_REQUIRED",
            "请输入客户名称。",
            "填写客户名称后重新提交。",
        )

    if not materials:
        raise CanonicalOperationError(
            "CUSTOMER_MATERIALS_REQUIRED",
            "请粘贴现有客户资料。",
            "填写已有资料后重新提交。",
        )

    if len(materials) > 50000:
        raise CanonicalOperationError(
            "CUSTOMER_MATERIALS_TOO_LONG",
            "本次客户资料过长。",
            "请把资料精简到 50000 字以内。",
        )

    projection = _customer_projection(
        settings,
        business_id,
    )

    if projection["status"] not in {
        "analysis_pending",
        "draft",
        "needs_more_info",
    }:
        raise CanonicalOperationError(
            "CUSTOMER_REANALYSIS_NOT_ALLOWED",
            "当前客户已经进入后续审核阶段。",
            "请继续当前审核流程，不要重新覆盖录入资料。",
        )

    latest = get_customer_input(
        settings,
        business_id,
    )

    if (
        latest["customer_name"] == customer_name
        and latest["industry"] == industry
        and latest["materials"] == materials
    ):
        return {
            **latest,
            "duplicate": True,
            "same_input": True,
        }

    root = settings.pipeline_root / "data" / "customer_intakes" / business_id

    numbers: list[int] = []

    for directory in root.glob("intake_*"):
        match = re.fullmatch(
            r"intake_(\d{4})",
            directory.name,
        )

        if match:
            numbers.append(int(match.group(1)))

    next_number = max(numbers, default=0) + 1

    intake_id = f"intake_{next_number:04d}"

    intake_root = root / intake_id

    request_path = intake_root / "customer_onboarding_request_v1.json"

    request = {
        "schema_version": (REQUEST_SCHEMA_VERSION),
        "business_id": business_id,
        "intake_id": intake_id,
        "customer_name": customer_name,
        "industry": industry,
        "materials": materials,
        "created_at": now_iso(),
        "supersedes_intake_id": (latest["intake_id"]),
        "authority": {
            "ui_request_is_customer_truth": False,
            "raw_materials_remain_local": True,
            "canonical_analysis_required": True,
            "previous_intake_preserved": True,
        },
    }

    _write_json_atomic(
        request_path,
        request,
    )

    return {
        "duplicate": False,
        "business_id": business_id,
        "intake_id": intake_id,
        "customer_name": customer_name,
        "industry": industry,
        "request_path": str(request_path.resolve()),
    }


def prepare_customer_onboarding_request(
    settings: Settings,
    *,
    customer_name: str,
    industry: str | None,
    materials: str,
    save_only: bool = False,
    create_separate: bool = False,
    submission_key: str | None = None,
    created_by_user_id: int | None = None,
    created_by_phone: str | None = None,
) -> dict[str, Any]:
    if create_separate and not submission_key:
        raise CanonicalOperationError("CUSTOMER_SUBMISSION_KEY_REQUIRED", "请确认是否为不同客户。", "请刷新添加页面后重新确认，已有客户不会被修改。")
    customer_name = customer_name.strip()
    industry = (industry or "").strip()
    materials = materials.strip()

    if not customer_name:
        raise CanonicalOperationError(
            "CUSTOMER_NAME_REQUIRED",
            "请输入客户名称。",
            "填写客户名称后重新提交。",
        )

    if not materials and not save_only:
        raise CanonicalOperationError(
            "CUSTOMER_MATERIALS_REQUIRED",
            "请粘贴现有客户资料。",
            "把已经知道的客户情况粘贴进来后重新提交。",
        )

    if len(materials) > 50000:
        raise CanonicalOperationError(
            "CUSTOMER_MATERIALS_TOO_LONG",
            "本次客户资料过长。",
            "请把资料精简到 50000 字以内后重新提交。",
        )

    normalized_name = _normalize_name(customer_name)

    # ---------------------------------------------------------
    # Existing customer duplicate guard
    #
    # Same customer name must never silently create a second
    # customer or reuse different raw materials.
    # ---------------------------------------------------------

    if submission_key:
        for path in (settings.pipeline_root / "data/customer_intakes").glob("*/intake_0001/customer_onboarding_request_v1.json"):
            previous = _read_json(path)
            if previous.get("submission_key") == submission_key:
                if previous.get("customer_name") != customer_name or previous.get("materials") != materials:
                    raise CanonicalOperationError("CUSTOMER_SUBMISSION_CONFLICT", "这次保存内容已变化。", "请打开已保存的客户继续填写。")
                return {"duplicate": True, "business_id": previous["business_id"], "intake_id": "intake_0001",
                    "request_path": str(path.resolve()), "same_input": True,
                    "saved_only": previous.get("save_only", False),
                    "existing_customer": _customer_projection(settings, previous["business_id"])}

    for customer in list_customers(settings):
        if create_separate or _normalize_name(customer["display_name"]) != normalized_name:
            continue

        existing_business_id = customer["business_id"]

        result: dict[str, Any] = {
            "duplicate": True,
            "existing_customer_check_required": True,
            "business_id": (existing_business_id),
            "existing_customer": (customer),
        }

        try:
            existing_input = get_customer_input(
                settings,
                existing_business_id,
            )
        except CanonicalOperationError:
            return result

        same_input = (
            existing_input["customer_name"] == customer_name
            and existing_input["industry"] == industry
            and existing_input["materials"] == materials
        )

        result["input_differs"] = not same_input

        if same_input:
            result.update(
                {
                    "intake_id": (existing_input["intake_id"]),
                    "request_path": (existing_input["request_path"]),
                }
            )

        return result

    # ---------------------------------------------------------
    # New customer identity
    # ---------------------------------------------------------

    business_id = _machine_business_id(
        customer_name,
        industry,
    )

    intake_id = "intake_0001"

    intake_root = (
        settings.pipeline_root / "data" / "customer_intakes" / business_id / intake_id
    )

    request_path = intake_root / "customer_onboarding_request_v1.json"

    # ---------------------------------------------------------
    # Recover an already-created immutable initial request.
    # ---------------------------------------------------------

    if request_path.is_file():
        existing = _read_json(request_path)

        same = (
            existing.get("business_id") == business_id
            and existing.get("intake_id") == intake_id
            and existing.get("customer_name") == customer_name
            and existing.get("industry") == industry
            and existing.get("materials") == materials
        )

        if not same:
            raise CanonicalOperationError(
                "CUSTOMER_INTAKE_CONFLICT",
                ("这个客户已经存在一份不同的" "首次录入资料。"),
                ("请打开现有客户继续处理，" "不要覆盖首次录入。"),
            )

        return {
            "duplicate": True,
            "same_input": True,
            "business_id": (business_id),
            "intake_id": (intake_id),
            "request_path": str(request_path.resolve()),
            "existing_customer": (
                _customer_projection(
                    settings,
                    business_id,
                )
            ),
        }

    # ---------------------------------------------------------
    # New immutable Customer Onboarding Request
    # ---------------------------------------------------------

    request = {
        "schema_version": (REQUEST_SCHEMA_VERSION),
        "business_id": (business_id),
        "intake_id": (intake_id),
        "customer_name": (customer_name),
        "industry": (industry),
        "materials": (materials),
        "save_only": save_only,
        "submission_key": submission_key,
        "created_by": {"user_id": created_by_user_id, "phone": created_by_phone},
        "created_at": (now_iso()),
        "authority": {
            "ui_request_is_customer_truth": (False),
            "raw_materials_remain_local": (True),
            "canonical_analysis_required": (True),
        },
    }

    _write_json_atomic(
        request_path,
        request,
    )

    return {
        "duplicate": False,
        "saved_only": save_only,
        "business_id": (business_id),
        "intake_id": (intake_id),
        "customer_name": (customer_name),
        "industry": (industry),
        "request_path": str(request_path.resolve()),
    }


def _pipeline_python(
    settings: Settings,
) -> str:
    return settings.pipeline_python_executable or settings.python_executable


def _run_json_command(
    settings: Settings,
    command: list[str],
    *,
    timeout: int = 180,
) -> dict[str, Any]:
    env = pipeline_subprocess_env(needs_deepseek=False)

    try:
        result = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "CUSTOMER_OPERATION_UNAVAILABLE",
            "客户操作暂时无法完成。",
            "请稍后重试；不要手动修改 Authority artifact。",
        ) from exc

    parsed: dict[str, Any] | None = None

    for line in reversed(result.stdout.splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(
            candidate,
            dict,
        ):
            parsed = candidate
            break

    if result.returncode != 0:
        code = str((parsed or {}).get("code") or ("CUSTOMER_OPERATION_" "FAILED"))

        if code == "SCALAR_FACT_CONFLICT":
            raise CanonicalOperationError(
                code,
                "新增资料与已确认的信息存在冲突，原档案仍然保留。",
                "请核对来源并修改或不采用本次冲突项。实质更正须另行审核，不能覆盖已批准事实。",
            )

        raise CanonicalOperationError(
            code,
            "客户操作没有完成。",
            "请检查当前客户状态后重新处理。",
        )

    if parsed is None:
        raise CanonicalOperationError(
            "CUSTOMER_OPERATION_INVALID_OUTPUT",
            "客户操作返回了无效结果。",
            "请检查 canonical operation 后重试。",
        )

    return parsed


def record_speaker_discovery_intent(
    settings: Settings,
    *,
    business_id: str,
    decisions: list[dict[str, Any]],
    confirmed_by_user_id: int,
    confirmed_by_phone: str,
) -> None:
    """Persist selection before releasing the Customer review lock.

    This is recoverable intake intent, never Speaker Truth or approval.
    A pre-existing result belongs to its original attempt and is not rewritten.
    """
    root = _latest_intake_dir(settings, business_id)
    if root is None or not decisions:
        return
    path = root / "speaker_discovery_confirmation_v1.json"
    if not path.exists():
        _write_json_atomic(
            path,
            {
                "business_id": business_id,
                "intake_id": root.name,
                "status": "pending",
                "retry_required": True,
                "decisions": decisions,
                "drafts": [],
                "confirmed_by_user_id": int(confirmed_by_user_id),
                "confirmed_by_phone": str(confirmed_by_phone),
                "confirmed_at": now_iso(),
            },
        )


def confirm_speaker_discovery(
    settings: Settings,
    *,
    business_id: str,
    decisions: list[dict[str, Any]],
    confirmed_by_user_id: int,
    confirmed_by_phone: str,
) -> dict[str, Any]:
    intake_dir = _latest_intake_dir(
        settings,
        business_id,
    )
    if intake_dir is None:
        raise CanonicalOperationError(
            "CUSTOMER_INTAKE_NOT_FOUND",
            "没有找到客户录入资料。",
            "客户信息已保留，请刷新后重试。",
        )
    discovery_path = _speaker_discovery_path(intake_dir)
    confirmation_path = intake_dir / "speaker_discovery_confirmation_v1.json"
    previous = _read_json(confirmation_path) if confirmation_path.is_file() else {}
    if not discovery_path.is_file():
        return {
            "schema_version": "speaker-discovery-confirmation-v1.0",
            "business_id": business_id,
            "intake_id": intake_dir.name,
            "status": "not_available",
            "decisions": [],
            "drafts": [],
        }

    artifact = _read_json(discovery_path)
    candidates = {
        str(item.get("candidate_id") or ""): item
        for item in artifact.get("speaker_candidates") or []
        if isinstance(item, dict) and item.get("candidate_id")
    }
    requested = {
        str(item.get("candidate_id") or ""): item
        for item in decisions
        if isinstance(item, dict) and item.get("candidate_id")
    }
    if set(requested) - set(candidates):
        raise CanonicalOperationError(
            "SPEAKER_CANDIDATE_NOT_FOUND", "人物候选已变化。", "请刷新客户资料后继续。"
        )
    prior_decisions = {
        item["candidate_id"]: item for item in previous.get("decisions", [])
    }
    if not requested and prior_decisions:
        requested = prior_decisions
    if (
        previous.get("status") == "completed"
        and not previous.get("retry_required")
        and all(
            all(
                item.get(key)
                == requested.get(item["candidate_id"], {}).get(key, item.get(key))
                for key in ("selected", "speaker_name", "public_role", "speaker_type")
            )
            for item in previous.get("decisions", [])
        )
    ):
        return previous
    attempts_root = intake_dir / "speaker_discovery_confirmation_attempts"
    attempt_number = len(list(attempts_root.glob("attempt_*.json"))) + 1
    intent = {
        "business_id": business_id,
        "intake_id": intake_dir.name,
        "status": "pending",
        "retry_required": True,
        "decisions": list(requested.values()),
        "drafts": [],
        "confirmed_by_user_id": int(confirmed_by_user_id),
        "confirmed_by_phone": str(confirmed_by_phone),
        "confirmed_at": now_iso(),
    }
    # Immutable intent precedes Draft creation; recovery never resubmits facts.
    _write_json_atomic(attempts_root / f"attempt_{attempt_number:04d}.json", intent)
    _write_json_atomic(confirmation_path, intent)
    timestamp = now_iso()
    normalized_decisions: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    allowed_types = {
        "owner_founder",
        "frontline_expert",
        "brand",
        "generic",
    }

    for candidate_id, candidate in candidates.items():
        decision = requested.get(candidate_id) or {}
        selected = decision.get("selected") is True
        speaker_name = str(
            decision.get("speaker_name") or candidate.get("name") or ""
        ).strip()
        public_role = str(
            decision.get("public_role") or candidate.get("public_role") or ""
        ).strip()
        speaker_type = str(decision.get("speaker_type") or candidate.get("speaker_type_hint") or "").strip()
        outcome = "not_selected"
        draft_ref = None

        prior = prior_decisions.get(candidate_id, {})
        if prior.get("outcome") in {"draft_created", "existing_speaker"}:
            normalized_decisions.append(prior)
            drafts.append(
                {
                    "candidate_id": candidate_id,
                    "speaker_id": prior["speaker_id"],
                    "outcome": prior["outcome"],
                }
            )
            continue
        if selected and (
            not speaker_name
            or not public_role
            or len(speaker_name) > 200
            or len(public_role) > 200
            or speaker_type not in allowed_types
        ):
            outcome = "identity_required"
        elif selected:
            try:
                prepared = prepare_discovered_speaker_draft(
                    settings,
                    business_id=business_id,
                    customer_intake_id=intake_dir.name,
                    candidate=candidate,
                    speaker_name=speaker_name,
                    public_role=public_role,
                    speaker_type=speaker_type,
                    confirmed_by_user_id=confirmed_by_user_id,
                    confirmed_by_phone=confirmed_by_phone,
                    confirmed_at=timestamp,
                )
                outcome = "existing_speaker" if prepared.get("duplicate") else "draft_created"
                draft_ref = prepared.get("speaker_id")
                drafts.append(
                    {
                        "candidate_id": candidate_id,
                        "speaker_id": prepared.get("speaker_id"),
                        "outcome": outcome,
                    }
                )
            except (CanonicalOperationError, OSError) as exc:
                outcome = "draft_creation_failed"
                drafts.append(
                    {
                        "candidate_id": candidate_id,
                        "speaker_id": None,
                        "outcome": outcome,
                        "error_code": getattr(exc, "code", "SPEAKER_DRAFT_UNAVAILABLE"),
                    }
                )

        normalized_decisions.append(
            {
                "candidate_id": candidate_id,
                "selected": selected,
                "speaker_name": speaker_name or None,
                "public_role": public_role or None,
                "speaker_type": speaker_type or None,
                "outcome": outcome,
                "speaker_id": draft_ref,
            }
        )

    confirmation = {
        "schema_version": "speaker-discovery-confirmation-v1.0",
        "business_id": business_id,
        "intake_id": intake_dir.name,
        "status": "completed",
        "confirmed_by_user_id": int(confirmed_by_user_id),
        "confirmed_by_phone": str(confirmed_by_phone),
        "confirmed_at": timestamp,
        "decisions": normalized_decisions,
        "retry_required": any(
            item["outcome"] in {"identity_required", "draft_creation_failed"}
            for item in normalized_decisions
        ),
        "drafts": drafts,
        "source": {
            "speaker_discovery_candidates_ref": str(discovery_path.resolve()),
        },
        "authority": {
            "human_confirmation_required": True,
            "discovery_is_speaker_truth": False,
            "speaker_draft_is_speaker_persona": False,
            "production_consumption_allowed": False,
        },
    }
    _write_json_atomic(confirmation_path, confirmation)
    return confirmation


def review_customer_facts(
    settings: Settings,
    *,
    business_id: str,
    decisions: list[dict[str, Any]],
    reviewer: str,
    note: str,
    industry_review: dict[str, Any] | None = None,
    constraint_decisions: list[dict[str, Any]] | None = None,
    submission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    intake_dir = _latest_intake_dir(
        settings,
        business_id,
    )

    if intake_dir is None:
        raise CanonicalOperationError(
            "CUSTOMER_INTAKE_NOT_FOUND",
            "没有找到这个客户的首次录入。",
            "请先完成客户信息分析。",
        )

    intake_id = intake_dir.name

    request = {
        "business_id": business_id,
        "intake_id": intake_id,
        "reviewer": reviewer,
        "note": note,
        "decisions": decisions,
    }
    if submission:
        request.update(submission)

    if industry_review is not None:
        request["industry_review"] = industry_review
    if constraint_decisions or submission:
        request["constraint_decisions"] = constraint_decisions
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(
                request,
                handle,
                ensure_ascii=False,
                indent=2,
            )

            temporary_path = Path(handle.name)

        command = [
            _pipeline_python(settings),
            str(settings.pipeline_root / "scripts" / ("customer_fact_" "review_v1.py")),
            "--review",
            str(temporary_path),
            "--pipeline-root",
            str(settings.pipeline_root),
        ]

        return _run_json_command(
            settings,
            command,
        )

    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def recheck_customer_readiness(
    settings: Settings,
    *,
    business_id: str,
) -> dict[str, Any]:
    """Re-evaluate a legacy blocked review without changing Human decisions."""

    intake_dir = _latest_intake_dir(settings, business_id)
    if intake_dir is None:
        raise CanonicalOperationError(
            "CUSTOMER_INTAKE_NOT_FOUND",
            "没有找到这个客户的首次录入。",
            "请先完成客户信息分析。",
        )
    review_path = intake_dir / "customer_fact_review_v1.json"
    if not review_path.is_file():
        raise CanonicalOperationError(
            "CUSTOMER_FACT_REVIEW_NOT_FOUND",
            "还没有可重新检查的客户信息。",
            "请先完成客户信息确认。",
        )
    review = _read_json(review_path)
    if review.get("status") != "completed_persona_blocked":
        raise CanonicalOperationError(
            "CUSTOMER_READINESS_RECHECK_NOT_REQUIRED",
            "当前客户不需要重新检查已有资料。",
            "请刷新客户详情并按当前状态继续。",
        )
    return review_customer_facts(
        settings,
        business_id=business_id,
        decisions=copy.deepcopy(review.get("decisions") or []),
        reviewer=str(review.get("reviewer") or ""),
        note=str(review.get("note") or ""),
    )


def approve_business_persona(
    settings: Settings,
    *,
    business_id: str,
    reviewer: str,
    note: str,
) -> dict[str, Any]:
    authority = resolve_persona_authority(
        settings,
        business_id,
        "business",
    )
    if authority.review_candidate is None:
        if authority.current is not None:
            return get_customer_detail(
                settings,
                business_id,
            )
        raise CanonicalOperationError(
            "BUSINESS_PERSONA_NOT_FOUND",
            "还没有可审核的客户档案。",
            "请先完成客户事实审核。",
        )
    persona_path = authority.review_candidate["path"]
    persona = authority.review_candidate["artifact"]
    lifecycle = persona.get("lifecycle") or {}

    if (
        lifecycle.get("status") != "review_required"
        or lifecycle.get("approved") is not False
    ):
        raise CanonicalOperationError(
            "BUSINESS_PERSONA_NOT_REVIEWABLE",
            "当前客户档案不处于可审核状态。",
            "请刷新客户详情后重新确认当前状态。",
        )

    command = [
        _pipeline_python(settings),
        str(settings.pipeline_root / "scripts" / "approve_persona_v1.py"),
        "--persona",
        str(persona_path.resolve()),
        "--reviewer",
        reviewer,
        "--note",
        (
            note.strip()
            or ("Internal Console Human Review " "approved the Business Persona.")
        ),
    ]

    env = pipeline_subprocess_env(needs_deepseek=False)

    try:
        result = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            env=env,
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "PERSONA_APPROVAL_UNAVAILABLE",
            "客户档案审核暂时无法完成。",
            "请稍后重试。",
        ) from exc

    if result.returncode != 0:
        raise CanonicalOperationError(
            "PERSONA_APPROVAL_FAILED",
            "客户档案没有批准成功。",
            "请检查关键事实是否完整，再重新审核。",
        )

    return get_customer_detail(
        settings,
        business_id,
    )
