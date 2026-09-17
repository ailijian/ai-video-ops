from __future__ import annotations

import json
import os
import subprocess
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
