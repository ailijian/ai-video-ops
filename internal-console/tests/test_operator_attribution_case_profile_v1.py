from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
import app.main as main_module

from app.auth_service import provision_user
from app.database import connect
from app.operator_projection import (
    case_reanalysis_hint,
    completed_operation_actor,
    operator_activity,
    original_task_actor,
    request_actor,
)
from app.task_service import create_case_task
from conftest import login_and_change_password


def test_new_case_requires_explicit_hint(client):
    csrf = login_and_change_password(client)
    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": "https://www.douyin.com/video/7999999999999999911"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CASE_OPERATOR_PROFILE_HINT_REQUIRED"
    assert client.get("/api/tasks").json()["tasks"] == []


def test_activity_api_filter_and_shared_workspace(client, settings):
    csrf = login_and_change_password(client)
    provision_user(settings.database_path, "13800000002")
    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "url": "https://www.douyin.com/video/7999999999999999917",
            "operator_profile_hint": "hybrid",
        },
    )
    assert response.status_code == 200
    task_id = response.json()["task"]["task_id"]
    accounts = client.get("/api/tasks/activity").json()["accounts"]
    first_id = next(
        account["user_id"]
        for account in accounts
        if account["phone_masked"] == "138****0000"
    )
    second_id = next(
        account["user_id"]
        for account in accounts
        if account["phone_masked"] == "138****0002"
    )
    assert any(
        event["source"] == task_id
        for event in client.get("/api/tasks/activity").json()["events"]
    )
    assert [
        event["source"]
        for event in client.get(f"/api/tasks/activity?user_id={first_id}").json()[
            "events"
        ]
    ] == [task_id]
    assert client.get(f"/api/tasks/activity?user_id={second_id}").json()["events"] == []
    # Attribution is a filter, not authorization: the same session sees shared tasks.
    assert client.get("/api/tasks").json()["tasks"][0]["task_id"] == task_id


@pytest.mark.parametrize("hint", ["mix", "news", "hybrid", "uncertain"])
def test_case_hint_is_durable_operator_input_not_analysis_truth(client, hint):
    csrf = login_and_change_password(client)
    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "url": "https://www.douyin.com/video/7999999999999999912",
            "operator_profile_hint": hint,
        },
    )
    assert response.status_code == 200
    task = response.json()["task"]
    assert task["payload"]["operator_profile_hint"] == hint
    assert "profile" not in task["payload"]
    assert task["created_by"]["phone"] == "13800000000"


def test_legacy_case_task_does_not_infer_operator_hint(settings):
    from app.database import apply_migrations

    apply_migrations(
        settings.database_path, Path(__file__).resolve().parents[1] / "migrations"
    )
    task = create_case_task(
        settings.database_path,
        source_url="https://www.douyin.com/video/7999999999999999913",
        case_id="7999999999999999913",
        operator_profile_hint="uncertain",
    )
    connection = connect(settings.database_path)
    try:
        connection.execute(
            "UPDATE tasks SET payload_json = ? WHERE task_id = ?",
            (json.dumps({"profile": "mix"}), task["task_id"]),
        )
        connection.commit()
    finally:
        connection.close()
    assert case_reanalysis_hint(settings.database_path, task["subject_ref"]) is None


def test_legacy_review_reanalysis_rejects_before_mutation(client, monkeypatch):
    csrf = login_and_change_password(client)
    monkeypatch.setattr(
        main_module, "get_case_detail", lambda *_: {"operator_profile_hint": None}
    )
    monkeypatch.setattr(
        main_module,
        "record_case_review_decision",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("must not mutate")
        ),
    )
    response = client.post(
        "/api/cases/7999999999999999918/review",
        headers={"X-CSRF-Token": csrf},
        json={"decision": "reanalyze", "reason": "重新检查"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CASE_OPERATOR_PROFILE_HINT_REQUIRED"


def test_original_actor_and_activity_filter_use_existing_task_truth(settings):
    from app.database import apply_migrations

    apply_migrations(
        settings.database_path, Path(__file__).resolve().parents[1] / "migrations"
    )
    provision_user(settings.database_path, "13800000001")
    provision_user(settings.database_path, "13800000002")
    connection = connect(settings.database_path)
    try:
        first_id = connection.execute(
            "SELECT id FROM users WHERE phone = ?", ("13800000001",)
        ).fetchone()["id"]
        second_id = connection.execute(
            "SELECT id FROM users WHERE phone = ?", ("13800000002",)
        ).fetchone()["id"]
    finally:
        connection.close()
    one = create_case_task(
        settings.database_path,
        source_url="https://www.douyin.com/video/7999999999999999914",
        case_id="7999999999999999914",
        operator_profile_hint="mix",
        created_by_user_id=first_id,
    )
    two = create_case_task(
        settings.database_path,
        source_url="https://www.douyin.com/video/7999999999999999915",
        case_id="7999999999999999915",
        operator_profile_hint="news",
        created_by_user_id=second_id,
    )
    assert (
        original_task_actor(
            settings.database_path, "case_analysis", one["subject_ref"]
        )["phone"]
        == "13800000001"
    )
    all_events = operator_activity(settings.database_path, settings.pipeline_root)
    only_second = operator_activity(
        settings.database_path, settings.pipeline_root, second_id
    )
    assert (
        len(
            [
                event
                for event in all_events["events"]
                if event["source"] in {one["task_id"], two["task_id"]}
            ]
        )
        == 2
    )
    assert [event["source"] for event in only_second["events"]] == [two["task_id"]]
    assert only_second["events"][0]["actor"]["phone_masked"] == "138****0002"


def test_historical_actor_is_unknown_not_guessed(settings):
    from app.database import apply_migrations

    apply_migrations(
        settings.database_path, Path(__file__).resolve().parents[1] / "migrations"
    )
    create_case_task(
        settings.database_path,
        source_url="https://www.douyin.com/video/7999999999999999916",
        case_id="7999999999999999916",
        operator_profile_hint="uncertain",
    )
    assert (
        original_task_actor(
            settings.database_path, "case_analysis", "7999999999999999916"
        )
        is None
    )
    assert request_actor({"created_at": "2026-09-20T00:00:00Z"}) is None


def test_legacy_approved_case_is_read_without_backfill(client, settings):
    case_path = (
        settings.pipeline_root
        / "data"
        / "cases"
        / "7999999999999999901"
        / "case_v1.json"
    )
    before = hashlib.sha256(case_path.read_bytes()).hexdigest()
    login_and_change_password(client)
    detail = client.get("/api/cases/7999999999999999901")
    assert detail.status_code == 200
    assert detail.json()["operator_profile_hint"] is None
    assert detail.json()["submitted_by"] is None
    assert hashlib.sha256(case_path.read_bytes()).hexdigest() == before


def test_export_actor_is_actual_completed_task_not_request_creator(settings):
    from app.database import apply_migrations
    from app.background_task_service import create_background_task

    apply_migrations(
        settings.database_path, Path(__file__).resolve().parents[1] / "migrations"
    )
    provision_user(settings.database_path, "13800000001")
    provision_user(settings.database_path, "13800000002")
    connection = connect(settings.database_path)
    try:
        creator_id = connection.execute(
            "SELECT id FROM users WHERE phone = ?", ("13800000001",)
        ).fetchone()["id"]
        exporter_id = connection.execute(
            "SELECT id FROM users WHERE phone = ?", ("13800000002",)
        ).fetchone()["id"]
    finally:
        connection.close()
    task = create_background_task(
        settings,
        operation="mix_export",
        request_id="gen_fixture_001",
        created_by_user_id=exporter_id,
    )
    connection = connect(settings.database_path)
    try:
        connection.execute(
            "UPDATE tasks SET status = 'completed' WHERE task_id = ?",
            (task["task_id"],),
        )
        connection.commit()
    finally:
        connection.close()
    assert (
        request_actor(
            {"created_by_user_id": creator_id, "created_by_phone": "13800000001"}
        )["user_id"]
        == creator_id
    )
    assert (
        completed_operation_actor(
            settings.database_path, "gen_fixture_001", "mix_export"
        )["user_id"]
        == exporter_id
    )
