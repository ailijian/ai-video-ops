from __future__ import annotations

import copy
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

BUSINESS_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,127}$")

REQUEST_SCHEMA_VERSION = "customer-onboarding-request-v1.0"


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
        status = "analysis_pending"

    return {
        "business_id": business_id,
        "display_name": str(display_name),
        "industry": str(industry),
        "status": status,
        "speaker_count": (
            _approved_speaker_count(
                settings,
                business_id,
            )
        ),
        "latest_intake_id": (intake_identity.get("intake_id")),
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

    reviewed_candidates: list[dict[str, Any]] = []

    fact_review: dict[str, Any] | None = None

    if intake_dir:
        candidate_path = intake_dir / ("persona_fact_" "candidates_v1.json")

        if candidate_path.is_file():
            artifact = _read_json(candidate_path)

            candidates = [
                _candidate_projection(item)
                for item in (artifact.get("fact_candidates") or [])
                if isinstance(
                    item,
                    dict,
                )
            ]

        reviewed_path = intake_dir / ("reviewed_persona_" "fact_candidates_v1.json")

        if reviewed_path.is_file():
            artifact = _read_json(reviewed_path)

            reviewed_candidates = [
                _candidate_projection(item)
                for item in (artifact.get("fact_candidates") or [])
                if isinstance(
                    item,
                    dict,
                )
            ]

        review_path = intake_dir / ("customer_fact_" "review_v1.json")

        if review_path.is_file():
            fact_review = _read_json(review_path)

    status = projection["status"]

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

    return {
        **projection,
        "fact_candidates": (candidates),
        "reviewed_fact_candidates": (reviewed_candidates),
        "fact_review": fact_review,
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
    identity = _normalize_name(customer_name) + "|" + _normalize_name(industry)

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]

    return f"customer_{digest}"


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

    intake_dir = _latest_intake_dir(
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
    industry = industry.strip()
    materials = materials.strip()

    if not customer_name:
        raise CanonicalOperationError(
            "CUSTOMER_NAME_REQUIRED",
            "请输入客户名称。",
            "填写客户名称后重新提交。",
        )

    if not industry:
        raise CanonicalOperationError(
            "CUSTOMER_INDUSTRY_REQUIRED",
            "请输入客户行业。",
            "填写行业后重新提交。",
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
    industry: str,
    materials: str,
) -> dict[str, Any]:
    customer_name = customer_name.strip()
    industry = industry.strip()
    materials = materials.strip()

    if not customer_name:
        raise CanonicalOperationError(
            "CUSTOMER_NAME_REQUIRED",
            "请输入客户名称。",
            "填写客户名称后重新提交。",
        )

    if not industry:
        raise CanonicalOperationError(
            "CUSTOMER_INDUSTRY_REQUIRED",
            "请输入客户行业。",
            "填写行业后重新提交。",
        )

    if not materials:
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

    for customer in list_customers(settings):
        if _normalize_name(customer["display_name"]) != normalized_name:
            continue

        existing_business_id = customer["business_id"]

        result: dict[str, Any] = {
            "duplicate": True,
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

        raise CanonicalOperationError(
            code,
            "客户操作没有完成。",
            (
                str((parsed or {}).get("message") or "")
                or ("请检查当前客户状态后重新处理。")
            ),
        )

    if parsed is None:
        raise CanonicalOperationError(
            "CUSTOMER_OPERATION_INVALID_OUTPUT",
            "客户操作返回了无效结果。",
            "请检查 canonical operation 后重试。",
        )

    return parsed


def review_customer_facts(
    settings: Settings,
    *,
    business_id: str,
    decisions: list[dict[str, Any]],
    reviewer: str,
    note: str,
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
