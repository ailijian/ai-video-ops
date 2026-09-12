from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_mix_scripts_v1 import (  # noqa: E402
    build_news_price_repurpose_plan,
    inspect_xlsx_headers,
    run_news_production_mvp_validation,
)
from match_generation_sources_v1 import (  # noqa: E402
    NEWS_PRICE_PATTERN_ID,
    NEWS_SCENE_PATTERN_ID,
    load_approved_persona,
    load_request,
    selected_content_pattern_compatibility,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NewsProductionMvpV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.output_root = Path(cls.temp.name) / "news_mvp"
        cls.paths = {
            "persona": ROOT
            / "data"
            / "personas"
            / "shufang_zhiyuan_community_canteen"
            / "revision_0001"
            / "persona_v1.json",
            "speaker": ROOT
            / "data"
            / "personas"
            / "lin_dongfang_frontline_chef"
            / "revision_0001"
            / "persona_v1.json",
            "novel_request": ROOT
            / "data"
            / "generation_requests"
            / "real_shufang_news_validation_novel_001"
            / "generation_request_v1.json",
            "repurpose_request": ROOT
            / "data"
            / "generation_requests"
            / "real_shufang_news_validation_repurpose_001"
            / "generation_request_v1.json",
            "content_plan": ROOT
            / "data"
            / "content_plans"
            / "real_shufang_mix_002"
            / "revisions"
            / "v1_1_1"
            / "content_plan_v1_1_1.json",
            "ledger": ROOT
            / "data"
            / "content_ledgers"
            / "shufang_zhiyuan_community_canteen"
            / "content_ledger_v1.json",
            "registry": ROOT
            / "data"
            / "production_profiles"
            / "production_profile_registry_v1.json",
            "coverage": ROOT
            / "data"
            / "creative_coverage"
            / "revisions"
            / "news_pattern_approval_creative_coverage_update_v1.json",
            "price_pattern": ROOT
            / "data"
            / "patterns"
            / "approved"
            / NEWS_PRICE_PATTERN_ID
            / "pattern_v1.json",
            "scene_pattern": ROOT
            / "data"
            / "patterns"
            / "approved"
            / NEWS_SCENE_PATTERN_ID
            / "pattern_v1.json",
            "approved_batch": ROOT
            / "data"
            / "generation_batches"
            / "real_shufang_mix_001"
            / "revisions"
            / "revision_0005"
            / "approved_generation_batch_v1.json",
            "export_receipt": ROOT
            / "output"
            / "real_shufang_mix_001_approved_mix_scripts.export_receipt.json",
            "news_template": ROOT / "output" / "新闻体视频制作文案导入模板.xlsx",
            "mix_template": ROOT
            / "output"
            / "素材混剪&数字人口播混剪文案导入模板.xlsx",
            "mix_export": ROOT
            / "output"
            / "real_shufang_mix_001_approved_mix_scripts.xlsx",
            "mix_pattern": ROOT
            / "data"
            / "patterns"
            / "approved"
            / "pcv1_narration_led_process_projection"
            / "pattern_v1.json",
        }
        cls.source_hashes = {
            name: sha256(path) for name, path in cls.paths.items()
        }
        args = SimpleNamespace(
            persona=str(cls.paths["persona"]),
            speaker_persona=str(cls.paths["speaker"]),
            novel_request=str(cls.paths["novel_request"]),
            repurpose_request=str(cls.paths["repurpose_request"]),
            content_plan=str(cls.paths["content_plan"]),
            content_ledger=str(cls.paths["ledger"]),
            production_profile_registry=str(cls.paths["registry"]),
            creative_coverage_update=str(cls.paths["coverage"]),
            news_pattern=[
                str(cls.paths["price_pattern"]),
                str(cls.paths["scene_pattern"]),
            ],
            historical_approved_batch=str(cls.paths["approved_batch"]),
            historical_export_receipt=str(cls.paths["export_receipt"]),
            news_template=str(cls.paths["news_template"]),
            output_root=str(cls.output_root),
        )
        cls.result = run_news_production_mvp_validation(args)
        cls.track_a = cls.result["track_a"]
        cls.track_b = cls.result["track_b"]
        cls.dry_run = cls.result["dry_run"]
        cls.registry = read_json(cls.paths["registry"])
        cls.price_pattern = read_json(cls.paths["price_pattern"])
        cls.scene_pattern = read_json(cls.paths["scene_pattern"])
        cls.persona, _ = load_approved_persona(cls.paths["persona"], "business")
        cls.speaker, _ = load_approved_persona(cls.paths["speaker"], "speaker")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_01_news_target_profile_and_default_reuse_intent_supported(self) -> None:
        request = read_json(self.paths["novel_request"])
        request.pop("reuse_intent")
        path = self.output_root / "default_request.json"
        path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        loaded, _ = load_request(path, self.persona, self.speaker)
        self.assertEqual(loaded["target_profile"], "news")
        self.assertEqual(loaded["reuse_intent"], "novel_content")

    def test_02_novel_request_does_not_reuse_mix_history(self) -> None:
        self.assertFalse(
            self.track_a["historical_exposure_policy"][
                "historical_price_content_used_as_novel"
            ]
        )
        self.assertEqual(self.track_a["selected_concepts"], [])

    def test_03_profile_switch_does_not_reset_novelty(self) -> None:
        policy = self.registry["cross_profile_semantic_policy"]
        self.assertFalse(policy["profile_change_resets_novelty"])
        self.assertTrue(self.track_a["historical_exposure_policy"]["mix_history_visible_to_news"])

    def test_04_track_a_returns_zero_capacity(self) -> None:
        self.assertEqual(self.track_a["capacity"]["news_novel_capacity"], 0)
        self.assertEqual(self.track_a["capacity"]["selected_quantity"], 0)

    def test_05_zero_capacity_is_valid_without_padding(self) -> None:
        capacity = self.track_a["capacity"]
        self.assertTrue(capacity["zero_capacity_is_valid"])
        self.assertEqual(capacity["status"], "capacity_limited")
        self.assertFalse(capacity["padding_generated"])

    def test_06_repurpose_requires_explicit_reuse_intent(self) -> None:
        request = read_json(self.paths["repurpose_request"])
        request["reuse_intent"] = "novel_content"
        with self.assertRaisesRegex(RuntimeError, "explicit cross_profile_repurpose"):
            build_news_price_repurpose_plan(
                request, {}, {}, {}, [], {}, {}, []
            )

    def test_07_repurpose_semantic_novelty_is_false(self) -> None:
        declaration = self.track_b["reuse_declaration"]
        self.assertEqual(declaration["reuse_intent"], "cross_profile_repurpose")
        self.assertFalse(declaration["semantic_novelty"])
        self.assertTrue(declaration["historical_content_reused"])

    def test_08_repurpose_adds_no_novel_capacity_or_opportunity(self) -> None:
        declaration = self.track_b["reuse_declaration"]
        self.assertEqual(declaration["novel_capacity_delta"], 0)
        self.assertEqual(declaration["new_central_claim_count_delta"], 0)
        self.assertEqual(declaration["content_opportunity_count_delta"], 0)

    def test_09_price_content_matches_approved_price_pattern(self) -> None:
        selected = self.track_b["pattern_matching"]["selected_pattern"]
        self.assertEqual(selected["pattern_id"], NEWS_PRICE_PATTERN_ID)
        self.assertTrue(selected["compatible"])

    def test_10_price_content_does_not_match_scene_pattern(self) -> None:
        assessment = next(
            item
            for item in self.track_b["pattern_matching"]["assessments"]
            if item["pattern_id"] == NEWS_SCENE_PATTERN_ID
        )
        self.assertFalse(assessment["compatible"])
        self.assertEqual(
            assessment["reason_code"],
            "no_approved_customer_state_a_b_correspondence",
        )

    def test_11_scene_pattern_cannot_create_missing_state_correspondence(self) -> None:
        status = self.track_a["scene_contrast_validation"]
        self.assertFalse(status["approved_state_a_b_correspondence_present"])
        self.assertFalse(status["customer_state_a_b_fabricated"])

    def test_12_only_approved_patterns_are_eligible(self) -> None:
        candidate = copy.deepcopy(self.price_pattern)
        candidate["status"] = "candidate"
        assessment = selected_content_pattern_compatibility(
            {
                "primary_fact_refs": ["pricing_facts"],
                "semantic_signature": {"primary_fact_bundle": ["pricing_facts"]},
            },
            candidate,
            "news",
        )
        self.assertFalse(assessment["compatible"])
        self.assertEqual(assessment["reason_code"], "pattern_not_approved")

    def test_13_case_references_are_structural_only(self) -> None:
        refs = self.track_b["case_structural_references"]
        self.assertEqual(len(refs), 3)
        self.assertTrue(
            all(item["case_reference_authority"] == "structural_only" for item in refs)
        )
        self.assertTrue(
            all(not item["case_specific_facts_are_customer_authority"] for item in refs)
        )

    def test_14_case_footage_is_not_production_eligible(self) -> None:
        refs = self.track_b["case_structural_references"]
        self.assertTrue(all(item["media_reuse_rights"] == "not_established" for item in refs))
        self.assertTrue(all(not item["production_footage_pool_eligible"] for item in refs))
        self.assertFalse(self.track_b["visual_anchor_policy"]["case_footage_used"])

    def test_15_news_beat_plan_follows_price_pattern_invariants(self) -> None:
        applied = self.track_b["pattern_application"]["applied_invariants"]
        self.assertEqual(
            [item["invariant"] for item in applied],
            self.price_pattern["definition"]["invariants"],
        )
        self.assertTrue(all(item["satisfied"] for item in applied))
        self.assertEqual(
            self.track_b["micro_beats"][0]["semantic_role"],
            "price_offer_first_semantic_anchor",
        )

    def test_16_narration_independence_is_inherited_from_news_profile(self) -> None:
        application = self.track_b["pattern_application"]
        self.assertFalse(application["continuous_mix_narration_required"])
        self.assertEqual(
            application["narration_independence_authority"],
            "inherited_from_production_profile_news",
        )

    def test_17_six_export_slots_are_not_pattern_invariant(self) -> None:
        self.assertFalse(
            self.track_b["pattern_application"]["six_export_slots_are_pattern_invariant"]
        )
        self.assertFalse(
            self.dry_run["implementation_constraints"]["pattern_invariant"]
        )

    def test_18_beat_mapping_has_no_duplicate_padding(self) -> None:
        mapping = self.track_b["beat_to_export_slot_mapping"]
        texts = [item["text"] for item in mapping["slots"]]
        self.assertEqual(mapping["export_slot_count"], 6)
        self.assertEqual(mapping["duplicate_padding_count"], 0)
        self.assertEqual(len(texts), len(set(texts)))

    def test_19_approximate_price_qualifiers_are_preserved(self) -> None:
        slots = self.track_b["beat_to_export_slot_mapping"]["slots"]
        slot_text = "".join(item["text"] for item in slots)
        self.assertIn("素菜通常8–10元", slot_text)
        self.assertIn("清蒸约15元", slot_text)
        self.assertIn("红烧约18元左右", slot_text)
        self.assertNotIn("固定15", slot_text)
        self.assertNotIn("统一8元", slot_text)

    def test_20_unknown_and_requires_review_facts_are_excluded(self) -> None:
        lineage_fields = {item["field"] for item in self.track_b["fact_lineage"]}
        self.assertEqual(lineage_fields, {"pricing_facts", "included_service_facts"})
        for item in self.track_b["fact_lineage"]:
            fact = self.persona["facts"][item["field"]]
            self.assertEqual(fact["state"], "known")
        self.assertFalse(self.track_b["authority"]["unknown_or_requires_review_consumed"])

    def test_21_privacy_gate_passes_without_remote_call(self) -> None:
        self.assertEqual(self.track_a["privacy"]["status"], "pass")
        self.assertEqual(self.track_b["privacy"]["status"], "pass")
        self.assertFalse(self.track_b["privacy"]["remote_call_performed"])
        self.assertEqual(self.result["summary"]["usage"]["remote_model_calls"], 0)

    def test_22_proof_authority_is_unchanged(self) -> None:
        self.assertEqual(self.track_b["proof"]["status"], "unchanged")
        self.assertFalse(self.track_b["proof"]["new_proof_claim_created"])
        self.assertFalse(self.track_b["authority"]["pattern_effectiveness_claimed"])

    def test_23_mix_pipeline_artifacts_remain_unchanged(self) -> None:
        for name in ("mix_template", "mix_export", "mix_pattern", "approved_batch"):
            self.assertEqual(sha256(self.paths[name]), self.source_hashes[name])
        record = next(
            item
            for item in self.registry["pattern_compatibility_records"]
            if item["pattern_id"] == "pcv1_narration_led_process_projection"
        )
        self.assertEqual(record["compatible_profiles"], ["mix"])

    def test_24_news_excel_template_is_unchanged_and_contract_valid(self) -> None:
        self.assertEqual(sha256(self.paths["news_template"]), self.source_hashes["news_template"])
        self.assertEqual(
            inspect_xlsx_headers(self.paths["news_template"], "Sheet1", 4, 6),
            ["标题1", "标题2", "标题3", "标题4", "标题5", "标题6"],
        )
        self.assertFalse(self.dry_run["workbook_written"])
        self.assertTrue(self.dry_run["validation"]["passed"])


if __name__ == "__main__":
    unittest.main()
