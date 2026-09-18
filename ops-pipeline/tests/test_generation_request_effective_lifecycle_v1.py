from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)
SCRIPTS = ROOT / "scripts"

sys.path.insert(
    0,
    str(SCRIPTS),
)

import generation_request_effective_lifecycle_v1 as subject


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
    *,
    request_id: str,
    business_id: str = "business_1",
    status: str = "created",
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
            "speaker_persona": "speaker_1",
            "target_profile": "mix",
            "quantity": 2,
            "confirmation": {
                "operator_requested_quantity": 2,
            },
            "lifecycle": {
                "status": status,
            },
        },
    )

    return path


def test_direct_terminal_status(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    path = request_fixture(
        pipeline,
        request_id="gen_direct",
        status="completed",
    )

    result = (
        subject.classify_request(
            pipeline_root=pipeline,
            request_path=path,
        )
    )

    assert (
        result["effective_terminal"]
        is True
    )
    assert (
        result["terminal_reason"]
        == "immutable_request_lifecycle"
    )


def test_human_resolution_sidecar_terminalizes_without_mutating_request(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    path = request_fixture(
        pipeline,
        request_id="gen_abandoned",
    )

    before = subject.sha256_file(
        path
    )

    write_json(
        path.parent
        / "generation_request_resolution_v1.json",
        {
            "schema_version": (
                "generation-request-resolution-v1.0"
            ),
            "request_id": (
                "gen_abandoned"
            ),
            "business_id": (
                "business_1"
            ),
            "disposition": (
                "abandoned"
            ),
            "reviewer": "Human",
            "reviewed_at": (
                "2026-09-18T00:00:00+00:00"
            ),
            "reason": (
                "Historical unapproved attempt "
                "explicitly closed by Human Operator."
            ),
            "human_gate": True,
            "request_ref": {
                "sha256": (
                    before
                ),
            },
        },
    )

    result = (
        subject.classify_request(
            pipeline_root=pipeline,
            request_path=path,
        )
    )

    assert (
        result["effective_terminal"]
        is True
    )
    assert (
        result["effective_status"]
        == "abandoned"
    )
    assert (
        subject.sha256_file(path)
        == before
    )


def test_validated_export_terminalizes_immutable_created_request(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    request_path = (
        request_fixture(
            pipeline,
            request_id=(
                "gen_exported"
            ),
        )
    )

    batch_path = (
        pipeline
        / "data"
        / "generation_batches"
        / "gen_exported"
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
            "request_id": (
                "gen_exported"
            ),
            "status": "approved",
            "lineage": {
                "request": {
                    "sha256": (
                        subject.sha256_file(
                            request_path
                        )
                    )
                }
            },
        },
    )

    batch_sha = (
        subject.sha256_file(
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
            "request_id": (
                "gen_exported"
            ),
            "status": "approved",
            "human_gate": True,
            "approved_batch": {
                "sha256": batch_sha,
            },
        },
    )

    output_path = (
        pipeline
        / "output"
        / "generated.xlsx"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output_path.write_bytes(
        b"excel"
    )

    write_json(
        pipeline
        / "output"
        / "generated.export_receipt.json",
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
                output_path.resolve()
            ),
            "output_sha256": (
                subject.sha256_file(
                    output_path
                )
            ),
        },
    )

    result = (
        subject.classify_request(
            pipeline_root=pipeline,
            request_path=(
                request_path
            ),
        )
    )

    assert (
        result["effective_terminal"]
        is True
    )
    assert (
        result["effective_status"]
        == "exported"
    )
    assert (
        result["terminal_reason"]
        == "validated_mix_export"
    )


def test_review_required_batch_remains_resumable(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    request_path = (
        request_fixture(
            pipeline,
            request_id=(
                "gen_review"
            ),
        )
    )

    batch_path = (
        pipeline
        / "data"
        / "generation_batches"
        / "gen_review"
        / "generation_batch_v1.json"
    )

    write_json(
        batch_path,
        {
            "schema_version": (
                "generation-batch-v1.0"
            ),
            "request_id": (
                "gen_review"
            ),
            "status": (
                "review_required"
            ),
        },
    )

    result = (
        subject.classify_request(
            pipeline_root=pipeline,
            request_path=(
                request_path
            ),
        )
    )

    assert (
        result["effective_terminal"]
        is False
    )
    assert (
        result["effective_stage"]
        == "HUMAN_REVIEW"
    )


def test_business_audit_reports_only_unclosed_request_active(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    request_fixture(
        pipeline,
        request_id="gen_closed",
        status="completed",
    )

    request_fixture(
        pipeline,
        request_id="gen_open",
        status="created",
    )

    result = (
        subject.audit_business_requests(
            pipeline_root=pipeline,
            business_id="business_1",
        )
    )

    assert (
        result["status"]
        == "single_active_request"
    )
    assert (
        result["active_request_ids"]
        == ["gen_open"]
    )


def test_profile_scoped_audit_ignores_other_profile_requests(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    mix_path = request_fixture(
        pipeline,
        request_id="gen_mix_open",
        status="created",
    )

    news_path = request_fixture(
        pipeline,
        request_id="gen_news_open",
        status="created",
    )

    news = subject.read_json(
        news_path
    )
    news["target_profile"] = "news"
    write_json(
        news_path,
        news,
    )

    mix = subject.audit_business_requests(
        pipeline_root=pipeline,
        business_id="business_1",
        profile="mix",
    )

    assert (
        mix["profile_filter"]
        == "mix"
    )
    assert (
        mix["active_request_ids"]
        == ["gen_mix_open"]
    )
    assert (
        mix["request_count"]
        == 1
    )

    news_result = subject.audit_business_requests(
        pipeline_root=pipeline,
        business_id="business_1",
        profile="news",
    )

    assert (
        news_result["active_request_ids"]
        == ["gen_news_open"]
    )


def test_all_profile_audit_can_remain_ambiguous_while_mix_is_unambiguous(
    tmp_path: Path,
):
    pipeline = tmp_path / "pipeline"

    request_fixture(
        pipeline,
        request_id="gen_mix_open",
        status="created",
    )

    news_path = request_fixture(
        pipeline,
        request_id="gen_news_open",
        status="created",
    )
    news = subject.read_json(
        news_path
    )
    news["target_profile"] = "news"
    write_json(
        news_path,
        news,
    )

    all_profiles = (
        subject.audit_business_requests(
            pipeline_root=pipeline,
            business_id="business_1",
        )
    )
    mix = subject.audit_business_requests(
        pipeline_root=pipeline,
        business_id="business_1",
        profile="mix",
    )

    assert (
        all_profiles["status"]
        == "active_request_ambiguity"
    )
    assert (
        mix["status"]
        == "single_active_request"
    )
