from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.canonical_gateway import get_customer_status, list_cases
from app.config import Settings
from conftest import login_and_change_password


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_case_projection_requires_explicit_human_approval_receipt(settings: Settings):
    cases = list_cases(settings)
    assert cases
    for case in cases:
        receipt = settings.pipeline_root / "data" / "cases" / case["case_id"] / "approval_receipt.json"
        if case["status"] == "approved":
            assert receipt.exists()
        else:
            assert case["status"] == "awaiting_review"


def test_console_schema_contains_only_auth_session_and_task_projection(settings: Settings):
    from app.database import apply_migrations

    apply_migrations(settings.database_path, settings.console_root / "migrations")
    connection = sqlite3.connect(settings.database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert {"users", "sessions", "tasks", "schema_migrations"} <= tables
    forbidden = {"personas", "customer_truth", "content_ledger", "cases", "rights", "capacity"}
    assert not (tables & forbidden)


def test_real_status_preserves_business_wide_novelty_and_media_rights(settings: Settings):
    status = get_customer_status(settings, "shufang_zhiyuan_community_canteen")
    assert status["content"]["remaining_high_quality_novel_capacity"] == 7
    assert status["content"]["latest_exported_news"]["semantic_novelty"] is False
    assert status["rights"]["speaker_media"] == "REVIEW_REQUIRED"


def test_workbench_read_does_not_release_operational_hold_or_mutate_control(client: TestClient, settings: Settings):
    control = (
        settings.pipeline_root
        / "data"
        / "operations"
        / "shufang_zhiyuan_community_canteen"
        / "operational_controls_v1.json"
    )
    before = sha256(control)
    login_and_change_password(client)
    for _ in range(2):
        response = client.get("/api/workbench")
        assert response.status_code == 200
        assert response.json()["status"]["operational_hold"]["active"] is True
        assert response.json()["status"]["primary_next_action"] == "WAIT_FOR_OPERATOR_RELEASE"
    assert sha256(control) == before


def test_foundation_has_no_approval_export_or_generation_write_endpoints(client: TestClient):
    login_and_change_password(client)
    for path in (
        "/api/cases/7059858129298803968/approve",
        "/api/personas/approve",
        "/api/content/generate",
        "/api/exports/retry",
    ):
        response = client.post(path, json={})
        assert response.status_code in {404, 405}
