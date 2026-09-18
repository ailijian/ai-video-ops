from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import show_customer_status_v1 as subject


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def test_approved_batch_discovery_supports_revisioned_and_flat_layout(
    tmp_path: Path,
):
    legacy = (
        tmp_path
        / "data"
        / "generation_batches"
        / "legacy_001"
        / "revisions"
        / "revision_0001"
        / "approved_generation_batch_v1.json"
    )

    current = (
        tmp_path
        / "data"
        / "generation_batches"
        / "current_001"
        / "approved_generation_batch_v1.json"
    )

    write_json(legacy, {"fixture": "legacy"})
    write_json(current, {"fixture": "current"})

    discovered = subject.iter_approved_generation_batch_paths(tmp_path)

    assert legacy.resolve() in discovered
    assert current.resolve() in discovered
    assert len(discovered) == 2


def test_current_console_capacity_fallback_is_zero_model(
    tmp_path: Path,
    monkeypatch,
):
    request_id = "gen_current_001"
    business_id = "business_1"
    speaker_id = "speaker_1"

    closure_path = (
        tmp_path
        / "data"
        / "generation_batches"
        / request_id
        / "generation_export_closure_v1.json"
    )

    write_json(
        closure_path,
        {
            "schema_version": "generation-export-closure-v1.0",
            "request_id": request_id,
            "status": "approved_exported_ledger_closed",
            "approved_batch": {
                "sha256": "a" * 64,
            },
        },
    )

    request_path = (
        tmp_path
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )

    write_json(
        request_path,
        {
            "schema_version": "generation-request-v1.0",
            "request_id": request_id,
            "persona_id": business_id,
            "speaker_persona": speaker_id,
            "target_profile": "mix",
            "quantity": 2,
        },
    )

    v1_1_path = (
        tmp_path
        / "data"
        / "content_plans"
        / request_id
        / "content_plan_v1_1.json"
    )

    write_json(
        v1_1_path,
        {
            "schema_version": "content-plan-v1.1",
            "request_id": request_id,
            "business_id": business_id,
            "speaker_id": speaker_id,
            "candidate_pool": {
                "candidates": [],
            },
        },
    )

    v1_1_1_path = (
        v1_1_path.parent
        / "content_plan_v1_1_1.json"
    )

    write_json(
        v1_1_1_path,
        {
            "schema_version": "content-plan-v1.1.1",
            "request_id": request_id,
            "business_id": business_id,
            "speaker_id": speaker_id,
            "lineage": {
                "source_v1_1_content_plan_sha256": subject.sha256_file(v1_1_path),
            },
        },
    )

    ledger = {
        "path": (
            tmp_path
            / "data"
            / "content_ledgers"
            / business_id
            / "content_ledger_v1.json"
        ),
        "file_sha256": "b" * 64,
        "artifact": {
            "schema_version": "content-ledger-v1.0",
            "business_id": business_id,
            "entries": [
                {
                    "content_id": "C001",
                    "batch_ref": request_id,
                    "status": "exported",
                }
            ],
            "fact_atom_catalog": [],
        },
        "entries": [
            {
                "content_id": "C001",
                "batch_ref": request_id,
                "status": "exported",
            }
        ],
    }

    monkeypatch.setattr(
        subject,
        "build_content_plan_v1_1_1",
        lambda **kwargs: {
            "capacity": {
                "high_quality_novel_capacity": 5,
                "status": "supported",
                "padding_generated": False,
            },
            "authority": {
                "remote_model_called": False,
            },
            "remote_model_call": {
                "performed": False,
            },
        },
    )

    result = subject._resolve_current_console_capacity(
        tmp_path,
        {
            "persona_id": business_id,
        },
        {
            "persona_id": speaker_id,
        },
        ledger,
        {
            "request_id": request_id,
            "file_sha256": "a" * 64,
            "export_status": "EXPORTED",
        },
    )

    assert result["remaining"] == 5
    assert (
        result["calculation_mode"]
        == "current_console_v1_1_1_reprojection"
    )
    assert result["remote_model_calls"] == 0
