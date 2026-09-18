from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(
    __file__
).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

import resolve_generation_request_v1 as subject
import generation_request_effective_lifecycle_v1 as lifecycle


def write_json(
    path: Path,
    value: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def request_fixture(
    pipeline: Path,
    request_id: str,
    *,
    business_id: str = "business_1",
    profile: str = "mix",
) -> Path:
    path = (
        pipeline
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )

    write_json(
        path,
        {
            "schema_version": (
                "generation-request-v1.0"
            ),
            "request_id": request_id,
            "persona_id": business_id,
            "speaker_persona": (
                "speaker_1"
            ),
            "target_profile": profile,
            "quantity": 2,
            "lifecycle": {
                "status": "created",
            },
        },
    )

    return path


def make_exported_request(
    pipeline: Path,
    request_id: str,
) -> Path:
    request_path = request_fixture(
        pipeline,
        request_id,
    )

    batch_path = (
        pipeline
        / "data"
        / "generation_batches"
        / request_id
        / "revisions"
        / "revision_0001"
        / "approved_generation_batch_v1.json"
    )

    write_json(
        batch_path,
        {
            "schema_version": (
                "approved-generation-batch-v1.0"
            ),
            "request_id": request_id,
            "status": "approved",
            "lineage": {
                "request": {
                    "sha256": (
                        lifecycle.sha256_file(
                            request_path
                        )
                    )
                }
            },
        },
    )

    batch_sha = (
        lifecycle.sha256_file(
            batch_path
        )
    )

    write_json(
        batch_path.parent
        / "generation_batch_approval_receipt.json",
        {
            "schema_version": (
                "generation-batch-approval-receipt-v1.0"
            ),
            "request_id": request_id,
            "status": "approved",
            "human_gate": True,
            "approved_batch": {
                "sha256": batch_sha,
            },
        },
    )

    output = (
        pipeline
        / "output"
        / f"{request_id}.xlsx"
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_bytes(
        b"excel"
    )

    write_json(
        pipeline
        / "output"
        / f"{request_id}.export_receipt.json",
        {
            "schema_version": (
                "mix-excel-export-receipt-v1.0"
            ),
            "validation_passed": True,
            "batch_path": str(
                batch_path.resolve()
            ),
            "batch_sha256": (
                batch_sha
            ),
            "output_path": str(
                output.resolve()
            ),
            "output_sha256": (
                lifecycle.sha256_file(
                    output
                )
            ),
        },
    )

    return request_path


def test_requires_explicit_human_approval(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    request_fixture(
        pipeline,
        "gen_old",
    )

    with pytest.raises(
        subject.ResolutionError
    ) as exc:
        subject.resolve_generation_request(
            pipeline_root=pipeline,
            request_id="gen_old",
            disposition="abandoned",
            reviewer="Human",
            reason="Historical attempt.",
            human_approved=False,
        )

    assert (
        exc.value.code
        == (
            "GENERATION_REQUEST_"
            "RESOLUTION_HUMAN_APPROVAL_REQUIRED"
        )
    )


def test_human_resolution_does_not_mutate_request(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    path = request_fixture(
        pipeline,
        "gen_old",
    )

    before = (
        lifecycle.sha256_file(
            path
        )
    )

    result = (
        subject.resolve_generation_request(
            pipeline_root=pipeline,
            request_id="gen_old",
            disposition="abandoned",
            reviewer="Human",
            reason=(
                "Historical unapproved attempt."
            ),
            human_approved=True,
        )
    )

    assert result[
        "effective_terminal"
    ] is True

    assert result[
        "effective_status"
    ] == "abandoned"

    assert (
        lifecycle.sha256_file(
            path
        )
        == before
    )


def test_superseded_request_must_be_validated_export(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    request_fixture(
        pipeline,
        "gen_old",
    )

    request_fixture(
        pipeline,
        "gen_new",
    )

    with pytest.raises(
        subject.ResolutionError
    ) as exc:
        subject.resolve_generation_request(
            pipeline_root=pipeline,
            request_id="gen_old",
            disposition="abandoned",
            reviewer="Human",
            reason=(
                "Superseded by later request."
            ),
            human_approved=True,
            superseded_by_request_id=(
                "gen_new"
            ),
        )

    assert (
        exc.value.code
        == (
            "GENERATION_REQUEST_"
            "SUPERSEDING_REQUEST_NOT_EXPORTED"
        )
    )


def test_validated_export_can_be_named_as_superseding_request(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    old = request_fixture(
        pipeline,
        "gen_old",
    )

    make_exported_request(
        pipeline,
        "gen_new",
    )

    result = (
        subject.resolve_generation_request(
            pipeline_root=pipeline,
            request_id="gen_old",
            disposition="abandoned",
            reviewer="Human",
            reason=(
                "Historical unapproved attempt; "
                "later request was approved/exported."
            ),
            human_approved=True,
            superseded_by_request_id=(
                "gen_new"
            ),
        )
    )

    assert (
        result[
            "effective_status"
        ]
        == "abandoned"
    )

    resolution = lifecycle.read_json(
        old.parent
        / "generation_request_resolution_v1.json"
    )

    assert (
        resolution[
            "superseded_by"
        ][
            "request_id"
        ]
        == "gen_new"
    )
