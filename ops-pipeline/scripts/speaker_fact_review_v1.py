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
    SPEAKER_REQUIRED_KNOWN_FIELDS,
    build_persona,
    sha256_file,
)
from customer_intake_v1 import (
    SCALAR_PERSONA_FIELDS,
    build_fact_candidate_artifact,
)
from speaker_onboarding_analysis_v1 import (
    load_approved_business_persona,
)

SCHEMA_VERSION = "speaker-fact-review-v1.0"

OPERATION_VERSION = "speaker_fact_review_v1.py@1.0"

DECISIONS = {
    "approve",
    "reject",
    "edit",
}


class SpeakerFactReviewError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
    ):
        super().__init__(message)
        self.code = code


def canonical_sha256(
    value: Any,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def read_json(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise SpeakerFactReviewError(
            "SPEAKER_ARTIFACT_NOT_FOUND",
            f"Missing artifact: {path}",
        )

    value = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(
        value,
        dict,
    ):
        raise SpeakerFactReviewError(
            "SPEAKER_ARTIFACT_INVALID",
            f"Invalid artifact: {path}",
        )

    return value


def write_atomic_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    os.replace(
        temporary,
        path,
    )


def write_new_or_same(
    path: Path,
    value: dict[str, Any],
) -> None:
    if path.exists():
        existing = read_json(path)

        if canonical_sha256(existing) != canonical_sha256(value):
            raise SpeakerFactReviewError(
                "SPEAKER_REVIEW_ARTIFACT_CONFLICT",
                ("Existing Speaker review " f"artifact differs: {path}"),
            )

        return

    write_atomic_json(
        path,
        value,
    )


def has_value(
    value: Any,
) -> bool:
    if value is None:
        return False

    if isinstance(
        value,
        str,
    ):
        return bool(value.strip())

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        return bool(value)

    return True


def normalize_decisions(
    decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []

    seen: set[str] = set()

    for raw in decisions:
        candidate_id = str(raw.get("candidate_id") or "").strip()

        decision = str(raw.get("decision") or "").strip().lower()

        if not candidate_id:
            raise SpeakerFactReviewError(
                "SPEAKER_DECISION_INVALID",
                "candidate_id is required.",
            )

        if candidate_id in seen:
            raise SpeakerFactReviewError(
                "SPEAKER_DECISION_DUPLICATE",
                ("Duplicate decision for " f"{candidate_id}."),
            )

        if decision not in DECISIONS:
            raise SpeakerFactReviewError(
                "SPEAKER_DECISION_INVALID",
                ("Unsupported decision: " f"{decision}"),
            )

        item = {
            "candidate_id": (candidate_id),
            "decision": decision,
            "note": str(raw.get("note") or "").strip(),
        }

        if decision == "edit":
            edited = copy.deepcopy(raw.get("edited_value"))

            if not has_value(edited):
                raise SpeakerFactReviewError(
                    "SPEAKER_EDIT_VALUE_REQUIRED",
                    ("edited_value is " f"required for {candidate_id}."),
                )

            item["edited_value"] = edited

        seen.add(candidate_id)

        result.append(item)

    result.sort(key=lambda item: (item["candidate_id"]))

    return result


def validate_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    values = {
        "business_id": str(request.get("business_id") or "").strip(),
        "speaker_id": str(request.get("speaker_id") or "").strip(),
        "intake_id": str(request.get("intake_id") or "").strip(),
        "reviewer": str(request.get("reviewer") or "").strip(),
        "note": str(request.get("note") or "").strip(),
    }

    for field in (
        "business_id",
        "speaker_id",
        "intake_id",
        "reviewer",
    ):
        if not values[field]:
            raise SpeakerFactReviewError(
                "SPEAKER_REVIEW_INVALID",
                f"{field} is required.",
            )

    decisions = request.get("decisions")

    if not isinstance(
        decisions,
        list,
    ):
        raise SpeakerFactReviewError(
            "SPEAKER_DECISIONS_REQUIRED",
            "decisions must be a list.",
        )

    values["decisions"] = normalize_decisions(decisions)

    return values


def validate_decision_coverage(
    candidate_artifact: dict[
        str,
        Any,
    ],
    decisions: list[dict[str, Any]],
) -> None:
    required_ids = {
        str(item.get("fact_candidate_id"))
        for item in (candidate_artifact.get("fact_candidates") or [])
        if item.get("candidate_state") == "requires_review"
    }

    supplied_ids = {item["candidate_id"] for item in decisions}

    missing = sorted(required_ids - supplied_ids)

    extra = sorted(supplied_ids - required_ids)

    if missing:
        raise SpeakerFactReviewError(
            "SPEAKER_REVIEW_INCOMPLETE",
            ("Missing Human decisions: " + ", ".join(missing)),
        )

    if extra:
        raise SpeakerFactReviewError(
            "SPEAKER_REVIEW_UNKNOWN_CANDIDATE",
            ("Unexpected candidate IDs: " + ", ".join(extra)),
        )


def apply_decisions(
    *,
    intake: dict[str, Any],
    candidate_artifact: dict[
        str,
        Any,
    ],
    decisions: list[dict[str, Any]],
    reviewer: str,
    reviewed_at: str,
) -> dict[str, Any]:
    decision_by_id = {item["candidate_id"]: item for item in decisions}

    reviewed: list[dict[str, Any]] = []

    for source in candidate_artifact.get("fact_candidates") or []:
        candidate = copy.deepcopy(source)

        if candidate.get("candidate_state") != "requires_review":
            reviewed.append(candidate)
            continue

        candidate_id = str(candidate["fact_candidate_id"])

        decision = decision_by_id[candidate_id]

        action = decision["decision"]

        candidate["human_review"] = {
            "decision": action,
            "reviewer": reviewer,
            "reviewed_at": (reviewed_at),
            "note": (decision.get("note") or ""),
            "human_gate": True,
        }

        if action == "approve":
            candidate["candidate_state"] = "known_candidate"

            candidate["confirmation_basis"] = "human_review_approved"

        elif action == "edit":
            candidate["candidate_state"] = "known_candidate"

            candidate["normalized_value"] = copy.deepcopy(decision["edited_value"])

            candidate["confirmation_basis"] = "human_review_edited"

        else:
            candidate["candidate_state"] = "unknown"

            candidate["normalized_value"] = None

            candidate["confirmation_basis"] = "human_review_rejected"

        candidate["review_note"] = decision.get("note") or (
            "Speaker Fact Candidate " "processed by Human Review."
        )

        reviewed.append(candidate)

    artifact = build_fact_candidate_artifact(
        intake,
        reviewed,
        created_at=reviewed_at,
        derived_authority_constraints=(
            candidate_artifact.get("derived_authority_constraints") or []
        ),
    )

    artifact["review"] = {
        "status": "completed",
        "reviewer": reviewer,
        "reviewed_at": (reviewed_at),
        "human_gate": True,
        "decisions": (copy.deepcopy(decisions)),
    }

    artifact["authority"].update(
        {
            "speaker_fact_review_completed": (True),
            "speaker_persona_approved": (False),
            "media_rights_established": (False),
            "business_facts_copied": (False),
        }
    )

    return artifact


def merge_values(
    values: list[Any],
    *,
    scalar: bool,
) -> Any:
    if not values:
        return None

    if scalar:
        fingerprints = {canonical_sha256(value) for value in values}

        if len(fingerprints) > 1:
            raise SpeakerFactReviewError(
                "SPEAKER_SCALAR_FACT_CONFLICT",
                ("Multiple values exist " "for one scalar Speaker field."),
            )

        return copy.deepcopy(values[-1])

    flattened: list[Any] = []

    for value in values:
        if isinstance(
            value,
            list,
        ):
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


def build_speaker_persona_input(
    *,
    business_id: str,
    speaker_id: str,
    speaker_type: str,
    intake_id: str,
    reviewed: dict[str, Any],
    reviewed_path: Path,
) -> dict[str, Any]:
    candidates = [
        item
        for item in (reviewed.get("fact_candidates") or [])
        if (
            item.get("persona_scope") == "speaker"
            and item.get("candidate_state") == "known_candidate"
        )
    ]

    fields = sorted(
        {
            str(item.get("target_field") or "")
            for item in candidates
            if item.get("target_field")
        }
    )

    facts: dict[
        str,
        Any,
    ] = {}

    for field in fields:
        selected = [item for item in candidates if item.get("target_field") == field]

        values = [
            item.get("normalized_value")
            for item in selected
            if has_value(item.get("normalized_value"))
        ]

        if not values:
            continue

        facts[field] = {
            "state": "known",
            "value": merge_values(
                values,
                scalar=(field in SCALAR_PERSONA_FIELDS),
            ),
            "source_refs": [
                (f"speaker_intake:" f"{intake_id}#" f"{item['fact_candidate_id']}")
                for item in selected
            ],
            "review_note": (
                "Built only from " "Human-reviewed Speaker " "Fact Candidates."
            ),
        }

    return {
        "persona_id": (speaker_id),
        "revision": 1,
        "persona_scope": ("speaker"),
        "speaker_type": (speaker_type),
        "business_persona_ref": {"persona_id": (business_id)},
        "fixture_only": False,
        "source_type": ("speaker_intake_" "human_fact_review"),
        "source_file": str(reviewed_path.resolve()),
        "source_ref": (f"speaker_intake:" f"{intake_id}"),
        "facts": facts,
    }


def speaker_blockers(
    persona_input: dict[
        str,
        Any,
    ],
) -> list[str]:
    facts = persona_input.get("facts") or {}

    return [
        field
        for field in (SPEAKER_REQUIRED_KNOWN_FIELDS)
        if (field not in facts or not has_value(facts[field].get("value")))
    ]


def ensure_or_build_persona(
    *,
    pipeline_root: Path,
    input_path: Path,
    business_persona_path: Path,
    speaker_id: str,
    created_at: str,
) -> tuple[
    Path,
    dict[str, Any],
]:
    output_root = pipeline_root / "data" / "personas"

    expected = output_root / speaker_id / "revision_0001" / "persona_v1.json"

    if expected.is_file():
        persona = read_json(expected)

        if (
            persona.get("persona_id") != speaker_id
            or persona.get("persona_scope") != "speaker"
            or (
                persona.get(
                    "provenance",
                    {},
                ).get("input_sha256")
                != sha256_file(input_path)
            )
        ):
            raise SpeakerFactReviewError(
                "SPEAKER_PERSONA_REVISION_CONFLICT",
                (
                    "Existing Speaker Persona "
                    "revision differs from "
                    "this reviewed intake."
                ),
            )

        return (
            expected,
            persona,
        )

    try:
        return build_persona(
            input_path,
            output_root,
            created_at=created_at,
            business_persona_path=(business_persona_path),
        )
    except Exception as exc:
        raise SpeakerFactReviewError(
            "SPEAKER_PERSONA_BUILD_FAILED",
            str(exc),
        ) from exc


def review_speaker_facts(
    *,
    request: dict[str, Any],
    pipeline_root: Path,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    request = validate_request(request)

    (
        business_path,
        business_persona,
    ) = load_approved_business_persona(
        pipeline_root,
        request["business_id"],
    )

    root = (
        pipeline_root
        / "data"
        / "speaker_intakes"
        / request["business_id"]
        / request["speaker_id"]
        / request["intake_id"]
    )

    intake_path = root / "speaker_intake_v1.json"

    candidates_path = root / ("speaker_fact_" "candidates_v1.json")

    intake = read_json(intake_path)

    candidates = read_json(candidates_path)

    business_ref = intake.get("business_ref") or {}

    if business_ref.get("persona_id") != request["business_id"] or business_ref.get(
        "revision"
    ) != business_persona.get("revision"):
        raise SpeakerFactReviewError(
            "SPEAKER_BUSINESS_LINEAGE_MISMATCH",
            ("Speaker Intake no longer " "matches the Approved " "Business Persona."),
        )

    validate_decision_coverage(
        candidates,
        request["decisions"],
    )

    fingerprint = canonical_sha256(
        {
            "business_id": (request["business_id"]),
            "speaker_id": (request["speaker_id"]),
            "intake_id": (request["intake_id"]),
            "reviewer": (request["reviewer"]),
            "decisions": (request["decisions"]),
            "candidate_sha256": (sha256_file(candidates_path)),
        }
    )

    review_path = root / "speaker_fact_review_v1.json"

    if review_path.is_file():
        existing = read_json(review_path)

        if existing.get("review_fingerprint") != fingerprint:
            raise SpeakerFactReviewError(
                "SPEAKER_REVIEW_ALREADY_FINALIZED",
                ("This Speaker Intake " "already has a different " "Human Review."),
            )

        if str(existing.get("status") or "").startswith("completed_"):
            return existing

        timestamp = str(existing.get("reviewed_at") or "")

    else:
        from datetime import (
            datetime,
            timezone,
        )

        timestamp = reviewed_at or datetime.now(timezone.utc).isoformat()

        existing = {
            "schema_version": (SCHEMA_VERSION),
            "operation_version": (OPERATION_VERSION),
            "business_id": (request["business_id"]),
            "speaker_id": (request["speaker_id"]),
            "intake_id": (request["intake_id"]),
            "status": ("review_in_progress"),
            "review_fingerprint": (fingerprint),
            "reviewer": (request["reviewer"]),
            "reviewed_at": (timestamp),
            "note": (request["note"]),
            "decisions": (copy.deepcopy(request["decisions"])),
            "authority": {
                "human_gate": True,
                "speaker_persona_approved": (False),
                "media_rights_established": (False),
            },
        }

        write_atomic_json(
            review_path,
            existing,
        )

    reviewed = apply_decisions(
        intake=intake,
        candidate_artifact=(candidates),
        decisions=request["decisions"],
        reviewer=request["reviewer"],
        reviewed_at=timestamp,
    )

    reviewed_path = root / ("reviewed_speaker_" "fact_candidates_v1.json")

    write_new_or_same(
        reviewed_path,
        reviewed,
    )

    speaker_type = str(
        intake.get(
            "speaker_selection",
            {},
        ).get("speaker_type")
        or ""
    )

    persona_input = build_speaker_persona_input(
        business_id=request["business_id"],
        speaker_id=request["speaker_id"],
        speaker_type=(speaker_type),
        intake_id=request["intake_id"],
        reviewed=reviewed,
        reviewed_path=(reviewed_path),
    )

    blockers = speaker_blockers(persona_input)

    if blockers:
        completed = {
            **existing,
            "status": ("completed_persona_blocked"),
            "artifacts": {
                "reviewed_candidates_v1": (str(reviewed_path.resolve())),
            },
            "speaker_persona_blockers": (blockers),
            "authority": {
                **existing["authority"],
                "speaker_fact_review_completed": (True),
                "speaker_persona_created": (False),
            },
            "next_action": ("COLLECT_MORE_SPEAKER_TRUTH"),
        }

        write_atomic_json(
            review_path,
            completed,
        )

        return completed

    input_path = root / "speaker_persona_input_v1.json"

    write_new_or_same(
        input_path,
        persona_input,
    )

    (
        persona_path,
        persona,
    ) = ensure_or_build_persona(
        pipeline_root=(pipeline_root),
        input_path=input_path,
        business_persona_path=(business_path),
        speaker_id=request["speaker_id"],
        created_at=timestamp,
    )

    lifecycle = persona.get("lifecycle") or {}

    completed = {
        **existing,
        "status": ("completed_persona_review_required"),
        "artifacts": {
            "reviewed_candidates_v1": (str(reviewed_path.resolve())),
            "speaker_persona_input_v1": (str(input_path.resolve())),
            "speaker_persona_v1": (str(persona_path.resolve())),
        },
        "speaker_persona": {
            "persona_id": (persona.get("persona_id")),
            "revision": (persona.get("revision")),
            "status": (lifecycle.get("status")),
            "approved": (lifecycle.get("approved") is True),
            "required_fact_approval_blockers": (
                persona.get(
                    "validation",
                    {},
                ).get(
                    "required_fact_approval_blockers",
                    [],
                )
            ),
        },
        "authority": {
            **existing["authority"],
            "speaker_fact_review_completed": (True),
            "speaker_persona_created": (True),
            "speaker_persona_approved": (lifecycle.get("approved") is True),
            "media_rights_established": (False),
            "business_facts_copied": (False),
        },
        "next_action": ("REVIEW_SPEAKER_PERSONA"),
    }

    write_atomic_json(
        review_path,
        completed,
    )

    return completed


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Apply Human decisions to "
            "Speaker Fact Candidates and "
            "build a review-required "
            "Speaker Persona."
        )
    )

    parser.add_argument(
        "--review",
        required=True,
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
        result = review_speaker_facts(
            request=request,
            pipeline_root=(pipeline_root),
        )

    except SpeakerFactReviewError as exc:
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
                "business_id": (result["business_id"]),
                "speaker_id": (result["speaker_id"]),
                "status": (result["status"]),
                "next_action": (result["next_action"]),
                "blockers": (
                    result.get(
                        "speaker_persona_blockers",
                        [],
                    )
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
