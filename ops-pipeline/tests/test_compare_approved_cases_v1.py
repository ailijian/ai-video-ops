from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compare_approved_cases_v1 import build_comparison  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
