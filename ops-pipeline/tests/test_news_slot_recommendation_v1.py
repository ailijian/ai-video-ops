from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import news_slot_recommendation_v1 as subject


def atom(
    atom_id: str,
    field: str,
    text: str,
) -> dict:
    return {
        "fact_atom_id": atom_id,
        "field": field,
        "original_known_fact": text,
        "normalized_meaning": text,
    }


def ledger_with(
    atoms: list[dict],
    *,
    content_id: str = "content_001",
    central_claim: str = "素菜通常8-10元，清蒸约15元，红烧约18元左右。",
) -> dict:
    refs = [item["fact_atom_id"] for item in atoms]
    return {
        "schema_version": "content-ledger-v1.0",
        "business_id": "business_001",
        "fact_atom_catalog": atoms,
        "entries": [
            {
                "content_id": content_id,
                "status": "exported",
                "title": "历史内容",
                "central_claim": central_claim,
                "semantic_signature": {
                    "primary_fact_bundle": [
                        "pricing_facts",
                    ]
                },
                "primary_fact_atom_refs": [],
                "communicated_information_units": [
                    {
                        "information_unit_id": f"u{index}",
                        "fact_atom_refs": [ref],
                        "explicitness": "explicit",
                    }
                    for index, ref in enumerate(
                        refs,
                        start=1,
                    )
                ],
            }
        ],
    }


def shufang_atoms() -> list[dict]:
    return [
        atom("pricing_facts::1", "pricing_facts", "清蒸约 15 元"),
        atom("pricing_facts::2", "pricing_facts", "素菜加工费通常 8-10 元"),
        atom("pricing_facts::3", "pricing_facts", "红烧约 18 元左右"),
        atom("included_service_facts::1", "included_service_facts", "免费提供油盐酱料"),
        atom("included_service_facts::2", "included_service_facts", "免费提供米饭"),
        atom("differentiators::1", "differentiators", "加工价格公开清晰"),
        atom("product_or_service_facts::1", "product_or_service_facts", "素菜加工费多在 8-10 元"),
    ]


def test_cross_field_duplicate_is_collapsed_and_shufang_recommends_six():
    result = subject.build_recommendation(
        ledger=ledger_with(shufang_atoms()),
        business_id="business_001",
        content_id="content_001",
    )

    assert result["algorithm_version"] == "news-slot-recommendation-v1.1"
    assert result["status"] == "supported"
    assert result["raw_candidate_count"] == 7
    assert result["eligible_candidate_count"] == 6
    assert result["recommended_slot_count"] == 6
    assert len(result["suppressed_duplicate_candidates"]) == 1
    assert (
        result["suppressed_duplicate_candidates"][0]["field"]
        == "product_or_service_facts"
    )
    assert result["random_selection_used"] is False
    assert result["padding_generated"] is False


def test_first_anchor_follows_source_claim_order_not_fact_atom_id():
    result = subject.build_recommendation(
        ledger=ledger_with(shufang_atoms()),
        business_id="business_001",
        content_id="content_001",
    )

    first = result["selected_candidates"][0]
    assert first["field"] == "pricing_facts"
    assert "8-10" in first["original_known_fact"]


def test_caps_at_eight_without_random_sampling():
    atoms = [
        atom(
            f"pricing_facts::{index}",
            "pricing_facts",
            f"项目{index}价格{index}元",
        )
        for index in range(1, 11)
    ]

    result = subject.build_recommendation(
        ledger=ledger_with(
            atoms,
            central_claim="项目1价格1元，项目2价格2元，项目3价格3元。",
        ),
        business_id="business_001",
        content_id="content_001",
    )

    assert result["recommended_slot_count"] == 8
    assert len(result["selected_candidates"]) == 8
    assert result["random_selection_used"] is False


def test_low_value_tail_does_not_force_eight():
    atoms = [
        atom("pricing_facts::1", "pricing_facts", "A套餐99元"),
        atom("pricing_facts::2", "pricing_facts", "B套餐129元"),
        atom("pricing_facts::3", "pricing_facts", "C套餐159元"),
        atom("product_or_service_facts::1", "product_or_service_facts", "提供基础服务"),
        atom("product_or_service_facts::2", "product_or_service_facts", "提供附加服务"),
        atom("product_or_service_facts::3", "product_or_service_facts", "支持预约"),
        atom("product_or_service_facts::4", "product_or_service_facts", "门店可咨询"),
    ]

    result = subject.build_recommendation(
        ledger=ledger_with(
            atoms,
            central_claim="A套餐99元，B套餐129元，C套餐159元。",
        ),
        business_id="business_001",
        content_id="content_001",
    )

    assert result["status"] == "supported"
    assert result["recommended_slot_count"] == 4


def test_fewer_than_four_distinct_facts_is_capacity_insufficient():
    atoms = [
        atom("pricing_facts::1", "pricing_facts", "A套餐99元"),
        atom("pricing_facts::2", "pricing_facts", "B套餐129元"),
        atom("included_service_facts::1", "included_service_facts", "赠送一次基础服务"),
    ]

    result = subject.build_recommendation(
        ledger=ledger_with(
            atoms,
            central_claim="A套餐99元，B套餐129元。",
        ),
        business_id="business_001",
        content_id="content_001",
    )

    assert result["status"] == "capacity_insufficient"
    assert result["recommended_slot_count"] == 3
    assert result["padding_generated"] is False


def test_without_price_anchor_news_price_slice_is_unsupported():
    atoms = [
        atom("included_service_facts::1", "included_service_facts", "包含服务A"),
        atom("included_service_facts::2", "included_service_facts", "包含服务B"),
        atom("differentiators::1", "differentiators", "优势A"),
        atom("differentiators::2", "differentiators", "优势B"),
    ]

    result = subject.build_recommendation(
        ledger=ledger_with(
            atoms,
            central_claim="包含服务A、服务B。",
        ),
        business_id="business_001",
        content_id="content_001",
    )

    assert result["status"] == "unsupported_no_price_offer_anchor"
    assert result["recommended_slot_count"] == 0
