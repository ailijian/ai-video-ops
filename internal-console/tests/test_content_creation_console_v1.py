from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import (
    TestClient,
)

from app import main as main_module
from app.auth_service import (
    provision_user,
)
from app.config import Settings


@pytest.fixture()
def content_settings(
    tmp_path: Path,
) -> Settings:
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
        session_cookie_name=("aivo_content_test"),
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


def test_capacity_preview_projects_canonical_result(
    content_settings: Settings,
    monkeypatch,
):
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
