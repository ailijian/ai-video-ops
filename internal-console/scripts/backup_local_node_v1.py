from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import sys
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any


_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "ops-pipeline" / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from operation_lock_v1 import OperationLockTimeout, operation_lock  # noqa: E402


BACKUP_SCHEMA_VERSION = "local-node-backup-v1.0"
BACKUP_PREFIX = "aivo-local-node-"
AUTHORITY_BACKUP_GATE = "authority_backup_gate"


class BackupError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def exclusive_backup_guard(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        pipeline_root = Path(kwargs["pipeline_root"])
        try:
            with operation_lock(
                pipeline_root,
                AUTHORITY_BACKUP_GATE,
                timeout_seconds=0.0,
            ):
                return function(*args, **kwargs)
        except OperationLockTimeout as exc:
            raise BackupError(
                "BACKUP_REQUIRES_IDLE_WINDOW",
                "Backup cannot overlap an authority mutation or another backup.",
            ) from exc

    return guarded


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_idle(database_path: Path) -> None:
    connection = sqlite3.connect(database_path, timeout=10)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = 'running'"
        ).fetchone()
    except sqlite3.Error as exc:
        raise BackupError("BACKUP_DATABASE_UNAVAILABLE", str(exc)) from exc
    finally:
        connection.close()
    if row and int(row[0]) > 0:
        raise BackupError(
            "BACKUP_REQUIRES_IDLE_WINDOW",
            "Backup requires an idle window with no running task.",
        )


def online_sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(source, timeout=10)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
        destination_connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        destination_connection.close()
        source_connection.close()


def _excluded(path: Path) -> bool:
    lowered = {part.lower() for part in path.parts}
    return bool(
        lowered.intersection(
            {".locks", ".venv", "__pycache__", ".pytest_cache", "cache", "tmp", "temp"}
        )
        or path.suffix.lower() in {".lock", ".tmp", ".pyc"}
    )


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if _excluded(relative):
            continue
        target = destination / relative
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def _manifest_files(root: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == "manifest.json":
            continue
        values.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return values


def validate_backup(backup_root: Path) -> dict[str, Any]:
    backup_root = backup_root.resolve()
    manifest_path = backup_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupError("BACKUP_MANIFEST_INVALID", "Unexpected backup schema.")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise BackupError("BACKUP_MANIFEST_INVALID", "Backup file manifest is missing.")
    for item in files:
        relative = str((item or {}).get("path") or "")
        candidate = (backup_root / relative).resolve()
        try:
            candidate.relative_to(backup_root)
        except ValueError as exc:
            raise BackupError("BACKUP_MANIFEST_INVALID", "Manifest path escapes backup root.") from exc
        if not candidate.is_file() or sha256_file(candidate) != item.get("sha256"):
            raise BackupError("BACKUP_CHECKSUM_MISMATCH", relative)

    sqlite_path = backup_root / "internal-console" / "console.sqlite3"
    with tempfile.TemporaryDirectory(prefix="aivo-restore-smoke-") as temporary:
        restored = Path(temporary) / "console.sqlite3"
        shutil.copy2(sqlite_path, restored)
        connection = sqlite3.connect(restored)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError("BACKUP_SQLITE_INVALID", "SQLite integrity check failed.")
            connection.execute("SELECT version FROM schema_migrations").fetchall()
        finally:
            connection.close()
    return {"ok": True, "file_count": len(files), "backup_root": str(backup_root)}


def apply_retention(destination: Path, *, daily: int, weekly: int) -> list[Path]:
    destination = destination.resolve()
    candidates: list[tuple[datetime, Path]] = []
    for path in destination.glob(f"{BACKUP_PREFIX}*"):
        resolved_path = path.resolve()
        if resolved_path.parent != destination:
            continue
        path = resolved_path
        manifest_path = path / "manifest.json"
        if not path.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(
                str(manifest["created_at"]).replace("Z", "+00:00")
            )
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue
        candidates.append((created, path))

    candidates.sort(reverse=True)
    daily_keep: list[Path] = []
    daily_keys: set[str] = set()
    weekly_keep: list[Path] = []
    weekly_keys: set[tuple[int, int]] = set()
    for created, path in candidates:
        day_key = created.date().isoformat()
        if day_key not in daily_keys and len(daily_keep) < daily:
            daily_keys.add(day_key)
            daily_keep.append(path)
        week = created.isocalendar()
        week_key = (week.year, week.week)
        if week_key not in weekly_keys and len(weekly_keep) < weekly:
            weekly_keys.add(week_key)
            weekly_keep.append(path)

    keep = set(daily_keep + weekly_keep)
    removed: list[Path] = []
    for _, path in candidates:
        if path not in keep:
            if path.resolve().parent != destination:
                raise BackupError(
                    "BACKUP_RETENTION_PATH_INVALID",
                    "Retention target escaped the backup destination.",
                )
            shutil.rmtree(path)
            removed.append(path)
    return removed


@exclusive_backup_guard
def create_backup(
    *,
    destination: Path,
    database_path: Path,
    pipeline_root: Path,
    repo_root: Path,
    retention_daily: int = 7,
    retention_weekly: int = 4,
    now: datetime | None = None,
) -> Path:
    destination = destination.expanduser().resolve()
    repo_root = repo_root.resolve()
    try:
        destination.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise BackupError(
            "BACKUP_DESTINATION_INVALID",
            "Backup destination must be outside the project directory.",
        )
    destination.mkdir(parents=True, exist_ok=True)
    require_idle(database_path)

    created = now or datetime.now(timezone.utc)
    name = BACKUP_PREFIX + created.strftime("%Y%m%dT%H%M%SZ")
    final_root = destination / name
    if final_root.exists():
        raise BackupError("BACKUP_ALREADY_EXISTS", str(final_root))
    temporary_root = destination / f".{name}.{os.getpid()}.tmp"
    temporary_root.mkdir(parents=False, exist_ok=False)
    try:
        online_sqlite_backup(
            database_path,
            temporary_root / "internal-console" / "console.sqlite3",
        )
        _copy_tree(pipeline_root / "data", temporary_root / "ops-pipeline" / "data")
        _copy_tree(pipeline_root / "output", temporary_root / "ops-pipeline" / "output")
        _copy_tree(repo_root / "deploy" / "local-node", temporary_root / "configuration")
        require_idle(database_path)
        manifest = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "created_at": created.isoformat().replace("+00:00", "Z"),
            "source": {
                "database": str(database_path.resolve()),
                "pipeline_root": str(pipeline_root.resolve()),
            },
            "files": _manifest_files(temporary_root),
        }
        (temporary_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        validate_backup(temporary_root)
        os.replace(temporary_root, final_root)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise
    apply_retention(
        destination,
        daily=max(1, retention_daily),
        weekly=max(0, retention_weekly),
    )
    return final_root


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up AI Video Ops local node data.")
    parser.add_argument("--destination")
    parser.add_argument("--database")
    parser.add_argument("--pipeline-root")
    parser.add_argument("--repo-root")
    parser.add_argument("--retention-daily", type=int, default=7)
    parser.add_argument("--retention-weekly", type=int, default=4)
    parser.add_argument("--validate", default=None)
    args = parser.parse_args()
    if args.validate:
        result = validate_backup(Path(args.validate))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    missing = [
        name
        for name in ("destination", "database", "pipeline_root", "repo_root")
        if not getattr(args, name)
    ]
    if missing:
        parser.error("backup mode requires: " + ", ".join(missing))
    try:
        path = create_backup(
            destination=Path(args.destination),
            database_path=Path(args.database),
            pipeline_root=Path(args.pipeline_root),
            repo_root=Path(args.repo_root),
            retention_daily=args.retention_daily,
            retention_weekly=args.retention_weekly,
        )
    except BackupError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "message": str(exc)}))
        return 2
    print(json.dumps({"ok": True, "backup_root": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
