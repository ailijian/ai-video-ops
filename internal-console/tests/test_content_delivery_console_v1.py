from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth_service import provision_user
from app.config import Settings


@pytest.fixture()
def delivery_settings(tmp_path: Path) -> Settings:
    console_root = Path(__file__).resolve().parents[1]
    repo_root = console_root.parent
    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=(repo_root / "ops-pipeline"),
        database_path=(tmp_path / "console.sqlite3"),
        python_executable=str(console_root / ".venv" / "Scripts" / "python.exe"),
        pipeline_python_executable=str(
            repo_root / "ops-pipeline" / ".venv" / "Scripts" / "python.exe"
        ),
        session_cookie_name="aivo_delivery_test",
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
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


def test_resolve_content_plan_route(delivery_settings: Settings, monkeypatch):
    calls = {}

    def fake(settings, request_id):
        calls["request_id"] = request_id
        return {
            "recovered": False,
            "remote_model_called": True,
            "state": fake_state(request_id),
        }

    monkeypatch.setattr(main_module, "resolve_content_plan", fake)

    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/resolve-content-plan",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert calls["request_id"] == "gen_fixture_001"
        assert response.json()["result"]["remote_model_called"] is True


def test_generate_scripts_route(delivery_settings: Settings, monkeypatch):
    calls = {}

    def fake(settings, request_id):
        calls["request_id"] = request_id
        return {
            "recovered": True,
            "remote_model_called": False,
            "state": fake_state(request_id),
        }

    monkeypatch.setattr(main_module, "generate_scripts", fake)

    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/generate-scripts",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert calls["request_id"] == "gen_fixture_001"
        assert response.json()["result"]["remote_model_called"] is False


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
                    {"content_id": "content_001", "decision": "approved"},
                    {"content_id": "content_002", "decision": "approved"},
                ],
            },
        )
        assert response.status_code == 200
        assert calls["reviewer"] == "13800000000"
        assert calls["request_id"] == "gen_fixture_001"
        assert len(calls["items"]) == 2
        assert response.json()["result"]["approved"] is True


def test_export_route(delivery_settings: Settings, monkeypatch):
    calls = {}

    def fake(settings, request_id):
        calls["request_id"] = request_id
        state = fake_state(request_id)
        state["export"] = {
            "completed": True,
            "output_name": "gen_fixture_001_approved_mix_scripts.xlsx",
            "exported_row_count": 2,
        }
        state["next_action"] = "EXCEL_EXPORTED"
        state["stop_point_reached"] = True
        return {"recovered": False, "state": state}

    monkeypatch.setattr(main_module, "export_mix_excel", fake)

    with TestClient(main_module.build_app(delivery_settings)) as client:
        provision_user(delivery_settings.database_path, "13800000000")
        csrf = login(client)
        response = client.post(
            "/api/create/gen_fixture_001/export-mix",
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert calls["request_id"] == "gen_fixture_001"
        assert response.json()["result"]["state"]["stop_point_reached"] is True


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
