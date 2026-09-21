from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from approve_persona_v1 import approve_persona  # noqa: E402
from build_persona_v1 import (  # noqa: E402
    assess_business_persona_capabilities,
    build_persona,
    validate_required_fact_authority,
)
from customer_fact_review_v1 import required_business_blockers  # noqa: E402
from customer_intake_v1 import (  # noqa: E402
    assess_persona_onboarding_readiness,
    build_customer_intake,
    build_initial_content_capacity_handoff,
)


def known(value: Any) -> dict[str, Any]:
    return {"state": "known", "value": value, "source_refs": ["fixture"]}


def unknown() -> dict[str, Any]:
    return {"state": "unknown", "value": None, "source_refs": []}


def facts(**values: Any) -> dict[str, dict[str, Any]]:
    return {field: known(value) for field, value in values.items()}


def candidate_artifact(authority_facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "fact_candidates": [
            {
                "fact_candidate_id": f"C-{index:03d}",
                "persona_scope": "business",
                "target_field": field,
                "candidate_state": "known_candidate",
                "normalized_value": fact["value"],
            }
            for index, (field, fact) in enumerate(authority_facts.items(), start=1)
        ]
    }


def persona_input(authority_facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "persona_id": "readiness_fixture",
        "revision": 1,
        "persona_scope": "business",
        "source_type": "test_fixture",
        "facts": authority_facts,
    }


def test_use_case_and_process_are_ready_without_audience_or_pains() -> None:
    authority_facts = facts(
        public_display_name="测试门店",
        industry="本地生活",
        primary_products_or_services=["上门维修"],
        customer_use_cases=["顾客家中水管突然漏水时预约上门"],
        service_process=["确认地址后上门检查并报价"],
    )
    authority_facts["core_audience"] = unknown()
    authority_facts["customer_pains"] = unknown()
    readiness = assess_business_persona_capabilities(authority_facts)
    assert readiness["ready"] is True
    assert required_business_blockers(persona_input(authority_facts)) == []
    assert validate_required_fact_authority(persona_input(authority_facts)) == []


def test_audience_and_pricing_are_ready_without_customer_pains() -> None:
    authority_facts = facts(
        public_display_name="测试门店",
        industry="餐饮",
        primary_products_or_services=["社区午餐"],
        core_audience=["附近居民"],
        pricing_facts=["午餐按实际选菜计价"],
    )
    authority_facts["customer_pains"] = unknown()
    readiness = assess_business_persona_capabilities(authority_facts)
    assert readiness["ready"] is True
    assert readiness["capability_groups"]["customer_use_context"]["satisfied"] is True


def test_name_and_industry_only_are_insufficient() -> None:
    readiness = assess_business_persona_capabilities(
        facts(public_display_name="测试门店", industry="餐饮")
    )
    assert readiness["ready"] is False
    assert set(readiness["blockers"]) == {
        "business_identity",
        "customer_use_context",
        "production_bearing_facts",
    }


def test_generic_praise_is_not_a_production_bearing_fact() -> None:
    readiness = assess_business_persona_capabilities(
        facts(
            public_display_name="测试门店",
            primary_products_or_services=["门店服务"],
            core_audience=["附近顾客"],
            differentiators=["我们很好"],
        )
    )
    assert readiness["ready"] is False
    assert readiness["blockers"] == ["production_bearing_facts"]


def test_unresolved_critical_conflict_blocks_capability_readiness() -> None:
    authority_facts = facts(
        public_display_name="测试门店",
        primary_products_or_services=["上门维修"],
        customer_use_cases=["顾客预约后上门"],
        process_facts=["上门前先确认故障情况"],
    )
    intake = build_customer_intake(
        intake_id="intake_0001",
        intake_type="initial_onboarding",
        provisional_business_id="readiness_fixture",
        business_ref=None,
        input_actor="authorized_business_representative",
        input_sources=[{"source_type": "fixture"}],
        raw_answers=[],
        speaker_selection={"speaker_type": "generic"},
        conflicts=[
            {
                "conflict_id": "critical-1",
                "severity": "critical",
                "resolved": False,
            }
        ],
    )
    readiness = assess_persona_onboarding_readiness(
        intake,
        candidate_artifact(authority_facts),
    )
    assert readiness["status"] == "insufficient"
    assert readiness["capability_groups"]["critical_constraints"]["satisfied"] is False
    assert "critical_constraints" in readiness["critical_missing_truth"]


def test_low_content_capacity_does_not_block_persona_approval(tmp_path: Path) -> None:
    authority_facts = facts(
        public_display_name="低容量测试客户",
        industry="本地生活",
        primary_products_or_services=["上门维修"],
        core_audience=["附近居民"],
        pricing_facts=["检查后按实际维修项目报价"],
    )
    input_path = tmp_path / "persona_input.json"
    input_path.write_text(
        json.dumps(
            {
                **persona_input(authority_facts),
                "persona_id": "low_capacity_customer",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    persona_path, _ = build_persona(
        input_path,
        tmp_path / "personas",
        created_at="2026-09-21T00:00:00+00:00",
    )
    approved, _, _ = approve_persona(
        persona_path,
        reviewer="测试审核人",
        note="能力组足够，允许确认客户档案。",
        approved_at="2026-09-21T00:01:00+00:00",
    )
    assert approved["lifecycle"]["status"] == "approved"
    capacity = build_initial_content_capacity_handoff(
        business_persona_path=persona_path,
        speaker_persona_path=None,
        requested_quantity=5,
        created_at="2026-09-21T00:02:00+00:00",
    )
    assert capacity["persona_production_ready"] is True
    assert capacity["capacity_status"] == "capacity_limited"
    assert capacity["content_gap_summary"]
