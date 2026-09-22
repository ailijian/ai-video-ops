"""Small feature rollout boundary for Novel News; not an authorization role system."""

from __future__ import annotations

import json
import re

from .canonical_gateway import CanonicalOperationError
from .config import Settings
from .database import connect


def novel_news_available(settings: Settings, phone: str | None) -> bool:
    if settings.novel_news_rollout == "on":
        return True
    return bool(
        settings.novel_news_rollout == "validation"
        and settings.novel_news_validation_phones
        and phone
        and phone in settings.novel_news_validation_phones
    )


def require_novel_news(settings: Settings, phone: str | None) -> None:
    if not novel_news_available(settings, phone):
        raise CanonicalOperationError(
            "NOVEL_NEWS_NOT_AVAILABLE",
            "新闻体创作新内容当前未开放。",
            "仍可使用“重新表达已有内容”；已有创作记录会保留。",
        )


def require_novel_news_task(settings: Settings, user_id: int | None) -> None:
    if settings.novel_news_rollout == "on":
        return
    if settings.novel_news_rollout != "validation" or not user_id:
        require_novel_news(settings, None)
    connection = connect(settings.database_path)
    try:
        row = connection.execute("SELECT phone FROM users WHERE id = ? AND status = 'active'", (user_id,)).fetchone()
    finally:
        connection.close()
    require_novel_news(settings, str(row["phone"]) if row else None)


def is_novel_news_request(settings: Settings, request_id: str) -> bool:
    if not re.fullmatch(r"gen_[A-Za-z0-9]+", request_id):
        return False
    path = settings.pipeline_root / "data/generation_requests" / request_id / "generation_request_v1.json"
    if not path.is_file():
        return False
    try:
        request = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(
        isinstance(request, dict)
        and request.get("request_id") == request_id
        and request.get("target_profile") == "news"
        and request.get("reuse_intent") == "novel_content"
    )


def require_if_novel_request(settings: Settings, request_id: str, phone: str | None) -> None:
    if is_novel_news_request(settings, request_id):
        require_novel_news(settings, phone)
