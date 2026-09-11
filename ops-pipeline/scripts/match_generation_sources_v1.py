from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_persona_v1 import fact_is_known, persona_content_hash, sha256_file
from privacy_projection_v1 import validate_case_privacy_gate
from production_profile_v1 import (
    COVERAGE_REPORT_SCHEMA_VERSION,
    pattern_compatibility_record,
    validate_registry,
    validate_target_profile,
)


PLAN_VERSION = "generation-source-plan-v1.0"
MATCHER_VERSION = "match_generation_sources_v1.py@1.0"
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


def load_approved_persona(
    path: Path, expected_scope: str = "business"
) -> tuple[dict[str, Any], str]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    persona = read_json(path)
    lifecycle = persona.get("lifecycle", {})
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        raise RuntimeError("Persona must be Approved before Matching.")
    if persona.get("persona_scope", "business") != expected_scope:
        raise RuntimeError(f"Matching expected a {expected_scope} Persona.")
    content_sha = persona_content_hash(persona)
    if persona.get("provenance", {}).get("content_sha256") != content_sha:
        raise RuntimeError("Approved Persona content changed without a new revision.")
    return persona, sha256_file(path)


def load_request(
    path: Path,
    persona: dict[str, Any],
    speaker_persona: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
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
    requested_speaker = request.get("speaker_persona")
    if requested_speaker:
        if speaker_persona is None:
            raise RuntimeError("Generation Request requires an Approved Speaker Persona.")
        if requested_speaker != speaker_persona.get("persona_id"):
            raise RuntimeError("Generation Request Speaker Persona ID mismatch.")
        if int(request.get("speaker_persona_revision") or 0) != int(
            speaker_persona.get("revision") or 0
        ):
            raise RuntimeError("Generation Request Speaker Persona revision mismatch.")
    elif speaker_persona is not None:
        raise RuntimeError("Speaker Persona supplied but not selected by Generation Request.")
    legacy_profile = request.get("profile")
    explicit_target = request.get("target_profile")
    if legacy_profile and explicit_target and legacy_profile != explicit_target:
        raise RuntimeError("Generation Request profile and target_profile conflict.")
    target_profile = explicit_target or legacy_profile
    if target_profile not in PROFILES:
        raise RuntimeError(
            "Generation Request target_profile must resolve to news or mix."
        )
    reuse_intent = request.get("reuse_intent") or "novel_content"
    if reuse_intent not in {"novel_content", "cross_profile_repurpose"}:
        raise RuntimeError("Generation Request reuse_intent is invalid.")
    if request.get("content_intent") not in CONTENT_INTENTS:
        raise RuntimeError("Generation Request content_intent is invalid.")
    quantity = int(request.get("quantity") or 0)
    if quantity <= 0:
        raise RuntimeError("Generation Request quantity must be positive.")
    if not str(request.get("platform") or "").strip():
        raise RuntimeError("Generation Request platform is required.")
    request = dict(request)
    request["target_profile"] = target_profile
    request.setdefault("profile", target_profile)
    request["reuse_intent"] = reuse_intent
    return request, sha256_file(path)


def load_profile_registry(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    registry = read_json(path)
    validate_registry(registry)
    return registry, sha256_file(path)


def load_compatibility_report(
    path: Path | None,
    registry_sha256: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        if registry_sha256 is not None:
            raise RuntimeError(
                "Canonical Profile Matching requires the Creative Coverage compatibility audit."
            )
        return None, None
    if registry_sha256 is None:
        raise RuntimeError("Creative Coverage compatibility audit requires a Profile Registry.")
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    report = read_json(path)
    if report.get("schema_version") != COVERAGE_REPORT_SCHEMA_VERSION:
        raise RuntimeError("Creative Coverage Report schema is invalid.")
    if (report.get("source_registry_ref") or {}).get("sha256") != registry_sha256:
        raise RuntimeError("Creative Coverage Report Registry SHA mismatch.")
    authority = report.get("authority") or {}
    if authority.get("can_change_compatibility") is not False:
        raise RuntimeError("Coverage Report incorrectly claims Compatibility authority.")
    return report, sha256_file(path)


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


def persona_capabilities(
    persona: dict[str, Any], speaker_persona: dict[str, Any] | None = None
) -> dict[str, bool]:
    return {
        "process_material_available": any(
            fact_is_known(persona, field)
            for field in ("process_facts", "service_process")
        ),
        "story_or_operator_context_available": any(
            fact_is_known(persona, field)
            for field in ("brand_story", "founder_or_operator_story")
        )
        or bool(
            speaker_persona
            and fact_is_known(speaker_persona, "speaker_role_facts")
        ),
        "product_or_service_facts_available": fact_is_known(
            persona, "product_or_service_facts"
        ),
    }


def pattern_eligibility(
    pattern: dict[str, Any],
    request: dict[str, Any],
    capabilities: dict[str, bool],
    registry: dict[str, Any] | None = None,
    pattern_sha256: str | None = None,
) -> tuple[bool, str]:
    pattern_id = pattern.get("pattern_id")
    target_profile = request.get("target_profile") or request.get("profile")
    if registry is not None:
        record = pattern_compatibility_record(
            registry,
            str(pattern_id),
            str(pattern_sha256 or ""),
        )
        if record is None:
            return False, "approved_pattern_has_no_canonical_profile_compatibility"
        if target_profile not in record.get("compatible_profiles", []):
            return False, f"profile_{target_profile}_outside_approved_pattern_compatibility"
    else:
        policy = PATTERN_POLICIES.get(str(pattern_id))
        if policy is None:
            return False, "approved_pattern_has_no_v1_production_scope_policy"
        if target_profile not in policy["profiles"]:
            return False, f"profile_{target_profile}_outside_approved_pattern_scope"
    policy = PATTERN_POLICIES.get(str(pattern_id))
    if policy is None:
        return False, "approved_pattern_has_no_v1_capability_policy"
    if policy["requires_process_material"] and not capabilities["process_material_available"]:
        return False, "persona_lacks_known_process_material"
    if policy["requires_story_or_operator_context"] and not capabilities["story_or_operator_context_available"]:
        return False, "persona_lacks_known_story_or_operator_context"
    if registry is not None:
        return True, (
            "Approved Pattern has canonical target-profile compatibility and matches "
            "the approved Persona capability policy."
        )
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
    speaker_persona_path: Path | None = None,
    profile_registry_path: Path | None = None,
    creative_coverage_report_path: Path | None = None,
) -> dict[str, Any]:
    persona_path = persona_path.expanduser().resolve()
    request_path = request_path.expanduser().resolve()
    persona, persona_sha = load_approved_persona(persona_path, "business")
    speaker_persona: dict[str, Any] | None = None
    speaker_sha: str | None = None
    resolved_speaker_path: Path | None = None
    if speaker_persona_path is not None:
        resolved_speaker_path = speaker_persona_path.expanduser().resolve()
        speaker_persona, speaker_sha = load_approved_persona(
            resolved_speaker_path, "speaker"
        )
        reference = speaker_persona.get("business_persona_ref") or {}
        if (
            reference.get("persona_id") != persona.get("persona_id")
            or int(reference.get("revision") or 0) != int(persona.get("revision") or 0)
            or reference.get("sha256") != persona_sha
        ):
            raise RuntimeError("Speaker Persona Business Persona lineage mismatch.")
    request, request_sha = load_request(request_path, persona, speaker_persona)
    registry, registry_sha = load_profile_registry(profile_registry_path)
    compatibility_report, compatibility_report_sha = load_compatibility_report(
        creative_coverage_report_path,
        registry_sha,
    )
    target_profile = str(request.get("target_profile"))
    profile_contract = (
        validate_target_profile(registry, target_profile)
        if registry is not None
        else None
    )
    patterns = load_patterns(pattern_paths)
    case_sources = load_cases_and_fingerprints(case_paths, fingerprint_paths)
    capabilities = persona_capabilities(persona, speaker_persona)
    excluded = excluded_candidate_sources(candidate_source_paths or [])

    eligible_patterns: list[dict[str, Any]] = []
    for item in patterns:
        eligible, reason = pattern_eligibility(
            item["artifact"],
            request,
            capabilities,
            registry,
            item["sha256"],
        )
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
    assessment_by_case = {
        item.get("case_id"): item
        for item in (
            (compatibility_report or {})
            .get("case_profile_compatibility_audit", {})
            .get("assessments", [])
        )
    }
    if eligible_patterns:
        selected_pattern = eligible_patterns[0]
        pattern = selected_pattern["artifact"]
        selected_pattern_profile_record = (
            pattern_compatibility_record(
                registry,
                str(pattern.get("pattern_id")),
                selected_pattern["sha256"],
            )
            if registry is not None
            else None
        )
        legacy_bridge_request_sha = str(
            (
                (selected_pattern_profile_record or {}).get("lineage") or {}
            ).get("real_mix_request_sha256")
            or ""
        )
        legacy_bridge_permitted = (
            target_profile == "mix"
            and bool(legacy_bridge_request_sha)
            and request_sha == legacy_bridge_request_sha
        )
        selected_patterns = [
            {
                "pattern_id": pattern.get("pattern_id"),
                "approved_pattern_sha": selected_pattern["sha256"],
                "eligibility_reason": selected_pattern["eligibility_reason"],
                "compatible_profiles": (
                    selected_pattern_profile_record.get("compatible_profiles", [])
                    if registry is not None
                    else sorted(PATTERN_POLICIES[str(pattern.get("pattern_id"))]["profiles"])
                ),
                "profile_compatibility_status": (
                    "approved_canonical_backfill"
                    if registry is not None
                    else "legacy_builtin_policy"
                ),
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
            compatibility_basis = "legacy_builtin_pattern_scope"
            compatibility_review_status = "legacy_not_profile_audited"
            approved_case_profile_compatibility = False
            if compatibility_report is not None:
                assessment = assessment_by_case.get(case_id)
                if not assessment:
                    excluded.append(
                        {
                            "source_id": case_id,
                            "source_type": "approved_case",
                            "reason": "Case has no Profile Compatibility assessment.",
                        }
                    )
                    continue
                approved_profiles = set(
                    assessment.get("approved_compatible_generation_profiles") or []
                )
                legacy_profiles = set(
                    (assessment.get("legacy_current_truth") or {}).get(
                        "compatible_profiles", []
                    )
                )
                if target_profile in approved_profiles:
                    compatibility_basis = "approved_profile_compatibility"
                    compatibility_review_status = "approved"
                    approved_case_profile_compatibility = True
                elif legacy_bridge_permitted and target_profile in legacy_profiles:
                    compatibility_basis = "legacy_current_truth_bridge"
                    compatibility_review_status = str(
                        assessment.get("review_status") or "review_required"
                    )
                else:
                    excluded.append(
                        {
                            "source_id": case_id,
                            "source_type": "approved_case",
                            "status": "profile_compatibility_not_approved",
                            "reason": (
                                f"Case is not approved compatible with target_profile "
                                f"{target_profile}; operator hint and observed profile are "
                                "not eligibility authority, and the legacy bridge is scoped "
                                "only to the frozen historical Request SHA."
                            ),
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
                "target_profile": target_profile,
                "profile_compatibility_basis": compatibility_basis,
                "profile_compatibility_review_status": compatibility_review_status,
                "approved_case_profile_compatibility": approved_case_profile_compatibility,
            }
            eligible_case_pool.append(entry)
        eligible_case_pool.sort(
            key=lambda item: (-item["ranking_score"], item["case_id"])
        )
        selected_cases = list(eligible_case_pool)

    if target_profile == "news" and not eligible_patterns:
        coverage_status = "insufficient"
        coverage_code = "research_coverage_insufficient"
        coverage_reason = (
            "No Approved News Pattern exists. The Approved mix Pattern cannot be used "
            "as a fallback for a News request."
        )
    elif eligible_patterns and selected_cases:
        coverage_status = "supported"
        coverage_code = "research_coverage_supported"
        if any(
            item.get("profile_compatibility_basis") == "legacy_current_truth_bridge"
            for item in selected_cases
        ):
            coverage_reason = (
                "The Approved Pattern passes canonical Mix Profile gates. Existing frozen "
                "Cases remain available through an explicit legacy current-truth bridge; "
                "their canonical Profile Compatibility still requires Human Review."
            )
        else:
            coverage_reason = (
                "An Approved Pattern and approved Profile-compatible Case pool pass all "
                "hard gates."
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
        "speaker_persona": (
            {
                "persona_id": speaker_persona.get("persona_id"),
                "revision": speaker_persona.get("revision"),
                "speaker_type": speaker_persona.get("speaker_type"),
                "speaker_sha": speaker_sha,
                "content_sha": speaker_persona.get("provenance", {}).get(
                    "content_sha256"
                ),
                "status": "approved",
                "business_persona_ref": speaker_persona.get(
                    "business_persona_ref"
                ),
                "fact_values_copied_to_plan": False,
                "path": str(resolved_speaker_path),
            }
            if speaker_persona
            else None
        ),
        "request": {
            "request_sha": request_sha,
            "profile": request.get("profile"),
            "target_profile": target_profile,
            "profile_resolution": (
                "explicit_target_profile"
                if request.get("target_profile")
                and read_json(request_path).get("target_profile")
                else "legacy_profile_field_resolved"
            ),
            "reuse_intent": request.get("reuse_intent"),
            "quantity": request.get("quantity"),
            "platform": request.get("platform"),
            "content_intent": request.get("content_intent"),
            "cta_intent": request.get("cta_intent"),
            "speaker_persona": request.get("speaker_persona"),
            "speaker_persona_revision": request.get("speaker_persona_revision"),
            "constraints": request.get("constraints") or {},
        },
        "coverage": {
            "status": coverage_status,
            "code": coverage_code,
            "reason": coverage_reason,
            "missing_creative_coverage": (
                (compatibility_report or {})
                .get("profiles", {})
                .get(target_profile, {})
                .get("major_gaps", [])
            ),
            "canonical_approved_compatible_case_count": sum(
                bool(item.get("approved_case_profile_compatibility"))
                for item in selected_cases
            ),
            "legacy_current_truth_bridge_case_count": sum(
                item.get("profile_compatibility_basis")
                == "legacy_current_truth_bridge"
                for item in selected_cases
            ),
            "legacy_bridge_scoped_to_historical_request_sha": True,
        },
        "production_profile_contract": {
            "mode": "canonical_registry" if registry is not None else "legacy_builtin_compatibility",
            "registry_schema_version": (
                registry.get("schema_version") if registry is not None else None
            ),
            "registry_sha256": registry_sha,
            "coverage_report_sha256": compatibility_report_sha,
            "target_profile": target_profile,
            "profile_status": profile_contract.get("status") if profile_contract else None,
            "script_shape": (
                profile_contract.get("script_contract", {}).get("shape")
                if profile_contract
                else None
            ),
            "storyboard_shape": (
                profile_contract.get("storyboard_contract", {}).get("shape")
                if profile_contract
                else None
            ),
            "export_contract_compatible": profile_contract is not None,
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
            "target_profile_must_be_resolved": True,
            "operator_profile_hint_cannot_grant_eligibility": True,
            "observed_source_profile_cannot_grant_eligibility": True,
            "new_cases_require_approved_profile_compatibility": registry is not None,
            "legacy_case_bridge_limited_to_frozen_current_truth": registry is not None,
            "shared_privacy_gateway_required_before_future_remote_generation": True,
            "speaker_overlay_authority_enforced": speaker_persona is not None,
            "speaker_cannot_inherit_unauthorized_business_facts": True,
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
            "speaker_business_facts_copied": False,
        },
        "validation": {
            "passed": True,
            "persona_approved": True,
            "persona_content_sha_valid": True,
            "speaker_persona_approved": speaker_persona is None
            or (
                speaker_persona.get("lifecycle", {}).get("status") == "approved"
                and speaker_persona.get("lifecycle", {}).get("approved") is True
            ),
            "speaker_business_lineage_valid": speaker_persona is None
            or speaker_persona.get("business_persona_ref", {}).get("sha256")
            == persona_sha,
            "request_persona_revision_match": True,
            "approved_patterns_only": True,
            "approved_cases_only": True,
            "fingerprint_lineage_complete": True,
            "input_sha_lineage_complete": True,
            "research_coverage_gate_applied": True,
            "news_does_not_fallback_to_mix": not (
                target_profile == "news" and selected_patterns
            ),
            "target_profile_registered": registry is None
            or target_profile in registry.get("profiles", {}),
            "profile_contract_compatible": registry is None
            or profile_contract is not None,
            "approved_pattern_profile_compatibility_applied": registry is None
            or all(
                target_profile in item.get("compatible_profiles", [])
                for item in selected_patterns
            ),
            "operator_profile_hint_used_for_eligibility": False,
            "observed_source_profile_used_as_approval": False,
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
    parser.add_argument("--speaker-persona")
    parser.add_argument("--request", required=True)
    parser.add_argument("--pattern", action="append", required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--fingerprint", action="append", required=True)
    parser.add_argument("--candidate-source", action="append", default=[])
    parser.add_argument("--profile-registry", required=True)
    parser.add_argument("--creative-coverage-report", required=True)
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
        Path(args.speaker_persona) if args.speaker_persona else None,
        Path(args.profile_registry),
        Path(args.creative_coverage_report),
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
