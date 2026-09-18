from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.auth_service import provision_user
from app.config import Settings


@pytest.fixture()
def news_settings(
    tmp_path: Path,
) -> Settings:
    console_root = (
        Path(__file__).resolve().parents[1]
    )
    repo_root = console_root.parent

    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=(
            repo_root
            / "ops-pipeline"
        ),
        database_path=(
            tmp_path
            / "console.sqlite3"
        ),
        python_executable=str(
            console_root
            / ".venv"
            / "Scripts"
            / "python.exe"
        ),
        pipeline_python_executable=str(
            repo_root
            / "ops-pipeline"
            / ".venv"
            / "Scripts"
            / "python.exe"
        ),
        session_cookie_name=(
            "aivo_news_delivery_test"
        ),
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id="unused",
    )


def login(
    client: TestClient,
) -> str:
    response = client.post(
        "/api/auth/login",
        json={
            "phone": "13800000000",
            "password": "123456",
        },
    )
    assert response.status_code == 200

    csrf = response.json()[
        "csrf_token"
    ]

    changed = client.post(
        "/api/auth/change-password",
        headers={
            "X-CSRF-Token": csrf
        },
        json={
            "current_password": "123456",
            "new_password": "News2026!",
            "confirm_password": "News2026!",
        },
    )
    assert changed.status_code == 200

    return changed.json()[
        "csrf_token"
    ]


def fake_state(
    request_id: str = (
        "news_fixture_001"
    ),
) -> dict:
    return {
        "request_id": request_id,
        "business_id": (
            "fixture_business"
        ),
        "speaker_id": (
            "fixture_speaker"
        ),
        "profile": "news",
        "profile_label": (
            "News 新闻体"
        ),
        "validated_slice": (
            "price_offer_cross_profile_repurpose"
        ),
        "source_content": {
            "content_id": (
                "mix_fixture-C001"
            ),
            "title": "加工费怎么算？",
            "central_claim": (
                "素菜通常8-10元，"
                "清蒸约15元，"
                "红烧约18元左右。"
            ),
            "status": "exported",
        },
        "recommended_slot_count": 6,
        "plan": {
            "ready": True,
            "slot_count": 6,
            "slots": [
                {
                    "slot_id": "S001",
                    "order": 1,
                    "semantic_role": (
                        "price_offer_first_semantic_anchor"
                    ),
                    "proposed_text": (
                        "素菜加工费通常8-10元"
                    ),
                    "source_known_fact": (
                        "素菜加工费通常 8-10 元"
                    ),
                    "source_field": (
                        "pricing_facts"
                    ),
                    "price_or_offer_anchor": True,
                    "soft_length_recommendation": {
                        "warning": True,
                    },
                }
            ],
        },
        "review": {
            "completed": False,
            "approved": False,
            "approved_slot_count": 0,
        },
        "export": {
            "completed": False,
            "presentation_history_closed": False,
            "slot_count": 0,
        },
        "next_action": "HUMAN_REVIEW",
        "stop_point_reached": False,
        "authority": {
            "semantic_novelty": False,
            "remote_model_called": False,
        },
    }


def test_news_active_route(
    news_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "get_active_news_request",
        lambda settings, business_id: {
            "active_request": {
                "request_id": (
                    "news_fixture_001"
                ),
                "business_id": business_id,
                "speaker_id": (
                    "fixture_speaker"
                ),
            }
        },
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        login(client)

        response = client.get(
            "/api/create/news/active"
            "?business_id=fixture_business"
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            response.json()[
                "active_request"
            ][
                "request_id"
            ]
            == "news_fixture_001"
        )


def test_news_preview_requires_csrf(
    news_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "preview_news_creation",
        lambda *args, **kwargs: {},
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        login(client)

        response = client.post(
            "/api/create/news/preview",
            json={
                "business_id": (
                    "fixture_business"
                ),
                "speaker_id": (
                    "fixture_speaker"
                ),
            },
        )

        assert (
            response.status_code
            == 403
        )


def test_news_preview_route(
    news_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "preview_news_creation",
        lambda settings, **kwargs: {
            "available": True,
            "eligible_source_count": 1,
            "eligible_sources": [
                {
                    "source_content_id": (
                        "mix_fixture-C001"
                    ),
                    "recommended_slot_count": 6,
                }
            ],
        },
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        csrf = login(client)

        response = client.post(
            "/api/create/news/preview",
            headers={
                "X-CSRF-Token": csrf
            },
            json={
                "business_id": (
                    "fixture_business"
                ),
                "speaker_id": (
                    "fixture_speaker"
                ),
            },
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            response.json()[
                "preview"
            ][
                "eligible_source_count"
            ]
            == 1
        )


def test_news_create_request_route(
    news_settings: Settings,
    monkeypatch,
):
    calls = {}

    def fake(
        settings,
        **kwargs,
    ):
        calls.update(kwargs)
        return {
            "recovered": False,
            "request": {
                "request_id": (
                    "news_fixture_001"
                ),
            },
            "state": fake_state(),
        }

    monkeypatch.setattr(
        main_module,
        "create_news_request",
        fake,
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        csrf = login(client)

        response = client.post(
            "/api/create/news/request",
            headers={
                "X-CSRF-Token": csrf
            },
            json={
                "business_id": (
                    "fixture_business"
                ),
                "speaker_id": (
                    "fixture_speaker"
                ),
                "source_content_id": (
                    "mix_fixture-C001"
                ),
                "idempotency_key": (
                    "fixture_key_001"
                ),
            },
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            calls[
                "source_content_id"
            ]
            == "mix_fixture-C001"
        )


def test_news_delivery_state_route(
    news_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "get_news_delivery_state",
        lambda settings, request_id: (
            fake_state(
                request_id
            )
        ),
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        login(client)

        response = client.get(
            "/api/create/news/"
            "news_fixture_001/delivery"
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            response.json()[
                "state"
            ][
                "next_action"
            ]
            == "HUMAN_REVIEW"
        )


def test_news_review_passes_authenticated_reviewer(
    news_settings: Settings,
    monkeypatch,
):
    calls = {}

    def fake(
        settings,
        request_id,
        *,
        reviewer,
        items,
    ):
        calls[
            "request_id"
        ] = request_id
        calls[
            "reviewer"
        ] = reviewer
        calls[
            "items"
        ] = items

        state = fake_state(
            request_id
        )
        state[
            "next_action"
        ] = "EXPORT_NEWS_EXCEL"
        state["review"] = {
            "completed": True,
            "approved": True,
            "approved_slot_count": 4,
        }

        return {
            "recovered": False,
            "state": state,
        }

    monkeypatch.setattr(
        main_module,
        "submit_news_review",
        fake,
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        csrf = login(client)

        response = client.post(
            "/api/create/news/"
            "news_fixture_001/review",
            headers={
                "X-CSRF-Token": csrf
            },
            json={
                "items": [
                    {
                        "slot_id": (
                            "S001"
                        ),
                        "decision": (
                            "approved"
                        ),
                        "approved_text": (
                            "素菜加工费通常8-10元"
                        ),
                        "note": "",
                    }
                ],
            },
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            calls["reviewer"]
            == "13800000000"
        )
        assert (
            calls["items"][0][
                "approved_text"
            ]
            == "素菜加工费通常8-10元"
        )


def test_news_export_route(
    news_settings: Settings,
    monkeypatch,
):
    monkeypatch.setattr(
        main_module,
        "export_news_excel",
        lambda settings, request_id: {
            "recovered": False,
            "state": {
                **fake_state(
                    request_id
                ),
                "next_action": (
                    "NEWS_EXCEL_EXPORTED"
                ),
                "stop_point_reached": True,
            },
        },
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        csrf = login(client)

        response = client.post(
            "/api/create/news/"
            "news_fixture_001/export",
            headers={
                "X-CSRF-Token": csrf
            },
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            response.json()[
                "result"
            ][
                "state"
            ][
                "stop_point_reached"
            ]
            is True
        )


def test_news_download_route(
    news_settings: Settings,
    monkeypatch,
    tmp_path: Path,
):
    excel = (
        tmp_path
        / "news.xlsx"
    )
    excel.write_bytes(
        b"news-excel"
    )

    monkeypatch.setattr(
        main_module,
        "exported_news_excel_path",
        lambda settings, request_id: excel,
    )
    monkeypatch.setattr(
        main_module,
        "exported_news_excel_filename",
        lambda settings, request_id: (
            "测试食堂_张三_News新闻体_1条_20260918_fixture.xlsx"
        ),
    )

    with TestClient(
        main_module.build_app(
            news_settings
        )
    ) as client:
        provision_user(
            news_settings.database_path,
            "13800000000",
        )
        login(client)

        response = client.get(
            "/api/create/news/"
            "news_fixture_001/excel"
        )

        assert (
            response.status_code
            == 200
        )
        assert (
            response.content
            == b"news-excel"
        )
