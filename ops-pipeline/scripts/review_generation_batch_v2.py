from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_INPUT_SCHEMA = "generation-batch-review-input-v2.0"
REVIEW_SCHEMA = "generation-batch-review-v2.0"
GENERATION_BATCH_SCHEMA = "generation-batch-v1.0"
APPROVED_BATCH_SCHEMA = "approved-generation-batch-v1.0"
REVIEWED_BATCH_SCHEMA = "reviewed-generation-batch-v1.0"
APPROVAL_RECEIPT_SCHEMA = "generation-batch-approval-receipt-v1.0"
APPROVER_VERSION = "review_generation_batch_v2.py@1.0"

VALID_DECISIONS = {
    "approved",
    "revised",
    "rejected",
}

FORBIDDEN_STRENGTHENING = (
    "保证",
    "绝对",
    "一定",
    "必然",
    "永久",
    "彻底",
    "零风险",
    "100%",
    "百分之百",
    "全网",
    "第一",
    "唯一",
    "最便宜",
    "最低价",
    "最好",
    "顶级",
)


class GenerationReviewV2Error(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_ARTIFACT_INVALID",
            f"Cannot read JSON artifact: {path}",
        ) from exc

    if not isinstance(value, dict):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_ARTIFACT_INVALID",
            f"JSON artifact must be an object: {path}",
        )

    return value


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def write_or_validate_json(
    path: Path,
    value: dict[str, Any],
) -> bool:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.is_file():
        existing = read_json(path)
        if canonical_sha256(
            existing
        ) != canonical_sha256(
            value
        ):
            raise GenerationReviewV2Error(
                "GENERATION_REVIEW_V2_ARTIFACT_CONFLICT",
                f"Immutable artifact already differs: {path}",
            )
        return False

    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        existing = read_json(path)
        if canonical_sha256(
            existing
        ) != canonical_sha256(
            value
        ):
            raise GenerationReviewV2Error(
                "GENERATION_REVIEW_V2_ARTIFACT_CONFLICT",
                f"Immutable artifact was concurrently created with different content: {path}",
            ) from exc
        return False

    return True


def _normalize_text(value: Any) -> str:
    return re.sub(
        r"[\W_]+",
        "",
        str(value or "").lower(),
        flags=re.UNICODE,
    )


def _numbers(value: Any) -> set[str]:
    return set(
        re.findall(
            r"\d+(?:\.\d+)?%?",
            str(value or ""),
        )
    )


def _revision_guard(
    *,
    source: dict[str, Any],
    revised_title: str,
    revised_narration: str,
    meaning_preserved: bool,
    new_facts_added: bool,
) -> dict[str, Any]:
    revised_title = str(
        revised_title or ""
    ).strip()
    revised_narration = str(
        revised_narration or ""
    ).strip()

    if not revised_title:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_REVISED_TITLE_REQUIRED",
            "Revised title cannot be empty.",
        )

    if not revised_narration:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_REVISED_NARRATION_REQUIRED",
            "Revised narration cannot be empty.",
        )

    if len(revised_title) > 120:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_REVISED_TITLE_TOO_LONG",
            "Revised title exceeds 120 characters.",
        )

    if len(revised_narration) > 3000:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_REVISED_NARRATION_TOO_LONG",
            "Revised narration exceeds 3000 characters.",
        )

    if meaning_preserved is not True:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_MEANING_PRESERVATION_REQUIRED",
            "Human revision must explicitly confirm meaning_preserved=true.",
        )

    if new_facts_added is not False:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_NEW_FACTS_FORBIDDEN",
            "Human revision cannot add new facts in Revision Workflow V1.",
        )

    source_title = str(
        source.get("title") or ""
    ).strip()
    source_narration = str(
        source.get("narration") or ""
    ).strip()
    central_claim = str(
        source.get("central_claim") or ""
    ).strip()

    if (
        revised_title == source_title
        and revised_narration == source_narration
    ):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_EMPTY_REVISION",
            "Revised decision requires at least one title or narration change.",
        )

    source_text = "\n".join(
        (
            source_title,
            source_narration,
            central_claim,
        )
    )
    revised_text = "\n".join(
        (
            revised_title,
            revised_narration,
        )
    )

    source_numbers = _numbers(
        source_text
    )
    revised_numbers = _numbers(
        revised_text
    )

    new_numbers = sorted(
        revised_numbers
        - source_numbers
    )
    if new_numbers:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_NEW_NUMERIC_FACT",
            (
                "Human revision introduced numeric tokens "
                "not present in the generated semantic envelope: "
                + ", ".join(new_numbers)
            ),
        )

    strengthened = [
        term
        for term in FORBIDDEN_STRENGTHENING
        if (
            term in revised_text
            and term not in source_text
        )
    ]
    if strengthened:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_STRENGTHENED_CLAIM",
            (
                "Human revision introduced strengthening language "
                "not present in the generated source: "
                + ", ".join(strengthened)
            ),
        )

    source_norm = _normalize_text(
        source_text
    )
    revised_norm = _normalize_text(
        revised_text
    )

    similarity = difflib.SequenceMatcher(
        None,
        source_norm,
        revised_norm,
    ).ratio()

    source_chars = set(
        source_norm
    )
    revised_chars = set(
        revised_norm
    )
    character_overlap = (
        len(
            source_chars
            & revised_chars
        )
        / max(
            1,
            len(revised_chars),
        )
    )

    if (
        similarity < 0.22
        and character_overlap < 0.48
    ):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_SEMANTIC_DRIFT_RISK",
            (
                "Human revision differs too far from the generated "
                "semantic envelope for an editorial-only revision. "
                "Return to Customer Truth / Generation instead."
            ),
        )

    return {
        "meaning_preserved": True,
        "new_facts_added": False,
        "new_numeric_tokens": [],
        "strengthening_terms_added": [],
        "source_to_revision_similarity": round(
            similarity,
            6,
        ),
        "revision_character_overlap": round(
            character_overlap,
            6,
        ),
        "central_claim_mutated": False,
        "guard_passed": True,
    }


def _canonical_review_input(
    review_input: dict[str, Any],
    source_ids: list[str],
) -> dict[str, Any]:
    if (
        review_input.get(
            "schema_version"
        )
        != REVIEW_INPUT_SCHEMA
    ):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_INPUT_SCHEMA_INVALID",
            "Human Review input schema is invalid.",
        )

    reviewer = str(
        review_input.get("reviewer")
        or ""
    ).strip()

    if not reviewer:
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_REVIEWER_REQUIRED",
            "Human reviewer is required.",
        )

    items = (
        review_input.get("items")
        or []
    )

    if not isinstance(items, list):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_ITEMS_INVALID",
            "Human Review items must be a list.",
        )

    by_id: dict[
        str,
        dict[str, Any],
    ] = {}

    for item in items:
        if not isinstance(
            item,
            dict,
        ):
            raise GenerationReviewV2Error(
                "GENERATION_REVIEW_V2_ITEM_INVALID",
                "Human Review item must be an object.",
            )

        content_id = str(
            item.get("content_id")
            or ""
        ).strip()

        decision = str(
            item.get("decision")
            or ""
        ).strip()

        if (
            not content_id
            or decision
            not in VALID_DECISIONS
            or content_id in by_id
        ):
            raise GenerationReviewV2Error(
                "GENERATION_REVIEW_V2_ITEM_INVALID",
                "Each generated item requires one unique approved / revised / rejected decision.",
            )

        normalized = {
            "content_id": content_id,
            "decision": decision,
            "note": str(
                item.get("note")
                or ""
            ).strip(),
        }

        if decision == "revised":
            normalized.update(
                {
                    "revised_title": str(
                        item.get(
                            "revised_title"
                        )
                        or ""
                    ).strip(),
                    "revised_narration": str(
                        item.get(
                            "revised_narration"
                        )
                        or ""
                    ).strip(),
                    "meaning_preserved": (
                        item.get(
                            "meaning_preserved"
                        )
                        is True
                    ),
                    "new_facts_added": (
                        item.get(
                            "new_facts_added"
                        )
                        is True
                    ),
                }
            )

        by_id[
            content_id
        ] = normalized

    if set(by_id) != set(
        source_ids
    ):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_INCOMPLETE",
            "Human Review must decide every generated item exactly once.",
        )

    return {
        "schema_version": (
            REVIEW_INPUT_SCHEMA
        ),
        "reviewer": reviewer,
        "note": str(
            review_input.get("note")
            or ""
        ).strip(),
        "items": [
            by_id[
                content_id
            ]
            for content_id in source_ids
        ],
    }


def _review_equivalent(
    existing: dict[str, Any],
    normalized_input: dict[str, Any],
    *,
    request_id: str,
    batch_sha256: str,
) -> bool:
    comparable_existing = {
        "schema_version": (
            REVIEW_INPUT_SCHEMA
        ),
        "reviewer": (
            existing.get(
                "reviewer"
            )
        ),
        "note": (
            existing.get(
                "note"
            )
            or ""
        ),
        "items": (
            existing.get("items")
            or []
        ),
    }

    return (
        existing.get(
            "schema_version"
        )
        == REVIEW_SCHEMA
        and existing.get(
            "request_id"
        )
        == request_id
        and existing.get(
            "batch_sha256"
        )
        == batch_sha256
        and canonical_sha256(
            comparable_existing
        )
        == canonical_sha256(
            normalized_input
        )
    )


def review_generation_batch_v2(
    *,
    batch_path: Path,
    review_input_path: Path,
) -> dict[str, Any]:
    batch_path = (
        batch_path
        .expanduser()
        .resolve()
    )
    review_input_path = (
        review_input_path
        .expanduser()
        .resolve()
    )

    if not batch_path.is_file():
        raise GenerationReviewV2Error(
            "GENERATION_BATCH_NOT_FOUND",
            f"Generation Batch not found: {batch_path}",
        )

    if not review_input_path.is_file():
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_INPUT_NOT_FOUND",
            f"Human Review input not found: {review_input_path}",
        )

    batch = read_json(
        batch_path
    )
    review_input = read_json(
        review_input_path
    )

    if (
        batch.get(
            "schema_version"
        )
        != GENERATION_BATCH_SCHEMA
        or batch.get(
            "status"
        )
        != "review_required"
        or (
            batch.get(
                "validation"
            )
            or {}
        ).get(
            "passed"
        )
        is not True
    ):
        raise GenerationReviewV2Error(
            "GENERATION_BATCH_NOT_REVIEWABLE",
            "Generation Batch is not a machine-passed review_required batch.",
        )

    source_contents = list(
        batch.get(
            "contents"
        )
        or []
    )

    if not source_contents:
        raise GenerationReviewV2Error(
            "GENERATION_BATCH_EMPTY",
            "Generation Batch contains no reviewable content.",
        )

    source_ids = [
        str(
            item.get(
                "content_id"
            )
            or ""
        )
        for item in source_contents
    ]

    if (
        any(
            not content_id
            for content_id in source_ids
        )
        or len(
            set(source_ids)
        )
        != len(
            source_ids
        )
    ):
        raise GenerationReviewV2Error(
            "GENERATION_BATCH_CONTENT_ID_INVALID",
            "Generation Batch content IDs are missing or duplicated.",
        )

    normalized_input = (
        _canonical_review_input(
            review_input,
            source_ids,
        )
    )

    request_id = str(
        batch.get(
            "request_id"
        )
        or ""
    ).strip()

    if not request_id:
        raise GenerationReviewV2Error(
            "GENERATION_BATCH_REQUEST_ID_REQUIRED",
            "Generation Batch request_id is required.",
        )

    batch_sha = sha256_file(
        batch_path
    )

    root = batch_path.parent
    canonical_review_path = (
        root
        / "generation_human_review_v2.json"
    )

    if canonical_review_path.is_file():
        canonical_review = read_json(
            canonical_review_path
        )
        if not _review_equivalent(
            canonical_review,
            normalized_input,
            request_id=request_id,
            batch_sha256=batch_sha,
        ):
            raise GenerationReviewV2Error(
                "GENERATION_REVIEW_V2_CONFLICT",
                "A different immutable Human Review V2 already exists for this Generation Batch.",
            )
        recovered_review = True
        reviewed_at = str(
            canonical_review.get(
                "reviewed_at"
            )
            or ""
        )
    else:
        reviewed_at = now_iso()
        canonical_review = {
            "schema_version": (
                REVIEW_SCHEMA
            ),
            "request_id": request_id,
            "batch_sha256": (
                batch_sha
            ),
            "reviewer": (
                normalized_input[
                    "reviewer"
                ]
            ),
            "reviewed_at": (
                reviewed_at
            ),
            "decision": (
                "review_items"
            ),
            "note": (
                normalized_input[
                    "note"
                ]
            ),
            "items": (
                normalized_input[
                    "items"
                ]
            ),
            "authority": {
                "generated_candidate_mutated": False,
                "central_claim_edit_allowed": False,
                "new_customer_fact_allowed": False,
                "human_revision_is_editorial_projection_only": True,
                "remote_model_called": False,
            },
        }

        write_or_validate_json(
            canonical_review_path,
            canonical_review,
        )
        recovered_review = False

    source_by_id = {
        str(
            item["content_id"]
        ): item
        for item in source_contents
    }

    approved_contents: list[
        dict[str, Any]
    ] = []
    rejected_items: list[
        dict[str, Any]
    ] = []

    original_approved_count = 0
    revised_approved_count = 0
    rejected_count = 0

    for review_item in (
        canonical_review.get(
            "items"
        )
        or []
    ):
        content_id = str(
            review_item[
                "content_id"
            ]
        )
        decision = str(
            review_item[
                "decision"
            ]
        )
        source = source_by_id[
            content_id
        ]

        if decision == "rejected":
            rejected_count += 1
            rejected_items.append(
                {
                    "content_id": content_id,
                    "decision": (
                        "rejected"
                    ),
                    "reviewer": (
                        canonical_review[
                            "reviewer"
                        ]
                    ),
                    "reviewed_at": (
                        reviewed_at
                    ),
                    "note": (
                        review_item.get(
                            "note"
                        )
                        or ""
                    ),
                    "source_title": (
                        source.get(
                            "title"
                        )
                    ),
                    "source_narration": (
                        source.get(
                            "narration"
                        )
                    ),
                }
            )
            continue

        reviewed = json.loads(
            json.dumps(
                source,
                ensure_ascii=False,
            )
        )

        human_review = {
            "reviewer": (
                canonical_review[
                    "reviewer"
                ]
            ),
            "reviewed_at": (
                reviewed_at
            ),
            "note": (
                review_item.get(
                    "note"
                )
                or ""
            ),
        }

        if decision == "approved":
            original_approved_count += 1
            human_review[
                "decision"
            ] = "approved"
            reviewed[
                "status"
            ] = "human_approved"
            reviewed[
                "human_review"
            ] = human_review
            reviewed[
                "human_revision"
            ] = None

        elif decision == "revised":
            guard = _revision_guard(
                source=source,
                revised_title=str(
                    review_item.get(
                        "revised_title"
                    )
                    or ""
                ),
                revised_narration=str(
                    review_item.get(
                        "revised_narration"
                    )
                    or ""
                ),
                meaning_preserved=(
                    review_item.get(
                        "meaning_preserved"
                    )
                    is True
                ),
                new_facts_added=(
                    review_item.get(
                        "new_facts_added"
                    )
                    is True
                ),
            )

            revised_approved_count += 1
            source_title = str(
                source.get(
                    "title"
                )
                or ""
            )
            source_narration = str(
                source.get(
                    "narration"
                )
                or ""
            )
            revised_title = str(
                review_item[
                    "revised_title"
                ]
            )
            revised_narration = str(
                review_item[
                    "revised_narration"
                ]
            )

            reviewed[
                "title"
            ] = revised_title
            reviewed[
                "narration"
            ] = revised_narration
            reviewed[
                "status"
            ] = "human_approved"

            human_review[
                "decision"
            ] = "revised_and_approved"
            reviewed[
                "human_review"
            ] = human_review
            reviewed[
                "human_revision"
            ] = {
                "revision_number": 1,
                "revision_type": (
                    "human_editorial_projection"
                ),
                "source_title": (
                    source_title
                ),
                "source_narration": (
                    source_narration
                ),
                "revised_title": (
                    revised_title
                ),
                "revised_narration": (
                    revised_narration
                ),
                "source_text_sha256": (
                    canonical_sha256(
                        {
                            "title": (
                                source_title
                            ),
                            "narration": (
                                source_narration
                            ),
                            "central_claim": (
                                source.get(
                                    "central_claim"
                                )
                            ),
                        }
                    )
                ),
                "revised_text_sha256": (
                    canonical_sha256(
                        {
                            "title": (
                                revised_title
                            ),
                            "narration": (
                                revised_narration
                            ),
                            "central_claim": (
                                source.get(
                                    "central_claim"
                                )
                            ),
                        }
                    )
                ),
                "fields_changed": [
                    field
                    for field, changed in (
                        (
                            "title",
                            revised_title
                            != source_title,
                        ),
                        (
                            "narration",
                            revised_narration
                            != source_narration,
                        ),
                    )
                    if changed
                ],
                "central_claim": (
                    source.get(
                        "central_claim"
                    )
                ),
                "guard": guard,
            }

        else:
            raise GenerationReviewV2Error(
                "GENERATION_REVIEW_V2_DECISION_INVALID",
                f"Unsupported Human Review decision: {decision}",
            )

        approved_contents.append(
            reviewed
        )

    approved_count = (
        original_approved_count
        + revised_approved_count
    )

    if (
        approved_count
        + rejected_count
        != len(
            source_contents
        )
    ):
        raise GenerationReviewV2Error(
            "GENERATION_REVIEW_V2_COUNT_MISMATCH",
            "Human Review item counts do not match the Generation Batch.",
        )

    human_review_summary = {
        "decision": (
            "review_items"
        ),
        "reviewer": (
            canonical_review[
                "reviewer"
            ]
        ),
        "reviewed_at": (
            reviewed_at
        ),
        "note": (
            canonical_review.get(
                "note"
            )
            or ""
        ),
        "source_generated_item_count": (
            len(
                source_contents
            )
        ),
        "approved_item_count": (
            approved_count
        ),
        "approved_without_revision_count": (
            original_approved_count
        ),
        "revised_and_approved_count": (
            revised_approved_count
        ),
        "rejected_item_count": (
            rejected_count
        ),
        "all_source_items_approved": (
            rejected_count == 0
        ),
        "all_export_items_human_approved": (
            approved_count > 0
        ),
        "partial_source_batch_approval": (
            approved_count > 0
            and rejected_count > 0
        ),
    }

    base = json.loads(
        json.dumps(
            batch,
            ensure_ascii=False,
        )
    )

    base[
        "lineage"
    ] = dict(
        batch.get(
            "lineage"
        )
        or {}
    )
    base[
        "lineage"
    ][
        "source_generation_batch"
    ] = {
        "path": str(
            batch_path
        ),
        "sha256": (
            batch_sha
        ),
    }
    base[
        "lineage"
    ][
        "human_review_v2"
    ] = {
        "path": str(
            canonical_review_path
        ),
        "sha256": (
            sha256_file(
                canonical_review_path
            )
        ),
    }

    base[
        "human_review"
    ] = (
        human_review_summary
    )
    base[
        "reviewed_source_content_ids"
    ] = (
        source_ids
    )
    base[
        "rejected_items"
    ] = (
        rejected_items
    )

    base[
        "authority"
    ] = dict(
        batch.get(
            "authority"
        )
        or {}
    )
    base[
        "authority"
    ].update(
        {
            "human_review_completed": True,
            "generated_candidate_mutated": False,
            "human_revision_is_projection": True,
            "new_customer_fact_created": False,
            "central_claim_mutated": False,
            "auto_approved": False,
            "remote_model_called_during_review": False,
        }
    )

    approval_receipt_path = (
        root
        / "generation_batch_approval_receipt.json"
    )

    if approved_count > 0:
        output_path = (
            root
            / "approved_generation_batch_v1.json"
        )
        base[
            "schema_version"
        ] = APPROVED_BATCH_SCHEMA
        base[
            "status"
        ] = "approved"
        base[
            "contents"
        ] = (
            approved_contents
        )
        base[
            "approved_export_count"
        ] = (
            approved_count
        )
        base[
            "authority"
        ][
            "export_allowed"
        ] = True

        approved_sha = (
            canonical_sha256(
                base
            )
        )
        write_or_validate_json(
            output_path,
            base,
        )
        actual_approved_sha = (
            sha256_file(
                output_path
            )
        )

        receipt = {
            "schema_version": (
                APPROVAL_RECEIPT_SCHEMA
            ),
            "request_id": (
                request_id
            ),
            "decision": (
                "review_items"
            ),
            "status": "approved",
            "reviewer": (
                canonical_review[
                    "reviewer"
                ]
            ),
            "reviewed_at": (
                reviewed_at
            ),
            "source_batch": {
                "path": str(
                    batch_path
                ),
                "sha256": (
                    batch_sha
                ),
            },
            "review_file": {
                "path": str(
                    canonical_review_path
                ),
                "sha256": (
                    sha256_file(
                        canonical_review_path
                    )
                ),
            },
            "reviewed_batch": {
                "path": str(
                    output_path
                ),
                "sha256": (
                    actual_approved_sha
                ),
            },
            "approved_batch": {
                "path": str(
                    output_path
                ),
                "sha256": (
                    actual_approved_sha
                ),
            },
            "approved_item_count": (
                approved_count
            ),
            "revised_and_approved_count": (
                revised_approved_count
            ),
            "rejected_item_count": (
                rejected_count
            ),
            "human_gate": True,
            "approver_version": (
                APPROVER_VERSION
            ),
        }

        write_or_validate_json(
            approval_receipt_path,
            receipt,
        )
        final_status = "approved"

    else:
        output_path = (
            root
            / "reviewed_generation_batch_v1.json"
        )
        base[
            "schema_version"
        ] = REVIEWED_BATCH_SCHEMA
        base[
            "status"
        ] = "rejected"
        base[
            "contents"
        ] = [
            {
                **json.loads(
                    json.dumps(
                        source,
                        ensure_ascii=False,
                    )
                ),
                "status": (
                    "human_rejected"
                ),
                "human_review": {
                    "decision": (
                        "rejected"
                    ),
                    "reviewer": (
                        canonical_review[
                            "reviewer"
                        ]
                    ),
                    "reviewed_at": (
                        reviewed_at
                    ),
                    "note": next(
                        (
                            item.get(
                                "note"
                            )
                            or ""
                            for item in (
                                canonical_review.get(
                                    "items"
                                )
                                or []
                            )
                            if item.get(
                                "content_id"
                            )
                            == source.get(
                                "content_id"
                            )
                        ),
                        "",
                    ),
                },
            }
            for source in (
                source_contents
            )
        ]
        base[
            "authority"
        ][
            "export_allowed"
        ] = False

        write_or_validate_json(
            output_path,
            base,
        )
        reviewed_sha = (
            sha256_file(
                output_path
            )
        )

        receipt = {
            "schema_version": (
                APPROVAL_RECEIPT_SCHEMA
            ),
            "request_id": (
                request_id
            ),
            "decision": (
                "review_items"
            ),
            "status": "rejected",
            "reviewer": (
                canonical_review[
                    "reviewer"
                ]
            ),
            "reviewed_at": (
                reviewed_at
            ),
            "source_batch": {
                "path": str(
                    batch_path
                ),
                "sha256": (
                    batch_sha
                ),
            },
            "review_file": {
                "path": str(
                    canonical_review_path
                ),
                "sha256": (
                    sha256_file(
                        canonical_review_path
                    )
                ),
            },
            "reviewed_batch": {
                "path": str(
                    output_path
                ),
                "sha256": (
                    reviewed_sha
                ),
            },
            "approved_item_count": 0,
            "revised_and_approved_count": 0,
            "rejected_item_count": (
                rejected_count
            ),
            "human_gate": True,
            "approver_version": (
                APPROVER_VERSION
            ),
        }

        write_or_validate_json(
            approval_receipt_path,
            receipt,
        )
        final_status = "rejected"

    return {
        "ok": True,
        "request_id": (
            request_id
        ),
        "status": (
            final_status
        ),
        "review_path": str(
            canonical_review_path
        ),
        "review_sha256": (
            sha256_file(
                canonical_review_path
            )
        ),
        "output_path": str(
            output_path
        ),
        "output_sha256": (
            sha256_file(
                output_path
            )
        ),
        "receipt_path": str(
            approval_receipt_path
        ),
        "receipt_sha256": (
            sha256_file(
                approval_receipt_path
            )
        ),
        "approved_item_count": (
            approved_count
        ),
        "revised_and_approved_count": (
            revised_approved_count
        ),
        "rejected_item_count": (
            rejected_count
        ),
        "partial_source_batch_approval": (
            approved_count > 0
            and rejected_count > 0
        ),
        "generated_candidate_mutated": False,
        "content_ledger_written": False,
        "excel_exported": False,
        "remote_model_called": False,
        "recovered": (
            recovered_review
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply Unified Human Review V2 to one immutable Generation Batch."
        )
    )
    parser.add_argument(
        "--batch",
        required=True,
    )
    parser.add_argument(
        "--review-file",
        required=True,
    )
    args = parser.parse_args()

    try:
        result = (
            review_generation_batch_v2(
                batch_path=Path(
                    args.batch
                ),
                review_input_path=Path(
                    args.review_file
                ),
            )
        )
    except GenerationReviewV2Error as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": (
                        exc.code
                    ),
                    "message": str(
                        exc
                    ),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(
            2
        ) from exc

    print(
        json.dumps(
            result,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
