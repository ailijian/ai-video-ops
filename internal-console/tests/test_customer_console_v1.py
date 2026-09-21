from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import (
    TestClient,
)

from app.auth_service import (
    provision_user,
)
from app.config import Settings
from app.main import build_app
from app.task_service import update_task


@pytest.fixture()
def customer_settings(
    tmp_path: Path,
) -> Settings:
    console_root = Path(__file__).resolve().parents[1]

    repo_root = console_root.parent

    pipeline_root = tmp_path / "pipeline"

    pipeline_root.mkdir(
        parents=True,
        exist_ok=True,
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
        session_cookie_name=("aivo_customer_test"),
        session_hours=1,
        secure_cookies=False,
        status_timeout_seconds=30,
        case_analysis_worker_enabled=False,
        customer_analysis_worker_enabled=False,
        speaker_analysis_worker_enabled=False,
        default_business_id=("unused_customer_test"),
    )


@pytest.fixture()
def customer_client(
    customer_settings: Settings,
):
    with TestClient(build_app(customer_settings)) as client:
        provision_user(
            customer_settings.database_path,
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
            "password": "123456",
        },
    )

    assert response.status_code == 200

    csrf = response.json()["csrf_token"]

    changed = client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={
            "current_password": ("123456"),
            "new_password": ("CustomerConsole2026!"),
            "confirm_password": ("CustomerConsole2026!"),
        },
    )

    assert changed.status_code == 200

    return changed.json()["csrf_token"]


def customer_payload():
    return {
        "customer_name": ("小爪宠物店"),
        "industry": "宠物服务",
        "materials": (
            "小爪宠物店提供宠物洗护和基础美容，"
            "主要服务附近养宠家庭。"
            "很多主人工作日没时间自己给宠物洗澡。"
        ),
    }


def test_new_customer_creates_recoverable_task_without_raw_materials_in_sqlite(
    customer_client: TestClient,
    customer_settings: Settings,
):
    csrf = login(customer_client)

    payload = customer_payload()

    response = customer_client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )

    assert response.status_code == 200

    body = response.json()

    assert body["duplicate"] is False

    task = body["task"]

    assert task["task_type"] == "customer_analysis"

    assert task["status"] == "queued"
    assert task["created_by"]["phone"] == "13800000000"

    serialized_payload = json.dumps(
        task["payload"],
        ensure_ascii=False,
    )

    assert payload["materials"] not in serialized_payload

    request_path = Path(task["payload"]["request_path"])

    assert request_path.is_file()

    request = json.loads(request_path.read_text(encoding="utf-8"))

    assert request["materials"] == payload["materials"]

    customers = customer_client.get("/api/customers")

    assert customers.status_code == 200

    projected = customers.json()["customers"]

    assert len(projected) == 1

    assert projected[0]["display_name"] == "小爪宠物店"

    assert projected[0]["status"] == "analyzing"
    assert projected[0]["submitted_by"]["phone"] == "13800000000"


def test_insufficient_readiness_customer_remains_in_list_for_later_completion(
    customer_client: TestClient,
    customer_settings: Settings,
):
    csrf = login(customer_client)
    created = customer_client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "customer_name": "资料待补客户",
            "industry": "本地生活",
            "materials": "目前只确认了客户名称和行业。",
        },
    ).json()
    request_path = Path(created["task"]["payload"]["request_path"])
    assert request_path.is_file(), "initial Customer / Intake must persist before readiness"
    review_path = request_path.parent / "customer_fact_review_v1.json"
    review_path.write_text(
        json.dumps(
            {
                "status": "completed_persona_blocked",
                "business_persona_blockers": [
                    "business_identity",
                    "customer_use_context",
                    "production_bearing_facts",
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    update_task(
        customer_settings.database_path,
        created["task"]["task_id"],
        status="completed",
        progress=100,
        stage="客户信息需要补充",
    )
    customers = customer_client.get("/api/customers").json()["customers"]
    projected = next(
        item for item in customers if item["business_id"] == created["business_id"]
    )
    assert projected["status"] == "needs_more_info"
    detail = customer_client.get(
        f"/api/customers/{created['business_id']}"
    ).json()
    assert detail["status"] == "needs_more_info"
    assert detail["fact_review"]["business_persona_blockers"] == [
        "business_identity",
        "customer_use_context",
        "production_bearing_facts",
    ]
    supplemented = customer_client.post(
        f"/api/customers/{created['business_id']}/reanalyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "customer_name": "资料待补客户",
            "industry": "本地生活",
            "materials": (
                "客户提供上门保洁；附近家庭会在搬家后预约；"
                "服务前先确认面积并报价。"
            ),
        },
    )
    assert supplemented.status_code == 200, supplemented.json()
    assert supplemented.json()["new_intake"] is True
    assert supplemented.json()["intake_id"] == "intake_0002"


def test_duplicate_customer_does_not_create_second_task(
    customer_client: TestClient,
):
    csrf = login(customer_client)

    payload = customer_payload()

    first = customer_client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": (csrf)},
        json=payload,
    )

    assert first.status_code == 200

    first_task = first.json()["task"]

    second = customer_client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": (csrf)},
        json=payload,
    )

    assert second.status_code == 200

    body = second.json()

    assert body["duplicate"] is True

    assert body["existing_task"]["task_id"] == first_task["task_id"]

    tasks = customer_client.get("/api/tasks").json()["tasks"]

    customer_tasks = [
        task for task in tasks if (task["task_type"] == "customer_analysis")
    ]

    assert len(customer_tasks) == 1


def test_customer_state_change_requires_csrf(
    customer_client: TestClient,
):
    login(customer_client)

    response = customer_client.post(
        "/api/customers/analyze",
        json=customer_payload(),
    )

    assert response.status_code == 403

    assert response.json()["detail"]["code"] == "CSRF_CHECK_FAILED"


def test_failed_customer_projects_failed_state_and_can_retry(
    customer_client: TestClient,
    customer_settings: Settings,
):
    csrf = login(customer_client)

    created = customer_client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": csrf},
        json=customer_payload(),
    ).json()

    old_task = created["task"]

    update_task(
        customer_settings.database_path,
        old_task["task_id"],
        status="failed",
        progress=35,
        stage="分析失败",
        error_code="TEST_FAILURE",
        error_message=("Fixture customer " "analysis failed."),
    )

    detail = customer_client.get(f"/api/customers/{created['business_id']}")

    assert detail.status_code == 200, detail.json()
    assert detail.json()["status"] == "failed"
    assert detail.json()["task"]["task_id"] == old_task["task_id"]

    retried = customer_client.post(
        (f"/api/customers/" f"{created['business_id']}/retry"),
        headers={"X-CSRF-Token": csrf},
    )

    assert retried.status_code == 200

    new_task = retried.json()["task"]

    assert new_task["task_id"] != old_task["task_id"]

    assert new_task["payload"]["request_path"] == old_task["payload"]["request_path"]


def test_modified_failed_customer_creates_new_intake_without_overwriting_old_one(
    customer_client: TestClient,
    customer_settings: Settings,
):
    csrf = login(customer_client)

    original = customer_payload()

    created = customer_client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": csrf},
        json=original,
    ).json()

    old_task = created["task"]

    update_task(
        customer_settings.database_path,
        old_task["task_id"],
        status="failed",
        progress=35,
        stage="分析失败",
        error_code="TEST_FAILURE",
        error_message="failed",
    )

    modified = {
        **original,
        "materials": (original["materials"] + " 门店还提供预约服务。"),
    }

    response = customer_client.post(
        (f"/api/customers/" f"{created['business_id']}/reanalyze"),
        headers={"X-CSRF-Token": csrf},
        json=modified,
    )

    assert response.status_code == 200
    body = response.json()

    assert body["intake_id"] == "intake_0002"

    root = (
        customer_settings.pipeline_root
        / "data"
        / "customer_intakes"
        / created["business_id"]
    )

    first = json.loads(
        (root / "intake_0001" / "customer_onboarding_request_v1.json").read_text(
            encoding="utf-8"
        )
    )

    second = json.loads(
        (root / "intake_0002" / "customer_onboarding_request_v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert first["materials"] == original["materials"]

    assert second["materials"] == modified["materials"]

    assert second["supersedes_intake_id"] == "intake_0001"
