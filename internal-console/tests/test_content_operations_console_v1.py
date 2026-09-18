from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth_service import provision_user
from app.config import Settings


@pytest.fixture()
def operations_settings(
    tmp_path: Path,
) -> Settings:
    console_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )
    repo_root = console_root.parent

    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=(
            repo_root / "ops-pipeline"
        ),
        database_path=(
            tmp_path / "console.sqlite3"
        ),
        python_executable=str(
            console_root
            / ".venv"
            / "Scripts"
            / "python.exe"
        ),
        pipeline_python_executable=str(
            repo_root
            / "ops-pipeline"
            / ".venv"
            / "Scripts"
            / "python.exe"
        ),
        session_cookie_name="aivo_operations_test",
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id="unused",
    )


def login(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/auth/login",
        json={
            "phone": "13800000000",
            "password": "123456",
        },
    )

    assert response.status_code == 200

    csrf = response.json()["csrf_token"]

    changed = client.post(
        "/api/auth/change-password",
        headers={
            "X-CSRF-Token": csrf,
        },
        json={
            "current_password": "123456",
            "new_password": "Operations2026!",
            "confirm_password": "Operations2026!",
        },
    )

    assert changed.status_code == 200


def test_content_operations_api_is_authenticated_read_only_projection(
    operations_settings: Settings,
    monkeypatch,
):
    projected = {
        "schema_version": "content-operations-view-v1.0",
        "customer": {
            "business_id": "fixture",
            "display_name": "测试客户",
        },
        "authority": {
            "projection_only": True,
        },
    }

    monkeypatch.setattr(
        main_module,
        "get_content_operations_view",
        lambda settings, business_id: projected,
    )

    with TestClient(
        main_module.build_app(
            operations_settings
        )
    ) as client:
        provision_user(
            operations_settings.database_path,
            "13800000000",
        )

        login(client)

        response = client.get(
            "/api/customers/fixture/content-operations"
        )

        assert response.status_code == 200
        assert response.json() == projected
