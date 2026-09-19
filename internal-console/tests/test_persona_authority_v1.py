from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.canonical_gateway import CanonicalOperationError
from app.persona_authority import (
    resolve_persona_authority,
    validate_speaker_business_binding,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_persona(
    root: Path,
    *,
    persona_id: str,
    directory: str,
    revision: int,
    scope: str = "business",
    status: str = "approved",
    previous: dict | None = None,
    business_ref: dict | None = None,
) -> dict:
    path = root / "data" / "personas" / persona_id / directory / "persona_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    approved = status == "approved"
    content_sha = f"content-{persona_id}-{revision}"
    persona = {
        "schema_version": "persona-v1.0",
        "persona_id": persona_id,
        "revision": revision,
        "persona_scope": scope,
        "lifecycle": {"status": status, "approved": approved},
        "approval": {"human_gate": approved},
        "provenance": {"content_sha256": content_sha},
        "revision_lineage": {
            "previous_approved_revision": previous,
            "silent_overwrite_allowed": False,
        },
    }
    if business_ref is not None:
        persona["business_persona_ref"] = business_ref
    path.write_text(json.dumps(persona, indent=2), encoding="utf-8")

    result = {
        "persona_id": persona_id,
        "revision": revision,
        "content_sha256": content_sha,
        "file_sha256": sha256(path),
        "path": path,
        "artifact": persona,
    }
    if approved:
        receipt = {
            "schema_version": "persona-approval-receipt-v1.0",
            "persona_id": persona_id,
            "revision": revision,
            "decision": "approved",
            "human_gate": True,
            "persona_sha256_after_approval": result["file_sha256"],
            "content_sha256": content_sha,
            "previous_approved_revision": previous,
        }
        (path.parent / "approval_receipt.json").write_text(
            json.dumps(receipt, indent=2),
            encoding="utf-8",
        )
    return result


def previous_ref(item: dict) -> dict:
    return {
        "path": str(item["path"]),
        "revision": item["revision"],
        "sha256": item["file_sha256"],
        "content_sha256": item["content_sha256"],
    }


def test_explicit_receipt_and_lineage_not_filename_order_select_current(
    tmp_path: Path,
):
    settings = SimpleNamespace(pipeline_root=tmp_path)
    first = write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_z_last_lexically",
        revision=1,
    )
    write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_a_first_lexically",
        revision=2,
        previous=previous_ref(first),
    )

    resolved = resolve_persona_authority(settings, "business_a", "business")

    assert resolved.current is not None
    assert resolved.current["revision"] == 2
    assert resolved.current["path"].parent.name == "revision_a_first_lexically"


def test_stale_review_revision_does_not_override_current_approved(
    tmp_path: Path,
):
    settings = SimpleNamespace(pipeline_root=tmp_path)
    write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_current",
        revision=1,
    )
    write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_zz_stale",
        revision=1,
        status="review_required",
    )

    resolved = resolve_persona_authority(settings, "business_a", "business")

    assert resolved.current is not None
    assert resolved.current["revision"] == 1
    assert resolved.review_candidate is None
    assert resolved.projected == resolved.current


def test_ambiguous_approved_persona_fails_closed(tmp_path: Path):
    settings = SimpleNamespace(pipeline_root=tmp_path)
    write_persona(
        tmp_path,
        persona_id="business_a",
        directory="branch_a",
        revision=1,
    )
    write_persona(
        tmp_path,
        persona_id="business_a",
        directory="branch_b",
        revision=1,
    )

    with pytest.raises(CanonicalOperationError) as caught:
        resolve_persona_authority(settings, "business_a", "business")

    assert caught.value.code == "CURRENT_AUTHORITY_AMBIGUITY"


def test_approved_receipt_mismatch_fails_closed(tmp_path: Path):
    settings = SimpleNamespace(pipeline_root=tmp_path)
    approved = write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_current",
        revision=1,
    )
    receipt_path = approved["path"].parent / "approval_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["content_sha256"] = "mismatched-content"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    with pytest.raises(CanonicalOperationError) as caught:
        resolve_persona_authority(settings, "business_a", "business")

    assert caught.value.code == "INVALID_PERSONA_APPROVAL_RECEIPT"


def test_ambiguous_approved_lineage_fails_closed(tmp_path: Path):
    settings = SimpleNamespace(pipeline_root=tmp_path)
    first = write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_one",
        revision=1,
    )
    wrong_previous = previous_ref(first)
    wrong_previous["sha256"] = "0" * 64
    write_persona(
        tmp_path,
        persona_id="business_a",
        directory="revision_two",
        revision=2,
        previous=wrong_previous,
    )

    with pytest.raises(CanonicalOperationError) as caught:
        resolve_persona_authority(settings, "business_a", "business")

    assert caught.value.code == "LINEAGE_HASH_MISMATCH"


def test_business_and_speaker_use_same_current_resolver_semantics(
    tmp_path: Path,
):
    settings = SimpleNamespace(pipeline_root=tmp_path)
    business = write_persona(
        tmp_path,
        persona_id="business_a",
        directory="business_current",
        revision=1,
    )
    speaker = write_persona(
        tmp_path,
        persona_id="speaker_a",
        directory="speaker_current",
        revision=1,
        scope="speaker",
        business_ref={
            "persona_id": "business_a",
            "revision": 1,
            "path": str(business["path"]),
            "sha256": business["file_sha256"],
            "content_sha256": business["content_sha256"],
            "status": "approved",
        },
    )

    business_current = resolve_persona_authority(
        settings, "business_a", "business"
    ).current
    speaker_current = resolve_persona_authority(
        settings, "speaker_a", "speaker"
    ).current

    assert business_current is not None
    assert speaker_current is not None
    validate_speaker_business_binding(speaker_current, business_current)
    assert speaker_current["path"] == speaker["path"]
