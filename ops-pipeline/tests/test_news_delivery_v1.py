from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import news_delivery_v1 as subject


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


def persona(
    *,
    persona_id: str,
    scope: str,
    revision: int,
    facts: dict,
    business_ref: dict | None = None,
) -> dict:
    value = {
        "persona_id": persona_id,
        "persona_scope": scope,
        "revision": revision,
        "facts": facts,
        "lifecycle": {
            "status": "approved",
            "approved": True,
        },
    }
    if business_ref is not None:
        value[
            "business_persona_ref"
        ] = business_ref
    return value


def known(value):
    return {
        "state": "known",
        "value": value,
        "source_refs": [],
    }


def build_fixture(
    tmp_path: Path,
) -> dict:
    pipeline = (
        tmp_path
        / "ops-pipeline"
    )
    business_id = (
        "business_fixture"
    )
    speaker_id = (
        "speaker_fixture"
    )
    source_content_id = (
        "mix_fixture-C001"
    )

    business_path = (
        pipeline
        / "data"
        / "personas"
        / business_id
        / "revision_0001"
        / "persona_v1.json"
    )
    business = persona(
        persona_id=business_id,
        scope="business",
        revision=1,
        facts={
            "public_display_name": known(
                "测试食堂"
            ),
        },
    )
    write_json(
        business_path,
        business,
    )

    speaker_path = (
        pipeline
        / "data"
        / "personas"
        / speaker_id
        / "revision_0001"
        / "persona_v1.json"
    )
    speaker = persona(
        persona_id=speaker_id,
        scope="speaker",
        revision=1,
        facts={
            "public_display_name": known(
                "张三"
            ),
        },
        business_ref={
            "persona_id": business_id,
            "revision": 1,
            "sha256": subject.sha256_file(
                business_path
            ),
        },
    )
    write_json(
        speaker_path,
        speaker,
    )

    atoms = [
        {
            "fact_atom_id": (
                "pricing_facts::1"
            ),
            "field": "pricing_facts",
            "original_known_fact": (
                "素菜加工费通常 8-10 元"
            ),
            "normalized_meaning": (
                "素菜加工费通常810元"
            ),
        },
        {
            "fact_atom_id": (
                "pricing_facts::2"
            ),
            "field": "pricing_facts",
            "original_known_fact": (
                "清蒸约 15 元"
            ),
            "normalized_meaning": (
                "清蒸约15元"
            ),
        },
        {
            "fact_atom_id": (
                "pricing_facts::3"
            ),
            "field": "pricing_facts",
            "original_known_fact": (
                "红烧约 18 元左右"
            ),
            "normalized_meaning": (
                "红烧约18元左右"
            ),
        },
        {
            "fact_atom_id": (
                "included_service_facts::1"
            ),
            "field": (
                "included_service_facts"
            ),
            "original_known_fact": (
                "免费提供油盐酱料"
            ),
            "normalized_meaning": (
                "免费提供油盐酱料"
            ),
        },
        {
            "fact_atom_id": (
                "included_service_facts::2"
            ),
            "field": (
                "included_service_facts"
            ),
            "original_known_fact": (
                "免费提供米饭"
            ),
            "normalized_meaning": (
                "免费提供米饭"
            ),
        },
        {
            "fact_atom_id": (
                "differentiators::1"
            ),
            "field": "differentiators",
            "original_known_fact": (
                "加工价格公开清晰"
            ),
            "normalized_meaning": (
                "加工价格公开清晰"
            ),
        },
        {
            "fact_atom_id": (
                "product_or_service_facts::1"
            ),
            "field": (
                "product_or_service_facts"
            ),
            "original_known_fact": (
                "素菜加工费多在 8-10 元"
            ),
            "normalized_meaning": (
                "素菜加工费多在810元"
            ),
        },
    ]

    entry = {
        "content_id": (
            source_content_id
        ),
        "status": "exported",
        "title": "加工费怎么算？",
        "central_claim": (
            "代炒菜加工费按菜品类型区分，"
            "素菜通常8-10元，"
            "清蒸约15元，"
            "红烧约18元左右。"
        ),
        "semantic_signature": {
            "primary_fact_bundle": [
                "pricing_facts",
            ]
        },
        "primary_fact_atom_refs": [],
        "communicated_information_units": [
            {
                "information_unit_id": (
                    f"u{index}"
                ),
                "fact_atom_refs": [
                    atom[
                        "fact_atom_id"
                    ]
                ],
                "explicitness": (
                    "explicit"
                ),
            }
            for index, atom in enumerate(
                atoms,
                start=1,
            )
        ],
    }
    ledger = {
        "schema_version": (
            "content-ledger-v1.0"
        ),
        "business_id": business_id,
        "entries": [
            entry
        ],
        "fact_atom_catalog": (
            atoms
        ),
    }
    ledger_path = (
        pipeline
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )
    write_json(
        ledger_path,
        ledger,
    )

    pattern_path = (
        pipeline
        / "data"
        / "patterns"
        / "approved"
        / subject.PRICE_PATTERN_ID
        / "pattern_v1.json"
    )
    write_json(
        pattern_path,
        {
            "pattern_id": (
                subject.PRICE_PATTERN_ID
            ),
            "status": "approved",
            "compatible_profiles": [
                "news"
            ],
            "evidence": [],
        },
    )

    coverage_path = (
        pipeline
        / "data"
        / "creative_coverage"
        / "revisions"
        / "news_final.json"
    )
    write_json(
        coverage_path,
        {
            "schema_version": (
                "news-production-mvp-coverage-update-v1.0"
            ),
            "status": (
                "current_derived_coverage_update"
            ),
            "news_current_readiness": {
                "operational_readiness": (
                    "production_validation_required"
                ),
                "validated_production_paths": [
                    subject.PRICE_PATTERN_ID
                ],
            },
            "pattern_production_validation": {
                subject.PRICE_PATTERN_ID: {
                    "status": "passed"
                }
            },
        },
    )

    template_source = (
        ROOT
        / "output"
        / "新闻体视频制作文案导入模板.xlsx"
    )
    template_target = (
        pipeline
        / "output"
        / "新闻体视频制作文案导入模板.xlsx"
    )
    template_target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        template_source,
        template_target,
    )

    return {
        "pipeline": pipeline,
        "business_id": business_id,
        "speaker_id": speaker_id,
        "source_content_id": (
            source_content_id
        ),
        "ledger_path": (
            ledger_path
        ),
    }


def build_review(
    tmp_path: Path,
    plan: dict,
    *,
    edit_first: str | None = None,
) -> Path:
    review = {
        "schema_version": (
            subject.REVIEW_SCHEMA
        ),
        "request_id": (
            plan["request_id"]
        ),
        "reviewer": "tester",
        "decision": (
            "approve_items"
        ),
        "items": [
            {
                "slot_id": (
                    slot["slot_id"]
                ),
                "decision": (
                    "approved"
                ),
                "approved_text": (
                    edit_first
                    if (
                        index == 0
                        and edit_first
                        is not None
                    )
                    else slot[
                        "proposed_text"
                    ]
                ),
            }
            for index, slot in enumerate(
                plan["slots"]
            )
        ],
    }
    path = (
        tmp_path
        / "review.json"
    )
    write_json(
        path,
        review,
    )
    return path


def test_news_creator_metadata_is_immutable_on_recovery(tmp_path: Path):
    fixture = build_fixture(tmp_path)
    arguments = dict(pipeline_root=fixture["pipeline"], business_id=fixture["business_id"],
        speaker_id=fixture["speaker_id"], source_content_id=fixture["source_content_id"],
        idempotency_key="news-creator-test")
    first, recovered = subject.create_news_delivery_request(**arguments,
        created_by_user_id=21, created_by_phone="13800000002")
    assert recovered is False
    second, recovered = subject.create_news_delivery_request(**arguments,
        created_by_user_id=22, created_by_phone="13800000003")
    assert recovered is True
    assert second == first
    assert first["created_by_user_id"] == 21
    assert first["created_by_phone"] == "13800000002"
    assert first["created_at"]


def test_preview_request_plan_approval_export_closure(
    tmp_path: Path,
):
    fixture = build_fixture(
        tmp_path
    )

    preview = (
        subject.preview_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            business_id=fixture[
                "business_id"
            ],
            speaker_id=fixture[
                "speaker_id"
            ],
        )
    )
    assert preview[
        "available"
    ] is True
    assert preview[
        "eligible_source_count"
    ] == 1
    assert preview[
        "eligible_sources"
    ][0][
        "recommended_slot_count"
    ] == 6

    request, recovered = (
        subject.create_news_delivery_request(
            pipeline_root=fixture[
                "pipeline"
            ],
            business_id=fixture[
                "business_id"
            ],
            speaker_id=fixture[
                "speaker_id"
            ],
            source_content_id=fixture[
                "source_content_id"
            ],
            idempotency_key=(
                "fixture-key"
            ),
        )
    )
    assert recovered is False

    same_request, recovered = (
        subject.create_news_delivery_request(
            pipeline_root=fixture[
                "pipeline"
            ],
            business_id=fixture[
                "business_id"
            ],
            speaker_id=fixture[
                "speaker_id"
            ],
            source_content_id=fixture[
                "source_content_id"
            ],
            idempotency_key=(
                "fixture-key"
            ),
        )
    )
    assert recovered is True
    assert (
        same_request[
            "request_id"
        ]
        == request[
            "request_id"
        ]
    )

    plan, recovered = (
        subject.resolve_news_delivery_plan(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
        )
    )
    assert recovered is False
    assert plan[
        "recommended_slot_count"
    ] == 6
    assert (
        plan["slots"][0][
            "source_known_fact"
        ]
        == "素菜加工费通常 8-10 元"
    )
    assert (
        plan["slots"][3][
            "proposed_text"
        ]
        == "油盐酱料免费"
    )
    assert (
        plan["authority"][
            "remote_model_called"
        ]
        is False
    )

    review_path = build_review(
        tmp_path,
        plan,
    )
    approved, recovered = (
        subject.approve_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
            review_path=review_path,
        )
    )
    assert recovered is False
    assert (
        approved[
            "approved_slot_count"
        ]
        == 6
    )

    ledger_before = (
        subject.read_json(
            fixture[
                "ledger_path"
            ]
        )
    )
    semantic_before = (
        subject.canonical_sha256(
            ledger_before[
                "entries"
            ]
        )
    )

    result, recovered = (
        subject.export_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
        )
    )
    assert recovered is False
    assert result[
        "stop_point_reached"
    ] is True
    assert result[
        "slot_count"
    ] == 6
    assert result[
        "semantic_entry_count_delta"
    ] == 0
    assert result[
        "remote_model_called"
    ] is False

    output_path = Path(
        result[
            "output_path"
        ]
    )
    assert output_path.is_file()
    assert (
        subject._xlsx_sheet_values(
            output_path,
            row_number=4,
            max_columns=6,
        )
        == [
            "标题1",
            "标题2",
            "标题3",
            "标题4",
            "标题5",
            "标题6",
        ]
    )

    ledger_after = (
        subject.read_json(
            fixture[
                "ledger_path"
            ]
        )
    )
    assert (
        subject.canonical_sha256(
            ledger_after[
                "entries"
            ]
        )
        == semantic_before
    )
    history = (
        ledger_after[
            "extensions"
        ][
            "presentation_history_v1"
        ][
            "entries"
        ]
    )
    assert len(
        history
    ) == 1
    assert (
        history[0][
            "source_content_ref"
        ]
        == fixture[
            "source_content_id"
        ]
    )
    assert (
        history[0][
            "semantic_novelty"
        ]
        is False
    )

    recovered_result, recovered = (
        subject.export_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
        )
    )
    assert recovered is True
    assert (
        recovered_result[
            "output_path"
        ]
        == result[
            "output_path"
        ]
    )
    ledger_after_recovery = (
        subject.read_json(
            fixture[
                "ledger_path"
            ]
        )
    )
    assert len(
        ledger_after_recovery[
            "extensions"
        ][
            "presentation_history_v1"
        ][
            "entries"
        ]
    ) == 1


@pytest.mark.parametrize(
    "count",
    [4, 8],
)
def test_dynamic_excel_supports_four_to_eight_columns(
    tmp_path: Path,
    count: int,
):
    template = (
        ROOT
        / "output"
        / "新闻体视频制作文案导入模板.xlsx"
    )
    output = (
        tmp_path
        / f"news_{count}.xlsx"
    )
    titles = [
        f"标题内容{index}"
        for index in range(
            1,
            count + 1,
        )
    ]
    result = (
        subject.export_dynamic_news_xlsx(
            template_path=template,
            output_path=output,
            titles=titles,
        )
    )
    assert result[
        "validation_passed"
    ] is True
    assert result[
        "slot_count"
    ] == count
    assert (
        subject._xlsx_sheet_values(
            output,
            row_number=4,
            max_columns=count,
        )
        == [
            f"标题{index}"
            for index in range(
                1,
                count + 1,
            )
        ]
    )
    assert (
        subject._xlsx_sheet_values(
            output,
            row_number=5,
            max_columns=count,
        )
        == titles
    )


def test_human_edit_cannot_drop_price_qualifier(
    tmp_path: Path,
):
    fixture = build_fixture(
        tmp_path
    )
    request, _ = (
        subject.create_news_delivery_request(
            pipeline_root=fixture[
                "pipeline"
            ],
            business_id=fixture[
                "business_id"
            ],
            speaker_id=fixture[
                "speaker_id"
            ],
            source_content_id=fixture[
                "source_content_id"
            ],
            idempotency_key=(
                "qualifier-key"
            ),
        )
    )
    plan, _ = (
        subject.resolve_news_delivery_plan(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
        )
    )
    review_path = build_review(
        tmp_path,
        plan,
        edit_first="素菜加工费8-10元",
    )

    with pytest.raises(
        subject.NewsDeliveryError
    ) as exc:
        subject.approve_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
            review_path=review_path,
        )

    assert (
        exc.value.code
        == "NEWS_DELIVERY_TITLE_LOST_QUALIFIER"
    )


def test_human_edit_cannot_drop_price_subject(
    tmp_path: Path,
):
    fixture = build_fixture(
        tmp_path
    )
    request, _ = (
        subject.create_news_delivery_request(
            pipeline_root=fixture[
                "pipeline"
            ],
            business_id=fixture[
                "business_id"
            ],
            speaker_id=fixture[
                "speaker_id"
            ],
            source_content_id=fixture[
                "source_content_id"
            ],
            idempotency_key=(
                "subject-key"
            ),
        )
    )
    plan, _ = (
        subject.resolve_news_delivery_plan(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
        )
    )
    review_path = build_review(
        tmp_path,
        plan,
        edit_first="通常8-10元",
    )

    with pytest.raises(
        subject.NewsDeliveryError
    ) as exc:
        subject.approve_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
            review_path=review_path,
        )

    assert (
        exc.value.code
        == "NEWS_DELIVERY_TITLE_LOST_SUBJECT"
    )


def test_preview_excludes_source_already_exported_as_same_news_pattern(
    tmp_path: Path,
):
    fixture = build_fixture(
        tmp_path
    )

    ledger = subject.read_json(
        fixture["ledger_path"]
    )
    ledger["extensions"] = {
        "presentation_history_v1": {
            "version": "content-presentation-history-v1.0",
            "storage_policy": "append_only",
            "semantic_novelty_authority": False,
            "entries": [
                {
                    "presentation_id": "old-news-P001",
                    "production_profile": "news",
                    "status": "exported",
                    "source_content_ref": fixture[
                        "source_content_id"
                    ],
                    "selected_pattern_ref": subject.PRICE_PATTERN_ID,
                    "exported_at": "2026-09-18T00:00:00+00:00",
                }
            ],
        }
    }
    write_json(
        fixture["ledger_path"],
        ledger,
    )

    preview = subject.preview_news_delivery(
        pipeline_root=fixture[
            "pipeline"
        ],
        business_id=fixture[
            "business_id"
        ],
        speaker_id=fixture[
            "speaker_id"
        ],
    )

    assert preview["available"] is False
    assert preview[
        "eligible_source_count"
    ] == 0
    assert preview[
        "already_presented_source_count"
    ] == 1
    assert preview[
        "already_presented_sources"
    ][0][
        "source_content_id"
    ] == fixture[
        "source_content_id"
    ]
    assert preview["authority"][
        "same_source_same_pattern_reexport_blocked"
    ] is True


def test_legacy_v1_approved_text_edit_projects_as_revised_and_approved(
    tmp_path: Path,
):
    fixture = build_fixture(
        tmp_path
    )

    request, _ = (
        subject.create_news_delivery_request(
            pipeline_root=fixture[
                "pipeline"
            ],
            business_id=fixture[
                "business_id"
            ],
            speaker_id=fixture[
                "speaker_id"
            ],
            source_content_id=fixture[
                "source_content_id"
            ],
            idempotency_key=(
                "legacy-v1-edit-key"
            ),
        )
    )

    plan, _ = (
        subject.resolve_news_delivery_plan(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
        )
    )

    review = {
        "schema_version": (
            subject.REVIEW_SCHEMA
        ),
        "request_id": (
            request[
                "request_id"
            ]
        ),
        "reviewer": "tester",
        "decision": (
            "approve_items"
        ),
        "items": [],
    }

    for index, slot in enumerate(
        plan[
            "slots"
        ]
    ):
        review[
            "items"
        ].append(
            {
                "slot_id": (
                    slot[
                        "slot_id"
                    ]
                ),
                "decision": (
                    "approved"
                ),
                "approved_text": (
                    "清蒸大约15元"
                    if index == 1
                    else slot[
                        "proposed_text"
                    ]
                ),
                "note": "",
            }
        )

    review_path = (
        tmp_path
        / "legacy_v1_edit_review.json"
    )

    write_json(
        review_path,
        review,
    )

    approved, _ = (
        subject.approve_news_delivery(
            pipeline_root=fixture[
                "pipeline"
            ],
            request_id=request[
                "request_id"
            ],
            review_path=(
                review_path
            ),
        )
    )

    edited = approved[
        "approved_slots"
    ][1]

    assert (
        edited[
            "approved_text"
        ]
        == "清蒸大约15元"
    )

    assert (
        edited[
            "human_review_decision"
        ]
        == "revised_and_approved"
    )

    assert (
        edited[
            "human_revision"
        ][
            "source_text"
        ]
        == "清蒸约15元"
    )
