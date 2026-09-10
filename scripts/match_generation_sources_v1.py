from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_persona_v1 import fact_is_known, persona_content_hash, sha256_file
from privacy_projection_v1 import validate_case_privacy_gate


PLAN_VERSION = "generation-source-plan-v1.0"
MATCHER_VERSION = "match_generation_sources_v1.py@0.1"
PROFILES = {"news", "mix"}
CONTENT_INTENTS = {
    "persona",
    "story",
    "trust",
    "process",
    "product",
    "conversion",
    "mixed",
}
PATTERN_POLICIES = {
    "pcv1_narration_led_process_projection": {
        "profiles": {"mix"},
        "requires_process_material": True,
        "requires_story_or_operator_context": True,
    }
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def known_value(persona: dict[str, Any], field: str) -> Any:
    if not fact_is_known(persona, field):
        return None
    return persona.get("facts", {}).get(field, {}).get("value")


def load_approved_persona(path: Path) -> tuple[dict[str, Any], str]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    persona = read_json(path)
    lifecycle = persona.get("lifecycle", {})
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        raise RuntimeError("Persona must be Approved before Matching.")
    content_sha = persona_content_hash(persona)
    if persona.get("provenance", {}).get("content_sha256") != content_sha:
        raise RuntimeError("Approved Persona content changed without a new revision.")
    return persona, sha256_file(path)


def load_request(path: Path, persona: dict[str, Any]) -> tuple[dict[str, Any], str]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    request = read_json(path)
    if request.get("schema_version") != "generation-request-v1.0":
        raise RuntimeError("Generation Request schema_version is invalid.")
    request_id = str(request.get("request_id") or "")
    if not request_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in request_id):
        raise RuntimeError("Generation Request request_id must be machine-safe.")
    if request.get("persona_id") != persona.get("persona_id"):
        raise RuntimeError("Generation Request Persona ID mismatch.")
    if int(request.get("persona_revision") or 0) != int(persona.get("revision") or 0):
        raise RuntimeError("Generation Request Persona revision mismatch.")
    if request.get("profile") not in PROFILES:
        raise RuntimeError("Generation Request profile is invalid.")
    if request.get("content_intent") not in CONTENT_INTENTS:
        raise RuntimeError("Generation Request content_intent is invalid.")
    quantity = int(request.get("quantity") or 0)
    if quantity <= 0:
        raise RuntimeError("Generation Request quantity must be positive.")
    if not str(request.get("platform") or "").strip():
        raise RuntimeError("Generation Request platform is required.")
    return request, sha256_file(path)


def load_patterns(paths: list[Path]) -> list[dict[str, Any]]:
    if not paths:
        raise RuntimeError("At least one Approved Pattern input is required.")
    patterns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        pattern = read_json(path)
        pattern_id = str(pattern.get("pattern_id") or "")
        if not pattern_id or pattern_id in seen:
            raise RuntimeError("Pattern IDs must be present and distinct.")
        if pattern.get("status") != "approved":
            raise RuntimeError(f"Pattern source {pattern_id} is not Approved.")
        if pattern.get("effectiveness", {}).get("status") != "unvalidated":
            raise RuntimeError("Production Foundation V1 expects unvalidated effectiveness authority.")
        seen.add(pattern_id)
        patterns.append(
            {
                "path": str(path),
                "sha256": sha256_file(path),
                "artifact": pattern,
            }
        )
    return sorted(patterns, key=lambda item: item["artifact"]["pattern_id"])


def load_cases_and_fingerprints(
    case_paths: list[Path], fingerprint_paths: list[Path]
) -> dict[str, dict[str, Any]]:
    if not case_paths or len(case_paths) != len(fingerprint_paths):
        raise RuntimeError("Approved Cases and Fingerprints must be non-empty and one-to-one.")
    cases: dict[str, dict[str, Any]] = {}
    for raw_path in case_paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        case = read_json(path)
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in cases:
            raise RuntimeError("Case IDs must be present and distinct.")
        lifecycle = case.get("lifecycle", {})
        if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
            raise RuntimeError(f"Case {case_id} is not Approved.")
        if case.get("validation", {}).get("passed") is not True:
            raise RuntimeError(f"Case {case_id} validation is not passed.")
        if isinstance(case.get("privacy_gate"), dict):
            validate_case_privacy_gate(case)
        cases[case_id] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "artifact": case,
        }

    fingerprints: dict[str, dict[str, Any]] = {}
    for raw_path in fingerprint_paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        fingerprint = read_json(path)
        case_id = str(fingerprint.get("case_id") or "")
        if case_id not in cases or case_id in fingerprints:
            raise RuntimeError("Fingerprint must map one-to-one to an Approved Case.")
        source_case = fingerprint.get("source_case", {})
        if source_case.get("status") != "approved" or source_case.get("approved") is not True:
            raise RuntimeError(f"Fingerprint {case_id} is not bound to an Approved Case.")
        if str(source_case.get("sha256") or "").lower() != cases[case_id]["sha256"]:
            raise RuntimeError(f"Fingerprint {case_id} source Case SHA-256 mismatch.")
        if fingerprint.get("pattern_mining_contract", {}).get("this_artifact_is_not_a_pattern") is not True:
            raise RuntimeError(f"Fingerprint {case_id} violates source authority.")
        fingerprints[case_id] = {
            "path": str(path),
            "sha256": sha256_file(path),
            "artifact": fingerprint,
        }
    if sorted(cases) != sorted(fingerprints):
        raise RuntimeError("Every Approved Case requires exactly one Fingerprint.")
    return {
        case_id: {
            "case": cases[case_id],
            "fingerprint": fingerprints[case_id],
        }
        for case_id in sorted(cases)
    }


def persona_capabilities(persona: dict[str, Any]) -> dict[str, bool]:
    return {
        "process_material_available": any(
            fact_is_known(persona, field)
            for field in ("process_facts", "service_process")
        ),
        "story_or_operator_context_available": any(
            fact_is_known(persona, field)
            for field in ("brand_story", "founder_or_operator_story")
        ),
        "product_or_service_facts_available": fact_is_known(
            persona, "product_or_service_facts"
        ),
    }


def pattern_eligibility(
    pattern: dict[str, Any], request: dict[str, Any], capabilities: dict[str, bool]
) -> tuple[bool, str]:
    pattern_id = pattern.get("pattern_id")
    policy = PATTERN_POLICIES.get(str(pattern_id))
    if policy is None:
        return False, "approved_pattern_has_no_v1_production_scope_policy"
    if request.get("profile") not in policy["profiles"]:
        return False, f"profile_{request.get('profile')}_outside_approved_pattern_scope"
    if policy["requires_process_material"] and not capabilities["process_material_available"]:
        return False, "persona_lacks_known_process_material"
    if policy["requires_story_or_operator_context"] and not capabilities["story_or_operator_context_available"]:
        return False, "persona_lacks_known_story_or_operator_context"
    return True, (
        "Approved mix-scope Pattern matches a narration-oriented operator/business-story "
        "Persona with KNOWN real process material."
    )


def normalize_industry(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "").replace("_", "")


def broad_industry(value: Any) -> str:
    normalized = normalize_industry(value)
    if any(term in normalized for term in ("餐饮", "bakery", "dessert", "food")):
        return "food"
    if any(term in normalized for term in ("绿植", "plant", "园艺")):
        return "plant_service"
    return normalized


def role_ratio(fingerprint: dict[str, Any], role: str) -> float:
    visual = fingerprint.get("visual_shot_features", {})
    count = float(visual.get("primary_role_counts", {}).get(role, 0))
    shots = float(visual.get("shot_count") or 0)
    return round(count / shots, 6) if shots else 0.0


def intent_compatibility(fingerprint: dict[str, Any], intent: str) -> float:
    action = role_ratio(fingerprint, "action")
    context = role_ratio(fingerprint, "context")
    product = role_ratio(fingerprint, "product")
    persona = role_ratio(fingerprint, "persona")
    if intent == "process":
        return action
    if intent == "product":
        return product
    if intent == "persona":
        return persona
    if intent == "story":
        return min(1.0, context + persona + action)
    if intent == "trust":
        return min(1.0, context + action + product)
    if intent == "conversion":
        return round(min(1.0, product + action), 6)
    return round(min(1.0, action + context + product + persona), 6)


def case_ranking(
    case_id: str,
    fingerprint: dict[str, Any],
    persona: dict[str, Any],
    request: dict[str, Any],
    pattern: dict[str, Any],
    capabilities: dict[str, bool],
) -> dict[str, Any]:
    persona_industry = known_value(persona, "industry")
    case_industry = fingerprint.get("identity", {}).get("industry")
    if normalize_industry(persona_industry) == normalize_industry(case_industry):
        industry_score = 1.0
    elif broad_industry(persona_industry) == broad_industry(case_industry):
        industry_score = 0.7
    else:
        industry_score = 0.0
    narration_ratio = float(
        fingerprint.get("narration_features", {}).get("speech_to_video_ratio") or 0
    )
    primary_roles = fingerprint.get("visual_shot_features", {}).get(
        "primary_role_counts", {}
    )
    components = {
        "industry_similarity": industry_score,
        "operator_business_story_compatibility": float(
            bool(fingerprint.get("structure_features", {}).get("audio_role"))
        ),
        "content_intent_compatibility": intent_compatibility(
            fingerprint, str(request.get("content_intent"))
        ),
        "persona_process_material_available": float(
            capabilities["process_material_available"]
        ),
        "persona_story_context_available": float(
            capabilities["story_or_operator_context_available"]
        ),
        "persona_presence_compatibility": 1.0 if primary_roles.get("persona", 0) else 0.5,
        "narration_oriented_structure": 1.0 if narration_ratio >= 0.5 else narration_ratio,
        "approved_pattern_supports_case": float(
            case_id in pattern.get("scope", {}).get("supported_case_ids", [])
        ),
    }
    score = round(sum(components.values()) / len(components), 6)
    return {
        "ranking_score": score,
        "ranking_components": components,
        "selection_reason": (
            "Approved Case/Fingerprint provides a structurally compatible reference; "
            "its client-specific facts remain non-transferable."
        ),
    }


def excluded_candidate_sources(paths: list[Path]) -> list[dict[str, Any]]:
    excluded: list[dict[str, Any]] = []
    for raw_path in paths:
        path = raw_path.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        candidate = read_json(path)
        pattern_id = str(candidate.get("pattern_id") or path.stem)
        excluded.append(
            {
                "source_id": pattern_id,
                "source_type": "pattern_candidate",
                "status": candidate.get("status"),
                "sha256": sha256_file(path),
                "reason": "Only Approved Patterns may enter Production Matching.",
            }
        )
        retained = candidate.get("research_disposition", {}).get(
            "retained_hypothesis"
        )
        if isinstance(retained, dict):
            excluded.append(
                {
                    "source_id": retained.get("hypothesis_id"),
                    "source_type": "research_hypothesis",
                    "status": retained.get("status"),
                    "reason": "Research Hypotheses are not Production Pattern authority.",
                }
            )
    return excluded


def build_source_plan(
    persona_path: Path,
    request_path: Path,
    pattern_paths: list[Path],
    case_paths: list[Path],
    fingerprint_paths: list[Path],
    candidate_source_paths: list[Path] | None = None,
) -> dict[str, Any]:
    persona_path = persona_path.expanduser().resolve()
    request_path = request_path.expanduser().resolve()
    persona, persona_sha = load_approved_persona(persona_path)
    request, request_sha = load_request(request_path, persona)
    patterns = load_patterns(pattern_paths)
    case_sources = load_cases_and_fingerprints(case_paths, fingerprint_paths)
    capabilities = persona_capabilities(persona)
    excluded = excluded_candidate_sources(candidate_source_paths or [])

    eligible_patterns: list[dict[str, Any]] = []
    for item in patterns:
        eligible, reason = pattern_eligibility(item["artifact"], request, capabilities)
        if eligible:
            eligible_patterns.append(item | {"eligibility_reason": reason})
        else:
            excluded.append(
                {
                    "source_id": item["artifact"].get("pattern_id"),
                    "source_type": "approved_pattern",
                    "status": "approved_but_not_eligible_for_request",
                    "sha256": item["sha256"],
                    "reason": reason,
                }
            )

    selected_patterns: list[dict[str, Any]] = []
    selected_cases: list[dict[str, Any]] = []
    eligible_case_pool: list[dict[str, Any]] = []
    if eligible_patterns:
        selected_pattern = eligible_patterns[0]
        pattern = selected_pattern["artifact"]
        selected_patterns = [
            {
                "pattern_id": pattern.get("pattern_id"),
                "approved_pattern_sha": selected_pattern["sha256"],
                "eligibility_reason": selected_pattern["eligibility_reason"],
                "effectiveness_status": pattern.get("effectiveness", {}).get("status"),
                "effectiveness_used_in_ranking": False,
            }
        ]
        supported_ids = set(pattern.get("scope", {}).get("supported_case_ids", []))
        for case_id, source in case_sources.items():
            if case_id not in supported_ids:
                excluded.append(
                    {
                        "source_id": case_id,
                        "source_type": "approved_case",
                        "reason": "Approved Case is outside the selected Pattern support lineage.",
                    }
                )
                continue
            fingerprint = source["fingerprint"]["artifact"]
            ranking = case_ranking(
                case_id, fingerprint, persona, request, pattern, capabilities
            )
            entry = {
                "case_id": case_id,
                "approved_case_sha": source["case"]["sha256"],
                "fingerprint_sha": source["fingerprint"]["sha256"],
                "ranking_score": ranking["ranking_score"],
                "ranking_components": ranking["ranking_components"],
                "selection_reason": ranking["selection_reason"],
            }
            eligible_case_pool.append(entry)
        eligible_case_pool.sort(
            key=lambda item: (-item["ranking_score"], item["case_id"])
        )
        selected_cases = list(eligible_case_pool)

    if request.get("profile") == "news" and not eligible_patterns:
        coverage_status = "insufficient"
        coverage_code = "research_coverage_insufficient"
        coverage_reason = (
            "No Approved News Pattern exists. The Approved mix Pattern cannot be used "
            "as a fallback for a News request."
        )
    elif eligible_patterns and selected_cases:
        coverage_status = "supported"
        coverage_code = "research_coverage_supported"
        coverage_reason = (
            "An Approved Pattern passes profile and Persona capability gates, with "
            "multiple Approved Case/Fingerprint references available for rotation."
        )
    else:
        coverage_status = "insufficient"
        coverage_code = "research_coverage_insufficient"
        coverage_reason = "No Approved Pattern and Case pool jointly pass all hard gates."

    known_fields = persona.get("fact_authority", {}).get("known_fields", [])
    unknown_fields = persona.get("fact_authority", {}).get("unknown_fields", [])
    review_fields = persona.get("fact_authority", {}).get(
        "requires_review_fields", []
    )
    return {
        "schema_version": PLAN_VERSION,
        "matcher_version": MATCHER_VERSION,
        "request_id": request.get("request_id"),
        "persona": {
            "persona_id": persona.get("persona_id"),
            "revision": persona.get("revision"),
            "persona_sha": persona_sha,
            "content_sha": persona.get("provenance", {}).get("content_sha256"),
            "status": "approved",
            "fixture_only": persona.get("fixture_only", False),
            "known_fact_fields": known_fields,
            "unknown_fact_fields": unknown_fields,
            "requires_review_fact_fields": review_fields,
            "fact_values_copied_to_plan": False,
        },
        "request": {
            "request_sha": request_sha,
            "profile": request.get("profile"),
            "quantity": request.get("quantity"),
            "platform": request.get("platform"),
            "content_intent": request.get("content_intent"),
            "cta_intent": request.get("cta_intent"),
            "constraints": request.get("constraints") or {},
        },
        "coverage": {
            "status": coverage_status,
            "code": coverage_code,
            "reason": coverage_reason,
        },
        "selected_patterns": selected_patterns,
        "eligible_case_pool": eligible_case_pool,
        "selected_cases": selected_cases,
        "rotation": {
            "case_rotation_enabled": len(eligible_case_pool) > 1,
            "case_rotation_order": [item["case_id"] for item in eligible_case_pool],
            "pattern_rotation_ready": True,
            "pattern_rotation_order": [
                item["pattern_id"] for item in selected_patterns
            ],
        },
        "excluded_sources": excluded,
        "generation_constraints": {
            "persona_facts_only": True,
            "known_persona_facts_only": True,
            "unknown_persona_facts_must_not_be_filled": True,
            "requires_review_facts_must_not_be_published_without_review": True,
            "case_facts_must_not_transfer": True,
            "effectiveness_claims_allowed": False,
            "pattern_scope_must_be_respected": True,
            "shared_privacy_gateway_required_before_future_remote_generation": True,
        },
        "ranking_policy": {
            "status": "provisional_v1_not_frozen",
            "deterministic": True,
            "performance_metrics_used": False,
            "effectiveness_used": False,
        },
        "authority": {
            "generation_not_started": True,
            "script_generation_performed": False,
            "remote_model_call_performed": False,
            "raw_whisper_read": False,
            "raw_visual_evidence_read": False,
            "candidate_case_read": False,
            "case_facts_used_as_persona_facts": False,
            "rejected_pattern_selected": False,
            "research_hypothesis_selected": False,
            "proof_reinterpreted": False,
        },
        "validation": {
            "passed": True,
            "persona_approved": True,
            "persona_content_sha_valid": True,
            "request_persona_revision_match": True,
            "approved_patterns_only": True,
            "approved_cases_only": True,
            "fingerprint_lineage_complete": True,
            "input_sha_lineage_complete": True,
            "research_coverage_gate_applied": True,
            "news_does_not_fallback_to_mix": not (
                request.get("profile") == "news" and selected_patterns
            ),
            "effectiveness_excluded_from_ranking": True,
            "remote_model_call_performed": False,
        },
    }


def write_source_plan(plan: dict[str, Any], output_root: Path) -> tuple[Path, str]:
    output_root = output_root.expanduser().resolve()
    output_path = (
        output_root
        / str(plan.get("request_id"))
        / "generation_source_plan_v1.json"
    )
    payload = json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        existing = output_path.read_bytes()
        if existing != payload:
            raise RuntimeError("Generation Source Plan exists with different deterministic content.")
        return output_path, hashlib.sha256(existing).hexdigest()
    with output_path.open("xb") as handle:
        handle.write(payload)
    return output_path, hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministically match an Approved Persona and Generation Request to "
            "Approved Patterns and Approved Case Fingerprints without generating content."
        )
    )
    parser.add_argument("--persona", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--pattern", action="append", required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--fingerprint", action="append", required=True)
    parser.add_argument("--candidate-source", action="append", default=[])
    parser.add_argument(
        "--output-root",
        default=None,
        help="Default: <project>/data/production_plans",
    )
    args = parser.parse_args()
    plan = build_source_plan(
        Path(args.persona),
        Path(args.request),
        [Path(value) for value in args.pattern],
        [Path(value) for value in args.case],
        [Path(value) for value in args.fingerprint],
        [Path(value) for value in args.candidate_source],
    )
    project_root = Path(__file__).resolve().parents[1]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "production_plans"
    )
    output_path, output_sha = write_source_plan(plan, output_root)
    print("GENERATION SOURCE MATCH V1 PASS")
    print(f"Request ID: {plan['request_id']}")
    print(f"Coverage: {plan['coverage']['code']}")
    print(f"Selected Patterns: {len(plan['selected_patterns'])}")
    print(f"Eligible Cases: {len(plan['eligible_case_pool'])}")
    print("Generation started: False")
    print("Remote model used: False")
    print(f"Plan SHA-256: {output_sha}")
    print(f"Plan: {output_path}")


if __name__ == "__main__":
    main()
