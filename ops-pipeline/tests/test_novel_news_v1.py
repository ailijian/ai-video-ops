from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import novel_news_v1 as subject
from content_quality_v1 import build_fact_atom_catalog, semantic_signature
from show_customer_status_v1 import sha256_file
from show_customer_status_v1 import _validated_novel_news_entries_after_mix


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def known(value: str) -> dict:
    return {"state": "known", "value": value, "source_refs": []}


def fixture(tmp_path: Path) -> tuple[Path, str, list[dict]]:
    root = tmp_path / "p"
    request_id = "gen_0123456789abcdef0123"
    business_path = root / "data/personas/business/revision_0001/persona_v1.json"
    speaker_path = root / "data/personas/speaker/revision_0001/persona_v1.json"
    business = {
        "persona_id": "business", "persona_scope": "business", "revision": 1,
        "facts": {
            "pricing_facts": known("素菜加工约8元"),
            "included_service_facts": known("调味料免费提供"),
            "product_or_service_facts": known("提供代炒菜服务"),
            "differentiators": known("现场透明加工"),
        },
    }
    speaker = {
        "persona_id": "speaker", "persona_scope": "speaker", "revision": 1,
        "business_persona_ref": {"persona_id": "business"},
        "facts": {"public_display_name": known("张师傅"), "public_role": known("厨师")},
    }
    write(business_path, business)
    write(speaker_path, speaker)
    atoms = build_fact_atom_catalog(business, sha256_file(business_path))
    by_field = {item["field"]: item for item in atoms}
    price_id = by_field["pricing_facts"]["fact_atom_id"]
    concept = {
        "concept_id": "news-price-fixture", "content_job": "price_offer_explanation",
        "audience_need": "understand_price", "primary_topic": "price_offer",
        "central_claim": "素菜加工约8元", "primary_fact_refs": ["pricing_facts"],
        "supporting_fact_refs": ["included_service_facts", "product_or_service_facts", "differentiators"],
        "primary_fact_atom_refs": [price_id], "fact_atom_refs": [price_id],
    }
    concept["semantic_signature"] = semantic_signature(concept, "business")
    request_path = root / "data/generation_requests" / request_id / "generation_request_v1.json"
    request = {
        "request_id": request_id, "target_profile": "news", "profile": "news",
        "reuse_intent": "novel_content", "quantity": 1, "persona_id": "business",
        "speaker_persona": "speaker", "created_at": "2026-09-22T00:00:00+00:00",
        "selected_content": concept,
        "lineage": {
            "business_persona_ref": {"path": str(business_path), "file_sha256": sha256_file(business_path)},
            "speaker_persona_ref": {"path": str(speaker_path), "file_sha256": sha256_file(speaker_path)},
        },
    }
    write(request_path, request)
    case_id = "7059858129298803968"
    pattern_path = root / "data/patterns/approved" / subject.PRICE_PATTERN / "pattern_v1.json"
    write(pattern_path, {
        "pattern_id": subject.PRICE_PATTERN, "status": "approved",
        "definition": {"invariants": ["price_or_offer_first_semantic_anchor"]},
        "scope": {"scope_limitation": "price_offer_led_only", "supported_case_ids": [case_id]},
        "evidence": [{"case_specific_fact": "Case title must not enter prompt"}],
    })
    fingerprint_path = root / "data/fingerprints" / case_id / "case_fingerprint_v1.json"
    write(fingerprint_path, {
        "case_id": case_id, "source_case_sha256": "fixture-approved-case-sha",
        "fingerprint_scope": "case_structural_evidence_only",
        "authority": {"case_specific_facts_transferred": False},
        "semantic_carrier_features": {"carrier_type": "on_screen_text_plus_visual_information_state", "continuous_narration_required": False, "micro_beat_count": 5},
        "visual_state_features": {"ordered_state_count": 5, "text_visual_relationship": "price_anchor_then_context"},
        "content_features": {"claims": ["Case title must not enter prompt"]},
    })
    write(root / "data/production_plans" / request_id / "generation_source_plan_v1.json", {
        "request_id": request_id, "request": {"request_sha": sha256_file(request_path)},
        "coverage": {"status": "supported"},
        "selected_patterns": [{"pattern_id": subject.PRICE_PATTERN, "approved_pattern_sha": sha256_file(pattern_path)}],
        "eligible_case_pool": [{"case_id": case_id, "approved_case_sha": "fixture-approved-case-sha", "fingerprint_sha": sha256_file(fingerprint_path)}],
    })
    template = ROOT / "output" / "新闻体视频制作文案导入模板.xlsx"
    target = root / "output" / template.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, target)
    write(root / "data/production_profiles/production_profile_registry_v1.json", {
        "profiles": {"news": {"export_contract": {"template_path": str(target), "template_sha256": sha256_file(target)}}},
    })
    beats = [
        {"semantic_role": "price_offer_first_semantic_anchor", "text": "素菜加工约8元", "visual_anchor": "价格牌", "duration_guidance": "约2秒", "source_fact_refs": [price_id]},
        {"semantic_role": "included_value_context", "text": "调味料免费提供", "visual_anchor": "调味料", "duration_guidance": "约2秒", "source_fact_refs": [by_field["included_service_facts"]["fact_atom_id"]]},
        {"semantic_role": "service_context", "text": "提供代炒菜服务", "visual_anchor": "厨房", "duration_guidance": "约2秒", "source_fact_refs": [by_field["product_or_service_facts"]["fact_atom_id"]]},
        {"semantic_role": "trust_context", "text": "现场透明加工", "visual_anchor": "现场", "duration_guidance": "约2秒", "source_fact_refs": [by_field["differentiators"]["fact_atom_id"]]},
    ]
    return root, request_id, beats


def test_novel_news_offline_generation_review_export_and_idempotency(tmp_path: Path) -> None:
    root, request_id, beats = fixture(tmp_path)
    prompts: list[str] = []

    def fake_transport(prompt: str) -> dict:
        prompts.append(prompt)
        return {"payload": {"beats": beats}, "response_sha256": "fixture"}

    plan = subject.generate_novel_news_plan(pipeline_root=root, request_id=request_id, transport=fake_transport)
    assert len(prompts) == 1
    assert "7059858129298803968" in prompts[0]
    assert "Case title" not in prompts[0]
    assert "price_or_offer_first_semantic_anchor" in prompts[0]
    assert "price_anchor_then_context" in prompts[0]
    assert len(plan["micro_information_beats"]) == 4
    assert plan["status"] == "review_required"
    with pytest.raises(subject.NovelNewsError):
        subject.review_novel_news_plan(
            pipeline_root=root, request_id=request_id, reviewer="operator",
            decisions=[{"beat_id": f"B{i:03d}", "decision": "rejected" if i == 1 else "approved"} for i in range(1, 5)],
        )
    with pytest.raises(subject.NovelNewsError):
        subject.review_novel_news_plan(
            pipeline_root=root, request_id=request_id, reviewer="operator",
            decisions=[{"beat_id": f"B{i:03d}", "decision": "revised" if i == 1 else "approved", "revised_text": "素菜加工约8元限量100份"} for i in range(1, 5)],
        )
    approved = subject.review_novel_news_plan(
        pipeline_root=root, request_id=request_id, reviewer="operator",
        decisions=[{"beat_id": f"B{i:03d}", "decision": "approved"} for i in range(1, 5)],
    )
    assert approved["human_gate"] is True
    first = subject.export_novel_news(pipeline_root=root, request_id=request_id, exported_by="operator")
    second = subject.export_novel_news(pipeline_root=root, request_id=request_id, exported_by="operator")
    assert first["new_semantic_content_count_delta"] == second["new_semantic_content_count_delta"] == 1
    ledger = json.loads((root / "data/content_ledgers/business/content_ledger_v1.json").read_text(encoding="utf-8"))
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["reuse_intent"] == "novel_content"
    assert len(ledger["entries"][0]["communicated_information_units"]) > 0
    presentations = ledger["extensions"]["presentation_history_v1"]["entries"]
    assert len(presentations) == 1
    assert presentations[0]["new_semantic_content_count_delta"] == 0


def test_beat_validation_requires_primary_price_and_approved_atom(tmp_path: Path) -> None:
    root, request_id, beats = fixture(tmp_path)
    context = subject._source_context(root, request_id)
    unsupported = [dict(item) for item in beats]
    unsupported[0]["source_fact_refs"] = ["business_volume_fact::fake"]
    with pytest.raises(subject.NovelNewsError, match="outside Approved"):
        subject._normalize_beats(unsupported, context)
    wrong_anchor = [dict(item) for item in beats]
    wrong_anchor[0]["semantic_role"] = "service_context"
    with pytest.raises(subject.NovelNewsError, match="First beat"):
        subject._normalize_beats(wrong_anchor, context)
    invented = [dict(item) for item in beats]
    invented[2]["text"] = "张师傅亲自提供代炒菜服务"
    with pytest.raises(subject.NovelNewsError, match="exact grounded excerpt"):
        subject._normalize_beats(invented, context)
    with pytest.raises(subject.NovelNewsError, match="4–8"):
        subject._normalize_beats(beats[:3], context)


def test_model_prompt_uses_privacy_safe_fact_atoms(tmp_path: Path) -> None:
    root, request_id, beats = fixture(tmp_path)
    request_path = root / "data/generation_requests" / request_id / "generation_request_v1.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    persona_path = Path(request["lineage"]["business_persona_ref"]["path"])
    persona = json.loads(persona_path.read_text(encoding="utf-8"))
    persona["facts"]["included_service_facts"] = known("调味料免费提供，联系13800138000")
    write(persona_path, persona)
    request["lineage"]["business_persona_ref"]["file_sha256"] = sha256_file(persona_path)
    atoms = build_fact_atom_catalog(persona, sha256_file(persona_path))
    by_field = {item["field"]: item for item in atoms}
    price_id = by_field["pricing_facts"]["fact_atom_id"]
    request["selected_content"]["primary_fact_atom_refs"] = [price_id]
    request["selected_content"]["fact_atom_refs"] = [price_id]
    write(request_path, request)
    source_path = root / "data/production_plans" / request_id / "generation_source_plan_v1.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["request"]["request_sha"] = sha256_file(request_path)
    write(source_path, source)
    for beat, field in zip(
        beats,
        ("pricing_facts", "included_service_facts", "product_or_service_facts", "differentiators"),
    ):
        beat["source_fact_refs"] = [by_field[field]["fact_atom_id"]]
    prompts: list[str] = []

    def fake_transport(prompt: str) -> dict:
        prompts.append(prompt)
        return {"payload": {"beats": beats}, "response_sha256": "fixture"}

    subject.generate_novel_news_plan(pipeline_root=root, request_id=request_id, transport=fake_transport)
    assert "13800138000" not in prompts[0]
    assert "调味料免费提供" in prompts[0]


def test_structural_fingerprint_change_fails_closed_before_model_call(tmp_path: Path) -> None:
    root, request_id, _ = fixture(tmp_path)
    fingerprint_path = root / "data/fingerprints/7059858129298803968/case_fingerprint_v1.json"
    fingerprint = json.loads(fingerprint_path.read_text(encoding="utf-8"))
    fingerprint["visual_state_features"]["ordered_state_count"] = 99
    write(fingerprint_path, fingerprint)
    prompts: list[str] = []
    with pytest.raises(subject.NovelNewsError, match="Fingerprint changed"):
        subject.generate_novel_news_plan(
            pipeline_root=root, request_id=request_id,
            transport=lambda prompt: prompts.append(prompt) or {},
        )
    assert prompts == []


def test_review_recovers_matching_sidecar_without_changing_human_decision(tmp_path: Path) -> None:
    root, request_id, beats = fixture(tmp_path)
    subject.generate_novel_news_plan(
        pipeline_root=root, request_id=request_id,
        transport=lambda prompt: {"payload": {"beats": beats}, "response_sha256": "fixture"},
    )
    decisions = [{"beat_id": f"B{i:03d}", "decision": "approved"} for i in range(1, 5)]
    paths = subject._paths(root, request_id)
    write(paths["review"], {
        "schema_version": subject.REVIEW_SCHEMA, "request_id": request_id,
        "reviewed_by": "operator", "reviewed_at": "2026-09-22T01:00:00+00:00", "decisions": decisions,
    })
    subject.review_novel_news_plan(
        pipeline_root=root, request_id=request_id, reviewer="operator", decisions=decisions,
    )
    assert paths["approved"].is_file()


def test_export_rechecks_business_wide_novelty_after_request(tmp_path: Path) -> None:
    root, request_id, beats = fixture(tmp_path)
    subject.generate_novel_news_plan(
        pipeline_root=root, request_id=request_id,
        transport=lambda prompt: {"payload": {"beats": beats}, "response_sha256": "fixture"},
    )
    subject.review_novel_news_plan(
        pipeline_root=root, request_id=request_id, reviewer="operator",
        decisions=[{"beat_id": f"B{i:03d}", "decision": "approved"} for i in range(1, 5)],
    )
    context = subject._source_context(root, request_id)
    atom_id = next(iter(context["primary_atoms"]))
    ledger = subject._empty_ledger(business_id="business", created_at="2026-09-22T00:00:00+00:00")
    ledger["entries"] = [{
        "content_id": "earlier_mix_content", "status": "exported", "production_profile": "mix",
        "communicated_information_units": [{
            "explicitness": "explicit", "normalized_meaning": "素菜加工约8元",
            "fact_atom_refs": [atom_id],
        }],
    }]
    ledger_path = root / "data/content_ledgers/business/content_ledger_v1.json"
    write(ledger_path, ledger)
    with pytest.raises(subject.NovelNewsError, match="already communicated"):
        subject.export_novel_news(pipeline_root=root, request_id=request_id, exported_by="operator")
    assert len(json.loads(ledger_path.read_text(encoding="utf-8"))["entries"]) == 1
    paths = subject._paths(root, request_id)
    assert not paths["receipt"].exists()
    assert not (root / "output" / f"News新内容_{request_id}.xlsx").exists()


def test_mix_capacity_can_reproject_only_after_valid_novel_news_semantic_append(tmp_path: Path) -> None:
    root = tmp_path / "p"
    request_id = "gen_newsexport001"
    request_path = root / "data/generation_requests" / request_id / "generation_request_v1.json"
    approval_path = root / "data/generation_batches" / request_id / "approved_novel_news_v1.json"
    receipt_path = approval_path.with_name("novel_news_export_receipt_v1.json")
    closure_path = approval_path.with_name("novel_news_export_closure_v1.json")
    output_path = root / "output/news.xlsx"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"fixture-xlsx")
    write(request_path, {"request_id": request_id, "persona_id": "business", "target_profile": "news", "reuse_intent": "novel_content"})
    write(approval_path, {"request_id": request_id, "human_gate": True})
    write(receipt_path, {
        "request_id": request_id, "approved_ref": {"sha256": sha256_file(approval_path)},
        "output_path": str(output_path), "output_sha256": sha256_file(output_path),
    })
    write(closure_path, {"request_id": request_id, "semantic_entry_count_delta": 1, "validation": {"passed": True}})
    news_entry = {
        "content_id": request_id + "-N001", "batch_ref": request_id, "business_id": "business",
        "production_profile": "news", "reuse_intent": "novel_content", "status": "exported",
        "source_request_ref": {"path": str(request_path), "sha256": sha256_file(request_path)},
        "approved_review_ref": {"path": str(approval_path), "sha256": sha256_file(approval_path)},
        "export_receipt_ref": {"path": str(receipt_path), "sha256": sha256_file(receipt_path)},
    }
    entries = [{"batch_ref": "gen_mix001", "content_id": "mix-content"}, news_entry]
    assert _validated_novel_news_entries_after_mix(root, "business", {"entries": entries}, "gen_mix001")
    assert not _validated_novel_news_entries_after_mix(root, "other", {"entries": entries}, "gen_mix001")
    broken = [{**entries[0]}, {**news_entry, "reuse_intent": "cross_profile_repurpose"}]
    assert not _validated_novel_news_entries_after_mix(root, "business", {"entries": broken}, "gen_mix001")


def test_scene_runtime_is_fixture_routable_but_ordinary_production_is_human_gated(tmp_path: Path) -> None:
    root, request_id, _ = fixture(tmp_path)
    paths = subject._paths(root, request_id)
    request = json.loads(paths["request"].read_text(encoding="utf-8"))
    business_path = Path(request["lineage"]["business_persona_ref"]["path"])
    business = json.loads(business_path.read_text(encoding="utf-8"))
    business["facts"]["product_or_service_facts"] = known("此前顾客需要排队等待")
    business["facts"]["differentiators"] = known("现在顾客可以在线预约")
    write(business_path, business)
    request["lineage"]["business_persona_ref"]["file_sha256"] = sha256_file(business_path)
    atoms = build_fact_atom_catalog(business, sha256_file(business_path))
    by_field = {item["field"]: item for item in atoms}
    state_a = by_field["product_or_service_facts"]["fact_atom_id"]
    state_b = by_field["differentiators"]["fact_atom_id"]
    request["selected_content"] = {
        "concept_id": "scene-approved-fixture", "central_claim": "顾客预约方式前后变化",
        "semantic_signature": semantic_signature({"central_claim": "顾客预约方式前后变化"}, "business"),
        "primary_fact_refs": ["product_or_service_facts", "differentiators"],
        "supporting_fact_refs": ["included_service_facts", "pricing_facts"],
        "state_a_fact_atom_refs": [state_a], "state_b_fact_atom_refs": [state_b],
        "approved_state_correspondence_refs": ["human-confirmed-comparable-service-state"],
    }
    request["controlled_scene_validation"] = True
    write(paths["request"], request)
    source = json.loads(paths["source_plan"].read_text(encoding="utf-8"))
    source["request"]["request_sha"] = sha256_file(paths["request"])
    scene_pattern_path = root / "data/patterns/approved" / subject.SCENE_PATTERN / "pattern_v1.json"
    write(scene_pattern_path, {
        "pattern_id": subject.SCENE_PATTERN, "status": "approved",
        "definition": {"invariants": ["approved_state_a_to_b_correspondence"]},
        "scope": {"scope_limitation": "scene_contrast_only", "supported_case_ids": ["7059858129298803968"]},
    })
    source["selected_patterns"] = [{"pattern_id": subject.SCENE_PATTERN, "approved_pattern_sha": sha256_file(scene_pattern_path)}]
    write(paths["source_plan"], source)
    with pytest.raises(subject.NovelNewsError, match="Human-authorized"):
        subject._source_context(root, request_id)
    write(paths["request"].with_name("scene_contrast_real_validation_approval_v1.json"), {
        "schema_version": "scene-contrast-real-validation-approval-v1.0",
        "request_id": request_id, "request_sha256": sha256_file(paths["request"]),
        "human_gate": True, "correspondence_confirmed": True,
    })
    beats = [
        {"semantic_role": "state_a", "text": "此前顾客需要排队等待", "visual_anchor": "此前现场", "duration_guidance": "约2秒", "source_fact_refs": [state_a]},
        {"semantic_role": "included_value_context", "text": "调味料免费提供", "visual_anchor": "服务信息", "duration_guidance": "约2秒", "source_fact_refs": [by_field["included_service_facts"]["fact_atom_id"]]},
        {"semantic_role": "price_scope_information", "text": "素菜加工约8元", "visual_anchor": "价格信息", "duration_guidance": "约2秒", "source_fact_refs": [by_field["pricing_facts"]["fact_atom_id"]]},
        {"semantic_role": "state_b", "text": "现在顾客可以在线预约", "visual_anchor": "现在现场", "duration_guidance": "约2秒", "source_fact_refs": [state_b]},
    ]
    plan = subject.generate_novel_news_plan(
        pipeline_root=root, request_id=request_id,
        transport=lambda prompt: {"payload": {"beats": beats}, "response_sha256": "fixture"},
    )
    assert plan["selected_pattern_id"] == subject.SCENE_PATTERN
    invalid = [dict(item) for item in beats]
    invalid[-1]["semantic_role"] = "service_context"
    with pytest.raises(subject.NovelNewsError, match="State A"):
        subject._normalize_beats(invalid, subject._source_context(root, request_id))
