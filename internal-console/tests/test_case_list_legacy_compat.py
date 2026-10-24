"""Historical Task FKs survive 001--003 -> 009 without inventing ownership."""
from dataclasses import replace
from collections import Counter

import pytest
from fastapi.testclient import TestClient
from app.auth_service import provision_user
from app.case_library_access import manage_reviewer
from app.database import apply_migrations, transaction
from app.main import build_app
from app.task_service import create_case_task
from test_case_intake_migration_v1 import legacy_database, snapshot, MIGRATIONS


@pytest.fixture
def legacy_node(settings, tmp_path):
    database, original = legacy_database(tmp_path / "legacy-node")
    statuses = ["completed"] * 13 + ["awaiting_review"] * 3 + ["failed"] * 10
    tasks = []
    for index, status in enumerate(statuses):
        case_id = str(7999999999999800000 + index)
        task = original if index == 0 else create_case_task(database,
            source_url="https://www.douyin.com/video/" + case_id,
            case_id=case_id, created_by_user_id=1, queue_max=100, gpu_pending_per_user_max=100)
        with transaction(database) as db:
            db.execute("UPDATE tasks SET status=?,created_by_user_id=1 WHERE task_id=?", (status, task["task_id"]))
        tasks.append(task)
    before = snapshot(database)
    apply_migrations(database, MIGRATIONS)
    migrated = snapshot(database)
    assert all(migrated[k] == v for k, v in before.items() if k != "schema_migrations")
    isolated = replace(settings, database_path=database, background_worker_enabled=False)
    application = build_app(isolated)
    with TestClient(application) as client:
        login = client.post("/api/auth/login", json={"phone": "19900001101", "password": "OfflineReview2026!"})
        changed = client.post("/api/auth/change-password", headers={"X-CSRF-Token": login.json()["csrf_token"]}, json={
            "current_password": "OfflineReview2026!", "new_password": "HistoricalList2026!", "confirm_password": "HistoricalList2026!"})
        assert changed.status_code == 200
        yield isolated, application, client, tasks


def test_migrated_26_tasks_without_excel_are_visible_and_never_become_shared(legacy_node):
    settings, _, client, tasks = legacy_node
    before = snapshot(settings.database_path)
    response = client.get("/api/cases?view=mine&page_size=50")
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 26
    assert Counter(row["status"] for row in result["cases"]) == {"completed": 13, "awaiting_review": 3, "failed": 10}
    assert {row["task_id"] for row in result["cases"]} == {task["task_id"] for task in tasks}
    assert not (settings.pipeline_root / "data/case_intake_imports").exists()
    assert client.get("/api/cases?view=shared").json()["total"] == 0
    assert snapshot(settings.database_path)["tasks"] == before["tasks"]
    assert client.get("/api/cases?view=mine&page_size=50").json() == result


def test_migrated_owner_privacy_orphan_and_reviewer_permissions(legacy_node):
    settings, application, client, tasks = legacy_node
    provision_user(settings.database_path, "19900001102")
    with TestClient(application) as other:
        login = other.post("/api/auth/login", json={"phone": "19900001102", "password": "123456"})
        changed = other.post("/api/auth/change-password", headers={"X-CSRF-Token": login.json()["csrf_token"]}, json={
            "current_password": "123456", "new_password": "HistoricalList2026!", "confirm_password": "HistoricalList2026!"})
        assert changed.status_code == 200
        assert other.get("/api/cases?view=mine").json()["total"] == 0
        assert other.get("/api/cases?view=review").status_code == 404
        assert other.get("/api/tasks/" + tasks[0]["task_id"]).status_code == 404
        manage_reviewer(settings, 2, action="grant", operator="synthetic-offline-maintenance", reason="Explicit isolated reviewer test")
        assert other.get("/api/tasks/" + tasks[0]["task_id"]).status_code == 200
        assert other.get("/api/cases?view=mine").json()["total"] == 0
    with transaction(settings.database_path) as db:
        db.execute("UPDATE tasks SET created_by_user_id=NULL WHERE task_id=?", (tasks[0]["task_id"],))
    assert client.get("/api/cases?view=mine&page_size=50").json()["total"] == 25
    assert client.get("/api/tasks/" + tasks[0]["task_id"]).status_code == 404


def test_old_intake_group_and_native_task_are_not_duplicated(legacy_node):
    settings, _, client, tasks = legacy_node
    with transaction(settings.database_path) as db:
        db.execute("INSERT INTO case_intake_groups VALUES (?,?,?,?,?)", ("intake-legacy-list", "legacy-list-operation", "synthetic-digest", 1, "2026-10-01T00:00:00Z"))
        db.execute("INSERT INTO case_intake_items(group_id,position,source_url,task_id,state) VALUES (?,?,?,?,?)", (
            "intake-legacy-list", 0, tasks[0]["payload"]["source_url"], tasks[0]["task_id"], "linked"))
    rows = client.get("/api/cases?view=mine&page_size=50").json()["cases"]
    assert len(rows) == 26
    assert sum(row.get("task_id") == tasks[0]["task_id"] for row in rows) == 1
