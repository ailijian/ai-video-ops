from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any

from operation_lock_v1 import OperationLockTimeout, operation_lock, scoped_lock_key

from content_creation_entry_v1 import (
    ContentCreationEntryError,
    build_content_creation_entry,
)
from show_customer_status_v1 import (
    AuthorityResolutionError,
    resolve_current_persona,
    resolve_speaker_persona,
    sha256_file,
)

from generation_request_effective_lifecycle_v1 import (
    EffectiveLifecycleError,
    request_is_effectively_in_flight,
)

REQUEST_SCHEMA_VERSION = "generation-request-v1.0"

HANDOFF_SCHEMA_VERSION = "generation-source-planning-" "handoff-v1.0"

OPERATION_VERSION = "generation_request_handoff_v1.py@1.0"

IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class GenerationRequestError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        preflight: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.preflight = preflight


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _business_generation_lock(
    pipeline_root: Path,
    business_id: str,
    timeout_seconds: float = 1.0,
):
    """
    Cross-process, business-scoped lock for Generation Request creation.

    This lock is orchestration-only.
    It is NOT canonical business state.

    Same business => serialized.
    Different businesses => independent locks.
    """

    try:
        with operation_lock(
            pipeline_root,
            scoped_lock_key("business", business_id),
            timeout_seconds=timeout_seconds,
        ):
            yield
    except OperationLockTimeout as exc:
        raise GenerationRequestError(
            "GENERATION_REQUEST_LOCK_TIMEOUT",
            "Timed out waiting for the business-scoped Generation Request lock.",
        ) from exc


def _business_locked(
    function,
):
    @wraps(function)
    def wrapper(
        *args,
        **kwargs,
    ):
        pipeline_root = (
            Path(
                kwargs["pipeline_root"]
            )
            .expanduser()
            .resolve()
        )

        business_id = str(
            kwargs["business_id"]
        )

        with _business_generation_lock(
            pipeline_root,
            business_id,
        ):
            return function(
                *args,
                **kwargs,
            )

    return wrapper


def canonical_sha256(
    value: Any,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def sha256_text(
    value: str,
) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise GenerationRequestError(
            "GENERATION_ARTIFACT_INVALID",
            f"Cannot read artifact: {path}",
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise GenerationRequestError(
            "GENERATION_ARTIFACT_INVALID",
            ("Generation artifact must " f"be an object: {path}"),
        )

    return value


def write_atomic_new_json(
    path: Path,
    value: dict[str, Any],
) -> bool:
    """Atomically create one new immutable JSON artifact.

    Returns True when this call created the artifact. Returns False when the
    artifact already existed with identical canonical content. Raises
    GENERATION_ARTIFACT_CONFLICT when an existing artifact differs.

    The final publish step is an atomic exclusive-create (os.link): an
    existing artifact is NEVER overwritten, not even when two concurrent
    confirmations race inside the same millisecond.
    """
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )

    if path.exists():
        existing = read_json(path)

        if canonical_sha256(existing) != canonical_sha256(value):
            raise GenerationRequestError(
                "GENERATION_ARTIFACT_CONFLICT",
                ("Immutable generation artifact " f"already differs: {path}"),
            )

        return False

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)

    try:
        os.link(
            temporary,
            path,
        )
    except FileExistsError:
        existing = read_json(path)

        if canonical_sha256(existing) != canonical_sha256(value):
            raise GenerationRequestError(
                "GENERATION_ARTIFACT_CONFLICT",
                (
                    "Immutable generation artifact "
                    "was created concurrently "
                    "with different content."
                ),
            )

        return False
    finally:
        temporary.unlink(missing_ok=True)

    return True


def evidence_ref(
    pipeline_root: Path,
    path: Path,
) -> str:
    try:
        return path.resolve().relative_to(pipeline_root.resolve()).as_posix()

    except ValueError:
        return str(path.resolve())


def _request_is_in_flight(
    pipeline_root: Path,
    request_path: Path,
) -> bool:
    try:
        return (
            request_is_effectively_in_flight(
                pipeline_root=(
                    pipeline_root
                ),
                request_path=(
                    request_path
                ),
            )
        )

    except EffectiveLifecycleError as exc:
        raise GenerationRequestError(
            exc.code,
            str(exc),
        ) from exc


def _active_in_flight_request_exists(
    pipeline_root: Path,
    business_id: str,
    profile: str,
    exclude_request_id: str | None = None,
) -> bool:
    root = (
        pipeline_root
        / "data"
        / "generation_requests"
    )

    if not root.exists():
        return False

    for path in root.glob(
        "*/generation_request_v1.json"
    ):
        try:
            request = read_json(
                path
            )
        except GenerationRequestError:
            continue

        if (
            str(
                request.get(
                    "persona_id"
                )
                or ""
            )
            != business_id
        ):
            continue

        if (
            str(
                request.get(
                    "target_profile"
                )
                or request.get(
                    "profile"
                )
                or ""
            ).lower()
            != profile
        ):
            continue

        if (
            exclude_request_id
            and request.get(
                "request_id"
            )
            == exclude_request_id
        ):
            continue

        if _request_is_in_flight(
            pipeline_root,
            path,
        ):
            return True

    return False


def _find_equivalent_active_request(
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
    selected_opportunity_id: str | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    # Effective lifecycle, not immutable Request status alone, decides in-flight.
    # Profile scope is explicit: old News validation Requests cannot block Mix.

    root = (
        pipeline_root
        / "data"
        / "generation_requests"
    )

    if not root.exists():
        return None

    for path in root.glob(
        "*/generation_request_v1.json"
    ):
        try:
            request = read_json(
                path
            )
        except GenerationRequestError:
            continue

        if (
            str(
                request.get(
                    "persona_id"
                )
                or ""
            )
            != business_id
        ):
            continue

        if (
            str(
                request.get(
                    "target_profile"
                )
                or request.get(
                    "profile"
                )
                or ""
            ).lower()
            != profile
        ):
            continue

        if not _request_is_in_flight(
            pipeline_root,
            path,
        ):
            continue

        if (
            str(
                request.get(
                    "speaker_persona"
                )
                or ""
            )
            != speaker_id
        ):
            continue

        if (
            int(
                request.get(
                    "quantity"
                )
                or 0
            )
            != confirmed_quantity
        ):
            continue

        if (request.get("selected_content") or {}).get("concept_id") != selected_opportunity_id:
            continue

        confirmation = (
            request.get(
                "confirmation"
            )
            or {}
        )

        if (
            int(
                confirmation.get(
                    "operator_requested_quantity"
                )
                or 0
            )
            != requested_quantity
        ):
            continue

        return (
            path,
            request,
        )

    return None

def request_id_for(
    business_id: str,
    idempotency_key: str,
) -> str:
    digest = hashlib.sha256(
        (f"{business_id}|" f"{idempotency_key}").encode("utf-8")
    ).hexdigest()[:20]

    return f"gen_{digest}"


def validate_confirmation(
    *,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
    idempotency_key: str,
) -> None:
    if profile not in {
        "mix",
        "news",
    }:
        raise GenerationRequestError(
            "GENERATION_PROFILE_INVALID",
            ("Generation profile must " "be mix or news."),
        )

    for field, value in (
        (
            "requested_quantity",
            requested_quantity,
        ),
        (
            "confirmed_quantity",
            confirmed_quantity,
        ),
    ):
        if (
            not isinstance(
                value,
                int,
            )
            or isinstance(
                value,
                bool,
            )
            or value < 1
            or value > 20
        ):
            raise GenerationRequestError(
                "GENERATION_QUANTITY_INVALID",
                (f"{field} must be " "an integer from 1 to 20."),
            )

    if not IDEMPOTENCY_RE.fullmatch(idempotency_key):
        raise GenerationRequestError(
            "GENERATION_IDEMPOTENCY_KEY_INVALID",
            (
                "idempotency_key must contain "
                "8-128 letters, numbers, "
                "underscores or hyphens."
            ),
        )


def confirmation_snapshot(
    preview: dict[str, Any],
    *,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
) -> dict[str, Any]:
    capacity = preview.get("capacity") or {}

    recommendation = preview.get("recommendation") or {}

    return {
        "business": (preview.get("business") or {}),
        "speaker": (preview.get("speaker") or {}),
        "profile": profile,
        "requested_quantity": (requested_quantity),
        "confirmed_quantity": (confirmed_quantity),
        "capacity": {
            "source_mode": (capacity.get("source_mode")),
            "ledger_entry_count": (capacity.get("ledger_entry_count")),
            "high_quality_novel_capacity": (
                capacity.get("high_quality_novel_capacity")
            ),
            "capacity_status": (capacity.get("capacity_status")),
            "padding_allowed": (capacity.get("padding_allowed")),
        },
        "production_feasibility": (
            preview.get("production_feasibility") or {}
        ),
        "recommendation": {
            "status": (recommendation.get("status")),
            "recommended_quantity": (recommendation.get("recommended_quantity")),
            "can_continue": (recommendation.get("can_continue")),
        },
        "evidence_refs": (preview.get("evidence_refs") or []),
    }


def validate_existing_request(
    request: dict[str, Any],
    *,
    business_id: str,
    speaker_id: str,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
    idempotency_key: str,
    require_idempotency_match: bool = True,
    selected_opportunity_id: str | None = None,
) -> None:
    confirmation = request.get("confirmation") or {}

    same = (
        request.get("schema_version") == REQUEST_SCHEMA_VERSION
        and request.get("persona_id") == business_id
        and request.get("speaker_persona") == speaker_id
        and request.get("target_profile") == profile
        and int(request.get("quantity") or 0) == confirmed_quantity
        and int(confirmation.get("operator_requested_quantity") or 0)
        == requested_quantity
        and (request.get("selected_content") or {}).get("concept_id") == selected_opportunity_id
    )

    if require_idempotency_match:
        expected_key_sha = sha256_text(idempotency_key)
        same = same and confirmation.get("idempotency_key_sha256") == expected_key_sha

    if not same:
        raise GenerationRequestError(
            "GENERATION_IDEMPOTENCY_CONFLICT",
            (
                "This confirmation does not match "
                "the existing Generation Request."
            ),
        )


def build_source_handoff(
    *,
    pipeline_root: Path,
    request_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    lineage = request.get("lineage") or {}

    return {
        "schema_version": (HANDOFF_SCHEMA_VERSION),
        "operation_version": (OPERATION_VERSION),
        "request_id": (request["request_id"]),
        "created_at": (request["created_at"]),
        "status": ("source_authority_" "resolution_pending"),
        "generation_request_ref": {
            "path": str(request_path.resolve()),
            "evidence_ref": (
                evidence_ref(
                    pipeline_root,
                    request_path,
                )
            ),
            "file_sha256": (sha256_file(request_path)),
        },
        "business_persona_ref": (lineage.get("business_persona_ref")),
        "speaker_persona_ref": (lineage.get("speaker_persona_ref")),
        "production_profile_registry_ref": (
            lineage.get("production_profile_registry_ref")
        ),
        "source_planning_contract": {
            "next_operation": ("match_generation_sources_v1.py"),
            "target_profile": (request["target_profile"]),
            "approved_patterns_only": (True),
            "approved_cases_only": (True),
            "approved_case_fingerprint_one_to_one_required": (True),
            "creative_coverage_report_required": (True),
            "profile_compatibility_approval_required": (True),
            "case_facts_must_not_transfer": (True),
            "pattern_effectiveness_must_not_be_invented": (True),
            "speaker_first_person_authority_required": (True),
        },
        "authority_roots": {
            "approved_pattern_root": ("data/patterns/approved"),
            "case_root": ("data/cases"),
            "production_plan_root": ("data/production_plans"),
        },
        "authority": {
            "generation_request_created": (True),
            "source_matching_performed": (False),
            "source_plan_created": (False),
            "content_plan_created": (False),
            "script_generation_performed": (False),
            "generation_batch_created": (False),
            "content_ledger_written": (False),
            "remote_model_called": (False),
            "media_rights_established": (False),
            "case_media_reuse_authorized": (False),
        },
        "next_action": ("RESOLVE_GENERATION_SOURCES"),
        "model_calls": {
            "remote": 0,
            "local": 0,
        },
    }


def recover_existing(
    *,
    pipeline_root: Path,
    request_path: Path,
    handoff_path: Path,
    business_id: str,
    speaker_id: str,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
    idempotency_key: str,
    require_idempotency_match: bool = True,
    selected_opportunity_id: str | None = None,
) -> dict[str, Any]:
    request = read_json(request_path)

    validate_existing_request(
        request,
        business_id=business_id,
        speaker_id=speaker_id,
        profile=profile,
        requested_quantity=(requested_quantity),
        confirmed_quantity=(confirmed_quantity),
        idempotency_key=(idempotency_key),
        require_idempotency_match=(require_idempotency_match),
        selected_opportunity_id=selected_opportunity_id,
    )

    if handoff_path.is_file():
        handoff = read_json(handoff_path)

        request_ref = handoff.get("generation_request_ref") or {}

        if request_ref.get("file_sha256") != sha256_file(request_path):
            raise GenerationRequestError(
                "GENERATION_HANDOFF_LINEAGE_MISMATCH",
                (
                    "Existing Source Planning "
                    "Handoff does not match "
                    "the Generation Request."
                ),
            )

    else:
        handoff = build_source_handoff(
            pipeline_root=(pipeline_root),
            request_path=(request_path),
            request=request,
        )

        write_atomic_new_json(
            handoff_path,
            handoff,
        )

    return {
        "request_id": (request["request_id"]),
        "request_path": str(request_path.resolve()),
        "request_sha256": (sha256_file(request_path)),
        "handoff_path": str(handoff_path.resolve()),
        "handoff_sha256": (sha256_file(handoff_path)),
        "confirmed_quantity": (request["quantity"]),
        "recovered": True,
        "next_action": ("RESOLVE_GENERATION_SOURCES"),
        "authority": {
            "script_generation_performed": (False),
            "content_ledger_written": (False),
            "remote_model_called": (False),
        },
    }


@_business_locked
def create_generation_request_handoff(
    *,
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    profile: str,
    requested_quantity: int,
    confirmed_quantity: int,
    idempotency_key: str,
    created_at: str | None = None,
    created_by_user_id: int | None = None,
    created_by_phone: str | None = None,
    selected_opportunity_id: str | None = None,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()

    profile = str(profile or "").strip().lower()

    idempotency_key = str(idempotency_key or "").strip()

    validate_confirmation(
        profile=profile,
        requested_quantity=(requested_quantity),
        confirmed_quantity=(confirmed_quantity),
        idempotency_key=(idempotency_key),
    )
    if (created_by_user_id is None) != (created_by_phone is None):
        raise GenerationRequestError(
            "GENERATION_REQUEST_CREATOR_INCOMPLETE",
            "Creator user ID and phone snapshot must be provided together.",
        )

    request_id = request_id_for(
        business_id,
        idempotency_key,
    )

    request_root = pipeline_root / "data" / "generation_requests" / request_id

    request_path = request_root / "generation_request_v1.json"

    handoff_path = request_root / ("generation_source_planning_" "handoff_v1.json")

    # Idempotent retry must recover before
    # recalculating capacity. Same business +
    # same idempotency key always returns the
    # same immutable Request.
    if request_path.is_file():
        return recover_existing(
            pipeline_root=(pipeline_root),
            request_path=(request_path),
            handoff_path=(handoff_path),
            business_id=(business_id),
            speaker_id=(speaker_id),
            profile=profile,
            requested_quantity=(requested_quantity),
            confirmed_quantity=(confirmed_quantity),
            idempotency_key=(idempotency_key),
            selected_opportunity_id=selected_opportunity_id,
        )

    equivalent = _find_equivalent_active_request(
        pipeline_root,
        business_id,
        speaker_id,
        profile,
        requested_quantity,
        confirmed_quantity,
        selected_opportunity_id,
    )

    if equivalent is not None:
        equivalent_path, equivalent_request = equivalent

        equivalent_root = equivalent_path.parent

        equivalent_handoff_path = equivalent_root / (
            "generation_source_planning_" "handoff_v1.json"
        )

        return recover_existing(
            pipeline_root=(pipeline_root),
            request_path=(equivalent_path),
            handoff_path=(equivalent_handoff_path),
            business_id=(business_id),
            speaker_id=(speaker_id),
            profile=profile,
            requested_quantity=(requested_quantity),
            confirmed_quantity=(confirmed_quantity),
            idempotency_key=(idempotency_key),
            require_idempotency_match=False,
            selected_opportunity_id=selected_opportunity_id,
        )

    if _active_in_flight_request_exists(
        pipeline_root,
        business_id,
        profile,
        exclude_request_id=request_id,
    ):
        raise GenerationRequestError(
            "CONTENT_GENERATION_IN_FLIGHT",
            (
                "An active Generation Request already "
                "exists for this customer. Complete or "
                "resolve it before creating a new one."
            ),
        )

    selected_content = None
    if profile == "news" and selected_opportunity_id is None:
        raise GenerationRequestError(
            "NEWS_NOVEL_OPPORTUNITY_REQUIRED",
            "Novel News requires one explicitly selected, novel content opportunity.",
        )
    if selected_opportunity_id is not None:
        if profile != "news" or requested_quantity != 1 or confirmed_quantity != 1:
            raise GenerationRequestError(
                "NEWS_NOVEL_REQUEST_CONTRACT_INVALID",
                "Novel News confirms exactly one selected opportunity per Request.",
            )
        from novel_news_opportunity_v1 import project_novel_news_opportunities

        opportunities = project_novel_news_opportunities(
            pipeline_root=pipeline_root, business_id=business_id, speaker_id=speaker_id
        )
        matching = [
            item for item in opportunities["opportunities"]
            if item["concept_id"] == selected_opportunity_id
        ]
        if len(matching) != 1:
            raise GenerationRequestError(
                "NEWS_NOVEL_OPPORTUNITY_STALE",
                "The selected Novel News opportunity is no longer available.",
            )
        selected_content = matching[0]
        feasibility = selected_content["production_feasibility"]
        if (
            selected_content["novelty_status"] != "novel"
            or feasibility.get("status") != "supported"
            or int(opportunities["available_novel_count"]) <= 0
        ):
            raise GenerationRequestError(
                "NEWS_NOVEL_PREFLIGHT_UNSUPPORTED",
                "Novel content and approved News source coverage must both be available.",
                preflight=opportunities,
            )
        business_preview = resolve_current_persona(pipeline_root, business_id, "business")
        speaker_preview = resolve_speaker_persona(pipeline_root, business_preview, speaker_id)
        ledger_path = pipeline_root / "data/content_ledgers" / business_id / "content_ledger_v1.json"
        preview = {
            "business": {"business_id": business_id, "revision": business_preview["revision"], "status": "APPROVED"},
            "speaker": {"speaker_id": speaker_id, "revision": speaker_preview["revision"], "status": "APPROVED"},
            "capacity": {
                "source_mode": "approved_fact_atoms_plus_business_wide_ledger",
                "ledger_entry_count": len(read_json(ledger_path).get("entries") or []) if ledger_path.is_file() else 0,
                "high_quality_novel_capacity": opportunities["available_novel_count"],
                "capacity_status": "available", "padding_allowed": False,
            },
            "production_feasibility": feasibility,
            "recommendation": {"status": "ready", "requested_quantity": 1, "recommended_quantity": 1, "can_continue": True, "blocker": None},
            "evidence_refs": [str(business_preview["path"]), str(speaker_preview["path"]), *( [str(ledger_path)] if ledger_path.is_file() else [])],
        }
    else:
        try:
            preview = build_content_creation_entry(
                pipeline_root=(pipeline_root),
                business_id=(business_id),
                speaker_id=(speaker_id),
                profile=profile,
                requested_quantity=(requested_quantity),
                created_at=created_at,
            )
        except ContentCreationEntryError as exc:
            raise GenerationRequestError(exc.code, str(exc)) from exc

    recommendation = preview.get("recommendation") or {}

    if recommendation.get("can_continue") is not True:
        raise GenerationRequestError(
            str(recommendation.get("blocker") or ("GENERATION_REQUEST_" "NOT_ALLOWED")),
            (
                "Current Content Creation Preflight does not allow an immutable "
                "Generation Request."
            ),
            preflight=preview,
        )

    recommended_quantity = int(recommendation.get("recommended_quantity") or 0)

    if recommended_quantity != confirmed_quantity:
        raise GenerationRequestError(
            "CAPACITY_CONFIRMATION_STALE",
            (
                "The confirmed quantity no "
                "longer matches the current "
                "Capacity recommendation. "
                "Run Capacity Check again."
            ),
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
        raise GenerationRequestError(
            exc.code,
            str(exc),
        ) from exc

    preview_business = preview.get("business") or {}

    preview_speaker = preview.get("speaker") or {}

    if int(preview_business.get("revision") or 0) != int(business["revision"]) or int(
        preview_speaker.get("revision") or 0
    ) != int(speaker["revision"]):
        raise GenerationRequestError(
            "CAPACITY_AUTHORITY_CHANGED",
            (
                "Persona Authority changed "
                "during Generation Request "
                "confirmation. Run Capacity "
                "Check again."
            ),
        )

    registry_path = (
        pipeline_root
        / "data"
        / "production_profiles"
        / ("production_profile_" "registry_v1.json")
    )

    if not registry_path.is_file():
        raise GenerationRequestError(
            "PRODUCTION_PROFILE_REGISTRY_NOT_FOUND",
            (
                "Production Profile Registry "
                "is required before creating "
                "a Generation Request."
            ),
        )

    snapshot = confirmation_snapshot(
        preview,
        profile=profile,
        requested_quantity=(requested_quantity),
        confirmed_quantity=(confirmed_quantity),
    )

    timestamp = created_at or now_iso()

    request = {
        "schema_version": (REQUEST_SCHEMA_VERSION),
        "operation_version": (OPERATION_VERSION),
        "request_id": request_id,
        "created_at": timestamp,
        "persona_id": (business["persona_id"]),
        "persona_revision": (business["revision"]),
        "speaker_persona": (speaker["persona_id"]),
        "speaker_persona_revision": (speaker["revision"]),
        "profile": profile,
        "target_profile": profile,
        "reuse_intent": ("novel_content"),
        **({"selected_content": selected_content} if selected_content is not None else {}),
        "content_intent": ("mixed"),
        "quantity": (confirmed_quantity),
        "platform": "douyin",
        "cta_intent": "none",
        "constraints": {
            "no_padding": True,
            "case_facts_must_not_transfer": (True),
            "unknown_persona_facts_must_not_be_filled": (True),
            "speaker_first_person_authority_required": (True),
            "profile_switch_does_not_reset_novelty": (True),
            "script_generation_does_not_establish_media_rights": (True),
        },
        "confirmation": {
            "operator_requested_quantity": (requested_quantity),
            "confirmed_quantity": (confirmed_quantity),
            "capacity_snapshot": (snapshot),
            "capacity_snapshot_sha256": (canonical_sha256(snapshot)),
            "idempotency_key_sha256": (sha256_text(idempotency_key)),
            "explicit_operator_confirmation": (True),
        },
        "lineage": {
            "business_persona_ref": {
                "persona_id": (business["persona_id"]),
                "revision": (business["revision"]),
                "path": str(business["path"].resolve()),
                "file_sha256": (business["file_sha256"]),
                "content_sha256": (business["content_sha256"]),
            },
            "speaker_persona_ref": {
                "persona_id": (speaker["persona_id"]),
                "revision": (speaker["revision"]),
                "path": str(speaker["path"].resolve()),
                "file_sha256": (speaker["file_sha256"]),
                "content_sha256": (speaker["content_sha256"]),
            },
            "production_profile_registry_ref": {
                "path": str(registry_path.resolve()),
                "file_sha256": (sha256_file(registry_path)),
            },
            "capacity_evidence_refs": (preview.get("evidence_refs") or []),
        },
        "lifecycle": {
            "status": "created",
            "generation_started": (False),
            "source_matching_started": (False),
            "human_review_required": (True),
        },
        "authority": {
            "generation_request_is_immutable": (True),
            "source_matching_performed": (False),
            "script_generation_performed": (False),
            "generation_batch_created": (False),
            "content_ledger_written": (False),
            "remote_model_called": (False),
            "media_rights_established": (False),
        },
    }
    if created_by_user_id is not None:
        request["created_by_user_id"] = created_by_user_id
        request["created_by_phone"] = created_by_phone

    created = write_atomic_new_json(
        request_path,
        request,
    )

    if not created:
        # A concurrent confirmation with the same idempotency key won the
        # atomic exclusive-create race. Recover the same immutable Request
        # instead of reporting a fresh creation.
        return recover_existing(
            pipeline_root=(pipeline_root),
            request_path=(request_path),
            handoff_path=(handoff_path),
            business_id=(business_id),
            speaker_id=(speaker_id),
            profile=profile,
            requested_quantity=(requested_quantity),
            confirmed_quantity=(confirmed_quantity),
            idempotency_key=(idempotency_key),
            selected_opportunity_id=selected_opportunity_id,
        )

    handoff = build_source_handoff(
        pipeline_root=(pipeline_root),
        request_path=(request_path),
        request=request,
    )

    write_atomic_new_json(
        handoff_path,
        handoff,
    )

    return {
        "request_id": request_id,
        "request_path": str(request_path.resolve()),
        "request_sha256": (sha256_file(request_path)),
        "handoff_path": str(handoff_path.resolve()),
        "handoff_sha256": (sha256_file(handoff_path)),
        "confirmed_quantity": (confirmed_quantity),
        "recovered": False,
        "next_action": ("RESOLVE_GENERATION_SOURCES"),
        "authority": {
            "generation_request_created": (True),
            "source_matching_performed": (False),
            "script_generation_performed": (False),
            "content_ledger_written": (False),
            "remote_model_called": (False),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create one immutable "
            "Generation Request and "
            "Source Planning Handoff "
            "without generating content."
        )
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
        required=True,
    )

    parser.add_argument(
        "--requested-quantity",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--confirmed-quantity",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--idempotency-key",
        required=True,
    )

    parser.add_argument(
        "--pipeline-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    parser.add_argument("--created-by-user-id", type=int)
    parser.add_argument("--created-by-phone")
    parser.add_argument("--selected-opportunity-id")

    args = parser.parse_args()

    try:
        result = create_generation_request_handoff(
            pipeline_root=Path(args.pipeline_root),
            business_id=(args.business_id),
            speaker_id=(args.speaker_id),
            profile=(args.profile),
            requested_quantity=(args.requested_quantity),
            confirmed_quantity=(args.confirmed_quantity),
            idempotency_key=(args.idempotency_key),
            created_by_user_id=args.created_by_user_id,
            created_by_phone=args.created_by_phone,
            selected_opportunity_id=args.selected_opportunity_id,
        )

    except GenerationRequestError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": str(exc),
                    "preflight": exc.preflight,
                },
                ensure_ascii=False,
            )
        )

        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "ok": True,
                "result": result,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
