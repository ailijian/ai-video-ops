from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from customer_intake_v1 import (
    build_initial_content_capacity_handoff,
)
from production_profile_v1 import (
    validate_registry,
)
from show_customer_status_v1 import (
    AuthorityResolutionError,
    load_content_ledger,
    resolve_batches,
    resolve_capacity,
    resolve_current_persona,
    resolve_speaker_persona,
)

SCHEMA_VERSION = "content-creation-entry-v1.0"
OPERATION_VERSION = "content_creation_entry_v1.py@1.0"

SUPPORTED_PROFILES = {
    "mix",
    "news",
}


class ContentCreationEntryError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ):
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise ContentCreationEntryError(
            "CONTENT_ENTRY_ARTIFACT_INVALID",
            f"Cannot read artifact: {path}",
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise ContentCreationEntryError(
            "CONTENT_ENTRY_ARTIFACT_INVALID",
            f"Artifact must be an object: {path}",
        )

    return value


def evidence_ref(
    pipeline_root: Path,
    path: Path,
) -> str:
    try:
        return path.resolve().relative_to(pipeline_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def load_profile_registry(
    pipeline_root: Path,
) -> tuple[
    Path,
    dict[str, Any],
    dict[str, dict[str, Any]],
]:
    path = (
        pipeline_root
        / "data"
        / "production_profiles"
        / "production_profile_registry_v1.json"
    )

    if not path.is_file():
        raise ContentCreationEntryError(
            "PRODUCTION_PROFILE_REGISTRY_NOT_FOUND",
            ("Production Profile Registry " "is required before content creation."),
        )

    registry = read_json(path)

    try:
        validate_registry(registry)
    except Exception as exc:
        raise ContentCreationEntryError(
            "PRODUCTION_PROFILE_REGISTRY_INVALID",
            str(exc),
        ) from exc

    profiles: dict[
        str,
        dict[str, Any],
    ] = {}

    for profile_id in sorted(SUPPORTED_PROFILES):
        profile = (
            registry.get(
                "profiles",
                {},
            ).get(profile_id)
            or {}
        )

        status = str(profile.get("status") or "unknown")

        available = status == "production_ready"

        profiles[profile_id] = {
            "profile_id": profile_id,
            "status": status,
            "available": available,
            "blocker": (None if available else ("PROFILE_NOT_" "PRODUCTION_READY")),
        }

    return (
        path,
        registry,
        profiles,
    )


def existing_generation_requests(
    pipeline_root: Path,
    business_id: str,
) -> list[Path]:
    root = pipeline_root / "data" / "generation_requests"

    if not root.exists():
        return []

    matches: list[Path] = []

    for path in root.glob("*/generation_request_v1.json"):
        try:
            request = read_json(path)
        except ContentCreationEntryError:
            raise

        recorded_business = str(
            request.get("persona_id") or request.get("business_id") or ""
        )

        if recorded_business == business_id:
            matches.append(path)

    return sorted(matches)


def resolve_capacity_preview(
    *,
    pipeline_root: Path,
    business: dict[str, Any],
    speaker: dict[str, Any],
    requested_quantity: int,
    created_at: str | None,
) -> dict[str, Any]:
    business_id = str(business["persona_id"])

    ledger_path = (
        pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )

    # ---------------------------------------------------------
    # Initial customer:
    # no Content Ledger means no Historical Exposure yet.
    #
    # Before treating it as "new", make sure a generation
    # request does not already exist. This prevents an absent
    # or lost Ledger from silently resetting novelty.
    # ---------------------------------------------------------

    if not ledger_path.is_file():
        historical_requests = existing_generation_requests(
            pipeline_root,
            business_id,
        )

        if historical_requests:
            raise ContentCreationEntryError(
                "CONTENT_HISTORY_WITHOUT_LEDGER",
                (
                    "Generation history exists but "
                    "the canonical Content Ledger "
                    "is missing. Capacity must not "
                    "be reset to an empty history."
                ),
            )

        handoff = build_initial_content_capacity_handoff(
            business_persona_path=(business["path"]),
            speaker_persona_path=(speaker["path"]),
            requested_quantity=(requested_quantity),
            created_at=(created_at),
        )

        capacity = int(handoff["high_quality_capacity"])

        return {
            "mode": ("initial_persona_capacity"),
            "high_quality_novel_capacity": (capacity),
            "capacity_status": (handoff.get("capacity_status")),
            "content_gap_summary": (handoff.get("content_gap_summary") or []),
            "quality_engine": (handoff.get("content_quality_engine")),
            "ledger_entry_count": 0,
            "evidence_paths": [],
            "authority": {
                "empty_history_assumed": (True),
                "existing_generation_history_checked": (True),
                "content_ledger_written": (False),
            },
        }

    # ---------------------------------------------------------
    # Existing customer:
    # capacity MUST come from Current Content Ledger lineage.
    # No fallback to empty history is allowed.
    # ---------------------------------------------------------

    try:
        ledger = load_content_ledger(
            pipeline_root,
            business_id,
        )

        batches = resolve_batches(
            pipeline_root,
            business_id,
            ledger,
            None,
        )

        active_batch = batches["active"]

        capacity = resolve_capacity(
            pipeline_root,
            business,
            speaker,
            ledger,
            active_batch,
        )

    except AuthorityResolutionError as exc:
        raise ContentCreationEntryError(
            exc.code,
            str(exc),
        ) from exc

    return {
        "mode": ("current_ledger_capacity"),
        "high_quality_novel_capacity": (int(capacity["remaining"])),
        "capacity_status": (capacity.get("status")),
        "content_gap_summary": [],
        "quality_engine": None,
        "ledger_entry_count": len(ledger["entries"]),
        "active_batch_ref": (active_batch["request_id"]),
        "evidence_paths": [
            ledger["path"],
            active_batch["path"],
            capacity["path"],
            capacity["source_path"],
        ],
        "authority": {
            "empty_history_assumed": (False),
            "content_ledger_required": (True),
            "content_ledger_written": (False),
        },
    }


def build_content_creation_entry(
    *,
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    profile: str,
    requested_quantity: int,
    created_at: str | None = None,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()

    profile = str(profile or "").strip().lower()

    if profile not in SUPPORTED_PROFILES:
        raise ContentCreationEntryError(
            "UNSUPPORTED_PRODUCTION_PROFILE",
            ("Production profile must " "be mix or news."),
        )

    if (
        not isinstance(
            requested_quantity,
            int,
        )
        or isinstance(
            requested_quantity,
            bool,
        )
        or requested_quantity < 1
        or requested_quantity > 20
    ):
        raise ContentCreationEntryError(
            "INVALID_REQUESTED_QUANTITY",
            ("requested_quantity must " "be an integer from 1 to 20."),
        )

    try:
        business = resolve_current_persona(
            pipeline_root,
            business_id,
            "business",
        )

        speaker = resolve_speaker_persona(
            pipeline_root,
            business,
            speaker_id,
        )

    except AuthorityResolutionError as exc:
        raise ContentCreationEntryError(
            exc.code,
            str(exc),
        ) from exc

    (
        registry_path,
        _,
        profiles,
    ) = load_profile_registry(pipeline_root)

    capacity = resolve_capacity_preview(
        pipeline_root=(pipeline_root),
        business=business,
        speaker=speaker,
        requested_quantity=(requested_quantity),
        created_at=created_at,
    )

    available_capacity = max(
        0,
        int(capacity["high_quality_novel_capacity"]),
    )

    selected_profile = profiles[profile]

    if not selected_profile["available"]:
        status = "profile_unavailable"

        recommended_quantity = 0

        next_action = "CHOOSE_AVAILABLE_PROFILE"

        can_continue = False

        blocker = selected_profile["blocker"]

    elif available_capacity <= 0:
        status = "capacity_exhausted"

        recommended_quantity = 0

        next_action = "COLLECT_MORE_CUSTOMER_TRUTH"

        can_continue = False

        blocker = "NO_HIGH_QUALITY_" "NOVEL_CAPACITY"

    elif requested_quantity > available_capacity:
        status = "capacity_limited"

        recommended_quantity = available_capacity

        next_action = "CONFIRM_RECOMMENDED_QUANTITY"

        can_continue = True

        blocker = None

    else:
        status = "ready"

        recommended_quantity = requested_quantity

        next_action = "CONFIRM_GENERATION"

        can_continue = True

        blocker = None

    evidence_paths: list[Path] = [
        business["path"],
        business["receipt_path"],
        speaker["path"],
        speaker["receipt_path"],
        registry_path,
        *(capacity.get("evidence_paths") or []),
    ]

    refs: list[str] = []

    for path in evidence_paths:
        ref = evidence_ref(
            pipeline_root,
            Path(path),
        )

        if ref not in refs:
            refs.append(ref)

    return {
        "schema_version": (SCHEMA_VERSION),
        "operation_version": (OPERATION_VERSION),
        "created_at": (created_at or now_iso()),
        "business": {
            "business_id": (business["persona_id"]),
            "revision": (business["revision"]),
            "status": "APPROVED",
        },
        "speaker": {
            "speaker_id": (speaker["persona_id"]),
            "revision": (speaker["revision"]),
            "status": "APPROVED",
        },
        "profiles": profiles,
        "selection": {
            "profile": profile,
            "requested_quantity": (requested_quantity),
        },
        "capacity": {
            "scope": ("business_wide_" "semantic_novelty"),
            "source_mode": (capacity["mode"]),
            "ledger_entry_count": (capacity["ledger_entry_count"]),
            "high_quality_novel_capacity": (available_capacity),
            "capacity_status": (capacity.get("capacity_status")),
            "content_gap_summary": (capacity.get("content_gap_summary") or []),
            "padding_allowed": False,
        },
        "recommendation": {
            "status": status,
            "requested_quantity": (requested_quantity),
            "recommended_quantity": (recommended_quantity),
            "quantity_reduced_by": max(
                0,
                requested_quantity - recommended_quantity,
            ),
            "can_continue": (can_continue),
            "blocker": blocker,
        },
        "next_action": (next_action),
        "authority": {
            "business_persona_approved": (True),
            "speaker_persona_approved": (True),
            "profile_switch_resets_novelty": (False),
            "content_ledger_is_business_wide": (True),
            "padding_allowed": False,
            "generation_request_created": (False),
            "script_generation_performed": (False),
            "generation_batch_created": (False),
            "content_ledger_written": (False),
            "media_rights_checked": (False),
            "script_creation_establishes_media_rights": (False),
            "remote_model_called": (False),
        },
        "evidence_refs": refs,
        "model_calls": {
            "remote": 0,
            "local": 0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=("Build a read-only Content " "Creation Entry + Capacity Preview.")
    )

    parser.add_argument(
        "--business-id",
        required=True,
    )

    parser.add_argument(
        "--speaker-id",
        required=True,
    )

    parser.add_argument(
        "--profile",
        choices=(
            "mix",
            "news",
        ),
        default="mix",
    )

    parser.add_argument(
        "--quantity",
        required=True,
        type=int,
    )

    parser.add_argument(
        "--pipeline-root",
        default=str(Path(__file__).resolve().parents[1]),
    )

    args = parser.parse_args()

    try:
        entry = build_content_creation_entry(
            pipeline_root=Path(args.pipeline_root),
            business_id=(args.business_id),
            speaker_id=(args.speaker_id),
            profile=(args.profile),
            requested_quantity=(args.quantity),
        )

    except ContentCreationEntryError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )

        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "ok": True,
                "entry": entry,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
