from __future__ import annotations

from dataclasses import replace
from fastapi.testclient import TestClient
import pytest

from app import main as main_module
from app import background_task_service as tasks
from app.auth_service import provision_user
from app.canonical_gateway import CanonicalOperationError


def login(client: TestClient) -> str:
    response = client.post("/api/auth/login", json={"phone": "13800000000", "password": "123456"})
    assert response.status_code == 200
    csrf = response.json()["csrf_token"]
    changed = client.post("/api/auth/change-password", headers={"X-CSRF-Token": csrf}, json={
        "current_password": "123456", "new_password": "NovelNews2026!", "confirm_password": "NovelNews2026!",
    })
    assert changed.status_code == 200
    return changed.json()["csrf_token"]


def test_news_novel_preview_confirm_and_review_routes_are_distinct(settings, monkeypatch) -> None:
    settings = replace(settings, novel_news_rollout="on")
    calls = []
    monkeypatch.setattr(main_module, "preview_novel_news", lambda config, business, speaker: {
        "business_id": business, "speaker_id": speaker, "opportunities": [],
        "authority": {"generation_request_created": False, "remote_model_called": False},
    })

    def confirm(config, **kwargs):
        calls.append(("confirm", kwargs))
        return {"request_id": "gen_novel001"}

    def review(config, request_id, **kwargs):
        calls.append(("review", request_id, kwargs))
        return {"request_id": request_id, "human_gate": True}

    monkeypatch.setattr(main_module, "confirm_content_creation", confirm)
    monkeypatch.setattr(main_module, "review_novel_news", review)
    monkeypatch.setattr(main_module, "get_active_generation_request", lambda config, business, profile="mix": {
        "active_request": {"business_id": business, "profile": profile}
    })
    with TestClient(main_module.build_app(settings)) as client:
        provision_user(settings.database_path, "13800000000")
        csrf = login(client)
        assert client.post("/api/create/novel-news/preview", json={"business_id": "business", "speaker_id": "speaker"}).status_code == 403
        preview = client.post("/api/create/novel-news/preview", headers={"X-CSRF-Token": csrf}, json={
            "business_id": "business", "speaker_id": "speaker",
        })
        assert preview.status_code == 200
        assert preview.json()["projection"]["business_id"] == "business"
        active = client.get("/api/create/active-request", params={"business_id": "business", "profile": "news"})
        assert active.status_code == 200
        assert active.json()["active_request"]["profile"] == "news"
        confirm_response = client.post("/api/create/confirm", headers={"X-CSRF-Token": csrf}, json={
            "business_id": "business", "speaker_id": "speaker", "profile": "news",
            "requested_quantity": 1, "confirmed_quantity": 1,
            "selected_opportunity_id": "news-price-fixture", "idempotency_key": "novel_console_0001",
        })
        assert confirm_response.status_code == 200
        assert calls[0][1]["selected_opportunity_id"] == "news-price-fixture"
        review_response = client.post("/api/create/novel-news/gen_novel001/review", headers={"X-CSRF-Token": csrf}, json={
            "decisions": [{"beat_id": f"B{i:03d}", "decision": "approved"} for i in range(1, 5)],
        })
        assert review_response.status_code == 200
        assert calls[1][0] == "review"
        assert calls[1][2]["reviewer"] == "13800000000"


def test_unsupported_novel_news_stage_never_enqueues_background_task(settings, monkeypatch) -> None:
    settings = replace(settings, novel_news_rollout="on")
    monkeypatch.setattr(tasks, "novel_news_state", lambda config, request_id: {"stage": "blocked"})
    with pytest.raises(CanonicalOperationError) as exc:
        tasks.create_background_task(
            settings, operation="novel_news_generate", request_id="gen_novel001", created_by_user_id=1,
        )
    assert exc.value.code == "NEWS_NOVEL_STAGE_INVALID"
