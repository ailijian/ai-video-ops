"""Durable UI groups; admission always goes through the existing single-case gateway."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .database import connect, transaction
from .douyin_source_input import ALLOWED_HOSTS, URL_RE, SourceInputError
from .task_service import get_task


def prepare_items(raw: str, resolve) -> list[dict]:
    candidates = [m.group(0).rstrip(",.，。；;：:！!？?、\"'」》】") for m in URL_RE.finditer(raw)]
    if not candidates:
        raise SourceInputError("CASE_URL_INVALID", "请粘贴抖音分享内容或视频链接。")
    if len(candidates) > 100:
        raise SourceInputError("CASE_BATCH_LIMIT", "输入链接过多，请分批粘贴；每批最多 10 条有效视频。")
    items, identities, extracted = [], {}, {}
    for url in candidates:
        item = {"source_url": url, "state": "pending"}
        if url in extracted:
            prior = items[extracted[url]]
            if prior.get("case_id"):
                item.update(case_id=prior["case_id"], canonical_url=prior["canonical_url"],
                            state="input_duplicate", duplicate_of=extracted[url], message="当前输入中重复的视频")
            else:
                item.update(state="error", error_code=prior.get("error_code"), message=prior.get("message"))
        else:
            try:
                if urlsplit(url).hostname not in ALLOWED_HOSTS:
                    raise SourceInputError("CASE_PLATFORM_UNSUPPORTED", "当前仅支持已验证的抖音视频获取。")
                source = resolve(url)
                item.update(case_id=source.video_id, canonical_url=source.canonical_url)
                if source.video_id in identities:
                    item.update(state="input_duplicate", duplicate_of=identities[source.video_id], message="当前输入中重复的视频")
                else:
                    identities[source.video_id] = len(items)
                    if len(identities) > 10:
                        raise SourceInputError("CASE_BATCH_LIMIT", "每批最多 10 条有效视频，请分批解析。")
            except SourceInputError as exc:
                if exc.code == "CASE_BATCH_LIMIT":
                    raise
                item.update(state="error", error_code=exc.code, message=exc.message)
            except ValueError:
                item.update(state="error", error_code="CASE_URL_INVALID", message="链接格式无效，请检查后重新粘贴。")
            extracted[url] = len(items)
        items.append(item)
    return items


def create_group(database_path, *, client_request_id: str, user_id: int, raw: str, resolve, source_upload_id=None) -> str:
    request_digest = hashlib.sha256(json.dumps([raw, source_upload_id], ensure_ascii=False).encode()).hexdigest()
    with transaction(database_path, immediate=True) as conn:
        existing = conn.execute("SELECT * FROM case_intake_groups WHERE client_request_id=?", (client_request_id,)).fetchone()
        if existing:
            if existing["request_digest"] != request_digest or existing["created_by_user_id"] != user_id:
                raise SourceInputError("CASE_GROUP_REQUEST_CONFLICT", "此提交编号已用于其他输入，请刷新后重新提交。")
            return existing["group_id"]
    # Resolve outside the write transaction; this can perform bounded short-link HEAD requests.
    items = prepare_items(raw, resolve)
    if source_upload_id and (len(items) != 1 or items[0]["state"] != "pending"):
        raise SourceInputError("CASE_UPLOAD_SINGLE_ONLY", "本地视频只能对应一个有效来源链接。")
    group_id = "intake-" + uuid.uuid4().hex
    with transaction(database_path, immediate=True) as conn:
        # Concurrent double-click/retry must recover the same group.
        existing = conn.execute("SELECT * FROM case_intake_groups WHERE client_request_id=?", (client_request_id,)).fetchone()
        if existing:
            if existing["request_digest"] != request_digest or existing["created_by_user_id"] != user_id:
                raise SourceInputError("CASE_GROUP_REQUEST_CONFLICT", "提交编号与输入不匹配。")
            return existing["group_id"]
        conn.execute("INSERT INTO case_intake_groups VALUES (?, ?, ?, ?, ?)",
                     (group_id, client_request_id, request_digest, user_id, datetime.now(timezone.utc).isoformat()))
        for position, item in enumerate(items):
            conn.execute(
                """INSERT INTO case_intake_items(group_id,position,source_url,canonical_url,case_id,state,duplicate_of,error_code,message,source_upload_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (group_id, position, item["source_url"], item.get("canonical_url"), item.get("case_id"), item["state"],
                 item.get("duplicate_of"), item.get("error_code"), item.get("message"), source_upload_id))
    return group_id


def dispatch_groups(database_path, submit) -> None:
    conn = connect(database_path)
    try:
        pending = conn.execute(
            """SELECT i.*,g.created_by_user_id FROM case_intake_items i JOIN case_intake_groups g USING(group_id)
               WHERE i.state='pending' ORDER BY g.created_at,i.position""").fetchall()
    finally:
        conn.close()
    for row in pending:
        item = dict(row)
        try:
            response = submit(item)
            task = response.get("task") or response.get("existing_task")
            values = ("linked", task.get("task_id") if task else None, None, response.get("message"), item["group_id"], item["position"])
        except Exception as exc:
            # HTTP and Task errors retain the canonical queue guard's decision.
            detail = getattr(exc, "detail", None)
            code = detail.get("code") if isinstance(detail, dict) else getattr(exc, "code", None)
            if code in {"TASK_QUEUE_FULL", "GPU_PENDING_LIMIT_REACHED", "OPERATION_ALREADY_ACTIVE"}:
                continue
            # Unexpected faults remain retryable on the next maintenance pass.
            if code is None:
                logging.getLogger(__name__).warning("Intake admission deferred (%s)", type(exc).__name__)
                continue
            message = detail.get("message") if isinstance(detail, dict) else str(exc)
            values = ("error", None, code, message, item["group_id"], item["position"])
        with transaction(database_path, immediate=True) as conn:
            conn.execute("UPDATE case_intake_items SET state=?,task_id=?,error_code=?,message=? WHERE group_id=? AND position=? AND state='pending'", values)


def get_group(database_path, group_id: str) -> dict | None:
    conn = connect(database_path)
    try:
        group = conn.execute("SELECT group_id,created_by_user_id,created_at FROM case_intake_groups WHERE group_id=?", (group_id,)).fetchone()
        if group is None:
            return None
        items = [dict(r) for r in conn.execute("SELECT * FROM case_intake_items WHERE group_id=? ORDER BY position", (group_id,))]
    finally:
        conn.close()
    for item in items:
        item["task"] = get_task(database_path, item["task_id"]) if item["task_id"] else None
        item.pop("source_upload_id", None)
    return {**dict(group), "items": items}


def list_groups(database_path) -> list[dict]:
    conn = connect(database_path)
    try:
        return [dict(r) for r in conn.execute("SELECT group_id,created_at FROM case_intake_groups ORDER BY created_at DESC LIMIT 50")]
    finally:
        conn.close()
