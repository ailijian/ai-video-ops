from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from approve_persona_v1 import approve_persona  # noqa: E402
from build_persona_v1 import build_persona  # noqa: E402
from match_generation_sources_v1 import build_source_plan  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductionFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.persona_input = self.root / "persona_input.json"
        write_json(self.persona_input, self.persona_source())
        self.persona_path, _persona = build_persona(
            self.persona_input,
            self.root / "personas",
            created_at="2026-09-11T00:00:00+00:00",
        )
        self.pattern_path = self.root / "pattern_v1.json"
        self.rejected_path = self.root / "rejected_candidate.json"
        self.case_paths: list[Path] = []
        self.fingerprint_paths: list[Path] = []
        case_ids = ["100", "200", "300"]
        write_json(self.pattern_path, self.pattern(case_ids))
        write_json(
            self.rejected_path,
            {
                "pattern_id": "rejected_pattern",
                "status": "review_rejected",
                "research_disposition": {
                    "retained_hypothesis": {
                        "hypothesis_id": "H002A",
                        "status": "research_hypothesis",
                    }
                },
            },
        )
        for index, case_id in enumerate(case_ids):
            case_path = self.root / f"case_{case_id}.json"
            write_json(
                case_path,
                {
                    "case_id": case_id,
                    "lifecycle": {"status": "approved", "approved": True},
                    "validation": {"passed": True},
                    "quality": {"human_review_completed": True},
                },
            )
            fingerprint_path = self.root / f"fingerprint_{case_id}.json"
            write_json(
                fingerprint_path,
                self.fingerprint(case_id, sha256(case_path), index),
            )
            self.case_paths.append(case_path)
            self.fingerprint_paths.append(fingerprint_path)
        self.mix_request = self.root / "mix.json"
        self.news_request = self.root / "news.json"
        write_json(self.mix_request, self.request("mix", "mix_request"))
        write_json(self.news_request, self.request("news", "news_request"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def fact(value, state: str = "known") -> dict:
        return {"state": state, "value": value, "source_refs": ["fixture"] if state != "unknown" else []}

    def persona_source(self, revision: int = 1) -> dict:
        return {
            "persona_id": "fixture_operator",
            "revision": revision,
            "fixture_only": True,
            "source_type": "test_fixture",
            "facts": {
                "public_display_name": self.fact("Fixture Operator"),
                "company_short_name": self.fact("Fixture Service"),
                "industry": self.fact("plant_service"),
                "years_in_business": self.fact(None, "unknown"),
                "primary_products_or_services": self.fact(["plant service"]),
                "core_audience": self.fact(["office clients"]),
                "customer_pains": self.fact(["maintenance burden"]),
                "differentiators": self.fact(["site assessment"]),
                "brand_story": self.fact("operator service story"),
                "founder_or_operator_story": self.fact("operator joins delivery"),
                "product_or_service_facts": self.fact(["rental", "care"]),
                "process_facts": self.fact(["survey", "setup", "care"]),
                "service_process": self.fact(["survey", "plan", "care"]),
                "forbidden_claims": self.fact(["unsupported performance claim"]),
            },
        }

    @staticmethod
    def pattern(case_ids: list[str]) -> dict:
        return {
            "pattern_id": "pcv1_narration_led_process_projection",
            "status": "approved",
            "scope": {"supported_case_ids": case_ids},
            "effectiveness": {
                "status": "unvalidated",
                "performance_data_used": False,
            },
        }

    @staticmethod
    def fingerprint(case_id: str, case_sha: str, index: int) -> dict:
        return {
            "case_id": case_id,
            "source_case": {
                "status": "approved",
                "approved": True,
                "sha256": case_sha,
            },
            "identity": {"industry": "plant_service" if index == 0 else "food"},
            "narration_features": {"speech_to_video_ratio": 0.8},
            "visual_shot_features": {
                "shot_count": 10,
                "primary_role_counts": {
                    "action": 5,
                    "context": 2,
                    "product": 2,
                    "persona": 1,
                },
            },
            "content_features": {
                "claims": ["case-specific fact: operating for 21 years"]
            },
            "structure_features": {"audio_role": "narration semantic spine"},
            "pattern_mining_contract": {"this_artifact_is_not_a_pattern": True},
        }

    @staticmethod
    def request(profile: str, request_id: str) -> dict:
        return {
            "schema_version": "generation-request-v1.0",
            "request_id": request_id,
            "persona_id": "fixture_operator",
            "persona_revision": 1,
            "profile": profile,
            "quantity": 10,
            "platform": "douyin",
            "content_intent": "mixed",
        }

    def approve(self) -> None:
        approve_persona(
            self.persona_path,
            "Fixture Reviewer",
            "Fixture approval",
            "2026-09-11T00:01:00+00:00",
        )

    def match(self, request_path: Path | None = None, pattern_paths=None) -> dict:
        return build_source_plan(
            self.persona_path,
            request_path or self.mix_request,
            pattern_paths or [self.pattern_path],
            self.case_paths,
            self.fingerprint_paths,
            [self.rejected_path],
        )

    def test_review_required_persona_cannot_match(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Approved"):
            self.match()

    def test_approved_persona_can_match(self) -> None:
        self.approve()
        plan = self.match()
        self.assertEqual(plan["coverage"]["status"], "supported")

    def test_approved_revision_cannot_be_silently_overwritten(self) -> None:
        self.approve()
        with self.assertRaisesRegex(RuntimeError, "silently overwritten"):
            build_persona(self.persona_input, self.root / "personas")
        revision_two_input = self.root / "persona_v2_input.json"
        revision_two = self.persona_source(revision=2)
        revision_two["facts"]["differentiators"] = self.fact(["new approved input"])
        write_json(revision_two_input, revision_two)
        revision_two_path, revision_two_persona = build_persona(
            revision_two_input,
            self.root / "personas",
            self.persona_path,
            "2026-09-11T00:02:00+00:00",
        )
        self.assertTrue(revision_two_path.is_file())
        self.assertEqual(revision_two_persona["revision"], 2)

    def test_unknown_fact_is_null_and_never_completed(self) -> None:
        persona = json.loads(self.persona_path.read_text(encoding="utf-8"))
        fact = persona["facts"]["years_in_business"]
        self.assertEqual(fact["state"], "unknown")
        self.assertIsNone(fact["value"])

    def test_case_fact_does_not_transfer_to_persona_or_plan(self) -> None:
        self.approve()
        plan = self.match()
        serialized = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn("operating for 21 years", serialized)
        self.assertFalse(plan["persona"]["fact_values_copied_to_plan"])
        self.assertTrue(plan["generation_constraints"]["case_facts_must_not_transfer"])

    def test_rejected_pattern_cannot_be_pattern_input(self) -> None:
        self.approve()
        with self.assertRaisesRegex(RuntimeError, "not Approved"):
            self.match(pattern_paths=[self.rejected_path])

    def test_research_hypothesis_cannot_be_pattern_input(self) -> None:
        self.approve()
        hypothesis_path = self.root / "hypothesis.json"
        write_json(
            hypothesis_path,
            {
                "pattern_id": "H002A",
                "status": "research_hypothesis",
                "effectiveness": {"status": "unvalidated"},
            },
        )
        with self.assertRaisesRegex(RuntimeError, "not Approved"):
            self.match(pattern_paths=[hypothesis_path])

    def test_news_request_is_insufficient_without_mix_fallback(self) -> None:
        self.approve()
        plan = self.match(self.news_request)
        self.assertEqual(plan["coverage"]["code"], "research_coverage_insufficient")
        self.assertEqual(plan["selected_patterns"], [])
        self.assertEqual(plan["selected_cases"], [])
        self.assertTrue(plan["validation"]["news_does_not_fallback_to_mix"])

    def test_mix_operator_persona_selects_approved_pattern(self) -> None:
        self.approve()
        plan = self.match()
        self.assertEqual(
            plan["selected_patterns"][0]["pattern_id"],
            "pcv1_narration_led_process_projection",
        )

    def test_effectiveness_never_participates_in_ranking(self) -> None:
        self.approve()
        plan = self.match()
        self.assertFalse(plan["ranking_policy"]["effectiveness_used"])
        self.assertFalse(plan["ranking_policy"]["performance_metrics_used"])
        for case in plan["selected_cases"]:
            self.assertNotIn("effectiveness", case["ranking_components"])

    def test_matching_is_deterministic(self) -> None:
        self.approve()
        self.assertEqual(self.match(), self.match())

    def test_sha_lineage_is_complete(self) -> None:
        self.approve()
        plan = self.match()
        self.assertEqual(plan["persona"]["persona_sha"], sha256(self.persona_path))
        self.assertEqual(plan["request"]["request_sha"], sha256(self.mix_request))
        self.assertEqual(plan["selected_patterns"][0]["approved_pattern_sha"], sha256(self.pattern_path))
        for item in plan["eligible_case_pool"]:
            index = [path.stem.split("_")[-1] for path in self.case_paths].index(item["case_id"])
            self.assertEqual(item["approved_case_sha"], sha256(self.case_paths[index]))
            self.assertEqual(item["fingerprint_sha"], sha256(self.fingerprint_paths[index]))

    def test_plan_supports_multiple_eligible_cases_and_rotation(self) -> None:
        self.approve()
        plan = self.match()
        self.assertEqual(len(plan["eligible_case_pool"]), 3)
        self.assertTrue(plan["rotation"]["case_rotation_enabled"])
        self.assertEqual(len(plan["rotation"]["case_rotation_order"]), 3)

    def test_raw_sources_and_remote_model_are_never_used(self) -> None:
        self.approve()
        plan = self.match()
        authority = plan["authority"]
        self.assertFalse(authority["raw_whisper_read"])
        self.assertFalse(authority["raw_visual_evidence_read"])
        self.assertFalse(authority["remote_model_call_performed"])
        self.assertFalse(authority["script_generation_performed"])

    def test_frontline_speaker_overlay_requires_approved_business_lineage(self) -> None:
        self.approve()
        speaker_input = self.root / "speaker_input.json"
        write_json(
            speaker_input,
            {
                "persona_id": "fixture_frontline_speaker",
                "revision": 1,
                "persona_scope": "speaker",
                "speaker_type": "frontline_expert",
                "business_persona_ref": "fixture_operator",
                "fixture_only": True,
                "source_type": "test_fixture",
                "facts": {
                    "public_display_name": self.fact("Fixture Speaker"),
                    "public_role": self.fact("主厨"),
                    "speaker_role_facts": self.fact(["负责窗口烹饪"]),
                    "first_person_allowed_topics": self.fact(["现场烹饪流程"]),
                    "first_person_forbidden_claims": self.fact(["我是老板"]),
                    "unknown_facts": self.fact(["从业年限", "是否创始人"]),
                },
            },
        )
        speaker_path, speaker = build_persona(
            speaker_input,
            self.root / "personas",
            created_at="2026-09-11T00:02:00+00:00",
            business_persona_path=self.persona_path,
        )
        self.assertEqual(speaker["persona_scope"], "speaker")
        self.assertFalse(speaker["speaker_authority"]["business_facts_copied"])
        approve_persona(
            speaker_path,
            "Fixture Reviewer",
            "Fixture Speaker approval",
            "2026-09-11T00:03:00+00:00",
        )
        request = self.request("mix", "speaker_mix_request")
        request["speaker_persona"] = "fixture_frontline_speaker"
        request["speaker_persona_revision"] = 1
        request_path = self.root / "speaker_mix_request.json"
        write_json(request_path, request)
        plan = build_source_plan(
            self.persona_path,
            request_path,
            [self.pattern_path],
            self.case_paths,
            self.fingerprint_paths,
            [self.rejected_path],
            speaker_path,
        )
        self.assertEqual(plan["speaker_persona"]["speaker_type"], "frontline_expert")
        self.assertEqual(plan["speaker_persona"]["speaker_sha"], sha256(speaker_path))
        self.assertTrue(plan["validation"]["speaker_business_lineage_valid"])
        self.assertFalse(plan["authority"]["speaker_business_facts_copied"])


if __name__ == "__main__":
    unittest.main()
