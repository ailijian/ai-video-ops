from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import generate_mix_scripts_v1 as generator  # noqa: E402
import resolve_generation_batch_v1 as subject  # noqa: E402


REQUEST_ID = "gen_script_test_001"
BUSINESS_ID = "fixture_pet_store"
SPEAKER_ID = "fixture_owner"
CASE_A = "case_a"
CASE_B = "case_b"
ATOM_A = "process_facts::atom_a"
ATOM_B = "process_facts::atom_b"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage_runtime(tmp_path: Path) -> dict[str, Path]:
    persona = tmp_path / "data/personas/business/revision_0001/persona_v1.json"
    speaker = tmp_path / "data/personas/speaker/revision_0001/persona_v1.json"
    request_path = tmp_path / "data/generation_requests" / REQUEST_ID / "generation_request_v1.json"
    source_path = tmp_path / "data/production_plans" / REQUEST_ID / "generation_source_plan_v1.json"
    pattern = tmp_path / "data/patterns/approved/pattern/pattern_v1.json"
    fp_a = tmp_path / "data/fingerprints" / CASE_A / "case_fingerprint_v1.json"
    fp_b = tmp_path / "data/fingerprints" / CASE_B / "case_fingerprint_v1.json"

    write_json(persona, {"persona_id": BUSINESS_ID})
    write_json(speaker, {"persona_id": SPEAKER_ID, "speaker_type": "owner_founder"})
    write_json(pattern, {"pattern_id": "pattern_001"})
    write_json(fp_a, {"case_id": CASE_A})
    write_json(fp_b, {"case_id": CASE_B})

    request = {
        "schema_version": "generation-request-v1.0",
        "request_id": REQUEST_ID,
        "created_at": "2026-09-18T00:00:00+00:00",
        "persona_id": BUSINESS_ID,
        "speaker_persona": SPEAKER_ID,
        "profile": "mix",
        "target_profile": "mix",
        "quantity": 2,
        "lifecycle": {"status": "created", "generation_started": False},
        "authority": {
            "script_generation_performed": False,
            "generation_batch_created": False,
        },
    }
    write_json(request_path, request)
    source = {
        "schema_version": "generation-source-plan-v1.0",
        "request_id": REQUEST_ID,
        "request": {"request_sha": sha256_file(request_path)},
        "coverage": {"status": "supported"},
        "selected_patterns": [{"pattern_id": "pattern_001"}],
        "eligible_case_pool": [
            {"case_id": CASE_A, "fingerprint_sha": sha256_file(fp_a)},
            {"case_id": CASE_B, "fingerprint_sha": sha256_file(fp_b)},
        ],
        "rotation": {"case_rotation_order": [CASE_A, CASE_B]},
    }
    write_json(source_path, source)

    plan_root = tmp_path / "data/content_plans" / REQUEST_ID
    v1_path = plan_root / "content_plan_v1.json"
    v1 = {
        "schema_version": "content-plan-v1.0",
        "request_id": REQUEST_ID,
        "planning_call": {
            "remote_model_call_performed": True,
            "remote_model_call_count": 1,
            "model": "deepseek-flash",
            "usage": {"total_tokens": 100},
        },
        "candidate_pool": {"configured_size": 8, "received_size": 8},
        "reuse_intent_contract": {"novel_content": True},
    }
    write_json(v1_path, v1)

    v11_path = plan_root / "content_plan_v1_1.json"
    write_json(v11_path, {"schema_version": "content-plan-v1.1", "request_id": REQUEST_ID})

    final_path = plan_root / "content_plan_v1_1_1.json"
    final = {
        "schema_version": "content-plan-v1.1.1",
        "quality_engine_version": "content-uniqueness-editorial-quality-v1.1.1",
        "created_at": "2026-09-18T00:00:00+00:00",
        "request_id": REQUEST_ID,
        "business_id": BUSINESS_ID,
        "speaker_id": SPEAKER_ID,
        "speaker_type": "owner_founder",
        "profile": "mix",
        "target_profile": "mix",
        "capacity": {
            "requested_quantity": 2,
            "high_quality_novel_capacity": 2,
            "selected_quantity": 2,
            "status": "supported",
            "padding_generated": False,
            "script_generation_performed": False,
        },
        "selected_concepts": [
            {
                "concept_id": "CONCEPT_001",
                "audience_need": "先检查吗",
                "content_job": "说明洗护前先检查",
                "primary_topic": "洗护前检查",
                "primary_fact_refs": ["process_facts"],
                "supporting_fact_refs": [],
                "speaker_fact_refs": ["first_person_allowed_topics"],
                "central_claim": "洗护前先检查宠物的皮肤和毛发状态。",
                "semantic_signature": {
                    "business_id": BUSINESS_ID,
                    "central_claim_key": "precheck",
                },
                "opening_strategy": "直接进入检查",
                "narrative_mode": "流程说明",
                "exclusive_anchor": {"value": "洗护前先检查皮肤毛发"},
                "visual_anchor": "检查皮肤毛发",
                "v1_1_1_gate_decision": "high_quality_novel",
                "material_information_gain_v1_1_1": {
                    "material_information_gain": True,
                    "reason": "new_fact_atom_adds_independent_editorial_or_decision_value",
                    "primary_fact_atom_refs": [ATOM_A],
                    "novel_primary_fact_atom_refs": [ATOM_A],
                },
                "editorial_score_v1_1_1": {"weighted_total": 3.98},
            },
            {
                "concept_id": "CONCEPT_002",
                "audience_need": "为什么处理方式不同",
                "content_job": "说明根据当时状态决定处理方式",
                "primary_topic": "根据状态决定洗护方式",
                "primary_fact_refs": ["process_facts"],
                "supporting_fact_refs": [],
                "speaker_fact_refs": ["first_person_allowed_topics"],
                "central_claim": "具体处理根据宠物当时的皮肤、毛发和实际状态判断。",
                "semantic_signature": {
                    "business_id": BUSINESS_ID,
                    "central_claim_key": "conditiondecision",
                },
                "opening_strategy": "从判断进入",
                "narrative_mode": "判断逻辑说明",
                "exclusive_anchor": {"value": "根据状态决定处理"},
                "visual_anchor": "观察状态后决定处理",
                "v1_1_1_gate_decision": "high_quality_novel",
                "material_information_gain_v1_1_1": {
                    "material_information_gain": True,
                    "reason": "new_fact_atom_adds_independent_editorial_or_decision_value",
                    "primary_fact_atom_refs": [ATOM_B],
                    "novel_primary_fact_atom_refs": [ATOM_B],
                },
                "editorial_score_v1_1_1": {"weighted_total": 3.98},
            },
        ],
        "lineage": {
            "source_v1_1_content_plan_sha256": sha256_file(v11_path),
            "preserved_source_artifacts": {"content_plan_v1": sha256_file(v1_path)},
        },
        "source_remote_planning": {
            "source_content_plan_v1_sha256": sha256_file(v1_path),
            "performed": True,
            "call_count": 1,
            "model": "deepseek-flash",
        },
    }
    write_json(final_path, final)
    return {
        "persona": persona,
        "speaker": speaker,
        "request": request_path,
        "source": source_path,
        "pattern": pattern,
        "fp_a": fp_a,
        "fp_b": fp_b,
        "v1": v1_path,
        "v11": v11_path,
        "final": final_path,
    }


def fake_context(paths: dict[str, Path]) -> dict:
    request = read_json(paths["request"])
    request["content_quality_v1"] = {
        "enabled": True,
        "candidate_pool_size": 8,
        "candidate_call_batch_size": 8,
        "minimum_editorial_score": 3.25,
    }
    return {
        "paths": {
            "persona": paths["persona"],
            "speaker_persona": paths["speaker"],
            "request": paths["request"],
            "source_plan": paths["source"],
            "pattern": paths["pattern"],
        },
        "persona": {"persona_id": BUSINESS_ID},
        "speaker_persona": {"persona_id": SPEAKER_ID, "speaker_type": "owner_founder"},
        "request": request,
        "source_plan": read_json(paths["source"]),
        "pattern": {"pattern_id": "pattern_001"},
        "fingerprints": {
            CASE_A: {"path": str(paths["fp_a"]), "sha256": sha256_file(paths["fp_a"]), "surrogate_ref": "CASE_REF_001"},
            CASE_B: {"path": str(paths["fp_b"]), "sha256": sha256_file(paths["fp_b"]), "surrogate_ref": "CASE_REF_002"},
        },
    }


def closure_memory() -> dict:
    return {
        "schema_version": "content-ledger-v1.0",
        "business_id": BUSINESS_ID,
        "entries": [],
        "fact_atom_catalog": [
            {
                "fact_atom_id": ATOM_A,
                "field": "process_facts",
                "normalized_meaning": "洗护前先检查宠物的皮肤和毛发状态",
                "original_known_fact": "洗护前先检查宠物的皮肤和毛发状态",
            },
            {
                "fact_atom_id": ATOM_B,
                "field": "process_facts",
                "normalized_meaning": "具体处理根据宠物当时的皮肤毛发和实际状态判断",
                "original_known_fact": "具体处理根据宠物当时的皮肤、毛发和实际状态判断",
            },
        ],
    }


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def patch_runtime(monkeypatch, paths: dict[str, Path], *, leak: bool = False, missing_own: bool = False):
    context = fake_context(paths)
    base_memory = {"schema_version": "content-ledger-v1.0", "business_id": BUSINESS_ID, "entries": []}
    closure = closure_memory()
    calls = {"generate_batch": 0, "validate_final": 0}

    monkeypatch.setattr(
        subject.content_plan_runtime,
        "load_request_and_source_plan",
        lambda pipeline_root, request_id: (
            paths["request"], read_json(paths["request"]), paths["source"], read_json(paths["source"])
        ),
    )
    monkeypatch.setattr(
        subject.content_plan_runtime,
        "content_quality_contract",
        lambda request: (
            {"enabled": True, "candidate_pool_size": 8, "candidate_call_batch_size": 8, "minimum_editorial_score": 3.25},
            "console_v1_runtime_default",
        ),
    )
    monkeypatch.setattr(
        subject.content_plan_runtime,
        "resolve_base_planning_memory",
        lambda pipeline_root, request: (copy.deepcopy(base_memory), "ephemeral_empty_history_projection"),
    )
    monkeypatch.setattr(subject.content_plan_runtime, "build_context", lambda **kwargs: copy.deepcopy(context))
    monkeypatch.setattr(
        subject.content_plan_runtime,
        "build_runtime_contract",
        lambda **kwargs: {"schema_version": "content-planning-runtime-contract-v1.0", "fixture": True},
    )
    monkeypatch.setattr(
        subject.content_plan_runtime,
        "build_closure_memory",
        lambda **kwargs: copy.deepcopy(closure),
    )

    def validate_final(**kwargs):
        calls["validate_final"] += 1
    monkeypatch.setattr(subject.content_plan_runtime, "validate_final_plan", validate_final)
    monkeypatch.setattr(subject, "validate_content_plan_input", lambda *args, **kwargs: None)

    def fake_generate_batch(context_value, model, max_attempts, transport, content_plan, content_ledger, created_at=None):
        calls["generate_batch"] += 1
        contents = []
        for index, concept in enumerate(content_plan["selected_concepts"], start=1):
            if concept["concept_id"] == "CONCEPT_001":
                narration = (
                    "这一步会先检查宠物的皮肤和毛发状态。"
                    if not missing_own
                    else "到店后会先做准备。"
                )
                if leak:
                    narration += "具体处理还会根据宠物当时的皮肤、毛发和实际状态判断。"
            else:
                narration = "具体处理根据宠物当时的皮肤、毛发和实际状态判断。"
            contents.append(
                {
                    "content_id": f"{REQUEST_ID}-C{index:03d}",
                    "concept_ref": concept["concept_id"],
                    "central_claim": concept["central_claim"],
                    "semantic_signature": copy.deepcopy(concept["semantic_signature"]),
                    "narration": narration,
                    "case_reference": {"case_id": concept["case_structural_ref"]},
                    "status": "generated",
                }
            )
        return {
            "schema_version": generator.SCHEMA_VERSION,
            "request_id": REQUEST_ID,
            "profile": "mix",
            "status": "review_required",
            "model": model,
            "contents": contents,
            "generated_count": len(contents),
            "generation_attempts": [{"attempt": 1}],
            "content_plan_ref": {"sha256": subject.canonical_sha256(content_plan)},
            "lineage": {"content_ledger": {"sha256": subject.canonical_sha256(content_ledger)}},
            "authority": {"human_review_required": True, "auto_approved": False},
            "validation": {},
        }
    monkeypatch.setattr(subject, "generate_batch", fake_generate_batch)

    def fake_write_batch(batch, output_root):
        directory = Path(output_root) / REQUEST_ID
        directory.mkdir(parents=True, exist_ok=True)
        batch_path = directory / "generation_batch_v1.json"
        review_path = directory / "generation_review_pack_v1.md"
        if batch_path.exists() or review_path.exists():
            raise RuntimeError("exists")
        write_json(batch_path, batch)
        review_path.write_text("fixture review", encoding="utf-8")
        return batch_path, review_path, sha256_file(batch_path)
    monkeypatch.setattr(subject, "write_batch", fake_write_batch)
    monkeypatch.setattr(
        subject,
        "write_review_pack_for_existing_batch",
        lambda batch_path, output_path=None: (
            output_path.write_text("recovered review", encoding="utf-8") if output_path else None
        ),
    )
    return calls, context, closure


def fake_transport(prompt: str) -> dict:
    raise AssertionError("Wrapper test should not directly invoke transport.")


def test_reuses_existing_mix_generator():
    assert subject.generate_batch is generator.generate_batch
    assert subject.validate_content_plan_input is generator.validate_content_plan_input


def test_generation_projection_uses_final_selection_and_reassigns_cases(tmp_path: Path, monkeypatch):
    paths = stage_runtime(tmp_path)
    calls, context, closure = patch_runtime(monkeypatch, paths)
    final = read_json(paths["final"])
    projection = subject.build_generation_content_plan_projection(
        context=context,
        source_plan=read_json(paths["source"]),
        v1_plan=read_json(paths["v1"]),
        final_plan=final,
        final_plan_path=paths["final"],
        closure_memory=closure,
        runtime_contract={"schema_version": "content-planning-runtime-contract-v1.0", "fixture": True},
    )
    assert [item["concept_id"] for item in projection["selected_concepts"]] == ["CONCEPT_001", "CONCEPT_002"]
    assert [item["case_structural_ref"] for item in projection["selected_concepts"]] == [CASE_A, CASE_B]
    assert projection["selected_concepts"][0]["generation_constraints"]["must_express_selected_material_centers"][0]["fact_atom_ref"] == ATOM_A
    assert projection["selected_concepts"][0]["generation_constraints"]["must_not_absorb_other_selected_material_centers"][0]["fact_atom_ref"] == ATOM_B


def test_first_run_generates_batch_from_final_v111_only(tmp_path: Path, monkeypatch):
    paths = stage_runtime(tmp_path)
    calls, _, _ = patch_runtime(monkeypatch, paths)
    result = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    assert calls["generate_batch"] == 1
    assert calls["validate_final"] == 1
    assert result["selected_concept_ids"] == ["CONCEPT_001", "CONCEPT_002"]
    assert result["generated_concept_ids"] == ["CONCEPT_001", "CONCEPT_002"]
    assert result["ready_for_human_review"] is True
    assert result["remote_model_called"] is True
    assert result["human_approval_performed"] is False
    assert result["content_ledger_written"] is False
    assert result["excel_exported"] is False
    assert subject.candidate_cache_path(tmp_path, REQUEST_ID).is_file()


def test_retry_recovers_without_second_model_call(tmp_path: Path, monkeypatch):
    paths = stage_runtime(tmp_path)
    calls, _, _ = patch_runtime(monkeypatch, paths)
    first = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    second = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    assert calls["generate_batch"] == 1
    assert first["generation_batch_sha256"] == second["generation_batch_sha256"]
    assert second["recovered"] is True
    assert second["remote_model_called"] is False
    assert second["generation_batch_created"] is False


def test_cross_concept_material_overlap_is_human_review_flag(
    tmp_path: Path, monkeypatch
):
    paths = stage_runtime(tmp_path)
    calls, _, _ = patch_runtime(monkeypatch, paths, leak=True)

    result = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )

    assert calls["generate_batch"] == 1
    assert result["ready_for_human_review"] is True
    assert result["remote_model_called"] is True
    assert subject.candidate_cache_path(tmp_path, REQUEST_ID).is_file()

    batch = read_json(Path(result["generation_batch_path"]))
    validation = (
        batch["script_generation_contract"]["material_center_validation"]
    )
    assert validation["passed"] is True
    assert any(
        "cross_concept_material_overlap_requires_human_review"
        in flag
        for flag in validation["human_review_flags"]
    )
    assert any(
        "cross_concept_material_overlap_requires_human_review"
        in (item.get("potential_review_flags") or [])
        for item in batch["contents"]
    )


def test_uncertain_own_narration_match_is_human_review_flag_not_false_hard_failure(
    tmp_path: Path, monkeypatch
):
    paths = stage_runtime(tmp_path)
    patch_runtime(monkeypatch, paths, missing_own=True)
    result = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    assert result["ready_for_human_review"] is True
    batch = read_json(Path(result["generation_batch_path"]))
    flags = (
        batch["script_generation_contract"]["material_center_validation"]
        .get("human_review_flags", [])
    )
    assert any("CONCEPT_001" in flag for flag in flags)



def test_candidate_cache_allows_offline_recovery_without_second_model_call(
    tmp_path: Path, monkeypatch
):
    paths = stage_runtime(tmp_path)
    calls, _, _ = patch_runtime(monkeypatch, paths)

    first = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    assert calls["generate_batch"] == 1
    assert first["remote_model_called"] is True
    assert subject.candidate_cache_path(tmp_path, REQUEST_ID).is_file()

    batch_path = Path(first["generation_batch_path"])
    review_path = Path(first["review_pack_path"])
    batch_path.unlink()
    review_path.unlink()

    second = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )

    assert calls["generate_batch"] == 1
    assert second["candidate_recovered"] is True
    assert second["remote_model_called"] is False
    assert second["ready_for_human_review"] is True

def test_final_content_plan_is_required(tmp_path: Path, monkeypatch):
    paths = stage_runtime(tmp_path)
    patch_runtime(monkeypatch, paths)
    paths["final"].unlink()
    with pytest.raises(subject.GenerationBatchResolutionError) as exc:
        subject.resolve_generation_batch(
            pipeline_root=tmp_path,
            request_id=REQUEST_ID,
            transport=fake_transport,
            model="fake-model",
        )
    assert exc.value.code == "FINAL_CONTENT_PLAN_REQUIRED"


def test_existing_batch_lineage_drift_fails_closed(tmp_path: Path, monkeypatch):
    paths = stage_runtime(tmp_path)
    patch_runtime(monkeypatch, paths)
    result = subject.resolve_generation_batch(
        pipeline_root=tmp_path,
        request_id=REQUEST_ID,
        transport=fake_transport,
        model="fake-model",
    )
    batch_path = Path(result["generation_batch_path"])
    batch = read_json(batch_path)
    batch["script_generation_contract"]["final_content_plan_ref"]["sha256"] = "0" * 64
    write_json(batch_path, batch)
    with pytest.raises(subject.GenerationBatchResolutionError) as exc:
        subject.resolve_generation_batch(
            pipeline_root=tmp_path,
            request_id=REQUEST_ID,
            transport=fake_transport,
            model="fake-model",
        )
    assert exc.value.code == "GENERATION_BATCH_LINEAGE_MISMATCH"
