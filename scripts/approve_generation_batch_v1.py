from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APPROVER_VERSION = "approve_generation_batch_v1.py@0.1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def approve_generation_batch(
    batch_path: Path,
    review_path: Path,
    approved_at: str | None = None,
) -> tuple[Path, Path, dict[str, Any], dict[str, Any]]:
    batch_path = batch_path.expanduser().resolve()
    review_path = review_path.expanduser().resolve()
    if not batch_path.is_file():
        raise FileNotFoundError(batch_path)
    if not review_path.is_file():
        raise FileNotFoundError(review_path)
    batch = read_json(batch_path)
    review = read_json(review_path)
    batch_sha = sha256_file(batch_path)
    if batch.get("status") != "review_required":
        raise RuntimeError("Generation Batch must be review_required.")
    if batch.get("validation", {}).get("passed") is not True:
        raise RuntimeError("Generation Batch machine validation is not passed.")
    if review.get("schema_version") != "generation-batch-review-v1.0":
        raise RuntimeError("Human Review file schema is invalid.")
    if review.get("batch_sha256") != batch_sha:
        raise RuntimeError("Human Review file Batch SHA mismatch.")
    if review.get("request_id") != batch.get("request_id"):
        raise RuntimeError("Human Review request_id mismatch.")
    reviewer = str(review.get("reviewer") or "").strip()
    if not reviewer:
        raise RuntimeError("Human reviewer is required.")
    decision = review.get("decision")
    if decision not in {"approve_items", "reject_batch"}:
        raise RuntimeError("Human Review decision is invalid.")

    source_items = {item["content_id"]: item for item in batch.get("contents", [])}
    review_items = review.get("items") or []
    review_by_id = {str(item.get("content_id")): item for item in review_items}
    if decision == "approve_items" and set(review_by_id) != set(source_items):
        raise RuntimeError("Human Review must decide every generated item exactly once.")
    if decision == "reject_batch" and review_items and set(review_by_id) != set(source_items):
        raise RuntimeError("Detailed rejected Batch Review must cover every item exactly once.")
    if len(review_by_id) != len(review_items):
        raise RuntimeError("Human Review contains duplicate content IDs.")
    timestamp = approved_at or now_iso()
    reviewed_contents: list[dict[str, Any]] = []
    approved_count = 0
    rejected_count = 0
    finding_counts: dict[str, int] = {}
    for content_id, source_item in source_items.items():
        if decision == "reject_batch":
            item_decision = review_by_id.get(content_id, {}).get(
                "decision", "rejected"
            )
            if item_decision == "reject":
                item_decision = "rejected"
            if item_decision not in {"keep", "revision_required", "rejected"}:
                raise RuntimeError(f"Invalid rejected Batch finding for {content_id}.")
            item_status = {
                "keep": "human_keep_for_revision",
                "revision_required": "human_revision_required",
                "rejected": "human_rejected",
            }[item_decision]
        else:
            item_decision = review_by_id[content_id].get("decision")
            if item_decision not in {"approved", "rejected"}:
                raise RuntimeError(f"Invalid Human Review decision for {content_id}.")
            item_status = (
                "human_approved" if item_decision == "approved" else "human_rejected"
            )
        finding_counts[item_decision] = finding_counts.get(item_decision, 0) + 1
        reviewed = dict(source_item)
        reviewed["status"] = item_status
        reviewed["human_review"] = {
            "decision": item_decision,
            "reviewer": reviewer,
            "reviewed_at": timestamp,
            "note": (
                review_by_id.get(content_id, {}).get("note") or review.get("note")
            ),
        }
        reviewed_contents.append(reviewed)
        if decision != "reject_batch" and item_decision == "approved":
            approved_count += 1
        else:
            rejected_count += 1

    if decision == "reject_batch":
        status = "rejected"
    elif approved_count == len(source_items) and approved_count == batch.get("requested_quantity"):
        status = "approved"
    else:
        status = "partially_approved"
    approved_batch = dict(batch)
    approved_batch["schema_version"] = (
        "approved-generation-batch-v1.0"
        if status == "approved"
        else "reviewed-generation-batch-v1.0"
    )
    approved_batch["status"] = status
    approved_batch["contents"] = reviewed_contents
    approved_batch["human_review"] = {
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": timestamp,
        "note": review.get("note"),
        "approved_item_count": approved_count,
        "rejected_item_count": rejected_count,
        "all_export_items_human_approved": status == "approved",
        "finding_counts": dict(sorted(finding_counts.items())),
    }
    approved_batch["lineage"] = dict(batch.get("lineage", {}))
    approved_batch["lineage"]["source_generation_batch"] = {
        "path": str(batch_path),
        "sha256": batch_sha,
    }
    approved_batch["lineage"]["human_review_file"] = {
        "path": str(review_path),
        "sha256": sha256_file(review_path),
    }
    approved_batch["authority"] = dict(batch.get("authority", {}))
    approved_batch["authority"].update(
        {
            "human_review_completed": True,
            "export_allowed": status == "approved",
            "auto_approved": False,
        }
    )

    output_path = batch_path.parent / (
        "approved_generation_batch_v1.json"
        if status == "approved"
        else "reviewed_generation_batch_v1.json"
    )
    receipt_path = batch_path.parent / "generation_batch_approval_receipt.json"
    if output_path.exists() or receipt_path.exists():
        raise RuntimeError("Approved Generation Batch already exists and cannot be overwritten.")
    approved_sha = write_new_json(output_path, approved_batch)
    receipt = {
        "schema_version": "generation-batch-approval-receipt-v1.0",
        "request_id": batch.get("request_id"),
        "decision": decision,
        "status": status,
        "reviewer": reviewer,
        "reviewed_at": timestamp,
        "source_batch": {"path": str(batch_path), "sha256": batch_sha},
        "review_file": {"path": str(review_path), "sha256": sha256_file(review_path)},
        "reviewed_batch": {"path": str(output_path), "sha256": approved_sha},
        "approved_item_count": approved_count,
        "rejected_item_count": rejected_count,
        "human_gate": True,
        "approver_version": APPROVER_VERSION,
    }
    if status == "approved":
        receipt["approved_batch"] = receipt["reviewed_batch"]
    write_new_json(receipt_path, receipt)
    return output_path, receipt_path, approved_batch, receipt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply explicit Human Review decisions to a Generation Batch."
    )
    parser.add_argument("--batch", required=True)
    parser.add_argument("--review-file", required=True)
    args = parser.parse_args()
    output_path, receipt_path, approved_batch, _receipt = approve_generation_batch(
        Path(args.batch), Path(args.review_file)
    )
    print("GENERATION BATCH HUMAN REVIEW PASS")
    print(f"Request: {approved_batch['request_id']}")
    print(f"Status: {approved_batch['status']}")
    print(f"Approved items: {approved_batch['human_review']['approved_item_count']}")
    print(f"Rejected items: {approved_batch['human_review']['rejected_item_count']}")
    print(f"Reviewed Batch: {output_path}")
    print(f"Receipt: {receipt_path}")


if __name__ == "__main__":
    main()
