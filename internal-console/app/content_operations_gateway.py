from __future__ import annotations

import inspect
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .content_delivery_gateway import (
    exported_excel_path,
    get_content_delivery_state,
)
from .content_gateway import (
    _effective_generation_request_audit,
    preview_content_creation,
)
from .customer_gateway import get_customer_detail
from .news_delivery_gateway import (
    exported_news_excel_path,
    get_news_delivery_state,
    preview_news_creation,
)
from .speaker_gateway import list_speakers


STRONG_EXPOSURE_STATUSES = {
    "exported",
    "published",
}

MIX_STAGE_LABELS = {
    "RESOLVE_GENERATION_SOURCES": "待解析创作来源",
    "CREATE_CONTENT_PLAN": "待生成内容计划",
    "GENERATE_SCRIPTS": "待生成脚本",
    "HUMAN_REVIEW": "待人工审核",
    "REVIEW_COMPLETE_NO_EXPORT": "审核完成，无可导出内容",
    "EXPORT_EXCEL": "待导出 Excel",
    "EXCEL_EXPORTED": "已完成",
}

NEWS_STAGE_LABELS = {
    "RESOLVE_PLAN": "待生成 News Plan",
    "HUMAN_REVIEW": "待人工审核",
    "EXPORT_EXCEL": "待导出 Excel",
    "EXCEL_EXPORTED": "已完成",
    "NEWS_EXCEL_EXPORTED": "已完成",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _invoke_supported(
    function: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    signature = inspect.signature(function)
    accepted = {
        name: value
        for name, value in kwargs.items()
        if name in signature.parameters
    }
    return function(**accepted)


def _approved_speakers(
    settings: Settings,
    business_id: str,
) -> list[dict[str, Any]]:
    try:
        speakers = list_speakers(
            settings,
            business_id,
        )
    except CanonicalOperationError:
        return []

    return [
        speaker
        for speaker in speakers
        if speaker.get("status") == "approved"
    ]


def _content_ledger(
    settings: Settings,
    business_id: str,
) -> dict[str, Any] | None:
    path = (
        settings.pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )
    if not path.is_file():
        return None

    ledger = _read_json(path)

    if (
        ledger is None
        or ledger.get("schema_version")
        != "content-ledger-v1.0"
        or str(ledger.get("business_id") or "")
        != business_id
    ):
        raise CanonicalOperationError(
            "CONTENT_OPERATIONS_LEDGER_INVALID",
            "客户历史内容记录无法可靠读取。",
            "请先恢复 Content Ledger Authority，再查看内容运营。",
        )

    return ledger


def _mix_delivery_groups(
    settings: Settings,
    business_id: str,
) -> list[dict[str, Any]]:
    """
    Historical Mix delivery count is projected from
    strong semantic exposure in the canonical Content Ledger.

    News Price/Offer repurpose does not create new semantic
    exposure and therefore is not counted here as Mix delivery.
    """

    ledger = _content_ledger(
        settings,
        business_id,
    )
    if ledger is None:
        return []

    groups: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue

        if str(entry.get("status") or "") not in STRONG_EXPOSURE_STATUSES:
            continue

        batch_ref = str(
            entry.get("batch_ref") or ""
        ).strip()

        if not batch_ref:
            continue

        groups[batch_ref].append(entry)

    deliveries: list[dict[str, Any]] = []

    for batch_ref, entries in groups.items():
        exported_times = [
            str(
                entry.get("exported_at")
                or entry.get("published_at")
                or entry.get("approved_at")
                or entry.get("created_at")
                or ""
            )
            for entry in entries
        ]

        download_ready = False
        try:
            output = exported_excel_path(
                settings,
                batch_ref,
            )
            download_ready = output.is_file()
        except Exception:
            download_ready = False

        deliveries.append(
            {
                "delivery_id": batch_ref,
                "profile": "mix",
                "kind": "mix_delivery",
                "item_count": len(entries),
                "title_count": None,
                "completed_at": max(
                    exported_times or [""]
                ),
                "status": "completed",
                "download_ready": download_ready,
                "download_url": (
                    f"/api/create/{batch_ref}/exported-excel"
                    if download_ready
                    else None
                ),
                "authority_source": (
                    "content_ledger_strong_exposure"
                ),
            }
        )

    deliveries.sort(
        key=lambda item: (
            item.get("completed_at") or ""
        ),
        reverse=True,
    )
    return deliveries


def _mix_active_work(
    settings: Settings,
    business_id: str,
) -> list[dict[str, Any]]:
    audit = _effective_generation_request_audit(
        settings,
        business_id,
        "mix",
    )

    active_ids = list(
        audit.get("active_request_ids") or []
    )
    work: list[dict[str, Any]] = []

    for request_id in active_ids:
        request_id = str(request_id)

        try:
            state = get_content_delivery_state(
                settings,
                request_id,
            )
        except CanonicalOperationError as exc:
            work.append(
                {
                    "profile": "mix",
                    "request_id": request_id,
                    "stage": "AUTHORITY_BLOCKED",
                    "stage_label": "需要处理 Authority 阻塞",
                    "status": "blocked",
                    "detail": exc.next_action,
                    "continue_url": (
                        f"/create?business_id={business_id}"
                    ),
                }
            )
            continue

        next_action = str(
            state.get("next_action") or ""
        )

        if next_action == "EXCEL_EXPORTED":
            continue

        work.append(
            {
                "profile": "mix",
                "request_id": request_id,
                "stage": next_action,
                "stage_label": MIX_STAGE_LABELS.get(
                    next_action,
                    next_action or "进行中",
                ),
                "status": "in_progress",
                "detail": None,
                "continue_url": (
                    f"/create?business_id={business_id}"
                ),
            }
        )

    return work


def _mix_capacity(
    settings: Settings,
    business_id: str,
    speaker_id: str | None,
) -> dict[str, Any]:
    if not speaker_id:
        return {
            "available": False,
            "remaining": None,
            "status": "speaker_required",
            "message": "还没有 Approved Speaker Persona。",
        }

    try:
        preview = preview_content_creation(
            settings,
            business_id=business_id,
            speaker_id=speaker_id,
            profile="mix",
            quantity=20,
        )
    except CanonicalOperationError as exc:
        return {
            "available": False,
            "remaining": None,
            "status": "authority_blocked",
            "message": (
                exc.next_action or exc.message
            ),
        }

    capacity = preview.get("capacity") or {}
    recommendation = (
        preview.get("recommendation") or {}
    )

    remaining = capacity.get(
        "high_quality_novel_capacity"
    )
    if remaining is None:
        remaining = capacity.get(
            "remaining_high_quality_novel_capacity"
        )

    can_continue = bool(
        recommendation.get("can_continue")
    )

    return {
        "available": can_continue,
        "remaining": (
            int(remaining or 0)
            if remaining is not None
            else None
        ),
        "status": (
            recommendation.get("status")
            or (
                "available"
                if can_continue
                else "exhausted"
            )
        ),
        "message": (
            recommendation.get("message")
            or (
                "当前仍有可用的高质量新内容。"
                if can_continue
                else "当前没有新的高质量 Mix 内容空间。"
            )
        ),
    }


def _news_request_ids(
    settings: Settings,
    business_id: str,
) -> list[str]:
    root = (
        settings.pipeline_root
        / "data"
        / "news_deliveries"
    )

    if not root.is_dir():
        return []

    request_ids: list[str] = []

    for request_dir in sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir()
        ),
        key=lambda path: path.name,
    ):
        request_path = (
            request_dir
            / "news_delivery_request_v1.json"
        )

        if not request_path.is_file():
            continue

        request = _read_json(request_path)

        if (
            request is None
            or str(request.get("business_id") or "")
            != business_id
        ):
            continue

        request_ids.append(request_dir.name)

    return request_ids


def _news_projection(
    settings: Settings,
    business_id: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    completed: list[dict[str, Any]] = []
    work: list[dict[str, Any]] = []

    for request_id in _news_request_ids(
        settings,
        business_id,
    ):
        try:
            state = get_news_delivery_state(
                settings,
                request_id,
            )
        except CanonicalOperationError as exc:
            work.append(
                {
                    "profile": "news",
                    "request_id": request_id,
                    "stage": "AUTHORITY_BLOCKED",
                    "stage_label": "需要处理 Authority 阻塞",
                    "status": "blocked",
                    "detail": exc.next_action,
                    "continue_url": (
                        f"/create?business_id={business_id}"
                    ),
                }
            )
            continue

        next_action = str(
            state.get("next_action") or ""
        )

        export = state.get("export") or {}
        closure = (
            state.get("export_closure") or {}
        )
        review = state.get("review") or {}

        completed_flag = (
            next_action
            in {
                "EXCEL_EXPORTED",
                "NEWS_EXCEL_EXPORTED",
            }
            or (
                export.get("completed") is True
                and closure.get("completed") is True
            )
        )

        if completed_flag:
            title_count = (
                export.get("slot_count")
                or export.get("exported_slot_count")
                or review.get("approved_slot_count")
                or review.get("approved_item_count")
                or 0
            )

            completed_at = (
                closure.get("created_at")
                or export.get("created_at")
                or ""
            )

            download_ready = False
            try:
                output = exported_news_excel_path(
                    settings,
                    request_id,
                )
                download_ready = output.is_file()
            except Exception:
                download_ready = False

            completed.append(
                {
                    "delivery_id": request_id,
                    "profile": "news",
                    "kind": "news_delivery",
                    "item_count": 1,
                    "title_count": int(
                        title_count or 0
                    ),
                    "completed_at": str(
                        completed_at
                    ),
                    "status": "completed",
                    "download_ready": download_ready,
                    "download_url": (
                        (
                            "/api/create/news/"
                            f"{request_id}/excel"
                        )
                        if download_ready
                        else None
                    ),
                    "authority_source": (
                        "news_export_closure"
                    ),
                }
            )
            continue

        work.append(
            {
                "profile": "news",
                "request_id": request_id,
                "stage": next_action,
                "stage_label": NEWS_STAGE_LABELS.get(
                    next_action,
                    next_action or "进行中",
                ),
                "status": "in_progress",
                "detail": None,
                "continue_url": (
                    f"/create?business_id={business_id}"
                ),
            }
        )

    completed.sort(
        key=lambda item: (
            item.get("completed_at") or ""
        ),
        reverse=True,
    )

    return completed, work


def _news_availability(
    settings: Settings,
    business_id: str,
    speaker_id: str | None,
) -> dict[str, Any]:
    if not speaker_id:
        return {
            "available": False,
            "status": "speaker_required",
            "message": "还没有 Approved Speaker Persona。",
        }

    try:
        preview = _invoke_supported(
            preview_news_creation,
            settings=settings,
            business_id=business_id,
            speaker_id=speaker_id,
        )
    except CanonicalOperationError as exc:
        return {
            "available": False,
            "status": "authority_blocked",
            "message": (
                exc.next_action or exc.message
            ),
        }

    if not isinstance(preview, dict):
        return {
            "available": False,
            "status": "unavailable",
            "message": "暂时无法确认 News 可用内容。",
        }

    recommendation = (
        preview.get("recommendation") or {}
    )

    available = bool(
        preview.get("available")
        or preview.get("eligible")
        or preview.get("can_create")
        or preview.get("source_content")
        or recommendation.get("can_continue")
    )

    status = (
        preview.get("status")
        or recommendation.get("status")
        or (
            "available"
            if available
            else "no_new_content"
        )
    )

    message = (
        preview.get("message")
        or recommendation.get("message")
        or (
            "当前有可用于 News 的内容。"
            if available
            else "当前没有新的可用 News 内容。"
        )
    )

    return {
        "available": available,
        "status": str(status),
        "message": str(message),
    }


def get_content_operations_view(
    settings: Settings,
    business_id: str,
) -> dict[str, Any]:
    """
    Customer-centric, read-only operations projection.

    No durable artifact, lifecycle state, SQLite record or
    remote-model call is created here.
    """

    customer = get_customer_detail(
        settings,
        business_id,
    )

    approved_speakers = _approved_speakers(
        settings,
        business_id,
    )

    default_speaker = (
        approved_speakers[0]
        if approved_speakers
        else None
    )

    default_speaker_id = (
        str(
            default_speaker.get("speaker_id")
            or ""
        )
        if default_speaker
        else None
    )

    mix_deliveries = _mix_delivery_groups(
        settings,
        business_id,
    )

    mix_work = _mix_active_work(
        settings,
        business_id,
    )

    (
        news_deliveries,
        news_work,
    ) = _news_projection(
        settings,
        business_id,
    )

    mix_capacity = _mix_capacity(
        settings,
        business_id,
        default_speaker_id,
    )

    news_availability = _news_availability(
        settings,
        business_id,
        default_speaker_id,
    )

    recent_deliveries = (
        mix_deliveries
        + news_deliveries
    )
    recent_deliveries.sort(
        key=lambda item: (
            item.get("completed_at") or ""
        ),
        reverse=True,
    )

    mix_item_count = sum(
        int(item.get("item_count") or 0)
        for item in mix_deliveries
    )

    news_video_count = len(
        news_deliveries
    )

    news_title_count = sum(
        int(item.get("title_count") or 0)
        for item in news_deliveries
    )

    current_work = (
        mix_work
        + news_work
    )

    return {
        "schema_version": "content-operations-view-v1.0",
        "customer": {
            "business_id": business_id,
            "display_name": (
                customer.get("display_name")
                or business_id
            ),
            "industry": customer.get("industry"),
            "approved_speaker_count": len(
                approved_speakers
            ),
            "default_speaker": (
                {
                    "speaker_id": default_speaker_id,
                    "display_name": (
                        default_speaker.get(
                            "display_name"
                        )
                    ),
                    "public_role": (
                        default_speaker.get(
                            "public_role"
                        )
                    ),
                }
                if default_speaker
                else None
            ),
        },
        "delivery_summary": {
            "mix": {
                "completed_batch_count": len(
                    mix_deliveries
                ),
                "completed_item_count": mix_item_count,
                "unit_label": "条",
            },
            "news": {
                "completed_video_count": news_video_count,
                "completed_title_count": news_title_count,
                "unit_label": "个视频",
            },
        },
        "capacity": {
            "mix": mix_capacity,
            "news": news_availability,
        },
        "current_work": current_work,
        "recent_deliveries": (
            recent_deliveries[:10]
        ),
        "actions": {
            "create_url": (
                (
                    "/create?"
                    f"business_id={business_id}"
                    f"&speaker_id={default_speaker_id}"
                )
                if default_speaker_id
                else None
            ),
            "customer_url": (
                f"/customers/{business_id}"
            ),
        },
        "authority": {
            "projection_only": True,
            "durable_artifact_written": False,
            "sqlite_state_written": False,
            "remote_model_called": False,
            "mix_history_source": (
                "content_ledger_strong_exposure"
            ),
            "mix_current_work_source": (
                "effective_generation_request_lifecycle"
            ),
            "news_history_source": (
                "news_export_closure"
            ),
            "capacity_source": (
                "existing_creation_previews"
            ),
        },
    }
