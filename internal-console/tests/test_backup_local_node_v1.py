from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.auth_service import provision_user
from app.database import apply_migrations
from app.operation_lock import operation_lock
from app.task_service import STANDARD_BACKGROUND, claim_task, submit_task


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backup_local_node_v1.py"
SPEC = importlib.util.spec_from_file_location("backup_local_node_v1", SCRIPT_PATH)
assert SPEC and SPEC.loader
backup_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_module)


@pytest.fixture()
def backup_sources(tmp_path: Path):
    repo = tmp_path / "repo"
    pipeline = repo / "ops-pipeline"
    data = pipeline / "data" / "personas" / "fixture"
    output = pipeline / "output"
    deploy = repo / "deploy" / "local-node"
    data.mkdir(parents=True)
    output.mkdir(parents=True)
    deploy.mkdir(parents=True)
    (data / "persona_v1.json").write_text('{"approved":true}', encoding="utf-8")
    (pipeline / "data" / ".locks").mkdir()
    (pipeline / "data" / ".locks" / "runtime.lock").write_text("lock")
    (output / "approved.xlsx").write_bytes(b"xlsx")
    (output / "approved.export_receipt.json").write_text(
        '{"validation_passed":true}', encoding="utf-8"
    )
    (deploy / "env.production.example").write_text(
        "AIVO_SECURE_COOKIES=1\n", encoding="utf-8"
    )
    database = repo / "internal-console" / "var" / "console.sqlite3"
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    apply_migrations(database, migrations)
    provision_user(database, "13800000000")
    destination = tmp_path / "external-backups"
    return repo, pipeline, database, destination


def test_online_backup_manifest_restore_smoke_and_exclusions(backup_sources):
    repo, pipeline, database, destination = backup_sources
    backup_root = backup_module.create_backup(
        destination=destination,
        database_path=database,
        pipeline_root=pipeline,
        repo_root=repo,
        now=datetime(2026, 9, 19, 1, 2, 3, tzinfo=timezone.utc),
    )
    result = backup_module.validate_backup(backup_root)
    assert result["ok"] is True
    assert (backup_root / "internal-console" / "console.sqlite3").is_file()
    assert (
        backup_root
        / "ops-pipeline"
        / "data"
        / "personas"
        / "fixture"
        / "persona_v1.json"
    ).is_file()
    assert not (backup_root / "ops-pipeline" / "data" / ".locks").exists()
    manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]


def test_backup_fails_closed_while_task_is_running(backup_sources):
    repo, pipeline, database, destination = backup_sources
    connection = __import__("sqlite3").connect(database)
    try:
        actor = connection.execute("SELECT id FROM users LIMIT 1").fetchone()[0]
    finally:
        connection.close()
    task = submit_task(
        database,
        task_id_prefix="backup-gate",
        task_type="content_generation",
        subject_ref="request_backup",
        operation_identity="content_plan:request_backup",
        execution_lane=STANDARD_BACKGROUND,
        payload={},
        stage="等待",
        created_by_user_id=actor,
        queue_max=20,
        gpu_pending_per_user_max=3,
    )
    assert claim_task(
        database,
        task["task_id"],
        worker_id="fake-worker",
        lease_seconds=120,
        stage="执行",
        task_type="content_generation",
    )
    with pytest.raises(backup_module.BackupError) as exc:
        backup_module.create_backup(
            destination=destination,
            database_path=database,
            pipeline_root=pipeline,
            repo_root=repo,
        )
    assert exc.value.code == "BACKUP_REQUIRES_IDLE_WINDOW"


def test_backup_fails_closed_while_authority_mutation_barrier_is_held(
    backup_sources,
):
    repo, pipeline, database, destination = backup_sources
    with operation_lock(
        pipeline,
        backup_module.AUTHORITY_BACKUP_GATE,
        timeout_seconds=0.0,
        shared=True,
    ):
        with pytest.raises(backup_module.BackupError) as exc:
            backup_module.create_backup(
                destination=destination,
                database_path=database,
                pipeline_root=pipeline,
                repo_root=repo,
            )
    assert exc.value.code == "BACKUP_REQUIRES_IDLE_WINDOW"


def test_backup_checksum_tamper_is_detected(backup_sources):
    repo, pipeline, database, destination = backup_sources
    backup_root = backup_module.create_backup(
        destination=destination,
        database_path=database,
        pipeline_root=pipeline,
        repo_root=repo,
    )
    artifact = (
        backup_root
        / "ops-pipeline"
        / "data"
        / "personas"
        / "fixture"
        / "persona_v1.json"
    )
    artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(backup_module.BackupError) as exc:
        backup_module.validate_backup(backup_root)
    assert exc.value.code == "BACKUP_CHECKSUM_MISMATCH"


def test_retention_keeps_seven_daily_and_four_weekly(tmp_path: Path):
    destination = tmp_path / "backups"
    destination.mkdir()
    start = datetime(2026, 9, 19, tzinfo=timezone.utc)
    for offset in range(45):
        created = start - timedelta(days=offset)
        root = destination / f"aivo-local-node-{created:%Y%m%dT000000Z}"
        root.mkdir()
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": backup_module.BACKUP_SCHEMA_VERSION,
                    "created_at": created.isoformat().replace("+00:00", "Z"),
                    "files": [],
                }
            ),
            encoding="utf-8",
        )
    backup_module.apply_retention(destination, daily=7, weekly=4)
    remaining = list(destination.glob("aivo-local-node-*"))
    assert 7 <= len(remaining) <= 11


def test_backup_destination_inside_repo_is_rejected(backup_sources):
    repo, pipeline, database, _ = backup_sources
    with pytest.raises(backup_module.BackupError) as exc:
        backup_module.create_backup(
            destination=repo / "backups",
            database_path=database,
            pipeline_root=pipeline,
            repo_root=repo,
        )
    assert exc.value.code == "BACKUP_DESTINATION_INVALID"


def test_backup_supports_windows_paths_longer_than_max_path(backup_sources):
    repo, pipeline, database, destination = backup_sources
    long_relative = Path("case_analysis_attempts")
    for index in range(5):
        long_relative /= f"segment_{index}_" + ("x" * 48)
    source = pipeline / "data" / long_relative / "checkpoint.json"
    os.makedirs(backup_module._filesystem_path(source.parent), exist_ok=True)
    with open(backup_module._filesystem_path(source), "w", encoding="utf-8") as handle:
        handle.write('{"status":"checkpoint"}')
    assert len(str(destination / "placeholder" / long_relative)) > 260

    first_backup = backup_module.create_backup(
        destination=destination,
        database_path=database,
        pipeline_root=pipeline,
        repo_root=repo,
        retention_daily=1,
        retention_weekly=0,
        now=datetime(2026, 9, 19, 1, 0, tzinfo=timezone.utc),
    )
    backup_root = backup_module.create_backup(
        destination=destination,
        database_path=database,
        pipeline_root=pipeline,
        repo_root=repo,
        retention_daily=1,
        retention_weekly=0,
        now=datetime(2026, 9, 19, 1, 1, tzinfo=timezone.utc),
    )
    assert not os.path.exists(backup_module._filesystem_path(first_backup))
    result = backup_module.validate_backup(backup_root)
    assert result["ok"] is True
    manifest = json.loads((backup_root / "manifest.json").read_text(encoding="utf-8"))
    expected = (Path("ops-pipeline") / "data" / long_relative / "checkpoint.json").as_posix()
    assert expected in {item["path"] for item in manifest["files"]}
