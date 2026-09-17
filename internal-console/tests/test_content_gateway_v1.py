from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.canonical_gateway import (
    CanonicalOperationError,
)
from app.content_gateway import (
    get_active_generation_request,
)


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


def sha256_file(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def make_request(
    root: Path,
    request_id: str,
    *,
    business_id: str = "fixture_business",
) -> Path:
    path = (
        root
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
                "fixture_speaker"
            ),
            "target_profile": "mix",
            "quantity": 3,
            "created_at": (
                "2026-09-18T"
                "00:00:00+00:00"
            ),
            "confirmation": {
                "operator_requested_quantity": (
                    5
                ),
            },
            "lifecycle": {
                "status": "created",
            },
            "authority": {
                "script_generation_performed": (
                    False
                ),
                "generation_batch_created": (
                    False
                ),
                "content_ledger_written": (
                    False
                ),
                "remote_model_called": (
                    False
                ),
            },
        },
    )

    return path


def make_handoff(
    request_path: Path,
    *,
    request_sha: str | None = None,
) -> Path:
    request = json.loads(
        request_path.read_text(
            encoding="utf-8"
        )
    )

    path = (
        request_path.parent
        / (
            "generation_source_planning_"
            "handoff_v1.json"
        )
    )

    write_json(
        path,
        {
            "schema_version": (
                "generation-source-planning-"
                "handoff-v1.0"
            ),
            "request_id": (
                request["request_id"]
            ),
            "status": (
                "source_authority_"
                "resolution_pending"
            ),
            "generation_request_ref": {
                "file_sha256": (
                    request_sha
                    or sha256_file(
                        request_path
                    )
                ),
            },
        },
    )

    return path


def settings(
    root: Path,
):
    return SimpleNamespace(
        pipeline_root=root,
    )


def test_one_active_request_projects_normally(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_handoff(
        request
    )

    result = (
        get_active_generation_request(
            settings(
                tmp_path
            ),
            "fixture_business",
        )
    )

    active = result[
        "active_request"
    ]

    assert (
        active[
            "request_id"
        ]
        == "gen_fixture_001"
    )

    assert (
        active[
            "handoff_ready"
        ]
        is True
    )


def test_multiple_active_requests_fail_closed(
    tmp_path: Path,
):
    make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_request(
        tmp_path,
        "gen_fixture_002",
    )

    with pytest.raises(
        CanonicalOperationError
    ) as exc:
        get_active_generation_request(
            settings(
                tmp_path
            ),
            "fixture_business",
        )

    assert (
        exc.value.code
        == (
            "CONTENT_GENERATION_"
            "ACTIVE_REQUEST_AMBIGUITY"
        )
    )


def test_handoff_lineage_mismatch_fails_closed(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_handoff(
        request,
        request_sha=(
            "0" * 64
        ),
    )

    with pytest.raises(
        CanonicalOperationError
    ) as exc:
        get_active_generation_request(
            settings(
                tmp_path
            ),
            "fixture_business",
        )

    assert (
        exc.value.code
        == (
            "GENERATION_HANDOFF_"
            "LINEAGE_MISMATCH"
        )
    )


def test_missing_handoff_is_recoverable_state(
    tmp_path: Path,
):
    make_request(
        tmp_path,
        "gen_fixture_001",
    )

    result = (
        get_active_generation_request(
            settings(
                tmp_path
            ),
            "fixture_business",
        )
    )

    active = result[
        "active_request"
    ]

    assert (
        active[
            "handoff_ready"
        ]
        is False
    )
