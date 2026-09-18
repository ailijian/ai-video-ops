from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from operational_controls_v1 import load_controls

from content_quality_v1 import (
    build_content_plan_v1_1_1,
)


SCHEMA_VERSION = "customer-status-read-model-v1.0"
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class AuthorityResolutionError(RuntimeError):
    def __init__(self, code: str, message: str, evidence_refs: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.evidence_refs = evidence_refs or []


def require_id(value: str, field: str) -> str:
    normalized = value.strip()
    if not ID_PATTERN.fullmatch(normalized):
        raise AuthorityResolutionError(
            "INVALID_IDENTIFIER",
            f"{field} must contain only letters, numbers, underscores, or hyphens.",
        )
    return normalized


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorityResolutionError(
            "INVALID_AUTHORITY_ARTIFACT", f"Cannot read JSON authority {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise AuthorityResolutionError(
            "INVALID_AUTHORITY_ARTIFACT", f"Authority must be a JSON object: {path}"
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_ref(pipeline_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(pipeline_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def resolve_recorded_path(pipeline_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_file():
        return candidate.resolve()
    normalized = raw_path.replace("\\", "/")
    marker = "/ops-pipeline/"
    lowered = normalized.lower()
    marker_index = lowered.find(marker)
    if marker_index >= 0:
        relative = normalized[marker_index + len(marker) :]
        relocated = pipeline_root / Path(relative)
        if relocated.is_file():
            return relocated.resolve()
    relative_candidate = pipeline_root / Path(normalized)
    if relative_candidate.is_file():
        return relative_candidate.resolve()
    raise AuthorityResolutionError(
        "MISSING_LINEAGE_ARTIFACT", f"Recorded lineage path does not exist: {raw_path}"
    )


def validate_file_ref(
    pipeline_root: Path,
    reference: dict[str, Any],
    *,
    path_keys: tuple[str, ...] = ("path",),
    sha_keys: tuple[str, ...] = ("sha256", "file_sha256"),
) -> Path:
    raw_path = next(
        (str(reference[key]) for key in path_keys if reference.get(key)), ""
    )
    expected_sha = next(
        (str(reference[key]) for key in sha_keys if reference.get(key)), ""
    )
    if not raw_path or not expected_sha:
        raise AuthorityResolutionError(
            "INCOMPLETE_LINEAGE", "Lineage reference requires an explicit path and SHA-256."
        )
    path = resolve_recorded_path(pipeline_root, raw_path)
    if sha256_file(path) != expected_sha:
        raise AuthorityResolutionError(
            "LINEAGE_HASH_MISMATCH", f"SHA-256 mismatch for lineage artifact: {path}"
        )
    return path


def validate_approved_persona(
    pipeline_root: Path,
    persona_path: Path,
    expected_id: str,
    expected_scope: str,
) -> dict[str, Any] | None:
    persona = read_json(persona_path)
    if persona.get("persona_id") != expected_id:
        return None
    lifecycle = persona.get("lifecycle") or {}
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        return None
    if persona.get("persona_scope", "business") != expected_scope:
        raise AuthorityResolutionError(
            "PERSONA_SCOPE_MISMATCH",
            f"Approved Persona has the wrong scope: {persona_path}",
            [evidence_ref(pipeline_root, persona_path)],
        )
    revision = persona.get("revision")
    if not isinstance(revision, int) or revision < 1:
        raise AuthorityResolutionError(
            "INVALID_PERSONA_REVISION", f"Invalid explicit Persona revision: {persona_path}"
        )
    receipt_path = persona_path.parent / "approval_receipt.json"
    if not receipt_path.is_file():
        raise AuthorityResolutionError(
            "PERSONA_APPROVAL_RECEIPT_REQUIRED",
            f"Approved Persona is missing its approval receipt: {persona_path}",
            [evidence_ref(pipeline_root, persona_path)],
        )
    receipt = read_json(receipt_path)
    valid_receipt = (
        receipt.get("schema_version") == "persona-approval-receipt-v1.0"
        and receipt.get("persona_id") == expected_id
        and receipt.get("revision") == revision
        and receipt.get("decision") == "approved"
        and receipt.get("human_gate") is True
        and receipt.get("persona_sha256_after_approval") == sha256_file(persona_path)
        and receipt.get("content_sha256")
        == (persona.get("provenance") or {}).get("content_sha256")
    )
    if not valid_receipt:
        raise AuthorityResolutionError(
            "INVALID_PERSONA_APPROVAL_RECEIPT",
            f"Persona approval receipt does not validate the approved revision: {receipt_path}",
            [
                evidence_ref(pipeline_root, persona_path),
                evidence_ref(pipeline_root, receipt_path),
            ],
        )
    if (persona.get("approval") or {}).get("human_gate") is not True:
        raise AuthorityResolutionError(
            "PERSONA_HUMAN_GATE_REQUIRED",
            f"Approved Persona does not preserve its Human Gate: {persona_path}",
        )
    return {
        "persona_id": expected_id,
        "revision": revision,
        "status": "APPROVED",
        "scope": expected_scope,
        "content_sha256": (persona.get("provenance") or {}).get("content_sha256"),
        "file_sha256": sha256_file(persona_path),
        "path": persona_path,
        "receipt_path": receipt_path,
        "artifact": persona,
    }


def resolve_current_persona(
    pipeline_root: Path, persona_id: str, expected_scope: str
) -> dict[str, Any]:
    persona_id = require_id(persona_id, "persona_id")
    root = pipeline_root / "data" / "personas" / persona_id
    if not root.is_dir():
        raise AuthorityResolutionError(
            "PERSONA_NOT_FOUND", f"Persona directory does not exist: {root}"
        )
    approved: list[dict[str, Any]] = []
    for path in root.glob("*/persona_v1.json"):
        value = validate_approved_persona(
            pipeline_root, path, persona_id, expected_scope
        )
        if value is not None:
            approved.append(value)
    if not approved:
        raise AuthorityResolutionError(
            "APPROVED_PERSONA_NOT_FOUND", f"No valid Approved Persona for {persona_id}."
        )
    by_revision: dict[int, list[dict[str, Any]]] = {}
    for item in approved:
        by_revision.setdefault(item["revision"], []).append(item)
    duplicates = [revision for revision, items in by_revision.items() if len(items) > 1]
    if duplicates:
        raise AuthorityResolutionError(
            "CURRENT_AUTHORITY_AMBIGUITY",
            f"Multiple Approved Persona artifacts claim revision(s): {duplicates}",
            [evidence_ref(pipeline_root, item["path"]) for item in approved],
        )
    selected = by_revision[max(by_revision)]
    current = selected[0]
    if current["revision"] > 1:
        previous_ref = (current["artifact"].get("revision_lineage") or {}).get(
            "previous_approved_revision"
        )
        if not isinstance(previous_ref, dict):
            raise AuthorityResolutionError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                "Highest Approved Persona revision lacks explicit previous-approved lineage.",
                [evidence_ref(pipeline_root, current["path"])],
            )
        lower_revisions = [revision for revision in by_revision if revision < current["revision"]]
        previous_revision = previous_ref.get("revision")
        if not lower_revisions or previous_revision != max(lower_revisions):
            raise AuthorityResolutionError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                "Persona previous-approved lineage does not resolve to the immediately prior Approved revision.",
            )
        previous = by_revision[previous_revision][0]
        if previous_ref.get("sha256") != previous["file_sha256"]:
            raise AuthorityResolutionError(
                "LINEAGE_HASH_MISMATCH",
                "Persona previous-approved lineage SHA-256 does not match.",
            )
    return current


def resolve_speaker_persona(
    pipeline_root: Path,
    business: dict[str, Any],
    speaker_id: str | None,
) -> dict[str, Any]:
    if speaker_id:
        candidates = [resolve_current_persona(pipeline_root, speaker_id, "speaker")]
    else:
        candidates = []
        personas_root = pipeline_root / "data" / "personas"
        for child in personas_root.iterdir():
            if not child.is_dir() or child.name == business["persona_id"]:
                continue
            try:
                candidate = resolve_current_persona(pipeline_root, child.name, "speaker")
            except AuthorityResolutionError as exc:
                if exc.code in {"APPROVED_PERSONA_NOT_FOUND", "PERSONA_SCOPE_MISMATCH"}:
                    continue
                raise
            reference = candidate["artifact"].get("business_persona_ref") or {}
            if reference.get("persona_id") == business["persona_id"]:
                candidates.append(candidate)
        if len(candidates) != 1:
            raise AuthorityResolutionError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                "Speaker Persona cannot be uniquely resolved; provide --speaker-id.",
                [evidence_ref(pipeline_root, item["path"]) for item in candidates],
            )
    speaker = candidates[0]
    reference = speaker["artifact"].get("business_persona_ref") or {}
    valid_business_binding = (
        reference.get("persona_id") == business["persona_id"]
        and reference.get("revision") == business["revision"]
        and reference.get("sha256") == business["file_sha256"]
        and reference.get("content_sha256") == business["content_sha256"]
        and reference.get("status") == "approved"
    )
    if not valid_business_binding:
        raise AuthorityResolutionError(
            "SPEAKER_BUSINESS_LINEAGE_MISMATCH",
            "Speaker Persona is not bound to the Current Approved Business Persona.",
            [
                evidence_ref(pipeline_root, business["path"]),
                evidence_ref(pipeline_root, speaker["path"]),
            ],
        )
    return speaker


def load_content_ledger(pipeline_root: Path, business_id: str) -> dict[str, Any]:
    path = (
        pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )
    if not path.is_file():
        raise AuthorityResolutionError(
            "CONTENT_LEDGER_NOT_FOUND", f"Canonical Content Ledger not found: {path}"
        )
    value = read_json(path)
    entries = value.get("entries")
    if (
        value.get("schema_version") != "content-ledger-v1.0"
        or value.get("business_id") != business_id
        or not isinstance(entries, list)
    ):
        raise AuthorityResolutionError(
            "INVALID_CONTENT_LEDGER", f"Invalid canonical Content Ledger: {path}"
        )
    return {"path": path, "artifact": value, "entries": entries, "file_sha256": sha256_file(path)}


def load_export_receipts(pipeline_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Load canonical export receipts across legacy and current delivery surfaces.

    Mix and the legacy News MVP stored receipts under output/*.export_receipt.json.
    News Delivery V1 stores its immutable receipt with the request lineage under
    data/news_deliveries/<request_id>/news_dynamic_excel_export_receipt_v1.json.

    Both are read-only Authority sources. Dynamic News receipts are presentation
    history receipts, not new semantic Content Ledger exposure.
    """
    receipts: list[tuple[Path, dict[str, Any]]] = []

    output_root = pipeline_root / "output"
    for path in output_root.glob("*.export_receipt.json"):
        value = read_json(path)
        if value.get("validation_passed") is True:
            receipts.append((path, value))

    news_root = pipeline_root / "data" / "news_deliveries"
    if news_root.exists():
        for path in news_root.glob(
            "*/news_dynamic_excel_export_receipt_v1.json"
        ):
            value = read_json(path)
            if (
                value.get("schema_version")
                == "news-dynamic-excel-export-receipt-v1.0"
                and value.get("validation_passed") is True
            ):
                receipts.append((path, value))

    return receipts


def validate_approved_batch(
    pipeline_root: Path, batch_path: Path, export_receipts: list[tuple[Path, dict[str, Any]]]
) -> dict[str, Any]:
    batch = read_json(batch_path)
    if (
        batch.get("schema_version") != "approved-generation-batch-v1.0"
        or batch.get("status") != "approved"
    ):
        raise AuthorityResolutionError(
            "INVALID_APPROVED_BATCH", f"Invalid Approved Batch: {batch_path}"
        )
    request_id = str(batch.get("request_id") or "")
    require_id(request_id, "request_id")
    request_path = (
        pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )
    if not request_path.is_file():
        raise AuthorityResolutionError(
            "GENERATION_REQUEST_NOT_FOUND", f"Generation Request not found: {request_path}"
        )
    request = read_json(request_path)
    if request.get("request_id") != request_id:
        raise AuthorityResolutionError(
            "GENERATION_REQUEST_LINEAGE_MISMATCH", f"Request ID mismatch: {request_path}"
        )
    receipt_path = batch_path.parent / "generation_batch_approval_receipt.json"
    if not receipt_path.is_file():
        raise AuthorityResolutionError(
            "BATCH_APPROVAL_RECEIPT_REQUIRED",
            f"Approved Batch is missing approval receipt: {batch_path}",
        )
    receipt = read_json(receipt_path)
    batch_sha = sha256_file(batch_path)
    approved_ref = receipt.get("approved_batch") or receipt.get("reviewed_batch") or {}
    if not (
        receipt.get("schema_version") == "generation-batch-approval-receipt-v1.0"
        and receipt.get("request_id") == request_id
        and receipt.get("status") == "approved"
        and receipt.get("human_gate") is True
        and approved_ref.get("sha256") == batch_sha
    ):
        raise AuthorityResolutionError(
            "INVALID_BATCH_APPROVAL_RECEIPT",
            f"Batch approval receipt does not validate the batch: {receipt_path}",
        )
    matching_exports = [
        (path, value)
        for path, value in export_receipts
        if value.get("batch_sha256") == batch_sha
    ]
    if len(matching_exports) > 1:
        raise AuthorityResolutionError(
            "CURRENT_AUTHORITY_AMBIGUITY",
            f"Multiple export receipts validate the same Approved Batch: {batch_path}",
            [evidence_ref(pipeline_root, path) for path, _ in matching_exports],
        )
    export_path: Path | None = None
    export_receipt: dict[str, Any] | None = None
    if matching_exports:
        export_path, export_receipt = matching_exports[0]
        output_path = resolve_recorded_path(pipeline_root, str(export_receipt.get("output_path") or ""))
        if sha256_file(output_path) != export_receipt.get("output_sha256"):
            raise AuthorityResolutionError(
                "LINEAGE_HASH_MISMATCH", f"Export output SHA-256 mismatch: {output_path}"
            )
    profile = str(batch.get("profile") or request.get("target_profile") or request.get("profile") or "")
    return {
        "request_id": request_id,
        "business_id": str(request.get("persona_id") or ""),
        "profile": profile,
        "batch_revision": batch.get("batch_revision"),
        "status": "APPROVED",
        "export_status": "EXPORTED" if export_receipt else "NOT_EXPORTED",
        "path": batch_path,
        "file_sha256": batch_sha,
        "receipt_path": receipt_path,
        "approved_at": receipt.get("reviewed_at"),
        "export_receipt_path": export_path,
        "artifact": batch,
        "request": request,
    }



def iter_approved_generation_batch_paths(
    pipeline_root: Path,
) -> list[Path]:
    # Support both historical revisioned layout and current flat Console layout.
    batches_root = (
        pipeline_root
        / "data"
        / "generation_batches"
    )

    if not batches_root.exists():
        return []

    paths: set[Path] = set()

    for pattern in (
        "*/revisions/*/approved_generation_batch_v1.json",
        "*/approved_generation_batch_v1.json",
    ):
        for path in batches_root.glob(pattern):
            if path.is_file():
                paths.add(path.resolve())

    return sorted(
        paths,
        key=lambda item: item.as_posix(),
    )


def resolve_batches(
    pipeline_root: Path,
    business_id: str,
    ledger: dict[str, Any],
    explicit_batch_id: str | None,
) -> dict[str, Any]:
    exports = load_export_receipts(pipeline_root)
    candidates: list[dict[str, Any]] = []
    for path in iter_approved_generation_batch_paths(
        pipeline_root
    ):
        candidate = validate_approved_batch(
            pipeline_root,
            path,
            exports,
        )
        if candidate["business_id"] == business_id:
            candidates.append(candidate)
    if not candidates:
        raise AuthorityResolutionError(
            "APPROVED_BATCH_NOT_FOUND", f"No Approved Batch for {business_id}."
        )
    approved_mix = [item for item in candidates if item["profile"] == "mix"]
    if not approved_mix or any(not item.get("approved_at") for item in approved_mix):
        raise AuthorityResolutionError(
            "CURRENT_AUTHORITY_AMBIGUITY",
            "Approved Mix Batch approval timestamps are incomplete.",
        )
    try:
        approval_times = {
            item["request_id"]: datetime.fromisoformat(
                str(item["approved_at"]).replace("Z", "+00:00")
            )
            for item in approved_mix
        }
    except ValueError as exc:
        raise AuthorityResolutionError(
            "INVALID_APPROVAL_TIMESTAMP", "Approved Mix Batch timestamp is invalid."
        ) from exc
    latest_approval_time = max(approval_times.values())
    latest_approved_candidates = [
        item
        for item in approved_mix
        if approval_times[item["request_id"]] == latest_approval_time
    ]
    if len(latest_approved_candidates) != 1:
        raise AuthorityResolutionError(
            "CURRENT_AUTHORITY_AMBIGUITY",
            "Latest Approved Mix Batch is ambiguous across approval receipts.",
        )
    latest_approved_mix = latest_approved_candidates[0]
    ledger_position: dict[str, int] = {}
    for index, entry in enumerate(ledger["entries"]):
        if isinstance(entry, dict) and entry.get("batch_ref"):
            ledger_position[str(entry["batch_ref"])] = index
    exported_mix = [
        item
        for item in candidates
        if item["profile"] == "mix"
        and item["export_status"] == "EXPORTED"
        and item["request_id"] in ledger_position
    ]
    if not exported_mix:
        raise AuthorityResolutionError(
            "EXPORTED_MIX_BATCH_NOT_FOUND",
            "No Approved + Exported Mix Batch is represented in the business Content Ledger.",
        )
    highest_position = max(ledger_position[item["request_id"]] for item in exported_mix)
    latest_mix_candidates = [
        item
        for item in exported_mix
        if ledger_position[item["request_id"]] == highest_position
    ]
    if len(latest_mix_candidates) != 1:
        raise AuthorityResolutionError(
            "CURRENT_AUTHORITY_AMBIGUITY",
            "Latest exported Mix Batch is ambiguous in Content Ledger lineage.",
        )
    latest_mix = latest_mix_candidates[0]
    if explicit_batch_id:
        explicit_batch_id = require_id(explicit_batch_id, "batch_id")
        explicit = [item for item in candidates if item["request_id"] == explicit_batch_id]
        if len(explicit) != 1:
            raise AuthorityResolutionError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                f"--batch-id must resolve to exactly one Approved Batch: {explicit_batch_id}",
            )
        active = explicit[0]
    else:
        active = latest_mix
    presentation_entries = (
        ((ledger["artifact"].get("extensions") or {}).get("presentation_history_v1") or {}).get("entries")
        or []
    )
    news_entries = [
        item
        for item in presentation_entries
        if isinstance(item, dict)
        and item.get("business_id") == business_id
        and item.get("production_profile") == "news"
        and item.get("status") == "exported"
    ]
    latest_news = None
    news_paths: list[Path] = []
    if news_entries:
        entry = news_entries[-1]
        approval_path = validate_file_ref(pipeline_root, entry.get("approval_ref") or {})
        news_output_path = validate_file_ref(pipeline_root, entry.get("export_ref") or {})
        news_receipts = [
            (path, value)
            for path, value in exports
            if value.get("schema_version")
            in {
                "news-excel-export-receipt-v1.0",
                "news-dynamic-excel-export-receipt-v1.0",
            }
            and value.get("request_id") == entry.get("request_id")
            and value.get("output_sha256") == sha256_file(news_output_path)
        ]
        if len(news_receipts) != 1:
            raise AuthorityResolutionError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                "Latest exported News presentation does not resolve to exactly one export receipt.",
            )

        news_receipt_path, news_receipt = news_receipts[0]
        news_paths = [approval_path, news_output_path, news_receipt_path]

        if (
            news_receipt.get("schema_version")
            == "news-dynamic-excel-export-receipt-v1.0"
        ):
            approved_ref = news_receipt.get("approved_news_delivery") or {}
            if (
                approved_ref.get("sha256") != sha256_file(approval_path)
                or news_receipt.get("reuse_intent")
                != "cross_profile_repurpose"
                or news_receipt.get("semantic_novelty") is not False
            ):
                raise AuthorityResolutionError(
                    "CURRENT_AUTHORITY_INVALID",
                    "Latest dynamic News receipt does not validate its Human Approval or repurpose boundary.",
                )

            closure_path = (
                news_receipt_path.parent
                / "news_delivery_export_closure_v1.json"
            )
            if not closure_path.is_file():
                raise AuthorityResolutionError(
                    "CURRENT_AUTHORITY_INCOMPLETE",
                    "Latest dynamic News export is missing Presentation History Closure.",
                )

            closure = read_json(closure_path)
            closure_validation = closure.get("validation") or {}
            closure_export = closure.get("excel_export") or {}
            closure_presentation = closure.get("presentation_history") or {}
            if (
                closure.get("schema_version")
                != "news-delivery-export-closure-v1.0"
                or closure.get("request_id") != entry.get("request_id")
                or closure_validation.get("passed") is not True
                or closure_export.get("sha256")
                != sha256_file(news_output_path)
                or closure_presentation.get("presentation_id")
                != entry.get("presentation_id")
                or closure_presentation.get("semantic_entry_count_delta") != 0
                or closure_presentation.get("semantic_entries_changed") is not False
            ):
                raise AuthorityResolutionError(
                    "CURRENT_AUTHORITY_INVALID",
                    "Latest dynamic News Presentation History Closure is invalid.",
                )

            news_paths.append(closure_path)

        latest_news = {
            "request_id": entry.get("request_id"),
            "status": "EXPORTED",
            "reuse_intent": entry.get("reuse_intent"),
            "semantic_novelty": entry.get("semantic_novelty"),
        }
    return {
        "active": active,
        "latest_approved_mix": latest_approved_mix,
        "latest_mix": latest_mix,
        "latest_news": latest_news,
        "news_paths": news_paths,
    }


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _latest_ledger_operation_time(ledger: dict[str, Any]) -> str | None:
    timestamps: list[str] = []

    for entry in ledger.get("entries") or []:
        if not isinstance(entry, dict):
            continue

        for key in (
            "published_at",
            "exported_at",
            "approved_at",
            "created_at",
        ):
            value = entry.get(key)
            if isinstance(value, str) and value:
                timestamps.append(value)

        for event in entry.get("events") or []:
            if not isinstance(event, dict):
                continue
            value = event.get("at")
            if isinstance(value, str) and value:
                timestamps.append(value)

    history = (
        ((ledger.get("extensions") or {}).get("presentation_history_v1") or {})
        .get("entries")
        or []
    )
    for entry in history:
        if not isinstance(entry, dict):
            continue

        for key in (
            "exported_at",
            "approved_at",
            "created_at",
        ):
            value = entry.get(key)
            if isinstance(value, str) and value:
                timestamps.append(value)

        for event in entry.get("events") or []:
            if not isinstance(event, dict):
                continue
            value = event.get("at")
            if isinstance(value, str) and value:
                timestamps.append(value)

    return max(timestamps) if timestamps else None


def _presentation_entry_is_nonsemantic(entry: dict[str, Any]) -> bool:
    if not isinstance(entry, dict):
        return False

    return (
        entry.get("production_profile") == "news"
        and entry.get("status") == "exported"
        and entry.get("semantic_novelty") is False
        and entry.get("communicated_information_units_created") is False
        and int(entry.get("new_semantic_content_count_delta") or 0) == 0
        and int(entry.get("new_central_claim_count_delta") or 0) == 0
        and int(entry.get("new_information_gain_delta") or 0) == 0
    )


def _capacity_ledger_matches_after_presentation_only_append(
    current_ledger: dict[str, Any],
    expected_canonical_sha256: str,
) -> tuple[bool, int]:
    """Accept only append-only News presentation drift after capacity freeze.

    Post-export capacity is semantic capacity. A later News cross-profile
    repurpose may append Presentation History and update ledger.updated_at
    without changing semantic Content Ledger entries.

    We prove that boundary by reconstructing earlier canonical Ledger states:
    only trailing non-semantic Presentation History entries may be removed,
    and the reconstructed canonical SHA must exactly equal the SHA frozen by
    post_export_remaining_capacity_v1.json.
    """

    if not expected_canonical_sha256:
        return False, 0

    if _canonical_sha256(current_ledger) == expected_canonical_sha256:
        return True, 0

    history_container = (
        (current_ledger.get("extensions") or {}).get("presentation_history_v1")
        or {}
    )
    history = history_container.get("entries") or []
    if not isinstance(history, list) or not history:
        return False, 0

    for removed_count in range(1, len(history) + 1):
        removed = history[-removed_count:]

        if not all(
            _presentation_entry_is_nonsemantic(entry)
            for entry in removed
        ):
            return False, 0

        keep_count = len(history) - removed_count
        candidate = json.loads(
            json.dumps(
                current_ledger,
                ensure_ascii=False,
            )
        )

        candidate_extensions = candidate.get("extensions") or {}
        candidate_history = (
            candidate_extensions.get("presentation_history_v1") or {}
        )
        candidate_history["entries"] = history[:keep_count]

        if keep_count == 0:
            # Try both historical shapes:
            # an empty existing presentation extension, or no extension yet.
            candidate_history["entries"] = []
            candidate_extensions["presentation_history_v1"] = candidate_history
            candidate["extensions"] = candidate_extensions

        latest_time = _latest_ledger_operation_time(candidate)
        if latest_time is not None:
            candidate["updated_at"] = latest_time

        if _canonical_sha256(candidate) == expected_canonical_sha256:
            return True, removed_count

        if keep_count == 0:
            no_extension_candidate = json.loads(
                json.dumps(
                    candidate,
                    ensure_ascii=False,
                )
            )
            no_extension_extensions = (
                no_extension_candidate.get("extensions") or {}
            )
            no_extension_extensions.pop(
                "presentation_history_v1",
                None,
            )
            if no_extension_extensions:
                no_extension_candidate["extensions"] = (
                    no_extension_extensions
                )
            else:
                no_extension_candidate.pop(
                    "extensions",
                    None,
                )

            latest_time = _latest_ledger_operation_time(
                no_extension_candidate
            )
            if latest_time is not None:
                no_extension_candidate["updated_at"] = latest_time

            if (
                _canonical_sha256(no_extension_candidate)
                == expected_canonical_sha256
            ):
                return True, removed_count

    return False, 0



def _resolve_current_console_capacity(
    pipeline_root: Path,
    business: dict[str, Any],
    speaker: dict[str, Any],
    ledger: dict[str, Any],
    active_batch: dict[str, Any],
) -> dict[str, Any]:
    # Current Console V1 stores Approved Batch flat under
    # data/generation_batches/<request_id>/ and closes export/ledger with
    # generation_export_closure_v1.json. It does not write the older
    # post_export_remaining_capacity_v1.json artifact.
    #
    # This path is read-only: reuse the preserved V1.1 candidate pool and
    # re-run only deterministic V1.1.1 gates against Current Ledger.

    request_id = str(
        active_batch.get("request_id")
        or ""
    )

    if not request_id:
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_LINEAGE_INVALID",
            "Active Approved Batch is missing request_id.",
        )

    if active_batch.get("export_status") != "EXPORTED":
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_LINEAGE_INVALID",
            "Current Console capacity fallback requires Approved + Exported Mix Batch.",
        )

    batch_root = (
        pipeline_root
        / "data"
        / "generation_batches"
        / request_id
    )

    closure_path = (
        batch_root
        / "generation_export_closure_v1.json"
    )

    if not closure_path.is_file():
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_NOT_FOUND",
            (
                "Neither legacy post-export capacity nor current "
                f"Generation Export Closure exists for {request_id}."
            ),
        )

    closure = read_json(closure_path)
    approved_ref = closure.get("approved_batch") or {}

    if not (
        closure.get("schema_version") == "generation-export-closure-v1.0"
        and closure.get("request_id") == request_id
        and closure.get("status") == "approved_exported_ledger_closed"
        and approved_ref.get("sha256") == active_batch.get("file_sha256")
    ):
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_LINEAGE_MISMATCH",
            "Generation Export Closure does not validate the Active Approved Batch.",
        )

    entries = list(ledger.get("entries") or [])

    represented = [
        entry
        for entry in entries
        if (
            isinstance(entry, dict)
            and str(entry.get("batch_ref") or "") == request_id
            and str(entry.get("status") or "") in {"exported", "published"}
        )
    ]

    if not represented:
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_LINEAGE_MISMATCH",
            (
                "Generation Export Closure exists, but Current Content Ledger "
                "does not represent the exported Mix Batch."
            ),
        )

    request_path = (
        pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )

    v1_1_path = (
        pipeline_root
        / "data"
        / "content_plans"
        / request_id
        / "content_plan_v1_1.json"
    )

    v1_1_1_path = (
        pipeline_root
        / "data"
        / "content_plans"
        / request_id
        / "content_plan_v1_1_1.json"
    )

    for required in (
        request_path,
        v1_1_path,
        v1_1_1_path,
    ):
        if not required.is_file():
            raise AuthorityResolutionError(
                "CURRENT_CAPACITY_SOURCE_NOT_FOUND",
                f"Current Console capacity source is missing: {required}",
            )

    request = read_json(request_path)
    v1_1 = read_json(v1_1_path)
    prior_v1_1_1 = read_json(v1_1_1_path)

    if not (
        request.get("request_id") == request_id
        and str(request.get("persona_id") or "") == business.get("persona_id")
        and str(request.get("speaker_persona") or "") == speaker.get("persona_id")
        and v1_1.get("request_id") == request_id
        and prior_v1_1_1.get("request_id") == request_id
    ):
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_LINEAGE_MISMATCH",
            "Current Console content-plan lineage does not match Current Customer Truth.",
        )

    prior_lineage = prior_v1_1_1.get("lineage") or {}
    expected_v1_1_sha = prior_lineage.get("source_v1_1_content_plan_sha256")

    if (
        expected_v1_1_sha
        and expected_v1_1_sha != sha256_file(v1_1_path)
    ):
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_LINEAGE_MISMATCH",
            "Stored V1.1.1 Content Plan no longer matches its V1.1 source plan.",
        )

    projected = build_content_plan_v1_1_1(
        v1_1_plan=v1_1,
        ledger=ledger["artifact"],
        request=request,
        source_artifact_hashes={
            "content_plan_v1_1": sha256_file(v1_1_path),
            "content_ledger_v1": ledger["file_sha256"],
        },
    )

    authority = projected.get("authority") or {}
    remote = projected.get("remote_model_call") or {}

    if (
        authority.get("remote_model_called") is not False
        or remote.get("performed") is not False
    ):
        raise AuthorityResolutionError(
            "CURRENT_CAPACITY_BOUNDARY_CROSSED",
            "Current Console capacity reprojection must remain deterministic and zero-model.",
        )

    capacity = projected.get("capacity") or {}
    remaining = capacity.get("high_quality_novel_capacity")

    if (
        not isinstance(remaining, int)
        or isinstance(remaining, bool)
        or remaining < 0
        or capacity.get("padding_generated") is not False
    ):
        raise AuthorityResolutionError(
            "INVALID_CURRENT_CAPACITY",
            "Current Console capacity reprojection returned invalid capacity.",
        )

    return {
        "remaining": remaining,
        "status": capacity.get("status"),
        "path": closure_path,
        "source_path": v1_1_1_path,
        "calculation_mode": "current_console_v1_1_1_reprojection",
        "remote_model_calls": 0,
    }


def resolve_capacity(
    pipeline_root: Path,
    business: dict[str, Any],
    speaker: dict[str, Any],
    ledger: dict[str, Any],
    active_batch: dict[str, Any],
) -> dict[str, Any]:
    path = (
        pipeline_root
        / "data"
        / "content_plans"
        / active_batch["request_id"]
        / "post_export_remaining_capacity_v1.json"
    )
    if not path.is_file():
        return _resolve_current_console_capacity(
            pipeline_root,
            business,
            speaker,
            ledger,
            active_batch,
        )
    value = read_json(path)
    lineage = value.get("lineage") or {}
    if value.get("business_id") != business["persona_id"]:
        raise AuthorityResolutionError(
            "CAPACITY_LINEAGE_MISMATCH", "Capacity business_id does not match Current Customer Truth."
        )
    approved_ref = lineage.get("approved_batch") or {}
    ledger_after = lineage.get("content_ledger_after") or {}
    if approved_ref.get("file_sha256") != active_batch["file_sha256"]:
        raise AuthorityResolutionError(
            "CAPACITY_LINEAGE_MISMATCH", "Capacity does not reference the Active Approved Batch."
        )
    if ledger_after.get("file_sha256") != ledger["file_sha256"]:
        presentation_only_match, appended_presentations = (
            _capacity_ledger_matches_after_presentation_only_append(
                ledger["artifact"],
                str(
                    ledger_after.get("canonical_content_sha256")
                    or ""
                ),
            )
        )

        if not presentation_only_match:
            raise AuthorityResolutionError(
                "CAPACITY_LINEAGE_MISMATCH",
                (
                    "Capacity does not reference the Current Content Ledger, "
                    "and the drift cannot be proven to be append-only "
                    "non-semantic News Presentation History."
                ),
            )

        if appended_presentations <= 0:
            raise AuthorityResolutionError(
                "CAPACITY_LINEAGE_MISMATCH",
                "Content Ledger file SHA changed without a recoverable Presentation History append.",
            )
    source_ref = lineage.get("source_capacity_recalculation") or {}
    source_path = validate_file_ref(pipeline_root, source_ref)
    source = read_json(source_path)
    source_lineage = source.get("lineage") or {}
    if not (
        source.get("business_id") == business["persona_id"]
        and source.get("speaker_id") == speaker["persona_id"]
        and source_lineage.get("business_persona_revision") == business["revision"]
        and source_lineage.get("business_persona_content_sha256") == business["content_sha256"]
        and source_lineage.get("speaker_persona_revision") == speaker["revision"]
        and source_lineage.get("speaker_persona_content_sha256") == speaker["content_sha256"]
    ):
        raise AuthorityResolutionError(
            "CAPACITY_LINEAGE_MISMATCH",
            "Capacity source does not match Current Business/Speaker Persona lineage.",
        )
    remaining = value.get("post_export_remaining_capacity")
    if not isinstance(remaining, int) or remaining < 0 or value.get("padding") is not False:
        raise AuthorityResolutionError(
            "INVALID_CURRENT_CAPACITY", f"Invalid post-export capacity artifact: {path}"
        )
    return {"remaining": remaining, "status": value.get("capacity_status"), "path": path, "source_path": source_path}


def resolve_creative_status(pipeline_root: Path) -> dict[str, Any]:
    registry_path = pipeline_root / "data" / "production_profiles" / "production_profile_registry_v1.json"
    coverage_path = (
        pipeline_root
        / "data"
        / "creative_coverage"
        / "revisions"
        / "news_production_mvp_final_validation_update_v1.json"
    )
    registry = read_json(registry_path)
    coverage = read_json(coverage_path)
    if registry.get("status") != "approved_frozen" or coverage.get("status") != "current_derived_coverage_update":
        raise AuthorityResolutionError(
            "CREATIVE_STATUS_INVALID", "Creative profile registry or active coverage update is invalid."
        )
    pattern_status = coverage.get("pattern_production_validation") or {}
    news_price_status = str(
        (pattern_status.get("pcv1_news_price_offer_led_micro_information") or {}).get(
            "status"
        )
        or "unknown"
    ).upper()
    if news_price_status == "PASSED":
        news_price_status = "VALIDATED"
    return {
        "mix": "AVAILABLE",
        "news_price": news_price_status,
        "news_scene_contrast": str((pattern_status.get("pcv1_news_scene_contrast") or {}).get("status") or "unknown").upper(),
        "paths": [registry_path, coverage_path],
    }


def resolve_footage(
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    active_batch: dict[str, Any],
) -> dict[str, Any]:
    root = pipeline_root / "data" / "production_footage" / active_batch["request_id"]
    required_names = {
        "summary": "production_footage_planning_summary_v1.json",
        "approval": "production_footage_planning_human_approval_v1.json",
        "requirements": "shot_requirement_plan_v1.json",
        "missions": "customer_capture_missions_v1.json",
        "inventory": "production_asset_inventory_v1.json",
        "coverage": "storyboard_coverage_v1.json",
        "rights": "subject_media_use_confirmation_v1.json",
    }
    paths = {key: root / name for key, name in required_names.items()}
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        raise AuthorityResolutionError(
            "FOOTAGE_LINEAGE_NOT_FOUND",
            "Footage artifacts bound to the Active Approved Batch are incomplete: "
            + ", ".join(str(path) for path in missing),
        )
    values = {key: read_json(path) for key, path in paths.items()}
    for key in ("summary", "approval", "requirements", "missions", "coverage"):
        if values[key].get("request_id") != active_batch["request_id"]:
            raise AuthorityResolutionError(
                "FOOTAGE_LINEAGE_MISMATCH", f"{key} is not bound to the Active Batch request."
            )
    requirement_lineage = values["requirements"].get("lineage") or {}
    if requirement_lineage.get("approved_batch_file_sha256") != active_batch["file_sha256"]:
        raise AuthorityResolutionError(
            "FOOTAGE_LINEAGE_MISMATCH", "Shot requirements do not reference the Active Approved Batch."
        )
    summary = values["summary"]
    approval = values["approval"]
    if not (
        str(approval.get("decision") or "").startswith("approved")
        and summary.get("validation", {}).get("human_approval_persisted") is True
        and summary.get("validation", {}).get("passed") is True
    ):
        raise AuthorityResolutionError(
            "FOOTAGE_HUMAN_APPROVAL_REQUIRED", "Footage planning is not Human Approved."
        )
    inventory = values["inventory"]
    rights = values["rights"]
    if inventory.get("business_id") != business_id:
        raise AuthorityResolutionError(
            "FOOTAGE_LINEAGE_MISMATCH", "Production Asset Inventory business_id mismatch."
        )
    if rights.get("business_id") != business_id or rights.get("subject_ref") != speaker_id:
        raise AuthorityResolutionError(
            "RIGHTS_LINEAGE_MISMATCH", "Subject Media status is not bound to the Current Speaker."
        )
    coverage_summary = values["coverage"].get("summary") or {}
    return {
        "planning": "APPROVED",
        "capture_missions": values["missions"].get("mission_count"),
        "capture_pack_status": str(summary.get("customer_capture_pack_status") or "unknown").upper(),
        "sent": bool(summary.get("customer_capture_pack_sent")),
        "registered_assets": inventory.get("asset_count"),
        "eligible_assets": inventory.get("eligible_asset_count"),
        "coverage": {
            "covered": coverage_summary.get("covered"),
            "partially_covered": coverage_summary.get("partially_covered"),
            "capture_required": coverage_summary.get("capture_required"),
            "blocked": coverage_summary.get("blocked"),
            "total": coverage_summary.get("content_count"),
        },
        "speaker_media": str(rights.get("status") or "unknown").upper(),
        "paths": list(paths.values()),
    }


def derive_would_be_next_action(
    active_batch: dict[str, Any], footage: dict[str, Any]
) -> str:
    if active_batch["status"] != "APPROVED":
        return "CONTENT_HUMAN_REVIEW"
    if active_batch["export_status"] != "EXPORTED":
        return "EXPORT_APPROVED_BATCH"
    if footage["planning"] != "APPROVED":
        return "FOOTAGE_PLANNING"
    if footage["capture_pack_status"] == "READY_TO_SEND" and not footage["sent"]:
        return "SEND_CUSTOMER_CAPTURE_PACK"
    if footage["registered_assets"] == 0:
        return "WAIT_FOR_CUSTOMER_ASSETS"
    if footage["coverage"]["capture_required"]:
        return "CHECK_FOOTAGE_COVERAGE"
    return "PRODUCTION_PACKAGE_NOT_IMPLEMENTED"


def public_persona(value: dict[str, Any], pipeline_root: Path) -> dict[str, Any]:
    return {
        "persona_id": value["persona_id"],
        "revision": value["revision"],
        "status": value["status"],
        "evidence_ref": evidence_ref(pipeline_root, value["path"]),
    }


def public_batch(value: dict[str, Any], pipeline_root: Path) -> dict[str, Any]:
    return {
        "request_id": value["request_id"],
        "profile": value["profile"],
        "batch_revision": value["batch_revision"],
        "status": value["status"],
        "export_status": value["export_status"],
        "evidence_ref": evidence_ref(pipeline_root, value["path"]),
    }


def build_customer_status(
    pipeline_root: Path,
    business_id: str,
    *,
    speaker_id: str | None = None,
    batch_id: str | None = None,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()
    business_id = require_id(business_id, "business_id")
    business = resolve_current_persona(pipeline_root, business_id, "business")
    speaker = resolve_speaker_persona(pipeline_root, business, speaker_id)
    ledger = load_content_ledger(pipeline_root, business_id)
    batches = resolve_batches(pipeline_root, business_id, ledger, batch_id)
    active_batch = batches["active"]
    capacity = resolve_capacity(pipeline_root, business, speaker, ledger, active_batch)
    creative = resolve_creative_status(pipeline_root)
    footage = resolve_footage(
        pipeline_root, business_id, speaker["persona_id"], active_batch
    )
    operations_root = pipeline_root / "data" / "operations"
    try:
        controls, controls_path = load_controls(operations_root, business_id)
    except (OSError, ValueError) as exc:
        raise AuthorityResolutionError(
            "OPERATIONAL_CONTROLS_INVALID",
            f"Operational Controls cannot be safely resolved: {exc}",
        ) from exc
    hold = (controls or {}).get("operational_hold") or {
        "active": False,
        "reason": None,
        "release_requires": "explicit_operator_release",
    }
    would_be = derive_would_be_next_action(active_batch, footage)
    primary = (
        "WAIT_FOR_OPERATOR_RELEASE"
        if hold.get("active") is True
        else would_be
    )
    blockers: list[dict[str, str]] = []
    if footage["speaker_media"] == "REVIEW_REQUIRED":
        blockers.append(
            {
                "code": "SPEAKER_MEDIA_REVIEW_REQUIRED_FOR_IDENTIFIABLE_CAPTURE",
                "scope": "identifiable_media_only",
            }
        )
    paths: list[Path] = [
        business["path"],
        business["receipt_path"],
        speaker["path"],
        speaker["receipt_path"],
        ledger["path"],
        active_batch["path"],
        active_batch["receipt_path"],
        capacity["path"],
        capacity["source_path"],
        *creative["paths"],
        *footage["paths"],
        *batches["news_paths"],
    ]
    if active_batch["export_receipt_path"]:
        paths.append(active_batch["export_receipt_path"])
    if controls is not None:
        paths.append(controls_path)
    refs: list[str] = []
    for path in paths:
        ref = evidence_ref(pipeline_root, path)
        if ref not in refs:
            refs.append(ref)
    return {
        "schema_version": SCHEMA_VERSION,
        "business": {"business_id": business_id},
        "customer_truth": {
            "business_persona": public_persona(business, pipeline_root),
            "speaker_persona": public_persona(speaker, pipeline_root),
        },
        "content": {
            "ledger_entries": len(ledger["entries"]),
            "legacy_validation_entry_count": (ledger["artifact"].get("validation") or {}).get("entry_count"),
            "remaining_high_quality_novel_capacity": capacity["remaining"],
            "capacity_status": str(capacity["status"] or "unknown").upper(),
            "latest_approved_mix": public_batch(batches["latest_approved_mix"], pipeline_root),
            "latest_exported_mix": public_batch(batches["latest_mix"], pipeline_root),
            "latest_exported_news": batches["latest_news"],
            "current_active_batch": public_batch(active_batch, pipeline_root),
        },
        "creative": {
            "mix": creative["mix"],
            "news_price": creative["news_price"],
            "news_scene_contrast": creative["news_scene_contrast"],
        },
        "footage": {
            key: value
            for key, value in footage.items()
            if key not in {"speaker_media", "paths"}
        },
        "rights": {
            "speaker_id": speaker["persona_id"],
            "speaker_media": footage["speaker_media"],
        },
        "blockers": blockers,
        "operational_hold": {
            "configured": controls is not None,
            "active": bool(hold.get("active")),
            "reason": hold.get("reason"),
            "release_requires": hold.get("release_requires"),
        },
        "primary_next_action": primary,
        "would_be_next_action": would_be if hold.get("active") is True else None,
        "evidence_refs": refs,
        "model_calls": {"remote": 0, "local": 0},
    }


def render_text(status: dict[str, Any]) -> str:
    truth = status["customer_truth"]
    content = status["content"]
    creative = status["creative"]
    footage = status["footage"]
    rights = status["rights"]
    hold = status["operational_hold"]
    coverage = footage["coverage"]
    business_persona = truth["business_persona"]
    speaker_persona = truth["speaker_persona"]
    mix = content["latest_exported_mix"]
    lines = [
        "AI VIDEO OPS — CUSTOMER STATUS",
        "",
        "Business",
        status["business"]["business_id"],
        "",
        "Customer Truth",
        f"Business Persona       Rev{business_persona['revision']} / {business_persona['status']}",
        f"Speaker Persona        Rev{speaker_persona['revision']} / {speaker_persona['status']}",
        "",
        "Content",
        f"Ledger Entries         {content['ledger_entries']}",
        f"Remaining Capacity     {content['remaining_high_quality_novel_capacity']}",
        f"Latest Mix Batch       {mix['request_id']}",
        f"Mix Status             {mix['status']} / {mix['export_status']}",
        "",
        "Creative",
        f"Mix                    {creative['mix']}",
        f"News Price             {creative['news_price']}",
        f"News Scene Contrast    {creative['news_scene_contrast']}",
        "",
        "Footage",
        f"Planning               {footage['planning']}",
        f"Capture Missions       {footage['capture_missions']}",
        f"Capture Pack           {footage['capture_pack_status']}",
        f"Sent                   {str(footage['sent']).lower()}",
        f"Registered Assets      {footage['registered_assets']}",
        f"Eligible Assets        {footage['eligible_assets']}",
        f"Coverage               {coverage['covered']}/{coverage['total']} covered",
        f"                       {coverage['capture_required']}/{coverage['total']} capture_required",
        "",
        "Rights",
        f"{speaker_persona['persona_id']}    {rights['speaker_media']}",
        "",
        "Operational Hold",
        "ACTIVE" if hold["active"] else "INACTIVE",
        "",
        "Primary Next Action",
        status["primary_next_action"],
    ]
    if status["would_be_next_action"]:
        lines.extend(("", "Would-be Next Action", status["would_be_next_action"]))
    return "\n".join(lines)


def blocked_status(business_id: str, exc: AuthorityResolutionError) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "business": {"business_id": business_id},
        "customer_truth": None,
        "content": None,
        "creative": None,
        "footage": None,
        "rights": None,
        "blockers": [{"code": exc.code, "message": str(exc)}],
        "operational_hold": None,
        "primary_next_action": "RESOLVE_AUTHORITY_BLOCKER",
        "would_be_next_action": None,
        "evidence_refs": exc.evidence_refs,
        "model_calls": {"remote": 0, "local": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only, derived-only Current Customer Status projection."
    )
    parser.add_argument("--business-id", required=True)
    parser.add_argument("--speaker-id")
    parser.add_argument("--batch-id")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--pipeline-root",
        default=str(Path(__file__).resolve().parents[1]),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    try:
        status = build_customer_status(
            Path(args.pipeline_root),
            args.business_id,
            speaker_id=args.speaker_id,
            batch_id=args.batch_id,
        )
    except AuthorityResolutionError as exc:
        status = blocked_status(args.business_id, exc)
        if args.format == "json":
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print("AI VIDEO OPS — CUSTOMER STATUS")
            print(f"\nBusiness\n{args.business_id}")
            print(f"\nBlocker\n{exc.code}: {exc}")
            print("\nPrimary Next Action\nRESOLVE_AUTHORITY_BLOCKER")
        sys.exit(2)
    if args.format == "json":
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(render_text(status))


if __name__ == "__main__":
    main()
