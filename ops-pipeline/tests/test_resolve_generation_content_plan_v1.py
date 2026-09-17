from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import content_quality_v1 as quality  # noqa: E402
import generate_mix_scripts_v1 as generator  # noqa: E402
import resolve_generation_content_plan_v1 as subject  # noqa: E402


REQUEST_ID = "gen_content_plan_test_001"
BUSINESS_ID = "fixture_pet_store"
SPEAKER_ID = "fixture_pet_store_owner"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_authorities(root: Path, *, coverage_status: str = "supported") -> dict[str, Path]:
    persona_path = root / "data/personas" / BUSINESS_ID / "revision_0001/persona_v1.json"
    speaker_path = root / "data/personas" / SPEAKER_ID / "revision_0001/persona_v1.json"
    pattern_path = root / "data/patterns/approved/pattern_001/pattern_v1.json"
    fingerprint_path = root / "data/fingerprints/case_001/case_fingerprint_v1.json"

    write_json(
        persona_path,
        {
            "persona_id": BUSINESS_ID,
            "facts": {
                "primary_products_or_services": {
                    "state": "known",
                    "value": ["宠物洗护", "基础美容"],
                },
                "process_facts": {
                    "state": "known",
                    "value": ["洗护前检查皮肤和毛发状态"],
                },
                "customer_pains": {
                    "state": "known",
                    "value": ["工作日没时间自己给宠物洗澡护理"],
                },
            },
        },
    )
    write_json(
        speaker_path,
        {
            "persona_id": SPEAKER_ID,
            "speaker_type": "owner_founder",
            "facts": {
                "first_person_allowed_topics": {
                    "state": "known",
                    "value": ["门店洗护流程"],
                }
            },
        },
    )
    write_json(pattern_path, {"pattern_id": "pattern_001", "status": "approved"})
    write_json(fingerprint_path, {"case_id": "case_001"})

    request_path = root / "data/generation_requests" / REQUEST_ID / "generation_request_v1.json"
    request = {
        "schema_version": "generation-request-v1.0",
        "request_id": REQUEST_ID,
        "created_at": "2026-09-18T01:00:00+00:00",
        "persona_id": BUSINESS_ID,
        "persona_revision": 1,
        "speaker_persona": SPEAKER_ID,
        "speaker_persona_revision": 1,
        "profile": "mix",
        "target_profile": "mix",
        "quantity": 2,
        "platform": "douyin",
        "content_intent": "mixed",
        "cta_intent": "none",
        "lifecycle": {"status": "created", "generation_started": False},
        "authority": {
            "script_generation_performed": False,
            "generation_batch_created": False,
            "content_ledger_written": False,
            "remote_model_called": False,
        },
        "lineage": {
            "business_persona_ref": {
                "path": str(persona_path.resolve()),
                "file_sha256": sha256_file(persona_path),
            },
            "speaker_persona_ref": {
                "path": str(speaker_path.resolve()),
                "file_sha256": sha256_file(speaker_path),
            },
        },
    }
    write_json(request_path, request)

    source_plan_path = root / "data/production_plans" / REQUEST_ID / "generation_source_plan_v1.json"
    write_json(
        source_plan_path,
        {
            "schema_version": "generation-source-plan-v1.0",
            "request_id": REQUEST_ID,
            "request": {"request_sha": sha256_file(request_path)},
            "coverage": {"status": coverage_status, "code": "fixture"},
            "selected_patterns": [
                {
                    "pattern_id": "pattern_001",
                    "approved_pattern_sha": sha256_file(pattern_path),
                }
            ],
            "eligible_case_pool": [
                {"case_id": "case_001", "fingerprint_sha": sha256_file(fingerprint_path)}
            ],
            "rotation": {"case_rotation_order": ["case_001"]},
        },
    )
    return {
        "persona": persona_path,
        "speaker": speaker_path,
        "pattern": pattern_path,
        "fingerprint": fingerprint_path,
        "request": request_path,
        "source_plan": source_plan_path,
    }


def fake_context(persona_path, request_path, source_plan_path, pattern_path, fingerprint_paths, speaker_path):
    return {
        "paths": {
            "persona": persona_path,
            "request": request_path,
            "source_plan": source_plan_path,
            "pattern": pattern_path,
            "speaker_persona": speaker_path,
        },
        "persona": json.loads(persona_path.read_text(encoding="utf-8")),
        "speaker_persona": json.loads(speaker_path.read_text(encoding="utf-8")),
        "request": json.loads(request_path.read_text(encoding="utf-8")),
        "source_plan": json.loads(source_plan_path.read_text(encoding="utf-8")),
        "pattern": json.loads(pattern_path.read_text(encoding="utf-8")),
        "fingerprints": {"case_001": {"path": str(fingerprint_paths[0])}},
    }


def v1_plan(context: dict) -> dict:
    request_id = context["request"]["request_id"]
    return {
        "schema_version": "content-plan-v1.0",
        "request_id": request_id,
        "business_id": BUSINESS_ID,
        "speaker_id": SPEAKER_ID,
        "candidate_pool": {
            "configured_size": 8,
            "received_size": 8,
            "candidates": [
                {"concept_id": "CONCEPT_002"},
                {"concept_id": "CONCEPT_004"},
            ],
        },
        "selected_concepts": [
            {"concept_id": "CONCEPT_002"},
            {"concept_id": "CONCEPT_004"},
        ],
        "capacity": {
            "requested_quantity": 2,
            "high_quality_novel_capacity": 2,
            "selected_quantity": 2,
            "status": "supported",
            "padding_generated": False,
        },
        "planning_call": {
            "remote_model_call_performed": True,
            "remote_model_call_count": 1,
            "model": "fake-model",
        },
    }


def v1_1_plan(context: dict) -> dict:
    return {
        "schema_version": "content-plan-v1.1",
        "request_id": context["request"]["request_id"],
        "business_id": BUSINESS_ID,
        "speaker_id": SPEAKER_ID,
        "speaker_type": "owner_founder",
        "candidate_pool": {"candidates": [{"concept_id": "CONCEPT_002"}, {"concept_id": "CONCEPT_004"}]},
        "capacity": {
            "requested_quantity": 2,
            "high_quality_novel_capacity": 2,
            "selected_quantity": 2,
            "status": "supported",
            "padding_generated": False,
            "script_generation_performed": False,
        },
        "selected_concepts": [{"concept_id": "CONCEPT_002"}, {"concept_id": "CONCEPT_004"}],
    }


def final_plan(
    context: dict,
    *,
    selected_ids=("CONCEPT_002",),
    source_v1_1_sha: str,
    content_memory_sha: str,
) -> dict:
    selected = [
        {"concept_id": value, "v1_1_1_gate_decision": "high_quality_novel"}
        for value in selected_ids
    ]
    return {
        "schema_version": "content-plan-v1.1.1",
        "request_id": context["request"]["request_id"],
        "business_id": BUSINESS_ID,
        "speaker_id": SPEAKER_ID,
        "speaker_type": "owner_founder",
        "capacity": {
            "requested_quantity": 2,
            "novelty_surviving_capacity": len(selected),
            "revision_required_capacity": 0,
            "high_quality_novel_capacity": len(selected),
            "selected_quantity": len(selected),
            "status": "supported" if len(selected) >= 2 else "capacity_limited",
            "padding_generated": False,
            "script_generation_performed": False,
        },
        "selected_concepts": selected,
        "lineage": {
            "source_v1_1_content_plan_sha256": source_v1_1_sha,
            "content_ledger_sha256": content_memory_sha,
        },
        "authority": {
            "remote_model_called": False,
            "script_generation_performed": False,
        },
    }


def patch_runtime(monkeypatch, *, final_selected=("CONCEPT_002",)):
    calls = {"generate": 0, "v1_1": 0, "v1_1_1": 0}

    def validate_inputs(persona_path, request_path, source_plan_path, pattern_path, fingerprint_paths, speaker_path):
        return fake_context(persona_path, request_path, source_plan_path, pattern_path, fingerprint_paths, speaker_path)

    def validate_v1(context, plan, ledger):
        assert plan["schema_version"] == "content-plan-v1.0"
        assert ledger["schema_version"] == "content-ledger-v1.0"

    def generate(context, ledger, model, transport, created_at=None):
        calls["generate"] += 1
        assert transport is not None
        return v1_plan(context)

    def build_v11(**kwargs):
        calls["v1_1"] += 1
        return v1_1_plan({"request": kwargs["request"]})

    def build_v111(**kwargs):
        calls["v1_1_1"] += 1
        hashes = kwargs["source_artifact_hashes"]
        return final_plan(
            {"request": kwargs["request"]},
            selected_ids=final_selected,
            source_v1_1_sha=hashes["content_plan_v1_1"],
            content_memory_sha=hashes["content_ledger_v1"],
        )

    monkeypatch.setattr(subject, "validate_generation_inputs", validate_inputs)
    monkeypatch.setattr(subject, "validate_content_plan_input", validate_v1)
    monkeypatch.setattr(subject, "generate_content_plan_v1", generate)
    monkeypatch.setattr(subject, "build_content_plan_v1_1", build_v11)
    monkeypatch.setattr(subject, "build_content_plan_v1_1_1", build_v111)
    return calls


def fake_transport(prompt: str) -> dict:
    raise AssertionError("Mocked planner should not invoke this transport directly.")


def test_wrapper_reuses_frozen_quality_engine_functions():
    assert subject.generate_content_plan_v1 is generator.generate_content_plan_v1
    assert subject.validate_generation_inputs is generator.validate_generation_inputs
    assert subject.build_content_plan_v1_1 is quality.build_content_plan_v1_1
    assert subject.build_content_plan_v1_1_1 is quality.build_content_plan_v1_1_1


def test_ephemeral_history_gets_fact_atom_catalog_without_writing_ledger(tmp_path: Path, monkeypatch):
    stage_authorities(tmp_path)
    monkeypatch.setattr(subject, "has_ledger_worthy_historical_exposure", lambda *a, **k: False)
    calls = patch_runtime(monkeypatch)

    result = subject.resolve_generation_content_plan(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )

    assert result["quality_baseline"] == "v1.1.1"
    assert result["selected_quantity"] == 1
    assert result["capacity_status"] == "capacity_limited"
    assert calls == {"generate": 1, "v1_1": 1, "v1_1_1": 1}
    assert not (tmp_path / "data/content_ledgers").exists()


def test_existing_v1_candidate_plan_is_upgraded_offline_without_model_call(tmp_path: Path, monkeypatch):
    stage_authorities(tmp_path)
    monkeypatch.setattr(subject, "has_ledger_worthy_historical_exposure", lambda *a, **k: False)
    calls = patch_runtime(monkeypatch)

    first = subject.resolve_generation_content_plan(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    plan_root = tmp_path / "data/content_plans" / REQUEST_ID
    (plan_root / "content_plan_v1_1.json").unlink()
    (plan_root / "content_plan_v1_1_1.json").unlink()

    second = subject.resolve_generation_content_plan(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )

    assert first["remote_model_called"] is True
    assert second["remote_model_called"] is False
    assert second["candidate_plan_recovered"] is True
    assert calls["generate"] == 1
    assert calls["v1_1"] == 2
    assert calls["v1_1_1"] == 2


def test_retry_recovers_all_three_plan_stages(tmp_path: Path, monkeypatch):
    stage_authorities(tmp_path)
    monkeypatch.setattr(subject, "has_ledger_worthy_historical_exposure", lambda *a, **k: False)
    calls = patch_runtime(monkeypatch)

    first = subject.resolve_generation_content_plan(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    second = subject.resolve_generation_content_plan(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )

    assert first["content_plan_sha256"] == second["content_plan_sha256"]
    assert second["candidate_plan_recovered"] is True
    assert second["v1_1_plan_recovered"] is True
    assert second["final_plan_recovered"] is True
    assert second["remote_model_called"] is False
    assert calls["generate"] == 1


def test_history_without_ledger_fails_closed(tmp_path: Path, monkeypatch):
    stage_authorities(tmp_path)
    monkeypatch.setattr(subject, "has_ledger_worthy_historical_exposure", lambda *a, **k: True)

    with pytest.raises(subject.ContentPlanResolutionError) as exc:
        subject.resolve_generation_content_plan(
            pipeline_root=tmp_path,
            request_id=REQUEST_ID,
            transport=fake_transport,
            model="fake-model",
        )
    assert exc.value.code == "CONTENT_HISTORY_WITHOUT_LEDGER"


def test_strong_history_without_fact_atom_catalog_fails_closed(tmp_path: Path, monkeypatch):
    stage_authorities(tmp_path)
    ledger_path = tmp_path / "data/content_ledgers" / BUSINESS_ID / "content_ledger_v1.json"
    write_json(
        ledger_path,
        {
            "schema_version": "content-ledger-v1.0",
            "business_id": BUSINESS_ID,
            "entries": [
                {
                    "content_id": "old_001",
                    "business_id": BUSINESS_ID,
                    "status": "exported",
                }
            ],
        },
    )
    patch_runtime(monkeypatch)

    with pytest.raises(subject.ContentPlanResolutionError) as exc:
        subject.resolve_generation_content_plan(
            pipeline_root=tmp_path,
            request_id=REQUEST_ID,
            transport=fake_transport,
            model="fake-model",
        )
    assert exc.value.code == "CONTENT_LEDGER_CLOSURE_AUTHORITY_INCOMPLETE"


def test_final_plan_is_v1_1_1_and_does_not_pad(tmp_path: Path, monkeypatch):
    stage_authorities(tmp_path)
    monkeypatch.setattr(subject, "has_ledger_worthy_historical_exposure", lambda *a, **k: False)
    patch_runtime(monkeypatch, final_selected=("CONCEPT_002",))

    result = subject.resolve_generation_content_plan(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    final = json.loads(Path(result["content_plan_path"]).read_text(encoding="utf-8"))

    assert final["schema_version"] == "content-plan-v1.1.1"
    assert final["capacity"]["selected_quantity"] == 1
    assert final["capacity"]["padding_generated"] is False
    assert final["capacity"]["script_generation_performed"] is False
    assert result["generation_batch_created"] is False
    assert result["content_ledger_written"] is False
    assert not (tmp_path / "data/generation_batches").exists()


def test_unsupported_source_coverage_still_blocks(tmp_path: Path):
    stage_authorities(tmp_path, coverage_status="insufficient")
    with pytest.raises(subject.ContentPlanResolutionError) as exc:
        subject.resolve_generation_content_plan(
            pipeline_root=tmp_path,
            request_id=REQUEST_ID,
            transport=fake_transport,
            model="fake-model",
        )
    assert exc.value.code == "CONTENT_PLAN_SOURCE_COVERAGE_UNSUPPORTED"
