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
