from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .canonical_gateway import (
    CanonicalOperationError,
)
from .config import Settings
from .customer_gateway import (
    list_customers,
)
from .speaker_gateway import (
    list_speakers,
)
from .path_safety import validate_identifier
from .subprocess_env import pipeline_subprocess_env
from .operator_projection import request_actor

GENERATION_REQUEST_SCHEMA = "generation-request-v1.0"

GENERATION_SOURCE_PLAN_SCHEMA = "generation-source-plan-v1.0"

TERMINAL_REQUEST_STATUSES = {
    "completed",
    "exported",
    "cancelled",
    "abandoned",
}


def _sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def _project_generation_source_plan(
    settings: Settings,
    request_id: str,
    request_path: Path,
) -> dict[str, Any]:
    """
    Read-only projection of the canonical
    Generation Source Plan.

    Projects data/production_plans/<request_id>/
    generation_source_plan_v1.json directly.
    No SQLite orchestration state.
    """

    empty_projection = {
        "source_plan_ready": False,
        "source_plan_status": None,
        "coverage_status": None,
        "coverage_code": None,
        "coverage_reason": None,
        "selected_pattern_count": 0,
        "eligible_case_count": 0,
    }

    plan_path = (
        settings.pipeline_root
        / "data"
        / "production_plans"
        / request_id
        / "generation_source_plan_v1.json"
    )

    if not plan_path.is_file():
        return empty_projection

    try:
        plan = json.loads(
            plan_path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise CanonicalOperationError(
            "GENERATION_SOURCE_PLAN_INVALID",
            (
                "Generation Source Plan "
                "无法读取。"
            ),
            (
                "请检查当前 Generation "
                "Request 的 Source Plan。"
            ),
        ) from exc

    if (
        not isinstance(
            plan,
            dict,
        )
        or plan.get(
            "schema_version"
        )
        != GENERATION_SOURCE_PLAN_SCHEMA
        or str(
            plan.get(
                "request_id"
            )
            or ""
        )
        != request_id
    ):
        raise CanonicalOperationError(
            "GENERATION_SOURCE_PLAN_LINEAGE_MISMATCH",
            (
                "Generation Source Plan "
                "与当前 Generation Request "
                "lineage 不一致。"
            ),
            (
                "停止继续处理并恢复正确的 "
                "Generation Source Plan。"
            ),
        )

    plan_request = (
        plan.get("request")
        or {}
    )

    if (
        str(
            plan_request.get(
                "request_sha"
            )
            or ""
        )
        != _sha256_file(
            request_path
        )
    ):
        raise CanonicalOperationError(
            (
                "GENERATION_SOURCE_PLAN_"
                "LINEAGE_MISMATCH"
            ),
            (
                "Generation Source Plan "
                "引用的 Generation Request "
                "SHA-256 与当前 immutable "
                "Request 不一致。"
            ),
            (
                "停止继续处理并恢复正确的 "
                "Generation Source Plan。"
            ),
        )

    coverage = (
        plan.get(
            "coverage"
        )
        or {}
    )

    return {
        "source_plan_ready": True,
        "source_plan_status": (
            "source_matching_completed"
        ),
        "coverage_status": (
            coverage.get(
                "status"
            )
        ),
        "coverage_code": (
            coverage.get(
                "code"
            )
        ),
        "coverage_reason": (
            coverage.get(
                "reason"
            )
        ),
        "selected_pattern_count": len(
            plan.get(
                "selected_patterns"
            )
            or []
        ),
        "eligible_case_count": len(
            plan.get(
                "eligible_case_pool"
            )
            or []
        ),
    }



def _effective_generation_request_audit(
    settings: Settings,
    business_id: str,
    profile: str,
) -> dict[str, Any]:
    executable = (
        getattr(
            settings,
            "pipeline_python_executable",
            None,
        )
        or getattr(
            settings,
            "python_executable",
            None,
        )
        or sys.executable
    )

    repo_root = getattr(
        settings,
        "repo_root",
        (
            Path(__file__)
            .resolve()
            .parents[2]
        ),
    )

    script = (
        Path(repo_root)
        / "ops-pipeline"
        / "scripts"
        / "generation_request_effective_lifecycle_v1.py"
    )

    command = [
        executable,
        str(script),
        "--pipeline-root",
        str(
            settings.pipeline_root
        ),
        "--business-id",
        business_id,
        "--profile",
        profile,
    ]

    env = pipeline_subprocess_env(needs_deepseek=False)

    try:
        process = subprocess.run(
            command,
            cwd=str(
                Path(repo_root)
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            env=env,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "GENERATION_EFFECTIVE_LIFECYCLE_UNAVAILABLE",
            "暂时无法确认当前创作状态。",
            (
                "不要创建新的 Request；"
                "请先恢复 Effective Lifecycle Resolver。"
            ),
        ) from exc

    try:
        parsed = json.loads(
            process.stdout
        )
    except json.JSONDecodeError as exc:
        raise CanonicalOperationError(
            "GENERATION_EFFECTIVE_LIFECYCLE_INVALID_OUTPUT",
            "当前创作状态解析返回了无效结果。",
            (
                "不要创建新的 Request；"
                "请检查 Effective Lifecycle Resolver。"
            ),
        ) from exc

    if (
        process.returncode != 0
        or not isinstance(
            parsed,
            dict,
        )
        or parsed.get(
            "ok"
        )
        is not True
        or not isinstance(
            parsed.get(
                "audit"
            ),
            dict,
        )
    ):
        raise CanonicalOperationError(
            str(
                parsed.get(
                    "code"
                )
                if isinstance(
                    parsed,
                    dict,
                )
                else (
                    "GENERATION_EFFECTIVE_"
                    "LIFECYCLE_FAILED"
                )
            ),
            "暂时无法确认当前创作状态。",
            str(
                parsed.get(
                    "message"
                )
                if isinstance(
                    parsed,
                    dict,
                )
                else (
                    "请检查 Effective "
                    "Lifecycle Resolver。"
                )
            ),
        )

    audit = parsed[
        "audit"
    ]

    if (
        audit.get(
            "read_only"
        )
        is not True
        or audit.get(
            "artifact_written"
        )
        is not False
        or audit.get(
            "remote_model_called"
        )
        is not False
        or audit.get(
            "profile_filter"
        )
        != profile
    ):
        raise CanonicalOperationError(
            "GENERATION_EFFECTIVE_LIFECYCLE_BOUNDARY_INVALID",
            "当前创作状态 Resolver 越过了只读边界。",
            "停止继续操作并检查 Effective Lifecycle Authority。",
        )

    return audit


def get_active_generation_request(
    settings: Settings,
    business_id: str,
    profile: str = "mix",
) -> dict[str, Any]:
    """
    Read-only projection of the canonical active
    Generation Request.

    Canonical artifacts only.
    No SQLite orchestration state.
    """

    profile = str(
        profile or "mix"
    ).strip().lower()

    if profile not in {
        "mix",
        "news",
    }:
        raise CanonicalOperationError(
            "GENERATION_PROFILE_INVALID",
            "创作模式无效。",
            "请选择 Mix 或 News。",
        )

    audit = (
        _effective_generation_request_audit(
            settings,
            business_id,
            profile,
        )
    )

    active_ids = list(
        audit.get(
            "active_request_ids"
        )
        or []
    )

    if not active_ids:
        return {
            "active_request": None
        }

    if len(
        active_ids
    ) > 1:
        raise CanonicalOperationError(
            "CONTENT_GENERATION_ACTIVE_REQUEST_AMBIGUITY",
            (
                "同一客户在当前创作模式下"
                "存在多个真正可恢复的 "
                "Generation Request。"
            ),
            (
                "停止继续创作并先解决 "
                "Generation Request Authority 冲突。"
            ),
        )

    request_id = str(
        active_ids[0]
    )

    request_path = (
        settings.pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )

    if not request_path.is_file():
        raise CanonicalOperationError(
            "GENERATION_REQUEST_NOT_FOUND",
            "Effective Lifecycle 指向的 Generation Request 不存在。",
            "停止继续操作并恢复 canonical Request lineage。",
        )

    try:
        request = json.loads(
            request_path.read_text(
                encoding="utf-8"
            )
        )

    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise CanonicalOperationError(
            "GENERATION_REQUEST_INVALID",
            "Generation Request 无法读取。",
            "停止继续操作并恢复 canonical Request。",
        ) from exc

    if (
        not isinstance(
            request,
            dict,
        )
        or request.get(
            "schema_version"
        )
        != GENERATION_REQUEST_SCHEMA
        or request.get(
            "request_id"
        )
        != request_id
        or str(
            request.get(
                "persona_id"
            )
            or ""
        )
        != business_id
        or str(
            request.get(
                "target_profile"
            )
            or request.get(
                "profile"
            )
            or ""
        ).lower()
        != profile
    ):
        raise CanonicalOperationError(
            "GENERATION_REQUEST_LINEAGE_MISMATCH",
            "Effective Lifecycle 与 Generation Request lineage 不一致。",
            "停止继续操作并恢复正确的 Request Authority。",
        )

    classifications = [
        item
        for item in (
            audit.get(
                "requests"
            )
            or []
        )
        if item.get(
            "request_id"
        )
        == request_id
    ]

    if len(
        classifications
    ) != 1:
        raise CanonicalOperationError(
            "GENERATION_EFFECTIVE_LIFECYCLE_AMBIGUITY",
            "无法唯一恢复当前 Generation Request 的 Effective Lifecycle。",
            "停止继续操作并检查 Resolver 输出。",
        )

    effective = (
        classifications[0]
    )

    handoff_path = (
        request_path.parent
        / (
            "generation_source_planning_"
            "handoff_v1.json"
        )
    )

    handoff_ready = False
    handoff_status = None

    if handoff_path.is_file():
        try:
            handoff = json.loads(
                handoff_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise CanonicalOperationError(
                "GENERATION_HANDOFF_INVALID",
                (
                    "Source Planning Handoff "
                    "无法读取。"
                ),
                (
                    "请恢复或修复当前 "
                    "Generation Request 的 Handoff。"
                ),
            ) from exc

        if not isinstance(
            handoff,
            dict,
        ):
            raise CanonicalOperationError(
                "GENERATION_HANDOFF_INVALID",
                (
                    "Source Planning Handoff "
                    "不是合法 JSON object。"
                ),
                (
                    "请恢复或修复当前 "
                    "Generation Request 的 Handoff。"
                ),
            )

        request_ref = (
            handoff.get(
                "generation_request_ref"
            )
            or {}
        )

        if (
            handoff.get(
                "schema_version"
            )
            != (
                "generation-source-planning-"
                "handoff-v1.0"
            )
            or handoff.get(
                "request_id"
            )
            != request.get(
                "request_id"
            )
            or request_ref.get(
                "file_sha256"
            )
            != _sha256_file(
                request_path
            )
        ):
            raise CanonicalOperationError(
                "GENERATION_HANDOFF_LINEAGE_MISMATCH",
                (
                    "Source Planning Handoff "
                    "与当前 Generation Request "
                    "lineage 不一致。"
                ),
                (
                    "停止继续处理并恢复正确的 "
                    "Source Planning Handoff。"
                ),
            )

        handoff_ready = True

        handoff_status = (
            handoff.get(
                "status"
            )
        )

    lifecycle = (
        request.get(
            "lifecycle"
        )
        or {}
    )

    confirmation = (
        request.get(
            "confirmation"
        )
        or {}
    )

    authority = (
        request.get(
            "authority"
        )
        or {}
    )

    source_plan = _project_generation_source_plan(
        settings,
        str(
            request.get(
                "request_id"
            )
            or ""
        ),
        request_path,
    )

    return {
        "active_request": {
            "created_by": request_actor(request),
            "request_id": (
                request.get(
                    "request_id"
                )
            ),
            "business_id": (
                business_id
            ),
            "speaker_id": (
                request.get(
                    "speaker_persona"
                )
            ),
            "profile": (
                request.get(
                    "target_profile"
                )
                or request.get(
                    "profile"
                )
            ),
            "requested_quantity": (
                confirmation.get(
                    "operator_requested_quantity"
                )
            ),
            "confirmed_quantity": (
                request.get(
                    "quantity"
                )
            ),
            "created_at": (
                request.get(
                    "created_at"
                )
            ),
            "lifecycle_status": (
                lifecycle.get(
                    "status"
                )
            ),
            "effective_status": (
                effective.get(
                    "effective_status"
                )
            ),
            "effective_stage": (
                effective.get(
                    "effective_stage"
                )
            ),
            "handoff_ready": (
                handoff_ready
            ),
            "handoff_status": (
                handoff_status
            ),
            **source_plan,
            "next_action": (
                "CREATE_CONTENT_PLAN"
                if source_plan.get(
                    "source_plan_ready"
                )
                else (
                    "RESOLVE_GENERATION_SOURCES"
                )
            ),
            "authority": {
                "script_generation_performed": bool(
                    authority.get(
                        "script_generation_performed"
                    )
                ),
                "generation_batch_created": bool(
                    authority.get(
                        "generation_batch_created"
                    )
                ),
                "content_ledger_written": bool(
                    authority.get(
                        "content_ledger_written"
                    )
                ),
                "remote_model_called": bool(
                    authority.get(
                        "remote_model_called"
                    )
                ),
            },
        }
    }


def list_creation_options(
    settings: Settings,
) -> dict[str, Any]:
    customers: list[dict[str, Any]] = []

    for customer in list_customers(settings):
        if customer.get("status") != "approved":
            continue

        business_id = str(customer["business_id"])

        try:
            speakers = list_speakers(
                settings,
                business_id,
            )

            authority_blocker = None

        except CanonicalOperationError as exc:
            speakers = []

            authority_blocker = {
                "code": exc.code,
                "message": exc.message,
                "next_action": (exc.next_action),
            }

        approved_speakers = [
            {
                "speaker_id": (speaker["speaker_id"]),
                "display_name": (speaker["display_name"]),
                "public_role": (speaker["public_role"]),
                "status": (speaker["status"]),
            }
            for speaker in speakers
            if (speaker.get("status") == "approved")
        ]

        customers.append(
            {
                "business_id": (business_id),
                "display_name": (customer["display_name"]),
                "industry": (customer.get("industry")),
                "business_persona_status": ("approved"),
                "speakers": (approved_speakers),
                "creation_ready": bool(approved_speakers),
                "authority_blocker": (authority_blocker),
            }
        )

    customers.sort(
        key=lambda item: (
            not item["creation_ready"],
            item["display_name"],
        )
    )

    return {
        "customers": customers,
        "ready_customer_count": sum(
            customer["creation_ready"] for customer in customers
        ),
        "authority": {
            "approved_business_persona_required": (True),
            "approved_speaker_persona_required": (True),
            "media_rights_required_for_script_capacity_preview": (False),
            "second_customer_truth_created": (False),
        },
    }


def _parse_json_output(
    stdout: str,
) -> dict[str, Any] | None:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(
            value,
            dict,
        ):
            return value

    return None


def preview_content_creation(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    profile: str,
    quantity: int,
) -> dict[str, Any]:
    executable = settings.pipeline_python_executable or settings.python_executable

    command = [
        executable,
        str(settings.pipeline_root / "scripts" / ("content_creation_" "entry_v1.py")),
        "--business-id",
        business_id,
        "--speaker-id",
        speaker_id,
        "--profile",
        profile,
        "--quantity",
        str(quantity),
        "--pipeline-root",
        str(settings.pipeline_root),
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
            timeout=60,
            check=False,
            env=env,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "CONTENT_CAPACITY_PREVIEW_UNAVAILABLE",
            "内容容量暂时无法检查。",
            "请稍后重新检查；当前没有生成任何脚本。",
        ) from exc

    parsed = _parse_json_output(result.stdout)

    if result.returncode != 0:
        raise CanonicalOperationError(
            str((parsed or {}).get("code") or ("CONTENT_CAPACITY_" "PREVIEW_FAILED")),
            "内容容量检查没有完成。",
            (
                str((parsed or {}).get("message") or "")
                or ("请检查客户、出镜人和" "当前内容 Authority。")
            ),
        )

    if (
        parsed is None
        or parsed.get("ok") is not True
        or not isinstance(
            parsed.get("entry"),
            dict,
        )
    ):
        raise CanonicalOperationError(
            "CONTENT_CAPACITY_PREVIEW_INVALID_OUTPUT",
            "内容容量检查返回了无效结果。",
            "请检查 canonical Content Creation Entry 后重试。",
        )

    entry = parsed["entry"]

    authority = entry.get("authority") or {}

    if (
        authority.get("script_generation_performed") is not False
        or authority.get("generation_request_created") is not False
        or authority.get("content_ledger_written") is not False
    ):
        raise CanonicalOperationError(
            "CONTENT_PREVIEW_MUTATION_DETECTED",
            "容量预览产生了不允许的副作用。",
            "停止继续操作并检查 Content Creation Entry。",
        )

    return entry


def confirm_content_creation(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
    idempotency_key: str,
    created_by_user_id: int | None = None,
    created_by_phone: str | None = None,
) -> dict[str, Any]:
    executable = settings.pipeline_python_executable or settings.python_executable

    command = [
        executable,
        str(
            settings.pipeline_root / "scripts" / ("generation_request_" "handoff_v1.py")
        ),
        "--business-id",
        business_id,
        "--speaker-id",
        speaker_id,
        "--profile",
        profile,
        "--requested-quantity",
        str(requested_quantity),
        "--confirmed-quantity",
        str(confirmed_quantity),
        "--idempotency-key",
        idempotency_key,
        "--pipeline-root",
        str(settings.pipeline_root),
    ]
    if created_by_user_id is not None:
        command.extend(["--created-by-user-id", str(created_by_user_id)])
        command.extend(["--created-by-phone", str(created_by_phone or "")])

    env = pipeline_subprocess_env(needs_deepseek=False)

    try:
        process = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            env=env,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "GENERATION_REQUEST_UNAVAILABLE",
            "Generation Request 暂时无法建立。",
            ("请稍后重试；当前没有" "生成任何脚本。"),
        ) from exc

    parsed = _parse_json_output(process.stdout)

    if process.returncode != 0:
        raise CanonicalOperationError(
            str((parsed or {}).get("code") or ("GENERATION_REQUEST_" "FAILED")),
            "Generation Request 没有建立。",
            (
                str((parsed or {}).get("message") or "")
                or ("请重新检查内容容量后" "再确认生成。")
            ),
        )

    if (
        parsed is None
        or parsed.get("ok") is not True
        or not isinstance(
            parsed.get("result"),
            dict,
        )
    ):
        raise CanonicalOperationError(
            "GENERATION_REQUEST_INVALID_OUTPUT",
            ("Generation Request " "返回了无效结果。"),
            ("请检查 canonical " "Generation Request operation。"),
        )

    result = parsed["result"]

    authority = result.get("authority") or {}

    if (
        authority.get("script_generation_performed") is not False
        or authority.get("content_ledger_written") is not False
        or authority.get("remote_model_called") is not False
    ):
        raise CanonicalOperationError(
            "GENERATION_REQUEST_BOUNDARY_CROSSED",
            ("Generation Request 阶段" "越过了允许边界。"),
            "停止继续处理并检查 canonical operation。",
        )

    return result


def resolve_generation_sources(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    try:
        request_id = validate_identifier(request_id, field="request_id")
    except ValueError:
        raise CanonicalOperationError(
            "GENERATION_REQUEST_ID_INVALID",
            "Generation Request ID 不合法。",
            "请从当前创作流程恢复正确的 Request。",
        ) from None
    executable = settings.pipeline_python_executable or settings.python_executable

    command = [
        executable,
        str(
            settings.pipeline_root
            / "scripts"
            / ("resolve_generation_" "source_plan_v1.py")
        ),
        "--request-id",
        request_id,
        "--pipeline-root",
        str(settings.pipeline_root),
    ]

    env = pipeline_subprocess_env(needs_deepseek=False)

    try:
        process = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
            env=env,
        )

    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "GENERATION_SOURCE_PLAN_UNAVAILABLE",
            ("Generation Source Plan " "暂时无法解析。"),
            ("请稍后重试；当前没有" "生成任何脚本。"),
        ) from exc

    parsed = _parse_json_output(process.stdout)

    if process.returncode != 0:
        raise CanonicalOperationError(
            str((parsed or {}).get("code") or ("GENERATION_SOURCE_" "PLAN_FAILED")),
            "Generation Source Plan 没有完成。",
            (
                str((parsed or {}).get("message") or "")
                or ("请检查 canonical Source " "Authority 后重试。")
            ),
        )

    if parsed is None or parsed.get("ok") is not True:
        raise CanonicalOperationError(
            "GENERATION_SOURCE_PLAN_INVALID_OUTPUT",
            ("Generation Source Plan " "返回了无效结果。"),
            ("请检查 canonical Source " "Plan operation。"),
        )

    if (
        parsed.get("remote_model_called") is not False
        or parsed.get("script_generation_performed") is not False
        or parsed.get("generation_batch_created") is not False
        or parsed.get("content_ledger_written") is not False
    ):
        raise CanonicalOperationError(
            "GENERATION_SOURCE_PLAN_BOUNDARY_CROSSED",
            ("Generation Source Plan 阶段" "越过了允许边界。"),
            "停止继续处理并检查 canonical operation。",
        )

    return parsed
