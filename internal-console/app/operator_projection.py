"""Read-only operator attribution from existing tasks and immutable receipts.

This module is a presentation projection, not a business authority or access control.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .database import connect


def mask_phone(phone: str | None) -> str:
    if not phone:
        return "历史记录 / 未记录"
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else "历史记录 / 未记录"


def _actor(row: Any) -> dict[str, Any] | None:
    if row is None or row["created_by_user_id"] is None:
        return None
    return {"user_id": row["created_by_user_id"], "phone": row["phone"]}


def original_task_actor(
    database_path: Path, task_type: str, subject_ref: str
) -> dict[str, Any] | None:
    if not database_path.is_file():
        return None
    connection = connect(database_path)
    try:
        row = connection.execute(
            """SELECT t.created_by_user_id, u.phone FROM tasks AS t
               LEFT JOIN users AS u ON u.id = t.created_by_user_id
               WHERE t.task_type = ? AND t.subject_ref = ?
               ORDER BY t.created_at ASC, t.task_id ASC LIMIT 1""",
            (task_type, subject_ref),
        ).fetchone()
        return _actor(row)
    finally:
        connection.close()


def case_reanalysis_hint(database_path: Path, case_id: str) -> str | None:
    if not database_path.is_file():
        return None
    connection = connect(database_path)
    try:
        row = connection.execute(
            """SELECT payload_json FROM tasks WHERE task_type = 'case_analysis'
               AND subject_ref = ? ORDER BY created_at DESC, task_id DESC LIMIT 1""",
            (case_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    try:
        hint = json.loads(row["payload_json"]).get("operator_profile_hint")
    except (TypeError, ValueError):
        return None
    return hint if hint in {"mix", "news", "hybrid", "uncertain"} else None


def request_actor(request: dict[str, Any]) -> dict[str, Any] | None:
    user_id = request.get("created_by_user_id")
    if user_id is None:
        return None
    return {"user_id": user_id, "phone": request.get("created_by_phone")}


def completed_operation_actor(
    database_path: Path, request_id: str, operation: str
) -> dict[str, Any] | None:
    if not database_path.is_file():
        return None
    connection = connect(database_path)
    try:
        try:
            rows = connection.execute(
                """SELECT t.created_by_user_id, u.phone, t.payload_json FROM tasks AS t
               LEFT JOIN users AS u ON u.id = t.created_by_user_id
               WHERE t.subject_ref = ? AND t.status = 'completed'
               ORDER BY t.updated_at DESC, t.task_id DESC""",
                (request_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            return None
    finally:
        connection.close()
    for row in rows:
        try:
            if json.loads(row["payload_json"]).get("operation") == operation:
                return _actor(row)
        except (TypeError, ValueError):
            continue
    return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def persona_approval_actor(
    pipeline_root: Path, persona: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not persona or not persona.get("approved") or not persona.get("path"):
        return None
    root = (pipeline_root / "data" / "personas").resolve()
    path = Path(str(persona["path"])).resolve()
    if not path.is_relative_to(root):
        return None
    receipt = _read_json(path.parent / "approval_receipt.json")
    if (
        not receipt
        or receipt.get("decision") != "approved"
        or receipt.get("persona_id") != persona.get("persona_id")
        or receipt.get("revision") != persona.get("revision")
        or not receipt.get("reviewer")
    ):
        return None
    return {"phone": str(receipt["reviewer"])}


def operator_activity(
    database_path: Path, pipeline_root: Path, user_id: int | None = None
) -> dict[str, Any]:
    connection = connect(database_path)
    try:
        users = [
            dict(row)
            for row in connection.execute("SELECT id, phone FROM users ORDER BY id")
        ]
        rows = connection.execute(
            """SELECT t.task_id, t.task_type, t.subject_ref, t.payload_json, t.status,
                      t.created_at, t.created_by_user_id, u.phone
               FROM tasks AS t LEFT JOIN users AS u ON u.id = t.created_by_user_id
               ORDER BY t.created_at DESC, t.task_id DESC"""
        ).fetchall()
    finally:
        connection.close()
    phones = {str(user["phone"]): user["id"] for user in users}
    events: list[dict[str, Any]] = []

    def add(
        kind: str,
        subject: str,
        timestamp: str | None,
        actor: dict[str, Any] | None,
        status: str,
        source: str,
    ) -> None:
        if user_id is not None and (actor or {}).get("user_id") != user_id:
            return
        events.append(
            {
                "kind": kind,
                "subject": subject,
                "at": timestamp,
                "actor": actor,
                "status": status,
                "source": source,
            }
        )

    task_labels = {
        "case_analysis": "提交案例",
        "customer_analysis": "新建客户",
        "speaker_analysis": "添加出镜人",
        "content_plan": "生成选题",
        "script_generation": "生成文案",
        "mix_export": "导出 Mix",
        "news_plan": "生成 News 选题",
        "news_export": "导出 News",
    }
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except (TypeError, ValueError):
            payload = {}
        operation = (
            payload.get("operation")
            if row["task_type"] in {"content_generation", "excel_export"}
            else row["task_type"]
        )
        label = task_labels.get(str(operation))
        if label:
            subject = (
                payload.get("customer_name")
                or payload.get("speaker_name")
                or row["subject_ref"]
            )
            add(
                label,
                str(subject),
                row["created_at"],
                _actor(row),
                row["status"],
                row["task_id"],
            )

    data = pipeline_root / "data"
    for folder, filename, kind in (
        ("generation_requests", "generation_request_v1.json", "创建 Mix 内容"),
        ("news_deliveries", "news_delivery_request_v1.json", "创建 News 内容"),
    ):
        for path in (data / folder).glob(f"*/{filename}"):
            record = _read_json(path)
            if record:
                add(
                    kind,
                    str(record.get("request_id") or path.parent.name),
                    record.get("created_at"),
                    request_actor(record),
                    "created",
                    str(record.get("request_id") or path.parent.name),
                )

    for pattern, kind, time_field in (
        ("cases/*/approval_receipt.json", "批准案例", "approved_at"),
        (
            "case_analysis_attempts/*/*/human_review_decision_v1.json",
            "案例审核",
            "decided_at",
        ),
        (
            "customer_intakes/*/intake_*/customer_fact_review_v1.json",
            "确认客户信息",
            "reviewed_at",
        ),
        (
            "speaker_intakes/*/*/intake_*/speaker_fact_review_v1.json",
            "确认出镜人信息",
            "reviewed_at",
        ),
        ("personas/*/revision_*/approval_receipt.json", "确认档案", "approved_at"),
        (
            "generation_batches/*/generation_batch_approval_receipt.json",
            "审核 Mix 内容",
            "approved_at",
        ),
        (
            "generation_batches/*/revisions/revision_*/generation_batch_approval_receipt.json",
            "审核 Mix 内容",
            "reviewed_at",
        ),
        (
            "news_deliveries/*/news_delivery_human_review_v1.json",
            "审核 News 内容",
            "reviewed_at",
        ),
    ):
        for path in data.glob(pattern):
            receipt = _read_json(path)
            if not receipt:
                continue
            phone = receipt.get("reviewer")
            actor = (
                {"user_id": phones.get(str(phone)), "phone": phone} if phone else None
            )
            subject = (
                receipt.get("case_id")
                or receipt.get("business_id")
                or receipt.get("speaker_id")
                or receipt.get("request_id")
                or receipt.get("persona_id")
                or path.parent.name
            )
            add(
                kind,
                str(subject),
                receipt.get(time_field)
                or receipt.get("reviewed_at")
                or receipt.get("created_at"),
                actor,
                str(receipt.get("decision") or receipt.get("status") or "completed"),
                path.name,
            )
    events.sort(key=lambda event: str(event["at"] or ""), reverse=True)
    return {
        "accounts": [
            {"user_id": u["id"], "phone_masked": mask_phone(u["phone"])} for u in users
        ],
        "events": [
            {
                **event,
                "actor": (
                    {
                        "user_id": event["actor"].get("user_id"),
                        "phone_masked": mask_phone(event["actor"].get("phone")),
                    }
                    if event["actor"]
                    else None
                ),
            }
            for event in events[:200]
        ],
    }
