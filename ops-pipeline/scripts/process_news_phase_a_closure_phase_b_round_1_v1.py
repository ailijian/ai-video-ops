from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from privacy_projection_v1 import PRIVACY_POLICY_VERSION, PRIVACY_SCHEMA_VERSION
from process_news_phase_a_round_2_v1 import (
    artifact_ref,
    canonical_case_705,
    find_formal_case,
    micro_beat_storyboard,
    pre_gate,
)
from production_profile_v1 import (
    BUILDER_VERSION,
    CASE_SOURCE_GOVERNANCE_AUDIT_SCHEMA_VERSION,
    CASE_SOURCE_GOVERNANCE_COMPANION_SCHEMA_VERSION,
    CASE_SOURCE_GOVERNANCE_POLICY_SCHEMA_VERSION,
    CASE_PROFILE_COMPATIBILITY_APPROVAL_SCHEMA_VERSION,
    CASE_PROFILE_STRUCTURAL_DECISION_SCHEMA_VERSION,
    NEWS_CREATIVE_COVERAGE_UPDATE_SCHEMA_VERSION,
    NEWS_PHASE_A_CLOSURE_SCHEMA_VERSION,
    NEWS_PHASE_B_DEPTH_BUILD_PLAN_SCHEMA_VERSION,
    NEWS_CROSS_CASE_RESEARCH_BUNDLE_SCHEMA_VERSION,
    NEWS_PHASE_B_HUMAN_REVIEW_CLOSURE_SCHEMA_VERSION,
    NEWS_PHASE_B_ROUND_1_SCOUT_SCHEMA_VERSION,
    now_iso,
    read_json,
    render_news_phase_a_case_review_markdown,
    sha256_file,
    validate_case_profile_compatibility_approval_v1,
    validate_case_profile_structural_decision_v1,
    validate_case_source_governance_audit_v1,
    validate_case_source_governance_companion_v1,
    validate_case_source_governance_policy_v1,
    validate_news_creative_coverage_update_v1,
    validate_news_phase_a_closure_v1,
    validate_news_phase_b_depth_build_plan_v1,
    validate_news_phase_b_human_review_closure_v1,
    validate_news_phase_b_round_1_scout_v1,
    validate_news_cross_case_research_bundle_v1,
    write_new_json,
    write_new_text,
)


CASE_705 = "7059858129298803968"
CASE_758 = "7582922932108774691"
CASE_750 = "7507825653623344396"


def write_json_if_absent(path: Path, value: dict[str, Any]) -> str:
    if path.exists():
        return sha256_file(path)
    return write_new_json(path, value)


def write_text_if_absent(path: Path, value: str) -> str:
    if path.exists():
        return sha256_file(path)
    return write_new_text(path, value)


def write_text_idempotent(path: Path, value: str) -> str:
    """Write a derived review artifact once and reject silent rewrites."""
    if path.exists():
        if path.read_text(encoding="utf-8") != value:
            raise RuntimeError(f"Existing review artifact differs from derived content: {path}")
        return sha256_file(path)
    return write_new_text(path, value)


def privacy_projection(
    case: dict[str, Any],
    *,
    visual_manifest_path: Path,
    transcript_path: Path,
    transcript_artifact_type: str,
    visible_person: bool,
) -> dict[str, Any]:
    return {
        "schema_version": PRIVACY_SCHEMA_VERSION,
        "policy_version": PRIVACY_POLICY_VERSION,
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "case_id": case["case_id"],
        "created_at": now_iso(),
        "source_artifacts": {
            "visual_manifest": artifact_ref(visual_manifest_path, "visual_manifest"),
            "transcript": artifact_ref(transcript_path, transcript_artifact_type),
        },
        "annotations": [],
        "projection_summary": {
            "text_fields_inspected": len(case["micro_beat_sequence"]) * 2,
            "annotated_fields": 0,
            "sensitive_span_count": 0,
            "high_confidence_redactions": 0,
            "review_required_items": 0,
            "projection_modes": ["safe_verbatim", "safe_semantic"],
            "human_source_inspection_recorded": True,
            "visible_person": visible_person,
        },
        "validation": {
            "passed": True,
            "unresolved_sensitive_items": 0,
            "high_confidence_redactions": 0,
            "review_required_items": 0,
            "raw_sources_modified": False,
        },
    }


def build_news_case_artifacts(
    root: Path,
    source: dict[str, Any],
    *,
    content_goal: str,
    visible_person: bool,
    source_rights_status: str,
    transcript_artifact_type: str,
) -> tuple[Path, Path, Path]:
    case_id = str(source["case_id"])
    case_dir = root / "data" / "cases" / case_id
    storyboard_path = case_dir / "reverse_storyboard_news_micro_beat_v1.json"
    privacy_path = root / "data" / "privacy" / case_id / "v1" / "privacy_projection_v1.json"
    case_path = case_dir / "case_v1.json"
    visual_manifest_path = Path(source["evidence_artifacts"]["visual_manifest"]["path"])
    transcript_path = Path(source["evidence_artifacts"]["transcript"]["path"])

    storyboard = micro_beat_storyboard(source)
    storyboard["video_understanding"]["content_goal_candidate"] = content_goal
    storyboard["timing_boundary"] = source.get("timing_boundary")
    write_json_if_absent(storyboard_path, storyboard)
    write_json_if_absent(
        privacy_path,
        privacy_projection(
            source,
            visual_manifest_path=visual_manifest_path,
            transcript_path=transcript_path,
            transcript_artifact_type=transcript_artifact_type,
            visible_person=visible_person,
        ),
    )
    case = canonical_case_705(
        source,
        storyboard_path=storyboard_path,
        privacy_path=privacy_path,
    )
    case["builder_version"] = f"{BUILDER_VERSION}+news-micro-beat-case-generalized"
    case["identity"]["research_target_ref"] = source["research_target_ref"]
    case["quality"]["warnings"].append(
        f"Source-rights status remains {source_rights_status}; Case facts are structural Evidence only."
    )
    case["source_rights_gate"] = {
        "status": source_rights_status,
        "approval_required_before_generation_use": source_rights_status != "review_passed",
        "structural_human_decision_does_not_bypass_gate": True,
    }
    case["profile_analysis"] = source["profile_analysis"]
    case["research_context"] = {
        "candidate_id": source["candidate_id"],
        "research_target_ref": source["research_target_ref"],
        "pattern_created": False,
    }
    write_json_if_absent(case_path, case)
    return case_path, storyboard_path, privacy_path


def news_fingerprint(
    case_path: Path,
    storyboard_path: Path,
    *,
    carrier_type: str,
    relationship: str,
) -> dict[str, Any]:
    case = read_json(case_path)
    storyboard = read_json(storyboard_path)
    return {
        "schema_version": "case-fingerprint-v1.0-draft",
        "builder_version": f"{BUILDER_VERSION}+news-micro-beat-fingerprint",
        "case_id": case["case_id"],
        "production_profile": "news",
        "source_case_sha256": sha256_file(case_path),
        "source_storyboard_sha256": sha256_file(storyboard_path),
        "fingerprint_scope": "case_structural_evidence_only",
        "semantic_carrier_features": {
            "carrier_type": carrier_type,
            "continuous_narration_required": False,
            "micro_beat_count": len(storyboard["micro_beat_sequence"]),
            "role_sequence": [
                beat["semantic_role"] for beat in storyboard["micro_beat_sequence"]
            ],
        },
        "visual_state_features": {
            "ordered_state_count": len(storyboard["shots"]),
            "text_visual_relationship": relationship,
        },
        "timing_boundary": storyboard.get("timing_boundary"),
        "pattern_state": {
            "pattern_mining_performed": False,
            "pattern_created": False,
        },
        "authority": {
            "case_specific_facts_transferred": False,
            "effectiveness_claimed": False,
        },
        "created_at": now_iso(),
    }


def compatibility_approval(
    case_path: Path,
    receipt_path: Path,
    fingerprint_path: Path,
    storyboard_path: Path,
    evidence_paths: list[Path],
) -> dict[str, Any]:
    case = read_json(case_path)
    return {
        "schema_version": CASE_PROFILE_COMPATIBILITY_APPROVAL_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "approval_id": f"case_profile_compatibility_approval_v1::{case['case_id']}",
        "status": "approved",
        "case_id": case["case_id"],
        "reviewer": "李健",
        "approved_at": case["lifecycle"]["approved_at"],
        "observed_source_profile": "news",
        "approved_compatible_generation_profiles": ["news"],
        "mix_compatibility": "not_approved",
        "decision": "approved_news_only",
        "source_approved_case_ref": artifact_ref(case_path, "approved_case"),
        "case_approval_receipt_ref": artifact_ref(receipt_path, "case_approval_receipt"),
        "fingerprint_ref": artifact_ref(fingerprint_path, "case_fingerprint"),
        "storyboard_ref": artifact_ref(storyboard_path, "reverse_storyboard_news_micro_beat"),
        "evidence_refs": [artifact_ref(path, "structural_evidence") for path in evidence_paths],
        "pattern_created": False,
        "case_lifecycle_modified_beyond_explicit_human_approval": False,
        "authority": {
            "case_specific_facts_transferred": False,
            "effectiveness_claimed": False,
            "pattern_authority_changed": False,
        },
    }


def round_2_scene_case(round_2: dict[str, Any]) -> dict[str, Any]:
    case = find_formal_case(round_2, CASE_750)
    case = json.loads(json.dumps(case, ensure_ascii=False))
    case["timing_boundary"] = {
        "source_duration_seconds": 16.167,
        "structural_reference": "allowed",
        "timing_template": "not_implied",
        "duration_template": "not_implied",
        "beat_count_template": "not_implied",
    }
    return case


def closure_artifact(
    *,
    round_1_path: Path,
    round_2_path: Path,
    case_705_path: Path,
    case_758_path: Path,
    case_750_path: Path,
    case_750_decision_path: Path,
) -> dict[str, Any]:
    outcomes = [
        {
            "target_id": "NEWS_PHASE_A_001",
            "direction": "number_or_price_led_micro_information",
            "result": "supported_structural_direction",
            "seed_case_id": CASE_705,
            "case_lifecycle_status": "approved",
            "case_ref": artifact_ref(case_705_path, "approved_news_case"),
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_002",
            "direction": "local_service_discovery",
            "result": "no_independent_news_structure_evidenced",
            "final_research_interpretation": "content_job_compatibility_probe",
            "round_1_result": "mix_mismatch",
            "round_2_result": "no_suitable_news_candidate",
            "phase_a_search_stopped": True,
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_003",
            "direction": "problem_or_alert",
            "result": "no_independent_news_structure_evidenced",
            "final_research_interpretation": "content_job_or_hook_type_or_unresolved_structure_hypothesis",
            "round_1_result": "mix_mismatch",
            "round_2_result": "no_suitable_news_candidate",
            "phase_a_search_stopped": True,
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_004",
            "direction": "scene_contrast",
            "result": "supported_structural_direction",
            "seed_case_id": CASE_750,
            "case_lifecycle_status": "review_required",
            "structural_profile_decision": "approved_gate_pending",
            "case_ref": artifact_ref(case_750_path, "review_required_news_case"),
            "decision_ref": artifact_ref(case_750_decision_path, "structural_profile_decision"),
            "blocking_gates": ["privacy_review", "source_rights_review"],
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_005",
            "direction": "event_or_campaign_information_progression",
            "result": "supported_structural_direction",
            "seed_case_id": CASE_758,
            "case_lifecycle_status": "approved",
            "case_ref": artifact_ref(case_758_path, "approved_news_case"),
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_006",
            "direction": "concrete_benefit",
            "result": "no_independent_news_structure_evidenced",
            "final_research_interpretation": "content_job_or_value_proposition",
            "round_1_result": "mix_mismatch",
            "round_2_result": "no_suitable_news_candidate",
            "phase_a_search_stopped": True,
            "pattern_created": False,
        },
    ]
    return {
        "schema_version": NEWS_PHASE_A_CLOSURE_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "closure_id": "news_phase_a_final_closure_v1",
        "status": "complete",
        "reviewer": "李健",
        "closed_at": now_iso(),
        "source_refs": {
            "round_1": artifact_ref(round_1_path, "round_1_research_history"),
            "round_2": artifact_ref(round_2_path, "round_2_research_history"),
        },
        "research_target_outcomes": outcomes,
        "supported_structural_directions": [
            "number_or_price_led_micro_information",
            "scene_contrast",
            "event_or_campaign_information_progression",
        ],
        "approved_news_case_ids": [CASE_705, CASE_758],
        "structural_seed_gate_pending_case_ids": [CASE_750],
        "approved_news_pattern_count": 0,
        "news_operational_readiness": "research_coverage_insufficient",
        "phase_b_status": "started_two_human_selected_directions_only",
        "authority": {
            "pattern_created": False,
            "pattern_mining_performed": False,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
            "persona_modified": False,
            "content_ledger_modified": False,
        },
    }


def phase_b_plan(closure_path: Path) -> dict[str, Any]:
    return {
        "schema_version": NEWS_PHASE_B_DEPTH_BUILD_PLAN_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "plan_id": "news_phase_b_depth_build_plan_v1",
        "status": "round_1_started",
        "created_at": now_iso(),
        "source_phase_a_closure_ref": artifact_ref(closure_path, "news_phase_a_closure"),
        "directions": [
            {
                "direction_id": "number_or_price_led_micro_information",
                "priority": "critical",
                "seed_case_id": CASE_705,
                "seed_case_status": "approved",
                "desired_invariants": [
                    "number_or_price_is_first_semantic_anchor",
                    "subsequent_micro_beats_explain_context",
                    "value_constraint_or_scope_follows",
                    "semantic_carrier_survives_without_continuous_mix_narration",
                ],
                "desired_invariants_authority": "research_hypothesis_not_pattern",
                "allowed_surface_variation": [
                    "price", "quantity", "duration", "package", "discount", "numeric_service_parameter"
                ],
                "redundancy_warning": "Do not collect repeated hot-spring offer videos or copy Seed surface details.",
                "discovery_candidate_count_target": 6,
                "formal_candidate_limit": 2,
                "pre_screen_criteria": [
                    "news_profile_pre_gate_strong",
                    "seed_structural_similarity_pass",
                    "surface_diversity_present",
                    "source_and_visual_evidence_recoverable",
                ],
                "stop_condition": "Stop at Human Review; wait for Approved Case count before cross-case research.",
            },
            {
                "direction_id": "scene_contrast",
                "priority": "high",
                "seed_case_id": CASE_750,
                "seed_case_status": "structural_profile_approved_privacy_source_gate_pending",
                "desired_invariants": [
                    "state_a_is_observable",
                    "contrast_or_transformation_is_observable",
                    "state_b_is_observable",
                    "state_change_materially_changes_user_understanding",
                    "continuous_narration_is_not_required",
                ],
                "desired_invariants_authority": "research_hypothesis_not_pattern",
                "allowed_surface_variation": [
                    "beauty", "repair", "cleaning", "food_preparation", "display", "public_space_change"
                ],
                "redundancy_warning": "Do not collect two more old-house renovation montages or unrelated pretty shots.",
                "discovery_candidate_count_target": 6,
                "formal_candidate_limit": 2,
                "pre_screen_criteria": [
                    "news_profile_pre_gate_strong",
                    "seed_structural_similarity_pass",
                    "meaningful_state_change_not_montage",
                    "surface_diversity_present",
                ],
                "stop_condition": "Stop at Human Review; no Pattern or cross-case comparison before approvals.",
            },
        ],
        "coverage_only_direction": "event_or_campaign_explanation",
        "coverage_only_case_id": CASE_758,
        "cross_case_research_status": "not_started_waiting_for_human_approved_cases",
        "pattern_created": False,
        "news_generation_authorized": False,
        "news_export_authorized": False,
    }


def discovery_candidate(
    *,
    candidate_id: str,
    direction: str,
    source_url: str,
    title: str,
    creator: str | None,
    publish_time: str | None,
    duration: str,
    likelihood: str,
    gate_checks: list[bool],
    gate_reason: str,
    similarity_result: str,
    similarity_reason: str,
    selected: bool,
    rank: int | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "case_target_ref": direction,
        "source_platform": "douyin",
        "source_url": source_url,
        "creator_or_account": creator,
        "title_or_description": title,
        "publish_time": publish_time,
        "retrieved_at": now_iso(),
        "operator_profile_hint": "news",
        "operator_notes": "Phase B Discovery; profile structure evaluated before surface topic.",
        "lightweight_structure_observation": {
            "approximate_duration": duration,
            "information_carrier": "public page metadata plus sampled visual states when ranked for pre-screen",
            "obvious_redundancy_risk": similarity_reason,
        },
        "news_profile_pre_gate": pre_gate(likelihood, gate_reason, gate_checks),
        "seed_structural_similarity_gate": {
            "seed_case_id": CASE_705 if direction == "number_or_price_led_micro_information" else CASE_750,
            "result": similarity_result,
            "reason": similarity_reason,
            "surface_diversity_required": True,
        },
        "rank": rank,
        "formal_pipeline_selected": selected,
        "selected_reason": similarity_reason if selected else None,
        "case_id": case_id,
        "case_created": selected,
        "pattern_mining_eligible": False,
        "retrieval_metadata": {
            "authority": "not_effectiveness_authority",
            "metrics_saved": False,
        },
    }


def phase_b_discoveries() -> list[dict[str, Any]]:
    price = [
        discovery_candidate(
            candidate_id="NEWSPB_PRICE_R1_C001", direction="number_or_price_led_micro_information",
            source_url="https://www.douyin.com/video/7653677821193127625",
            title="本地健身单次卡现价与原价", creator="重力之契24H健身（万象城1店）",
            publish_time="2026-06-21", duration="20.7s", likelihood="strong",
            gate_checks=[True, True, True, True, True],
            gate_reason="Captions and changing gym states remain understandable without continuous narration.",
            similarity_result="fail",
            similarity_reason="The first semantic anchor is a summer fitness exhortation; price appears later, so it does not match the Seed organization.",
            selected=False,
        ),
        discovery_candidate(
            candidate_id="NEWSPB_PRICE_R1_C002", direction="number_or_price_led_micro_information",
            source_url="https://www.douyin.com/video/7640840358842207507",
            title="中国电信 Token 套餐：9.9 元/月与额度", creator="证券时报",
            publish_time="2026-05-18", duration="8.033s", likelihood="strong",
            gate_checks=[True, True, True, True, True],
            gate_reason="Persistent price and quantity text, package table, and partner scope form independent micro states with no reliable narration.",
            similarity_result="pass",
            similarity_reason="Price and quantity are the first semantic anchors; later states add package tiers and scope, with a surface different from the Seed.",
            selected=True, rank=1, case_id="7640840358842207507",
        ),
        discovery_candidate(
            candidate_id="NEWSPB_PRICE_R1_C003", direction="number_or_price_led_micro_information",
            source_url="https://www.douyin.com/video/7635146658208744867",
            title="手工/游戏体验原价 29.9、现价 14.9", creator=None,
            publish_time=None, duration="7.5s", likelihood="strong",
            gate_checks=[True, True, True, True, True],
            gate_reason="The price comparison remains visible over several changing service-use states and survives without narration.",
            similarity_result="pass",
            similarity_reason="A price comparison opens the sequence, then varied activity and group-use states explain service context; surface differs from both Seed and telecom package.",
            selected=True, rank=2, case_id="7635146658208744867",
        ),
        discovery_candidate(
            candidate_id="NEWSPB_PRICE_R1_C004", direction="number_or_price_led_micro_information",
            source_url="https://www.douyin.com/video/7664466270192873339",
            title="套圈数量阶梯价格", creator=None, publish_time=None, duration="24s",
            likelihood="possible", gate_checks=[True, True, True, True, False],
            gate_reason="Several price/quantity states are visible, but lightweight evidence cannot exclude continuous promotional narration dependency.",
            similarity_result="pass", similarity_reason="Numeric tiers resemble the Seed organization, but News Profile evidence is not strong enough.", selected=False,
        ),
        discovery_candidate(
            candidate_id="NEWSPB_PRICE_R1_C005", direction="number_or_price_led_micro_information",
            source_url="https://www.douyin.com/video/7672665492410174783",
            title="298 元抗衰套餐模板视频", creator=None, publish_time=None, duration="short",
            likelihood="weak", gate_checks=[True, False, False, False, False],
            gate_reason="A numeric offer is present, but source authenticity and recoverable multi-state progression are insufficient.",
            similarity_result="fail", similarity_reason="One price card does not provide the Seed's contextual progression.", selected=False,
        ),
        discovery_candidate(
            candidate_id="NEWSPB_PRICE_R1_C006", direction="number_or_price_led_micro_information",
            source_url="https://www.douyin.com/video/7631132644876684515",
            title="餐饮新套餐短视频", creator=None, publish_time=None, duration="10s",
            likelihood="possible", gate_checks=[True, True, True, False, True],
            gate_reason="Package text is recoverable, but distinct information-state depth is unclear from lightweight evidence.",
            similarity_result="pass", similarity_reason="Package-first surface may be comparable, but the profile gate is not strong enough for formal selection.", selected=False,
        ),
    ]
    scene = [
        discovery_candidate(
            candidate_id="NEWSPB_SCENE_R1_C001", direction="scene_contrast",
            source_url="https://www.douyin.com/video/7638835262881292209",
            title="汽车喷漆完成效果展示", creator="梁山局部补漆无痕修复",
            publish_time="2026-05-12", duration="7.633s", likelihood="possible",
            gate_checks=[True, True, True, False, True],
            gate_reason="The visual carrier is independent, but sampled states show a finished-result pan rather than multiple semantic beats.",
            similarity_result="fail", similarity_reason="No recoverable damaged State A is shown, so the sequence is result montage rather than meaningful A→B contrast.", selected=False,
        ),
        discovery_candidate(
            candidate_id="NEWSPB_SCENE_R1_C002", direction="scene_contrast",
            source_url="https://www.douyin.com/video/7639693960727179747",
            title="单眼皮调整：半脸状态到完成态", creator="吴紫瑜MAKEUP",
            publish_time="2026-05-14", duration="8.217s", likelihood="strong",
            gate_checks=[True, True, True, True, True],
            gate_reason="Split-face starting state, application, and full result are visually recoverable without narration.",
            similarity_result="pass", similarity_reason="Observable partial/before state progresses through an action to a full result and changes the viewer's understanding; beauty surface differs from renovation.",
            selected=True, rank=1, case_id="7639693960727179747",
        ),
        discovery_candidate(
            candidate_id="NEWSPB_SCENE_R1_C003", direction="scene_contrast",
            source_url="https://www.douyin.com/video/7616327461634652005",
            title="宁波秀水街区多地点改造前后", creator="胡颖（胡说宁波）",
            publish_time="2026-03-14", duration="42.1s", likelihood="strong",
            gate_checks=[True, True, True, True, True],
            gate_reason="Repeated paired historical/current location states and labels form recoverable visual micro-information groups.",
            similarity_result="pass", similarity_reason="Each place provides a meaningful State A/State B pair; public-space surface differs from renovation and beauty.",
            selected=True, rank=2, case_id="7616327461634652005",
        ),
        discovery_candidate(
            candidate_id="NEWSPB_SCENE_R1_C004", direction="scene_contrast",
            source_url="https://www.douyin.com/video/7533605827338439999",
            title="素人妆前妆后反差", creator="相思寄予湫",
            publish_time="2025-08-01", duration="36s", likelihood="possible",
            gate_checks=[True, True, True, True, False],
            gate_reason="Before/after states are likely visible, but compressed progression and source/privacy suitability are not yet strong.",
            similarity_result="pass", similarity_reason="Potentially meaningful transformation, but it is redundant with the stronger makeup candidate and has greater privacy risk.", selected=False,
        ),
        discovery_candidate(
            candidate_id="NEWSPB_SCENE_R1_C005", direction="scene_contrast",
            source_url="https://www.douyin.com/video/7656794183638935887",
            title="灰地砖长过程改造前后", creator="小迷糊的家",
            publish_time="2026-06-29", duration="59s", likelihood="weak",
            gate_checks=[True, False, False, True, False],
            gate_reason="The extended tutorial/process narrative is closer to Mix even though before/after appears.",
            similarity_result="pass", similarity_reason="State change exists, but the organization depends on long process explanation and repeats the renovation surface.", selected=False,
        ),
        discovery_candidate(
            candidate_id="NEWSPB_SCENE_R1_C006", direction="scene_contrast",
            source_url="https://www.douyin.com/video/7626629508988488293",
            title="50 平老破小装修流程与前后", creator="柚子酱",
            publish_time="2026-04-09", duration="34s", likelihood="weak",
            gate_checks=[True, False, False, True, False],
            gate_reason="Continuous renovation explanation and process dominate the semantic carrier.",
            similarity_result="fail", similarity_reason="It is a shortened Mix/process explanation and repeats the Seed's renovation surface.", selected=False,
        ),
    ]
    return [
        {"direction_id": "number_or_price_led_micro_information", "discovery_candidates": price},
        {"direction_id": "scene_contrast", "discovery_candidates": scene},
    ]


def phase_b_formal_sources(root: Path) -> dict[str, dict[str, Any]]:
    definitions = {
        "7640840358842207507": {
            "candidate_id": "NEWSPB_PRICE_R1_C002",
            "target": "number_or_price_led_micro_information",
            "source_dir": "PRICE_B_R1_C002",
            "duration": 8.033,
            "carrier": "on_screen_text_plus_visual_information_state",
            "visible": False,
            "beats": [
                ("B001", "price_quantity_hook", "个人最低资费 9.9 元/月；包含 1000 万 Tokens/月", "价格与额度构成首屏主信息", 0.0, 2.85, ["frame_000000000ms.jpg", "frame_000002500ms.jpg"]),
                ("B002", "package_scope", "基础、专业、旗舰三档套餐及对应月资费与额度", "套餐表与适用任务形成范围状态", 2.85, 5.7, ["frame_000003500ms.jpg", "frame_000005500ms.jpg"]),
                ("B003", "partner_or_rights_scope", "合作伙伴权益与服务范围说明", "合作范围信息状态收尾", 5.7, 8.033, ["frame_000006850ms.jpg", "frame_000008000ms.jpg"]),
            ],
        },
        "7635146658208744867": {
            "candidate_id": "NEWSPB_PRICE_R1_C003",
            "target": "number_or_price_led_micro_information",
            "source_dir": "PRICE_B_R1_C003",
            "duration": 7.5,
            "carrier": "persistent_price_text_plus_visual_service_states",
            "visible": True,
            "beats": [
                ("B001", "price_comparison_hook", "手工体验原价 29.9；现价 14.9", "价格比较首屏覆盖游戏画面", 0.0, 0.75, ["frame_000000000ms.jpg", "frame_000000750ms.jpg"]),
                ("B002", "activity_context_one", "价格文字保持", "第一类对战体验", 0.75, 2.25, ["frame_000001500ms.jpg", "frame_000002250ms.jpg"]),
                ("B003", "activity_context_two", "价格文字保持", "另一类游戏/设备状态", 2.25, 3.75, ["frame_000002500ms.jpg", "frame_000003750ms.jpg"]),
                ("B004", "group_use_context", "价格文字保持", "多人现场体验状态", 3.75, 5.25, ["frame_000004500ms.jpg", "frame_000005250ms.jpg"]),
                ("B005", "service_close", "价格文字保持", "活动画面收尾", 5.25, 7.5, ["frame_000006000ms.jpg", "frame_000007467ms.jpg"]),
            ],
        },
        "7639693960727179747": {
            "candidate_id": "NEWSPB_SCENE_R1_C002",
            "target": "scene_contrast",
            "source_dir": "SCENE_B_R1_C002",
            "duration": 8.217,
            "carrier": "visual_information_state_sequence",
            "visible": True,
            "beats": [
                ("B001", "split_state_hook", "无可靠连续口播", "一侧眼妆完成、另一侧未完成的同屏对照", 0.0, 0.967, ["frame_000000000ms.jpg", "frame_000000967ms.jpg"]),
                ("B002", "transformation_action", "无可靠连续口播", "未完成侧的具体操作推进", 0.967, 4.058, ["frame_000001583ms.jpg", "frame_000003767ms.jpg"]),
                ("B003", "result_reveal", "无可靠连续口播", "遮挡/移开展示两侧完成态", 4.058, 5.5, ["frame_000004350ms.jpg", "frame_000005500ms.jpg"]),
                ("B004", "result_close", "无可靠连续口播", "完成态表情与局部细节收尾", 5.5, 8.217, ["frame_000006500ms.jpg", "frame_000008199ms.jpg"]),
            ],
        },
        "7616327461634652005": {
            "candidate_id": "NEWSPB_SCENE_R1_C003",
            "target": "scene_contrast",
            "source_dir": "SCENE_B_R1_C003",
            "duration": 42.1,
            "carrier": "paired_visual_state_sequence_plus_onscreen_labels",
            "visible": True,
            "beats": [
                ("B001", "location_pair_one", "桂芳巷陈宅", "同一建筑改造前/后并列", 0.0, 8.0, ["frame_000000000ms.jpg", "frame_000005000ms.jpg"]),
                ("B002", "location_pair_two", "孙家巷干部楼", "同一街巷改造前/后并列", 8.0, 16.0, ["frame_000010000ms.jpg", "frame_000015000ms.jpg"]),
                ("B003", "location_pair_three", "大桥街", "道路及街景改造前/后并列", 16.0, 24.0, ["frame_000020000ms.jpg", "frame_000023000ms.jpg"]),
                ("B004", "location_pair_four", "大桥街另一状态", "旧街道与完成态公共空间并列", 24.0, 34.0, ["frame_000030000ms.jpg", "frame_000033000ms.jpg"]),
                ("B005", "location_pair_five", "秀水街", "街巷改造前/后并列收尾", 34.0, 42.1, ["frame_000040000ms.jpg", "frame_000042000ms.jpg"]),
            ],
        },
    }
    result: dict[str, dict[str, Any]] = {}
    for case_id, definition in definitions.items():
        video_path = root / "data" / "sources" / "news_phase_b_round_1" / definition["source_dir"] / f"{case_id}.mp4"
        visual_path = root / "data" / "visual" / case_id / "visual_evidence_manifest.json"
        transcript_path = root / "data" / "analysis" / case_id / "transcript_segments.json"
        visual = read_json(visual_path)
        beats = [
            {
                "beat_id": beat_id,
                "semantic_role": role,
                "text_or_narration": text,
                "visual_state": visual_state,
                "start_seconds": start,
                "end_seconds": end,
                "evidence_refs": refs,
            }
            for beat_id, role, text, visual_state, start, end, refs in definition["beats"]
        ]
        result[case_id] = {
            "candidate_id": definition["candidate_id"],
            "case_id": case_id,
            "research_target_ref": definition["target"],
            "lifecycle": {"status": "review_required", "approved": False},
            "source_evidence": {
                "platform": "douyin",
                "source_url": f"https://www.douyin.com/video/{case_id}",
                "video_path": str(video_path.resolve()),
                "video_sha256": sha256_file(video_path),
                "duration_seconds": definition["duration"],
            },
            "evidence_artifacts": {
                "visual_manifest": {
                    **artifact_ref(visual_path, "visual_manifest"),
                    "frame_count": visual["evidence_frame_count"],
                    "scene_count": visual["scene_count"],
                },
                "transcript": {
                    **artifact_ref(transcript_path, "transcript_excluded_no_reliable_speech"),
                    "reliability": "excluded_no_reliable_semantic_speech",
                },
            },
            "formal_pipeline": {
                "source_acquisition": "complete",
                "privacy_projection": "complete_human_review_required",
                "semantic_carrier_extraction": "complete",
                "visual_evidence": "complete",
                "information_state_analysis": "complete",
                "micro_beat_storyboard": "complete",
                "case_build": "complete_review_required",
                "human_review": "pending",
            },
            "semantic_carrier_recovery": {
                "carrier_type": definition["carrier"],
                "primary_semantic_carrier_recovered": True,
                "narration_presence": "no_reliable_continuous_narration",
                "transcript_reliability": "excluded",
                "onscreen_text_timing_recovered": True,
                "visual_state_recovered": True,
                "relationship_summary": "Ordered text and/or visual information states carry the structure without continuous Mix narration.",
            },
            "profile_analysis": {
                "operator_profile_hint": "news",
                "observed_source_profile": "news",
                "compatible_generation_profiles_candidate": ["news"],
                "confidence": "medium",
                "classification_forced_by_target": False,
            },
            "target_fit_assessment": {
                "result": "suitable",
                "reason": "Both structural gates passed and the Semantic Carrier is recoverable from the sampled source Evidence.",
            },
            "micro_beat_sequence": beats,
            "privacy": {
                "status": "human_review_required" if definition["visible"] else "projection_pass_source_rights_review_required",
                "visible_person": definition["visible"],
                "obvious_sensitive_pii": False,
                "source_rights_status": "review_required",
                "raw_evidence_remote_sent": False,
            },
            "proof": {
                "status": "not_upgraded",
                "case_claims_semantics": "candidate_unverified",
                "retrieval_metrics_used_as_effectiveness": False,
            },
            "pattern_state": {"pattern_mining_performed": False, "pattern_candidates": []},
            "authority": {
                "case_specific_facts_transferred": False,
                "persona_modified": False,
                "content_ledger_modified": False,
            },
            "human_review": {
                "required": True,
                "recommendation": "review_for_case_approval",
                "review_focus": [
                    "micro-beat boundaries",
                    "News profile classification",
                    "privacy and source rights",
                    "no Case fact transfer or Proof upgrade",
                ],
            },
        }
    return result


def render_closure_markdown(closure: dict[str, Any]) -> str:
    lines = [
        "# News Phase A — Final Closure",
        "",
        "Status: **COMPLETE**",
        "",
        "| Target | Result | Seed / interpretation |",
        "|---|---|---|",
    ]
    for item in closure["research_target_outcomes"]:
        detail = item.get("seed_case_id") or item.get("final_research_interpretation")
        lines.append(f"| {item['target_id']} | {item['result']} | {detail} |")
    lines.extend([
        "",
        "News Operational Readiness remains `research_coverage_insufficient`: Approved News Pattern = 0.",
        "",
    ])
    return "\n".join(lines)


def render_phase_b_plan_markdown(plan: dict[str, Any]) -> str:
    lines = ["# News Phase B Depth Build — Round 1 Plan", ""]
    for item in plan["directions"]:
        lines.extend([
            f"## {item['direction_id']}", "",
            f"- Priority: `{item['priority']}`",
            f"- Seed: `{item['seed_case_id']}` ({item['seed_case_status']})",
            f"- Discovery target: {item['discovery_candidate_count_target']}",
            f"- Formal Candidate limit: {item['formal_candidate_limit']}", "",
            "Desired invariants are Research Hypotheses, not Approved Pattern invariants.", "",
        ])
    lines.append("Event / Campaign Explanation remains coverage-only in this round. No Pattern or generation is authorized.")
    return "\n".join(lines) + "\n"


def render_phase_b_scout_markdown(scout: dict[str, Any]) -> str:
    lines = ["# News Phase B Depth Build — Round 1 Scout", "", "Status: **Human Review Ready**", ""]
    for direction in scout["directions"]:
        lines.extend([
            f"## {direction['direction_id']}", "",
            "| Candidate | News gate | Seed similarity | Formal |",
            "|---|---|---|---|",
        ])
        for candidate in direction["discovery_candidates"]:
            lines.append(
                f"| {candidate['candidate_id']} | {candidate['news_profile_pre_gate']['news_profile_likelihood']} | "
                f"{candidate['seed_structural_similarity_gate']['result']} | "
                f"{'yes' if candidate['formal_pipeline_selected'] else 'no'} |"
            )
        lines.append("")
    lines.append("All Formal Candidates stop at `review_required`. Cross-case research and Pattern mining have not started.")
    return "\n".join(lines) + "\n"


PHASE_B_HUMAN_REVIEW_ASSESSMENTS: dict[str, dict[str, Any]] = {
    "7640840358842207507": {
        "seed_case_id": CASE_705,
        "structure_fit": "strong",
        "semantic_carrier_components": {
            "on_screen_text": "primary",
            "narration": "no_reliable_continuous_narration",
            "visual_state": "supporting_context_and_scope",
            "combination": "on_screen_text_plus_visual_information_state",
            "continuous_narration_dependency": False,
        },
        "seed_similarity": {
            "first_semantic_anchor": "9.9 元/月与 1000 万 Tokens/月构成首个语义锚点。",
            "number_or_price_role": "价格是主锚点，数量用于说明套餐额度。",
            "following_context_beats": "套餐层级与适用任务继续解释首屏 offer。",
            "constraint_or_scope": "套餐档位、额度和合作范围形成明确 scope。",
            "value_or_close": "以合作伙伴权益/服务范围收尾；不据此验证商业价值。",
            "narration_dependency": "不依赖连续口播。",
            "visual_state_function": "信息卡和套餐表承担 scope progression。",
        },
        "surface_diversity": {
            "industry_or_topic": "电信/AI Token 套餐；Seed 为本地温泉团购。",
            "content_surface": "订阅资费与用量额度；Seed 为次数卡价格。",
            "visual_surface": "数字信息卡、套餐表；Seed 为门店和设施画面。",
            "semantic_organization": "均以价格/数量 offer 开场，再用状态解释范围；组织相似而表层不同。",
            "assessment": "strong",
        },
        "scope_evidence": "price_offer_led_only",
        "scope_warning": "数量用于套餐额度说明；当前 Evidence 不足以泛化为 broader number-led structure。",
        "source_provenance_status": "source_url_and_local_sha256_recorded_not_rights_clearance",
        "lifecycle_impact": (
            "If approved: Price-led reaches 2 canonical approved cases and may support Pattern Hypothesis research; "
            "if both pending Price-led cases are approved, it reaches 3 and becomes eligible_for_pattern_candidate_research."
        ),
    },
    "7635146658208744867": {
        "seed_case_id": CASE_705,
        "structure_fit": "strong_with_scope_limit",
        "semantic_carrier_components": {
            "on_screen_text": "primary_persistent_price_offer",
            "narration": "no_reliable_continuous_narration",
            "visual_state": "supporting_service_use_context",
            "combination": "persistent_price_text_plus_visual_service_states",
            "continuous_narration_dependency": False,
        },
        "seed_similarity": {
            "first_semantic_anchor": "29.9 元原价到 14.9 元现价构成首个语义锚点。",
            "number_or_price_role": "价格折扣是主锚点；没有独立的 broader numeric parameter progression。",
            "following_context_beats": "不同活动、设备和多人体验画面解释 offer 的使用语境。",
            "constraint_or_scope": "未恢复出明确限制或范围 Beat。",
            "value_or_close": "价格文字保持，以活动使用画面收尾。",
            "narration_dependency": "不依赖连续口播。",
            "visual_state_function": "变化的活动状态为持续价格 offer 提供语境。",
        },
        "surface_diversity": {
            "industry_or_topic": "手工/游戏体验；Seed 为本地温泉团购。",
            "content_surface": "体验项目折扣；Seed 为温泉次数卡。",
            "visual_surface": "动态活动、设备与多人体验；Seed 为门店、设施和购买页。",
            "semantic_organization": "均以价格 offer 开场并持续，再用服务状态解释；本 Case 的 scope/constraint 较弱。",
            "assessment": "strong",
        },
        "scope_evidence": "price_offer_led_only",
        "scope_warning": "Evidence 仅支持折扣/促销价格开场，不能据此泛化为 broader number-led structure。",
        "source_provenance_status": "source_url_and_local_sha256_recorded_not_rights_clearance",
        "lifecycle_impact": (
            "If approved: Price-led reaches 2 canonical approved cases and may support Pattern Hypothesis research; "
            "if both pending Price-led cases are approved, it reaches 3 and becomes eligible_for_pattern_candidate_research."
        ),
    },
    "7639693960727179747": {
        "seed_case_id": CASE_750,
        "structure_fit": "strong",
        "semantic_carrier_components": {
            "on_screen_text": "non_primary",
            "narration": "no_reliable_continuous_narration",
            "visual_state": "primary",
            "combination": "visual_information_state_sequence",
            "continuous_narration_dependency": False,
        },
        "seed_similarity": {
            "state_a": "同屏呈现一侧眼妆完成、另一侧未完成。",
            "transition_or_transformation": "镜头明确记录未完成侧的实际操作推进。",
            "state_b": "遮挡移开后展示两侧完成态，并以细节收尾。",
            "contrast_changes_understanding": "是；观众可从初始差异、操作到结果恢复变化过程，而非仅观看两个漂亮镜头。",
            "narration_dependency": "不依赖连续口播。",
            "visual_state_progression": "State A → operation → reveal → State B close。",
        },
        "surface_diversity": {
            "industry_or_topic": "美妆操作；Seed 为住宅空间改造。",
            "content_surface": "人物局部状态改变；Seed 为多个空间完成前后。",
            "visual_surface": "同一人物半脸对照与近景操作；Seed 为空间全景、局部叠加和露台。",
            "semantic_organization": "都以可见 State A/B 承担语义，但本 Case 额外提供可恢复的操作过程。",
            "assessment": "strong",
        },
        "scene_contrast_quality": "strong",
        "scene_quality_reason": "具备可恢复的 State A、实际 operation/transition 与 State B，不是仅有 before/after 标签。",
        "source_provenance_status": "source_url_and_local_sha256_recorded_not_rights_clearance",
        "lifecycle_impact": (
            "If approved while Seed 750782 remains rights-pending: Scene Contrast has 1 canonical approved case. "
            "If both pending Scene Contrast cases are approved and Seed remains pending, it reaches 2 and is "
            "eligible_for_pattern_hypothesis_only."
        ),
    },
    "7616327461634652005": {
        "seed_case_id": CASE_750,
        "structure_fit": "supported_with_progression_limit",
        "semantic_carrier_components": {
            "on_screen_text": "supporting_location_labels",
            "narration": "no_reliable_continuous_narration",
            "visual_state": "primary_paired_old_new_states",
            "combination": "paired_visual_state_sequence_plus_onscreen_labels",
            "continuous_narration_dependency": False,
        },
        "seed_similarity": {
            "state_a": "每组展示同一地点的历史/改造前状态。",
            "transition_or_transformation": "主要为同地点旧/新状态配对切换；没有恢复出具体施工操作。",
            "state_b": "每组展示对应地点的当前/改造后状态。",
            "contrast_changes_understanding": "是；配对地点与标签让观众理解公共空间发生了变化。",
            "narration_dependency": "不依赖连续口播。",
            "visual_state_progression": "多个独立 old/new pair 依序展开，整体更接近 repeated comparison catalogue。",
        },
        "surface_diversity": {
            "industry_or_topic": "城市街区/公共空间变化；Seed 为住宅装修。",
            "content_surface": "多个地点的历史与当前对照；Seed 为单套住宅多个空间。",
            "visual_surface": "带地点标签的并列旧/新图片组；Seed 为实拍空间和转场叠加。",
            "semantic_organization": "都依赖可见 A/B；本 Case 是重复配对目录，Seed 是连续空间变化与结果收尾。",
            "assessment": "strong",
        },
        "scene_contrast_quality": "moderate",
        "scene_quality_reason": "每个旧/新地点对照具有信息意义，但缺少可恢复的 transformation action，整体主要是重复 visual slideshow。",
        "source_provenance_status": "source_url_and_local_sha256_recorded_not_rights_clearance",
        "lifecycle_impact": (
            "If approved while Seed 750782 remains rights-pending: Scene Contrast has 1 canonical approved case. "
            "If both pending Scene Contrast cases are approved and Seed remains pending, it reaches 2 and is "
            "eligible_for_pattern_hypothesis_only."
        ),
    },
}


def _format_seconds(value: float) -> str:
    return f"{float(value):.3f}"


def render_phase_b_concise_review_pack(
    formal: dict[str, Any],
    case_artifact: dict[str, Any],
    assessment: dict[str, Any],
) -> str:
    case_id = str(formal["case_id"])
    identity = case_artifact["identity"]
    profile = case_artifact["profile_analysis"]
    carrier = assessment["semantic_carrier_components"]
    privacy = formal["privacy"]
    lines = [
        f"# News Phase B Round 1｜Concise Human Review｜{case_id}",
        "",
        "Status: **Review Required / Not Approved**",
        "",
        "## A. Identity",
        "",
        f"- Case ID：`{case_id}`",
        f"- Source URL：{identity['source_url']}",
        f"- Research Direction：`{formal['research_target_ref']}`",
        f"- Seed Case：`{assessment['seed_case_id']}`",
        f"- Duration：{identity['duration_seconds']}s",
        "",
        "## B. Profile",
        "",
        f"- operator_profile_hint：`{profile['operator_profile_hint']}`",
        f"- observed_source_profile：`{profile['observed_source_profile']}`",
        f"- compatible_generation_profiles candidate：`{profile['compatible_generation_profiles_candidate']}`",
        "",
        "## C. Semantic Carrier",
        "",
        f"- on-screen text：`{carrier['on_screen_text']}`",
        f"- narration：`{carrier['narration']}`",
        f"- visual state：`{carrier['visual_state']}`",
        f"- combination：`{carrier['combination']}`",
        f"- depends on continuous narration：`{str(carrier['continuous_narration_dependency']).lower()}`",
        "",
        "## D. Micro Beat Sequence",
        "",
        "| Beat | Start–end | Semantic role | Text / narration | Visual state | Evidence refs |",
        "|---|---:|---|---|---|---|",
    ]
    for beat in formal["micro_beat_sequence"]:
        refs = ", ".join(beat["evidence_refs"])
        lines.append(
            f"| {beat['beat_id']} | {_format_seconds(beat['start_seconds'])}–{_format_seconds(beat['end_seconds'])}s | "
            f"{beat['semantic_role']} | {beat['text_or_narration']} | {beat['visual_state']} | {refs} |"
        )
    lines.extend(
        [
            "",
            "## E. Seed Structural Similarity",
            "",
            f"Seed：`{assessment['seed_case_id']}`",
            "",
        ]
    )
    for key, value in assessment["seed_similarity"].items():
        lines.append(f"- {key}：{value}")
    lines.extend(
        [
            "",
            f"Structure fit：`{assessment['structure_fit']}`",
            "",
            "> This is a Research Assessment, not an Approved Pattern invariant.",
            "",
            "## F. Surface Diversity",
            "",
        ]
    )
    for key, value in assessment["surface_diversity"].items():
        lines.append(f"- {key}：{value}")
    lines.extend(
        [
            "",
            "> Surface Diversity is Presentation/Research evidence; it is not Semantic Novelty.",
            "",
        ]
    )
    if formal["research_target_ref"] == "number_or_price_led_micro_information":
        lines.extend(
            [
                "## G. Price-led Scope Warning",
                "",
                f"- scope_evidence：`{assessment['scope_evidence']}`",
                f"- warning：{assessment['scope_warning']}",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## G. Scene Contrast Quality",
                "",
                f"- scene_contrast_quality：`{assessment['scene_contrast_quality']}`",
                f"- reason：{assessment['scene_quality_reason']}",
                "",
            ]
        )
    visible_status = "visible_person_present_review_required" if privacy["visible_person"] else "no_visible_person_observed"
    lines.extend(
        [
            "## H. Rights / Privacy",
            "",
            f"- privacy_status：`{privacy['status']}`",
            f"- visible_person_status：`{visible_status}`",
            f"- source_provenance_status：`{assessment['source_provenance_status']}`",
            f"- source_rights_status：`{privacy['source_rights_status']}`",
            "",
            "Structure fit does not satisfy or bypass source-rights/privacy review.",
            "",
            "## I. Conditional Lifecycle Impact",
            "",
            f"- {assessment['lifecycle_impact']}",
            "- Pattern Eligibility is calculated only; no Cross-case Comparison or Pattern Research was performed.",
            "",
            "## Human Review Gate",
            "",
            "- [ ] Identity and source Evidence agree.",
            "- [ ] Micro Beat boundaries and carrier are materially correct.",
            "- [ ] Seed similarity and surface-diversity assessment are accepted or corrected.",
            "- [ ] Privacy and source rights are independently resolved.",
            "- [ ] No Case fact transfer, Proof upgrade, or Pattern claim occurred.",
            "",
            "Do not approve through this document. Use the existing explicit Case Human Gate.",
            "",
        ]
    )
    return "\n".join(lines)


def render_phase_b_human_review_summary(rows: list[dict[str, str]]) -> str:
    lines = [
        "# News Phase B Round 1｜Human Review Summary V1",
        "",
        "| Case | Direction | Observed profile | Structure fit | Surface diversity | Privacy | Rights | Lifecycle impact |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['case']} | {row['direction']} | {row['observed_profile']} | {row['structure_fit']} | "
            f"{row['surface_diversity']} | {row['privacy']} | {row['rights']} | {row['lifecycle_impact']} |"
        )
    return "\n".join(lines) + "\n"


def prepare_phase_b_human_review(root: Path) -> list[Path]:
    round_1_dir = root / "data" / "case_acquisition" / "news_phase_b" / "round_1"
    scout_path = round_1_dir / "news_phase_b_round_1_scout_v1.json"
    scout = read_json(scout_path)
    validate_news_phase_b_round_1_scout_v1(scout)
    formals = {
        str(item["case_id"]): item for item in scout["formal_case_candidates"]
    }
    if set(formals) != set(PHASE_B_HUMAN_REVIEW_ASSESSMENTS):
        raise RuntimeError("Phase B Human Review preparation requires exactly the four reviewed Formal Candidates.")

    paths: list[Path] = []
    summary_rows: list[dict[str, str]] = []
    for case_id, assessment in PHASE_B_HUMAN_REVIEW_ASSESSMENTS.items():
        formal = formals[case_id]
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        case_artifact = read_json(case_path)
        if case_artifact["lifecycle"]["status"] != "review_required":
            raise RuntimeError(f"Human Review preparation cannot alter or accept Case lifecycle: {case_id}")
        if sha256_file(case_path) != formal["canonical_case_ref"]["sha256"]:
            raise RuntimeError(f"Case lineage changed before Human Review preparation: {case_id}")
        pack_path = round_1_dir / "human_review" / case_id / "case_human_review_pack_concise_v1.md"
        write_text_idempotent(
            pack_path,
            render_phase_b_concise_review_pack(formal, case_artifact, assessment),
        )
        paths.append(pack_path)
        summary_rows.append(
            {
                "case": case_id,
                "direction": formal["research_target_ref"],
                "observed_profile": case_artifact["profile_analysis"]["observed_source_profile"],
                "structure_fit": assessment["structure_fit"],
                "surface_diversity": assessment["surface_diversity"]["assessment"],
                "privacy": formal["privacy"]["status"],
                "rights": formal["privacy"]["source_rights_status"],
                "lifecycle_impact": assessment["lifecycle_impact"],
            }
        )
    summary_path = round_1_dir / "news_phase_b_round_1_human_review_summary_v1.md"
    write_text_idempotent(summary_path, render_phase_b_human_review_summary(summary_rows))
    paths.append(summary_path)
    return paths


PHASE_B_STRUCTURAL_DECISION_REASONS: dict[str, list[str]] = {
    "7640840358842207507": [
        "9.9 元/月与 1000 万 Tokens/月形成首个 offer anchor。",
        "后续套餐层级、额度与权益解释 scope。",
        "on-screen text 为 primary Semantic Carrier；不依赖 continuous narration。",
        "与 705 Seed 结构相似，但行业与 surface 明显不同。",
    ],
    "7635146658208744867": [
        "29.9 → 14.9 构成首个 price comparison anchor。",
        "价格文字持续存在，后续 visual service states 提供 offer 使用语境。",
        "不依赖 continuous narration，且 surface 与 Seed 不同。",
        "constraint/scope Beat 较弱；不得预设 explicit scope 为 Pattern invariant。",
    ],
    "7639693960727179747": [
        "可恢复 State A → actual operation → reveal → State B。",
        "visual state 是 primary Semantic Carrier，不需要 narration。",
        "Scene Contrast quality = strong。",
    ],
    "7616327461634652005": [
        "多个有意义的 old/new state 配对改变用户对地点变化的理解。",
        "没有可恢复 transformation action，主要是 repeated comparison catalogue。",
        "该边界差异不使其失去有效 News Case Evidence 资格。",
        "不得提前把 transformation action 冻结成 Scene Contrast invariant。",
    ],
}


def _case_source_provenance(case: dict[str, Any]) -> dict[str, Any]:
    video = (case.get("source_evidence") or {}).get("video") or {}
    local_path = Path(str(video.get("path") or "")).expanduser().resolve()
    local_exists = local_path.is_file()
    recorded_sha = str(video.get("sha256") or "")
    actual_sha = sha256_file(local_path) if local_exists else None
    return {
        "traceable": bool(
            case.get("case_id")
            and (case.get("identity") or {}).get("platform")
            and local_exists
        ),
        "platform": (case.get("identity") or {}).get("platform"),
        "source_url": (case.get("identity") or {}).get("source_url"),
        "source_url_present": bool((case.get("identity") or {}).get("source_url")),
        "local_source_path": str(local_path),
        "local_source_exists": local_exists,
        "local_source_sha256": actual_sha,
        "recorded_source_sha256": recorded_sha or None,
        "recorded_sha_matches": None if not recorded_sha else recorded_sha == actual_sha,
        "semantics": "identity_and_evidence_lineage_not_reuse_permission",
    }


def build_phase_b_human_review_closure(root: Path) -> dict[str, Any]:
    round_1_dir = root / "data" / "case_acquisition" / "news_phase_b" / "round_1"
    scout_path = round_1_dir / "news_phase_b_round_1_scout_v1.json"
    scout = read_json(scout_path)
    validate_news_phase_b_round_1_scout_v1(scout)
    formals = {
        str(item["case_id"]): item for item in scout["formal_case_candidates"]
    }
    decisions: list[dict[str, Any]] = []
    for case_id, assessment in PHASE_B_HUMAN_REVIEW_ASSESSMENTS.items():
        formal = formals[case_id]
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        case_artifact = read_json(case_path)
        if case_artifact["lifecycle"]["status"] != "review_required":
            raise RuntimeError(f"Structural PASS cannot rewrite Case lifecycle: {case_id}")
        if sha256_file(case_path) != formal["canonical_case_ref"]["sha256"]:
            raise RuntimeError(f"Case changed before structural closure: {case_id}")
        effective_direction = (
            "price_offer_led_micro_information"
            if formal["research_target_ref"] == "number_or_price_led_micro_information"
            else "scene_contrast"
        )
        decision = {
            "case_id": case_id,
            "reviewer": "李健",
            "human_structural_profile_decision": "pass",
            "observed_source_profile": "news",
            "compatible_generation_profiles_candidate": ["news"],
            "research_direction": effective_direction,
            "research_role": {
                "7640840358842207507": "core_evidence",
                "7635146658208744867": "variant_evidence",
                "7639693960727179747": "core_evidence",
                "7616327461634652005": "boundary_variant_evidence",
            }[case_id],
            "reason": PHASE_B_STRUCTURAL_DECISION_REASONS[case_id],
            "scope_evidence": assessment.get("scope_evidence"),
            "scene_contrast_quality": assessment.get("scene_contrast_quality"),
            "transformation_action_required_for_case_validity": (
                False if case_id == "7616327461634652005" else None
            ),
            "canonical_case_lifecycle_status": "review_required",
            "canonical_case_approval_withheld": True,
            "governance_dependency": "case_source_governance_audit_v1",
            "case_ref": artifact_ref(case_path, "review_required_case"),
            "storyboard_ref": artifact_ref(
                case_path.parent / "reverse_storyboard_news_micro_beat_v1.json",
                "reverse_storyboard_news_micro_beat",
            ),
            "concise_review_pack_ref": artifact_ref(
                round_1_dir
                / "human_review"
                / case_id
                / "case_human_review_pack_concise_v1.md",
                "concise_human_review_pack",
            ),
        }
        decisions.append(decision)
    return {
        "schema_version": NEWS_PHASE_B_HUMAN_REVIEW_CLOSURE_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "closure_id": "news_phase_b_round_1_human_review_closure_v1",
        "status": "human_structural_review_complete_governance_pending",
        "reviewer": "李健",
        "closed_at": now_iso(),
        "source_scout_ref": artifact_ref(scout_path, "news_phase_b_round_1_scout_v1"),
        "human_structural_profile_decisions": decisions,
        "research_scope_amendment": {
            "amendment_type": "research_scope_correction",
            "historical_research_target": "number_or_price_led_micro_information",
            "historical_artifacts_modified": False,
            "effective_research_evidence_scope": "price_offer_led_micro_information",
            "scope_evidence": "price_offer_led_only",
            "supporting_case_ids": [
                CASE_705,
                "7640840358842207507",
                "7635146658208744867",
            ],
            "reason": (
                "All current Evidence is driven by price, offer, package or discount; "
                "generic number-led structure is not evidenced."
            ),
            "broader_number_led_status": "insufficient_evidence",
            "future_research_boundary": (
                "A non-price numeric-first Case requires a separate future Research direction."
            ),
            "pattern_invariant_claimed": False,
        },
        "research_role_authority": {
            "allowed_values": [
                "core_evidence",
                "variant_evidence",
                "boundary_variant_evidence",
            ],
            "purpose": "future_cross_case_research_interpretation_only",
            "changes_case_approval_authority": False,
            "changes_pattern_lifecycle_threshold": False,
            "invalidates_boundary_evidence": False,
        },
        "direction_evidence_status": {
            "price_offer_led_micro_information": {
                "canonical_approved_case_ids": [CASE_705],
                "structural_pass_canonical_pending_case_ids": [
                    "7640840358842207507",
                    "7635146658208744867",
                ],
                "current_canonical_approved_count": 1,
                "if_all_pending_approved_count": 3,
                "conditional_status": [
                    "eligible_for_cross_case_comparison",
                    "eligible_for_pattern_candidate_research",
                ],
                "research_executed": False,
            },
            "scene_contrast": {
                "canonical_approved_case_ids": [],
                "structural_pass_canonical_pending_case_ids": [
                    CASE_750,
                    "7639693960727179747",
                    "7616327461634652005",
                ],
                "current_canonical_approved_count": 0,
                "if_phase_b_two_approved_seed_pending_count": 2,
                "if_all_three_approved_count": 3,
                "conditional_status_if_two": "pattern_hypothesis_research_only",
                "conditional_status_if_three": "eligible_for_cross_case_comparison",
                "research_executed": False,
            },
        },
        "authority": {
            "case_approved": False,
            "case_artifact_modified": False,
            "pattern_research_performed": False,
            "cross_case_comparison_performed": False,
            "new_case_acquisition_performed": False,
            "remote_model_called": False,
            "privacy_authority_changed": False,
            "proof_authority_changed": False,
        },
    }


def build_case_source_governance_audit(root: Path) -> dict[str, Any]:
    historical_ids = [
        "7680512578585870322",
        "7683027343636542565",
        "7650056203686530319",
        CASE_705,
        CASE_758,
    ]
    current_ids = [
        CASE_750,
        "7640840358842207507",
        "7635146658208744867",
        "7639693960727179747",
        "7616327461634652005",
    ]
    case_audit: list[dict[str, Any]] = []
    for case_id in historical_ids + current_ids:
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        case = read_json(case_path)
        rights = case.get("source_rights_gate")
        privacy = case.get("privacy_gate") or {}
        receipt_path = case_path.parent / "approval_receipt.json"
        case_audit.append(
            {
                "case_id": case_id,
                "cohort": (
                    "historical_canonical_approved"
                    if case_id in historical_ids
                    else "current_structural_pass_canonical_pending"
                ),
                "case_lifecycle_status": case["lifecycle"]["status"],
                "case_ref": artifact_ref(case_path, "canonical_case"),
                "approval_receipt_ref": (
                    artifact_ref(receipt_path, "case_approval_receipt")
                    if receipt_path.is_file()
                    else None
                ),
                "source_provenance": _case_source_provenance(case),
                "privacy_status": (
                    "library_safe"
                    if privacy.get("library_safe") is True
                    else "legacy_embedded_privacy_gate_absent"
                ),
                "source_rights_field": {
                    "present": rights is not None,
                    "status": (rights or {}).get("status"),
                    "enforced_by_canonical_approve_case_v1": False,
                },
                "research_ingestion_eligibility": (
                    "historically_accepted_by_human_case_approval"
                    if case_id in historical_ids
                    else "human_policy_decision_required"
                ),
                "media_reuse_rights": "not_established_by_case_approval",
                "case_artifact_modified_by_audit": False,
            }
        )
    approval_script = root / "scripts" / "approve_case_v1.py"
    frozen_profile_authority = (
        root.parent
        / "docs"
        / "design"
        / "Production Profile & Creative Coverage V1｜产品与工程冻结框架.md"
    )
    working_architecture = (
        root.parent
        / "docs"
        / "product"
        / "AI短视频代运营生产工作流与案例资产架构_V0.1_Working_Architecture.md"
    )
    return {
        "schema_version": CASE_SOURCE_GOVERNANCE_AUDIT_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "audit_id": "case_source_governance_audit_v1",
        "status": "human_policy_decision_required",
        "created_at": now_iso(),
        "scope": {
            "historical_approved_case_ids": historical_ids,
            "current_structural_pass_canonical_pending_case_ids": current_ids,
            "legal_conclusion_scope": "none",
        },
        "authority_refs": {
            "canonical_case_approval_implementation": artifact_ref(
                approval_script, "approve_case_v1"
            ),
            "frozen_production_profile_authority": artifact_ref(
                frozen_profile_authority, "frozen_product_authority"
            ),
            "working_case_library_policy": artifact_ref(
                working_architecture, "working_architecture"
            ),
        },
        "historical_case_approval_requirements": {
            "source_traceable": True,
            "validation_passed": True,
            "privacy_library_safe_under_current_approval_script": True,
            "visual_coverage_candidate_complete": True,
            "storyboard_present": True,
            "human_review_required_before_approval": True,
            "proof_boundary_preserved": True,
            "pattern_mining_not_performed": True,
            "source_rights_gate_checked_by_approve_case_v1": False,
            "media_reuse_rights_established": False,
        },
        "current_news_case_requirements": {
            "canonical_case_requirements_unchanged": True,
            "news_semantic_carrier_recoverable": True,
            "profile_classification_human_reviewed": True,
            "privacy_gate_preserved": True,
            "source_rights_review_required_field_added_conservatively": True,
            "source_rights_field_is_canonical_approval_gate": False,
            "pending_policy_resolution_before_current_case_approval": True,
        },
        "governance_distinction": {
            "source_provenance": {
                "meaning": "Source URL where available, platform/case identity, local source and SHA/evidence lineage are traceable.",
                "does_not_mean": "permission to reuse the source footage",
            },
            "research_ingestion_eligibility": {
                "meaning": "Company/Case Library policy permits internal structural research on this source.",
                "current_policy_state": "not_frozen_as_executable_status",
            },
            "media_reuse_rights": {
                "meaning": "Permission to use original video/audio/frames directly in customer Production.",
                "current_case_approval_effect": "not_granted",
            },
        },
        "detected_drift": {
            "source_rights_field_origin": "news_acquisition_conservative_field_not_canonical_approval_gate",
            "canonical_approve_case_checks_source_rights": False,
            "historical_approved_cases_have_uniform_source_rights_field": False,
            "field_semantics_overloaded": True,
            "behavioral_difference_detected": (
                "Current News Cases were conservatively held pending on a field that historical Case Approval did not enforce."
            ),
            "canonical_case_policy_silently_changed": False,
            "reason_no_silent_change": (
                "No pending Case was approved or rejected under a newly invented rule; lifecycle remains review_required pending policy decision."
            ),
            "legacy_privacy_note": (
                "Case 7680512578585870322 predates the embedded privacy_gate now enforced by the current approval script; this audit does not amend it."
            ),
        },
        "blocking_semantics": {
            "source_provenance": "missing_or_untraceable_blocks_case_research_approval",
            "privacy": "library_safe_false_blocks_case_research_approval",
            "evidence_and_human_review": "failed_or_incomplete_blocks_case_research_approval",
            "research_ingestion_eligibility": "human_policy_decision_required",
            "media_reuse_rights": "blocks_footage_reuse_not_structural_fact_authority",
        },
        "human_policy_decision_points": [
            {
                "decision_id": "GOV-001",
                "question": (
                    "Does canonical Case approval authorize internal structural research only when provenance, privacy and Evidence gates pass, "
                    "or is separate per-source research_ingestion approval required?"
                ),
            },
            {
                "decision_id": "GOV-002",
                "question": (
                    "Which evidence/status values establish research_ingestion_eligibility for public-platform sources?"
                ),
            },
            {
                "decision_id": "GOV-003",
                "question": (
                    "Should media_reuse_rights remain a separate production-footage gate rather than a Case structural-research approval gate?"
                ),
            },
            {
                "decision_id": "GOV-004",
                "question": (
                    "How should historical approved Cases without a source_rights field be represented without rewriting their approved artifacts?"
                ),
            },
        ],
        "case_audit": case_audit,
        "interim_behavior": {
            "four_phase_b_cases": "human_structural_pass_canonical_review_required",
            "scene_seed_750782": "human_structural_pass_canonical_review_required",
            "historical_approved_cases": "unchanged",
            "footage_reuse_without_media_rights": "blocked",
        },
        "authority": {
            "legal_conclusion_made": False,
            "case_approval_policy_changed": False,
            "case_lifecycle_changed": False,
            "privacy_authority_changed": False,
            "proof_authority_changed": False,
            "pattern_research_performed": False,
            "new_case_acquisition_performed": False,
            "remote_model_called": False,
        },
    }


def render_phase_b_human_review_closure(closure: dict[str, Any]) -> str:
    lines = [
        "# News Phase B Round 1｜Human Review Closure",
        "",
        "Status: **Human Structural Review Complete / Governance Pending**",
        "",
        "| Case | Decision | Direction | Research role | Canonical lifecycle |",
        "|---|---|---|---|---|",
    ]
    for item in closure["human_structural_profile_decisions"]:
        lines.append(
            f"| {item['case_id']} | PASS | {item['research_direction']} | "
            f"{item['research_role']} | {item['canonical_case_lifecycle_status']} |"
        )
    scope = closure["research_scope_amendment"]
    lines.extend([
        "",
        "## Research Scope Amendment",
        "",
        f"`{scope['historical_research_target']}` is retained in historical Artifacts. Current Evidence scope is "
        f"`{scope['effective_research_evidence_scope']}` / `{scope['scope_evidence']}`. Broader number-led remains "
        f"`{scope['broader_number_led_status']}`.",
        "",
        "## Conditional Eligibility",
        "",
        "- Price/Offer-led: 1 canonical approved now; if both pending Cases are approved, 3 → cross-case comparison and Pattern Candidate Research eligible.",
        "- Scene Contrast: 0 canonical approved now; if only both Phase B Cases are approved, 2 → Pattern Hypothesis Research only; if all three including 750782 are approved, 3 → Cross-case Comparison eligible.",
        "",
        "No Case Approval, Cross-case Comparison, or Pattern Research was performed.",
        "",
    ])
    return "\n".join(lines)


def render_case_source_governance_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# Case Source Governance Audit V1",
        "",
        "Status: **Human Policy Decision Required**",
        "",
        "## Finding",
        "",
        "`source_rights_review_required` was added during News acquisition as a conservative field. "
        "The canonical Case approval implementation does not inspect it, and historical approved Cases do not use it consistently. "
        "It therefore cannot be silently promoted into a new Case Approval Authority.",
        "",
        "## Three Separate Concepts",
        "",
        "- Source provenance: traceable identity and Evidence lineage; not reuse permission.",
        "- Research ingestion eligibility: permission under company policy for internal structural research; executable policy is not frozen.",
        "- Media reuse rights: permission to use original footage/audio/frames in customer Production; Case approval does not grant it.",
        "",
        "## Case Audit",
        "",
        "| Case | Cohort | Lifecycle | Provenance | Privacy | source_rights field | Research ingestion | Media reuse |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in audit["case_audit"]:
        rights = item["source_rights_field"]
        lines.append(
            f"| {item['case_id']} | {item['cohort']} | {item['case_lifecycle_status']} | "
            f"{'traceable' if item['source_provenance']['traceable'] else 'not_traceable'} | "
            f"{item['privacy_status']} | {rights['status'] or 'absent'} | "
            f"{item['research_ingestion_eligibility']} | {item['media_reuse_rights']} |"
        )
    lines.extend([
        "",
        "## Policy Decisions Required",
        "",
    ])
    for item in audit["human_policy_decision_points"]:
        lines.append(f"- **{item['decision_id']}** — {item['question']}")
    lines.extend([
        "",
        "No legal conclusion or Case lifecycle change is made by this audit.",
        "",
    ])
    return "\n".join(lines)


def close_phase_b_human_review_and_audit_governance(root: Path) -> list[Path]:
    round_1_dir = root / "data" / "case_acquisition" / "news_phase_b" / "round_1"
    closure_dir = round_1_dir / "human_review_closure"
    closure_path = closure_dir / "news_phase_b_round_1_human_review_closure_v1.json"
    closure = build_phase_b_human_review_closure(root)
    validate_news_phase_b_human_review_closure_v1(closure)
    write_json_if_absent(closure_path, closure)
    closure_md = closure_dir / "news_phase_b_round_1_human_review_closure_v1.md"
    write_text_if_absent(closure_md, render_phase_b_human_review_closure(closure))

    audit_dir = root / "data" / "case_governance"
    audit_path = audit_dir / "case_source_governance_audit_v1.json"
    audit = build_case_source_governance_audit(root)
    validate_case_source_governance_audit_v1(audit)
    write_json_if_absent(audit_path, audit)
    audit_md = audit_dir / "case_source_governance_audit_v1.md"
    write_text_if_absent(audit_md, render_case_source_governance_audit(audit))
    return [closure_path, closure_md, audit_path, audit_md]


PENDING_NEWS_APPROVAL_IDS = [
    CASE_750,
    "7640840358842207507",
    "7635146658208744867",
    "7639693960727179747",
    "7616327461634652005",
]

HISTORICAL_APPROVED_GOVERNANCE_IDS = [
    "7680512578585870322",
    "7683027343636542565",
    "7650056203686530319",
    CASE_705,
    CASE_758,
]


def build_case_source_governance_policy(
    root: Path,
    *,
    review_closure_path: Path,
    prior_audit_path: Path,
) -> dict[str, Any]:
    decisions: list[dict[str, Any]] = []
    for case_id in PENDING_NEWS_APPROVAL_IDS:
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        case = read_json(case_path)
        if case["lifecycle"]["status"] not in {"review_required", "approved"}:
            raise RuntimeError(f"Unexpected Case lifecycle before policy decision: {case_id}")
        research_direction = (
            "price_offer_led_micro_information"
            if case_id in {"7640840358842207507", "7635146658208744867"}
            else "scene_contrast"
        )
        research_role = {
            CASE_750: "core_evidence",
            "7640840358842207507": "core_evidence",
            "7635146658208744867": "variant_evidence",
            "7639693960727179747": "core_evidence",
            "7616327461634652005": "boundary_variant_evidence",
        }[case_id]
        decisions.append(
            {
                "case_id": case_id,
                "canonical_case_decision": "approve",
                "human_structural_profile_decision": "pass",
                "observed_source_profile": "news",
                "compatible_generation_profiles": ["news"],
                "research_direction": research_direction,
                "research_role": research_role,
                "research_ingestion_eligibility": "eligible_for_internal_research",
                "media_reuse_rights": "not_established",
                "no_current_company_policy_block": True,
                "preapproval_case_ref": {
                    **artifact_ref(case_path, "review_required_case"),
                    "expected_change": "explicit_canonical_human_approval_only",
                },
                "human_decision_ref": artifact_ref(
                    (
                        root
                        / "data"
                        / "cases"
                        / CASE_750
                        / "case_profile_structural_decision_v1.json"
                        if case_id == CASE_750
                        else review_closure_path
                    ),
                    (
                        "case_profile_structural_decision_v1"
                        if case_id == CASE_750
                        else "news_phase_b_human_review_closure_v1"
                    ),
                ),
            }
        )
    return {
        "schema_version": CASE_SOURCE_GOVERNANCE_POLICY_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "policy_id": "case_source_governance_v1",
        "version": "V1.0",
        "status": "approved_frozen",
        "reviewer": "李健",
        "approved_at": now_iso(),
        "resolves_audit_ref": artifact_ref(prior_audit_path, "case_source_governance_audit_v1"),
        "canonical_case_approval": {
            "authorization_scope": "internal_creative_structural_research_eligibility",
            "grants_copyright_ownership": False,
            "grants_media_reuse_permission": False,
            "grants_footage_redistribution_permission": False,
            "grants_customer_production_footage_authorization": False,
        },
        "research_ingestion_eligibility": {
            "allowed_values": [
                "eligible_for_internal_research",
                "review_required",
                "blocked",
            ],
            "public_platform_minimum_requirements": [
                "source_provenance_traceable",
                "source_url_or_case_id_and_local_sha_traceable",
                "evidence_lineage_complete",
                "privacy_policy_satisfied",
                "human_case_review_pass",
                "no_current_company_policy_block",
            ],
            "semantics": "internal_governance_decision_not_legal_rights_claim",
        },
        "media_reuse_rights": {
            "allowed_values": [
                "licensed",
                "authorized",
                "not_established",
                "blocked",
            ],
            "public_source_default": "not_established",
            "changed_by_case_approval": False,
            "production_footage_pool_allowed_values": ["licensed", "authorized"],
        },
        "legacy_source_rights_field": {
            "canonical_case_approval_gate": False,
            "deprecated_for_combined_semantics": True,
            "historical_artifacts_deleted_or_rewritten": False,
            "replacement": [
                "research_ingestion_eligibility",
                "media_reuse_rights",
            ],
        },
        "historical_case_policy": {
            "companion_metadata_required": True,
            "approved_artifact_rewrite_forbidden": True,
            "historical_research_eligibility_representation": "eligible_for_internal_research",
            "historical_eligibility_basis": "historically_accepted_for_internal_research",
            "default_media_reuse_rights": "not_established",
            "legacy_privacy_case_id": "7680512578585870322",
            "legacy_privacy_basis": "legacy_approval_before_embedded_privacy_gate",
        },
        "pending_case_human_governance_decisions": decisions,
        "research_scope": {
            "price_offer_led_micro_information": {
                "approved_evidence_target_case_ids": [
                    CASE_705,
                    "7640840358842207507",
                    "7635146658208744867",
                ],
                "scope_evidence": "price_offer_led_only",
                "broader_number_led": "insufficient_evidence",
            },
            "scene_contrast": {
                "approved_evidence_target_case_ids": [
                    CASE_750,
                    "7639693960727179747",
                    "7616327461634652005",
                ],
                "operation_required": False,
                "transition_required": False,
                "before_after_wording_required": False,
                "duration_frozen": False,
                "beat_count_frozen": False,
            },
        },
        "authority": {
            "legal_rights_claimed": False,
            "pattern_lifecycle_changed": False,
            "proof_authority_changed": False,
            "privacy_authority_changed": False,
        },
    }


def render_case_source_governance_policy(policy: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Case Source Governance V1",
            "",
            "Status: **Approved / Frozen**",
            "",
            "Canonical Case Approval authorizes internal creative/structural research eligibility only.",
            "It does not grant copyright ownership, media reuse, redistribution, or customer-production footage authorization.",
            "",
            "## Research Ingestion Eligibility",
            "",
            "Allowed: `eligible_for_internal_research`, `review_required`, `blocked`.",
            "This is an internal governance decision, not a legal rights claim.",
            "",
            "## Media Reuse Rights",
            "",
            "Allowed: `licensed`, `authorized`, `not_established`, `blocked`.",
            "Public-source Cases default to `not_established`; Case Approval never changes this status.",
            "Only `licensed` or `authorized` media may enter the customer Production Footage Pool.",
            "",
            "## Legacy source_rights Field",
            "",
            "The combined legacy field is not a canonical Case Approval gate and must no longer represent both research ingestion and media reuse.",
            "Historical Artifacts remain unchanged; companion metadata carries the split governance states.",
            "",
        ]
    )


def build_case_governance_companion(
    root: Path,
    case_id: str,
    *,
    policy_path: Path,
    historical: bool,
) -> dict[str, Any]:
    case_path = root / "data" / "cases" / case_id / "case_v1.json"
    case = read_json(case_path)
    if case["lifecycle"]["status"] != "approved":
        raise RuntimeError(f"Governance Companion requires Approved Case: {case_id}")
    receipt_path = case_path.parent / "approval_receipt.json"
    provenance = _case_source_provenance(case)
    if not provenance["traceable"]:
        raise RuntimeError(f"Source provenance is not traceable: {case_id}")
    privacy_basis = (
        "legacy_approval_before_embedded_privacy_gate"
        if case_id == "7680512578585870322"
        else "embedded_privacy_gate_library_safe"
    )
    return {
        "schema_version": CASE_SOURCE_GOVERNANCE_COMPANION_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "companion_id": f"case_source_governance_companion_v1::{case_id}",
        "case_id": case_id,
        "canonical_case_status": "approved",
        "case_ref": artifact_ref(case_path, "approved_case"),
        "case_approval_receipt_ref": artifact_ref(receipt_path, "case_approval_receipt"),
        "source_provenance": {
            "status": "traceable",
            **provenance,
        },
        "research_ingestion_eligibility": "eligible_for_internal_research",
        "research_ingestion_basis": (
            "historically_accepted_for_internal_research"
            if historical
            else "explicit_human_governance_decision"
        ),
        "media_reuse_rights": "not_established",
        "production_footage_pool_eligible": False,
        "privacy_basis": privacy_basis,
        "legacy_source_rights_field_observation": {
            "present": case.get("source_rights_gate") is not None,
            "status": (case.get("source_rights_gate") or {}).get("status"),
            "used_as_current_governance_authority": False,
        },
        "governance_policy_version": "V1.0",
        "governance_policy_ref": artifact_ref(policy_path, "case_source_governance_policy_v1"),
        "case_approval_changed_media_reuse_rights": False,
        "created_at": now_iso(),
    }


def _research_surface(case_id: str) -> dict[str, Any]:
    if case_id == CASE_705:
        return {
            "industry_or_topic": "local_hot_spring_offer",
            "content_surface": "multi_visit_price_cards",
            "visual_surface": "venue_facilities_and_purchase_interface",
            "semantic_organization": "price_offer_anchor_then_context_scope_and_close",
        }
    if case_id == CASE_750:
        return {
            "industry_or_topic": "residential_space_renovation",
            "content_surface": "multiple_room_before_after_states",
            "visual_surface": "space_views_with_overlay_transitions",
            "semantic_organization": "repeated_state_a_to_state_b_groups_then_result_close",
        }
    assessment = PHASE_B_HUMAN_REVIEW_ASSESSMENTS[case_id]["surface_diversity"]
    return {
        "industry_or_topic": assessment["industry_or_topic"],
        "content_surface": assessment["content_surface"],
        "visual_surface": assessment["visual_surface"],
        "semantic_organization": assessment["semantic_organization"],
    }


def build_news_cross_case_research_bundle(
    root: Path,
    *,
    direction: str,
    case_roles: dict[str, str],
    policy_path: Path,
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    governance_root = root / "data" / "case_governance" / "cases"
    for case_id, role in case_roles.items():
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        fingerprint_path = root / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"
        storyboard_path = case_path.parent / "reverse_storyboard_news_micro_beat_v1.json"
        companion_path = governance_root / case_id / "case_source_governance_companion_v1.json"
        case = read_json(case_path)
        fingerprint = read_json(fingerprint_path)
        storyboard = read_json(storyboard_path)
        companion = read_json(companion_path)
        validate_case_source_governance_companion_v1(
            companion,
            expected_case_sha256=sha256_file(case_path),
        )
        beats = storyboard["micro_beat_sequence"]
        entries.append(
            {
                "case_id": case_id,
                "canonical_case_status": "approved",
                "observed_source_profile": "news",
                "research_role": role,
                "research_ingestion_eligibility": companion["research_ingestion_eligibility"],
                "media_reuse_rights": companion["media_reuse_rights"],
                "case_ref": artifact_ref(case_path, "approved_case"),
                "fingerprint_ref": artifact_ref(fingerprint_path, "case_fingerprint"),
                "storyboard_ref": artifact_ref(storyboard_path, "news_micro_beat_storyboard"),
                "governance_companion_ref": artifact_ref(
                    companion_path, "case_source_governance_companion_v1"
                ),
                "micro_beat_structure": beats,
                "semantic_carrier": fingerprint["semantic_carrier_features"],
                "surface_characteristics": _research_surface(case_id),
                "timing": {
                    "duration_seconds": case["identity"]["duration_seconds"],
                    "beat_count": len(beats),
                    "duration_or_beat_count_is_pattern_invariant": False,
                },
                "hook": {
                    "semantic_role": beats[0]["semantic_role"],
                    "visual_state": beats[0]["visual_state"],
                },
                "progression": [beat["semantic_role"] for beat in beats],
                "visual_states": [beat["visual_state"] for beat in beats],
                "close": {
                    "semantic_role": beats[-1]["semantic_role"],
                    "visual_state": beats[-1]["visual_state"],
                },
                "proof_trust_behavior": {
                    "verified_proof_count": (case.get("quality") or {}).get(
                        "verified_proof_count", 0
                    ),
                    "claims_semantics": (case.get("storyboard") or {}).get(
                        "claims_semantics"
                    ),
                    "effectiveness_status": "unvalidated",
                    "case_claims_are_customer_authority": False,
                },
            }
        )
    scope = (
        {
            "effective_scope": "price_offer_led_micro_information",
            "scope_evidence": "price_offer_led_only",
            "broader_number_led": "insufficient_evidence",
        }
        if direction == "price_offer_led_micro_information"
        else {
            "effective_scope": "scene_contrast",
            "operation_required": False,
            "transition_required": False,
            "before_after_wording_required": False,
            "duration_or_beat_count_frozen": False,
        }
    )
    return {
        "schema_version": NEWS_CROSS_CASE_RESEARCH_BUNDLE_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "bundle_id": f"news_cross_case_research_bundle_v1::{direction}",
        "status": "cross_case_research_ready",
        "production_profile": "news",
        "research_direction": direction,
        "created_at": now_iso(),
        "governance_policy_ref": artifact_ref(policy_path, "case_source_governance_policy_v1"),
        "scope": scope,
        "cases": entries,
        "canonical_approved_case_count": len(entries),
        "eligible_for_cross_case_comparison": True,
        "eligible_for_pattern_candidate_research": True,
        "eligibility_is_not_automatic_pattern_candidate": True,
        "comparison_executed": False,
        "comparison_execution_status": (
            "not_run_existing_comparator_requires_exactly_two_legacy_fingerprint_cases_and_is_not_news_bundle_compatible"
        ),
        "pattern_candidate_created": False,
        "authority": {
            "case_specific_facts_used_as_customer_authority": False,
            "effectiveness_claimed": False,
            "proof_upgraded": False,
            "pattern_created": False,
            "remote_model_called": False,
        },
    }


def render_news_cross_case_research_bundle(bundle: dict[str, Any]) -> str:
    lines = [
        f"# News Cross-case Research Input｜{bundle['research_direction']}",
        "",
        "Status: **Cross-case Research Ready**",
        "",
        "| Case | Research role | Duration | Beats | Media reuse |",
        "|---|---|---:|---:|---|",
    ]
    for item in bundle["cases"]:
        lines.append(
            f"| {item['case_id']} | {item['research_role']} | "
            f"{item['timing']['duration_seconds']}s | {item['timing']['beat_count']} | "
            f"{item['media_reuse_rights']} |"
        )
    lines.extend([
        "",
        f"Comparison status: `{bundle['comparison_execution_status']}`.",
        "",
        "No Pattern Candidate, effectiveness claim, Proof upgrade, or Customer Fact transfer was produced.",
        "",
    ])
    return "\n".join(lines)


def apply_source_governance_and_approve_news_cases(root: Path) -> list[Path]:
    governance_dir = root / "data" / "case_governance"
    prior_audit_path = governance_dir / "case_source_governance_audit_v1.json"
    review_closure_path = (
        root
        / "data"
        / "case_acquisition"
        / "news_phase_b"
        / "round_1"
        / "human_review_closure"
        / "news_phase_b_round_1_human_review_closure_v1.json"
    )
    policy_path = governance_dir / "case_source_governance_policy_v1.json"
    policy = build_case_source_governance_policy(
        root,
        review_closure_path=review_closure_path,
        prior_audit_path=prior_audit_path,
    )
    validate_case_source_governance_policy_v1(policy)
    write_json_if_absent(policy_path, policy)
    policy_md = governance_dir / "case_source_governance_policy_v1.md"
    write_text_if_absent(policy_md, render_case_source_governance_policy(policy))

    approval_notes = {
        CASE_750: "Human approval under Case Source Governance V1: Scene Contrast structural evidence; internal research only; media reuse not established.",
        "7640840358842207507": "Human approval under Case Source Governance V1: price/offer-led core evidence; internal research only; media reuse not established.",
        "7635146658208744867": "Human approval under Case Source Governance V1: price/offer-led variant evidence; internal research only; media reuse not established.",
        "7639693960727179747": "Human approval under Case Source Governance V1: Scene Contrast core evidence; internal research only; media reuse not established.",
        "7616327461634652005": "Human approval under Case Source Governance V1: Scene Contrast boundary variant without required transformation action; internal research only; media reuse not established.",
    }
    for case_id in PENDING_NEWS_APPROVAL_IDS:
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        case = read_json(case_path)
        if case["lifecycle"]["status"] == "review_required":
            subprocess.run(
                [
                    sys.executable,
                    str((root / "scripts" / "approve_case_v1.py").resolve()),
                    "--case",
                    str(case_path),
                    "--reviewer",
                    "李健",
                    "--note",
                    approval_notes[case_id],
                    "--governance-policy",
                    str(policy_path),
                ],
                check=True,
            )
        elif case["lifecycle"]["status"] != "approved":
            raise RuntimeError(f"Unexpected Case lifecycle: {case_id}")

    companion_paths: dict[str, Path] = {}
    for case_id in HISTORICAL_APPROVED_GOVERNANCE_IDS + PENDING_NEWS_APPROVAL_IDS:
        companion_path = (
            governance_dir
            / "cases"
            / case_id
            / "case_source_governance_companion_v1.json"
        )
        companion = build_case_governance_companion(
            root,
            case_id,
            policy_path=policy_path,
            historical=case_id in HISTORICAL_APPROVED_GOVERNANCE_IDS,
        )
        validate_case_source_governance_companion_v1(
            companion,
            expected_case_sha256=sha256_file(
                root / "data" / "cases" / case_id / "case_v1.json"
            ),
        )
        write_json_if_absent(companion_path, companion)
        companion_paths[case_id] = companion_path

    fingerprint_specs = {
        CASE_750: (
            "visual_information_state_sequence",
            "state_a_contrast_state_b_groups_with_result_close",
        ),
        "7640840358842207507": (
            "on_screen_text_plus_visual_information_state",
            "price_offer_anchor_then_package_and_scope_states",
        ),
        "7635146658208744867": (
            "persistent_price_text_plus_visual_service_states",
            "price_comparison_anchor_then_service_context_states",
        ),
        "7639693960727179747": (
            "visual_information_state_sequence",
            "state_a_operation_reveal_state_b",
        ),
        "7616327461634652005": (
            "paired_visual_state_sequence_plus_onscreen_labels",
            "repeated_meaningful_old_new_location_pairs",
        ),
    }
    for case_id, (carrier, relationship) in fingerprint_specs.items():
        case_path = root / "data" / "cases" / case_id / "case_v1.json"
        storyboard_path = case_path.parent / "reverse_storyboard_news_micro_beat_v1.json"
        fingerprint_path = root / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"
        write_json_if_absent(
            fingerprint_path,
            news_fingerprint(
                case_path,
                storyboard_path,
                carrier_type=carrier,
                relationship=relationship,
            ),
        )
        receipt_path = case_path.parent / "approval_receipt.json"
        compatibility_path = case_path.parent / "case_profile_compatibility_approval_v1.json"
        human_decision_path = (
            case_path.parent / "case_profile_structural_decision_v1.json"
            if case_id == CASE_750
            else review_closure_path
        )
        approval = compatibility_approval(
            case_path,
            receipt_path,
            fingerprint_path,
            storyboard_path,
            [human_decision_path, policy_path, companion_paths[case_id]],
        )
        validate_case_profile_compatibility_approval_v1(
            approval,
            approved_case_sha256=sha256_file(case_path),
        )
        write_json_if_absent(compatibility_path, approval)

    bundle_specs = {
        "price_offer_led_micro_information": {
            CASE_705: "core_evidence",
            "7640840358842207507": "core_evidence",
            "7635146658208744867": "variant_evidence",
        },
        "scene_contrast": {
            CASE_750: "core_evidence",
            "7639693960727179747": "core_evidence",
            "7616327461634652005": "boundary_variant_evidence",
        },
    }
    output_paths = [policy_path, policy_md]
    for direction, roles in bundle_specs.items():
        bundle = build_news_cross_case_research_bundle(
            root,
            direction=direction,
            case_roles=roles,
            policy_path=policy_path,
        )
        validate_news_cross_case_research_bundle_v1(bundle)
        output_dir = root / "data" / "cross_case_research" / "news" / direction
        bundle_path = output_dir / "research_input_bundle_v1.json"
        bundle_md = output_dir / "research_input_bundle_v1.md"
        write_json_if_absent(bundle_path, bundle)
        write_text_if_absent(bundle_md, render_news_cross_case_research_bundle(bundle))
        output_paths.extend([bundle_path, bundle_md])
    output_paths.extend(companion_paths.values())
    return output_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Close News Phase A and execute Phase B Depth Build Round 1 through Human Review.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument(
        "--prepare-human-review-only",
        action="store_true",
        help="Build concise review packs from existing Phase B artifacts without acquisition or model calls.",
    )
    parser.add_argument(
        "--close-human-review-governance-audit-only",
        action="store_true",
        help="Persist structural PASS decisions and audit source governance without Case approval.",
    )
    parser.add_argument(
        "--apply-source-governance-and-approve-news-cases",
        action="store_true",
        help=(
            "Freeze the Human-approved Case Source Governance V1 policy, approve the "
            "five pending News Cases through the canonical Case gate, and prepare "
            "Cross-case Research input bundles without running comparison or Pattern research."
        ),
    )
    args = parser.parse_args()
    root = Path(args.project_root).expanduser().resolve()

    selected_modes = sum(
        bool(value)
        for value in (
            args.prepare_human_review_only,
            args.close_human_review_governance_audit_only,
            args.apply_source_governance_and_approve_news_cases,
        )
    )
    if selected_modes > 1:
        raise ValueError("Select only one Phase B workflow mode.")

    if args.apply_source_governance_and_approve_news_cases:
        output_paths = apply_source_governance_and_approve_news_cases(root)
        print("CASE SOURCE GOVERNANCE V1 + NEWS CASE APPROVAL PASS")
        for output_path in output_paths:
            print(output_path)
        print("Canonical Case approvals: 5")
        print("Media reuse rights granted: 0")
        print("Cross-case comparison: not run")
        print("Pattern research: not started")
        print("Remote model calls: 0")
        print("New Case acquisition: 0")
        return

    if args.close_human_review_governance_audit_only:
        output_paths = close_phase_b_human_review_and_audit_governance(root)
        print("NEWS PHASE B ROUND 1 HUMAN REVIEW CLOSURE + GOVERNANCE AUDIT PASS")
        for output_path in output_paths:
            print(output_path)
        print("Canonical Case approvals: 0")
        print("Remote model calls: 0")
        print("New Case acquisition: 0")
        print("Pattern research: not started")
        return

    if args.prepare_human_review_only:
        output_paths = prepare_phase_b_human_review(root)
        print("NEWS PHASE B ROUND 1 HUMAN REVIEW PREPARATION PASS")
        for output_path in output_paths:
            print(output_path)
        print("Remote model calls: 0")
        print("New Case acquisition: 0")
        print("Pattern research: not started")
        return

    round_1_path = root / "data" / "case_acquisition" / "news_phase_a" / "news_phase_a_breadth_scout_v1.json"
    round_2_path = root / "data" / "case_acquisition" / "news_phase_a" / "round_2" / "news_phase_a_round_2_targeted_discovery_v1.json"
    round_1 = read_json(round_1_path)
    round_2 = read_json(round_2_path)

    # 758: explicit Human Approval through the existing canonical Case gate.
    source_758 = json.loads(json.dumps(find_formal_case(round_1, CASE_758), ensure_ascii=False))
    source_758["timing_boundary"] = {
        "source_duration_seconds": 98.333,
        "structural_reference": "allowed",
        "timing_template": "not_implied",
        "duration_template": "not_implied",
        "beat_count_template": "not_implied",
        "news_registry_configurable_constraints_modified": False,
    }
    case_758_path = root / "data" / "cases" / CASE_758 / "case_v1.json"
    storyboard_758_path = case_758_path.parent / "reverse_storyboard_news_micro_beat_v1.json"
    if not case_758_path.exists():
        case_758_path, storyboard_758_path, _ = build_news_case_artifacts(
            root,
            source_758,
            content_goal="Recover an ordered event/campaign rundown from time, components, tasks, rewards, access and close states.",
            visible_person=False,
            source_rights_status="human_reviewed_for_case_approval",
            transcript_artifact_type="usable_transcript_pending_case_specific_truth_verification",
        )
        subprocess.run([
            sys.executable,
            str((root / "scripts" / "approve_case_v1.py").resolve()),
            "--case", str(case_758_path),
            "--reviewer", "李健",
            "--note", (
                "Human Decision APPROVE: seven recovered event/campaign information states materially match the source. "
                "The 98.333-second duration and seven-beat count do not create timing or duration templates."
            ),
        ], check=True)
    elif read_json(case_758_path).get("lifecycle", {}).get("status") != "approved":
        raise RuntimeError("Existing 758 Case is not approved; refusing an implicit lifecycle rewrite.")
    receipt_758_path = case_758_path.parent / "approval_receipt.json"
    fingerprint_758_path = root / "data" / "fingerprints" / CASE_758 / "case_fingerprint_v1.json"
    write_json_if_absent(
        fingerprint_758_path,
        news_fingerprint(
            case_758_path,
            storyboard_758_path,
            carrier_type="on_screen_text_plus_spoken_narration_plus_visual_information_state",
            relationship="ordered_event_information_states_with_access_and_close",
        ),
    )
    compatibility_758_path = case_758_path.parent / "case_profile_compatibility_approval_v1.json"
    compatibility_758 = compatibility_approval(
        case_758_path,
        receipt_758_path,
        fingerprint_758_path,
        storyboard_758_path,
        [round_1_path, Path(source_758["evidence_artifacts"]["visual_manifest"]["path"])],
    )
    validate_case_profile_compatibility_approval_v1(
        compatibility_758, approved_case_sha256=sha256_file(case_758_path)
    )
    write_json_if_absent(compatibility_758_path, compatibility_758)

    # 750782: persist Human structural/profile approval, but fail closed on unresolved privacy/source rights.
    source_750 = round_2_scene_case(round_2)
    case_750_path, storyboard_750_path, privacy_750_path = build_news_case_artifacts(
        root,
        source_750,
        content_goal="Recover meaningful visual State A to transformation/contrast to State B groups without narration.",
        visible_person=True,
        source_rights_status="review_required",
        transcript_artifact_type="transcript_excluded_no_reliable_continuous_narration",
    )
    case_750_decision_path = case_750_path.parent / "case_profile_structural_decision_v1.json"
    case_750_decision = {
        "schema_version": CASE_PROFILE_STRUCTURAL_DECISION_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "decision_id": f"case_profile_structural_decision_v1::{CASE_750}",
        "case_id": CASE_750,
        "reviewer": "李健",
        "decided_at": now_iso(),
        "decision": "structural_profile_approved_gate_pending",
        "observed_source_profile": "news",
        "structural_compatible_generation_profiles": ["news"],
        "canonical_approved_compatible_generation_profiles": [],
        "mix_compatibility": "not_approved",
        "case_lifecycle_status": "review_required",
        "unresolved_gates": ["privacy_review", "source_rights_review"],
        "structural_basis": {
            "semantic_carrier": "visual_information_state_sequence",
            "continuous_narration_required": False,
            "micro_beat_count": 5,
            "duration_seconds": 16.167,
        },
        "case_ref": artifact_ref(case_750_path, "review_required_case"),
        "storyboard_ref": artifact_ref(storyboard_750_path, "reverse_storyboard_news_micro_beat"),
        "privacy_projection_ref": artifact_ref(privacy_750_path, "privacy_projection"),
        "pattern_created": False,
        "authority": {
            "structural_decision_is_case_approval": False,
            "profile_decision_bypasses_privacy_or_rights": False,
            "case_specific_facts_transferred": False,
        },
    }
    validate_case_profile_structural_decision_v1(case_750_decision)
    write_json_if_absent(case_750_decision_path, case_750_decision)

    closure_dir = root / "data" / "case_acquisition" / "news_phase_a" / "closure"
    closure_path = closure_dir / "news_phase_a_final_closure_v1.json"
    closure = closure_artifact(
        round_1_path=round_1_path,
        round_2_path=round_2_path,
        case_705_path=root / "data" / "cases" / CASE_705 / "case_v1.json",
        case_758_path=case_758_path,
        case_750_path=case_750_path,
        case_750_decision_path=case_750_decision_path,
    )
    validate_news_phase_a_closure_v1(closure)
    write_json_if_absent(closure_path, closure)
    write_text_if_absent(closure_dir / "news_phase_a_final_closure_v1.md", render_closure_markdown(closure))

    registry_path = root / "data" / "production_profiles" / "production_profile_registry_v1.json"
    old_coverage_path = root / "data" / "creative_coverage" / "creative_coverage_report_v1.json"
    coverage_update = {
        "schema_version": NEWS_CREATIVE_COVERAGE_UPDATE_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "update_id": "news_phase_a_closure_creative_coverage_update_v1",
        "status": "current_derived_coverage_update",
        "created_at": now_iso(),
        "source_refs": {
            "frozen_registry": artifact_ref(registry_path, "production_profile_registry_v1"),
            "approved_coverage_baseline": artifact_ref(old_coverage_path, "creative_coverage_report_v1"),
            "phase_a_closure": artifact_ref(closure_path, "news_phase_a_closure"),
        },
        "news_current_coverage": {
            "operational_readiness": "research_coverage_insufficient",
            "creative_coverage": "evidence_breadth_present_pattern_coverage_zero",
            "approved_news_pattern_count": 0,
            "approved_news_compatible_case_ids": [CASE_705, CASE_758],
            "structural_seed_gate_pending_case_ids": [CASE_750],
            "structural_evidence_direction_count": 3,
            "structural_evidence_directions": [
                "number_or_price_led_micro_information",
                "scene_contrast",
                "event_or_campaign_information_progression",
            ],
            "news_generation_authorized": False,
        },
        "changes_canonical_coverage_authority": False,
        "pattern_coverage": 0,
    }
    validate_news_creative_coverage_update_v1(coverage_update)
    coverage_update_dir = root / "data" / "creative_coverage" / "revisions"
    coverage_update_path = coverage_update_dir / "news_phase_a_closure_creative_coverage_update_v1.json"
    write_json_if_absent(coverage_update_path, coverage_update)
    write_text_if_absent(
        coverage_update_dir / "news_phase_a_closure_creative_coverage_update_v1.md",
        "# News Creative Coverage Update\n\nPhase A is complete with three structural Evidence directions. "
        "Approved News Pattern remains 0, so operational readiness remains `research_coverage_insufficient`.\n",
    )

    phase_b_dir = root / "data" / "case_acquisition" / "news_phase_b"
    plan_path = phase_b_dir / "news_phase_b_depth_build_plan_v1.json"
    plan = phase_b_plan(closure_path)
    validate_news_phase_b_depth_build_plan_v1(plan)
    write_json_if_absent(plan_path, plan)
    write_text_if_absent(phase_b_dir / "news_phase_b_depth_build_plan_v1.md", render_phase_b_plan_markdown(plan))

    directions = phase_b_discoveries()
    formal_sources = phase_b_formal_sources(root)
    formal_cases: list[dict[str, Any]] = []
    round_1_dir = phase_b_dir / "round_1"
    for case_id, formal in formal_sources.items():
        case_path, storyboard_path, _ = build_news_case_artifacts(
            root,
            formal,
            content_goal=(
                "Compare a numeric first anchor with ordered scope/context states."
                if formal["research_target_ref"] == "number_or_price_led_micro_information"
                else "Recover meaningful visual State A, change/contrast and State B without narration."
            ),
            visible_person=formal["privacy"]["visible_person"],
            source_rights_status="review_required",
            transcript_artifact_type="transcript_excluded_no_reliable_semantic_speech",
        )
        formal["canonical_case_ref"] = artifact_ref(case_path, "review_required_case")
        formal["storyboard_ref"] = artifact_ref(storyboard_path, "reverse_storyboard_news_micro_beat")
        formal_cases.append(formal)
        write_text_if_absent(
            round_1_dir / "human_review" / case_id / "case_human_review_pack_v1.md",
            render_news_phase_a_case_review_markdown(formal),
        )

    scout = {
        "schema_version": NEWS_PHASE_B_ROUND_1_SCOUT_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "scout_id": "news_phase_b_depth_build_round_1_scout_v1",
        "status": "human_review_ready",
        "production_profile": "news",
        "created_at": now_iso(),
        "source_plan_ref": artifact_ref(plan_path, "news_phase_b_depth_build_plan_v1"),
        "directions": directions,
        "formal_case_candidates": formal_cases,
        "summary": {
            "direction_count": 2,
            "discovery_candidate_count": sum(len(item["discovery_candidates"]) for item in directions),
            "formal_candidate_count": len(formal_cases),
            "formal_candidate_count_by_direction": {
                direction["direction_id"]: sum(
                    1 for item in direction["discovery_candidates"] if item["formal_pipeline_selected"]
                ) for direction in directions
            },
            "local_prescreen_visual_extractions": 6,
            "local_formal_whisper_calls": 4,
            "remote_model_calls": 0,
            "cross_case_research_status": "not_started",
            "pattern_status": "not_created",
            "news_operational_readiness": "research_coverage_insufficient",
        },
        "authority": {
            "case_auto_approved": False,
            "pattern_created": False,
            "pattern_mining_performed": False,
            "cross_case_research_started": False,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
            "persona_modified": False,
            "content_ledger_modified": False,
        },
    }
    validate_news_phase_b_round_1_scout_v1(scout)
    scout_path = round_1_dir / "news_phase_b_round_1_scout_v1.json"
    write_json_if_absent(scout_path, scout)
    write_text_if_absent(round_1_dir / "news_phase_b_round_1_scout_v1.md", render_phase_b_scout_markdown(scout))

    print("NEWS PHASE A FINAL CLOSURE + PHASE B ROUND 1 PASS")
    print(f"758 approved Case: {case_758_path}")
    print(f"750782 structural decision (gates pending): {case_750_decision_path}")
    print(f"Phase A Closure: {closure_path}")
    print(f"Coverage Update: {coverage_update_path}")
    print(f"Phase B Plan: {plan_path}")
    print(f"Phase B Scout: {scout_path}")
    print("Discovery Candidates: 12")
    print("Formal Case Candidates: 4 (all review_required)")
    print("Remote model calls: 0")
    print("Approved News Pattern: 0")


if __name__ == "__main__":
    main()
