from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth_service import provision_user
from app.config import Settings
from app.main import build_app


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    console_root = Path(__file__).resolve().parents[1]
    repo_root = console_root.parent
    fixture_root = (
        repo_root
        / "ops-pipeline"
        / "tests"
        / "fixtures"
        / "authority_baseline_v1"
    )
    pipeline_root = tmp_path / "ops-pipeline"
    shutil.copytree(fixture_root, pipeline_root)
    shutil.copytree(
        repo_root / "ops-pipeline" / "scripts",
        pipeline_root / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=pipeline_root,
        database_path=tmp_path / "console.sqlite3",
        python_executable=sys.executable,
        session_cookie_name="aivo_test_session",
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id="fixture_business_001",
    )


@pytest.fixture()
def client(settings: Settings):
    with TestClient(build_app(settings)) as test_client:
        provision_user(settings.database_path, "13800000000")
        yield test_client


def login_and_change_password(client: TestClient) -> str:
    login = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "123456"},
    )
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": "123456",
            "new_password": "ReviewConsole2026!",
            "confirm_password": "ReviewConsole2026!",
        },
    )
    assert changed.status_code == 200
    return changed.json()["csrf_token"]
