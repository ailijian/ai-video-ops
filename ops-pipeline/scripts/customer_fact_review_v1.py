from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from build_persona_v1 import (
    assess_business_persona_capabilities,
    build_persona,
    sha256_file,
)
from customer_intake_v1 import (
    SCALAR_PERSONA_FIELDS,
    build_fact_candidate_artifact,
    critical_readiness_constraints,
)

SCHEMA_VERSION = "customer-fact-review-v1.0"
OPERATION_VERSION = "customer_fact_review_v1.py@1.0"

DECISIONS = {"approve", "reject", "edit"}


class CustomerFactReviewError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CustomerFactReviewError(
            "ARTIFACT_NOT_FOUND",
            f"Required artifact does not exist: {path}",
        )

    value = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(value, dict):
        raise CustomerFactReviewError(
            "INVALID_JSON",
            f"Expected a JSON object: {path}",
        )

    return value


def write_atomic_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)

    os.replace(temporary, path)


def write_new_or_same(
    path: Path,
    value: dict[str, Any],
) -> None:
    if path.exists():
        existing = read_json(path)

        if canonical_sha256(existing) != canonical_sha256(value):
            raise CustomerFactReviewError(
                "FACT_REVIEW_ARTIFACT_CONFLICT",
                f"Existing fact-review artifact differs: {path}",
            )

        return

    write_atomic_json(path, value)


def has_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)

    return True


def normalize_decisions(
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in decisions:
        if not isinstance(raw, dict):
            raise CustomerFactReviewError(
                "INVALID_REVIEW_DECISION",
                "Every decision must be an object.",
            )

        candidate_id = str(raw.get("candidate_id") or "").strip()

        decision = str(raw.get("decision") or "").strip().lower()

        note = str(raw.get("note") or "").strip()

        if not candidate_id:
            raise CustomerFactReviewError(
                "INVALID_REVIEW_DECISION",
                "candidate_id is required.",
            )

        if candidate_id in seen:
            raise CustomerFactReviewError(
                "DUPLICATE_REVIEW_DECISION",
                f"Duplicate decision for {candidate_id}.",
            )

        seen.add(candidate_id)

        if decision not in DECISIONS:
            raise CustomerFactReviewError(
                "INVALID_REVIEW_DECISION",
                f"Unsupported decision: {decision!r}",
            )

        item: dict[str, Any] = {
            "candidate_id": candidate_id,
            "decision": decision,
            "note": note,
        }

        if decision == "edit":
            edited_value = copy.deepcopy(raw.get("edited_value"))

            if not has_value(edited_value):
                raise CustomerFactReviewError(
                    "EDITED_VALUE_REQUIRED",
                    (f"Decision edit for {candidate_id} " "requires edited_value."),
                )

            item["edited_value"] = edited_value

        normalized.append(item)

    normalized.sort(key=lambda item: item["candidate_id"])

    return normalized


def validate_review_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    business_id = str(request.get("business_id") or "").strip()

    intake_id = str(request.get("intake_id") or "").strip()

    reviewer = str(request.get("reviewer") or "").strip()

    note = str(request.get("note") or "").strip()

    decisions = request.get("decisions")

    if not business_id:
        raise CustomerFactReviewError(
            "BUSINESS_ID_REQUIRED",
            "business_id is required.",
        )

    if not intake_id:
        raise CustomerFactReviewError(
            "INTAKE_ID_REQUIRED",
            "intake_id is required.",
        )

    if not reviewer:
        raise CustomerFactReviewError(
            "REVIEWER_REQUIRED",
            "reviewer is required.",
        )

    if not isinstance(decisions, list):
        raise CustomerFactReviewError(
            "DECISIONS_REQUIRED",
            "decisions must be a list.",
        )

    return {
        "business_id": business_id,
        "intake_id": intake_id,
        "reviewer": reviewer,
        "note": note,
        "decisions": normalize_decisions(decisions),
    }


def validate_candidate_lineage(
    *,
    intake: dict[str, Any],
    candidate_artifact: dict[str, Any],
) -> None:
    intake_ref = candidate_artifact.get("intake_ref") or {}

    if intake_ref.get("intake_id") != intake.get("intake_id"):
        raise CustomerFactReviewError(
            "CANDIDATE_INTAKE_MISMATCH",
            "Fact candidates do not belong to this intake.",
        )

    expected_sha = (intake.get("raw_input_contract") or {}).get("raw_answers_sha256")

    if intake_ref.get("raw_answers_sha256") != expected_sha:
        raise CustomerFactReviewError(
            "RAW_INPUT_LINEAGE_MISMATCH",
            ("Fact candidates no longer match " "the immutable raw intake."),
        )


def validate_decision_coverage(
    *,
    candidate_artifact: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> None:
    candidates = candidate_artifact.get("fact_candidates") or []

    review_required_ids = {
        str(item.get("fact_candidate_id"))
        for item in candidates
        if item.get("candidate_state") == "requires_review"
    }

    decision_ids = {item["candidate_id"] for item in decisions}

    missing = sorted(review_required_ids - decision_ids)

    extra = sorted(decision_ids - review_required_ids)

    if missing:
        raise CustomerFactReviewError(
            "FACT_REVIEW_INCOMPLETE",
            (
                "Every requires_review candidate "
                "needs an explicit Human decision. "
                "Missing: " + ", ".join(missing)
            ),
        )

    if extra:
        raise CustomerFactReviewError(
            "FACT_REVIEW_UNKNOWN_CANDIDATE",
            (
                "Review decisions contain candidates "
                "that are not currently awaiting review: " + ", ".join(extra)
            ),
        )


def apply_human_decisions(
    *,
    intake: dict[str, Any],
    candidate_artifact: dict[str, Any],
    decisions: list[dict[str, Any]],
    reviewer: str,
    reviewed_at: str,
) -> dict[str, Any]:
    decision_by_id = {item["candidate_id"]: item for item in decisions}

    reviewed_candidates: list[dict[str, Any]] = []

    for source in candidate_artifact.get("fact_candidates") or []:
        candidate = copy.deepcopy(source)

        candidate_id = str(candidate.get("fact_candidate_id") or "")

        if candidate.get("candidate_state") != "requires_review":
            reviewed_candidates.append(candidate)
            continue

        decision = decision_by_id[candidate_id]
        action = decision["decision"]
        note = decision.get("note") or ""

        candidate["human_review"] = {
            "decision": action,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "note": note,
            "human_gate": True,
        }

        if action == "approve":
            candidate["candidate_state"] = "known_candidate"

            candidate["confirmation_basis"] = "human_review_approved"

            candidate["review_note"] = note or (
                "Human Review confirmed this " "AI-extracted fact candidate."
            )

        elif action == "edit":
            candidate["candidate_state"] = "known_candidate"

            candidate["normalized_value"] = copy.deepcopy(decision["edited_value"])

            candidate["confirmation_basis"] = "human_review_edited"

            candidate["review_note"] = note or (
                "Human Review corrected the "
                "AI-extracted candidate before "
                "Persona construction."
            )

        else:
            candidate["candidate_state"] = "unknown"

            candidate["normalized_value"] = None

            candidate["confirmation_basis"] = "human_review_rejected"

            candidate["review_note"] = note or (
                "Human Review rejected this " "AI-extracted candidate."
            )

        reviewed_candidates.append(candidate)

    reviewed = build_fact_candidate_artifact(
        intake,
        reviewed_candidates,
        created_at=reviewed_at,
        derived_authority_constraints=(
            candidate_artifact.get("derived_authority_constraints") or []
        ),
    )

    reviewed["review"] = {
        "status": "completed",
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "human_gate": True,
        "decisions": copy.deepcopy(decisions),
    }

    reviewed["authority"].update(
        {
            "human_review_completed": True,
            "persona_fact_authority_created": False,
            "persona_approval_completed": False,
            "production_consumption_allowed": False,
        }
    )

    return reviewed


def merge_known_values(
    values: list[Any],
    *,
    scalar: bool,
) -> Any:
    if not values:
        return None

    if scalar:
        canonical_values = {canonical_sha256(value) for value in values}

        if len(canonical_values) > 1:
            raise CustomerFactReviewError(
                "SCALAR_FACT_CONFLICT",
                (
                    "Multiple different known values "
                    "exist for one scalar Persona field."
                ),
            )

        return copy.deepcopy(values[-1])

    flattened: list[Any] = []

    for value in values:
        if isinstance(value, list):
            flattened.extend(copy.deepcopy(value))
        else:
            flattened.append(copy.deepcopy(value))

    result: list[Any] = []
    seen: set[str] = set()

    for value in flattened:
        fingerprint = canonical_sha256(value)

        if fingerprint in seen:
            continue

        seen.add(fingerprint)
        result.append(value)

    return result


def build_business_persona_input(
    *,
    business_id: str,
    intake_id: str,
    reviewed_artifact: dict[str, Any],
    reviewed_artifact_path: Path,
    reviewed_sources: list[tuple[str, dict[str, Any], Path]] | None = None,
) -> dict[str, Any]:
    sources = reviewed_sources or [
        (intake_id, reviewed_artifact, reviewed_artifact_path)
    ]
    business_candidates: list[dict[str, Any]] = []
    for source_intake_id, artifact, _path in sources:
        for source in artifact.get("fact_candidates") or []:
            if (
                source.get("persona_scope") != "business"
                or source.get("candidate_state") != "known_candidate"
            ):
                continue
            candidate = copy.deepcopy(source)
            candidate["_source_intake_id"] = source_intake_id
            business_candidates.append(candidate)

    fields = sorted(
        {
            str(item.get("target_field") or "")
            for item in business_candidates
            if item.get("target_field")
        }
    )

    facts: dict[str, Any] = {}

    for field in fields:
        selected = [
            item for item in business_candidates if item.get("target_field") == field
        ]

        values = [
            item.get("normalized_value")
            for item in selected
            if has_value(item.get("normalized_value"))
        ]

        if not values:
            continue

        merged = merge_known_values(
            values,
            scalar=(field in SCALAR_PERSONA_FIELDS),
        )

        source_refs = [
            (
                "customer_intake:"
                f"{item['_source_intake_id']}#"
                f"{item['fact_candidate_id']}"
            )
            for item in selected
        ]

        facts[field] = {
            "state": "known",
            "value": merged,
            "source_refs": source_refs,
            "review_note": (
                "Built only from Human-reviewed " "Customer Intake Fact Candidates."
            ),
        }

    return {
        "persona_id": business_id,
        "revision": 1,
        "persona_scope": "business",
        "fixture_only": False,
        "source_type": (
            "customer_intake_human_fact_review"
            if len(sources) == 1
            else "customer_intake_human_fact_review_combined"
        ),
        "source_file": str(reviewed_artifact_path.resolve()),
        "source_ref": (
            f"customer_intake:{intake_id}"
            if len(sources) == 1
            else "customer_intakes:" + ",".join(item[0] for item in sources)
        ),
        "source_files": [str(item[2].resolve()) for item in sources],
        "facts": facts,
    }


def required_business_blockers(
    persona_input: dict[str, Any],
    *,
    intake: dict[str, Any] | None = None,
    critical_constraints: list[dict[str, Any]] | None = None,
) -> list[str]:
    facts = persona_input.get("facts") or {}
    readiness = assess_business_persona_capabilities(
        facts,
        critical_constraints=(
            critical_constraints
            if critical_constraints is not None
            else critical_readiness_constraints(intake)
            if intake is not None
            else []
        ),
    )
    return list(readiness["blockers"])


def reviewed_business_sources(
    pipeline_root: Path,
    business_id: str,
) -> list[tuple[str, dict[str, Any], Path]]:
    root = pipeline_root / "data" / "customer_intakes" / business_id
    result: list[tuple[str, dict[str, Any], Path]] = []
    if not root.exists():
        return result
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        path = directory / "reviewed_persona_fact_candidates_v1.json"
        if path.is_file():
            result.append((directory.name, read_json(path), path))
    return result


def combined_critical_constraints(
    pipeline_root: Path,
    business_id: str,
) -> list[dict[str, Any]]:
    root = pipeline_root / "data" / "customer_intakes" / business_id
    if not root.exists():
        return []
    addressed: set[str] = set()
    constraints: list[tuple[str, dict[str, Any]]] = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        intake_path = directory / "customer_intake_v1.json"
        reviewed_path = directory / "reviewed_persona_fact_candidates_v1.json"
        if not intake_path.is_file():
            continue
        intake = read_json(intake_path)
        if reviewed_path.is_file():
            reviewed = read_json(reviewed_path)
            has_confirmed_fact = any(
                item.get("candidate_state") == "known_candidate"
                and item.get("human_review", {}).get("decision") in {"approve", "edit"}
                for item in reviewed.get("fact_candidates") or []
            )
            if has_confirmed_fact:
                addressed.update(
                    str(item.get("target_gap") or "")
                    for item in intake.get("target_gaps") or []
                )
        for item in critical_readiness_constraints(intake):
            constraint_id = str(
                item.get("constraint_id")
                or item.get("conflict_id")
                or item.get("question_id")
                or canonical_sha256(item)[:16]
            )
            constraints.append((constraint_id, item))
    return [
        item
        for constraint_id, item in constraints
        if "critical_constraints" not in addressed
        and f"critical_constraints:{constraint_id}" not in addressed
    ]


def ensure_or_build_business_persona(
    *,
    pipeline_root: Path,
    business_id: str,
    input_path: Path,
    created_at: str,
) -> tuple[Path, dict[str, Any]]:
    output_root = pipeline_root / "data" / "personas"

    expected_path = output_root / business_id / "revision_0001" / "persona_v1.json"

    if expected_path.is_file():
        persona = read_json(expected_path)

        provenance = persona.get("provenance") or {}

        if (
            persona.get("persona_id") != business_id
            or persona.get("persona_scope") != "business"
            or int(persona.get("revision") or 0) != 1
            or provenance.get("input_sha256") != sha256_file(input_path)
        ):
            raise CustomerFactReviewError(
                "PERSONA_REVISION_CONFLICT",
                (
                    "An existing Persona revision "
                    "does not match this reviewed "
                    "Customer Intake."
                ),
            )

        return expected_path, persona

    try:
        return build_persona(
            input_path,
            output_root,
            created_at=created_at,
        )
    except Exception as exc:
        raise CustomerFactReviewError(
            "BUSINESS_PERSONA_BUILD_FAILED",
            str(exc),
        ) from exc


def review_customer_facts(
    *,
    request: dict[str, Any],
    pipeline_root: Path,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    request = validate_review_request(request)

    business_id = request["business_id"]

    intake_id = request["intake_id"]

    intake_root = pipeline_root / "data" / "customer_intakes" / business_id / intake_id

    intake_path = intake_root / "customer_intake_v1.json"

    candidates_path = intake_root / "persona_fact_candidates_v1.json"

    intake = read_json(intake_path)

    candidate_artifact = read_json(candidates_path)

    if intake.get("provisional_business_id") != business_id:
        raise CustomerFactReviewError(
            "BUSINESS_INTAKE_MISMATCH",
            ("Customer Intake does not " "belong to this business."),
        )

    validate_candidate_lineage(
        intake=intake,
        candidate_artifact=(candidate_artifact),
    )

    validate_decision_coverage(
        candidate_artifact=(candidate_artifact),
        decisions=request["decisions"],
    )

    candidate_sha = sha256_file(candidates_path)

    review_fingerprint = canonical_sha256(
        {
            "business_id": business_id,
            "intake_id": intake_id,
            "reviewer": request["reviewer"],
            "note": request["note"],
            "candidate_sha256": (candidate_sha),
            "decisions": request["decisions"],
        }
    )

    review_path = intake_root / "customer_fact_review_v1.json"

    existing_review: dict[str, Any] | None = None

    if review_path.is_file():
        existing_review = read_json(review_path)

        if existing_review.get("review_fingerprint") != review_fingerprint:
            raise CustomerFactReviewError(
                "FACT_REVIEW_ALREADY_FINALIZED",
                ("This intake already has " "a different Human Fact Review."),
            )

        if existing_review.get("status") == "completed_persona_review_required":
            return existing_review

        timestamp = str(existing_review.get("reviewed_at") or "")

        if not timestamp:
            raise CustomerFactReviewError(
                "FACT_REVIEW_STATE_INVALID",
                ("Existing fact-review state " "has no reviewed_at."),
            )

    else:
        from datetime import (
            datetime,
            timezone,
        )

        timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()

        intent = {
            "schema_version": (SCHEMA_VERSION),
            "operation_version": (OPERATION_VERSION),
            "business_id": business_id,
            "intake_id": intake_id,
            "status": ("review_in_progress"),
            "review_fingerprint": (review_fingerprint),
            "reviewer": request["reviewer"],
            "reviewed_at": timestamp,
            "note": request["note"],
            "source": {
                "customer_intake_path": str(intake_path.resolve()),
                "fact_candidates_path": str(candidates_path.resolve()),
                "fact_candidates_sha256": (candidate_sha),
            },
            "decisions": copy.deepcopy(request["decisions"]),
            "authority": {
                "human_gate": True,
                "review_decision_immutable": True,
                "persona_approved": False,
            },
        }

        write_atomic_json(
            review_path,
            intent,
        )

        existing_review = intent

    reviewed = apply_human_decisions(
        intake=intake,
        candidate_artifact=(candidate_artifact),
        decisions=request["decisions"],
        reviewer=request["reviewer"],
        reviewed_at=timestamp,
    )

    reviewed_path = intake_root / ("reviewed_persona_" "fact_candidates_v1.json")

    write_new_or_same(
        reviewed_path,
        reviewed,
    )

    reviewed_sources = reviewed_business_sources(
        pipeline_root,
        business_id,
    )

    persona_input = build_business_persona_input(
        business_id=business_id,
        intake_id=intake_id,
        reviewed_artifact=reviewed,
        reviewed_artifact_path=(reviewed_path),
        reviewed_sources=reviewed_sources,
    )

    blockers = required_business_blockers(
        persona_input,
        critical_constraints=combined_critical_constraints(
            pipeline_root,
            business_id,
        ),
    )

    if blockers:
        completed = {
            **existing_review,
            "status": ("completed_persona_blocked"),
            "artifacts": {
                "reviewed_candidates_v1": (str(reviewed_path.resolve())),
            },
            "business_persona_blockers": (blockers),
            "authority": {
                **existing_review["authority"],
                "fact_review_completed": True,
                "business_persona_created": False,
                "persona_approved": False,
            },
            "next_action": ("COLLECT_MORE_CUSTOMER_TRUTH"),
        }

        write_atomic_json(
            review_path,
            completed,
        )

        return completed

    persona_input_path = intake_root / "business_persona_input_v1.json"

    write_new_or_same(
        persona_input_path,
        persona_input,
    )

    (
        persona_path,
        persona,
    ) = ensure_or_build_business_persona(
        pipeline_root=pipeline_root,
        business_id=business_id,
        input_path=persona_input_path,
        created_at=timestamp,
    )

    lifecycle = persona.get("lifecycle") or {}

    if lifecycle.get("status") not in {
        "review_required",
        "approved",
    }:
        raise CustomerFactReviewError(
            "BUSINESS_PERSONA_STATE_INVALID",
            ("Business Persona was created " "in an unexpected lifecycle state."),
        )

    completed = {
        **existing_review,
        "status": ("completed_persona_review_required"),
        "artifacts": {
            "reviewed_candidates_v1": (str(reviewed_path.resolve())),
            "business_persona_input_v1": (str(persona_input_path.resolve())),
            "business_persona_v1": (str(persona_path.resolve())),
        },
        "business_persona": {
            "persona_id": persona.get("persona_id"),
            "revision": persona.get("revision"),
            "persona_scope": persona.get("persona_scope"),
            "lifecycle_status": (lifecycle.get("status")),
            "required_fact_approval_blockers": (
                (persona.get("validation") or {}).get(
                    "required_fact_approval_blockers",
                    [],
                )
            ),
        },
        "authority": {
            **existing_review["authority"],
            "fact_review_completed": True,
            "business_persona_created": True,
            "persona_approved": (lifecycle.get("approved") is True),
            "production_consumption_allowed": (lifecycle.get("approved") is True),
        },
        "next_action": ("REVIEW_BUSINESS_PERSONA"),
    }

    write_atomic_json(
        review_path,
        completed,
    )

    return completed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply explicit Human decisions "
            "to Customer Intake Fact Candidates "
            "and construct a review-required "
            "Business Persona candidate."
        )
    )

    parser.add_argument(
        "--review",
        required=True,
        help=("Path to Human Fact Review " "request JSON."),
    )

    parser.add_argument(
        "--pipeline-root",
        default=None,
    )

    args = parser.parse_args()

    pipeline_root = (
        Path(args.pipeline_root).expanduser().resolve()
        if args.pipeline_root
        else Path(__file__).resolve().parents[1]
    )

    request = read_json(Path(args.review).expanduser().resolve())

    try:
        result = review_customer_facts(
            request=request,
            pipeline_root=pipeline_root,
        )
    except CustomerFactReviewError as exc:
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
                "business_id": result["business_id"],
                "intake_id": result["intake_id"],
                "status": result["status"],
                "next_action": result["next_action"],
                "business_persona": (result.get("business_persona")),
                "blockers": (
                    result.get(
                        "business_persona_blockers",
                        [],
                    )
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
