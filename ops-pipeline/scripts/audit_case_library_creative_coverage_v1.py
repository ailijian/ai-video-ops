"""Read-only Existing Case Library -> Creative Coverage audit.

This operation reads approved library authorities and writes only a sanitized
diagnostic report to an operator-selected directory outside canonical data.
It cannot approve a Case/Pattern, change compatibility, or call a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "existing-case-library-creative-coverage-audit-v1.0"

CAPABILITY_REQUIREMENTS = {
    "pcv1_narration_led_process_projection": [
        "KNOWN process_facts OR service_process",
        "KNOWN brand_story OR founder_or_operator_story OR approved Speaker role facts",
    ],
    "pcv1_news_price_offer_led_micro_information": [
        "News target profile",
        "primary Authority-supported pricing or offer fact",
    ],
    "pcv1_news_scene_contrast": [
        "News target profile",
        "Approved recoverable State A / State B correspondence",
    ],
}

MIX_DIMENSIONS = {
    "service_explanation": "pcv1_narration_led_process_projection",
    "process": "pcv1_narration_led_process_projection",
    "founder_person_story": None,
    "trust_differentiator": None,
    "faq_question_answer": None,
    "customer_use_scenario": None,
    "conversion": None,
    "boundary_misconception": None,
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON authority must be an object: {path}")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_values(values: list[str | None]) -> dict[str, int]:
    return dict(sorted(Counter(value or "unknown" for value in values).items()))


def source_case_sha(fingerprint: dict[str, Any]) -> str:
    return str(
        fingerprint.get("source_case_sha256")
        or (fingerprint.get("source_case") or {}).get("sha256")
        or (fingerprint.get("provenance") or {}).get("approved_case_sha256")
        or ""
    )


def fingerprint_preserves_pattern_boundary(fingerprint: dict[str, Any]) -> bool:
    contract = fingerprint.get("pattern_mining_contract") or {}
    if contract.get("this_artifact_is_not_a_pattern") is True:
        return True
    return (
        fingerprint.get("fingerprint_scope") == "case_structural_evidence_only"
        and (fingerprint.get("pattern_state") or {}).get("pattern_created") is False
    )


def load_master_approvals(data_root: Path) -> tuple[dict[str, dict], dict[str, Any]]:
    path = (
        data_root
        / "production_profiles"
        / "approvals"
        / "production_profile_compatibility_approval_v1.json"
    )
    if not path.is_file():
        return {}, {}
    artifact = read_json(path)
    return {
        str(item.get("case_id")): {
            **item,
            "_canonical_parent_status": artifact.get("status"),
        }
        for item in artifact.get("case_profile_compatibility_approvals") or []
        if item.get("case_id")
    }, artifact.get("pattern_profile_compatibility_approval") or {}


def load_coverage_assessments(data_root: Path) -> dict[str, dict[str, Any]]:
    path = data_root / "creative_coverage" / "creative_coverage_report_v1.json"
    if not path.is_file():
        return {}
    report = read_json(path)
    return {
        str(item.get("case_id")): item
        for item in (
            (report.get("case_profile_compatibility_audit") or {}).get(
                "assessments"
            )
            or []
        )
        if item.get("case_id")
    }


def compatibility_for_case(
    case_path: Path,
    case_sha: str,
    fingerprint_path: Path,
    master: dict[str, dict],
) -> dict[str, Any]:
    case_id = case_path.parent.name
    local_path = case_path.parent / "case_profile_compatibility_approval_v1.json"
    artifact = read_json(local_path) if local_path.is_file() else master.get(case_id) or {}
    approved_profiles = list(
        artifact.get("approved_compatible_generation_profiles") or []
    )
    source_ref = artifact.get("source_approved_case_ref") or {}
    fingerprint_ref = artifact.get("fingerprint_ref") or {}
    lineage_valid = bool(artifact) and (
        artifact.get("status") == "approved"
        or artifact.get("_canonical_parent_status") == "approved"
    )
    if source_ref:
        lineage_valid = lineage_valid and source_ref.get("sha256") == case_sha
    if fingerprint_ref:
        lineage_valid = lineage_valid and fingerprint_ref.get("sha256") == sha256_file(
            fingerprint_path
        )
    return {
        "approval_present": bool(artifact),
        "approval_source": (
            "case_sidecar" if local_path.is_file() else "canonical_master_approval"
            if artifact
            else None
        ),
        "approved_compatible_profiles": approved_profiles if lineage_valid else [],
        "lineage_valid": lineage_valid,
        "observed_source_profile": artifact.get("observed_source_profile"),
        "decision": artifact.get("decision"),
    }


def case_inventory(data_root: Path) -> list[dict[str, Any]]:
    master, _ = load_master_approvals(data_root)
    assessments = load_coverage_assessments(data_root)
    rows: list[dict[str, Any]] = []
    for case_path in sorted((data_root / "cases").glob("*/case_v1.json")):
        case = read_json(case_path)
        case_id = str(case.get("case_id") or case_path.parent.name)
        lifecycle = case.get("lifecycle") or {}
        approved = lifecycle.get("status") == "approved" and lifecycle.get("approved") is True
        case_sha = sha256_file(case_path)
        fingerprint_path = (
            data_root / "fingerprints" / case_id / "case_fingerprint_v1.json"
        )
        fingerprint = read_json(fingerprint_path) if fingerprint_path.is_file() else {}
        fingerprint_valid = bool(fingerprint) and (
            str(fingerprint.get("case_id") or "") == case_id
            and source_case_sha(fingerprint) == case_sha
            and fingerprint_preserves_pattern_boundary(fingerprint)
        )
        compatibility = (
            compatibility_for_case(
                case_path,
                case_sha,
                fingerprint_path,
                master,
            )
            if fingerprint_path.is_file()
            else {
                "approval_present": False,
                "approved_compatible_profiles": [],
                "lineage_valid": False,
            }
        )
        assessment = assessments.get(case_id) or {}
        identity = case.get("identity") or {}
        rows.append(
            {
                "case_id": case_id,
                "approved": approved,
                "case_sha256": case_sha,
                "fingerprint_present": fingerprint_path.is_file(),
                "fingerprint_valid": fingerprint_valid,
                "fingerprint_sha256": (
                    sha256_file(fingerprint_path) if fingerprint_path.is_file() else None
                ),
                "operator_profile_hint": assessment.get("operator_profile_hint"),
                "observed_source_profile": (
                    compatibility.get("observed_source_profile")
                    or assessment.get("observed_source_profile")
                    or fingerprint.get("production_profile")
                    or identity.get("analysis_profile")
                ),
                "approved_compatible_profiles": compatibility.get(
                    "approved_compatible_profiles"
                )
                or [],
                "compatibility_approval_present": compatibility.get(
                    "approval_present"
                ),
                "compatibility_lineage_valid": compatibility.get("lineage_valid"),
                "compatibility_approval_source": compatibility.get("approval_source"),
                "structural": structural_projection(fingerprint),
            }
        )
    return rows


def structural_projection(fingerprint: dict[str, Any]) -> dict[str, Any]:
    narration = fingerprint.get("narration_features") or {}
    visual = fingerprint.get("visual_shot_features") or {}
    audio_visual = fingerprint.get("audio_visual_features") or {}
    structure = fingerprint.get("structure_features") or {}
    semantic = fingerprint.get("semantic_carrier_features") or {}
    return {
        "production_profile": fingerprint.get("production_profile"),
        "carrier_type": semantic.get("carrier_type"),
        "role_sequence": semantic.get("role_sequence") or [],
        "structure_signature": structure.get("structure_signature"),
        "speech_to_video_ratio": narration.get("speech_to_video_ratio"),
        "shot_count": visual.get("shot_count") or semantic.get("micro_beat_count"),
        "primary_role_counts": visual.get("primary_role_counts") or {},
        "separate_audio_visual_tracks": audio_visual.get(
            "narration_and_shots_are_separate_tracks"
        ),
        "shot_to_narration_cardinality": audio_visual.get(
            "shot_to_narration_cardinality"
        ),
        "text_visual_relationship": (
            fingerprint.get("visual_state_features") or {}
        ).get("text_visual_relationship"),
    }


def pattern_inventory(data_root: Path) -> list[dict[str, Any]]:
    _, master_pattern_approval = load_master_approvals(data_root)
    use_count: Counter[str] = Counter()
    for path in (data_root / "production_plans").glob(
        "*/generation_source_plan_v1.json"
    ):
        try:
            plan = read_json(path)
        except Exception:
            continue
        for item in plan.get("selected_patterns") or []:
            if item.get("pattern_id"):
                use_count[str(item["pattern_id"])] += 1

    rows: list[dict[str, Any]] = []
    for pattern_path in sorted(
        (data_root / "patterns" / "approved").glob("*/pattern_v1.json")
    ):
        pattern = read_json(pattern_path)
        pattern_id = str(pattern.get("pattern_id") or pattern_path.parent.name)
        receipt_path = pattern_path.parent / "approval_receipt.json"
        receipt = read_json(receipt_path) if receipt_path.is_file() else {}
        compatible_profiles = list(pattern.get("compatible_profiles") or [])
        if not compatible_profiles and master_pattern_approval.get("pattern_id") == pattern_id:
            compatible_profiles = list(
                master_pattern_approval.get("compatible_profiles") or []
            )
        rows.append(
            {
                "pattern_id": pattern_id,
                "approved": pattern.get("status") == "approved",
                "compatible_profiles": compatible_profiles,
                "supported_case_ids": list(
                    (pattern.get("scope") or {}).get("supported_case_ids") or []
                ),
                "production_capability_requirements": CAPABILITY_REQUIREMENTS.get(
                    pattern_id, ["No V1 production matching policy registered"]
                ),
                "human_approval_present": receipt_path.is_file()
                and (
                    receipt.get("status") == "approved"
                    or receipt.get("decision") == "approved"
                    or receipt.get("human_gate") is True
                ),
                "case_count": len(
                    (pattern.get("scope") or {}).get("supported_case_ids") or []
                ),
                "current_production_use_count": use_count[pattern_id],
                "pattern_sha256": sha256_file(pattern_path),
            }
        )
    return rows


def recurring_signals(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in cases:
        if not item["approved"] or not item["fingerprint_valid"]:
            continue
        structural = item["structural"]
        if structural.get("carrier_type"):
            signals[f"carrier::{structural['carrier_type']}"] .append(item)
        if structural.get("separate_audio_visual_tracks") is True and structural.get(
            "shot_to_narration_cardinality"
        ) == "many_to_many":
            signals["narration_many_to_many_visual_projection"].append(item)
        ratio = structural.get("speech_to_video_ratio")
        role_counts = structural.get("primary_role_counts") or {}
        if isinstance(ratio, (int, float)) and ratio >= 0.5 and role_counts.get(
            "action", 0
        ):
            signals["narration_over_real_action_or_process"].append(item)
        signature = structural.get("structure_signature")
        if signature and "hook" in signature and "payoff" in signature:
            signals["hook_to_payoff_progression"].append(item)
        relationship = structural.get("text_visual_relationship")
        if relationship:
            signals[f"text_visual::{relationship}"].append(item)

    result: list[dict[str, Any]] = []
    for signal, items in sorted(signals.items()):
        if len(items) < 2:
            continue
        result.append(
            {
                "signal": signal,
                "case_ids": [item["case_id"] for item in items],
                "evidence_count": len(items),
                "structural_commonality": signal.replace("::", ": "),
                "major_differences": {
                    "structure_signatures": sorted(
                        {
                            item["structural"].get("structure_signature") or "not_recorded"
                            for item in items
                        }
                    ),
                    "shot_counts": sorted(
                        {
                            item["structural"].get("shot_count")
                            for item in items
                            if item["structural"].get("shot_count") is not None
                        }
                    ),
                },
                "research_confidence": "medium" if len(items) >= 3 else "low",
                "authority": "STRUCTURAL_SIGNAL_ONLY_NOT_PATTERN",
            }
        )
    return result


def research_candidates(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unresolved_mix = [
        item
        for item in cases
        if item["approved"]
        and item["fingerprint_valid"]
        and item["observed_source_profile"] in {"mix", None}
        and "mix" not in item["approved_compatible_profiles"]
    ]
    if len(unresolved_mix) < 2:
        return []
    return [
        {
            "candidate_id": "mix_service_value_real_interaction_research",
            "status": "RESEARCH_CANDIDATE_ONLY",
            "why_research_worthy": (
                "At least two approved structural fingerprints combine narration with "
                "real service/customer interaction, outside current Pattern support lineage."
            ),
            "supporting_case_ids": [item["case_id"] for item in unresolved_mix],
            "structural_evidence": [
                {
                    "case_id": item["case_id"],
                    "signature": item["structural"].get("structure_signature"),
                    "speech_to_video_ratio": item["structural"].get(
                        "speech_to_video_ratio"
                    ),
                    "roles": item["structural"].get("primary_role_counts"),
                }
                for item in unresolved_mix
            ],
            "what_is_still_missing": [
                "Human-approved Mix profile compatibility for each Case",
                "Cross-case research proving a shared invariant beyond topic similarity",
                "Explicit distinction from the approved process-projection Pattern",
            ],
            "what_would_falsify_it": (
                "Human review finds the commonality is only service topic/brand sentiment "
                "and not a reusable structural sequence."
            ),
            "potential_content_jobs_covered": [
                "trust_differentiator",
                "customer_use_scenario",
            ],
            "research_confidence": "low",
        }
    ]


def current_request_mapping(data_root: Path, request_id: str | None) -> dict[str, Any]:
    known_fields: set[str] = set()
    request: dict[str, Any] = {}
    if request_id:
        request_path = (
            data_root / "generation_requests" / request_id / "generation_request_v1.json"
        )
        if request_path.is_file():
            request = read_json(request_path)
            persona_ref = (request.get("lineage") or {}).get("business_persona_ref") or {}
            raw_path = persona_ref.get("path")
            if raw_path:
                persona_path = Path(str(raw_path))
                if persona_path.is_file():
                    persona = read_json(persona_path)
                    known_fields = set(
                        (persona.get("fact_authority") or {}).get("known_fields") or []
                    )
                    if not known_fields:
                        known_fields = {
                            key
                            for key, value in (persona.get("facts") or {}).items()
                            if isinstance(value, dict) and value.get("state") == "known"
                        }

    opportunities = [
        {
            "opportunity_family": "service_information",
            "customer_truth_present": bool(
                known_fields
                & {"primary_products_or_services", "product_or_service_facts"}
            ),
            "current_pattern_coverage": "conditional_process_pattern_only",
            "blocking_reason": (
                "Current approved Mix Pattern additionally requires KNOWN process material."
            ),
            "existing_cases_potentially_relevant": [
                "7650056203686530319",
                "7680512578585870322",
                "7683027343636542565",
            ],
            "research_path": "Add non-process service-explanation structural coverage.",
        },
        {
            "opportunity_family": "customer_use_context",
            "customer_truth_present": bool(
                known_fields & {"core_audience", "customer_use_cases", "customer_pains"}
            ),
            "current_pattern_coverage": "none",
            "blocking_reason": "No approved Mix customer/use-scenario Pattern.",
            "existing_cases_potentially_relevant": [
                "7657225197486131407",
                "7687296010611280827",
            ],
            "research_path": "Review compatibility, then perform cross-case structural research.",
        },
        {
            "opportunity_family": "trust_differentiator",
            "customer_truth_present": bool(known_fields & {"differentiators"}),
            "current_pattern_coverage": "none",
            "blocking_reason": "No approved Mix trust/differentiator Pattern.",
            "existing_cases_potentially_relevant": [
                "7657225197486131407",
                "7687296010611280827",
            ],
            "research_path": "Human compatibility review plus cross-case structure research.",
        },
        {
            "opportunity_family": "founder_person_story",
            "customer_truth_present": bool(
                known_fields & {"brand_story", "founder_or_operator_story"}
            ),
            "current_pattern_coverage": "none_without_process_material",
            "blocking_reason": (
                "Existing process Pattern can use story context but does not cover a standalone "
                "person/founder story without process truth."
            ),
            "existing_cases_potentially_relevant": [],
            "research_path": "Acquire and research person-driven narrative Cases.",
        },
    ]
    return {
        "request_id": request_id,
        "request_found": bool(request),
        "business_id": request.get("persona_id"),
        "known_fact_fields": sorted(known_fields),
        "classification": "CREATIVE_COVERAGE_GAP",
        "opportunities": opportunities,
    }


def build_audit(data_root: Path, request_id: str | None) -> dict[str, Any]:
    cases = case_inventory(data_root)
    patterns = pattern_inventory(data_root)
    supported_by_patterns = {
        case_id
        for pattern in patterns
        for case_id in pattern["supported_case_ids"]
    }
    unbound = [
        item["case_id"]
        for item in cases
        if item["approved"]
        and item["fingerprint_valid"]
        and item["approved_compatible_profiles"]
        and item["case_id"] not in supported_by_patterns
    ]
    approved_mix_cases = {
        item["case_id"]
        for item in cases
        if "mix" in item["approved_compatible_profiles"]
    }
    matrix = []
    patterns_by_id = {item["pattern_id"]: item for item in patterns}
    for dimension, pattern_id in MIX_DIMENSIONS.items():
        pattern = patterns_by_id.get(pattern_id) if pattern_id else None
        compatible = (
            sorted(approved_mix_cases & set(pattern["supported_case_ids"]))
            if pattern
            else []
        )
        matrix.append(
            {
                "content_job_or_capability": dimension,
                "approved_pattern": pattern_id,
                "compatible_cases": compatible,
                "production_ready": bool(pattern and compatible),
                "note": (
                    "Production minimum met: one Approved Pattern plus at least one "
                    "Approved, fingerprint-valid, profile-compatible supporting Case."
                    if pattern and compatible
                    else "No approved Pattern/Case lineage currently covers this dimension."
                ),
            }
        )

    valid = [item for item in cases if item["approved"] and item["fingerprint_valid"]]
    invalid = [item["case_id"] for item in cases if item["approved"] and not item["fingerprint_valid"]]
    compatibility_not_approved = [
        item["case_id"]
        for item in valid
        if not item["approved_compatible_profiles"]
    ]
    lineage_missing = unbound
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only",
        "approved_case_inventory": {
            "total_approved_cases": sum(item["approved"] for item in cases),
            "cases_with_valid_fingerprint": len(valid),
            "cases_without_valid_fingerprint": invalid,
            "operator_profile_hint_counts": count_values(
                [item["operator_profile_hint"] for item in cases if item["approved"]]
            ),
            "observed_source_profile_counts": count_values(
                [item["observed_source_profile"] for item in cases if item["approved"]]
            ),
            "approved_compatible_profile_counts": count_values(
                [
                    profile
                    for item in cases
                    for profile in item["approved_compatible_profiles"]
                ]
            ),
            "cases": cases,
        },
        "approved_pattern_inventory": patterns,
        "pattern_case_matrix": [
            {
                "pattern_id": item["pattern_id"],
                "compatible_profiles": item["compatible_profiles"],
                "supported_case_ids": item["supported_case_ids"],
                "minimum_production_support_met": bool(
                    item["approved"]
                    and item["human_approval_present"]
                    and item["supported_case_ids"]
                ),
            }
            for item in patterns
        ],
        "unbound_approved_cases": unbound,
        "mix_coverage_matrix": matrix,
        "recurring_structural_signals": recurring_signals(cases),
        "top_research_candidates": research_candidates(cases)[:5],
        "acquisition_and_research_gaps": {
            "A_more_cases_required": [
                "founder/person story",
                "FAQ/Q&A breadth",
                "conversion",
                "boundary/misconception",
            ],
            "B_cross_case_research_or_pattern_approval_required": [
                "trust/differentiator and customer/use-scenario signals are promising but not approved coverage"
            ],
            "C_case_profile_compatibility_not_approved": compatibility_not_approved,
            "D_pattern_support_lineage_not_updated": lineage_missing,
        },
        "current_failing_customer_mapping": current_request_mapping(
            data_root, request_id
        ),
        "authority": {
            "production_data_modified": False,
            "case_compatibility_modified": False,
            "pattern_created": False,
            "pattern_approved": False,
            "remote_model_calls": 0,
            "local_model_calls": 0,
            "report_is_authority": False,
        },
    }


def markdown_report(audit: dict[str, Any]) -> str:
    case_inventory = audit["approved_case_inventory"]
    lines = [
        "# Existing Case Library → Mix Creative Coverage Audit V1",
        "",
        "## A. Approved Case inventory",
        "",
        f"- Total Approved Cases: {case_inventory['total_approved_cases']}",
        f"- Cases with valid Fingerprint: {case_inventory['cases_with_valid_fingerprint']}",
        f"- Cases without valid Fingerprint: {len(case_inventory['cases_without_valid_fingerprint'])}",
        f"- Observed Source Profiles: `{json.dumps(case_inventory['observed_source_profile_counts'], ensure_ascii=False)}`",
        f"- Approved Compatible Profiles: `{json.dumps(case_inventory['approved_compatible_profile_counts'], ensure_ascii=False)}`",
        "",
        "## B. Approved Pattern inventory",
        "",
        "| Pattern | Profiles | Cases | Human Approval | Production Uses |",
        "|---|---|---:|---|---:|",
    ]
    for pattern in audit["approved_pattern_inventory"]:
        lines.append(
            "| {pattern_id} | {profiles} | {case_count} | {approval} | {uses} |".format(
                pattern_id=pattern["pattern_id"],
                profiles=", ".join(pattern["compatible_profiles"]) or "none",
                case_count=pattern["case_count"],
                approval="yes" if pattern["human_approval_present"] else "no",
                uses=pattern["current_production_use_count"],
            )
        )
    lines.extend(
        [
            "",
            "## C. Unbound Approved Cases",
            "",
            ", ".join(audit["unbound_approved_cases"]) or "None.",
            "",
            "## D. Mix Coverage Matrix",
            "",
            "| Capability | Approved Pattern | Compatible Cases | Production Ready |",
            "|---|---|---|---|",
        ]
    )
    for row in audit["mix_coverage_matrix"]:
        lines.append(
            f"| {row['content_job_or_capability']} | {row['approved_pattern'] or 'none'} | "
            f"{', '.join(row['compatible_cases']) or 'none'} | "
            f"{'yes' if row['production_ready'] else 'no'} |"
        )
    lines.extend(["", "## E. Recurring Structural Signals", ""])
    for item in audit["recurring_structural_signals"]:
        lines.append(
            f"- `{item['signal']}`: {item['evidence_count']} Cases "
            f"({', '.join(item['case_ids'])}); confidence={item['research_confidence']}."
        )
    lines.extend(["", "## F. Top Research Candidates", ""])
    if not audit["top_research_candidates"]:
        lines.append("Insufficient evidence for a reliable Pattern research candidate.")
    for item in audit["top_research_candidates"]:
        lines.append(
            f"- `{item['candidate_id']}` — **{item['status']}**; Cases: "
            f"{', '.join(item['supporting_case_ids'])}; confidence={item['research_confidence']}."
        )
    gaps = audit["acquisition_and_research_gaps"]
    lines.extend(
        [
            "",
            "## G. Acquisition / Research Gaps",
            "",
            f"- A — More Cases: {', '.join(gaps['A_more_cases_required'])}",
            f"- B — Research/Approval: {', '.join(gaps['B_cross_case_research_or_pattern_approval_required'])}",
            f"- C — Compatibility not approved: {', '.join(gaps['C_case_profile_compatibility_not_approved']) or 'none'}",
            f"- D — Support lineage missing: {', '.join(gaps['D_pattern_support_lineage_not_updated']) or 'none'}",
            "",
            "## H. Current failing customer mapping",
            "",
            f"Classification: **{audit['current_failing_customer_mapping']['classification']}**",
            "",
        ]
    )
    for row in audit["current_failing_customer_mapping"]["opportunities"]:
        lines.append(
            f"- `{row['opportunity_family']}`: {row['blocking_reason']} "
            f"Research path: {row['research_path']}"
        )
    lines.extend(
        [
            "",
            "## I. Authority",
            "",
            "Production Data Modified = 0  ",
            "Remote Model Calls = 0  ",
            "Local Model Calls = 0  ",
            "No Pattern created or approved; no Case compatibility changed.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--request-id")
    args = parser.parse_args()
    pipeline_root = Path(args.pipeline_root).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    audit = build_audit(pipeline_root / "data", args.request_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "existing_case_library_creative_coverage_audit_v1.json"
    md_path = output_dir / "existing_case_library_creative_coverage_audit_v1.md"
    json_path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path.write_text(markdown_report(audit), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "json_report": str(json_path),
                "markdown_report": str(md_path),
                "summary": {
                    "approved_cases": audit["approved_case_inventory"][
                        "total_approved_cases"
                    ],
                    "valid_fingerprints": audit["approved_case_inventory"][
                        "cases_with_valid_fingerprint"
                    ],
                    "approved_patterns": len(audit["approved_pattern_inventory"]),
                    "unbound_cases": len(audit["unbound_approved_cases"]),
                    "mix_ready_dimensions": sum(
                        row["production_ready"]
                        for row in audit["mix_coverage_matrix"]
                    ),
                },
                "model_calls": {"remote": 0, "local": 0},
                "production_data_modified": False,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
