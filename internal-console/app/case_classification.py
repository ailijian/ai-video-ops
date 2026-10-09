"""Evidence-derived intake labels, separate from Case and compatibility approval."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from pathlib import Path

from .canonical_gateway import (
    CanonicalOperationError, _find_case_path, _read_json, _sha256, _write_atomic,
)
from .config import Settings
from .path_safety import resolve_within

# Same formal options as the existing industry selector; custom labels remain human-only.
CASE_INDUSTRIES = ("餐饮", "本地生活", "零售", "烘焙甜品", "美容", "教培", "服装", "饰品", "通用行业")
PROFILE_LABELS = {"mix": "素材混剪", "news": "新闻体", "hybrid": "混合型", "uncertain": "暂不确定"}
INDUSTRY_CUES = {
    "餐饮": ("餐厅", "厨房", "用餐", "菜品", "炒菜", "烹饪"),
    "烘焙甜品": ("蛋糕", "面包", "烘焙", "甜品", "奶油"),
    "美容": ("美容", "护肤", "美甲", "美容院", "美发"),
    "教培": ("课堂", "教学", "培训", "课程", "老师"),
    "服装": ("服装", "试衣", "穿搭", "衣架", "衣服"),
    "饰品": ("首饰", "项链", "耳环", "戒指", "手镯"),
    "零售": ("货架", "收银", "超市", "零售", "商品陈列"),
    "本地生活": ("维修", "家政", "洗车", "保洁", "上门服务"),
}
AUTHORITY = {
    "operator_labels_only": True, "case_approval": False,
    "profile_compatibility_approval": False, "media_rights_granted": False,
    "customer_facts_created": False, "source_evidence_modified": False,
}


def _context(settings: Settings, case_id: str):
    case_path, attempt = _find_case_path(settings, case_id)
    case = _read_json(case_path)
    attempt_id = str((attempt or {}).get("attempt_id") or (case.get("analysis_lineage") or {}).get("attempt_id") or "")
    path = None
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", attempt_id):
        path = resolve_within(settings.pipeline_root / "data", "case_analysis_attempts", case_id, attempt_id, "case_classification_review_v1.json")
    return case_path, case, attempt_id, path


def _narration_from_bound_storyboard(settings: Settings, case: dict) -> list:
    ref = ((case.get("storyboard") or {}).get("artifact") or {})
    if not ref.get("path") or not ref.get("sha256"):
        return []
    path = Path(ref["path"])
    if not path.is_absolute():
        path = settings.pipeline_root / path
    path = path.resolve()
    if not path.is_relative_to(settings.pipeline_root.resolve()) or not path.is_file() or _sha256(path) != ref["sha256"]:
        return []
    board = _read_json(path)
    if board.get("case_id") != case.get("case_id") or not (board.get("validation") or {}).get("passed"):
        return []
    return board.get("narration_track") or []


def recommend_classification(case: dict, digest: str, narration: list | None = None) -> dict:
    """Read only already projected evidence. No model, title heuristic, or fact transfer."""
    shots = (case.get("storyboard") or {}).get("shots") or []
    narration = narration if narration is not None else ((case.get("storyboard") or {}).get("narration_track") or [])
    duration = (case.get("identity") or {}).get("duration_seconds")
    duration = float(duration) if isinstance(duration, (int, float)) and math.isfinite(duration) else 0
    profile = "uncertain"
    profile_reason = "暂时无法准确判断，请选择。"
    evidence_refs = []
    # Overlapping narration intervals must not manufacture speech dominance.
    spans = []
    for segment in narration:
        start, end = segment.get("start"), segment.get("end")
        if (isinstance(start, (int, float)) and isinstance(end, (int, float))
                and math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration):
            spans.append((start, end))
    covered = 0.0
    cursor = 0.0
    for start, end in sorted(spans):
        covered += max(0, end - max(cursor, start))
        cursor = max(cursor, end)
    independent = sum(
        (s.get("interpretation") or {}).get("audio_to_visual_text") == "independent"
        and bool((s.get("evidence") or {}).get("onscreen_text_safe_verbatim")
                 or (s.get("evidence") or {}).get("onscreen_text_sequence"))
        for s in shots
    )
    validation = case.get("validation") or {}
    speech_status = (case.get("audio_evidence") or {}).get("speech_evidence_status")
    usable = validation.get("passed") is True and validation.get("privacy_gate_passed") is True and bool(shots)
    if usable and duration > 0 and (spans or speech_status == "not_detected"):
        speech_dominant = covered / duration >= 0.5
        text_dominant = independent / len(shots) >= 0.5
        if speech_dominant and text_dominant:
            profile = "hybrid"
            profile_reason = "连续口播和独立的画面文字都承担了主要表达，因此更接近混合型。"
        elif speech_dominant and len(shots) >= 2:
            profile = "mix"
            profile_reason = "视频主要通过连续口播表达内容，多个画面用于辅助说明，因此更接近素材混剪。"
        elif text_dominant:
            profile = "news"
            profile_reason = "主要信息通过多个独立的画面文字段落呈现，口播占比较少，因此更接近新闻体。"
        evidence_refs = [str(s.get("shot_id") or index + 1) for index, s in enumerate(shots)]
    # Industry is conservative: at least two distinct cues in observable scenes.
    # A title, claim, or operator's prior selection cannot establish an AI suggestion.
    scenes = " ".join(
        str(v) for s in shots for v in ((s.get("evidence") or {}).get("observable_scene_safe_verbatim") or [])
    )
    scores = {label: sum(cue in scenes for cue in cues) for label, cues in INDUSTRY_CUES.items()} if usable else {}
    ordered = sorted(scores, key=scores.get, reverse=True)
    industry = None
    if ordered and scores[ordered[0]] >= 2 and (len(ordered) == 1 or scores[ordered[0]] > scores[ordered[1]]):
        industry = ordered[0]
    return {
        "industry": industry, "observed_source_profile": profile,
        "industry_reason": f"已分析的画面中出现多项{industry}场景线索，请对照视频检查。" if industry else "暂时无法准确判断，请选择。",
        "profile_reason": profile_reason,
        "needs_human_judgment": industry is None or profile == "uncertain",
        "method": "derived_from_existing_projected_evidence_v1",
        "case_sha256": digest, "shot_refs": evidence_refs,
        "evidence_lineage": case.get("provenance") or {},
        "remote_model_called": False,
    }


def classification_state(settings: Settings, case_id: str) -> dict:
    case_path, case, attempt_id, path = _context(settings, case_id)
    digest = _sha256(case_path)
    suggestion = recommend_classification(case, digest, _narration_from_bound_storyboard(settings, case))
    record = _read_json(path) if path and path.is_file() else None
    if record and not (
        record.get("schema_version") == "case-classification-review-v1.0"
        and record.get("case_id") == case_id and record.get("attempt_id") == attempt_id
        and record.get("authority") == AUTHORITY
        and record.get("original_suggestion", {}).get("case_sha256")
        and record.get("human", {}).get("profile") in PROFILE_LABELS
        and record.get("human", {}).get("confirmed_by_user_id")
    ):
        raise CanonicalOperationError("CASE_CLASSIFICATION_INVALID", "分类确认记录无法核对。", "请联系管理员，不要改写审核记录。")
    approved = (case.get("lifecycle") or {}).get("approved") is True
    stale = bool(record and not approved and record.get("confirmed_case_sha256") != digest)
    return {
        "case_id": case_id, "attempt_id": attempt_id,
        "suggestion": record["original_suggestion"] if record else suggestion,
        "human": record.get("human") if record else None,
        "status": "confirmed" if record and not stale else "needs_confirmation",
        "stale": stale, "candidate_sha256": digest,
        "confirmation_sha256": _sha256(path) if record else None,
        "can_confirm": path is not None and not approved and (case.get("lifecycle") or {}).get("status") == "review_required",
        "authority": AUTHORITY,
    }


def classification_summary(settings: Settings, case_id: str) -> dict:
    state = classification_state(settings, case_id)
    human = state["human"] or {}
    return {"status": state["status"], "industry": human.get("industry"), "profile": human.get("profile"),
            "confirmed_by": {"phone": human["confirmed_by_phone"]} if human else None,
            "confirmed_at": human.get("confirmed_at")}


def confirm_classification(settings: Settings, case_id: str, *, industry: str | None, profile: str,
                           candidate_sha256: str, expected_confirmation_sha256: str | None,
                           actor_user_id: int, actor_phone: str) -> dict:
    state = classification_state(settings, case_id)
    if not state["can_confirm"] or candidate_sha256 != state["candidate_sha256"] or expected_confirmation_sha256 != state["confirmation_sha256"]:
        raise CanonicalOperationError("CASE_CLASSIFICATION_CONFLICT", "分类结果已变化。", "刷新结果后重新确认。")
    industry = industry.strip() if industry else None
    if profile not in PROFILE_LABELS or (industry is not None and (not industry or len(industry) > 30 or industry in {"待分类", "unknown"})):
        raise CanonicalOperationError("CASE_CLASSIFICATION_INVALID", "请选择有效分类或显式保留未确定状态。", "检查行业与视频结构后重新确认。")
    _, _, attempt_id, path = _context(settings, case_id)
    previous = _read_json(path) if path.is_file() else None
    human = {"industry": industry, "profile": profile, "confirmed_by_user_id": actor_user_id,
             "confirmed_by_phone": actor_phone, "confirmed_at": datetime.now(timezone.utc).isoformat()}
    record = {
        "schema_version": "case-classification-review-v1.0", "case_id": case_id, "attempt_id": attempt_id,
        "original_suggestion": state["suggestion"], "confirmed_case_sha256": candidate_sha256,
        "human": human, "previous_human_choices": (previous.get("previous_human_choices", []) + [previous["human"]]) if previous else [],
        "authority": AUTHORITY,
    }
    _write_atomic(path, record)
    return classification_state(settings, case_id)
