from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "customer_onboarding_analysis_v1.py"
)

SCRIPTS_DIR = SCRIPT.parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location(
    "customer_onboarding_analysis_v1",
    SCRIPT,
)

assert SPEC and SPEC.loader

module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture_extractor(_: dict):
    return {
        "facts": [
            {
                "topic": "primary_service",
                "value": ["宠物洗护", "基础美容"],
                "evidence_quote": "提供宠物洗护和基础美容",
            },
            {
                "topic": "core_audience",
                "value": ["附近养宠家庭"],
                "evidence_quote": "主要服务附近养宠家庭",
            },
            {
                "topic": "customer_pain",
                "value": ["主人工作日没有时间自己洗护"],
                "evidence_quote": "工作日没时间自己给宠物洗澡",
            },
            {
                "topic": "differentiator",
                "value": ["洗护前会先确认皮肤和毛发状态"],
                "evidence_quote": "洗之前会先看皮肤和毛发状态",
            },
        ],
        "model": "fixture-model",
        "usage": {},
    }


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


def test_freeform_materials_create_review_required_candidates(
    tmp_path: Path,
):
    summary = module.analyze_customer_onboarding(
        request=build_request(),
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    assert summary["status"] == "awaiting_fact_review"
    assert summary["authority"]["persona_created"] is False
    assert summary["authority"]["persona_approved"] is False
    assert summary["authority"]["human_review_required"] is True

    candidates_path = Path(summary["artifacts"]["fact_candidates_v1"])

    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))

    by_field = {item["target_field"]: item for item in candidates["fact_candidates"]}

    # Operator explicit identity survives as deterministic candidates.
    assert by_field["public_display_name"]["candidate_state"] == "known_candidate"

    assert by_field["industry"]["candidate_state"] == "known_candidate"

    # AI extraction can never promote directly to known Customer Truth.
    for field in (
        "primary_products_or_services",
        "core_audience",
        "customer_pains",
        "differentiators",
    ):
        assert by_field[field]["candidate_state"] == "requires_review"


def test_raw_input_remains_immutable_and_separate(
    tmp_path: Path,
):
    request = build_request()

    summary = module.analyze_customer_onboarding(
        request=request,
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    intake = json.loads(
        Path(summary["artifacts"]["customer_intake_v1"]).read_text(encoding="utf-8")
    )

    raw_material = next(
        item
        for item in intake["raw_answers"]
        if item["topic"] == "freeform_customer_materials"
    )

    assert raw_material["answer_text"] == request["materials"]

    assert intake["raw_input_contract"]["ai_extracted_candidates_embedded"] is False

    assert intake["authority"]["raw_input_is_not_persona_authority"] is True


def test_privacy_projection_blocks_raw_phone_egress(
    tmp_path: Path,
):
    request = build_request()

    request["materials"] += " 顾客姓名：张三，联系电话：13812345678。"

    summary = module.analyze_customer_onboarding(
        request=request,
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    projection = json.loads(
        Path(summary["artifacts"]["privacy_projection_v1"]).read_text(encoding="utf-8")
    )

    safe = projection["projection"]["materials_safe_semantic"]

    assert "13812345678" not in safe

    audit = json.loads(
        Path(summary["artifacts"]["egress_audit_v1"]).read_text(encoding="utf-8")
    )

    assert audit["raw_customer_input_sent_directly"] is False


def test_case_library_is_not_consumed(
    tmp_path: Path,
):
    summary = module.analyze_customer_onboarding(
        request=build_request(),
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    assert summary["authority"]["case_sources_consumed"] is False


def test_retry_with_same_input_is_recoverable(
    tmp_path: Path,
):
    request = build_request()

    first = module.analyze_customer_onboarding(
        request=request,
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    second = module.analyze_customer_onboarding(
        request=request,
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    assert first["candidate_summary"] == second["candidate_summary"]


def test_same_intake_cannot_silently_change_raw_materials(
    tmp_path: Path,
):
    request = build_request()

    module.analyze_customer_onboarding(
        request=request,
        pipeline_root=tmp_path,
        extractor=fixture_extractor,
        created_at="2026-09-17T00:00:00+00:00",
    )

    changed = build_request()
    changed["materials"] += " 新增一段不同信息。"

    try:
        module.analyze_customer_onboarding(
            request=changed,
            pipeline_root=tmp_path,
            extractor=fixture_extractor,
            created_at="2026-09-17T00:00:00+00:00",
        )
    except module.CustomerOnboardingError as exc:
        assert exc.code == "ONBOARDING_ARTIFACT_CONFLICT"
    else:
        raise AssertionError("Changing immutable intake input must fail closed.")
