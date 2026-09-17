from __future__ import annotations

import hashlib
import json
import os
import subprocess
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

GENERATION_REQUEST_SCHEMA = "generation-request-v1.0"

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


def get_active_generation_request(
    settings: Settings,
    business_id: str,
) -> dict[str, Any]:
    """
    Read-only projection of the canonical active
    Generation Request.

    Canonical artifacts only.
    No SQLite orchestration state.
    """

    root = (
        settings.pipeline_root
        / "data"
        / "generation_requests"
    )

    if not root.exists():
        return {
            "active_request": None
        }

    candidates: list[
        tuple[
            Path,
            dict[str, Any],
        ]
    ] = []

    for path in root.glob(
        "*/generation_request_v1.json"
    ):
        try:
            request = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        if not isinstance(
            request,
            dict,
        ):
            continue

        if (
            request.get(
                "schema_version"
            )
            != GENERATION_REQUEST_SCHEMA
        ):
            continue

        if (
            str(
                request.get(
                    "persona_id"
                )
                or ""
            )
            != business_id
        ):
            continue

        request_id = str(
            request.get(
                "request_id"
            )
            or ""
        )

        if (
            not request_id
            or request_id
            != path.parent.name
        ):
            raise CanonicalOperationError(
                "GENERATION_REQUEST_LINEAGE_MISMATCH",
                (
                    "Generation Request "
                    "目录与 request_id 不一致。"
                ),
                (
                    "请先修复 Generation Request "
                    "canonical lineage。"
                ),
            )

        lifecycle = (
            request.get(
                "lifecycle"
            )
            or {}
        )

        if (
            str(
                lifecycle.get(
                    "status"
                )
                or ""
            )
            in TERMINAL_REQUEST_STATUSES
        ):
            continue

        candidates.append(
            (
                path,
                request,
            )
        )

    if not candidates:
        return {
            "active_request": None
        }

    if len(candidates) > 1:
        raise CanonicalOperationError(
            "CONTENT_GENERATION_ACTIVE_REQUEST_AMBIGUITY",
            (
                "同一客户存在多个 active "
                "Generation Request。"
            ),
            (
                "停止继续创作并先解决 "
                "Generation Request Authority 冲突。"
            ),
        )

    (
        request_path,
        request,
    ) = candidates[0]

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

    return {
        "active_request": {
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
            "handoff_ready": (
                handoff_ready
            ),
            "handoff_status": (
                handoff_status
            ),
            "next_action": (
                "RESOLVE_GENERATION_SOURCES"
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

    env = os.environ.copy()

    env["PYTHONIOENCODING"] = "utf-8"

    env["PYTHONUTF8"] = "1"

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

    env = os.environ.copy()

    env["PYTHONIOENCODING"] = "utf-8"

    env["PYTHONUTF8"] = "1"

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
