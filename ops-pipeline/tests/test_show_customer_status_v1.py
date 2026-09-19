from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from authority_test_support import FIXTURE_ROOT

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = FIXTURE_ROOT
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import show_customer_status_v1 as status_v1  # noqa: E402


BUSINESS_ID = "fixture_business_001"
SPEAKER_ID = "fixture_speaker_001"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CurrentCustomerStatusV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.status = status_v1.build_customer_status(ROOT, BUSINESS_ID)

    def test_current_personas_resolve_to_approved_fixture_revision(self) -> None:
        truth = self.status["customer_truth"]
        self.assertEqual(truth["business_persona"]["revision"], 1)
        self.assertEqual(truth["business_persona"]["status"], "APPROVED")
        self.assertEqual(truth["speaker_persona"]["persona_id"], SPEAKER_ID)
        self.assertEqual(truth["speaker_persona"]["revision"], 1)
        self.assertEqual(truth["speaker_persona"]["status"], "APPROVED")

    def test_ledger_uses_actual_entries_not_stale_validation_count(self) -> None:
        content = self.status["content"]
        self.assertEqual(content["ledger_entries"], 1)
        self.assertEqual(content["legacy_validation_entry_count"], 1)

    def test_capacity_and_latest_mix_resolve_through_lineage(self) -> None:
        content = self.status["content"]
        self.assertEqual(content["remaining_high_quality_novel_capacity"], 7)
        self.assertEqual(content["latest_approved_mix"]["request_id"], "fixture_mix_request_001")
        self.assertEqual(content["latest_exported_mix"]["request_id"], "fixture_mix_request_001")
        self.assertEqual(content["latest_exported_mix"]["status"], "APPROVED")
        self.assertEqual(content["latest_exported_mix"]["export_status"], "EXPORTED")

    def test_footage_and_rights_are_bound_to_active_batch(self) -> None:
        footage = self.status["footage"]
        self.assertEqual(footage["planning"], "APPROVED")
        self.assertEqual(footage["capture_missions"], 1)
        self.assertEqual(footage["capture_pack_status"], "READY_TO_SEND")
        self.assertFalse(footage["sent"])
        self.assertEqual(footage["registered_assets"], 0)
        self.assertEqual(footage["eligible_assets"], 0)
        self.assertEqual(footage["coverage"]["covered"], 0)
        self.assertEqual(footage["coverage"]["capture_required"], 1)
        self.assertEqual(footage["coverage"]["total"], 1)
        self.assertEqual(self.status["rights"]["speaker_media"], "REVIEW_REQUIRED")

    def test_creative_status_preserves_narrow_news_boundary(self) -> None:
        creative = self.status["creative"]
        self.assertEqual(creative["mix"], "AVAILABLE")
        self.assertEqual(creative["news_price"], "VALIDATED")
        self.assertEqual(
            creative["news_scene_contrast"],
            "PENDING",
        )

    def test_hold_overrides_normal_execution_with_exactly_one_primary_action(self) -> None:
        self.assertTrue(self.status["operational_hold"]["active"])
        self.assertEqual(
            self.status["primary_next_action"], "WAIT_FOR_OPERATOR_RELEASE"
        )
        self.assertEqual(
            self.status["would_be_next_action"], "SEND_CUSTOMER_CAPTURE_PACK"
        )
        self.assertIsInstance(self.status["primary_next_action"], str)

    def test_explicit_release_projection_restores_would_be_action_without_writing(self) -> None:
        inactive = {
            "schema_version": "operational-controls-v1",
            "business_id": BUSINESS_ID,
            "operational_hold": {
                "active": False,
                "reason": "customer outreach intentionally deferred",
                "set_by": "Human Operator",
                "set_at": "2026-09-13T00:00:00+00:00",
                "release_requires": "explicit_operator_release",
            },
            "updated_at": "2026-09-13T00:01:00+00:00",
            "last_action": "release_hold",
            "last_actor": "Human Operator",
            "history": [],
        }
        control_path = ROOT / "data" / "operations" / BUSINESS_ID / "operational_controls_v1.json"
        with patch.object(status_v1, "load_controls", return_value=(inactive, control_path)):
            status = status_v1.build_customer_status(ROOT, BUSINESS_ID)

        self.assertEqual(status["primary_next_action"], "SEND_CUSTOMER_CAPTURE_PACK")
        self.assertIsNone(status["would_be_next_action"])

    def test_status_read_is_hash_stable_and_calls_zero_models(self) -> None:
        paths = [
            ROOT / ref
            for ref in self.status["evidence_refs"]
            if not Path(ref).is_absolute()
        ]
        before = {path: sha256(path) for path in paths}

        second = status_v1.build_customer_status(ROOT, BUSINESS_ID)

        self.assertEqual(before, {path: sha256(path) for path in paths})
        self.assertEqual(second["model_calls"], {"remote": 0, "local": 0})


class PersonaResolverFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_approved_persona(
        self, directory: str, persona_id: str, revision: int, *, receipt: bool
    ) -> Path:
        path = self.root / "data" / "personas" / persona_id / directory / "persona_v1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        persona = {
            "schema_version": "persona-v1.0",
            "persona_id": persona_id,
            "revision": revision,
            "persona_scope": "business",
            "lifecycle": {"status": "approved", "approved": True},
            "approval": {"human_gate": True},
            "provenance": {"content_sha256": f"content-{directory}"},
            "revision_lineage": {"silent_overwrite_allowed": False},
        }
        path.write_text(json.dumps(persona, indent=2), encoding="utf-8")
        if receipt:
            receipt_path = path.parent / "approval_receipt.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "schema_version": "persona-approval-receipt-v1.0",
                        "persona_id": persona_id,
                        "revision": revision,
                        "decision": "approved",
                        "human_gate": True,
                        "persona_sha256_after_approval": sha256(path),
                        "content_sha256": f"content-{directory}",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return path

    def test_approval_receipt_is_required(self) -> None:
        self.write_approved_persona("revision_a", "business_a", 1, receipt=False)
        with self.assertRaisesRegex(
            status_v1.AuthorityResolutionError, "missing its approval receipt"
        ):
            status_v1.resolve_current_persona(self.root, "business_a", "business")

    def test_duplicate_explicit_revision_fails_closed(self) -> None:
        self.write_approved_persona("revision_a", "business_a", 2, receipt=True)
        self.write_approved_persona("revision_b", "business_a", 2, receipt=True)
        with self.assertRaises(status_v1.AuthorityResolutionError) as caught:
            status_v1.resolve_current_persona(self.root, "business_a", "business")
        self.assertEqual(caught.exception.code, "CURRENT_AUTHORITY_AMBIGUITY")
        blocked = status_v1.blocked_status("business_a", caught.exception)
        self.assertEqual(blocked["primary_next_action"], "RESOLVE_AUTHORITY_BLOCKER")
        self.assertNotEqual(
            blocked["primary_next_action"], "WAIT_FOR_OPERATOR_RELEASE"
        )


if __name__ == "__main__":
    unittest.main()
