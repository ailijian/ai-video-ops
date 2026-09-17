from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )


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
    "speaker_analysis_test",
    "speaker_onboarding_analysis_v1.py",
)

review = load_module(
    "speaker_review_test",
    "speaker_fact_review_v1.py",
)


from approve_persona_v1 import (  # noqa: E402
    approve_persona,
)
from build_persona_v1 import (  # noqa: E402
    build_persona,
)


def create_approved_business(
    root: Path,
):
    input_path = root / "fixture_business_input.json"

    input_path.write_text(
        json.dumps(
            {
                "persona_id": ("fixture_pet_store"),
                "revision": 1,
                "persona_scope": ("business"),
                "fixture_only": True,
                "source_type": ("test_fixture"),
                "source_file": (str(input_path)),
                "source_ref": ("fixture"),
                "facts": {
                    "public_display_name": {
                        "state": "known",
                        "value": ("小爪宠物店"),
                        "source_refs": ["fixture"],
                    },
                    "industry": {
                        "state": "known",
                        "value": ("宠物服务"),
                        "source_refs": ["fixture"],
                    },
                    "primary_products_or_services": {
                        "state": "known",
                        "value": ["宠物洗护"],
                        "source_refs": ["fixture"],
                    },
                    "core_audience": {
                        "state": "known",
                        "value": ["门店周边养宠家庭"],
                        "source_refs": ["fixture"],
                    },
                    "customer_pains": {
                        "state": "known",
                        "value": ["工作日缺少时间"],
                        "source_refs": ["fixture"],
                    },
                    "differentiators": {
                        "state": "known",
                        "value": ["洗护前检查状态"],
                        "source_refs": ["fixture"],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    path, _ = build_persona(
        input_path,
        root / "data/personas",
        created_at=("2026-09-17T" "00:00:00+00:00"),
    )

    approved, _, _ = approve_persona(
        path,
        reviewer="李健",
        note=("Approved Business " "Persona fixture."),
        approved_at=("2026-09-17T" "00:10:00+00:00"),
    )

    assert approved["lifecycle"]["approved"] is True

    return path


def speaker_request():
    return {
        "business_id": ("fixture_pet_store"),
        "speaker_name": "王琳",
        "public_role": "店主",
        "speaker_type": ("owner_founder"),
        "materials": (
            "王琳是小爪宠物店店主，"
            "日常由她亲自接待顾客，"
            "检查宠物皮肤和毛发状态，"
            "并根据现场情况确认洗护方案。"
            "她可以分享自己在门店接待、"
            "宠物洗护前判断和日常服务中的实际经验。"
        ),
        "forbidden_claims": [
            "不得声称自己是兽医",
            "不得进行医疗诊断",
        ],
    }


def fixture_extractor(
    _: dict,
):
    return {
        "facts": [
            {
                "topic": ("speaker_practice"),
                "value": [
                    "亲自接待顾客",
                    ("检查宠物皮肤" "和毛发状态"),
                    ("根据现场情况" "确认洗护方案"),
                ],
                "evidence_quote": ("日常由她亲自接待顾客"),
            },
            {
                "topic": ("speaker_allowed_topics"),
                "value": [
                    "门店接待",
                    "宠物洗护前判断",
                    "日常服务经验",
                ],
                "evidence_quote": ("她可以分享自己在门店接待"),
            },
            {
                "topic": ("speaker_scope"),
                "value": ["仅以本人实际参与的" "门店服务经验进行" "第一人称表达"],
                "evidence_quote": ("日常由她亲自接待顾客"),
            },
        ],
        "model": "fixture-model",
        "usage": {},
    }


def prepare_analysis(
    tmp_path: Path,
):
    create_approved_business(tmp_path)

    return analysis.analyze_speaker_onboarding(
        request=(speaker_request()),
        pipeline_root=(tmp_path),
        extractor=(fixture_extractor),
        created_at=("2026-09-17T" "01:00:00+00:00"),
    )


def review_request(
    summary: dict,
):
    candidates = json.loads(
        Path(summary["artifacts"]["speaker_fact_candidates_v1"]).read_text(
            encoding="utf-8"
        )
    )

    decisions = [
        {
            "candidate_id": (item["fact_candidate_id"]),
            "decision": ("approve"),
            "note": ("测试人工确认"),
        }
        for item in (candidates["fact_candidates"])
        if (item["candidate_state"] == "requires_review")
    ]

    return {
        "business_id": (summary["business_id"]),
        "speaker_id": (summary["speaker_id"]),
        "intake_id": (summary["intake_id"]),
        "reviewer": "李健",
        "note": ("Speaker Fact Human " "Review completed."),
        "decisions": decisions,
    }


def test_analysis_creates_speaker_candidates_without_copying_business_facts(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    assert summary["status"] == ("awaiting_" "speaker_fact_review")

    assert summary["authority"]["business_persona_approved"] is True

    assert summary["authority"]["media_rights_established"] is False

    candidates = json.loads(
        Path(summary["artifacts"]["speaker_fact_candidates_v1"]).read_text(
            encoding="utf-8"
        )
    )

    fields = {item["target_field"] for item in (candidates["fact_candidates"])}

    assert "public_display_name" in fields

    assert "public_role" in fields

    assert "speaker_role_facts" in fields

    assert "first_person_allowed_topics" in fields

    assert "first_person_forbidden_claims" in fields

    for business_only in (
        "industry",
        "core_audience",
        "customer_pains",
        "differentiators",
    ):
        assert business_only not in fields


def test_ai_speaker_facts_remain_requires_review(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    candidates = json.loads(
        Path(summary["artifacts"]["speaker_fact_candidates_v1"]).read_text(
            encoding="utf-8"
        )
    )

    ai_items = [
        item
        for item in (candidates["fact_candidates"])
        if item.get("classification") == ("ai_extracted_" "speaker_onboarding")
    ]

    assert ai_items

    assert all(item["candidate_state"] == "requires_review" for item in ai_items)


def test_human_review_builds_review_required_speaker_persona(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    result = review.review_speaker_facts(
        request=(review_request(summary)),
        pipeline_root=(tmp_path),
        reviewed_at=("2026-09-17T" "02:00:00+00:00"),
    )

    assert result["status"] == ("completed_" "persona_review_required")

    persona = json.loads(
        Path(result["artifacts"]["speaker_persona_v1"]).read_text(encoding="utf-8")
    )

    assert persona["persona_scope"] == "speaker"

    assert persona["lifecycle"]["status"] == "review_required"

    assert persona["business_persona_ref"]["persona_id"] == "fixture_pet_store"

    assert persona["validation"]["required_fact_approval_blockers"] == []


def test_rejecting_required_speaker_fact_blocks_persona(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    request = review_request(summary)

    candidates = json.loads(
        Path(summary["artifacts"]["speaker_fact_candidates_v1"]).read_text(
            encoding="utf-8"
        )
    )

    role_fact = next(
        item
        for item in (candidates["fact_candidates"])
        if item["target_field"] == "speaker_role_facts"
    )

    for decision in request["decisions"]:
        if decision["candidate_id"] == role_fact["fact_candidate_id"]:
            decision["decision"] = "reject"

    result = review.review_speaker_facts(
        request=request,
        pipeline_root=(tmp_path),
        reviewed_at=("2026-09-17T" "02:00:00+00:00"),
    )

    assert result["status"] == ("completed_" "persona_blocked")

    assert "speaker_role_facts" in result["speaker_persona_blockers"]


def test_speaker_persona_requires_second_explicit_approval(
    tmp_path: Path,
):
    summary = prepare_analysis(tmp_path)

    result = review.review_speaker_facts(
        request=(review_request(summary)),
        pipeline_root=(tmp_path),
        reviewed_at=("2026-09-17T" "02:00:00+00:00"),
    )

    persona_path = Path(result["artifacts"]["speaker_persona_v1"])

    before = json.loads(persona_path.read_text(encoding="utf-8"))

    assert before["lifecycle"]["approved"] is False

    (
        approved,
        receipt,
        _,
    ) = approve_persona(
        persona_path,
        reviewer="李健",
        note=("Human approved " "Speaker Persona."),
        approved_at=("2026-09-17T" "03:00:00+00:00"),
    )

    assert approved["lifecycle"]["approved"] is True

    assert receipt["human_gate"] is True


def test_speaker_analysis_requires_approved_business_persona(
    tmp_path: Path,
):
    try:
        (
            analysis.analyze_speaker_onboarding(
                request=(speaker_request()),
                pipeline_root=(tmp_path),
                extractor=(fixture_extractor),
            )
        )

    except analysis.SpeakerOnboardingError as exc:
        assert exc.code == ("APPROVED_BUSINESS_" "PERSONA_REQUIRED")

    else:
        raise AssertionError(
            ("Speaker onboarding " "must require an Approved " "Business Persona.")
        )


def test_speaker_analysis_retry_is_idempotent(
    tmp_path: Path,
):
    create_approved_business(tmp_path)

    calls = {
        "count": 0,
    }

    def counting_extractor(
        payload: dict,
    ):
        calls["count"] += 1
        return fixture_extractor(payload)

    first = analysis.analyze_speaker_onboarding(
        request=(speaker_request()),
        pipeline_root=(tmp_path),
        extractor=(counting_extractor),
    )

    second = analysis.analyze_speaker_onboarding(
        request=(speaker_request()),
        pipeline_root=(tmp_path),
        extractor=(counting_extractor),
    )

    assert calls["count"] == 1

    assert first["speaker_id"] == second["speaker_id"]

    assert first["created_at"] == second["created_at"]
