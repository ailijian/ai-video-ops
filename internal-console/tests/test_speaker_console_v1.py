from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth_service import provision_user
from app.config import Settings
from app.main import build_app


@pytest.fixture()
def speaker_settings(
    tmp_path: Path,
) -> Settings:
    console_root = Path(__file__).resolve().parents[1]

    repo_root = console_root.parent

    pipeline_root = tmp_path / "pipeline"

    persona_path = (
        pipeline_root
        / "data"
        / "personas"
        / "fixture_pet_store"
        / "revision_0001"
        / "persona_v1.json"
    )

    persona_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    persona = {
        "schema_version": ("persona-v1.0"),
        "persona_id": ("fixture_pet_store"),
        "revision": 1,
        "persona_scope": ("business"),
        "lifecycle": {
            "status": ("approved"),
            "approved": True,
            "retired": False,
            "human_review_required": (True),
        },
        "facts": {
            "public_display_name": {
                "state": ("known"),
                "value": ("小爪宠物店"),
            },
            "industry": {
                "state": ("known"),
                "value": ("宠物服务"),
            },
        },
        "provenance": {
            "content_sha256": ("fixture"),
        },
        "approval": {
            "human_gate": True,
        },
    }
    persona_path.write_text(
        json.dumps(
            persona,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    persona_sha256 = hashlib.sha256(persona_path.read_bytes()).hexdigest()
    (persona_path.parent / "approval_receipt.json").write_text(
        json.dumps(
            {
                "schema_version": "persona-approval-receipt-v1.0",
                "persona_id": "fixture_pet_store",
                "revision": 1,
                "decision": "approved",
                "human_gate": True,
                "persona_sha256_after_approval": persona_sha256,
                "content_sha256": "fixture",
                "previous_approved_revision": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=pipeline_root,
        database_path=(tmp_path / "console.sqlite3"),
        python_executable=str(console_root / ".venv" / "Scripts" / "python.exe"),
        pipeline_python_executable=str(
            repo_root / "ops-pipeline" / ".venv" / "Scripts" / "python.exe"
        ),
        session_cookie_name=("aivo_speaker_test"),
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id=("fixture_pet_store"),
    )


@pytest.fixture()
def speaker_client(
    speaker_settings: Settings,
):
    with TestClient(build_app(speaker_settings)) as client:
        provision_user(
            speaker_settings.database_path,
            "13800000000",
        )

        yield client


def login(
    client: TestClient,
) -> str:
    response = client.post(
        "/api/auth/login",
        json={
            "phone": ("13800000000"),
            "password": ("123456"),
        },
    )

    assert response.status_code == 200

    csrf = response.json()["csrf_token"]

    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": (csrf)},
        json={
            "current_password": ("123456"),
            "new_password": ("SpeakerConsole2026!"),
            "confirm_password": ("SpeakerConsole2026!"),
        },
    )

    assert changed.status_code == 200

    return changed.json()["csrf_token"]


def speaker_payload():
    return {
        "speaker_name": "王琳",
        "public_role": "店主",
        "speaker_type": ("owner_founder"),
        "materials": (
            "王琳是门店店主，"
            "日常亲自接待顾客，"
            "会检查宠物皮肤和毛发状态，"
            "并根据现场情况确认洗护方式。"
        ),
        "forbidden_claims": [
            "不得声称自己是兽医",
            "不得进行医疗诊断",
        ],
    }


def write_blocked_speaker(
    settings: Settings,
    *,
    speaker_id: str = "speaker_gap_fixture",
    blockers: list[str] | None = None,
) -> Path:
    root = (
        settings.pipeline_root
        / "data"
        / "speaker_intakes"
        / "fixture_pet_store"
        / speaker_id
        / "intake_0001"
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "speaker_onboarding_request_v1.json").write_text(
        json.dumps(
            {
                "business_id": "fixture_pet_store",
                "speaker_id": speaker_id,
                "intake_id": "intake_0001",
                "speaker_name": "王琳",
                "public_role": "店主",
                "speaker_type": "owner_founder",
                "materials": "王琳本人负责门店接待。",
                "forbidden_claims": [],
                "source_type": "internal_console_speaker_materials",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "speaker_fact_review_v1.json").write_text(
        json.dumps(
            {
                "status": "completed_persona_blocked",
                "speaker_persona_blockers": blockers or ["speaker_role_facts"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "reviewed_speaker_fact_candidates_v1.json").write_text(
        json.dumps(
            {
                "review": {"status": "completed"},
                "fact_candidates": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return root


def test_create_speaker_analysis_task_without_raw_materials_in_sqlite(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    payload = speaker_payload()

    response = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=payload,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["duplicate"] is False

    task = body["task"]

    assert task["task_type"] == "speaker_analysis"

    assert task["status"] == "queued"
    assert task["created_by"]["phone"] == "13800000000"

    serialized = json.dumps(
        task["payload"],
        ensure_ascii=False,
    )

    assert payload["materials"] not in serialized

    request_path = Path(task["payload"]["request_path"])

    assert request_path.is_file()

    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert request["materials"] == payload["materials"]

    assert request["authority"]["media_rights_established"] is False


def test_duplicate_speaker_does_not_create_second_task(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    payload = speaker_payload()

    first = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": csrf},
        json=payload,
    ).json()

    second = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=payload,
    )

    assert second.status_code == 200

    body = second.json()

    assert body["duplicate"] is True

    assert body["existing_task"]["task_id"] == first["task"]["task_id"]

    tasks = speaker_client.get("/api/tasks").json()["tasks"]

    speaker_tasks = [
        task for task in tasks if (task["task_type"] == "speaker_analysis")
    ]

    assert len(speaker_tasks) == 1


def test_speaker_list_projects_pending_speaker(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    created = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=(speaker_payload()),
    ).json()

    response = speaker_client.get(("/api/customers/" "fixture_pet_store/" "speakers"))

    assert response.status_code == 200

    speakers = response.json()["speakers"]

    assert len(speakers) == 1

    assert speakers[0]["speaker_id"] == created["speaker_id"]

    assert speakers[0]["status"] == "analyzing"


def test_speaker_state_change_requires_csrf(
    speaker_client: TestClient,
):
    login(speaker_client)

    response = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        json=(speaker_payload()),
    )

    assert response.status_code == 403

    assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


def test_speaker_task_type_is_supported_by_database_migration(
    speaker_client: TestClient,
):
    csrf = login(speaker_client)

    response = speaker_client.post(
        ("/api/customers/" "fixture_pet_store/" "speakers/analyze"),
        headers={"X-CSRF-Token": (csrf)},
        json=(speaker_payload()),
    )

    assert response.status_code == 200

    assert response.json()["task"]["task_type"] == "speaker_analysis"


def test_unapproved_customer_can_save_speaker_draft_then_start_after_approval(
    speaker_client: TestClient,
    speaker_settings: Settings,
):
    persona_path = (
        speaker_settings.pipeline_root
        / "data"
        / "personas"
        / "fixture_pet_store"
        / "revision_0001"
        / "persona_v1.json"
    )
    receipt_path = persona_path.parent / "approval_receipt.json"
    persona = json.loads(persona_path.read_text(encoding="utf-8"))
    persona["lifecycle"].update({"status": "review_required", "approved": False})
    persona_path.write_text(
        json.dumps(persona, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    receipt_path.unlink()
    csrf = login(speaker_client)
    created = speaker_client.post(
        "/api/customers/fixture_pet_store/speakers/analyze",
        headers={"X-CSRF-Token": csrf},
        json=speaker_payload(),
    )
    assert created.status_code == 200, created.json()
    body = created.json()
    assert body["draft_saved"] is True
    assert body["state"] == "pending_customer_profile"
    assert speaker_client.get("/api/tasks").json()["tasks"] == []
    listed = speaker_client.get(
        "/api/customers/fixture_pet_store/speakers"
    ).json()
    assert listed["can_add_speaker"] is True
    assert listed["analysis_allowed"] is False
    assert listed["speakers"][0]["status"] == "pending_customer_profile"
    speaker_id = body["speaker_id"]
    detail = speaker_client.get(
        f"/api/customers/fixture_pet_store/speakers/{speaker_id}"
    ).json()
    request_path = (
        speaker_settings.pipeline_root
        / "data"
        / "speaker_intakes"
        / "fixture_pet_store"
        / speaker_id
        / "intake_0001"
        / "speaker_onboarding_request_v1.json"
    )
    request_bytes = request_path.read_bytes()
    request = json.loads(request_bytes)
    assert detail["status"] == "pending_customer_profile"
    assert "business_persona_ref" not in request
    assert request["authority"]["production_consumption_allowed"] is False
    assert all(
        option.get("speaker_id") != speaker_id
        for option in speaker_client.get("/api/create/options").json().get(
            "options", []
        )
    )

    persona["lifecycle"].update({"status": "approved", "approved": True})
    persona_path.write_text(
        json.dumps(persona, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    persona_sha256 = hashlib.sha256(persona_path.read_bytes()).hexdigest()
    receipt_path.write_text(
        json.dumps(
            {
                "schema_version": "persona-approval-receipt-v1.0",
                "persona_id": "fixture_pet_store",
                "revision": 1,
                "decision": "approved",
                "human_gate": True,
                "persona_sha256_after_approval": persona_sha256,
                "content_sha256": "fixture",
                "previous_approved_revision": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    ready = speaker_client.get(
        f"/api/customers/fixture_pet_store/speakers/{speaker_id}"
    ).json()
    assert ready["status"] == "analysis_pending"
    started = speaker_client.post(
        f"/api/customers/fixture_pet_store/speakers/{speaker_id}/analyze",
        headers={"X-CSRF-Token": csrf},
    )
    assert started.status_code == 200, started.json()
    assert started.json()["started"] is True
    assert started.json()["task"]["task_type"] == "speaker_analysis"
    assert request_path.read_bytes() == request_bytes


def test_needs_more_info_has_targeted_gap_supplement_and_preserves_lineage(
    speaker_client: TestClient,
    speaker_settings: Settings,
):
    csrf = login(speaker_client)
    first_root = write_blocked_speaker(speaker_settings)
    detail = speaker_client.get(
        "/api/customers/fixture_pet_store/speakers/speaker_gap_fixture"
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "needs_more_info"
    assert body["readiness_gaps"] == [
        {
            "field": "speaker_role_facts",
            "title": "本人职责与经历",
            "question": "他/她平时具体负责什么？有哪些事情是本人亲自做的或真实经历过的？",
        }
    ]
    response = speaker_client.post(
        "/api/customers/fixture_pet_store/speakers/speaker_gap_fixture/gaps/supplement",
        headers={"X-CSRF-Token": csrf},
        json={"answers": {"speaker_role_facts": "本人每天亲自接待并检查洗护状态。"}},
    )
    assert response.status_code == 200, response.json()
    task = response.json()["task"]
    request = json.loads(Path(task["payload"]["request_path"]).read_text(encoding="utf-8"))
    assert request["intake_type"] == "gap_supplement"
    assert request["target_gaps"] == ["speaker_role_facts"]
    assert request["raw_answers"] == {
        "speaker_role_facts": "本人每天亲自接待并检查洗护状态。"
    }
    assert request["authority"]["supplement_is_speaker_truth"] is False
    assert request["authority"]["previous_speaker_facts_preserved"] is True
    assert request["previous_reviewed_fact_refs"] == [
        str((first_root / "reviewed_speaker_fact_candidates_v1.json").resolve())
    ]


def test_forbidden_only_legacy_blocker_offers_deterministic_recheck(
    speaker_client: TestClient,
    speaker_settings: Settings,
):
    login(speaker_client)
    write_blocked_speaker(
        speaker_settings,
        speaker_id="speaker_recheck_fixture",
        blockers=["first_person_forbidden_claims"],
    )
    body = speaker_client.get(
        "/api/customers/fixture_pet_store/speakers/speaker_recheck_fixture"
    ).json()
    assert body["status"] == "needs_more_info"
    assert body["can_recheck_existing"] is True
    assert body["readiness_gaps"] == []


def test_speaker_ui_exposes_optional_forbidden_and_no_dead_end_loop():
    source = (
        Path(__file__).resolve().parents[1]
        / "static"
        / "assets"
        / "speaker-views.js"
    ).read_text(encoding="utf-8")
    assert "额外明确限制（选填）" in source
    assert "补充出镜人资料" in source
    assert "确认刚补充的信息" in source
    assert "重新检查现有资料" in source
    assert "未记录额外明确限制" in source
    assert 'primaryLabel: "返回出镜人"' not in source
