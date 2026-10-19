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
PROGRESS_VERSION = "customer-fact-review-progress-v1.0"


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


def read_review_progress(directory: Path) -> dict[str, Any]:
    """Deterministic read projection of append-only Human Decisions, never SQLite."""
    intake = read_json(directory / "customer_intake_v1.json")
    if canonical_sha256(intake.get("raw_answers", [])) != intake.get("raw_input_contract", {}).get("raw_answers_sha256"):
        raise CustomerFactReviewError("FACT_REVIEW_SOURCE_INVALID", "Saved source does not match its immutable raw SHA.")
    candidate_path = directory / "persona_fact_candidates_v1.json"
    candidate = read_json(candidate_path)
    validate_candidate_lineage(intake=intake, candidate_artifact=candidate)
    candidate_sha = sha256_file(candidate_path)
    artifact = copy.deepcopy(candidate)
    decisions, constraints, receipts = [], [], []
    industry = None
    parent = None
    for index, path in enumerate(sorted((directory / "review_progress").glob("*.json")), 1):
        receipt = read_json(path)
        if (receipt.get("schema_version") != PROGRESS_VERSION or receipt.get("sequence") != index
                or receipt.get("parent_sha256") != parent or receipt.get("candidate_sha256") != candidate_sha
                or receipt.get("intake_sha256") != sha256_file(directory / "customer_intake_v1.json")
                or receipt.get("business_id") != intake["provisional_business_id"]
                or receipt.get("intake_id") != intake["intake_id"]
                or not receipt.get("reviewer") or not receipt.get("reviewed_at")
                or receipt.get("authority", {}).get("human_gate") is not True):
            raise CustomerFactReviewError("FACT_REVIEW_PROGRESS_INVALID", "Immutable review progress source/sequence/actor differs.")
        normalized = validate_review_request(receipt["request"])
        if (normalized["reviewer"] != receipt["reviewer"] or normalized["business_id"] != receipt["business_id"]
                or normalized["intake_id"] != receipt["intake_id"]
                or canonical_sha256(receipt["request"]) != receipt["request_sha256"]):
            raise CustomerFactReviewError("FACT_REVIEW_PROGRESS_INVALID", "Review receipt request identity differs.")
        _validate_progress_subset(artifact, normalized)
        artifact = apply_human_decisions(intake=intake, candidate_artifact=artifact,
            decisions=normalized["decisions"], reviewer=receipt["reviewer"], reviewed_at=receipt["reviewed_at"],
            industry_review=normalized.get("industry_review"), constraint_decisions=normalized.get("constraint_decisions"),
            candidate_sha=candidate_sha, partial=True)
        # Bind every new decision to the exact original candidate/source and receipt.
        new_ids = {v["candidate_id"] for v in normalized["decisions"]}
        for item in artifact["fact_candidates"]:
            if item.get("fact_candidate_id") in new_ids:
                item["human_review"].update(candidate_sha256=candidate_sha,
                    source_intake_sha256=receipt["intake_sha256"], receipt_sha256=sha256_file(path))
        decisions.extend(normalized["decisions"])
        constraints.extend(normalized.get("constraint_decisions", []))
        if normalized.get("industry_review") is not None:
            industry = normalized["industry_review"]
        parent = sha256_file(path)
        receipts.append({**receipt, "path": str(path), "file_sha256": parent})
    pending = [v["fact_candidate_id"] for v in artifact["fact_candidates"] if v.get("candidate_state") == "requires_review"]
    pending_constraints = [v["constraint_id"] for v in artifact.get("derived_authority_constraints", []) if not v.get("human_review")]
    complete = not pending and not pending_constraints
    artifact["authority"]["human_review_completed"] = complete
    return {"artifact": artifact, "decisions": decisions, "constraint_decisions": constraints,
        "industry_review": industry, "receipts": receipts, "version": parent,
        "pending_ids": pending, "pending_constraint_ids": pending_constraints, "complete": complete}


def _validate_progress_subset(artifact: dict[str, Any], request: dict[str, Any]) -> None:
    pending = {v["fact_candidate_id"] for v in artifact.get("fact_candidates", []) if v.get("candidate_state") == "requires_review"}
    ids = {v["candidate_id"] for v in request["decisions"]}
    constraints = {v["constraint_id"] for v in artifact.get("derived_authority_constraints", []) if not v.get("human_review")}
    if ids - pending or {v["constraint_id"] for v in request.get("constraint_decisions", [])} - constraints:
        raise CustomerFactReviewError("FACT_REVIEW_DECISION_IMMUTABLE", "Unknown or previously reviewed item cannot be overwritten.")
    if request.get("industry_review") and any(v.get("target_field") == "industry" for v in artifact.get("fact_candidates", [])):
        raise CustomerFactReviewError("INDUSTRY_CANDIDATE_ALREADY_EXISTS", "The existing classification is immutable.")


def save_review_progress(*, request: dict[str, Any], pipeline_root: Path,
        reviewed_at: str | None = None) -> dict[str, Any]:
    """Append a legal subset, then resume the existing complete-review builder.

    A receipt is the durable commit point. Later derived files are recoverable;
    multi-file completion is deliberately not claimed to be atomic.
    """
    from datetime import datetime, timezone
    operation_id = str(request.get("operation_id") or "")
    if len(operation_id) != 32 or any(v not in "0123456789abcdef" for v in operation_id):
        raise CustomerFactReviewError("INVALID_REVIEW_OPERATION", "Use a server-issued review operation identity.")
    normalized = validate_review_request(request)
    directory = pipeline_root / "data" / "customer_intakes" / normalized["business_id"] / normalized["intake_id"]
    progress = read_review_progress(directory)
    existing = next((v for v in progress["receipts"] if v["operation_id"] == operation_id), None)
    intent = {**normalized, "operation_id": operation_id,
        "context_version": request.get("context_version"), "context_sha256": request.get("context_sha256")}
    if existing:
        if existing["request_sha256"] != canonical_sha256(intent) or existing["reviewer"] != normalized["reviewer"]:
            raise CustomerFactReviewError("REVIEW_REPLAY_CONFLICT", "A review operation cannot be reused for a different actor or payload.")
    else:
        if (directory / "customer_fact_review_v1.json").exists():
            completed = read_json(directory / "customer_fact_review_v1.json")
            if (str(completed.get("status", "")).startswith("completed_") and not normalized["decisions"]
                    and not normalized.get("constraint_decisions") and not normalized.get("industry_review")):
                return completed  # Read-only refresh/no-op, never a replacement Human decision.
            raise CustomerFactReviewError("FACT_REVIEW_ALREADY_FINALIZED", "Completed review cannot be changed by a new batch.")
        if request.get("context_version") != progress["version"]:
            raise CustomerFactReviewError("REVIEW_CONTEXT_STALE", "Review progress changed; reload and check it.")
        _validate_progress_subset(progress["artifact"], normalized)
        if (not normalized["decisions"] and not normalized.get("constraint_decisions") and not normalized.get("industry_review")
                and not progress["complete"]):
            raise CustomerFactReviewError("EMPTY_REVIEW_SUBMISSION", "No legal review selection was submitted.")
        timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()
        # Validate all changes before persisting anything, including source-backed amendments.
        preview = apply_human_decisions(intake=read_json(directory / "customer_intake_v1.json"),
            candidate_artifact=progress["artifact"], decisions=normalized["decisions"],
            reviewer=normalized["reviewer"], reviewed_at=timestamp, partial=True,
            industry_review=normalized.get("industry_review"), constraint_decisions=normalized.get("constraint_decisions"),
            candidate_sha=sha256_file(directory / "persona_fact_candidates_v1.json"))
        historical = reviewed_business_sources(pipeline_root, normalized["business_id"])
        from persona_review_lifecycle_v1 import effective_sources, replacement_fields
        historical = effective_sources(historical)
        replacements = replacement_fields(directory, preview)
        from show_customer_status_v1 import resolve_current_persona, AuthorityResolutionError
        try:
            current = resolve_current_persona(pipeline_root, normalized["business_id"], "business")
        except AuthorityResolutionError as exc:
            if exc.code not in {"PERSONA_NOT_FOUND", "APPROVED_PERSONA_NOT_FOUND"}:
                raise
            current = None
        from persona_review_lifecycle_v1 import scalar_review_values
        for field, values in scalar_review_values(historical, preview, current, replacements).items():
            if values:
                try:
                    merge_known_values(values, scalar=True)
                except CustomerFactReviewError:
                    fingerprint = canonical_sha256([intent, field, sha256_file(directory / "persona_fact_candidates_v1.json")])
                    path = directory / "fact_conflicts" / f"review_{fingerprint[:24]}.json"
                    if not path.exists():
                        write_new_or_same(path, {"status": "awaiting_explicit_human_resolution", "field": field,
                            "review_fingerprint": fingerprint, "reviewer": normalized["reviewer"], "attempted_at": timestamp,
                            "decisions": normalized["decisions"], "candidate_sha256": sha256_file(directory / "persona_fact_candidates_v1.json"),
                            "approved_persona_sha256": current["file_sha256"] if current else None,
                            "authority": {"fact_review_finalized": False, "approved_truth_changed": False}})
                    elif read_json(path).get("review_fingerprint") != fingerprint:
                        raise CustomerFactReviewError("FACT_CONFLICT_RECORD_COLLISION", "Conflict identity collision")
                    raise
        sequence = len(progress["receipts"]) + 1
        receipt = {"schema_version": PROGRESS_VERSION, "sequence": sequence,
            "operation_id": operation_id, "parent_sha256": progress["version"],
            "candidate_sha256": sha256_file(directory / "persona_fact_candidates_v1.json"),
            "intake_sha256": sha256_file(directory / "customer_intake_v1.json"),
            "business_id": normalized["business_id"], "intake_id": normalized["intake_id"],
            "reviewer": normalized["reviewer"], "reviewed_at": timestamp,
            "request": intent, "request_sha256": canonical_sha256(intent),
            "authority": {"human_gate": True, "decision_immutable": True, "persona_approved": False}}
        write_new_or_same(directory / "review_progress" / f"{sequence:06d}_{operation_id}.json", receipt)
        progress = read_review_progress(directory)
    if not progress["complete"]:
        return {"business_id": normalized["business_id"], "intake_id": normalized["intake_id"],
            "status": "review_progress_saved", "next_action": "CONTINUE_FACT_REVIEW",
            "pending_count": len(progress["pending_ids"]) + len(progress["pending_constraint_ids"]),
            "saved_count": len(progress["decisions"]) + len(progress["constraint_decisions"]),
            "authority": {"human_gate": True, "fact_review_completed": False, "persona_approved": False}}
    aggregate = {"business_id": normalized["business_id"], "intake_id": normalized["intake_id"],
        "reviewer": progress["receipts"][-1]["reviewer"], "note": "Completed immutable partial Human Review coverage.",
        "decisions": progress["decisions"], "constraint_decisions": progress["constraint_decisions"]}
    if progress["industry_review"] is not None:
        aggregate["industry_review"] = progress["industry_review"]
    return review_customer_facts(request=aggregate, pipeline_root=pipeline_root,
        reviewed_at=progress["receipts"][-1]["reviewed_at"], _progress=progress)


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

    normalized = {
        "business_id": business_id,
        "intake_id": intake_id,
        "reviewer": reviewer,
        "note": note,
        "decisions": normalize_decisions(decisions),
    }
    if request.get("industry_review") is not None:
        industry = request["industry_review"]
        from customer_intake_v1 import CUSTOMER_INDUSTRIES
        if not isinstance(industry, dict) or industry.get("decision") not in {"confirm", "uncertain"}:
            raise CustomerFactReviewError("INVALID_INDUSTRY_REVIEW", "Choose an industry or explicitly leave it uncertain.")
        value = industry.get("value")
        if industry["decision"] == "confirm" and value not in CUSTOMER_INDUSTRIES:
            raise CustomerFactReviewError("INVALID_INDUSTRY_REVIEW", "Use an existing industry option.")
        if industry["decision"] == "uncertain" and value is not None:
            raise CustomerFactReviewError("INVALID_INDUSTRY_REVIEW", "Uncertain industry cannot include a known value.")
        normalized["industry_review"] = {"decision": industry["decision"], "value": value}
    if "constraint_decisions" in request:
        from customer_constraints_v1 import normalize_decisions as normalize_constraints
        normalized["constraint_decisions"] = normalize_constraints(request["constraint_decisions"])
    return normalized


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
    industry_review: dict[str, Any] | None = None,
    constraint_decisions: list[dict[str, Any]] | None = None,
    candidate_sha: str | None = None,
    partial: bool = False,
) -> dict[str, Any]:
    decision_by_id = {item["candidate_id"]: item for item in decisions}

    reviewed_candidates: list[dict[str, Any]] = []

    for source in candidate_artifact.get("fact_candidates") or []:
        candidate = copy.deepcopy(source)

        candidate_id = str(candidate.get("fact_candidate_id") or "")

        if candidate.get("candidate_state") != "requires_review":
            reviewed_candidates.append(candidate)
            continue

        if partial and candidate_id not in decision_by_id:
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

    if industry_review is not None:
        if any(item.get("target_field") == "industry" for item in candidate_artifact.get("fact_candidates", [])):
            raise CustomerFactReviewError("INDUSTRY_CANDIDATE_ALREADY_EXISTS", "Review the original industry candidate instead.")
        confirmed = industry_review["decision"] == "confirm"
        reviewed_candidates.append({
            "fact_candidate_id": f"{intake['intake_id']}_human_industry",
            "persona_scope": "business", "target_field": "industry",
            "candidate_state": "known_candidate" if confirmed else "unknown",
            "normalized_value": industry_review.get("value") if confirmed else None,
            "confirmation_basis": "human_industry_confirmed" if confirmed else "human_industry_uncertain",
            "source_type": "explicit_human_classification", "source_excerpt": "运营在客户事实审核时明确选择；并非 AI 提取或前置输入。",
            "human_review": {"reviewer": reviewer, "reviewed_at": reviewed_at,
                "decision": industry_review["decision"], "human_gate": True},
        })

    from customer_constraints_v1 import apply_decisions as apply_constraints
    constraints = candidate_artifact.get("derived_authority_constraints") or []
    selected_constraints = constraints
    remaining_constraints = []
    if partial:
        selected_ids = {v["constraint_id"] for v in constraint_decisions or []}
        selected_constraints = [v for v in constraints if v["constraint_id"] in selected_ids]
        remaining_constraints = [copy.deepcopy(v) for v in constraints if v["constraint_id"] not in selected_ids]
    reviewed_constraints = apply_constraints(selected_constraints, constraint_decisions or [], intake=intake,
        candidate_sha=candidate_sha or canonical_sha256(candidate_artifact),
        reviewer=reviewer, reviewed_at=reviewed_at) if selected_constraints or constraint_decisions else []
    if partial:
        by_constraint = {v["constraint_id"]: v for v in reviewed_constraints + remaining_constraints}
        reviewed_constraints = [by_constraint[v["constraint_id"]] for v in constraints]
    reviewed = build_fact_candidate_artifact(
        intake,
        reviewed_candidates,
        created_at=reviewed_at,
        derived_authority_constraints=reviewed_constraints,
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

    result = {
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
    constraints = [copy.deepcopy(item) for _, artifact, _ in sources
        for item in artifact.get("derived_authority_constraints") or []]
    if constraints:
        from customer_constraints_v1 import CONTRACT_VERSION
        result["persona_control_layer"] = {"contract_version": CONTRACT_VERSION,
            "derived_authority_constraints": constraints}
        # Excluded claims never become usable Known Truth. Pending/core records
        # stay visible for readiness; do not invoke production before approval.
        from customer_constraints_v1 import policy
        rules = policy(constraints)
        for field, fact in result["facts"].items():
            if field in rules["excluded_fields"] or any(term in json.dumps(fact["value"], ensure_ascii=False) for term in rules["blocked_terms"]):
                fact.update(state="unknown", value=None)
    return result


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
    from customer_constraints_v1 import validate_control_layer
    blockers = list(readiness["blockers"])
    if validate_control_layer(persona_input)["blockers"] and "critical_constraints" not in blockers:
        blockers.append("critical_constraints")
    return blockers


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
    from customer_constraints_v1 import collect, policy, unresolved_legacy_constraints
    records = collect(pipeline_root, business_id)
    return [v["record"] for v in unresolved_legacy_constraints(pipeline_root, business_id, records)] + policy(records)["blockers"]


def ensure_or_build_business_persona(
    *,
    pipeline_root: Path,
    business_id: str,
    input_path: Path,
    created_at: str,
) -> tuple[Path, dict[str, Any]]:
    output_root = pipeline_root / "data" / "personas"

    source = read_json(input_path)
    revision = int(source.get("revision") or 1)
    from persona_review_lifecycle_v1 import candidate_path
    expected_path = candidate_path(output_root, source)

    if expected_path.is_file():
        persona = read_json(expected_path)

        provenance = persona.get("provenance") or {}

        if (
            persona.get("persona_id") != business_id
            or persona.get("persona_scope") != "business"
            or int(persona.get("revision") or 0) != revision
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
            previous_persona_path=(Path(source["previous_approved_persona_path"])
                if source.get("previous_approved_persona_path") else None),
        )
    except Exception as exc:
        raise CustomerFactReviewError(
            "BUSINESS_PERSONA_BUILD_FAILED",
            str(exc),
        ) from exc


def derive_business_persona_input(*, pipeline_root: Path, business_id: str,
        intake_root: Path, reviewed: dict[str, Any], proposed: bool = False):
    """One read-only derivation for the final preview and the existing writer.

    Proposed data is produced by the same Human decision validator, never an
    alternative runtime source or a trusted client assertion of approval.
    """
    intake_id = intake_root.name
    reviewed_path = intake_root / "reviewed_persona_fact_candidates_v1.json"
    reviewed_sources = reviewed_business_sources(
        pipeline_root,
        business_id,
    )

    from persona_review_lifecycle_v1 import effective_sources, apply_revision_input, replacement_fields
    if proposed:
        reviewed_sources = [v for v in reviewed_sources if v[0] != intake_id]
        reviewed_sources.append((intake_id, reviewed, reviewed_path))
        reviewed_sources.sort(key=lambda v: v[0])
    reviewed_sources = effective_sources(reviewed_sources)
    replacing = replacement_fields(intake_root, reviewed)

    persona_input = build_business_persona_input(
        business_id=business_id,
        intake_id=intake_id,
        reviewed_artifact=reviewed,
        reviewed_artifact_path=(reviewed_path),
        reviewed_sources=reviewed_sources,
    )
    apply_revision_input(pipeline_root, "business", business_id, intake_root, persona_input, reviewed)
    from customer_constraints_v1 import CONTRACT_VERSION, collect, policy, unresolved_legacy_constraints
    effective_constraints = collect(pipeline_root, business_id,
        proposed_review=(intake_id, reviewed) if proposed else None)
    if effective_constraints:
        persona_input["persona_control_layer"] = {"contract_version": CONTRACT_VERSION,
            "derived_authority_constraints": effective_constraints}

    # The existing approved resolver owns effective lineage. An additive intake
    # retains legacy approved facts even when they predate Console intake files.
    from show_customer_status_v1 import resolve_current_persona, AuthorityResolutionError
    try:
        current = resolve_current_persona(pipeline_root, business_id, "business")
    except AuthorityResolutionError as exc:
        if exc.code not in {"PERSONA_NOT_FOUND", "APPROVED_PERSONA_NOT_FOUND"}:
            raise CustomerFactReviewError(exc.code, "Approved Business lineage is invalid.") from exc
        current = None
    no_new_facts = False
    if current:
        original_facts = current["artifact"].get("facts") or {}
        for field, fact in original_facts.items():
            if field in replacing:
                continue
            if fact.get("state") != "known":
                continue
            added = persona_input["facts"].get(field)
            if added:
                added["value"] = merge_known_values([fact["value"], added["value"]], scalar=field in SCALAR_PERSONA_FIELDS)
                added["source_refs"] = list(dict.fromkeys([
                    *(fact.get("source_refs") or []), *(added.get("source_refs") or []),
                    f"approved_business_revision:{current['revision']}:{current['file_sha256']}#{field}",
                ]))
            else:
                persona_input["facts"][field] = copy.deepcopy(fact)
        old_values = {key: value.get("value") for key, value in original_facts.items() if value.get("state") == "known"}
        new_values = {key: value.get("value") for key, value in persona_input["facts"].items() if value.get("state") == "known"}
        no_new_facts = (old_values == new_values and
            current["artifact"].get("persona_control_layer") == persona_input.get("persona_control_layer"))
        persona_input["revision"] = int(current["revision"]) + 1
        persona_input["previous_approved_persona_path"] = str(current["path"])

    if effective_constraints:
        rules = policy(effective_constraints)
        for field, fact in persona_input["facts"].items():
            if fact.get("state") == "known" and (field in rules["excluded_fields"] or any(
                    term in json.dumps(fact.get("value"), ensure_ascii=False) for term in rules["blocked_terms"])):
                fact.update(state="unknown", value=None)

    blockers = required_business_blockers(
        persona_input,
        critical_constraints=([v["record"] for v in unresolved_legacy_constraints(
            pipeline_root, business_id, effective_constraints)] + policy(effective_constraints)["blockers"]),
    )

    return persona_input, blockers, no_new_facts


def review_customer_facts(
    *,
    request: dict[str, Any],
    pipeline_root: Path,
    reviewed_at: str | None = None,
    _progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if request.get("review_mode") == "resume":
        directory = pipeline_root / "data" / "customer_intakes" / request["business_id"] / request["intake_id"]
        state = read_review_progress(directory)
        if not state["complete"] or not state["receipts"] or state["receipts"][-1]["reviewer"] != request["reviewer"]:
            raise CustomerFactReviewError("INVALID_REVIEW_RECOVERY", "Only the submitting actor can resume completed durable coverage.")
        return save_review_progress(request=state["receipts"][-1]["request"], pipeline_root=pipeline_root)
    if request.get("review_mode") == "progress":
        return save_review_progress(request=request, pipeline_root=pipeline_root, reviewed_at=reviewed_at)
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
    if (intake_root / "review_progress").is_dir() and _progress is None:
        raise CustomerFactReviewError("FACT_REVIEW_USE_PROGRESS", "Append-only review decisions cannot be replaced by a legacy complete request.")

    candidate_sha = sha256_file(candidates_path)

    review_fingerprint = canonical_sha256(
        {
            "business_id": business_id,
            "intake_id": intake_id,
            "reviewer": request["reviewer"],
            "note": request["note"],
            "candidate_sha256": (candidate_sha),
            "decisions": request["decisions"],
            **({"industry_review": request["industry_review"]} if "industry_review" in request else {}),
            **({"constraint_decisions": request["constraint_decisions"]} if "constraint_decisions" in request else {}),
            **({"progress_version": _progress["version"]} if _progress else {}),
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

        # Detect contradictory scalar approvals before finalizing Human Review.
        # Preserve a conflict attempt, so a later explicit reject/correction can
        # resolve it without rewriting any finalized decision or Approved fact.
        preview = copy.deepcopy(_progress["artifact"]) if _progress else apply_human_decisions(intake=intake, candidate_artifact=candidate_artifact,
            decisions=request["decisions"], reviewer=request["reviewer"], reviewed_at=timestamp,
            industry_review=request.get("industry_review"), constraint_decisions=request.get("constraint_decisions"),
            candidate_sha=candidate_sha)
        historical = reviewed_business_sources(pipeline_root, business_id)
        from persona_review_lifecycle_v1 import effective_sources, replacement_fields
        historical = effective_sources(historical)
        replacement = replacement_fields(intake_root, preview)
        from show_customer_status_v1 import resolve_current_persona, AuthorityResolutionError
        try:
            approved = resolve_current_persona(pipeline_root, business_id, "business")
        except AuthorityResolutionError as exc:
            if exc.code not in {"PERSONA_NOT_FOUND", "APPROVED_PERSONA_NOT_FOUND"}:
                raise CustomerFactReviewError(exc.code, "Approved Business lineage is invalid.") from exc
            approved = None
        from persona_review_lifecycle_v1 import scalar_review_values
        for field, values in scalar_review_values(historical, preview, approved, replacement).items():
            try:
                if values:
                    merge_known_values(values, scalar=True)
            except CustomerFactReviewError:
                # Keep the atomic temporary path within Windows path limits.
                # Full identity stays in the artifact; a prefix collision fails
                # closed rather than hiding a distinct Human conflict attempt.
                path = intake_root / "fact_conflicts" / f"review_{review_fingerprint[:24]}.json"
                if path.exists() and read_json(path).get("review_fingerprint") != review_fingerprint:
                    raise CustomerFactReviewError("FACT_CONFLICT_RECORD_COLLISION", "Conflict evidence identity collision.")
                if not path.exists():
                    write_new_or_same(path, {"status": "awaiting_explicit_human_resolution", "field": field,
                        "review_fingerprint": review_fingerprint,
                        "reviewer": request["reviewer"], "attempted_at": timestamp,
                        "decisions": request["decisions"], "candidate_sha256": candidate_sha,
                        "approved_persona_sha256": approved["file_sha256"] if approved else None,
                        "authority": {"fact_review_finalized": False, "approved_truth_changed": False}})
                raise

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
            **({"industry_review": request["industry_review"]} if "industry_review" in request else {}),
            **({"constraint_decisions": request["constraint_decisions"]} if "constraint_decisions" in request else {}),
            **({"progress_version": _progress["version"]} if _progress else {}),
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

    reviewed = copy.deepcopy(_progress["artifact"]) if _progress else apply_human_decisions(
        intake=intake,
        candidate_artifact=(candidate_artifact),
        decisions=request["decisions"],
        reviewer=request["reviewer"],
        reviewed_at=timestamp,
        industry_review=request.get("industry_review"),
        constraint_decisions=request.get("constraint_decisions"), candidate_sha=candidate_sha,
    )

    reviewed_path = intake_root / ("reviewed_persona_" "fact_candidates_v1.json")

    write_new_or_same(
        reviewed_path,
        reviewed,
    )

    persona_input, blockers, no_new_facts = derive_business_persona_input(
        pipeline_root=pipeline_root, business_id=business_id, intake_root=intake_root, reviewed=reviewed)

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

    if no_new_facts:
        completed = {**existing_review, "status": "completed_no_new_facts",
            "artifacts": {"reviewed_candidates_v1": str(reviewed_path.resolve())},
            "authority": {**existing_review["authority"], "fact_review_completed": True,
                "business_persona_created": False, "persona_approved": False},
            "next_action": "NO_NEW_FACTS_EXISTING_APPROVAL_PRESERVED"}
        write_atomic_json(review_path, completed)
        return completed

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
                "authority": result.get("authority"),
                "saved_count": result.get("saved_count"),
                "pending_count": result.get("pending_count", 0),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
