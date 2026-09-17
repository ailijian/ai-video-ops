from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )


from approve_persona_v1 import (  # noqa: E402
    approve_persona,
)
from build_persona_v1 import (  # noqa: E402
    build_persona,
)
from content_creation_entry_v1 import (  # noqa: E402
    ContentCreationEntryError,
    build_content_creation_entry,
)


def write_json(
    path: Path,
    value: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def known(
    value,
) -> dict:
    return {
        "state": "known",
        "value": value,
        "source_refs": ["fixture"],
    }


def create_registry(
    root: Path,
) -> None:
    contract = {
        "fixture": True,
    }

    profiles = {}

    for profile_id, status in (
        (
            "mix",
            "production_ready",
        ),
        (
            "news",
            ("research_coverage_" "insufficient"),
        ),
    ):
        profiles[profile_id] = {
            "profile_id": (profile_id),
            "status": status,
            "script_contract": (dict(contract)),
            "storyboard_contract": (dict(contract)),
            "export_contract": (dict(contract)),
            "case_compatibility_policy": (dict(contract)),
            "pattern_compatibility_policy": (dict(contract)),
            "validation_policy": (dict(contract)),
        }

    write_json(
        root
        / "data"
        / "production_profiles"
        / ("production_profile_" "registry_v1.json"),
        {
            "schema_version": ("production-profile-" "registry-v1.0"),
            "status": ("approved_frozen"),
            "target_profiles": [
                "mix",
                "news",
            ],
            "source_profile_classifications": [
                "news",
                "mix",
                "hybrid",
                "uncertain",
            ],
            "profiles": profiles,
        },
    )


def create_approved_personas(
    root: Path,
) -> tuple[
    Path,
    Path,
]:
    persona_root = root / "data" / "personas"

    business_input = root / "business_input.json"

    write_json(
        business_input,
        {
            "persona_id": ("fixture_pet_store"),
            "revision": 1,
            "persona_scope": ("business"),
            "fixture_only": True,
            "source_type": ("test_fixture"),
            "source_ref": ("fixture"),
            "facts": {
                "public_display_name": (known("小爪宠物店")),
                "industry": (known("宠物服务")),
                "primary_products_or_services": (
                    known(
                        [
                            "宠物洗护",
                            "基础美容",
                        ]
                    )
                ),
                "core_audience": (known(["门店周边" "养宠家庭"])),
                "customer_use_cases": (known(["需要日常" "宠物洗护"])),
                "customer_pains": (known(["工作日没有" "时间自己护理"])),
                "differentiators": (known(["洗护前检查" "皮肤和毛发状态"])),
                "process_facts": (
                    known(
                        [
                            ("洗护前检查" "皮肤和毛发"),
                            ("根据现场状态" "确认洗护方案"),
                        ]
                    )
                ),
            },
        },
    )

    business_path, _ = build_persona(
        business_input,
        persona_root,
        created_at=("2026-09-17T" "00:00:00+00:00"),
    )

    approve_persona(
        business_path,
        reviewer="李健",
        note=("Fixture Business " "Persona approved."),
        approved_at=("2026-09-17T" "00:10:00+00:00"),
    )

    speaker_input = root / "speaker_input.json"

    write_json(
        speaker_input,
        {
            "persona_id": ("fixture_pet_store_owner"),
            "revision": 1,
            "persona_scope": ("speaker"),
            "speaker_type": ("owner_founder"),
            "business_persona_ref": {"persona_id": ("fixture_pet_store")},
            "fixture_only": True,
            "source_type": ("test_fixture"),
            "source_ref": ("fixture"),
            "facts": {
                "public_display_name": (known("王琳")),
                "public_role": (known("店主")),
                "speaker_role_facts": (
                    known(
                        [
                            "亲自接待顾客",
                            ("检查宠物皮肤" "和毛发状态"),
                            ("根据现场情况" "确认洗护方案"),
                        ]
                    )
                ),
                "first_person_allowed_topics": (
                    known(
                        [
                            "门店接待",
                            ("宠物洗护" "前判断"),
                            "日常服务经验",
                        ]
                    )
                ),
                "first_person_forbidden_claims": (
                    known(
                        [
                            ("不得声称" "自己是兽医"),
                            ("不得进行" "医疗诊断"),
                        ]
                    )
                ),
                "role_scope_constraints": (known(["只讲本人" "实际参与的" "门店服务"])),
            },
        },
    )

    speaker_path, _ = build_persona(
        speaker_input,
        persona_root,
        created_at=("2026-09-17T" "00:20:00+00:00"),
        business_persona_path=(business_path),
    )

    approve_persona(
        speaker_path,
        reviewer="李健",
        note=("Fixture Speaker " "Persona approved."),
        approved_at=("2026-09-17T" "00:30:00+00:00"),
    )

    return (
        business_path,
        speaker_path,
    )


def prepare(
    root: Path,
) -> None:
    create_registry(root)

    create_approved_personas(root)


def test_new_customer_mix_capacity_preview_is_read_only(
    tmp_path: Path,
):
    prepare(tmp_path)

    entry = build_content_creation_entry(
        pipeline_root=tmp_path,
        business_id=("fixture_pet_store"),
        speaker_id=("fixture_pet_store_owner"),
        profile="mix",
        requested_quantity=10,
        created_at=("2026-09-17T" "01:00:00+00:00"),
    )

    assert entry["profiles"]["mix"]["available"] is True

    assert entry["capacity"]["source_mode"] == ("initial_persona_capacity")

    assert entry["capacity"]["ledger_entry_count"] == 0

    assert entry["capacity"]["high_quality_novel_capacity"] == 3

    assert entry["recommendation"]["status"] == "capacity_limited"

    assert entry["recommendation"]["recommended_quantity"] == 3

    assert entry["capacity"]["padding_allowed"] is False

    assert entry["authority"]["script_generation_performed"] is False

    assert entry["authority"]["generation_batch_created"] is False

    assert entry["authority"]["content_ledger_written"] is False

    assert entry["model_calls"] == {
        "remote": 0,
        "local": 0,
    }


def test_quantity_within_capacity_is_ready(
    tmp_path: Path,
):
    prepare(tmp_path)

    entry = build_content_creation_entry(
        pipeline_root=tmp_path,
        business_id=("fixture_pet_store"),
        speaker_id=("fixture_pet_store_owner"),
        profile="mix",
        requested_quantity=2,
    )

    assert entry["recommendation"]["status"] == "ready"

    assert entry["recommendation"]["recommended_quantity"] == 2

    assert entry["recommendation"]["can_continue"] is True

    assert entry["next_action"] == "CONFIRM_GENERATION"


def test_news_is_visible_but_not_production_ready(
    tmp_path: Path,
):
    prepare(tmp_path)

    entry = build_content_creation_entry(
        pipeline_root=tmp_path,
        business_id=("fixture_pet_store"),
        speaker_id=("fixture_pet_store_owner"),
        profile="news",
        requested_quantity=2,
    )

    assert entry["profiles"]["news"]["available"] is False

    assert entry["profiles"]["news"]["status"] == ("research_coverage_" "insufficient")

    assert entry["recommendation"]["status"] == "profile_unavailable"

    assert entry["recommendation"]["recommended_quantity"] == 0

    assert entry["recommendation"]["can_continue"] is False

    assert entry["next_action"] == "CHOOSE_AVAILABLE_PROFILE"


def test_existing_generation_history_without_ledger_fails_closed(
    tmp_path: Path,
):
    prepare(tmp_path)

    write_json(
        tmp_path
        / "data"
        / "generation_requests"
        / "old_request"
        / "generation_request_v1.json",
        {
            "request_id": ("old_request"),
            "persona_id": ("fixture_pet_store"),
            "target_profile": ("mix"),
        },
    )

    with pytest.raises(ContentCreationEntryError) as exc:
        build_content_creation_entry(
            pipeline_root=tmp_path,
            business_id=("fixture_pet_store"),
            speaker_id=("fixture_pet_store_owner"),
            profile="mix",
            requested_quantity=3,
        )

    assert exc.value.code == ("CONTENT_HISTORY_" "WITHOUT_LEDGER")


def test_invalid_quantity_fails_closed(
    tmp_path: Path,
):
    prepare(tmp_path)

    with pytest.raises(ContentCreationEntryError) as exc:
        build_content_creation_entry(
            pipeline_root=tmp_path,
            business_id=("fixture_pet_store"),
            speaker_id=("fixture_pet_store_owner"),
            profile="mix",
            requested_quantity=0,
        )

    assert exc.value.code == "INVALID_REQUESTED_QUANTITY"
