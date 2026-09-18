from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import close_generation_export_v1 as subject
from content_quality_v1 import build_fact_atom_catalog
from generate_mix_scripts_v1 import safe_persona_projection


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def fixture_runtime(tmp_path: Path) -> tuple[str, Path]:
    request_id = "gen_fixture_export_001"
    business_id = "customer_fixture_pet"
    speaker_id = "speaker_fixture_owner"

    persona = {
        "persona_id": business_id,
        "persona_scope": "business",
        "revision": 1,
        "facts": {
            "public_display_name": {
                "state": "known",
                "value": "小爪宠物店",
                "source_refs": [],
            },
            "process_facts": {
                "state": "known",
                "value": [
                    "洗护前先检查宠物的皮肤和毛发状态",
                ],
                "source_refs": [],
            },
        },
    }
    speaker = {
        "persona_id": speaker_id,
        "persona_scope": "speaker",
        "revision": 1,
        "speaker_type": "owner_founder",
        "facts": {
            "public_display_name": {
                "state": "known",
                "value": "王琳",
                "source_refs": [],
            },
            "public_role": {
                "state": "known",
                "value": "店主",
                "source_refs": [],
            },
        },
    }

    persona_path = tmp_path / "persona.json"
    speaker_path = tmp_path / "speaker.json"
    write_json(persona_path, persona)
    write_json(speaker_path, speaker)

    request = {
        "schema_version": "generation-request-v1.0",
        "request_id": request_id,
        "persona_id": business_id,
        "speaker_persona": speaker_id,
        "profile": "mix",
        "quantity": 1,
        "created_at": "2026-09-18T10:00:00+08:00",
        "lineage": {
            "business_persona_ref": {
                "path": str(persona_path.resolve()),
                "file_sha256": sha256(persona_path),
            },
            "speaker_persona_ref": {
                "path": str(speaker_path.resolve()),
                "file_sha256": sha256(speaker_path),
            },
        },
    }
    request_path = (
        tmp_path
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )
    write_json(request_path, request)

    safe_fields = set(
        safe_persona_projection(persona)["facts"]
    )
    atoms = build_fact_atom_catalog(
        persona,
        sha256(persona_path),
        safe_fields,
    )
    process_atom = next(
        atom
        for atom in atoms
        if atom["field"] == "process_facts"
    )

    batch_root = (
        tmp_path
        / "data"
        / "generation_batches"
        / request_id
    )
    approved_path = (
        batch_root
        / "approved_generation_batch_v1.json"
    )
    approved = {
        "schema_version": "approved-generation-batch-v1.0",
        "request_id": request_id,
        "profile": "mix",
        "status": "approved",
        "created_at": "2026-09-18T10:02:00+08:00",
        "human_review": {
            "reviewed_at": "2026-09-18T10:03:00+08:00",
        },
        "contents": [
            {
                "content_id": f"{request_id}-C001",
                "concept_ref": "CONCEPT_001",
                "status": "human_approved",
                "persona_ref": {
                    "persona_id": business_id,
                },
                "speaker_ref": {
                    "persona_id": speaker_id,
                },
                "semantic_signature": {
                    "primary_fact_bundle": [
                        "process_facts",
                    ],
                },
                "presentation_signature": {
                    "opening_strategy": "direct",
                },
                "central_claim": (
                    "宠物洗护开始前先检查皮肤和毛发状态。"
                ),
                "title": "洗护前，先看皮肤和毛发",
                "narration": (
                    "洗护前先检查宠物的皮肤和毛发状态。"
                ),
                "primary_persona_fact_refs": [
                    "process_facts",
                ],
                "optional_secondary_fact_refs": [],
                "speaker_fact_refs_used": [],
                "primary_fact_atoms": [
                    process_atom["fact_atom_id"],
                ],
                "editorial_summary": {
                    "customer_specificity_class": (
                        "customer_specific"
                    )
                },
            }
        ],
    }
    write_json(approved_path, approved)

    approval_receipt = {
        "schema_version": (
            "generation-batch-approval-receipt-v1.0"
        ),
        "request_id": request_id,
        "status": "approved",
        "approved_batch": {
            "path": str(approved_path.resolve()),
            "sha256": sha256(approved_path),
        },
    }
    write_json(
        batch_root
        / "generation_batch_approval_receipt.json",
        approval_receipt,
    )

    excel = (
        tmp_path
        / "output"
        / "小爪宠物店_王琳_Mix混剪_1条_20260918_fixture.xlsx"
    )
    excel.parent.mkdir(parents=True, exist_ok=True)
    excel.write_bytes(b"fixture-excel")

    export_receipt = {
        "schema_version": (
            "mix-excel-export-receipt-v1.0"
        ),
        "batch_sha256": sha256(approved_path),
        "output_sha256": sha256(excel),
        "exported_row_count": 1,
        "validation_passed": True,
    }
    write_json(
        excel.with_suffix(
            ".export_receipt.json"
        ),
        export_receipt,
    )

    return request_id, excel


def test_export_closure_creates_strong_ledger_and_recovers(
    tmp_path: Path,
):
    request_id, excel = fixture_runtime(
        tmp_path
    )

    first = subject.close_generation_export(
        pipeline_root=tmp_path,
        request_id=request_id,
        excel_path=excel,
    )

    assert first["ok"] is True
    assert first["recovered"] is False
    assert first["remote_model_called"] is False
    assert first["stop_point_reached"] is True

    ledger_path = Path(
        first["content_ledger_path"]
    )
    ledger = subject.read_json(
        ledger_path
    )

    assert ledger["business_id"] == (
        "customer_fixture_pet"
    )
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["status"] == (
        "exported"
    )
    assert (
        ledger["entries"][0]["batch_ref"]
        == request_id
    )
    assert (
        ledger["historical_exposure_summary"][
            "strong_content_count"
        ]
        == 1
    )

    second = subject.close_generation_export(
        pipeline_root=tmp_path,
        request_id=request_id,
        excel_path=excel,
    )

    assert second["ok"] is True
    assert second["recovered"] is True
    assert second["content_ledger_sha256"] == (
        first["content_ledger_sha256"]
    )


def test_export_closure_rejects_changed_excel(
    tmp_path: Path,
):
    request_id, excel = fixture_runtime(
        tmp_path
    )
    subject.close_generation_export(
        pipeline_root=tmp_path,
        request_id=request_id,
        excel_path=excel,
    )

    excel.write_bytes(b"changed")

    with pytest.raises(
        subject.ExportClosureError
    ) as exc:
        subject.close_generation_export(
            pipeline_root=tmp_path,
            request_id=request_id,
            excel_path=excel,
        )

    assert exc.value.code in {
        "EXPORT_CLOSURE_EXCEL_LINEAGE_MISMATCH",
        "EXPORT_CLOSURE_RECOVERY_LINEAGE_MISMATCH",
    }
