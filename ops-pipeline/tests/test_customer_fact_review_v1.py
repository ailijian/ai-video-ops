from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(
    name: str,
    filename: str,
):
    path = SCRIPTS / filename

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    assert spec and spec.loader

    module = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(module)

    return module


analysis = load_module(
    "customer_onboarding_analysis_v1_test",
    "customer_onboarding_analysis_v1.py",
)

review = load_module(
    "customer_fact_review_v1_test",
    "customer_fact_review_v1.py",
)

from approve_persona_v1 import (  # noqa: E402
    approve_persona,
)


def build_request():
    return {
        "business_id": "fixture_pet_store",
        "intake_id": "intake_0001",
        "customer_name": "小爪宠物店",
        "industry": "宠物服务",
        "materials": (
            "小爪宠物店提供宠物洗护和基础美容，"
            "主要服务附近养宠家庭。"
            "很多主人工作日没时间自己给宠物洗澡。"
            "我们洗之前会先看皮肤和毛发状态，"
            "再确认适合的洗护方式。"
        ),
    }


def fixture_extractor(_: dict):
    return {
        "facts": [
            {
                "topic": "primary_service",
                "value": [
                    "宠物洗护",
                    "基础美容",
                ],
                "evidence_quote": ("提供宠物洗护和基础美容"),
            },
            {
                "topic": "core_audience",
                "value": ["附近养宠家庭"],
                "evidence_quote": ("主要服务附近养宠家庭"),
            },
            {
                "topic": "customer_pain",
                "value": ["主人工作日没有时间" "自己给宠物洗澡"],
                "evidence_quote": ("工作日没时间自己给宠物洗澡"),
            },
            {
                "topic": "differentiator",
                "value": ["洗护前先确认皮肤" "和毛发状态"],
                "evidence_quote": ("洗之前会先看皮肤和毛发状态"),
            },
        ],
        "model": "fixture-model",
        "usage": {},
    }


def prepare_analysis(
    tmp_path: Path,
):
    return analysis.analyze_customer_onboarding(
        request=build_request(),
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at=("2026-09-17T" "00:00:00+00:00"),
    )


def approval_decisions(
    summary: dict,
):
    candidates = json.loads(
        Path(summary["artifacts"]["fact_candidates_v1"]).read_text(encoding="utf-8")
    )

    return [
        {
            "candidate_id": item["fact_candidate_id"],
            "decision": "approve",
            "note": ("测试人工确认"),
        }
        for item in candidates["fact_candidates"]
        if item["candidate_state"] == "requires_review"
    ]


def build_review_request(
    summary: dict,
):
    return {
        "business_id": (summary["business_id"]),
        "intake_id": (summary["intake_id"]),
        "reviewer": "李健",
        "note": ("Human reviewed initial " "Customer Truth candidates."),
        "decisions": (approval_decisions(summary)),
    }


def test_human_review_builds_business_persona_candidate(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    result = review.review_customer_facts(
        request=build_review_request(summary),
        pipeline_root=tmp_path,
        reviewed_at=("2026-09-17T" "01:00:00+00:00"),
    )

    assert result["status"] == ("completed_" "persona_review_required")

    assert result["authority"]["fact_review_completed"] is True

    assert result["authority"]["business_persona_created"] is True

    assert result["authority"]["persona_approved"] is False

    persona_path = Path(result["artifacts"]["business_persona_v1"])

    persona = json.loads(persona_path.read_text(encoding="utf-8"))

    assert persona["persona_scope"] == "business"

    assert persona["lifecycle"]["status"] == "review_required"

    assert persona["lifecycle"]["approved"] is False

    assert persona["validation"]["required_fact_approval_blockers"] == []


def test_ai_candidates_become_known_only_after_human_decision(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    result = review.review_customer_facts(
        request=build_review_request(summary),
        pipeline_root=tmp_path,
        reviewed_at=("2026-09-17T" "01:00:00+00:00"),
    )

    reviewed = json.loads(
        Path(result["artifacts"]["reviewed_candidates_v1"]).read_text(encoding="utf-8")
    )

    ai_candidates = [
        item
        for item in reviewed["fact_candidates"]
        if item.get("classification") == ("ai_extracted_" "initial_onboarding")
    ]

    assert ai_candidates

    for item in ai_candidates:
        assert item["candidate_state"] == "known_candidate"

        assert item["confirmation_basis"] == "human_review_approved"

        assert item["human_review"]["human_gate"] is True


def test_incomplete_review_fails_closed(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    request = build_review_request(summary)

    request["decisions"] = request["decisions"][:-1]

    try:
        review.review_customer_facts(
            request=request,
            pipeline_root=tmp_path,
        )
    except review.CustomerFactReviewError as exc:
        assert exc.code == "FACT_REVIEW_INCOMPLETE"
    else:
        raise AssertionError(("Incomplete Human Review " "must fail closed."))


def test_rejecting_all_customer_context_blocks_persona_creation(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    request = build_review_request(summary)

    candidates = json.loads(
        Path(summary["artifacts"]["fact_candidates_v1"]).read_text(encoding="utf-8")
    )

    for decision in request["decisions"]:
        candidate = next(
            item
            for item in candidates["fact_candidates"]
            if item["fact_candidate_id"] == decision["candidate_id"]
        )
        if candidate["target_field"] in {"core_audience", "customer_pains"}:
            decision["decision"] = "reject"

    result = review.review_customer_facts(
        request=request,
        pipeline_root=tmp_path,
        reviewed_at=("2026-09-17T" "01:00:00+00:00"),
    )

    assert result["status"] == ("completed_" "persona_blocked")

    assert result["business_persona_blockers"] == ["customer_use_context"]

    assert result["authority"]["business_persona_created"] is False

    persona_path = (
        tmp_path
        / "data"
        / "personas"
        / "fixture_pet_store"
        / "revision_0001"
        / "persona_v1.json"
    )

    assert not persona_path.exists()


def test_edit_decision_becomes_explicit_human_value(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    request = build_review_request(summary)

    candidates = json.loads(
        Path(summary["artifacts"]["fact_candidates_v1"]).read_text(encoding="utf-8")
    )

    audience = next(
        item
        for item in candidates["fact_candidates"]
        if item["target_field"] == "core_audience"
    )

    for decision in request["decisions"]:
        if decision["candidate_id"] == audience["fact_candidate_id"]:
            decision.update(
                {
                    "decision": "edit",
                    "edited_value": ["门店周边的" "养宠家庭"],
                    "note": ("人工修正表述"),
                }
            )

    result = review.review_customer_facts(
        request=request,
        pipeline_root=tmp_path,
        reviewed_at=("2026-09-17T" "01:00:00+00:00"),
    )

    persona = json.loads(
        Path(result["artifacts"]["business_persona_v1"]).read_text(encoding="utf-8")
    )

    assert persona["facts"]["core_audience"]["value"] == ["门店周边的养宠家庭"]


def test_review_retry_is_idempotent(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    request = build_review_request(summary)

    first = review.review_customer_facts(
        request=request,
        pipeline_root=tmp_path,
    )

    second = review.review_customer_facts(
        request=request,
        pipeline_root=tmp_path,
    )

    assert first["review_fingerprint"] == second["review_fingerprint"]

    assert first["reviewed_at"] == second["reviewed_at"]

    assert first["artifacts"] == second["artifacts"]


def test_legacy_fixed_field_block_can_be_rechecked_without_new_decisions(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)
    request = build_review_request(summary)
    intake_root = Path(summary["artifacts"]["customer_intake_v1"]).parent
    candidates_path = Path(summary["artifacts"]["fact_candidates_v1"])
    reviewed_at = "2026-09-17T01:00:00+00:00"
    fingerprint = review.canonical_sha256(
        {
            "business_id": request["business_id"],
            "intake_id": request["intake_id"],
            "reviewer": request["reviewer"],
            "note": request["note"],
            "candidate_sha256": review.sha256_file(candidates_path),
            "decisions": request["decisions"],
        }
    )
    (intake_root / "customer_fact_review_v1.json").write_text(
        json.dumps(
            {
                "schema_version": "customer-fact-review-v1.0",
                "operation_version": "customer_fact_review_v1.py@1.0",
                "business_id": request["business_id"],
                "intake_id": request["intake_id"],
                "status": "completed_persona_blocked",
                "review_fingerprint": fingerprint,
                "reviewer": request["reviewer"],
                "reviewed_at": reviewed_at,
                "note": request["note"],
                "decisions": request["decisions"],
                "business_persona_blockers": ["core_audience", "customer_pains"],
                "authority": {
                    "human_gate": True,
                    "review_decision_immutable": True,
                    "persona_approved": False,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    result = review.review_customer_facts(
        request=request,
        pipeline_root=tmp_path,
    )
    assert result["status"] == "completed_persona_review_required"
    assert result["review_fingerprint"] == fingerprint
    assert Path(result["artifacts"]["business_persona_v1"]).is_file()


def test_different_review_cannot_silently_replace_human_decision(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    first_request = build_review_request(summary)

    review.review_customer_facts(
        request=first_request,
        pipeline_root=tmp_path,
        reviewed_at=("2026-09-17T" "01:00:00+00:00"),
    )

    changed_request = build_review_request(summary)

    changed_request["decisions"][0]["note"] = "不同的人工决策说明"

    try:
        review.review_customer_facts(
            request=changed_request,
            pipeline_root=tmp_path,
        )
    except review.CustomerFactReviewError as exc:
        assert exc.code == ("FACT_REVIEW_" "ALREADY_FINALIZED")
    else:
        raise AssertionError(("Human Review must not " "be silently replaced."))


def test_persona_requires_second_explicit_human_approval(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    result = review.review_customer_facts(
        request=build_review_request(summary),
        pipeline_root=tmp_path,
        reviewed_at=("2026-09-17T" "01:00:00+00:00"),
    )

    persona_path = Path(result["artifacts"]["business_persona_v1"])

    before = json.loads(persona_path.read_text(encoding="utf-8"))

    assert before["lifecycle"]["status"] == "review_required"

    approved, receipt, receipt_path = approve_persona(
        persona_path,
        reviewer="李健",
        note=(
            "Human approved Business "
            "Persona after reviewing "
            "the complete fact authority."
        ),
        approved_at=("2026-09-17T" "02:00:00+00:00"),
    )

    assert approved["lifecycle"]["status"] == "approved"

    assert approved["lifecycle"]["approved"] is True

    assert receipt["human_gate"] is True

    assert receipt_path.is_file()


def test_gap_supplement_merges_reviewed_facts_without_changing_old_decisions(
    tmp_path: Path,
):
    initial_request = build_request()

    def initial_extractor(_: dict):
        return {
            "facts": [
                {
                    "topic": "primary_service",
                    "value": ["宠物洗护"],
                    "evidence_quote": "提供宠物洗护",
                },
            ],
            "model": "fixture-model",
            "usage": {},
        }

    initial = analysis.analyze_customer_onboarding(
        request=initial_request,
        pipeline_root=tmp_path,
        extractor=initial_extractor,
        created_at="2026-09-21T00:00:00+00:00",
    )
    initial_review_request = build_review_request(initial)
    initial_result = review.review_customer_facts(
        request=initial_review_request,
        pipeline_root=tmp_path,
        reviewed_at="2026-09-21T00:10:00+00:00",
    )
    assert initial_result["status"] == "completed_persona_blocked"
    assert initial_result["business_persona_blockers"] == [
        "customer_use_context",
        "production_bearing_facts",
    ]
    initial_reviewed_path = Path(
        initial_result["artifacts"]["reviewed_candidates_v1"]
    )
    initial_review_path = initial_reviewed_path.parent / "customer_fact_review_v1.json"
    old_reviewed_bytes = initial_reviewed_path.read_bytes()
    old_review_bytes = initial_review_path.read_bytes()

    supplement_request = {
        "intake_type": "gap_supplement",
        "business_id": "fixture_pet_store",
        "intake_id": "intake_0002",
        "customer_name": "小爪宠物店",
        "industry": "宠物服务",
        "gap_answers": [
            {
                "target_gap": "customer_use_context",
                "raw_answer": "主要顾客是附近养宠家庭。",
            }
        ],
        "reviewed_context": {
            "public_display_name": "小爪宠物店",
            "industry": "宠物服务",
            "primary_products_or_services": ["宠物洗护"],
        },
        "created_by": {"user_id": 7, "phone": "13800000000"},
        "source_lineage": {
            "previous_intake_ids": ["intake_0001"],
            "old_human_decisions_preserved": True,
        },
    }

    def supplement_extractor(_: dict):
        return {
            "facts": [
                {
                    "topic": "core_audience",
                    "value": ["附近养宠家庭"],
                    "evidence_quote": "附近养宠家庭",
                }
            ],
            "model": "fixture-model",
            "usage": {},
        }

    supplement = analysis.analyze_customer_onboarding(
        request=supplement_request,
        pipeline_root=tmp_path,
        extractor=supplement_extractor,
        created_at="2026-09-21T01:00:00+00:00",
    )
    partial_result = review.review_customer_facts(
        request={
            "business_id": supplement["business_id"],
            "intake_id": supplement["intake_id"],
            "reviewer": "李健",
            "note": "只确认本轮补充的信息。",
            "decisions": approval_decisions(supplement),
        },
        pipeline_root=tmp_path,
        reviewed_at="2026-09-21T01:10:00+00:00",
    )
    assert partial_result["status"] == "completed_persona_blocked"
    assert partial_result["business_persona_blockers"] == [
        "production_bearing_facts"
    ]
    assert initial_reviewed_path.read_bytes() == old_reviewed_bytes
    assert initial_review_path.read_bytes() == old_review_bytes

    production_supplement_request = {
        **supplement_request,
        "intake_id": "intake_0003",
        "gap_answers": [
            {
                "target_gap": "production_bearing_facts",
                "raw_answer": "洗护前会先查看宠物皮肤和毛发状态。",
            }
        ],
        "source_lineage": {
            "previous_intake_ids": ["intake_0001", "intake_0002"],
            "old_human_decisions_preserved": True,
        },
    }

    def production_supplement_extractor(_: dict):
        return {
            "facts": [
                {
                    "topic": "service_process",
                    "value": ["洗护前查看宠物皮肤和毛发状态"],
                    "evidence_quote": "洗护前会先查看宠物皮肤和毛发状态",
                }
            ],
            "model": "fixture-model",
            "usage": {},
        }

    production_supplement = analysis.analyze_customer_onboarding(
        request=production_supplement_request,
        pipeline_root=tmp_path,
        extractor=production_supplement_extractor,
        created_at="2026-09-21T02:00:00+00:00",
    )
    supplement_result = review.review_customer_facts(
        request={
            "business_id": production_supplement["business_id"],
            "intake_id": production_supplement["intake_id"],
            "reviewer": "李健",
            "note": "确认剩余缺口的新增信息。",
            "decisions": approval_decisions(production_supplement),
        },
        pipeline_root=tmp_path,
        reviewed_at="2026-09-21T02:10:00+00:00",
    )
    assert supplement_result["status"] == "completed_persona_review_required"
    persona = json.loads(
        Path(supplement_result["artifacts"]["business_persona_v1"]).read_text(
            encoding="utf-8"
        )
    )
    assert persona["facts"]["primary_products_or_services"]["value"] == [
        "宠物洗护"
    ]
    assert persona["facts"]["core_audience"]["value"] == [
        "附近养宠家庭"
    ]
    assert persona["facts"]["process_facts"]["value"] == [
        "洗护前查看宠物皮肤和毛发状态"
    ]
    assert initial_reviewed_path.read_bytes() == old_reviewed_bytes
    assert initial_review_path.read_bytes() == old_review_bytes
    source_refs = persona["facts"]["primary_products_or_services"]["source_refs"]
    assert any("intake_0001" in item for item in source_refs)
    audience_refs = persona["facts"]["core_audience"]["source_refs"]
    assert any("intake_0002" in item for item in audience_refs)
    process_refs = persona["facts"]["process_facts"]["source_refs"]
    assert any("intake_0003" in item for item in process_refs)
