from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .canonical_gateway import CanonicalOperationError
from .config import Settings


NEWS_REQUEST_SCHEMA = "news-delivery-request-v1.0"
NEWS_PLAN_SCHEMA = "news-delivery-plan-v1.0"
NEWS_REVIEW_SCHEMA = "news-delivery-human-review-v1.0"
NEWS_REVIEW_SCHEMA_V1_1 = "news-delivery-human-review-v1.1"
NEWS_APPROVED_SCHEMA = "approved-news-delivery-v1.0"
NEWS_EXPORT_RECEIPT_SCHEMA = "news-dynamic-excel-export-receipt-v1.0"
NEWS_CLOSURE_SCHEMA = "news-delivery-export-closure-v1.0"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalOperationError(
            "NEWS_DELIVERY_ARTIFACT_INVALID",
            f"News artifact 无法读取：{path}",
            "停止当前 News 操作并恢复 canonical artifact。",
        ) from exc

    if not isinstance(value, dict):
        raise CanonicalOperationError(
            "NEWS_DELIVERY_ARTIFACT_INVALID",
            f"News artifact 不是 JSON object：{path}",
            "停止当前 News 操作并恢复 canonical artifact。",
        )
    return value


def _pipeline_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _parse_json_output(stdout: str) -> dict[str, Any] | None:
    text = str(stdout or "").strip()
    if not text:
        return None

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass

    for line in reversed(text.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _run_news_command(
    settings: Settings,
    args: list[str],
    *,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    executable = (
        settings.pipeline_python_executable
        or settings.python_executable
    )
    command = [
        executable,
        str(
            settings.pipeline_root
            / "scripts"
            / "news_delivery_v1.py"
        ),
        *args,
    ]

    try:
        process = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=_pipeline_env(),
        )
    except (
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise CanonicalOperationError(
            "NEWS_DELIVERY_RUNTIME_UNAVAILABLE",
            "News Delivery 暂时无法执行。",
            "保留现有 canonical artifacts，修复运行环境后重试。",
        ) from exc

    parsed = _parse_json_output(
        process.stdout
    )

    if process.returncode != 0:
        raise CanonicalOperationError(
            str(
                (parsed or {}).get("code")
                or "NEWS_DELIVERY_FAILED"
            ),
            str(
                (parsed or {}).get("message")
                or process.stderr
                or process.stdout
                or "News Delivery 执行失败。"
            ).strip(),
            "不要覆盖现有 News artifacts；修复当前阶段后重试。",
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
            "NEWS_DELIVERY_INVALID_OUTPUT",
            "News Delivery 返回了无效结果。",
            "停止继续操作并检查 news_delivery_v1.py 输出契约。",
        )

    return parsed


def _request_root(
    settings: Settings,
    request_id: str,
) -> Path:
    return (
        settings.pipeline_root
        / "data"
        / "news_deliveries"
        / request_id
    )


def _paths(
    settings: Settings,
    request_id: str,
) -> dict[str, Path]:
    root = _request_root(
        settings,
        request_id,
    )
    return {
        "root": root,
        "request": (
            root
            / "news_delivery_request_v1.json"
        ),
        "plan": (
            root
            / "news_delivery_plan_v1.json"
        ),
        "review": (
            root
            / "news_delivery_human_review_v1.json"
        ),
        "approved": (
            root
            / "approved_news_delivery_v1.json"
        ),
        "receipt": (
            root
            / "news_dynamic_excel_export_receipt_v1.json"
        ),
        "closure": (
            root
            / "news_delivery_export_closure_v1.json"
        ),
    }



def _completed_news_deliveries(
    settings: Settings,
    business_id: str,
) -> list[dict[str, Any]]:
    root = (
        settings.pipeline_root
        / "data"
        / "news_deliveries"
    )
    if not root.exists():
        return []

    completed: list[
        dict[str, Any]
    ] = []

    for request_path in root.glob(
        "*/news_delivery_request_v1.json"
    ):
        try:
            request = json.loads(
                request_path.read_text(
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
            != NEWS_REQUEST_SCHEMA
            or request.get(
                "business_id"
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
        if not request_id:
            continue

        paths = _paths(
            settings,
            request_id,
        )
        if (
            not paths[
                "receipt"
            ].is_file()
            or not paths[
                "closure"
            ].is_file()
        ):
            continue

        try:
            export = _project_export(
                paths
            )
        except CanonicalOperationError:
            continue

        if (
            not export[
                "completed"
            ]
            or not export[
                "presentation_history_closed"
            ]
        ):
            continue

        completed.append(
            {
                "request_id": (
                    request_id
                ),
                "speaker_id": (
                    request.get(
                        "speaker_id"
                    )
                ),
                "source_content_id": (
                    request.get(
                        "source_content_id"
                    )
                ),
                "created_at": (
                    request.get(
                        "created_at"
                    )
                ),
                "output_name": (
                    export.get(
                        "output_name"
                    )
                ),
                "slot_count": int(
                    export.get(
                        "slot_count"
                    )
                    or 0
                ),
            }
        )

    completed.sort(
        key=lambda item: str(
            item.get(
                "created_at"
            )
            or ""
        ),
        reverse=True,
    )
    return completed

def preview_news_creation(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
) -> dict[str, Any]:
    parsed = _run_news_command(
        settings,
        [
            "--action",
            "preview",
            "--pipeline-root",
            str(settings.pipeline_root),
            "--business-id",
            business_id,
            "--speaker-id",
            speaker_id,
        ],
    )
    preview = parsed["result"]

    authority = (
        preview.get("authority")
        or {}
    )
    if (
        authority.get(
            "remote_model_called"
        )
        is not False
        or authority.get(
            "content_ledger_written"
        )
        is not False
    ):
        raise CanonicalOperationError(
            "NEWS_PREVIEW_MUTATION_DETECTED",
            "News 可用性预览产生了不允许的副作用。",
            "停止继续操作并检查 News Preview Authority。",
        )

    preview = dict(preview)
    preview[
        "completed_deliveries"
    ] = _completed_news_deliveries(
        settings,
        business_id,
    )[:5]

    return preview


def create_news_request(
    settings: Settings,
    *,
    business_id: str,
    speaker_id: str,
    source_content_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    parsed = _run_news_command(
        settings,
        [
            "--action",
            "create-request",
            "--pipeline-root",
            str(settings.pipeline_root),
            "--business-id",
            business_id,
            "--speaker-id",
            speaker_id,
            "--source-content-id",
            source_content_id,
            "--idempotency-key",
            idempotency_key,
        ],
    )
    request = parsed["result"]

    if (
        request.get("schema_version")
        != NEWS_REQUEST_SCHEMA
        or request.get("business_id")
        != business_id
        or request.get("speaker_id")
        != speaker_id
        or request.get(
            "source_content_id"
        )
        != source_content_id
    ):
        raise CanonicalOperationError(
            "NEWS_REQUEST_LINEAGE_INVALID",
            "News Delivery Request lineage 不一致。",
            "停止继续操作并检查 immutable News Delivery Request。",
        )

    return {
        "recovered": bool(
            parsed.get("recovered")
        ),
        "request": request,
        "state": get_news_delivery_state(
            settings,
            str(
                request["request_id"]
            ),
        ),
    }


def get_active_news_request(
    settings: Settings,
    business_id: str,
) -> dict[str, Any]:
    root = (
        settings.pipeline_root
        / "data"
        / "news_deliveries"
    )
    if not root.exists():
        return {
            "active_request": None
        }

    candidates: list[
        tuple[Path, dict[str, Any]]
    ] = []

    for path in root.glob(
        "*/news_delivery_request_v1.json"
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
            != NEWS_REQUEST_SCHEMA
        ):
            continue
        if str(
            request.get(
                "business_id"
            )
            or ""
        ) != business_id:
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
                "NEWS_REQUEST_LINEAGE_MISMATCH",
                "News Delivery Request 目录与 request_id 不一致。",
                "先修复 News Delivery canonical lineage。",
            )

        closure = (
            path.parent
            / "news_delivery_export_closure_v1.json"
        )
        if closure.is_file():
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
            "NEWS_ACTIVE_REQUEST_AMBIGUITY",
            "同一客户存在多个未闭合 News Delivery Request。",
            "停止继续 News 创作并先解决 Request Authority 冲突。",
        )

    _path, request = (
        candidates[0]
    )
    return {
        "active_request": {
            "request_id": (
                request[
                    "request_id"
                ]
            ),
            "business_id": (
                request[
                    "business_id"
                ]
            ),
            "speaker_id": (
                request[
                    "speaker_id"
                ]
            ),
            "source_content_id": (
                request[
                    "source_content_id"
                ]
            ),
            "recommended_slot_count": int(
                request.get(
                    "recommended_slot_count"
                )
                or 0
            ),
        }
    }


def _project_plan(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ready": False,
            "slot_count": 0,
            "slots": [],
        }

    plan = _read_json(path)
    if (
        plan.get("schema_version")
        != NEWS_PLAN_SCHEMA
        or plan.get("status")
        != "review_required"
        or (
            plan.get(
                "validation"
            )
            or {}
        ).get(
            "passed"
        )
        is not True
    ):
        raise CanonicalOperationError(
            "NEWS_PLAN_INVALID",
            "News Delivery Plan 不是有效的 review-ready artifact。",
            "停止继续操作并恢复正确的 News Delivery Plan。",
        )

    slots: list[
        dict[str, Any]
    ] = []
    for item in (
        plan.get("slots")
        or []
    ):
        slots.append(
            {
                "slot_id": (
                    item.get("slot_id")
                ),
                "order": (
                    item.get("order")
                ),
                "semantic_role": (
                    item.get(
                        "semantic_role"
                    )
                ),
                "proposed_text": (
                    item.get(
                        "proposed_text"
                    )
                ),
                "source_known_fact": (
                    item.get(
                        "source_known_fact"
                    )
                ),
                "source_field": (
                    item.get(
                        "source_field"
                    )
                ),
                "price_or_offer_anchor": bool(
                    item.get(
                        "price_or_offer_anchor"
                    )
                ),
                "soft_length_recommendation": (
                    item.get(
                        "soft_length_recommendation"
                    )
                    or {}
                ),
            }
        )

    return {
        "ready": True,
        "sha256": (
            _sha256_file(path)
        ),
        "slot_count": len(
            slots
        ),
        "slots": slots,
        "source_content_id": (
            plan.get(
                "source_content_id"
            )
        ),
        "remote_model_called": (
            (
                plan.get(
                    "authority"
                )
                or {}
            ).get(
                "remote_model_called"
            )
        ),
    }


def _project_review(
    paths: dict[str, Path],
) -> dict[str, Any]:
    approved_path = (
        paths["approved"]
    )
    review_path = paths["review"]

    if not review_path.is_file():
        return {
            "completed": False,
            "approved": False,
            "approved_slot_count": 0,
            "reviewer": None,
        }

    review = _read_json(
        review_path
    )
    if (
        review.get("schema_version")
        not in {
            NEWS_REVIEW_SCHEMA,
            NEWS_REVIEW_SCHEMA_V1_1,
        }
    ):
        raise CanonicalOperationError(
            "NEWS_REVIEW_INVALID",
            "News Human Review schema 不合法。",
            "停止继续操作并恢复正确的 Human Review。",
        )

    if not approved_path.is_file():
        return {
            "completed": True,
            "approved": False,
            "approved_slot_count": 0,
            "reviewer": (
                review.get("reviewer")
            ),
        }

    approved = _read_json(
        approved_path
    )
    if (
        approved.get(
            "schema_version"
        )
        != NEWS_APPROVED_SCHEMA
        or approved.get(
            "status"
        )
        != "approved_for_export"
        or (
            approved.get(
                "validation"
            )
            or {}
        ).get(
            "passed"
        )
        is not True
    ):
        raise CanonicalOperationError(
            "NEWS_APPROVED_ARTIFACT_INVALID",
            "Approved News Delivery artifact 不合法。",
            "停止导出并恢复正确的 Human Approval。",
        )

    return {
        "completed": True,
        "approved": True,
        "approved_slot_count": int(
            approved.get(
                "approved_slot_count"
            )
            or 0
        ),
        "reviewer": (
            (
                approved.get(
                    "human_review"
                )
                or {}
            ).get(
                "reviewer"
            )
        ),
        "revised_and_approved_count": sum(
            1
            for item in (
                approved.get("approved_slots")
                or []
            )
            if item.get("human_review_decision")
            == "revised_and_approved"
        ),
        "approved_slots": [
            {
                "slot_id": (
                    item.get("slot_id")
                ),
                "approved_text": (
                    item.get(
                        "approved_text"
                    )
                ),
                "export_order": (
                    item.get(
                        "export_order"
                    )
                ),
                "human_edited": bool(
                    item.get(
                        "human_edited"
                    )
                ),
                "human_review_decision": (
                    item.get(
                        "human_review_decision"
                    )
                ),
            }
            for item in (
                approved.get(
                    "approved_slots"
                )
                or []
            )
        ],
    }


def _project_export(
    paths: dict[str, Path],
) -> dict[str, Any]:
    receipt_path = (
        paths["receipt"]
    )
    closure_path = (
        paths["closure"]
    )

    if not receipt_path.is_file():
        return {
            "completed": False,
            "presentation_history_closed": False,
            "output_name": None,
            "slot_count": 0,
        }

    receipt = _read_json(
        receipt_path
    )
    if (
        receipt.get(
            "schema_version"
        )
        != NEWS_EXPORT_RECEIPT_SCHEMA
        or receipt.get(
            "validation_passed"
        )
        is not True
    ):
        raise CanonicalOperationError(
            "NEWS_EXPORT_RECEIPT_INVALID",
            "News Excel Export Receipt 不合法。",
            "停止交付并恢复正确的 News Export Receipt。",
        )

    output_path = Path(
        str(
            receipt.get(
                "output_path"
            )
            or ""
        )
    ).expanduser().resolve()
    if (
        not output_path.is_file()
        or receipt.get(
            "output_sha256"
        )
        != _sha256_file(
            output_path
        )
    ):
        raise CanonicalOperationError(
            "NEWS_EXPORT_LINEAGE_MISMATCH",
            "News Excel 与 Export Receipt lineage 不一致。",
            "停止交付并恢复正确的 Excel / Receipt。",
        )

    closed = (
        closure_path.is_file()
    )
    if closed:
        closure = _read_json(
            closure_path
        )
        if (
            closure.get(
                "schema_version"
            )
            != NEWS_CLOSURE_SCHEMA
            or (
                closure.get(
                    "validation"
                )
                or {}
            ).get(
                "passed"
            )
            is not True
        ):
            raise CanonicalOperationError(
                "NEWS_EXPORT_CLOSURE_INVALID",
                "News Export Closure 不合法。",
                "停止下一次 News 创作并恢复 Presentation History Closure。",
            )

    ledger = (
        receipt.get(
            "content_ledger"
        )
        or {}
    )
    if (
        ledger.get(
            "semantic_entry_count_before"
        )
        != ledger.get(
            "semantic_entry_count_after"
        )
    ):
        raise CanonicalOperationError(
            "NEWS_EXPORT_SEMANTIC_LEDGER_DELTA",
            "News Repurpose 错误地改变了 Semantic Ledger entry count。",
            "停止下一次 News 创作并恢复 Content Ledger。",
        )

    return {
        "completed": True,
        "presentation_history_closed": (
            closed
        ),
        "output_name": (
            receipt.get(
                "output_name"
            )
            or output_path.name
        ),
        "output_path": str(
            output_path
        ),
        "output_sha256": (
            receipt.get(
                "output_sha256"
            )
        ),
        "slot_count": int(
            receipt.get(
                "slot_count"
            )
            or 0
        ),
        "semantic_entry_count_delta": 0,
    }


def get_news_delivery_state(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    paths = _paths(
        settings,
        request_id,
    )
    request_path = (
        paths["request"]
    )
    if not request_path.is_file():
        raise CanonicalOperationError(
            "NEWS_REQUEST_NOT_FOUND",
            "News Delivery Request 不存在。",
            "回到 News 创作入口重新选择历史内容。",
        )

    request = _read_json(
        request_path
    )
    if (
        request.get(
            "schema_version"
        )
        != NEWS_REQUEST_SCHEMA
        or request.get(
            "request_id"
        )
        != request_id
    ):
        raise CanonicalOperationError(
            "NEWS_REQUEST_INVALID",
            "News Delivery Request schema 或 identity 不合法。",
            "停止继续操作并恢复 immutable Request。",
        )

    plan = _project_plan(
        paths["plan"]
    )
    review = _project_review(
        paths
    )
    export = _project_export(
        paths
    )

    if (
        export["completed"]
        and export[
            "presentation_history_closed"
        ]
    ):
        next_action = (
            "NEWS_EXCEL_EXPORTED"
        )
    elif review["approved"]:
        next_action = (
            "EXPORT_NEWS_EXCEL"
        )
    elif plan["ready"]:
        next_action = (
            "HUMAN_REVIEW"
        )
    else:
        next_action = (
            "RESOLVE_NEWS_PLAN"
        )

    source = (
        request.get(
            "source_content"
        )
        or {}
    )

    return {
        "request_id": request_id,
        "business_id": (
            request.get(
                "business_id"
            )
        ),
        "speaker_id": (
            request.get(
                "speaker_id"
            )
        ),
        "profile": "news",
        "profile_label": (
            "News 新闻体"
        ),
        "validated_slice": (
            request.get(
                "validated_slice"
            )
        ),
        "source_content": {
            "content_id": (
                request.get(
                    "source_content_id"
                )
            ),
            "title": (
                source.get("title")
            ),
            "central_claim": (
                source.get(
                    "central_claim"
                )
            ),
            "status": (
                source.get(
                    "status"
                )
            ),
        },
        "recommended_slot_count": int(
            request.get(
                "recommended_slot_count"
            )
            or 0
        ),
        "plan": plan,
        "review": review,
        "export": export,
        "next_action": (
            next_action
        ),
        "stop_point_reached": (
            export["completed"]
            and export[
                "presentation_history_closed"
            ]
        ),
        "authority": {
            "semantic_novelty": False,
            "new_semantic_content_created": False,
            "remote_model_called": False,
            "scene_contrast_opened": False,
        },
    }


def resolve_news_plan(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    parsed = _run_news_command(
        settings,
        [
            "--action",
            "resolve-plan",
            "--pipeline-root",
            str(settings.pipeline_root),
            "--request-id",
            request_id,
        ],
    )
    result = parsed["result"]

    if (
        result.get(
            "schema_version"
        )
        != NEWS_PLAN_SCHEMA
        or (
            result.get(
                "authority"
            )
            or {}
        ).get(
            "remote_model_called"
        )
        is not False
    ):
        raise CanonicalOperationError(
            "NEWS_PLAN_OUTPUT_INVALID",
            "News Plan 输出没有通过 Console Authority 检查。",
            "停止继续操作并检查 deterministic News Plan。",
        )

    return {
        "recovered": bool(
            parsed.get("recovered")
        ),
        "state": get_news_delivery_state(
            settings,
            request_id,
        ),
    }


def submit_news_review(
    settings: Settings,
    request_id: str,
    *,
    reviewer: str,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    state = get_news_delivery_state(
        settings,
        request_id,
    )
    if state["next_action"] != "HUMAN_REVIEW":
        raise CanonicalOperationError(
            "NEWS_REVIEW_STAGE_INVALID",
            "当前 News Request 不在 Human Review 阶段。",
            "刷新当前 News Delivery 状态后再操作。",
        )

    review = {
        "schema_version": (
            NEWS_REVIEW_SCHEMA_V1_1
        ),
        "request_id": (
            request_id
        ),
        "reviewer": (
            reviewer
        ),
        "decision": (
            "approve_items"
        ),
        "items": items,
    }

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix=(
            f"{request_id}_review_"
        ),
        delete=False,
    ) as handle:
        json.dump(
            review,
            handle,
            ensure_ascii=False,
            indent=2,
        )
        temp_path = Path(
            handle.name
        )

    try:
        parsed = _run_news_command(
            settings,
            [
                "--action",
                "approve",
                "--pipeline-root",
                str(
                    settings.pipeline_root
                ),
                "--request-id",
                request_id,
                "--review",
                str(temp_path),
            ],
        )
    finally:
        temp_path.unlink(
            missing_ok=True
        )

    approved = parsed["result"]
    if (
        approved.get(
            "schema_version"
        )
        != NEWS_APPROVED_SCHEMA
        or approved.get(
            "status"
        )
        != "approved_for_export"
    ):
        raise CanonicalOperationError(
            "NEWS_REVIEW_OUTPUT_INVALID",
            "Human Review 没有形成有效的 Approved News Delivery。",
            "不要导出；先恢复正确的 Human Approval。",
        )

    return {
        "recovered": bool(
            parsed.get("recovered")
        ),
        "state": get_news_delivery_state(
            settings,
            request_id,
        ),
    }


def export_news_excel(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    parsed = _run_news_command(
        settings,
        [
            "--action",
            "export",
            "--pipeline-root",
            str(settings.pipeline_root),
            "--request-id",
            request_id,
        ],
        timeout_seconds=180,
    )

    result = parsed["result"]
    if (
        result.get(
            "stop_point_reached"
        )
        is not True
        or result.get(
            "remote_model_called"
        )
        is not False
        or int(
            result.get(
                "semantic_entry_count_delta"
            )
            or 0
        )
        != 0
    ):
        raise CanonicalOperationError(
            "NEWS_EXPORT_STOP_POINT_INVALID",
            "News Excel 已执行，但 Presentation History Closure 没有正确闭合。",
            "不要开始下一次 News 创作；先恢复 Export Closure。",
        )

    state = get_news_delivery_state(
        settings,
        request_id,
    )
    if not state[
        "stop_point_reached"
    ]:
        raise CanonicalOperationError(
            "NEWS_EXPORT_STOP_POINT_NOT_REACHED",
            "News Excel 已导出，但本轮交付事实链仍未闭合。",
            "检查 Excel Receipt 与 Presentation History Closure。",
        )

    return {
        "recovered": bool(
            parsed.get("recovered")
        ),
        "state": state,
    }


def exported_news_excel_path(
    settings: Settings,
    request_id: str,
) -> Path:
    paths = _paths(
        settings,
        request_id,
    )
    if not paths[
        "receipt"
    ].is_file():
        raise CanonicalOperationError(
            "NEWS_EXCEL_NOT_EXPORTED",
            "News Excel 尚未导出。",
            "先完成人工审核与 News Excel Export。",
        )

    receipt = _read_json(
        paths["receipt"]
    )
    output = Path(
        str(
            receipt.get(
                "output_path"
            )
            or ""
        )
    ).expanduser().resolve()

    if (
        not output.is_file()
        or receipt.get(
            "output_sha256"
        )
        != _sha256_file(
            output
        )
    ):
        raise CanonicalOperationError(
            "NEWS_EXCEL_LINEAGE_MISMATCH",
            "News Excel 文件与 Export Receipt 不一致。",
            "停止下载并恢复正确的 Excel artifact。",
        )
    return output


def exported_news_excel_filename(
    settings: Settings,
    request_id: str,
) -> str:
    paths = _paths(
        settings,
        request_id,
    )
    if not paths[
        "receipt"
    ].is_file():
        return (
            exported_news_excel_path(
                settings,
                request_id,
            ).name
        )

    receipt = _read_json(
        paths["receipt"]
    )
    return str(
        receipt.get(
            "output_name"
        )
        or exported_news_excel_path(
            settings,
            request_id,
        ).name
    )
