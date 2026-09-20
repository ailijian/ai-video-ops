from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import login_and_change_password


def test_first_login_forces_password_change_then_exposes_fixture_workbench(
    client: TestClient,
):
    login = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "123456"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=strict" in login.headers["set-cookie"]

    blocked = client.get("/api/workbench")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "PASSWORD_CHANGE_REQUIRED"

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
    assert changed.json()["user"]["must_change_password"] is False

    workbench = client.get("/api/workbench")
    assert workbench.status_code == 200
    status = workbench.json()["status"]
    assert status["primary_next_action"] == "WAIT_FOR_OPERATOR_RELEASE"
    assert status["operational_hold"]["active"] is True
    assert status["content"]["remaining_high_quality_novel_capacity"] == 7


def test_login_failure_does_not_reveal_account_existence(client: TestClient):
    known = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "wrong-password"},
    )
    unknown = client.post(
        "/api/auth/login",
        json={"phone": "13999999999", "password": "wrong-password"},
    )
    assert known.status_code == unknown.status_code == 401
    assert known.json()["detail"]["message"] == unknown.json()["detail"]["message"]


def test_state_change_requires_csrf(client: TestClient):
    login = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "123456"},
    )
    assert login.status_code == 200
    rejected = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "123456",
            "new_password": "ReviewConsole2026!",
            "confirm_password": "ReviewConsole2026!",
        },
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


def test_duplicate_case_resolves_without_creating_a_task(client: TestClient):
    csrf = login_and_change_password(client)
    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "url": "https://www.douyin.com/video/7999999999999999901?share=another-form"
        },
    )
    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert response.json()["state"] == "approved"
    assert response.json()["duplicate_kind"] == "source_identity"
    assert response.json()["can_reanalyze"] is False
    assert response.json()["existing_case"]["case_id"] == "7999999999999999901"
    assert client.get("/api/tasks").json()["tasks"] == []


def test_novel_case_creates_one_recoverable_canonical_task(client: TestClient):
    csrf = login_and_change_password(client)
    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": "https://www.douyin.com/video/7999999999999999999", "operator_profile_hint": "mix"},
    )
    assert response.status_code == 200
    assert response.json()["duplicate"] is False
    task = response.json()["task"]
    assert task["status"] == "queued"
    assert task["subject_ref"] == "7999999999999999999"
    assert task["payload"]["operator_profile_hint"] == "mix"
    assert task["created_by"]["phone"] == "13800000000"

    duplicate = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": "https://www.douyin.com/video/7999999999999999999?share=1"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["existing_task"]["task_id"] == task["task_id"]
    assert len(client.get("/api/tasks").json()["tasks"]) == 1


def test_task_projection_survives_a_new_app_instance(client: TestClient, settings):
    csrf = login_and_change_password(client)
    created = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": "https://www.douyin.com/video/7999999999999999998", "operator_profile_hint": "mix"},
    ).json()["task"]

    from app.main import build_app

    with TestClient(build_app(settings)) as restarted:
        login = restarted.post(
            "/api/auth/login",
            json={"phone": "13800000000", "password": "ReviewConsole2026!"},
        )
        assert login.status_code == 200
        recovered = restarted.get(f"/api/tasks/{created['task_id']}")
        assert recovered.status_code == 200
        assert recovered.json()["task"]["status"] == "queued"
