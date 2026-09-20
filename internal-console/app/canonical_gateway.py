from __future__ import annotations

import json
import hashlib
import copy
import logging
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .config import Settings
from .subprocess_env import pipeline_subprocess_env

logger = logging.getLogger(__name__)

BUSINESS_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,127}$")
DOUYIN_VIDEO_ID_RE = re.compile(r"(?:/video/|video_id=)(\d{10,24})")

PROFILE_LABELS = {"mix": "口播混剪", "news": "信息卡点"}
INDUSTRY_LABELS = {
    "local_service": "本地生活",
    "local-service": "本地生活",
    "bakery-dessert": "烘焙甜品",
    "restaurant": "餐饮",
    "retail": "零售",
    "unknown": "待分类",
}


class CanonicalOperationError(RuntimeError):
    def __init__(self, code: str, message: str, next_action: str):
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_action = next_action


@dataclass(frozen=True)
class CaseProjection:
    case_id: str
    title: str
    summary: str
    platform: str
    duration_seconds: float | None
    profile: str
    industry: str
    status: str
    source_url: str | None
    approved_at: str | None
    operator_profile_hint: str | None = None
    observed_source_profile: str | None = None
    approved_by: dict[str, Any] | None = None
    attempt_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "summary": self.summary,
            "platform": self.platform,
            "duration_seconds": self.duration_seconds,
            "profile": self.profile,
            "industry": self.industry,
            "status": self.status,
            "source_url": self.source_url,
            "approved_at": self.approved_at,
            "operator_profile_hint": self.operator_profile_hint,
            "observed_source_profile": self.observed_source_profile,
            "approved_by": self.approved_by,
            "attempt_id": self.attempt_id,
        }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalOperationError(
            "CANONICAL_ARTIFACT_INVALID",
            "无法读取现有 Authority artifact。",
            "请先修复 artifact 或 lineage，再刷新页面。",
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalOperationError(
            "CANONICAL_ARTIFACT_INVALID",
            "现有 Authority artifact 格式无效。",
            "请先修复 artifact，再刷新页面。",
        )
    return value


def get_customer_status(settings: Settings, business_id: str) -> dict[str, Any]:
    if not BUSINESS_ID_RE.fullmatch(business_id):
        raise CanonicalOperationError(
            "INVALID_BUSINESS_ID",
            "客户引用格式无效。",
            "请返回客户列表后重新选择。",
        )
    script = settings.pipeline_root / "scripts" / "show_customer_status_v1.py"
    command = [
        settings.python_executable,
        str(script),
        "--business-id",
        business_id,
        "--format",
        "json",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.status_timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanonicalOperationError(
            "STATUS_RESOLVER_UNAVAILABLE",
            "暂时无法读取客户当前状态。",
            "请稍后重试；不要手动推断或修改业务状态。",
        ) from exc
    if result.returncode != 0:
        raise CanonicalOperationError(
            "STATUS_RESOLVER_FAILED",
            "客户状态解析失败。",
            "请按 resolver 返回的 Authority blocker 处理后重试。",
        )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CanonicalOperationError(
            "STATUS_RESOLVER_INVALID_OUTPUT",
            "客户状态解析器返回了无效结果。",
            "请检查 canonical status resolver 后重试。",
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("business", {}).get("business_id") != business_id
    ):
        raise CanonicalOperationError(
            "STATUS_RESOLVER_INVALID_OUTPUT",
            "客户状态结果与请求不一致。",
            "请检查 Authority lineage 后重试。",
        )
    return payload


def _safe_chinese_text(value: Any, *, max_length: int = 320) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if chinese < 4 or latin > max(8, chinese // 2):
        return ""
    return text if len(text) <= max_length else f"{text[: max_length - 1]}…"


def _case_metadata(case: dict[str, Any]) -> dict[str, Any]:
    source = case.get("source_evidence") or {}
    metadata_ref = source.get("metadata") or {}
    metadata_path = Path(str(metadata_ref.get("path") or ""))
    if not metadata_path.is_file():
        return {}
    try:
        return _read_json(metadata_path)
    except CanonicalOperationError:
        return {}


def _source_dimensions(metadata: dict[str, Any]) -> tuple[int | None, int | None]:
    video = metadata.get("video") if isinstance(metadata.get("video"), dict) else {}
    width = video.get("width")
    height = video.get("height")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return None, None
    if width <= 0 or height <= 0 or width > 16384 or height > 16384:
        return None, None
    return int(width), int(height)


def _project_case(case_path: Path, *, attempt_id: str | None = None) -> CaseProjection:
    case = _read_json(case_path)
    case_id = str(case.get("case_id") or case_path.parent.name)
    lifecycle = case.get("lifecycle") if isinstance(case.get("lifecycle"), dict) else {}
    identity = case.get("identity") if isinstance(case.get("identity"), dict) else {}
    source_evidence = (
        case.get("source_evidence")
        if isinstance(case.get("source_evidence"), dict)
        else {}
    )
    video = (
        source_evidence.get("video")
        if isinstance(source_evidence.get("video"), dict)
        else {}
    )
    storyboard = (
        case.get("storyboard") if isinstance(case.get("storyboard"), dict) else {}
    )
    understanding = (
        storyboard.get("video_understanding")
        if isinstance(storyboard.get("video_understanding"), dict)
        else {}
    )

    metadata = _case_metadata(case)
    raw_title = _safe_chinese_text(metadata.get("desc"), max_length=76)
    if not raw_title:
        raw_title = Path(str(video.get("path") or case_id)).stem
    raw_title = re.sub(rf"[_\s-]*{re.escape(case_id)}$", "", raw_title).strip(" _-")
    if not raw_title or raw_title == case_id:
        raw_title = f"抖音案例 {case_id[-6:]}"
    title = raw_title if len(raw_title) <= 76 else f"{raw_title[:73]}…"
    summary = _safe_chinese_text(understanding.get("content_goal_candidate"))

    receipt_path = case_path.parent / "approval_receipt.json"
    receipt = _read_json(receipt_path) if receipt_path.exists() else {}
    lifecycle_status = str(lifecycle.get("status") or "review_required").lower()
    approved = (
        lifecycle_status == "approved"
        and receipt.get("decision") == "approved"
        and receipt.get("human_gate") is True
    )
    if bool(lifecycle.get("retired")) or lifecycle_status in {"archived", "retired"}:
        status = "archived"
    elif approved:
        status = "approved"
    elif lifecycle_status in {"failed", "error"}:
        status = "failed"
    else:
        status = "awaiting_review"

    duration = identity.get("duration_seconds")
    return CaseProjection(
        case_id=case_id,
        title=title,
        summary=summary,
        platform=str(identity.get("platform") or "unknown"),
        duration_seconds=(
            float(duration) if isinstance(duration, (int, float)) else None
        ),
        profile=PROFILE_LABELS.get(
            str(identity.get("analysis_profile") or "unknown").lower(), "待分类"
        ),
        industry=INDUSTRY_LABELS.get(
            str(identity.get("industry") or "unknown").lower(),
            _safe_chinese_text(identity.get("industry"), max_length=30) or "待分类",
        ),
        status=status,
        source_url=str(identity["source_url"]) if identity.get("source_url") else None,
        approved_at=(
            str(lifecycle["approved_at"]) if lifecycle.get("approved_at") else None
        ),
        operator_profile_hint=(
            str(case["operator_profile_hint"])
            if case.get("operator_profile_hint") in {"mix", "news", "hybrid", "uncertain"}
            else None
        ),
        observed_source_profile=(
            (case.get("profile_analysis") or {}).get("observed_source_profile")
        ),
        approved_by=(
            {"phone": str(receipt["reviewer"])}
            if approved and receipt.get("reviewer") else None
        ),
        attempt_id=attempt_id,
    )


def _analysis_states(
    settings: Settings, case_id: str | None = None
) -> list[tuple[Path, dict[str, Any]]]:
    root = settings.pipeline_root / "data" / "case_analysis_attempts"
    pattern = (
        f"{case_id}/*/case_analysis_attempt_v1.json"
        if case_id
        else "*/*/case_analysis_attempt_v1.json"
    )
    values: list[tuple[Path, dict[str, Any]]] = []
    for path in root.glob(pattern):
        try:
            state = _read_json(path)
        except CanonicalOperationError:
            continue
        values.append((path, state))
    values.sort(key=lambda item: str(item[1].get("updated_at") or ""), reverse=True)
    return values


def _latest_candidate(
    settings: Settings, case_id: str
) -> tuple[Path, dict[str, Any]] | None:
    for state_path, state in _analysis_states(settings, case_id):
        candidate = Path(
            str((state.get("artifacts") or {}).get("case_candidate_v1") or "")
        )
        if state.get("status") == "awaiting_review" and candidate.is_file():
            return candidate, state
    return None


def list_cases(settings: Settings) -> list[dict[str, Any]]:
    cases_root = settings.pipeline_root / "data" / "cases"
    if not cases_root.exists():
        return []
    projections: list[CaseProjection] = [
        _project_case(case_path)
        for case_path in cases_root.glob("*/case_v1.json")
        if case_path.is_file()
    ]
    canonical_ids = {item.case_id for item in projections}
    seen_candidates: set[str] = set()
    for _, state in _analysis_states(settings):
        case_id = str(state.get("case_id") or "")
        if not case_id or case_id in canonical_ids or case_id in seen_candidates:
            continue
        candidate = Path(
            str((state.get("artifacts") or {}).get("case_candidate_v1") or "")
        )
        if state.get("status") != "awaiting_review" or not candidate.is_file():
            continue
        projections.append(
            _project_case(candidate, attempt_id=str(state.get("attempt_id") or ""))
        )
        seen_candidates.add(case_id)
    projections.sort(
        key=lambda item: (item.approved_at or "", item.case_id), reverse=True
    )
    return [item.to_dict() for item in projections]


def normalize_source_url(url: str) -> str:
    raw = url.strip()
    if len(raw) > 2048:
        raise ValueError("URL is too long")
    parts = urlsplit(raw)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL must use http or https")
    host = parts.hostname.lower() if parts.hostname else ""
    if host not in {"douyin.com", "www.douyin.com", "v.douyin.com", "iesdouyin.com"}:
        raise ValueError("unsupported source")
    clean_path = re.sub(r"/+", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), host, clean_path, "", ""))


def find_duplicate_case(settings: Settings, url: str) -> dict[str, Any] | None:
    normalized = normalize_source_url(url)
    video_match = DOUYIN_VIDEO_ID_RE.search(url)
    video_id = video_match.group(1) if video_match else None
    for case in list_cases(settings):
        if video_id and case["case_id"] == video_id:
            return case
        source_url = case.get("source_url")
        if source_url:
            try:
                if normalize_source_url(source_url) == normalized:
                    return case
            except ValueError:
                continue
    return None


def resolve_case_source_duplicate(
    settings: Settings,
    url: str,
) -> dict[str, Any] | None:
    """
    Resolve deterministic duplicate state for one canonical source identity.

    This does not perform semantic similarity matching.
    """

    normalized = normalize_source_url(url)

    # Search the raw URL as well, because video_id may live in a query string
    # that normalize_source_url intentionally removes.
    match = DOUYIN_VIDEO_ID_RE.search(url)
    if match is None:
        match = DOUYIN_VIDEO_ID_RE.search(normalized)

    if match is None:
        return None

    case_id = match.group(1)

    canonical = settings.pipeline_root / "data" / "cases" / case_id / "case_v1.json"

    if canonical.is_file():
        projection = _project_case(canonical).to_dict()

        return {
            "duplicate": True,
            "duplicate_kind": "source_identity",
            "state": "approved",
            "case_id": case_id,
            "attempt_id": None,
            "existing_case": projection,
            "can_reanalyze": False,
            "message": "这个视频已经在案例库里了。",
            "next_action": "查看已有案例。",
        }

    states = _analysis_states(settings, case_id)

    for state_path, state in states:
        status = str(state.get("status") or "").lower()

        if status not in {
            "queued",
            "running",
            "awaiting_review",
            "failed",
            "rejected",
            "approved",
        }:
            continue

        attempt_id = str(state.get("attempt_id") or state_path.parent.name)

        existing_case: dict[str, Any] | None = None

        candidate = Path(
            str((state.get("artifacts") or {}).get("case_candidate_v1") or "")
        )

        if candidate.is_file():
            existing_case = _project_case(
                candidate,
                attempt_id=attempt_id,
            ).to_dict()

            # _project_case reads the Candidate's own lifecycle, which remains
            # review_required even after a Human rejects the attempt.
            # The attempt lifecycle is authoritative for the analysis state.
        if status == "rejected" and existing_case is not None:
            existing_case["status"] = "rejected"

        rejection_reason = None
        if status == "rejected":
            decision_path = Path(str(state.get("human_review_decision") or ""))
            if decision_path.is_file():
                try:
                    rejection_reason = str(_read_json(decision_path).get("reason") or "")
                except CanonicalOperationError:
                    rejection_reason = None

        if status in {"queued", "running"}:
            message = "这个视频正在分析。"
            next_action = "查看任务进度。"
            can_reanalyze = False
        elif status == "awaiting_review":
            message = "这个视频已经分析完成，正在等待审核。"
            next_action = "去审核案例。"
            can_reanalyze = False
        elif status == "approved":
            message = "这个视频已经在案例库里了。"
            next_action = "查看已有案例。"
            can_reanalyze = False
        elif status == "failed":
            message = "这个视频之前分析失败。"
            next_action = "可以显式重新分析。"
            can_reanalyze = True
        else:
            message = "这个案例之前没有收录。"
            next_action = "如有新的判断，可以显式重新分析。"
            can_reanalyze = True

        return {
            "duplicate": True,
            "duplicate_kind": "source_identity",
            "state": status,
            "case_id": case_id,
            "attempt_id": attempt_id,
            "existing_case": existing_case,
            "can_reanalyze": can_reanalyze,
            "message": message,
            "next_action": next_action,
            "rejection_reason": rejection_reason,
        }

    return None


def case_analysis_capability() -> dict[str, Any]:
    return {
        "available": True,
        "operation": "case_analysis_v1",
        "message": "可以分析完整的抖音视频链接。",
        "next_action": "提交后可离开页面，任务进度会持续保留。",
    }


def source_case_id(url: str) -> str:
    normalized = normalize_source_url(url)

    # Prefer the original URL because some valid Douyin variants may carry
    # video_id in the query string, while normalization intentionally removes
    # query parameters.
    match = DOUYIN_VIDEO_ID_RE.search(url)
    if match is None:
        match = DOUYIN_VIDEO_ID_RE.search(normalized)

    if match is None:
        raise ValueError("full video URL required")

    return match.group(1)


def _find_case_path(
    settings: Settings, case_id: str
) -> tuple[Path, dict[str, Any] | None]:
    if not re.fullmatch(r"\d{10,24}", str(case_id or "")):
        raise CanonicalOperationError(
            "CASE_NOT_FOUND", "没有找到这个案例。", "请返回案例库后重新选择。"
        )
    canonical = settings.pipeline_root / "data" / "cases" / case_id / "case_v1.json"
    if canonical.is_file():
        return canonical, None
    candidate = _latest_candidate(settings, case_id)
    if candidate is None:
        raise CanonicalOperationError(
            "CASE_NOT_FOUND", "没有找到这个案例。", "请返回案例库后重新选择。"
        )
    return candidate


def _case_title(case: dict[str, Any], case_path: Path) -> str:
    metadata = _case_metadata(case)
    title = _safe_chinese_text(metadata.get("desc"), max_length=110)
    if title:
        return title
    source_video = ((case.get("source_evidence") or {}).get("video") or {}).get("path")
    raw = Path(str(source_video or case_path.parent.name)).stem
    case_id = str(case.get("case_id") or case_path.parent.name)
    cleaned = re.sub(rf"[_\s-]*{re.escape(case_id)}$", "", raw).strip(" _-")
    return cleaned or f"抖音案例 {case_id[-6:]}"


def _partial_approval_state(
    settings: Settings, case_id: str, case: dict[str, Any]
) -> dict[str, Any] | None:
    lifecycle = case.get("lifecycle") or {}
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        return None
    attempt_id = str((case.get("analysis_lineage") or {}).get("attempt_id") or "")
    if not attempt_id:
        return None
    for _, state in _analysis_states(settings, case_id):
        if str(state.get("attempt_id") or "") != attempt_id:
            continue
        if state.get("status") not in {"awaiting_review", "approved"}:
            return None
        companion_path = _approval_companion_path(settings, case_id)
        if state.get("status") == "awaiting_review" or not companion_path.is_file():
            return state
        try:
            _validate_governance_companion(
                _read_json(companion_path),
                case_path=settings.pipeline_root
                / "data"
                / "cases"
                / case_id
                / "case_v1.json",
                receipt_path=settings.pipeline_root
                / "data"
                / "cases"
                / case_id
                / "approval_receipt.json",
            )
        except CanonicalOperationError:
            return state
        return None
    return None


def get_case_detail(settings: Settings, case_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{10,24}", case_id):
        raise CanonicalOperationError(
            "CASE_NOT_FOUND", "没有找到这个案例。", "请返回案例库后重新选择。"
        )
    case_path, attempt = _find_case_path(settings, case_id)
    case = _read_json(case_path)
    recovery_state = _partial_approval_state(settings, case_id, case)
    projection = _project_case(
        case_path,
        attempt_id=str(attempt.get("attempt_id")) if attempt else None,
    ).to_dict()
    understanding = (case.get("storyboard") or {}).get("video_understanding") or {}
    metadata = _case_metadata(case)
    source_width, source_height = _source_dimensions(metadata)
    if recovery_state is not None:
        projection["status"] = "awaiting_review"
    sequence = [
        _safe_chinese_text(item.get("description"), max_length=260)
        for item in (understanding.get("structure_sequence") or [])
        if isinstance(item, dict)
    ]
    sequence = [value for value in sequence if value]
    shots: list[dict[str, Any]] = []
    for index, shot in enumerate(
        (case.get("storyboard") or {}).get("shots") or [], start=1
    ):
        evidence = shot.get("evidence") or {}
        interpretation = shot.get("interpretation") or {}
        scenes = [
            _safe_chinese_text(value, max_length=180)
            for value in (evidence.get("observable_scene_safe_verbatim") or [])
        ]
        scenes = [value for value in scenes if value]
        onscreen = [
            _safe_chinese_text(value, max_length=140)
            for value in (evidence.get("onscreen_text_safe_verbatim") or [])
        ]
        onscreen = [value for value in onscreen if value]
        shots.append(
            {
                "number": index,
                "start": shot.get("start"),
                "end": shot.get("end"),
                "narration": _safe_chinese_text(
                    evidence.get("audio_overlap_safe_verbatim"), max_length=260
                ),
                "scene": "；".join(scenes[:2]),
                "onscreen_text": "；".join(onscreen[:2]),
                "function": _safe_chinese_text(
                    interpretation.get("narrative_function"), max_length=260
                ),
            }
        )
    lifecycle = case.get("lifecycle") or {}
    try:
        review_source_url = normalize_source_url(str(projection.get("source_url") or ""))
    except ValueError:
        review_source_url = None
    try:
        case_media_path(settings, case_id)
        local_media_available = True
    except CanonicalOperationError:
        local_media_available = False
    review_attempt_id = str(
        (attempt or {}).get("attempt_id")
        or (case.get("analysis_lineage") or {}).get("attempt_id")
        or ""
    )
    review_receipt = {}
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", review_attempt_id):
        review_receipt_path = (
            settings.pipeline_root / "data" / "case_analysis_attempts" / case_id
            / review_attempt_id / "human_review_decision_v1.json"
        )
        if review_receipt_path.is_file():
            review_receipt = _read_json(review_receipt_path)
    return {
        **projection,
        "reviewed_by": (
            {"phone": str(review_receipt["reviewer"])} if review_receipt.get("reviewer") else None
        ),
        "title": _case_title(case, case_path),
        "description": _safe_chinese_text(metadata.get("desc"), max_length=360),
        "what_it_says": {
            "topic": _safe_chinese_text(metadata.get("desc"), max_length=220),
            "core_expression": _safe_chinese_text(
                understanding.get("content_goal_candidate"), max_length=520
            ),
        },
        "how_it_tells": {
            "opening": sequence[0] if sequence else "",
            "development": sequence[1:-1] if len(sequence) > 2 else sequence[1:],
            "ending": sequence[-1] if len(sequence) > 1 else "",
        },
        "reusable_observations": [
            value
            for value in (
                _safe_chinese_text(
                    understanding.get("audio_visual_strategy"), max_length=420
                ),
                _safe_chinese_text(understanding.get("audio_role"), max_length=320),
                _safe_chinese_text(
                    understanding.get("visual_scene_role"), max_length=320
                ),
            )
            if value
        ],
        "full_breakdown": {
            "narration": _safe_chinese_text(
                (case.get("audio_evidence") or {}).get("transcript_safe_semantic"),
                max_length=12000,
            ),
            "shots": shots,
        },
        "review": {
            "can_review": lifecycle.get("status") == "review_required"
            or recovery_state is not None,
            "approved": lifecycle.get("status") == "approved"
            and lifecycle.get("approved") is True
            and recovery_state is None,
            "approval_recovery_required": recovery_state is not None,
            "attempt_id": (
                str(recovery_state.get("attempt_id"))
                if recovery_state is not None
                else str(attempt.get("attempt_id")) if attempt else None
            ),
        },
        "review_media": {
            "local_available": local_media_available,
            "local_url": (
                f"/api/cases/{case_id}/media" if local_media_available else None
            ),
            "remote_embed_url": (
                f"https://open.douyin.com/player/video?vid={case_id}"
            ),
            "source_url": review_source_url,
            "remote_player_is_authority": False,
            "source_width": source_width,
            "source_height": source_height,
            "aspect_ratio": (
                source_width / source_height
                if source_width is not None and source_height is not None
                else 9 / 16
            ),
        },
        "media_rights": {
            "production_authorized": False,
            "message": "批准入库不代表原视频素材可以用于客户生产。",
        },
    }


def case_media_path(settings: Settings, case_id: str) -> Path:
    case_path, _ = _find_case_path(settings, case_id)
    case = _read_json(case_path)
    video = Path(
        str(
            (((case.get("source_evidence") or {}).get("video") or {}).get("path")) or ""
        )
    )
    allowed = (settings.repo_root / "douyin-downloader" / "Downloaded").resolve()
    try:
        resolved = video.resolve(strict=True)
        resolved.relative_to(allowed)
    except (OSError, ValueError) as exc:
        raise CanonicalOperationError(
            "CASE_MEDIA_UNAVAILABLE",
            "案例原视频暂时无法播放。",
            "请检查原始来源文件是否仍然可用。",
        ) from exc
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _governance_policy_path(settings: Settings) -> Path:
    return (
        settings.pipeline_root
        / "data"
        / "case_governance"
        / "case_source_governance_policy_v1.json"
    )


def _governance_companion(
    settings: Settings,
    case_path: Path,
    *,
    canonical_case_path: Path | None = None,
) -> dict[str, Any]:
    case = _read_json(case_path)
    receipt = case_path.parent / "approval_receipt.json"
    published_case_path = canonical_case_path or case_path
    published_receipt_path = published_case_path.parent / "approval_receipt.json"
    legacy_gate = case.get("source_rights_gate")
    policy = _governance_policy_path(settings)
    if legacy_gate is not None and not policy.is_file():
        raise CanonicalOperationError(
            "CASE_SOURCE_GOVERNANCE_BLOCKED",
            "历史案例缺少已冻结的来源治理策略，不能完成入库。",
            "请恢复与该历史案例匹配的 Approved/Frozen Governance Policy 后重试。",
        )
    if legacy_gate is not None:
        policy_value = _read_json(policy)
        if (
            policy_value.get("schema_version")
            != "case-source-governance-policy-v1.0"
            or policy_value.get("status") != "approved_frozen"
            or policy_value.get("version") != "V1.0"
        ):
            raise CanonicalOperationError(
                "CASE_SOURCE_GOVERNANCE_BLOCKED",
                "历史案例的来源治理策略无效，不能完成入库。",
                "请恢复有效的 Approved/Frozen Governance Policy V1.0 后重试。",
            )
    source_path = Path(
        str(
            (((case.get("source_evidence") or {}).get("video") or {}).get("path")) or ""
        )
    )
    source_url = str((case.get("identity") or {}).get("source_url") or "")
    approved_traceability = (
        (case.get("approval") or {}).get("source_traceability") or {}
    )
    recorded_source_sha256 = str(
        approved_traceability.get("recorded_source_sha256")
        or ((case.get("source_provenance") or {}).get("recorded_source_media_sha256"))
        or (((case.get("source_evidence") or {}).get("video") or {}).get("sha256"))
        or ""
    ).lower()
    stable_video_id = str(
        approved_traceability.get("stable_video_id") or case.get("case_id") or ""
    )
    acquisition_lineage_valid = (
        approved_traceability.get("acquisition_lineage_valid") is True
    )
    traceable = bool(
        source_url
        and stable_video_id
        and recorded_source_sha256
        and acquisition_lineage_valid
    )
    return {
        "schema_version": "case-source-governance-companion-v1.0",
        "builder_version": "internal-console-case-approval-gateway@1.1",
        "companion_id": f"case_source_governance_companion_v1::{case['case_id']}",
        "case_id": case["case_id"],
        "canonical_case_status": "approved",
        "case_ref": {
            "artifact_type": "approved_case",
            "path": str(published_case_path),
            "sha256": _sha256(case_path),
            "source_artifact_modified": False,
        },
        "case_approval_receipt_ref": {
            "artifact_type": "case_approval_receipt",
            "path": str(published_receipt_path),
            "sha256": _sha256(receipt),
            "source_artifact_modified": False,
        },
        "source_provenance": {
            "status": "traceable" if traceable else "invalid",
            "traceable": traceable,
            "platform": "douyin",
            "source_url": source_url,
            "source_url_present": bool(source_url),
            "stable_video_id": stable_video_id,
            "stable_identity_present": bool(stable_video_id),
            "local_source_path": str(source_path),
            "local_source_exists": source_path.is_file(),
            "local_source_sha256": (
                _sha256(source_path) if source_path.is_file() else None
            ),
            "recorded_source_sha256": recorded_source_sha256,
            "recorded_sha_matches": (
                _sha256(source_path) == recorded_source_sha256
                if source_path.is_file() and recorded_source_sha256
                else None
            ),
            "source_acquisition_path": approved_traceability.get(
                "source_acquisition_path"
            ),
            "acquisition_lineage_valid": acquisition_lineage_valid,
            "source_metadata_path": approved_traceability.get(
                "source_metadata_path"
            ),
            "source_metadata_valid": approved_traceability.get(
                "source_metadata_valid"
            )
            is True,
            "semantics": "identity_and_evidence_lineage_not_reuse_permission",
        },
        "research_ingestion_eligibility": "eligible_for_internal_research",
        "research_ingestion_basis": "explicit_human_governance_decision",
        "media_reuse_rights": "not_established",
        "production_footage_pool_eligible": False,
        "privacy_basis": "embedded_privacy_gate_library_safe",
        "legacy_source_rights_field_observation": {
            "present": legacy_gate is not None,
            "status": (
                str((legacy_gate or {}).get("status") or "") or None
                if isinstance(legacy_gate, dict)
                else None
            ),
            "used_as_current_governance_authority": False,
        },
        "governance_policy_version": "V1.0" if legacy_gate is not None else None,
        "governance_policy_ref": (
            {
                "applicable": True,
                "artifact_type": "case_source_governance_policy_v1",
                "path": str(policy),
                "sha256": _sha256(policy),
                "source_artifact_modified": False,
            }
            if legacy_gate is not None
            else {
                "applicable": False,
                "artifact_type": "case_source_governance_policy_v1",
                "path": None,
                "sha256": None,
                "source_artifact_modified": False,
            }
        ),
        "case_approval_changed_media_reuse_rights": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _approval_companion_path(settings: Settings, case_id: str) -> Path:
    return (
        settings.pipeline_root
        / "data"
        / "case_governance"
        / "cases"
        / case_id
        / "case_source_governance_companion_v1.json"
    )


def _approval_candidate(
    settings: Settings, case_id: str
) -> tuple[Path, dict[str, Any]] | None:
    for _, state in _analysis_states(settings, case_id):
        candidate = Path(
            str((state.get("artifacts") or {}).get("case_candidate_v1") or "")
        )
        if state.get("status") in {"awaiting_review", "approved"} and candidate.is_file():
            return candidate, state
    return None


def _approval_block(message: str, next_action: str) -> CanonicalOperationError:
    return CanonicalOperationError("CASE_APPROVAL_BLOCKED", message, next_action)


def _validate_approved_case_artifacts(
    case_path: Path,
    *,
    expected_case_id: str,
    expected_attempt_id: str,
    expected_reviewer: str | None = None,
    recovery: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    code = "CASE_APPROVAL_RECOVERY_REQUIRED" if recovery else "CASE_APPROVAL_BLOCKED"

    def invalid(message: str) -> None:
        raise CanonicalOperationError(
            code,
            message,
            "请核对当前 Attempt lineage 与必需审批 artifact 后重试；不要手工修改 Authority 文件。",
        )

    case = _read_json(case_path)
    receipt_path = case_path.parent / "approval_receipt.json"
    if not receipt_path.is_file():
        invalid("案例审批回执缺失，审批未完成。")
    receipt = _read_json(receipt_path)
    lifecycle = case.get("lifecycle") or {}
    approval = case.get("approval") or {}
    lineage = case.get("analysis_lineage") or {}
    if str(case.get("case_id") or "") != expected_case_id:
        invalid("审批后的 Case identity 与请求不一致。")
    if str(lineage.get("attempt_id") or "") != expected_attempt_id:
        invalid("已批准 Case 来自不同的分析 Attempt，不能自动补齐。")
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        invalid("审批脚本没有形成完整的 approved lifecycle。")
    if (
        receipt.get("case_id") != expected_case_id
        or receipt.get("decision") != "approved"
        or receipt.get("human_gate") is not True
    ):
        invalid("案例审批回执与 Human Gate 不一致。")
    reviewer = str(approval.get("reviewer") or "")
    if not reviewer or reviewer != str(receipt.get("reviewer") or ""):
        invalid("案例与审批回执的 Human reviewer 不一致。")
    if expected_reviewer is not None and reviewer != expected_reviewer:
        invalid("审批结果未保留当前登录审核人。")
    if str(receipt.get("case_sha256_after_approval") or "").lower() != _sha256(
        case_path
    ):
        invalid("案例审批回执的 SHA-256 与 approved Case 不一致。")
    traceability = approval.get("source_traceability") or {}
    recorded_sha = str(traceability.get("recorded_source_sha256") or "").lower()
    if not (
        traceability.get("traceable") is True
        and traceability.get("acquisition_lineage_valid") is True
        and traceability.get("source_metadata_valid") is True
        and str(traceability.get("stable_video_id") or "") == expected_case_id
        and str(traceability.get("source_url") or "")
        and re.fullmatch(r"[0-9a-f]{64}", recorded_sha)
    ):
        invalid("案例来源 URL、稳定编号、媒体 SHA 或 acquisition lineage 无效。")
    privacy = case.get("privacy_gate") or {}
    if not (
        privacy.get("library_safe") is True
        and privacy.get("unresolved_sensitive_items") == 0
        and privacy.get("derived_artifact_scan_passed") is True
    ):
        invalid("案例隐私投影尚未满足入库条件。")
    if approval.get("media_reuse_authorized") is True:
        invalid("案例审批不得授予原媒体复用权。")
    if receipt.get("case_approval_grants_media_reuse") is True:
        invalid("案例审批回执不得授予原媒体复用权。")
    return case, receipt


def _validate_governance_companion(
    companion: dict[str, Any],
    *,
    case_path: Path,
    receipt_path: Path,
) -> None:
    expected_case_id = str(_read_json(case_path).get("case_id") or "")
    if not (
        companion.get("canonical_case_status") == "approved"
        and companion.get("case_id") == expected_case_id
        and (companion.get("source_provenance") or {}).get("traceable") is True
        and companion.get("media_reuse_rights") == "not_established"
        and companion.get("production_footage_pool_eligible") is False
        and (companion.get("case_ref") or {}).get("sha256") == _sha256(case_path)
        and (companion.get("case_approval_receipt_ref") or {}).get("sha256")
        == _sha256(receipt_path)
    ):
        raise CanonicalOperationError(
            "CASE_SOURCE_GOVERNANCE_BLOCKED",
            "案例来源治理 companion 校验失败。",
            "请核对来源 lineage 与审批回执后重试；不要手工补写 companion。",
        )


def _remove_staged_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _publish_approval_transaction(
    *,
    staged_case_dir: Path,
    canonical_dir: Path,
    staged_companion_path: Path,
    companion_path: Path,
    staged_state_path: Path,
    state_path: Path,
) -> None:
    transaction_id = uuid.uuid4().hex
    canonical_backup = canonical_dir.parent / f".{canonical_dir.name}.{transaction_id}.rollback"
    companion_backup = companion_path.parent / f".{companion_path.name}.{transaction_id}.rollback"
    canonical_was_present = canonical_dir.exists()
    companion_was_present = companion_path.exists()
    canonical_published = False
    companion_published = False
    try:
        canonical_dir.parent.mkdir(parents=True, exist_ok=True)
        companion_path.parent.mkdir(parents=True, exist_ok=True)
        if canonical_was_present:
            os.replace(canonical_dir, canonical_backup)
        if companion_was_present:
            os.replace(companion_path, companion_backup)
        os.replace(staged_companion_path, companion_path)
        companion_published = True
        os.replace(staged_case_dir, canonical_dir)
        canonical_published = True
        os.replace(staged_state_path, state_path)
    except OSError as exc:
        if canonical_published:
            _remove_staged_path(canonical_dir)
        if canonical_was_present and canonical_backup.exists():
            os.replace(canonical_backup, canonical_dir)
        if companion_published:
            _remove_staged_path(companion_path)
        if companion_was_present and companion_backup.exists():
            os.replace(companion_backup, companion_path)
        raise _approval_block(
            "案例审批 artifact 发布失败，原 Authority 已保持不变。",
            "请检查本机文件系统后重试审批。",
        ) from exc
    else:
        _remove_staged_path(canonical_backup)
        _remove_staged_path(companion_backup)


def _run_case_fingerprint(settings: Settings, case_path: Path) -> str:
    try:
        result = subprocess.run(
            [
                settings.pipeline_python_executable or settings.python_executable,
                str(settings.pipeline_root / "scripts" / "build_case_fingerprint_v1.py"),
                "--case",
                str(case_path),
            ],
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "retry_required"
    return "completed" if result.returncode == 0 else "retry_required"


def _update_fingerprint_status(state_path: Path, status: str) -> None:
    try:
        state = _read_json(state_path)
        state["fingerprint_status"] = status
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_atomic(state_path, state)
    except (CanonicalOperationError, OSError):
        logger.exception("Unable to persist optional Case fingerprint status")


def _reconcile_partial_case_approval(
    settings: Settings,
    case_id: str,
    candidate_path: Path,
    state: dict[str, Any],
    *,
    requested_by: str,
) -> dict[str, Any]:
    canonical_path = settings.pipeline_root / "data" / "cases" / case_id / "case_v1.json"
    state_path = candidate_path.parents[2] / "case_analysis_attempt_v1.json"
    attempt_id = str(state.get("attempt_id") or "")
    _, receipt = _validate_approved_case_artifacts(
        canonical_path,
        expected_case_id=case_id,
        expected_attempt_id=attempt_id,
        recovery=True,
    )
    companion_path = _approval_companion_path(settings, case_id)
    companion_exists = companion_path.is_file()
    if companion_exists:
        _validate_governance_companion(
            _read_json(companion_path),
            case_path=canonical_path,
            receipt_path=canonical_path.parent / "approval_receipt.json",
        )
    if state.get("status") == "approved" and companion_exists:
        raise CanonicalOperationError(
            "CASE_ALREADY_APPROVED",
            "这个案例已经完整入库。",
            "请返回案例库查看，不要重复审批。",
        )

    now = datetime.now(timezone.utc).isoformat()
    next_state = copy.deepcopy(state)
    next_state.update(
        {
            "status": "approved",
            "approved_case_path": str(canonical_path),
            "governance_companion_path": str(companion_path),
            "fingerprint_status": str(state.get("fingerprint_status") or "pending"),
            "updated_at": now,
            "approval_reconciliation": {
                "kind": "system_partial_approval_reconciliation",
                "reconciled_at": now,
                "requested_by": requested_by,
                "original_reviewer": receipt.get("reviewer"),
                "attempt_id": attempt_id,
                "canonical_case_sha256": _sha256(canonical_path),
                "approval_receipt_sha256": _sha256(
                    canonical_path.parent / "approval_receipt.json"
                ),
                "second_human_approval_performed": False,
            },
        }
    )
    staged_state = state_path.parent / ".approval-state.stage"
    staged_companion = companion_path.parent / ".approval-companion.stage"
    _write_atomic(staged_state, next_state)
    try:
        if not companion_exists:
            companion = _governance_companion(settings, canonical_path)
            _validate_governance_companion(
                companion,
                case_path=canonical_path,
                receipt_path=canonical_path.parent / "approval_receipt.json",
            )
            _write_atomic(staged_companion, companion)
            companion_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged_companion, companion_path)
        try:
            os.replace(staged_state, state_path)
        except OSError as exc:
            if not companion_exists:
                _remove_staged_path(companion_path)
            raise CanonicalOperationError(
                "CASE_APPROVAL_RECOVERY_REQUIRED",
                "审批恢复状态写入失败，approved Case 未被修改。",
                "请检查文件系统后重试同一案例审批。",
            ) from exc
    finally:
        _remove_staged_path(staged_state)
        _remove_staged_path(staged_companion)
    fingerprint_status = _run_case_fingerprint(settings, canonical_path)
    _update_fingerprint_status(state_path, fingerprint_status)
    return get_case_detail(settings, case_id)


def approve_case_candidate(
    settings: Settings,
    case_id: str,
    *,
    reviewer: str,
    note: str,
) -> dict[str, Any]:
    candidate = _approval_candidate(settings, case_id)
    canonical_dir = settings.pipeline_root / "data" / "cases" / case_id
    canonical_path = canonical_dir / "case_v1.json"
    if candidate is None:
        if (
            canonical_path.is_file()
            and (_read_json(canonical_path).get("lifecycle") or {}).get("status")
            == "approved"
        ):
            raise CanonicalOperationError(
                "CASE_ALREADY_APPROVED", "这个案例已经入库。", "请返回案例库查看。"
            )
        raise CanonicalOperationError(
            "CASE_REVIEW_NOT_READY",
            "案例还没有可审核的分析结果。",
            "请等待分析完成后重试。",
        )
    candidate_path, state = candidate
    attempt_id = str(state.get("attempt_id") or "")
    if canonical_path.is_file():
        current = _read_json(canonical_path)
        if (current.get("lifecycle") or {}).get("status") == "approved":
            return _reconcile_partial_case_approval(
                settings,
                case_id,
                candidate_path,
                state,
                requested_by=reviewer,
            )
        backup = candidate_path.parents[2] / "superseded_canonical"
        if not backup.exists():
            shutil.copytree(canonical_dir, backup)
    if state.get("status") != "awaiting_review":
        raise CanonicalOperationError(
            "CASE_APPROVAL_RECOVERY_REQUIRED",
            "Attempt 状态与 canonical approval 状态不一致。",
            "请核对当前 Attempt 后重试；不要创建第二次人工审批。",
        )
    transaction_id = uuid.uuid4().hex[:8]
    temporary_dir = canonical_dir.parent / f".{case_id}.{transaction_id}.stage"
    canonical_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(candidate_path.parent, temporary_dir)
    staged_case_path = temporary_dir / "case_v1.json"
    candidate_value = _read_json(candidate_path)
    policy = _governance_policy_path(settings)
    legacy_policy_required = candidate_value.get("source_rights_gate") is not None
    if legacy_policy_required and not policy.is_file():
        _remove_staged_path(temporary_dir)
        raise CanonicalOperationError(
            "CASE_SOURCE_GOVERNANCE_BLOCKED",
            "历史案例缺少已冻结的来源治理策略，不能完成入库。",
            "请恢复与该历史案例匹配的 Approved/Frozen Governance Policy 后重试。",
        )
    command = [
        settings.pipeline_python_executable or settings.python_executable,
        str(settings.pipeline_root / "scripts" / "approve_case_v1.py"),
        "--case",
        str(staged_case_path),
        "--reviewer",
        reviewer,
        "--note",
        note,
    ]
    if legacy_policy_required:
        command.extend(["--governance-policy", str(policy)])
    try:
        result = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _remove_staged_path(temporary_dir)
        raise _approval_block(
            "案例审批校验暂时无法完成。",
            "请检查本机 Pipeline runtime 后重试。",
        ) from exc
    if result.returncode != 0:
        logger.warning("Case approval blocked for %s: %s", case_id, result.stderr or result.stdout)
        _remove_staged_path(temporary_dir)
        raise _approval_block(
            "案例未通过入库校验。",
            "请根据分析与来源边界修正后重新审核。",
        )

    companion_path = _approval_companion_path(settings, case_id)
    staged_companion_path = companion_path.parent / ".approval-companion.stage"
    state_path = candidate_path.parents[2] / "case_analysis_attempt_v1.json"
    staged_state_path = state_path.parent / ".approval-state.stage"
    try:
        staged_receipt_path = staged_case_path.parent / "approval_receipt.json"
        staged_receipt = _read_json(staged_receipt_path)
        staged_receipt["case_path"] = str(canonical_path)
        _write_atomic(staged_receipt_path, staged_receipt)
        _validate_approved_case_artifacts(
            staged_case_path,
            expected_case_id=case_id,
            expected_attempt_id=attempt_id,
            expected_reviewer=reviewer,
        )
        companion = _governance_companion(
            settings,
            staged_case_path,
            canonical_case_path=canonical_path,
        )
        _validate_governance_companion(
            companion,
            case_path=staged_case_path,
            receipt_path=staged_receipt_path,
        )
        _write_atomic(staged_companion_path, companion)
        next_state = copy.deepcopy(state)
        next_state.update(
            {
                "status": "approved",
                "approved_case_path": str(canonical_path),
                "governance_companion_path": str(companion_path),
                "fingerprint_status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_atomic(staged_state_path, next_state)
        _publish_approval_transaction(
            staged_case_dir=temporary_dir,
            canonical_dir=canonical_dir,
            staged_companion_path=staged_companion_path,
            companion_path=companion_path,
            staged_state_path=staged_state_path,
            state_path=state_path,
        )
    finally:
        _remove_staged_path(temporary_dir)
        _remove_staged_path(staged_companion_path)
        _remove_staged_path(staged_state_path)
    fingerprint_status = _run_case_fingerprint(settings, canonical_path)
    _update_fingerprint_status(state_path, fingerprint_status)
    return get_case_detail(settings, case_id)


def record_case_review_decision(
    settings: Settings,
    case_id: str,
    *,
    reviewer: str,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    candidate = _latest_candidate(settings, case_id)
    if candidate is None:
        raise CanonicalOperationError(
            "CASE_REVIEW_NOT_READY",
            "案例还没有可审核的分析结果。",
            "请等待分析完成后重试。",
        )
    candidate_path, state = candidate
    receipt = {
        "schema_version": "case-human-review-decision-v1.0",
        "case_id": case_id,
        "attempt_id": state.get("attempt_id"),
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "human_gate": True,
        "case_candidate_sha256": _sha256(candidate_path),
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "media_reuse_rights_changed": False,
    }
    receipt_path = candidate_path.parents[2] / "human_review_decision_v1.json"
    _write_atomic(receipt_path, receipt)
    state["human_review_decision"] = str(receipt_path)
    if decision == "reject":
        state["status"] = "rejected"
        state["current_stage"] = "不收录"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    attempt_root = candidate_path.parents[2]
    state_path = attempt_root / "case_analysis_attempt_v1.json"
    _write_atomic(state_path, state)
    if decision == "reject":
        command = [
            settings.pipeline_python_executable or settings.python_executable,
            str(settings.pipeline_root / "scripts" / "storage_retention_v1.py"),
            "--pipeline-root",
            str(settings.pipeline_root),
            "--downloader-root",
            str(settings.repo_root / "douyin-downloader"),
            "--attempt-root",
            str(attempt_root),
            "--trigger",
            "human_reject",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=settings.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=pipeline_subprocess_env(needs_deepseek=False),
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = None
            cleanup_error = str(exc)
        else:
            cleanup_error = (result.stderr or result.stdout).strip()
        if result is None or result.returncode != 0:
            latest = _read_json(state_path)
            latest["cleanup_status"] = "retry_required"
            latest["storage_cleanup"] = {
                "status": "retry_required",
                "trigger": "human_reject",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "error": cleanup_error or "Storage cleanup command failed.",
            }
            _write_atomic(state_path, latest)
    return receipt
