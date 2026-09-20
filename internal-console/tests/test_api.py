from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.task_service import (
    create_case_task, get_task,
    reconcile_approved_case_tasks, update_task,
)
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


def test_duplicate_uses_active_task_when_attempt_file_points_to_another_id(
    client: TestClient, settings,
):
    csrf = login_and_change_password(client)
    case_id = "7999999999999999976"
    url = f"https://www.douyin.com/video/{case_id}"
    created = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": url, "operator_profile_hint": "mix"},
    ).json()["task"]

    # A stale or separately recorded attempt must not hide the durable task.
    state_path = (
        settings.pipeline_root / "data" / "case_analysis_attempts" /
        case_id / "older-attempt" / "case_analysis_attempt_v1.json"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "attempt_id": "older-attempt",
        "status": "running",
        "updated_at": "2099-01-01T00:00:00Z",
    }), encoding="utf-8")

    duplicate = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": url},
    )
    assert duplicate.status_code == 200
    body = duplicate.json()
    assert body["duplicate"] is True
    assert body["state"] == "running"
    assert body["attempt_id"] == created["task_id"]
    assert body["existing_task"]["task_id"] == created["task_id"]

    # A retry of a failed historical attempt must also return the current task.
    state_path.write_text(json.dumps({
        "attempt_id": "older-attempt",
        "status": "failed",
        "updated_at": "2099-01-01T00:00:00Z",
    }), encoding="utf-8")
    retry = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": url, "reanalyze": True, "reason": "再次分析"},
    )
    assert retry.status_code == 200
    assert retry.json()["state"] == "running"
    assert retry.json()["existing_task"]["task_id"] == created["task_id"]
    assert retry.json()["reanalyze_blocked"] is True
    assert len(client.get("/api/tasks").json()["tasks"]) == 1


def test_orphan_running_attempt_does_not_claim_recoverable_progress(
    client: TestClient, settings,
):
    csrf = login_and_change_password(client)
    case_id = "7999999999999999977"
    state_path = (
        settings.pipeline_root / "data" / "case_analysis_attempts" /
        case_id / "orphan-attempt" / "case_analysis_attempt_v1.json"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "attempt_id": "orphan-attempt",
        "status": "running",
        "updated_at": "2099-01-01T00:00:00Z",
    }), encoding="utf-8")

    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": f"https://www.douyin.com/video/{case_id}", "operator_profile_hint": "mix"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CASE_TASK_PROGRESS_UNAVAILABLE"
    assert client.get("/api/tasks").json()["tasks"] == []


def test_review_closes_exact_running_attempt_and_late_worker_cannot_reopen_it(
    client: TestClient, settings, monkeypatch,
):
    csrf = login_and_change_password(client)
    case_id = "7999999999999999978"
    task = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": f"https://www.douyin.com/video/{case_id}", "operator_profile_hint": "mix"},
    ).json()["task"]
    update_task(settings.database_path, task["task_id"], status="running", progress=99)
    from app import main as main_module
    monkeypatch.setattr(main_module, "approve_case_candidate", lambda *args, **kwargs: {
        "case_id": case_id, "review": {"approved": True, "attempt_id": task["task_id"]},
    })
    approved = client.post(
        f"/api/cases/{case_id}/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "approve", "reason": "已核对"},
    )
    assert approved.status_code == 200
    for late_status in ("running", "awaiting_review", "failed"):
        update_task(settings.database_path, task["task_id"], status=late_status, progress=74)
    current = get_task(settings.database_path, task["task_id"])
    assert current["status"] == "completed"
    assert current["progress"] == 100
    assert current["stage"] == "已批准入库"


def test_approved_case_reconciles_only_its_own_attempt_and_preserves_failed_history(
    client: TestClient, settings,
):
    csrf = login_and_change_password(client)
    case_id = "7999999999999999979"
    url = f"https://www.douyin.com/video/{case_id}"
    old = create_case_task(
        settings.database_path, source_url=url, case_id=case_id,
        operator_profile_hint="mix", created_by_user_id=1,
    )
    update_task(settings.database_path, old["task_id"], status="failed", progress=74)
    approved = create_case_task(
        settings.database_path, source_url=url, case_id=case_id,
        operator_profile_hint="mix", reanalyze=True, created_by_user_id=1,
    )
    update_task(settings.database_path, approved["task_id"], status="awaiting_review", progress=100)
    case_dir = settings.pipeline_root / "data" / "cases" / case_id
    case_dir.mkdir(parents=True)
    (case_dir / "case_v1.json").write_text(json.dumps({
        "case_id": case_id,
        "lifecycle": {"status": "approved", "approved": True},
        "analysis_lineage": {"attempt_id": approved["task_id"]},
        "identity": {"platform": "douyin", "source_url": url},
    }), encoding="utf-8")
    (case_dir / "approval_receipt.json").write_text(json.dumps({
        "case_id": case_id, "decision": "approved", "human_gate": True,
    }), encoding="utf-8")

    # Read projections are correct even before the maintenance pass persists them.
    from app.canonical_gateway import get_case_detail
    approved_detail = get_case_detail(settings, case_id)
    assert approved_detail["status"] == "approved", approved_detail
    assert approved_detail["review"]["approved"] is True, approved_detail
    assert approved_detail["review"]["attempt_id"] == approved["task_id"]
    projected = {task["task_id"]: task for task in client.get("/api/tasks").json()["tasks"]}
    assert projected[approved["task_id"]]["status"] == "completed"
    assert projected[approved["task_id"]]["progress"] == 100
    assert projected[old["task_id"]]["status"] == "failed"
    assert projected[old["task_id"]]["current_case_status"] == "approved"
    detail = client.get(f"/api/tasks/{old['task_id']}").json()
    assert detail["task"]["status"] == "failed"
    assert detail["task"]["current_case_status"] == "approved"
    workbench = client.get("/api/workbench").json()
    recent = {task["task_id"]: task for task in workbench["recent_tasks"]}
    assert recent[approved["task_id"]]["status"] == "completed"

    assert reconcile_approved_case_tasks(settings) == 1
    assert get_task(settings.database_path, approved["task_id"])["status"] == "completed"
    assert get_task(settings.database_path, old["task_id"])["status"] == "failed"
    assert reconcile_approved_case_tasks(settings) == 0


def test_failed_attempt_points_to_new_active_progress_instead_of_another_retry(
    client: TestClient, settings,
):
    csrf = login_and_change_password(client)
    case_id = "7999999999999999980"
    url = f"https://www.douyin.com/video/{case_id}"
    old = create_case_task(
        settings.database_path, source_url=url, case_id=case_id,
        operator_profile_hint="mix", created_by_user_id=1,
    )
    update_task(settings.database_path, old["task_id"], status="failed", progress=74)
    current = create_case_task(
        settings.database_path, source_url=url, case_id=case_id,
        operator_profile_hint="mix", reanalyze=True, created_by_user_id=1,
    )
    old_detail = client.get(f"/api/tasks/{old['task_id']}").json()["task"]
    assert old_detail["status"] == "failed"
    assert old_detail["current_active_task_id"] == current["task_id"]
    retry = client.post(
        "/api/cases/analyze", headers={"X-CSRF-Token": csrf},
        json={"url": url, "reanalyze": True, "reason": "再次分析"},
    )
    assert retry.status_code == 200
    assert retry.json()["existing_task"]["task_id"] == current["task_id"]
    assert len(client.get("/api/tasks").json()["tasks"]) == 2


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
