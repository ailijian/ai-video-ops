from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from conftest import login_and_change_password


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def post_unavailable(client: TestClient, path: str) -> int:
    return client.post(path, json={}).status_code


def test_01_case_analysis_does_not_auto_approve(client: TestClient, settings: Settings):
    csrf = login_and_change_password(client)
    before = sorted((settings.pipeline_root / "data" / "cases").glob("*/approval_receipt.json"))
    response = client.post(
        "/api/cases/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"url": "https://www.douyin.com/video/7999999999999999999"},
    )
    after = sorted((settings.pipeline_root / "data" / "cases").glob("*/approval_receipt.json"))
    assert response.status_code == 200
    assert response.json()["task"]["status"] == "queued"
    assert before == after


def test_02_persona_extraction_does_not_auto_approve(client: TestClient):
    login_and_change_password(client)
    assert post_unavailable(client, "/api/personas/extract-and-approve") in {404, 405}


def test_03_generated_content_does_not_auto_approve(client: TestClient):
    login_and_change_password(client)
    assert post_unavailable(client, "/api/content/generate-and-approve") in {404, 405}


def test_04_case_media_cannot_become_production_media(settings: Settings):
    companions = list(
        (settings.pipeline_root / "data" / "case_governance" / "cases").glob(
            "*/case_source_governance_companion_v1.json"
        )
    )
    assert companions
    for path in companions:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert value["media_reuse_rights"] == "not_established"
        assert value["production_footage_pool_eligible"] is False


def test_05_speaker_persona_does_not_create_media_rights(client: TestClient):
    login_and_change_password(client)
    status = client.get("/api/status/current").json()
    assert status["customer_truth"]["speaker_persona"]["status"] == "APPROVED"
    assert status["rights"]["speaker_media"] == "REVIEW_REQUIRED"


def test_06_profile_switch_does_not_reset_novelty(client: TestClient):
    login_and_change_password(client)
    status = client.get("/api/status/current").json()
    assert status["content"]["latest_exported_news"]["reuse_intent"] == "cross_profile_repurpose"
    assert status["content"]["latest_exported_news"]["semantic_novelty"] is False


def test_07_capacity_limit_blocks_padding_surface(client: TestClient):
    login_and_change_password(client)
    status = client.get("/api/status/current").json()
    assert status["content"]["remaining_high_quality_novel_capacity"] == 7
    assert post_unavailable(client, "/api/content/generate?quantity=8") in {404, 405}


def test_08_ui_status_does_not_become_second_authority(settings: Settings):
    from app.database import apply_migrations

    apply_migrations(settings.database_path, settings.console_root / "migrations")
    connection = sqlite3.connect(settings.database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert not tables.intersection({"customer_status", "project_status", "video_status"})


def test_09_export_retry_cannot_regenerate(client: TestClient, settings: Settings):
    login_and_change_password(client)
    batch = (
        settings.pipeline_root
        / "data"
        / "generation_batches"
        / "real_shufang_mix_003"
        / "revisions"
        / "revision_0004"
        / "approved_generation_batch_v1.json"
    )
    before = file_sha(batch)
    assert post_unavailable(client, "/api/exports/retry") in {404, 405}
    assert file_sha(batch) == before


def test_10_operational_hold_remains_active(client: TestClient, settings: Settings):
    control = (
        settings.pipeline_root
        / "data"
        / "operations"
        / "shufang_zhiyuan_community_canteen"
        / "operational_controls_v1.json"
    )
    before = file_sha(control)
    login_and_change_password(client)
    status = client.get("/api/workbench").json()["status"]
    assert status["operational_hold"]["active"] is True
    assert status["primary_next_action"] == "WAIT_FOR_OPERATOR_RELEASE"
    assert file_sha(control) == before
