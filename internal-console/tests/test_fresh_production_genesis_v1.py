from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth_service import provision_user
from app.config import Settings


@pytest.fixture()
def empty_settings(tmp_path: Path) -> Settings:
    console_root = Path(__file__).resolve().parents[1]
    repo_root = console_root.parent
    pipeline_root = tmp_path / "ops-pipeline"
    pipeline_root.mkdir(parents=True)
    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=pipeline_root,
        database_path=tmp_path / "console.sqlite3",
        python_executable=sys.executable,
        pipeline_python_executable=None,
        session_cookie_name="aivo_fresh_genesis_test",
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        background_worker_enabled=False,
        default_business_id=None,
    )


def login_and_change_password(client: TestClient) -> str:
    login = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "123456"},
    )
    assert login.status_code == 200
    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": login.json()["csrf_token"]},
        json={
            "current_password": "123456",
            "new_password": "FreshGenesis2026!",
            "confirm_password": "FreshGenesis2026!",
        },
    )
    assert changed.status_code == 200
    return changed.json()["csrf_token"]


def test_fresh_empty_node_login_and_workbench_are_available(
    empty_settings: Settings,
):
    with TestClient(main_module.build_app(empty_settings)) as client:
        provision_user(empty_settings.database_path, "13800000000")
        csrf = login_and_change_password(client)

        workbench = client.get("/api/workbench")
        cases = client.get("/api/cases")
        customers = client.get("/api/customers")
        first_case = client.post(
            "/api/cases/analyze",
            headers={"X-CSRF-Token": csrf},
            json={"url": "https://www.douyin.com/video/7999999999999999123"},
        )
        first_customer = client.post(
            "/api/customers/analyze",
            headers={"X-CSRF-Token": csrf},
            json={
                "customer_name": "Fresh Production Customer",
                "industry": "local_service",
                "materials": "Fresh Production 的首个客户资料，仅用于隔离测试。",
            },
        )

    assert workbench.status_code == 200
    body = workbench.json()
    assert body["has_customers"] is False
    assert body["status"] is None
    assert body["customers"] == []
    assert body["customer_selection"]["selected_business_id"] is None
    assert body["attention"] == {
        "case_reviews": 0,
        "persona_reviews": 0,
        "content_reviews": 0,
        "running_tasks": 0,
    }
    assert body["recent_tasks"] == []
    assert body["capabilities"]["add_case"]["available"] is True
    assert body["capabilities"]["new_customer"]["available"] is True
    assert body["capabilities"]["content_creation"]["available"] is False
    assert cases.status_code == 200
    assert cases.json()["cases"] == []
    assert customers.status_code == 200
    assert customers.json()["customers"] == []
    assert first_case.status_code == 200
    assert first_case.json()["task"]["status"] == "queued"
    assert first_customer.status_code == 200
    assert first_customer.json()["task"]["status"] == "queued"


def test_current_status_requires_customer_or_accepts_explicit_business_id(
    empty_settings: Settings,
    monkeypatch,
):
    calls = []
    monkeypatch.setattr(
        main_module,
        "get_customer_status",
        lambda settings, business_id: (
            calls.append(business_id)
            or {"business": {"business_id": business_id}}
        ),
    )

    with TestClient(main_module.build_app(empty_settings)) as client:
        provision_user(empty_settings.database_path, "13800000000")
        login_and_change_password(client)

        missing = client.get("/api/status/current")
        explicit = client.get(
            "/api/status/current?business_id=business_explicit"
        )

    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "CURRENT_CUSTOMER_REQUIRED"
    assert explicit.status_code == 200
    assert explicit.json()["business"]["business_id"] == "business_explicit"
    assert calls == ["business_explicit"]


def test_one_customer_resolves_but_multiple_customers_do_not_pick_first(
    empty_settings: Settings,
    monkeypatch,
):
    customers = [
        {
            "business_id": "business_one",
            "display_name": "唯一客户",
            "status": "approved",
        }
    ]
    calls = []
    monkeypatch.setattr(
        main_module,
        "list_customers",
        lambda settings: list(customers),
    )
    monkeypatch.setattr(
        main_module,
        "get_customer_status",
        lambda settings, business_id: (
            calls.append(business_id)
            or {"business": {"business_id": business_id}}
        ),
    )
    monkeypatch.setattr(
        main_module,
        "list_creation_options",
        lambda settings: {"ready_customer_count": 0},
    )
    monkeypatch.setattr(main_module, "speaker_attention_count", lambda settings: 0)

    with TestClient(main_module.build_app(empty_settings)) as client:
        provision_user(empty_settings.database_path, "13800000000")
        login_and_change_password(client)

        one = client.get("/api/workbench")
        customers[:] = [
            {
                "business_id": "business_z",
                "display_name": "客户 Z",
                "status": "approved",
            },
            {
                "business_id": "business_a",
                "display_name": "客户 A",
                "status": "approved",
            },
        ]
        calls.clear()
        multiple = client.get("/api/workbench")

    assert one.status_code == 200
    assert one.json()["status"]["business"]["business_id"] == "business_one"
    assert one.json()["customer_selection"]["source"] == "only_customer"
    assert multiple.status_code == 200
    assert multiple.json()["has_customers"] is True
    assert multiple.json()["status"] is None
    assert multiple.json()["customer_selection"]["selected_business_id"] is None
    assert multiple.json()["customer_selection"]["error"]["code"] == (
        "CURRENT_CUSTOMER_REQUIRED"
    )
    assert calls == []


def test_configured_default_is_convenience_and_invalid_value_creates_no_authority(
    empty_settings: Settings,
    tmp_path: Path,
    monkeypatch,
):
    customers = [
        {
            "business_id": "business_a",
            "display_name": "客户 A",
            "status": "approved",
        },
        {
            "business_id": "business_b",
            "display_name": "客户 B",
            "status": "approved",
        },
    ]
    calls = []
    monkeypatch.setattr(main_module, "list_customers", lambda settings: customers)
    monkeypatch.setattr(
        main_module,
        "get_customer_status",
        lambda settings, business_id: (
            calls.append(business_id)
            or {"business": {"business_id": business_id}}
        ),
    )
    monkeypatch.setattr(
        main_module,
        "list_creation_options",
        lambda settings: {"ready_customer_count": 0},
    )
    monkeypatch.setattr(main_module, "speaker_attention_count", lambda settings: 0)

    configured = replace(
        empty_settings,
        database_path=tmp_path / "configured.sqlite3",
        session_cookie_name="aivo_configured_customer_test",
        default_business_id="business_b",
    )
    with TestClient(main_module.build_app(configured)) as client:
        provision_user(configured.database_path, "13800000000")
        login_and_change_password(client)
        selected = client.get("/api/workbench")

    assert selected.status_code == 200
    assert selected.json()["status"]["business"]["business_id"] == "business_b"
    assert selected.json()["customer_selection"]["source"] == "configured_default"
    assert calls == ["business_b"]

    calls.clear()
    invalid = replace(
        empty_settings,
        database_path=tmp_path / "invalid.sqlite3",
        session_cookie_name="aivo_invalid_customer_test",
        default_business_id="missing_business",
    )
    with TestClient(main_module.build_app(invalid)) as client:
        provision_user(invalid.database_path, "13800000000")
        login_and_change_password(client)
        degraded = client.get("/api/workbench")
        invalid_current = client.get("/api/status/current")

    assert degraded.status_code == 200
    assert degraded.json()["has_customers"] is True
    assert degraded.json()["status"] is None
    assert degraded.json()["customer_selection"]["selected_business_id"] is None
    assert degraded.json()["customer_selection"]["error"]["code"] == (
        "CONFIGURED_CUSTOMER_NOT_FOUND"
    )
    assert invalid_current.status_code == 409
    assert invalid_current.json()["detail"]["code"] == (
        "CONFIGURED_CUSTOMER_NOT_FOUND"
    )
    assert calls == []


def test_no_legacy_customer_is_a_configuration_default(
    empty_settings: Settings,
    monkeypatch,
):
    config_source = (
        empty_settings.console_root / "app" / "config.py"
    ).read_text(encoding="utf-8")

    assert empty_settings.default_business_id is None
    assert "shufang_zhiyuan_community_canteen" not in config_source

    monkeypatch.delenv("AIVO_ENV_FILE", raising=False)
    monkeypatch.delenv("AIVO_DEFAULT_BUSINESS_ID", raising=False)
    assert Settings.from_environment().default_business_id is None

    monkeypatch.setenv("AIVO_DEFAULT_BUSINESS_ID", "  business_optional  ")
    assert Settings.from_environment().default_business_id == "business_optional"


def test_workbench_frontend_has_formal_empty_state_and_guarded_creation(
    empty_settings: Settings,
):
    app_source = (
        empty_settings.console_root / "static" / "assets" / "app.js"
    ).read_text(encoding="utf-8")

    assert "今天需要做什么" in app_source
    assert "还没有客户" in app_source
    assert "从添加案例或建立第一个客户开始。" in app_source
    assert "添加案例" in app_source
    assert "新建客户" in app_source
    assert "quick-card-disabled" in app_source
    assert "需要已批准的客户与出镜人" in app_source
    assert "书房市集志泉社区食堂" not in app_source
