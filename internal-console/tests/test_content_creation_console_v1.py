from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import (
    TestClient,
)

from app import main as main_module
from app import content_gateway as content_gateway_module
from app.auth_service import (
    provision_user,
)
from app.config import Settings


@pytest.fixture()
def content_settings(
    settings: Settings,
) -> Settings:
    return replace(
        settings,
        session_cookie_name=("aivo_content_test"),
        default_business_id="unused",
    )


def login(
    client: TestClient,
) -> str:
    response = client.post(
        "/api/auth/login",
        json={
            "phone": ("13800000000"),
            "password": ("123456"),
        },
    )

    assert response.status_code == 200

    csrf = response.json()["csrf_token"]

    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": ("123456"),
            "new_password": ("Content2026!"),
            "confirm_password": ("Content2026!"),
        },
    )

    assert changed.status_code == 200

    return changed.json()["csrf_token"]


def test_creation_options_projection(
    content_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "list_creation_options",
        lambda settings: {
            "customers": [
                {
                    "business_id": ("fixture_pet_store"),
                    "display_name": ("小爪宠物店"),
                    "industry": ("宠物服务"),
                    "creation_ready": (True),
                    "speakers": [
                        {
                            "speaker_id": ("speaker_fixture"),
                            "display_name": ("王琳"),
                            "public_role": ("店主"),
                            "status": ("approved"),
                        }
                    ],
                }
            ],
            "ready_customer_count": 1,
        },
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.get("/api/create/options")

        assert response.status_code == 200

        body = response.json()

        assert body["ready_customer_count"] == 1

        assert body["customers"][0]["speakers"][0]["display_name"] == "王琳"


def test_capacity_preview_requires_csrf(
    content_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "preview_content_creation",
        lambda *args, **kwargs: {},
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.post(
            ("/api/create/" "capacity-preview"),
            json={
                "business_id": ("fixture_pet_store"),
                "speaker_id": ("speaker_fixture"),
                "profile": "mix",
                "quantity": 5,
            },
        )

        assert response.status_code == 403

        assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


@pytest.mark.parametrize("rollout", ["off", "validation", "on"])
def test_capacity_preview_projects_canonical_result(
    content_settings: Settings,
    monkeypatch,
    rollout: str,
):
    content_settings = replace(
        content_settings,
        novel_news_rollout=rollout,
        novel_news_validation_phones=("13900000000",),
    )
    calls = {}

    def fake_preview(
        settings,
        *,
        business_id,
        speaker_id,
        profile,
        quantity,
    ):
        calls.update(
            {
                "business_id": (business_id),
                "speaker_id": (speaker_id),
                "profile": profile,
                "quantity": quantity,
            }
        )

        return {
            "business": {
                "business_id": (business_id),
            },
            "speaker": {
                "speaker_id": (speaker_id),
            },
            "selection": {
                "profile": profile,
                "requested_quantity": (quantity),
            },
            "capacity": {
                "high_quality_novel_capacity": (3),
                "padding_allowed": (False),
            },
            "recommendation": {
                "status": ("capacity_limited"),
                "requested_quantity": (5),
                "recommended_quantity": (3),
                "can_continue": (True),
            },
            "authority": {
                "script_generation_performed": (False),
            },
        }

    monkeypatch.setattr(
        main_module,
        "preview_content_creation",
        fake_preview,
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        csrf = login(client)

        response = client.post(
            ("/api/create/" "capacity-preview"),
            headers={"X-CSRF-Token": (csrf)},
            json={
                "business_id": ("fixture_pet_store"),
                "speaker_id": ("speaker_fixture"),
                "profile": "mix",
                "quantity": 5,
            },
        )

        assert response.status_code == 200

        assert calls == {
            "business_id": ("fixture_pet_store"),
            "speaker_id": ("speaker_fixture"),
            "profile": "mix",
            "quantity": 5,
        }

        preview = response.json()["preview"]

        assert preview["recommendation"]["recommended_quantity"] == 3

        assert preview["capacity"]["padding_allowed"] is False


def test_generation_confirm_requires_csrf(
    content_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "confirm_content_creation",
        lambda *args, **kwargs: {},
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.post(
            "/api/create/confirm",
            json={
                "business_id": ("fixture_pet_store"),
                "speaker_id": ("speaker_fixture"),
                "profile": "mix",
                "requested_quantity": 5,
                "confirmed_quantity": 3,
                "idempotency_key": ("console_test_0001"),
            },
        )

        assert response.status_code == 403

        assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


def test_active_request_projection_found(
    content_settings: Settings,
    monkeypatch,
):
    projection = {
        "request_id": ("gen_fixture_001"),
        "business_id": ("fixture_pet_store"),
        "speaker_id": ("speaker_fixture"),
        "profile": "mix",
        "requested_quantity": 5,
        "confirmed_quantity": 3,
        "created_at": ("2026-09-17T10:00:00+00:00"),
        "lifecycle_status": "created",
        "handoff_ready": True,
        "handoff_status": ("source_authority_" "resolution_pending"),
        "next_action": ("RESOLVE_GENERATION_SOURCES"),
        "authority": {
            "script_generation_performed": False,
            "generation_batch_created": False,
            "content_ledger_written": False,
            "remote_model_called": False,
        },
    }

    calls = {}

    def fake_active(
        settings,
        business_id,
    ):
        calls["business_id"] = business_id

        return {"active_request": projection}

    monkeypatch.setattr(
        main_module,
        "get_active_generation_request",
        fake_active,
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.get(
            "/api/create/active-request",
            params={"business_id": ("fixture_pet_store")},
        )

        assert response.status_code == 200

        body = response.json()

        assert calls == {"business_id": ("fixture_pet_store")}

        assert body["active_request"]["request_id"] == "gen_fixture_001"

        assert body["active_request"]["confirmed_quantity"] == 3

        assert body["active_request"]["authority"]["remote_model_called"] is False


def test_active_request_projection_none(
    content_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "get_active_generation_request",
        lambda settings, business_id: {"active_request": None},
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.get(
            "/api/create/active-request",
            params={"business_id": ("fixture_pet_store")},
        )

        assert response.status_code == 200

        assert response.json()["active_request"] is None


def test_generation_confirm_projects_canonical_request(
    content_settings: Settings,
    monkeypatch,
):
    calls = {}

    def fake_confirm(
        settings,
        **kwargs,
    ):
        calls.update(kwargs)

        return {
            "request_id": ("gen_fixture_001"),
            "confirmed_quantity": 3,
            "recovered": False,
            "next_action": ("RESOLVE_GENERATION_SOURCES"),
            "authority": {
                "generation_request_created": (True),
                "source_matching_performed": (False),
                "script_generation_performed": (False),
                "content_ledger_written": (False),
                "remote_model_called": (False),
            },
        }

    monkeypatch.setattr(
        main_module,
        "confirm_content_creation",
        fake_confirm,
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        csrf = login(client)

        response = client.post(
            "/api/create/confirm",
            headers={"X-CSRF-Token": csrf},
            json={
                "business_id": ("fixture_pet_store"),
                "speaker_id": ("speaker_fixture"),
                "profile": "mix",
                "requested_quantity": 5,
                "confirmed_quantity": 3,
                "idempotency_key": ("console_test_0001"),
            },
        )

        assert response.status_code == 200

        result = response.json()["result"]

        assert result["request_id"] == "gen_fixture_001"

        assert result["confirmed_quantity"] == 3

        assert result["authority"]["script_generation_performed"] is False

        assert calls == {
            "business_id": ("fixture_pet_store"),
            "speaker_id": ("speaker_fixture"),
            "profile": "mix",
            "requested_quantity": 5,
            "confirmed_quantity": 3,
            "idempotency_key": ("console_test_0001"),
            "created_by_user_id": 1,
            "created_by_phone": "13800000000",
        }


def test_resolve_sources_requires_csrf(
    content_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "resolve_generation_sources",
        lambda *args, **kwargs: {},
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.post(
            "/api/create/gen_fixture_001/resolve-sources",
        )

        assert response.status_code == 403

        assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


@pytest.mark.parametrize(
    ("failure_code", "expected_message"),
    [
        ("PRODUCTION_PROFILE_REGISTRY_NOT_FOUND", "创作基础资料尚未就绪。"),
        ("CONTENT_HISTORY_WITHOUT_LEDGER", "历史内容记录需要核对。"),
        ("SOURCE_AUTHORITY_INVALID", "现有创作结构资料需要核对。"),
    ],
)
def test_mix_preview_fail_closed_error_is_safe_and_does_not_create_request(
    content_settings: Settings,
    monkeypatch,
    failure_code: str,
    expected_message: str,
):
    """Known authority/history gaps retain codes but not technical details."""
    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(content_settings.database_path, "13800000000")
        csrf = login(client)
        requests_root = content_settings.pipeline_root / "data" / "generation_requests"
        before_requests = sorted(requests_root.rglob("generation_request_v1.json"))
        monkeypatch.setattr(
            content_gateway_module.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=2,
                stdout=json.dumps({
                    "ok": False,
                    "code": failure_code,
                    "message": "Sensitive technical artifact path: C:\\fixture\\secret.json",
                }),
                stderr="",
            ),
        )
        response = client.post(
            "/api/create/capacity-preview",
            headers={"X-CSRF-Token": csrf},
            json={
                "business_id": "fixture_pet_store",
                "speaker_id": "speaker_fixture",
                "profile": "mix",
                "quantity": 4,
            },
        )

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == failure_code
    assert detail["message"] == expected_message
    assert "维护人员" in detail["next_action"]
    assert "C:\\fixture" not in str(detail)
    assert sorted(requests_root.rglob("generation_request_v1.json")) == before_requests


def test_resolve_sources_projects_canonical_result(
    content_settings: Settings,
    monkeypatch,
):
    calls = {}

    def fake_resolve(
        settings,
        request_id,
    ):
        calls["request_id"] = request_id

        return {
            "ok": True,
            "request_id": request_id,
            "source_plan_path": "fixture-plan",
            "source_plan_sha256": "a" * 64,
            "coverage_status": "supported",
            "coverage_code": ("research_coverage_" "supported"),
            "selected_pattern_count": 1,
            "eligible_case_count": 3,
            "remote_model_called": False,
            "script_generation_performed": False,
            "recovered": False,
        }

    monkeypatch.setattr(
        main_module,
        "resolve_generation_sources",
        fake_resolve,
    )

    with TestClient(main_module.build_app(content_settings)) as client:
        provision_user(
            content_settings.database_path,
            "13800000000",
        )

        csrf = login(client)

        response = client.post(
            "/api/create/gen_fixture_001/resolve-sources",
            headers={"X-CSRF-Token": csrf},
        )

        assert response.status_code == 200

        result = response.json()["result"]

        assert result["request_id"] == "gen_fixture_001"

        assert result["coverage_status"] == "supported"

        assert result["remote_model_called"] is False

        assert result["script_generation_performed"] is False

        assert calls == {"request_id": "gen_fixture_001"}
