from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from operation_lock_v1 import OperationLockTimeout, operation_lock
from speech_evidence_v1 import (
    classify_transcription_speech_evidence,
    require_audio_speech_evidence,
)


SCHEMA_VERSION = "storage-cleanup-receipt-v1.0"
FAILED_RETENTION = timedelta(hours=24)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class StorageCleanupError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageCleanupError(
            "CLEANUP_ARTIFACT_INVALID", f"Cannot read cleanup artifact: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise StorageCleanupError(
            "CLEANUP_ARTIFACT_INVALID", f"Expected JSON object: {path}"
        )
    return value


def write_atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _json_valid(path: Path, validator: Callable[[dict[str, Any]], bool]) -> bool:
    try:
        return path.is_file() and validator(read_json(path))
    except (StorageCleanupError, OSError, TypeError, ValueError):
        return False


def _artifact_path(state: dict[str, Any], name: str) -> Path:
    value = (state.get("artifacts") or {}).get(name)
    return Path(str(value or "")).expanduser()


def _speech_evidence_valid(state: dict[str, Any], case_id: str) -> bool:
    """Validate durable raw/Audio V1 evidence through the canonical classifier."""

    try:
        raw = read_json(_artifact_path(state, "transcript_segments"))
        audio = read_json(_artifact_path(state, "audio_v1"))
        segments = raw.get("segments")
        discarded_segments = raw.get("discarded_segments")
        duration = raw.get("duration")
        if not isinstance(segments, list) or not isinstance(discarded_segments, list):
            return False
        if (
            not isinstance(raw.get("source_file"), str)
            or not raw["source_file"].strip()
        ):
            return False
        if not isinstance(raw.get("model"), str) or not raw["model"].strip():
            return False
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or float(duration) <= 0
        ):
            return False
        audio_segments = audio.get("segments")
        audio_words = audio.get("words")
        audio_validation = audio.get("validation")
        if (
            audio.get("case_id") != case_id
            or not isinstance(audio_segments, list)
            or not isinstance(audio_words, list)
            or not isinstance(audio_validation, dict)
            or audio_validation.get("passed") is not True
        ):
            return False

        raw_status = classify_transcription_speech_evidence(raw)
        audio_status = require_audio_speech_evidence(audio)
        return (
            audio.get("speech_evidence_status") == audio_status
            and raw_status == audio_status
        )
    except (RuntimeError, StorageCleanupError, OSError, TypeError, ValueError):
        return False


def validate_success_cleanup_eligibility(attempt_root: Path) -> dict[str, Any]:
    """Fail closed unless every successful-analysis artifact is durable."""

    attempt_root = attempt_root.resolve()
    state_path = attempt_root / "case_analysis_attempt_v1.json"
    state = read_json(state_path)
    case_id = str(state.get("case_id") or "")
    if state.get("status") != "awaiting_review":
        raise StorageCleanupError(
            "CLEANUP_NOT_ELIGIBLE",
            "Successful cleanup requires durable awaiting_review attempt state.",
        )

    checks = {
        "source_acquisition": _json_valid(
            attempt_root / "source_acquisition_v1.json",
            lambda value: value.get("case_id") == case_id
            and str(value.get("stable_video_id") or value.get("case_id") or "")
            == case_id
            and bool(value.get("source_url"))
            and str(value.get("platform") or "").lower() == "douyin"
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(value.get("source_video_sha256") or "").lower(),
            )
            is not None
            and Path(str(value.get("metadata") or "")).is_file(),
        ),
        "speech_evidence": _speech_evidence_valid(state, case_id),
        "visual_manifest": _json_valid(
            _artifact_path(state, "visual_manifest"),
            lambda value: value.get("case_id") == case_id
            and bool(value.get("frames")),
        ),
        "visual_timeline": _json_valid(
            _artifact_path(state, "visual_v1"),
            lambda value: value.get("case_id") == case_id
            and value.get("coverage", {}).get("coverage_label")
            == "candidate_complete",
        ),
        "privacy_projection": _json_valid(
            _artifact_path(state, "privacy_projection_v1"),
            lambda value: value.get("case_id") == case_id
            and bool(value.get("privacy_policy_version") or value.get("policy_version")),
        ),
        "narration_review": _json_valid(
            _artifact_path(state, "narration_review_v1"),
            lambda value: value.get("case_id") == case_id
            and value.get("validation", {}).get("passed") is True
            and value.get("manual_review", {}).get("required") is False,
        ),
        "shot_boundaries": _json_valid(
            _artifact_path(state, "shot_boundaries_v1"),
            lambda value: value.get("case_id") == case_id
            and value.get("validation", {}).get("passed") is True,
        ),
        "storyboard": _json_valid(
            _artifact_path(state, "reverse_storyboard_v1"),
            lambda value: value.get("case_id") == case_id
            and value.get("validation", {}).get("passed") is True,
        ),
        "case_candidate": _json_valid(
            _artifact_path(state, "case_candidate_v1"),
            lambda value: value.get("case_id") == case_id
            and value.get("lifecycle", {}).get("status") == "review_required"
            and value.get("validation", {}).get("passed") is True,
        ),
    }
    missing = [name for name, valid in checks.items() if not valid]
    if missing:
        raise StorageCleanupError(
            "CLEANUP_EVIDENCE_NOT_DURABLE",
            "Successful cleanup evidence is incomplete: " + ", ".join(missing),
        )
    return state


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _transient_targets(
    attempt_root: Path,
    downloader_root: Path,
) -> tuple[list[tuple[str, Path]], list[str]]:
    state = read_json(attempt_root / "case_analysis_attempt_v1.json")
    case_id = str(state.get("case_id") or "")
    acquisition_path = attempt_root / "source_acquisition_v1.json"
    acquisition = read_json(acquisition_path) if acquisition_path.is_file() else {}
    allowed_downloads = (downloader_root / "Downloaded").resolve()
    targets: list[tuple[str, Path]] = []
    unsafe: list[str] = []

    for category, key in (
        ("source_video", "video"),
        ("source_music", "music"),
        ("source_cover_thumbnail", "cover"),
    ):
        raw = str(acquisition.get(key) or "").strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not _is_within(path, allowed_downloads):
            unsafe.append(f"{category}:{path}")
            continue
        targets.append((category, path.resolve()))

    raw_video = str(acquisition.get("video") or "").strip()
    if raw_video:
        video_path = Path(raw_video).expanduser()
        if _is_within(video_path, allowed_downloads):
            for pattern, category in (
                (f"*{case_id}*_music.*", "source_music"),
                (f"*{case_id}*_cover.*", "source_cover_thumbnail"),
                (f"*{case_id}*thumbnail*", "source_cover_thumbnail"),
            ):
                for companion in video_path.parent.glob(pattern):
                    if companion.is_file() and _is_within(
                        companion, allowed_downloads
                    ):
                        targets.append((category, companion.resolve()))

    visual_root = attempt_root / "evidence" / "visual" / case_id
    original_frames_root = visual_root / "frames"
    for path in original_frames_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            if _is_within(path, original_frames_root):
                targets.append(("original_frames", path.resolve()))
            else:
                unsafe.append(f"original_frames:{path}")
    proxy_frames_root = visual_root / "visual_v1" / "proxies"
    for path in proxy_frames_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            if _is_within(path, proxy_frames_root):
                targets.append(("qwen_proxy_frames", path.resolve()))
            else:
                unsafe.append(f"qwen_proxy_frames:{path}")

    unique: dict[Path, str] = {}
    for category, path in targets:
        unique.setdefault(path, category)
    return [(category, path) for path, category in unique.items()], unsafe


def _prune_empty_directories(root: Path) -> None:
    if not root.is_dir():
        return
    for path in sorted(
        (item for item in root.rglob("*") if item.is_dir() and not item.is_symlink()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        try:
            path.rmdir()
        except OSError:
            pass
    try:
        root.rmdir()
    except OSError:
        pass


def _record_cleanup_state(
    state_path: Path,
    receipt_path: Path,
    receipt: dict[str, Any],
) -> None:
    state = read_json(state_path)
    state["cleanup_status"] = receipt["cleanup_status"]
    state["storage_cleanup"] = {
        "status": receipt["cleanup_status"],
        "receipt": str(receipt_path),
        "updated_at": receipt["cleanup_at"],
        "trigger": receipt["trigger"],
    }
    state.setdefault("artifacts", {})["storage_cleanup_receipt_v1"] = str(
        receipt_path
    )
    write_atomic_json(state_path, state)


def mark_cleanup_retry_required(
    attempt_root: Path,
    *,
    trigger: str,
    error: str,
    now: datetime | None = None,
) -> None:
    state_path = attempt_root / "case_analysis_attempt_v1.json"
    state = read_json(state_path)
    cleanup_at = iso_utc(now)
    acquisition_path = attempt_root / "source_acquisition_v1.json"
    try:
        acquisition = read_json(acquisition_path) if acquisition_path.is_file() else {}
    except StorageCleanupError:
        acquisition = {}
    receipt_path = attempt_root / "storage_cleanup_receipt_v1.json"
    try:
        previous = read_json(receipt_path) if receipt_path.is_file() else {}
    except StorageCleanupError:
        previous = {}
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "case_id": str(state.get("case_id") or attempt_root.parent.name),
        "attempt_id": str(state.get("attempt_id") or attempt_root.name),
        "trigger": trigger,
        "cleanup_at": cleanup_at,
        "cleanup_status": "retry_required",
        "deleted_file_count": int(previous.get("deleted_file_count") or 0),
        "deleted_bytes": int(previous.get("deleted_bytes") or 0),
        "deleted_categories": sorted(previous.get("deleted_categories") or []),
        "source_url_retained": bool(
            acquisition.get("source_url")
            or (state.get("source") or {}).get("canonical_url")
        ),
        "source_media_sha256_retained": bool(
            acquisition.get("source_video_sha256")
        ),
        "structured_evidence_retained": True,
        "failed_targets": [error],
    }
    write_atomic_json(receipt_path, receipt)
    state["cleanup_status"] = "retry_required"
    state["storage_cleanup"] = {
        "status": "retry_required",
        "receipt": str(receipt_path),
        "updated_at": cleanup_at,
        "trigger": trigger,
        "error": error,
    }
    state.setdefault("artifacts", {})["storage_cleanup_receipt_v1"] = str(
        receipt_path
    )
    write_atomic_json(state_path, state)


def _cleanup_attempt_transient_media_unlocked(
    attempt_root: Path,
    downloader_root: Path,
    *,
    trigger: str,
    require_success_evidence: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    attempt_root = attempt_root.resolve()
    downloader_root = downloader_root.resolve()
    state_path = attempt_root / "case_analysis_attempt_v1.json"
    if require_success_evidence:
        state = validate_success_cleanup_eligibility(attempt_root)
    else:
        state = read_json(state_path)
        if state.get("status") in {"queued", "running"}:
            raise StorageCleanupError(
                "CLEANUP_ACTIVE_ATTEMPT",
                "Queued or running attempts must never be cleaned.",
            )

    targets, unsafe_targets = _transient_targets(attempt_root, downloader_root)
    deleted_count = 0
    deleted_bytes = 0
    deleted_categories: set[str] = set()
    failures = list(unsafe_targets)
    for category, path in targets:
        if not path.exists():
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError as exc:
            failures.append(f"{category}:{path}:{exc}")
            continue
        deleted_count += 1
        deleted_bytes += size
        deleted_categories.add(category)

    case_id = str(state.get("case_id") or "")
    visual_root = attempt_root / "evidence" / "visual" / case_id
    _prune_empty_directories(visual_root / "frames")
    _prune_empty_directories(visual_root / "visual_v1" / "proxies")

    acquisition_path = attempt_root / "source_acquisition_v1.json"
    acquisition = read_json(acquisition_path) if acquisition_path.is_file() else {}
    source_url_retained = bool(
        acquisition.get("source_url")
        or (state.get("source") or {}).get("canonical_url")
    )
    source_sha_retained = bool(acquisition.get("source_video_sha256"))

    receipt_path = attempt_root / "storage_cleanup_receipt_v1.json"
    previous = read_json(receipt_path) if receipt_path.is_file() else {}
    categories = set(previous.get("deleted_categories") or [])
    categories.update(deleted_categories)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case_id,
        "attempt_id": str(state.get("attempt_id") or attempt_root.name),
        "trigger": trigger,
        "cleanup_at": iso_utc(now),
        "cleanup_status": "retry_required" if failures else "completed",
        "deleted_file_count": int(previous.get("deleted_file_count") or 0)
        + deleted_count,
        "deleted_bytes": int(previous.get("deleted_bytes") or 0) + deleted_bytes,
        "deleted_categories": sorted(categories),
        "source_url_retained": source_url_retained,
        "source_media_sha256_retained": source_sha_retained,
        "structured_evidence_retained": True,
        "failed_targets": failures,
    }
    write_atomic_json(receipt_path, receipt)
    _record_cleanup_state(state_path, receipt_path, receipt)
    return receipt


def cleanup_attempt_transient_media(
    attempt_root: Path,
    downloader_root: Path,
    *,
    trigger: str,
    require_success_evidence: bool,
    now: datetime | None = None,
    lock_timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    attempt_root = attempt_root.resolve()
    state = read_json(attempt_root / "case_analysis_attempt_v1.json")
    key = (
        f"storage_cleanup:{state.get('case_id') or attempt_root.parent.name}:"
        f"{state.get('attempt_id') or attempt_root.name}"
    )
    pipeline_root = attempt_root.parents[3]
    with operation_lock(
        pipeline_root,
        key,
        timeout_seconds=lock_timeout_seconds,
    ):
        return _cleanup_attempt_transient_media_unlocked(
            attempt_root,
            downloader_root,
            trigger=trigger,
            require_success_evidence=require_success_evidence,
            now=now,
        )


def cleanup_successful_attempt(
    attempt_root: Path,
    downloader_root: Path,
    *,
    trigger: str = "analysis_awaiting_review",
    now: datetime | None = None,
    lock_timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    return cleanup_attempt_transient_media(
        attempt_root,
        downloader_root,
        trigger=trigger,
        require_success_evidence=True,
        now=now,
        lock_timeout_seconds=lock_timeout_seconds,
    )


def cleanup_rejected_attempt(
    attempt_root: Path,
    downloader_root: Path,
    *,
    now: datetime | None = None,
    lock_timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    state = read_json(attempt_root / "case_analysis_attempt_v1.json")
    if state.get("status") != "rejected":
        raise StorageCleanupError(
            "CLEANUP_NOT_REJECTED", "Reject cleanup requires rejected attempt state."
        )
    return cleanup_attempt_transient_media(
        attempt_root,
        downloader_root,
        trigger="human_reject",
        require_success_evidence=False,
        now=now,
        lock_timeout_seconds=lock_timeout_seconds,
    )


def run_storage_maintenance(
    pipeline_root: Path,
    downloader_root: Path,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    current = (now or utc_now()).astimezone(timezone.utc)
    attempts_root = pipeline_root.resolve() / "data" / "case_analysis_attempts"
    results: list[dict[str, Any]] = []
    for state_path in attempts_root.glob("*/*/case_analysis_attempt_v1.json"):
        try:
            state = read_json(state_path)
            status = str(state.get("status") or "")
            cleanup_status = str(state.get("cleanup_status") or "")
            if cleanup_status == "completed":
                continue
            if status == "awaiting_review":
                results.append(
                    cleanup_successful_attempt(
                        state_path.parent,
                        downloader_root,
                        trigger="hourly_storage_maintenance",
                        now=current,
                        lock_timeout_seconds=0.0,
                    )
                )
            elif status == "rejected":
                results.append(
                    cleanup_attempt_transient_media(
                        state_path.parent,
                        downloader_root,
                        trigger="hourly_storage_maintenance_rejected",
                        require_success_evidence=False,
                        now=current,
                        lock_timeout_seconds=0.0,
                    )
                )
            elif status == "failed":
                terminal_at = parse_utc(str(state.get("updated_at") or ""))
                if terminal_at is not None and current - terminal_at >= FAILED_RETENTION:
                    results.append(
                        cleanup_attempt_transient_media(
                            state_path.parent,
                            downloader_root,
                            trigger="failed_retention_expired_24h",
                            require_success_evidence=False,
                            now=current,
                            lock_timeout_seconds=0.0,
                        )
                    )
        except OperationLockTimeout:
            continue
        except Exception as exc:
            try:
                mark_cleanup_retry_required(
                    state_path.parent,
                    trigger="hourly_storage_maintenance",
                    error=str(exc),
                    now=current,
                )
            except Exception:
                pass
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean transient Case media without changing Case Authority."
    )
    parser.add_argument("--pipeline-root", required=True)
    parser.add_argument("--downloader-root", required=True)
    parser.add_argument("--maintenance", action="store_true")
    parser.add_argument("--attempt-root")
    parser.add_argument(
        "--trigger",
        choices=["analysis_awaiting_review", "human_reject"],
        default="analysis_awaiting_review",
    )
    args = parser.parse_args()

    pipeline_root = Path(args.pipeline_root).expanduser().resolve()
    downloader_root = Path(args.downloader_root).expanduser().resolve()
    if args.maintenance:
        results = run_storage_maintenance(pipeline_root, downloader_root)
        print(json.dumps({"cleaned": len(results)}, ensure_ascii=False))
        return
    if not args.attempt_root:
        parser.error("--attempt-root is required without --maintenance")
    attempt_root = Path(args.attempt_root).expanduser().resolve()
    if args.trigger == "human_reject":
        receipt = cleanup_rejected_attempt(attempt_root, downloader_root)
    else:
        receipt = cleanup_successful_attempt(attempt_root, downloader_root)
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
