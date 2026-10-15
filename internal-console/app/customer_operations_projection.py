"""Bounded public list over existing Canonical owners; no writes or model calls."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import urlencode

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .customer_gateway import _customer_projection, _known_fact_value, BUSINESS_ID_RE
from .database import connect
from .persona_authority import resolve_persona_authority, validate_speaker_business_binding
from .speaker_gateway import _speaker_projection

# The Console adapter already exposes this scripts root through persona_authority.
from content_creation_entry_v1 import build_content_creation_entry, ContentCreationEntryError
from generation_request_effective_lifecycle_v1 import classify_request, EffectiveLifecycleError


def request_navigation_context(settings, request_id, mode, expected_business_id=None):
    """Resolve navigation identity even when delivery is blocked; grants no production authority."""
    from .content_delivery_gateway import _load_request
    from .news_delivery_gateway import _request_root, NEWS_REQUEST_SCHEMA
    from .customer_gateway import get_customer_detail
    if mode is None:
        news_path = _request_root(settings, request_id) / "news_delivery_request_v1.json"
        generation_path = settings.pipeline_root / "data/generation_requests" / request_id / "generation_request_v1.json"
        if news_path.is_file() and generation_path.is_file():
            raise CanonicalOperationError("REQUEST_CONTEXT_AMBIGUOUS", "此请求编号存在多个创作上下文。", "请从客户作品记录的准确入口继续。")
        if news_path.is_file():
            mode = "repurpose"
        else:
            _, original = _load_request(settings, request_id)
            mode = "novel" if (original.get("target_profile") or original.get("profile")) == "news" else "mix"
    if mode == "repurpose":
        path = _request_root(settings, request_id) / "news_delivery_request_v1.json"
        if not path.is_file():
            raise CanonicalOperationError("NEWS_REQUEST_NOT_FOUND", "没有找到原创作请求。", "请从任务或作品记录重新进入。")
        request = _read(path)
        if request.get("schema_version") != NEWS_REQUEST_SCHEMA or request.get("request_id") != request_id:
            raise CanonicalOperationError("REQUEST_LINEAGE_INVALID", "创作请求身份不一致。", "请恢复原请求后重试。")
        owner = str(request.get("business_id") or "")
        status = (request.get("lifecycle") or {}).get("status")
    else:
        path, request = _load_request(settings, request_id)
        profile = request.get("target_profile") or request.get("profile")
        if profile != ("news" if mode == "novel" else "mix"):
            raise CanonicalOperationError("REQUEST_PROFILE_MISMATCH", "创作类型与原请求不一致。", "请从原作品记录重新进入。")
        owner = str(request.get("persona_id") or "")
        status = classify_request(pipeline_root=settings.pipeline_root, request_path=path)["effective_status"]
    if expected_business_id is not None and expected_business_id != owner:
        raise CanonicalOperationError("REQUEST_BUSINESS_MISMATCH", "创作记录与指定客户不匹配。", "请从原任务或客户作品记录重新进入。")
    customer = get_customer_detail(settings, owner)
    return {"business_id": owner, "display_name": customer["display_name"], "request_id": request_id,
            "mode": mode, "status": status}


def _read(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    return value


def _timestamp(value):
    """Normalize persisted times; invalid/missing timestamps never mean 'now'."""
    try:
        stamp = datetime.fromisoformat(str(value))
        return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return ""


def creation_record_index(settings: Settings) -> dict[str, list[dict[str, Any]]]:
    """Count requests, not outputs/exports. Resolve immutable/effective lifecycle."""
    from .news_delivery_gateway import get_news_delivery_state
    from .content_delivery_gateway import get_content_delivery_state
    from .novel_news_gateway import novel_news_state
    records = defaultdict(list)
    locations = [("generation", "generation_requests", "generation_request_v1.json"),
                 ("repurpose", "news_deliveries", "news_delivery_request_v1.json")]
    for namespace, directory, filename in locations:
        for path in sorted((settings.pipeline_root / "data" / directory).glob(f"*/{filename}")):
            request = _read(path)
            business_id = str(request.get("persona_id") or request.get("business_id") or "")
            if not BUSINESS_ID_RE.fullmatch(business_id):
                raise ValueError("Request business identity is invalid")
            request_id = str(request.get("request_id") or "")
            if request_id != path.parent.name:
                raise ValueError("Request identity does not match its directory")
            profile = str(request.get("target_profile") or request.get("profile") or ("news" if namespace == "repurpose" else ""))
            if profile not in {"mix", "news"}:
                raise ValueError("Unsupported request profile")
            query = {"business_id": business_id, "request_id": request_id, "profile": profile}
            if namespace == "repurpose":
                query["news_mode"] = "cross_profile_repurpose"
            elif profile == "news":
                query["news_mode"] = "novel_content"
            record = {"record_id": f"{namespace}:{request_id}", "request_id": request_id,
                      "business_id": business_id, "profile": profile,
                      "updated_at": _timestamp(request.get("created_at")) or None,
                      "url": "/create?" + urlencode(query), "action_required": False,
                      "status": "unknown", "label": "记录需要核对"}
            try:
                if namespace == "generation":
                    effective = classify_request(pipeline_root=settings.pipeline_root, request_path=path)
                    record["status"] = effective["effective_status"]
                    record["terminal"] = effective["effective_terminal"]
                    if effective["effective_terminal"]:
                        record["label"] = "已导出" if effective["effective_status"] == "exported" else "已结束"
                    elif profile == "mix":
                        state = get_content_delivery_state(settings, request_id, include_actors=False)
                        stage = state.get("next_action")
                        record.update(stage=stage, action_required=True,
                                      label={"HUMAN_REVIEW": "待审核", "EXPORT_EXCEL": "待导出", "SOURCE_COVERAGE_BLOCKED": "查看创作条件"}.get(stage, "继续创作"))
                    else:
                        state = novel_news_state(settings, request_id)
                        record.update(stage=state.get("stage"), action_required=True, label="继续新闻体创作")
                else:
                    state = get_news_delivery_state(settings, request_id, include_actors=False)
                    done = state.get("stop_point_reached") is True
                    record.update(terminal=done, status="exported" if done else "resumable",
                                  stage=state.get("next_action"), action_required=not done,
                                  label="已导出" if done else "继续新闻体创作")
            except (CanonicalOperationError, EffectiveLifecycleError, ValueError, RuntimeError):
                record.update(status="blocked", action_required=True, label="查看记录阻断原因", terminal=False)
            records[business_id].append(record)
    for rows in records.values():
        rows.sort(key=lambda row: (str(row.get("updated_at") or ""), row["record_id"]), reverse=True)
    return dict(records)


def _identity_index(settings):
    business_ids = set()
    speakers = defaultdict(set)
    for directory in (settings.pipeline_root / "data/personas").glob("*"):
        if not directory.is_dir():
            continue
        for path in directory.glob("revision_*/persona_v1.json"):
            value = _read(path)
            if value.get("persona_scope", "business") == "business":
                business_ids.add(directory.name)
            elif value.get("persona_scope") == "speaker":
                owner = str((value.get("business_persona_ref") or {}).get("persona_id") or "")
                speakers[owner].add(directory.name)
    for directory in (settings.pipeline_root / "data/customer_intakes").glob("*"):
        if directory.is_dir() and BUSINESS_ID_RE.fullmatch(directory.name):
            business_ids.add(directory.name)
    for owner in (settings.pipeline_root / "data/speaker_intakes").glob("*"):
        for directory in owner.glob("*"):
            if directory.is_dir():
                speakers[owner.name].add(directory.name)
    return business_ids, speakers


def _task_index(settings, business_ids, speakers, records):
    """One SQL read for the list, no per-card task/persona HTTP requests."""
    owners = {speaker: business for business, ids in speakers.items() for speaker in ids}
    owners.update({row["request_id"]: business for business, rows in records.items() for row in rows})
    owners.update({business: business for business in business_ids})
    result = defaultdict(list)
    with connect(settings.database_path) as db:
        rows = db.execute("SELECT task_id, task_type, subject_ref, status, payload_json, updated_at, operation_identity FROM tasks WHERE task_type IN ('customer_analysis', 'speaker_analysis', 'content_generation', 'excel_export') ORDER BY updated_at DESC, task_id DESC").fetchall()
    seen = set()
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        owner = owners.get(row["subject_ref"]) or payload.get("business_id")
        if owner not in business_ids:
            continue
        key = (owner, row["task_type"], row["subject_ref"], payload.get("operation") or payload.get("intake_id"))
        if key in seen:
            continue
        seen.add(key)
        result[owner].append({"task_id": row["task_id"], "subject_ref": row["subject_ref"],
                              "task_type": row["task_type"], "status": row["status"], "updated_at": row["updated_at"],
                              "intake_id": payload.get("intake_id"), "operation": payload.get("operation")})
    return result


def _creation_conditions(settings, business_id, approved, *, novel_available=False):
    from news_delivery_v1 import preview_news_delivery
    paths = []
    for speaker in approved:
        for profile in (("mix", "news") if novel_available else ("mix",)):
            try:
                preview = build_content_creation_entry(pipeline_root=settings.pipeline_root,
                    business_id=business_id, speaker_id=speaker["speaker_id"], profile=profile, requested_quantity=1)
                paths.append({"speaker_id": speaker["speaker_id"], "profile": profile, "mode": "novel" if profile == "news" else "mix",
                              "supported": preview["recommendation"]["can_continue"] is True,
                              "status": preview["recommendation"]["status"]})
            except (ContentCreationEntryError, RuntimeError, ValueError) as exc:
                paths.append({"speaker_id": speaker["speaker_id"], "profile": profile,
                              "supported": False, "status": getattr(exc, "code", "unavailable")})
        try:
            preview = preview_news_delivery(pipeline_root=settings.pipeline_root, business_id=business_id, speaker_id=speaker["speaker_id"])
            paths.append({"speaker_id": speaker["speaker_id"], "profile": "news", "mode": "repurpose",
                          "supported": preview["available"] is True, "status": "ready" if preview["available"] else "no_eligible_source"})
        except RuntimeError as exc:
            paths.append({"speaker_id": speaker["speaker_id"], "profile": "news", "mode": "repurpose", "supported": False, "status": getattr(exc, "code", "unavailable")})
    # Novel News / repurpose availability is never inferred from Business approval.
    # This list conservatively advertises paths proven by the formal entry preview.
    return {"ready": any(p["supported"] for p in paths), "paths": paths}


def _operation_row(settings, business_id, speaker_ids, tasks, records, records_known=True, *, novel_available=False):
    customer = _customer_projection(settings, business_id, approved_speaker_count=0)
    tasks = [task for task in tasks if task["task_type"] != "customer_analysis" or not task.get("intake_id") or task["intake_id"] == customer.get("latest_intake_id")]
    authority = resolve_persona_authority(settings, business_id, "business")
    current = authority.current
    approved, pending_speakers = [], []
    for speaker_id in sorted(speaker_ids):
        projection = _speaker_projection(settings, business_id, speaker_id)
        speaker = resolve_persona_authority(settings, speaker_id, "speaker").current
        valid = False
        if current and speaker:
            try:
                validate_speaker_business_binding(speaker, current)
                valid = int((speaker["artifact"].get("business_persona_ref") or {}).get("revision") or 0) == int(current["revision"])
            except CanonicalOperationError:
                valid = False
        if valid:
            approved.append({"speaker_id": speaker_id,
                "display_name": _known_fact_value(speaker["artifact"], "public_display_name") or speaker_id,
                "public_role": _known_fact_value(speaker["artifact"], "public_role"),
                "speaker_type": speaker["artifact"].get("speaker_type")})
        if projection["status"] != "approved":
            pending_speakers.append({"speaker_id": speaker_id, "status": projection["status"]})
    industry_record = customer.get("industry_classification") or {}
    industry = (industry_record.get("value") if industry_record.get("decision") in {"approve", "edit"} else None)
    if not industry_record and current:
        industry = _known_fact_value(current["artifact"], "industry")
    region = _known_fact_value(current["artifact"], "location_public_area") if current else None
    conditions = _creation_conditions(settings, business_id, approved, novel_available=novel_available) if current else {"ready": False, "paths": []}
    constraints = (current or {}).get("production_constraints") or {}
    # Pending first-time material can contain a core conflict before any Persona
    # exists. Read the same canonical owner; do not invent a readiness state.
    from customer_constraints_v1 import collect, policy, unresolved_legacy_constraints
    controls = collect(settings.pipeline_root, business_id)
    core_pending = any(item["constraint_type"] == "identity_conflict" or item["scope"] == "business"
                       for item in policy(controls)["blockers"])
    blocked = bool(constraints.get("blockers") or core_pending
                   or unresolved_legacy_constraints(settings.pipeline_root, business_id, controls))
    detail_url = f"/customers/{business_id}"
    work_url = detail_url + "/content"
    status = customer["status"]
    actionable = set()
    if status in {"draft", "fact_review_required", "persona_review_required", "needs_more_info"}:
        actionable.add("business")
    actionable.update("speaker:" + row["speaker_id"] for row in pending_speakers
                      if row["status"] not in {"analysis_pending", "pending_customer_profile"})
    active_records = [row for row in records if row.get("action_required")]
    failed = [task for task in tasks if task["status"] == "failed"]
    running = [task for task in tasks if task["status"] in {"queued", "running"}]
    # A running execution is not an operator todo. Only suppress a record when
    # the task matches its current canonical next step, never a pending review.
    expected_operation = {"CREATE_CONTENT_PLAN": "content_plan", "GENERATE_SCRIPTS": "script_generation",
                          "EXPORT_EXCEL": "mix_export", "RESOLVE_NEWS_PLAN": "news_plan",
                          "EXPORT_NEWS_EXCEL": "news_export", "generation": "novel_news_generate",
                          "export": "novel_news_export"}
    active_records = [row for row in active_records if not any(
        task.get("subject_ref") == row["request_id"] and task.get("operation") == expected_operation.get(row.get("stage"))
        and task.get("operation") is not None for task in running)]
    actionable.update(row["record_id"] for row in active_records)
    request_ids = {row["request_id"] for row in records}
    # A task is an execution projection. Completed canonical stages supersede historical failures.
    failed = [task for task in failed if task["subject_ref"] not in request_ids or any(
        row["request_id"] == task["subject_ref"] and row.get("action_required")
        and (not row.get("stage") or expected_operation.get(row["stage"]) == task.get("operation")) for row in records)]
    for task in failed:
        subject = task["subject_ref"]
        key = next((row["record_id"] for row in records if row["request_id"] == subject), None)
        actionable.add(key or ("business" if subject == business_id else "speaker:" + subject))
    title, label, url, kind = "待建档", "继续完善资料", detail_url + "/edit", "setup"
    note = "资料完善后再核对并批准档案。"
    if blocked:
        title, label, url, kind = "待核实", "查看阻断原因", detail_url, "blocked"
        note = "核心限制尚未解除，相关创作仍受阻。"
        actionable.add("business")
    elif failed:
        task = failed[0]
        resume = next((row["url"] for row in records if row["request_id"] == task["subject_ref"]), None)
        if task["task_type"] == "customer_analysis":
            resume = detail_url
        elif task["task_type"] == "speaker_analysis":
            resume = detail_url + "/speakers/" + task["subject_ref"]
        title, label, url, kind = "异常", "处理异常", resume or "/tasks/" + task["task_id"], "error"
        note = "失败任务需处理；其他独立创作条件会重新核对。"
    elif status == "fact_review_required":
        title, label, url, kind = "待核对", "去核对资料", detail_url, "review"
        note = "AI 整理的信息仍需要人工核对。"
    elif status == "persona_review_required":
        title, label, url, kind = "待批准", "查看待批准事项", detail_url, "approval"
        note = "事实核对与正式档案批准分别完成。"
    elif status == "needs_more_info":
        title, label, url, kind = "待处理", "继续处理资料", detail_url, "setup"
        note = "查看资料缺口、识别遗漏或待核实事项。"
    elif active_records:
        title, label, url, kind = "待处理", active_records[0]["label"], active_records[0]["url"], "work"
        note = "继续已有请求，不创建新的创作。"
    elif running:
        title, label, url, kind = "处理中", "查看处理进度", "/tasks/" + running[0]["task_id"], "running"
        note = "任务在后台运行。"
    elif conditions["ready"]:
        supported = next(path for path in conditions["paths"] if path["supported"])
        query = {"business_id": business_id, "speaker_id": supported["speaker_id"], "profile": supported["profile"]}
        if supported["profile"] == "news":
            query["news_mode"] = "novel_content" if supported.get("mode") == "novel" else "cross_profile_repurpose"
        title, label, url, kind = "可创作", "开始创作", "/create?" + urlencode(query), "ready"
        note = "至少一条正式路径可用；进入后再次校验。"
    elif pending_speakers and current:
        title, label, url, kind = "待处理", "查看出镜人资料", detail_url, "speaker"
        note = "出镜人资料仍需独立审核或复核。"
    elif current:
        title, label, url, kind = "查看创作条件", "查看创作条件", "/create?" + urlencode({"business_id": business_id}), "conditions"
        note = "档案已批准；内容空间与结构可行性还需核对。"
    approved.sort(key=lambda row: (str(row["display_name"]), row["speaker_id"]))
    updated = max([_timestamp(customer.get("submitted_at")), _timestamp(industry_record.get("reviewed_at")), _timestamp((current or {}).get("artifact", {}).get("lifecycle", {}).get("approved_at"))] + [_timestamp(t.get("updated_at")) for t in tasks] + [_timestamp(r.get("updated_at")) for r in records])
    return {"business_id": business_id, "display_name": customer["display_name"],
            "industry": industry, "region": region if isinstance(region, str) else None,
            "approved_speaker_count": len(approved), "speaker": approved[0] if approved else None,
            "creation_record_count": len(records) if records_known else None,
            "pending_count": len(actionable) if records_known else None,
            "creation_ready": conditions["ready"] and not blocked, "creation_conditions": conditions,
            "operation": {"status": title, "kind": kind, "note": note, "primary": {"label": label, "url": url}, "secondary": {"label": "查看作品记录", "url": work_url}},
            "updated_at": updated or None, "detail_url": detail_url}


def list_customer_operations(settings: Settings, *, search="", filter_by="all", sort_by="action", page=1, page_size=20, actor_phone=""):
    from .novel_news_rollout import novel_news_available
    novel_available = novel_news_available(settings, actor_phone)
    try:
        business_ids, speakers = _identity_index(settings)
    except (ValueError, OSError, RuntimeError) as exc:
        raise CanonicalOperationError("CUSTOMER_LIST_INDEX_UNAVAILABLE", "客户记录暂时无法可靠读取。", "请稍后重试，或从已有任务进入原工作。") from exc
    records_known = True
    try:
        records = creation_record_index(settings)
    except (ValueError, OSError, RuntimeError):
        records, records_known = {}, False
    tasks = _task_index(settings, business_ids, speakers, records)
    rows = []
    for business_id in sorted(business_ids):
        try:
            rows.append(_operation_row(settings, business_id, speakers[business_id], tasks[business_id], records.get(business_id, []), records_known, novel_available=novel_available))
        except (CanonicalOperationError, ValueError, OSError, RuntimeError):
            rows.append({"business_id": business_id, "display_name": business_id, "industry": None, "region": None,
                "approved_speaker_count": None, "creation_record_count": None, "pending_count": None, "creation_ready": False,
                "detail_url": f"/customers/{business_id}", "updated_at": None,
                "operation": {"status": "需核对", "kind": "error", "note": "记录暂时无法可靠读取，请查看详情。",
                "primary": {"label": "查看阻断原因", "url": f"/customers/{business_id}"},
                "secondary": {"label": "查看作品记录", "url": f"/customers/{business_id}/content"}}})
    term = search.strip().casefold()
    rows = [row for row in rows if term in " ".join(str(row.get(key) or "") for key in ("display_name", "industry", "region")).casefold()]
    counts = {"all": len(rows), "pending": sum((row.get("pending_count") or 0) > 0 or row["operation"]["kind"] == "error" for row in rows), "ready": sum(row["creation_ready"] for row in rows)}
    if filter_by == "pending":
        rows = [row for row in rows if (row.get("pending_count") or 0) > 0 or row["operation"]["kind"] == "error"]
    elif filter_by == "ready":
        rows = [row for row in rows if row["creation_ready"]]
    # Stable ties: ID, then trustworthy recent time, then actionable matters.
    rows.sort(key=lambda row: row["business_id"])
    rows.sort(key=lambda row: row.get("updated_at") or "", reverse=True)
    if sort_by == "action":
        rows.sort(key=lambda row: not ((row.get("pending_count") or 0) > 0 or row["operation"]["kind"] == "error"))
    total = len(rows)
    return {"schema_version": "customer-operations-list-v1.0", "customers": rows[(page-1)*page_size:page*page_size],
            "total": total, "page": page, "page_size": page_size, "filter_counts": counts,
            "counts_scope": "all_search_matches", "projection_only": True}
