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
    REJECTED_PATTERN_ID,
    approve_pattern,
    reject_candidate,
)


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


if __name__ == "__main__":
    unittest.main()
