from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "persona-v1.0"
BUILDER_VERSION = "build_persona_v1.py@0.3"
FACT_STATES = {"known", "unknown", "requires_review"}
PERSONA_SCOPES = {"business", "speaker"}
SPEAKER_TYPES = {"owner_founder", "frontline_expert", "brand", "generic"}
FACT_FIELDS = (
    "public_display_name",
    "company_short_name",
    "industry",
    "years_in_business",
    "service_area",
    "location_public_area",
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
    "pricing_facts",
    "included_service_facts",
    "process_facts",
    "service_process",
    "service_time_facts",
    "business_volume_fact",
    "time_efficiency_fact",
    "authorized_customer_cases_or_feedback",
    "values",
    "business_principles",
    "beliefs",
    "tone_preferences",
    "public_role",
    "speaker_role_facts",
    "first_person_allowed_topics",
    "first_person_forbidden_claims",
    "role_scope_constraints",
    "unknown_facts",
    "forbidden_claims",
    "prohibited_topics",
    "information_requiring_human_review",
)
REQUIRED_IDENTITY_ALTERNATIVES = (
    "company_short_name",
    "public_display_name",
)
BUSINESS_OFFERING_FIELDS = (
    "primary_products_or_services",
    "product_or_service_facts",
)
CUSTOMER_USE_CONTEXT_FIELDS = (
    "core_audience",
    "customer_use_cases",
    "customer_pains",
)
PRODUCTION_BEARING_FIELDS = (
    "product_or_service_facts",
    "pricing_facts",
    "included_service_facts",
    "process_facts",
    "service_process",
    "service_time_facts",
    "business_volume_fact",
    "time_efficiency_fact",
    "authorized_customer_cases_or_feedback",
    "differentiators",
    "selection_reasons",
    "customer_use_cases",
    "business_principles",
)
GENERIC_PRODUCTION_CLAIMS = {
    "很好",
    "我们很好",
    "非常好",
    "产品很好",
    "服务很好",
    "品质很好",
    "我们很专业",
    "专业",
    "优质",
    "高品质",
    "值得信赖",
    "客户至上",
}
SPEAKER_REQUIRED_KNOWN_FIELDS = (
    "public_display_name",
    "public_role",
    "speaker_role_facts",
    "first_person_allowed_topics",
    "first_person_forbidden_claims",
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


def _atomic_values(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return [item for value_item in value for item in _atomic_values(value_item)]
    if isinstance(value, dict):
        return [item for value_item in value.values() for item in _atomic_values(value_item)]
    return [value]


def _specific_production_value(value: Any) -> bool:
    for item in _atomic_values(value):
        if not has_value(item):
            continue
        if not isinstance(item, str):
            return True
        normalized = "".join(
            character for character in item.strip().casefold() if character.isalnum()
        )
        if normalized and normalized not in GENERIC_PRODUCTION_CLAIMS:
            return True
    return False


def assess_business_persona_capabilities(
    facts: dict[str, Any],
    *,
    critical_constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive minimum viable Business Persona readiness from KNOWN authority.

    This is deliberately capability based. UNKNOWN and REQUIRES_REVIEW facts
    remain outside the evidence set and no field-completion percentage is used.
    """

    known = {
        field: fact.get("value")
        for field, fact in facts.items()
        if isinstance(fact, dict)
        and fact.get("state") == "known"
        and has_value(fact.get("value"))
    }
    constraints = copy.deepcopy(critical_constraints or [])
    identity_evidence = sorted(set(known) & set(REQUIRED_IDENTITY_ALTERNATIVES))
    offering_evidence = sorted(set(known) & set(BUSINESS_OFFERING_FIELDS))
    context_evidence = sorted(set(known) & set(CUSTOMER_USE_CONTEXT_FIELDS))
    production_evidence = sorted(
        field
        for field in set(known) & set(PRODUCTION_BEARING_FIELDS)
        if _specific_production_value(known[field])
    )
    groups = {
        "business_identity": {
            "required": True,
            "satisfied": bool(identity_evidence and offering_evidence),
            "evidence_fields": identity_evidence + offering_evidence,
        },
        "customer_use_context": {
            "required": True,
            "satisfied": bool(context_evidence),
            "evidence_fields": context_evidence,
        },
        "production_bearing_facts": {
            "required": True,
            "satisfied": bool(production_evidence),
            "evidence_fields": production_evidence,
        },
        "critical_constraints": {
            "required": True,
            "satisfied": not constraints,
            "evidence_fields": [],
            "blocking_items": constraints,
        },
    }
    blockers = [
        name
        for name, group in groups.items()
        if group["required"] and not group["satisfied"]
    ]
    return {
        "ready": not blockers,
        "capability_groups": groups,
        "blockers": blockers,
        "known_fields": sorted(known),
        "field_completion_percentage_used": False,
    }


def validate_required_fact_authority(persona: dict[str, Any]) -> list[str]:
    if persona.get("persona_scope", "business") == "speaker":
        errors = [
            f"{field} must be KNOWN before Speaker Persona approval."
            for field in SPEAKER_REQUIRED_KNOWN_FIELDS
            if not fact_is_known(persona, field)
        ]
        if not isinstance(persona.get("business_persona_ref"), dict):
            errors.append("Speaker Persona requires an Approved Business Persona reference.")
        return errors
    readiness = assess_business_persona_capabilities(persona.get("facts") or {})
    return [
        f"{group} capability must be satisfied before approval."
        for group in readiness["blockers"]
    ]


def persona_content_hash(persona: dict[str, Any]) -> str:
    content = {
        "persona_id": persona.get("persona_id"),
        "revision": persona.get("revision"),
        "persona_scope": persona.get("persona_scope", "business"),
        "speaker_type": persona.get("speaker_type"),
        "business_persona_ref": persona.get("business_persona_ref"),
        "speaker_authority": persona.get("speaker_authority"),
        "facts": persona.get("facts", {}),
    }
    # This optional control-layer extension is deliberately excluded for legacy
    # Personas so their already-approved content hashes remain byte-for-byte valid.
    if "persona_control_layer" in persona:
        content["persona_control_layer"] = persona["persona_control_layer"]
    return canonical_sha256(content)


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    return sha256_bytes(payload)


def render_persona_review_pack(persona: dict[str, Any]) -> str:
    lines = [
        "# Persona V1 Human Review Pack",
        "",
        f"Persona ID: `{persona['persona_id']}`",
        f"Revision: `{persona['revision']}`",
        f"Scope: `{persona.get('persona_scope', 'business')}`",
        f"Status: `{persona['lifecycle']['status']}`",
    ]
    if persona.get("speaker_type"):
        lines.append(f"Speaker Type: `{persona['speaker_type']}`")
    if persona.get("business_persona_ref"):
        lines.append(
            "Business Persona Ref: `"
            + str(persona["business_persona_ref"].get("persona_id"))
            + "`"
        )
    for state, heading in (
        ("known", "KNOWN"),
        ("unknown", "UNKNOWN"),
        ("requires_review", "REQUIRES_REVIEW"),
    ):
        lines.extend(["", f"## {heading}", ""])
        selected = [
            (field, fact)
            for field, fact in persona.get("facts", {}).items()
            if fact.get("state") == state
        ]
        if not selected:
            lines.append("None.")
        for field, fact in selected:
            lines.append(f"### {field}")
            if state == "unknown":
                lines.append("`UNKNOWN: model must not complete`")
            else:
                lines.append("```json")
                lines.append(json.dumps(fact.get("value"), ensure_ascii=False, indent=2))
                lines.append("```")
            if fact.get("review_note"):
                lines.append(f"Review note: {fact['review_note']}")
            lines.append("")
    lines.extend(["## FORBIDDEN", ""])
    for field in ("forbidden_claims", "prohibited_topics", "first_person_forbidden_claims"):
        fact = persona.get("facts", {}).get(field, {})
        if fact.get("state") == "known":
            lines.append(f"### {field}")
            lines.append("```json")
            lines.append(json.dumps(fact.get("value"), ensure_ascii=False, indent=2))
            lines.append("```")
    if persona.get("persona_scope") == "speaker":
        lines.extend(["", "## Speaker can say", ""])
        lines.append(
            json.dumps(
                persona.get("facts", {}).get("first_person_allowed_topics", {}).get("value"),
                ensure_ascii=False,
                indent=2,
            )
        )
        if persona.get("persona_control_layer"):
            lines.extend(["", "## Derived Speaker Authority Constraints", ""])
            lines.append("```json")
            lines.append(
                json.dumps(
                    persona["persona_control_layer"],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            lines.append("```")
        lines.extend(["", "## Speaker cannot say", ""])
        lines.append(
            json.dumps(
                persona.get("facts", {}).get("first_person_forbidden_claims", {}).get("value"),
                ensure_ascii=False,
                indent=2,
            )
        )
    lines.extend(["", "Human approval is required before Production Matching.", ""])
    return "\n".join(lines)


def build_persona(
    input_path: Path,
    output_root: Path,
    previous_persona_path: Path | None = None,
    created_at: str | None = None,
    business_persona_path: Path | None = None,
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

    persona_scope = str(source.get("persona_scope") or "business").strip().lower()
    if persona_scope not in PERSONA_SCOPES:
        raise RuntimeError("Persona scope must be business or speaker.")
    speaker_type = source.get("speaker_type")
    business_ref: dict[str, Any] | None = None
    if persona_scope == "speaker":
        speaker_type = str(speaker_type or "").strip().lower()
        if speaker_type not in SPEAKER_TYPES:
            raise RuntimeError("Speaker Persona requires a valid speaker_type.")
        if business_persona_path is None:
            raise RuntimeError("Speaker Persona requires --business-persona.")
        business_path = business_persona_path.expanduser().resolve()
        business = read_json(business_path)
        lifecycle = business.get("lifecycle", {})
        if (
            business.get("persona_scope", "business") != "business"
            or lifecycle.get("status") != "approved"
            or lifecycle.get("approved") is not True
        ):
            raise RuntimeError("Speaker Persona must reference an Approved Business Persona.")
        expected_ref = source.get("business_persona_ref")
        expected_id = (
            expected_ref.get("persona_id")
            if isinstance(expected_ref, dict)
            else expected_ref
        )
        if expected_id != business.get("persona_id"):
            raise RuntimeError("Speaker business_persona_ref does not match the supplied Business Persona.")
        business_ref = {
            "persona_id": business.get("persona_id"),
            "revision": business.get("revision"),
            "path": str(business_path),
            "sha256": sha256_file(business_path),
            "content_sha256": business.get("provenance", {}).get("content_sha256"),
            "status": "approved",
        }
    elif speaker_type or source.get("business_persona_ref"):
        raise RuntimeError("Business Persona cannot declare Speaker-only authority fields.")

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
    persona_control_layer = source.get("persona_control_layer")
    if persona_control_layer is not None:
        if persona_scope != "speaker" or not isinstance(persona_control_layer, dict):
            raise RuntimeError(
                "persona_control_layer is an optional Speaker Persona control extension."
            )
        constraints = persona_control_layer.get("derived_authority_constraints")
        if not isinstance(constraints, list) or not constraints:
            raise RuntimeError(
                "Speaker persona_control_layer requires derived_authority_constraints."
            )
    persona: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "persona_id": persona_id,
        "revision": revision,
        "persona_scope": persona_scope,
        "speaker_type": speaker_type if persona_scope == "speaker" else None,
        "business_persona_ref": business_ref,
        "speaker_authority": (
            {
                "business_facts_copied": False,
                "first_person_claims_require_speaker_known_fact_or_allowed_topic": True,
                "business_facts_require_business_persona_lineage": True,
            }
            if persona_scope == "speaker"
            else None
        ),
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
            "persona_scope_valid": True,
            "speaker_business_facts_copied": False,
            "derived_authority_constraints_are_not_content_facts": True,
        },
    }
    if persona_control_layer is not None:
        persona["persona_control_layer"] = copy.deepcopy(persona_control_layer)
    persona["validation"]["required_fact_approval_blockers"] = (
        validate_required_fact_authority(persona)
    )
    persona["provenance"]["content_sha256"] = persona_content_hash(persona)

    output_path = output_root / persona_id / f"revision_{revision:04d}" / "persona_v1.json"
    review_path = output_path.parent / "persona_review_pack_v1.md"
    if output_path.exists() or review_path.exists():
        raise RuntimeError(
            "Persona revision already exists; Approved Persona revisions cannot be silently overwritten."
        )
    write_new_json(output_path, persona)
    review_path.write_text(render_persona_review_pack(persona), encoding="utf-8")
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
    parser.add_argument(
        "--business-persona",
        default=None,
        help="Required for persona_scope=speaker; must be an Approved Business Persona.",
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
        business_persona_path=(
            Path(args.business_persona) if args.business_persona else None
        ),
    )
    print("PERSONA V1 BUILD PASS")
    print(f"Persona ID: {persona['persona_id']}")
    print(f"Revision: {persona['revision']}")
    print("Status: review_required")
    print(f"Fixture only: {persona['fixture_only']}")
    print(f"Content SHA-256: {persona['provenance']['content_sha256']}")
    print(f"Persona: {output_path}")
    print(f"Review Pack: {output_path.parent / 'persona_review_pack_v1.md'}")


if __name__ == "__main__":
    main()
