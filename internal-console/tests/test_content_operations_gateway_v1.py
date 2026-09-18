from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app import content_operations_gateway as subject


def write_json(
    path: Path,
    value: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_content_operations_projects_existing_authorities_only(
    tmp_path: Path,
    monkeypatch,
):
    pipeline = tmp_path / "ops-pipeline"

    settings = SimpleNamespace(
        pipeline_root=pipeline,
    )

    business_id = "fixture_pet_store"

    write_json(
        pipeline
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json",
        {
            "schema_version": "content-ledger-v1.0",
            "business_id": business_id,
            "entries": [
                {
                    "content_id": "C001",
                    "batch_ref": "gen_001",
                    "status": "exported",
                    "exported_at": "2026-09-18T10:00:00+00:00",
                },
                {
                    "content_id": "C002",
                    "batch_ref": "gen_001",
                    "status": "exported",
                    "exported_at": "2026-09-18T10:00:00+00:00",
                },
                {
                    "content_id": "C003",
                    "batch_ref": "gen_old",
                    "status": "review_required",
                },
            ],
        },
    )

    write_json(
        pipeline
        / "data"
        / "news_deliveries"
        / "news_001"
        / "news_delivery_request_v1.json",
        {
            "schema_version": "news-delivery-request-v1.0",
            "request_id": "news_001",
            "business_id": business_id,
        },
    )

    monkeypatch.setattr(
        subject,
        "get_customer_detail",
        lambda settings, business_id: {
            "business_id": business_id,
            "display_name": "测试门店",
            "industry": "宠物服务",
        },
    )

    monkeypatch.setattr(
        subject,
        "list_speakers",
        lambda settings, business_id: [
            {
                "speaker_id": "speaker_001",
                "display_name": "王琳",
                "public_role": "店主",
                "status": "approved",
            }
        ],
    )

    monkeypatch.setattr(
        subject,
        "_effective_generation_request_audit",
        lambda settings, business_id, profile: {
            "read_only": True,
            "active_request_ids": [],
        },
    )

    monkeypatch.setattr(
        subject,
        "preview_content_creation",
        lambda settings, **kwargs: {
            "capacity": {
                "high_quality_novel_capacity": 3,
            },
            "recommendation": {
                "can_continue": True,
                "status": "supported",
            },
        },
    )

    monkeypatch.setattr(
        subject,
        "preview_news_creation",
        lambda **kwargs: {
            "available": False,
            "status": "no_new_content",
            "message": "当前没有新的可用内容。",
        },
    )

    monkeypatch.setattr(
        subject,
        "get_news_delivery_state",
        lambda settings, request_id: {
            "next_action": "NEWS_EXCEL_EXPORTED",
            "review": {
                "approved_slot_count": 6,
            },
            "export": {
                "completed": True,
                "slot_count": 6,
                "created_at": "2026-09-18T11:00:00+00:00",
            },
            "export_closure": {
                "completed": True,
                "created_at": "2026-09-18T11:01:00+00:00",
            },
        },
    )

    class FakePath:
        def is_file(self):
            return True

    monkeypatch.setattr(
        subject,
        "exported_excel_path",
        lambda settings, request_id: FakePath(),
    )

    monkeypatch.setattr(
        subject,
        "exported_news_excel_path",
        lambda settings, request_id: FakePath(),
    )

    result = subject.get_content_operations_view(
        settings,
        business_id,
    )

    assert (
        result["authority"]["projection_only"]
        is True
    )
    assert (
        result["authority"]["durable_artifact_written"]
        is False
    )
    assert (
        result["delivery_summary"]["mix"]["completed_item_count"]
        == 2
    )
    assert (
        result["delivery_summary"]["news"]["completed_video_count"]
        == 1
    )
    assert (
        result["delivery_summary"]["news"]["completed_title_count"]
        == 6
    )
    assert (
        result["capacity"]["mix"]["remaining"]
        == 3
    )
    assert (
        result["capacity"]["news"]["available"]
        is False
    )
    assert (
        len(result["recent_deliveries"])
        == 2
    )
