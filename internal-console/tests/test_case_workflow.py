from __future__ import annotations

import json

from app.canonical_gateway import case_analysis_capability, get_case_detail, list_cases


def test_case_capability_maps_one_canonical_operation():
    capability = case_analysis_capability()
    assert capability["available"] is True
    assert capability["operation"] == "case_analysis_v1"


def test_case_library_uses_business_language(settings):
    cases = list_cases(settings)
    assert cases
    assert all(case["profile"] not in {"mix", "news", "MIX", "NEWS"} for case in cases)
    assert all(case["industry"] != "local_service" for case in cases)
    for case in cases:
        summary = case["summary"]
        if summary:
            assert any("\u4e00" <= character <= "\u9fff" for character in summary)


def test_case_detail_is_privacy_safe_and_keeps_media_rights_separate(settings):
    detail = get_case_detail(settings, "7999999999999999901")
    serialized = json.dumps(detail, ensure_ascii=False).lower()
    assert detail["review"]["approved"] is True
    assert detail["media_rights"]["production_authorized"] is False
    assert "sha256" not in serialized
    assert "fact_id" not in serialized
    assert "frame_" not in serialized
    assert "raw json" not in serialized


def test_surface_copy_does_not_expose_internal_authority_language(settings):
    static_root = settings.console_root / "static"
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in static_root.rglob("*")
        if path.suffix in {".js", ".html", ".css"}
    )
    for forbidden in (
        "Authority Projection Only",
        "canonical Current Status Read Model",
        "Authority 已解析",
        "Human Gate 保留",
        "local_service",
    ):
        assert forbidden not in text
