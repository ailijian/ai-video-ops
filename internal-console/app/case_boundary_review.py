"""Human boundary decisions for a paused Case analysis attempt."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .database import transaction
from .task_service import get_task


class BoundaryReviewError(ValueError):
    pass


def _paths(settings: Settings, task: dict[str, Any]) -> tuple[Path, Path, Path]:
    case_id = str(task.get("subject_ref") or "")
    task_id = str(task.get("task_id") or "")
    if not re.fullmatch(r"\d{10,24}", case_id) or not re.fullmatch(
        rf"case-{case_id}-[a-f0-9]{{12}}", task_id
    ):
        raise BoundaryReviewError("案例分析任务标识无效。")
    root = settings.pipeline_root / "data" / "case_analysis_attempts" / case_id / task_id
    return (
        root / "case_analysis_attempt_v1.json",
        root / "evidence" / "shots" / "shot_boundaries_v1_1.json",
        root / "evidence" / "shots",
    )


def pending_boundary_review(settings: Settings, task: dict[str, Any]) -> dict[str, Any] | None:
    if task.get("task_type") != "case_analysis" or task.get("status") != "failed":
        return None
    state_path, shots_path, _ = _paths(settings, task)
    if not state_path.is_file() or not shots_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        shots_bytes = shots_path.read_bytes()
        shots = json.loads(shots_bytes)
    except (OSError, json.JSONDecodeError):
        return None
    acquisition = state_path.parent / "source_acquisition_v1.json"
    if not acquisition.is_file():
        return None
    try:
        source = json.loads(acquisition.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    video = Path(str(source.get("video") or ""))
    if not video.is_file() or not re.fullmatch(r"[a-f0-9]{64}", str(source.get("source_video_sha256") or "")):
        return None
    try:
        with video.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source["source_video_sha256"]:
                return None
    except OSError:
        return None
    if (
        state.get("status") != "failed"
        or state.get("attempt_id") != task["task_id"]
        or state.get("case_id") != task["subject_ref"]
        or shots.get("case_id") != task["subject_ref"]
        or shots.get("validation", {}).get("passed") is not True
        or shots.get("manual_review", {}).get("required") is not True
    ):
        return None
    items = shots.get("manual_review", {}).get("items") or []
    if not isinstance(items, list) or not items:
        return None
    pending: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            return None
        frame_id = str(item.get("frame_id") or item.get("boundary_frame_id") or "")
        if not re.fullmatch(r"frame_\d{9}ms\.jpg", frame_id):
            return None
        row = pending.setdefault(frame_id, {"frame_id": frame_id, "issues": []})
        row["issues"].append({
            "type": item.get("type"),
            "start": item.get("start", item.get("timestamp_seconds")),
            "end": item.get("end"),
            "duration": item.get("duration"),
            "reason": str(item.get("reason") or "")[:300],
        })
    return {
        "shot_sha256": hashlib.sha256(shots_bytes).hexdigest(),
        "items": list(pending.values()),
        "source_url": state.get("source", {}).get("canonical_url"),
    }


def submit_boundary_review(
    settings: Settings,
    task: dict[str, Any],
    *,
    shot_sha256: str,
    decisions: list[dict[str, str]],
    user_id: int,
    phone: str,
) -> dict[str, Any]:
    pending = pending_boundary_review(settings, task)
    if pending is None:
        raise BoundaryReviewError("当前任务没有可确认的分镜，或原视频已经清理。")
    if pending["shot_sha256"] != shot_sha256:
        raise BoundaryReviewError("分镜结果已变化，请刷新任务后重新确认。")
    expected = {item["frame_id"] for item in pending["items"]}
    supplied = {item.get("frame_id") for item in decisions}
    if len(decisions) != len(expected) or supplied != expected or any(
        item.get("action") not in {"keep", "reject"} for item in decisions
    ):
        raise BoundaryReviewError("请逐一确认所有待复核的分镜。")
    _, _, review_root = _paths(settings, task)
    previous_files = sorted(review_root.glob("boundary_review_???.json"))
    if len(previous_files) >= 999:
        raise BoundaryReviewError("分镜复核次数过多，请联系管理员。")
    prior_decisions: list[dict[str, str]] = []
    if previous_files:
        try:
            previous = json.loads(previous_files[-1].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundaryReviewError("此前的分镜复核记录无法读取。") from exc
        if previous.get("case_id") != task["subject_ref"] or previous.get("attempt_id") != task["task_id"]:
            raise BoundaryReviewError("此前的分镜复核记录不匹配。")
        prior_decisions = previous.get("decisions") or []
    overlap = expected.intersection({item.get("frame_id") for item in prior_decisions})
    previously_saved = bool(overlap)
    if previously_saved and (
        overlap != expected
        or previous.get("shot_boundaries_sha256") != shot_sha256
        or {item["frame_id"]: item["action"] for item in prior_decisions if item.get("frame_id") in expected}
        != {item["frame_id"]: item["action"] for item in decisions}
    ):
        raise BoundaryReviewError("分镜复核记录存在冲突，请联系管理员。")
    review_path = review_root / f"boundary_review_{len(previous_files) + 1:03d}.json"
    receipt = {
        "schema_version": "case-boundary-review-v1.0",
        "case_id": task["subject_ref"],
        "attempt_id": task["task_id"],
        "shot_boundaries_sha256": shot_sha256,
        "reviewed_by_user_id": user_id,
        "reviewed_by_phone": phone,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "decisions": prior_decisions + [
            {
                "frame_id": item["frame_id"],
                "action": item["action"],
                "reason": "人工对照原视频确认保留分镜" if item["action"] == "keep"
                else "人工对照原视频确认合并分镜",
            }
            for item in decisions
        ],
    }
    # The caller holds the per-task operation lock. Never overwrite a human receipt.
    if not previously_saved:
        with review_path.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
    with transaction(settings.database_path, immediate=True) as connection:
        changed = connection.execute(
            """UPDATE tasks SET status = 'queued', progress = 84,
               stage = '等待继续分析', error_code = NULL, error_message = NULL,
               updated_at = ? WHERE task_id = ? AND status = 'failed'
               AND task_type = 'case_analysis'""",
            (datetime.now(timezone.utc).isoformat(), task["task_id"]),
        )
        if changed.rowcount != 1:
            raise BoundaryReviewError("任务状态已经变化，请刷新页面。")
    return get_task(settings.database_path, task["task_id"])
