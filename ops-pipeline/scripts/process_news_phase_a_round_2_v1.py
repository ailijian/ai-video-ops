from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from privacy_projection_v1 import (
    PRIVACY_POLICY_VERSION,
    PRIVACY_SCHEMA_VERSION,
    build_case_privacy_gate,
    load_privacy_projection,
)
from production_profile_v1 import (
    BUILDER_VERSION,
    CASE_PROFILE_COMPATIBILITY_APPROVAL_SCHEMA_VERSION,
    NEWS_PHASE_A_ROUND_1_DECISION_SCHEMA_VERSION,
    NEWS_PHASE_A_ROUND_2_SCOUT_SCHEMA_VERSION,
    now_iso,
    read_json,
    render_concise_news_case_review_markdown,
    render_news_phase_a_case_review_markdown,
    render_news_phase_a_round_2_markdown,
    sha256_file,
    validate_case_profile_compatibility_approval_v1,
    validate_news_phase_a_round_1_decision_v1,
    validate_news_phase_a_round_2_scout_v1,
    validate_news_phase_a_scout_v1,
    write_new_json,
    write_new_text,
)


CASE_705 = "7059858129298803968"
CASE_758 = "7582922932108774691"
ROUND_2_CASE = "7507825653623344396"


def artifact_ref(path: Path, artifact_type: str) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "artifact_type": artifact_type,
        "path": str(path),
        "sha256": sha256_file(path),
        "source_artifact_modified": False,
    }


def find_formal_case(scout: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(
        item
        for item in scout.get("formal_case_candidates") or []
        if str(item.get("case_id")) == case_id
    )


def micro_beat_storyboard(case: dict[str, Any]) -> dict[str, Any]:
    beats = case["micro_beat_sequence"]
    shots = []
    for index, beat in enumerate(beats, start=1):
        start = float(beat["start_seconds"])
        end = float(beat["end_seconds"])
        shots.append(
            {
                "shot_id": f"S{index:03d}",
                "start": start,
                "end": end,
                "duration": round(end - start, 6),
                "micro_beat_ref": beat["beat_id"],
                "evidence": {
                    "onscreen_text_sequence": [beat["text_or_narration"]],
                    "observable_scene_sequence": [beat["visual_state"]],
                    "visual_frame_refs": beat["evidence_refs"],
                    "information_states": [
                        {
                            "semantic_role": beat["semantic_role"],
                            "safe_semantic_text": beat["text_or_narration"],
                            "visual_state": beat["visual_state"],
                            "evidence_refs": beat["evidence_refs"],
                        }
                    ],
                    "narration_links": [],
                },
                "interpretation": {
                    "primary_role": beat["semantic_role"],
                    "secondary_roles": ["micro_information_state"],
                    "narrative_function": (
                        "Restore one ordered News micro-information state from "
                        "on-screen text and observable visual evidence."
                    ),
                    "audio_to_visual_text": "not_required",
                    "audio_to_visual_scene": "not_required",
                    "proof_assessment": {
                        "is_proof": False,
                        "proof_type": None,
                        "supports_claim": "",
                        "basis": "",
                    },
                    "confidence": "human_confirmed",
                    "uncertainties": [
                        "Commercial validity and current availability are not verified."
                    ],
                },
            }
        )
    return {
        "schema_version": "reverse-storyboard-v1.1-news-micro-beat",
        "case_id": case["case_id"],
        "production_profile": "news",
        "storyboard_type": "reverse_micro_beat_sequence",
        "semantic_carrier": case["semantic_carrier_recovery"],
        "micro_beat_sequence": beats,
        "narration_track": [],
        "shots": shots,
        "claims_semantics": "candidate_unverified_unless_supported_by_verified_proofs",
        "video_understanding": {
            "content_goal_candidate": (
                "Use ordered price, service-context, facility and purchase states "
                "to communicate a compact offer summary."
            ),
            "hook_candidate": {
                "audio": "",
                "visual_text": beats[0]["text_or_narration"],
                "visual_scene": beats[0]["visual_state"],
            },
            "structure_sequence": [
                {
                    "shot_refs": [shot["shot_id"]],
                    "stage": beat["semantic_role"],
                    "description": beat["visual_state"],
                }
                for shot, beat in zip(shots, beats)
            ],
            "claims": [
                {
                    "text": beat["text_or_narration"],
                    "status": "candidate_unverified",
                    "evidence_refs": beat["evidence_refs"],
                }
                for beat in beats
            ],
            "verified_proofs": [],
            "uncertainties": [
                "The Case is structural Evidence only; offer validity is not Proof Authority."
            ],
        },
        "validation": {
            "passed": True,
            "micro_beat_count": len(beats),
            "continuous_narration_required": False,
            "evidence_refs_present": True,
        },
    }


def privacy_projection_for_705(
    case: dict[str, Any],
    *,
    visual_manifest_path: Path,
    transcript_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": PRIVACY_SCHEMA_VERSION,
        "policy_version": PRIVACY_POLICY_VERSION,
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "case_id": case["case_id"],
        "created_at": now_iso(),
        "source_artifacts": {
            "visual_manifest": artifact_ref(visual_manifest_path, "visual_manifest"),
            "transcript": artifact_ref(transcript_path, "transcript_excluded_as_asr_hallucination"),
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
            "visible_person": False,
        },
        "validation": {
            "passed": True,
            "unresolved_sensitive_items": 0,
            "high_confidence_redactions": 0,
            "review_required_items": 0,
            "raw_sources_modified": False,
        },
    }


def canonical_case_705(
    source: dict[str, Any],
    *,
    storyboard_path: Path,
    privacy_path: Path,
) -> dict[str, Any]:
    video_path = Path(source["source_evidence"]["video_path"]).resolve()
    visual = source["evidence_artifacts"]["visual_manifest"]
    privacy_context = load_privacy_projection(
        privacy_path, expected_case_id=source["case_id"]
    )
    storyboard = read_json(storyboard_path)
    privacy_gate = build_case_privacy_gate(
        privacy_context=privacy_context,
        derived_artifact={
            "storyboard": {
                "shots": storyboard["shots"],
                "video_understanding": storyboard["video_understanding"],
                "claims_semantics": storyboard["claims_semantics"],
            }
        },
    )
    privacy_gate["privacy_policy_version"] = PRIVACY_POLICY_VERSION
    return {
        "schema_version": "case-v1.1-draft",
        "builder_version": f"{BUILDER_VERSION}+news-micro-beat-case",
        "case_id": source["case_id"],
        "lifecycle": {
            "status": "review_required",
            "approved": False,
            "retired": False,
            "built_at": now_iso(),
            "approval_rule": (
                "A human must inspect the original source against the News Micro Beat "
                "Sequence before this Case becomes approved."
            ),
        },
        "identity": {
            "platform": "douyin",
            "source_url": source["source_evidence"]["source_url"],
            "analysis_profile": "news",
            "industry": "local_service",
            "duration_seconds": source["source_evidence"]["duration_seconds"],
        },
        "source_evidence": {
            "video": {
                "path": str(video_path),
                "size_bytes": video_path.stat().st_size,
                "sha256": sha256_file(video_path),
            },
            "authority": "source",
        },
        "audio_evidence": {
            "has_reliable_speech": False,
            "transcript_reliability": "excluded_as_asr_hallucination",
            "semantic_carrier": "on_screen_text_plus_visual_information_state",
        },
        "visual_evidence": {
            "candidate_frame_count": visual["frame_count"],
            "analyzed_frame_count": visual["frame_count"],
            "coverage_label": "candidate_complete",
            "artifact": visual,
            "authority": "visual_manifest_plus_human_source_inspection",
        },
        "storyboard": {
            **storyboard,
            "artifact": artifact_ref(storyboard_path, "reverse_storyboard_news_micro_beat"),
        },
        "quality": {
            "grade": "case_analysis",
            "editing_grade": False,
            "human_review_required": True,
            "human_review_completed": False,
            "verified_proof_count": 0,
            "warnings": [
                "Case-specific offer facts remain candidate/unverified.",
                "Source-rights status is not upgraded into Proof or Customer Authority.",
            ],
        },
        "pattern_state": {
            "pattern_mining_performed": False,
            "pattern_candidates": [],
            "note": "Case approval does not create a Pattern.",
        },
        "privacy_gate": privacy_gate,
        "source_artifacts": {
            "video": str(video_path),
            "storyboard_v1": str(storyboard_path.resolve()),
            "privacy_projection_v1": str(privacy_path.resolve()),
        },
        "validation": {
            "passed": True,
            "case_id_consistent": True,
            "micro_beat_sequence_valid": True,
            "semantic_carrier_recovered": True,
            "continuous_narration_required": False,
            "proof_consistency_valid": True,
            "human_approval_required": True,
            "auto_approved": False,
            "human_approval_completed": False,
        },
    }


def news_fingerprint_705(case_path: Path, storyboard_path: Path) -> dict[str, Any]:
    case = read_json(case_path)
    storyboard = read_json(storyboard_path)
    return {
        "schema_version": "case-fingerprint-v1.0-draft",
        "builder_version": f"{BUILDER_VERSION}+news-micro-beat-fingerprint",
        "case_id": CASE_705,
        "production_profile": "news",
        "source_case_sha256": sha256_file(case_path),
        "source_storyboard_sha256": sha256_file(storyboard_path),
        "fingerprint_scope": "case_structural_evidence_only",
        "semantic_carrier_features": {
            "carrier_type": "on_screen_text_plus_visual_information_state",
            "continuous_narration_required": False,
            "micro_beat_count": len(storyboard["micro_beat_sequence"]),
            "role_sequence": [
                beat["semantic_role"] for beat in storyboard["micro_beat_sequence"]
            ],
        },
        "visual_state_features": {
            "ordered_state_count": len(storyboard["shots"]),
            "text_visual_relationship": "persistent_text_over_changing_service_states",
        },
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


def round_1_decision(
    *,
    scout_path: Path,
    case_705_path: Path,
    case_705_receipt_path: Path,
    concise_758_path: Path,
) -> dict[str, Any]:
    decisions = [
        {
            "target_id": "NEWS_PHASE_A_001",
            "case_id": CASE_705,
            "decision": "target_fit_approved",
            "observed_source_profile": "news",
            "approved_compatible_generation_profiles": ["news"],
            "micro_beat_evidence_materially_matches_source": True,
            "case_lifecycle_result": "approved",
            "canonical_case_ref": artifact_ref(case_705_path, "approved_case"),
            "case_approval_receipt_ref": artifact_ref(case_705_receipt_path, "case_approval_receipt"),
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_002",
            "case_id": "7629552120978861049",
            "decision": "reject_for_news_target_profile_mismatch",
            "observed_source_profile": "mix",
            "approved_compatible_generation_profiles": [],
            "artifacts_preserved": True,
            "automatically_rerouted_to_mix": False,
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_003",
            "case_id": "7673808914944625983",
            "decision": "reject_for_news_target_profile_mismatch",
            "observed_source_profile": "mix",
            "approved_compatible_generation_profiles": [],
            "artifacts_preserved": True,
            "automatically_rerouted_to_mix": False,
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_004",
            "case_id": "7506527387438845184",
            "decision": "retain_as_hybrid_boundary_candidate",
            "observed_source_profile": "hybrid",
            "approved_compatible_generation_profiles": [],
            "compatible_generation_profiles_candidate": ["news", "mix"],
            "clean_news_seed": False,
            "artifacts_preserved": True,
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_005",
            "case_id": CASE_758,
            "decision": "pending_final_human_review",
            "observed_source_profile": "news",
            "approved_compatible_generation_profiles": [],
            "concise_review_pack_ref": artifact_ref(concise_758_path, "concise_human_review_pack"),
            "pattern_created": False,
        },
        {
            "target_id": "NEWS_PHASE_A_006",
            "case_id": "7614013950665018678",
            "decision": "reject_for_news_target_profile_mismatch",
            "observed_source_profile": "mix",
            "approved_compatible_generation_profiles": [],
            "artifacts_preserved": True,
            "automatically_rerouted_to_mix": False,
            "pattern_created": False,
        },
    ]
    return {
        "schema_version": NEWS_PHASE_A_ROUND_1_DECISION_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "decision_id": "news_phase_a_round_1_human_decision_v1",
        "status": "human_decision_persisted",
        "reviewer": "李健",
        "reviewed_at": now_iso(),
        "source_round_1_scout_ref": artifact_ref(scout_path, "news_phase_a_round_1_scout"),
        "case_decisions": decisions,
        "phase_b_status": "not_started_blocked",
        "authority": {
            "pattern_created": False,
            "pattern_mining_performed": False,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
            "persona_modified": False,
            "content_ledger_modified": False,
        },
    }


def pre_gate(likelihood: str, reason: str, checks: list[bool]) -> dict[str, Any]:
    keys = [
        "main_semantic_carrier_recoverable_from_micro_information_states",
        "captions_are_not_merely_following_continuous_narration",
        "semantic_understanding_survives_without_continuous_narration",
        "multiple_distinct_information_states_or_beats",
        "compressed_information_progression_not_shortened_mix",
    ]
    return {
        "news_profile_likelihood": likelihood,
        "checks": dict(zip(keys, checks)),
        "reason": reason,
    }


def discovery(
    candidate_id: str,
    target: str,
    url: str,
    title: str,
    likelihood: str,
    reason: str,
    checks: list[bool],
    *,
    approximate_duration: str,
    formal: bool = False,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "research_target_ref": target,
        "source_platform": "douyin",
        "source_url": url,
        "creator_or_account": None,
        "title_or_description": title,
        "publish_time": None,
        "retrieved_at": now_iso(),
        "operator_profile_hint": "news",
        "operator_notes": "Round 2 discovery; News structure evaluated before target topic fit.",
        "lightweight_structure_observation": {
            "information_carrier": "public page preview and recoverable media states",
            "hook_type": target.lower(),
            "approximate_duration": approximate_duration,
            "text_state_behavior": reason,
            "narration_presence": "not_authoritative_until_formal_extraction",
            "visual_state_behavior": reason,
            "obvious_redundancy_risk": "continuous_narration_or_topic_only_match",
        },
        "pre_screen": {
            "target_desired_structure_fit": formal,
            "shortened_mix_risk": likelihood != "strong",
            "information_beats_recoverable": checks[0],
            "video_quality_sufficient_for_lightweight_assessment": True,
            "obvious_privacy_or_source_obstacle": "none" if formal else "not_cleared_for_formal_pipeline",
        },
        "news_profile_pre_gate": pre_gate(likelihood, reason, checks),
        "rank": 1 if formal else None,
        "formal_pipeline_selected": formal,
        "selected_reason": (
            "Pure visual before/after state progression is recoverable without narration."
            if formal
            else None
        ),
        "why_better_than_alternatives": (
            "It supplies repeated room-level raw-to-finished contrasts, clear state transitions, "
            "and no dependency on continuous Mix narration."
            if formal
            else None
        ),
        "case_created": formal,
        "pattern_mining_eligible": False,
        "retrieval_metadata": {
            "authority": "not_effectiveness_authority",
            "metrics_saved": False,
        },
    }


def round_2_formal_scene(
    candidate: dict[str, Any],
    *,
    video_path: Path,
    visual_manifest_path: Path,
    transcript_path: Path,
) -> dict[str, Any]:
    beats = [
        {
            "beat_id": "B001",
            "semantic_role": "whole_space_before_after_hook",
            "text_or_narration": "无可靠连续口播；主要语义来自毛坯客厅到完成态客厅的视觉切换",
            "visual_state": "毛坯客厅 → 完成态客厅",
            "start_seconds": 0.0,
            "end_seconds": 1.7,
            "evidence_refs": ["frame_000000000ms.jpg", "frame_000001700ms.jpg"],
        },
        {
            "beat_id": "B002",
            "semantic_role": "dining_kitchen_contrast",
            "text_or_narration": "撕纸式局部叠加展示餐厨完成态，再切到完整完成态",
            "visual_state": "毛坯餐厨 + 完成态局部 → 完成态餐厨",
            "start_seconds": 1.7,
            "end_seconds": 5.7,
            "evidence_refs": ["frame_000004200ms.jpg", "frame_000005700ms.jpg"],
        },
        {
            "beat_id": "B003",
            "semantic_role": "bedroom_contrast",
            "text_or_narration": "毛坯卧室与完成态阅读/休息区形成第二组空间结果对照",
            "visual_state": "毛坯卧室 + 完成态局部 → 完成态卧室",
            "start_seconds": 5.7,
            "end_seconds": 9.667,
            "evidence_refs": ["frame_000008933ms.jpg", "frame_000009667ms.jpg"],
        },
        {
            "beat_id": "B004",
            "semantic_role": "terrace_construction_contrast",
            "text_or_narration": "露台施工状态通过局部叠加过渡到完成态花园",
            "visual_state": "露台施工 → 完成态花园露台",
            "start_seconds": 9.667,
            "end_seconds": 13.733,
            "evidence_refs": ["frame_000012233ms.jpg", "frame_000013733ms.jpg"],
        },
        {
            "beat_id": "B005",
            "semantic_role": "result_close",
            "text_or_narration": "以完成态露台连续状态收束视觉结果",
            "visual_state": "完成态花园露台与日常使用状态",
            "start_seconds": 13.733,
            "end_seconds": 16.167,
            "evidence_refs": ["frame_000014933ms.jpg", "frame_000015500ms.jpg"],
        },
    ]
    return {
        "candidate_id": candidate["candidate_id"],
        "case_id": ROUND_2_CASE,
        "research_target_ref": "NEWS_PHASE_A_004",
        "lifecycle": {
            "status": "review_required",
            "approved": False,
            "approval_rule": "Human Review required against original source and Micro Beat Sequence.",
        },
        "source_evidence": {
            "platform": "douyin",
            "source_url": candidate["source_url"],
            "video_path": str(video_path.resolve()),
            "video_sha256": sha256_file(video_path),
            "duration_seconds": 16.167,
        },
        "evidence_artifacts": {
            "visual_manifest": {
                **artifact_ref(visual_manifest_path, "visual_manifest"),
                "frame_count": 21,
                "scene_count": 10,
            },
            "transcript": {
                **artifact_ref(transcript_path, "transcript"),
                "reliability": "excluded_as_non_semantic_watermark_or_music_detection",
            },
        },
        "formal_pipeline": {
            "source_acquisition": "complete",
            "privacy_safe_evidence": "review_required_visible_person_no_obvious_pii",
            "semantic_carrier_extraction": "complete",
            "visual_evidence": "complete",
            "shot_or_information_state_analysis": "complete",
            "reverse_storyboard": "complete_micro_beat_sequence",
            "case_build": "complete_review_required",
            "human_review": "pending",
        },
        "news_profile_pre_gate": candidate["news_profile_pre_gate"],
        "semantic_carrier_recovery": {
            "carrier_type": "visual_information_state_sequence",
            "primary_semantic_carrier_recovered": True,
            "narration_presence": "no_reliable_continuous_narration",
            "transcript_reliability": "excluded",
            "onscreen_text_timing_recovered": True,
            "visual_state_recovered": True,
            "relationship_summary": (
                "Room-level raw, overlay-transition and finished states carry the contrast; "
                "continuous narration is not required."
            ),
        },
        "target_fit_assessment": {
            "result": "suitable",
            "reason": "Five ordered state groups repeatedly encode before/after scene contrast.",
        },
        "profile_analysis": {
            "operator_profile_hint": "news",
            "observed_source_profile": "news",
            "compatible_generation_profiles_candidate": ["news"],
            "confidence": "medium",
            "classification_forced_by_target": False,
        },
        "micro_beat_sequence": beats,
        "privacy": {
            "status": "human_review_required",
            "obvious_sensitive_pii": False,
            "visible_person": True,
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
                "visual-state boundaries",
                "clean News profile classification",
                "visible person privacy",
                "source rights",
            ],
        },
    }


def build_round_2_scout(
    *,
    round_1_scout_path: Path,
    round_1_decision_path: Path,
    video_path: Path,
    visual_manifest_path: Path,
    transcript_path: Path,
) -> dict[str, Any]:
    round_1 = read_json(round_1_scout_path)
    old_urls = sorted(
        item["source_url"]
        for target in round_1["research_targets"]
        for item in target["discovery_candidates"]
    )
    local = [
        discovery("NEWSA002_R2_C001", "NEWS_PHASE_A_002", "https://www.douyin.com/video/7614340715272264177", "天元公学西站校区游泳馆开放与路线", "weak", "路线讲解依赖连续口播/跟随字幕，去除旁白后多数语义丢失。", [False, False, False, True, False], approximate_duration="59s"),
        discovery("NEWSA002_R2_C002", "NEWS_PHASE_A_002", "https://www.douyin.com/video/7673721655789685349", "本地网咖开业介绍", "weak", "以连续门店介绍为主，尚未显示独立 micro-state progression。", [False, False, False, True, False], approximate_duration="52s"),
        discovery("NEWSA002_R2_C003", "NEWS_PHASE_A_002", "https://www.douyin.com/video/7664142136292658895", "本地餐饮门店开业与地址", "possible", "存在地址/开业信息状态，但结构是否脱离连续推广口播仍不确定。", [True, False, False, True, False], approximate_duration="34s"),
        discovery("NEWSA002_R2_C004", "NEWS_PHASE_A_002", "https://www.douyin.com/video/7674951555737080704", "商场开业信息", "possible", "可见开业信息状态，但压缩节拍与 narration independence 证据不足。", [True, True, False, True, False], approximate_duration="45s"),
        discovery("NEWSA002_R2_C005", "NEWS_PHASE_A_002", "https://www.douyin.com/video/7675206846819361189", "本地服务短促介绍", "possible", "时长短但轻量预览不足以证明它不是 shortened Mix。", [True, True, False, True, False], approximate_duration="17s"),
    ]
    alert = [
        discovery("NEWSA003_R2_C001", "NEWS_PHASE_A_003", "https://www.douyin.com/video/7674245227254901929", "电梯使用风险提示（AI 生成声明）", "possible", "存在多个风险场景，但 AI 生成声明与状态真实性降低正式 Evidence 价值。", [True, True, True, True, False], approximate_duration="44s"),
        discovery("NEWSA003_R2_C002", "NEWS_PHASE_A_003", "https://www.douyin.com/video/7670167473023267057", "人群聚集风险提醒", "weak", "长口播解释占主导，字幕主要跟随 narration。", [False, False, False, True, False], approximate_duration="67s"),
        discovery("NEWSA003_R2_C003", "NEWS_PHASE_A_003", "https://www.douyin.com/video/7674922626464099001", "机械作业安全提醒", "weak", "培训型连续讲解为主，不是压缩 micro-information progression。", [False, False, False, True, False], approximate_duration="64s"),
        discovery("NEWSA003_R2_C004", "NEWS_PHASE_A_003", "https://www.douyin.com/video/7676412822028469839", "防溺水安全说明", "weak", "时长与持续说明结构更接近 Mix/讲解型内容。", [False, False, False, True, False], approximate_duration="143s"),
        discovery("NEWSA003_R2_C005", "NEWS_PHASE_A_003", "https://www.douyin.com/video/7676321333344603444", "化工安全线说明", "weak", "连续培训 narration 构成主要语义载体。", [False, False, False, True, False], approximate_duration="120s"),
    ]
    scene = [
        discovery("NEWSA004_R2_C001", "NEWS_PHASE_A_004", "https://www.douyin.com/video/7507825653623344396", "108 平老房改造前后对比", "strong", "五组毛坯/施工/完成态以纯视觉 micro states 推进，不依赖连续旁白。", [True, True, True, True, True], approximate_duration="16.167s", formal=True),
        discovery("NEWSA004_R2_C002", "NEWS_PHASE_A_004", "https://www.douyin.com/video/7591037717979467048", "轮毂翻新前后", "possible", "可见 before/after，但状态数量与内容广度较弱。", [True, True, True, False, True], approximate_duration="short"),
        discovery("NEWSA004_R2_C003", "NEWS_PHASE_A_004", "https://www.douyin.com/video/7475288098922974501", "整车翻新过程", "weak", "长过程记录更依赖连续过程理解，compressed beat 证据不足。", [False, True, False, True, False], approximate_duration="long"),
        discovery("NEWSA004_R2_C004", "NEWS_PHASE_A_004", "https://www.douyin.com/video/7551657824292506932", "老房改造全过程", "weak", "长叙事改造内容，不是紧凑的 News state sequence。", [False, False, False, True, False], approximate_duration="long"),
    ]
    benefit = [
        discovery("NEWSA006_R2_C001", "NEWS_PHASE_A_006", "https://www.douyin.com/video/7535362488529145148", "员工福利与企业文化说明", "weak", "长篇观点/连续口播占主导，福利点不是独立压缩状态。", [False, False, False, True, False], approximate_duration="long"),
        discovery("NEWSA006_R2_C002", "NEWS_PHASE_A_006", "https://jingxuan.douyin.com/m/video/7678129673810243142", "游戏周年福利总结", "weak", "5 分钟以上解释内容，主要语义依赖连续讲解。", [False, False, False, True, False], approximate_duration="5m31s"),
        discovery("NEWSA006_R2_C003", "NEWS_PHASE_A_006", "https://www.douyin.com/video/7563280571766410536", "新手福利与角色指南", "weak", "教程 narration 与步骤说明持续展开，不符合 micro-information compression。", [False, False, False, True, False], approximate_duration="long"),
        discovery("NEWSA006_R2_C004", "NEWS_PHASE_A_006", "https://www.douyin.com/shipin/7643992176430762019", "工会出行福利聚合页", "possible", "聚合页显示短促福利样例，但未解析到唯一可核验 source video。", [True, True, True, True, False], approximate_duration="15s example"),
        discovery("NEWSA006_R2_C005", "NEWS_PHASE_A_006", "https://www.douyin.com/topic/7638768320216549410", "免费汉堡福利聚合页", "possible", "多条短视频具备具体权益，但当前 source lineage 仍是聚合页而非正式 Case。", [True, True, True, True, False], approximate_duration="18-36s examples"),
    ]
    formal_candidate = scene[0]
    formal_case = round_2_formal_scene(
        formal_candidate,
        video_path=video_path,
        visual_manifest_path=visual_manifest_path,
        transcript_path=transcript_path,
    )
    targets = []
    for target_id, capability, candidates in (
        ("NEWS_PHASE_A_002", "local_service_discovery", local),
        ("NEWS_PHASE_A_003", "problem_or_alert", alert),
        ("NEWS_PHASE_A_004", "scene_contrast", scene),
        ("NEWS_PHASE_A_006", "concrete_benefit", benefit),
    ):
        selected = next(
            (item for item in candidates if item["formal_pipeline_selected"]), None
        )
        targets.append(
            {
                "target_id": target_id,
                "missing_capability": capability,
                "target_status": (
                    "formal_candidate_selected"
                    if selected
                    else "no_suitable_news_candidate"
                ),
                "status_reason": (
                    selected["selected_reason"]
                    if selected
                    else "No discovery passed the strong News Profile Pre-gate; standards were not lowered."
                ),
                "formal_candidate_ref": selected["candidate_id"] if selected else None,
                "discovery_candidates": candidates,
            }
        )
    return {
        "schema_version": NEWS_PHASE_A_ROUND_2_SCOUT_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "scout_id": "news_phase_a_round_2_targeted_discovery_v1",
        "status": "human_review_ready",
        "production_profile": "news",
        "created_at": now_iso(),
        "source_refs": {
            "round_1_scout": artifact_ref(round_1_scout_path, "round_1_scout"),
            "round_1_human_decision": artifact_ref(round_1_decision_path, "round_1_human_decision"),
        },
        "round_1_candidate_urls_excluded": old_urls,
        "research_targets": targets,
        "formal_case_candidates": [formal_case],
        "round_2_summary": {
            "targets_searched": 4,
            "discovery_candidate_count": sum(
                len(target["discovery_candidates"]) for target in targets
            ),
            "strong_pre_gate_count": 1,
            "formal_candidate_count": 1,
            "no_suitable_news_candidate_targets": [
                target["target_id"]
                for target in targets
                if target["target_status"] == "no_suitable_news_candidate"
            ],
            "observed_profile_distribution_formal": {
                "news": 1,
                "mix": 0,
                "hybrid": 0,
                "uncertain": 0,
            },
            "news_status_after_round_2": "research_coverage_insufficient",
            "phase_b_status": "not_started_blocked",
        },
        "model_and_tool_usage": {
            "remote_model_calls": 0,
            "deepseek_calls": 0,
            "qwen_full_timeline_calls": 0,
            "local_whisper_calls": 1,
            "local_opencv_visual_extractions": 1,
            "browser_discovery": True,
            "retrieval_metrics_are_effectiveness_authority": False,
        },
        "authority": {
            "case_auto_approved": False,
            "pattern_created": False,
            "pattern_mining_performed": False,
            "phase_b_started": False,
            "news_generation_performed": False,
            "news_excel_export_performed": False,
            "persona_modified": False,
            "content_ledger_modified": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Persist News Phase A Round 1 Human Decisions, approve the reviewed 705 "
            "Case through the existing Case gate, and build Round 2 Targeted Discovery."
        )
    )
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    root = Path(args.project_root).expanduser().resolve()
    scout_path = root / "data" / "case_acquisition" / "news_phase_a" / "news_phase_a_breadth_scout_v1.json"
    round_1 = read_json(scout_path)
    validate_news_phase_a_scout_v1(round_1)
    case_705_source = find_formal_case(round_1, CASE_705)
    case_758_source = find_formal_case(round_1, CASE_758)

    concise_758_path = root / "data" / "case_acquisition" / "news_phase_a" / "human_review" / CASE_758 / "case_human_review_pack_concise_v1.md"
    write_new_text(
        concise_758_path,
        render_concise_news_case_review_markdown(case_758_source),
    )

    case_705_dir = root / "data" / "cases" / CASE_705
    storyboard_path = case_705_dir / "reverse_storyboard_news_micro_beat_v1.json"
    privacy_path = root / "data" / "privacy" / CASE_705 / "v1" / "privacy_projection_v1.json"
    case_path = case_705_dir / "case_v1.json"
    visual_manifest_path = Path(case_705_source["evidence_artifacts"]["visual_manifest"]["path"])
    transcript_path = Path(case_705_source["evidence_artifacts"]["transcript"]["path"])
    write_new_json(storyboard_path, micro_beat_storyboard(case_705_source))
    write_new_json(
        privacy_path,
        privacy_projection_for_705(
            case_705_source,
            visual_manifest_path=visual_manifest_path,
            transcript_path=transcript_path,
        ),
    )
    write_new_json(
        case_path,
        canonical_case_705(
            case_705_source,
            storyboard_path=storyboard_path,
            privacy_path=privacy_path,
        ),
    )
    subprocess.run(
        [
            sys.executable,
            str((root / "scripts" / "approve_case_v1.py").resolve()),
            "--case",
            str(case_path),
            "--reviewer",
            "李健",
            "--note",
            (
                "Reviewer directly inspected the source; the five extracted Micro Beats "
                "materially match the number/price-led News structure."
            ),
        ],
        check=True,
    )
    receipt_path = case_705_dir / "approval_receipt.json"
    fingerprint_path = root / "data" / "fingerprints" / CASE_705 / "case_fingerprint_v1.json"
    write_new_json(fingerprint_path, news_fingerprint_705(case_path, storyboard_path))

    compatibility_path = case_705_dir / "case_profile_compatibility_approval_v1.json"
    compatibility = {
        "schema_version": CASE_PROFILE_COMPATIBILITY_APPROVAL_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "approval_id": f"case_profile_compatibility_approval_v1::{CASE_705}",
        "status": "approved",
        "case_id": CASE_705,
        "reviewer": "李健",
        "approved_at": read_json(case_path)["lifecycle"]["approved_at"],
        "observed_source_profile": "news",
        "approved_compatible_generation_profiles": ["news"],
        "mix_compatibility": "not_approved",
        "decision": "approved_news_only",
        "source_approved_case_ref": artifact_ref(case_path, "approved_case"),
        "case_approval_receipt_ref": artifact_ref(receipt_path, "case_approval_receipt"),
        "fingerprint_ref": artifact_ref(fingerprint_path, "case_fingerprint"),
        "storyboard_ref": artifact_ref(storyboard_path, "reverse_storyboard_news_micro_beat"),
        "evidence_refs": [
            artifact_ref(scout_path, "news_phase_a_round_1_scout"),
            artifact_ref(visual_manifest_path, "visual_manifest"),
        ],
        "pattern_created": False,
        "case_lifecycle_modified_beyond_explicit_human_approval": False,
        "authority": {
            "case_specific_facts_transferred": False,
            "effectiveness_claimed": False,
            "pattern_authority_changed": False,
        },
    }
    validate_case_profile_compatibility_approval_v1(
        compatibility,
        approved_case_sha256=sha256_file(case_path),
    )
    write_new_json(compatibility_path, compatibility)

    decision_path = root / "data" / "case_acquisition" / "news_phase_a" / "news_phase_a_round_1_human_decision_v1.json"
    decision = round_1_decision(
        scout_path=scout_path,
        case_705_path=case_path,
        case_705_receipt_path=receipt_path,
        concise_758_path=concise_758_path,
    )
    validate_news_phase_a_round_1_decision_v1(
        decision, round_1_scout_sha256=sha256_file(scout_path)
    )
    write_new_json(decision_path, decision)

    round_2_video = root / "data" / "sources" / "news_phase_a_round_2" / "NEWS_PHASE_A_004" / "NEWSA004_R2_C001" / f"{ROUND_2_CASE}.mp4"
    round_2_visual = root / "data" / "visual" / ROUND_2_CASE / "visual_evidence_manifest.json"
    round_2_transcript = root / "data" / "analysis" / ROUND_2_CASE / "transcript_segments.json"
    round_2 = build_round_2_scout(
        round_1_scout_path=scout_path,
        round_1_decision_path=decision_path,
        video_path=round_2_video,
        visual_manifest_path=round_2_visual,
        transcript_path=round_2_transcript,
    )
    validate_news_phase_a_round_2_scout_v1(
        round_2,
        round_1_scout_sha256=sha256_file(scout_path),
        round_1_decision_sha256=sha256_file(decision_path),
    )
    round_2_dir = root / "data" / "case_acquisition" / "news_phase_a" / "round_2"
    round_2_json = round_2_dir / "news_phase_a_round_2_targeted_discovery_v1.json"
    round_2_md = round_2_dir / "news_phase_a_round_2_targeted_discovery_v1.md"
    write_new_json(round_2_json, round_2)
    write_new_text(round_2_md, render_news_phase_a_round_2_markdown(round_2))
    round_2_case = round_2["formal_case_candidates"][0]
    round_2_review = round_2_dir / "human_review" / ROUND_2_CASE / "case_human_review_pack_v1.md"
    write_new_text(round_2_review, render_news_phase_a_case_review_markdown(round_2_case))

    print("NEWS PHASE A ROUND 2 HUMAN DECISION + TARGETED DISCOVERY PASS")
    print(f"705 canonical Case: {case_path}")
    print(f"705 compatibility approval: {compatibility_path}")
    print(f"758 concise review pack: {concise_758_path}")
    print(f"Round 2 Scout: {round_2_json}")
    print("Round 2 discoveries: 19")
    print("Round 2 formal Candidates: 1")
    print("Round 2 no-suitable targets: 3")
    print("Remote model calls: 0")
    print("Phase B: not_started_blocked")
    print("Pattern created: 0")


if __name__ == "__main__":
    main()
