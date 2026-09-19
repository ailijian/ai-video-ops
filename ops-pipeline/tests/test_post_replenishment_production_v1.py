from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from authority_test_support import live_authority_root

pytestmark = pytest.mark.live_authority
REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = live_authority_root()
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from content_quality_v1 import (  # noqa: E402
    build_exported_semantic_ledger_update,
    build_fact_atom_catalog,
    build_post_export_remaining_capacity,
    build_storyboard_plan,
)
from generate_mix_scripts_v1 import (  # noqa: E402
    POST_REPLENISHMENT_CONCEPT_ALLOWLIST,
    POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT,
    _post_replenishment_revision_integrity,
    bounded_fact_violations,
    build_post_replenishment_content_plan,
    build_post_replenishment_generation_request,
    safe_persona_projection,
    safe_speaker_projection,
    validate_generated_item,
    validate_post_replenishment_script_boundaries,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PostReplenishmentProductionV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        temp_root = Path(cls.temp.name)
        cls.persona_path = (
            ROOT
            / "data/personas/shufang_zhiyuan_community_canteen/revision_0002/persona_v1.json"
        )
        cls.speaker_path = (
            ROOT
            / "data/personas/lin_dongfang_frontline_chef/revision_0002/persona_v1.json"
        )
        cls.capacity_path = (
            ROOT
            / "data/content_plans/real_shufang_replenishment_rev2/content_capacity_recalculation_v1.json"
        )
        cls.approval_path = (
            ROOT
            / "data/content_plans/real_shufang_replenishment_rev2/content_capacity_recalculation_v1_human_approval.json"
        )
        cls.ledger_path = (
            ROOT
            / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
        )
        cls.request = build_post_replenishment_generation_request(
            created_at="2026-09-13T00:00:00+00:00"
        )
        cls.request_path = temp_root / "generation_request_v1.json"
        cls.request_path.write_text(
            json.dumps(cls.request, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        cls.source_plan = {
            "selected_patterns": [
                {"pattern_id": "pcv1_narration_led_process_projection"}
            ],
            "rotation": {
                "case_rotation_order": [
                    "7683027343636542565",
                    "7680512578585870322",
                    "7650056203686530319",
                ]
            },
        }
        cls.source_plan_path = temp_root / "generation_source_plan_v1.json"
        cls.source_plan_path.write_text(
            json.dumps(cls.source_plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cls.current_ledger = read_json(cls.ledger_path)
        cls.ledger = copy.deepcopy(cls.current_ledger)
        cls.ledger["entries"] = [
            entry
            for entry in cls.ledger.get("entries") or []
            if entry.get("batch_ref") != "real_shufang_mix_003"
        ]
        cls.ledger_before = copy.deepcopy(cls.ledger)
        cls.context = {
            "request": cls.request,
            "persona": read_json(cls.persona_path),
            "speaker_persona": read_json(cls.speaker_path),
            "source_plan": cls.source_plan,
            "paths": {
                "persona": cls.persona_path,
                "speaker_persona": cls.speaker_path,
                "request": cls.request_path,
                "source_plan": cls.source_plan_path,
            },
        }
        cls.capacity = read_json(cls.capacity_path)
        cls.approval = read_json(cls.approval_path)
        cls.plan = build_post_replenishment_content_plan(
            context=cls.context,
            capacity=cls.capacity,
            capacity_approval=cls.approval,
            capacity_source_sha256=sha256(cls.capacity_path),
            ledger=cls.ledger,
            created_at="2026-09-13T00:00:00+00:00",
        )
        cls.by_id = {
            item["concept_id"]: item for item in cls.plan["selected_concepts"]
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_01_capacity_human_approval_is_twelve(self) -> None:
        self.assertEqual(self.approval["capacity"]["after_capacity"], 12)
        self.assertEqual(self.approval["decision"], "approved")

    def test_02_capacity_inventory_is_not_batch_quantity(self) -> None:
        self.assertEqual(
            self.plan["source_semantic_opportunity_inventory"]["high_quality_capacity"],
            12,
        )
        self.assertEqual(self.plan["capacity"]["requested_quantity"], 4)
        self.assertEqual(self.plan["capacity"]["selected_quantity"], 4)

    def test_03_effective_gate_is_not_legacy_diagnostic(self) -> None:
        self.assertTrue(
            all(
                item["novelty_summary"]["effective_gate"]["decision"]
                == "high_quality_novel"
                for item in self.plan["selected_concepts"]
            )
        )

    def test_04_exact_four_concept_allowlist(self) -> None:
        self.assertEqual(
            [item["concept_id"] for item in self.plan["selected_concepts"]],
            list(POST_REPLENISHMENT_CONCEPT_ALLOWLIST),
        )

    def test_05_no_concept_substitution_or_padding(self) -> None:
        self.assertTrue(self.plan["validation"]["no_substitution"])
        self.assertTrue(self.plan["validation"]["no_padding"])
        self.assertFalse(self.plan["capacity"]["padding_generated"])

    def test_06_all_four_remain_historically_novel(self) -> None:
        self.assertTrue(self.plan["validation"]["historical_novelty_passed"])
        self.assertTrue(
            all(
                item["material_information_gain"]["material_information_gain"]
                for item in self.plan["selected_concepts"]
            )
        )

    def test_07_intra_batch_semantic_diversity_passes(self) -> None:
        self.assertTrue(
            self.plan["intra_batch_semantic_diversity"]["passed"]
        )
        self.assertTrue(
            all(
                item["distinct"]
                for item in self.plan["intra_batch_semantic_diversity"][
                    "pair_assessments"
                ]
            )
        )

    def test_08_crab_duration_requires_observed_instance_scope(self) -> None:
        good = {
            "title": "三只梭子蟹的一次服务",
            "narration": "一次真实服务里，三只梭子蟹加年糕，从接收到打包约15分钟，这个时间只代表本次实例。",
            "central_claim": self.by_id["REV2-CONCEPT-010"]["central_claim"],
        }
        self.assertEqual(
            validate_post_replenishment_script_boundaries(
                good, self.by_id["REV2-CONCEPT-010"]
            ),
            [],
        )
        bad = dict(good, narration="三只梭子蟹加年糕一般15分钟就能取餐。")
        self.assertTrue(
            validate_post_replenishment_script_boundaries(
                bad, self.by_id["REV2-CONCEPT-010"]
            )
        )

    def test_09_clam_script_cannot_guarantee_sand_removal(self) -> None:
        bad = {
            "title": "花蛤处理",
            "narration": "花蛤交给窗口，固定半小时保证吐净，不用等待太久。",
            "central_claim": "花蛤处理",
        }
        errors = validate_post_replenishment_script_boundaries(
            bad, self.by_id["REV2-CONCEPT-001"]
        )
        self.assertTrue(any("forbidden_claim" in item for item in errors))

    def test_10_whiteboard_cannot_claim_effectiveness(self) -> None:
        bad = {
            "title": "窗口白板",
            "narration": "白板写着排单和预计等待，效率明显提升。",
            "central_claim": "白板显示排单与预计等待。",
        }
        self.assertIn(
            "post_replenishment_forbidden_claim:效率明显提升",
            validate_post_replenishment_script_boundaries(
                bad, self.by_id["REV2-CONCEPT-004"]
            ),
        )

    def test_11_whiteboard_decision_is_not_assigned_to_lin(self) -> None:
        bad = {
            "title": "我决定放白板",
            "narration": "我决定设置白板，显示排单和预计等待。",
            "central_claim": "窗口白板",
        }
        errors = validate_post_replenishment_script_boundaries(
            bad, self.by_id["REV2-CONCEPT-004"]
        )
        self.assertTrue(any("misattributed" in item or "我决定" in item for item in errors))

    def test_12_fish_check_remains_speaker_specific(self) -> None:
        concept = self.by_id["REV2-CONCEPT-006"]
        self.assertEqual(concept["primary_fact_refs"], [])
        self.assertEqual(concept["speaker_fact_refs"], ["speaker_role_facts"])
        bad = {
            "title": "行业鉴鱼标准",
            "narration": "所有鱼都必须按科学鉴鱼标准检查鱼腹和鳃。",
            "central_claim": "行业标准",
        }
        self.assertTrue(
            validate_post_replenishment_script_boundaries(bad, concept)
        )

    def test_13_no_unauthorized_customer_quote_or_story(self) -> None:
        self.assertTrue(
            all(
                item["conditional_customer_story_used"] is False
                and item.get("customer_story_ref") in (None, "")
                for item in self.plan["selected_concepts"]
            )
        )

    def test_14_no_requires_review_fact(self) -> None:
        self.assertTrue(
            all(
                item["requires_review_fact_used"] is False
                for item in self.plan["selected_concepts"]
            )
        )

    def test_15_case_media_is_never_available_for_production(self) -> None:
        self.assertTrue(
            all(
                item["case_media_allowed"] is False
                for item in self.plan["selected_concepts"]
            )
        )

    def test_16_planning_does_not_mutate_content_ledger(self) -> None:
        self.assertEqual(self.ledger, self.ledger_before)

    def test_17_no_excel_export_or_auto_approval(self) -> None:
        self.assertFalse(self.request["constraints"]["excel_export_allowed"])
        self.assertFalse(self.request["constraints"]["auto_approval_allowed"])

    def test_18_only_approved_mix_pattern_is_assigned(self) -> None:
        self.assertEqual(
            {item["pattern_ref"] for item in self.plan["selected_concepts"]},
            {"pcv1_narration_led_process_projection"},
        )

    def test_19_production_request_is_mix_not_news(self) -> None:
        self.assertEqual(self.request["target_profile"], "mix")
        self.assertNotEqual(self.request["target_profile"], "news")

    def test_20_privacy_proof_and_authority_boundaries_hold(self) -> None:
        authority = self.plan["authority"]
        self.assertTrue(authority["known_business_facts_only"])
        self.assertTrue(authority["known_speaker_facts_only"])
        self.assertFalse(authority["case_facts_transferred"])
        self.assertFalse(authority["pattern_effectiveness_used"])

    def test_21_storyboard_requires_customer_owned_footage(self) -> None:
        storyboard = build_storyboard_plan(self.plan)
        self.assertTrue(
            all(
                item["case_media_allowed"] is False
                and item["footage_gap"]
                == "requires_customer_owned_capture_confirmation"
                for item in storyboard["items"]
            )
        )

    def test_22_fifteen_minutes_does_not_trigger_five_minute_guard(self) -> None:
        errors = bounded_fact_violations(
            "一次真实服务从接收到打包约15分钟，只代表这一次。",
            safe_persona_projection(self.context["persona"]),
        )
        self.assertNotIn("five_minute_scope_or_qualifier_lost", errors)

    def test_23_negated_guarantee_is_a_boundary_not_an_assertion(self) -> None:
        concept = self.by_id["REV2-CONCEPT-001"]
        item = {
            "slot_id": "SLOT_002",
            "concept_ref": concept["concept_id"],
            "central_claim": concept["central_claim"],
            "central_claim_key": concept["semantic_signature"]["central_claim_key"],
            "title": "花蛤临时吐沙要先说清等待",
            "narration": "花蛤如果没提前吐沙，我会先说明需要额外等待，也不能保证完全无沙。",
            "persona_fact_refs_used": concept["primary_fact_refs"],
            "speaker_fact_refs_used": concept["speaker_fact_refs"],
            "claim_candidates": [
                {
                    "text": concept["central_claim"],
                    "persona_fact_refs": concept["primary_fact_refs"],
                    "speaker_fact_refs": concept["speaker_fact_refs"],
                }
            ],
            "customer_feedback_provenance": [],
            "cta": {"present": False, "text": None},
        }
        normalized, errors, _flags = validate_generated_item(
            item,
            set(concept["primary_fact_refs"]),
            safe_persona_projection(self.context["persona"]),
            [],
            "none",
            {"primary_angle": concept["primary_topic"]},
            False,
            set(concept["speaker_fact_refs"]),
            safe_speaker_projection(self.context["speaker_persona"]),
            [],
        )
        self.assertIsNotNone(normalized, errors)
        self.assertNotIn("unsupported_assertion:保证", errors)

    def test_24_explicit_not_industry_standard_is_allowed(self) -> None:
        concept = self.by_id["REV2-CONCEPT-006"]
        good = {
            "title": "我接鱼先看现场状态",
            "narration": "一次经验后，我接鱼会先按鱼腹、看鱼鳃，再决定是否处理；这只是我的习惯，不是行业标准。",
            "central_claim": concept["central_claim"],
        }
        self.assertEqual(
            validate_post_replenishment_script_boundaries(good, concept), []
        )

    def test_25_human_editorial_text_passes_scope_boundaries(self) -> None:
        for concept_id, editorial in POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT.items():
            item = {
                "title": editorial["title"],
                "narration": editorial["narration"],
                "central_claim": self.by_id[concept_id]["central_claim"],
            }
            self.assertEqual(
                validate_post_replenishment_script_boundaries(
                    item, self.by_id[concept_id]
                ),
                [],
                concept_id,
            )

    def test_26_human_clam_wait_wording_keeps_negated_commitment(self) -> None:
        editorial = POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT["REV2-CONCEPT-001"]
        self.assertIn("没法保证完全无沙", editorial["narration"])
        self.assertNotIn("保证吐净", editorial["narration"])

    def test_27_revision_integrity_rejects_central_claim_change(self) -> None:
        source = {"title": "A", "narration": "B", "central_claim": "C"}
        editorial_only = dict(source, title="A2", narration="B2")
        self.assertTrue(
            _post_replenishment_revision_integrity(source, editorial_only)
        )
        self.assertFalse(
            _post_replenishment_revision_integrity(
                source, dict(editorial_only, central_claim="changed")
            )
        )

    def test_28_ledger_lineage_audit_names_both_hash_semantics(self) -> None:
        audit = read_json(
            ROOT
            / "data/generation_batches/real_shufang_mix_003/revisions/revision_0004/content_ledger_lineage_audit_v1.json"
        )
        self.assertTrue(audit["validation"]["passed"])
        self.assertNotEqual(
            audit["ledger_ref"]["file_sha256"],
            audit["ledger_ref"]["canonical_content_sha256"],
        )
        self.assertEqual(
            audit["root_cause"],
            "same_json_file_different_hash_semantics_file_bytes_vs_canonical_sorted_compact_json",
        )

    def test_29_exported_ledger_update_is_append_only_with_information_units(self) -> None:
        source_batch = read_json(
            ROOT
            / "data/generation_batches/real_shufang_mix_003/revisions/revision_0003/generation_batch_v1.json"
        )
        entries = []
        for item in source_batch["contents"]:
            editorial = POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT[item["concept_ref"]]
            entries.append(
                {
                    "content_id": item["content_id"],
                    "concept_ref": item["concept_ref"],
                    "business_id": item["persona_ref"]["persona_id"],
                    "speaker_id": item["speaker_ref"]["persona_id"],
                    "batch_ref": source_batch["request_id"],
                    "production_profile": "mix",
                    "reuse_intent": "novel_content",
                    "semantic_signature": item["semantic_signature"],
                    "presentation_signature": item["presentation_signature"],
                    "central_claim": item["central_claim"],
                    "title": editorial["title"],
                    "narration": editorial["narration"],
                    "primary_fact_refs": sorted(
                        set(item.get("primary_persona_fact_refs") or [])
                        | set(item.get("speaker_fact_refs") or [])
                    ),
                    "supporting_fact_refs": [],
                    "primary_fact_atom_refs": item["primary_fact_atoms"],
                    "exclusive_anchor": item["exclusive_anchor"],
                    "status": "exported",
                    "created_at": source_batch["created_at"],
                    "approved_at": "2026-09-13T00:00:00+00:00",
                    "exported_at": "2026-09-13T00:00:01+00:00",
                    "published_at": None,
                    "events": [],
                }
            )
        business = read_json(self.persona_path)
        speaker = read_json(self.speaker_path)
        atoms = build_fact_atom_catalog(
            business, business["provenance"]["content_sha256"]
        ) + build_fact_atom_catalog(
            speaker, speaker["provenance"]["content_sha256"]
        )
        updated = build_exported_semantic_ledger_update(
            self.ledger,
            entries,
            atoms,
            exported_at="2026-09-13T00:00:01+00:00",
        )
        self.assertEqual(
            updated["entries"][: len(self.ledger["entries"])],
            self.ledger["entries"],
        )
        appended = updated["entries"][-4:]
        self.assertTrue(all(item["status"] == "exported" for item in appended))
        self.assertTrue(
            all(item["communicated_information_units"] for item in appended)
        )
        self.assertTrue(all(item["information_units"] for item in appended))

    def test_30_post_export_capacity_is_recalculated_without_padding(self) -> None:
        source_batch = read_json(
            ROOT
            / "data/generation_batches/real_shufang_mix_003/revisions/revision_0003/generation_batch_v1.json"
        )
        entries = []
        for item in source_batch["contents"]:
            entries.append(
                {
                    "content_id": item["content_id"],
                    "concept_ref": item["concept_ref"],
                    "business_id": item["persona_ref"]["persona_id"],
                    "speaker_id": item["speaker_ref"]["persona_id"],
                    "batch_ref": source_batch["request_id"],
                    "production_profile": "mix",
                    "reuse_intent": "novel_content",
                    "semantic_signature": item["semantic_signature"],
                    "presentation_signature": item["presentation_signature"],
                    "central_claim": item["central_claim"],
                    "title": POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT[
                        item["concept_ref"]
                    ]["title"],
                    "narration": POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT[
                        item["concept_ref"]
                    ]["narration"],
                    "primary_fact_refs": sorted(
                        set(item.get("primary_persona_fact_refs") or [])
                        | set(item.get("speaker_fact_refs") or [])
                    ),
                    "supporting_fact_refs": [],
                    "primary_fact_atom_refs": item["primary_fact_atoms"],
                    "exclusive_anchor": item["exclusive_anchor"],
                    "status": "exported",
                    "created_at": source_batch["created_at"],
                    "approved_at": "2026-09-13T00:00:00+00:00",
                    "exported_at": "2026-09-13T00:00:01+00:00",
                    "published_at": None,
                    "events": [],
                }
            )
        business = read_json(self.persona_path)
        speaker = read_json(self.speaker_path)
        atoms = build_fact_atom_catalog(
            business, business["provenance"]["content_sha256"]
        ) + build_fact_atom_catalog(
            speaker, speaker["provenance"]["content_sha256"]
        )
        updated = build_exported_semantic_ledger_update(
            self.ledger,
            entries,
            atoms,
            exported_at="2026-09-13T00:00:01+00:00",
        )
        result = build_post_export_remaining_capacity(
            self.capacity,
            updated,
            list(POST_REPLENISHMENT_CONCEPT_ALLOWLIST),
            created_at="2026-09-13T00:00:02+00:00",
        )
        self.assertEqual(
            result["recalculation_method"],
            "historical_exposure_plus_material_information_gain_plus_editorial_quality",
        )
        self.assertLessEqual(result["post_export_remaining_capacity"], 8)
        self.assertFalse(result["padding"])
        self.assertTrue(
            all(
                item["concept_id"] not in POST_REPLENISHMENT_CONCEPT_ALLOWLIST
                for item in result["remaining_high_quality_concepts"]
            )
        )

    def test_31_demonstrative_single_order_is_not_business_volume(self) -> None:
        concept = self.by_id["REV2-CONCEPT-010"]
        editorial = POST_REPLENISHMENT_HUMAN_EDITORIAL_TEXT["REV2-CONCEPT-010"]
        item = {
            "concept_ref": concept["concept_id"],
            "central_claim": concept["central_claim"],
            "central_claim_key": concept["semantic_signature"]["central_claim_key"],
            "title": editorial["title"],
            "narration": editorial["narration"],
            "persona_fact_refs_used": concept["primary_fact_refs"],
            "speaker_fact_refs_used": concept["speaker_fact_refs"],
            "claim_candidates": [],
            "customer_feedback_provenance": [],
            "cta": {"present": False, "text": None},
        }
        normalized, errors, _flags = validate_generated_item(
            item,
            set(safe_persona_projection(self.context["persona"])["facts"]),
            safe_persona_projection(self.context["persona"]),
            [],
            "none",
            {"primary_angle": concept["primary_topic"]},
            False,
            set(safe_speaker_projection(self.context["speaker_persona"])["facts"]),
            safe_speaker_projection(self.context["speaker_persona"]),
            [],
        )
        self.assertIsNotNone(normalized, errors)
        self.assertNotIn("unsupported_numeric_fact:一单", errors)


if __name__ == "__main__":
    unittest.main()
