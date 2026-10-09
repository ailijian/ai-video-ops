"""Migration 004 safety checks, including a read-only online-backup audit CLI."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from app.auth_service import provision_user
from app.database import apply_migrations, transaction
from app.task_service import create_case_task, get_task, patch_task_payload

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def snapshot(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name: sorted(db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                for name in names}


def online_backup(source, target):
    assert source.resolve() != target.resolve() and not target.exists()
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)


def integrity(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        return {"integrity_check": db.execute("PRAGMA integrity_check").fetchone()[0],
                "foreign_key_errors": len(db.execute("PRAGMA foreign_key_check").fetchall())}


def legacy_database(root):
    root.mkdir()
    migrations = root / "migrations"
    migrations.mkdir()
    for name in ("001_initial.sql", "002_speaker_analysis_task.sql", "003_local_production_node_hardening.sql"):
        shutil.copy2(MIGRATIONS / name, migrations / name)
    path = root / "legacy.sqlite3"
    apply_migrations(path, migrations)
    provision_user(path, "19900001101", "OfflineReview2026!")
    task = create_case_task(path, source_url="https://www.douyin.com/video/7999999999999999700",
                            case_id="7999999999999999700", industry="餐饮")
    patch_task_payload(path, task["task_id"], {"profile": "mix"})
    return path, task


def test_migration_preserves_populated_backup_and_detects_repeated_start(tmp_path):
    source, task = legacy_database(tmp_path / "legacy")
    copy = tmp_path / "upgrade.sqlite3"
    before = snapshot(source)
    online_backup(source, copy)
    apply_migrations(copy, MIGRATIONS)
    first = snapshot(copy)
    for table, rows in before.items():
        if table != "schema_migrations":
            assert first[table] == rows
    assert get_task(copy, task["task_id"])["payload"]["profile"] == "mix"
    assert len(first["schema_migrations"]) == len(before["schema_migrations"]) + 1
    with transaction(copy) as db:
        db.execute("INSERT INTO case_intake_groups VALUES ('historical-group','request','digest',1,'2026-10-09')")
        db.execute("INSERT INTO case_intake_items(group_id,position,source_url,task_id,state) VALUES (?,?,?,?,?)",
                   ("historical-group", 0, task["payload"]["source_url"], task["task_id"], "linked"))
    populated = snapshot(copy)
    apply_migrations(copy, MIGRATIONS)
    assert snapshot(copy) == populated
    assert snapshot(source) == before
    assert integrity(copy) == {"integrity_check": "ok", "foreign_key_errors": 0}


def test_failed_migration_rolls_back_ddl_rows_and_applied_marker(tmp_path):
    source, _ = legacy_database(tmp_path / "legacy")
    before = snapshot(source)
    broken = tmp_path / "broken"
    shutil.copytree(MIGRATIONS, broken)
    migration = broken / "004_case_intake_groups.sql"
    migration.write_text(migration.read_text() + "\nINSERT INTO nonexistent_table VALUES (1);\n")
    with pytest.raises(sqlite3.OperationalError):
        apply_migrations(source, broken)
    assert snapshot(source) == before
    assert "case_intake_groups" not in snapshot(source)
    apply_migrations(source, MIGRATIONS)
    assert integrity(source) == {"integrity_check": "ok", "foreign_key_errors": 0}


def test_concurrent_initializers_apply_migration_once(tmp_path):
    source, _ = legacy_database(tmp_path / "legacy")
    before = snapshot(source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: apply_migrations(source, MIGRATIONS), range(2)))
    after = snapshot(source)
    assert len(after["schema_migrations"]) == 4
    assert after["users"] == before["users"] and after["tasks"] == before["tasks"]


def audit_existing_database(source: Path, output: Path):
    """Only source access is SQLite mode=ro backup; reports contain no row values."""
    if output.exists():
        raise ValueError("Use a new evidence directory")
    output.mkdir(parents=True)
    backup, upgraded = output / "before.sqlite3", output / "migrated.sqlite3"
    online_backup(source, backup)
    before = snapshot(backup)
    assert before["users"] and before["tasks"], "Expected an existing populated database"
    assert not any(row[0] == "004_case_intake_groups" for row in before["schema_migrations"])
    online_backup(backup, upgraded)
    apply_migrations(upgraded, MIGRATIONS)
    after = snapshot(upgraded)
    preserved = all(after[table] == rows for table, rows in before.items() if table != "schema_migrations")
    assert preserved
    apply_migrations(upgraded, MIGRATIONS)
    assert snapshot(upgraded) == after
    restored = output / "restore-smoke.sqlite3"
    online_backup(backup, restored)
    assert snapshot(restored) == before
    failed = output / "rollback.sqlite3"
    online_backup(backup, failed)
    broken = output / "broken-migrations"
    shutil.copytree(MIGRATIONS, broken)
    migration = broken / "004_case_intake_groups.sql"
    migration.write_text(migration.read_text() + "\nINSERT INTO nonexistent_table VALUES (1);\n")
    try:
        apply_migrations(failed, broken)
    except sqlite3.OperationalError:
        assert snapshot(failed) == before
    else:
        raise AssertionError("Injected failure did not fail")
    apply_migrations(failed, MIGRATIONS)
    checks = {name: integrity(path) for name, path in (("backup", backup), ("upgraded", upgraded),
                                                     ("restored", restored), ("recovered", failed))}
    assert all(check == {"integrity_check": "ok", "foreign_key_errors": 0} for check in checks.values())
    report = {"source": str(source), "source_access": "SQLite mode=ro online backup",
              "historical_table_counts": {name: len(rows) for name, rows in before.items()},
              "historical_rows_preserved": preserved, "repeat_start_unchanged": True,
              "failure_rollback_verified": True, "recovery_after_failure_verified": True,
              "backup_restore_verified": True, "checks": checks,
              "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
              "migrated_versions": [row[0] for row in after["schema_migrations"]],
              "migration_004_sha256": hashlib.sha256((MIGRATIONS / "004_case_intake_groups.sql").read_bytes()).hexdigest()}
    (output / "migration-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    audit_existing_database(arguments.source.resolve(), arguments.output.resolve())
