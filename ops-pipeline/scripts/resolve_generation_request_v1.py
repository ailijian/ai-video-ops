from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generation_request_effective_lifecycle_v1 import (
    RESOLUTION_SCHEMA_VERSION,
    EffectiveLifecycleError,
    classify_request,
    read_json,
    sha256_file,
)


ALLOWED_DISPOSITIONS = {
    "abandoned",
    "cancelled",
}


class ResolutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def canonical_sha256(
    value: Any,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        payload
    ).hexdigest()


def write_new_json(
    path: Path,
    value: dict[str, Any],
) -> bool:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.is_file():
        existing = read_json(path)

        if (
            canonical_sha256(
                existing
            )
            != canonical_sha256(
                value
            )
        ):
            raise ResolutionError(
                "GENERATION_REQUEST_RESOLUTION_CONFLICT",
                (
                    "Immutable Generation Request "
                    "Resolution already exists "
                    "with different content."
                ),
            )

        return False

    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )

    try:
        with path.open(
            "x",
            encoding="utf-8",
        ) as handle:
            handle.write(
                payload
            )
    except FileExistsError as exc:
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_CONFLICT",
            (
                "Generation Request Resolution "
                "was created concurrently."
            ),
        ) from exc

    return True


def resolve_generation_request(
    *,
    pipeline_root: Path,
    request_id: str,
    disposition: str,
    reviewer: str,
    reason: str,
    human_approved: bool,
    superseded_by_request_id: str | None = None,
) -> dict[str, Any]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )

    request_id = str(
        request_id or ""
    ).strip()

    disposition = str(
        disposition or ""
    ).strip().lower()

    reviewer = str(
        reviewer or ""
    ).strip()

    reason = str(
        reason or ""
    ).strip()

    if not human_approved:
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_HUMAN_APPROVAL_REQUIRED",
            (
                "Explicit --human-approved "
                "is required."
            ),
        )

    if (
        disposition
        not in ALLOWED_DISPOSITIONS
    ):
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_DISPOSITION_INVALID",
            (
                "disposition must be "
                "abandoned or cancelled."
            ),
        )

    if not reviewer:
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_REVIEWER_REQUIRED",
            "reviewer is required.",
        )

    if not reason:
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_REASON_REQUIRED",
            "reason is required.",
        )

    request_path = (
        pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )

    if not request_path.is_file():
        raise ResolutionError(
            "GENERATION_REQUEST_NOT_FOUND",
            (
                "Generation Request "
                f"does not exist: {request_id}"
            ),
        )

    before = classify_request(
        pipeline_root=pipeline_root,
        request_path=request_path,
    )

    if before.get(
        "effective_terminal"
    ) is True:
        raise ResolutionError(
            "GENERATION_REQUEST_ALREADY_TERMINAL",
            (
                "Generation Request is already "
                "effectively terminal."
            ),
        )

    if before.get(
        "blockers"
    ):
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_BLOCKED",
            (
                "Generation Request has unresolved "
                "Authority blockers and cannot be "
                "human-terminalized safely."
            ),
        )

    superseded_ref = None

    if superseded_by_request_id:
        superseded_by_request_id = str(
            superseded_by_request_id
        ).strip()

        replacement_path = (
            pipeline_root
            / "data"
            / "generation_requests"
            / superseded_by_request_id
            / "generation_request_v1.json"
        )

        if not replacement_path.is_file():
            raise ResolutionError(
                "GENERATION_REQUEST_SUPERSEDING_REQUEST_NOT_FOUND",
                (
                    "Superseding Generation Request "
                    "does not exist."
                ),
            )

        replacement = (
            classify_request(
                pipeline_root=pipeline_root,
                request_path=replacement_path,
            )
        )

        if (
            replacement.get(
                "business_id"
            )
            != before.get(
                "business_id"
            )
            or replacement.get(
                "profile"
            )
            != before.get(
                "profile"
            )
        ):
            raise ResolutionError(
                "GENERATION_REQUEST_SUPERSEDING_LINEAGE_MISMATCH",
                (
                    "Superseding Request must belong "
                    "to the same business and profile."
                ),
            )

        if (
            replacement.get(
                "effective_terminal"
            )
            is not True
            or replacement.get(
                "effective_status"
            )
            != "exported"
        ):
            raise ResolutionError(
                "GENERATION_REQUEST_SUPERSEDING_REQUEST_NOT_EXPORTED",
                (
                    "Superseding Request must already "
                    "resolve to a validated export."
                ),
            )

        superseded_ref = {
            "request_id": (
                superseded_by_request_id
            ),
            "request_path": str(
                replacement_path.resolve()
            ),
            "request_sha256": (
                sha256_file(
                    replacement_path
                )
            ),
            "effective_status": (
                replacement[
                    "effective_status"
                ]
            ),
            "terminal_reason": (
                replacement[
                    "terminal_reason"
                ]
            ),
        }

    reviewed_at = now_iso()

    resolution = {
        "schema_version": (
            RESOLUTION_SCHEMA_VERSION
        ),
        "request_id": request_id,
        "business_id": (
            before[
                "business_id"
            ]
        ),
        "profile": (
            before[
                "profile"
            ]
        ),
        "disposition": disposition,
        "reviewer": reviewer,
        "reviewed_at": (
            reviewed_at
        ),
        "reason": reason,
        "human_gate": True,
        "request_ref": {
            "path": str(
                request_path.resolve()
            ),
            "sha256": (
                sha256_file(
                    request_path
                )
            ),
        },
        "prior_effective_state": {
            "effective_status": (
                before[
                    "effective_status"
                ]
            ),
            "effective_stage": (
                before[
                    "effective_stage"
                ]
            ),
            "effective_terminal": (
                before[
                    "effective_terminal"
                ]
            ),
        },
        "superseded_by": (
            superseded_ref
        ),
        "authority": {
            "request_mutated": False,
            "generation_batch_mutated": False,
            "content_ledger_mutated": False,
            "semantic_content_created": False,
            "remote_model_called": False,
        },
    }

    resolution_path = (
        request_path.parent
        / "generation_request_resolution_v1.json"
    )

    created = write_new_json(
        resolution_path,
        resolution,
    )

    after = classify_request(
        pipeline_root=pipeline_root,
        request_path=request_path,
    )

    if (
        after.get(
            "effective_terminal"
        )
        is not True
        or after.get(
            "effective_status"
        )
        != disposition
        or after.get(
            "terminal_reason"
        )
        != "human_resolution_sidecar"
    ):
        raise ResolutionError(
            "GENERATION_REQUEST_RESOLUTION_VALIDATION_FAILED",
            (
                "Resolution artifact was written "
                "but Effective Lifecycle did not "
                "resolve to the expected terminal state."
            ),
        )

    return {
        "request_id": request_id,
        "created": created,
        "resolution_path": str(
            resolution_path.resolve()
        ),
        "resolution_sha256": (
            sha256_file(
                resolution_path
            )
        ),
        "request_sha256_before": (
            resolution[
                "request_ref"
            ][
                "sha256"
            ]
        ),
        "request_sha256_after": (
            sha256_file(
                request_path
            )
        ),
        "effective_status": (
            after[
                "effective_status"
            ]
        ),
        "effective_terminal": (
            after[
                "effective_terminal"
            ]
        ),
        "terminal_reason": (
            after[
                "terminal_reason"
            ]
        ),
        "remote_model_called": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Human-approved immutable sidecar "
            "resolution for one Generation Request."
        )
    )

    parser.add_argument(
        "--pipeline-root",
        default=str(
            Path(__file__)
            .resolve()
            .parents[1]
        ),
    )

    parser.add_argument(
        "--request-id",
        required=True,
    )

    parser.add_argument(
        "--disposition",
        required=True,
        choices=(
            "abandoned",
            "cancelled",
        ),
    )

    parser.add_argument(
        "--reviewer",
        required=True,
    )

    parser.add_argument(
        "--reason",
        required=True,
    )

    parser.add_argument(
        "--superseded-by-request-id",
    )

    parser.add_argument(
        "--human-approved",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        result = (
            resolve_generation_request(
                pipeline_root=Path(
                    args.pipeline_root
                ),
                request_id=(
                    args.request_id
                ),
                disposition=(
                    args.disposition
                ),
                reviewer=(
                    args.reviewer
                ),
                reason=(
                    args.reason
                ),
                human_approved=(
                    args.human_approved
                ),
                superseded_by_request_id=(
                    args.superseded_by_request_id
                ),
            )
        )

    except (
        ResolutionError,
        EffectiveLifecycleError,
    ) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": getattr(
                        exc,
                        "code",
                        "GENERATION_REQUEST_RESOLUTION_FAILED",
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
            {
                "ok": True,
                "result": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
