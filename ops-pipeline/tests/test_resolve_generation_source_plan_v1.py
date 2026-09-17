from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )


import match_generation_sources_v1 as matcher  # noqa: E402
import resolve_generation_source_plan_v1 as subject  # noqa: E402

DATA = ROOT / "data"

BUSINESS_PERSONA_ID = "customer_0cf9d0db56a3"
SPEAKER_PERSONA_ID = "speaker_5c8203106b3ecf"
DRAFT_FINGERPRINT_CASE_ID = "7059858129298803968"
BOUND_CASE_ID = "7680512578585870322"


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_canonical_authorities(root: Path) -> None:
    for name in (
        "patterns",
        "cases",
        "fingerprints",
        "production_profiles",
        "creative_coverage",
    ):
        shutil.copytree(
            DATA / name,
            root / "data" / name,
        )

    for persona_id in (
        BUSINESS_PERSONA_ID,
        SPEAKER_PERSONA_ID,
    ):
        shutil.copytree(
            DATA / "personas" / persona_id,
            root / "data" / "personas" / persona_id,
        )


def authority_refs(root: Path) -> dict:
    def ref(path: Path) -> dict:
        return {
            "path": str(path),
            "file_sha256": sha256_file(path),
        }

    return {
        "business_persona_ref": ref(
            root
            / "data"
            / "personas"
            / BUSINESS_PERSONA_ID
            / "revision_0001"
            / "persona_v1.json"
        ),
        "speaker_persona_ref": ref(
            root
            / "data"
            / "personas"
            / SPEAKER_PERSONA_ID
            / "revision_0001"
            / "persona_v1.json"
        ),
        "production_profile_registry_ref": ref(
            root
            / "data"
            / "production_profiles"
            / "production_profile_registry_v1.json"
        ),
    }


def make_request(
    root: Path,
    request_id: str,
    *,
    lineage: dict | None = None,
    target_profile: str = "mix",
    generation_started: bool = False,
    content_request_id: str | None = None,
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
            "schema_version": "generation-request-v1.0",
            "request_id": content_request_id or request_id,
            "persona_id": BUSINESS_PERSONA_ID,
            "persona_revision": 1,
            "speaker_persona": SPEAKER_PERSONA_ID,
            "speaker_persona_revision": 1,
            "profile": target_profile,
            "target_profile": target_profile,
            "quantity": 2,
            "platform": "douyin",
            "content_intent": "mixed",
            "created_at": "2026-09-18T00:00:00+00:00",
            "confirmation": {
                "operator_requested_quantity": 2,
            },
            "constraints": {
                "no_padding": True,
            },
            "lineage": dict(lineage or {}),
            "lifecycle": {
                "status": "created",
                "generation_started": generation_started,
                "source_matching_started": False,
                "human_review_required": True,
            },
            "authority": {
                "generation_request_is_immutable": True,
                "source_matching_performed": False,
                "script_generation_performed": False,
                "generation_batch_created": False,
                "content_ledger_written": False,
                "remote_model_called": False,
                "media_rights_established": False,
            },
        },
    )

    return path


def make_handoff(
    root: Path,
    request_path: Path,
    *,
    refs: dict | None = None,
    request_id: str | None = None,
    request_sha: str | None = None,
) -> Path:
    request = json.loads(request_path.read_text(encoding="utf-8"))

    authority = (
        dict(refs)
        if refs is not None
        else authority_refs(root)
    )

    handoff = {
        "schema_version": ("generation-source-planning-" "handoff-v1.0"),
        "request_id": request_id or request["request_id"],
        "status": "source_authority_resolution_pending",
        "generation_request_ref": {
            "path": str(request_path),
            "file_sha256": request_sha or sha256_file(request_path),
        },
        "business_persona_ref": authority["business_persona_ref"],
        "speaker_persona_ref": authority["speaker_persona_ref"],
        "production_profile_registry_ref": authority[
            "production_profile_registry_ref"
        ],
        "authority_roots": {
            "approved_pattern_root": ("data/patterns/approved"),
            "case_root": "data/cases",
            "production_plan_root": ("data/production_plans"),
        },
        "authority": {
            "source_matching_performed": False,
            "remote_model_called": False,
        },
    }

    path = (
        request_path.parent
        / "generation_source_planning_handoff_v1.json"
    )

    write_json(path, handoff)

    return path


def stage_request(
    root: Path,
    request_id: str = "gen_test_source_plan",
    **kwargs,
) -> Path:
    stage_canonical_authorities(root)

    refs = authority_refs(root)

    request_path = make_request(
        root,
        request_id,
        lineage=refs,
        **kwargs,
    )

    make_handoff(
        root,
        request_path,
        refs=refs,
    )

    return request_path


def resolve(root: Path, request_id: str) -> dict:
    return subject.resolve_generation_source_plan(
        pipeline_root=root,
        request_id=request_id,
    )


def plan_path(root: Path, request_id: str) -> Path:
    return (
        root
        / "data"
        / "production_plans"
        / request_id
        / "generation_source_plan_v1.json"
    )


def test_source_plan_requires_valid_request_handoff_lineage(
    tmp_path: Path,
):
    request_path = stage_request(tmp_path)

    handoff_path = (
        request_path.parent
        / "generation_source_planning_handoff_v1.json"
    )

    handoff_path.unlink()

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(tmp_path, "gen_test_source_plan")

    assert exc.value.code == "SOURCE_PLANNING_HANDOFF_REQUIRED"

    make_handoff(
        tmp_path,
        request_path,
        request_sha="0" * 64,
    )

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(tmp_path, "gen_test_source_plan")

    assert exc.value.code == ("GENERATION_HANDOFF_" "LINEAGE_MISMATCH")

    started_root = tmp_path / "started"

    stage_request(
        started_root,
        generation_started=True,
    )

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(
            started_root,
            "gen_test_source_plan",
        )

    assert exc.value.code == "GENERATION_ALREADY_STARTED"


def test_source_plan_uses_existing_matcher(
    tmp_path: Path,
):
    assert subject.build_source_plan is matcher.build_source_plan

    assert subject.write_source_plan is matcher.write_source_plan

    stage_request(tmp_path)

    result = resolve(tmp_path, "gen_test_source_plan")

    assert result["ok"] is True

    plan = json.loads(
        plan_path(tmp_path, "gen_test_source_plan").read_text(
            encoding="utf-8"
        )
    )

    assert plan["matcher_version"] == matcher.MATCHER_VERSION

    assert plan["schema_version"] == matcher.PLAN_VERSION

    assert result["source_plan_sha256"] == sha256_file(
        plan_path(tmp_path, "gen_test_source_plan")
    )


def test_source_plan_only_uses_approved_patterns(
    tmp_path: Path,
):
    stage_request(tmp_path)

    write_json(
        tmp_path
        / "data"
        / "patterns"
        / "approved"
        / "rejected_pattern"
        / "pattern_v1.json",
        {
            "pattern_id": "rejected_pattern",
            "status": "review_rejected",
            "scope": {"supported_case_ids": []},
            "effectiveness": {
                "status": "unvalidated",
                "performance_data_used": False,
            },
        },
    )

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(tmp_path, "gen_test_source_plan")

    assert exc.value.code == "SOURCE_MATCHING_FAILED"

    assert not plan_path(tmp_path, "gen_test_source_plan").exists()


def test_source_plan_only_uses_approved_cases_and_fingerprints(
    tmp_path: Path,
):
    stage_request(tmp_path)

    result = resolve(tmp_path, "gen_test_source_plan")

    assert result["eligible_case_count"] == 3

    serialized = plan_path(tmp_path, "gen_test_source_plan").read_text(
        encoding="utf-8"
    )

    assert DRAFT_FINGERPRINT_CASE_ID not in serialized

    tampered_root = tmp_path / "tampered"

    stage_request(tampered_root)

    fingerprint_path = (
        tampered_root
        / "data"
        / "fingerprints"
        / BOUND_CASE_ID
        / "case_fingerprint_v1.json"
    )

    fingerprint = json.loads(
        fingerprint_path.read_text(encoding="utf-8")
    )

    fingerprint["source_case"]["sha256"] = "0" * 64

    write_json(fingerprint_path, fingerprint)

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(tampered_root, "gen_test_source_plan")

    assert exc.value.code == ("SOURCE_PLAN_LINEAGE_" "MISMATCH")


def test_source_plan_is_idempotent(
    tmp_path: Path,
):
    stage_request(tmp_path)

    first = resolve(tmp_path, "gen_test_source_plan")

    assert first["recovered"] is False

    second = resolve(tmp_path, "gen_test_source_plan")

    assert second["recovered"] is True

    assert second["source_plan_sha256"] == first["source_plan_sha256"]

    plan_dir = plan_path(tmp_path, "gen_test_source_plan").parent

    assert [
        path.name for path in plan_dir.iterdir()
    ] == ["generation_source_plan_v1.json"]


def test_existing_different_plan_fails_closed(
    tmp_path: Path,
):
    stage_request(tmp_path)

    target = plan_path(tmp_path, "gen_test_source_plan")

    write_json(target, {"tampered": True})

    original_bytes = target.read_bytes()

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(tmp_path, "gen_test_source_plan")

    assert exc.value.code == "SOURCE_PLAN_CONFLICT"

    assert target.read_bytes() == original_bytes


def test_source_plan_remote_model_calls_zero(
    tmp_path: Path,
):
    stage_request(tmp_path)

    result = resolve(tmp_path, "gen_test_source_plan")

    assert result["remote_model_called"] is False

    assert result["script_generation_performed"] is False

    assert (
        result[
            "generation_batch_created"
        ]
        is False
    )

    assert (
        result[
            "content_ledger_written"
        ]
        is False
    )

    plan = json.loads(
        plan_path(tmp_path, "gen_test_source_plan").read_text(
            encoding="utf-8"
        )
    )

    assert plan["authority"]["remote_model_call_performed"] is False

    assert plan["authority"]["script_generation_performed"] is False


def test_source_plan_does_not_create_batch(
    tmp_path: Path,
):
    stage_request(tmp_path)

    resolve(tmp_path, "gen_test_source_plan")

    assert not (tmp_path / "data" / "generation_batches").exists()

    assert not list(tmp_path.rglob("*generation_batch*"))


def test_source_plan_does_not_write_ledger(
    tmp_path: Path,
):
    stage_request(tmp_path)

    resolve(tmp_path, "gen_test_source_plan")

    assert not (tmp_path / "data" / "content_ledger").exists()

    assert not list(tmp_path.rglob("*ledger*"))


def test_news_insufficient_coverage_still_fails_closed(
    tmp_path: Path,
):
    stage_request(
        tmp_path,
        target_profile="news",
    )

    result = resolve(tmp_path, "gen_test_source_plan")

    assert result["ok"] is True

    assert result["coverage_status"] == "insufficient"

    assert result["coverage_code"] == ("research_coverage_" "insufficient")

    assert result["selected_pattern_count"] == 0

    plan = json.loads(
        plan_path(tmp_path, "gen_test_source_plan").read_text(
            encoding="utf-8"
        )
    )

    assert plan["validation"]["news_does_not_fallback_to_mix"] is True


def test_source_plan_request_id_mismatch_fails_closed(
    tmp_path: Path,
):
    stage_request(
        tmp_path,
        content_request_id="gen_someone_else",
    )

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(tmp_path, "gen_test_source_plan")

    assert exc.value.code == ("GENERATION_REQUEST_" "LINEAGE_MISMATCH")

    other_root = tmp_path / "other"

    stage_request(other_root)

    request_path = (
        other_root
        / "data"
        / "generation_requests"
        / "gen_test_source_plan"
        / "generation_request_v1.json"
    )

    make_handoff(
        other_root,
        request_path,
        request_id="gen_someone_else",
    )

    with pytest.raises(subject.SourcePlanError) as exc:
        resolve(other_root, "gen_test_source_plan")

    assert exc.value.code == ("GENERATION_HANDOFF_" "LINEAGE_MISMATCH")


def test_handoff_authority_ref_must_match_request_lineage(
    tmp_path: Path,
):
    request_path = stage_request(
        tmp_path
    )

    handoff_path = (
        request_path.parent
        / (
            "generation_source_planning_"
            "handoff_v1.json"
        )
    )

    handoff = json.loads(
        handoff_path.read_text(
            encoding="utf-8"
        )
    )

    handoff[
        "production_profile_registry_ref"
    ][
        "file_sha256"
    ] = "0" * 64

    write_json(
        handoff_path,
        handoff,
    )

    with pytest.raises(
        subject.SourcePlanError
    ) as exc:
        resolve(
            tmp_path,
            "gen_test_source_plan",
        )

    assert (
        exc.value.code
        == "SOURCE_PLAN_LINEAGE_MISMATCH"
    )


def test_source_planning_rejects_closed_request_lifecycle(
    tmp_path: Path,
):
    request_path = stage_request(
        tmp_path
    )

    request = json.loads(
        request_path.read_text(
            encoding="utf-8"
        )
    )

    request[
        "lifecycle"
    ][
        "status"
    ] = "cancelled"

    write_json(
        request_path,
        request,
    )

    make_handoff(
        tmp_path,
        request_path,
    )

    with pytest.raises(
        subject.SourcePlanError
    ) as exc:
        resolve(
            tmp_path,
            "gen_test_source_plan",
        )

    assert (
        exc.value.code
        == (
            "SOURCE_PLANNING_"
            "LIFECYCLE_CLOSED"
        )
    )
