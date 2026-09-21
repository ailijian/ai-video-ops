from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.canonical_gateway import (
    CanonicalOperationError,
)
from app.content_gateway import (
    get_active_generation_request,
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


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
    profile: str = "mix",
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
            "target_profile": profile,
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


def make_source_plan(
    root: Path,
    request_id: str,
    *,
    plan_request_id: str | None = None,
    coverage_status: str = "supported",
) -> Path:
    path = (
        root
        / "data"
        / "production_plans"
        / request_id
        / "generation_source_plan_v1.json"
    )

    request_path = (
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
                "generation-source-plan-v1.0"
            ),
            "request_id": (
                plan_request_id
                or request_id
            ),
            "request": {
                "request_sha": (
                    sha256_file(
                        request_path
                    )
                ),
            },
            "coverage": {
                "status": coverage_status,
                "code": (
                    "research_coverage_"
                    + ("supported" if coverage_status == "supported" else "insufficient")
                ),
                "reason": (
                    "An Approved Pattern and approved Profile-compatible Case pool "
                    "pass all hard gates."
                    if coverage_status == "supported"
                    else "No Approved Pattern and Case pool jointly pass all hard gates."
                ),
                "humanized_reason": (
                    "现有创作结构可以支持。"
                    if coverage_status == "supported"
                    else "当前有值得做的内容方向，但现有创作结构暂时不能支持。"
                ),
                "blocker_type": (
                    None
                    if coverage_status == "supported"
                    else "PERSONA_LACKS_PATTERN_CAPABILITY"
                ),
                "blocker_codes": (
                    []
                    if coverage_status == "supported"
                    else ["PERSONA_LACKS_PATTERN_CAPABILITY"]
                ),
            },
            "selected_patterns": [
                {
                    "pattern_id": (
                        "pcv1_narration_led_"
                        "process_projection"
                    )
                }
            ],
            "eligible_case_pool": [
                {"case_id": "100"},
                {"case_id": "200"},
                {"case_id": "300"},
            ],
        },
    )

    return path


def test_active_request_projection_reports_source_plan_ready(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_handoff(request)

    make_source_plan(
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
            "source_plan_ready"
        ]
        is True
    )

    assert (
        active[
            "source_plan_status"
        ]
        == "source_matching_supported"
    )

    assert (
        active[
            "coverage_status"
        ]
        == "supported"
    )

    assert (
        active[
            "coverage_code"
        ]
        == (
            "research_coverage_"
            "supported"
        )
    )

    assert (
        active[
            "selected_pattern_count"
        ]
        == 1
    )

    assert (
        active[
            "eligible_case_count"
        ]
        == 3
    )

    assert (
        active[
            "next_action"
        ]
        == "CREATE_CONTENT_PLAN"
    )


def test_active_request_projection_without_plan_is_not_ready(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_handoff(request)

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
            "source_plan_ready"
        ]
        is False
    )

    assert (
        active[
            "coverage_status"
        ]
        is None
    )

    assert (
        active[
            "selected_pattern_count"
        ]
        == 0
    )

    assert (
        active[
            "eligible_case_count"
        ]
        == 0
    )

    assert (
        active[
            "next_action"
        ]
        == "RESOLVE_GENERATION_SOURCES"
    )


def test_source_plan_artifact_with_unsupported_coverage_is_blocked(
    tmp_path: Path,
):
    request = make_request(tmp_path, "gen_fixture_001")
    make_handoff(request)
    make_source_plan(
        tmp_path,
        "gen_fixture_001",
        coverage_status="insufficient",
    )

    active = get_active_generation_request(
        settings(tmp_path),
        "fixture_business",
    )["active_request"]

    assert active["source_plan_artifact_exists"] is True
    assert active["source_coverage_supported"] is False
    assert active["source_plan_ready"] is False
    assert active["coverage_status"] == "insufficient"
    assert active["next_action"] == "SOURCE_COVERAGE_BLOCKED"
    assert active["production_feasibility"]["blocker_type"] == (
        "PERSONA_LACKS_PATTERN_CAPABILITY"
    )


def test_source_plan_request_id_mismatch_fails_closed(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_handoff(request)

    make_source_plan(
        tmp_path,
        "gen_fixture_001",
        plan_request_id=(
            "gen_someone_else"
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
            "GENERATION_SOURCE_PLAN_"
            "LINEAGE_MISMATCH"
        )
    )


def test_source_plan_request_sha_mismatch_fails_closed(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_fixture_001",
    )

    make_handoff(
        request
    )

    plan_path = make_source_plan(
        tmp_path,
        "gen_fixture_001",
    )

    plan = json.loads(
        plan_path.read_text(
            encoding="utf-8"
        )
    )

    plan[
        "request"
    ][
        "request_sha"
    ] = "0" * 64

    write_json(
        plan_path,
        plan,
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
            "GENERATION_SOURCE_PLAN_"
            "LINEAGE_MISMATCH"
        )
    )


def test_other_profile_request_does_not_create_mix_ambiguity(
    tmp_path: Path,
):
    mix = make_request(
        tmp_path,
        "gen_mix_001",
        profile="mix",
    )

    make_handoff(
        mix
    )

    make_request(
        tmp_path,
        "gen_news_001",
        profile="news",
    )

    result = (
        get_active_generation_request(
            settings(
                tmp_path
            ),
            "fixture_business",
        )
    )

    assert (
        result[
            "active_request"
        ][
            "request_id"
        ]
        == "gen_mix_001"
    )


def test_human_resolution_sidecar_removes_request_from_active_mix_projection(
    tmp_path: Path,
):
    request = make_request(
        tmp_path,
        "gen_mix_001",
        profile="mix",
    )

    write_json(
        request.parent
        / "generation_request_resolution_v1.json",
        {
            "schema_version": (
                "generation-request-resolution-v1.0"
            ),
            "request_id": (
                "gen_mix_001"
            ),
            "business_id": (
                "fixture_business"
            ),
            "profile": "mix",
            "disposition": (
                "abandoned"
            ),
            "reviewer": "Human",
            "reviewed_at": (
                "2026-09-18T00:00:00+00:00"
            ),
            "reason": (
                "Historical unapproved attempt."
            ),
            "human_gate": True,
            "request_ref": {
                "sha256": (
                    sha256_file(
                        request
                    )
                ),
            },
        },
    )

    result = (
        get_active_generation_request(
            settings(
                tmp_path
            ),
            "fixture_business",
        )
    )

    assert (
        result[
            "active_request"
        ]
        is None
    )
