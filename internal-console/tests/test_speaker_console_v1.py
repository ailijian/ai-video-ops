from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth_service import provision_user
from app.config import Settings
from app.main import build_app


@pytest.fixture()
def speaker_settings(
    tmp_path: Path,
) -> Settings:
    console_root = Path(__file__).resolve().parents[1]

    repo_root = console_root.parent

    pipeline_root = tmp_path / "pipeline"

    persona_path = (
        pipeline_root
        / "data"
        / "personas"
        / "fixture_pet_store"
        / "revision_0001"
        / "persona_v1.json"
    )

    persona_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    persona = {
        "schema_version": ("persona-v1.0"),
        "persona_id": ("fixture_pet_store"),
        "revision": 1,
        "persona_scope": ("business"),
        "lifecycle": {
            "status": ("approved"),
            "approved": True,
            "retired": False,
            "human_review_required": (True),
        },
        "facts": {
            "public_display_name": {
                "state": ("known"),
                "value": ("小爪宠物店"),
            },
            "industry": {
                "state": ("known"),
                "value": ("宠物服务"),
            },
        },
        "provenance": {
            "content_sha256": ("fixture"),
        },
        "approval": {
            "human_gate": True,
        },
    }
    persona_path.write_text(
        json.dumps(
            persona,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    persona_sha256 = hashlib.sha256(persona_path.read_bytes()).hexdigest()
    (persona_path.parent / "approval_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "persona-approval-receipt-v1.0",
                "persona_id": "fixture_pet_store",
                "revision": 1,
                "decision": "approved",
                "human_gate": True,
                "persona_sha256_after_approval": persona_sha256,
                "content_sha256": "fixture",
                "previous_approved_revision": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=pipeline_root,
        database_path=(tmp_path / "console.sqlite3"),
        python_executable=str(console_root / ".venv" / "Scripts" / "python.exe"),
        pipeline_python_executable=str(
            repo_root / "ops-pipeline" / ".venv" / "Scripts" / "python.exe"
        ),
        session_cookie_name=("aivo_speaker_test"),
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id=("fixture_pet_store"),
    )


@pytest.fixture()
def speaker_client(
    speaker_settings: Settings,
):
    with TestClient(build_app(speaker_settings)) as client:
        provision_user(
            speaker_settings.database_path,
            "13800000000",
        )

        yield client


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
        headers={"X-CSRF-Token": (csrf)},
        json={
            "current_password": ("123456"),
            "new_password": ("SpeakerConsole2026!"),
            "confirm_password": ("SpeakerConsole2026!"),
        },
    )

    assert changed.status_code == 200

    return changed.json()["csrf_token"]


def speaker_payload():
    return {
        "speaker_name": "王琳",
        "public_role": "店主",
        "speaker_type": ("owner_founder"),
        "materials": (
            "王琳是门店店主，"
            "日常亲自接待顾客，"
            "会检查宠物皮肤和毛发状态，"
            "并根据现场情况确认洗护方式。"
        ),
        "forbidden_claims": [
            "不得声称自己是兽医",
            "不得进行医疗诊断",
        ],
    }


def test_create_speaker_analysis_task_without_raw_materials_in_sqlite(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    payload = speaker_payload()

    response = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=payload,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["duplicate"] is False

    task = body["task"]

    assert task["task_type"] == "speaker_analysis"

    assert task["status"] == "queued"

    serialized = json.dumps(
        task["payload"],
        ensure_ascii=False,
    )

    assert payload["materials"] not in serialized

    request_path = Path(task["payload"]["request_path"])

    assert request_path.is_file()

    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert request["materials"] == payload["materials"]

    assert request["authority"]["media_rights_established"] is False


def test_duplicate_speaker_does_not_create_second_task(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    payload = speaker_payload()

    first = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": csrf},
        json=payload,
    ).json()

    second = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=payload,
    )

    assert second.status_code == 200

    body = second.json()

    assert body["duplicate"] is True

    assert body["existing_task"]["task_id"] == first["task"]["task_id"]

    tasks = speaker_client.get("/api/tasks").json()["tasks"]

    speaker_tasks = [
        task for task in tasks if (task["task_type"] == "speaker_analysis")
    ]

    assert len(speaker_tasks) == 1


def test_speaker_list_projects_pending_speaker(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    created = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=(speaker_payload()),
    ).json()

    response = speaker_client.get(("/api/customers/" "fixture_pet_store/" "speakers"))

    assert response.status_code == 200

    speakers = response.json()["speakers"]

    assert len(speakers) == 1

    assert speakers[0]["speaker_id"] == created["speaker_id"]

    assert speakers[0]["status"] == "analyzing"


def test_speaker_state_change_requires_csrf(
    speaker_client: TestClient,
):
    login(speaker_client)

    response = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        json=(speaker_payload()),
    )

    assert response.status_code == 403

    assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


def test_speaker_task_type_is_supported_by_database_migration(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    response = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=(speaker_payload()),
    )

    assert response.status_code == 200

    assert response.json()["task"]["task_type"] == "speaker_analysis"
