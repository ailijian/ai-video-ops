from __future__ import annotations

import json
import hashlib
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
    if not isinstance(payload, dict) or payload.get("business", {}).get("business_id") != business_id:
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


def _project_case(case_path: Path, *, attempt_id: str | None = None) -> CaseProjection:
    case = _read_json(case_path)
    case_id = str(case.get("case_id") or case_path.parent.name)
    lifecycle = case.get("lifecycle") if isinstance(case.get("lifecycle"), dict) else {}
    identity = case.get("identity") if isinstance(case.get("identity"), dict) else {}
    source_evidence = (
        case.get("source_evidence") if isinstance(case.get("source_evidence"), dict) else {}
    )
    video = source_evidence.get("video") if isinstance(source_evidence.get("video"), dict) else {}
    storyboard = case.get("storyboard") if isinstance(case.get("storyboard"), dict) else {}
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
        duration_seconds=float(duration) if isinstance(duration, (int, float)) else None,
        profile=PROFILE_LABELS.get(
            str(identity.get("analysis_profile") or "unknown").lower(), "待分类"
        ),
        industry=INDUSTRY_LABELS.get(
            str(identity.get("industry") or "unknown").lower(),
            _safe_chinese_text(identity.get("industry"), max_length=30) or "待分类",
        ),
        status=status,
        source_url=str(identity["source_url"]) if identity.get("source_url") else None,
        approved_at=str(lifecycle["approved_at"]) if lifecycle.get("approved_at") else None,
        attempt_id=attempt_id,
    )


def _analysis_states(settings: Settings, case_id: str | None = None) -> list[tuple[Path, dict[str, Any]]]:
    root = settings.pipeline_root / "data" / "case_analysis_attempts"
    pattern = f"{case_id}/*/case_analysis_attempt_v1.json" if case_id else "*/*/case_analysis_attempt_v1.json"
    values: list[tuple[Path, dict[str, Any]]] = []
    for path in root.glob(pattern):
        try:
            state = _read_json(path)
        except CanonicalOperationError:
            continue
        values.append((path, state))
    values.sort(key=lambda item: str(item[1].get("updated_at") or ""), reverse=True)
    return values


def _latest_candidate(settings: Settings, case_id: str) -> tuple[Path, dict[str, Any]] | None:
    for state_path, state in _analysis_states(settings, case_id):
        candidate = Path(str((state.get("artifacts") or {}).get("case_candidate_v1") or ""))
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
        candidate = Path(str((state.get("artifacts") or {}).get("case_candidate_v1") or ""))
        if state.get("status") != "awaiting_review" or not candidate.is_file():
            continue
        projections.append(
            _project_case(candidate, attempt_id=str(state.get("attempt_id") or ""))
        )
        seen_candidates.add(case_id)
    projections.sort(key=lambda item: (item.approved_at or "", item.case_id), reverse=True)
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


def case_analysis_capability() -> dict[str, Any]:
    return {
        "available": True,
        "operation": "case_analysis_v1",
        "message": "可以分析完整的抖音视频链接。",
        "next_action": "提交后可离开页面，任务进度会持续保留。",
    }


def source_case_id(url: str) -> str:
    normalized = normalize_source_url(url)
    match = DOUYIN_VIDEO_ID_RE.search(normalized)
    if match is None:
        raise ValueError("full video URL required")
    return match.group(1)


def _find_case_path(settings: Settings, case_id: str) -> tuple[Path, dict[str, Any] | None]:
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


def get_case_detail(settings: Settings, case_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"\d{10,24}", case_id):
        raise CanonicalOperationError(
            "CASE_NOT_FOUND", "没有找到这个案例。", "请返回案例库后重新选择。"
        )
    case_path, attempt = _find_case_path(settings, case_id)
    case = _read_json(case_path)
    projection = _project_case(
        case_path,
        attempt_id=str(attempt.get("attempt_id")) if attempt else None,
    ).to_dict()
    understanding = ((case.get("storyboard") or {}).get("video_understanding") or {})
    metadata = _case_metadata(case)
    sequence = [
        _safe_chinese_text(item.get("description"), max_length=260)
        for item in (understanding.get("structure_sequence") or [])
        if isinstance(item, dict)
    ]
    sequence = [value for value in sequence if value]
    shots: list[dict[str, Any]] = []
    for index, shot in enumerate((case.get("storyboard") or {}).get("shots") or [], start=1):
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
    return {
        **projection,
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
                _safe_chinese_text(understanding.get("audio_visual_strategy"), max_length=420),
                _safe_chinese_text(understanding.get("audio_role"), max_length=320),
                _safe_chinese_text(understanding.get("visual_scene_role"), max_length=320),
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
            "can_review": lifecycle.get("status") == "review_required",
            "approved": lifecycle.get("status") == "approved" and lifecycle.get("approved") is True,
            "attempt_id": str(attempt.get("attempt_id")) if attempt else None,
        },
        "media_rights": {
            "production_authorized": False,
            "message": "批准入库不代表原视频素材可以用于客户生产。",
        },
    }


def case_media_path(settings: Settings, case_id: str) -> Path:
    case_path, _ = _find_case_path(settings, case_id)
    case = _read_json(case_path)
    video = Path(str((((case.get("source_evidence") or {}).get("video") or {}).get("path")) or ""))
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


def _governance_companion(settings: Settings, case_path: Path) -> dict[str, Any]:
    case = _read_json(case_path)
    receipt = case_path.parent / "approval_receipt.json"
    policy = settings.pipeline_root / "data" / "case_governance" / "case_source_governance_policy_v1.json"
    source_path = Path(str((((case.get("source_evidence") or {}).get("video") or {}).get("path")) or ""))
    source_url = str((case.get("identity") or {}).get("source_url") or "")
    return {
        "schema_version": "case-source-governance-companion-v1.0",
        "builder_version": "internal-console-case-approval-gateway@1.0",
        "companion_id": f"case_source_governance_companion_v1::{case['case_id']}",
        "case_id": case["case_id"],
        "canonical_case_status": "approved",
        "case_ref": {"artifact_type": "approved_case", "path": str(case_path), "sha256": _sha256(case_path), "source_artifact_modified": False},
        "case_approval_receipt_ref": {"artifact_type": "case_approval_receipt", "path": str(receipt), "sha256": _sha256(receipt), "source_artifact_modified": False},
        "source_provenance": {
            "status": "traceable",
            "traceable": bool(source_url and source_path.is_file()),
            "platform": "douyin",
            "source_url": source_url,
            "source_url_present": bool(source_url),
            "local_source_path": str(source_path),
            "local_source_exists": source_path.is_file(),
            "local_source_sha256": _sha256(source_path) if source_path.is_file() else None,
            "recorded_source_sha256": None,
            "recorded_sha_matches": None,
            "semantics": "identity_and_evidence_lineage_not_reuse_permission",
        },
        "research_ingestion_eligibility": "eligible_for_internal_research",
        "research_ingestion_basis": "explicit_human_governance_decision",
        "media_reuse_rights": "not_established",
        "production_footage_pool_eligible": False,
        "privacy_basis": "embedded_privacy_gate_library_safe",
        "legacy_source_rights_field_observation": {"present": False, "status": None, "used_as_current_governance_authority": False},
        "governance_policy_version": "V1.0",
        "governance_policy_ref": {"artifact_type": "case_source_governance_policy_v1", "path": str(policy), "sha256": _sha256(policy), "source_artifact_modified": False},
        "case_approval_changed_media_reuse_rights": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def approve_case_candidate(
    settings: Settings,
    case_id: str,
    *,
    reviewer: str,
    note: str,
) -> dict[str, Any]:
    candidate = _latest_candidate(settings, case_id)
    if candidate is None:
        canonical = settings.pipeline_root / "data" / "cases" / case_id / "case_v1.json"
        if canonical.is_file() and (_read_json(canonical).get("lifecycle") or {}).get("status") == "approved":
            raise CanonicalOperationError(
                "CASE_ALREADY_APPROVED", "这个案例已经入库。", "请返回案例库查看。"
            )
        raise CanonicalOperationError(
            "CASE_REVIEW_NOT_READY", "案例还没有可审核的分析结果。", "请等待分析完成后重试。"
        )
    candidate_path, state = candidate
    canonical_dir = settings.pipeline_root / "data" / "cases" / case_id
    canonical_path = canonical_dir / "case_v1.json"
    if canonical_path.is_file():
        current = _read_json(canonical_path)
        if (current.get("lifecycle") or {}).get("status") == "approved":
            raise CanonicalOperationError(
                "APPROVED_CASE_IMMUTABLE",
                "已入库案例不能被重新分析结果覆盖。",
                "保留当前已入库版本；如需版本升级，请建立单独的 Case revision contract。",
            )
        backup = candidate_path.parents[2] / "superseded_canonical"
        if not backup.exists():
            shutil.copytree(canonical_dir, backup)
        shutil.rmtree(canonical_dir)
    temporary_dir = canonical_dir.parent / f".{case_id}.{uuid.uuid4().hex}.tmp"
    shutil.copytree(candidate_path.parent, temporary_dir)
    os.replace(temporary_dir, canonical_dir)
    command = [
        settings.pipeline_python_executable or settings.python_executable,
        str(settings.pipeline_root / "scripts" / "approve_case_v1.py"),
        "--case",
        str(canonical_path),
        "--reviewer",
        reviewer,
        "--note",
        note,
    ]
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
    if result.returncode != 0:
        raise CanonicalOperationError(
            "CASE_APPROVAL_BLOCKED",
            "案例未通过入库校验。",
            "请根据分析与来源边界修正后重新审核。",
        )
    companion = _governance_companion(settings, canonical_path)
    if companion["source_provenance"]["traceable"] is not True:
        raise CanonicalOperationError(
            "CASE_SOURCE_GOVERNANCE_BLOCKED",
            "案例来源无法追溯，不能完成入库。",
            "请恢复来源文件与视频链接后重试。",
        )
    companion_path = (
        settings.pipeline_root
        / "data"
        / "case_governance"
        / "cases"
        / case_id
        / "case_source_governance_companion_v1.json"
    )
    _write_atomic(companion_path, companion)
    fingerprint_result = subprocess.run(
        [
            settings.pipeline_python_executable or settings.python_executable,
            str(settings.pipeline_root / "scripts" / "build_case_fingerprint_v1.py"),
            "--case",
            str(canonical_path),
        ],
        cwd=settings.repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    state["status"] = "approved"
    state["approved_case_path"] = str(canonical_path)
    state["governance_companion_path"] = str(companion_path)
    state["fingerprint_status"] = "completed" if fingerprint_result.returncode == 0 else "retry_required"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state_path = candidate_path.parents[2] / "case_analysis_attempt_v1.json"
    _write_atomic(state_path, state)
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
            "CASE_REVIEW_NOT_READY", "案例还没有可审核的分析结果。", "请等待分析完成后重试。"
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
    _write_atomic(candidate_path.parents[2] / "case_analysis_attempt_v1.json", state)
    return receipt
