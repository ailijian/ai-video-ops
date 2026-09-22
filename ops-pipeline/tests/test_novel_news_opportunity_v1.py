from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import match_generation_sources_v1 as matcher
import novel_news_opportunity_v1 as subject
from content_quality_v1 import build_fact_atom_catalog
from show_customer_status_v1 import sha256_file


def known(value: str) -> dict:
    return {"state": "known", "value": value, "source_refs": []}


def source_fixture(tmp_path: Path, monkeypatch, *, history: list[dict] | None = None):
    business_path = tmp_path / "business_persona_v1.json"
    speaker_path = tmp_path / "speaker_persona_v1.json"
    business = {
        "persona_id": "customer_a", "revision": 1,
        "facts": {
            "pricing_facts": known("素菜加工通常约8元"),
            "business_volume_fact": known("每天接待100位顾客"),
            "included_service_facts": known("调味料免费提供"),
        },
    }
    speaker = {"persona_id": "speaker_a", "revision": 1, "facts": {"public_role": known("厨师")}}
    business_path.write_text(json.dumps(business, ensure_ascii=False), encoding="utf-8")
    speaker_path.write_text(json.dumps(speaker, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(subject, "resolve_current_persona", lambda root, business_id, scope: {"path": business_path, "artifact": business})
    monkeypatch.setattr(subject, "resolve_speaker_persona", lambda root, resolved, speaker_id: {"path": speaker_path, "artifact": speaker})
    monkeypatch.setattr(subject, "preview_generation_feasibility", lambda **kwargs: {"status": "supported", "eligible_pattern_count": 1, "eligible_case_count": 1})
    if history is not None:
        ledger_path = tmp_path / "data/content_ledgers/customer_a/content_ledger_v1.json"
        ledger_path.parent.mkdir(parents=True)
        ledger_path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(subject, "load_content_ledger", lambda root, business_id: {"artifact": {"entries": history, "fact_atom_catalog": []}})
    return business, business_path


def test_price_opportunity_uses_approved_fact_atom_and_preserves_qualifier(tmp_path: Path, monkeypatch) -> None:
    business, path = source_fixture(tmp_path, monkeypatch)
    projection = subject.project_novel_news_opportunities(pipeline_root=tmp_path, business_id="customer_a", speaker_id="speaker_a")
    assert projection["available_novel_count"] == projection["production_ready_count"] == 1
    item = projection["opportunities"][0]
    assert item["primary_fact_refs"] == ["pricing_facts"]
    assert item["central_claim"] == "素菜加工通常约8元"
    assert item["fact_atom_refs"] == [build_fact_atom_catalog(business, sha256_file(path))[2]["fact_atom_id"]] or item["fact_atom_refs"][0].startswith("pricing_facts::")
    assert "source_fact_values" not in item


def test_price_opportunity_redacts_private_contact_before_preview(tmp_path: Path, monkeypatch) -> None:
    business, path = source_fixture(tmp_path, monkeypatch)
    business["facts"]["pricing_facts"] = known("素菜加工通常约8元，电话13800138000")
    path.write_text(json.dumps(business, ensure_ascii=False), encoding="utf-8")
    projection = subject.project_novel_news_opportunities(
        pipeline_root=tmp_path, business_id="customer_a", speaker_id="speaker_a"
    )
    assert projection["available_novel_count"] == 1
    assert "13800138000" not in json.dumps(projection, ensure_ascii=False)
    assert "素菜加工通常约8元" in projection["opportunities"][0]["central_claim"]


def test_prior_mix_semantic_memory_blocks_news_novel_but_not_other_business(tmp_path: Path, monkeypatch) -> None:
    business, path = source_fixture(tmp_path, monkeypatch)
    atom = next(item for item in build_fact_atom_catalog(business, sha256_file(path)) if item["field"] == "pricing_facts")
    history = [{
        "content_id": "mix_001", "status": "exported", "production_profile": "mix",
        "communicated_information_units": [{
            "explicitness": "explicit", "normalized_meaning": atom["normalized_meaning"],
            "fact_atom_refs": [atom["fact_atom_id"]],
        }],
    }]
    source_fixture(tmp_path, monkeypatch, history=history)
    old = subject.project_novel_news_opportunities(pipeline_root=tmp_path, business_id="customer_a", speaker_id="speaker_a")
    assert old["available_novel_count"] == 0
    assert old["opportunities"][0]["novelty_status"] == "already_communicated"
    other = tmp_path / "other"
    other.mkdir()
    source_fixture(other, monkeypatch)
    fresh = subject.project_novel_news_opportunities(pipeline_root=other, business_id="customer_b", speaker_id="speaker_b")
    assert fresh["available_novel_count"] == 1


def test_price_matcher_rejects_generic_numbers_and_supporting_only_price() -> None:
    pattern = {"pattern_id": matcher.NEWS_PRICE_PATTERN_ID, "status": "approved", "compatible_profiles": ["news"]}
    generic = matcher.selected_content_pattern_compatibility(
        {"primary_fact_refs": ["business_volume_fact"], "central_claim": "每天接待100位顾客"}, pattern, "news"
    )
    supporting = matcher.selected_content_pattern_compatibility(
        {"primary_fact_refs": ["product_or_service_facts"], "supporting_fact_refs": ["pricing_facts"]}, pattern, "news"
    )
    primary = matcher.selected_content_pattern_compatibility(
        {"primary_fact_refs": ["pricing_facts"], "central_claim": "素菜加工通常约8元"}, pattern, "news"
    )
    assert generic["compatible"] is False
    assert supporting["compatible"] is False
    assert primary["compatible"] is True


def test_scene_contrast_requires_explicit_state_correspondence() -> None:
    pattern = {"pattern_id": matcher.NEWS_SCENE_PATTERN_ID, "status": "approved", "compatible_profiles": ["news"]}
    absent = matcher.selected_content_pattern_compatibility({}, pattern, "news")
    explicit = matcher.selected_content_pattern_compatibility(
        {"approved_state_correspondence_refs": ["approved_correspondence"],
         "state_a_fact_atom_refs": ["state_a::approved"],
         "state_b_fact_atom_refs": ["state_b::approved"]}, pattern, "news"
    )
    assert absent["compatible"] is False
    assert explicit["compatible"] is True
