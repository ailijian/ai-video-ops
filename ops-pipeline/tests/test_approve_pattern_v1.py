from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approve_pattern_v1 import (  # noqa: E402
    APPROVAL_NOTE,
    APPROVABLE_PATTERN_ID,
    NEWS_PRICE_PATTERN_ID,
    NEWS_SCENE_PATTERN_ID,
    REJECTED_PATTERN_ID,
    approve_pattern,
    approve_news_pattern,
    build_news_approved_pattern,
    build_news_pattern_coverage_update,
    reject_candidate,
    validate_news_approved_pattern,
)


ROOT = SCRIPTS.parent


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PatternApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.approved_root = self.root / "approved"
        self.research_path = self.root / "pattern_research_v1.json"
        self.case_ids = ["100", "200", "300"]
        self.fingerprint_hashes = {
            case_id: hashlib.sha256(f"fp-{case_id}".encode()).hexdigest()
            for case_id in self.case_ids
        }
        self.research = {
            "case_ids": self.case_ids,
            "case_sources": [
                {
                    "case_id": case_id,
                    "fingerprint_sha": self.fingerprint_hashes[case_id],
                }
                for case_id in self.case_ids
            ],
            "pattern_candidate_ids": [APPROVABLE_PATTERN_ID, REJECTED_PATTERN_ID],
            "authority": {"remote_model_used": False},
            "validation": {"passed": True},
        }
        write_json(self.research_path, self.research)
        self.approve_candidate_path = self.root / "candidate_1.json"
        self.reject_candidate_path = self.root / "candidate_2.json"
        write_json(
            self.approve_candidate_path,
            self.candidate(APPROVABLE_PATTERN_ID),
        )
        write_json(
            self.reject_candidate_path,
            self.candidate(REJECTED_PATTERN_ID),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def candidate(self, pattern_id: str) -> dict:
        return {
            "pattern_id": pattern_id,
            "status": "candidate",
            "scope": {
                "supported_case_count": 3,
                "supported_case_ids": self.case_ids,
                "industry_scope": ["food", "plant_service"],
            },
            "evidence": [
                {
                    "case_id": case_id,
                    "fingerprint_sha": self.fingerprint_hashes[case_id],
                    "observed": {
                        "speech_ratio": 0.8,
                        "primary_role_counts": {"action": 5, "context": 5},
                        "scene_relation_counts": {"supplement": 10},
                    },
                }
                for case_id in self.case_ids
            ],
            "contradicting_evidence": [],
            "effectiveness": {
                "status": "unvalidated",
                "performance_data_used": False,
            },
            "authority": {
                "candidate_only": True,
                "human_review_required": True,
            },
            "lineage": {
                "approved_case_sha256": {
                    case_id: hashlib.sha256(f"case-{case_id}".encode()).hexdigest()
                    for case_id in self.case_ids
                },
                "fingerprint_sha256": self.fingerprint_hashes,
            },
        }

    def approve(self):
        return approve_pattern(
            self.approve_candidate_path,
            self.research_path,
            self.approved_root,
            "Reviewer",
            APPROVAL_NOTE,
            "2026-09-11T00:00:00+00:00",
        )

    def test_approval_freezes_candidate_research_and_pattern_hashes(self) -> None:
        candidate_sha = sha256(self.approve_candidate_path)
        research_sha = sha256(self.research_path)
        pattern_path, receipt_path, pattern, receipt = self.approve()
        self.assertEqual(pattern["status"], "approved")
        self.assertEqual(receipt["source_candidate"]["sha256"], candidate_sha)
        self.assertEqual(receipt["source_research"]["sha256"], research_sha)
        self.assertEqual(receipt["approved_pattern"]["sha256"], sha256(pattern_path))
        self.assertTrue(receipt_path.is_file())

    def test_approved_definition_contains_only_creative_invariants(self) -> None:
        _pattern_path, _receipt_path, pattern, _receipt = self.approve()
        serialized = json.dumps(pattern["definition"], ensure_ascii=False).lower()
        for forbidden in (
            "many-to-many",
            "many_to_many",
            "verified proof",
            "verified-proof",
            "proof authority",
            "track representation",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertIn(
            "Narration is the primary semantic spine.",
            pattern["definition"]["invariants"],
        )
        self.assertEqual(len(pattern["definition"]["invariants"]), 4)

    def test_scope_and_effectiveness_remain_strict(self) -> None:
        _pattern_path, _receipt_path, pattern, _receipt = self.approve()
        self.assertEqual(pattern["scope"]["supported_case_count"], 3)
        self.assertEqual(pattern["effectiveness"]["status"], "unvalidated")
        self.assertFalse(pattern["effectiveness"]["performance_data_used"])
        self.assertFalse(pattern["effectiveness"]["causal_or_performance_claims_permitted"])

    def test_repeated_approval_cannot_overwrite(self) -> None:
        pattern_path, _receipt_path, _pattern, _receipt = self.approve()
        first_sha = sha256(pattern_path)
        with self.assertRaisesRegex(RuntimeError, "cannot overwrite"):
            self.approve()
        self.assertEqual(sha256(pattern_path), first_sha)

    def test_rejected_candidate_is_retained_without_approved_pattern(self) -> None:
        original_candidate_sha = sha256(self.reject_candidate_path)
        original_research_sha = sha256(self.research_path)
        reviewed, before_sha, _after_sha = reject_candidate(
            self.reject_candidate_path,
            self.research_path,
            self.approved_root,
            "Reviewer",
            reviewed_at="2026-09-11T00:00:00+00:00",
        )
        self.assertEqual(before_sha, original_candidate_sha)
        self.assertEqual(reviewed["status"], "review_rejected")
        self.assertTrue(self.reject_candidate_path.is_file())
        self.assertEqual(sha256(self.research_path), original_research_sha)
        self.assertFalse(
            (self.approved_root / REJECTED_PATTERN_ID / "pattern_v1.json").exists()
        )
        disposition = reviewed["research_disposition"]
        self.assertEqual(
            disposition["retained_hypothesis"]["working_name"],
            "Multimodal Hook Hypothesis",
        )
        self.assertEqual(
            disposition["observed_traits"][0]["status"], "observed_trait"
        )
        self.assertFalse(
            disposition["observed_traits"][0]["pattern_invariant"]
        )

    def test_remote_model_authority_never_changes(self) -> None:
        _pattern_path, _receipt_path, pattern, receipt = self.approve()
        self.assertFalse(pattern["authority_constraints"]["remote_model_used"])
        self.assertFalse(pattern["validation"]["remote_model_call_performed"])
        self.assertFalse(receipt["remote_model_call_performed"])


class NewsPatternFinalApprovalTests(unittest.TestCase):
    REGISTRY = ROOT / "data" / "production_profiles" / "production_profile_registry_v1.json"
    COVERAGE_BASELINE = ROOT / "data" / "creative_coverage" / "creative_coverage_report_v1.json"
    MIX_PATTERN = (
        ROOT
        / "data"
        / "patterns"
        / "approved"
        / "pcv1_narration_led_process_projection"
        / "pattern_v1.json"
    )
    CANDIDATES = {
        NEWS_PRICE_PATTERN_ID: (
            ROOT
            / "data"
            / "patterns"
            / "candidates"
            / NEWS_PRICE_PATTERN_ID
            / "pattern_candidate_v1.json"
        ),
        NEWS_SCENE_PATTERN_ID: (
            ROOT
            / "data"
            / "patterns"
            / "candidates"
            / NEWS_SCENE_PATTERN_ID
            / "pattern_candidate_v1.json"
        ),
    }
    EXPECTED_FROZEN_SHAS = {
        str(CANDIDATES[NEWS_PRICE_PATTERN_ID]): "85e8fe20dac87c0322188758b12b350667440174475ea7e8ec7a2e0a6f2c750c",
        str(CANDIDATES[NEWS_SCENE_PATTERN_ID]): "826142c862edb7c7390316d7d5b6fa11e308e88849cbe93b6d9fff74c5a37fb8",
        str(
            ROOT
            / "data/cross_case_research/news/price_offer_led_micro_information/price_offer_led_cross_case_comparison_v1.json"
        ): "3244a442afd8b8a031a16f2906f5d7f79029d0fb7bb8af81f630b58118722307",
        str(
            ROOT
            / "data/cross_case_research/news/price_offer_led_micro_information/price_offer_led_cross_case_comparison_v1_human_approval_v1.json"
        ): "eaead94409c232b08647d4ba3956b0eaa6c88e569c79c62067fe2ffa8dc9946f",
        str(
            ROOT
            / "data/cross_case_research/news/scene_contrast/scene_contrast_cross_case_comparison_v1.json"
        ): "35e8597d8cb263f14a9cd9e804fb249a9c9e14195036b9fe712ca07b2eada88e",
        str(
            ROOT
            / "data/cross_case_research/news/scene_contrast/scene_contrast_cross_case_comparison_v1_human_approval_v1.json"
        ): "20b7c8f98602270f1d5d9be9293a73429c03044574a5af460d5b1f8410765fd1",
        str(MIX_PATTERN): "e610e610965214a07d523cd66dd6b829ec7b5515fdd9f2b2b8314446a8ac190a",
        str(REGISTRY): "ba344af8ed12e9ccf94c552f6ec314f9c856f9466cd050bba1572233a9cbf527",
        str(COVERAGE_BASELINE): "442e25a78ee1641f24796893490f14480ff88a3453630cc44883725128f76b9a",
    }

    def build(self, pattern_id: str) -> tuple[dict, dict]:
        return build_news_approved_pattern(
            self.CANDIDATES[pattern_id],
            self.REGISTRY,
            "李健",
            "2026-09-12T20:00:00+00:00",
        )

    def test_frozen_source_artifact_hashes_remain_unchanged(self) -> None:
        self.assertEqual(
            {path: sha256(Path(path)) for path in self.EXPECTED_FROZEN_SHAS},
            self.EXPECTED_FROZEN_SHAS,
        )

    def test_repository_contains_two_canonical_approved_news_patterns(self) -> None:
        for pattern_id in self.CANDIDATES:
            pattern_path = (
                ROOT / "data" / "patterns" / "approved" / pattern_id / "pattern_v1.json"
            )
            receipt_path = pattern_path.parent / "approval_receipt.json"
            pattern = json.loads(pattern_path.read_text(encoding="utf-8"))
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            validate_news_approved_pattern(pattern)
            self.assertEqual(pattern["status"], "approved")
            self.assertEqual(pattern["compatible_profiles"], ["news"])
            self.assertEqual(receipt["reviewer"], "李健")
            self.assertEqual(receipt["approved_pattern"]["sha256"], sha256(pattern_path))
            self.assertEqual(receipt["source_candidate"]["sha256"], sha256(self.CANDIDATES[pattern_id]))

        approved_news = [
            path.parent.name
            for path in (ROOT / "data" / "patterns" / "approved").glob("*/pattern_v1.json")
            if json.loads(path.read_text(encoding="utf-8")).get("compatible_profiles")
            == ["news"]
        ]
        self.assertEqual(sorted(approved_news), sorted(self.CANDIDATES))

    def test_repository_coverage_revision_records_validation_gate(self) -> None:
        update_path = (
            ROOT
            / "data"
            / "creative_coverage"
            / "revisions"
            / "news_pattern_approval_creative_coverage_update_v1.json"
        )
        update = json.loads(update_path.read_text(encoding="utf-8"))
        news = update["news_current_coverage"]
        self.assertEqual(news["approved_news_pattern_count"], 2)
        self.assertEqual(news["operational_readiness"], "production_validation_required")
        self.assertFalse(news["news_production_ready"])
        self.assertFalse(news["news_generation_authorized"])
        self.assertFalse(news["news_excel_export_authorized"])
        for item in update["source_refs"]["approved_news_patterns"]:
            self.assertEqual(item["pattern_ref"]["sha256"], sha256(Path(item["pattern_ref"]["path"])))
            self.assertEqual(
                item["approval_receipt_ref"]["sha256"],
                sha256(Path(item["approval_receipt_ref"]["path"])),
            )

    def test_price_pattern_has_exactly_three_owned_invariants(self) -> None:
        pattern, _receipt = self.build(NEWS_PRICE_PATTERN_ID)
        validate_news_approved_pattern(pattern)
        self.assertEqual(
            pattern["definition"]["invariants"],
            [
                "price_or_offer_first_semantic_anchor",
                "multiple_recoverable_micro_information_states_follow_the_anchor",
                "later_states_materially_contextualize_scope_explain_or_situate_the_offer",
            ],
        )

    def test_price_narration_rule_is_inherited_not_duplicated(self) -> None:
        pattern, _receipt = self.build(NEWS_PRICE_PATTERN_ID)
        self.assertFalse(
            any("narration" in item for item in pattern["definition"]["invariants"])
        )
        constraint = pattern["inherited_profile_constraints"][0]
        self.assertEqual(constraint["owner"], "production_profile:news")
        self.assertEqual(constraint["authority"], "inherited_profile_constraint")
        self.assertFalse(constraint["pattern_owned_invariant"])

    def test_price_scope_and_post_anchor_relation_remain_narrow(self) -> None:
        pattern, _receipt = self.build(NEWS_PRICE_PATTERN_ID)
        self.assertEqual(pattern["scope"]["scope_limitation"], "price_offer_led_only")
        self.assertEqual(pattern["scope"]["explicitly_not_supported"], "generic_number_led")
        guard = pattern["definition"]["semantic_relation_guard"]
        self.assertTrue(guard["required"])
        self.assertEqual(
            guard["unrelated_b_roll_plus_persistent_price_text"], "out_of_scope"
        )

    def test_price_variants_do_not_freeze_timing_cta_or_scope_beat(self) -> None:
        pattern, _receipt = self.build(NEWS_PRICE_PATTERN_ID)
        non_invariants = pattern["definition"]["non_invariants"]
        self.assertIn("independent_explicit_scope_beat", non_invariants)
        self.assertIn("explicit_close", non_invariants)
        self.assertIn("exact_beat_count", non_invariants)
        self.assertIn("exact_duration", non_invariants)

    def test_scene_pattern_has_exactly_three_owned_invariants(self) -> None:
        pattern, _receipt = self.build(NEWS_SCENE_PATTERN_ID)
        validate_news_approved_pattern(pattern)
        self.assertEqual(
            pattern["definition"]["invariants"],
            [
                "meaningful_comparable_state_a_and_state_b",
                "state_difference_materially_changes_understanding",
                "visual_information_state_is_primary_semantic_carrier",
            ],
        )
        self.assertFalse(
            any("narration" in item for item in pattern["definition"]["invariants"])
        )

    def test_scene_scope_guard_and_unresolved_question_are_preserved(self) -> None:
        pattern, _receipt = self.build(NEWS_SCENE_PATTERN_ID)
        guard = pattern["scope"]["production_scope_guard"]
        self.assertEqual(guard["explicit_recoverable_state_correspondence"], "required")
        self.assertEqual(guard["same_subject_identity_requirement"], "unresolved")
        self.assertEqual(guard["arbitrary_cross_subject_contrast"], "out_of_scope")
        question = pattern["unresolved_questions"][0]
        self.assertEqual(question["question_id"], "same_subject_identity_requirement")
        self.assertEqual(question["status"], "unresolved")
        self.assertIsNone(question["frozen_answer"])

    def test_scene_transformation_is_optional_and_before_after_is_not_proof(self) -> None:
        pattern, _receipt = self.build(NEWS_SCENE_PATTERN_ID)
        self.assertEqual(pattern["transformation_action"]["status"], "optional_enhancer")
        self.assertFalse(pattern["transformation_action"]["pattern_invariant"])
        proof = pattern["proof_boundary"]
        self.assertFalse(proof["state_difference_is_automatically_verified_proof"])
        self.assertTrue(proof["observable_state_difference_is_not_verified_proof"])
        self.assertFalse(proof["causality_proven"])
        self.assertFalse(proof["transformation_attribution_proven"])

    def test_lineage_binds_candidate_comparison_approval_and_all_evidence(self) -> None:
        for pattern_id, candidate_path in self.CANDIDATES.items():
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            pattern, receipt = self.build(pattern_id)
            self.assertEqual(pattern["lineage"]["source_candidate"]["sha256"], sha256(candidate_path))
            self.assertEqual(
                pattern["lineage"]["source_comparison"]["sha256"],
                candidate["lineage"]["comparison_ref"]["sha256"],
            )
            self.assertEqual(
                pattern["lineage"]["source_comparison_human_approval"]["sha256"],
                candidate["lineage"]["comparison_human_approval_ref"]["sha256"],
            )
            self.assertEqual(len(receipt["supporting_evidence"]), 3)
            for evidence in receipt["supporting_evidence"]:
                for key in ("case_ref", "fingerprint_ref", "micro_beat_storyboard_ref"):
                    self.assertEqual(
                        evidence[key]["sha256"], sha256(Path(evidence[key]["path"]))
                    )

    def test_build_does_not_modify_candidates_cases_comparisons_or_mix_pattern(self) -> None:
        paths = [self.MIX_PATTERN, *self.CANDIDATES.values()]
        for candidate_path in self.CANDIDATES.values():
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            paths.extend(
                [
                    Path(candidate["lineage"]["comparison_ref"]["path"]),
                    Path(candidate["lineage"]["comparison_human_approval_ref"]["path"]),
                ]
            )
            paths.extend(
                Path(item["approved_case_ref"]["path"])
                for item in candidate["evidence"]
            )
        before = {str(path): sha256(path) for path in paths}
        for pattern_id in self.CANDIDATES:
            self.build(pattern_id)
        self.assertEqual(before, {str(path): sha256(path) for path in paths})

    def test_approval_writes_new_artifacts_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pattern_path, receipt_path, pattern, receipt = approve_news_pattern(
                self.CANDIDATES[NEWS_PRICE_PATTERN_ID],
                self.REGISTRY,
                root,
                "李健",
                "2026-09-12T20:00:00+00:00",
            )
            self.assertEqual(receipt["approved_pattern"]["sha256"], sha256(pattern_path))
            self.assertTrue(receipt_path.is_file())
            self.assertEqual(pattern["status"], "approved")
            with self.assertRaisesRegex(RuntimeError, "cannot overwrite"):
                approve_news_pattern(
                    self.CANDIDATES[NEWS_PRICE_PATTERN_ID],
                    self.REGISTRY,
                    root,
                    "李健",
                )

    def test_coverage_moves_to_validation_required_not_production_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outputs = [
                approve_news_pattern(
                    candidate,
                    self.REGISTRY,
                    root,
                    "李健",
                    "2026-09-12T20:00:00+00:00",
                )
                for candidate in self.CANDIDATES.values()
            ]
            update = build_news_pattern_coverage_update(
                [item[0] for item in outputs],
                [item[1] for item in outputs],
                self.REGISTRY,
                self.COVERAGE_BASELINE,
                "2026-09-12T20:00:00+00:00",
            )
            news = update["news_current_coverage"]
            self.assertEqual(news["approved_news_pattern_count"], 2)
            self.assertEqual(news["operational_readiness"], "production_validation_required")
            self.assertFalse(news["news_production_ready"])
            self.assertFalse(news["news_generation_authorized"])
            self.assertFalse(news["news_excel_export_authorized"])
            self.assertEqual(news["coverage_only_case_id"], "7582922932108774691")
            self.assertFalse(update["changes_canonical_registry"])

    def test_effectiveness_and_remote_model_authority_remain_absent(self) -> None:
        for pattern_id in self.CANDIDATES:
            pattern, receipt = self.build(pattern_id)
            self.assertEqual(pattern["effectiveness"]["status"], "unvalidated")
            self.assertFalse(pattern["effectiveness"]["performance_data_available"])
            self.assertFalse(pattern["effectiveness"]["performance_data_used"])
            self.assertFalse(pattern["validation"]["news_generation_performed"])
            self.assertFalse(pattern["validation"]["news_excel_export_performed"])
            self.assertFalse(receipt["remote_model_call_performed"])
        self.assertFalse(
            (ROOT / "data" / "patterns" / "approved" / "pcv1_news_event_explanation").exists()
        )


if __name__ == "__main__":
    unittest.main()
