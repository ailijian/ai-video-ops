from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent / "authority_baseline_v1"
BUSINESS_ID = "fixture_business_001"
SPEAKER_ID = "fixture_speaker_001"
CASE_ID = "7999999999999999901"
MIX_REQUEST_ID = "fixture_mix_request_001"
NEWS_REQUEST_ID = "fixture_news_request_001"
AT = "2026-01-01T00:00:00+00:00"


def write_json(relative: str, value: dict[str, Any]) -> Path:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_text(relative: str, value: str) -> Path:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, str]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": sha256(path),
    }


def build() -> None:
    business = write_json(
        f"data/personas/{BUSINESS_ID}/revision_0001/persona_v1.json",
        {
            "schema_version": "persona-v1.0",
            "persona_id": BUSINESS_ID,
            "persona_scope": "business",
            "revision": 1,
            "identity": {"display_name": "合成测试商户", "industry": "restaurant"},
            "facts": {
                "business_name": {
                    "fact_id": "fixture_business_fact_001",
                    "state": "known",
                    "value": "合成测试商户",
                },
                "industry": {
                    "fact_id": "fixture_business_fact_002",
                    "state": "known",
                    "value": "餐饮服务",
                },
            },
            "provenance": {"content_sha256": "1" * 64, "synthetic": True},
            "approval": {"human_gate": True, "reviewer": "fixture_reviewer"},
            "lifecycle": {"status": "approved", "approved": True},
        },
    )
    write_json(
        f"data/personas/{BUSINESS_ID}/revision_0001/approval_receipt.json",
        {
            "schema_version": "persona-approval-receipt-v1.0",
            "persona_id": BUSINESS_ID,
            "revision": 1,
            "decision": "approved",
            "human_gate": True,
            "content_sha256": "1" * 64,
            "persona_sha256_after_approval": sha256(business),
            "reviewed_at": AT,
        },
    )

    speaker = write_json(
        f"data/personas/{SPEAKER_ID}/revision_0001/persona_v1.json",
        {
            "schema_version": "persona-v1.0",
            "persona_id": SPEAKER_ID,
            "persona_scope": "speaker",
            "revision": 1,
            "identity": {"display_name": "合成测试讲述者"},
            "business_persona_ref": {
                "persona_id": BUSINESS_ID,
                "revision": 1,
                "sha256": sha256(business),
                "content_sha256": "1" * 64,
                "status": "approved",
            },
            "facts": {
                "display_name": {
                    "fact_id": "fixture_speaker_fact_001",
                    "state": "known",
                    "value": "合成测试讲述者",
                }
            },
            "provenance": {"content_sha256": "2" * 64, "synthetic": True},
            "approval": {"human_gate": True, "reviewer": "fixture_reviewer"},
            "lifecycle": {"status": "approved", "approved": True},
        },
    )
    write_json(
        f"data/personas/{SPEAKER_ID}/revision_0001/approval_receipt.json",
        {
            "schema_version": "persona-approval-receipt-v1.0",
            "persona_id": SPEAKER_ID,
            "revision": 1,
            "decision": "approved",
            "human_gate": True,
            "content_sha256": "2" * 64,
            "persona_sha256_after_approval": sha256(speaker),
            "reviewed_at": AT,
        },
    )

    case = write_json(
        f"data/cases/{CASE_ID}/case_v1.json",
        {
            "schema_version": "case-v1.0",
            "case_id": CASE_ID,
            "identity": {
                "platform": "douyin",
                "source_url": f"https://www.douyin.com/video/{CASE_ID}",
                "stable_video_id": CASE_ID,
                "analysis_profile": "mix",
                "industry": "restaurant",
                "duration_seconds": 24.0,
            },
            "source_evidence": {
                "video": {
                    "path": f"data/transient/source_media/{CASE_ID}.mp4",
                    "sha256": "3" * 64,
                    "local_source_exists": False,
                }
            },
            "storyboard": {
                "video_understanding": {
                    "content_goal_candidate": "用清晰步骤解释服务价值并保留人工判断",
                    "structure_sequence": [
                        {"description": "先提出顾客关心的问题"},
                        {"description": "再展示可核验的服务步骤"},
                        {"description": "最后邀请顾客自行判断"},
                    ],
                },
                "shots": [
                    {
                        "start": 0,
                        "end": 8,
                        "evidence": {
                            "observable_scene_safe_verbatim": ["讲述者展示服务台面"],
                            "onscreen_text_safe_verbatim": ["价格以现场公示为准"],
                            "audio_overlap_safe_verbatim": "先看清服务内容再做决定",
                        },
                        "interpretation": {"narrative_function": "建立问题与范围"},
                    }
                ],
            },
            "lifecycle": {
                "status": "approved",
                "approved": True,
                "approved_at": AT,
                "human_gate": True,
            },
            "authority": {"facts_transferred": False, "media_rights_established": False},
        },
    )
    write_json(
        f"data/cases/{CASE_ID}/approval_receipt.json",
        {
            "schema_version": "case-approval-receipt-v1.0",
            "case_id": CASE_ID,
            "decision": "approved",
            "human_gate": True,
            "case_sha256": sha256(case),
            "reviewed_at": AT,
        },
    )
    write_json(
        f"data/case_governance/cases/{CASE_ID}/case_source_governance_companion_v1.json",
        {
            "schema_version": "case-source-governance-companion-v1.0",
            "case_id": CASE_ID,
            "source_url": f"https://www.douyin.com/video/{CASE_ID}",
            "stable_video_id": CASE_ID,
            "recorded_source_media_sha256": "3" * 64,
            "acquisition_lineage_valid": True,
            "media_reuse_rights": "not_established",
            "production_footage_pool_eligible": False,
            "local_source_exists": False,
        },
    )
    write_json(
        f"data/fingerprints/{CASE_ID}/case_fingerprint_v1.json",
        {
            "schema_version": "case-fingerprint-v1.0",
            "case_id": CASE_ID,
            "case_file_sha256": sha256(case),
            "structural_signature": ["question", "evidence", "human_judgment"],
            "facts_transferred": False,
        },
    )

    candidate = write_json(
        "data/patterns/candidates/fixture_pattern_candidate_001/pattern_candidate_v1.json",
        {
            "schema_version": "pattern-candidate-v1.0",
            "pattern_id": "fixture_pattern_001",
            "status": "review_required",
            "supported_case_ids": [CASE_ID],
            "effectiveness": {"status": "unvalidated", "performance_data_used": False},
            "authority": {"pattern_approved": False, "facts_transferred": False},
        },
    )
    pattern = write_json(
        "data/patterns/approved/fixture_pattern_001/pattern_v1.json",
        {
            "schema_version": "pattern-v1.0",
            "pattern_id": "fixture_pattern_001",
            "status": "approved",
            "compatible_profiles": ["mix"],
            "creative_invariants": ["问题先行", "证据可核验", "结论保留边界"],
            "scope": {"supported_case_ids": [CASE_ID], "industry": "restaurant"},
            "effectiveness": {"status": "unvalidated", "performance_data_used": False},
            "lineage": {"candidate": ref(candidate), "case_refs": [ref(case)]},
            "approval": {"human_gate": True, "reviewer": "fixture_reviewer"},
        },
    )
    write_json(
        "data/patterns/approved/fixture_pattern_001/approval_receipt.json",
        {
            "schema_version": "pattern-approval-receipt-v1.0",
            "pattern_id": "fixture_pattern_001",
            "decision": "approved",
            "human_gate": True,
            "pattern_sha256": sha256(pattern),
            "candidate_sha256": sha256(candidate),
            "reviewed_at": AT,
        },
    )
    write_json(
        "data/cross_case_research/fixture_comparison_001/cross_case_comparison_v1.json",
        {
            "schema_version": "cross-case-comparison-v1.0",
            "comparison_id": "fixture_comparison_001",
            "case_refs": [ref(case)],
            "status": "human_reviewed",
            "proof_authority": "structural_hypothesis_only",
            "facts_transferred": False,
        },
    )

    write_json(
        "data/production_profiles/production_profile_registry_v1.json",
        {
            "schema_version": "production-profile-registry-v1.0",
            "status": "approved_frozen",
            "profiles": {
                "mix": {"generation_enabled": True},
                "news": {"generation_enabled": True, "generic_novel_news_ready": False},
            },
        },
    )
    write_json(
        "data/creative_coverage/creative_coverage_report_v1.json",
        {
            "schema_version": "creative-coverage-v1.0",
            "status": "derived_no_approval_authority",
            "mix": {"available": True},
            "news": {"scene_contrast": "pending_real_customer_opportunity"},
        },
    )
    write_json(
        "data/creative_coverage/revisions/news_production_mvp_final_validation_update_v1.json",
        {
            "schema_version": "creative-coverage-update-v1.0",
            "status": "current_derived_coverage_update",
            "pattern_production_validation": {
                "pcv1_news_price_offer_led_micro_information": {"status": "passed"},
                "pcv1_news_scene_contrast": {"status": "pending"},
            },
        },
    )

    request = write_json(
        f"data/generation_requests/{MIX_REQUEST_ID}/generation_request_v1.json",
        {
            "schema_version": "generation-request-v1.0",
            "request_id": MIX_REQUEST_ID,
            "persona_id": BUSINESS_ID,
            "speaker_persona": SPEAKER_ID,
            "target_profile": "mix",
            "quantity": 1,
            "human_review_required": True,
        },
    )
    batch = write_json(
        f"data/generation_batches/{MIX_REQUEST_ID}/revisions/revision_0001/approved_generation_batch_v1.json",
        {
            "schema_version": "approved-generation-batch-v1.0",
            "request_id": MIX_REQUEST_ID,
            "profile": "mix",
            "batch_revision": 1,
            "status": "approved",
            "human_gate": True,
            "items": [
                {
                    "content_id": "fixture_mix_content_001",
                    "central_claim": "介绍透明报价的服务边界",
                    "case_media_used": False,
                }
            ],
            "lineage": {"generation_request": ref(request), "pattern": ref(pattern)},
        },
    )
    write_json(
        f"data/generation_batches/{MIX_REQUEST_ID}/revisions/revision_0001/generation_batch_approval_receipt.json",
        {
            "schema_version": "generation-batch-approval-receipt-v1.0",
            "request_id": MIX_REQUEST_ID,
            "status": "approved",
            "human_gate": True,
            "approved_batch": {"path": batch.relative_to(ROOT).as_posix(), "sha256": sha256(batch)},
            "reviewed_at": AT,
        },
    )
    mix_output = write_text(
        f"output/{MIX_REQUEST_ID}_approved_export.txt",
        "synthetic approved export; no production content\n",
    )
    write_json(
        f"output/{MIX_REQUEST_ID}_approved_export.export_receipt.json",
        {
            "schema_version": "excel-export-receipt-v1.0",
            "request_id": MIX_REQUEST_ID,
            "validation_passed": True,
            "batch_sha256": sha256(batch),
            "output_path": mix_output.relative_to(ROOT).as_posix(),
            "output_sha256": sha256(mix_output),
        },
    )
    write_json(
        f"data/export_closures/{MIX_REQUEST_ID}/export_closure_v1.json",
        {
            "schema_version": "export-closure-v1.0",
            "request_id": MIX_REQUEST_ID,
            "status": "closed",
            "approved_batch_sha256": sha256(batch),
            "human_gate_preserved": True,
            "regeneration_performed": False,
        },
    )

    news_approval = write_json(
        f"data/news_deliveries/{NEWS_REQUEST_ID}/news_delivery_human_approval_v1.json",
        {
            "schema_version": "news-delivery-human-approval-v1.0",
            "request_id": NEWS_REQUEST_ID,
            "decision": "approved",
            "human_gate": True,
            "reuse_intent": "cross_profile_repurpose",
            "semantic_novelty": False,
        },
    )
    news_output = write_text(
        f"data/news_deliveries/{NEWS_REQUEST_ID}/approved_news_export.txt",
        "synthetic cross-profile presentation; no production content\n",
    )
    news_receipt = write_json(
        f"data/news_deliveries/{NEWS_REQUEST_ID}/news_dynamic_excel_export_receipt_v1.json",
        {
            "schema_version": "news-dynamic-excel-export-receipt-v1.0",
            "request_id": NEWS_REQUEST_ID,
            "validation_passed": True,
            "reuse_intent": "cross_profile_repurpose",
            "semantic_novelty": False,
            "approved_news_delivery": ref(news_approval),
            "output_path": news_output.relative_to(ROOT).as_posix(),
            "output_sha256": sha256(news_output),
        },
    )
    write_json(
        f"data/news_deliveries/{NEWS_REQUEST_ID}/news_delivery_export_closure_v1.json",
        {
            "schema_version": "news-delivery-export-closure-v1.0",
            "request_id": NEWS_REQUEST_ID,
            "validation": {"passed": True},
            "excel_export": {"sha256": sha256(news_output)},
            "presentation_history": {
                "presentation_id": "fixture_news_presentation_001",
                "semantic_entry_count_delta": 0,
                "semantic_entries_changed": False,
            },
        },
    )

    ledger = write_json(
        f"data/content_ledgers/{BUSINESS_ID}/content_ledger_v1.json",
        {
            "schema_version": "content-ledger-v1.0",
            "business_id": BUSINESS_ID,
            "entries": [
                {
                    "content_id": "fixture_mix_content_001",
                    "batch_ref": MIX_REQUEST_ID,
                    "status": "exported",
                    "semantic_novelty": True,
                    "exported_at": AT,
                }
            ],
            "extensions": {
                "presentation_history_v1": {
                    "entries": [
                        {
                            "presentation_id": "fixture_news_presentation_001",
                            "request_id": NEWS_REQUEST_ID,
                            "business_id": BUSINESS_ID,
                            "production_profile": "news",
                            "status": "exported",
                            "reuse_intent": "cross_profile_repurpose",
                            "semantic_novelty": False,
                            "communicated_information_units_created": False,
                            "new_semantic_content_count_delta": 0,
                            "new_central_claim_count_delta": 0,
                            "new_information_gain_delta": 0,
                            "approval_ref": ref(news_approval),
                            "export_ref": ref(news_output),
                            "exported_at": AT,
                        }
                    ]
                }
            },
            "validation": {"entry_count": 1, "append_only": True},
            "updated_at": AT,
        },
    )

    source_capacity = write_json(
        f"data/content_plans/{MIX_REQUEST_ID}/content_capacity_recalculation_v1.json",
        {
            "schema_version": "content-capacity-recalculation-v1.0",
            "business_id": BUSINESS_ID,
            "speaker_id": SPEAKER_ID,
            "capacity": 7,
            "lineage": {
                "business_persona_revision": 1,
                "business_persona_content_sha256": "1" * 64,
                "speaker_persona_revision": 1,
                "speaker_persona_content_sha256": "2" * 64,
            },
        },
    )
    write_json(
        f"data/content_plans/{MIX_REQUEST_ID}/post_export_remaining_capacity_v1.json",
        {
            "schema_version": "post-export-remaining-capacity-v1.0",
            "business_id": BUSINESS_ID,
            "post_export_remaining_capacity": 7,
            "capacity_status": "capacity_limited",
            "padding": False,
            "lineage": {
                "approved_batch": {"file_sha256": sha256(batch)},
                "content_ledger_after": {"file_sha256": sha256(ledger)},
                "source_capacity_recalculation": ref(source_capacity),
            },
        },
    )

    footage_root = f"data/production_footage/{MIX_REQUEST_ID}"
    write_json(
        f"{footage_root}/production_footage_planning_summary_v1.json",
        {
            "request_id": MIX_REQUEST_ID,
            "customer_capture_pack_status": "ready_to_send",
            "customer_capture_pack_sent": False,
            "validation": {"human_approval_persisted": True, "passed": True},
        },
    )
    write_json(
        f"{footage_root}/production_footage_planning_human_approval_v1.json",
        {"request_id": MIX_REQUEST_ID, "decision": "approved_for_planning", "human_gate": True},
    )
    write_json(
        f"{footage_root}/shot_requirement_plan_v1.json",
        {
            "request_id": MIX_REQUEST_ID,
            "lineage": {"approved_batch_file_sha256": sha256(batch)},
            "requirements": [],
        },
    )
    write_json(
        f"{footage_root}/customer_capture_missions_v1.json",
        {"request_id": MIX_REQUEST_ID, "mission_count": 1, "missions": []},
    )
    write_json(
        f"{footage_root}/production_asset_inventory_v1.json",
        {"business_id": BUSINESS_ID, "asset_count": 0, "eligible_asset_count": 0, "assets": []},
    )
    write_json(
        f"{footage_root}/storyboard_coverage_v1.json",
        {
            "request_id": MIX_REQUEST_ID,
            "summary": {"covered": 0, "partially_covered": 0, "capture_required": 1, "blocked": 0, "content_count": 1},
        },
    )
    write_json(
        f"{footage_root}/subject_media_use_confirmation_v1.json",
        {"business_id": BUSINESS_ID, "subject_ref": SPEAKER_ID, "status": "review_required"},
    )

    write_json(
        f"data/operations/{BUSINESS_ID}/operational_controls_v1.json",
        {
            "schema_version": "operational-controls-v1",
            "business_id": BUSINESS_ID,
            "operational_hold": {
                "active": True,
                "reason": "synthetic fixture requires explicit operator release",
                "set_by": "fixture_operator",
                "set_at": AT,
                "release_requires": "explicit_operator_release",
            },
            "updated_at": AT,
            "last_action": "set_hold",
            "last_actor": "fixture_operator",
            "history": [
                {"action": "set_hold", "actor": "fixture_operator", "at": AT, "reason": "synthetic fixture requires explicit operator release"}
            ],
        },
    )

    files = sorted(
        path for path in ROOT.rglob("*") if path.is_file() and path.name not in {"README.md", "fixture_manifest_v1.json"}
    )
    write_json(
        "fixture_manifest_v1.json",
        {
            "schema_version": "synthetic-authority-fixture-manifest-v1.0",
            "synthetic": True,
            "contains_production_truth": False,
            "identities": {
                "business_id": BUSINESS_ID,
                "speaker_id": SPEAKER_ID,
                "case_id": CASE_ID,
                "mix_request_id": MIX_REQUEST_ID,
                "news_request_id": NEWS_REQUEST_ID,
            },
            "files": [
                {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
                for path in files
            ],
        },
    )


if __name__ == "__main__":
    build()
