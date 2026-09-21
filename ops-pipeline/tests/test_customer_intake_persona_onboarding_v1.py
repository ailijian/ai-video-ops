from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from authority_test_support import live_authority_root

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = live_authority_root()
SCRIPTS = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from customer_intake_v1 import (  # noqa: E402
    BUSINESS_REV2_REVIEW_REFS,
    apply_persona_revision_2_human_decisions,
    assess_persona_onboarding_readiness,
    build_customer_intake,
    build_fact_extraction_coverage_audit,
    build_revision_input,
    extract_initial_fact_candidates,
    extract_shufang_replenishment_candidates,
    parse_interview_markdown,
    plan_follow_up,
    run_stage_a,
    run_stage_b,
    stage_a_fixtures,
)
from content_quality_v1 import (  # noqa: E402
    canonical_sha256,
    resolve_effective_content_gate_decision,
)
from generate_mix_scripts_v1 import validate_content_plan_input  # noqa: E402
import generate_mix_scripts_v1 as mix_generator  # noqa: E402


INTERVIEW = (
    ROOT
    / "data/content_replenishment/shufang_zhiyuan_community_canteen/intake_0001"
    / "林东方｜内容补充采访单.md"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CustomerIntakePersonaOnboardingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.temp_root = Path(cls.temp.name)
        cls.fixture_answers = stage_a_fixtures()
        cls.initial_intakes = {}
        cls.initial_candidates = {}
        for name, answers in cls.fixture_answers.items():
            intake = build_customer_intake(
                intake_id=f"test_{name}",
                intake_type="initial_onboarding",
                provisional_business_id=f"{name}_business",
                business_ref=None,
                input_actor="authorized_business_representative",
                input_sources=[{"source_type": "test_fixture"}],
                raw_answers=answers,
                speaker_selection={"speaker_type": "frontline_expert"},
                created_at="2026-09-12T00:00:00+00:00",
            )
            cls.initial_intakes[name] = intake
            cls.initial_candidates[name] = extract_initial_fact_candidates(intake)

        cls._live_fixture_ready = False

    @classmethod
    def prepare_live_fixture(cls) -> None:
        if cls._live_fixture_ready:
            return
        raw_answers = parse_interview_markdown(INTERVIEW)
        cls.real_intake = build_customer_intake(
            intake_id="test_real_replenishment",
            intake_type="replenishment",
            provisional_business_id=None,
            business_ref={"persona_id": "shufang_zhiyuan_community_canteen", "revision": 1},
            input_actor="speaker",
            input_sources=[
                {
                    "source_type": "raw_customer_interview_markdown",
                    "source_path": str(INTERVIEW),
                    "source_sha256": sha256(INTERVIEW),
                }
            ],
            raw_answers=raw_answers,
            speaker_selection={
                "speaker_type": "frontline_expert",
                "speaker_ref": {"persona_id": "lin_dongfang_frontline_chef", "revision": 1},
            },
            conflicts=[
                {
                    "conflict_id": "existing_yongtai_entity_binding_concern",
                    "severity": "critical",
                    "resolved": False,
                }
            ],
            created_at="2026-09-12T00:00:00+00:00",
        )
        cls.real_candidates = extract_shufang_replenishment_candidates(cls.real_intake)
        cls.reviewed_candidates = apply_persona_revision_2_human_decisions(
            cls.real_candidates,
            reviewer="李健",
            reviewed_at="2026-09-13T00:00:00+00:00",
        )
        cls.coverage_audit = build_fact_extraction_coverage_audit(
            cls.real_intake,
            cls.reviewed_candidates,
            created_at="2026-09-13T00:00:00+00:00",
        )
        cls._live_fixture_ready = True

    def setUp(self) -> None:
        match = re.match(r"test_(\d+)_", self._testMethodName)
        if (match and int(match.group(1)) >= 11) or self._testMethodName == "test_follow_up_planner_only_targets_critical_missing_truth":
            self.prepare_live_fixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    @classmethod
    def candidate(cls, candidate_id: str) -> dict:
        return next(
            item
            for item in cls.real_candidates["fact_candidates"]
            if item["fact_candidate_id"] == candidate_id
        )

    def test_01_sufficient_initial_intake_reaches_persona_review_ready(self) -> None:
        readiness = assess_persona_onboarding_readiness(
            self.initial_intakes["fixture_a"], self.initial_candidates["fixture_a"]
        )
        self.assertEqual(readiness["status"], "persona_review_ready")

    def test_02_minimal_pet_store_intake_remains_insufficient(self) -> None:
        readiness = assess_persona_onboarding_readiness(
            self.initial_intakes["fixture_b"], self.initial_candidates["fixture_b"]
        )
        self.assertEqual(readiness["status"], "insufficient")
        self.assertIn("business_identity", readiness["critical_missing_truth"])
        self.assertIn("customer_use_context", readiness["critical_missing_truth"])
        self.assertIn("speaker_authority", readiness["critical_missing_truth"])

    def test_03_unknown_fields_are_not_filled(self) -> None:
        candidates = self.initial_candidates["fixture_b"]["fact_candidates"]
        self.assertEqual({item["target_field"] for item in candidates}, {"industry"})
        serialized = json.dumps(candidates, ensure_ascii=False)
        for forbidden in ("客户痛点", "服务流程", "价格", "差异化", "创业"):
            self.assertNotIn(forbidden, serialized)

    def test_04_frontline_speaker_does_not_inherit_founder_first_person(self) -> None:
        candidates = self.initial_candidates["fixture_c"]["fact_candidates"]
        founder = [
            item for item in candidates if item["target_field"] == "founder_or_operator_story"
        ]
        self.assertEqual(founder[0]["persona_scope"], "business")
        speaker_values = json.dumps(
            [item["normalized_value"] for item in candidates if item["persona_scope"] == "speaker"],
            ensure_ascii=False,
        )
        self.assertNotIn("老板因社区缺少及时维修而创办公司", speaker_values)
        self.assertIn("我创办了公司", speaker_values)

    def test_05_raw_answers_are_immutable_during_extraction(self) -> None:
        intake = copy.deepcopy(self.initial_intakes["fixture_a"])
        before = intake["raw_input_contract"]["raw_answers_sha256"]
        extract_initial_fact_candidates(intake)
        self.assertEqual(before, intake["raw_input_contract"]["raw_answers_sha256"])
        self.assertEqual(
            before,
            hashlib.sha256(
                json.dumps(
                    intake["raw_answers"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )

    def test_06_unresolved_conflict_blocks_readiness(self) -> None:
        intake = copy.deepcopy(self.initial_intakes["fixture_a"])
        intake["conflicts"] = [
            {"conflict_id": "C", "severity": "critical", "resolved": False}
        ]
        readiness = assess_persona_onboarding_readiness(
            intake, self.initial_candidates["fixture_a"]
        )
        self.assertEqual(readiness["status"], "insufficient")
        self.assertEqual(readiness["critical_conflicts"][0]["conflict_id"], "C")

    def test_07_readiness_is_capability_based_not_field_percentage(self) -> None:
        readiness = assess_persona_onboarding_readiness(
            self.initial_intakes["fixture_a"], self.initial_candidates["fixture_a"]
        )
        self.assertFalse(readiness["authority"]["field_completion_percentage_used"])
        self.assertEqual(
            set(readiness["capability_groups"]),
            {
                "business_identity",
                "customer_use_context",
                "production_bearing_facts",
                "critical_constraints",
                "speaker_authority",
            },
        )

    def test_08_stage_a_uses_existing_persona_approval_lifecycle(self) -> None:
        summary = run_stage_a(
            self.temp_root / "stage_a_integration",
            created_at="2026-09-12T00:00:00+00:00",
        )
        fixture = summary["fixtures"]["fixture_a"]
        business = json.loads(Path(fixture["business_persona_path"]).read_text(encoding="utf-8"))
        speaker = json.loads(Path(fixture["speaker_persona_path"]).read_text(encoding="utf-8"))
        self.assertEqual(business["lifecycle"]["status"], "approved")
        self.assertEqual(speaker["lifecycle"]["status"], "approved")
        self.assertTrue((Path(fixture["business_persona_path"]).parent / "approval_receipt.json").is_file())
        self.assertTrue(summary["acceptance"]["passed"])

    def test_09_initial_capacity_handoff_uses_quality_engine(self) -> None:
        summary_path = self.temp_root / "stage_a_integration/stage_a_validation_summary_v1.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        capacity = summary["fixtures"]["fixture_a"]["capacity"]
        self.assertEqual(capacity["requested_quantity"], 10)
        self.assertGreater(capacity["high_quality_capacity"], 0)
        self.assertEqual(capacity["capacity_status"], "capacity_limited")
        self.assertFalse(capacity["authority"]["script_generation_performed"])

    def test_10_low_capacity_does_not_unapprove_persona(self) -> None:
        summary = json.loads(
            (self.temp_root / "stage_a_integration/stage_a_validation_summary_v1.json").read_text(encoding="utf-8")
        )
        fixture = summary["fixtures"]["fixture_a"]
        persona = json.loads(Path(fixture["business_persona_path"]).read_text(encoding="utf-8"))
        self.assertEqual(fixture["capacity"]["capacity_status"], "capacity_limited")
        self.assertTrue(persona["lifecycle"]["approved"])

    def test_11_real_interview_is_replenishment_not_initial(self) -> None:
        self.assertEqual(self.real_intake["intake_type"], "replenishment")

    def test_12_interview_actor_types_remain_distinct(self) -> None:
        by_id = {item["answer_id"]: item for item in self.real_intake["raw_answers"]}
        self.assertEqual(by_id["CORE_Q01"]["input_actor"], "speaker")
        self.assertEqual(by_id["CORE_Q10"]["source_type"], "operator_recorded_customer_confirmation")
        self.assertEqual(by_id["OPTIONAL_Q08"]["source_type"], "operator_recorded_authorized_business_representative")
        self.assertEqual(by_id["OPTIONAL_Q09"]["input_actor"], "public_source_recorded_by_operator")

    def test_13_small_sun_authorization_is_single_content_scoped(self) -> None:
        candidate = self.candidate("B-R2-009")
        self.assertEqual(candidate["authorization"]["authorization_scope"], "single_content_use_only")
        self.assertNotIn("reuse_authorized", candidate["normalized_value"])

    def test_14_unauthorized_q5_quote_does_not_inherit_q10_authorization(self) -> None:
        candidate = self.candidate("B-R2-010")
        self.assertEqual(candidate["candidate_state"], "requires_review")
        self.assertEqual(candidate["normalized_value"]["reuse_status"], "unauthorized_for_reuse")

    def test_15_small_sun_photos_and_videos_remain_unauthorized(self) -> None:
        authorization = self.candidate("B-R2-009")["authorization"]
        self.assertFalse(authorization["image"])
        self.assertFalse(authorization["video"])

    def test_16_tao_authorization_preserves_media_and_unknown_scope(self) -> None:
        candidate = self.candidate("B-R2-011")
        auth = candidate["authorization"]
        self.assertFalse(auth["image"])
        self.assertFalse(auth["video"])
        self.assertIsNone(auth["channel_scope"])
        self.assertIsNone(auth["duration_scope"])
        self.assertIsNone(auth["commercial_scope"])

    def test_17_whiteboard_outcome_is_not_proof(self) -> None:
        candidate = self.candidate("B-R2-013")
        self.assertEqual(candidate["candidate_state"], "requires_review")
        self.assertEqual(candidate["normalized_value"]["proof_status"], "candidate_unverified_outcome")
        self.assertIn("not_verified_proof", candidate["speaker_authority_assessment"])

    def test_18_yongtai_entity_data_stays_requires_review(self) -> None:
        for candidate_id in ("B-R2-016", "B-R2-017", "B-R2-018"):
            candidate = self.candidate(candidate_id)
            self.assertEqual(candidate["candidate_state"], "requires_review")
            self.assertEqual(candidate["classification"], "entity_binding_review")
            self.assertIn("existing_yongtai_entity_binding_concern", candidate["conflict_refs"])

    def test_19_extra_fish_processing_fee_stays_requires_review(self) -> None:
        candidate = self.candidate("B-R2-008")
        self.assertEqual(candidate["candidate_state"], "requires_review")
        self.assertIsNone(candidate["normalized_value"]["official_rule"])

    def test_20_culinary_judgment_is_speaker_observation_not_business_truth(self) -> None:
        for candidate_id in ("S-R2-006", "S-R2-007", "S-R2-009"):
            candidate = self.candidate(candidate_id)
            self.assertEqual(candidate["persona_scope"], "speaker")
            self.assertFalse(candidate["normalized_value"]["universal_truth"])

    def test_21_operational_heuristic_is_not_fixed_process_rule(self) -> None:
        candidate = self.candidate("S-R2-004")
        self.assertEqual(candidate["classification"], "speaker_operational_heuristic")
        self.assertFalse(candidate["normalized_value"]["fixed_rule"])

    def test_22_stage_b_preserves_revision_one_and_ledger_hashes(self) -> None:
        project = self.temp_root / "stage_b_project"
        business_src = ROOT / "data/personas/shufang_zhiyuan_community_canteen/revision_0001/persona_v1.json"
        speaker_src = ROOT / "data/personas/lin_dongfang_frontline_chef/revision_0001/persona_v1.json"
        ledger_src = ROOT / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
        business_dst = project / "data/personas/shufang_zhiyuan_community_canteen/revision_0001/persona_v1.json"
        speaker_dst = project / "data/personas/lin_dongfang_frontline_chef/revision_0001/persona_v1.json"
        ledger_dst = project / "data/content_ledgers/shufang_zhiyuan_community_canteen/content_ledger_v1.json"
        for source, target in ((business_src, business_dst), (speaker_src, speaker_dst), (ledger_src, ledger_dst)):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        before = {"business": sha256(business_dst), "speaker": sha256(speaker_dst), "ledger": sha256(ledger_dst)}
        summary = run_stage_b(
            project_root=project,
            interview_path=INTERVIEW,
            output_root=project / "data/customer_intakes/shufang/intake_0001",
            created_at="2026-09-12T00:00:00+00:00",
        )
        after = {"business": sha256(business_dst), "speaker": sha256(speaker_dst), "ledger": sha256(ledger_dst)}
        self.assertEqual(before, after)
        self.assertTrue(summary["frozen_sources_unchanged"])
        self.assertFalse(summary["persona_revision_2_approved"])
        self.assertTrue(Path(summary["business_review_pack_path"]).is_file())
        self.assertTrue(Path(summary["speaker_review_pack_path"]).is_file())
        readiness = json.loads(
            (
                project
                / "data/customer_intakes/shufang/intake_0001/persona_onboarding_readiness_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(readiness["status"], "production_ready")
        self.assertTrue(readiness["candidate_revision_blockers"])
        revision_two = json.loads(
            (
                project
                / "data/personas/shufang_zhiyuan_community_canteen/revision_0002/persona_v1.json"
            ).read_text(encoding="utf-8")
        )
        stories = revision_two["facts"]["authorized_customer_cases_or_feedback"]["value"]
        self.assertEqual(
            sum(str(item.get("customer_label", "")).startswith("陶先生") for item in stories),
            1,
        )
        tao = next(item for item in stories if item.get("customer_label") == "陶先生")
        self.assertFalse(tao["image_authorized"])
        self.assertNotIn("reuse_authorized", tao)

    def test_23_capacity_recalculation_is_blocked_before_rev2_approval(self) -> None:
        summary = json.loads(
            (
                self.temp_root
                / "stage_b_project/data/customer_intakes/shufang/intake_0001/real_replenishment_validation_summary_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            summary["capacity_recalculation_status"],
            "blocked_pending_persona_revision_approval",
        )
        self.assertFalse(summary["scripts_generated"])
        self.assertFalse(summary["production_batch_created"])
        self.assertFalse(summary["excel_exported"])

    def test_24_privacy_authority_proof_and_remote_boundaries_hold(self) -> None:
        authority = self.real_candidates["authority"]
        self.assertTrue(authority["candidates_are_not_known_persona_facts"])
        self.assertTrue(authority["human_review_required"])
        self.assertFalse(authority["case_facts_consumed"])
        self.assertFalse(authority["remote_model_call_performed"])
        serialized = json.dumps(self.real_candidates, ensure_ascii=False)
        self.assertIn("candidate_unverified_outcome", serialized)
        self.assertNotIn('"proof_status": "verified"', serialized)

    def test_25_all_raw_answers_have_explicit_extraction_coverage(self) -> None:
        rows = self.coverage_audit["raw_answer_coverage"]
        self.assertEqual(len(rows), 21)
        self.assertEqual(
            {row["raw_answer_ref"] for row in rows},
            {answer["answer_id"] for answer in self.real_intake["raw_answers"]},
        )
        self.assertEqual(
            self.coverage_audit["summary"]["silently_ignored_raw_answers"], []
        )
        self.assertFalse(
            self.coverage_audit["summary"]["material_extraction_gap_found"]
        )

    def test_26_no_candidate_required_has_an_exclusion_reason(self) -> None:
        rows = self.coverage_audit["raw_answer_coverage"]
        self.assertTrue(
            all(
                row.get("exclusion_reason")
                for row in rows
                if row["coverage_status"] == "no_candidate_required"
            )
        )

    def test_27_s_r2_011_is_a_constraint_not_a_fact_candidate(self) -> None:
        ids = {
            item["fact_candidate_id"]
            for item in self.real_candidates["fact_candidates"]
        }
        self.assertNotIn("S-R2-011", ids)
        constraint = self.real_candidates["derived_authority_constraints"][0]
        self.assertEqual(constraint["constraint_id"], "S-R2-011")
        self.assertFalse(constraint["fact_atom_eligible"])
        self.assertFalse(constraint["content_capacity_eligible"])

    def test_28_s_r2_011_enters_speaker_control_layer_only(self) -> None:
        previous = json.loads(
            (ROOT / "data/personas/lin_dongfang_frontline_chef/revision_0001/persona_v1.json").read_text(
                encoding="utf-8"
            )
        )
        revision_input, applied = build_revision_input(
            previous_persona=previous,
            candidate_artifact=self.reviewed_candidates,
            scope="speaker",
            source_ref="reviewed-candidates",
        )
        controls = revision_input["persona_control_layer"][
            "derived_authority_constraints"
        ]
        self.assertEqual(controls[0]["constraint_id"], "S-R2-011")
        self.assertFalse(revision_input["persona_control_layer"]["fact_atom_eligible"])
        self.assertNotIn("S-R2-011", {item["fact_candidate_id"] for item in applied})

    def test_29_business_scope_normalizations_do_not_become_universal(self) -> None:
        boundary = self.candidate("B-R2-004")["normalized_value"]
        handling = self.candidate("B-R2-005")["normalized_value"]
        self.assertFalse(boundary["company_wide_permanent_policy"])
        self.assertFalse(boundary["industry_rule"])
        self.assertFalse(handling["mandatory_company_wide_process"])

    def test_30_wait_examples_are_not_sla_or_all_time_rules(self) -> None:
        example = self.candidate("B-R2-006")["normalized_value"]
        boundary = self.candidate("B-R2-007")["normalized_value"]
        self.assertFalse(example["typical_wait"])
        self.assertFalse(example["sla"])
        self.assertFalse(example["service_promise"])
        self.assertFalse(boundary["all_time_wait_rule"])

    def test_31_s_r2_002_does_not_create_unconfirmed_pricing(self) -> None:
        practice = self.candidate("S-R2-002")["normalized_value"]
        self.assertFalse(practice["official_pricing_authority"])
        self.assertFalse(practice["new_pricing_amount_or_formula"])

    def test_32_missing_speaker_candidates_are_source_bounded(self) -> None:
        change = self.candidate("S-R2-012")["normalized_value"]
        fish = self.candidate("S-R2-013")["normalized_value"]
        self.assertFalse(change["mandatory_company_wide_policy"])
        self.assertTrue(fish["source_bound_example_and_timing_allowed"])
        self.assertFalse(fish["universal_truth"])

    def test_33_b_r2_019_is_case_specific_and_quote_free(self) -> None:
        service = self.candidate("B-R2-019")["normalized_value"]
        self.assertTrue(service["case_specific_observed_duration"])
        self.assertFalse(service["typical_service_time"])
        self.assertFalse(service["sla"])
        self.assertFalse(service["guaranteed_duration"])
        self.assertFalse(service["customer_quote_included"])

    def test_34_story_truth_remains_conditionally_production_eligible(self) -> None:
        by_id = {
            item["fact_candidate_id"]: item
            for item in self.reviewed_candidates["fact_candidates"]
        }
        self.assertFalse(by_id["B-R2-009"]["production_authority_eligible"])
        self.assertFalse(by_id["B-R2-011"]["production_authority_eligible"])
        self.assertEqual(
            by_id["B-R2-009"]["production_eligibility"]["status"], "conditional"
        )
        self.assertFalse(
            by_id["B-R2-009"]["normalized_value"]["image_authorized"]
        )
        self.assertFalse(
            by_id["B-R2-011"]["normalized_value"]["video_authorized"]
        )

    def test_35_requires_review_decisions_remain_excluded(self) -> None:
        by_id = {
            item["fact_candidate_id"]: item
            for item in self.reviewed_candidates["fact_candidates"]
        }
        for candidate_id in BUSINESS_REV2_REVIEW_REFS:
            self.assertEqual(
                by_id[candidate_id]["human_review"]["decision"],
                "keep_requires_review",
            )
            self.assertFalse(by_id[candidate_id]["production_authority_eligible"])

    def test_36_effective_gate_preserves_legacy_diagnostic(self) -> None:
        concept = {
            "concept_id": "CONCEPT_016",
            "gate_decision": "hard_duplicate_rejected",
            "v1_1_1_gate_decision": "high_quality_novel",
            "replenishment_gate_decision": "high_quality_novel",
        }
        before = copy.deepcopy(concept)
        resolved = resolve_effective_content_gate_decision(concept)
        self.assertEqual(resolved["decision"], "high_quality_novel")
        self.assertEqual(resolved["source_field"], "replenishment_gate_decision")
        self.assertEqual(concept, before)
        self.assertEqual(
            resolved["historical_diagnostics"]["gate_decision"],
            "hard_duplicate_rejected",
        )

    def test_37_rev2_gate_precedence_is_canonical(self) -> None:
        resolved = resolve_effective_content_gate_decision(
            {
                "gate_decision": "hard_duplicate_rejected",
                "v1_1_gate_decision": "historical_exposure_rejected",
                "replenishment_gate_decision": "high_quality_novel",
            }
        )
        self.assertEqual(resolved["policy"], "content_capacity_replenishment_v1")
        self.assertEqual(resolved["decision"], "high_quality_novel")

    def test_38_mix_generation_validation_uses_effective_gate(self) -> None:
        root = self.temp_root / "effective_gate_mix_consumer"
        root.mkdir(parents=True, exist_ok=True)
        paths = {}
        for name, value in {
            "persona": {"persona_id": "business"},
            "request": {"request_id": "request"},
            "source_plan": {"source_plan_id": "source"},
        }.items():
            path = root / f"{name}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            paths[name] = path
        ledger = {"schema_version": "content-ledger-v1.0", "entries": []}
        context = {
            "request": {"request_id": "request"},
            "persona": {"persona_id": "business"},
            "speaker_persona": {"persona_id": "speaker"},
            "paths": paths,
            "source_plan": {
                "eligible_case_pool": [{"case_id": "case"}],
                "selected_patterns": [{"pattern_id": "pattern"}],
            },
        }
        concept = {
            "concept_id": "CONCEPT_016",
            "gate_decision": "hard_duplicate_rejected",
            "replenishment_gate_decision": "high_quality_novel",
            "semantic_signature": {"business_id": "business"},
            "presentation_signature": {"speaker_id": "speaker"},
            "case_structural_ref": "case",
            "pattern_ref": "pattern",
        }
        plan = {
            "schema_version": "content-plan-v1.0",
            "request_id": "request",
            "business_id": "business",
            "speaker_id": "speaker",
            "lineage": {
                "persona": {"sha256": sha256(paths["persona"])},
                "request": {"sha256": sha256(paths["request"])},
                "source_plan": {"sha256": sha256(paths["source_plan"])},
                "content_ledger_sha256": canonical_sha256(ledger),
            },
            "selected_concepts": [concept],
            "capacity": {
                "selected_quantity": 1,
                "high_quality_novel_capacity": 1,
                "padding_generated": False,
            },
            "authority": {"pattern_effectiveness_used": False},
        }
        validate_content_plan_input(context, plan, ledger)
        del concept["replenishment_gate_decision"]
        with self.assertRaisesRegex(RuntimeError, "non-passing"):
            validate_content_plan_input(context, plan, ledger)

    def test_39_news_capacity_consumer_uses_effective_gate(self) -> None:
        concept = {
            "concept_id": "CONCEPT_016",
            "central_claim": "approved replenishment meaning",
            "primary_fact_refs": [],
            "supporting_fact_refs": [],
            "gate_decision": "hard_duplicate_rejected",
            "replenishment_gate_decision": "high_quality_novel",
        }
        with patch.object(
            mix_generator,
            "match_selected_content_to_approved_patterns",
            return_value={"compatible_pattern_count": 1, "assessments": []},
        ):
            result = mix_generator.assess_news_novel_capacity(
                {
                    "request_id": "news-request",
                    "persona_id": "business",
                    "speaker_persona": "speaker",
                    "target_profile": "news",
                    "reuse_intent": "novel_content",
                    "quantity": 1,
                },
                {
                    "selected_concepts": [concept],
                    "capacity": {"high_quality_novel_capacity": 1},
                },
                [],
                {"facts": {}, "authority": {}},
            )
        item = result["remaining_novel_concepts"][0]
        self.assertTrue(item["semantic_novelty"])
        self.assertEqual(
            item["source_content_quality_gate"]["source_field"],
            "replenishment_gate_decision",
        )

    def test_follow_up_planner_only_targets_critical_missing_truth(self) -> None:
        readiness = assess_persona_onboarding_readiness(
            self.initial_intakes["fixture_b"], self.initial_candidates["fixture_b"]
        )
        questions = plan_follow_up(self.initial_intakes["fixture_b"], readiness)
        self.assertEqual(
            {item["reason"] for item in questions}, {"critical_missing_truth"}
        )
        self.assertEqual(len({item["target_topic"] for item in questions}), len(questions))


if __name__ == "__main__":
    unittest.main()


for _name in dir(CustomerIntakePersonaOnboardingTests):
    _match = re.match(r"test_(\d+)_", _name)
    if (_match and int(_match.group(1)) >= 11) or _name == "test_follow_up_planner_only_targets_critical_missing_truth":
        setattr(
            CustomerIntakePersonaOnboardingTests,
            _name,
            pytest.mark.live_authority(
                getattr(CustomerIntakePersonaOnboardingTests, _name)
            ),
        )
