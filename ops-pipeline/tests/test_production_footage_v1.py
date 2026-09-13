from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from production_footage_v1 import (  # noqa: E402
    ASSET_SCHEMA_VERSION,
    audit_production_asset_inventory_v1,
    build_customer_capture_missions_v1,
    build_subject_media_use_confirmation_v1,
    build_shot_requirement_plan_v1,
    build_storyboard_coverage_v1,
    evaluate_production_asset_eligibility,
    match_production_assets_v1,
    production_asset_contract_v1,
    render_customer_capture_pack_v1,
    run_real_validation,
    sha256_file,
    subject_capture_paths,
    subject_media_use_confirmation_contract_v1,
)


APPROVED_BATCH_PATH = (
    ROOT
    / "data"
    / "generation_batches"
    / "real_shufang_mix_003"
    / "revisions"
    / "revision_0004"
    / "approved_generation_batch_v1.json"
)
LEDGER_PATH = (
    ROOT
    / "data"
    / "content_ledgers"
    / "shufang_zhiyuan_community_canteen"
    / "content_ledger_v1.json"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ProductionFootageV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.batch = load_json(APPROVED_BATCH_PATH)
        cls.plan = build_shot_requirement_plan_v1(
            cls.batch,
            batch_path=APPROVED_BATCH_PATH,
            created_at="2026-09-13T00:00:00+08:00",
        )

    def requirement(self, concept_ref: str, role: str = "hero") -> dict:
        return next(
            item
            for item in self.plan["requirements"]
            if item["concept_ref"] == concept_ref
            and item["requirement_role"] == role
        )

    def asset(self, **changes) -> dict:
        value = {
            "schema_version": ASSET_SCHEMA_VERSION,
            "asset_id": "asset-001",
            "business_id": "shufang_zhiyuan_community_canteen",
            "source_type": "customer_new_capture",
            "source_ref": "customer-upload-001",
            "file_ref": "customer-assets/asset-001.mp4",
            "checksum": "a" * 64,
            "captured_at": "2026-09-13T00:00:00+08:00",
            "uploaded_at": "2026-09-13T00:00:00+08:00",
            "media_type": "video",
            "duration": 8.0,
            "orientation": "portrait",
            "observable_content": [],
            "people_present": False,
            "identifiable_people": False,
            "speaker_present": False,
            "ownership_basis": "customer_confirmed",
            "media_use_status": "authorized",
            "privacy_status": "passed",
            "subject_release_status": "not_required",
            "customer_story_scope_ref": None,
            "event_relationship": "actual_current_operation",
            "production_eligibility": {},
            "eligible_profiles": ["mix"],
            "analysis_version": "deterministic-test",
        }
        value.update(changes)
        return value

    def inventory(self, assets: list[dict]) -> dict:
        return {
            "schema_version": "production-asset-inventory-v1.0",
            "assets": assets,
            "asset_count": len(assets),
            "eligible_asset_count": sum(
                evaluate_production_asset_eligibility(item, target_profile="mix")[
                    "eligible"
                ]
                for item in assets
            ),
        }

    def test_01_approved_batch_produces_one_hero_per_content(self) -> None:
        self.assertEqual(self.plan["content_count"], 4)
        self.assertTrue(
            all(item["hero_requirement_count"] == 1 for item in self.plan["contents"])
        )

    def test_02_no_fixed_shot_count_is_frozen(self) -> None:
        self.assertFalse(self.plan["fixed_shot_count_required"])
        supporting_counts = {
            item["supporting_requirement_count"] for item in self.plan["contents"]
        }
        self.assertGreater(len(supporting_counts), 1)

    def test_03_case_media_never_enters_production_asset_pool(self) -> None:
        asset = self.asset(source_type="case_library")
        result = evaluate_production_asset_eligibility(asset, target_profile="mix")
        self.assertEqual(result["status"], "blocked")
        self.assertIn(
            "source_type_not_allowed_case_library_is_never_production_source",
            result["blocking_reasons"],
        )

    def test_04_media_use_not_established_is_not_eligible(self) -> None:
        result = evaluate_production_asset_eligibility(
            self.asset(media_use_status="not_established"), target_profile="mix"
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], "review_required")

    def test_05_ownership_does_not_bypass_privacy(self) -> None:
        result = evaluate_production_asset_eligibility(
            self.asset(ownership_basis="customer_owned", privacy_status="blocked"),
            target_profile="mix",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["ownership_alone_used"])

    def test_06_identifiable_people_need_subject_release(self) -> None:
        result = evaluate_production_asset_eligibility(
            self.asset(
                people_present=True,
                identifiable_people=True,
                subject_release_status="review_required",
            ),
            target_profile="mix",
        )
        self.assertEqual(result["status"], "review_required")

    def test_07_customer_story_media_block_stays_blocked(self) -> None:
        result = evaluate_production_asset_eligibility(
            self.asset(
                customer_story_scope_ref="B-R2-009",
                customer_story_media_authorization={
                    "image_authorized": False,
                    "video_authorized": False,
                },
            ),
            target_profile="mix",
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIn("customer_story_media_not_authorized", result["blocking_reasons"])

    def test_08_speaker_persona_does_not_imply_media_authorization(self) -> None:
        fish = self.requirement("REV2-CONCEPT-006")
        self.assertEqual(
            fish["speaker_presence"]["media_authorization_status"], "review_required"
        )
        self.assertFalse(
            fish["speaker_presence"]["persona_approval_implies_media_authorization"]
        )
        self.assertIn("hands_only", fish["speaker_presence"]["alternatives"])

    def test_09_busy_kitchen_cannot_match_whiteboard_hero(self) -> None:
        whiteboard = self.requirement("REV2-CONCEPT-004")
        plan = {**self.plan, "requirements": [whiteboard]}
        result = match_production_assets_v1(
            plan,
            self.inventory([self.asset(observable_content=["busy_kitchen"])]),
            created_at="2026-09-13T00:00:00+08:00",
        )
        self.assertEqual(result["matches"][0]["match_decision"], "gap")

    def test_10_whiteboard_state_can_match_when_privacy_safe(self) -> None:
        whiteboard = self.requirement("REV2-CONCEPT-004")
        plan = {**self.plan, "requirements": [whiteboard]}
        result = match_production_assets_v1(
            plan,
            self.inventory(
                [
                    self.asset(
                        observable_content=["queue_board", "queue_order_or_estimated_wait"]
                    )
                ]
            ),
            created_at="2026-09-13T00:00:00+08:00",
        )
        self.assertEqual(result["matches"][0]["match_decision"], "matched")

    def test_11_generic_fish_is_partial_not_full_hero(self) -> None:
        fish = self.requirement("REV2-CONCEPT-006")
        plan = {**self.plan, "requirements": [fish]}
        result = match_production_assets_v1(
            plan,
            self.inventory([self.asset(observable_content=["fish"])]),
            created_at="2026-09-13T00:00:00+08:00",
        )
        self.assertEqual(result["matches"][0]["match_decision"], "partial")

    def test_12_generic_crab_process_is_partial_and_illustrative(self) -> None:
        crab = self.requirement("REV2-CONCEPT-010")
        plan = {**self.plan, "requirements": [crab]}
        asset = self.asset(
            observable_content=["three_swimming_crabs"],
            event_relationship="illustrative_same_process",
        )
        result = match_production_assets_v1(
            plan,
            self.inventory([asset]),
            created_at="2026-09-13T00:00:00+08:00",
        )
        match = result["matches"][0]
        self.assertEqual(match["match_decision"], "partial")
        self.assertTrue(
            match["event_relationship_fit"][0]["cannot_prove_original_event"]
        )
        self.assertFalse(
            match["candidate_details"][0]["visual_truth_boundary"][
                "claim_authority_upgraded"
            ]
        )

    def test_13_finished_clam_result_cannot_satisfy_boundary_hero(self) -> None:
        clam = self.requirement("REV2-CONCEPT-001")
        plan = {**self.plan, "requirements": [clam]}
        result = match_production_assets_v1(
            plan,
            self.inventory([self.asset(observable_content=["finished_clam_dish"])]),
            created_at="2026-09-13T00:00:00+08:00",
        )
        self.assertEqual(result["matches"][0]["match_decision"], "gap")
        self.assertIn(
            "visual claim of fully sand-free result",
            clam["unacceptable_or_misleading_forms"],
        )

    def test_14_hero_and_supporting_roles_remain_distinct(self) -> None:
        roles = {item["requirement_role"] for item in self.plan["requirements"]}
        self.assertEqual(roles, {"hero", "supporting"})
        self.assertTrue(
            all(
                sum(
                    item["requirement_role"] == "hero"
                    for item in self.plan["requirements"]
                    if item["content_id"] == content["content_id"]
                )
                == 1
                for content in self.plan["contents"]
            )
        )

    def test_15_zero_assets_yields_four_capture_required_contents(self) -> None:
        matches = match_production_assets_v1(
            self.plan,
            self.inventory([]),
            created_at="2026-09-13T00:00:00+08:00",
        )
        coverage = build_storyboard_coverage_v1(
            self.plan, matches, created_at="2026-09-13T00:00:00+08:00"
        )
        self.assertEqual(coverage["summary"]["capture_required"], 4)
        self.assertEqual(coverage["summary"]["covered"], 0)

    def test_16_capture_gaps_describe_visual_information(self) -> None:
        matches = match_production_assets_v1(self.plan, self.inventory([]))
        coverage = build_storyboard_coverage_v1(self.plan, matches)
        for gap in coverage["capture_gaps"]:
            self.assertTrue(gap["semantic_goal"])
            self.assertTrue(gap["missing_state"])
            self.assertNotEqual(gap["missing_state"], "缺素材")

    def test_17_capture_pack_is_customer_readable_without_internal_ids(self) -> None:
        matches = match_production_assets_v1(self.plan, self.inventory([]))
        coverage = build_storyboard_coverage_v1(self.plan, matches)
        markdown = render_customer_capture_pack_v1(self.plan, coverage)
        self.assertIn("拍什么", markdown)
        self.assertIn("一定要拍到", markdown)
        self.assertIn("替代方式", markdown)
        self.assertIn("隐私", markdown)
        self.assertNotIn("real_shufang_mix_003-C001", markdown)
        self.assertNotIn("Fact Atom", markdown)
        self.assertNotIn("SHA", markdown)
        self.assertNotIn("case_structural", markdown)

    def test_18_capture_pack_requires_speaker_authorization_or_safe_alternative(self) -> None:
        matches = match_production_assets_v1(self.plan, self.inventory([]))
        coverage = build_storyboard_coverage_v1(self.plan, matches)
        markdown = render_customer_capture_pack_v1(self.plan, coverage)
        self.assertIn("林东方本人清晰出镜", markdown)
        self.assertIn("只拍手部、食材和操作动作", markdown)
        self.assertIn("A：林东方确认同意本批视频清晰出镜后拍摄", markdown)
        self.assertIn("B：没有确认或不愿清晰出镜时", markdown)

    def test_19_case_research_roots_are_explicitly_excluded(self) -> None:
        inventory = audit_production_asset_inventory_v1(
            business_id="shufang_zhiyuan_community_canteen",
            workspace_root=ROOT,
            target_profile="mix",
            created_at="2026-09-13T00:00:00+08:00",
        )
        excluded = " ".join(inventory["excluded_case_research_roots"])
        self.assertIn("cases", excluded)
        self.assertIn("visual", excluded)
        self.assertFalse(inventory["authority"]["case_media_ingested"])

    def test_20_asset_contract_keeps_story_and_media_rights_separate(self) -> None:
        contract = production_asset_contract_v1()
        fields = set(contract["required_fields"])
        self.assertIn("customer_story_scope_ref", fields)
        self.assertIn("media_use_status", fields)
        self.assertFalse(
            contract["boundaries"]["customer_story_authorization_equals_media_rights"]
        )

    def test_21_real_validation_does_not_change_batch_or_ledger(self) -> None:
        batch_before = sha256_file(APPROVED_BATCH_PATH)
        ledger_before = sha256_file(LEDGER_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            result = run_real_validation(
                approved_batch_path=APPROVED_BATCH_PATH,
                output_dir=Path(temporary) / "output",
                workspace_root=ROOT,
                created_at="2026-09-13T00:00:00+08:00",
            )
        self.assertTrue(result["validation"]["passed"])
        self.assertEqual(sha256_file(APPROVED_BATCH_PATH), batch_before)
        self.assertEqual(sha256_file(LEDGER_PATH), ledger_before)
        self.assertFalse(result["content_ledger_write_performed"])

    def test_22_no_models_editing_or_sending_are_triggered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_real_validation(
                approved_batch_path=APPROVED_BATCH_PATH,
                output_dir=Path(temporary) / "output",
                workspace_root=ROOT,
                created_at="2026-09-13T00:00:00+08:00",
            )
        self.assertEqual(result["remote_model_calls"], 0)
        self.assertEqual(result["local_model_calls"], 0)
        self.assertFalse(result["customer_capture_pack_sent"])
        self.assertFalse(result["editing_started"])
        self.assertFalse(result["rendering_started"])

    def test_23_unrelated_blocked_asset_does_not_block_requirement(self) -> None:
        whiteboard = self.requirement("REV2-CONCEPT-004")
        plan = {**self.plan, "requirements": [whiteboard]}
        unrelated = self.asset(
            observable_content=["generic_fish"],
            media_use_status="blocked",
        )
        result = match_production_assets_v1(
            plan,
            self.inventory([unrelated]),
            created_at="2026-09-13T00:00:00+08:00",
        )
        self.assertEqual(result["matches"][0]["match_decision"], "gap")

    def test_24_other_source_type_requires_review(self) -> None:
        result = evaluate_production_asset_eligibility(
            self.asset(source_type="other_review_required"), target_profile="mix"
        )
        self.assertEqual(result["status"], "review_required")
        self.assertIn("source_type_requires_review", result["review_reasons"])

    def test_25_customer_pack_translates_machine_capture_labels(self) -> None:
        matches = match_production_assets_v1(self.plan, self.inventory([]))
        coverage = build_storyboard_coverage_v1(self.plan, matches)
        markdown = render_customer_capture_pack_v1(self.plan, coverage)
        self.assertIn("年糕与梭子蟹在同一加工流程中", markdown)
        self.assertNotIn("same-frame ingredients", markdown)
        self.assertNotIn("generic fish beauty shot", markdown)

    def test_26_asset_analysis_contract_is_observation_only(self) -> None:
        analysis = production_asset_contract_v1()["analysis_contract"]
        self.assertIn("visible_text", analysis["observable_content_fields"])
        self.assertIn("privacy_indicators", analysis["observable_content_fields"])
        self.assertIn("candidate_visual_roles", analysis["observable_content_fields"])
        self.assertFalse(analysis["analysis_may_assert_customer_fact_truth"])
        self.assertFalse(analysis["case_lifecycle_reused"])

    def test_27_real_review_pack_contains_all_human_gate_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            run_real_validation(
                approved_batch_path=APPROVED_BATCH_PATH,
                output_dir=output,
                workspace_root=ROOT,
                created_at="2026-09-13T00:00:00+08:00",
            )
            markdown = (output / "production_footage_planning_review_pack_v1.md").read_text(
                encoding="utf-8"
            )
        self.assertIn("Approved contents: 4", markdown)
        self.assertIn("Existing Production Asset Inventory", markdown)
        self.assertIn("Matched assets", markdown)
        self.assertIn("Overall coverage", markdown)
        self.assertIn("Capture gaps", markdown)
        self.assertIn("Rights / Privacy / Visual Truth", markdown)
        self.assertIn("林东方 identifiable media status", markdown)
        self.assertIn("Customer Capture Pack Preview", markdown)

    def test_28_c002_visual_state_does_not_claim_prior_sand_purge(self) -> None:
        clam = self.requirement("REV2-CONCEPT-001")
        self.assertNotIn("未提前吐沙", clam["required_visible_state"])
        self.assertFalse(
            clam["content_truth_context"][
                "visual_asset_can_independently_prove_prior_sand_purge_state"
            ]
        )
        self.assertIn(
            "未提前吐沙",
            clam["content_truth_context"]["approved_customer_truth"],
        )

    def test_29_c002_approved_content_truth_is_unchanged(self) -> None:
        content = next(
            item
            for item in self.batch["contents"]
            if item["concept_ref"] == "REV2-CONCEPT-001"
        )
        self.assertIn("没提前吐沙的花蛤", content["narration"])
        self.assertEqual(
            sha256_file(APPROVED_BATCH_PATH),
            "387590b6ec9e624e5b9603c208f43ff0e0bf568c7bc20797a0502da3944982db",
        )

    def test_30_c003_staged_demo_cannot_fully_match_actual_hero(self) -> None:
        whiteboard = self.requirement("REV2-CONCEPT-004")
        plan = {**self.plan, "requirements": [whiteboard]}
        staged = self.asset(
            observable_content=["queue_board", "queue_order_or_estimated_wait"],
            event_relationship="illustrative_same_process",
        )
        result = match_production_assets_v1(plan, self.inventory([staged]))
        self.assertEqual(result["matches"][0]["match_decision"], "gap")
        self.assertFalse(
            whiteboard["event_relationship_requirement"][
                "staged_demo_can_satisfy_hero"
            ]
        )

    def test_31_capture_missions_cover_all_internal_requirements_once(self) -> None:
        missions = build_customer_capture_missions_v1(self.plan)
        covered = [
            requirement_id
            for mission in missions["missions"]
            for requirement_id in mission["covers_requirement_ids"]
        ]
        expected = [item["requirement_id"] for item in self.plan["requirements"]]
        self.assertEqual(missions["mission_count"], 4)
        self.assertEqual(len(expected), 14)
        self.assertEqual(sorted(covered), sorted(expected))
        self.assertEqual(len(covered), len(set(covered)))
        self.assertTrue(
            any(len(mission["covers_requirement_ids"]) > 1 for mission in missions["missions"])
        )

    def test_32_customer_pack_exposes_four_missions_not_fourteen_tasks(self) -> None:
        matches = match_production_assets_v1(self.plan, self.inventory([]))
        coverage = build_storyboard_coverage_v1(self.plan, matches)
        missions = build_customer_capture_missions_v1(
            self.plan, status="ready_to_send"
        )
        markdown = render_customer_capture_pack_v1(
            self.plan, coverage, missions, status="ready_to_send"
        )
        self.assertIn("这次一共拍 4 组素材", markdown)
        self.assertEqual(markdown.count("**拍什么：**"), 4)
        self.assertNotIn("14 个", markdown)
        self.assertIn("可以发送，尚未发送", markdown)

    def test_33_subject_media_confirmation_is_batch_scope_bound(self) -> None:
        contract = subject_media_use_confirmation_contract_v1()
        confirmation = build_subject_media_use_confirmation_v1()
        self.assertEqual(
            set(contract["allowed_statuses"]),
            {"authorized", "declined", "review_required"},
        )
        self.assertEqual(confirmation["status"], "review_required")
        self.assertEqual(confirmation["scope_refs"], ["real_shufang_mix_003"])
        self.assertEqual(confirmation["use_scope"], "current_batch_only")
        self.assertTrue(confirmation["future_use_requires_recheck"])
        self.assertFalse(confirmation["persona_approval_used_as_media_authorization"])

    def test_34_declined_face_use_still_allows_non_identifying_capture(self) -> None:
        confirmation = build_subject_media_use_confirmation_v1(status="declined")
        paths = subject_capture_paths(confirmation)
        self.assertFalse(paths["identifiable_subject_capture_allowed"])
        self.assertTrue(paths["non_identifying_capture_allowed"])
        self.assertIn("hands_only", paths["non_identifying_options"])
        self.assertFalse(paths["declining_identifiable_use_blocks_capture_mission"])

    def test_35_human_review_closure_persists_approval_and_stops_before_send(self) -> None:
        batch_before = sha256_file(APPROVED_BATCH_PATH)
        ledger_before = sha256_file(LEDGER_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            result = run_real_validation(
                approved_batch_path=APPROVED_BATCH_PATH,
                output_dir=output,
                workspace_root=ROOT,
                created_at="2026-09-13T00:00:00+08:00",
                human_review_closure=True,
                reviewer="李健",
            )
            approval = load_json(
                output / "production_footage_planning_human_approval_v1.json"
            )
            missions = load_json(output / "customer_capture_missions_v1.json")
            confirmation = load_json(
                output / "subject_media_use_confirmation_v1.json"
            )
        self.assertEqual(approval["reviewer"], "李健")
        self.assertEqual(approval["decision"], "approved_after_minor_normalization")
        self.assertEqual(missions["status"], "ready_to_send")
        self.assertEqual(confirmation["status"], "review_required")
        self.assertEqual(result["customer_capture_pack_status"], "ready_to_send")
        self.assertFalse(result["customer_capture_pack_sent"])
        self.assertFalse(result["asset_intake_started"])
        self.assertFalse(result["editing_started"])
        self.assertFalse(result["rendering_started"])
        self.assertEqual(sha256_file(APPROVED_BATCH_PATH), batch_before)
        self.assertEqual(sha256_file(LEDGER_PATH), ledger_before)

    def test_36_c003_privacy_preserves_real_mechanism_not_invented_ui(self) -> None:
        missions = build_customer_capture_missions_v1(self.plan)
        board = next(
            item for item in missions["missions"] if item["mission_id"] == "MISSION-003"
        )
        self.assertIn("真实白板上的排单结构或预计等待结构", board["must_capture"])
        self.assertIn(
            "把完全虚构的演示白板当成当前真实使用状态", board["avoid"]
        )


if __name__ == "__main__":
    unittest.main()
