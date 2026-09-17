from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_persona_v1 import (
    persona_content_hash,
    sha256_bytes,
    sha256_file,
    validate_required_fact_authority,
)

APPROVER_VERSION = "approve_persona_v1.py@0.3"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_atomic_json(path: Path, value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return sha256_bytes(payload)


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
    return sha256_bytes(payload)


def approve_persona(
    persona_path: Path,
    reviewer: str,
    note: str,
    approved_at: str | None = None,
    decision_metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    persona_path = persona_path.expanduser().resolve()
    if not persona_path.is_file():
        raise FileNotFoundError(persona_path)
    original_bytes = persona_path.read_bytes()
    before_sha = sha256_bytes(original_bytes)
    persona = json.loads(original_bytes.decode("utf-8"))
    errors: list[str] = []
    lifecycle = persona.get("lifecycle", {})
    if (
        lifecycle.get("status") != "review_required"
        or lifecycle.get("approved") is not False
    ):
        errors.append("Persona must be review_required and not approved.")
    errors.extend(validate_required_fact_authority(persona))
    recorded_content_sha = str(
        persona.get("provenance", {}).get("content_sha256") or ""
    )
    actual_content_sha = persona_content_hash(persona)
    if recorded_content_sha != actual_content_sha:
        errors.append("Persona content SHA-256 mismatch.")
    if persona.get("validation", {}).get("passed") is not True:
        errors.append("Persona build validation is not passed.")
    if persona.get("validation", {}).get("case_sources_consumed") is not False:
        errors.append("Persona unexpectedly consumed Case sources.")
    if persona.get("persona_scope", "business") == "speaker":
        reference = persona.get("business_persona_ref") or {}
        business_path = Path(str(reference.get("path") or ""))
        if not business_path.is_file():
            errors.append("Speaker Business Persona reference is missing.")
        elif sha256_file(business_path) != reference.get("sha256"):
            errors.append("Speaker Business Persona SHA-256 mismatch.")
        else:
            business = json.loads(business_path.read_text(encoding="utf-8"))
            if (
                business.get("persona_scope", "business") != "business"
                or business.get("lifecycle", {}).get("status") != "approved"
                or business.get("lifecycle", {}).get("approved") is not True
            ):
                errors.append(
                    "Speaker must remain bound to an Approved Business Persona."
                )
    receipt_path = persona_path.parent / "approval_receipt.json"
    if receipt_path.exists():
        errors.append("Persona approval receipt already exists.")
    if errors:
        raise RuntimeError("Persona approval blocked: " + " ".join(errors))

    metadata = copy.deepcopy(decision_metadata or {})
    allowed_metadata = {
        "approved_delta_refs",
        "lineage_only_refs",
        "excluded_review_refs",
        "derived_constraint_refs",
        "decision_artifact_ref",
    }
    unexpected_metadata = sorted(set(metadata) - allowed_metadata)
    if unexpected_metadata:
        raise ValueError(
            "Unsupported Persona approval decision metadata: "
            + ", ".join(unexpected_metadata)
        )

    timestamp = approved_at or now_iso()
    lifecycle.update(
        {
            "status": "approved",
            "approved": True,
            "human_review_required": False,
            "approved_at": timestamp,
            "approved_by": reviewer,
            "approval_note": note,
        }
    )
    persona["lifecycle"] = lifecycle
    persona["approval"] = {
        "decision": "approved",
        "reviewer": reviewer,
        "approved_at": timestamp,
        "note": note,
        "human_gate": True,
        "approver_version": APPROVER_VERSION,
    }
    if metadata:
        persona["approval"]["review_decision_metadata"] = metadata
    persona["validation"]["human_approval_completed"] = True
    persona["validation"]["auto_approved"] = False
    after_sha = write_atomic_json(persona_path, persona)
    receipt = {
        "schema_version": "persona-approval-receipt-v1.0",
        "persona_id": persona.get("persona_id"),
        "revision": persona.get("revision"),
        "fixture_only": persona.get("fixture_only", False),
        "decision": "approved",
        "reviewer": reviewer,
        "approved_at": timestamp,
        "note": note,
        "human_gate": True,
        "persona_path": str(persona_path),
        "persona_sha256_before_approval": before_sha,
        "persona_sha256_after_approval": after_sha,
        "content_sha256": actual_content_sha,
        "previous_approved_revision": persona.get("revision_lineage", {}).get(
            "previous_approved_revision"
        ),
    }
    if metadata:
        receipt["review_decision_metadata"] = metadata
    write_new_json(receipt_path, receipt)
    return persona, receipt, receipt_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply explicit Human Approval to one immutable Persona revision."
    )
    parser.add_argument("--persona", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--note",
        default="Test Human Approval confirmed the Persona fact authority for fixture-only Production Foundation validation.",
    )
    args = parser.parse_args()
    persona, receipt, receipt_path = approve_persona(
        Path(args.persona), args.reviewer, args.note
    )
    print("PERSONA V1 APPROVAL PASS")
    print(f"Persona ID: {persona['persona_id']}")
    print(f"Revision: {persona['revision']}")
    print("Status: approved")
    print(f"Reviewer: {args.reviewer}")
    print(f"Approved at: {persona['approval']['approved_at']}")
    print(f"Persona SHA-256: {receipt['persona_sha256_after_approval']}")
    print(f"Receipt: {receipt_path}")
    # Machine-readable final line for Console / canonical callers.
    # Keep this as the LAST stdout line.
    print(
        json.dumps(
            {
                "ok": True,
                "persona_id": persona["persona_id"],
                "revision": persona["revision"],
                "status": "approved",
                "reviewer": args.reviewer,
                "approved_at": persona["approval"]["approved_at"],
                "persona_sha256": receipt["persona_sha256_after_approval"],
                "receipt_path": str(receipt_path),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
