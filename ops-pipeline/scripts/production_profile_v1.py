from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree


REGISTRY_SCHEMA_VERSION = "production-profile-registry-v1.0"
COVERAGE_REPORT_SCHEMA_VERSION = "creative-coverage-report-v1.0"
COMPATIBILITY_APPROVAL_SCHEMA_VERSION = (
    "production-profile-compatibility-approval-v1.0"
)
CASE_ACQUISITION_PLAN_SCHEMA_VERSION = "case-acquisition-plan-v1.0"
CASE_ACQUISITION_PLAN_AMENDMENT_SCHEMA_VERSION = (
    "case-acquisition-plan-amendment-v1.0"
)
NEWS_PHASE_A_SCOUT_SCHEMA_VERSION = "news-phase-a-breadth-scout-v1.0"
NEWS_PHASE_A_ROUND_1_DECISION_SCHEMA_VERSION = (
    "news-phase-a-round-1-human-decision-v1.0"
)
NEWS_PHASE_A_ROUND_2_SCOUT_SCHEMA_VERSION = (
    "news-phase-a-round-2-targeted-discovery-v1.0"
)
NEWS_PHASE_A_CLOSURE_SCHEMA_VERSION = "news-phase-a-closure-v1.0"
NEWS_CREATIVE_COVERAGE_UPDATE_SCHEMA_VERSION = (
    "news-creative-coverage-update-v1.0"
)
NEWS_PHASE_B_DEPTH_BUILD_PLAN_SCHEMA_VERSION = (
    "news-phase-b-depth-build-plan-v1.0"
)
NEWS_PHASE_B_ROUND_1_SCOUT_SCHEMA_VERSION = (
    "news-phase-b-round-1-scout-v1.0"
)
CASE_PROFILE_STRUCTURAL_DECISION_SCHEMA_VERSION = (
    "case-profile-structural-decision-v1.0"
)
NEWS_PHASE_B_HUMAN_REVIEW_CLOSURE_SCHEMA_VERSION = (
    "news-phase-b-round-1-human-review-closure-v1.0"
)
CASE_SOURCE_GOVERNANCE_AUDIT_SCHEMA_VERSION = (
    "case-source-governance-audit-v1.0"
)
CASE_SOURCE_GOVERNANCE_POLICY_SCHEMA_VERSION = (
    "case-source-governance-policy-v1.0"
)
CASE_SOURCE_GOVERNANCE_COMPANION_SCHEMA_VERSION = (
    "case-source-governance-companion-v1.0"
)
NEWS_CROSS_CASE_RESEARCH_BUNDLE_SCHEMA_VERSION = (
    "news-cross-case-research-input-bundle-v1.0"
)
CASE_PROFILE_COMPATIBILITY_APPROVAL_SCHEMA_VERSION = (
    "case-profile-compatibility-approval-v1.0"
)
BUILDER_VERSION = "production_profile_v1.py@1.0"
TARGET_PROFILES = {"news", "mix"}
SOURCE_PROFILE_CLASSIFICATIONS = {"news", "mix", "hybrid", "uncertain"}
OPERATOR_PROFILE_HINTS = {"news", "mix", "hybrid", "uncertain"}
MIX_PATTERN_ID = "pcv1_narration_led_process_projection"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    return hashlib.sha256(payload).hexdigest()


def _xlsx_first_sheet_row(path: Path, row_number: int, column_count: int) -> list[Any]:
    """Read one XLSX row without modifying or recalculating the workbook."""
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    with zipfile.ZipFile(path, "r") as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{main_ns}}}si"):
                shared.append(
                    "".join(node.text or "" for node in item.iter(f"{{{main_ns}}}t"))
                )
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        first_sheet = workbook.find(f".//{{{main_ns}}}sheet")
        if first_sheet is None:
            raise RuntimeError(f"Workbook has no worksheet: {path}")
        relation_id = first_sheet.attrib[f"{{{rel_ns}}}id"]
        rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for relation in rels.findall(f"{{{package_rel_ns}}}Relationship"):
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise RuntimeError(f"Workbook worksheet relationship is missing: {path}")
        sheet_path = target.lstrip("/")
        if not sheet_path.startswith("xl/"):
            sheet_path = "xl/" + sheet_path
        sheet = ElementTree.fromstring(archive.read(sheet_path))
        values: dict[str, Any] = {}
        for cell in sheet.findall(
            f".//{{{main_ns}}}row[@r='{row_number}']/{{{main_ns}}}c"
        ):
            address = str(cell.attrib.get("r") or "")
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{{{main_ns}}}v")
            inline_node = cell.find(f"{{{main_ns}}}is")
            value: Any = None
            if cell_type == "s" and value_node is not None:
                value = shared[int(value_node.text or 0)]
            elif cell_type == "inlineStr" and inline_node is not None:
                value = "".join(
                    node.text or ""
                    for node in inline_node.iter(f"{{{main_ns}}}t")
                )
            elif value_node is not None:
                value = value_node.text
            values[address] = value
        return [
            values.get(f"{chr(ord('A') + column)}{row_number}")
            for column in range(column_count)
        ]


def validate_target_profile(registry: dict[str, Any], target_profile: str) -> dict[str, Any]:
    if target_profile not in TARGET_PROFILES:
        raise ValueError(
            "Generation target_profile must resolve to news or mix; hybrid, uncertain, "
            "and unknown values fail closed."
        )
    profiles = registry.get("profiles") or {}
    profile = profiles.get(target_profile)
    if not isinstance(profile, dict):
        raise ValueError(f"Production Profile is not registered: {target_profile}")
    if profile.get("profile_id") != target_profile:
        raise ValueError("Production Profile Registry identity mismatch.")
    return profile


def validate_registry(registry: dict[str, Any]) -> None:
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError("Production Profile Registry schema is invalid.")
    if set((registry.get("profiles") or {}).keys()) != TARGET_PROFILES:
        raise ValueError("Production Profile Registry must register exactly news and mix in V1.")
    if set(registry.get("target_profiles") or []) != TARGET_PROFILES:
        raise ValueError("V1 target_profiles must resolve to news and mix only.")
    if set(registry.get("source_profile_classifications") or []) != SOURCE_PROFILE_CLASSIFICATIONS:
        raise ValueError("Source profile classifications are incomplete.")
    for profile_id in sorted(TARGET_PROFILES):
        profile = validate_target_profile(registry, profile_id)
        for contract in (
            "script_contract",
            "storyboard_contract",
            "export_contract",
            "case_compatibility_policy",
            "pattern_compatibility_policy",
            "validation_policy",
        ):
            if not isinstance(profile.get(contract), dict):
                raise ValueError(f"{profile_id} is missing {contract}.")
    mix = registry["profiles"]["mix"]
    news = registry["profiles"]["news"]
    if mix.get("status") != "production_ready":
        raise ValueError("Mix frozen operational readiness changed.")
    if news.get("status") != "research_coverage_insufficient":
        raise ValueError("News frozen operational readiness changed.")


def build_production_profile_registry_v1(
    *,
    mix_template_path: Path,
    news_template_path: Path,
    approved_pattern_path: Path,
    pattern_approval_receipt_path: Path,
    real_mix_source_plan_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    paths = [
        mix_template_path,
        news_template_path,
        approved_pattern_path,
        pattern_approval_receipt_path,
        real_mix_source_plan_path,
    ]
    paths = [path.expanduser().resolve() for path in paths]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    (
        mix_template_path,
        news_template_path,
        approved_pattern_path,
        pattern_approval_receipt_path,
        real_mix_source_plan_path,
    ) = paths
    mix_headers = _xlsx_first_sheet_row(mix_template_path, 4, 2)
    news_headers = _xlsx_first_sheet_row(news_template_path, 4, 6)
    if mix_headers != ["视频制作标题", "视频制作口播内容"]:
        raise RuntimeError(f"Mix Excel contract changed: {mix_headers}")
    if news_headers != [f"标题{index}" for index in range(1, 7)]:
        raise RuntimeError(f"News Excel contract changed: {news_headers}")

    pattern = read_json(approved_pattern_path)
    receipt = read_json(pattern_approval_receipt_path)
    source_plan = read_json(real_mix_source_plan_path)
    pattern_sha = sha256_file(approved_pattern_path)
    if pattern.get("pattern_id") != MIX_PATTERN_ID or pattern.get("status") != "approved":
        raise RuntimeError("Frozen Mix Pattern is not Approved.")
    if receipt.get("human_gate") is not True or not str(receipt.get("decision") or "").startswith("approved"):
        raise RuntimeError("Pattern Profile backfill requires the existing Human Approval.")
    approved_ref = receipt.get("approved_pattern") or {}
    if approved_ref.get("sha256") != pattern_sha:
        raise RuntimeError("Pattern approval receipt SHA mismatch.")
    selected_pattern_ids = {
        item.get("pattern_id") for item in source_plan.get("selected_patterns") or []
    }
    real_mix_request_sha = str(
        (source_plan.get("request") or {}).get("request_sha") or ""
    )
    selected_case_ids = [
        item.get("case_id") for item in source_plan.get("selected_cases") or []
    ]
    if (
        source_plan.get("request", {}).get("profile") != "mix"
        or source_plan.get("coverage", {}).get("status") != "supported"
        or MIX_PATTERN_ID not in selected_pattern_ids
        or not selected_case_ids
        or len(real_mix_request_sha) != 64
    ):
        raise RuntimeError("Real Mix Source Plan does not support canonical compatibility backfill.")

    common_case_policy = {
        "canonical_eligibility_field": "compatible_generation_profiles",
        "operator_profile_hint_is_authority": False,
        "observed_source_profile_is_automatic_eligibility": False,
        "approved_compatibility_required_for_new_matching": True,
        "case_facts_transfer_permitted": False,
    }
    common_pattern_policy = {
        "approved_pattern_required": True,
        "profile_compatibility_must_be_explicit": True,
        "cross_profile_compatibility_is_automatic": False,
        "effectiveness_authority_created": False,
    }
    registry = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "registry_id": "production_profile_registry_v1",
        "registry_version": "1.0",
        "status": "approved_frozen",
        "created_at": created_at or now_iso(),
        "target_profiles": ["news", "mix"],
        "source_profile_classifications": ["news", "mix", "hybrid", "uncertain"],
        "upload_case_contract": {
            "operator_profile_hint": {
                "allowed_values": ["news", "mix", "hybrid", "uncertain"],
                "required": True,
                "routing_and_retrieval_only": True,
                "canonical_compatibility_authority": False,
            },
            "operator_notes": {
                "required": False,
                "pattern_authority": False,
                "compatibility_authority": False,
            },
        },
        "cross_profile_semantic_policy": {
            "production_profile_is_presentation_identity": True,
            "semantic_history_scope": "business_wide_across_profiles",
            "profile_change_resets_novelty": False,
            "default_reuse_intent": "novel_content",
            "allowed_reuse_intents": ["novel_content", "cross_profile_repurpose"],
            "cross_profile_repurpose_is_novel": False,
            "cross_profile_repurpose_adds_novel_capacity": False,
        },
        "profiles": {
            "mix": {
                "profile_id": "mix",
                "profile_version": "1.0",
                "status": "production_ready",
                "operational_readiness": "production_ready",
                "creative_coverage": "narrow",
                "semantic_definition": (
                    "Narration is the primary semantic spine; real people, process, "
                    "service, product, and scene material provide visual projection."
                ),
                "script_contract": {
                    "shape": "title_and_narration",
                    "required_fields": ["title", "narration"],
                    "narration_is_primary_semantic_spine": True,
                },
                "storyboard_contract": {
                    "profile_field_required": True,
                    "shape": "narration_to_visual_many_to_many",
                    "required_fields": [
                        "narration_segment",
                        "visual_shots",
                        "hero_shot_role",
                        "supporting_shot_roles",
                        "visual_anchor",
                        "avoid_recent_visual_anchor",
                    ],
                    "many_to_many_audio_visual_mapping": True,
                },
                "export_contract": {
                    "implementation_version": "current_v1",
                    "template_path": str(mix_template_path),
                    "template_sha256": sha256_file(mix_template_path),
                    "sheet": "Sheet1",
                    "header_row": 4,
                    "headers": mix_headers,
                    "first_data_row": 5,
                    "contract_changed": False,
                },
                "case_compatibility_policy": common_case_policy,
                "pattern_compatibility_policy": common_pattern_policy
                | {"approved_compatible_pattern_ids": [MIX_PATTERN_ID]},
                "validation_policy": {
                    "title_required": True,
                    "narration_required": True,
                    "profile_compatible_pattern_required": True,
                    "profile_compatible_case_required": True,
                    "privacy_gate_before_remote_call": True,
                },
            },
            "news": {
                "profile_id": "news",
                "profile_version": "1.0",
                "status": "research_coverage_insufficient",
                "operational_readiness": "research_coverage_insufficient",
                "creative_coverage": "insufficient",
                "semantic_definition": (
                    "Short, dense micro-information beats are the primary semantic "
                    "carrier; News is not a shortened Mix script."
                ),
                "script_contract": {
                    "shape": "micro_information_beats",
                    "beat_fields": [
                        "semantic_role",
                        "text",
                        "visual_anchor",
                        "order",
                        "duration_guidance",
                        "evidence_lineage",
                    ],
                    "current_implementation_constraints": {
                        "title_columns": 6,
                        "recommended_max_characters_per_title": 8,
                        "preferred_duration_seconds": [6, 8],
                        "authority": "configurable_not_frozen_profile_semantics",
                    },
                },
                "storyboard_contract": {
                    "profile_field_required": True,
                    "shape": "micro_beat_sequence",
                    "required_fields": [
                        "semantic_role",
                        "text",
                        "visual_state",
                        "order",
                        "duration_guidance",
                        "evidence_lineage",
                    ],
                    "narration_many_to_many_required": False,
                },
                "export_contract": {
                    "implementation_version": "current_v1",
                    "template_path": str(news_template_path),
                    "template_sha256": sha256_file(news_template_path),
                    "sheet": "Sheet1",
                    "header_row": 4,
                    "headers": news_headers,
                    "first_data_row": 5,
                    "contract_changed": False,
                    "six_columns_are_current_implementation_not_frozen_semantics": True,
                },
                "case_compatibility_policy": common_case_policy,
                "pattern_compatibility_policy": common_pattern_policy
                | {"approved_compatible_pattern_ids": []},
                "validation_policy": {
                    "micro_beat_contract_required": True,
                    "profile_compatible_pattern_required": True,
                    "profile_compatible_case_required": True,
                    "mix_pattern_fallback_permitted": False,
                    "privacy_gate_before_remote_call": True,
                },
            },
        },
        "pattern_compatibility_records": [
            {
                "pattern_id": MIX_PATTERN_ID,
                "approved_pattern_sha256": pattern_sha,
                "compatible_profiles": ["mix"],
                "compatibility_status": "approved_canonical_backfill",
                "news_compatible": False,
                "basis": [
                    "approved_frozen_product_authority",
                    "approved_pattern_definition_and_scope",
                    "completed_real_mix_source_matching_and_production_lineage",
                ],
                "effectiveness_status": pattern.get("effectiveness", {}).get("status"),
                "effectiveness_claim_created": False,
                "approved_pattern_artifact_modified": False,
                "lineage": {
                    "pattern_path": str(approved_pattern_path),
                    "pattern_sha256": pattern_sha,
                    "approval_receipt_path": str(pattern_approval_receipt_path),
                    "approval_receipt_sha256": sha256_file(pattern_approval_receipt_path),
                    "real_mix_source_plan_path": str(real_mix_source_plan_path),
                    "real_mix_source_plan_sha256": sha256_file(real_mix_source_plan_path),
                    "real_mix_request_sha256": real_mix_request_sha,
                    "legacy_supported_case_ids": selected_case_ids,
                },
            }
        ],
        "authority": {
            "canonical_production_contract_registry": True,
            "case_lifecycle_changed": False,
            "pattern_lifecycle_changed": False,
            "content_ledger_changed": False,
            "persona_authority_changed": False,
            "privacy_or_proof_authority_changed": False,
            "new_pattern_created": False,
            "news_generation_enabled": False,
            "remote_model_called": False,
        },
        "validation": {
            "passed": True,
            "news_and_mix_registered": True,
            "hybrid_and_uncertain_not_generation_targets": True,
            "mix_export_contract_verified": True,
            "news_export_contract_verified": True,
            "mix_pattern_compatibility_backfilled": True,
            "mix_pattern_not_promoted_to_news": True,
        },
    }
    validate_registry(registry)
    return registry


def pattern_compatibility_record(
    registry: dict[str, Any], pattern_id: str, pattern_sha256: str
) -> dict[str, Any] | None:
    for record in registry.get("pattern_compatibility_records") or []:
        if record.get("pattern_id") != pattern_id:
            continue
        if record.get("approved_pattern_sha256") != pattern_sha256:
            raise RuntimeError("Pattern Profile compatibility SHA does not match Pattern Authority.")
        return record
    return None


def _candidate_capabilities(fingerprint: dict[str, Any]) -> dict[str, list[str]]:
    visual = fingerprint.get("visual_shot_features") or {}
    narration = fingerprint.get("narration_features") or {}
    audiovisual = fingerprint.get("audio_visual_features") or {}
    structure = fingerprint.get("structure_features") or {}
    content = fingerprint.get("content_features") or {}
    roles = visual.get("primary_role_counts") or {}
    hook = structure.get("hook_candidate") or {}
    sequence = str(structure.get("structure_signature") or "")
    opening: list[str] = []
    if "?" in str(hook.get("audio") or ""):
        opening.append("question")
    if hook.get("visual_scene"):
        opening.append("scene")
    narrative: list[str] = []
    if "development" in sequence and "payoff" in sequence:
        narrative.append("process_result")
    if "?" in str(hook.get("audio") or ""):
        narrative.append("question_answer")
    visual_projection: list[str] = []
    role_map = {
        "persona": "person",
        "action": "process",
        "product": "product",
        "context": "scene",
    }
    for source_role, capability in role_map.items():
        if roles.get(source_role, 0):
            visual_projection.append(capability)
    if sum((audiovisual.get("text_relation_counts") or {}).values()):
        visual_projection.append("text")
    speaker_modes = ["narrator"] if float(narration.get("speech_to_video_ratio") or 0) else []
    trust = ["process_only"] if roles.get("action", 0) else []
    closing = [] if content.get("has_explicit_cta") else ["none"]
    if "payoff" in sequence:
        closing.append("information_close")
    return {
        "opening_hook": sorted(set(opening)),
        "narrative_progression": sorted(set(narrative)),
        "visual_projection": sorted(set(visual_projection)),
        "speaker_mode": speaker_modes,
        "trust_proof": trust,
        "closing_cta": sorted(set(closing)),
        "content_job_compatibility": ["process", "service_explanation"],
    }


def audit_case_profile_compatibility_v1(
    *,
    case_path: Path,
    case_approval_receipt_path: Path,
    fingerprint_path: Path,
    storyboard_path: Path,
    legacy_mix_case_ids: set[str],
) -> dict[str, Any]:
    paths = [
        case_path.expanduser().resolve(),
        case_approval_receipt_path.expanduser().resolve(),
        fingerprint_path.expanduser().resolve(),
        storyboard_path.expanduser().resolve(),
    ]
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    case_path, case_approval_receipt_path, fingerprint_path, storyboard_path = paths
    case = read_json(case_path)
    receipt = read_json(case_approval_receipt_path)
    fingerprint = read_json(fingerprint_path)
    storyboard = read_json(storyboard_path)
    case_id = str(case.get("case_id") or "")
    case_sha = sha256_file(case_path)
    fingerprint_sha = sha256_file(fingerprint_path)
    storyboard_sha = sha256_file(storyboard_path)
    if not case_id or fingerprint.get("case_id") != case_id or storyboard.get("case_id") != case_id:
        raise RuntimeError("Case/Fingerprint/Storyboard identity mismatch.")
    lifecycle = case.get("lifecycle") or {}
    if lifecycle.get("status") != "approved" or lifecycle.get("approved") is not True:
        raise RuntimeError(f"Case {case_id} is not Approved.")
    if receipt.get("decision") != "approved" or receipt.get("human_gate") is not True:
        raise RuntimeError(f"Case {case_id} approval receipt is invalid.")
    if receipt.get("case_sha256_after_approval") != case_sha:
        raise RuntimeError(f"Case {case_id} Approved SHA mismatch.")
    if (fingerprint.get("source_case") or {}).get("sha256") != case_sha:
        raise RuntimeError(f"Fingerprint {case_id} does not reference the frozen Case SHA.")

    narration = fingerprint.get("narration_features") or {}
    visual = fingerprint.get("visual_shot_features") or {}
    audiovisual = fingerprint.get("audio_visual_features") or {}
    structure = fingerprint.get("structure_features") or {}
    content = fingerprint.get("content_features") or {}
    speech_ratio = float(narration.get("speech_to_video_ratio") or 0)
    shot_count = int(visual.get("shot_count") or 0)
    independent_text_count = int(
        (audiovisual.get("text_relation_counts") or {}).get("independent", 0)
    )
    independent_text_ratio = (
        round(independent_text_count / shot_count, 6) if shot_count else 0.0
    )
    narration_dominant = (
        speech_ratio >= 0.5
        and audiovisual.get("narration_and_shots_are_separate_tracks") is True
        and audiovisual.get("shot_to_narration_cardinality") == "many_to_many"
    )
    micro_beat_dominant = speech_ratio < 0.5 and independent_text_ratio >= 0.5
    if narration_dominant and micro_beat_dominant:
        observed_profile = "hybrid"
    elif narration_dominant:
        observed_profile = "mix"
    elif micro_beat_dominant:
        observed_profile = "news"
    else:
        observed_profile = "uncertain"
    candidate_profiles = {
        "mix": ["mix"],
        "news": ["news"],
        "hybrid": ["news", "mix"],
        "uncertain": [],
    }[observed_profile]
    operator_hint = case.get("operator_profile_hint")
    if operator_hint not in OPERATOR_PROFILE_HINTS:
        operator_hint = None
    shot_stats = visual.get("shot_duration_stats") or {}
    role_counts = visual.get("primary_role_counts") or {}
    structural_summary = {
        "narration_dominance": {
            "speech_to_video_ratio": speech_ratio,
            "narration_and_shots_are_separate_tracks": audiovisual.get(
                "narration_and_shots_are_separate_tracks"
            ),
            "shot_to_narration_cardinality": audiovisual.get(
                "shot_to_narration_cardinality"
            ),
            "assessment": "dominant" if narration_dominant else "not_dominant",
        },
        "text_beat_structure": {
            "independent_text_shot_count": independent_text_count,
            "independent_text_shot_ratio": independent_text_ratio,
            "micro_information_beats_dominate": micro_beat_dominant,
        },
        "shot_duration_and_rhythm": {
            "shot_count": shot_count,
            "duration_seconds": fingerprint.get("identity", {}).get("duration_seconds"),
            "mean_shot_duration_seconds": shot_stats.get("mean"),
            "median_shot_duration_seconds": shot_stats.get("median"),
            "shots_under_one_second_ratio": visual.get("shots_under_1s_ratio"),
        },
        "visual_projection": {
            "primary_role_counts": role_counts,
            "scene_relation_counts": audiovisual.get("scene_relation_counts") or {},
            "many_to_many": audiovisual.get("shot_to_narration_cardinality")
            == "many_to_many",
        },
        "onscreen_text_behavior": {
            "onscreen_text_shot_ratio": visual.get("onscreen_text_shot_ratio"),
            "text_relation_counts": audiovisual.get("text_relation_counts") or {},
            "independent_text_is_primary_semantic_carrier": micro_beat_dominant,
        },
        "story_progression": {
            "structure_signature": structure.get("structure_signature"),
            "hook_modalities": structure.get("hook_modalities") or [],
            "explicit_cta": bool(content.get("has_explicit_cta")),
            "verified_proof_count": int(content.get("verified_proof_count") or 0),
        },
    }
    legacy_profiles = ["mix"] if case_id in legacy_mix_case_ids else []
    return {
        "assessment_version": "case-profile-compatibility-assessment-v1.0",
        "case_id": case_id,
        "operator_profile_hint": operator_hint,
        "operator_profile_hint_status": "missing_unknown" if operator_hint is None else "provided_non_authoritative",
        "observed_source_profile": observed_profile,
        "compatible_generation_profiles_candidate": candidate_profiles,
        "approved_compatible_generation_profiles": [],
        "confidence": "high" if observed_profile in {"mix", "news"} else "medium",
        "assessment_status": "observed",
        "review_status": "review_required",
        "classification_reason": (
            "Narration is the dominant semantic carrier with many-to-many process, "
            "scene, person, and product visual projection. Independent text beats do "
            "not dominate the structure."
            if observed_profile == "mix"
            else "Structural evidence requires Human Review before compatibility approval."
        ),
        "structural_evidence_summary": structural_summary,
        "candidate_creative_capabilities": _candidate_capabilities(fingerprint),
        "legacy_current_truth": {
            "compatible_profiles": legacy_profiles,
            "basis": "existing_approved_pattern_support_and_completed_mix_production_lineage"
            if legacy_profiles
            else None,
            "is_canonical_compatibility_approval": False,
        },
        "lineage": {
            "approved_case": {
                "path": str(case_path),
                "sha256": case_sha,
                "modified_by_backfill": False,
            },
            "approval_receipt": {
                "path": str(case_approval_receipt_path),
                "sha256": sha256_file(case_approval_receipt_path),
            },
            "fingerprint": {
                "path": str(fingerprint_path),
                "sha256": fingerprint_sha,
            },
            "storyboard": {
                "path": str(storyboard_path),
                "sha256": storyboard_sha,
            },
        },
        "authority": {
            "assessment_is_case_approval": False,
            "assessment_changes_case_compatibility": False,
            "operator_hint_used_as_eligibility": False,
            "case_specific_facts_exported": False,
            "remote_model_called": False,
        },
    }


def _coverage_dimension(
    dimension: str,
    approved: list[str],
    candidate: list[str],
    gaps: list[str],
) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "approved_capabilities": sorted(set(approved)),
        "candidate_observed_capabilities": sorted(set(candidate)),
        "missing_or_weak_capabilities": sorted(set(gaps)),
    }


def _acquisition_gap(
    target_profile: str,
    coverage_dimension: str,
    missing_capability: str,
    why_it_matters: str,
    existing_similar_coverage: str,
    desired_case_characteristics: list[str],
    priority: str,
) -> dict[str, Any]:
    return {
        "target_profile": target_profile,
        "coverage_dimension": coverage_dimension,
        "missing_capability": missing_capability,
        "why_it_matters": why_it_matters,
        "existing_similar_coverage": existing_similar_coverage,
        "desired_case_characteristics": desired_case_characteristics,
        "priority": priority,
        "artifact_type": "research_target_not_pattern",
    }


def build_creative_coverage_report_v1(
    *,
    registry: dict[str, Any],
    registry_ref: dict[str, Any],
    case_assessments: list[dict[str, Any]],
    created_at: str | None = None,
) -> dict[str, Any]:
    validate_registry(registry)
    if not case_assessments:
        raise ValueError("Creative Coverage Report requires Case assessments.")
    approved_pattern_records = [
        item
        for item in registry.get("pattern_compatibility_records") or []
        if item.get("compatibility_status") == "approved_canonical_backfill"
    ]
    mix_patterns = [
        item for item in approved_pattern_records if "mix" in item.get("compatible_profiles", [])
    ]
    news_patterns = [
        item for item in approved_pattern_records if "news" in item.get("compatible_profiles", [])
    ]

    candidate_by_profile = {
        profile: [
            item["case_id"]
            for item in case_assessments
            if profile in item.get("compatible_generation_profiles_candidate", [])
        ]
        for profile in sorted(TARGET_PROFILES)
    }
    approved_by_profile = {
        profile: [
            item["case_id"]
            for item in case_assessments
            if profile in item.get("approved_compatible_generation_profiles", [])
        ]
        for profile in sorted(TARGET_PROFILES)
    }
    legacy_by_profile = {
        profile: [
            item["case_id"]
            for item in case_assessments
            if profile
            in (item.get("legacy_current_truth") or {}).get("compatible_profiles", [])
        ]
        for profile in sorted(TARGET_PROFILES)
    }
    observed_mix_capabilities: dict[str, list[str]] = {}
    for assessment in case_assessments:
        if "mix" not in assessment.get("compatible_generation_profiles_candidate", []):
            continue
        for dimension, capabilities in (
            assessment.get("candidate_creative_capabilities") or {}
        ).items():
            observed_mix_capabilities.setdefault(dimension, []).extend(capabilities)

    mix_matrix = [
        _coverage_dimension("opening_hook", [], observed_mix_capabilities.get("opening_hook", []), ["number", "contrast", "result", "person_driven"]),
        _coverage_dimension("narrative_progression", ["narration_led_process_projection"], observed_mix_capabilities.get("narrative_progression", []), ["customer_story", "frontline_pov", "misconception_correction", "faq"]),
        _coverage_dimension("visual_projection", ["person", "process", "product", "scene"], observed_mix_capabilities.get("visual_projection", []), ["customer", "proof", "before_after"]),
        _coverage_dimension("speaker_mode", ["narrator", "frontline_expert"], observed_mix_capabilities.get("speaker_mode", []), ["customer", "owner_person_driven"]),
        _coverage_dimension("trust_proof", [], observed_mix_capabilities.get("trust_proof", []), ["customer_feedback", "numeric_fact", "real_result", "before_after", "document_dashboard"]),
        _coverage_dimension("closing_cta", [], observed_mix_capabilities.get("closing_cta", []), ["question_close", "action_cta", "interaction_cta"]),
        _coverage_dimension("content_job_compatibility", ["service_explanation", "process"], observed_mix_capabilities.get("content_job_compatibility", []), ["customer_story", "boundary", "trust", "conversion", "faq"]),
    ]
    news_matrix = [
        _coverage_dimension("opening_hook", [], [], ["number", "price", "local_service_discovery", "problem_alert", "scene_contrast", "event", "concrete_benefit"]),
        _coverage_dimension("narrative_progression", [], [], ["micro_question_answer", "event_explanation", "problem_resolution", "contrast_payoff"]),
        _coverage_dimension("visual_projection", [], [], ["text", "scene", "product", "proof", "before_after"]),
        _coverage_dimension("speaker_mode", [], [], ["narrator", "brand", "customer"]),
        _coverage_dimension("trust_proof", [], [], ["numeric_fact", "customer_feedback", "real_result", "document_dashboard"]),
        _coverage_dimension("closing_cta", [], [], ["information_close", "question_close", "interaction_cta"]),
        _coverage_dimension("content_job_compatibility", [], [], ["service_explanation", "pricing", "boundary", "trust", "faq"]),
    ]

    gaps = [
        _acquisition_gap("news", "opening_hook", "number_or_price_led", "News needs a clear first-beat information entry structure.", "No Approved News Pattern or Case compatibility exists.", ["A specific number or price is the first information beat", "Subsequent beats add context and meaning", "Visual/text states are separately observable"], "critical"),
        _acquisition_gap("news", "content_job_compatibility", "local_service_discovery", "Local service discovery is a core News-shaped research direction.", "Mix service explanation exists but is narration-led.", ["Local service or event is identified immediately", "Micro beats explain who, where, and what", "Source evidence is traceable"], "critical"),
        _acquisition_gap("news", "opening_hook", "problem_or_alert", "A problem/alert opening tests a materially different News entry structure.", "No approved short alert structure exists.", ["First beat states a concrete problem or caution", "Later beats supply bounded action value", "No unsupported urgency"], "high"),
        _acquisition_gap("news", "narrative_progression", "scene_contrast", "Contrast can provide progression without borrowing Mix narration structure.", "Current Cases project process scenes under narration.", ["Observable before/after or two-scene contrast", "Text beats explain the contrast", "The payoff is evidence-bound"], "high"),
        _acquisition_gap("news", "narrative_progression", "event_explanation", "Event-led cases are required to evaluate News temporal progression.", "No Approved event/micro-beat coverage exists.", ["A real event anchors the sequence", "Each beat adds distinct event information", "Order and evidence lineage are explicit"], "high"),
        _acquisition_gap("news", "content_job_compatibility", "concrete_benefit", "News needs compact decision value that remains semantically complete.", "No Approved News capability demonstrates this.", ["A concrete benefit is stated without vague claims", "Supporting fact appears in a separate beat", "Visual support does not replace authority"], "high"),
        _acquisition_gap("mix", "narrative_progression", "customer_story", "Current breadth is dominated by narration-led process projection.", "Three similar Cases increase evidence depth for the same structural family.", ["A real customer is the narrative driver", "Situation, decision, and outcome are distinct", "Publication authorization is visible in evidence"], "high"),
        _acquisition_gap("mix", "speaker_mode", "frontline_pov", "A first-person frontline judgment structure is not approved coverage.", "Frontline speaker generation exists, but source Case breadth remains narration/process-led.", ["Frontline worker narrates a personally observed moment", "Judgment and action are structurally central", "Business strategy is not assigned to the frontline role"], "high"),
        _acquisition_gap("mix", "trust_proof", "verified_result_or_proof", "Process visuals cannot be counted as Proof.", "Current Case fingerprints report zero verified proof.", ["A real result or before/after state is observable", "Claim-to-evidence linkage is explicit", "Proof boundaries are preserved"], "high"),
        _acquisition_gap("mix", "narrative_progression", "misconception_correction", "The current pattern does not cover misconception-to-correction progression.", "Current progression centers on narration and process projection.", ["A specific misconception opens the narrative", "Correction adds factual decision value", "Visuals support rather than invent the correction"], "medium"),
        _acquisition_gap("mix", "narrative_progression", "faq_question_answer", "Strong FAQ structure would expand service and boundary explanation breadth.", "One observed Case has a question hook, but no Approved FAQ Pattern exists.", ["A real customer question is explicit", "Answer is bounded and authority-supported", "Question and answer control the progression"], "medium"),
        _acquisition_gap("mix", "closing_cta", "intentional_close_or_cta", "Current fingerprints contain no explicit CTA coverage.", "Observed closing is none or informational payoff.", ["Close is structurally observable", "CTA type is distinguishable", "CTA does not create unsupported claims"], "medium"),
        _acquisition_gap("mix", "speaker_mode", "person_driven_narrative", "A person-led arc would add breadth beyond process visuals.", "Persona imagery exists but does not dominate the approved structure.", ["A person remains the narrative subject", "Scene progression follows that person's actions or decisions", "Process footage is supporting rather than dominant"], "medium"),
    ]
    report = {
        "schema_version": COVERAGE_REPORT_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "report_id": "creative_coverage_report_v1",
        "status": "review_required",
        "created_at": created_at or now_iso(),
        "source_registry_ref": registry_ref,
        "pattern_profile_compatibility": approved_pattern_records,
        "case_profile_compatibility_audit": {
            "assessment_count": len(case_assessments),
            "assessments": sorted(case_assessments, key=lambda item: item["case_id"]),
            "canonical_case_artifacts_modified": False,
            "human_compatibility_review_required": True,
        },
        "profiles": {
            "mix": {
                "operational_readiness": "production_ready",
                "creative_coverage": "narrow",
                "approved_compatible_patterns": [item["pattern_id"] for item in mix_patterns],
                "approved_compatible_cases": sorted(approved_by_profile["mix"]),
                "candidate_compatible_cases": sorted(candidate_by_profile["mix"]),
                "review_required_cases": sorted(candidate_by_profile["mix"]),
                "legacy_current_truth_cases": sorted(legacy_by_profile["mix"]),
                "legacy_compatibility_bridge_required": not bool(approved_by_profile["mix"]),
                "creative_breadth": {
                    "structural_family_count": 1,
                    "evidence_depth_case_count": len(legacy_by_profile["mix"]),
                    "case_count_is_not_creative_breadth": True,
                },
                "creative_capability_matrix": mix_matrix,
                "strengths": [
                    "approved_narration_led_process_projection",
                    "many_to_many_audio_visual_projection",
                    "person_process_product_and_scene_visuals",
                    "completed_real_customer_mix_production",
                ],
                "major_gaps": [
                    "customer_story",
                    "frontline_pov",
                    "verified_result_or_proof",
                    "misconception_correction",
                    "faq_question_answer",
                    "intentional_close_or_cta",
                    "person_driven_narrative",
                ],
            },
            "news": {
                "operational_readiness": "research_coverage_insufficient",
                "creative_coverage": "insufficient",
                "approved_compatible_patterns": [item["pattern_id"] for item in news_patterns],
                "approved_compatible_cases": sorted(approved_by_profile["news"]),
                "candidate_compatible_cases": sorted(candidate_by_profile["news"]),
                "review_required_cases": sorted(candidate_by_profile["news"]),
                "legacy_current_truth_cases": sorted(legacy_by_profile["news"]),
                "creative_breadth": {
                    "structural_family_count": 0,
                    "evidence_depth_case_count": 0,
                    "case_count_is_not_creative_breadth": True,
                },
                "creative_capability_matrix": news_matrix,
                "strengths": ["downstream_excel_contract_verified", "case_analysis_infrastructure_exists"],
                "major_gaps": [
                    "approved_news_pattern",
                    "approved_news_compatible_cases",
                    "micro_information_beat_evidence",
                    "news_hook_breadth",
                    "news_visual_text_progression",
                ],
            },
        },
        "case_acquisition_gaps": gaps,
        "current_state_answers": {
            "mix_can_produce": True,
            "news_can_produce": False,
            "news_failure_code": "research_coverage_insufficient",
            "news_mix_pattern_fallback": False,
            "mix_approved_creative_pattern_count": len(mix_patterns),
            "news_approved_creative_pattern_count": len(news_patterns),
            "case_compatibility_requires_human_review": True,
        },
        "export_contract_validation": {
            "mix": registry["profiles"]["mix"]["export_contract"],
            "news": registry["profiles"]["news"]["export_contract"],
            "templates_modified": False,
        },
        "authority": {
            "derived_planning_artifact": True,
            "can_approve_case": False,
            "can_approve_pattern": False,
            "can_change_compatibility": False,
            "can_claim_effectiveness": False,
            "can_modify_profile_contract": False,
            "case_facts_used_as_customer_authority": False,
            "new_case_collected": False,
            "new_pattern_created": False,
            "remote_model_called": False,
        },
        "validation": {
            "passed": True,
            "operational_readiness_separate_from_creative_coverage": True,
            "evidence_depth_separate_from_creative_breadth": True,
            "approved_candidate_and_review_required_cases_separated": True,
            "process_not_treated_as_proof": True,
            "gaps_are_research_targets_not_patterns": True,
        },
    }
    return report


def render_creative_coverage_report_markdown(report: dict[str, Any]) -> str:
    profiles = report["profiles"]
    lines = [
        "# Creative Coverage Report V1",
        "",
        "Status: Review Required",
        "",
        "本报告是 Derived Planning Artifact，不批准 Case、Pattern 或 Profile Compatibility。",
        "",
        "## Pattern Compatibility",
        "",
    ]
    for record in report.get("pattern_profile_compatibility") or []:
        lines.extend(
            [
                f"- Pattern: {record['pattern_id']}",
                f"- Compatible profiles: {', '.join(record['compatible_profiles'])}",
                f"- Compatibility status: {record['compatibility_status']}",
                f"- Effectiveness status: {record['effectiveness_status']}",
                "",
            ]
        )
    lines.extend(
        [
        "## Current Readiness",
        "",
        "| Profile | Operational Readiness | Creative Coverage | Approved Patterns | Approved Cases | Candidate Cases |",
        "|---|---|---|---:|---:|---:|",
        ]
    )
    for profile_id in ("mix", "news"):
        profile = profiles[profile_id]
        lines.append(
            "| {profile} | {readiness} | {coverage} | {patterns} | {approved} | {candidate} |".format(
                profile=profile_id,
                readiness=profile["operational_readiness"],
                coverage=profile["creative_coverage"],
                patterns=len(profile["approved_compatible_patterns"]),
                approved=len(profile["approved_compatible_cases"]),
                candidate=len(profile["candidate_compatible_cases"]),
            )
        )
    lines.extend(["", "## Existing Case Compatibility Audit", ""])
    for assessment in report["case_profile_compatibility_audit"]["assessments"]:
        evidence = assessment["structural_evidence_summary"]
        lines.extend(
            [
                f"### Case {assessment['case_id']}",
                "",
                f"- Operator hint: {assessment['operator_profile_hint'] or 'unknown'}",
                f"- Observed source profile: {assessment['observed_source_profile']}",
                f"- Candidate compatible profiles: {', '.join(assessment['compatible_generation_profiles_candidate']) or 'none'}",
                f"- Review status: {assessment['review_status']}",
                f"- Narration ratio: {evidence['narration_dominance']['speech_to_video_ratio']}",
                f"- Shot rhythm: {evidence['shot_duration_and_rhythm']['shot_count']} shots, mean {evidence['shot_duration_and_rhythm']['mean_shot_duration_seconds']}s",
                f"- Text behavior: independent beat ratio {evidence['text_beat_structure']['independent_text_shot_ratio']}",
                f"- Story progression: {evidence['story_progression']['structure_signature']}",
                "",
            ]
        )
    for profile_id, title in (("mix", "Mix Coverage"), ("news", "News Coverage")):
        profile = profiles[profile_id]
        lines.extend([f"## {title}", "", "Strengths:", ""])
        lines.extend(f"- {item}" for item in profile["strengths"])
        lines.extend(["", "Major gaps:", ""])
        lines.extend(f"- {item}" for item in profile["major_gaps"])
        lines.extend(["", "| Dimension | Approved | Candidate Observed | Missing / Weak |", "|---|---|---|---|"])
        for row in profile["creative_capability_matrix"]:
            lines.append(
                f"| {row['dimension']} | {', '.join(row['approved_capabilities']) or 'none'} | "
                f"{', '.join(row['candidate_observed_capabilities']) or 'none'} | "
                f"{', '.join(row['missing_or_weak_capabilities']) or 'none'} |"
            )
        lines.append("")
    lines.extend(["## Case Acquisition Gap Plan", ""])
    for profile_id in ("news", "mix"):
        lines.extend([f"### {profile_id}", ""])
        for gap in report["case_acquisition_gaps"]:
            if gap["target_profile"] != profile_id:
                continue
            lines.extend(
                [
                    f"- **{gap['missing_capability']}** ({gap['priority']}): {gap['why_it_matters']}",
                    f"  - Desired evidence: {'; '.join(gap['desired_case_characteristics'])}",
                ]
            )
        lines.append("")
    lines.extend(
        [
            "## Authority Boundary",
            "",
            "这些 Gap 是 Case Research Target，不是提前命名或批准的 Pattern。News 仍然禁止使用 Mix Pattern fallback；现有 Case Compatibility assessment 必须经过 Human Review 才能成为 canonical compatibility。",
            "",
        ]
    )
    return "\n".join(lines)


def validate_profile_compatibility_approval_v1(
    approval: dict[str, Any],
    *,
    registry_sha256: str | None = None,
    coverage_report_sha256: str | None = None,
) -> None:
    if approval.get("schema_version") != COMPATIBILITY_APPROVAL_SCHEMA_VERSION:
        raise ValueError("Production Profile Compatibility Approval schema is invalid.")
    if approval.get("status") != "approved":
        raise ValueError("Production Profile Compatibility Approval is not approved.")
    if str(approval.get("reviewer") or "").strip() != "李健":
        raise ValueError("Production Profile Compatibility Approval reviewer is invalid.")
    if registry_sha256 and (
        (approval.get("source_registry_ref") or {}).get("sha256")
        != registry_sha256
    ):
        raise ValueError("Compatibility Approval Registry SHA mismatch.")
    if coverage_report_sha256 and (
        (approval.get("source_coverage_report_ref") or {}).get("sha256")
        != coverage_report_sha256
    ):
        raise ValueError("Compatibility Approval Coverage Report SHA mismatch.")
    case_approvals = approval.get("case_profile_compatibility_approvals") or []
    expected_case_ids = {
        "7680512578585870322",
        "7683027343636542565",
        "7650056203686530319",
    }
    if {item.get("case_id") for item in case_approvals} != expected_case_ids:
        raise ValueError("Compatibility Approval must contain the three frozen Cases.")
    for item in case_approvals:
        if item.get("observed_source_profile") != "mix":
            raise ValueError("Approved Case observed_source_profile must be mix.")
        if item.get("approved_compatible_generation_profiles") != ["mix"]:
            raise ValueError("Approved Case compatibility must be mix only.")
        if item.get("news_compatibility") != "not_approved":
            raise ValueError("Approved Case News compatibility must remain not approved.")
        if item.get("decision") != "approved_mix_only":
            raise ValueError("Approved Case compatibility decision is invalid.")
        for field in (
            "source_approved_case_ref",
            "fingerprint_ref",
            "storyboard_ref",
        ):
            reference = item.get(field) or {}
            if len(str(reference.get("sha256") or "")) != 64:
                raise ValueError(f"Case compatibility approval is missing {field} SHA.")
    pattern = approval.get("pattern_profile_compatibility_approval") or {}
    if (
        pattern.get("pattern_id") != MIX_PATTERN_ID
        or pattern.get("compatible_profiles") != ["mix"]
        or pattern.get("news_compatibility") != "not_approved"
        or pattern.get("effectiveness") != "unvalidated"
    ):
        raise ValueError("Pattern Profile compatibility approval is invalid.")
    baseline = approval.get("creative_coverage_baseline_approval") or {}
    if baseline.get("decision") != "approve_as_current_coverage_baseline":
        raise ValueError("Creative Coverage baseline is not approved.")
    authority = approval.get("authority") or {}
    if any(
        authority.get(field) is not False
        for field in (
            "case_lifecycle_changed",
            "pattern_lifecycle_changed",
            "coverage_report_granted_approval_authority",
            "privacy_authority_changed",
            "proof_authority_changed",
            "remote_model_called",
        )
    ):
        raise ValueError("Compatibility Approval crosses a frozen Authority boundary.")


def _verified_lineage_ref(reference: dict[str, Any], *, artifact_type: str) -> dict[str, Any]:
    path = Path(str(reference.get("path") or "")).expanduser().resolve()
    expected_sha = str(reference.get("sha256") or "")
    if not path.is_file() or sha256_file(path) != expected_sha:
        raise RuntimeError(f"{artifact_type} lineage is missing or changed: {path}")
    return {
        "artifact_type": artifact_type,
        "path": str(path),
        "sha256": expected_sha,
        "source_artifact_modified": False,
    }


def build_profile_compatibility_approval_v1(
    *,
    registry_path: Path,
    coverage_report_path: Path,
    reviewer: str,
    approved_at: str | None = None,
) -> dict[str, Any]:
    registry_path = registry_path.expanduser().resolve()
    coverage_report_path = coverage_report_path.expanduser().resolve()
    registry = read_json(registry_path)
    report = read_json(coverage_report_path)
    validate_registry(registry)
    registry_sha = sha256_file(registry_path)
    report_sha = sha256_file(coverage_report_path)
    if report.get("schema_version") != COVERAGE_REPORT_SCHEMA_VERSION:
        raise RuntimeError("Creative Coverage Report schema is invalid.")
    if (report.get("source_registry_ref") or {}).get("sha256") != registry_sha:
        raise RuntimeError("Creative Coverage Report Registry lineage mismatch.")
    reviewer = reviewer.strip()
    if reviewer != "李健":
        raise ValueError("This Human Review Decision is authorized for reviewer 李健.")
    decision_time = approved_at or now_iso()
    assessments = (
        (report.get("case_profile_compatibility_audit") or {}).get("assessments")
        or []
    )
    case_approvals: list[dict[str, Any]] = []
    for assessment in sorted(assessments, key=lambda item: str(item.get("case_id"))):
        if (
            assessment.get("observed_source_profile") != "mix"
            or assessment.get("compatible_generation_profiles_candidate") != ["mix"]
            or assessment.get("review_status") != "review_required"
        ):
            raise RuntimeError("Case Profile assessment is not eligible for this decision.")
        lineage = assessment.get("lineage") or {}
        case_approvals.append(
            {
                "case_id": assessment.get("case_id"),
                "observed_source_profile": "mix",
                "approved_profile": "mix",
                "approved_compatible_generation_profiles": ["mix"],
                "news_compatibility": "not_approved",
                "decision": "approved_mix_only",
                "reviewer": reviewer,
                "approved_at": decision_time,
                "evidence_refs": [
                    {
                        "artifact_type": "creative_coverage_case_assessment",
                        "path": str(coverage_report_path),
                        "sha256": report_sha,
                        "json_pointer": (
                            "/case_profile_compatibility_audit/assessments/"
                            + str(assessment.get("case_id"))
                        ),
                    }
                ],
                "source_approved_case_ref": _verified_lineage_ref(
                    lineage.get("approved_case") or {}, artifact_type="approved_case"
                ),
                "fingerprint_ref": _verified_lineage_ref(
                    lineage.get("fingerprint") or {}, artifact_type="case_fingerprint"
                ),
                "storyboard_ref": _verified_lineage_ref(
                    lineage.get("storyboard") or {}, artifact_type="reverse_storyboard"
                ),
                "source_artifacts_modified": False,
            }
        )
    pattern_record = pattern_compatibility_record(
        registry,
        MIX_PATTERN_ID,
        str(
            ((report.get("pattern_profile_compatibility") or [{}])[0]).get(
                "approved_pattern_sha256"
            )
            or ""
        ),
    )
    pattern_lineage = pattern_record.get("lineage") or {}
    pattern_path = Path(str(pattern_lineage.get("pattern_path") or "")).resolve()
    if not pattern_path.is_file() or sha256_file(pattern_path) != pattern_record.get(
        "approved_pattern_sha256"
    ):
        raise RuntimeError("Approved Pattern lineage changed before compatibility approval.")
    approval = {
        "schema_version": COMPATIBILITY_APPROVAL_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "approval_id": "production_profile_compatibility_approval_v1",
        "status": "approved",
        "reviewer": reviewer,
        "approved_at": decision_time,
        "source_registry_ref": {
            "path": str(registry_path),
            "sha256": registry_sha,
            "schema_version": registry.get("schema_version"),
        },
        "source_coverage_report_ref": {
            "path": str(coverage_report_path),
            "sha256": report_sha,
            "schema_version": report.get("schema_version"),
            "source_status": report.get("status"),
            "source_report_modified": False,
        },
        "case_profile_compatibility_approvals": case_approvals,
        "pattern_profile_compatibility_approval": {
            "pattern_id": MIX_PATTERN_ID,
            "compatible_profiles": ["mix"],
            "news_compatibility": "not_approved",
            "effectiveness": "unvalidated",
            "decision": "approved_mix_only",
            "reviewer": reviewer,
            "approved_at": decision_time,
            "approved_pattern_ref": {
                "path": str(pattern_path),
                "sha256": pattern_record.get("approved_pattern_sha256"),
                "source_artifact_modified": False,
            },
            "registry_compatibility_record_ref": {
                "path": str(registry_path),
                "sha256": registry_sha,
                "pattern_id": MIX_PATTERN_ID,
            },
            "pattern_lifecycle_modified": False,
        },
        "creative_coverage_baseline_approval": {
            "decision": "approve_as_current_coverage_baseline",
            "effective_review_status": "approved",
            "source_report_ref": {
                "path": str(coverage_report_path),
                "sha256": report_sha,
                "source_report_modified": False,
            },
            "current_truth": {
                "mix": {
                    "operational_readiness": "production_ready",
                    "creative_coverage": "narrow",
                    "evidence_depth": 3,
                    "creative_structural_breadth": 1,
                },
                "news": {
                    "operational_readiness": "research_coverage_insufficient",
                    "creative_coverage": "insufficient",
                    "approved_news_pattern_count": 0,
                    "approved_news_compatible_case_count": 0,
                },
            },
            "coverage_report_is_derived_planning_artifact": True,
            "coverage_report_granted_case_or_pattern_authority": False,
        },
        "authority": {
            "approval_scope": "profile_compatibility_and_coverage_baseline_only",
            "case_lifecycle_changed": False,
            "pattern_lifecycle_changed": False,
            "coverage_report_granted_approval_authority": False,
            "persona_authority_changed": False,
            "content_ledger_changed": False,
            "privacy_authority_changed": False,
            "proof_authority_changed": False,
            "remote_model_called": False,
        },
    }
    validate_profile_compatibility_approval_v1(
        approval,
        registry_sha256=registry_sha,
        coverage_report_sha256=report_sha,
    )
    return approval


def _minimum_case_evidence() -> list[str]:
    return [
        "可访问的原始视频，画面与音频质量足以分析",
        "完整字幕，或可准确辨识的口播内容",
        "可识别的屏幕文字及其时间位置",
        "可恢复镜头边界、时长和顺序以生成 Fingerprint",
        "可以观察视觉与文字或口播之间的关系",
        "Case Approval 前能够核验来源并完成隐私检查",
    ]


def _research_target(
    *,
    target_id: str,
    profile: str,
    dimension: str,
    capability: str,
    desired: list[str],
    valuable: str,
    redundant: str,
    priority: str,
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "production_profile": profile,
        "expected_profile": profile,
        "coverage_dimension": dimension,
        "missing_capability": capability,
        "desired_structural_characteristics": desired,
        "what_would_make_the_case_valuable": valuable,
        "what_would_make_it_redundant": redundant,
        "acquisition_priority": priority,
        "planned_case_candidate_count": 1,
        "minimum_evidence_required": _minimum_case_evidence(),
        "artifact_type": "research_target_not_pattern",
        "operator_profile_hint_recommendation": profile,
        "final_compatibility_authority": (
            "structural_evidence_analysis_plus_human_review"
        ),
    }


def build_case_acquisition_plan_v1(
    *,
    registry_path: Path,
    coverage_report_path: Path,
    compatibility_approval_path: Path,
    created_at: str | None = None,
) -> dict[str, Any]:
    registry_path = registry_path.expanduser().resolve()
    coverage_report_path = coverage_report_path.expanduser().resolve()
    compatibility_approval_path = compatibility_approval_path.expanduser().resolve()
    registry = read_json(registry_path)
    report = read_json(coverage_report_path)
    approval = read_json(compatibility_approval_path)
    registry_sha = sha256_file(registry_path)
    report_sha = sha256_file(coverage_report_path)
    approval_sha = sha256_file(compatibility_approval_path)
    validate_registry(registry)
    validate_profile_compatibility_approval_v1(
        approval,
        registry_sha256=registry_sha,
        coverage_report_sha256=report_sha,
    )
    if (approval.get("creative_coverage_baseline_approval") or {}).get(
        "effective_review_status"
    ) != "approved":
        raise RuntimeError("Case Acquisition requires an Approved Coverage baseline.")
    news_targets = [
        _research_target(
            target_id="NEWS_PHASE_A_001",
            profile="news",
            dimension="opening_hook",
            capability="number_or_price_led_micro_information",
            desired=[
                "真实数字或价格构成第一个语义节拍",
                "后续节拍依次补充单位、上下文、限制条件和具体意义",
                "文字状态变化和视觉证据具有可恢复的时间关系",
                "整体由 micro beats 驱动，而不是把连续 Mix 旁白剪短",
            ],
            valuable="能够观察数字事实如何驱动有顺序的微信息与视觉状态。",
            redundant="数字只是装饰，或视频本质仍是被剪短的旁白加流程画面。",
            priority="critical",
        ),
        _research_target(
            target_id="NEWS_PHASE_A_002",
            profile="news",
            dimension="content_job_compatibility",
            capability="local_service_discovery",
            desired=[
                "地点、服务、适用对象和行动信息形成不同节拍",
                "无需长旁白，观众即可判断哪里提供什么服务",
                "视觉状态变化承担发现语境，而不是通用蒙太奇",
            ],
            valuable="补充当前 Evidence 中缺失的本地服务发现结构。",
            redundant="只是重复通用服务介绍，没有清晰的信息节拍推进。",
            priority="critical",
        ),
        _research_target(
            target_id="NEWS_PHASE_A_003",
            profile="news",
            dimension="opening_hook",
            capability="problem_or_alert",
            desired=[
                "问题或提醒以明确的信息状态开场",
                "受影响对象、限制条件和建议行动分为不同节拍",
                "视觉证据支持提醒内容，而不是制造不存在的风险",
            ],
            valuable="补充问题驱动、且信息顺序可分析的紧迫型结构。",
            redundant="只有耸动措辞，没有具体问题、边界或行动节拍。",
            priority="high",
        ),
        _research_target(
            target_id="NEWS_PHASE_A_004",
            profile="news",
            dimension="narrative_progression",
            capability="scene_contrast",
            desired=[
                "存在两个实质不同的场景或状态节拍",
                "对比改变观众理解，而不只是画面外观不同",
                "文字与视觉能够明确 before/after 或 A/B 关系",
            ],
            valuable="补充对比驱动的推进方式和新的视觉—语义关系。",
            redundant="只是不同镜头的蒙太奇，没有有意义的状态对比。",
            priority="high",
        ),
        _research_target(
            target_id="NEWS_PHASE_A_005",
            profile="news",
            dimension="narrative_progression",
            capability="event_explanation",
            desired=[
                "事件、时间、影响和应对分别形成可恢复节拍",
                "节拍顺序是理解事件经过的必要条件",
                "来源 Evidence 支持屏幕上展示的事件信息",
            ],
            valuable="补充按时间推进的事件解释，而不是静态服务说明。",
            redundant="只展示事件标题，没有影响或应对过程。",
            priority="high",
        ),
        _research_target(
            target_id="NEWS_PHASE_A_006",
            profile="news",
            dimension="content_job_compatibility",
            capability="concrete_benefit",
            desired=[
                "具体收益被明确表达为一个信息节拍",
                "收益由可观察 Evidence 或可归属事实限定和支持",
                "结束节拍明确说明对观众的实际价值",
            ],
            valuable="补充以具体收益驱动、Evidence 可追溯的压缩表达。",
            redundant="只使用方便、专业等通用表述，没有 Proof。",
            priority="high",
        ),
    ]
    mix_targets = [
        _research_target(
            target_id="MIX_GAP_001",
            profile="mix",
            dimension="narrative_progression",
            capability="customer_story",
            desired=[
                "真实人物、起始场景、转折和结果构成叙事主线",
                "人物身份、原话和媒体复用授权均可审查",
                "流程画面支持人物故事，而不是取代故事",
            ],
            valuable="在旁白加流程投射之外，增加人物驱动的故事宽度。",
            redundant="只是通用流程画面叠加无法核验的匿名评价。",
            priority="high_after_news",
        ),
        _research_target(
            target_id="MIX_GAP_002",
            profile="mix",
            dimension="speaker_mode",
            capability="frontline_pov",
            desired=[
                "一线专家的真实观察或判断驱动内容推进",
                "Speaker 的行为和可见工作支持其观点",
                "不要求一线角色回答超出角色范围的品牌战略",
            ],
            valuable="增加 Speaker-specific 判断和自然的一线叙事模式。",
            redundant="只是让一线人员朗读旁白，没有独有观察。",
            priority="high_after_news",
        ),
        _research_target(
            target_id="MIX_GAP_003",
            profile="mix",
            dimension="trust_proof",
            capability="verified_proof_or_result",
            desired=[
                "可验证结果、数字、文档、看板或前后状态是内容核心",
                "Proof 来源和 Claim 范围可以追溯",
                "视觉 Evidence 所证明的内容超出单纯过程展示",
            ],
            valuable="补充当前 process-only Evidence 无法提供的真实 Proof Coverage。",
            redundant="只展示工作过程，却声称未经支持的效果。",
            priority="high_after_news",
        ),
        _research_target(
            target_id="MIX_GAP_004",
            profile="mix",
            dimension="narrative_progression",
            capability="misconception_correction",
            desired=[
                "明确提出、检验并纠正一个具体误解",
                "纠正结论有可观察或可归属的 Evidence 支持",
                "推进过程带来新的决策价值，而不是换一种说法",
            ],
            valuable="补充当前流程叙事没有的纠错型推进。",
            redundant="只用“你以为”作为 Hook，随后仍回到相同流程说明。",
            priority="medium_after_news",
        ),
        _research_target(
            target_id="MIX_GAP_005",
            profile="mix",
            dimension="narrative_progression",
            capability="faq_question_answer",
            desired=[
                "真实 Audience Question 决定信息顺序",
                "回答包含明确边界、决策或行动价值",
                "镜头投射回答所需 Evidence，而不是通用工作画面",
            ],
            valuable="增加具有决策用途、可复用的 Q&A 结构。",
            redundant="问题 Hook 之后仍进入已有的通用流程结构。",
            priority="medium_after_news",
        ),
        _research_target(
            target_id="MIX_GAP_006",
            profile="mix",
            dimension="closing_cta",
            capability="intentional_closing_or_cta",
            desired=[
                "结束语义角色明确，并在前文有结构铺垫",
                "提问、互动或行动 CTA 自然承接 Content Job",
                "结束方式可在口播和 Storyboard Evidence 中观察",
            ],
            valuable="增加主动设计的收束能力，而不是信息讲完即停止。",
            redundant="没有结构连接，只在结尾附加通用关注 CTA。",
            priority="medium_after_news",
        ),
        _research_target(
            target_id="MIX_GAP_007",
            profile="mix",
            dimension="speaker_mode",
            capability="person_driven_narrative",
            desired=[
                "一个可识别人物的选择或行动组织整体顺序",
                "该人物贯穿 setup、development 和 payoff",
                "视觉投射保持人物连续性，而不是使用可互换 B-roll",
            ],
            valuable="为 Mix Coverage 增加人物连续性和叙事主动性。",
            redundant="人物只短暂出现，主线仍是通用旁白和流程画面。",
            priority="medium_after_news",
        ),
    ]
    plan = {
        "schema_version": CASE_ACQUISITION_PLAN_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "plan_id": "case_acquisition_plan_v1",
        "status": "review_required",
        "created_at": created_at or now_iso(),
        "source_refs": {
            "production_profile_registry": {
                "path": str(registry_path),
                "sha256": registry_sha,
            },
            "creative_coverage_report": {
                "path": str(coverage_report_path),
                "sha256": report_sha,
            },
            "human_compatibility_and_baseline_approval": {
                "path": str(compatibility_approval_path),
                "sha256": approval_sha,
                "reviewer": approval.get("reviewer"),
                "approved_at": approval.get("approved_at"),
            },
        },
        "profile_priority": ["news", "mix"],
        "coverage_baseline": (
            approval.get("creative_coverage_baseline_approval") or {}
        ).get("current_truth"),
        "news_phase_a_breadth_scout": {
            "status": "planned_review_required",
            "objective": "Explore distinct News creative structure space without creating Patterns.",
            "execution_authorized": False,
            "research_targets": news_targets,
        },
        "news_phase_b_depth_build": {
            "status": "not_started_blocked",
            "execution_authorized": False,
            "trigger_rule": {
                "required": [
                    "Phase A Case Candidate 已完成 Evidence Extraction",
                    "Phase A Case 已通过 Case Human Review 并成为 Approved",
                    "Human Review 已选出 1–2 个 Production 价值最高的结构方向",
                ],
                "then": (
                    "围绕入选方向获取相似但不重复的 Case；不得为了达到数量而降低 "
                    "Case Approval 标准。"
                ),
            },
            "pattern_lifecycle_reference": [
                "1 approved case -> fingerprint",
                "2 approved cases -> pattern hypothesis",
                "3+ approved cases -> pattern candidate",
                "pattern candidate -> human review",
            ],
        },
        "mix_gap_plan": {
            "status": "planned_lower_priority_than_news",
            "execution_authorized": False,
            "redundancy_exclusion": "不要继续优先收集 generic narration plus process visuals。",
            "research_targets": mix_targets,
        },
        "operator_intake_contract": {
            "operator_profile_hint_allowed": ["news", "mix", "hybrid", "uncertain"],
            "operator_notes_allowed": True,
            "research_target_may_recommend_expected_profile": True,
            "operator_hint_is_final_compatibility_authority": False,
            "final_compatibility_authority": (
                "structural_evidence_analysis_plus_human_review"
            ),
        },
        "authority": {
            "research_targets_are_patterns": False,
            "case_created": False,
            "video_search_performed": False,
            "video_download_performed": False,
            "pattern_mining_performed": False,
            "remote_model_called": False,
            "case_facts_are_customer_authority": False,
            "case_lifecycle_changed": False,
            "pattern_lifecycle_changed": False,
            "privacy_authority_changed": False,
            "proof_authority_changed": False,
        },
    }
    if len(news_targets) != 6 or len(mix_targets) != 7:
        raise RuntimeError("Case Acquisition target coverage is incomplete.")
    if any(
        item.get("artifact_type") != "research_target_not_pattern"
        for item in news_targets + mix_targets
    ):
        raise RuntimeError("Case Acquisition Research Targets cannot be Patterns.")
    return plan


def render_case_acquisition_plan_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Case Acquisition Plan V1",
        "",
        "Status: **Review Required — Planning Only**",
        "",
        "本计划只定义下一轮应寻找的结构 Evidence。本轮不搜索、不下载、不创建 Case，也不执行 Pattern Mining。",
        "",
        "## Current Approved Coverage Baseline",
        "",
        "- Mix：production_ready；creative coverage narrow；evidence depth 3；structural breadth 1。",
        "- News：research_coverage_insufficient；creative coverage insufficient；Approved Pattern 0；Approved compatible Case 0。",
        "",
        "## News Phase A — Breadth Scout",
        "",
        "每个方向先规划 1 个高质量 Case Candidate。目标是探索不同结构，不是提前创建 Pattern。",
        "",
    ]
    for target in plan["news_phase_a_breadth_scout"]["research_targets"]:
        lines.extend(
            [
                f"### {target['target_id']}｜{target['missing_capability']}",
                "",
                f"- Coverage dimension：{target['coverage_dimension']}",
                f"- Priority：{target['acquisition_priority']}",
                f"- Desired structure：{'；'.join(target['desired_structural_characteristics'])}",
                f"- Valuable when：{target['what_would_make_the_case_valuable']}",
                f"- Redundant when：{target['what_would_make_it_redundant']}",
                "",
            ]
        )
    phase_b = plan["news_phase_b_depth_build"]
    lines.extend(
        [
            "## News Phase B — Depth Build",
            "",
            "当前状态：**Not Started / Blocked**。只有 Phase A Case 完成 Evidence Extraction、通过 Case Human Review，并由人选出 1–2 个最高 Production 价值方向后才能启动。",
            "",
            f"启动后：{phase_b['trigger_rule']['then']}",
            "",
            "## Mix Gap Plan — Lower Priority",
            "",
            "不继续优先收集 generic narration + process visuals。",
            "",
        ]
    )
    for target in plan["mix_gap_plan"]["research_targets"]:
        lines.extend(
            [
                f"### {target['target_id']}｜{target['missing_capability']}",
                "",
                f"- Desired structure：{'；'.join(target['desired_structural_characteristics'])}",
                f"- Adds breadth because：{target['what_would_make_the_case_valuable']}",
                f"- Redundancy warning：{target['what_would_make_it_redundant']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Operator Contract",
            "",
            "未来采集时 operator_profile_hint 仍可选 news / mix / hybrid / uncertain，但仅用于路由。最终 compatibility 必须来自结构 Evidence Analysis + Human Review。",
            "",
            "## Stop Boundary",
            "",
            "该计划通过 Human Review 前，不得开始视频搜索、下载、Case 创建或 Pattern Mining。",
            "",
        ]
    )
    return "\n".join(lines)


def build_case_acquisition_plan_amendment_v1(
    *,
    plan_path: Path,
    reviewer: str,
    reviewed_at: str | None = None,
) -> dict[str, Any]:
    """Persist a reference-first Human amendment without rewriting the plan."""
    plan_path = plan_path.expanduser().resolve()
    plan = read_json(plan_path)
    if plan.get("schema_version") != CASE_ACQUISITION_PLAN_SCHEMA_VERSION:
        raise ValueError("Case Acquisition Plan schema is invalid.")
    if reviewer.strip() != "李健":
        raise ValueError("This amendment is authorized for reviewer 李健.")
    requirement = {
        "requirement": "能够完整恢复主要 Semantic Carrier。",
        "allowed_semantic_carriers": [
            "on_screen_text",
            "spoken_narration",
            "text_plus_narration",
            "necessary_visual_information_state",
        ],
        "required_recoverables": [
            "information_beat_sequence",
            "onscreen_text_timing",
            "visual_state",
            "shot_or_state_sequence",
            "text_audio_visual_relationship",
        ],
        "transcript_required_when_no_spoken_narration": False,
        "pure_onscreen_text_case_allowed": True,
    }
    amendment = {
        "schema_version": CASE_ACQUISITION_PLAN_AMENDMENT_SCHEMA_VERSION,
        "amendment_id": "case_acquisition_plan_v1_amendment_0001",
        "status": "approved",
        "decision": "approved_with_minor_amendment",
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at or now_iso(),
        "source_plan_ref": {
            "path": str(plan_path),
            "sha256": sha256_file(plan_path),
            "source_plan_modified": False,
        },
        "scope": "news_minimum_evidence_requirement_only",
        "superseded_wording": "完整字幕，或可准确辨识的口播内容",
        "effective_news_minimum_evidence_requirement": requirement,
        "other_plan_content_unchanged": True,
        "authority": {
            "profile_registry_changed": False,
            "creative_coverage_changed": False,
            "case_lifecycle_changed": False,
            "pattern_lifecycle_changed": False,
            "privacy_authority_changed": False,
            "proof_authority_changed": False,
            "persona_authority_changed": False,
            "content_ledger_changed": False,
        },
    }
    validate_case_acquisition_plan_amendment_v1(
        amendment,
        plan_sha256=sha256_file(plan_path),
    )
    return amendment


def validate_case_acquisition_plan_amendment_v1(
    amendment: dict[str, Any],
    *,
    plan_sha256: str | None = None,
) -> None:
    if amendment.get("schema_version") != CASE_ACQUISITION_PLAN_AMENDMENT_SCHEMA_VERSION:
        raise ValueError("Case Acquisition Plan Amendment schema is invalid.")
    if amendment.get("status") != "approved":
        raise ValueError("Case Acquisition Plan Amendment is not approved.")
    if amendment.get("decision") != "approved_with_minor_amendment":
        raise ValueError("Case Acquisition Plan Amendment decision is invalid.")
    if amendment.get("reviewer") != "李健":
        raise ValueError("Case Acquisition Plan Amendment reviewer is invalid.")
    source_ref = amendment.get("source_plan_ref") or {}
    if plan_sha256 and source_ref.get("sha256") != plan_sha256:
        raise ValueError("Case Acquisition Plan Amendment lineage mismatch.")
    if source_ref.get("source_plan_modified") is not False:
        raise ValueError("Case Acquisition Plan Amendment must not rewrite the plan.")
    requirement = amendment.get("effective_news_minimum_evidence_requirement") or {}
    if requirement.get("requirement") != "能够完整恢复主要 Semantic Carrier。":
        raise ValueError("Effective News evidence requirement is invalid.")
    if requirement.get("transcript_required_when_no_spoken_narration") is not False:
        raise ValueError("Pure on-screen-text News Cases cannot require a Transcript.")
    if requirement.get("pure_onscreen_text_case_allowed") is not True:
        raise ValueError("Pure on-screen-text News Cases must be allowed.")
    required = {
        "information_beat_sequence",
        "onscreen_text_timing",
        "visual_state",
        "shot_or_state_sequence",
        "text_audio_visual_relationship",
    }
    if set(requirement.get("required_recoverables") or []) != required:
        raise ValueError("News Semantic Carrier recoverables are incomplete.")
    if amendment.get("other_plan_content_unchanged") is not True:
        raise ValueError("The amendment may not change other plan content.")
    authority = amendment.get("authority") or {}
    if any(value is not False for value in authority.values()):
        raise ValueError("The amendment crosses a frozen Authority boundary.")


def validate_news_phase_a_scout_v1(
    scout: dict[str, Any],
    *,
    plan_sha256: str | None = None,
    amendment_sha256: str | None = None,
) -> None:
    if scout.get("schema_version") != NEWS_PHASE_A_SCOUT_SCHEMA_VERSION:
        raise ValueError("News Phase A Scout schema is invalid.")
    if scout.get("status") != "human_review_ready":
        raise ValueError("News Phase A Scout must stop at Human Review Ready.")
    if scout.get("production_profile") != "news":
        raise ValueError("News Phase A Scout production_profile must be news.")
    refs = scout.get("source_refs") or {}
    if plan_sha256 and (refs.get("case_acquisition_plan") or {}).get("sha256") != plan_sha256:
        raise ValueError("News Phase A Scout Plan lineage mismatch.")
    if amendment_sha256 and (refs.get("plan_amendment") or {}).get("sha256") != amendment_sha256:
        raise ValueError("News Phase A Scout Amendment lineage mismatch.")

    expected_target_ids = {f"NEWS_PHASE_A_{index:03d}" for index in range(1, 7)}
    targets = scout.get("research_targets") or []
    if {target.get("target_id") for target in targets} != expected_target_ids:
        raise ValueError("News Phase A Scout must contain the six approved targets.")

    selected_ids: set[str] = set()
    for target in targets:
        discoveries = target.get("discovery_candidates") or []
        if not 3 <= len(discoveries) <= 5:
            raise ValueError(
                f"{target.get('target_id')}: expected 3-5 Discovery Candidates."
            )
        formal = [item for item in discoveries if item.get("formal_pipeline_selected")]
        if len(formal) > 1:
            raise ValueError(f"{target.get('target_id')}: at most one formal Candidate is allowed.")
        if target.get("target_status") == "formal_candidate_selected" and len(formal) != 1:
            raise ValueError(f"{target.get('target_id')}: selected target needs one formal Candidate.")
        if target.get("target_status") == "no_suitable_candidate" and formal:
            raise ValueError(f"{target.get('target_id')}: no-suitable target cannot select a Candidate.")
        for item in discoveries:
            for field in (
                "candidate_id",
                "research_target_ref",
                "source_platform",
                "retrieved_at",
                "operator_profile_hint",
                "lightweight_structure_observation",
                "pre_screen",
            ):
                if field not in item:
                    raise ValueError(f"Discovery Candidate missing {field}.")
            if item.get("research_target_ref") != target.get("target_id"):
                raise ValueError("Discovery Candidate target lineage mismatch.")
            metadata = item.get("retrieval_metadata")
            if metadata and metadata.get("authority") != "not_effectiveness_authority":
                raise ValueError("Retrieval metrics cannot become Effectiveness Authority.")
            if item.get("formal_pipeline_selected"):
                if item.get("rank") != 1:
                    raise ValueError("Formal Candidate must be rank 1.")
                if not str(item.get("selected_reason") or "").strip():
                    raise ValueError("Formal Candidate is missing selected_reason.")
                if not str(item.get("why_better_than_alternatives") or "").strip():
                    raise ValueError("Formal Candidate is missing alternative comparison.")
                selected_ids.add(str(item.get("candidate_id")))
            elif item.get("case_created") is not False or item.get("pattern_mining_eligible") is not False:
                raise ValueError("Unselected Discovery Candidate cannot create a Case or enter Pattern Mining.")

    cases = scout.get("formal_case_candidates") or []
    if {str(item.get("candidate_id")) for item in cases} != selected_ids:
        raise ValueError("Formal Case Candidates must exactly match selected Discovery Candidates.")
    for case in cases:
        lifecycle = case.get("lifecycle") or {}
        if lifecycle.get("status") != "review_required" or lifecycle.get("approved") is not False:
            raise ValueError("Formal Case Candidate must stop at review_required.")
        profile = case.get("profile_analysis") or {}
        if profile.get("observed_source_profile") not in SOURCE_PROFILE_CLASSIFICATIONS:
            raise ValueError("Formal Case Candidate observed profile is invalid.")
        compatible = profile.get("compatible_generation_profiles_candidate") or []
        if any(item not in TARGET_PROFILES for item in compatible):
            raise ValueError("Formal Case Candidate compatibility candidate is invalid.")
        carrier = case.get("semantic_carrier_recovery") or {}
        if carrier.get("primary_semantic_carrier_recovered") is not True:
            raise ValueError("Formal Case Candidate did not recover its Semantic Carrier.")
        beats = case.get("micro_beat_sequence") or []
        if not beats:
            raise ValueError("Formal Case Candidate has no Micro Beat Sequence attempt.")
        for beat in beats:
            for field in (
                "beat_id",
                "semantic_role",
                "text_or_narration",
                "visual_state",
                "start_seconds",
                "end_seconds",
                "evidence_refs",
            ):
                if field not in beat:
                    raise ValueError(f"Micro Beat is missing {field}.")
        if case.get("pattern_state", {}).get("pattern_mining_performed") is not False:
            raise ValueError("News Phase A cannot perform Pattern Mining.")
        if case.get("authority", {}).get("case_specific_facts_transferred") is not False:
            raise ValueError("Case-specific facts cannot transfer to Customer Authority.")

    authority = scout.get("authority") or {}
    forbidden_true = (
        "case_auto_approved",
        "pattern_created",
        "pattern_mining_performed",
        "news_generation_performed",
        "news_excel_export_performed",
        "persona_modified",
        "content_ledger_modified",
        "performance_authority_introduced",
        "phase_b_started",
        "mix_acquisition_started",
    )
    if any(authority.get(field) is not False for field in forbidden_true):
        raise ValueError("News Phase A Scout crossed a stop boundary.")


def validate_news_profile_pre_gate(pre_gate: dict[str, Any]) -> None:
    """Validate the cheap structural gate used before target-fit assessment."""
    likelihood = pre_gate.get("news_profile_likelihood")
    if likelihood not in {"strong", "possible", "weak"}:
        raise ValueError("News Profile Pre-gate likelihood is invalid.")
    checks = pre_gate.get("checks") or {}
    required = {
        "main_semantic_carrier_recoverable_from_micro_information_states",
        "captions_are_not_merely_following_continuous_narration",
        "semantic_understanding_survives_without_continuous_narration",
        "multiple_distinct_information_states_or_beats",
        "compressed_information_progression_not_shortened_mix",
    }
    if set(checks) != required or any(
        not isinstance(checks.get(name), bool) for name in required
    ):
        raise ValueError("News Profile Pre-gate checks are incomplete.")
    if likelihood == "strong" and not all(checks.values()):
        raise ValueError("A strong News Profile Pre-gate must pass every check.")
    if not str(pre_gate.get("reason") or "").strip():
        raise ValueError("News Profile Pre-gate requires an evidence-grounded reason.")


def validate_news_phase_a_round_1_decision_v1(
    decision: dict[str, Any],
    *,
    round_1_scout_sha256: str | None = None,
) -> None:
    if decision.get("schema_version") != NEWS_PHASE_A_ROUND_1_DECISION_SCHEMA_VERSION:
        raise ValueError("News Phase A Round 1 decision schema is invalid.")
    if decision.get("status") != "human_decision_persisted":
        raise ValueError("Round 1 Human Decision status is invalid.")
    if decision.get("reviewer") != "李健":
        raise ValueError("Round 1 Human Decision reviewer is invalid.")
    source = decision.get("source_round_1_scout_ref") or {}
    if round_1_scout_sha256 and source.get("sha256") != round_1_scout_sha256:
        raise ValueError("Round 1 Human Decision source lineage mismatch.")
    expected = {
        "7059858129298803968": ("target_fit_approved", "news"),
        "7629552120978861049": (
            "reject_for_news_target_profile_mismatch",
            "mix",
        ),
        "7673808914944625983": (
            "reject_for_news_target_profile_mismatch",
            "mix",
        ),
        "7506527387438845184": (
            "retain_as_hybrid_boundary_candidate",
            "hybrid",
        ),
        "7582922932108774691": ("pending_final_human_review", "news"),
        "7614013950665018678": (
            "reject_for_news_target_profile_mismatch",
            "mix",
        ),
    }
    records = decision.get("case_decisions") or []
    if {str(item.get("case_id")) for item in records} != set(expected):
        raise ValueError("Round 1 Human Decision must resolve all six targets.")
    for item in records:
        expected_decision, expected_profile = expected[str(item.get("case_id"))]
        if item.get("decision") != expected_decision:
            raise ValueError("Round 1 Case decision differs from Human Authority.")
        if item.get("observed_source_profile") != expected_profile:
            raise ValueError("Round 1 observed source profile differs from Human Authority.")
        if item.get("pattern_created") is not False:
            raise ValueError("Round 1 Human Decision cannot create a Pattern.")
    if decision.get("phase_b_status") != "not_started_blocked":
        raise ValueError("Phase B must remain blocked.")


def validate_news_phase_a_round_2_scout_v1(
    scout: dict[str, Any],
    *,
    round_1_scout_sha256: str | None = None,
    round_1_decision_sha256: str | None = None,
) -> None:
    if scout.get("schema_version") != NEWS_PHASE_A_ROUND_2_SCOUT_SCHEMA_VERSION:
        raise ValueError("News Phase A Round 2 Scout schema is invalid.")
    if scout.get("status") != "human_review_ready":
        raise ValueError("Round 2 Scout must stop at Human Review Ready.")
    if scout.get("production_profile") != "news":
        raise ValueError("Round 2 Scout production_profile must be news.")
    refs = scout.get("source_refs") or {}
    if round_1_scout_sha256 and (
        (refs.get("round_1_scout") or {}).get("sha256")
        != round_1_scout_sha256
    ):
        raise ValueError("Round 2 Scout Round 1 lineage mismatch.")
    if round_1_decision_sha256 and (
        (refs.get("round_1_human_decision") or {}).get("sha256")
        != round_1_decision_sha256
    ):
        raise ValueError("Round 2 Scout Human Decision lineage mismatch.")
    expected_targets = {
        "NEWS_PHASE_A_002",
        "NEWS_PHASE_A_003",
        "NEWS_PHASE_A_004",
        "NEWS_PHASE_A_006",
    }
    targets = scout.get("research_targets") or []
    if {item.get("target_id") for item in targets} != expected_targets:
        raise ValueError("Round 2 Scout contains an unauthorized target.")
    round_1_urls = set(scout.get("round_1_candidate_urls_excluded") or [])
    selected_ids: set[str] = set()
    for target in targets:
        discoveries = target.get("discovery_candidates") or []
        if not 3 <= len(discoveries) <= 5:
            raise ValueError("Each Round 2 target needs 3-5 new discoveries.")
        formal = [item for item in discoveries if item.get("formal_pipeline_selected")]
        if len(formal) > 1:
            raise ValueError("Each Round 2 target may select at most one formal Case.")
        if target.get("target_status") == "formal_candidate_selected" and len(formal) != 1:
            raise ValueError("A selected Round 2 target needs one formal Candidate.")
        if target.get("target_status") == "no_suitable_news_candidate" and formal:
            raise ValueError("No-suitable News target cannot select a formal Candidate.")
        for candidate in discoveries:
            if candidate.get("source_url") in round_1_urls:
                raise ValueError("Round 2 reused a rejected Round 1 Candidate.")
            validate_news_profile_pre_gate(candidate.get("news_profile_pre_gate") or {})
            if candidate.get("formal_pipeline_selected"):
                if candidate.get("rank") != 1:
                    raise ValueError("Round 2 formal Candidate must be rank 1.")
                if (
                    candidate["news_profile_pre_gate"]["news_profile_likelihood"]
                    != "strong"
                ):
                    raise ValueError("Only strong News Candidates may enter Formal Pipeline.")
                selected_ids.add(str(candidate.get("candidate_id")))
            elif candidate.get("case_created") is not False:
                raise ValueError("Unselected Round 2 discovery cannot create a Case.")
    formal_cases = scout.get("formal_case_candidates") or []
    if {str(item.get("candidate_id")) for item in formal_cases} != selected_ids:
        raise ValueError("Round 2 formal Case list does not match selections.")
    for case in formal_cases:
        validate_news_profile_pre_gate(case.get("news_profile_pre_gate") or {})
        if (case.get("lifecycle") or {}).get("status") != "review_required":
            raise ValueError("Round 2 formal Case must stop at review_required.")
        if (case.get("profile_analysis") or {}).get("observed_source_profile") not in SOURCE_PROFILE_CLASSIFICATIONS:
            raise ValueError("Round 2 observed source profile is invalid.")
        if not case.get("micro_beat_sequence"):
            raise ValueError("Round 2 formal Case has no Micro Beat Sequence.")
    authority = scout.get("authority") or {}
    for field in (
        "case_auto_approved",
        "pattern_created",
        "pattern_mining_performed",
        "phase_b_started",
        "news_generation_performed",
        "news_excel_export_performed",
        "persona_modified",
        "content_ledger_modified",
    ):
        if authority.get(field) is not False:
            raise ValueError("Round 2 Scout crossed a frozen boundary.")


def validate_case_profile_compatibility_approval_v1(
    approval: dict[str, Any],
    *,
    approved_case_sha256: str | None = None,
) -> None:
    if approval.get("schema_version") != CASE_PROFILE_COMPATIBILITY_APPROVAL_SCHEMA_VERSION:
        raise ValueError("Case Profile Compatibility Approval schema is invalid.")
    if approval.get("status") != "approved":
        raise ValueError("News Case Profile Compatibility is not approved.")
    if not str(approval.get("case_id") or "").strip():
        raise ValueError("News Case compatibility approval is missing case_id.")
    if approval.get("reviewer") != "李健":
        raise ValueError("News Case compatibility reviewer is invalid.")
    if approval.get("observed_source_profile") != "news":
        raise ValueError("Approved observed source profile must be news.")
    if approval.get("approved_compatible_generation_profiles") != ["news"]:
        raise ValueError("Approved compatibility must be news only.")
    if approval.get("decision") != "approved_news_only":
        raise ValueError("News Case compatibility decision is invalid.")
    case_ref = approval.get("source_approved_case_ref") or {}
    if approved_case_sha256 and case_ref.get("sha256") != approved_case_sha256:
        raise ValueError("News Case compatibility Case SHA mismatch.")
    if approval.get("pattern_created") is not False:
        raise ValueError("Compatibility approval cannot create a Pattern.")


def validate_news_phase_a_closure_v1(closure: dict[str, Any]) -> None:
    if closure.get("schema_version") != NEWS_PHASE_A_CLOSURE_SCHEMA_VERSION:
        raise ValueError("News Phase A Closure schema is invalid.")
    if closure.get("status") != "complete":
        raise ValueError("News Phase A must be explicitly complete.")
    outcomes = closure.get("research_target_outcomes") or []
    if {item.get("target_id") for item in outcomes} != {
        f"NEWS_PHASE_A_{index:03d}" for index in range(1, 7)
    }:
        raise ValueError("News Phase A Closure must resolve all six targets.")
    supported = {
        item.get("target_id")
        for item in outcomes
        if item.get("result") == "supported_structural_direction"
    }
    if supported != {
        "NEWS_PHASE_A_001",
        "NEWS_PHASE_A_004",
        "NEWS_PHASE_A_005",
    }:
        raise ValueError("News Phase A supported directions differ from Human Authority.")
    for item in outcomes:
        if item.get("target_id") in {
            "NEWS_PHASE_A_002",
            "NEWS_PHASE_A_003",
            "NEWS_PHASE_A_006",
        }:
            if item.get("result") != "no_independent_news_structure_evidenced":
                raise ValueError("Unsupported Phase A target was not closed conservatively.")
            if item.get("pattern_created") is not False:
                raise ValueError("A research closure cannot create a Pattern.")
    if closure.get("approved_news_pattern_count") != 0:
        raise ValueError("Phase A Closure cannot create an Approved News Pattern.")
    authority = closure.get("authority") or {}
    for field in (
        "pattern_created",
        "pattern_mining_performed",
        "news_generation_performed",
        "news_excel_export_performed",
        "persona_modified",
        "content_ledger_modified",
    ):
        if authority.get(field) is not False:
            raise ValueError("Phase A Closure crossed an Authority boundary.")


def validate_case_profile_structural_decision_v1(decision: dict[str, Any]) -> None:
    if decision.get("schema_version") != CASE_PROFILE_STRUCTURAL_DECISION_SCHEMA_VERSION:
        raise ValueError("Case structural/profile decision schema is invalid.")
    if decision.get("decision") != "structural_profile_approved_gate_pending":
        raise ValueError("Case structural/profile decision is invalid.")
    if decision.get("observed_source_profile") != "news":
        raise ValueError("Pending structural decision must preserve observed=news.")
    if decision.get("structural_compatible_generation_profiles") != ["news"]:
        raise ValueError("Pending structural compatibility must remain news-only.")
    if decision.get("canonical_approved_compatible_generation_profiles") != []:
        raise ValueError("A gate-pending Case cannot gain canonical compatibility.")
    if decision.get("case_lifecycle_status") != "review_required":
        raise ValueError("A gate-pending Case must remain review_required.")
    gates = decision.get("unresolved_gates") or []
    if not {"privacy_review", "source_rights_review"}.issubset(set(gates)):
        raise ValueError("Pending privacy/source-rights gates must be explicit.")
    if decision.get("pattern_created") is not False:
        raise ValueError("Structural approval cannot create a Pattern.")


def validate_news_creative_coverage_update_v1(update: dict[str, Any]) -> None:
    if update.get("schema_version") != NEWS_CREATIVE_COVERAGE_UPDATE_SCHEMA_VERSION:
        raise ValueError("News Creative Coverage Update schema is invalid.")
    news = update.get("news_current_coverage") or {}
    if news.get("operational_readiness") != "research_coverage_insufficient":
        raise ValueError("News readiness cannot advance without an Approved Pattern.")
    if news.get("approved_news_pattern_count") != 0:
        raise ValueError("News pattern coverage must remain zero.")
    if set(news.get("structural_evidence_directions") or []) != {
        "number_or_price_led_micro_information",
        "scene_contrast",
        "event_or_campaign_information_progression",
    }:
        raise ValueError("News evidence breadth is not the approved Phase A result.")
    if update.get("changes_canonical_coverage_authority") is not False:
        raise ValueError("Coverage Update is derived planning Evidence only.")


def validate_news_phase_b_depth_build_plan_v1(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != NEWS_PHASE_B_DEPTH_BUILD_PLAN_SCHEMA_VERSION:
        raise ValueError("News Phase B Depth Build Plan schema is invalid.")
    if plan.get("status") != "round_1_started":
        raise ValueError("News Phase B Round 1 status is invalid.")
    directions = plan.get("directions") or []
    if [item.get("direction_id") for item in directions] != [
        "number_or_price_led_micro_information",
        "scene_contrast",
    ]:
        raise ValueError("Phase B may include only the two Human-selected directions.")
    for item in directions:
        if not 4 <= item.get("discovery_candidate_count_target", 0) <= 6:
            raise ValueError("Each Phase B direction must scout 4-6 Candidates.")
        if item.get("formal_candidate_limit") != 2:
            raise ValueError("Each Phase B direction is limited to two formal Candidates.")
        if item.get("desired_invariants_authority") != "research_hypothesis_not_pattern":
            raise ValueError("Desired invariants cannot become Pattern Authority.")
    if plan.get("coverage_only_direction") != "event_or_campaign_explanation":
        raise ValueError("Event Explanation must remain coverage-only in Round 1.")
    if plan.get("pattern_created") is not False:
        raise ValueError("Phase B Plan cannot create a Pattern.")


def validate_news_phase_b_round_1_scout_v1(scout: dict[str, Any]) -> None:
    if scout.get("schema_version") != NEWS_PHASE_B_ROUND_1_SCOUT_SCHEMA_VERSION:
        raise ValueError("News Phase B Round 1 Scout schema is invalid.")
    if scout.get("status") != "human_review_ready":
        raise ValueError("Phase B Round 1 must stop at Human Review Ready.")
    expected = {
        "number_or_price_led_micro_information",
        "scene_contrast",
    }
    directions = scout.get("directions") or []
    if {item.get("direction_id") for item in directions} != expected:
        raise ValueError("Phase B Scout contains an unauthorized direction.")
    selected: set[str] = set()
    for direction in directions:
        discoveries = direction.get("discovery_candidates") or []
        if not 4 <= len(discoveries) <= 6:
            raise ValueError("Each Phase B direction needs 4-6 Discovery Candidates.")
        formal = [item for item in discoveries if item.get("formal_pipeline_selected")]
        if len(formal) > 2:
            raise ValueError("A Phase B direction may select at most two formal Candidates.")
        for candidate in discoveries:
            validate_news_profile_pre_gate(candidate.get("news_profile_pre_gate") or {})
            similarity = candidate.get("seed_structural_similarity_gate") or {}
            if similarity.get("result") not in {"pass", "fail"}:
                raise ValueError("Seed Structural Similarity gate result is missing.")
            if candidate.get("formal_pipeline_selected"):
                if candidate["news_profile_pre_gate"]["news_profile_likelihood"] != "strong":
                    raise ValueError("Formal Phase B Candidate must be strong News.")
                if similarity.get("result") != "pass":
                    raise ValueError("Formal Phase B Candidate must match its Seed structure.")
                selected.add(str(candidate.get("candidate_id")))
            elif candidate.get("case_created") is not False:
                raise ValueError("Unselected Phase B discovery cannot create a Case.")
    formal_cases = scout.get("formal_case_candidates") or []
    if {str(item.get("candidate_id")) for item in formal_cases} != selected:
        raise ValueError("Phase B formal Case list does not match selected discoveries.")
    for case in formal_cases:
        lifecycle = case.get("lifecycle") or {}
        if lifecycle.get("status") != "review_required" or lifecycle.get("approved") is not False:
            raise ValueError("Phase B formal Cases must stop at review_required.")
        if not case.get("micro_beat_sequence"):
            raise ValueError("Phase B formal Case is missing Micro Beat evidence.")
        if case.get("pattern_state", {}).get("pattern_mining_performed") is not False:
            raise ValueError("Phase B Round 1 cannot start Pattern Mining.")
    authority = scout.get("authority") or {}
    for field in (
        "case_auto_approved",
        "pattern_created",
        "pattern_mining_performed",
        "cross_case_research_started",
        "news_generation_performed",
        "news_excel_export_performed",
        "persona_modified",
        "content_ledger_modified",
    ):
        if authority.get(field) is not False:
            raise ValueError("Phase B Round 1 crossed a stop boundary.")


def validate_news_phase_b_human_review_closure_v1(
    closure: dict[str, Any],
) -> None:
    if closure.get("schema_version") != NEWS_PHASE_B_HUMAN_REVIEW_CLOSURE_SCHEMA_VERSION:
        raise ValueError("News Phase B Human Review Closure schema is invalid.")
    if closure.get("status") != "human_structural_review_complete_governance_pending":
        raise ValueError("News Phase B Human Review Closure status is invalid.")
    if closure.get("reviewer") != "李健":
        raise ValueError("News Phase B Human Review Closure reviewer is invalid.")
    decisions = closure.get("human_structural_profile_decisions") or []
    expected = {
        "7640840358842207507": (
            "price_offer_led_micro_information",
            "core_evidence",
        ),
        "7635146658208744867": (
            "price_offer_led_micro_information",
            "variant_evidence",
        ),
        "7639693960727179747": ("scene_contrast", "core_evidence"),
        "7616327461634652005": (
            "scene_contrast",
            "boundary_variant_evidence",
        ),
    }
    if {str(item.get("case_id")) for item in decisions} != set(expected):
        raise ValueError("Human Review Closure must contain exactly four decisions.")
    for decision in decisions:
        case_id = str(decision.get("case_id"))
        direction, research_role = expected[case_id]
        if (
            decision.get("human_structural_profile_decision") != "pass"
            or decision.get("observed_source_profile") != "news"
            or decision.get("compatible_generation_profiles_candidate") != ["news"]
            or decision.get("research_direction") != direction
            or decision.get("research_role") != research_role
            or decision.get("canonical_case_lifecycle_status") != "review_required"
            or decision.get("canonical_case_approval_withheld") is not True
        ):
            raise ValueError(f"Human structural decision is invalid: {case_id}")
        case_ref = decision.get("case_ref") or {}
        if len(str(case_ref.get("sha256") or "")) != 64:
            raise ValueError(f"Human structural decision lacks Case SHA: {case_id}")
    scope = closure.get("research_scope_amendment") or {}
    if (
        scope.get("historical_research_target")
        != "number_or_price_led_micro_information"
        or scope.get("effective_research_evidence_scope")
        != "price_offer_led_micro_information"
        or scope.get("scope_evidence") != "price_offer_led_only"
        or scope.get("broader_number_led_status") != "insufficient_evidence"
        or scope.get("historical_artifacts_modified") is not False
    ):
        raise ValueError("Price-led Research scope amendment is invalid.")
    roles = closure.get("research_role_authority") or {}
    if any(
        roles.get(field) is not False
        for field in (
            "changes_case_approval_authority",
            "changes_pattern_lifecycle_threshold",
            "invalidates_boundary_evidence",
        )
    ):
        raise ValueError("Research role metadata crosses an Authority boundary.")
    authority = closure.get("authority") or {}
    for field in (
        "case_approved",
        "case_artifact_modified",
        "pattern_research_performed",
        "cross_case_comparison_performed",
        "new_case_acquisition_performed",
        "remote_model_called",
        "privacy_authority_changed",
        "proof_authority_changed",
    ):
        if authority.get(field) is not False:
            raise ValueError("Human Review Closure crosses a frozen Authority boundary.")


def validate_case_source_governance_audit_v1(audit: dict[str, Any]) -> None:
    if audit.get("schema_version") != CASE_SOURCE_GOVERNANCE_AUDIT_SCHEMA_VERSION:
        raise ValueError("Case Source Governance Audit schema is invalid.")
    if audit.get("status") != "human_policy_decision_required":
        raise ValueError("Governance Audit must remain human_policy_decision_required.")
    cases = audit.get("case_audit") or []
    expected = {
        "7680512578585870322",
        "7683027343636542565",
        "7650056203686530319",
        "7059858129298803968",
        "7582922932108774691",
        "7507825653623344396",
        "7640840358842207507",
        "7635146658208744867",
        "7639693960727179747",
        "7616327461634652005",
    }
    if {str(item.get("case_id")) for item in cases} != expected:
        raise ValueError("Governance Audit does not contain the required ten Cases.")
    for item in cases:
        if len(str((item.get("case_ref") or {}).get("sha256") or "")) != 64:
            raise ValueError("Governance Audit Case lineage is incomplete.")
        if item.get("source_provenance", {}).get("traceable") is not True:
            raise ValueError("Governance Audit requires traceable source provenance.")
    distinction = audit.get("governance_distinction") or {}
    if set(distinction) != {
        "source_provenance",
        "research_ingestion_eligibility",
        "media_reuse_rights",
    }:
        raise ValueError("Governance Audit must keep the three rights concepts separate.")
    drift = audit.get("detected_drift") or {}
    if (
        drift.get("source_rights_field_origin")
        != "news_acquisition_conservative_field_not_canonical_approval_gate"
        or drift.get("canonical_case_policy_silently_changed") is not False
        or drift.get("field_semantics_overloaded") is not True
    ):
        raise ValueError("Governance Audit drift finding is invalid.")
    blockers = audit.get("blocking_semantics") or {}
    if blockers.get("research_ingestion_eligibility") != "human_policy_decision_required":
        raise ValueError("Unfrozen research-ingestion policy must fail closed for this closure.")
    if blockers.get("media_reuse_rights") != "blocks_footage_reuse_not_structural_fact_authority":
        raise ValueError("Media reuse rights semantics are not sufficiently separated.")
    authority = audit.get("authority") or {}
    for field in (
        "legal_conclusion_made",
        "case_approval_policy_changed",
        "case_lifecycle_changed",
        "privacy_authority_changed",
        "proof_authority_changed",
        "pattern_research_performed",
        "new_case_acquisition_performed",
        "remote_model_called",
    ):
        if authority.get(field) is not False:
            raise ValueError("Governance Audit crosses an Authority boundary.")


def validate_case_source_governance_policy_v1(policy: dict[str, Any]) -> None:
    if policy.get("schema_version") != CASE_SOURCE_GOVERNANCE_POLICY_SCHEMA_VERSION:
        raise ValueError("Case Source Governance Policy schema is invalid.")
    if policy.get("status") != "approved_frozen" or policy.get("version") != "V1.0":
        raise ValueError("Case Source Governance Policy is not Approved/Frozen V1.0.")
    if policy.get("reviewer") != "李健":
        raise ValueError("Case Source Governance Policy reviewer is invalid.")
    approval = policy.get("canonical_case_approval") or {}
    if (
        approval.get("authorization_scope")
        != "internal_creative_structural_research_eligibility"
        or approval.get("grants_copyright_ownership") is not False
        or approval.get("grants_media_reuse_permission") is not False
        or approval.get("grants_footage_redistribution_permission") is not False
        or approval.get("grants_customer_production_footage_authorization") is not False
    ):
        raise ValueError("Canonical Case Approval scope is invalid.")
    ingestion = policy.get("research_ingestion_eligibility") or {}
    if set(ingestion.get("allowed_values") or []) != {
        "eligible_for_internal_research",
        "review_required",
        "blocked",
    }:
        raise ValueError("Research ingestion statuses are invalid.")
    media = policy.get("media_reuse_rights") or {}
    if set(media.get("allowed_values") or []) != {
        "licensed",
        "authorized",
        "not_established",
        "blocked",
    }:
        raise ValueError("Media reuse statuses are invalid.")
    if (
        media.get("public_source_default") != "not_established"
        or media.get("changed_by_case_approval") is not False
    ):
        raise ValueError("Public-source media reuse must default to not_established.")
    decisions = policy.get("pending_case_human_governance_decisions") or []
    expected = {
        "7507825653623344396",
        "7640840358842207507",
        "7635146658208744867",
        "7639693960727179747",
        "7616327461634652005",
    }
    if {str(item.get("case_id")) for item in decisions} != expected:
        raise ValueError("Governance Policy must contain the five Human Case decisions.")
    for decision in decisions:
        if (
            decision.get("canonical_case_decision") != "approve"
            or decision.get("research_ingestion_eligibility")
            != "eligible_for_internal_research"
            or decision.get("media_reuse_rights") != "not_established"
            or decision.get("observed_source_profile") != "news"
            or decision.get("compatible_generation_profiles") != ["news"]
        ):
            raise ValueError("Pending Case governance decision is invalid.")
    authority = policy.get("authority") or {}
    if (
        authority.get("legal_rights_claimed") is not False
        or authority.get("pattern_lifecycle_changed") is not False
        or authority.get("proof_authority_changed") is not False
        or authority.get("privacy_authority_changed") is not False
    ):
        raise ValueError("Governance Policy crosses an Authority boundary.")


def validate_case_source_governance_companion_v1(
    companion: dict[str, Any],
    *,
    expected_case_sha256: str | None = None,
) -> None:
    if companion.get("schema_version") != CASE_SOURCE_GOVERNANCE_COMPANION_SCHEMA_VERSION:
        raise ValueError("Case Source Governance Companion schema is invalid.")
    legacy_observation = companion.get("legacy_source_rights_field_observation") or {}
    policy_ref = companion.get("governance_policy_ref") or {}
    policy_not_applicable = policy_ref.get("applicable") is False
    if policy_not_applicable:
        if (
            legacy_observation.get("present") is not False
            or companion.get("governance_policy_version") is not None
            or policy_ref.get("path") is not None
            or policy_ref.get("sha256") is not None
        ):
            raise ValueError(
                "Current-schema Case cannot waive an applicable legacy Governance policy."
            )
    elif companion.get("governance_policy_version") != "V1.0":
        raise ValueError("Case Source Governance Companion policy version is invalid.")
    if companion.get("canonical_case_status") != "approved":
        raise ValueError("Case Source Governance Companion requires an Approved Case.")
    case_ref = companion.get("case_ref") or {}
    if expected_case_sha256 and case_ref.get("sha256") != expected_case_sha256:
        raise ValueError("Case Source Governance Companion Case SHA mismatch.")
    if companion.get("source_provenance", {}).get("status") != "traceable":
        raise ValueError("Case Source Governance Companion provenance is not traceable.")
    if companion.get("research_ingestion_eligibility") != "eligible_for_internal_research":
        raise ValueError("Approved Case is not eligible for internal research.")
    if companion.get("media_reuse_rights") not in {
        "licensed",
        "authorized",
        "not_established",
        "blocked",
    }:
        raise ValueError("Case Source Governance Companion media rights are invalid.")
    if companion.get("case_approval_changed_media_reuse_rights") is not False:
        raise ValueError("Case Approval cannot change media reuse rights.")


def case_is_eligible_for_production_footage(
    companion: dict[str, Any],
) -> bool:
    validate_case_source_governance_companion_v1(companion)
    return companion.get("media_reuse_rights") in {"licensed", "authorized"}


def validate_news_cross_case_research_bundle_v1(bundle: dict[str, Any]) -> None:
    if bundle.get("schema_version") != NEWS_CROSS_CASE_RESEARCH_BUNDLE_SCHEMA_VERSION:
        raise ValueError("News Cross-case Research Bundle schema is invalid.")
    if bundle.get("status") != "cross_case_research_ready":
        raise ValueError("News Cross-case Research Bundle is not ready.")
    cases = bundle.get("cases") or []
    if len(cases) < 2 or len({item.get("case_id") for item in cases}) != len(cases):
        raise ValueError("News Cross-case Research Bundle requires N >= 2 distinct Cases.")
    if bundle.get("canonical_approved_case_count") != len(cases):
        raise ValueError("News Cross-case Research Bundle Case count is inconsistent.")
    for item in cases:
        if item.get("canonical_case_status") != "approved":
            raise ValueError("News Cross-case Research Bundle requires Approved Cases.")
        if item.get("observed_source_profile") != "news":
            raise ValueError("News Cross-case Research Bundle contains non-News Evidence.")
        if item.get("research_ingestion_eligibility") != "eligible_for_internal_research":
            raise ValueError("Research Bundle contains ineligible Case Evidence.")
        if item.get("media_reuse_rights") != "not_established":
            raise ValueError("Research Bundle must not imply media reuse rights.")
        if not item.get("micro_beat_structure"):
            raise ValueError("Research Bundle Case lacks Micro Beat structure.")
        for field in ("case_ref", "fingerprint_ref", "storyboard_ref"):
            if len(str((item.get(field) or {}).get("sha256") or "")) != 64:
                raise ValueError("Research Bundle lineage is incomplete.")
    if bundle.get("pattern_candidate_created") is not False:
        raise ValueError("Research Input Bundle cannot create a Pattern Candidate.")
    if bundle.get("comparison_executed") is not False:
        raise ValueError("This preparation Bundle cannot claim comparison execution.")
    authority = bundle.get("authority") or {}
    for field in (
        "case_specific_facts_used_as_customer_authority",
        "effectiveness_claimed",
        "proof_upgraded",
        "pattern_created",
        "remote_model_called",
    ):
        if authority.get(field) is not False:
            raise ValueError("Research Bundle crosses an Authority boundary.")


def render_news_phase_a_round_2_markdown(scout: dict[str, Any]) -> str:
    lines = [
        "# News Phase A — Round 2 Targeted Discovery",
        "",
        "Status: **Human Review Ready**",
        "",
        "本轮先做 News Profile Pre-gate，再判断 Research Target Fit。只有 `strong` 候选进入正式 Case Pipeline。",
        "",
    ]
    for target in scout.get("research_targets") or []:
        lines.extend(
            [
                f"## {target['target_id']}｜{target['missing_capability']}",
                "",
                f"- Discovery Candidates：{len(target.get('discovery_candidates') or [])}",
                f"- Target status：`{target['target_status']}`",
                f"- Formal Candidate：`{target.get('formal_candidate_ref') or 'none'}`",
                "",
                "| Candidate | Likelihood | Pre-gate result | Formal |",
                "|---|---|---|---|",
            ]
        )
        for item in target.get("discovery_candidates") or []:
            gate = item["news_profile_pre_gate"]
            lines.append(
                f"| {item['candidate_id']} | {gate['news_profile_likelihood']} | "
                f"{gate['reason']} | {'yes' if item['formal_pipeline_selected'] else 'no'} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Stop Boundary",
            "",
            "Phase B remains `not_started_blocked`. No Pattern, News generation, or News export was created.",
            "",
        ]
    )
    return "\n".join(lines)


def render_concise_news_case_review_markdown(case: dict[str, Any]) -> str:
    carrier = case["semantic_carrier_recovery"]
    profile = case["profile_analysis"]
    lines = [
        f"# News Case Concise Human Review｜{case['case_id']}",
        "",
        "Status: **Pending Final Human Review / Not Approved**",
        "",
        f"- Source：{case['source_evidence']['source_url']}",
        f"- Raw Semantic Carrier：`{carrier['carrier_type']}`",
        f"- Observed source profile：`{profile['observed_source_profile']}`",
        f"- Compatibility candidate：`{profile['compatible_generation_profiles_candidate']}`",
        "",
        "## Why continuous narration is not required",
        "",
        carrier["relationship_summary"],
        "",
        "## Seven Micro Beats",
        "",
        "| Beat | Time | Text / narration | Visual state | Evidence refs |",
        "|---|---|---|---|---|",
    ]
    for beat in case["micro_beat_sequence"]:
        lines.append(
            f"| {beat['beat_id']} | {beat['start_seconds']:.3f}–{beat['end_seconds']:.3f}s | "
            f"{str(beat['text_or_narration']).replace('|', '｜')} | "
            f"{str(beat['visual_state']).replace('|', '｜')} | "
            f"{', '.join(beat['evidence_refs'])} |"
        )
    lines.extend(
        [
            "",
            "## Profile classification reasoning",
            "",
            "事件时间、年度报告、任务/奖励、玩法列表、专属抽奖、入口与收尾构成七个可独立恢复的信息状态；连续口播不是理解这些状态的必要条件。该判断仍等待本次最终人审。",
            "",
            "Case-specific facts remain unverified and cannot transfer to Customer Authority. No Pattern was created.",
            "",
        ]
    )
    return "\n".join(lines)


def render_news_phase_a_scout_markdown(scout: dict[str, Any]) -> str:
    lines = [
        "# News Phase A — Breadth Scout Human Review Pack",
        "",
        "Status: **Human Review Ready / No Case Approved**",
        "",
        "本包记录 Discovery、低成本预筛、正式候选 Evidence 与 Profile assessment。Research Target 不是 Pattern，Case-specific 内容也不是客户事实来源。",
        "",
        "## Discovery and Selection",
        "",
    ]
    for target in scout.get("research_targets") or []:
        selected = next(
            (
                item
                for item in target.get("discovery_candidates") or []
                if item.get("formal_pipeline_selected")
            ),
            None,
        )
        lines.extend(
            [
                f"### {target['target_id']}｜{target['missing_capability']}",
                "",
                f"- Discovery Candidates：{len(target.get('discovery_candidates') or [])}",
                f"- Status：{target['target_status']}",
                f"- Formal Candidate：{selected['candidate_id'] if selected else 'none'}",
                f"- Selection：{selected.get('selected_reason') if selected else target.get('status_reason')}",
                "",
            ]
        )
    lines.extend(["## Formal Case Candidates", ""])
    for case in scout.get("formal_case_candidates") or []:
        profile = case["profile_analysis"]
        lines.extend(
            [
                f"### {case['case_id']}",
                "",
                f"- Target：{case['research_target_ref']}",
                f"- Status：{case['lifecycle']['status']}",
                f"- Observed source profile：{profile['observed_source_profile']}",
                f"- Compatibility candidate：{', '.join(profile['compatible_generation_profiles_candidate']) or 'none'}",
                f"- Target fit：{case['target_fit_assessment']['result']}",
                f"- Semantic carrier：{case['semantic_carrier_recovery']['carrier_type']}",
                f"- Micro beats：{len(case['micro_beat_sequence'])}",
                f"- Review recommendation：{case['human_review']['recommendation']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Human Gates",
            "",
            "- [ ] Raw source and source URL are correct.",
            "- [ ] Semantic Carrier and Micro Beat timing are materially correct.",
            "- [ ] observed_source_profile is reasonable and was not forced by the target.",
            "- [ ] Privacy/source-rights review is complete.",
            "- [ ] Case-specific claims remain unverified and do not transfer.",
            "- [ ] Profile compatibility is still only a candidate assessment.",
            "",
            "Phase B remains blocked until all six targets complete Human Review and a human selects 1–2 directions.",
            "",
        ]
    )
    return "\n".join(lines)


def render_news_phase_a_case_review_markdown(case: dict[str, Any]) -> str:
    profile = case["profile_analysis"]
    carrier = case["semantic_carrier_recovery"]
    source = case["source_evidence"]
    lines = [
        f"# News Phase A Case Human Review｜{case['case_id']}",
        "",
        "Status: **Review Required / Not Approved**",
        "",
        f"- Research Target：`{case['research_target_ref']}`",
        f"- Source：{source['source_url']}",
        f"- Duration：{source['duration_seconds']:.3f}s",
        f"- Operator profile hint：`{profile['operator_profile_hint']}`",
        f"- Observed source profile：`{profile['observed_source_profile']}`",
        f"- Compatible profiles candidate：`{profile['compatible_generation_profiles_candidate']}`",
        f"- Target fit：`{case['target_fit_assessment']['result']}`",
        f"- Review recommendation：`{case['human_review']['recommendation']}`",
        "",
        "## Semantic Carrier",
        "",
        f"- Type：`{carrier['carrier_type']}`",
        f"- Narration：`{carrier['narration_presence']}`",
        f"- Transcript reliability：`{carrier['transcript_reliability']}`",
        f"- Relationship：{carrier['relationship_summary']}",
        "",
        "## Micro Beat Sequence",
        "",
        "| Beat | Time | Semantic role | Text / narration | Visual state | Evidence refs |",
        "|---|---|---|---|---|---|",
    ]
    for beat in case["micro_beat_sequence"]:
        text_value = str(beat["text_or_narration"]).replace("|", "｜")
        visual_state = str(beat["visual_state"]).replace("|", "｜")
        refs = ", ".join(beat["evidence_refs"])
        lines.append(
            f"| {beat['beat_id']} | {beat['start_seconds']:.3f}–{beat['end_seconds']:.3f}s | "
            f"{beat['semantic_role']} | {text_value} | {visual_state} | {refs} |"
        )
    lines.extend(
        [
            "",
            "## Authority Boundaries",
            "",
            "- Case-specific facts remain candidate/unverified and cannot enter Customer Persona.",
            "- Retrieval metrics are not Effectiveness Authority.",
            "- compatible_generation_profiles is a candidate assessment only.",
            "- Pattern Mining was not performed.",
            "",
            "## Human Review",
            "",
        ]
    )
    for item in case["human_review"]["review_focus"]:
        lines.append(f"- [ ] {item}")
    lines.extend(
        [
            "- [ ] Source video and evidence refs agree.",
            "- [ ] Micro Beat timing and Semantic Carrier are materially correct.",
            "- [ ] Privacy/source-rights review is complete.",
            "- [ ] Profile classification is accepted or explicitly corrected.",
            "",
            "Do not approve through this document. Use the existing explicit Case Human Gate after review.",
            "",
        ]
    )
    return "\n".join(lines)


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def write_new_text(path: Path, value: str) -> str:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.encode("utf-8")
    with path.open("xb") as handle:
        handle.write(payload)
    return hashlib.sha256(payload).hexdigest()


def _resolved_paths(values: Iterable[str]) -> list[Path]:
    return [Path(value).expanduser().resolve() for value in values]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the canonical Production Profile Registry and the derived Creative "
            "Coverage / Case Compatibility Audit without changing source Authority."
        )
    )
    parser.add_argument("--mix-template", required=True)
    parser.add_argument("--news-template", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--pattern-approval", required=True)
    parser.add_argument("--real-mix-source-plan", required=True)
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--case-approval", action="append", required=True)
    parser.add_argument("--fingerprint", action="append", required=True)
    parser.add_argument("--storyboard", action="append", required=True)
    parser.add_argument("--registry-output", required=True)
    parser.add_argument("--coverage-json-output", required=True)
    parser.add_argument("--coverage-markdown-output", required=True)
    args = parser.parse_args()
    case_paths = _resolved_paths(args.case)
    approval_paths = _resolved_paths(args.case_approval)
    fingerprint_paths = _resolved_paths(args.fingerprint)
    storyboard_paths = _resolved_paths(args.storyboard)
    if len({len(case_paths), len(approval_paths), len(fingerprint_paths), len(storyboard_paths)}) != 1:
        raise RuntimeError("Case, approval, fingerprint, and storyboard inputs must be one-to-one.")
    source_paths = _resolved_paths(
        [
            args.mix_template,
            args.news_template,
            args.pattern,
            args.pattern_approval,
            args.real_mix_source_plan,
        ]
    ) + case_paths + approval_paths + fingerprint_paths + storyboard_paths
    source_hashes_before = {str(path): sha256_file(path) for path in source_paths}
    registry = build_production_profile_registry_v1(
        mix_template_path=Path(args.mix_template),
        news_template_path=Path(args.news_template),
        approved_pattern_path=Path(args.pattern),
        pattern_approval_receipt_path=Path(args.pattern_approval),
        real_mix_source_plan_path=Path(args.real_mix_source_plan),
    )
    legacy_mix_case_ids = set(
        registry["pattern_compatibility_records"][0]["lineage"][
            "legacy_supported_case_ids"
        ]
    )
    assessments = [
        audit_case_profile_compatibility_v1(
            case_path=case_path,
            case_approval_receipt_path=approval_path,
            fingerprint_path=fingerprint_path,
            storyboard_path=storyboard_path,
            legacy_mix_case_ids=legacy_mix_case_ids,
        )
        for case_path, approval_path, fingerprint_path, storyboard_path in zip(
            case_paths,
            approval_paths,
            fingerprint_paths,
            storyboard_paths,
            strict=True,
        )
    ]
    registry_output = Path(args.registry_output).expanduser().resolve()
    registry_sha = write_new_json(registry_output, registry)
    report = build_creative_coverage_report_v1(
        registry=registry,
        registry_ref={
            "path": str(registry_output),
            "sha256": registry_sha,
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "status": registry["status"],
        },
        case_assessments=assessments,
    )
    report_sha = write_new_json(Path(args.coverage_json_output), report)
    markdown_sha = write_new_text(
        Path(args.coverage_markdown_output),
        render_creative_coverage_report_markdown(report),
    )
    source_hashes_after = {str(path): sha256_file(path) for path in source_paths}
    if source_hashes_after != source_hashes_before:
        raise RuntimeError("A frozen source artifact changed during Profile/Coverage build.")
    print("PRODUCTION PROFILE & CREATIVE COVERAGE V1 PASS")
    print(f"Registry SHA-256: {registry_sha}")
    print(f"Coverage Report SHA-256: {report_sha}")
    print(f"Coverage Markdown SHA-256: {markdown_sha}")
    print(f"Case assessments: {len(assessments)} review_required")
    print("Mix readiness: production_ready / narrow")
    print("News readiness: research_coverage_insufficient / insufficient")
    print("Remote model calls: 0")
    print("Frozen source artifacts unchanged: True")


if __name__ == "__main__":
    main()
