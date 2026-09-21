from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.config import Settings
from app import content_delivery_gateway as subject


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def settings_for(
    tmp_path: Path,
) -> Settings:
    console_root = (
        Path(__file__).resolve().parents[1]
    )
    return Settings(
        repo_root=tmp_path,
        console_root=console_root,
        pipeline_root=tmp_path / "ops-pipeline",
        database_path=tmp_path / "console.sqlite3",
        python_executable="python",
        pipeline_python_executable="python",
        session_cookie_name="test",
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id="unused",
    )


def build_request(
    tmp_path: Path,
) -> tuple[Settings, str, dict]:
    settings = settings_for(tmp_path)
    request_id = "gen_9cf88c22ec3a49cd2264"

    persona = {
        "persona_id": "customer_pet",
        "facts": {
            "public_display_name": {
                "state": "known",
                "value": "小爪宠物店",
            },
        },
    }
    speaker = {
        "persona_id": "speaker_owner",
        "facts": {
            "public_display_name": {
                "state": "known",
                "value": "王琳",
            },
        },
    }
    persona_path = tmp_path / "persona.json"
    speaker_path = tmp_path / "speaker.json"
    write_json(persona_path, persona)
    write_json(speaker_path, speaker)

    request = {
        "schema_version": (
            "generation-request-v1.0"
        ),
        "request_id": request_id,
        "persona_id": "customer_pet",
        "speaker_persona": "speaker_owner",
        "profile": "mix",
        "quantity": 2,
        "created_at": (
            "2026-09-18T10:00:00+08:00"
        ),
        "lineage": {
            "business_persona_ref": {
                "path": str(
                    persona_path.resolve()
                ),
                "file_sha256": sha256(
                    persona_path
                ),
            },
            "speaker_persona_ref": {
                "path": str(
                    speaker_path.resolve()
                ),
                "file_sha256": sha256(
                    speaker_path
                ),
            },
        },
    }

    request_path = (
        settings.pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )
    write_json(request_path, request)

    return settings, request_id, request


def test_operator_friendly_export_filename(
    tmp_path: Path,
):
    _settings, _request_id, request = (
        build_request(tmp_path)
    )

    assert (
        subject.export_filename_for_request(
            request
        )
        == (
            "小爪宠物店_王琳_Mix混剪_2条_"
            "20260918_9cf88c.xlsx"
        )
    )


def test_legacy_excel_is_recovered_but_download_name_is_friendly(
    tmp_path: Path,
):
    settings, request_id, request = (
        build_request(tmp_path)
    )
    legacy = (
        settings.pipeline_root
        / "output"
        / f"{request_id}_approved_mix_scripts.xlsx"
    )
    legacy.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    legacy.write_bytes(b"legacy")

    receipt = {
        "validation_passed": True,
        "output_sha256": sha256(legacy),
        "exported_row_count": 2,
    }
    write_json(
        legacy.with_suffix(
            ".export_receipt.json"
        ),
        receipt,
    )

    projected = subject._project_export(
        settings,
        request_id,
        request,
    )

    assert projected["completed"] is True
    assert projected[
        "legacy_recovered"
    ] is True
    assert projected["output_name"] == (
        "小爪宠物店_王琳_Mix混剪_2条_"
        "20260918_9cf88c.xlsx"
    )
    assert (
        subject.exported_excel_path(
            settings,
            request_id,
        )
        == legacy
    )
    assert (
        subject.exported_excel_filename(
            settings,
            request_id,
        )
        == projected["output_name"]
    )


def test_excel_without_ledger_closure_is_not_stop_point(
    tmp_path: Path,
    monkeypatch,
):
    settings, request_id, request = (
        build_request(tmp_path)
    )

    paths = subject._request_paths(
        settings,
        request_id,
    )
    paths["source_plan"].parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    paths["source_plan"].write_text(
        json.dumps(
            {
                "schema_version": "generation-source-plan-v1.0",
                "request_id": request_id,
                "request": {
                    "request_sha": sha256(paths["request"]),
                },
                "coverage": {
                    "status": "supported",
                    "code": "research_coverage_supported",
                },
                "selected_patterns": [{"pattern_id": "fixture_pattern"}],
                "eligible_case_pool": [{"case_id": "fixture_case"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        subject,
        "_project_content_plan",
        lambda path: {
            "ready": True,
        },
    )
    monkeypatch.setattr(
        subject,
        "_project_generation_batch",
        lambda path: {
            "ready": True,
        },
    )
    monkeypatch.setattr(
        subject,
        "_project_review",
        lambda paths: {
            "completed": True,
            "approved": True,
            "approved_item_count": 2,
        },
    )
    monkeypatch.setattr(
        subject,
        "_project_export",
        lambda *args, **kwargs: {
            "completed": True,
            "output_name": "friendly.xlsx",
        },
    )
    monkeypatch.setattr(
        subject,
        "_project_export_closure",
        lambda *args, **kwargs: {
            "completed": False,
            "content_ledger_written": False,
        },
    )

    state = (
        subject.get_content_delivery_state(
            settings,
            request_id,
        )
    )

    assert state["next_action"] == (
        "EXPORT_EXCEL"
    )
    assert (
        state["stop_point_reached"]
        is False
    )
