from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from approve_persona_v1 import approve_persona  # noqa: E402
from build_persona_v1 import build_persona  # noqa: E402
from match_generation_sources_v1 import build_source_plan  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def known(value) -> dict:
    return {"state": "known", "value": value, "source_refs": ["fixture"]}


def business_input(persona_id: str, *, process: bool = True) -> dict:
    facts = {
        "public_display_name": known(f"{persona_id} customer"),
        "industry": known("service"),
        "primary_products_or_services": known(["service"]),
        "core_audience": known(["customer"]),
        "customer_use_cases": known(["use context"]),
        "customer_pains": known(["customer pain"]),
        "differentiators": known(["trusted delivery"]),
        "product_or_service_facts": known(["real service fact"]),
        "founder_or_operator_story": known("operator participates in delivery"),
    }
    if process:
        facts["process_facts"] = known(["inspect", "plan", "deliver"])
        facts["service_process"] = known(["inspect", "plan", "deliver"])
    return {
        "persona_id": persona_id,
        "revision": 1,
        "persona_scope": "business",
        "fixture_only": True,
        "source_type": "test_fixture",
        "source_ref": "fixture",
        "facts": facts,
    }


def approved_business(root: Path, persona_id: str, *, process: bool = True) -> Path:
    source = root / f"{persona_id}_input.json"
    write_json(source, business_input(persona_id, process=process))
    path, _ = build_persona(
        source,
        root / "personas",
        created_at="2026-09-22T00:00:00+00:00",
    )
    approve_persona(
        path,
        reviewer="Fixture Reviewer",
        note="Fixture approval.",
        approved_at="2026-09-22T00:01:00+00:00",
    )
    return path


def approved_speaker(root: Path, business_path: Path, speaker_id: str) -> Path:
    business = json.loads(business_path.read_text(encoding="utf-8"))
    source = root / f"{speaker_id}_input.json"
    write_json(
        source,
        {
            "persona_id": speaker_id,
            "revision": 1,
            "persona_scope": "speaker",
            "speaker_type": "owner_founder",
            "business_persona_ref": {"persona_id": business["persona_id"]},
            "fixture_only": True,
            "source_type": "test_fixture",
            "source_ref": "fixture",
            "facts": {
                "public_display_name": known(speaker_id),
                "public_role": known("operator"),
                "speaker_role_facts": known(["personally delivers the service"]),
                "first_person_allowed_topics": known(["real delivery experience"]),
            },
        },
    )
    path, _ = build_persona(
        source,
        root / "personas",
        created_at="2026-09-22T00:02:00+00:00",
        business_persona_path=business_path,
    )
    approve_persona(
        path,
        reviewer="Fixture Reviewer",
        note="Fixture speaker approval.",
        approved_at="2026-09-22T00:03:00+00:00",
    )
    return path


def matching_sources(root: Path) -> tuple[Path, Path, Path]:
    pattern_path = root / "pattern.json"
    case_path = root / "case.json"
    fingerprint_path = root / "fingerprint.json"
    write_json(
        pattern_path,
        {
            "pattern_id": "pcv1_narration_led_process_projection",
            "status": "approved",
            "scope": {"supported_case_ids": ["case_x"]},
            "effectiveness": {"status": "unvalidated", "performance_data_used": False},
        },
    )
    write_json(
        case_path,
        {
            "case_id": "case_x",
            "lifecycle": {"status": "approved", "approved": True},
            "validation": {"passed": True},
            "quality": {"human_review_completed": True},
        },
    )
    write_json(
        fingerprint_path,
        {
            "case_id": "case_x",
            "source_case": {
                "status": "approved",
                "approved": True,
                "sha256": sha256_file(case_path),
            },
            "identity": {"industry": "service"},
            "narration_features": {"speech_to_video_ratio": 0.8},
            "visual_shot_features": {
                "shot_count": 5,
                "primary_role_counts": {
                    "action": 3,
                    "context": 1,
                    "product": 1,
                    "persona": 0,
                },
            },
            "structure_features": {"audio_role": "narration semantic spine"},
            "pattern_mining_contract": {"this_artifact_is_not_a_pattern": True},
        },
    )
    return pattern_path, case_path, fingerprint_path


def context(persona_path: Path, speaker_path: Path | None = None) -> dict:
    persona = json.loads(persona_path.read_text(encoding="utf-8"))
    result = {
        "target_profile": "mix",
        "reuse_intent": "novel_content",
        "content_intent": "mixed",
        "quantity": 2,
        "platform": "douyin",
        "persona_id": persona["persona_id"],
        "persona_revision": persona["revision"],
    }
    if speaker_path is not None:
        speaker = json.loads(speaker_path.read_text(encoding="utf-8"))
        result["speaker_persona"] = speaker["persona_id"]
        result["speaker_persona_revision"] = speaker["revision"]
    return result


def formal_request(root: Path, persona_path: Path, speaker_path: Path | None = None) -> Path:
    request = context(persona_path, speaker_path)
    request.update(
        {
            "schema_version": "generation-request-v1.0",
            "request_id": "fixture_request",
            "profile": "mix",
        }
    )
    path = root / "request.json"
    write_json(path, request)
    return path


def match(
    persona_path: Path,
    pattern_path: Path,
    case_path: Path,
    fingerprint_path: Path,
    *,
    request_path: Path | None = None,
    request_context: dict | None = None,
    speaker_path: Path | None = None,
) -> dict:
    return build_source_plan(
        persona_path=persona_path,
        request_path=request_path,
        request_context=request_context,
        pattern_paths=[pattern_path],
        case_paths=[case_path],
        fingerprint_paths=[fingerprint_path],
        speaker_persona_path=speaker_path,
    )


def test_preview_supported_if_and_only_if_formal_matcher_supported(tmp_path: Path) -> None:
    persona = approved_business(tmp_path, "customer_a", process=True)
    pattern, case, fingerprint = matching_sources(tmp_path)
    preview = match(
        persona,
        pattern,
        case,
        fingerprint,
        request_context=context(persona),
    )
    formal = match(
        persona,
        pattern,
        case,
        fingerprint,
        request_path=formal_request(tmp_path, persona),
    )
    assert preview["feasibility"]["status"] == "supported"
    assert formal["feasibility"]["status"] == "supported"
    assert preview["selected_patterns"] == formal["selected_patterns"]
    assert preview["eligible_case_pool"] == formal["eligible_case_pool"]


def test_preview_unsupported_if_and_only_if_formal_matcher_unsupported(tmp_path: Path) -> None:
    persona = approved_business(tmp_path, "customer_a", process=False)
    pattern, case, fingerprint = matching_sources(tmp_path)
    preview = match(
        persona,
        pattern,
        case,
        fingerprint,
        request_context=context(persona),
    )
    formal = match(
        persona,
        pattern,
        case,
        fingerprint,
        request_path=formal_request(tmp_path, persona),
    )
    assert preview["feasibility"]["status"] == "unsupported"
    assert formal["feasibility"]["status"] == "unsupported"
    assert preview["feasibility"]["blocker_type"] == "PERSONA_LACKS_PATTERN_CAPABILITY"
    assert preview["selected_patterns"] == formal["selected_patterns"] == []
    assert preview["eligible_case_pool"] == formal["eligible_case_pool"] == []


def test_process_pattern_remains_ineligible_without_process_truth(tmp_path: Path) -> None:
    persona = approved_business(tmp_path, "customer_a", process=False)
    pattern, case, fingerprint = matching_sources(tmp_path)
    result = match(
        persona,
        pattern,
        case,
        fingerprint,
        request_context=context(persona),
    )
    assert "persona_lacks_known_process_material" in {
        item.get("reason") for item in result["excluded_sources"]
    }
    assert result["feasibility"]["optional_customer_truth_route"] == {
        "capability": "process_material",
        "label": "补充真实服务流程",
        "is_optional": True,
        "changes_persona_readiness": False,
    }


def test_case_reuse_is_global_across_customers(tmp_path: Path) -> None:
    pattern, case, fingerprint = matching_sources(tmp_path)
    customer_a = approved_business(tmp_path, "customer_a")
    customer_b = approved_business(tmp_path, "customer_b")
    a = match(customer_a, pattern, case, fingerprint, request_context=context(customer_a))
    b = match(customer_b, pattern, case, fingerprint, request_context=context(customer_b))
    assert [item["case_id"] for item in a["eligible_case_pool"]] == ["case_x"]
    assert [item["case_id"] for item in b["eligible_case_pool"]] == ["case_x"]


def test_pattern_reuse_is_global_across_customers(tmp_path: Path) -> None:
    pattern, case, fingerprint = matching_sources(tmp_path)
    customer_a = approved_business(tmp_path, "customer_a")
    customer_b = approved_business(tmp_path, "customer_b")
    for customer in (customer_a, customer_b):
        result = match(customer, pattern, case, fingerprint, request_context=context(customer))
        assert [item["pattern_id"] for item in result["selected_patterns"]] == [
            "pcv1_narration_led_process_projection"
        ]


def test_case_usage_is_not_content_novelty(tmp_path: Path) -> None:
    pattern, case, fingerprint = matching_sources(tmp_path)
    customer_a = approved_business(tmp_path, "customer_a")
    customer_b = approved_business(tmp_path, "customer_b")
    usage_history = tmp_path / "data" / "content_ledgers" / "customer_a" / "content_ledger_v1.json"
    write_json(
        usage_history,
        {
            "business_id": "customer_a",
            "entries": [{"case_id": "case_x", "semantic_signature": "already discussed"}],
        },
    )
    result = match(customer_b, pattern, case, fingerprint, request_context=context(customer_b))
    assert [item["case_id"] for item in result["eligible_case_pool"]] == ["case_x"]
    assert "content_ledgers" not in json.dumps(result, ensure_ascii=False)


def test_content_novelty_is_business_scoped(tmp_path: Path) -> None:
    # Source matching has no Content Ledger input. Novelty remains an
    # independent, business-wide contract and cannot become Case consumption.
    pattern, case, fingerprint = matching_sources(tmp_path)
    customer_a = approved_business(tmp_path, "customer_a")
    customer_b = approved_business(tmp_path, "customer_b")
    write_json(
        tmp_path / "data" / "content_ledgers" / "customer_a" / "content_ledger_v1.json",
        {"business_id": "customer_a", "entries": [{"profile": "mix", "concept": "x"}]},
    )
    a = match(customer_a, pattern, case, fingerprint, request_context=context(customer_a))
    b = match(customer_b, pattern, case, fingerprint, request_context=context(customer_b))
    assert a["request"]["reuse_intent"] == b["request"]["reuse_intent"] == "novel_content"
    assert a["eligible_case_pool"] and b["eligible_case_pool"]


def test_same_business_different_speakers_do_not_consume_case(tmp_path: Path) -> None:
    pattern, case, fingerprint = matching_sources(tmp_path)
    business = approved_business(tmp_path, "customer_a")
    speaker_a = approved_speaker(tmp_path, business, "speaker_a")
    speaker_b = approved_speaker(tmp_path, business, "speaker_b")
    for speaker in (speaker_a, speaker_b):
        result = match(
            business,
            pattern,
            case,
            fingerprint,
            request_context=context(business, speaker),
            speaker_path=speaker,
        )
        assert [item["case_id"] for item in result["eligible_case_pool"]] == ["case_x"]
