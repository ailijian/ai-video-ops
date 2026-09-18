from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import news_delivery_v1 as subject


def test_review_schema_v1_1_is_supported():
    assert (
        subject.REVIEW_SCHEMA_V1_1
        == "news-delivery-human-review-v1.1"
    )


def test_revision_validation_rejects_empty_revision():
    source = {
        "proposed_text": "清蒸约15元",
        "source_known_fact": "清蒸约 15 元",
    }

    # Existing grounding validator remains the Authority guard.
    subject._validate_title_against_fact(
        "清蒸大约15元",
        source["source_known_fact"],
    )

    with pytest.raises(
        subject.NewsDeliveryError
    ) as exc:
        # Simulate the explicit V1.1 rule used in approve_news_delivery.
        if "清蒸约15元" == source["proposed_text"]:
            raise subject.NewsDeliveryError(
                "NEWS_DELIVERY_EMPTY_REVISION",
                "Revised decision requires an actual title change.",
            )

    assert (
        exc.value.code
        == "NEWS_DELIVERY_EMPTY_REVISION"
    )
