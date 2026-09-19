from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from authority_test_support import live_authority_root

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from mine_pattern_candidates_v1 import (  # noqa: E402
    build_news_pattern_candidate,
    build_pattern_research,
    validate_news_pattern_candidate,
)


ROOT = live_authority_root()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PatternResearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.case_paths: list[Path] = []
        self.fingerprint_paths: list[Path] = []
        for index, case_id in enumerate(("100", "200", "300"), start=1):
            case_path = self.root / f"case_{case_id}.json"
            case = {
                "case_id": case_id,
                "lifecycle": {"status": "approved", "approved": True},
                "validation": {"passed": True},
                "quality": {
                    "human_review_completed": True,
                    "verified_proof_count": 0,
                },
                "pattern_state": {"pattern_mining_performed": False},
            }
            write_json(case_path, case)
            fingerprint_path = self.root / f"fingerprint_{case_id}.json"
            write_json(
                fingerprint_path,
                self.fingerprint(case_id, sha256(case_path), index),
            )
            self.case_paths.append(case_path)
            self.fingerprint_paths.append(fingerprint_path)
        self.comparison_path = self.root / "comparison.json"
        write_json(
            self.comparison_path,
            {
                "case_ids": ["100", "200"],
                "authority": {"remote_model_used": False},
                "pattern_assessment": {
                    "status": "hypothesis",
                    "hypotheses": [{"id": "H001"}, {"id": "H002"}],
                },
                "validation": {"passed": True},
            },
        )

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
                "industry": "food" if index < 3 else "plant_service",
                "duration_seconds": 20.0 * index,
            },
            "narration_features": {
                "segment_count": 5,
                "total_speech_seconds": 15.0,
                "speech_to_video_ratio": 0.75,
            },
            "visual_shot_features": {
                "shot_count": 10,
                "shot_duration_stats": {"mean": 2.0, "median": 1.5},
                "shots_under_1s_ratio": 0.2,
                "primary_role_counts": {"action": 6, "context": 4},
                "onscreen_text_shot_ratio": 0.5,
            },
            "content_features": {
                "content_goal_candidate": "business service explanation",
                "claims": [{"claim": "service claim", "status": "candidate"}],
                "verified_proof_count": 0,
                "proof_shot_refs": [],
                "has_explicit_cta": False,
            },
            "structure_features": {
                "structure_signature": "hook>development>payoff",
                "hook_modalities": ["audio", "visual_text", "visual_scene"],
                "audio_role": "Narration carries the main semantic line.",
            },
            "audio_visual_features": {
                "scene_relation_counts": {"supplement": 10},
                "narration_and_shots_are_separate_tracks": True,
                "shot_to_narration_cardinality": "many_to_many",
            },
            "pattern_mining_contract": {
                "eligible_for_pattern_mining": True,
                "this_artifact_is_not_a_pattern": True,
            },
            "provenance": {"approved_case_sha256": case_hash},
        }

    def build(self) -> tuple[dict, list[dict]]:
        return build_pattern_research(
            self.case_paths,
            self.fingerprint_paths,
            self.comparison_path,
        )

    def test_fewer_than_three_cases_cannot_create_candidate(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "At least three"):
            build_pattern_research(
                self.case_paths[:2],
                self.fingerprint_paths[:2],
                self.comparison_path,
            )

    def test_non_approved_case_is_rejected(self) -> None:
        case = json.loads(self.case_paths[0].read_text(encoding="utf-8"))
        case["lifecycle"] = {"status": "review_required", "approved": False}
        write_json(self.case_paths[0], case)
        with self.assertRaisesRegex(RuntimeError, "not Approved"):
            self.build()

    def test_missing_fingerprint_is_rejected(self) -> None:
        missing = self.root / "missing.json"
        with self.assertRaises(FileNotFoundError):
            build_pattern_research(
                self.case_paths,
                [self.fingerprint_paths[0], self.fingerprint_paths[1], missing],
                self.comparison_path,
            )

    def test_input_order_does_not_change_research(self) -> None:
        forward = self.build()
        reverse = build_pattern_research(
            list(reversed(self.case_paths)),
            list(reversed(self.fingerprint_paths)),
            self.comparison_path,
        )
        self.assertEqual(forward, reverse)

    def test_candidates_have_three_supporting_cases_and_never_approve(self) -> None:
        research, candidates = self.build()
        self.assertEqual(research["pattern_candidate_count"], 2)
        for candidate in candidates:
            self.assertGreaterEqual(candidate["scope"]["supported_case_count"], 3)
            self.assertEqual(candidate["status"], "candidate")
            self.assertTrue(candidate["authority"]["candidate_only"])
            self.assertTrue(candidate["authority"]["human_review_required"])
            self.assertFalse(candidate["authority"]["auto_approval_performed"])

    def test_process_is_not_upgraded_to_proof(self) -> None:
        research, candidates = self.build()
        self.assertTrue(research["validation"]["proof_not_upgraded"])
        self.assertEqual(
            set(research["validation"]["effective_verified_proof_counts"].values()),
            {0},
        )
        self.assertTrue(
            all(
                candidate["authority"]["proof_reinterpreted"] is False
                for candidate in candidates
            )
        )

    def test_effectiveness_is_always_unvalidated(self) -> None:
        research, candidates = self.build()
        self.assertEqual(research["effectiveness_authority"]["status"], "unvalidated")
        self.assertFalse(research["effectiveness_authority"]["performance_data_used"])
        for candidate in candidates:
            self.assertEqual(candidate["effectiveness"]["status"], "unvalidated")
            self.assertFalse(candidate["effectiveness"]["performance_data_used"])

    def test_raw_authorities_are_not_read(self) -> None:
        research, _candidates = self.build()
        authority = research["authority"]
        self.assertFalse(authority["raw_whisper_read"])
        self.assertFalse(authority["raw_visual_evidence_read"])
        self.assertFalse(authority["storyboard_raw_interpretation_read"])
        self.assertTrue(research["validation"]["raw_authority_not_read"])

    def test_sha_lineage_is_complete(self) -> None:
        research, candidates = self.build()
        for source, case_path, fingerprint_path in zip(
            research["case_sources"], self.case_paths, self.fingerprint_paths
        ):
            self.assertEqual(source["approved_case_sha"], sha256(case_path))
            self.assertEqual(source["fingerprint_sha"], sha256(fingerprint_path))
        self.assertEqual(
            research["prior_comparison"]["sha256"], sha256(self.comparison_path)
        )
        for candidate in candidates:
            self.assertEqual(set(candidate["lineage"]["approved_case_sha256"]), {"100", "200", "300"})
            self.assertEqual(set(candidate["lineage"]["fingerprint_sha256"]), {"100", "200", "300"})

    def test_privacy_gate_rejects_injected_pii(self) -> None:
        fingerprint = json.loads(
            self.fingerprint_paths[0].read_text(encoding="utf-8")
        )
        fingerprint["content_features"]["content_goal_candidate"] = (
            "contact phone: 13812345678"
        )
        write_json(self.fingerprint_paths[0], fingerprint)
        with self.assertRaises(RuntimeError):
            self.build()

    def test_case_three_contradiction_weakens_hypotheses_and_blocks_candidates(self) -> None:
        fingerprint = json.loads(
            self.fingerprint_paths[2].read_text(encoding="utf-8")
        )
        fingerprint["visual_shot_features"]["primary_role_counts"] = {
            "context": 10
        }
        fingerprint["audio_visual_features"] = {
            "scene_relation_counts": {"independent": 10},
            "narration_and_shots_are_separate_tracks": False,
            "shot_to_narration_cardinality": "one_to_one",
        }
        fingerprint["content_features"]["has_explicit_cta"] = True
        write_json(self.fingerprint_paths[2], fingerprint)

        research, candidates = self.build()
        self.assertEqual(research["hypothesis_review"]["H001"]["status"], "weakened")
        self.assertEqual(research["hypothesis_review"]["H002"]["status"], "weakened")
        self.assertEqual(research["pattern_candidate_count"], 0)
        self.assertEqual(candidates, [])

    def test_remote_model_is_never_used(self) -> None:
        research, _candidates = self.build()
        self.assertFalse(research["authority"]["remote_model_used"])
        self.assertFalse(research["validation"]["remote_model_call_performed"])


@pytest.mark.live_authority
class NewsPatternCandidateTests(unittest.TestCase):
    PRICE_ROOT = (
        ROOT
        / "data"
        / "cross_case_research"
        / "news"
        / "price_offer_led_micro_information"
    )
    PRICE_COMPARISON = PRICE_ROOT / "price_offer_led_cross_case_comparison_v1.json"
    PRICE_APPROVAL = (
        PRICE_ROOT / "price_offer_led_cross_case_comparison_v1_human_approval_v1.json"
    )
    PRICE_CANDIDATE = (
        ROOT
        / "data"
        / "patterns"
        / "candidates"
        / "pcv1_news_price_offer_led_micro_information"
        / "pattern_candidate_v1.json"
    )
    PRICE_PACK = PRICE_CANDIDATE.parent / "pattern_candidate_human_review_pack_v1.md"
    SCENE_ROOT = ROOT / "data" / "cross_case_research" / "news" / "scene_contrast"
    SCENE_COMPARISON = SCENE_ROOT / "scene_contrast_cross_case_comparison_v1.json"
    SCENE_APPROVAL = (
        SCENE_ROOT / "scene_contrast_cross_case_comparison_v1_human_approval_v1.json"
    )
    SCENE_CANDIDATE = (
        ROOT
        / "data"
        / "patterns"
        / "candidates"
        / "pcv1_news_scene_contrast"
        / "pattern_candidate_v1.json"
    )
    SCENE_PACK = SCENE_CANDIDATE.parent / "pattern_candidate_human_review_pack_v1.md"

    def load_candidates(self) -> tuple[dict, dict]:
        return (
            json.loads(self.PRICE_CANDIDATE.read_text(encoding="utf-8")),
            json.loads(self.SCENE_CANDIDATE.read_text(encoding="utf-8")),
        )

    def test_candidates_stop_at_review_required_not_approved_pattern(self) -> None:
        for candidate in self.load_candidates():
            validate_news_pattern_candidate(candidate)
            self.assertEqual(candidate["status"], "review_required")
            self.assertEqual(candidate["candidate_state"], "candidate")
            self.assertEqual(candidate["compatible_profile_candidate"], ["news"])
            self.assertTrue(candidate["authority"]["candidate_only"])
            self.assertFalse(candidate["authority"]["approved_pattern"])
            self.assertFalse(candidate["authority"]["auto_approved"])

    def test_price_candidate_scope_and_non_invariants_are_narrow(self) -> None:
        price, _scene = self.load_candidates()
        invariants = price["definition"]["candidate_invariants"]
        self.assertEqual(price["scope"]["scope_limitation"], "price_offer_led_only")
        self.assertEqual(
            price["scope"]["explicitly_not_supported"], "generic_number_led"
        )
        self.assertFalse(any("explicit_scope" in value for value in invariants))
        self.assertFalse(any("close" in value for value in invariants))
        self.assertIn(
            "independent_explicit_scope_beat",
            price["definition"]["explicitly_not_frozen"],
        )
        self.assertIn("explicit_close", price["definition"]["explicitly_not_frozen"])

    def test_scene_candidate_excludes_transformation_and_retains_boundary(self) -> None:
        _price, scene = self.load_candidates()
        invariants = scene["definition"]["candidate_invariants"]
        self.assertFalse(any("transformation" in value for value in invariants))
        self.assertEqual(scene["transformation_action"]["status"], "optional_enhancer")
        self.assertFalse(scene["transformation_action"]["candidate_invariant"])
        boundary = scene["boundary_evidence"]
        self.assertEqual(boundary[0]["case_id"], "7616327461634652005")
        self.assertTrue(boundary[0]["shared_core_preserved"])

    def test_scene_same_subject_identity_remains_unresolved(self) -> None:
        _price, scene = self.load_candidates()
        question = scene["unresolved_questions"][0]
        self.assertEqual(question["question_id"], "same_subject_identity_requirement")
        self.assertEqual(question["status"], "unresolved")
        self.assertIsNone(question["frozen_answer"])

    def test_scene_contrast_does_not_become_verified_proof(self) -> None:
        _price, scene = self.load_candidates()
        proof = scene["proof_boundary"]
        self.assertTrue(proof["observable_state_difference"])
        self.assertFalse(proof["state_difference_is_automatically_verified_proof"])
        self.assertFalse(proof["causality_proven"])
        self.assertFalse(proof["service_effect_proven"])
        self.assertFalse(proof["commercial_result_proven"])

    def test_candidates_have_no_effectiveness_or_performance_authority(self) -> None:
        for candidate in self.load_candidates():
            self.assertEqual(candidate["effectiveness"]["status"], "unvalidated")
            self.assertFalse(candidate["effectiveness"]["performance_data_available"])
            self.assertFalse(candidate["effectiveness"]["performance_data_used"])
            self.assertFalse(candidate["authority"]["effectiveness_claimed"])
            self.assertFalse(candidate["authority"]["performance_authority_created"])
            self.assertFalse(candidate["authority"]["remote_model_used"])

    def test_candidate_lineage_preserves_cases_comparisons_and_mix_pattern(self) -> None:
        inputs = (
            (self.PRICE_COMPARISON, self.PRICE_APPROVAL),
            (self.SCENE_COMPARISON, self.SCENE_APPROVAL),
        )
        case_paths: set[Path] = set()
        for candidate in self.load_candidates():
            for item in candidate["evidence"]:
                case_paths.add(Path(item["approved_case_ref"]["path"]))
        tracked_paths = list(case_paths) + [
            self.PRICE_COMPARISON,
            self.SCENE_COMPARISON,
            ROOT
            / "data"
            / "patterns"
            / "approved"
            / "pcv1_narration_led_process_projection"
            / "pattern_v1.json",
        ]
        before = {str(path): sha256(path) for path in tracked_paths}
        for comparison, approval in inputs:
            rebuilt = build_news_pattern_candidate(comparison, approval)
            validate_news_pattern_candidate(rebuilt)
        self.assertEqual(before, {str(path): sha256(path) for path in tracked_paths})
        for candidate in self.load_candidates():
            self.assertEqual(
                candidate["lineage"]["comparison_ref"]["sha256"],
                sha256(Path(candidate["lineage"]["comparison_ref"]["path"])),
            )
            self.assertEqual(
                set(candidate["lineage"]["case_sha256"]),
                set(candidate["scope"]["supported_case_ids"]),
            )

    def test_human_review_packs_are_self_contained(self) -> None:
        for pack_path in (self.PRICE_PACK, self.SCENE_PACK):
            text = pack_path.read_text(encoding="utf-8")
            for heading in (
                "## A. Pattern ID",
                "## B. Compatible Profile Candidate",
                "## C. Evidence Cases",
                "## D. Comparison Source",
                "## E. Candidate Summary",
                "## F. Candidate Invariants",
                "## G. Variants",
                "## H. Boundary Evidence",
                "## I. Counterexamples / Attacks",
                "## J. Scope",
                "## K. Scope Limitations",
                "## L. Unresolved Questions",
                "## M. Proof / Effectiveness Boundary",
                "## N. Production Implications",
                "## O. Explicitly NOT Frozen",
            ):
                self.assertIn(heading, text)
            self.assertIn("Review Required / Not Approved", text)

    def test_news_readiness_and_event_direction_remain_unchanged(self) -> None:
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
        self.assertFalse(
            (
                ROOT
                / "data"
                / "patterns"
                / "candidates"
                / "pcv1_news_event_explanation"
            ).exists()
        )
        for candidate in self.load_candidates():
            self.assertFalse(candidate["authority"]["news_generation_performed"])
            self.assertFalse(candidate["authority"]["news_excel_export_performed"])


if __name__ == "__main__":
    unittest.main()
