from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from content_quality_v1 import (
    LEDGER_SCHEMA_VERSION,
    STRONG_MEMORY_STATUSES,
    build_exported_semantic_ledger_update,
    build_fact_atom_catalog,
    canonical_sha256,
    replace_ledger_after_export,
)
from generate_mix_scripts_v1 import (
    safe_persona_projection,
    safe_speaker_projection,
)


CLOSURE_SCHEMA_VERSION = "generation-export-closure-v1.0"


class ExportClosureError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExportClosureError(
            "EXPORT_CLOSURE_ARTIFACT_INVALID",
            f"Cannot read artifact: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise ExportClosureError(
            "EXPORT_CLOSURE_ARTIFACT_INVALID",
            f"Artifact must be a JSON object: {path}",
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise ExportClosureError(
            "EXPORT_CLOSURE_ARTIFACT_CONFLICT",
            f"Immutable artifact already exists: {path}",
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _resolve_lineage_file(
    ref: dict[str, Any],
    label: str,
) -> Path:
    path = Path(str(ref.get("path") or "")).expanduser().resolve()
    expected = str(ref.get("file_sha256") or "")
    if not path.is_file() or not expected:
        raise ExportClosureError(
            "EXPORT_CLOSURE_LINEAGE_MISSING",
            f"{label} lineage is incomplete.",
        )
    if sha256_file(path) != expected:
        raise ExportClosureError(
            "EXPORT_CLOSURE_LINEAGE_MISMATCH",
            f"{label} SHA-256 does not match immutable Generation Request lineage.",
        )
    return path


def _empty_ledger(
    *,
    business_id: str,
    created_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "created_at": created_at,
        "updated_at": created_at,
        "business_id": business_id,
        "storage_policy": "append_only_entries_v1",
        "novelty_authority": {
            "strong_memory_statuses": sorted(STRONG_MEMORY_STATUSES),
            "generated_or_rejected_drafts_permanently_reserve_semantic_space": False,
        },
        "entries": [],
        "fact_atom_catalog": [],
        "fact_usage_pressure": [],
        "historical_exposure_summary": {
            "explicit_fact_atom_refs": [],
            "communication_role_distribution": {},
            "strong_content_count": 0,
            "explicit_information_unit_count": 0,
        },
        "validation": {
            "passed": True,
            "entry_count": 0,
            "strong_memory_count": 0,
            "baseline_not_mutated": True,
        },
    }


def _build_fact_atoms(
    persona: dict[str, Any],
    persona_sha: str,
    speaker: dict[str, Any],
    speaker_sha: str,
) -> list[dict[str, Any]]:
    business_safe_fields = set(
        (safe_persona_projection(persona).get("facts") or {}).keys()
    )
    speaker_safe_fields = set(
        (safe_speaker_projection(speaker).get("facts") or {}).keys()
    )
    return (
        build_fact_atom_catalog(
            persona,
            persona_sha,
            business_safe_fields,
        )
        + build_fact_atom_catalog(
            speaker,
            speaker_sha,
            speaker_safe_fields,
        )
    )


def _build_export_entries(
    *,
    approved: dict[str, Any],
    approved_batch_path: Path,
    approval_receipt_path: Path,
    excel_path: Path,
    exported_at: str,
) -> list[dict[str, Any]]:
    approved_at = str(
        (approved.get("human_review") or {}).get("reviewed_at")
        or exported_at
    )
    entries: list[dict[str, Any]] = []

    for item in approved.get("contents") or []:
        if item.get("status") != "human_approved":
            raise ExportClosureError(
                "EXPORT_CLOSURE_NON_APPROVED_CONTENT",
                "Only Human Approved content may enter exported Strong Memory.",
            )

        persona_ref = item.get("persona_ref") or {}
        speaker_ref = item.get("speaker_ref") or {}
        speaker_fact_refs = (
            item.get("speaker_fact_refs_used")
            or item.get("speaker_fact_refs")
            or []
        )

        entries.append(
            {
                "content_id": item["content_id"],
                "concept_ref": item.get("concept_ref"),
                "business_id": persona_ref.get("persona_id"),
                "speaker_id": speaker_ref.get("persona_id"),
                "production_profile": approved.get("profile"),
                "reuse_intent": approved.get("reuse_intent") or "novel_content",
                "batch_ref": approved.get("request_id"),
                "semantic_signature": item.get("semantic_signature"),
                "presentation_signature": item.get("presentation_signature"),
                "central_claim": item.get("central_claim"),
                "title": item.get("title"),
                "narration": item.get("narration"),
                "primary_fact_refs": sorted(
                    set(item.get("primary_persona_fact_refs") or [])
                    | set(speaker_fact_refs)
                ),
                "supporting_fact_refs": (
                    item.get("optional_secondary_fact_refs") or []
                ),
                "primary_fact_atom_refs": (
                    item.get("primary_fact_atoms") or []
                ),
                "exclusive_anchor": item.get("exclusive_anchor"),
                "customer_specificity_class": (
                    (item.get("editorial_summary") or {}).get(
                        "customer_specificity_class",
                        "customer_specific",
                    )
                ),
                "status": "exported",
                "created_at": approved.get("created_at"),
                "approved_at": approved_at,
                "exported_at": exported_at,
                "published_at": None,
                "events": [
                    {
                        "status": "approved",
                        "at": approved_at,
                        "source": "generation_batch_human_approval_v1",
                    },
                    {
                        "status": "exported",
                        "at": exported_at,
                        "source": "mix_excel_export_v1",
                    },
                ],
                "lineage": {
                    "approved_batch_sha256": sha256_file(
                        approved_batch_path
                    ),
                    "approval_receipt_sha256": sha256_file(
                        approval_receipt_path
                    ),
                    "excel_sha256": sha256_file(excel_path),
                },
            }
        )

    if not entries:
        raise ExportClosureError(
            "EXPORT_CLOSURE_EMPTY_BATCH",
            "Approved Generation Batch contains no exportable content.",
        )
    return entries


def _validate_existing_entries(
    ledger: dict[str, Any],
    new_entries: list[dict[str, Any]],
) -> bool:
    current = {
        str(entry.get("content_id") or ""): entry
        for entry in ledger.get("entries") or []
    }
    ids = [str(entry["content_id"]) for entry in new_entries]
    present = [content_id in current for content_id in ids]

    if not any(present):
        return False

    if not all(present):
        raise ExportClosureError(
            "EXPORT_CLOSURE_PARTIAL_LEDGER_WRITE",
            "Only part of the current exported Batch is already present in Content Ledger.",
        )

    for expected in new_entries:
        actual = current[str(expected["content_id"])]
        if (
            actual.get("status") != "exported"
            or actual.get("batch_ref") != expected.get("batch_ref")
            or actual.get("central_claim") != expected.get("central_claim")
            or actual.get("title") != expected.get("title")
            or actual.get("narration") != expected.get("narration")
        ):
            raise ExportClosureError(
                "EXPORT_CLOSURE_LEDGER_CONFLICT",
                "Existing Content Ledger entry differs from the current exported Batch.",
            )
    return True


def _validate_recovered_closure(
    *,
    closure: dict[str, Any],
    request_id: str,
    approved_batch_path: Path,
    excel_path: Path,
    ledger_path: Path,
) -> None:
    if (
        closure.get("schema_version") != CLOSURE_SCHEMA_VERSION
        or closure.get("request_id") != request_id
        or (closure.get("validation") or {}).get("passed") is not True
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_RECOVERY_INVALID",
            "Existing Export Closure artifact is invalid.",
        )

    if (
        (closure.get("approved_batch") or {}).get("sha256")
        != sha256_file(approved_batch_path)
        or (closure.get("excel_export") or {}).get("sha256")
        != sha256_file(excel_path)
        or not ledger_path.is_file()
        or (closure.get("content_ledger") or {}).get("sha256_after")
        != sha256_file(ledger_path)
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_RECOVERY_LINEAGE_MISMATCH",
            "Existing Export Closure lineage no longer matches canonical artifacts.",
        )


def historical_ledger_material(root, request_id, kind, exported_at):
    """Frozen Native sources for full semantic replay, without a current gate."""
    from profile_compatibility_decisions_v1_1 import ref, resolve_ref
    from delivery_receipt_recovery_v1 import human_state, validate_export_receipt
    from export_mix_excel_v1 import validate_workbook
    directory=Path(root)/'data/generation_batches'/request_id
    request_path=Path(root)/'data/generation_requests'/request_id/'generation_request_v1.json'
    request=read_json(request_path);approved_path=directory/'approved_generation_batch_v1.json'
    approved=read_json(approved_path);human=directory/'generation_batch_approval_receipt.json'
    state=human_state(directory)
    if kind!='mix_semantic' or not state['completed'] or not state['approved']:
        from ledger_history_v1 import LedgerHistoryError
        raise LedgerHistoryError('HUMAN_PROOF_REQUIRED')
    intent_path=directory/'generation_export_intent_v1.json'
    intent=read_json(intent_path)
    output=Path(root)/intent['output_path'];receipt_path=output.with_suffix('.export_receipt.json')
    receipt=read_json(receipt_path);validate_export_receipt(root,receipt,output,request_id=request_id)
    template=resolve_ref(root,intent['template_ref'])
    validate_workbook(output,template,approved['contents'])
    persona=_resolve_lineage_file(request['lineage']['business_persona_ref'],'Business Persona')
    speaker=_resolve_lineage_file(request['lineage']['speaker_persona_ref'],'Speaker Persona')
    sources={k:ref(root,p) for k,p in {'request':request_path,'approved':approved_path,'human':human,
        'review':directory/'generation_human_review_v2.json','receipt':receipt_path,'output':output,
        'business':persona,'speaker':speaker,'intent':intent_path,'template':template,
        'publication':directory/'generation_export_publication_v1.json'}.items()}
    return {'kind':kind,'request_id':request_id,'source_refs':sources,'exported_at':exported_at,
        'entries':_build_export_entries(approved=approved,approved_batch_path=approved_path,
            approval_receipt_path=human,excel_path=output,exported_at=exported_at),
        'fact_atoms':_build_fact_atoms(read_json(persona),sha256_file(persona),read_json(speaker),sha256_file(speaker)),
        'receipt_path':receipt_path,'closure_path':directory/'generation_export_closure_v1.json'}


def validate_historical_core_bundle(root, request_id, ledger_snapshot):
    """Explicit A0 reader. The original v1.0 reader above remains unchanged."""
    from profile_compatibility_decisions_v1_1 import ref
    from ledger_history_v1 import LedgerHistoryError
    directory=Path(root)/'data/generation_batches'/request_id
    closure_path=directory/'generation_export_closure_v1.json';closure=read_json(closure_path)
    recipe=historical_ledger_material(root,request_id,'mix_semantic',closure['created_at'])
    sources=recipe['source_refs'];approved=Path(root)/sources['approved']['path'];output=recipe['receipt_path'].with_suffix('.xlsx')
    # .export_receipt.json is not a workbook suffix; use the Native output ref.
    output=Path(root)/sources['output']['path']
    _validate_recovered_closure(closure=closure,request_id=request_id,approved_batch_path=approved,
        excel_path=output,ledger_path=Path(ledger_snapshot))
    request=read_json(Path(root)/sources['request']['path'])
    ledger=read_json(ledger_snapshot)
    if (ledger.get('business_id')!=request['persona_id'] or ledger.get('schema_version')!=LEDGER_SCHEMA_VERSION
        or canonical_sha256(ledger)!=closure['content_ledger']['canonical_sha256_after']
        or closure['approval_receipt']['sha256']!=sources['human']['sha256']
        or closure['excel_export']['receipt_sha256']!=sources['receipt']['sha256']):
        raise LedgerHistoryError('CORE_BUNDLE_INVALID')
    _validate_existing_entries(ledger,recipe['entries'])
    return {'closure_ref':ref(root,closure_path),'approved_ref':sources['approved'],
        'approval_receipt_ref':sources['human'],'xlsx_ref':sources['output'],'export_receipt_ref':sources['receipt']}


def verify_generation_export_anchor(*, pipeline_root, request_id):
    from ledger_history_v1 import validate_anchor
    return validate_anchor(Path(pipeline_root),request_id)


def read_completed_generation_export(*, pipeline_root, request_id, excel_path):
    """Explicit reader dispatch. Unknown/invalid anchor never downgrades."""
    from ledger_history_v1 import anchor_path
    root=Path(pipeline_root)
    if not anchor_path(root,request_id).is_file():
        return close_generation_export(pipeline_root=root,request_id=request_id,excel_path=Path(excel_path),verify_only=True)
    verified=verify_generation_export_anchor(pipeline_root=root,request_id=request_id)
    closure_path=root/verified['closure_ref']['path'];closure=read_json(closure_path)
    if Path(closure['excel_export']['path']).resolve()!=Path(excel_path).resolve():
        raise ExportClosureError('EXPORT_CLOSURE_EXCEL_LINEAGE_MISMATCH','Original Excel identity differs')
    return {'ok':True,'request_id':request_id,'recovered':True,'closure_path':str(closure_path),
        'closure_sha256':sha256_file(closure_path),'content_ledger_path':str(root/verified['ledger_ref']['path']),
        'content_ledger_sha256':verified['ledger_ref']['sha256'],
        'appended_content_ids':closure['content_ledger']['appended_content_ids'],
        'remote_model_called':False,'stop_point_reached':True,'history_anchor_ref':verified['anchor_ref']}


def ensure_generation_export_anchor(*, pipeline_root, request_id):
    from ledger_history_v1 import ensure_anchor, validate_anchor, finish_request
    root=Path(pipeline_root);directory=root/'data/generation_batches'/request_id
    closure=read_json(directory/'generation_export_closure_v1.json')
    request=read_json(root/'data/generation_requests'/request_id/'generation_request_v1.json')
    finish_request(root,request['persona_id'],request_id,Path(closure['excel_export']['receipt_path']),
                   directory/'generation_export_closure_v1.json')
    ensure_anchor(root,request_id)
    return validate_anchor(root,request_id)


from profile_compatibility_consumers_v1_1 import guarded as compatibility_guarded


@compatibility_guarded
def close_generation_export(
    *,
    pipeline_root: Path,
    request_id: str,
    excel_path: Path,
    verify_only: bool = False,
    authorization_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()
    excel_path = excel_path.expanduser().resolve()

    request_path = (
        pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )
    batch_root = (
        pipeline_root
        / "data"
        / "generation_batches"
        / request_id
    )
    approved_batch_path = (
        batch_root / "approved_generation_batch_v1.json"
    )
    approval_receipt_path = (
        batch_root / "generation_batch_approval_receipt.json"
    )
    closure_path = (
        batch_root / "generation_export_closure_v1.json"
    )
    export_receipt_path = excel_path.with_suffix(
        ".export_receipt.json"
    )

    for path in (
        request_path,
        approved_batch_path,
        approval_receipt_path,
        excel_path,
        export_receipt_path,
    ):
        if not path.is_file():
            raise ExportClosureError(
                "EXPORT_CLOSURE_REQUIRED_ARTIFACT_MISSING",
                f"Required export-closure artifact is missing: {path}",
            )

    request = read_json(request_path)
    approved = read_json(approved_batch_path)
    approval_receipt = read_json(approval_receipt_path)
    from generation_recovery_v1 import validate_approved_source
    validate_approved_source(pipeline_root, request_id, approved, approval_receipt)
    export_receipt = read_json(export_receipt_path)
    from delivery_receipt_recovery_v1 import validate_export_receipt
    validate_export_receipt(pipeline_root, export_receipt, excel_path, request_id=request_id)

    if (
        str(request.get("request_id") or "") != request_id
        or str(approved.get("request_id") or "") != request_id
        or approved.get("status") != "approved"
        or approved.get("profile") != "mix"
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_BATCH_AUTHORITY_INVALID",
            "Export Closure requires the matching Approved Mix Generation Batch.",
        )

    if (
        approval_receipt.get("status") != "approved"
        or (approval_receipt.get("approved_batch") or {}).get("sha256")
        != sha256_file(approved_batch_path)
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_APPROVAL_LINEAGE_MISMATCH",
            "Generation Batch Approval Receipt does not authorize this Approved Batch.",
        )

    if (
        export_receipt.get("validation_passed") is not True
        or export_receipt.get("batch_sha256")
        != sha256_file(approved_batch_path)
        or export_receipt.get("output_sha256")
        != sha256_file(excel_path)
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_EXCEL_LINEAGE_MISMATCH",
            "Excel Export Receipt does not validate this Approved Batch and Excel output.",
        )

    business_id = str(request.get("persona_id") or "")
    if not business_id:
        raise ExportClosureError(
            "EXPORT_CLOSURE_BUSINESS_ID_MISSING",
            "Generation Request has no business persona identity.",
        )

    ledger_path = (
        pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )

    if verify_only and not closure_path.is_file():
        raise ExportClosureError('EXPORT_CLOSURE_REQUIRED_ARTIFACT_MISSING', 'No completed canonical Closure exists')
    if closure_path.is_file():
        closure = read_json(closure_path)
        _validate_recovered_closure(
            closure=closure,
            request_id=request_id,
            approved_batch_path=approved_batch_path,
            excel_path=excel_path,
            ledger_path=ledger_path,
        )
        if not verify_only and (batch_root/'generation_export_intent_v1.json').is_file():
            ensure_generation_export_anchor(pipeline_root=pipeline_root,request_id=request_id)
        return {
            "ok": True,
            "request_id": request_id,
            "recovered": True,
            "closure_path": str(closure_path),
            "closure_sha256": sha256_file(closure_path),
            "content_ledger_path": str(ledger_path),
            "content_ledger_sha256": sha256_file(ledger_path),
            "appended_content_ids": (
                (closure.get("content_ledger") or {}).get(
                    "appended_content_ids"
                )
                or []
            ),
            "remote_model_called": False,
            "stop_point_reached": True,
        }

    lineage = request.get("lineage") or {}
    persona_path = _resolve_lineage_file(
        lineage.get("business_persona_ref") or {},
        "Business Persona",
    )
    speaker_path = _resolve_lineage_file(
        lineage.get("speaker_persona_ref") or {},
        "Speaker Persona",
    )
    persona = read_json(persona_path)
    from customer_constraints_v1 import assert_publication_allowed, publication_text
    assert_publication_allowed(persona, persona_path, [publication_text(v) for v in approved.get("contents", [])])
    speaker = read_json(speaker_path)

    if (
        persona.get("persona_id") != business_id
        or speaker.get("persona_id")
        != request.get("speaker_persona")
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_PERSONA_IDENTITY_MISMATCH",
            "Persona identity does not match immutable Generation Request.",
        )

    fact_atoms = _build_fact_atoms(
        persona,
        sha256_file(persona_path),
        speaker,
        sha256_file(speaker_path),
    )

    exported_at = datetime.fromtimestamp(
        excel_path.stat().st_mtime,
        tz=timezone.utc,
    ).isoformat()

    new_entries = _build_export_entries(
        approved=approved,
        approved_batch_path=approved_batch_path,
        approval_receipt_path=approval_receipt_path,
        excel_path=excel_path,
        exported_at=exported_at,
    )

    if any(
        entry.get("business_id") != business_id
        for entry in new_entries
    ):
        raise ExportClosureError(
            "EXPORT_CLOSURE_BUSINESS_LINEAGE_MISMATCH",
            "Approved content Business Persona differs from Generation Request.",
        )

    def authorize_pending_closure():
        from delivery_receipt_recovery_v1 import export_paths,check,EXPORT,identity,source_snapshot,ReceiptRecoveryError
        from generation_recovery_v1 import resolve_ref
        intent_path,_=export_paths(pipeline_root,request_id)
        if intent_path.is_file():
            intent=check(read_json(intent_path),EXPORT);identity(authorization_context,intent)
            if source_snapshot(pipeline_root,resolve_ref(pipeline_root,intent['sources']['batch_ref']))!=intent['sources']:
                raise ReceiptRecoveryError('DELIVERY_SOURCE_CHANGED','Source changed before native Closure')
    authorize_pending_closure()
    ledger_existed = ledger_path.is_file()
    if ledger_existed:
        ledger_before = read_json(ledger_path)
        if (
            ledger_before.get("schema_version")
            != LEDGER_SCHEMA_VERSION
            or ledger_before.get("business_id")
            != business_id
        ):
            raise ExportClosureError(
                "EXPORT_CLOSURE_LEDGER_AUTHORITY_INVALID",
                "Existing canonical Content Ledger is invalid for this business.",
            )
    else:
        ledger_before = _empty_ledger(
            business_id=business_id,
            created_at=str(
                request.get("created_at")
                or exported_at
            ),
        )

    ledger_file_sha_before = (
        sha256_file(ledger_path)
        if ledger_existed
        else None
    )
    ledger_content_sha_before = canonical_sha256(
        ledger_before
    )

    already_appended = _validate_existing_entries(
        ledger_before,
        new_entries,
    )

    if already_appended:
        prospective_ledger = ledger_before
        ledger_file_sha_after = sha256_file(
            ledger_path
        )
    else:
        prospective_ledger = (
            build_exported_semantic_ledger_update(
                ledger_before,
                new_entries,
                fact_atoms,
                exported_at=exported_at,
            )
        )
        prospective_ledger["validation"] = {
            "passed": True,
            "entry_count": len(
                prospective_ledger.get("entries") or []
            ),
            "strong_memory_count": sum(
                str(entry.get("status") or "")
                in STRONG_MEMORY_STATUSES
                for entry in (
                    prospective_ledger.get("entries")
                    or []
                )
            ),
            "baseline_not_mutated": True,
            "latest_export_request_id": request_id,
        }

        authorize_pending_closure()
        if ledger_existed:
            ledger_file_sha_after = (
                replace_ledger_after_export(
                    ledger_path,
                    ledger_before,
                    prospective_ledger,
                    history_context={'root':pipeline_root,'business':business_id,'request_id':request_id,
                        'kind':'mix_semantic','exported_at':exported_at}
                    if (batch_root/'generation_export_intent_v1.json').is_file() else None,
                )
            )
        else:
            from contextlib import nullcontext
            from ledger_history_v1 import transition, bytes_for
            scope=transition(pipeline_root,business_id,request_id,'mix_semantic',ledger_before,prospective_ledger,
                exported_at=exported_at,after_bytes=bytes_for(prospective_ledger)) if (batch_root/'generation_export_intent_v1.json').is_file() else nullcontext()
            with scope:
                ledger_file_sha_after = write_new_json(ledger_path, prospective_ledger)

    persisted = read_json(ledger_path)
    _validate_existing_entries(
        persisted,
        new_entries,
    )

    closure = {
        "schema_version": CLOSURE_SCHEMA_VERSION,
        "created_at": exported_at,
        "request_id": request_id,
        "status": "approved_exported_ledger_closed",
        "approved_batch": {
            "path": str(
                approved_batch_path.resolve()
            ),
            "sha256": sha256_file(
                approved_batch_path
            ),
        },
        "approval_receipt": {
            "path": str(
                approval_receipt_path.resolve()
            ),
            "sha256": sha256_file(
                approval_receipt_path
            ),
        },
        "excel_export": {
            "path": str(excel_path),
            "sha256": sha256_file(excel_path),
            "receipt_path": str(
                export_receipt_path.resolve()
            ),
            "receipt_sha256": sha256_file(
                export_receipt_path
            ),
        },
        "content_ledger": {
            "path": str(ledger_path.resolve()),
            "existed_before": ledger_existed,
            "sha256_before": ledger_file_sha_before,
            "canonical_sha256_before": (
                ledger_content_sha_before
            ),
            "sha256_after": (
                ledger_file_sha_after
            ),
            "canonical_sha256_after": (
                canonical_sha256(
                    read_json(ledger_path)
                )
            ),
            "appended_content_ids": [
                entry["content_id"]
                for entry in new_entries
            ],
            "append_only": True,
            "already_appended_recovery": (
                already_appended
            ),
        },
        "authority": {
            "human_approval_required": True,
            "excel_export_required": True,
            "content_ledger_append_after_approval_and_export_only": True,
            "generated_or_rejected_drafts_are_not_strong_memory": True,
            "remote_model_calls": 0,
        },
        "validation": {
            "passed": True,
            "approved_item_count": len(
                approved.get("contents") or []
            ),
            "exported_item_count": len(
                new_entries
            ),
            "ledger_entries_verified": True,
        },
    }

    authorize_pending_closure()
    closure_sha = write_new_json(
        closure_path,
        closure,
    )
    if (batch_root/'generation_export_intent_v1.json').is_file():
        ensure_generation_export_anchor(pipeline_root=pipeline_root,request_id=request_id)

    return {
        "ok": True,
        "request_id": request_id,
        "recovered": False,
        "closure_path": str(
            closure_path.resolve()
        ),
        "closure_sha256": closure_sha,
        "content_ledger_path": str(
            ledger_path.resolve()
        ),
        "content_ledger_sha256": (
            sha256_file(ledger_path)
        ),
        "appended_content_ids": [
            entry["content_id"]
            for entry in new_entries
        ],
        "remote_model_called": False,
        "stop_point_reached": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Close one Approved + Exported Mix Generation "
            "Request into the canonical Content Ledger."
        )
    )
    parser.add_argument(
        "--request-id",
        required=True,
    )
    parser.add_argument(
        "--pipeline-root",
        default=str(
            Path(__file__).resolve().parents[1]
        ),
    )
    parser.add_argument(
        "--excel",
        required=True,
    )
    parser.add_argument('--authorization-file')
    parser.add_argument('--verify-history', action='store_true',
        help='Read-only versioned completed-export verification; never repair or enqueue.')
    args = parser.parse_args()

    try:
        if args.verify_history:
            result = read_completed_generation_export(pipeline_root=Path(args.pipeline_root),
                request_id=str(args.request_id).strip(), excel_path=Path(args.excel))
        else:
            result = close_generation_export(
                pipeline_root=Path(args.pipeline_root),
                request_id=str(args.request_id).strip(), excel_path=Path(args.excel),
                authorization_context=read_json(Path(args.authorization_file)) if args.authorization_file else None)
    except (ExportClosureError, RuntimeError, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": getattr(exc, 'code', 'EXPORT_HISTORY_VERIFICATION_FAILED'),
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(
        json.dumps(
            result,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
