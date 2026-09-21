from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app import background_task_service
from app.auth_service import provision_user
from app.config import Settings
from app.task_service import list_tasks


@pytest.fixture()
def delivery_settings(settings: Settings) -> Settings:
    return replace(
        settings,
        session_cookie_name="aivo_delivery_test",
        default_business_id="unused",
    )


def login(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "123456"},
    )
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": "123456",
            "new_password": "Delivery2026!",
            "confirm_password": "Delivery2026!",
        },
    )
    assert changed.status_code == 200
    return changed.json()["csrf_token"]


def fake_state(request_id: str = "gen_fixture_001") -> dict:
    return {
        "request_id": request_id,
        "business_id": "fixture_pet_store",
        "speaker_id": "speaker_fixture",
        "profile": "mix",
        "confirmed_quantity": 2,
        "source_plan_ready": True,
        "source_plan_artifact_exists": True,
        "source_coverage_supported": True,
        "content_plan": {"ready": True, "selected_quantity": 2},
        "generation": {
            "ready": True,
            "status": "review_required",
            "generated_count": 2,
            "contents": [
                {
                    "content_id": "content_001",
                    "concept_ref": "CONCEPT_001",
                    "title": "标题1",
                    "narration": "口播1",
                    "central_claim": "主张1",
                    "potential_review_flags": [],
                },
                {
                    "content_id": "content_002",
                    "concept_ref": "CONCEPT_002",
                    "title": "标题2",
                    "narration": "口播2",
                    "central_claim": "主张2",
                    "potential_review_flags": [],
                },
            ],
        },
        "review": {
            "completed": False,
            "status": None,
            "approved": False,
        },
        "export": {
            "completed": False,
            "output_name": "gen_fixture_001_approved_mix_scripts.xlsx",
        },
        "next_action": "HUMAN_REVIEW",
        "stop_point_reached": False,
    }


def test_delivery_state_route(delivery_settings: Settings, monkeypatch):
    monkeypatch.setattr(
        main_module,
        "get_content_delivery_state",
        lambda settings, request_id: fake_state(request_id),
    )
    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        login(client)
        response = client.get("/api/create/gen_fixture_001/delivery")
        assert response.status_code == 200
        assert response.json()["state"]["next_action"] == "HUMAN_REVIEW"


def test_resolve_content_plan_requires_csrf(
    delivery_settings: Settings, monkeypatch
):
    monkeypatch.setattr(
        main_module,
        "resolve_content_plan",
        lambda *args, **kwargs: {},
    )
    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        login(client)
        response = client.post(
            "/api/create/gen_fixture_001/resolve-content-plan"
        )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


def test_resolve_content_plan_route_returns_durable_task(
    delivery_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        background_task_service,
        "get_content_delivery_state",
        lambda settings, request_id: fake_state(request_id),
    )
    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/resolve-content-plan",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        task = response.json()["task"]
        assert response.json()["accepted"] is True
        assert task["status"] == "queued"
        assert task["subject_ref"] == "gen_fixture_001"
        assert task["payload"]["operation"] == "content_plan"
        assert task["created_by"]["phone"] == "13800000000"


def test_blocked_source_coverage_direct_post_creates_no_task(
    delivery_settings: Settings,
    monkeypatch,
):
    blocked = fake_state("gen_blocked")
    blocked.update(
        {
            "source_plan_ready": False,
            "source_plan_artifact_exists": True,
            "source_coverage_supported": False,
            "coverage_reason": "当前创作结构暂时不能支持。",
            "production_feasibility": {
                "status": "unsupported",
                "blocker_type": "PERSONA_LACKS_PATTERN_CAPABILITY",
                "humanized_reason": "当前创作结构暂时不能支持。",
            },
            "next_action": "SOURCE_COVERAGE_BLOCKED",
        }
    )
    monkeypatch.setattr(
        background_task_service,
        "get_content_delivery_state",
        lambda settings, request_id: blocked,
    )

    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        before = list_tasks(delivery_settings.database_path, limit=500)

        first = client.post(
            "/api/create/gen_blocked/resolve-content-plan",
            headers={"X-CSRF-Token": csrf},
        )
        second = client.post(
            "/api/create/gen_blocked/resolve-content-plan",
            headers={"X-CSRF-Token": csrf},
        )

        assert first.status_code == 409
        assert second.status_code == 409
        assert first.json()["detail"]["code"] == (
            "CONTENT_PLAN_SOURCE_COVERAGE_UNSUPPORTED"
        )
        assert first.json()["detail"]["task_created"] is False
        assert len(list_tasks(delivery_settings.database_path, limit=500)) == len(before)


def test_generate_scripts_route_returns_durable_task(delivery_settings: Settings):
    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/generate-scripts",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        task = response.json()["task"]
        assert task["status"] == "queued"
        assert task["payload"]["operation"] == "script_generation"


def test_review_route_forwards_authenticated_reviewer(
    delivery_settings: Settings, monkeypatch
):
    calls = {}

    def fake(settings, request_id, *, reviewer, items, note):
        calls.update(
            {
                "request_id": request_id,
                "reviewer": reviewer,
                "items": items,
                "note": note,
            }
        )
        state = fake_state(request_id)
        state["review"] = {
            "completed": True,
            "status": "approved",
            "approved": True,
        }
        state["next_action"] = "EXPORT_EXCEL"
        return {"recovered": False, "approved": True, "state": state}

    monkeypatch.setattr(main_module, "submit_generation_review", fake)

    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/review",
            headers={"X-CSRF-Token": csrf},
            json={
                "note": "人工审核通过",
                "items": [
                    {
                        "content_id": "content_001",
                        "decision": "approved",
                    },
                    {
                        "content_id": "content_002",
                        "decision": "revised",
                        "revised_title": "修改后的标题2",
                        "revised_narration": "修改后的口播2",
                    },
                ],
            },
        )
        assert response.status_code == 200
        assert calls["reviewer"] == "13800000000"
        assert calls["request_id"] == "gen_fixture_001"
        assert len(calls["items"]) == 2
        assert (
            calls["items"][1][
                "decision"
            ]
            == "revised"
        )
        assert (
            calls["items"][1][
                "revised_title"
            ]
            == "修改后的标题2"
        )
        assert response.json()["result"]["approved"] is True


def test_export_route_returns_durable_task(delivery_settings: Settings):
    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/export-mix",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        task = response.json()["task"]
        assert task["task_type"] == "excel_export"
        assert task["payload"]["operation"] == "mix_export"


def test_download_route_returns_existing_file(
    delivery_settings: Settings, monkeypatch, tmp_path: Path
):
    excel = tmp_path / "out.xlsx"
    excel.write_bytes(b"excel")
    monkeypatch.setattr(
        main_module,
        "exported_excel_path",
        lambda settings, request_id: excel,
    )
    monkeypatch.setattr(
        main_module,
        "exported_excel_filename",
        lambda settings, request_id: (
            "小爪宠物店_王琳_Mix混剪_2条_20260918_fixture.xlsx"
        ),
    )
    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        login(client)
        response = client.get(
            "/api/create/gen_fixture_001/exported-excel"
        )
        assert response.status_code == 200
        assert response.content == b"excel"
