from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_mix_scripts_v1 import (  # noqa: E402
    NEWS_PRICE_PATTERN_ID,
    NEWS_SCENE_PATTERN_ID,
    append_news_presentation_history,
    validate_news_excel_export,
    validate_news_export_approval,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NewsProductionMvpFinalV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.paths = {
            "track_a": ROOT
            / "data/news_production_mvp/real_shufang_news_validation_novel_001/news_novel_capacity_validation_v1.json",
            "track_b": ROOT
            / "data/news_production_mvp/real_shufang_news_validation_repurpose_001/news_micro_beat_plan_v1.json",
            "track_a_approval": ROOT
            / "data/news_production_mvp/real_shufang_news_validation_novel_001/news_novel_capacity_human_approval_v1.json",
            "track_b_approval": ROOT
            / "data/news_production_mvp/real_shufang_news_validation_repurpose_001/news_generation_human_approval_v1.json",
            "ledger": ROOT
            / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json",
            "content_plan": ROOT
            / "data/content_plans/real_shufang_mix_002/revisions/v1_1_1/content_plan_v1_1_1.json",
            "coverage_source": ROOT
            / "data/creative_coverage/revisions/news_pattern_approval_creative_coverage_update_v1.json",
            "coverage_final": ROOT
            / "data/creative_coverage/revisions/news_production_mvp_final_validation_update_v1.json",
            "registry": ROOT / "data/production_profiles/production_profile_registry_v1.json",
            "price_pattern": ROOT
            / f"data/patterns/approved/{NEWS_PRICE_PATTERN_ID}/pattern_v1.json",
            "scene_pattern": ROOT
            / f"data/patterns/approved/{NEWS_SCENE_PATTERN_ID}/pattern_v1.json",
            "news_template": ROOT / "output/新闻体视频制作文案导入模板.xlsx",
            "news_export": ROOT
            / "output/real_shufang_news_validation_repurpose_001_approved_news.xlsx",
            "receipt": ROOT
            / "output/real_shufang_news_validation_repurpose_001_approved_news.export_receipt.json",
            "mix_template": ROOT / "output/素材混剪&数字人口播混剪文案导入模板.xlsx",
            "mix_export": ROOT / "output/real_shufang_mix_001_approved_mix_scripts.xlsx",
        }
        cls.track_a = read_json(cls.paths["track_a"])
        cls.track_b = read_json(cls.paths["track_b"])
        cls.ledger = read_json(cls.paths["ledger"])
        cls.track_a_approval = read_json(cls.paths["track_a_approval"])
        cls.track_b_approval = read_json(cls.paths["track_b_approval"])
        cls.coverage = read_json(cls.paths["coverage_final"])
        cls.receipt = read_json(cls.paths["receipt"])
        cls.expected_slots = [
            "素菜通常8–10元",
            "清蒸约15元",
            "红烧约18元左右",
            "油盐酱料免费",
            "米饭免费",
            "价格公开清晰",
        ]

    def test_01_track_a_zero_capacity_remains_valid(self) -> None:
        result = self.track_a_approval["approved_result"]
        self.assertEqual(result["news_novel_capacity"], 0)
        self.assertEqual(result["status"], "capacity_limited")
        self.assertFalse(result["padding_generated"])

    def test_02_track_b_approved_repurpose_can_export(self) -> None:
        self.assertEqual(
            validate_news_export_approval(self.track_b_approval), self.expected_slots
        )
        self.assertTrue(self.paths["news_export"].is_file())

    def test_03_repurpose_cannot_become_novel_content(self) -> None:
        reuse = self.track_b_approval["reuse_declaration"]
        self.assertEqual(reuse["reuse_intent"], "cross_profile_repurpose")
        self.assertFalse(reuse["semantic_novelty"])
        self.assertEqual(reuse["new_semantic_content_count_delta"], 0)

    def test_04_presentation_history_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.json"
            source = copy.deepcopy(self.ledger)
            source.get("extensions", {}).pop("presentation_history_v1", None)
            path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
            updated, entry, _sha = append_news_presentation_history(
                path,
                source,
                approval_ref={"path": "approval", "sha256": "a" * 64},
                output_ref={"path": "output", "sha256": "b" * 64},
                exported_at="2026-09-12T00:00:00+00:00",
            )
            self.assertEqual(entry["status"], "exported")
            self.assertEqual(len(updated["entries"]), len(source["entries"]))
            self.assertEqual(
                len(updated["extensions"]["presentation_history_v1"]["entries"]), 1
            )

    def test_05_semantic_historical_exposure_is_not_duplicated(self) -> None:
        history = self.ledger["extensions"]["presentation_history_v1"]
        entry = history["entries"][-1]
        self.assertFalse(entry["communicated_information_units_created"])
        self.assertEqual(entry["new_semantic_content_count_delta"], 0)
        self.assertEqual(self.receipt["content_ledger"]["semantic_entry_count_before"], 17)
        self.assertEqual(self.receipt["content_ledger"]["semantic_entry_count_after"], 17)

    def test_06_first_display_slot_preserves_price_offer_anchor(self) -> None:
        mapping = self.track_b_approval["approved_export_slot_mapping"]
        self.assertTrue(mapping["first_display_slot_price_offer_anchor_recoverable"])
        self.assertEqual(mapping["slots"][0]["text"], "素菜通常8–10元")

    def test_07_soft_length_warning_does_not_mutate_fact(self) -> None:
        first = self.track_b_approval["approved_export_slot_mapping"]["slots"][0]
        self.assertTrue(first["display_length_soft_warning"])
        self.assertEqual(first["text"], "素菜通常8–10元")
        self.assertEqual(first["display_length_policy"], "configurable_soft_recommendation")

    def test_08_price_qualifiers_are_preserved(self) -> None:
        text = "；".join(self.expected_slots)
        self.assertIn("通常", text)
        self.assertIn("约", text)
        self.assertIn("左右", text)

    def test_09_six_slot_mapping_is_exact(self) -> None:
        slots = self.track_b_approval["approved_export_slot_mapping"]["slots"]
        self.assertEqual([item["text"] for item in slots], self.expected_slots)
        self.assertEqual([item["header"] for item in slots], [f"标题{i}" for i in range(1, 7)])

    def test_10_news_template_and_rows_one_to_four_are_unchanged(self) -> None:
        registry = read_json(self.paths["registry"])
        self.assertEqual(
            sha256(self.paths["news_template"]),
            registry["profiles"]["news"]["export_contract"]["template_sha256"],
        )
        validation = validate_news_excel_export(
            self.paths["news_template"],
            self.paths["news_export"],
            self.expected_slots,
            sha256(self.paths["news_template"]),
        )
        self.assertTrue(validation["checks"]["rows_1_4_content_and_styles_preserved"])

    def test_11_unapproved_news_plan_export_is_rejected(self) -> None:
        unapproved = copy.deepcopy(self.track_b_approval)
        unapproved["status"] = "review_required"
        unapproved["human_review"]["decision"] = "pending"
        with self.assertRaisesRegex(RuntimeError, "Unapproved News Plan"):
            validate_news_export_approval(unapproved)

    def test_12_price_pattern_production_validation_passed(self) -> None:
        status = self.coverage["pattern_production_validation"][NEWS_PRICE_PATTERN_ID]
        self.assertEqual(status["status"], "passed")

    def test_13_scene_pattern_remains_production_unvalidated(self) -> None:
        status = self.coverage["pattern_production_validation"][NEWS_SCENE_PATTERN_ID]
        self.assertEqual(status["status"], "pending_real_customer_opportunity")

    def test_14_scene_pattern_does_not_fabricate_customer_truth(self) -> None:
        status = self.coverage["pattern_production_validation"][NEWS_SCENE_PATTERN_ID]
        self.assertFalse(status["customer_state_a_b_fabricated"])

    def test_15_mix_export_contract_is_unchanged(self) -> None:
        self.assertEqual(
            sha256(self.paths["mix_template"]),
            "598b12a7a87dd498e48b1022c51a0a9f54402cd8ec5ea5d68913c06cad7c4d67",
        )
        self.assertEqual(
            sha256(self.paths["mix_export"]),
            "1c64d2f46c5878506ad5880f8ca137fda34d3860759a66791ec1b3aa1a54a910",
        )

    def test_16_content_quality_capacity_is_unchanged(self) -> None:
        capacity = read_json(self.paths["content_plan"])["capacity"]
        self.assertEqual(capacity["high_quality_novel_capacity"], 2)
        self.assertEqual(self.receipt["novel_capacity"]["delta"], 0)

    def test_17_privacy_proof_and_authority_remain_unchanged(self) -> None:
        authority = self.receipt["authority"]
        self.assertFalse(authority["case_facts_transferred"])
        self.assertFalse(authority["case_footage_used"])
        self.assertFalse(authority["privacy_or_proof_authority_changed"])
        self.assertEqual(authority["remote_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
