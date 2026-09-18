from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(
    __file__
).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )

import review_generation_batch_v2 as subject


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


def make_batch(
    tmp_path: Path,
) -> Path:
    path = (
        tmp_path
        / "data"
        / "generation_batches"
        / "gen_fixture"
        / "generation_batch_v1.json"
    )

    write_json(
        path,
        {
            "schema_version": (
                "generation-batch-v1.0"
            ),
            "request_id": (
                "gen_fixture"
            ),
            "profile": "mix",
            "status": (
                "review_required"
            ),
            "requested_quantity": 3,
            "validation": {
                "passed": True,
            },
            "contents": [
                {
                    "content_id": (
                        "gen_fixture-C001"
                    ),
                    "title": (
                        "先检查再洗护"
                    ),
                    "narration": (
                        "洗护前先看宠物皮肤和毛发状态，再确认怎么处理。"
                    ),
                    "central_claim": (
                        "洗护前先检查宠物皮肤和毛发状态。"
                    ),
                    "status": "generated",
                },
                {
                    "content_id": (
                        "gen_fixture-C002"
                    ),
                    "title": (
                        "每次洗护方式可能不同"
                    ),
                    "narration": (
                        "具体处理根据宠物当时的皮肤、毛发和实际状态判断。"
                    ),
                    "central_claim": (
                        "洗护方式根据宠物当时状态判断。"
                    ),
                    "status": "generated",
                },
                {
                    "content_id": (
                        "gen_fixture-C003"
                    ),
                    "title": (
                        "第三条候选"
                    ),
                    "narration": (
                        "这是第三条候选内容。"
                    ),
                    "central_claim": (
                        "第三条候选内容。"
                    ),
                    "status": "generated",
                },
            ],
            "authority": {
                "content_ledger_written": False,
            },
        },
    )

    return path


def make_review(
    tmp_path: Path,
    items: list[dict],
) -> Path:
    path = (
        tmp_path
        / "review_input.json"
    )
    write_json(
        path,
        {
            "schema_version": (
                "generation-batch-review-input-v2.0"
            ),
            "reviewer": "tester",
            "note": "",
            "items": items,
        },
    )
    return path


def test_partial_approval_and_revision_exports_only_human_approved_projection(
    tmp_path: Path,
):
    batch = make_batch(
        tmp_path
    )

    review = make_review(
        tmp_path,
        [
            {
                "content_id": (
                    "gen_fixture-C001"
                ),
                "decision": (
                    "approved"
                ),
                "note": "",
            },
            {
                "content_id": (
                    "gen_fixture-C002"
                ),
                "decision": (
                    "revised"
                ),
                "revised_title": (
                    "同一只宠物，每次洗护方式可能不同"
                ),
                "revised_narration": (
                    "同一只宠物每次到店状态都可能不同，具体洗护方式还是根据当时的皮肤、毛发和实际状态判断。"
                ),
                "meaning_preserved": True,
                "new_facts_added": False,
                "note": (
                    "更自然的口播表达"
                ),
            },
            {
                "content_id": (
                    "gen_fixture-C003"
                ),
                "decision": (
                    "rejected"
                ),
                "note": (
                    "不值得发布"
                ),
            },
        ],
    )

    result = (
        subject.review_generation_batch_v2(
            batch_path=batch,
            review_input_path=review,
        )
    )

    assert (
        result["status"]
        == "approved"
    )
    assert (
        result[
            "approved_item_count"
        ]
        == 2
    )
    assert (
        result[
            "revised_and_approved_count"
        ]
        == 1
    )
    assert (
        result[
            "rejected_item_count"
        ]
        == 1
    )
    assert (
        result[
            "partial_source_batch_approval"
        ]
        is True
    )

    approved = subject.read_json(
        Path(
            result[
                "output_path"
            ]
        )
    )

    assert len(
        approved["contents"]
    ) == 2
    assert all(
        item["status"]
        == "human_approved"
        for item in (
            approved["contents"]
        )
    )

    revised = next(
        item
        for item in (
            approved["contents"]
        )
        if item[
            "content_id"
        ]
        == "gen_fixture-C002"
    )

    assert (
        revised[
            "human_review"
        ][
            "decision"
        ]
        == "revised_and_approved"
    )
    assert (
        revised[
            "central_claim"
        ]
        == "洗护方式根据宠物当时状态判断。"
    )
    assert (
        revised[
            "human_revision"
        ][
            "central_claim"
        ]
        == "洗护方式根据宠物当时状态判断。"
    )


def test_revision_cannot_add_numeric_fact(
    tmp_path: Path,
):
    batch = make_batch(
        tmp_path
    )

    review = make_review(
        tmp_path,
        [
            {
                "content_id": (
                    "gen_fixture-C001"
                ),
                "decision": (
                    "revised"
                ),
                "revised_title": (
                    "洗护前先检查3项"
                ),
                "revised_narration": (
                    "洗护前先检查3项，再确认怎么处理。"
                ),
                "meaning_preserved": True,
                "new_facts_added": False,
            },
            {
                "content_id": (
                    "gen_fixture-C002"
                ),
                "decision": (
                    "rejected"
                ),
            },
            {
                "content_id": (
                    "gen_fixture-C003"
                ),
                "decision": (
                    "rejected"
                ),
            },
        ],
    )

    with pytest.raises(
        subject.GenerationReviewV2Error
    ) as exc:
        subject.review_generation_batch_v2(
            batch_path=batch,
            review_input_path=review,
        )

    assert (
        exc.value.code
        == "GENERATION_REVIEW_V2_NEW_NUMERIC_FACT"
    )


def test_revision_cannot_add_strengthening_claim(
    tmp_path: Path,
):
    batch = make_batch(
        tmp_path
    )

    review = make_review(
        tmp_path,
        [
            {
                "content_id": (
                    "gen_fixture-C001"
                ),
                "decision": (
                    "revised"
                ),
                "revised_title": (
                    "洗护前一定先检查"
                ),
                "revised_narration": (
                    "我们保证洗护前一定先检查宠物皮肤和毛发状态。"
                ),
                "meaning_preserved": True,
                "new_facts_added": False,
            },
            {
                "content_id": (
                    "gen_fixture-C002"
                ),
                "decision": (
                    "rejected"
                ),
            },
            {
                "content_id": (
                    "gen_fixture-C003"
                ),
                "decision": (
                    "rejected"
                ),
            },
        ],
    )

    with pytest.raises(
        subject.GenerationReviewV2Error
    ) as exc:
        subject.review_generation_batch_v2(
            batch_path=batch,
            review_input_path=review,
        )

    assert (
        exc.value.code
        == "GENERATION_REVIEW_V2_STRENGTHENED_CLAIM"
    )


def test_all_rejected_creates_non_exportable_reviewed_batch(
    tmp_path: Path,
):
    batch = make_batch(
        tmp_path
    )

    review = make_review(
        tmp_path,
        [
            {
                "content_id": (
                    content_id
                ),
                "decision": (
                    "rejected"
                ),
                "note": "",
            }
            for content_id in (
                "gen_fixture-C001",
                "gen_fixture-C002",
                "gen_fixture-C003",
            )
        ],
    )

    result = (
        subject.review_generation_batch_v2(
            batch_path=batch,
            review_input_path=review,
        )
    )

    assert (
        result["status"]
        == "rejected"
    )
    assert (
        result[
            "approved_item_count"
        ]
        == 0
    )

    reviewed = subject.read_json(
        Path(
            result[
                "output_path"
            ]
        )
    )

    assert (
        reviewed["status"]
        == "rejected"
    )
    assert (
        reviewed[
            "authority"
        ][
            "export_allowed"
        ]
        is False
    )


def test_same_review_recovers_idempotently(
    tmp_path: Path,
):
    batch = make_batch(
        tmp_path
    )

    items = [
        {
            "content_id": (
                "gen_fixture-C001"
            ),
            "decision": (
                "approved"
            ),
        },
        {
            "content_id": (
                "gen_fixture-C002"
            ),
            "decision": (
                "approved"
            ),
        },
        {
            "content_id": (
                "gen_fixture-C003"
            ),
            "decision": (
                "rejected"
            ),
        },
    ]

    review = make_review(
        tmp_path,
        items,
    )

    first = (
        subject.review_generation_batch_v2(
            batch_path=batch,
            review_input_path=review,
        )
    )

    second = (
        subject.review_generation_batch_v2(
            batch_path=batch,
            review_input_path=review,
        )
    )

    assert (
        second["recovered"]
        is True
    )
    assert (
        second[
            "output_sha256"
        ]
        == first[
            "output_sha256"
        ]
    )
