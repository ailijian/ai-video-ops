from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.background_task_service import BackgroundTaskRunner, create_background_task
from app.canonical_gateway import CanonicalOperationError, case_media_path
from app.auth_service import (
    cleanup_expired_sessions,
    create_session,
    provision_user,
    resolve_session,
)
from app.config import Settings
from app.content_delivery_gateway import _pipeline_env as content_pipeline_env
from app.database import apply_migrations, connect, transaction
from app.news_delivery_gateway import _pipeline_env as news_pipeline_env
from app.operation_lock import OperationLockTimeout, operation_lock
from app.path_safety import resolve_within, validate_identifier
from app.task_service import (
    CaseTaskRunner,
    GPU_HEAVY,
    STANDARD_BACKGROUND,
    TaskSubmissionError,
    claim_task,
    create_case_task,
    get_task,
    iso_utc,
    iter_queued_tasks,
    recover_expired_tasks,
    submit_task,
    update_task,
)
from conftest import login_and_change_password


@pytest.fixture()
def hardening_db(tmp_path: Path) -> Path:
    database = tmp_path / "console.sqlite3"
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    apply_migrations(database, migrations)
    provision_user(database, "13800000000")
    return database


def user_id(database: Path) -> int:
    connection = connect(database)
    try:
        return int(connection.execute("SELECT id FROM users LIMIT 1").fetchone()["id"])
    finally:
        connection.close()


def test_task_migration_preserves_historical_rows_with_null_actor(tmp_path: Path):
    database = tmp_path / "legacy.sqlite3"
    source_migrations = Path(__file__).resolve().parents[1] / "migrations"
    legacy_migrations = tmp_path / "legacy-migrations"
    legacy_migrations.mkdir()
    for name in ("001_initial.sql", "002_speaker_analysis_task.sql"):
        shutil.copy2(source_migrations / name, legacy_migrations / name)
    apply_migrations(database, legacy_migrations)
    timestamp = iso_utc()
    with transaction(database) as connection:
        connection.execute(
            """
            INSERT INTO tasks(
                task_id, task_type, subject_ref, status, progress, stage,
                payload_json, created_at, updated_at
            ) VALUES ('historical-task', 'case_analysis', '7999999999999999998',
                      'completed', 100, '历史完成', '{}', ?, ?)
            """,
            (timestamp, timestamp),
        )

    apply_migrations(database, source_migrations)
    migrated = get_task(database, "historical-task")
    assert migrated is not None
    assert migrated["created_by"] is None
    assert migrated["execution_lane"] == GPU_HEAVY
    assert migrated["attempt_count"] == 0


def test_two_simultaneous_same_case_submits_create_one_active_task(
    hardening_db: Path,
):
    actor = user_id(hardening_db)
    barrier = threading.Barrier(2)

    def submit() -> dict:
        barrier.wait()
        return create_case_task(
            hardening_db,
            source_url="https://www.douyin.com/video/7999999999999999999",
            case_id="7999999999999999999",
            operator_profile_hint="mix",
            created_by_user_id=actor,
            queue_max=20,
            gpu_pending_per_user_max=3,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))

    assert results[0]["task_id"] == results[1]["task_id"]
    connection = connect(hardening_db)
    try:
        count = connection.execute(
            """
            SELECT COUNT(*) AS count FROM tasks
            WHERE operation_identity = 'case_analysis:7999999999999999999'
              AND status IN ('queued', 'running')
            """
        ).fetchone()["count"]
    finally:
        connection.close()
    assert count == 1


def test_case_batch_uses_existing_fifo_and_per_user_gpu_limit(hardening_db: Path):
    actor = user_id(hardening_db)

    def submit(case_number: int) -> dict:
        case_id = f"79999999999999999{case_number:02d}"
        return create_case_task(
            hardening_db,
            source_url=f"https://www.douyin.com/video/{case_id}",
            case_id=case_id,
            operator_profile_hint="uncertain",
            created_by_user_id=actor,
            queue_max=20,
            gpu_pending_per_user_max=3,
        )

    accepted = [submit(number) for number in range(3)]
    assert [task["task_id"] for task in iter_queued_tasks(
        hardening_db, task_types=("case_analysis",)
    )] == [task["task_id"] for task in accepted]
    assert submit(0)["task_id"] == accepted[0]["task_id"]
    with pytest.raises(TaskSubmissionError, match="maximum number") as blocked:
        submit(3)
    assert blocked.value.code == "GPU_PENDING_LIMIT_REACHED"
    with transaction(hardening_db) as connection:
        connection.execute(
            "UPDATE tasks SET status = 'completed' WHERE task_id = ?",
            (accepted[0]["task_id"],),
        )
    next_task = submit(3)
    assert [task["task_id"] for task in iter_queued_tasks(
        hardening_db, task_types=("case_analysis",)
    )] == [accepted[1]["task_id"], accepted[2]["task_id"], next_task["task_id"]]


def test_two_workers_cannot_claim_same_task(hardening_db: Path):
    task = submit_task(
        hardening_db,
        task_id_prefix="claim",
        task_type="content_generation",
        subject_ref="request_claim_001",
        operation_identity="content_plan:request_claim_001",
        execution_lane=STANDARD_BACKGROUND,
        payload={"operation": "content_plan"},
        stage="等待开始",
        created_by_user_id=user_id(hardening_db),
        queue_max=20,
        gpu_pending_per_user_max=3,
    )
    barrier = threading.Barrier(2)

    def claim(worker: str) -> bool:
        barrier.wait()
        return claim_task(
            hardening_db,
            task["task_id"],
            worker_id=worker,
            lease_seconds=120,
            stage="执行",
            task_type="content_generation",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("worker-a", "worker-b")))
    assert sorted(results) == [False, True]
    claimed = get_task(hardening_db, task["task_id"])
    assert claimed is not None
    assert claimed["attempt_count"] == 1
    assert claimed["worker_id"] in {"worker-a", "worker-b"}
    assert claimed["started_at"] and claimed["heartbeat_at"] and claimed["lease_expires_at"]


def test_fifo_pages_beyond_one_hundred_tasks(hardening_db: Path):
    actor = user_id(hardening_db)
    task_ids: list[str] = []
    for index in range(125):
        task = submit_task(
            hardening_db,
            task_id_prefix=f"fifo-{index:03d}",
            task_type="content_generation",
            subject_ref=f"request_{index:03d}",
            operation_identity=f"content_plan:request_{index:03d}",
            execution_lane=STANDARD_BACKGROUND,
            payload={"operation": "content_plan"},
            stage="等待开始",
            created_by_user_id=actor,
            queue_max=200,
            gpu_pending_per_user_max=3,
        )
        task_ids.append(task["task_id"])
        with transaction(hardening_db) as connection:
            connection.execute(
                "UPDATE tasks SET created_at = ? WHERE task_id = ?",
                (f"2026-01-01T00:{index // 60:02d}:{index % 60:02d}Z", task["task_id"]),
            )

    queued = list(
        iter_queued_tasks(hardening_db, task_types=("content_generation",))
    )
    assert len(queued) == 125
    assert [item["task_id"] for item in queued] == task_ids


def test_expired_lease_recovers_but_live_lease_is_not_requeued(hardening_db: Path):
    actor = user_id(hardening_db)

    def new_task(identity: str) -> dict:
        return submit_task(
            hardening_db,
            task_id_prefix=identity,
            task_type="content_generation",
            subject_ref=identity,
            operation_identity=f"content_plan:{identity}",
            execution_lane=STANDARD_BACKGROUND,
            payload={"operation": "content_plan"},
            stage="等待",
            created_by_user_id=actor,
            queue_max=20,
            gpu_pending_per_user_max=3,
        )

    expired = new_task("expired_lease")
    live = new_task("live_lease")
    assert claim_task(
        hardening_db,
        expired["task_id"],
        worker_id="old-worker",
        lease_seconds=120,
        stage="执行",
        task_type="content_generation",
    )
    assert claim_task(
        hardening_db,
        live["task_id"],
        worker_id="live-worker",
        lease_seconds=120,
        stage="执行",
        task_type="content_generation",
    )
    with transaction(hardening_db) as connection:
        connection.execute(
            "UPDATE tasks SET lease_expires_at = ? WHERE task_id = ?",
            (iso_utc(datetime.now(timezone.utc) - timedelta(seconds=1)), expired["task_id"]),
        )

    recovered = recover_expired_tasks(
        hardening_db, task_types=("content_generation",)
    )
    assert recovered == [expired["task_id"]]
    assert get_task(hardening_db, expired["task_id"])["status"] == "queued"
    assert get_task(hardening_db, live["task_id"])["status"] == "running"


def test_case_recovery_prefers_exact_attempt_over_older_canonical(
    settings: Settings,
    tmp_path: Path,
):
    settings = Settings(
        **{
            **settings.__dict__,
            "pipeline_root": tmp_path / "isolated-pipeline",
        }
    )
    apply_migrations(
        settings.database_path,
        Path(__file__).resolve().parents[1] / "migrations",
    )
    task = create_case_task(
        settings.database_path,
        source_url="https://www.douyin.com/video/7999999999999999999",
        case_id="7999999999999999999",
        operator_profile_hint="mix",
        reanalyze=True,
    )
    canonical = (
        settings.pipeline_root
        / "data"
        / "cases"
        / task["subject_ref"]
        / "case_v1.json"
    )
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text("{}", encoding="utf-8")
    attempt = (
        settings.pipeline_root
        / "data"
        / "case_analysis_attempts"
        / task["subject_ref"]
        / task["task_id"]
        / "case_analysis_attempt_v1.json"
    )
    attempt.parent.mkdir(parents=True, exist_ok=True)
    attempt.write_text('{"status":"running"}', encoding="utf-8")

    runner = CaseTaskRunner(settings)
    try:
        assert runner._reconcile_business_state(task["task_id"]) is None
        attempt.write_text('{"status":"awaiting_review"}', encoding="utf-8")
        assert runner._reconcile_business_state(task["task_id"]) == "awaiting_review"
    finally:
        runner.close()


def test_task_progress_and_heartbeat_writes_are_throttled(hardening_db: Path):
    task = submit_task(
        hardening_db,
        task_id_prefix="progress",
        task_type="content_generation",
        subject_ref="progress_001",
        operation_identity="content_plan:progress_001",
        execution_lane=STANDARD_BACKGROUND,
        payload={},
        stage="执行",
        created_by_user_id=user_id(hardening_db),
        queue_max=20,
        gpu_pending_per_user_max=3,
    )
    assert claim_task(
        hardening_db,
        task["task_id"],
        worker_id="worker",
        lease_seconds=120,
        stage="执行",
        task_type="content_generation",
    )
    before = get_task(hardening_db, task["task_id"])
    update_task(
        hardening_db,
        task["task_id"],
        status="running",
        progress=before["progress"],
        stage=before["stage"],
        worker_id="worker",
        lease_seconds=120,
        heartbeat_interval_seconds=10,
    )
    after = get_task(hardening_db, task["task_id"])
    assert after["updated_at"] == before["updated_at"]
    assert after["heartbeat_at"] == before["heartbeat_at"]


def test_fake_background_operation_completes_without_model_call(
    settings: Settings, tmp_path: Path
):
    with TestClient(main_module.build_app(settings)):
        provision_user(settings.database_path, "13800000000")
        connection = connect(settings.database_path)
        try:
            actor = int(connection.execute("SELECT id FROM users LIMIT 1").fetchone()["id"])
        finally:
            connection.close()
        marker = tmp_path / "canonical-content-plan.json"

        def fake_handler(_settings: Settings, request_id: str) -> dict:
            marker.write_text(json.dumps({"request_id": request_id}), encoding="utf-8")
            return {"state": {"content_plan": {"ready": True}}}

        task = create_background_task(
            settings,
            operation="content_plan",
            request_id="request_fake_001",
            created_by_user_id=actor,
        )
        runner = BackgroundTaskRunner(settings, handlers={"content_plan": fake_handler})
        try:
            runner._run(task["task_id"])
        finally:
            runner.close()
        completed = get_task(settings.database_path, task["task_id"])
        assert completed["status"] == "completed"
        assert marker.is_file()
        assert json.loads(marker.read_text())["request_id"] == "request_fake_001"


def test_global_gpu_lock_blocks_a_second_process_and_releases_after_exit(tmp_path: Path):
    scripts = Path(__file__).resolve().parents[2] / "ops-pipeline" / "scripts"
    pipeline_root = tmp_path / "pipeline"
    ready = tmp_path / "ready"
    release = tmp_path / "release"
    code = (
        "import sys,time; from pathlib import Path; "
        f"sys.path.insert(0,{str(scripts)!r}); "
        "from operation_lock_v1 import operation_lock; "
        f"root=Path({str(pipeline_root)!r}); ready=Path({str(ready)!r}); release=Path({str(release)!r}); "
        "\nwith operation_lock(root,'global_gpu',timeout_seconds=2):"
        "\n ready.write_text('ready');"
        "\n while not release.exists(): time.sleep(0.02)"
    )
    process = subprocess.Popen([sys.executable, "-c", code])
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        with pytest.raises(OperationLockTimeout):
            with operation_lock(
                pipeline_root, "global_gpu", timeout_seconds=0.15, poll_seconds=0.02
            ):
                pass
        release.write_text("release", encoding="utf-8")
        assert process.wait(timeout=5) == 0
        with operation_lock(pipeline_root, "global_gpu", timeout_seconds=0.2):
            pass
    finally:
        release.write_text("release", encoding="utf-8")
        if process.poll() is None:
            process.kill()


def test_operation_lock_releases_after_exception(tmp_path: Path):
    with pytest.raises(RuntimeError):
        with operation_lock(tmp_path, "persona:fixture", timeout_seconds=0):
            raise RuntimeError("fake mutation failed")
    with operation_lock(tmp_path, "persona:fixture", timeout_seconds=0):
        pass


@pytest.mark.parametrize("scope", ["persona", "case"])
def test_same_entity_double_mutation_allows_only_one_writer(
    tmp_path: Path, scope: str
):
    entered = threading.Event()
    release = threading.Event()
    outcomes: list[str] = []
    artifact = tmp_path / f"{scope}.json"
    receipt = tmp_path / f"{scope}.receipt.json"

    def mutate(wait: bool) -> None:
        try:
            with operation_lock(tmp_path, f"{scope}:same", timeout_seconds=0):
                current = json.loads(artifact.read_text(encoding="utf-8")) if artifact.exists() else {"revision": 0}
                entered.set()
                if wait:
                    release.wait(timeout=2)
                current["revision"] += 1
                artifact.write_text(json.dumps(current), encoding="utf-8")
                receipt.write_text(json.dumps({"revision": current["revision"]}), encoding="utf-8")
                outcomes.append("mutated")
        except OperationLockTimeout:
            outcomes.append("conflict")

    first = threading.Thread(target=mutate, args=(True,))
    first.start()
    assert entered.wait(timeout=2)
    second = threading.Thread(target=mutate, args=(False,))
    second.start()
    second.join(timeout=2)
    release.set()
    first.join(timeout=2)
    assert sorted(outcomes) == ["conflict", "mutated"]
    assert json.loads(artifact.read_text())["revision"] == 1
    assert json.loads(receipt.read_text())["revision"] == 1


@pytest.mark.parametrize("entity", ["persona", "case"])
def test_console_authority_routes_return_409_for_simultaneous_same_entity(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    entity: str,
):
    app = main_module.build_app(settings)
    entered = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    if entity == "persona":
        def fake_persona(settings, *, business_id, reviewer, note):
            calls.append(reviewer)
            entered.set()
            release.wait(timeout=2)
            return {"business_id": business_id, "approved": True}

        monkeypatch.setattr(main_module, "approve_business_persona", fake_persona)
        route = "/api/customers/fixture_business/persona/approve"
        body = {"note": "approve"}
    else:
        def fake_case(settings, case_id, *, reviewer, note):
            calls.append(reviewer)
            entered.set()
            release.wait(timeout=2)
            return {"case_id": case_id, "review": {"approved": True}}

        monkeypatch.setattr(main_module, "approve_case_candidate", fake_case)
        route = "/api/cases/7999999999999999966/review"
        body = {"decision": "approve", "reason": "reviewed"}

    with TestClient(app) as first_client, TestClient(app) as second_client:
        provision_user(settings.database_path, "13800000000")
        first_csrf = login_and_change_password(first_client)
        second_login = second_client.post(
            "/api/auth/login",
            json={"phone": "13800000000", "password": "ReviewConsole2026!"},
        )
        second_csrf = second_login.json()["csrf_token"]
        first_response: list[Any] = []

        thread = threading.Thread(
            target=lambda: first_response.append(
                first_client.post(
                    route,
                    headers={"X-CSRF-Token": first_csrf},
                    json=body,
                )
            )
        )
        thread.start()
        assert entered.wait(timeout=2)
        conflict = second_client.post(
            route,
            headers={"X-CSRF-Token": second_csrf},
            json=body,
        )
        release.set()
        thread.join(timeout=2)

    assert first_response[0].status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "OPERATION_IN_PROGRESS"
    assert calls == ["13800000000"]


def test_business_scoped_intake_allocation_cannot_duplicate_ids(tmp_path: Path):
    allocated: list[str] = []

    def allocate() -> None:
        with operation_lock(tmp_path, "business:fixture", timeout_seconds=2):
            existing = sorted(tmp_path.glob("intake_*.json"))
            intake_id = f"intake_{len(existing) + 1:04d}"
            time.sleep(0.03)
            (tmp_path / f"{intake_id}.json").write_text("{}", encoding="utf-8")
            allocated.append(intake_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: allocate(), range(2)))
    assert sorted(allocated) == ["intake_0001", "intake_0002"]


def test_business_scoped_ledger_closure_cannot_lose_update(tmp_path: Path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"entries": []}), encoding="utf-8")

    def close(entry: str) -> None:
        with operation_lock(tmp_path, "business:fixture", timeout_seconds=2):
            value = json.loads(ledger.read_text(encoding="utf-8"))
            time.sleep(0.03)
            value["entries"].append(entry)
            ledger.write_text(json.dumps(value), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(close, ("request-a", "request-b")))
    assert sorted(json.loads(ledger.read_text())["entries"]) == ["request-a", "request-b"]


def test_sqlite_wal_busy_timeout_and_session_maintenance(hardening_db: Path):
    connection = connect(hardening_db)
    try:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
    finally:
        connection.close()

    token, context = create_session(hardening_db, user_id(hardening_db), 1)
    before_connection = connect(hardening_db)
    try:
        before = before_connection.execute(
            "SELECT last_seen_at FROM sessions WHERE token_hash = ?", (context.token_hash,)
        ).fetchone()["last_seen_at"]
    finally:
        before_connection.close()
    assert resolve_session(hardening_db, token, last_seen_interval_seconds=300)
    after_connection = connect(hardening_db)
    try:
        after = after_connection.execute(
            "SELECT last_seen_at FROM sessions WHERE token_hash = ?", (context.token_hash,)
        ).fetchone()["last_seen_at"]
    finally:
        after_connection.close()
    assert after == before

    with transaction(hardening_db) as connection:
        connection.execute(
            "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
            (iso_utc(datetime.now(timezone.utc) - timedelta(seconds=1)), context.token_hash),
        )
    assert cleanup_expired_sessions(hardening_db) == 1


def test_path_and_secret_hardening(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "approved"
    root.mkdir()
    assert resolve_within(root, "request_001").is_relative_to(root.resolve())
    with pytest.raises(ValueError):
        resolve_within(root, "..", "escape")
    for invalid in ("../request", "C:\\absolute", "%2e%2e", "/absolute"):
        with pytest.raises(ValueError):
            validate_identifier(invalid, field="request_id")

    settings = Settings(
        repo_root=tmp_path,
        console_root=tmp_path / "internal-console",
        pipeline_root=tmp_path / "ops-pipeline",
        database_path=tmp_path / "console.sqlite3",
        python_executable=sys.executable,
    )
    with pytest.raises(CanonicalOperationError):
        case_media_path(settings, "../outside")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-secret-never-log")
    monkeypatch.setenv("AIVO_FRP_TOKEN", "edge-secret-never-pass")
    assert "DEEPSEEK_API_KEY" not in content_pipeline_env(needs_deepseek=False)
    assert "DEEPSEEK_API_KEY" not in news_pipeline_env()
    assert content_pipeline_env(needs_deepseek=True)["DEEPSEEK_API_KEY"] == "test-secret-never-log"
    assert "AIVO_FRP_TOKEN" not in content_pipeline_env(needs_deepseek=True)
    assert "AIVO_FRP_TOKEN" not in news_pipeline_env()


def test_secure_cookie_and_authenticated_task_actor_cannot_be_spoofed(
    settings: Settings,
):
    production = Settings(
        **{
            **settings.__dict__,
            "secure_cookies": True,
        }
    )
    with TestClient(main_module.build_app(production), base_url="https://testserver") as client:
        provision_user(production.database_path, "13800000000")
        login = client.post(
            "/api/auth/login",
            json={"phone": "13800000000", "password": "123456"},
        )
        assert "Secure" in login.headers["set-cookie"]
        csrf = login.json()["csrf_token"]
        changed = client.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": csrf},
            json={
                "current_password": "123456",
                "new_password": "Hardening2026!",
                "confirm_password": "Hardening2026!",
            },
        )
        csrf = changed.json()["csrf_token"]
        response = client.post(
            "/api/cases/analyze",
            headers={"X-CSRF-Token": csrf},
            json={
                "url": "https://www.douyin.com/video/7999999999999999977",
                "created_by_user_id": 999999,
                "operator_profile_hint": "mix",
            },
        )
        assert response.status_code == 200
        assert response.json()["task"]["created_by"]["phone"] == "13800000000"
        assert response.json()["task"]["created_by"]["user_id"] != 999999


def test_three_fake_users_can_submit_and_read_shared_tasks_without_db_lock(
    settings: Settings,
):
    app = main_module.build_app(settings)
    with TestClient(app) as client:
        phones = ["13800000001", "13800000002", "13800000003"]
        csrf_tokens: dict[str, str] = {}
        for phone in phones:
            provision_user(settings.database_path, phone)
            login = client.post(
                "/api/auth/login", json={"phone": phone, "password": "123456"}
            )
            changed = client.post(
                "/api/auth/change-password",
                headers={"X-CSRF-Token": login.json()["csrf_token"]},
                json={
                    "current_password": "123456",
                    "new_password": f"Hardening-{phone}!",
                    "confirm_password": f"Hardening-{phone}!",
                },
            )
            csrf_tokens[phone] = changed.json()["csrf_token"]

        def submit(index: int) -> int:
            local = TestClient(app)
            login = local.post(
                "/api/auth/login",
                json={"phone": phones[index], "password": f"Hardening-{phones[index]}!"},
            )
            response = local.post(
                "/api/cases/analyze",
                headers={"X-CSRF-Token": login.json()["csrf_token"]},
                json={"url": f"https://www.douyin.com/video/78899999999999999{index:02d}", "operator_profile_hint": "mix"},
            )
            local.close()
            return response.status_code

        with ThreadPoolExecutor(max_workers=3) as executor:
            statuses = list(executor.map(submit, range(3)))
        assert statuses == [200, 200, 200]
        tasks = client.get("/api/tasks").json()["tasks"]
        assert len(tasks) == 3
        assert {item["created_by"]["phone"] for item in tasks} == set(phones)


def test_production_templates_never_trust_forwarded_wildcard():
    root = Path(__file__).resolve().parents[2] / "deploy" / "local-node"
    text = "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in root.rglob("*")
        if path.is_file()
    )
    assert '--forwarded-allow-ips "*"' not in text
    assert "--host 127.0.0.1" in text
    assert "--workers 1" in text
    assert "AIVO_SECURE_COOKIES=1" in text
