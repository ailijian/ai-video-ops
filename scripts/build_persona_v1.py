from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "persona-v1.0"
BUILDER_VERSION = "build_persona_v1.py@0.1"
FACT_STATES = {"known", "unknown", "requires_review"}
FACT_FIELDS = (
    "public_display_name",
    "company_short_name",
    "industry",
    "years_in_business",
    "service_area",
    "business_address",
    "primary_products_or_services",
    "secondary_products_or_services",
    "core_audience",
    "customer_use_cases",
    "customer_pains",
    "differentiators",
    "selection_reasons",
    "brand_story",
    "founder_or_operator_story",
    "important_turning_points",
    "product_or_service_facts",
    "process_facts",
    "service_process",
    "authorized_customer_cases_or_feedback",
    "values",
    "beliefs",
    "tone_preferences",
    "unknown_facts",
    "forbidden_claims",
    "prohibited_topics",
    "information_requiring_human_review",
)
REQUIRED_KNOWN_FIELDS = (
    "industry",
    "primary_products_or_services",
    "core_audience",
    "customer_pains",
    "differentiators",
)
REQUIRED_IDENTITY_ALTERNATIVES = (
    "company_short_name",
    "public_display_name",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def normalize_fact(field: str, raw: Any) -> dict[str, Any]:
    if raw is None:
        return {
            "state": "unknown",
            "value": None,
            "source_refs": [],
            "review_note": None,
        }
    if not isinstance(raw, dict):
        raise RuntimeError(f"Persona fact {field!r} must be an authority record.")
    state = str(raw.get("state") or "").strip().lower()
    if state not in FACT_STATES:
        raise RuntimeError(f"Persona fact {field!r} has invalid state {state!r}.")
    value = raw.get("value")
    if state == "unknown":
        value = None
    elif not has_value(value):
        raise RuntimeError(f"Persona fact {field!r} requires a non-empty value.")
    source_refs = raw.get("source_refs") or []
    if not isinstance(source_refs, list):
        raise RuntimeError(f"Persona fact {field!r} source_refs must be a list.")
    review_note = raw.get("review_note")
    if state == "requires_review" and not str(review_note or "").strip():
        raise RuntimeError(f"Persona fact {field!r} requires a review_note.")
    return {
        "state": state,
        "value": value,
        "source_refs": [str(item) for item in source_refs],
        "review_note": str(review_note) if review_note is not None else None,
    }


def fact_is_known(persona: dict[str, Any], field: str) -> bool:
    fact = persona.get("facts", {}).get(field, {})
    return fact.get("state") == "known" and has_value(fact.get("value"))


def validate_required_fact_authority(persona: dict[str, Any]) -> list[str]:
    errors = [
        f"{field} must be KNOWN before approval."
        for field in REQUIRED_KNOWN_FIELDS
        if not fact_is_known(persona, field)
    ]
    if not any(fact_is_known(persona, field) for field in REQUIRED_IDENTITY_ALTERNATIVES):
        errors.append(
            "company_short_name or public_display_name must be KNOWN before approval."
        )
    return errors


def persona_content_hash(persona: dict[str, Any]) -> str:
    return canonical_sha256(
        {
            "persona_id": persona.get("persona_id"),
            "revision": persona.get("revision"),
            "facts": persona.get("facts", {}),
        }
    )


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    return sha256_bytes(payload)


def build_persona(
    input_path: Path,
    output_root: Path,
    previous_persona_path: Path | None = None,
    created_at: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    input_path = input_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    source = read_json(input_path)
    persona_id = str(source.get("persona_id") or "").strip()
    if not persona_id:
        raise RuntimeError("persona_id is required.")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in persona_id):
        raise RuntimeError("persona_id must be machine-safe.")
    revision = int(source.get("revision") or 1)
    if revision < 1:
        raise RuntimeError("Persona revision must be positive.")

    previous_ref: dict[str, Any] | None = None
    if previous_persona_path is not None:
        previous_path = previous_persona_path.expanduser().resolve()
        if not previous_path.is_file():
            raise FileNotFoundError(previous_path)
        previous = read_json(previous_path)
        if previous.get("persona_id") != persona_id:
            raise RuntimeError("Previous Persona ID does not match the new revision.")
        if previous.get("lifecycle", {}).get("status") != "approved":
            raise RuntimeError("Previous Persona revision must be Approved.")
        if revision != int(previous.get("revision") or 0) + 1:
            raise RuntimeError("New Persona revision must increment the Approved revision by one.")
        previous_ref = {
            "path": str(previous_path),
            "revision": previous.get("revision"),
            "sha256": sha256_file(previous_path),
            "content_sha256": previous.get("provenance", {}).get("content_sha256"),
        }
    elif revision != 1:
        raise RuntimeError("Revision greater than one requires --previous-persona.")

    raw_facts = source.get("facts") or {}
    if not isinstance(raw_facts, dict):
        raise RuntimeError("Persona input facts must be an object.")
    unknown_fields = sorted(set(raw_facts) - set(FACT_FIELDS))
    if unknown_fields:
        raise RuntimeError("Unknown Persona fields: " + ", ".join(unknown_fields))
    facts = {field: normalize_fact(field, raw_facts.get(field)) for field in FACT_FIELDS}
    states = {
        state: [field for field, fact in facts.items() if fact["state"] == state]
        for state in sorted(FACT_STATES)
    }
    timestamp = created_at or now_iso()
    persona: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "persona_id": persona_id,
        "revision": revision,
        "fixture_only": bool(source.get("fixture_only", False)),
        "lifecycle": {
            "status": "review_required",
            "approved": False,
            "retired": False,
            "human_review_required": True,
            "built_at": timestamp,
        },
        "facts": facts,
        "fact_authority": {
            "known_fields": states["known"],
            "unknown_fields": states["unknown"],
            "requires_review_fields": states["requires_review"],
            "generation_rule": "Only KNOWN facts may be used as client facts.",
            "unknown_facts_must_not_be_completed": True,
            "requires_review_facts_must_not_be_published_without_review": True,
            "case_facts_must_not_transfer": True,
        },
        "privacy": {
            "trusted_local_fact_authority": True,
            "external_model_egress_allowed_directly": False,
            "shared_privacy_projection_required_before_external_model": True,
            "private_contact_or_address_fields_are_not_automatically_egress_safe": True,
        },
        "revision_lineage": {
            "previous_approved_revision": previous_ref,
            "silent_overwrite_allowed": False,
        },
        "provenance": {
            "source_type": str(source.get("source_type") or "unspecified"),
            "source_file": source.get("source_file"),
            "source_ref": source.get("source_ref"),
            "input_path": str(input_path),
            "input_sha256": sha256_file(input_path),
            "created_at": timestamp,
            "builder_version": BUILDER_VERSION,
        },
        "validation": {
            "passed": True,
            "fact_states_valid": True,
            "unknown_values_are_null": all(
                facts[field]["value"] is None for field in states["unknown"]
            ),
            "required_fact_approval_blockers": [],
            "build_cannot_approve": True,
            "case_sources_consumed": False,
            "remote_model_call_performed": False,
        },
    }
    persona["validation"]["required_fact_approval_blockers"] = (
        validate_required_fact_authority(persona)
    )
    persona["provenance"]["content_sha256"] = persona_content_hash(persona)

    output_path = output_root / persona_id / f"revision_{revision:04d}" / "persona_v1.json"
    if output_path.exists():
        raise RuntimeError(
            "Persona revision already exists; Approved Persona revisions cannot be silently overwritten."
        )
    write_new_json(output_path, persona)
    return output_path, persona


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a review-required Persona Fact Authority V1."
    )
    parser.add_argument("--input", required=True, help="Persona input JSON.")
    parser.add_argument(
        "--previous-persona",
        default=None,
        help="Required for revision > 1; must reference the prior Approved Persona.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/personas",
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "personas"
    )
    output_path, persona = build_persona(
        Path(args.input),
        output_root,
        Path(args.previous_persona) if args.previous_persona else None,
    )
    print("PERSONA V1 BUILD PASS")
    print(f"Persona ID: {persona['persona_id']}")
    print(f"Revision: {persona['revision']}")
    print("Status: review_required")
    print(f"Fixture only: {persona['fixture_only']}")
    print(f"Content SHA-256: {persona['provenance']['content_sha256']}")
    print(f"Persona: {output_path}")


if __name__ == "__main__":
    main()
