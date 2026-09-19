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
        "必须先批准客户档案，才能添加出镜人。",
        "请先完成 Business Persona 审核。",
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
        status = "analysis_pending"

    return {
        "business_id": business_id,
        "speaker_id": speaker_id,
        "display_name": str(speaker_name),
        "public_role": str(public_role),
        "speaker_type": str(speaker_type),
        "status": status,
        "latest_intake_id": (request.get("intake_id")),
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
    _approved_business_persona(
        settings,
        business_id,
    )

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
) -> dict[str, Any]:
    business_path, business = _approved_business_persona(
        settings,
        business_id,
    )

    speaker_name = speaker_name.strip()
    public_role = public_role.strip()
    speaker_type = speaker_type.strip()
    materials = materials.strip()

    forbidden_claims = [
        str(item).strip() for item in (forbidden_claims or []) if str(item).strip()
    ]

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

    if not forbidden_claims:
        raise CanonicalOperationError(
            "SPEAKER_FORBIDDEN_CLAIMS_REQUIRED",
            "请至少明确一条这个出镜人不能以第一人称表达的内容。",
            "填写第一人称表达边界后重新提交。",
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

    request = {
        "schema_version": (REQUEST_SCHEMA_VERSION),
        "business_id": (business_id),
        "speaker_id": (speaker_id),
        "intake_id": (intake_id),
        "speaker_name": (speaker_name),
        "public_role": (public_role),
        "speaker_type": (speaker_type),
        "materials": (materials),
        "forbidden_claims": (forbidden_claims),
        "created_at": (now_iso()),
        "business_persona_ref": {
            "persona_id": (business.get("persona_id")),
            "revision": (business.get("revision")),
            "path": str(business_path.resolve()),
        },
        "authority": {
            "raw_input_is_speaker_persona": (False),
            "speaker_persona_requires_human_review": (True),
            "business_facts_must_not_be_copied": (True),
            "media_rights_established": (False),
        },
    }

    _write_atomic_json(
        request_path,
        request,
    )

    return {
        "duplicate": False,
        "business_id": (business_id),
        "speaker_id": (speaker_id),
        "intake_id": (intake_id),
        "speaker_name": (speaker_name),
        "public_role": (public_role),
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
