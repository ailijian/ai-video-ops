from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from production_profile_v1 import (  # noqa: E402
    audit_case_profile_compatibility_v1,
    build_case_acquisition_plan_amendment_v1,
    build_case_acquisition_plan_v1,
    build_creative_coverage_report_v1,
    build_profile_compatibility_approval_v1,
    build_production_profile_registry_v1,
    case_is_eligible_for_production_footage,
    validate_case_acquisition_plan_amendment_v1,
    validate_case_profile_compatibility_approval_v1,
    validate_case_profile_structural_decision_v1,
    validate_case_source_governance_audit_v1,
    validate_case_source_governance_companion_v1,
    validate_case_source_governance_policy_v1,
    validate_news_cross_case_research_bundle_v1,
    validate_news_creative_coverage_update_v1,
    validate_news_phase_a_closure_v1,
    validate_news_phase_a_round_1_decision_v1,
    validate_news_phase_a_round_2_scout_v1,
    validate_news_phase_a_scout_v1,
    validate_news_phase_b_depth_build_plan_v1,
    validate_news_phase_b_human_review_closure_v1,
    validate_news_phase_b_round_1_scout_v1,
    validate_news_profile_pre_gate,
    validate_profile_compatibility_approval_v1,
    validate_registry,
    validate_target_profile,
)
from match_generation_sources_v1 import build_source_plan  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductionProfileV1Tests(unittest.TestCase):
    CASE_IDS = (
        "7680512578585870322",
        "7683027343636542565",
        "7650056203686530319",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.mix_template = ROOT / "output" / "素材混剪&数字人口播混剪文案导入模板.xlsx"
        cls.news_template = ROOT / "output" / "新闻体视频制作文案导入模板.xlsx"
        cls.pattern_path = (
            ROOT
            / "data"
            / "patterns"
            / "approved"
            / "pcv1_narration_led_process_projection"
            / "pattern_v1.json"
        )
        cls.pattern_approval = cls.pattern_path.parent / "approval_receipt.json"
        cls.source_plan = (
            ROOT
            / "data"
            / "production_plans"
            / "real_shufang_mix_001"
            / "generation_source_plan_v1.json"
        )
        cls.registry_path = (
            ROOT
            / "data"
            / "production_profiles"
            / "production_profile_registry_v1.json"
        )
        cls.coverage_report_path = (
            ROOT
            / "data"
            / "creative_coverage"
            / "creative_coverage_report_v1.json"
        )
        cls.compatibility_approval_path = (
            ROOT
            / "data"
            / "production_profiles"
            / "approvals"
            / "production_profile_compatibility_approval_v1.json"
        )
        cls.acquisition_plan_path = (
            ROOT
            / "data"
            / "case_acquisition"
            / "case_acquisition_plan_v1.json"
        )
        cls.acquisition_plan_amendment_path = (
            ROOT
            / "data"
            / "case_acquisition"
            / "amendments"
            / "case_acquisition_plan_v1_amendment_0001.json"
        )
        cls.news_phase_a_scout_path = (
            ROOT
            / "data"
            / "case_acquisition"
            / "news_phase_a"
            / "news_phase_a_breadth_scout_v1.json"
        )
        cls.news_phase_a_round_1_decision_path = (
            cls.news_phase_a_scout_path.parent
            / "news_phase_a_round_1_human_decision_v1.json"
        )
        cls.news_phase_a_round_2_path = (
            cls.news_phase_a_scout_path.parent
            / "round_2"
            / "news_phase_a_round_2_targeted_discovery_v1.json"
        )
        cls.news_case_705_path = ROOT / "data" / "cases" / "7059858129298803968" / "case_v1.json"
        cls.news_case_705_compatibility_path = (
            cls.news_case_705_path.parent
            / "case_profile_compatibility_approval_v1.json"
        )
        cls.news_case_758_path = ROOT / "data" / "cases" / "7582922932108774691" / "case_v1.json"
        cls.news_case_758_compatibility_path = (
            cls.news_case_758_path.parent / "case_profile_compatibility_approval_v1.json"
        )
        cls.news_case_750_path = ROOT / "data" / "cases" / "7507825653623344396" / "case_v1.json"
        cls.news_case_750_structural_decision_path = (
            cls.news_case_750_path.parent / "case_profile_structural_decision_v1.json"
        )
        cls.news_phase_a_closure_path = (
            cls.news_phase_a_scout_path.parent / "closure" / "news_phase_a_final_closure_v1.json"
        )
        cls.news_coverage_update_path = (
            ROOT / "data" / "creative_coverage" / "revisions"
            / "news_phase_a_closure_creative_coverage_update_v1.json"
        )
        cls.news_phase_b_plan_path = (
            ROOT / "data" / "case_acquisition" / "news_phase_b"
            / "news_phase_b_depth_build_plan_v1.json"
        )
        cls.news_phase_b_scout_path = (
            cls.news_phase_b_plan_path.parent / "round_1" / "news_phase_b_round_1_scout_v1.json"
        )
        cls.news_phase_b_review_closure_path = (
            cls.news_phase_b_scout_path.parent
            / "human_review_closure"
            / "news_phase_b_round_1_human_review_closure_v1.json"
        )
        cls.case_source_governance_audit_path = (
            ROOT / "data" / "case_governance" / "case_source_governance_audit_v1.json"
        )
        cls.case_source_governance_policy_path = (
            ROOT / "data" / "case_governance" / "case_source_governance_policy_v1.json"
        )
        cls.case_source_governance_companion_root = (
            ROOT / "data" / "case_governance" / "cases"
        )
        cls.price_cross_case_bundle_path = (
            ROOT
            / "data"
            / "cross_case_research"
            / "news"
            / "price_offer_led_micro_information"
            / "research_input_bundle_v1.json"
        )
        cls.scene_cross_case_bundle_path = (
            ROOT
            / "data"
            / "cross_case_research"
            / "news"
            / "scene_contrast"
            / "research_input_bundle_v1.json"
        )
        cls.news_phase_b_review_closure_path = (
            cls.news_phase_b_scout_path.parent
            / "human_review_closure"
            / "news_phase_b_round_1_human_review_closure_v1.json"
        )
        cls.case_source_governance_audit_path = (
            ROOT / "data" / "case_governance" / "case_source_governance_audit_v1.json"
        )
        cls.registry = build_production_profile_registry_v1(
            mix_template_path=cls.mix_template,
            news_template_path=cls.news_template,
            approved_pattern_path=cls.pattern_path,
            pattern_approval_receipt_path=cls.pattern_approval,
            real_mix_source_plan_path=cls.source_plan,
            created_at="2026-09-11T00:00:00+00:00",
        )
        cls.assessments = []
        frozen_case_ids = set(cls.CASE_IDS)
        for case_id in cls.CASE_IDS:
            case_root = ROOT / "data" / "cases" / case_id
            cls.assessments.append(
                audit_case_profile_compatibility_v1(
                    case_path=case_root / "case_v1.json",
                    case_approval_receipt_path=case_root / "approval_receipt.json",
                    fingerprint_path=(
                        ROOT
                        / "data"
                        / "fingerprints"
                        / case_id
                        / "case_fingerprint_v1.json"
                    ),
                    storyboard_path=(
                        ROOT
                        / "data"
                        / "storyboards"
                        / case_id
                        / "v1"
                        / "reverse_storyboard_v1.json"
                    ),
                    legacy_mix_case_ids=frozen_case_ids,
                )
            )
        cls.report = build_creative_coverage_report_v1(
            registry=cls.registry,
            registry_ref={
                "path": "fixture/production_profile_registry_v1.json",
                "sha256": "registry-sha",
                "schema_version": cls.registry["schema_version"],
                "status": cls.registry["status"],
            },
            case_assessments=cls.assessments,
            created_at="2026-09-11T00:00:00+00:00",
        )

    def test_registry_registers_news_and_mix_only(self) -> None:
        validate_registry(self.registry)
        self.assertEqual(set(self.registry["profiles"]), {"news", "mix"})
        self.assertEqual(self.registry["profiles"]["mix"]["status"], "production_ready")
        self.assertEqual(
            self.registry["profiles"]["news"]["status"],
            "research_coverage_insufficient",
        )

    def test_hybrid_and_unknown_cannot_be_generation_targets(self) -> None:
        with self.assertRaises(ValueError):
            validate_target_profile(self.registry, "hybrid")
        with self.assertRaises(ValueError):
            validate_target_profile(self.registry, "uncertain")
        with self.assertRaises(ValueError):
            validate_target_profile(self.registry, "other")

    def test_registry_preserves_current_excel_contracts(self) -> None:
        mix = self.registry["profiles"]["mix"]["export_contract"]
        news = self.registry["profiles"]["news"]["export_contract"]
        self.assertEqual(mix["headers"], ["视频制作标题", "视频制作口播内容"])
        self.assertEqual(news["headers"], [f"标题{index}" for index in range(1, 7)])
        self.assertEqual(mix["template_sha256"], sha256(self.mix_template))
        self.assertEqual(news["template_sha256"], sha256(self.news_template))
        self.assertTrue(
            news["six_columns_are_current_implementation_not_frozen_semantics"]
        )

    def test_pattern_is_canonically_mix_compatible_not_news_compatible(self) -> None:
        record = self.registry["pattern_compatibility_records"][0]
        self.assertEqual(record["compatible_profiles"], ["mix"])
        self.assertFalse(record["news_compatible"])
        self.assertEqual(record["approved_pattern_sha256"], sha256(self.pattern_path))
        self.assertFalse(record["approved_pattern_artifact_modified"])
        self.assertEqual(record["effectiveness_status"], "unvalidated")

    def test_operator_hint_is_not_case_compatibility_authority(self) -> None:
        for assessment in self.assessments:
            self.assertIsNone(assessment["operator_profile_hint"])
            self.assertEqual(
                assessment["operator_profile_hint_status"], "missing_unknown"
            )
            self.assertFalse(
                assessment["authority"]["operator_hint_used_as_eligibility"]
            )

    def test_observed_profile_does_not_auto_approve_generation_compatibility(self) -> None:
        for assessment in self.assessments:
            self.assertEqual(assessment["observed_source_profile"], "mix")
            self.assertEqual(
                assessment["compatible_generation_profiles_candidate"], ["mix"]
            )
            self.assertEqual(assessment["approved_compatible_generation_profiles"], [])
            self.assertEqual(assessment["review_status"], "review_required")

    def test_case_assessment_has_structural_evidence_and_sha_lineage(self) -> None:
        for assessment in self.assessments:
            evidence = assessment["structural_evidence_summary"]
            self.assertEqual(evidence["narration_dominance"]["assessment"], "dominant")
            self.assertTrue(evidence["visual_projection"]["many_to_many"])
            self.assertFalse(
                evidence["text_beat_structure"]["micro_information_beats_dominate"]
            )
            for source in ("approved_case", "fingerprint", "storyboard"):
                self.assertEqual(len(assessment["lineage"][source]["sha256"]), 64)
            self.assertFalse(
                assessment["lineage"]["approved_case"]["modified_by_backfill"]
            )

    def test_approved_case_hashes_are_unchanged(self) -> None:
        expected = {
            "7680512578585870322": "30e102808d5e198e18ba8176523472b5271ba3789403ab97e7e873daf4c415f1",
            "7683027343636542565": "3e4d117edd67c7b73022e05fdb880ade205e1ab5a5d4509aefd52d1c65ee78a3",
            "7650056203686530319": "0d43b2536057fba7c8a1e9a802c8870042f97b001eee85a0b776b64a85d53814",
        }
        for case_id, digest in expected.items():
            self.assertEqual(
                sha256(ROOT / "data" / "cases" / case_id / "case_v1.json"),
                digest,
            )

    def test_human_approval_persists_three_canonical_mix_case_decisions(self) -> None:
        approval = json.loads(
            self.compatibility_approval_path.read_text(encoding="utf-8")
        )
        validate_profile_compatibility_approval_v1(
            approval,
            registry_sha256=sha256(self.registry_path),
            coverage_report_sha256=sha256(self.coverage_report_path),
        )
        self.assertEqual(approval["reviewer"], "李健")
        decisions = approval["case_profile_compatibility_approvals"]
        self.assertEqual({item["case_id"] for item in decisions}, set(self.CASE_IDS))
        self.assertTrue(
            all(
                item["approved_compatible_generation_profiles"] == ["mix"]
                and item["news_compatibility"] == "not_approved"
                and item["decision"] == "approved_mix_only"
                for item in decisions
            )
        )

    def test_pattern_human_compatibility_persists_mix_only(self) -> None:
        approval = json.loads(
            self.compatibility_approval_path.read_text(encoding="utf-8")
        )
        pattern = approval["pattern_profile_compatibility_approval"]
        self.assertEqual(pattern["compatible_profiles"], ["mix"])
        self.assertEqual(pattern["news_compatibility"], "not_approved")
        self.assertEqual(pattern["effectiveness"], "unvalidated")
        self.assertEqual(pattern["approved_pattern_ref"]["sha256"], sha256(self.pattern_path))

    def test_similar_cases_add_evidence_depth_not_creative_breadth(self) -> None:
        breadth = self.report["profiles"]["mix"]["creative_breadth"]
        self.assertEqual(breadth["evidence_depth_case_count"], 3)
        self.assertEqual(breadth["structural_family_count"], 1)
        self.assertTrue(breadth["case_count_is_not_creative_breadth"])

    def test_coverage_report_has_no_approval_authority(self) -> None:
        authority = self.report["authority"]
        self.assertFalse(authority["can_approve_case"])
        self.assertFalse(authority["can_approve_pattern"])
        self.assertFalse(authority["can_change_compatibility"])
        self.assertFalse(authority["can_claim_effectiveness"])
        self.assertFalse(authority["case_facts_used_as_customer_authority"])

    def test_coverage_gaps_are_research_targets_not_patterns(self) -> None:
        gaps = self.report["case_acquisition_gaps"]
        self.assertTrue(any(item["target_profile"] == "news" for item in gaps))
        self.assertTrue(any(item["target_profile"] == "mix" for item in gaps))
        self.assertTrue(
            all(item["artifact_type"] == "research_target_not_pattern" for item in gaps)
        )
        self.assertEqual(
            self.report["profiles"]["news"]["approved_compatible_patterns"], []
        )

    def canonical_match(
        self,
        target_profile: str,
        *,
        preserve_historical_request: bool = False,
        use_compatibility_approval: bool = True,
    ) -> dict:
        persona_path = (
            ROOT
            / "data"
            / "personas"
            / "shufang_zhiyuan_community_canteen"
            / "revision_0001"
            / "persona_v1.json"
        )
        speaker_path = (
            ROOT
            / "data"
            / "personas"
            / "lin_dongfang_frontline_chef"
            / "revision_0001"
            / "persona_v1.json"
        )
        source_request = json.loads(
            (
                ROOT
                / "data"
                / "generation_requests"
                / "real_shufang_mix_001"
                / "generation_request_v1.json"
            ).read_text(encoding="utf-8")
        )
        if not preserve_historical_request:
            source_request["request_id"] = f"profile_{target_profile}_validation"
            source_request["profile"] = target_profile
            source_request["target_profile"] = target_profile
        case_paths = [
            ROOT / "data" / "cases" / case_id / "case_v1.json"
            for case_id in self.CASE_IDS
        ]
        fingerprint_paths = [
            ROOT / "data" / "fingerprints" / case_id / "case_fingerprint_v1.json"
            for case_id in self.CASE_IDS
        ]
        if preserve_historical_request:
            request_path = (
                ROOT
                / "data"
                / "generation_requests"
                / "real_shufang_mix_001"
                / "generation_request_v1.json"
            )
            return build_source_plan(
                persona_path,
                request_path,
                [self.pattern_path],
                case_paths,
                fingerprint_paths,
                speaker_persona_path=speaker_path,
                profile_registry_path=(
                    ROOT
                    / "data"
                    / "production_profiles"
                    / "production_profile_registry_v1.json"
                ),
                creative_coverage_report_path=(
                    ROOT
                    / "data"
                    / "creative_coverage"
                    / "creative_coverage_report_v1.json"
                ),
                profile_compatibility_approval_path=(
                    self.compatibility_approval_path
                    if use_compatibility_approval
                    else None
                ),
            )
        with tempfile.TemporaryDirectory() as temporary:
            request_path = Path(temporary) / "request.json"
            request_path.write_text(
                json.dumps(source_request, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return build_source_plan(
                persona_path,
                request_path,
                [self.pattern_path],
                case_paths,
                fingerprint_paths,
                speaker_persona_path=speaker_path,
                profile_registry_path=(
                    ROOT
                    / "data"
                    / "production_profiles"
                    / "production_profile_registry_v1.json"
                ),
                creative_coverage_report_path=(
                    ROOT
                    / "data"
                    / "creative_coverage"
                    / "creative_coverage_report_v1.json"
                ),
                profile_compatibility_approval_path=(
                    self.compatibility_approval_path
                    if use_compatibility_approval
                    else None
                ),
            )

    def test_profile_aware_mix_matching_preserves_real_production_foundation(self) -> None:
        plan = self.canonical_match(
            "mix",
            preserve_historical_request=True,
            use_compatibility_approval=False,
        )
        self.assertEqual(plan["coverage"]["status"], "supported")
        self.assertEqual(plan["request"]["target_profile"], "mix")
        self.assertEqual(
            [item["pattern_id"] for item in plan["selected_patterns"]],
            ["pcv1_narration_led_process_projection"],
        )
        self.assertEqual(len(plan["selected_cases"]), 3)
        self.assertEqual(
            plan["coverage"]["canonical_approved_compatible_case_count"], 0
        )
        self.assertEqual(
            plan["coverage"]["legacy_current_truth_bridge_case_count"], 3
        )
        self.assertTrue(
            all(
                item["profile_compatibility_basis"]
                == "legacy_current_truth_bridge"
                for item in plan["selected_cases"]
            )
        )
        self.assertFalse(
            plan["validation"]["operator_profile_hint_used_for_eligibility"]
        )
        self.assertTrue(
            plan["coverage"]["legacy_bridge_scoped_to_historical_request_sha"]
        )

    def test_new_mix_request_cannot_use_unreviewed_legacy_case_compatibility(self) -> None:
        plan = self.canonical_match("mix", use_compatibility_approval=False)
        self.assertEqual(plan["coverage"]["code"], "research_coverage_insufficient")
        self.assertEqual(plan["coverage"]["canonical_approved_compatible_case_count"], 0)
        self.assertEqual(plan["coverage"]["legacy_current_truth_bridge_case_count"], 0)
        self.assertEqual(plan["selected_cases"], [])

    def test_new_mix_request_uses_three_canonical_approved_cases(self) -> None:
        plan = self.canonical_match("mix", use_compatibility_approval=True)
        self.assertEqual(plan["coverage"]["status"], "supported")
        self.assertEqual(plan["coverage"]["canonical_approved_compatible_case_count"], 3)
        self.assertEqual(plan["coverage"]["legacy_current_truth_bridge_case_count"], 0)
        self.assertEqual(len(plan["selected_cases"]), 3)
        self.assertTrue(
            all(
                item["profile_compatibility_basis"]
                == "approved_profile_compatibility"
                for item in plan["selected_cases"]
            )
        )

    def test_profile_aware_news_matching_fails_without_mix_fallback(self) -> None:
        plan = self.canonical_match("news", use_compatibility_approval=True)
        self.assertEqual(
            plan["coverage"]["code"], "research_coverage_insufficient"
        )
        self.assertEqual(plan["selected_patterns"], [])
        self.assertEqual(plan["selected_cases"], [])
        self.assertTrue(plan["validation"]["news_does_not_fallback_to_mix"])
        self.assertIn("approved_news_pattern", plan["coverage"]["missing_creative_coverage"])

    def test_profile_matching_does_not_transfer_case_facts(self) -> None:
        plan = self.canonical_match("mix", use_compatibility_approval=True)
        self.assertTrue(plan["generation_constraints"]["case_facts_must_not_transfer"])
        self.assertFalse(plan["authority"]["case_facts_used_as_persona_facts"])
        self.assertFalse(plan["validation"]["observed_source_profile_used_as_approval"])

    def test_coverage_report_is_unchanged_and_approved_by_companion_receipt(self) -> None:
        self.assertEqual(
            sha256(self.coverage_report_path),
            "442e25a78ee1641f24796893490f14480ff88a3453630cc44883725128f76b9a",
        )
        approval = json.loads(
            self.compatibility_approval_path.read_text(encoding="utf-8")
        )
        baseline = approval["creative_coverage_baseline_approval"]
        self.assertEqual(baseline["effective_review_status"], "approved")
        self.assertFalse(baseline["source_report_ref"]["source_report_modified"])
        self.assertFalse(
            baseline["coverage_report_granted_case_or_pattern_authority"]
        )

    def test_acquisition_plan_separates_news_phase_a_and_phase_b(self) -> None:
        plan = json.loads(self.acquisition_plan_path.read_text(encoding="utf-8"))
        phase_a = plan["news_phase_a_breadth_scout"]
        phase_b = plan["news_phase_b_depth_build"]
        self.assertEqual(len(phase_a["research_targets"]), 6)
        self.assertFalse(phase_a["execution_authorized"])
        self.assertEqual(phase_b["status"], "not_started_blocked")
        self.assertFalse(phase_b["execution_authorized"])
        self.assertIn("Human Review", " ".join(phase_b["trigger_rule"]["required"]))

    def test_acquisition_targets_are_not_patterns_and_no_acquisition_executed(self) -> None:
        plan = json.loads(self.acquisition_plan_path.read_text(encoding="utf-8"))
        targets = (
            plan["news_phase_a_breadth_scout"]["research_targets"]
            + plan["mix_gap_plan"]["research_targets"]
        )
        self.assertTrue(
            all(item["artifact_type"] == "research_target_not_pattern" for item in targets)
        )
        self.assertTrue(all(item["planned_case_candidate_count"] == 1 for item in targets))
        authority = plan["authority"]
        self.assertFalse(authority["research_targets_are_patterns"])
        self.assertFalse(authority["case_created"])
        self.assertFalse(authority["video_search_performed"])
        self.assertFalse(authority["video_download_performed"])
        self.assertFalse(authority["pattern_mining_performed"])
        self.assertFalse(authority["remote_model_called"])

    def test_acquisition_plan_has_lower_priority_mix_gap_targets(self) -> None:
        plan = json.loads(self.acquisition_plan_path.read_text(encoding="utf-8"))
        self.assertEqual(plan["profile_priority"], ["news", "mix"])
        targets = plan["mix_gap_plan"]["research_targets"]
        self.assertEqual(len(targets), 7)
        self.assertTrue(
            all("after_news" in item["acquisition_priority"] for item in targets)
        )
        self.assertIn(
            "generic narration plus process visuals",
            plan["mix_gap_plan"]["redundancy_exclusion"],
        )

    def test_news_evidence_amendment_is_reference_first_and_allows_text_only(self) -> None:
        self.assertEqual(
            sha256(self.acquisition_plan_path),
            "13c6311a574f866a611ab812dcfffce888e29a1eb8fa436e99be64bbbd6cddb5",
        )
        amendment = json.loads(
            self.acquisition_plan_amendment_path.read_text(encoding="utf-8")
        )
        validate_case_acquisition_plan_amendment_v1(
            amendment,
            plan_sha256=sha256(self.acquisition_plan_path),
        )
        requirement = amendment["effective_news_minimum_evidence_requirement"]
        self.assertTrue(requirement["pure_onscreen_text_case_allowed"])
        self.assertFalse(
            requirement["transcript_required_when_no_spoken_narration"]
        )
        self.assertIn("on_screen_text", requirement["allowed_semantic_carriers"])
        self.assertTrue(amendment["other_plan_content_unchanged"])

    def test_news_evidence_amendment_builder_rejects_unauthorized_reviewer(self) -> None:
        with self.assertRaises(ValueError):
            build_case_acquisition_plan_amendment_v1(
                plan_path=self.acquisition_plan_path,
                reviewer="not_the_human_reviewer",
            )

    def test_phase_a_scout_has_three_to_five_candidates_per_target(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        validate_news_phase_a_scout_v1(
            scout,
            plan_sha256=sha256(self.acquisition_plan_path),
            amendment_sha256=sha256(self.acquisition_plan_amendment_path),
        )
        self.assertEqual(len(scout["research_targets"]), 6)
        counts = [
            len(target["discovery_candidates"])
            for target in scout["research_targets"]
        ]
        self.assertTrue(all(3 <= count <= 5 for count in counts))
        self.assertEqual(sum(counts), 25)

    def test_phase_a_selects_only_rank_one_and_unselected_never_create_cases(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        selected = []
        for target in scout["research_targets"]:
            formal = [
                item
                for item in target["discovery_candidates"]
                if item["formal_pipeline_selected"]
            ]
            self.assertEqual(len(formal), 1)
            self.assertEqual(formal[0]["rank"], 1)
            self.assertTrue(formal[0]["selected_reason"])
            self.assertTrue(formal[0]["why_better_than_alternatives"])
            selected.extend(formal)
            for item in target["discovery_candidates"]:
                if not item["formal_pipeline_selected"]:
                    self.assertFalse(item["case_created"])
                    self.assertFalse(item["pattern_mining_eligible"])
        self.assertEqual(len(selected), 6)
        self.assertEqual(len(scout["formal_case_candidates"]), 6)

    def test_retrieval_metrics_are_never_effectiveness_authority(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        with_metrics = [
            item
            for target in scout["research_targets"]
            for item in target["discovery_candidates"]
            if item.get("retrieval_metadata")
        ]
        self.assertTrue(with_metrics)
        self.assertTrue(
            all(
                item["retrieval_metadata"]["authority"]
                == "not_effectiveness_authority"
                for item in with_metrics
            )
        )
        self.assertFalse(
            scout["model_and_tool_usage"][
                "retrieval_metrics_are_effectiveness_authority"
            ]
        )

    def test_profile_analysis_is_evidence_based_not_forced_by_news_target(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        cases = scout["formal_case_candidates"]
        distribution = {}
        for case in cases:
            profile = case["profile_analysis"]
            self.assertFalse(profile["classification_forced_by_target"])
            distribution[profile["observed_source_profile"]] = (
                distribution.get(profile["observed_source_profile"], 0) + 1
            )
        self.assertEqual(distribution, {"news": 2, "mix": 3, "hybrid": 1})
        self.assertEqual(
            scout["phase_a_summary"]["observed_profile_distribution"],
            {"news": 2, "hybrid": 1, "mix": 3, "uncertain": 0},
        )

    def test_news_micro_beat_extraction_accepts_no_narration_semantic_carrier(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        text_only = next(
            case
            for case in scout["formal_case_candidates"]
            if case["case_id"] == "7059858129298803968"
        )
        carrier = text_only["semantic_carrier_recovery"]
        self.assertEqual(
            carrier["carrier_type"], "on_screen_text_plus_visual_information_state"
        )
        self.assertTrue(carrier["primary_semantic_carrier_recovered"])
        self.assertEqual(carrier["transcript_reliability"], "excluded_as_asr_hallucination")
        self.assertTrue(text_only["micro_beat_sequence"])

    def test_formal_candidates_stop_at_human_review_and_preserve_authority(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        for case in scout["formal_case_candidates"]:
            self.assertEqual(case["lifecycle"]["status"], "review_required")
            self.assertFalse(case["lifecycle"]["approved"])
            self.assertFalse(case["pattern_state"]["pattern_mining_performed"])
            self.assertFalse(case["authority"]["case_specific_facts_transferred"])
            self.assertFalse(case["authority"]["persona_modified"])
            self.assertFalse(case["authority"]["content_ledger_modified"])
            self.assertTrue(Path(case["source_evidence"]["video_path"]).is_file())
            self.assertEqual(
                sha256(Path(case["source_evidence"]["video_path"])),
                case["source_evidence"]["video_sha256"],
            )
        authority = scout["authority"]
        self.assertFalse(authority["case_auto_approved"])
        self.assertFalse(authority["pattern_created"])
        self.assertFalse(authority["phase_b_started"])
        self.assertFalse(authority["mix_acquisition_started"])

    def test_scout_uses_no_remote_models_and_keeps_news_insufficient(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        usage = scout["model_and_tool_usage"]
        self.assertEqual(usage["remote_model_calls"], 0)
        self.assertEqual(usage["deepseek_calls"], 0)
        self.assertEqual(usage["candidate_planning_model_calls"], 0)
        self.assertEqual(
            scout["phase_a_summary"]["news_status_after_scout"],
            "research_coverage_insufficient",
        )
        self.assertEqual(
            scout["phase_a_summary"]["phase_b_status"], "not_started_blocked"
        )

    def test_six_case_human_review_packs_exist(self) -> None:
        scout = json.loads(self.news_phase_a_scout_path.read_text(encoding="utf-8"))
        for case in scout["formal_case_candidates"]:
            path = (
                self.news_phase_a_scout_path.parent
                / "human_review"
                / case["case_id"]
                / "case_human_review_pack_v1.md"
            )
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Review Required / Not Approved", text)
            self.assertIn("Micro Beat Sequence", text)

    def test_round_1_human_decisions_are_persisted_without_rerouting_or_pattern(self) -> None:
        decision = json.loads(
            self.news_phase_a_round_1_decision_path.read_text(encoding="utf-8")
        )
        validate_news_phase_a_round_1_decision_v1(
            decision,
            round_1_scout_sha256=sha256(self.news_phase_a_scout_path),
        )
        records = {item["case_id"]: item for item in decision["case_decisions"]}
        self.assertEqual(records["7059858129298803968"]["case_lifecycle_result"], "approved")
        self.assertFalse(records["7629552120978861049"]["automatically_rerouted_to_mix"])
        self.assertFalse(records["7673808914944625983"]["automatically_rerouted_to_mix"])
        self.assertFalse(records["7614013950665018678"]["automatically_rerouted_to_mix"])
        self.assertEqual(decision["phase_b_status"], "not_started_blocked")
        self.assertTrue(all(not item["pattern_created"] for item in records.values()))

    def test_705_is_canonically_approved_for_news_with_five_matching_beats(self) -> None:
        case = json.loads(self.news_case_705_path.read_text(encoding="utf-8"))
        approval = json.loads(
            self.news_case_705_compatibility_path.read_text(encoding="utf-8")
        )
        self.assertEqual(case["lifecycle"]["status"], "approved")
        self.assertEqual(case["lifecycle"]["approved_by"], "李健")
        self.assertEqual(case["identity"]["analysis_profile"], "news")
        self.assertEqual(len(case["storyboard"]["micro_beat_sequence"]), 5)
        self.assertFalse(case["storyboard"]["semantic_carrier"]["narration_presence"] == "present")
        validate_case_profile_compatibility_approval_v1(
            approval,
            approved_case_sha256=sha256(self.news_case_705_path),
        )
        self.assertEqual(approval["approved_compatible_generation_profiles"], ["news"])
        self.assertFalse(approval["pattern_created"])

    def test_758_concise_review_pack_preserves_pending_state_and_seven_beats(self) -> None:
        path = (
            self.news_phase_a_scout_path.parent
            / "human_review"
            / "7582922932108774691"
            / "case_human_review_pack_concise_v1.md"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn("Pending Final Human Review / Not Approved", text)
        self.assertIn("Seven Micro Beats", text)
        for index in range(1, 8):
            self.assertIn(f"B{index:03d}", text)
        self.assertIn("continuous narration is not required", text)

    def test_round_2_pre_gate_precedes_target_fit_and_only_strong_enters_formal(self) -> None:
        scout = json.loads(self.news_phase_a_round_2_path.read_text(encoding="utf-8"))
        validate_news_phase_a_round_2_scout_v1(
            scout,
            round_1_scout_sha256=sha256(self.news_phase_a_scout_path),
            round_1_decision_sha256=sha256(self.news_phase_a_round_1_decision_path),
        )
        selected = []
        for target in scout["research_targets"]:
            self.assertTrue(3 <= len(target["discovery_candidates"]) <= 5)
            for candidate in target["discovery_candidates"]:
                validate_news_profile_pre_gate(candidate["news_profile_pre_gate"])
                if candidate["formal_pipeline_selected"]:
                    selected.append(candidate)
                    self.assertEqual(
                        candidate["news_profile_pre_gate"]["news_profile_likelihood"],
                        "strong",
                    )
        self.assertEqual([item["candidate_id"] for item in selected], ["NEWSA004_R2_C001"])

    def test_round_2_does_not_reuse_round_1_and_validly_stops_three_targets(self) -> None:
        scout = json.loads(self.news_phase_a_round_2_path.read_text(encoding="utf-8"))
        old_urls = set(scout["round_1_candidate_urls_excluded"])
        new_urls = {
            candidate["source_url"]
            for target in scout["research_targets"]
            for candidate in target["discovery_candidates"]
        }
        self.assertFalse(old_urls & new_urls)
        self.assertEqual(scout["round_2_summary"]["discovery_candidate_count"], 19)
        self.assertEqual(
            set(scout["round_2_summary"]["no_suitable_news_candidate_targets"]),
            {"NEWS_PHASE_A_002", "NEWS_PHASE_A_003", "NEWS_PHASE_A_006"},
        )

    def test_round_2_scene_contrast_case_has_recoverable_visual_micro_beats(self) -> None:
        scout = json.loads(self.news_phase_a_round_2_path.read_text(encoding="utf-8"))
        case = scout["formal_case_candidates"][0]
        self.assertEqual(case["case_id"], "7507825653623344396")
        self.assertEqual(case["profile_analysis"]["observed_source_profile"], "news")
        self.assertEqual(case["semantic_carrier_recovery"]["carrier_type"], "visual_information_state_sequence")
        self.assertEqual(len(case["micro_beat_sequence"]), 5)
        self.assertTrue(Path(case["source_evidence"]["video_path"]).is_file())
        self.assertEqual(
            sha256(Path(case["source_evidence"]["video_path"])),
            case["source_evidence"]["video_sha256"],
        )
        self.assertEqual(case["lifecycle"]["status"], "review_required")
        self.assertFalse(case["lifecycle"]["approved"])

    def test_round_2_preserves_privacy_proof_authority_and_phase_b_stop(self) -> None:
        scout = json.loads(self.news_phase_a_round_2_path.read_text(encoding="utf-8"))
        case = scout["formal_case_candidates"][0]
        self.assertFalse(case["privacy"]["obvious_sensitive_pii"])
        self.assertEqual(case["privacy"]["status"], "human_review_required")
        self.assertEqual(case["proof"]["status"], "not_upgraded")
        self.assertFalse(case["authority"]["case_specific_facts_transferred"])
        self.assertEqual(scout["model_and_tool_usage"]["remote_model_calls"], 0)
        self.assertEqual(scout["round_2_summary"]["phase_b_status"], "not_started_blocked")
        self.assertFalse(scout["authority"]["pattern_created"])

    def test_758_is_approved_news_evidence_without_timing_template(self) -> None:
        case = json.loads(self.news_case_758_path.read_text(encoding="utf-8"))
        approval = json.loads(
            self.news_case_758_compatibility_path.read_text(encoding="utf-8")
        )
        self.assertEqual(case["lifecycle"]["status"], "approved")
        self.assertEqual(case["lifecycle"]["approved_by"], "李健")
        self.assertEqual(len(case["storyboard"]["micro_beat_sequence"]), 7)
        timing = case["storyboard"]["timing_boundary"]
        self.assertEqual(timing["source_duration_seconds"], 98.333)
        self.assertEqual(timing["timing_template"], "not_implied")
        self.assertEqual(timing["duration_template"], "not_implied")
        self.assertFalse(timing["news_registry_configurable_constraints_modified"])
        validate_case_profile_compatibility_approval_v1(
            approval, approved_case_sha256=sha256(self.news_case_758_path)
        )
        self.assertEqual(approval["approved_compatible_generation_profiles"], ["news"])
        self.assertFalse(approval["pattern_created"])

    def test_750_visual_only_news_structure_is_valid_and_requires_explicit_governance(self) -> None:
        case = json.loads(self.news_case_750_path.read_text(encoding="utf-8"))
        decision = json.loads(
            self.news_case_750_structural_decision_path.read_text(encoding="utf-8")
        )
        validate_case_profile_structural_decision_v1(decision)
        # The earlier structural decision remains an immutable gate-pending snapshot.
        self.assertEqual(decision["case_lifecycle_status"], "review_required")
        self.assertEqual(decision["canonical_approved_compatible_generation_profiles"], [])
        self.assertEqual(
            set(decision["unresolved_gates"]),
            {"privacy_review", "source_rights_review"},
        )
        # The current Case was approved only after the explicit V1 governance decision.
        self.assertEqual(case["lifecycle"]["status"], "approved")
        self.assertTrue(case["lifecycle"]["approved"])
        self.assertEqual(case["approval"]["source_governance"]["policy_version"], "V1.0")
        self.assertFalse(case["approval"]["media_reuse_authorized"])
        self.assertFalse(case["storyboard"]["validation"]["continuous_narration_required"])
        self.assertEqual(
            case["storyboard"]["semantic_carrier"]["carrier_type"],
            "visual_information_state_sequence",
        )
        self.assertEqual(len(case["storyboard"]["micro_beat_sequence"]), 5)
        self.assertEqual(decision["structural_compatible_generation_profiles"], ["news"])

    def test_phase_a_closes_with_three_supported_directions_not_six(self) -> None:
        closure = json.loads(self.news_phase_a_closure_path.read_text(encoding="utf-8"))
        validate_news_phase_a_closure_v1(closure)
        self.assertEqual(closure["status"], "complete")
        self.assertEqual(len(closure["supported_structural_directions"]), 3)
        outcomes = {item["target_id"]: item for item in closure["research_target_outcomes"]}
        for target in ("NEWS_PHASE_A_002", "NEWS_PHASE_A_003", "NEWS_PHASE_A_006"):
            self.assertEqual(
                outcomes[target]["result"], "no_independent_news_structure_evidenced"
            )
            self.assertFalse(outcomes[target]["pattern_created"])
        self.assertEqual(closure["approved_news_pattern_count"], 0)

    def test_creative_coverage_update_is_companion_and_news_stays_insufficient(self) -> None:
        update = json.loads(self.news_coverage_update_path.read_text(encoding="utf-8"))
        validate_news_creative_coverage_update_v1(update)
        news = update["news_current_coverage"]
        self.assertEqual(news["approved_news_compatible_case_ids"], [
            "7059858129298803968", "7582922932108774691"
        ])
        self.assertEqual(news["structural_seed_gate_pending_case_ids"], [
            "7507825653623344396"
        ])
        self.assertEqual(news["approved_news_pattern_count"], 0)
        self.assertFalse(news["news_generation_authorized"])
        self.assertEqual(
            update["source_refs"]["approved_coverage_baseline"]["sha256"],
            sha256(self.coverage_report_path),
        )

    def test_phase_b_plan_contains_only_selected_directions_and_no_pattern(self) -> None:
        plan = json.loads(self.news_phase_b_plan_path.read_text(encoding="utf-8"))
        validate_news_phase_b_depth_build_plan_v1(plan)
        self.assertEqual(
            [item["direction_id"] for item in plan["directions"]],
            ["number_or_price_led_micro_information", "scene_contrast"],
        )
        self.assertEqual(plan["coverage_only_direction"], "event_or_campaign_explanation")
        self.assertFalse(plan["pattern_created"])
        self.assertFalse(plan["news_generation_authorized"])
        self.assertFalse(plan["news_export_authorized"])

    def test_phase_b_double_gate_selects_four_review_required_cases(self) -> None:
        scout = json.loads(self.news_phase_b_scout_path.read_text(encoding="utf-8"))
        validate_news_phase_b_round_1_scout_v1(scout)
        self.assertEqual(scout["summary"]["discovery_candidate_count"], 12)
        self.assertEqual(scout["summary"]["formal_candidate_count"], 4)
        for case in scout["formal_case_candidates"]:
            self.assertEqual(case["lifecycle"]["status"], "review_required")
            self.assertFalse(case["lifecycle"]["approved"])
            self.assertEqual(case["profile_analysis"]["observed_source_profile"], "news")
            self.assertEqual(case["profile_analysis"]["compatible_generation_profiles_candidate"], ["news"])
            self.assertFalse(case["pattern_state"]["pattern_mining_performed"])

    def test_price_gate_rejects_topic_match_when_price_is_not_first_anchor(self) -> None:
        scout = json.loads(self.news_phase_b_scout_path.read_text(encoding="utf-8"))
        price = next(
            item for item in scout["directions"]
            if item["direction_id"] == "number_or_price_led_micro_information"
        )
        candidate = next(
            item for item in price["discovery_candidates"]
            if item["candidate_id"] == "NEWSPB_PRICE_R1_C001"
        )
        self.assertEqual(candidate["news_profile_pre_gate"]["news_profile_likelihood"], "strong")
        self.assertEqual(candidate["seed_structural_similarity_gate"]["result"], "fail")
        self.assertFalse(candidate["formal_pipeline_selected"])

    def test_scene_gate_rejects_result_montage_without_state_a(self) -> None:
        scout = json.loads(self.news_phase_b_scout_path.read_text(encoding="utf-8"))
        scene = next(
            item for item in scout["directions"] if item["direction_id"] == "scene_contrast"
        )
        candidate = next(
            item for item in scene["discovery_candidates"]
            if item["candidate_id"] == "NEWSPB_SCENE_R1_C001"
        )
        self.assertEqual(candidate["seed_structural_similarity_gate"]["result"], "fail")
        self.assertIn("State A", candidate["seed_structural_similarity_gate"]["reason"])
        self.assertFalse(candidate["formal_pipeline_selected"])

    def test_phase_b_preserves_privacy_proof_authority_and_stop_boundaries(self) -> None:
        scout = json.loads(self.news_phase_b_scout_path.read_text(encoding="utf-8"))
        self.assertEqual(scout["summary"]["remote_model_calls"], 0)
        self.assertEqual(scout["summary"]["cross_case_research_status"], "not_started")
        self.assertEqual(scout["summary"]["pattern_status"], "not_created")
        self.assertEqual(
            scout["summary"]["news_operational_readiness"],
            "research_coverage_insufficient",
        )
        self.assertTrue(all(case["proof"]["status"] == "not_upgraded" for case in scout["formal_case_candidates"]))
        self.assertTrue(all(not case["authority"]["case_specific_facts_transferred"] for case in scout["formal_case_candidates"]))
        self.assertTrue(all(value is False for value in scout["authority"].values()))

    def test_phase_b_concise_review_packs_cover_required_human_review_fields(self) -> None:
        review_root = self.news_phase_b_scout_path.parent / "human_review"
        case_ids = (
            "7640840358842207507",
            "7635146658208744867",
            "7639693960727179747",
            "7616327461634652005",
        )
        for case_id in case_ids:
            pack_path = review_root / case_id / "case_human_review_pack_concise_v1.md"
            text = pack_path.read_text(encoding="utf-8")
            for heading in (
                "## A. Identity",
                "## B. Profile",
                "## C. Semantic Carrier",
                "## D. Micro Beat Sequence",
                "## E. Seed Structural Similarity",
                "## F. Surface Diversity",
                "## H. Rights / Privacy",
                "## I. Conditional Lifecycle Impact",
            ):
                self.assertIn(heading, text)
            self.assertIn("depends on continuous narration：`false`", text)
            self.assertIn("not an Approved Pattern invariant", text)
            self.assertIn("it is not Semantic Novelty", text)
            self.assertIn("source_rights_status：`review_required`", text)
            self.assertIn("Status: **Review Required / Not Approved**", text)

    def test_price_review_packs_fail_closed_to_price_offer_scope(self) -> None:
        review_root = self.news_phase_b_scout_path.parent / "human_review"
        for case_id in ("7640840358842207507", "7635146658208744867"):
            text = (
                review_root / case_id / "case_human_review_pack_concise_v1.md"
            ).read_text(encoding="utf-8")
            self.assertIn("scope_evidence：`price_offer_led_only`", text)
            self.assertIn("泛化", text)
            self.assertIn("broader number-led", text)
            self.assertNotIn("scope_evidence：`broader_number_led`", text)

    def test_scene_review_packs_distinguish_progression_quality(self) -> None:
        review_root = self.news_phase_b_scout_path.parent / "human_review"
        operation_pack = (
            review_root
            / "7639693960727179747"
            / "case_human_review_pack_concise_v1.md"
        ).read_text(encoding="utf-8")
        slideshow_pack = (
            review_root
            / "7616327461634652005"
            / "case_human_review_pack_concise_v1.md"
        ).read_text(encoding="utf-8")
        self.assertIn("scene_contrast_quality：`strong`", operation_pack)
        self.assertIn("State A → operation → reveal → State B close", operation_pack)
        self.assertIn("scene_contrast_quality：`moderate`", slideshow_pack)
        self.assertIn("重复 visual slideshow", slideshow_pack)

    def test_historical_direction_status_remains_conditional_and_current_approval_runs_no_pattern_research(self) -> None:
        review_root = self.news_phase_b_scout_path.parent / "human_review"
        price_pack = (
            review_root
            / "7640840358842207507"
            / "case_human_review_pack_concise_v1.md"
        ).read_text(encoding="utf-8")
        scene_pack = (
            review_root
            / "7639693960727179747"
            / "case_human_review_pack_concise_v1.md"
        ).read_text(encoding="utf-8")
        self.assertIn("eligible_for_pattern_candidate_research", price_pack)
        self.assertIn("eligible_for_pattern_hypothesis_only", scene_pack)
        self.assertIn("Seed 750782 remains rights-pending", scene_pack)
        self.assertIn("no Cross-case Comparison or Pattern Research was performed", price_pack)
        for case_id in (
            "7640840358842207507",
            "7635146658208744867",
            "7639693960727179747",
            "7616327461634652005",
        ):
            case = json.loads(
                (ROOT / "data" / "cases" / case_id / "case_v1.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(case["lifecycle"]["status"], "approved")
            self.assertEqual(
                case["approval"]["source_governance"]["research_ingestion_eligibility"],
                "eligible_for_internal_research",
            )
            self.assertEqual(
                case["approval"]["source_governance"]["media_reuse_rights"],
                "not_established",
            )
            self.assertFalse(case["pattern_state"]["pattern_mining_performed"])

    def test_phase_b_human_review_summary_has_only_requested_decision_columns(self) -> None:
        summary_path = (
            self.news_phase_b_scout_path.parent
            / "news_phase_b_round_1_human_review_summary_v1.md"
        )
        lines = summary_path.read_text(encoding="utf-8").splitlines()
        header = next(line for line in lines if line.startswith("| Case |"))
        self.assertEqual(
            header,
            "| Case | Direction | Observed profile | Structure fit | Surface diversity | Privacy | Rights | Lifecycle impact |",
        )
        self.assertEqual(sum(1 for line in lines if line.startswith("| 76")), 4)
        self.assertNotIn("Pattern Candidate", "\n".join(lines))

    def test_structural_pass_snapshot_precedes_explicit_governance_approval(self) -> None:
        closure = json.loads(
            self.news_phase_b_review_closure_path.read_text(encoding="utf-8")
        )
        validate_news_phase_b_human_review_closure_v1(closure)
        decisions = {
            item["case_id"]: item
            for item in closure["human_structural_profile_decisions"]
        }
        self.assertEqual(set(decisions), {
            "7640840358842207507",
            "7635146658208744867",
            "7639693960727179747",
            "7616327461634652005",
        })
        for case_id, decision in decisions.items():
            self.assertEqual(decision["human_structural_profile_decision"], "pass")
            self.assertTrue(decision["canonical_case_approval_withheld"])
            self.assertEqual(decision["canonical_case_lifecycle_status"], "review_required")
            case = json.loads(
                (ROOT / "data" / "cases" / case_id / "case_v1.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(case["lifecycle"]["status"], "approved")
            self.assertEqual(case["approval"]["source_governance"]["policy_version"], "V1.0")
            self.assertNotEqual(
                decision["case_ref"]["sha256"],
                sha256(ROOT / "data" / "cases" / case_id / "case_v1.json"),
            )

    def test_price_research_scope_is_narrowed_without_rewriting_history(self) -> None:
        closure = json.loads(
            self.news_phase_b_review_closure_path.read_text(encoding="utf-8")
        )
        scope = closure["research_scope_amendment"]
        self.assertEqual(
            scope["historical_research_target"],
            "number_or_price_led_micro_information",
        )
        self.assertEqual(
            scope["effective_research_evidence_scope"],
            "price_offer_led_micro_information",
        )
        self.assertEqual(scope["scope_evidence"], "price_offer_led_only")
        self.assertEqual(scope["broader_number_led_status"], "insufficient_evidence")
        self.assertFalse(scope["historical_artifacts_modified"])
        self.assertFalse(scope["pattern_invariant_claimed"])

    def test_boundary_variant_remains_valid_without_transformation_invariant(self) -> None:
        closure = json.loads(
            self.news_phase_b_review_closure_path.read_text(encoding="utf-8")
        )
        decision = next(
            item
            for item in closure["human_structural_profile_decisions"]
            if item["case_id"] == "7616327461634652005"
        )
        self.assertEqual(decision["research_role"], "boundary_variant_evidence")
        self.assertEqual(decision["human_structural_profile_decision"], "pass")
        self.assertFalse(decision["transformation_action_required_for_case_validity"])
        self.assertEqual(decision["canonical_case_lifecycle_status"], "review_required")
        role_authority = closure["research_role_authority"]
        self.assertFalse(role_authority["changes_case_approval_authority"])
        self.assertFalse(role_authority["changes_pattern_lifecycle_threshold"])
        self.assertFalse(role_authority["invalidates_boundary_evidence"])

    def test_source_governance_audit_separates_three_concepts_and_finds_drift(self) -> None:
        audit = json.loads(
            self.case_source_governance_audit_path.read_text(encoding="utf-8")
        )
        validate_case_source_governance_audit_v1(audit)
        self.assertEqual(audit["status"], "human_policy_decision_required")
        self.assertEqual(set(audit["governance_distinction"]), {
            "source_provenance",
            "research_ingestion_eligibility",
            "media_reuse_rights",
        })
        drift = audit["detected_drift"]
        self.assertFalse(drift["canonical_approve_case_checks_source_rights"])
        self.assertFalse(drift["historical_approved_cases_have_uniform_source_rights_field"])
        self.assertTrue(drift["field_semantics_overloaded"])
        self.assertFalse(drift["canonical_case_policy_silently_changed"])
        self.assertEqual(
            audit["blocking_semantics"]["media_reuse_rights"],
            "blocks_footage_reuse_not_structural_fact_authority",
        )

    def test_governance_audit_snapshot_preserves_historical_and_preapproval_hashes(self) -> None:
        expected = {
            "7680512578585870322": "30e102808d5e198e18ba8176523472b5271ba3789403ab97e7e873daf4c415f1",
            "7683027343636542565": "3e4d117edd67c7b73022e05fdb880ade205e1ab5a5d4509aefd52d1c65ee78a3",
            "7650056203686530319": "0d43b2536057fba7c8a1e9a802c8870042f97b001eee85a0b776b64a85d53814",
            "7059858129298803968": "a7e7d43b3d4feb79fe5e6a995cdcb6b36c8427db26a7296fef574094e3f249ab",
            "7582922932108774691": "ea69858357639a0dcb6b92d3ca6a8f2636c03d41d04fec58418a4101b6bf7669",
            "7507825653623344396": "b55d25ecbde3bad9b1bc68eef02468c6824e7a53d705960a73db44da3e87e138",
            "7640840358842207507": "e71d50f080c5d6e361bc39d87a19ef1725241c516f693017fccfb3d6543fae90",
            "7635146658208744867": "9ca2295f8b9e154d76b8058568163fe5f24f214fea09ba239f2036f2f2740531",
            "7639693960727179747": "0affa975b4d12423f8fb97b22ffcfa6a045eb4803fd16384d799cade77e19f10",
            "7616327461634652005": "94841fedc32a2a36024e2db57636dae3c382f540f36973404aff7cdf7bcf7b17",
        }
        audit = json.loads(
            self.case_source_governance_audit_path.read_text(encoding="utf-8")
        )
        audit_by_id = {item["case_id"]: item for item in audit["case_audit"]}
        for case_id, digest in expected.items():
            case_path = ROOT / "data" / "cases" / case_id / "case_v1.json"
            self.assertEqual(audit_by_id[case_id]["case_ref"]["sha256"], digest)
            self.assertFalse(audit_by_id[case_id]["case_artifact_modified_by_audit"])
            if case_id in {
                "7507825653623344396",
                "7640840358842207507",
                "7635146658208744867",
                "7639693960727179747",
                "7616327461634652005",
            }:
                self.assertNotEqual(sha256(case_path), digest)
                current = json.loads(case_path.read_text(encoding="utf-8"))
                self.assertEqual(current["lifecycle"]["status"], "approved")
            else:
                self.assertEqual(sha256(case_path), digest)

    def test_governance_closure_only_calculates_conditional_pattern_eligibility(self) -> None:
        closure = json.loads(
            self.news_phase_b_review_closure_path.read_text(encoding="utf-8")
        )
        status = closure["direction_evidence_status"]
        price = status["price_offer_led_micro_information"]
        scene = status["scene_contrast"]
        self.assertEqual(price["current_canonical_approved_count"], 1)
        self.assertEqual(price["if_all_pending_approved_count"], 3)
        self.assertIn(
            "eligible_for_pattern_candidate_research",
            price["conditional_status"],
        )
        self.assertEqual(scene["current_canonical_approved_count"], 0)
        self.assertEqual(scene["if_phase_b_two_approved_seed_pending_count"], 2)
        self.assertEqual(scene["if_all_three_approved_count"], 3)
        self.assertEqual(
            scene["conditional_status_if_two"],
            "pattern_hypothesis_research_only",
        )
        self.assertTrue(all(not item["research_executed"] for item in status.values()))
        self.assertTrue(all(value is False for value in closure["authority"].values()))

    def test_case_source_governance_policy_freezes_internal_research_scope_only(self) -> None:
        policy = json.loads(
            self.case_source_governance_policy_path.read_text(encoding="utf-8")
        )
        validate_case_source_governance_policy_v1(policy)
        approval = policy["canonical_case_approval"]
        self.assertEqual(
            approval["authorization_scope"],
            "internal_creative_structural_research_eligibility",
        )
        self.assertFalse(approval["grants_copyright_ownership"])
        self.assertFalse(approval["grants_media_reuse_permission"])
        self.assertFalse(approval["grants_footage_redistribution_permission"])
        self.assertFalse(approval["grants_customer_production_footage_authorization"])
        self.assertFalse(policy["legacy_source_rights_field"]["canonical_case_approval_gate"])

    def test_historical_governance_companions_are_reference_first(self) -> None:
        expected_hashes = {
            "7680512578585870322": "30e102808d5e198e18ba8176523472b5271ba3789403ab97e7e873daf4c415f1",
            "7683027343636542565": "3e4d117edd67c7b73022e05fdb880ade205e1ab5a5d4509aefd52d1c65ee78a3",
            "7650056203686530319": "0d43b2536057fba7c8a1e9a802c8870042f97b001eee85a0b776b64a85d53814",
            "7059858129298803968": "a7e7d43b3d4feb79fe5e6a995cdcb6b36c8427db26a7296fef574094e3f249ab",
            "7582922932108774691": "ea69858357639a0dcb6b92d3ca6a8f2636c03d41d04fec58418a4101b6bf7669",
        }
        for case_id, expected_sha in expected_hashes.items():
            case_path = ROOT / "data" / "cases" / case_id / "case_v1.json"
            companion_path = (
                self.case_source_governance_audit_path.parent
                / "cases"
                / case_id
                / "case_source_governance_companion_v1.json"
            )
            companion = json.loads(companion_path.read_text(encoding="utf-8"))
            self.assertEqual(sha256(case_path), expected_sha)
            validate_case_source_governance_companion_v1(
                companion, expected_case_sha256=expected_sha
            )
            self.assertEqual(
                companion["research_ingestion_basis"],
                "historically_accepted_for_internal_research",
            )
            self.assertEqual(companion["media_reuse_rights"], "not_established")
            self.assertFalse(companion["production_footage_pool_eligible"])
        legacy = json.loads(
            (
                self.case_source_governance_audit_path.parent
                / "cases"
                / "7680512578585870322"
                / "case_source_governance_companion_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            legacy["privacy_basis"],
            "legacy_approval_before_embedded_privacy_gate",
        )

    def test_five_pending_news_cases_are_canonically_approved_news_only(self) -> None:
        case_ids = (
            "7507825653623344396",
            "7640840358842207507",
            "7635146658208744867",
            "7639693960727179747",
            "7616327461634652005",
        )
        for case_id in case_ids:
            case_root = ROOT / "data" / "cases" / case_id
            case_path = case_root / "case_v1.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            receipt = json.loads(
                (case_root / "approval_receipt.json").read_text(encoding="utf-8")
            )
            compatibility = json.loads(
                (case_root / "case_profile_compatibility_approval_v1.json").read_text(
                    encoding="utf-8"
                )
            )
            companion = json.loads(
                (
                    self.case_source_governance_audit_path.parent
                    / "cases"
                    / case_id
                    / "case_source_governance_companion_v1.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(case["lifecycle"]["status"], "approved")
            self.assertEqual(case["lifecycle"]["approved_by"], "李健")
            self.assertEqual(
                receipt["source_governance"]["research_ingestion_eligibility"],
                "eligible_for_internal_research",
            )
            self.assertFalse(receipt["case_approval_grants_media_reuse"])
            validate_case_profile_compatibility_approval_v1(
                compatibility, approved_case_sha256=sha256(case_path)
            )
            self.assertEqual(
                compatibility["approved_compatible_generation_profiles"], ["news"]
            )
            validate_case_source_governance_companion_v1(
                companion, expected_case_sha256=sha256(case_path)
            )
            self.assertFalse(case_is_eligible_for_production_footage(companion))

    def test_public_source_traceability_does_not_imply_media_reuse(self) -> None:
        companion = json.loads(
            (
                self.case_source_governance_audit_path.parent
                / "cases"
                / "7640840358842207507"
                / "case_source_governance_companion_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(companion["source_provenance"]["status"], "traceable")
        self.assertEqual(
            companion["research_ingestion_eligibility"],
            "eligible_for_internal_research",
        )
        self.assertEqual(companion["media_reuse_rights"], "not_established")
        self.assertFalse(case_is_eligible_for_production_footage(companion))

    def test_price_offer_cross_case_bundle_is_ready_without_broader_number_claim(self) -> None:
        bundle = json.loads(
            self.price_cross_case_bundle_path.read_text(encoding="utf-8")
        )
        validate_news_cross_case_research_bundle_v1(bundle)
        self.assertEqual(
            [item["case_id"] for item in bundle["cases"]],
            [
                "7059858129298803968",
                "7640840358842207507",
                "7635146658208744867",
            ],
        )
        self.assertEqual(bundle["scope"]["scope_evidence"], "price_offer_led_only")
        self.assertEqual(bundle["scope"]["broader_number_led"], "insufficient_evidence")
        self.assertEqual(bundle["canonical_approved_case_count"], 3)
        self.assertTrue(bundle["eligible_for_cross_case_comparison"])
        self.assertTrue(bundle["eligible_for_pattern_candidate_research"])
        self.assertFalse(bundle["comparison_executed"])
        self.assertFalse(bundle["pattern_candidate_created"])

    def test_scene_contrast_bundle_accepts_boundary_variant_without_operation_invariant(self) -> None:
        bundle = json.loads(
            self.scene_cross_case_bundle_path.read_text(encoding="utf-8")
        )
        validate_news_cross_case_research_bundle_v1(bundle)
        self.assertEqual(
            [item["case_id"] for item in bundle["cases"]],
            [
                "7507825653623344396",
                "7639693960727179747",
                "7616327461634652005",
            ],
        )
        roles = {item["case_id"]: item["research_role"] for item in bundle["cases"]}
        self.assertEqual(
            roles["7616327461634652005"], "boundary_variant_evidence"
        )
        self.assertFalse(bundle["scope"]["operation_required"])
        self.assertFalse(bundle["scope"]["transition_required"])
        self.assertFalse(bundle["scope"]["before_after_wording_required"])
        self.assertEqual(bundle["canonical_approved_case_count"], 3)
        self.assertTrue(bundle["eligible_for_cross_case_comparison"])
        self.assertFalse(bundle["comparison_executed"])
        self.assertFalse(bundle["pattern_candidate_created"])

    def test_cross_case_research_inputs_do_not_transfer_authority_or_run_models(self) -> None:
        for path in (
            self.price_cross_case_bundle_path,
            self.scene_cross_case_bundle_path,
        ):
            bundle = json.loads(path.read_text(encoding="utf-8"))
            authority = bundle["authority"]
            self.assertTrue(all(value is False for value in authority.values()))
            self.assertFalse(bundle["comparison_executed"])
            self.assertFalse(bundle["pattern_candidate_created"])
            self.assertIn("not_run_existing_comparator", bundle["comparison_execution_status"])

    def test_registry_and_original_coverage_artifacts_remain_unchanged(self) -> None:
        self.assertEqual(
            sha256(self.registry_path),
            "ba344af8ed12e9ccf94c552f6ec314f9c856f9466cd050bba1572233a9cbf527",
        )
        self.assertEqual(
            sha256(self.coverage_report_path),
            "442e25a78ee1641f24796893490f14480ff88a3453630cc44883725128f76b9a",
        )


if __name__ == "__main__":
    unittest.main()
