from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from privacy_projection_v1 import validate_case_privacy_gate


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_atomic_json(path: Path, data: dict[str, Any]) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(payload)
    temp_path.replace(path)

    return sha256_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Explicitly approve a reviewed Canonical Case V1. "
            "This is a human gate; the script never auto-approves."
        )
    )
    parser.add_argument(
        "--case",
        required=True,
        help="Path to case_v1.json",
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Human reviewer name/identifier",
    )
    parser.add_argument(
        "--note",
        default="Human review passed against the source video and Reverse Storyboard V1.1.",
    )
    args = parser.parse_args()

    case_path = Path(args.case).expanduser().resolve()
    if not case_path.exists():
        raise FileNotFoundError(case_path)

    original_bytes = case_path.read_bytes()
    original_sha256 = sha256_bytes(original_bytes)
    case = json.loads(original_bytes.decode("utf-8"))

    errors: list[str] = []

    lifecycle = case.get("lifecycle", {})
    validation = case.get("validation", {})
    visual = case.get("visual_evidence", {})
    storyboard = case.get("storyboard", {})
    quality = case.get("quality", {})

    if lifecycle.get("status") != "review_required":
        errors.append(
            f"Expected lifecycle.status='review_required', got {lifecycle.get('status')!r}"
        )

    if lifecycle.get("approved") is True:
        errors.append("Case is already approved.")

    if validation.get("passed") is not True:
        errors.append("Case validation.passed is not true.")

    try:
        validate_case_privacy_gate(case)
    except RuntimeError as exc:
        errors.append(str(exc))

    if visual.get("coverage_label") != "candidate_complete":
        errors.append(
            "Visual coverage is not candidate_complete."
        )

    shots = storyboard.get("shots") or []
    if not shots:
        errors.append("Storyboard contains no shots.")

    if quality.get("human_review_required") is not True:
        errors.append(
            "Case does not declare human_review_required=true."
        )

    if errors:
        print("\nCASE APPROVAL BLOCKED")
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(2)

    approved_at = now_iso()

    lifecycle["status"] = "approved"
    lifecycle["approved"] = True
    lifecycle["approved_at"] = approved_at
    lifecycle["approved_by"] = args.reviewer
    lifecycle["approval_note"] = args.note

    case["lifecycle"] = lifecycle

    case["approval"] = {
        "decision": "approved",
        "reviewer": args.reviewer,
        "approved_at": approved_at,
        "note": args.note,
        "review_basis": [
            "source_video",
            "reverse_storyboard_v1_1",
            "audio_evidence",
            "visual_evidence",
            "shot_roles",
            "proof_boundary",
        ],
        "human_gate": True,
    }

    case.setdefault("quality", {})
    case["quality"]["human_review_required"] = False
    case["quality"]["human_review_completed"] = True

    case.setdefault("validation", {})
    case["validation"]["human_approval_completed"] = True
    case["validation"]["auto_approved"] = False

    approved_sha256 = write_atomic_json(
        case_path,
        case,
    )

    receipt = {
        "case_id": case.get("case_id"),
        "decision": "approved",
        "reviewer": args.reviewer,
        "approved_at": approved_at,
        "note": args.note,
        "human_gate": True,
        "case_path": str(case_path),
        "case_sha256_before_approval": original_sha256,
        "case_sha256_after_approval": approved_sha256,
    }

    receipt_path = case_path.parent / "approval_receipt.json"
    write_atomic_json(receipt_path, receipt)

    print()
    print("CASE APPROVAL PASS")
    print(f"Case ID: {case.get('case_id')}")
    print("Status: approved")
    print("Approved: True")
    print(f"Reviewer: {args.reviewer}")
    print(f"Approved at: {approved_at}")
    print(f"Case: {case_path}")
    print(f"Receipt: {receipt_path}")


if __name__ == "__main__":
    main()
