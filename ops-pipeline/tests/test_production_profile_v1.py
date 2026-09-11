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
    build_creative_coverage_report_v1,
    build_production_profile_registry_v1,
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
            )

    def test_profile_aware_mix_matching_preserves_real_production_foundation(self) -> None:
        plan = self.canonical_match("mix", preserve_historical_request=True)
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
        plan = self.canonical_match("mix")
        self.assertEqual(plan["coverage"]["code"], "research_coverage_insufficient")
        self.assertEqual(plan["coverage"]["canonical_approved_compatible_case_count"], 0)
        self.assertEqual(plan["coverage"]["legacy_current_truth_bridge_case_count"], 0)
        self.assertEqual(plan["selected_cases"], [])

    def test_profile_aware_news_matching_fails_without_mix_fallback(self) -> None:
        plan = self.canonical_match("news")
        self.assertEqual(
            plan["coverage"]["code"], "research_coverage_insufficient"
        )
        self.assertEqual(plan["selected_patterns"], [])
        self.assertEqual(plan["selected_cases"], [])
        self.assertTrue(plan["validation"]["news_does_not_fallback_to_mix"])
        self.assertIn("approved_news_pattern", plan["coverage"]["missing_creative_coverage"])

    def test_profile_matching_does_not_transfer_case_facts(self) -> None:
        plan = self.canonical_match("mix", preserve_historical_request=True)
        self.assertTrue(plan["generation_constraints"]["case_facts_must_not_transfer"])
        self.assertFalse(plan["authority"]["case_facts_used_as_persona_facts"])
        self.assertFalse(plan["validation"]["observed_source_profile_used_as_approval"])


if __name__ == "__main__":
    unittest.main()
