from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(database_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def apply_migrations(database_path: Path, migrations_path: Path) -> None:
    with transaction(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for migration in sorted(migrations_path.glob("*.sql")):
            version = migration.stem
            if version in applied:
                continue
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (version,),
            )
