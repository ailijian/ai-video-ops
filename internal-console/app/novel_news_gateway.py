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
) -> dict[str, Any]:
    executable = settings.pipeline_python_executable or settings.python_executable
    command = [executable, str(settings.pipeline_root / "scripts" / script), *args]
    try:
        result = subprocess.run(
            command, cwd=settings.repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180 if remote else 60,
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
        raise CanonicalOperationError(
            str((parsed or {}).get("code") or "NEWS_NOVEL_OPERATION_FAILED"),
            "新闻体新内容操作没有完成。",
            str((parsed or {}).get("message") or "请检查已批准资料与创作来源。"),
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
    return _run(settings, "novel_news_v1.py", [
        "status", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
    ])["result"]


def generate_novel_news(settings: Settings, request_id: str) -> dict[str, Any]:
    actor = original_task_actor(settings.database_path, "content_generation", request_id) or {}
    return _run(settings, "novel_news_v1.py", [
        "generate", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
        "--actor", str(actor.get("phone") or "historical-operator"),
    ], remote=True)["result"]


def review_novel_news(
    settings: Settings, request_id: str, *, decisions: list[dict[str, Any]], reviewer: str
) -> dict[str, Any]:
    return _run(settings, "novel_news_v1.py", [
        "review", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
        "--actor", reviewer,
    ], payload={"decisions": decisions})["result"]


def export_novel_news(settings: Settings, request_id: str) -> dict[str, Any]:
    actor = original_task_actor(settings.database_path, "excel_export", request_id) or {}
    return _run(settings, "novel_news_v1.py", [
        "export", "--pipeline-root", str(settings.pipeline_root),
        "--request-id", validate_identifier(request_id, field="request_id"),
        "--actor", str(actor.get("phone") or "historical-operator"),
    ])["result"]


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
