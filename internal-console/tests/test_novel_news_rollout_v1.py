from __future__ import annotations

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app import background_task_service as tasks
from app.auth_service import provision_user
from app.config import Settings
from app.novel_news_rollout import novel_news_available
from app.task_service import get_task


def login(client: TestClient, phone: str) -> str:
    response = client.post("/api/auth/login", json={"phone": phone, "password": "123456"})
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    changed = client.post("/api/auth/change-password", headers={"X-CSRF-Token": csrf}, json={
        "current_password": "123456", "new_password": "NovelRollout2026!", "confirm_password": "NovelRollout2026!",
    })
    assert changed.status_code == 200
    return changed.json()["csrf_token"]


def test_rollout_config_defaults_and_invalid_validation_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("AIVO_ENV_FILE", raising=False)
    monkeypatch.delenv("AIVO_NOVEL_NEWS_ROLLOUT", raising=False)
    monkeypatch.delenv("AIVO_NOVEL_NEWS_VALIDATION_PHONES", raising=False)
    assert Settings.from_environment().novel_news_rollout == "off"
    monkeypatch.setenv("AIVO_NOVEL_NEWS_ROLLOUT", "validation")
    with pytest.raises(ValueError, match="VALIDATION_PHONES"):
        Settings.from_environment()
    monkeypatch.setenv("AIVO_NOVEL_NEWS_VALIDATION_PHONES", " , ")
    with pytest.raises(ValueError, match="VALIDATION_PHONES"):
        Settings.from_environment()
    monkeypatch.setenv("AIVO_NOVEL_NEWS_VALIDATION_PHONES", "13800000000, 13900000000")
    configured = Settings.from_environment()
    assert configured.novel_news_validation_phones == ("13800000000", "13900000000")
    monkeypatch.setenv("AIVO_NOVEL_NEWS_ROLLOUT", "invalid")
    with pytest.raises(ValueError, match="ROLLOUT"):
        Settings.from_environment()
    assert not novel_news_available(replace(configured, novel_news_validation_phones=()), "13800000000")


def test_off_blocks_direct_novel_preview_mutations_and_recovery_without_touching_artifacts(settings, monkeypatch) -> None:
    assert settings.novel_news_rollout == "off"
    monkeypatch.setattr(main_module, "list_creation_options", lambda config: {"customers": []})
    monkeypatch.setattr(main_module, "preview_novel_news", lambda *args: pytest.fail("preview crossed rollout"))
    monkeypatch.setattr(main_module, "confirm_content_creation", lambda *args, **kwargs: pytest.fail("request crossed rollout"))
    monkeypatch.setattr(main_module, "review_novel_news", lambda *args, **kwargs: pytest.fail("review crossed rollout"))
    request_id = "gen_rollout001"
    request_path = settings.pipeline_root / "data/generation_requests" / request_id / "generation_request_v1.json"
    request_path.parent.mkdir(parents=True)
    request_path.write_text(json.dumps({
        "request_id": request_id, "target_profile": "news", "reuse_intent": "novel_content",
    }), encoding="utf-8")
    original = request_path.read_bytes()
    with TestClient(main_module.build_app(settings)) as client:
        provision_user(settings.database_path, "13800000000")
        csrf = login(client, "13800000000")
        headers = {"X-CSRF-Token": csrf}
        options = client.get("/api/create/options")
        assert options.status_code == 200 and options.json()["novel_news"]["available"] is False
        assert client.post("/api/create/novel-news/preview", headers=headers, json={
            "business_id": "business", "speaker_id": "speaker",
        }).status_code == 403
        assert client.post("/api/create/capacity-preview", headers=headers, json={
            "business_id": "business", "speaker_id": "speaker", "profile": "news", "quantity": 1,
        }).status_code == 403
        assert client.post("/api/create/confirm", headers=headers, json={
            "business_id": "business", "speaker_id": "speaker", "profile": "news",
            "requested_quantity": 1, "confirmed_quantity": 1,
            "selected_opportunity_id": "news-price-fixture", "idempotency_key": "rollout_001",
        }).status_code == 403
        for operation in ("generate", "export"):
            assert client.post(f"/api/create/novel-news/{request_id}/{operation}", headers=headers).status_code == 403
        assert client.post(f"/api/create/novel-news/{request_id}/review", headers=headers, json={
            "decisions": [{"beat_id": f"B{index:03d}", "decision": "approved"} for index in range(1, 5)],
        }).status_code == 403
        assert client.post(f"/api/create/{request_id}/resolve-sources", headers=headers).status_code == 403
        assert client.post(f"/api/create/news/{request_id}/resolve-plan", headers=headers).status_code == 403
        assert client.get("/api/create/active-request", params={"business_id": "business", "profile": "news"}).json() == {
            "active_request": None, "novel_news_unavailable": True,
        }
        state = client.get(f"/api/create/novel-news/{request_id}/state")
        assert state.status_code == 200 and state.json()["state"]["stage"] == "unavailable"
        assert client.get(f"/api/create/novel-news/{request_id}/excel").status_code == 403
    assert request_path.read_bytes() == original


def test_validation_allowlist_and_on_are_enforced_for_direct_api(settings, monkeypatch) -> None:
    monkeypatch.setattr(main_module, "list_creation_options", lambda config: {"customers": []})
    monkeypatch.setattr(main_module, "preview_novel_news", lambda config, business, speaker: {"business_id": business})
    monkeypatch.setattr(main_module, "confirm_content_creation", lambda config, **kwargs: {"request_id": "gen_rollout004"})
    confirm_payload = {
        "business_id": "business", "speaker_id": "speaker", "profile": "news",
        "requested_quantity": 1, "confirmed_quantity": 1,
        "selected_opportunity_id": "news-price-fixture", "idempotency_key": "rollout_confirm_001",
    }
    validation = replace(settings, novel_news_rollout="validation", novel_news_validation_phones=("13800000000",))
    with TestClient(main_module.build_app(validation)) as client:
        provision_user(settings.database_path, "13800000000")
        csrf = login(client, "13800000000")
        assert client.get("/api/create/options").json()["novel_news"] == {
            "available": True, "verification_badge": True,
        }
        assert client.post("/api/create/novel-news/preview", headers={"X-CSRF-Token": csrf}, json={
            "business_id": "business", "speaker_id": "speaker",
        }).status_code == 200
        assert client.post("/api/create/confirm", headers={"X-CSRF-Token": csrf}, json=confirm_payload).status_code == 200
    with TestClient(main_module.build_app(validation)) as client:
        provision_user(settings.database_path, "13900000000")
        csrf = login(client, "13900000000")
        assert client.get("/api/create/options").json()["novel_news"]["available"] is False
        assert client.post("/api/create/novel-news/preview", headers={"X-CSRF-Token": csrf}, json={
            "business_id": "business", "speaker_id": "speaker",
        }).status_code == 403
        assert client.post("/api/create/confirm", headers={"X-CSRF-Token": csrf}, json=confirm_payload).status_code == 403
    enabled = replace(settings, novel_news_rollout="on", novel_news_validation_phones=())
    with TestClient(main_module.build_app(enabled)) as client:
        provision_user(settings.database_path, "13700000000")
        csrf = login(client, "13700000000")
        assert client.get("/api/create/options").json()["novel_news"] == {
            "available": True, "verification_badge": False,
        }
        assert client.post("/api/create/novel-news/preview", headers={"X-CSRF-Token": csrf}, json={
            "business_id": "business", "speaker_id": "speaker",
        }).status_code == 200
        assert client.post("/api/create/confirm", headers={"X-CSRF-Token": csrf}, json=confirm_payload).status_code == 200


def test_off_keeps_repurpose_preview_request_plan_review_and_export(settings, monkeypatch) -> None:
    monkeypatch.setattr(main_module, "preview_news_creation", lambda *args, **kwargs: {"available": True})
    monkeypatch.setattr(main_module, "create_news_request", lambda *args, **kwargs: {"request_id": "news_rollout_001"})
    monkeypatch.setattr(main_module, "submit_news_review", lambda *args, **kwargs: {"approved": True})
    with TestClient(main_module.build_app(settings)) as client:
        provision_user(settings.database_path, "13800000000")
        headers = {"X-CSRF-Token": login(client, "13800000000")}
        assert client.post("/api/create/news/preview", headers=headers, json={
            "business_id": "business", "speaker_id": "speaker",
        }).status_code == 200
        assert client.post("/api/create/news/request", headers=headers, json={
            "business_id": "business", "speaker_id": "speaker", "source_content_id": "existing_content",
            "idempotency_key": "repurpose_rollout_001",
        }).status_code == 200
        assert client.post("/api/create/news/news_rollout_001/resolve-plan", headers=headers).status_code == 200
        assert client.post("/api/create/news/news_rollout_001/review", headers=headers, json={
            "items": [{"slot_id": "S001", "decision": "approved", "approved_text": "已有价格信息", "note": ""}],
        }).status_code == 200
        assert client.post("/api/create/news/news_rollout_001/export", headers=headers).status_code == 200


def test_queued_novel_task_does_not_run_after_rollout_switches_off(settings, monkeypatch) -> None:
    enabled = replace(settings, novel_news_rollout="on", background_worker_enabled=False)
    monkeypatch.setattr(tasks, "novel_news_state", lambda config, request_id: {"stage": "generation"})
    from app.database import apply_migrations
    apply_migrations(settings.database_path, settings.console_root / "migrations")
    provision_user(settings.database_path, "13800000000")
    task = tasks.create_background_task(
        enabled, operation="novel_news_generate", request_id="gen_rollout002", created_by_user_id=1,
    )
    called: list[str] = []
    blocked = replace(settings, novel_news_rollout="off", background_worker_enabled=False)
    runner = tasks.BackgroundTaskRunner(blocked, handlers={
        "novel_news_generate": lambda config, request_id: called.append(request_id) or {},
    })
    try:
        runner._run(task["task_id"])
    finally:
        runner.close()
    assert called == []
    assert get_task(settings.database_path, task["task_id"])["error_code"] == "NOVEL_NEWS_NOT_AVAILABLE"

    validation = replace(settings, novel_news_rollout="validation", novel_news_validation_phones=("13800000000",))
    allowed_task = tasks.create_background_task(
        validation, operation="novel_news_generate", request_id="gen_rollout003", created_by_user_id=1,
    )
    allowed_runner = tasks.BackgroundTaskRunner(validation, handlers={
        "novel_news_generate": lambda config, request_id: called.append(request_id) or {},
    })
    try:
        allowed_runner._run(allowed_task["task_id"])
    finally:
        allowed_runner.close()
    assert called == ["gen_rollout003"]
    assert get_task(settings.database_path, allowed_task["task_id"])["status"] == "completed"
