"""Console adapter for canonical Novel News operations (separate from Repurpose)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .path_safety import resolve_within, validate_identifier
from pathlib import Path
import hashlib
from .operator_projection import original_task_actor
from .subprocess_env import pipeline_subprocess_env


def _run(
    settings: Settings, script: str, args: list[str], *,
    payload: dict[str, Any] | None = None, remote: bool = False,
    local_timeout_seconds: int = 60,
) -> dict[str, Any]:
    executable = settings.pipeline_python_executable or settings.python_executable
    command = [executable, str(settings.pipeline_root / "scripts" / script), *args]
    try:
        result = subprocess.run(
            command, cwd=settings.repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180 if remote else local_timeout_seconds,
            input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
            env=pipeline_subprocess_env(needs_deepseek=remote), check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanonicalOperationError(
            "NEWS_NOVEL_RUNTIME_UNAVAILABLE", "新闻体新内容暂时无法执行。",
            "请稍后重试；已有 Request 与审核结果会保留。",
        ) from exc
    parsed = None
    for line in reversed(result.stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            parsed = value
            break
    if result.returncode != 0 or not parsed or parsed.get("ok") is not True:
        code = str((parsed or {}).get('code') or 'NEWS_NOVEL_OPERATION_FAILED')
        reason = {
            'PROFILE_COMPATIBILITY_BLOCKED': ('新闻体的兼容性或发布资格已变化。', '请先核对当前结构、兼容性和发布版本，原操作会保留。'),
            'NEWS_NOVEL_SOURCE_COVERAGE_UNSUPPORTED': ('现有结构与案例不足以支持这次新闻体。', '请先完成适用的结构和兼容性审核，再检查创作条件。'),
            'NEWS_NOVEL_PRICE_AUTHORITY_INVALID': ('本次价格或适用条件尚未核实。', '请先核对客户的价格、服务及适用条件。'),
            'NEWS_NOVEL_PERSONA_LINEAGE_INVALID': ('客户或出镜人资料已更新。', '请先核对当前资料版本，不能自动沿用原确认。'),
            'NEWS_GENERATION_OUTCOME_UNKNOWN': ('模型执行结果无法确认。', '系统不会自动重复生成；明确重新尝试可能产生额外费用。'),
            'NEWS_GENERATION_SUPERSEDED': ('原生成执行已被新的明确尝试替代。', '请刷新查看新尝试，旧记录仍会保留。'),
            'NEWS_GENERATION_SOURCE_CHANGED': ('本次创作来源已经变化。', '请重新核对客户、事实、限制和创作参考。'),
        }.get(code)
        raise CanonicalOperationError(
            code,
            reason[0] if reason else "新闻体新内容操作没有完成。",
            reason[1] if reason else "导出结果需要重新核对。" if code.startswith("NEWS_EXPORT_")
            else "请检查已批准资料与创作来源；原操作记录会保留。",
        )
    return parsed


def preview_novel_news(settings: Settings, business_id: str, speaker_id: str) -> dict[str, Any]:
    result = _run(settings, "novel_news_opportunity_v1.py", [
        "--pipeline-root", str(settings.pipeline_root),
        "--business-id", validate_identifier(business_id, field="business_id"),
        "--speaker-id", validate_identifier(speaker_id, field="speaker_id"),
    ])
    projection = result["projection"]
    authority = projection.get("authority") or {}
    if any(authority.get(key) is not False for key in (
        "generation_request_created", "source_plan_written", "content_ledger_written", "remote_model_called"
    )):
        raise CanonicalOperationError("NEWS_NOVEL_PREVIEW_MUTATION", "新闻体预览越过只读边界。", "停止当前操作。")
    return projection


def novel_news_state(settings: Settings, request_id: str) -> dict[str, Any]:
    state = _run(settings, "novel_news_v1.py", [
        "status", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
    ])["result"]
    from .database import connect
    with connect(settings.database_path) as db:
        row = db.execute("SELECT status,lease_expires_at,attempt_count,payload_json FROM tasks WHERE subject_ref=? "
            "AND json_extract(payload_json,'$.operation')='novel_news_generate' ORDER BY rowid DESC LIMIT 1",
            (request_id,)).fetchone()
    from novel_news_generation_recovery_v1 import project_task_execution
    state['generation'] = project_task_execution(settings.pipeline_root, request_id, state.get('generation') or {}, row)
    if state['generation'].get('recovery_state') == 'source_or_authorization_conflict' and state.get('stage') != 'completed':
        state['stage'] = 'blocked'
    return state


def generate_novel_news(settings: Settings, request_id: str, *, operation_id=None, intent_sha256=None,
                        authorization_context=None, task_id=None) -> dict[str, Any]:
    actor = original_task_actor(settings.database_path, "content_generation", request_id) or {}
    return _run(settings, "novel_news_v1.py", [
        "generate", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
        "--actor", str(actor.get("phone") or "historical-operator"),
    ], remote=True, payload={'operation_id': operation_id, 'intent_sha256': intent_sha256,
                            'authorization_context': authorization_context, 'task_id': task_id})["result"]


def review_novel_news(
    settings: Settings, request_id: str, *, decisions: list[dict[str, Any]], reviewer: str
) -> dict[str, Any]:
    return _run(settings, "novel_news_v1.py", [
        "review", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
        "--actor", reviewer,
    ], payload={"decisions": decisions})["result"]


def export_novel_news(settings: Settings, request_id: str, *, authorization_context=None) -> dict[str, Any]:
    actor = original_task_actor(settings.database_path, "excel_export", request_id) or {}
    return _run(settings, "novel_news_v1.py", [
        "export", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
        "--actor", str(actor.get("phone") or "historical-operator"),
    ], payload={"export_context": authorization_context})["result"]


def novel_news_excel(settings: Settings, request_id: str) -> Path:
    state = novel_news_state(settings, request_id)
    if state.get("stage") != "completed":
        raise CanonicalOperationError("NEWS_NOVEL_EXPORT_NOT_READY", "新闻体尚未完成导出。", "请先完成审核与导出。")
    receipt = state.get("export") or {}
    try:
        path = resolve_within(settings.pipeline_root / "output", str(receipt.get("output_path") or ""))
    except ValueError as exc:
        raise CanonicalOperationError("NEWS_NOVEL_EXPORT_PATH_INVALID", "导出路径不安全。", "停止下载并检查导出谱系。") from exc
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != receipt.get("output_sha256"):
        raise CanonicalOperationError("NEWS_NOVEL_EXPORT_LINEAGE_INVALID", "导出文件与回执不一致。", "停止下载并检查导出谱系。")
    return path
