from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )


import generation_request_handoff_v1 as subject  # noqa: E402

from match_generation_sources_v1 import (  # noqa: E402
    load_request,
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


def fake_authorities(
    tmp_path: Path,
):
    business_path = (
        tmp_path
        / "data"
        / "personas"
        / "fixture_pet_store"
        / "revision_0001"
        / "persona_v1.json"
    )

    speaker_path = (
        tmp_path
        / "data"
        / "personas"
        / "fixture_pet_store_owner"
        / "revision_0001"
        / "persona_v1.json"
    )

    business_receipt = business_path.parent / "approval_receipt.json"

    speaker_receipt = speaker_path.parent / "approval_receipt.json"

    registry_path = (
        tmp_path
        / "data"
        / "production_profiles"
        / "production_profile_registry_v1.json"
    )

    for path, value in (
        (
            business_path,
            {"fixture": "business"},
        ),
        (
            speaker_path,
            {"fixture": "speaker"},
        ),
        (
            business_receipt,
            {"fixture": ("business_receipt")},
        ),
        (
            speaker_receipt,
            {"fixture": ("speaker_receipt")},
        ),
        (
            registry_path,
            {"fixture": "registry"},
        ),
    ):
        write_json(
            path,
            value,
        )

    business = {
        "persona_id": ("fixture_pet_store"),
        "revision": 1,
        "path": business_path,
        "receipt_path": (business_receipt),
        "file_sha256": (subject.sha256_file(business_path)),
        "content_sha256": ("b" * 64),
    }

    speaker = {
        "persona_id": ("fixture_pet_store_owner"),
        "revision": 1,
        "path": speaker_path,
        "receipt_path": (speaker_receipt),
        "file_sha256": (subject.sha256_file(speaker_path)),
        "content_sha256": ("s" * 64),
    }

    return (
        business,
        speaker,
    )


def fake_preview(
    *,
    quantity=5,
    recommended=3,
    can_continue=True,
    status="capacity_limited",
):
    return {
        "business": {
            "business_id": ("fixture_pet_store"),
            "revision": 1,
            "status": "APPROVED",
        },
        "speaker": {
            "speaker_id": ("fixture_pet_store_owner"),
            "revision": 1,
            "status": "APPROVED",
        },
        "profiles": {
            "mix": {
                "profile_id": "mix",
                "status": ("production_ready"),
                "available": True,
            },
            "news": {
                "profile_id": "news",
                "status": ("research_coverage_" "insufficient"),
                "available": False,
            },
        },
        "selection": {
            "profile": "mix",
            "requested_quantity": (quantity),
        },
        "capacity": {
            "scope": ("business_wide_" "semantic_novelty"),
            "source_mode": ("initial_persona_capacity"),
            "ledger_entry_count": 0,
            "high_quality_novel_capacity": (recommended),
            "capacity_status": (status),
            "content_gap_summary": [],
            "padding_allowed": False,
        },
        "recommendation": {
            "status": status,
            "requested_quantity": (quantity),
            "recommended_quantity": (recommended),
            "can_continue": (can_continue),
            "blocker": (None if can_continue else "TEST_BLOCKER"),
        },
        "evidence_refs": [
            "fixture-business",
            "fixture-speaker",
        ],
    }


def patch_authority(
    tmp_path: Path,
    monkeypatch,
    *,
    preview=None,
):
    (
        business,
        speaker,
    ) = fake_authorities(tmp_path)

    monkeypatch.setattr(
        subject,
        "build_content_creation_entry",
        lambda **kwargs: (
            preview or fake_preview(quantity=kwargs["requested_quantity"])
        ),
    )

    monkeypatch.setattr(
        subject,
        "resolve_current_persona",
        lambda *args, **kwargs: (business),
    )

    monkeypatch.setattr(
        subject,
        "resolve_speaker_persona",
        lambda *args, **kwargs: (speaker),
    )

    return (
        business,
        speaker,
    )


def create_request(
    tmp_path: Path,
    *,
    idempotency_key=(
        "console_test_0001"
    ),
    requested=5,
    confirmed=3,
    created_at=(
        "2026-09-17T"
        "10:00:00+00:00"
    ),
):
    return (
        subject
        .create_generation_request_handoff(
            pipeline_root=tmp_path,
            business_id=(
                "fixture_pet_store"
            ),
            speaker_id=(
                "fixture_pet_store_owner"
            ),
            profile="mix",
            requested_quantity=(
                requested
            ),
            confirmed_quantity=(
                confirmed
            ),
            idempotency_key=(
                idempotency_key
            ),
            created_at=created_at,
        )
    )


def test_creates_matcher_compatible_immutable_request_and_handoff(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    result = create_request(tmp_path)

    request_path = Path(result["request_path"])

    handoff_path = Path(result["handoff_path"])

    assert request_path.is_file()
    assert handoff_path.is_file()

    request = json.loads(request_path.read_text(encoding="utf-8"))

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))

    assert request["schema_version"] == "generation-request-v1.0"

    assert request["quantity"] == 3

    assert request["target_profile"] == "mix"

    assert request["content_intent"] == "mixed"

    assert request["platform"] == "douyin"

    assert request["constraints"]["no_padding"] is True

    assert request["authority"]["script_generation_performed"] is False

    parsed, _ = load_request(
        request_path,
        {
            "persona_id": ("fixture_pet_store"),
            "revision": 1,
        },
        {
            "persona_id": ("fixture_pet_store_owner"),
            "revision": 1,
        },
    )

    assert parsed["request_id"] == result["request_id"]

    assert handoff["status"] == ("source_authority_" "resolution_pending")

    assert handoff["authority"]["source_matching_performed"] is False

    assert handoff["authority"]["remote_model_called"] is False

    assert handoff["generation_request_ref"]["file_sha256"] == subject.sha256_file(
        request_path
    )


def test_same_idempotency_key_recovers_same_request(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    first = create_request(tmp_path)

    monkeypatch.setattr(
        subject,
        "build_content_creation_entry",
        lambda **kwargs: (
            (_ for _ in ()).throw(
                AssertionError("Idempotent retry " "must not recalculate.")
            )
        ),
    )

    second = create_request(tmp_path)

    assert second["request_id"] == first["request_id"]

    assert second["request_sha256"] == first["request_sha256"]

    assert second["handoff_sha256"] == first["handoff_sha256"]

    assert second["recovered"] is True


def test_stale_capacity_confirmation_fails_before_write(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
        preview=fake_preview(
            quantity=5,
            recommended=2,
        ),
    )

    with pytest.raises(subject.GenerationRequestError) as exc:
        create_request(
            tmp_path,
            requested=5,
            confirmed=3,
        )

    assert exc.value.code == "CAPACITY_CONFIRMATION_STALE"

    request_root = tmp_path / "data" / "generation_requests"

    assert not request_root.exists() or not any(
        request_root.rglob("generation_request_v1.json")
    )


def test_unavailable_profile_cannot_create_request(
    tmp_path: Path,
    monkeypatch,
):
    preview = fake_preview(
        quantity=2,
        recommended=0,
        can_continue=False,
        status="profile_unavailable",
    )

    preview["selection"]["profile"] = "news"

    preview["recommendation"]["blocker"] = "PROFILE_NOT_" "PRODUCTION_READY"

    patch_authority(
        tmp_path,
        monkeypatch,
        preview=preview,
    )

    with pytest.raises(subject.GenerationRequestError) as exc:
        (
            subject.create_generation_request_handoff(
                pipeline_root=tmp_path,
                business_id=("fixture_pet_store"),
                speaker_id=("fixture_pet_store_owner"),
                profile="news",
                requested_quantity=2,
                confirmed_quantity=2,
                idempotency_key=("console_test_news_01"),
            )
        )

    assert exc.value.code == ("PROFILE_NOT_" "PRODUCTION_READY")


def test_same_idempotency_key_cannot_change_confirmation(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    create_request(tmp_path)

    with pytest.raises(subject.GenerationRequestError) as exc:
        create_request(
            tmp_path,
            requested=5,
            confirmed=2,
        )

    assert exc.value.code == ("GENERATION_" "IDEMPOTENCY_CONFLICT")


def test_equivalent_active_request_is_recovered_with_different_key(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    first = create_request(
        tmp_path,
        idempotency_key=("console_test_0001"),
    )

    second = subject.create_generation_request_handoff(
        pipeline_root=tmp_path,
        business_id=("fixture_pet_store"),
        speaker_id=("fixture_pet_store_owner"),
        profile="mix",
        requested_quantity=5,
        confirmed_quantity=3,
        idempotency_key=("console_test_0002"),
    )

    assert second["request_id"] == first["request_id"]

    assert second["recovered"] is True

    request_root = tmp_path / "data" / "generation_requests"

    requests = list(request_root.rglob("generation_request_v1.json"))

    assert len(requests) == 1


def test_different_active_request_blocks_parallel_creation(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    create_request(
        tmp_path,
        idempotency_key=("console_test_0001"),
    )

    with pytest.raises(subject.GenerationRequestError) as exc:
        subject.create_generation_request_handoff(
            pipeline_root=tmp_path,
            business_id=("fixture_pet_store"),
            speaker_id=("fixture_pet_store_owner"),
            profile="mix",
            requested_quantity=5,
            confirmed_quantity=2,
            idempotency_key=("console_test_0002"),
        )

    assert exc.value.code == "CONTENT_GENERATION_IN_FLIGHT"

    request_root = tmp_path / "data" / "generation_requests"

    requests = list(request_root.rglob("generation_request_v1.json"))

    assert len(requests) == 1


def test_same_confirmed_but_different_requested_quantity_blocks(
    tmp_path: Path,
    monkeypatch,
):
    """Same confirmed quantity with a different operator requested quantity
    is a different confirmation, not an equivalent Request: it must hit the
    active-request blocker instead of an idempotency conflict or a silent
    recovery.
    """
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    create_request(
        tmp_path,
        idempotency_key=("console_test_0001"),
        requested=5,
        confirmed=3,
    )

    with pytest.raises(subject.GenerationRequestError) as exc:
        subject.create_generation_request_handoff(
            pipeline_root=tmp_path,
            business_id=("fixture_pet_store"),
            speaker_id=("fixture_pet_store_owner"),
            profile="mix",
            requested_quantity=10,
            confirmed_quantity=3,
            idempotency_key=("console_test_0002"),
        )

    assert exc.value.code == "CONTENT_GENERATION_IN_FLIGHT"

    request_root = tmp_path / "data" / "generation_requests"

    requests = list(request_root.rglob("generation_request_v1.json"))

    assert len(requests) == 1


def test_concurrent_same_idempotency_key_creates_single_request(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    results: list[dict] = []

    errors: list[
        Exception
    ] = []

    barrier = threading.Barrier(
        2
    )

    timestamps = [
        (
            "2026-09-17T"
            "10:00:00.000001+00:00"
        ),
        (
            "2026-09-17T"
            "10:00:00.999999+00:00"
        ),
    ]

    def worker(
        index: int,
    ):
        try:
            barrier.wait(
                timeout=10
            )

            results.append(
                create_request(
                    tmp_path,
                    idempotency_key=(
                        "console_test_0001"
                    ),
                    created_at=(
                        timestamps[
                            index
                        ]
                    ),
                )
            )

        except Exception as exc:
            errors.append(
                exc
            )

    threads = [
        threading.Thread(
            target=worker,
            args=(0,),
        ),
        threading.Thread(
            target=worker,
            args=(1,),
        ),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(
            timeout=30
        )

    assert not errors

    assert len(results) == 2

    assert (
        results[0][
            "request_id"
        ]
        == results[1][
            "request_id"
        ]
    )

    assert (
        results[0][
            "request_sha256"
        ]
        == results[1][
            "request_sha256"
        ]
    )

    request_root = (
        tmp_path
        / "data"
        / "generation_requests"
    )

    requests = list(
        request_root.rglob(
            "generation_request_v1.json"
        )
    )

    assert len(requests) == 1

    assert (
        subject.sha256_file(
            requests[0]
        )
        == results[0][
            "request_sha256"
        ]
    )


def test_concurrent_different_keys_same_business_create_only_one_request(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    results: list[dict] = []

    errors: list[
        Exception
    ] = []

    barrier = threading.Barrier(
        2
    )

    keys = [
        "console_parallel_0001",
        "console_parallel_0002",
    ]

    timestamps = [
        (
            "2026-09-17T"
            "11:00:00.000001+00:00"
        ),
        (
            "2026-09-17T"
            "11:00:00.999999+00:00"
        ),
    ]

    def worker(
        index: int,
    ):
        try:
            barrier.wait(
                timeout=10
            )

            results.append(
                create_request(
                    tmp_path,
                    idempotency_key=(
                        keys[index]
                    ),
                    created_at=(
                        timestamps[
                            index
                        ]
                    ),
                )
            )

        except Exception as exc:
            errors.append(
                exc
            )

    threads = [
        threading.Thread(
            target=worker,
            args=(0,),
        ),
        threading.Thread(
            target=worker,
            args=(1,),
        ),
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(
            timeout=30
        )

    assert not errors

    assert len(results) == 2

    assert (
        results[0][
            "request_id"
        ]
        == results[1][
            "request_id"
        ]
    )

    request_root = (
        tmp_path
        / "data"
        / "generation_requests"
    )

    requests = list(
        request_root.rglob(
            "generation_request_v1.json"
        )
    )

    assert len(requests) == 1

    recovered_count = sum(
        result.get(
            "recovered"
        )
        is True
        for result in results
    )

    assert recovered_count == 1


def test_request_does_not_write_ledger_or_batch(
    tmp_path: Path,
    monkeypatch,
):
    patch_authority(
        tmp_path,
        monkeypatch,
    )

    result = create_request(tmp_path)

    ledger_path = (
        tmp_path
        / "data"
        / "content_ledgers"
        / "fixture_pet_store"
        / "content_ledger_v1.json"
    )

    assert not ledger_path.exists()

    batch_root = tmp_path / "data" / "generation_batches"

    assert not batch_root.exists()

    assert result["authority"]["remote_model_called"] is False

    assert result["authority"]["script_generation_performed"] is False
