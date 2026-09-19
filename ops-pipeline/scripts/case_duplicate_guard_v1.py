from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ACTIVE_DUPLICATE_STATUSES = {
    "queued",
    "running",
    "awaiting_review",
    "approved",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def find_media_identity_duplicate(
    pipeline_root: Path,
    *,
    current_case_id: str,
    current_attempt_id: str,
    media_sha256: str,
) -> dict[str, Any] | None:
    """
    Hard duplicate guard for exact media identity.

    This function intentionally does NOT perform semantic / visual similarity
    matching. Only exact SHA-256 identity is allowed to hard-block a Case.

    Priority:
    1. Existing approved Case governance records.
    2. Existing active / review-ready Case analysis attempts.

    Failed/rejected attempts do not create a cross-source hard block because
    they never became approved/review-ready research authority.
    """

    expected_sha = str(media_sha256 or "").strip().lower()
    if not expected_sha:
        return None

    # 1. Approved Case Library.
    governance_root = (
        pipeline_root
        / "data"
        / "case_governance"
        / "cases"
    )

    if governance_root.exists():
        for companion_path in governance_root.glob(
            "*/case_source_governance_companion_v1.json"
        ):
            companion = _read_json(companion_path)
            if not companion:
                continue

            case_id = str(
                companion.get("case_id")
                or companion_path.parent.name
            )

            if case_id == current_case_id:
                continue

            source = (
                companion.get("source_provenance")
                if isinstance(companion.get("source_provenance"), dict)
                else {}
            )

            recorded_sha = str(
                source.get("recorded_source_sha256")
                or source.get("local_source_sha256")
                or ""
            ).lower()

            if (
                recorded_sha == expected_sha
                and companion.get("canonical_case_status") == "approved"
            ):
                return {
                    "kind": "media_identity",
                    "existing_case_id": case_id,
                    "existing_status": "approved",
                    "existing_attempt_id": None,
                    "matched_sha256": expected_sha,
                    "authority": "approved_case_governance",
                }

    # 2. Current / review-ready Case analysis attempts.
    attempts_root = (
        pipeline_root
        / "data"
        / "case_analysis_attempts"
    )

    if not attempts_root.exists():
        return None

    for acquisition_path in attempts_root.glob(
        "*/*/source_acquisition_v1.json"
    ):
        attempt_id = acquisition_path.parent.name
        case_id = acquisition_path.parent.parent.name

        if (
            case_id == current_case_id
            and attempt_id == current_attempt_id
        ):
            continue

        # Same canonical source identity belongs to the same Case lineage and
        # is handled by source-identity / reanalysis rules, not media identity.
        if case_id == current_case_id:
            continue

        acquisition = _read_json(acquisition_path)
        if not acquisition:
            continue

        recorded_sha = str(
            acquisition.get("source_video_sha256") or ""
        ).lower()

        if recorded_sha != expected_sha:
            continue

        state_path = (
            acquisition_path.parent
            / "case_analysis_attempt_v1.json"
        )
        state = _read_json(state_path) or {}

        status = str(state.get("status") or "").lower()
        if status not in ACTIVE_DUPLICATE_STATUSES:
            continue

        return {
            "kind": "media_identity",
            "existing_case_id": case_id,
            "existing_status": status,
            "existing_attempt_id": str(
                state.get("attempt_id") or attempt_id
            ),
            "matched_sha256": expected_sha,
            "authority": "case_analysis_source_acquisition",
        }

    return None
