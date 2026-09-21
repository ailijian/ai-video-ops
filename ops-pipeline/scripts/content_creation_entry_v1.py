from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from customer_intake_v1 import (
    build_initial_content_capacity_handoff,
)
from generation_feasibility_v1 import (
    preview_generation_feasibility,
)
from production_profile_v1 import (
    validate_registry,
)
from show_customer_status_v1 import (
    AuthorityResolutionError,
    load_content_ledger,
    load_export_receipts,
    iter_approved_generation_batch_paths,
    resolve_batches,
    resolve_capacity,
    resolve_current_persona,
    resolve_recorded_path,
    resolve_speaker_persona,
    sha256_file,
    validate_approved_batch,
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


def _request_business_id(
    pipeline_root: Path,
    request_id: str,
) -> str | None:
    """Best-effort ownership probe used only to scope canonical validation."""
    if not request_id:
        return None

    request_path = (
        pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )

    if not request_path.is_file():
        return None

    try:
        request = read_json(request_path)
    except ContentCreationEntryError:
        return None

    return str(request.get("persona_id") or request.get("business_id") or "")


def has_ledger_worthy_historical_exposure(
    pipeline_root: Path,
    business_id: str,
) -> bool:
    """Return True only when canonical Approved + Exported content exists.

    Generation Request alone is NOT ledger-worthy historical exposure.
    Source Planning Handoff / Content Plan / orchestration artifacts alone
    are NOT ledger-worthy historical exposure.
    Approved but not Exported Batch is NOT ledger-worthy historical exposure:
    the canonical Content Ledger is the authority for business-wide semantic
    history and Export is the point where durable published history is
    established.

    Canonical validation is reused from show_customer_status_v1. An Approved
    Batch or export receipt that belongs to this business but fails canonical
    validation is authority corruption, not "no history": fail closed with
    CONTENT_HISTORY_AUTHORITY_INVALID.
    """
    try:
        exports = load_export_receipts(pipeline_root)
    except AuthorityResolutionError as exc:
        raise ContentCreationEntryError(
            "CONTENT_HISTORY_AUTHORITY_INVALID",
            (
                "Export receipts cannot be safely "
                "resolved while the canonical Content "
                f"Ledger is missing: {exc}"
            ),
        ) from exc

    for path in iter_approved_generation_batch_paths(
        pipeline_root
    ):
        try:
            batch = read_json(path)
        except ContentCreationEntryError as exc:
            raise ContentCreationEntryError(
                "CONTENT_HISTORY_AUTHORITY_INVALID",
                (f"Approved Batch artifact is unreadable: {path}"),
            ) from exc

        owner = _request_business_id(
            pipeline_root,
            str(batch.get("request_id") or ""),
        )

        if owner is not None and owner != business_id:
            continue

        try:
            candidate = validate_approved_batch(
                pipeline_root,
                path,
                exports,
            )
        except AuthorityResolutionError as exc:
            raise ContentCreationEntryError(
                "CONTENT_HISTORY_AUTHORITY_INVALID",
                (
                    "Approved Batch authority is invalid "
                    "while the canonical Content Ledger "
                    f"is missing: {exc}"
                ),
            ) from exc

        if candidate["business_id"] != business_id:
            continue

        if candidate["export_status"] == "EXPORTED":
            return True

    for _, receipt in exports:
        if receipt.get("schema_version") != "news-excel-export-receipt-v1.0":
            continue

        owner = _request_business_id(
            pipeline_root,
            str(receipt.get("request_id") or ""),
        )

        if owner != business_id:
            continue

        try:
            output_path = resolve_recorded_path(
                pipeline_root,
                str(receipt.get("output_path") or ""),
            )
        except AuthorityResolutionError as exc:
            raise ContentCreationEntryError(
                "CONTENT_HISTORY_AUTHORITY_INVALID",
                (
                    "News export output cannot be resolved "
                    "while the canonical Content Ledger "
                    f"is missing: {exc}"
                ),
            ) from exc

        if sha256_file(output_path) != receipt.get("output_sha256"):
            raise ContentCreationEntryError(
                "CONTENT_HISTORY_AUTHORITY_INVALID",
                (f"News export output SHA-256 mismatch: {output_path}"),
            )

        return True

    return False


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
    # Generation Request existence alone does NOT constitute
    # Historical Exposure. Only canonical Approved + Exported
    # semantic content that should already be recorded in the
    # Content Ledger can trigger CONTENT_HISTORY_WITHOUT_LEDGER.
    # ---------------------------------------------------------

    if not ledger_path.is_file():
        if has_ledger_worthy_historical_exposure(
            pipeline_root,
            business_id,
        ):
            raise ContentCreationEntryError(
                "CONTENT_HISTORY_WITHOUT_LEDGER",
                (
                    "Approved and exported content exists "
                    "but the canonical Content Ledger "
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
                "ledger_worthy_historical_exposure_checked": (True),
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

    try:
        production_feasibility = preview_generation_feasibility(
            pipeline_root=pipeline_root,
            business_persona_path=business["path"],
            speaker_persona_path=speaker["path"],
            profile_registry_path=registry_path,
            target_profile=profile,
            quantity=max(1, min(requested_quantity, max(available_capacity, 1))),
            reuse_intent="novel_content",
            content_intent="mixed",
            platform="douyin",
            constraints={
                "no_padding": True,
                "case_facts_must_not_transfer": True,
                "unknown_persona_facts_must_not_be_filled": True,
                "speaker_first_person_authority_required": True,
                "profile_switch_does_not_reset_novelty": True,
                "script_generation_does_not_establish_media_rights": True,
            },
        )
    except Exception as exc:
        raise ContentCreationEntryError(
            "SOURCE_AUTHORITY_INVALID",
            f"Creative Production Feasibility cannot be resolved safely: {exc}",
        ) from exc

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

    elif production_feasibility.get("status") != "supported":
        status = "creative_coverage_unsupported"

        recommended_quantity = min(
            requested_quantity,
            available_capacity,
        )

        next_action = "REVIEW_CREATIVE_COVERAGE_GAP"

        can_continue = False

        blocker = str(
            production_feasibility.get("blocker_type")
            or "NO_APPROVED_COMPATIBLE_CASE"
        )

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
        "content_opportunity": {
            "requested_quantity": requested_quantity,
            "available_quantity": available_capacity,
            "suggested_quantity": recommended_quantity,
            "scope": "business_wide_semantic_novelty",
        },
        "production_feasibility": production_feasibility,
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
            "generation_feasibility_preview_performed": (True),
            "generation_feasibility_preview_is_authority": (False),
            "source_plan_written": (False),
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
