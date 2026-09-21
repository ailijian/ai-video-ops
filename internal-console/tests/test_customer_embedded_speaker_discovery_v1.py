from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.auth_service import provision_user
from app.canonical_gateway import CanonicalOperationError
from app.config import Settings
from app.customer_gateway import confirm_speaker_discovery
from app.main import build_app
from app.speaker_gateway import list_speakers, prepare_speaker_onboarding_request


def settings_for(tmp_path: Path) -> Settings:
    console_root = Path(__file__).resolve().parents[1]
    repo_root = console_root.parent
    pipeline_root = tmp_path / "pipeline"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        repo_root=repo_root,
        console_root=console_root,
        pipeline_root=pipeline_root,
        database_path=tmp_path / "console.sqlite3",
        python_executable=str(console_root / ".venv" / "Scripts" / "python.exe"),
        pipeline_python_executable=str(
            repo_root / "ops-pipeline" / ".venv" / "Scripts" / "python.exe"
        ),
        session_cookie_name="aivo_discovery_test",
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id="fixture_business",
    )


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def discovery_fixture(
    settings: Settings,
    *,
    name: str | None = "杜建青",
    role: str | None = "创始人",
) -> tuple[Path, str]:
    root = (
        settings.pipeline_root
        / "data"
        / "customer_intakes"
        / "fixture_business"
        / "intake_0001"
    )
    candidate_id = "speaker_candidate_fixture"
    write_json(root / "customer_onboarding_request_v1.json", {"materials": "原始资料"})
    write_json(root / "customer_intake_v1.json", {"intake_id": "intake_0001"})
    write_json(
        root / "customer_intake_privacy_projection_v1.json",
        {"projection": {"materials_safe_semantic": "创始人杜建青经营餐饮30年"}},
    )
    write_json(
        root / "speaker_discovery_candidates_v1.json",
        {
            "schema_version": "speaker-discovery-candidates-v1.0",
            "business_id": "fixture_business",
            "intake_id": "intake_0001",
            "speaker_discovery_status": "completed",
            "speaker_candidates": [
                {
                    "candidate_id": candidate_id,
                    "name": name,
                    "public_role": role,
                    "speaker_type_hint": "owner_founder",
                    "candidate_status": "potential_representative",
                    "evidence_quotes": ["创始人杜建青经营餐饮30年"],
                    "personal_material_quotes": ["创始人杜建青经营餐饮30年"],
                    "explicit_forbidden_claims": [],
                }
            ],
        },
    )
    return root, candidate_id


def test_unconfirmed_candidate_does_not_create_speaker_draft(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    root, candidate_id = discovery_fixture(settings)
    result = confirm_speaker_discovery(
        settings,
        business_id="fixture_business",
        decisions=[{"candidate_id": candidate_id, "selected": False}],
        confirmed_by_user_id=7,
        confirmed_by_phone="13800000000",
    )
    assert result["decisions"][0]["outcome"] == "not_selected"
    speaker_root = settings.pipeline_root / "data" / "speaker_intakes"
    assert not speaker_root.exists()
    assert (root / "speaker_discovery_confirmation_v1.json").is_file()


def test_human_confirmation_creates_traceable_pending_speaker_draft(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path)
    _root, candidate_id = discovery_fixture(settings)
    result = confirm_speaker_discovery(
        settings,
        business_id="fixture_business",
        decisions=[
            {
                "candidate_id": candidate_id,
                "selected": True,
                "speaker_name": "杜建青",
                "public_role": "创始人",
                "speaker_type": "owner_founder",
            }
        ],
        confirmed_by_user_id=7,
        confirmed_by_phone="13800000000",
    )
    assert result["decisions"][0]["outcome"] == "draft_created"
    speaker_id = result["decisions"][0]["speaker_id"]
    request_path = (
        settings.pipeline_root
        / "data"
        / "speaker_intakes"
        / "fixture_business"
        / speaker_id
        / "intake_0001"
        / "speaker_onboarding_request_v1.json"
    )
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["source_type"] == "customer_intake_speaker_discovery"
    assert request["draft_status"] == "pending_business_persona_approval"
    assert request["forbidden_claims"] == []
    assert request["human_confirmed_identity"]["confirmed_by_user_id"] == 7
    assert request["source_lineage"]["business_fact_promoted_to_speaker_fact"] is False
    assert request["authority"]["production_consumption_allowed"] is False
    projected = list_speakers(settings, "fixture_business")
    assert projected[0]["status"] == "pending_customer_profile"
    assert projected[0]["human_confirmed_discovery"] is True


def test_selected_candidate_with_missing_identity_does_not_block_customer_flow(
    tmp_path: Path,
) -> None:
    settings = settings_for(tmp_path)
    _root, candidate_id = discovery_fixture(settings, name=None, role="老板")
    result = confirm_speaker_discovery(
        settings,
        business_id="fixture_business",
        decisions=[{"candidate_id": candidate_id, "selected": True}],
        confirmed_by_user_id=7,
        confirmed_by_phone="13800000000",
    )
    assert result["status"] == "completed"
    assert result["decisions"][0]["outcome"] == "identity_required"


def test_manual_add_matches_discovered_draft_without_duplicate(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    _root, candidate_id = discovery_fixture(settings)
    confirmed = confirm_speaker_discovery(
        settings,
        business_id="fixture_business",
        decisions=[
            {
                "candidate_id": candidate_id,
                "selected": True,
                "speaker_name": "杜建青",
                "public_role": "创始人",
                "speaker_type": "owner_founder",
            }
        ],
        confirmed_by_user_id=7,
        confirmed_by_phone="13800000000",
    )
    speaker_id = confirmed["decisions"][0]["speaker_id"]
    manual = prepare_speaker_onboarding_request(
        settings,
        business_id="fixture_business",
        speaker_name="杜建青",
        public_role="创始人",
        speaker_type="owner_founder",
        materials="人工补充的更多资料",
        forbidden_claims=[],
    )
    assert manual["duplicate"] is True
    assert manual["speaker_id"] == speaker_id
    speakers = list(
        (settings.pipeline_root / "data" / "speaker_intakes" / "fixture_business").iterdir()
    )
    assert len(speakers) == 1


def login(client: TestClient, settings: Settings) -> str:
    provision_user(settings.database_path, "13800000000")
    response = client.post(
        "/api/auth/login",
        json={"phone": "13800000000", "password": "123456"},
    )
    csrf = response.json()["csrf_token"]
    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": "123456",
            "new_password": "Discovery2026!",
            "confirm_password": "Discovery2026!",
        },
    )
    return changed.json()["csrf_token"]


def test_business_approval_auto_starts_confirmed_speaker_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path)
    request_path = tmp_path / "speaker_request.json"
    write_json(request_path, {"fixture": True})
    monkeypatch.setattr(
        main_module,
        "approve_business_persona",
        lambda *_args, **_kwargs: {"business_id": "fixture_business", "status": "approved"},
    )
    monkeypatch.setattr(
        main_module,
        "list_speakers",
        lambda *_args, **_kwargs: [
            {
                "speaker_id": "speaker_fixture",
                "display_name": "杜建青",
                "public_role": "创始人",
                "status": "analysis_pending",
                "human_confirmed_discovery": True,
            }
        ],
    )
    monkeypatch.setattr(
        main_module,
        "prepare_speaker_draft_analysis",
        lambda *_args, **_kwargs: {
            "intake_id": "intake_0001",
            "request_path": str(request_path),
            "speaker_name": "杜建青",
            "public_role": "创始人",
        },
    )
    monkeypatch.setattr(
        main_module,
        "create_speaker_task",
        lambda *_args, **_kwargs: {
            "task_id": "speaker-task-1",
            "task_type": "speaker_analysis",
            "subject_ref": "speaker_fixture",
            "status": "queued",
        },
    )
    recorded: list[dict] = []
    monkeypatch.setattr(
        main_module,
        "record_speaker_auto_handoff_status",
        lambda *_args, **kwargs: recorded.append(kwargs),
    )
    with TestClient(build_app(settings)) as client:
        csrf = login(client, settings)
        response = client.post(
            "/api/customers/fixture_business/persona/approve",
            headers={"X-CSRF-Token": csrf},
            json={"note": "approved"},
        )
    assert response.status_code == 200
    handoff = response.json()["speaker_handoff"]
    assert handoff["task_count"] == 1
    assert handoff["started"][0]["task_id"] == "speaker-task-1"
    assert recorded[0]["status"] == "analysis_pending"


def test_auto_handoff_failure_never_rolls_back_business_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for(tmp_path)
    monkeypatch.setattr(
        main_module,
        "approve_business_persona",
        lambda *_args, **_kwargs: {"business_id": "fixture_business", "status": "approved"},
    )
    monkeypatch.setattr(
        main_module,
        "list_speakers",
        lambda *_args, **_kwargs: [
            {
                "speaker_id": "speaker_fixture",
                "status": "analysis_pending",
                "human_confirmed_discovery": True,
            }
        ],
    )

    def fail(*_args, **_kwargs):
        raise CanonicalOperationError("HANDOFF_TEST_FAILURE", "failed", "retry")

    monkeypatch.setattr(main_module, "prepare_speaker_draft_analysis", fail)
    recorded: list[dict] = []
    monkeypatch.setattr(
        main_module,
        "record_speaker_auto_handoff_status",
        lambda *_args, **kwargs: recorded.append(kwargs),
    )
    with TestClient(build_app(settings)) as client:
        csrf = login(client, settings)
        response = client.post(
            "/api/customers/fixture_business/persona/approve",
            headers={"X-CSRF-Token": csrf},
            json={"note": "approved"},
        )
    assert response.status_code == 200
    assert response.json()["customer"]["status"] == "approved"
    assert response.json()["speaker_handoff"]["failed"] == [
        {"speaker_id": "speaker_fixture", "error_code": "HANDOFF_TEST_FAILURE"}
    ]
    assert recorded[0]["status"] == "retry_required"
