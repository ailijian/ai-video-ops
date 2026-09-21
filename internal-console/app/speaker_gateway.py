from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .persona_authority import (
    resolve_persona_authority,
    validate_speaker_business_binding,
)
from .subprocess_env import pipeline_subprocess_env

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,127}$")

SPEAKER_TYPES = {
    "owner_founder",
    "frontline_expert",
    "brand",
    "generic",
}

REQUEST_SCHEMA_VERSION = "speaker-onboarding-request-v1.0"

SPEAKER_GAP_QUESTIONS = {
    "public_display_name": {
        "title": "出镜人姓名",
        "question": "这个出镜人应该如何称呼？",
    },
    "public_role": {
        "title": "公开身份",
        "question": "这个人对外是什么身份？",
    },
    "speaker_role_facts": {
        "title": "本人职责与经历",
        "question": "他/她平时具体负责什么？有哪些事情是本人亲自做的或真实经历过的？",
    },
    "first_person_allowed_topics": {
        "title": "可以本人讲的内容",
        "question": "哪些内容适合由他/她本人用第一人称来讲？可以写职责、亲自做过的事情或真实经历。",
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
            "SPEAKER_ARTIFACT_INVALID",
            "出镜人 Authority artifact 无法读取。",
            "请检查出镜人数据后重试。",
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise CanonicalOperationError(
            "SPEAKER_ARTIFACT_INVALID",
            "出镜人 Authority artifact 格式无效。",
            "请检查出镜人数据后重试。",
        )

    return value


def _write_atomic_json(
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


def _normalize_name(
    value: str,
) -> str:
    return re.sub(
        r"\s+",
        "",
        str(value or ""),
    ).casefold()


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


def _known_fact(
    persona: dict[str, Any] | None,
    field: str,
) -> Any:
    if not persona:
        return None

    fact = persona.get("facts", {}).get(field, {})

    if fact.get("state") != "known":
        return None

    return fact.get("value")


def _latest_persona(
    settings: Settings,
    persona_id: str,
) -> (
    tuple[
        Path,
        dict[str, Any],
    ]
    | None
):
    resolved = resolve_persona_authority(
        settings,
        persona_id,
        "speaker",
    )
    projected = resolved.projected
    if projected is None:
        return None
    return projected["path"], projected["artifact"]


def _approved_business_persona(
    settings: Settings,
    business_id: str,
) -> tuple[
    Path,
    dict[str, Any],
]:
    current = resolve_persona_authority(
        settings,
        business_id,
        "business",
    ).current
    if current is not None:
        return current["path"], current["artifact"]

    raise CanonicalOperationError(
        "APPROVED_BUSINESS_PERSONA_REQUIRED",
        "必须先确认客户档案，才能分析出镜人资料。",
        "已保存的出镜人资料会保留，请先完成客户档案确认。",
    )


def _latest_intake_dir(
    settings: Settings,
    business_id: str,
    speaker_id: str,
) -> Path | None:
    root = (
        settings.pipeline_root / "data" / "speaker_intakes" / business_id / speaker_id
    )

    if not root.exists():
        return None

    values = sorted(
        (path for path in root.iterdir() if path.is_dir()),
        reverse=True,
    )

    return values[0] if values else None


def _speaker_request(
    intake_dir: Path | None,
) -> dict[str, Any]:
    if intake_dir is None:
        return {}

    path = intake_dir / "speaker_onboarding_request_v1.json"

    if not path.is_file():
        return {}

    return _read_json(path)


def _project_persona(
    path: Path,
    persona: dict[str, Any],
) -> dict[str, Any]:
    lifecycle = persona.get("lifecycle") or {}

    facts = []

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
        "speaker_type": (persona.get("speaker_type")),
        "status": (lifecycle.get("status")),
        "approved": (lifecycle.get("approved") is True),
        "approved_at": (lifecycle.get("approved_at")),
        "facts": facts,
        "path": str(path.resolve()),
    }


def _candidate_projection(
    item: dict[str, Any],
) -> dict[str, Any]:
    excerpt = str(item.get("source_excerpt") or "")

    if len(excerpt) > 600:
        excerpt = excerpt[:599] + "…"

    return {
        "candidate_id": (item.get("fact_candidate_id")),
        "field": (item.get("target_field")),
        "state": (item.get("candidate_state")),
        "value": (item.get("normalized_value")),
        "source_excerpt": (excerpt),
        "review_note": (item.get("review_note")),
        "human_review": (item.get("human_review")),
    }


def _speaker_projection(
    settings: Settings,
    business_id: str,
    speaker_id: str,
) -> dict[str, Any]:
    intake_dir = _latest_intake_dir(
        settings,
        business_id,
        speaker_id,
    )

    request = _speaker_request(intake_dir)
    handoff: dict[str, Any] = {}
    if intake_dir is not None:
        handoff_path = intake_dir / "speaker_auto_handoff_v1.json"
        if handoff_path.is_file():
            handoff = _read_json(handoff_path)

    business_authority = resolve_persona_authority(
        settings,
        business_id,
        "business",
    ).current
    persona_authority = resolve_persona_authority(
        settings,
        speaker_id,
        "speaker",
    )
    persona_entry = persona_authority.projected

    persona_path = None
    persona = None

    if persona_entry:
        persona_path = persona_entry["path"]
        persona = persona_entry["artifact"]

        reference = persona.get("business_persona_ref") or {}

        if (
            persona.get("persona_scope") != "speaker"
            or reference.get("persona_id") != business_id
        ):
            raise CanonicalOperationError(
                "SPEAKER_BUSINESS_LINEAGE_MISMATCH",
                "出镜人 Persona 与当前客户不匹配。",
                "请返回客户详情重新选择，或修复 Persona lineage。",
            )
        elif business_authority is None:
            raise CanonicalOperationError(
                "APPROVED_BUSINESS_PERSONA_REQUIRED",
                "必须先批准客户档案，才能读取出镜人 Authority。",
                "请先完成 Business Persona 审核。",
            )
        else:
            validate_speaker_business_binding(
                persona_entry,
                business_authority,
            )

    speaker_name = (
        _known_fact(
            persona,
            "public_display_name",
        )
        or request.get("speaker_name")
        or speaker_id
    )

    public_role = (
        _known_fact(
            persona,
            "public_role",
        )
        or request.get("public_role")
        or "身份待确认"
    )

    speaker_type = (
        (persona or {}).get("speaker_type") or request.get("speaker_type") or "generic"
    )

    status = "draft"

    review = None

    if intake_dir:
        candidate_path = intake_dir / ("speaker_fact_" "candidates_v1.json")

        review_path = intake_dir / ("speaker_fact_" "review_v1.json")

        if review_path.is_file():
            review = _read_json(review_path)

        review_status = str((review or {}).get("status") or "")

        if candidate_path.is_file() and not review_status.startswith("completed_"):
            status = "fact_review_required"

        elif review_status == ("completed_" "persona_blocked"):
            status = "needs_more_info"

    if persona:
        lifecycle = persona.get("lifecycle") or {}

        if lifecycle.get("status") == "review_required":
            status = "persona_review_required"

        elif (
            lifecycle.get("status") == "approved" and lifecycle.get("approved") is True
        ):
            status = "approved"

    elif request and status == "draft":
        status = (
            "analysis_pending"
            if business_authority is not None
            else "pending_customer_profile"
        )

    return {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "display_name": str(speaker_name),
        "public_role": str(public_role),
        "speaker_type": str(speaker_type),
        "status": status,
        "latest_intake_id": (request.get("intake_id")),
        "latest_intake_type": request.get("intake_type") or "initial_onboarding",
        "source_type": request.get("source_type")
        or "internal_console_speaker_materials",
        "human_confirmed_discovery": bool(
            request.get("human_confirmed_identity")
            and request.get("source_type")
            == "customer_intake_speaker_discovery"
        ),
        "auto_handoff_status": handoff.get("status"),
        "speaker_persona": (
            _project_persona(
                persona_path,
                persona,
            )
            if (persona_path and persona)
            else None
        ),
        "media_rights": {
            "established": False,
            "authority_managed_by_speaker_persona": (False),
        },
    }


def list_speakers(
    settings: Settings,
    business_id: str,
) -> list[dict[str, Any]]:
    speaker_ids: set[str] = set()

    intake_root = settings.pipeline_root / "data" / "speaker_intakes" / business_id

    if intake_root.exists():
        for directory in (path for path in (intake_root.iterdir()) if path.is_dir()):
            if ID_RE.fullmatch(directory.name):
                speaker_ids.add(directory.name)

    persona_root = settings.pipeline_root / "data" / "personas"

    if persona_root.exists():
        for directory in (path for path in (persona_root.iterdir()) if path.is_dir()):
            paths = list(directory.glob("revision_*/persona_v1.json"))
            if not paths:
                continue
            personas = [_read_json(path) for path in paths]
            if any(
                persona.get("persona_scope") == "speaker"
                and (persona.get("business_persona_ref") or {}).get("persona_id")
                == business_id
                for persona in personas
            ):
                speaker_ids.add(directory.name)

    values = [
        _speaker_projection(
            settings,
            business_id,
            speaker_id,
        )
        for speaker_id in sorted(speaker_ids)
    ]

    values.sort(
        key=lambda item: (
            item["status"] != "fact_review_required",
            item["status"] != "persona_review_required",
            item["display_name"],
        )
    )

    return values


def speaker_attention_count(
    settings: Settings,
) -> int:
    root = settings.pipeline_root / "data" / "speaker_intakes"

    if not root.exists():
        return 0

    count = 0

    for business_dir in (path for path in root.iterdir() if path.is_dir()):
        try:
            speakers = list_speakers(
                settings,
                business_dir.name,
            )
        except CanonicalOperationError:
            continue

        count += sum(
            item["status"]
            in {
                "fact_review_required",
                "persona_review_required",
            }
            or item.get("auto_handoff_status") == "retry_required"
            for item in speakers
        )

    return count


def get_speaker_detail(
    settings: Settings,
    business_id: str,
    speaker_id: str,
) -> dict[str, Any]:
    if not ID_RE.fullmatch(business_id):
        raise CanonicalOperationError(
            "INVALID_BUSINESS_ID",
            "客户引用格式无效。",
            "请返回客户详情重新选择。",
        )

    if not ID_RE.fullmatch(speaker_id):
        raise CanonicalOperationError(
            "INVALID_SPEAKER_ID",
            "出镜人引用格式无效。",
            "请返回客户详情重新选择。",
        )

    intake_dir = _latest_intake_dir(
        settings,
        business_id,
        speaker_id,
    )

    persona_entry = _latest_persona(
        settings,
        speaker_id,
    )

    if intake_dir is None and persona_entry is None:
        raise CanonicalOperationError(
            "SPEAKER_NOT_FOUND",
            "没有找到这个出镜人。",
            "请返回客户详情重新选择。",
        )

    detail = _speaker_projection(
        settings,
        business_id,
        speaker_id,
    )

    candidates = []
    reviewed = []
    review = None

    if intake_dir:
        candidates_path = intake_dir / ("speaker_fact_" "candidates_v1.json")

        if candidates_path.is_file():
            artifact = _read_json(candidates_path)

            candidates = [
                _candidate_projection(item)
                for item in (artifact.get("fact_candidates") or [])
                if isinstance(
                    item,
                    dict,
                )
            ]

        reviewed_path = intake_dir / ("reviewed_speaker_" "fact_candidates_v1.json")

        if reviewed_path.is_file():
            artifact = _read_json(reviewed_path)

            reviewed = [
                _candidate_projection(item)
                for item in (artifact.get("fact_candidates") or [])
                if isinstance(
                    item,
                    dict,
                )
            ]

        review_path = intake_dir / ("speaker_fact_" "review_v1.json")

        if review_path.is_file():
            review = _read_json(review_path)

    raw_blockers = list((review or {}).get("speaker_persona_blockers") or [])
    can_recheck_existing = detail["status"] == "needs_more_info" and bool(
        raw_blockers
    ) and set(raw_blockers) == {"first_person_forbidden_claims"}
    readiness_gaps = [
        {"field": field, **SPEAKER_GAP_QUESTIONS[field]}
        for field in raw_blockers
        if field in SPEAKER_GAP_QUESTIONS
    ]

    next_action = {
        "analysis_pending": ("WAIT_FOR_SPEAKER_ANALYSIS"),
        "fact_review_required": ("REVIEW_SPEAKER_FACTS"),
        "needs_more_info": ("COLLECT_MORE_SPEAKER_TRUTH"),
        "persona_review_required": ("REVIEW_SPEAKER_PERSONA"),
        "approved": ("SPEAKER_PERSONA_READY"),
    }.get(
        detail["status"],
        "NONE",
    )

    return {
        **detail,
        "fact_candidates": (candidates),
        "reviewed_fact_candidates": (reviewed),
        "fact_review": review,
        "readiness_gaps": readiness_gaps,
        "can_recheck_existing": can_recheck_existing,
        "next_action": (next_action),
        "authority": {
            "raw_input_is_speaker_persona": (False),
            "fact_candidate_is_speaker_truth": (False),
            "fact_review_is_persona_approval": (False),
            "business_fact_is_speaker_first_person_fact": (False),
            "speaker_persona_is_media_rights": (False),
        },
    }


def prepare_speaker_onboarding_request(
    settings: Settings,
    *,
    business_id: str,
    speaker_name: str,
    public_role: str,
    speaker_type: str,
    materials: str,
    forbidden_claims: list[str],
    source_type: str = "internal_console_speaker_materials",
    source_lineage: dict[str, Any] | None = None,
    human_confirmed_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    business_entry = resolve_persona_authority(
        settings,
        business_id,
        "business",
    ).current
    business_path = business_entry["path"] if business_entry is not None else None
    business = business_entry["artifact"] if business_entry is not None else None

    speaker_name = speaker_name.strip()
    public_role = public_role.strip()
    speaker_type = speaker_type.strip()
    materials = materials.strip()

    forbidden_claims = [
        str(item).strip() for item in (forbidden_claims or []) if str(item).strip()
    ]
    source_type = str(source_type or "").strip()
    source_lineage = dict(source_lineage or {})
    human_confirmed_identity = dict(human_confirmed_identity or {})

    if not speaker_name:
        raise CanonicalOperationError(
            "SPEAKER_NAME_REQUIRED",
            "请输入出镜人姓名。",
            "填写姓名后重新提交。",
        )

    if not public_role:
        raise CanonicalOperationError(
            "SPEAKER_ROLE_REQUIRED",
            "请输入出镜人的公开身份。",
            "填写公开身份后重新提交。",
        )

    if speaker_type not in SPEAKER_TYPES:
        raise CanonicalOperationError(
            "SPEAKER_TYPE_INVALID",
            "出镜人类型无效。",
            "请重新选择出镜人类型。",
        )

    if not materials:
        raise CanonicalOperationError(
            "SPEAKER_MATERIALS_REQUIRED",
            "请填写已有的出镜人资料。",
            "补充本人经历、职责或可讲内容后重新提交。",
        )

    if len(materials) > 50000:
        raise CanonicalOperationError(
            "SPEAKER_MATERIALS_TOO_LONG",
            "出镜人资料过长。",
            "请将资料精简到 50000 字以内。",
        )

    if source_type not in {
        "internal_console_speaker_materials",
        "customer_intake_speaker_discovery",
    }:
        raise CanonicalOperationError(
            "SPEAKER_SOURCE_TYPE_INVALID",
            "出镜人资料来源无效。",
            "请返回客户详情后重新操作。",
        )

    for existing in list_speakers(
        settings,
        business_id,
    ):
        if _normalize_name(existing["display_name"]) == _normalize_name(
            speaker_name
        ) and _normalize_name(existing["public_role"]) == _normalize_name(public_role):
            intake_dir = _latest_intake_dir(
                settings,
                business_id,
                existing["speaker_id"],
            )

            request = _speaker_request(intake_dir)

            result = {
                "duplicate": True,
                "business_id": (business_id),
                "speaker_id": (existing["speaker_id"]),
                "existing_speaker": (existing),
            }

            if request:
                same = (
                    request.get("speaker_name") == speaker_name
                    and request.get("public_role") == public_role
                    and request.get("speaker_type") == speaker_type
                    and request.get("materials") == materials
                    and request.get("forbidden_claims") == forbidden_claims
                    and request.get(
                        "source_type", "internal_console_speaker_materials"
                    )
                    == source_type
                )

                result["input_differs"] = not same

                if same:
                    result.update(
                        {
                            "intake_id": (request["intake_id"]),
                            "request_path": (
                                str(
                                    (
                                        intake_dir
                                        / ("speaker_onboarding_" "request_v1.json")
                                    ).resolve()
                                )
                            ),
                        }
                    )

            return result

    speaker_id = machine_speaker_id(
        business_id,
        speaker_name,
        public_role,
    )

    intake_id = "intake_0001"

    root = (
        settings.pipeline_root
        / "data"
        / "speaker_intakes"
        / business_id
        / speaker_id
        / intake_id
    )

    request_path = root / ("speaker_onboarding_" "request_v1.json")

    if request_path.is_file():
        existing = _read_json(request_path)

        same = (
            existing.get("speaker_name") == speaker_name
            and existing.get("public_role") == public_role
            and existing.get("speaker_type") == speaker_type
            and existing.get("materials") == materials
            and existing.get("forbidden_claims") == forbidden_claims
            and existing.get(
                "source_type", "internal_console_speaker_materials"
            )
            == source_type
        )

        if not same:
            raise CanonicalOperationError(
                "SPEAKER_INTAKE_CONFLICT",
                "这个出镜人已经存在一份不同的首次录入资料。",
                "请打开现有出镜人继续处理，不要覆盖首次录入。",
            )

        return {
            "duplicate": True,
            "business_id": (business_id),
            "speaker_id": (speaker_id),
            "intake_id": (intake_id),
            "request_path": str(request_path.resolve()),
            "existing_speaker": (
                _speaker_projection(
                    settings,
                    business_id,
                    speaker_id,
                )
            ),
        }

    request: dict[str, Any] = {
        "schema_version": (REQUEST_SCHEMA_VERSION),
        "business_id": (business_id),
        "speaker_id": (speaker_id),
        "intake_id": (intake_id),
        "speaker_name": (speaker_name),
        "public_role": (public_role),
        "speaker_type": (speaker_type),
        "materials": (materials),
        "forbidden_claims": (forbidden_claims),
        "source_type": source_type,
        "source_lineage": source_lineage,
        "human_confirmed_identity": human_confirmed_identity,
        "created_at": (now_iso()),
        "draft_status": (
            "ready_for_analysis"
            if business is not None
            else "pending_business_persona_approval"
        ),
        "authority": {
            "raw_input_is_speaker_persona": (False),
            "speaker_persona_requires_human_review": (True),
            "business_facts_must_not_be_copied": (True),
            "media_rights_established": (False),
            "speaker_analysis_allowed": business is not None,
            "production_consumption_allowed": False,
        },
    }

    if business is not None and business_path is not None:
        request["business_persona_ref"] = {
            "persona_id": (business.get("persona_id")),
            "revision": (business.get("revision")),
            "path": str(business_path.resolve()),
        }

    _write_atomic_json(
        request_path,
        request,
    )

    return {
        "duplicate": False,
        "draft_saved": business is None,
        "business_id": (business_id),
        "speaker_id": (speaker_id),
        "intake_id": (intake_id),
        "speaker_name": (speaker_name),
        "public_role": (public_role),
        "request_path": str(request_path.resolve()),
    }


def _next_speaker_intake_id(
    settings: Settings,
    business_id: str,
    speaker_id: str,
) -> str:
    root = settings.pipeline_root / "data" / "speaker_intakes" / business_id / speaker_id
    numbers: list[int] = []
    if root.exists():
        for path in root.glob("intake_*"):
            match = re.fullmatch(r"intake_(\d+)", path.name)
            if match and path.is_dir():
                numbers.append(int(match.group(1)))
    return f"intake_{max(numbers, default=0) + 1:04d}"


def prepare_speaker_gap_supplement_request(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    answers: dict[str, str],
    created_by_user_id: int,
    created_by_phone: str,
) -> dict[str, Any]:
    _approved_business_persona(settings, business_id)
    detail = get_speaker_detail(settings, business_id, speaker_id)
    if detail["status"] != "needs_more_info":
        raise CanonicalOperationError(
            "SPEAKER_GAP_SUPPLEMENT_NOT_REQUIRED",
            "当前出镜人不处于待补充状态。",
            "请刷新页面后按当前状态继续。",
        )
    required = [item["field"] for item in detail["readiness_gaps"]]
    normalized = {
        str(field): str(value or "").strip() for field, value in (answers or {}).items()
    }
    if not required or set(normalized) != set(required) or any(
        not normalized[field] for field in required
    ):
        raise CanonicalOperationError(
            "SPEAKER_GAP_ANSWERS_INCOMPLETE",
            "请完成当前缺失的出镜人信息。",
            "只需补充页面列出的内容。",
        )
    intake_root = (
        settings.pipeline_root
        / "data"
        / "speaker_intakes"
        / business_id
        / speaker_id
    )
    previous_refs = [
        str(path.resolve())
        for path in sorted(
            intake_root.glob("intake_*/reviewed_speaker_fact_candidates_v1.json")
        )
    ]
    intake_id = _next_speaker_intake_id(settings, business_id, speaker_id)
    root = intake_root / intake_id
    request_path = root / "speaker_onboarding_request_v1.json"
    created_at = now_iso()
    request = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "business_id": business_id,
        "speaker_id": speaker_id,
        "intake_id": intake_id,
        "intake_type": "gap_supplement",
        "speaker_name": detail["display_name"],
        "public_role": detail["public_role"],
        "speaker_type": detail["speaker_type"],
        "materials": "\n\n".join(
            f"{SPEAKER_GAP_QUESTIONS[field]['title']}：{normalized[field]}"
            for field in required
        ),
        "forbidden_claims": [],
        "target_gaps": required,
        "raw_answers": normalized,
        "source_type": "internal_console_speaker_gap_supplement",
        "source_lineage": {
            "previous_reviewed_fact_refs": previous_refs,
            "previous_human_decisions_preserved": True,
        },
        "previous_reviewed_fact_refs": previous_refs,
        "created_by": {
            "user_id": int(created_by_user_id),
            "phone": str(created_by_phone),
        },
        "human_confirmed_identity": {},
        "created_at": created_at,
        "draft_status": "ready_for_analysis",
        "authority": {
            "supplement_is_speaker_truth": False,
            "human_review_required": True,
            "previous_speaker_facts_preserved": True,
            "business_facts_must_not_be_copied": True,
            "production_consumption_allowed": False,
        },
    }
    _write_atomic_json(request_path, request)
    return {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "intake_id": intake_id,
        "request_path": str(request_path.resolve()),
        "speaker_name": detail["display_name"],
        "public_role": detail["public_role"],
    }


def prepare_discovered_speaker_draft(
    settings: Settings,
    *,
    business_id: str,
    customer_intake_id: str,
    candidate: dict[str, Any],
    speaker_name: str,
    public_role: str,
    speaker_type: str,
    confirmed_by_user_id: int,
    confirmed_by_phone: str,
    confirmed_at: str,
) -> dict[str, Any]:
    intake_root = (
        settings.pipeline_root
        / "data"
        / "customer_intakes"
        / business_id
        / customer_intake_id
    )
    raw_request_path = intake_root / "customer_onboarding_request_v1.json"
    customer_intake_path = intake_root / "customer_intake_v1.json"
    privacy_path = intake_root / "customer_intake_privacy_projection_v1.json"
    discovery_path = intake_root / "speaker_discovery_candidates_v1.json"
    for path in (
        raw_request_path,
        customer_intake_path,
        privacy_path,
        discovery_path,
    ):
        if not path.is_file():
            raise CanonicalOperationError(
                "SPEAKER_DISCOVERY_LINEAGE_MISSING",
                "出镜人候选来源资料不完整。",
                "客户信息已保留，请稍后重试出镜人确认。",
            )

    quotes: list[str] = []
    for field in ("personal_material_quotes", "evidence_quotes"):
        for item in candidate.get(field) or []:
            value = str(item or "").strip()
            if value and value not in quotes:
                quotes.append(value)
    if not quotes:
        raise CanonicalOperationError(
            "SPEAKER_DISCOVERY_EVIDENCE_REQUIRED",
            "这位出镜人没有可追溯的来源依据。",
            "请暂不创建，或从客户详情手工添加出镜人。",
        )

    candidate_id = str(candidate.get("candidate_id") or "")
    source_lineage = {
        "customer_intake_ref": str(customer_intake_path.resolve()),
        "customer_raw_material_ref": str(raw_request_path.resolve()),
        "privacy_projection_ref": str(privacy_path.resolve()),
        "candidate_ref": f"{discovery_path.resolve()}#{candidate_id}",
        "evidence_quotes": list(candidate.get("evidence_quotes") or []),
        "personal_material_quotes": list(
            candidate.get("personal_material_quotes") or []
        ),
        "business_fact_promoted_to_speaker_fact": False,
    }
    confirmation = {
        "candidate_id": candidate_id,
        "speaker_name": speaker_name.strip(),
        "public_role": public_role.strip(),
        "confirmed_by_user_id": int(confirmed_by_user_id),
        "confirmed_by_phone": str(confirmed_by_phone),
        "confirmed_at": confirmed_at,
    }
    return prepare_speaker_onboarding_request(
        settings,
        business_id=business_id,
        speaker_name=speaker_name,
        public_role=public_role,
        speaker_type=speaker_type,
        materials="\n\n".join(quotes),
        forbidden_claims=list(candidate.get("explicit_forbidden_claims") or []),
        source_type="customer_intake_speaker_discovery",
        source_lineage=source_lineage,
        human_confirmed_identity=confirmation,
    )


def record_speaker_auto_handoff_status(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    status: str,
    task_id: str | None = None,
    error_code: str | None = None,
) -> None:
    if status not in {"analysis_pending", "retry_required"}:
        raise ValueError("Unsupported Speaker auto-handoff status.")
    intake_dir = _latest_intake_dir(settings, business_id, speaker_id)
    if intake_dir is None:
        return
    _write_atomic_json(
        intake_dir / "speaker_auto_handoff_v1.json",
        {
            "schema_version": "speaker-auto-handoff-v1.0",
            "business_id": business_id,
            "speaker_id": speaker_id,
            "status": status,
            "task_id": task_id,
            "error_code": error_code,
            "updated_at": now_iso(),
            "authority": {
                "handoff_is_speaker_persona_approval": False,
                "production_consumption_allowed": False,
            },
        },
    )


def prepare_speaker_draft_analysis(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
) -> dict[str, Any]:
    _approved_business_persona(settings, business_id)
    detail = get_speaker_detail(settings, business_id, speaker_id)
    if detail["status"] != "analysis_pending":
        raise CanonicalOperationError(
            "SPEAKER_DRAFT_NOT_READY",
            "当前出镜人资料不处于待分析状态。",
            "请刷新页面后按当前状态继续。",
        )
    intake_dir = _latest_intake_dir(settings, business_id, speaker_id)
    request = _speaker_request(intake_dir)
    if intake_dir is None or not request:
        raise CanonicalOperationError(
            "SPEAKER_INTAKE_NOT_FOUND",
            "没有找到已保存的出镜人资料。",
            "请返回客户详情后重新选择。",
        )
    return {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "intake_id": str(request.get("intake_id") or intake_dir.name),
        "request_path": str(
            (intake_dir / "speaker_onboarding_request_v1.json").resolve()
        ),
        "speaker_name": detail["display_name"],
        "public_role": detail["public_role"],
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
            "SPEAKER_OPERATION_UNAVAILABLE",
            "出镜人操作暂时无法完成。",
            "请稍后重试。",
        ) from exc

    parsed = None

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
        raise CanonicalOperationError(
            str((parsed or {}).get("code") or ("SPEAKER_OPERATION_FAILED")),
            "出镜人操作没有完成。",
            (
                str((parsed or {}).get("message") or "")
                or "请检查当前出镜人状态后重试。"
            ),
        )

    if parsed is None:
        raise CanonicalOperationError(
            "SPEAKER_OPERATION_INVALID_OUTPUT",
            "出镜人操作返回了无效结果。",
            "请检查 canonical operation 后重试。",
        )

    return parsed


def review_speaker_facts(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    decisions: list[dict[str, Any]],
    reviewer: str,
    note: str,
) -> dict[str, Any]:
    intake_dir = _latest_intake_dir(
        settings,
        business_id,
        speaker_id,
    )

    if intake_dir is None:
        raise CanonicalOperationError(
            "SPEAKER_INTAKE_NOT_FOUND",
            "没有找到这个出镜人的首次录入。",
            "请先分析出镜人资料。",
        )

    request = {
        "business_id": (business_id),
        "speaker_id": (speaker_id),
        "intake_id": (intake_dir.name),
        "reviewer": (reviewer),
        "note": note,
        "decisions": (decisions),
    }

    temporary = None

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

            temporary = Path(handle.name)

        command = [
            _pipeline_python(settings),
            str(settings.pipeline_root / "scripts" / ("speaker_fact_" "review_v1.py")),
            "--review",
            str(temporary.resolve()),
            "--pipeline-root",
            str(settings.pipeline_root),
        ]

        return _run_json_command(
            settings,
            command,
        )

    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)


def recheck_speaker_readiness(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    reviewer: str,
) -> dict[str, Any]:
    request = {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "reviewer": reviewer,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(request, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        command = [
            _pipeline_python(settings),
            str(settings.pipeline_root / "scripts" / "speaker_fact_review_v1.py"),
            "--recheck",
            str(temporary.resolve()),
            "--pipeline-root",
            str(settings.pipeline_root),
        ]
        return _run_json_command(settings, command)
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)


def approve_speaker_persona(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    reviewer: str,
    note: str,
) -> dict[str, Any]:
    authority = resolve_persona_authority(
        settings,
        speaker_id,
        "speaker",
    )
    if authority.review_candidate is None:
        if authority.current is not None:
            return get_speaker_detail(
                settings,
                business_id,
                speaker_id,
            )
        raise CanonicalOperationError(
            "SPEAKER_PERSONA_NOT_FOUND",
            "还没有可审核的出镜人档案。",
            "请先完成出镜人事实审核。",
        )
    path = authority.review_candidate["path"]
    persona = authority.review_candidate["artifact"]

    reference = persona.get("business_persona_ref") or {}

    if (
        persona.get("persona_scope") != "speaker"
        or reference.get("persona_id") != business_id
    ):
        raise CanonicalOperationError(
            "SPEAKER_BUSINESS_LINEAGE_MISMATCH",
            "出镜人档案与当前客户不匹配。",
            "请返回客户详情重新选择。",
        )

    business_authority = resolve_persona_authority(
        settings,
        business_id,
        "business",
    ).current
    if business_authority is None:
        raise CanonicalOperationError(
            "APPROVED_BUSINESS_PERSONA_REQUIRED",
            "必须先批准客户档案，才能批准出镜人档案。",
            "请先完成 Business Persona 审核。",
        )
    validate_speaker_business_binding(
        authority.review_candidate,
        business_authority,
    )

    lifecycle = persona.get("lifecycle") or {}

    if (
        lifecycle.get("status") != "review_required"
        or lifecycle.get("approved") is not False
    ):
        raise CanonicalOperationError(
            "SPEAKER_PERSONA_NOT_REVIEWABLE",
            "当前出镜人档案不处于可审核状态。",
            "请刷新页面确认最新状态。",
        )

    command = [
        _pipeline_python(settings),
        str(settings.pipeline_root / "scripts" / "approve_persona_v1.py"),
        "--persona",
        str(path.resolve()),
        "--reviewer",
        reviewer,
        "--note",
        (
            note.strip()
            or ("Internal Console Human Review " "approved the Speaker Persona.")
        ),
    ]

    _run_json_command(
        settings,
        command,
        timeout=120,
    )

    return get_speaker_detail(
        settings,
        business_id,
        speaker_id,
    )
