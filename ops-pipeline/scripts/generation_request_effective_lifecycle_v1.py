from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REQUEST_SCHEMA_VERSION = "generation-request-v1.0"
RESOLUTION_SCHEMA_VERSION = "generation-request-resolution-v1.0"

DIRECT_TERMINAL_STATUSES = {
    "completed",
    "exported",
    "cancelled",
    "abandoned",
}

SIDE_CAR_TERMINAL_DISPOSITIONS = {
    "cancelled",
    "abandoned",
}

MIX_EXPORT_RECEIPT_SCHEMA = "mix-excel-export-receipt-v1.0"
APPROVED_BATCH_SCHEMA = "approved-generation-batch-v1.0"
APPROVAL_RECEIPT_SCHEMA = "generation-batch-approval-receipt-v1.0"


class EffectiveLifecycleError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise EffectiveLifecycleError(
            "GENERATION_EFFECTIVE_LIFECYCLE_ARTIFACT_INVALID",
            f"Cannot read JSON artifact: {path}",
        ) from exc

    if not isinstance(value, dict):
        raise EffectiveLifecycleError(
            "GENERATION_EFFECTIVE_LIFECYCLE_ARTIFACT_INVALID",
            f"JSON artifact must be an object: {path}",
        )

    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def evidence_ref(
    pipeline_root: Path,
    path: Path,
) -> str:
    try:
        return (
            path.resolve()
            .relative_to(
                pipeline_root.resolve()
            )
            .as_posix()
        )
    except ValueError:
        return str(path.resolve())


def resolve_recorded_path(
    pipeline_root: Path,
    raw: Any,
) -> Path:
    text = str(raw or "").strip()

    if not text:
        raise EffectiveLifecycleError(
            "GENERATION_EFFECTIVE_LIFECYCLE_PATH_MISSING",
            "Recorded artifact path is empty.",
        )

    direct = Path(text).expanduser()

    if direct.is_file():
        return direct.resolve()

    normalized = text.replace(
        "\\",
        "/",
    )

    marker = "/ops-pipeline/"

    if marker in normalized.lower():
        lower = normalized.lower()
        index = lower.index(marker)
        relative = normalized[
            index + len(marker):
        ]

        candidate = (
            pipeline_root
            / Path(relative)
        )

        if candidate.is_file():
            return candidate.resolve()

    candidate = (
        pipeline_root
        / Path(normalized)
    )

    if candidate.is_file():
        return candidate.resolve()

    raise EffectiveLifecycleError(
        "GENERATION_EFFECTIVE_LIFECYCLE_PATH_NOT_FOUND",
        f"Recorded artifact cannot be resolved: {text}",
    )


def _request_resolution_path(
    request_path: Path,
) -> Path:
    return (
        request_path.parent
        / "generation_request_resolution_v1.json"
    )


def _validate_resolution_sidecar(
    *,
    pipeline_root: Path,
    request_path: Path,
    request: dict[str, Any],
) -> dict[str, Any] | None:
    path = _request_resolution_path(
        request_path
    )

    if not path.is_file():
        return None

    value = read_json(path)

    request_ref = (
        value.get("request_ref")
        or {}
    )

    disposition = str(
        value.get("disposition")
        or ""
    )

    if (
        value.get("schema_version")
        != RESOLUTION_SCHEMA_VERSION
        or value.get("request_id")
        != request.get("request_id")
        or value.get("business_id")
        != request.get("persona_id")
        or disposition
        not in SIDE_CAR_TERMINAL_DISPOSITIONS
        or value.get("human_gate")
        is not True
        or not str(
            value.get("reviewer")
            or ""
        ).strip()
        or not str(
            value.get("reason")
            or ""
        ).strip()
        or request_ref.get("sha256")
        != sha256_file(
            request_path
        )
    ):
        raise EffectiveLifecycleError(
            "GENERATION_REQUEST_RESOLUTION_INVALID",
            (
                "Generation Request Resolution "
                f"is invalid: {path}"
            ),
        )

    return {
        "path": path.resolve(),
        "artifact": value,
        "disposition": disposition,
        "evidence_ref": evidence_ref(
            pipeline_root,
            path,
        ),
    }


def _candidate_approved_batches(
    pipeline_root: Path,
    request_id: str,
) -> list[tuple[Path, dict[str, Any]]]:
    root = (
        pipeline_root
        / "data"
        / "generation_batches"
        / request_id
    )

    if not root.exists():
        return []

    result: list[
        tuple[Path, dict[str, Any]]
    ] = []

    for path in root.rglob(
        "approved_generation_batch_v1.json"
    ):
        try:
            value = read_json(path)
        except EffectiveLifecycleError:
            continue

        if (
            value.get("schema_version")
            == APPROVED_BATCH_SCHEMA
            and value.get("status")
            == "approved"
            and value.get("request_id")
            == request_id
        ):
            result.append(
                (
                    path.resolve(),
                    value,
                )
            )

    return result


def _candidate_generation_batches(
    pipeline_root: Path,
    request_id: str,
) -> list[tuple[Path, dict[str, Any]]]:
    root = (
        pipeline_root
        / "data"
        / "generation_batches"
        / request_id
    )

    if not root.exists():
        return []

    result: list[
        tuple[Path, dict[str, Any]]
    ] = []

    for path in root.rglob(
        "generation_batch_v1.json"
    ):
        try:
            value = read_json(path)
        except EffectiveLifecycleError:
            continue

        if (
            value.get("request_id")
            == request_id
        ):
            result.append(
                (
                    path.resolve(),
                    value,
                )
            )

    return result


def _validate_approved_batch(
    *,
    pipeline_root: Path,
    request_path: Path,
    request: dict[str, Any],
    batch_path: Path,
    batch: dict[str, Any],
) -> dict[str, Any]:
    batch_sha = sha256_file(
        batch_path
    )

    approval_path = (
        batch_path.parent
        / "generation_batch_approval_receipt.json"
    )

    if not approval_path.is_file():
        raise EffectiveLifecycleError(
            "GENERATION_APPROVAL_RECEIPT_REQUIRED",
            (
                "Approved Generation Batch "
                f"is missing approval receipt: {batch_path}"
            ),
        )

    approval = read_json(
        approval_path
    )

    approved_ref = (
        approval.get(
            "approved_batch"
        )
        or approval.get(
            "reviewed_batch"
        )
        or {}
    )

    if (
        batch.get("schema_version")
        != APPROVED_BATCH_SCHEMA
        or batch.get("status")
        != "approved"
        or batch.get("request_id")
        != request.get("request_id")
        or approval.get("schema_version")
        != APPROVAL_RECEIPT_SCHEMA
        or approval.get("request_id")
        != request.get("request_id")
        or approval.get("status")
        != "approved"
        or approval.get("human_gate")
        is not True
        or approved_ref.get("sha256")
        != batch_sha
    ):
        raise EffectiveLifecycleError(
            "GENERATION_APPROVED_BATCH_LINEAGE_INVALID",
            (
                "Approved Generation Batch / "
                "approval receipt lineage is invalid."
            ),
        )

    lineage = (
        batch.get("lineage")
        or {}
    )

    request_ref = (
        lineage.get("request")
        or {}
    )

    if request_ref:
        expected = (
            request_ref.get("sha256")
            or request_ref.get(
                "file_sha256"
            )
        )

        if (
            expected
            and expected
            != sha256_file(
                request_path
            )
        ):
            raise EffectiveLifecycleError(
                "GENERATION_APPROVED_BATCH_REQUEST_LINEAGE_INVALID",
                (
                    "Approved Generation Batch "
                    "does not reference the immutable Request."
                ),
            )

    return {
        "batch_path": (
            batch_path.resolve()
        ),
        "batch_sha256": batch_sha,
        "approval_path": (
            approval_path.resolve()
        ),
        "approval_sha256": (
            sha256_file(
                approval_path
            )
        ),
    }


def _validated_exports_for_request(
    *,
    pipeline_root: Path,
    request_path: Path,
    request: dict[str, Any],
    approved_batches: list[
        tuple[Path, dict[str, Any]]
    ],
) -> list[dict[str, Any]]:
    approved_by_sha: dict[
        str,
        tuple[
            Path,
            dict[str, Any],
            dict[str, Any],
        ],
    ] = {}

    for batch_path, batch in (
        approved_batches
    ):
        validation = (
            _validate_approved_batch(
                pipeline_root=(
                    pipeline_root
                ),
                request_path=(
                    request_path
                ),
                request=request,
                batch_path=batch_path,
                batch=batch,
            )
        )

        approved_by_sha[
            validation[
                "batch_sha256"
            ]
        ] = (
            batch_path,
            batch,
            validation,
        )

    output_root = (
        pipeline_root
        / "output"
    )

    if not output_root.exists():
        return []

    exports: list[
        dict[str, Any]
    ] = []

    for receipt_path in (
        output_root.glob(
            "*.export_receipt.json"
        )
    ):
        try:
            receipt = read_json(
                receipt_path
            )
        except EffectiveLifecycleError:
            continue

        if (
            receipt.get(
                "schema_version"
            )
            != MIX_EXPORT_RECEIPT_SCHEMA
            or receipt.get(
                "validation_passed"
            )
            is not True
        ):
            continue

        batch_sha = str(
            receipt.get(
                "batch_sha256"
            )
            or ""
        )

        matched = (
            approved_by_sha.get(
                batch_sha
            )
        )

        if matched is None:
            continue

        batch_path, _batch, validation = (
            matched
        )

        try:
            recorded_batch = (
                resolve_recorded_path(
                    pipeline_root,
                    receipt.get(
                        "batch_path"
                    ),
                )
            )
            output_path = (
                resolve_recorded_path(
                    pipeline_root,
                    receipt.get(
                        "output_path"
                    ),
                )
            )
        except EffectiveLifecycleError:
            continue

        if (
            recorded_batch
            != batch_path.resolve()
            or sha256_file(
                recorded_batch
            )
            != batch_sha
            or sha256_file(
                output_path
            )
            != receipt.get(
                "output_sha256"
            )
        ):
            continue

        exports.append(
            {
                "receipt_path": (
                    receipt_path.resolve()
                ),
                "receipt_sha256": (
                    sha256_file(
                        receipt_path
                    )
                ),
                "output_path": (
                    output_path
                ),
                "output_sha256": (
                    receipt.get(
                        "output_sha256"
                    )
                ),
                **validation,
            }
        )

    return exports



def _reviewed_rejected_batch(
    pipeline_root: Path,
    request_id: str,
) -> dict[str, Any] | None:
    root = (
        pipeline_root
        / "data"
        / "generation_batches"
        / request_id
    )

    reviewed_path = (
        root
        / "reviewed_generation_batch_v1.json"
    )
    receipt_path = (
        root
        / "generation_batch_approval_receipt.json"
    )

    if not reviewed_path.is_file():
        return None

    if not receipt_path.is_file():
        raise EffectiveLifecycleError(
            "GENERATION_REVIEW_RECEIPT_REQUIRED",
            "Reviewed Generation Batch exists without approval receipt.",
        )

    reviewed = read_json(
        reviewed_path
    )
    receipt = read_json(
        receipt_path
    )
    reviewed_sha = sha256_file(
        reviewed_path
    )
    reviewed_ref = (
        receipt.get("reviewed_batch")
        or {}
    )

    if not (
        reviewed.get("schema_version")
        == "reviewed-generation-batch-v1.0"
        and reviewed.get("request_id")
        == request_id
        and reviewed.get("status")
        == "rejected"
        and receipt.get("schema_version")
        == "generation-batch-approval-receipt-v1.0"
        and receipt.get("request_id")
        == request_id
        and receipt.get("status")
        == "rejected"
        and receipt.get("human_gate")
        is True
        and reviewed_ref.get("sha256")
        == reviewed_sha
    ):
        raise EffectiveLifecycleError(
            "GENERATION_REVIEWED_BATCH_LINEAGE_INVALID",
            "Reviewed Generation Batch / receipt lineage is invalid.",
        )

    return {
        "reviewed_path": reviewed_path.resolve(),
        "receipt_path": receipt_path.resolve(),
        "reviewed_sha256": reviewed_sha,
    }


def classify_request(
    *,
    pipeline_root: Path,
    request_path: Path,
) -> dict[str, Any]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )

    request_path = (
        request_path
        .expanduser()
        .resolve()
    )

    request = read_json(
        request_path
    )

    if (
        request.get("schema_version")
        != REQUEST_SCHEMA_VERSION
    ):
        raise EffectiveLifecycleError(
            "GENERATION_REQUEST_SCHEMA_INVALID",
            (
                "Unsupported Generation Request "
                f"schema: {request_path}"
            ),
        )

    request_id = str(
        request.get("request_id")
        or ""
    )

    if (
        not request_id
        or request_path.parent.name
        != request_id
    ):
        raise EffectiveLifecycleError(
            "GENERATION_REQUEST_LINEAGE_MISMATCH",
            (
                "Generation Request directory "
                "does not match request_id."
            ),
        )

    lifecycle = (
        request.get("lifecycle")
        or {}
    )

    direct_status = str(
        lifecycle.get("status")
        or ""
    )

    result: dict[str, Any] = {
        "request_id": request_id,
        "business_id": (
            request.get(
                "persona_id"
            )
        ),
        "speaker_id": (
            request.get(
                "speaker_persona"
            )
        ),
        "profile": (
            request.get(
                "target_profile"
            )
            or request.get(
                "profile"
            )
        ),
        "request_path": (
            str(request_path)
        ),
        "request_sha256": (
            sha256_file(
                request_path
            )
        ),
        "immutable_lifecycle_status": (
            direct_status
        ),
        "effective_terminal": False,
        "effective_status": (
            "resumable"
        ),
        "effective_stage": (
            "REQUEST_CREATED"
        ),
        "terminal_reason": None,
        "blockers": [],
        "evidence_refs": [
            evidence_ref(
                pipeline_root,
                request_path,
            )
        ],
    }

    if (
        direct_status
        in DIRECT_TERMINAL_STATUSES
    ):
        result.update(
            {
                "effective_terminal": (
                    True
                ),
                "effective_status": (
                    direct_status
                ),
                "effective_stage": (
                    "TERMINAL"
                ),
                "terminal_reason": (
                    "immutable_request_lifecycle"
                ),
            }
        )
        return result

    resolution = (
        _validate_resolution_sidecar(
            pipeline_root=pipeline_root,
            request_path=request_path,
            request=request,
        )
    )

    if resolution is not None:
        result[
            "evidence_refs"
        ].append(
            resolution[
                "evidence_ref"
            ]
        )

        result.update(
            {
                "effective_terminal": (
                    True
                ),
                "effective_status": (
                    resolution[
                        "disposition"
                    ]
                ),
                "effective_stage": (
                    "TERMINAL"
                ),
                "terminal_reason": (
                    "human_resolution_sidecar"
                ),
                "resolution": {
                    "path": str(
                        resolution[
                            "path"
                        ]
                    ),
                    "disposition": (
                        resolution[
                            "disposition"
                        ]
                    ),
                },
            }
        )

        return result

    rejected_review = (
        _reviewed_rejected_batch(
            pipeline_root,
            request_id,
        )
    )

    if rejected_review is not None:
        result[
            "evidence_refs"
        ].extend(
            [
                evidence_ref(
                    pipeline_root,
                    rejected_review[
                        "reviewed_path"
                    ],
                ),
                evidence_ref(
                    pipeline_root,
                    rejected_review[
                        "receipt_path"
                    ],
                ),
            ]
        )

        result.update(
            {
                "effective_terminal": True,
                "effective_status": "rejected",
                "effective_stage": "TERMINAL",
                "terminal_reason": "human_review_all_rejected",
            }
        )
        return result

    approved_batches = (
        _candidate_approved_batches(
            pipeline_root,
            request_id,
        )
    )

    validated_exports: list[
        dict[str, Any]
    ] = []

    try:
        validated_exports = (
            _validated_exports_for_request(
                pipeline_root=(
                    pipeline_root
                ),
                request_path=(
                    request_path
                ),
                request=request,
                approved_batches=(
                    approved_batches
                ),
            )
        )
    except EffectiveLifecycleError as exc:
        result["blockers"].append(
            {
                "code": exc.code,
                "message": str(exc),
            }
        )

    if validated_exports:
        if len(
            validated_exports
        ) > 1:
            result["blockers"].append(
                {
                    "code": (
                        "GENERATION_MULTIPLE_VALIDATED_EXPORTS"
                    ),
                    "message": (
                        "More than one validated Mix "
                        "export resolves to this Request."
                    ),
                }
            )

        for item in (
            validated_exports
        ):
            result[
                "evidence_refs"
            ].extend(
                [
                    evidence_ref(
                        pipeline_root,
                        Path(
                            item[
                                "approval_path"
                            ]
                        ),
                    ),
                    evidence_ref(
                        pipeline_root,
                        Path(
                            item[
                                "receipt_path"
                            ]
                        ),
                    ),
                    evidence_ref(
                        pipeline_root,
                        Path(
                            item[
                                "output_path"
                            ]
                        ),
                    ),
                ]
            )

        result.update(
            {
                "effective_terminal": (
                    True
                ),
                "effective_status": (
                    "exported"
                ),
                "effective_stage": (
                    "TERMINAL"
                ),
                "terminal_reason": (
                    "validated_mix_export"
                ),
                "validated_export_count": (
                    len(
                        validated_exports
                    )
                ),
            }
        )

        return result

    if approved_batches:
        if len(
            approved_batches
        ) > 1:
            result["blockers"].append(
                {
                    "code": (
                        "GENERATION_APPROVED_BATCH_AMBIGUITY"
                    ),
                    "message": (
                        "Multiple Approved Generation "
                        "Batches exist without a validated export."
                    ),
                }
            )

        result[
            "effective_stage"
        ] = "APPROVED_PENDING_EXPORT"

        for path, _batch in (
            approved_batches
        ):
            result[
                "evidence_refs"
            ].append(
                evidence_ref(
                    pipeline_root,
                    path,
                )
            )

        return result

    generation_batches = (
        _candidate_generation_batches(
            pipeline_root,
            request_id,
        )
    )

    review_required = [
        (
            path,
            batch,
        )
        for path, batch in (
            generation_batches
        )
        if batch.get("status")
        == "review_required"
    ]

    if review_required:
        result[
            "effective_stage"
        ] = "HUMAN_REVIEW"

        for path, _batch in (
            review_required
        ):
            result[
                "evidence_refs"
            ].append(
                evidence_ref(
                    pipeline_root,
                    path,
                )
            )

        return result

    source_plan_path = (
        pipeline_root
        / "data"
        / "production_plans"
        / request_id
        / "generation_source_plan_v1.json"
    )

    if source_plan_path.is_file():
        result[
            "effective_stage"
        ] = "SOURCE_PLAN_READY"
        result[
            "evidence_refs"
        ].append(
            evidence_ref(
                pipeline_root,
                source_plan_path,
            )
        )

    return result


def audit_business_requests(
    *,
    pipeline_root: Path,
    business_id: str,
    profile: str | None = None,
) -> dict[str, Any]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )

    profile_filter = (
        str(profile or "")
        .strip()
        .lower()
        or None
    )

    if (
        profile_filter is not None
        and profile_filter
        not in {"mix", "news"}
    ):
        raise EffectiveLifecycleError(
            "GENERATION_PROFILE_INVALID",
            "profile must be mix, news, or omitted.",
        )

    root = (
        pipeline_root
        / "data"
        / "generation_requests"
    )

    requests: list[
        dict[str, Any]
    ] = []

    if root.exists():
        for path in root.glob(
            "*/generation_request_v1.json"
        ):
            try:
                value = read_json(path)
            except EffectiveLifecycleError:
                continue

            if str(
                value.get("persona_id")
                or ""
            ) != business_id:
                continue

            classification = (
                classify_request(
                    pipeline_root=(
                        pipeline_root
                    ),
                    request_path=path,
                )
            )

            if (
                profile_filter
                is not None
                and str(
                    classification.get(
                        "profile"
                    )
                    or ""
                ).lower()
                != profile_filter
            ):
                continue

            requests.append(
                classification
            )

    requests.sort(
        key=lambda item: str(
            item.get(
                "request_id"
            )
            or ""
        )
    )

    active = [
        item
        for item in requests
        if (
            item.get(
                "effective_terminal"
            )
            is not True
        )
    ]

    terminal = [
        item
        for item in requests
        if (
            item.get(
                "effective_terminal"
            )
            is True
        )
    ]

    if not active:
        status = "no_active_request"
        active_request_id = None
    elif len(active) == 1:
        status = "single_active_request"
        active_request_id = (
            active[0][
                "request_id"
            ]
        )
    else:
        status = (
            "active_request_ambiguity"
        )
        active_request_id = None

    return {
        "schema_version": (
            "generation-request-effective-lifecycle-audit-v1.0"
        ),
        "business_id": business_id,
        "profile_filter": (
            profile_filter
        ),
        "read_only": True,
        "artifact_written": False,
        "remote_model_called": False,
        "status": status,
        "active_request_id": (
            active_request_id
        ),
        "active_request_count": len(
            active
        ),
        "terminal_request_count": (
            len(terminal)
        ),
        "request_count": len(
            requests
        ),
        "active_request_ids": [
            item["request_id"]
            for item in active
        ],
        "requests": requests,
    }


def request_is_effectively_in_flight(
    *,
    pipeline_root: Path,
    request_path: Path,
) -> bool:
    return (
        classify_request(
            pipeline_root=(
                pipeline_root
            ),
            request_path=(
                request_path
            ),
        ).get(
            "effective_terminal"
        )
        is not True
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only Generation Request "
            "Effective Lifecycle audit."
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
        "--business-id",
        required=True,
    )

    parser.add_argument(
        "--profile",
        choices=(
            "mix",
            "news",
        ),
    )

    args = parser.parse_args()

    try:
        result = (
            audit_business_requests(
                pipeline_root=Path(
                    args.pipeline_root
                ),
                business_id=(
                    args.business_id
                ),
                profile=(
                    args.profile
                ),
            )
        )
    except EffectiveLifecycleError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": exc.code,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(
        json.dumps(
            {
                "ok": True,
                "audit": result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
