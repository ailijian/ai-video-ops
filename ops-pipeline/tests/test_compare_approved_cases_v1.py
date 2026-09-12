from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compare_approved_cases_v1 import (  # noqa: E402
    build_comparison,
    build_comparison_human_approval,
    build_generalized_research_comparison,
    validate_comparison_human_approval,
    validate_generalized_research_comparison,
)


ROOT = SCRIPTS.parent


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CrossCaseComparisonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.case_paths: list[Path] = []
        self.fingerprint_paths: list[Path] = []
        for index, case_id in enumerate(("100", "200"), start=1):
            case_path = self.root / f"case_{case_id}.json"
            case = {
                "case_id": case_id,
                "lifecycle": {"status": "approved", "approved": True},
                "validation": {"passed": True},
                "quality": {"human_review_completed": True},
                "pattern_state": {"pattern_mining_performed": False},
            }
            write_json(case_path, case)
            fingerprint_path = self.root / f"fingerprint_{case_id}.json"
            fingerprint = self.fingerprint(case_id, sha256(case_path), index)
            write_json(fingerprint_path, fingerprint)
            self.case_paths.append(case_path)
            self.fingerprint_paths.append(fingerprint_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def fingerprint(case_id: str, case_hash: str, index: int) -> dict:
        return {
            "case_id": case_id,
            "source_case": {
                "sha256": case_hash,
                "status": "approved",
                "approved": True,
            },
            "identity": {
                "industry": "food",
                "duration_seconds": 20.0 * index,
            },
            "content_features": {
                "content_goal_candidate": "餐饮经营行动展示",
                "claims": ["行动主张"],
                "verified_proof_count": 0,
                "proof_shot_refs": [],
                "has_verified_proof": False,
                "has_explicit_cta": False,
            },
            "narration_features": {
                "segment_count": 5 * index,
                "total_speech_seconds": 15.0 * index,
                "speech_to_video_ratio": 0.75,
            },
            "visual_shot_features": {
                "shot_count": 10 * index,
                "shot_duration_stats": {"mean": 2.0, "median": 1.5},
                "shots_under_1s": 2,
                "shots_under_1s_ratio": 0.2,
                "shots_under_0_5s": 0,
                "shots_under_0_5s_ratio": 0.0,
                "primary_role_counts": {"action": 6 * index, "context": 4 * index},
                "secondary_role_counts": {},
                "onscreen_text_shot_count": 5,
                "onscreen_text_shot_ratio": 0.5,
            },
            "audio_visual_features": {
                "shot_to_narration_cardinality": "many_to_many",
            },
            "structure_features": {
                "structure_signature": "hook>development>payoff",
                "structure_sequence": [
                    {"stage": "hook", "description": "行动开场"},
                    {"stage": "development", "description": "经营过程"},
                    {"stage": "payoff", "description": "观点收束"},
                ],
                "hook_modalities": ["audio", "visual_text", "visual_scene"],
                "hook_candidate": {},
                "audio_role": "旁白提出行动观点",
                "visual_text_role": "文字重复观点",
                "visual_scene_role": "经营行动画面",
                "audio_visual_strategy": "旁白配合行动画面",
            },
            "pattern_mining_contract": {"this_artifact_is_not_a_pattern": True},
            "provenance": {"approved_case_sha256": case_hash},
        }

    def compare(self) -> dict:
        return build_comparison(self.case_paths, self.fingerprint_paths)

    def test_non_approved_case_is_rejected(self) -> None:
        case = json.loads(self.case_paths[0].read_text(encoding="utf-8"))
        case["lifecycle"] = {"status": "review_required", "approved": False}
        write_json(self.case_paths[0], case)
        with self.assertRaisesRegex(RuntimeError, "not Approved"):
            self.compare()

    def test_missing_fingerprint_is_rejected(self) -> None:
        missing = self.root / "missing.json"
        with self.assertRaises(FileNotFoundError):
            build_comparison(self.case_paths, [self.fingerprint_paths[0], missing])

    def test_input_order_does_not_change_output(self) -> None:
        forward = self.compare()
        reverse = build_comparison(
            list(reversed(self.case_paths)),
            list(reversed(self.fingerprint_paths)),
        )
        self.assertEqual(forward, reverse)

    def test_two_cases_never_exceed_hypothesis_authority(self) -> None:
        result = self.compare()
        self.assertIn(result["pattern_assessment"]["status"], {"hypothesis", "none"})
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("pattern_candidate", serialized)
        self.assertNotIn("approved_pattern", serialized)

    def test_proof_is_not_upgraded(self) -> None:
        result = self.compare()
        counts = result["dimensions"]["proof"]["effective_verified_proof_count"]
        self.assertEqual(counts, {"100": 0, "200": 0})
        self.assertTrue(result["validation"]["proof_not_upgraded"])

    def test_privacy_gate_rejects_injected_pii(self) -> None:
        fingerprint = json.loads(
            self.fingerprint_paths[0].read_text(encoding="utf-8")
        )
        fingerprint["content_features"]["content_goal_candidate"] = (
            "联系电话：13812345678"
        )
        write_json(self.fingerprint_paths[0], fingerprint)
        with self.assertRaises(RuntimeError):
            self.compare()

    def test_case_and_fingerprint_hashes_are_traceable(self) -> None:
        result = self.compare()
        for case_id, case_path, fingerprint_path in zip(
            ("100", "200"), self.case_paths, self.fingerprint_paths
        ):
            item = result["input_artifacts"][case_id]
            self.assertEqual(item["approved_case"]["sha256"], sha256(case_path))
            self.assertEqual(item["fingerprint"]["sha256"], sha256(fingerprint_path))
            self.assertEqual(
                item["fingerprint"]["source_case_sha256"], sha256(case_path)
            )


class GeneralizedNewsCrossCaseComparisonTests(unittest.TestCase):
    PRICE_BUNDLE = (
        ROOT
        / "data"
        / "cross_case_research"
        / "news"
        / "price_offer_led_micro_information"
        / "research_input_bundle_v1.json"
    )
    PRICE_COMPARISON = PRICE_BUNDLE.parent / "price_offer_led_cross_case_comparison_v1.json"
    SCENE_BUNDLE = (
        ROOT
        / "data"
        / "cross_case_research"
        / "news"
        / "scene_contrast"
        / "research_input_bundle_v1.json"
    )
    SCENE_COMPARISON = SCENE_BUNDLE.parent / "scene_contrast_cross_case_comparison_v1.json"
    PRICE_APPROVAL = (
        PRICE_BUNDLE.parent
        / "price_offer_led_cross_case_comparison_v1_human_approval_v1.json"
    )
    SCENE_APPROVAL = (
        SCENE_BUNDLE.parent
        / "scene_contrast_cross_case_comparison_v1_human_approval_v1.json"
    )

    def test_generalized_comparator_supports_three_approved_cases(self) -> None:
        for path in (self.PRICE_BUNDLE, self.SCENE_BUNDLE):
            result = build_generalized_research_comparison(path)
            validate_generalized_research_comparison(result)
            self.assertEqual(result["case_count"], 3)
            self.assertEqual(result["status"], "review_required")
            self.assertFalse(result["pattern_candidate_eligibility"]["creates_pattern_candidate"])

    def test_generalized_comparator_is_not_hardcoded_to_exactly_three(self) -> None:
        bundle = json.loads(self.PRICE_BUNDLE.read_text(encoding="utf-8"))
        bundle["cases"] = bundle["cases"][:2]
        bundle["canonical_approved_case_count"] = 2
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "two_case_research_bundle.json"
            write_json(path, bundle)
            result = build_generalized_research_comparison(path)
        self.assertEqual(result["case_count"], 2)
        self.assertTrue(result["validation"]["minimum_two_cases_supported"])
        self.assertFalse(result["validation"]["exact_case_count_hardcoded"])
        self.assertEqual(result["candidate_research_readiness"], "needs_more_evidence")

    def test_majority_similarity_does_not_automatically_become_invariant(self) -> None:
        price = json.loads(self.PRICE_COMPARISON.read_text(encoding="utf-8"))
        scene = json.loads(self.SCENE_COMPARISON.read_text(encoding="utf-8"))
        majority = [
            item
            for result in (price, scene)
            for item in result["variants"]
            if item["status"] == "supported_majority"
        ]
        self.assertTrue(majority)
        self.assertTrue(
            all(not item["eligible_as_candidate_invariant"] for item in majority)
        )

    def test_price_scope_and_scope_beat_fail_closed(self) -> None:
        result = json.loads(self.PRICE_COMPARISON.read_text(encoding="utf-8"))
        self.assertEqual(
            result["scope_statement"]["current_evidence_supports"],
            "price_offer_led_micro_information",
        )
        self.assertEqual(
            result["scope_statement"]["current_evidence_does_not_yet_support"],
            "broader_number_led",
        )
        scope = next(
            item for item in result["variants"] if item["observation_id"] == "PRICE_VAR_002"
        )
        self.assertEqual(scope["support_count"], 1)
        self.assertFalse(scope["eligible_as_candidate_invariant"])
        token_boundary = next(
            item
            for item in result["boundary_conditions"]
            if item["case_id"] == "7640840358842207507"
        )
        self.assertIn(
            "automatic_generic_number_led_scope_expansion",
            token_boundary["attacks"],
        )

    def test_scene_boundary_case_contradicts_transformation_invariant(self) -> None:
        result = json.loads(self.SCENE_COMPARISON.read_text(encoding="utf-8"))
        action = result["transformation_action_status"]
        self.assertEqual(action["status"], "optional_enhancer")
        self.assertTrue(action["invariant_claim_contradicted"])
        self.assertEqual(
            action["valid_without_transformation_action_case_ids"],
            ["7616327461634652005"],
        )
        boundary = result["boundary_variant_findings"][0]
        self.assertTrue(boundary["shared_core_preserved"])

    def test_narration_timing_and_surface_do_not_become_invariants(self) -> None:
        for path in (self.PRICE_COMPARISON, self.SCENE_COMPARISON):
            result = json.loads(path.read_text(encoding="utf-8"))
            narration = next(
                item
                for item in result["candidate_invariants"]
                if "narration" in item["statement"].lower()
            )
            self.assertEqual(narration["status"], "supported_all_cases")
            timing = next(
                item
                for item in result["variants"]
                if item["evidence_dimensions"] == ["timing_and_duration"]
            )
            self.assertFalse(timing["eligible_as_candidate_invariant"])
            diversity = result["structural_similarity_and_surface_diversity"]
            self.assertTrue(diversity["surface_diversity_observed"])
            self.assertFalse(diversity["surface_diversity_is_structural_evidence"])

    def test_comparison_preserves_case_sha_pattern_and_authority_boundaries(self) -> None:
        bundle_paths = (self.PRICE_BUNDLE, self.SCENE_BUNDLE)
        case_paths = []
        for path in bundle_paths:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            case_paths.extend(
                Path(item["case_ref"]["path"]) for item in bundle["cases"]
            )
        before = {str(path): sha256(path) for path in case_paths}
        for path in bundle_paths:
            result = build_generalized_research_comparison(path)
            authority = result["authority"]
            self.assertTrue(authority["approved_cases_only"])
            self.assertTrue(
                all(
                    value is False
                    for key, value in authority.items()
                    if key != "approved_cases_only"
                )
            )
            self.assertFalse(result["effectiveness_boundary"]["effectiveness_claimed"])
            self.assertFalse(result["effectiveness_boundary"]["performance_data_consumed"])
        self.assertEqual(before, {str(path): sha256(path) for path in case_paths})
        for path in case_paths:
            case = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(case["pattern_state"]["pattern_mining_performed"])

    def test_news_readiness_remains_insufficient(self) -> None:
        registry = json.loads(
            (
                ROOT
                / "data"
                / "production_profiles"
                / "production_profile_registry_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            registry["profiles"]["news"]["operational_readiness"],
            "research_coverage_insufficient",
        )
        self.assertEqual(
            registry["profiles"]["news"]["pattern_compatibility_policy"][
                "approved_compatible_pattern_ids"
            ],
            [],
        )

    def test_human_approval_approves_comparison_not_pattern(self) -> None:
        for comparison_path, approval_path in (
            (self.PRICE_COMPARISON, self.PRICE_APPROVAL),
            (self.SCENE_COMPARISON, self.SCENE_APPROVAL),
        ):
            approval = json.loads(approval_path.read_text(encoding="utf-8"))
            validate_comparison_human_approval(
                approval,
                expected_comparison_sha256=sha256(comparison_path),
            )
            self.assertEqual(
                approval["approval_scope"],
                "research_comparison_only_not_pattern_approval",
            )
            self.assertTrue(approval["authority"]["comparison_approved"])
            self.assertFalse(approval["authority"]["pattern_approved"])
            self.assertFalse(
                approval["authority"]["pattern_candidate_created_by_approval"]
            )

    def test_comparison_approval_is_reference_first_and_preserves_source_sha(self) -> None:
        for comparison_path, approval_path in (
            (self.PRICE_COMPARISON, self.PRICE_APPROVAL),
            (self.SCENE_COMPARISON, self.SCENE_APPROVAL),
        ):
            before = sha256(comparison_path)
            rebuilt = build_comparison_human_approval(
                comparison_path,
                reviewer="李健",
                reviewed_at="2026-09-12T00:00:00+00:00",
            )
            self.assertEqual(rebuilt["comparison_ref"]["sha256"], before)
            self.assertFalse(rebuilt["comparison_ref"]["source_comparison_modified"])
            self.assertEqual(sha256(comparison_path), before)


if __name__ == "__main__":
    unittest.main()
