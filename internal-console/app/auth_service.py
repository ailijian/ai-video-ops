from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .database import connect, transaction
from .security import (
    hash_password,
    hash_session_token,
    new_csrf_token,
    new_session_token,
    verify_password,
)


PHONE_RE = re.compile(r"^\+?\d{6,20}$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat().replace("+00:00", "Z")


def normalize_phone(phone: str) -> str:
    normalized = re.sub(r"[\s()-]", "", phone.strip())
    if not PHONE_RE.fullmatch(normalized):
        raise ValueError("invalid phone format")
    return normalized


def validate_new_password(password: str, current_password: str | None = None) -> None:
    if len(password) < 8:
        raise ValueError("新密码至少需要 8 个字符")
    if password == "123456":
        raise ValueError("新密码不能继续使用初始密码")
    if current_password is not None and password == current_password:
        raise ValueError("新密码不能与当前密码相同")
    if password.isspace():
        raise ValueError("新密码不能只包含空格")


@dataclass(frozen=True)
class SessionContext:
    token_hash: str
    csrf_token: str
    user: dict[str, Any]


def provision_user(
    database_path: Path,
    phone: str,
    initial_password: str = "123456",
    *,
    reset_existing: bool = False,
) -> str:
    normalized = normalize_phone(phone)
    timestamp = iso_utc()
    password_hash = hash_password(initial_password)
    with transaction(database_path) as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE phone = ?", (normalized,)
        ).fetchone()
        if existing is not None:
            if not reset_existing:
                raise ValueError("user already exists")
            connection.execute(
                """
                UPDATE users
                SET password_hash = ?, must_change_password = 1,
                    status = 'active', updated_at = ?
                WHERE id = ?
                """,
                (password_hash, timestamp, existing["id"]),
            )
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (existing["id"],))
            return "reset"
        connection.execute(
            """
            INSERT INTO users(
                phone, password_hash, must_change_password, status, created_at, updated_at
            ) VALUES (?, ?, 1, 'active', ?, ?)
            """,
            (normalized, password_hash, timestamp, timestamp),
        )
    return "created"


def authenticate(database_path: Path, phone: str, password: str) -> dict[str, Any] | None:
    try:
        normalized = normalize_phone(phone)
    except ValueError:
        return None
    connection = connect(database_path)
    try:
        row = connection.execute(
            """
            SELECT id, phone, password_hash, must_change_password, status
            FROM users WHERE phone = ?
            """,
            (normalized,),
        ).fetchone()
    finally:
        connection.close()
    if row is None or row["status"] != "active":
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {
        "id": row["id"],
        "phone": row["phone"],
        "must_change_password": bool(row["must_change_password"]),
        "status": row["status"],
    }


def create_session(
    database_path: Path, user_id: int, session_hours: int
) -> tuple[str, SessionContext]:
    token = new_session_token()
    token_hash = hash_session_token(token)
    csrf_token = new_csrf_token()
    created = now_utc()
    expires = created + timedelta(hours=session_hours)
    with transaction(database_path) as connection:
        connection.execute(
            """
            INSERT INTO sessions(
                token_hash, user_id, csrf_token, expires_at, created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                token_hash,
                user_id,
                csrf_token,
                iso_utc(expires),
                iso_utc(created),
                iso_utc(created),
            ),
        )
        row = connection.execute(
            "SELECT id, phone, must_change_password, status FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("session user disappeared")
    return token, SessionContext(
        token_hash=token_hash,
        csrf_token=csrf_token,
        user={
            "id": row["id"],
            "phone": row["phone"],
            "must_change_password": bool(row["must_change_password"]),
            "status": row["status"],
        },
    )


def resolve_session(database_path: Path, token: str | None) -> SessionContext | None:
    if not token:
        return None
    token_hash = hash_session_token(token)
    timestamp = iso_utc()
    with transaction(database_path) as connection:
        row = connection.execute(
            """
            SELECT s.token_hash, s.csrf_token, s.expires_at,
                   u.id, u.phone, u.must_change_password, u.status
            FROM sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        if expires_at <= now_utc() or row["status"] != "active":
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
            return None
        connection.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
            (timestamp, token_hash),
        )
    return SessionContext(
        token_hash=row["token_hash"],
        csrf_token=row["csrf_token"],
        user={
            "id": row["id"],
            "phone": row["phone"],
            "must_change_password": bool(row["must_change_password"]),
            "status": row["status"],
        },
    )


def change_password(
    database_path: Path,
    session: SessionContext,
    current_password: str,
    new_password: str,
    session_hours: int,
) -> tuple[str, SessionContext]:
    validate_new_password(new_password, current_password)
    connection = connect(database_path)
    try:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?", (session.user["id"],)
        ).fetchone()
    finally:
        connection.close()
    if row is None or not verify_password(current_password, row["password_hash"]):
        raise ValueError("当前密码不正确")

    timestamp = iso_utc()
    with transaction(database_path) as connection:
        connection.execute(
            """
            UPDATE users
            SET password_hash = ?, must_change_password = 0, updated_at = ?
            WHERE id = ?
            """,
            (hash_password(new_password), timestamp, session.user["id"]),
        )
        connection.execute("DELETE FROM sessions WHERE user_id = ?", (session.user["id"],))
    return create_session(database_path, session.user["id"], session_hours)


def delete_session(database_path: Path, token_hash: str) -> None:
    with transaction(database_path) as connection:
        connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
