from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from content_quality_v1 import (  # noqa: E402
    approved_persona_ref,
    append_ledger_entries,
    audience_need_lineage_v1_1_1,
    build_content_capacity_replenishment_intake_v1,
    build_content_gap_report_v1,
    build_content_plan_v1_1_1,
    build_content_plan_v1_1,
    build_content_plan,
    build_fact_atom_catalog,
    build_storyboard_plan,
    canonical_sha256,
    editorial_score_v1_1,
    enrich_ledger_with_communicated_information,
    historical_exposure_evaluation,
    infer_audience_need_origin,
    material_information_gain_v1_1_1,
    novel_exclusive_anchor_evaluation,
    novelty_evaluation,
    presentation_signature,
    render_content_capacity_replenishment_intake_markdown,
    reuse_intent_contract,
    semantic_duplicate_reasons,
    semantic_signature,
    speaker_fit_evaluation,
    unsupported_detail_flags_v1_1,
    validate_candidate_authority,
    validate_script_against_plan,
    verify_frozen_hashes,
)
from generate_mix_scripts_v1 import (  # noqa: E402
    RemoteAttemptError,
    generate_batch,
    generate_content_plan_v1,
    persist_remote_failure_telemetry,
    prepare_content_plan_egress,
)


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ContentQualityV1Tests(unittest.TestCase):
    BUSINESS_ID = "business_001"
    SPEAKER_ID = "speaker_001"

    def concept(
        self,
        concept_id: str,
        claim_key: str,
        primary_ref: str = "pricing_facts",
        **changes,
    ) -> dict:
        value = {
            "concept_id": concept_id,
            "audience_need": f"need_{concept_id}",
            "content_job": f"job_{concept_id}",
            "primary_topic": f"topic_{concept_id}",
            "primary_fact_refs": [primary_ref],
            "supporting_fact_refs": [],
            "speaker_fact_refs": ["speaker_role_facts"],
            "central_claim": f"中心结论{concept_id}",
            "central_claim_key": claim_key,
            "exclusive_anchor": {
                "kind": "specific_price",
                "value": f"具体锚点{concept_id}",
                "fact_refs": [primary_ref],
            },
            "customer_story_ref": None,
            "speaker_id": self.SPEAKER_ID,
            "speaker_type": "frontline_expert",
            "opening_strategy": f"opening_{concept_id}",
            "narrative_mode": f"mode_{concept_id}",
            "case_structural_ref": "case_001",
            "visual_anchor": f"visual_{concept_id}",
            "why_publish": f"information_gain_{concept_id}",
        }
        value.update(changes)
        value["semantic_signature"] = semantic_signature(value, self.BUSINESS_ID)
        value["presentation_signature"] = presentation_signature(
            value,
            value.get("speaker_id"),
            value.get("speaker_type"),
        )
        return value

    def ledger_entry(
        self,
        concept: dict,
        status: str = "approved",
        content_id: str = "historical_001",
    ) -> dict:
        return {
            "content_id": content_id,
            "business_id": self.BUSINESS_ID,
            "speaker_id": concept.get("speaker_id"),
            "semantic_signature": concept["semantic_signature"],
            "presentation_signature": concept["presentation_signature"],
            "central_claim": concept["central_claim"],
            "title": "历史标题",
            "narration": "历史口播内容与已批准事实相符。",
            "primary_fact_refs": concept["primary_fact_refs"],
            "supporting_fact_refs": concept.get("supporting_fact_refs") or [],
            "status": status,
        }

    def ledger(self, entries: list[dict] | None = None) -> dict:
        return {
            "schema_version": "content-ledger-v1.0",
            "business_id": self.BUSINESS_ID,
            "entries": entries or [],
        }

    def v1_1_persona(self) -> dict:
        return {
            "persona_id": self.BUSINESS_ID,
            "revision": 1,
            "facts": {
                "differentiators": {
                    "state": "known",
                    "value": [
                        "食材由顾客自行选择",
                        "明厨亮灶，加工过程可见",
                        "加工价格公开清晰",
                    ],
                },
                "core_audience": {
                    "state": "known",
                    "value": ["不太会做饭的年轻夫妻", "周边居民"],
                },
                "customer_pains": {
                    "state": "known",
                    "value": ["不太会做饭", "不想自己从头处理食材"],
                },
                "customer_use_cases": {
                    "state": "known",
                    "value": [
                        "在菜市场购买食材后送至代炒菜窗口加工",
                        "购买梭子蟹等水产后直接加工",
                    ],
                },
                "time_efficiency_fact": {
                    "state": "known",
                    "value": "从购买食材到菜品上桌，全程约30分钟",
                },
                "business_volume_fact": {
                    "state": "known",
                    "value": "平日一餐服务20余位客人，节假日通常生意更好",
                },
                "service_process": {
                    "state": "known",
                    "value": "顾客把买好的食材送至代炒菜窗口",
                },
                "business_principles": {
                    "state": "known",
                    "value": "通过菜场配套服务提升市集便民属性",
                },
                "unknown_fact": {"state": "unknown", "value": "不能使用"},
                "review_fact": {
                    "state": "requires_review",
                    "value": "不能使用",
                },
            },
        }

    def v1_1_ledger(self) -> tuple[dict, list[dict]]:
        persona = self.v1_1_persona()
        entries = [
            {
                "content_id": "B0-C001",
                "business_id": self.BUSINESS_ID,
                "speaker_id": self.SPEAKER_ID,
                "primary_fact_refs": ["service_process"],
                "supporting_fact_refs": ["differentiators"],
                "narration": (
                    "食材由顾客自行选择。顾客把买好的食材送至代炒菜窗口。"
                ),
                "status": "exported",
            },
            {
                "content_id": "B0-C003",
                "business_id": self.BUSINESS_ID,
                "speaker_id": self.SPEAKER_ID,
                "primary_fact_refs": ["differentiators"],
                "supporting_fact_refs": [],
                "narration": "加工价格公开清晰。",
                "status": "exported",
            },
            {
                "content_id": "B0-C006",
                "business_id": self.BUSINESS_ID,
                "speaker_id": self.SPEAKER_ID,
                "primary_fact_refs": ["service_process"],
                "supporting_fact_refs": ["time_efficiency_fact"],
                "narration": "从购买食材到菜品上桌，全程约30分钟。",
                "status": "exported",
            },
            {
                "content_id": "B0-C008",
                "business_id": self.BUSINESS_ID,
                "speaker_id": self.SPEAKER_ID,
                "primary_fact_refs": ["service_process"],
                "supporting_fact_refs": ["differentiators"],
                "narration": "明厨亮灶，加工过程可见。",
                "status": "exported",
            },
            {
                "content_id": "B0-C007",
                "business_id": self.BUSINESS_ID,
                "speaker_id": self.SPEAKER_ID,
                "primary_fact_refs": ["customer_pains"],
                "supporting_fact_refs": ["customer_use_cases"],
                "narration": (
                    "不太会做饭，又不想从头处理食材，可以把买好的食材送到"
                    "代炒菜窗口加工。"
                ),
                "status": "exported",
            },
        ]
        enriched = enrich_ledger_with_communicated_information(
            self.ledger(entries),
            persona,
            "persona-sha-v1",
            migrated_at="2026-09-11T00:00:00+00:00",
        )
        return enriched, enriched["fact_atom_catalog"]

    def exposure_concept(
        self,
        concept_id: str,
        fact_ref: str,
        fact_text: str,
        **changes,
    ) -> dict:
        return self.concept(
            concept_id,
            f"claim_{concept_id}",
            primary_ref=fact_ref,
            central_claim=fact_text,
            primary_topic=fact_text,
            exclusive_anchor={
                "kind": "authorized_specific_fact",
                "value": fact_text,
                "fact_refs": [fact_ref],
            },
            **changes,
        )

    def test_semantic_duplicate_cannot_be_rescued_by_title_change(self) -> None:
        old = self.concept("OLD", "same_claim")
        new = self.concept("NEW", "same_claim", title="完全不同的标题")
        self.assertTrue(semantic_duplicate_reasons(new, old))

    def test_semantic_duplicate_cannot_be_rescued_by_speaker_change(self) -> None:
        old = self.concept("OLD", "same_claim")
        new = self.concept("NEW", "same_claim", speaker_id="brand_speaker")
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        self.assertTrue(semantic_duplicate_reasons(new, old))

    def test_speaker_reframe_with_distinctive_claim_overlap_is_conservative(self) -> None:
        old = self.concept(
            "OLD",
            "taste_request",
            primary_ref="product_or_service_facts",
            central_claim="顾客可以告诉师傅少盐少辣等需求，师傅按要求加工。",
        )
        old["primary_fact_refs"] = ["product_or_service_facts", "differentiators"]
        old["semantic_signature"] = semantic_signature(old, self.BUSINESS_ID)
        new = self.concept(
            "NEW",
            "chef_executes_taste_request",
            primary_ref="product_or_service_facts",
            central_claim="换成主厨来讲，也只是根据少盐少辣等需求进行加工。",
            supporting_fact_refs=["differentiators"],
            speaker_id="brand_speaker",
        )
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        novelty = novelty_evaluation(new, [self.ledger_entry(old)])
        self.assertTrue(novelty["uncertain"])
        self.assertEqual(novelty["decision"], "uncertain")

    def test_semantic_duplicate_cannot_be_rescued_by_case_change(self) -> None:
        old = self.concept("OLD", "same_claim")
        new = self.concept("NEW", "same_claim", case_structural_ref="case_999")
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        self.assertTrue(semantic_duplicate_reasons(new, old))

    def test_mix_history_blocks_same_semantic_content_in_news(self) -> None:
        old = self.concept("OLD", "same_claim", production_profile="mix")
        old["presentation_signature"] = presentation_signature(
            old, old["speaker_id"], old["speaker_type"]
        )
        new = self.concept("NEW", "same_claim", production_profile="news")
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        new["presentation_signature"] = presentation_signature(
            new, new["speaker_id"], new["speaker_type"]
        )
        entry = self.ledger_entry(old)
        entry["production_profile"] = "mix"
        novelty = novelty_evaluation(new, [entry])
        self.assertTrue(novelty["hard_duplicate"])
        self.assertEqual(new["presentation_signature"]["production_profile"], "news")

    def test_news_history_blocks_same_semantic_content_in_mix(self) -> None:
        old = self.concept("OLD", "same_claim", production_profile="news")
        new = self.concept("NEW", "same_claim", production_profile="mix")
        entry = self.ledger_entry(old)
        entry["production_profile"] = "news"
        self.assertTrue(novelty_evaluation(new, [entry])["hard_duplicate"])

    def test_production_profile_is_presentation_not_semantic_identity(self) -> None:
        mix = self.concept("SAME", "same_claim", production_profile="mix")
        news = self.concept("SAME", "same_claim", production_profile="news")
        mix_semantic = semantic_signature(mix, self.BUSINESS_ID)
        news_semantic = semantic_signature(news, self.BUSINESS_ID)
        self.assertEqual(mix_semantic, news_semantic)
        self.assertNotEqual(
            presentation_signature(mix, self.SPEAKER_ID, "frontline_expert"),
            presentation_signature(news, self.SPEAKER_ID, "frontline_expert"),
        )

    def test_cross_profile_repurpose_is_reused_content_not_novel_capacity(self) -> None:
        contract = reuse_intent_contract(
            "cross_profile_repurpose", ["historical_mix_001"]
        )
        self.assertTrue(contract["reused_semantic_content"])
        self.assertFalse(contract["novel_content"])
        self.assertFalse(contract["novel_capacity_eligible"])
        self.assertFalse(contract["historical_exposure_reset"])

    def test_profile_metadata_does_not_change_fact_authority(self) -> None:
        candidate = self.concept("PROFILE", "claim", production_profile="news")
        valid, errors = validate_candidate_authority(
            candidate,
            {"pricing_facts"},
            {"speaker_role_facts"},
        )
        self.assertIsNotNone(valid)
        self.assertEqual(errors, [])

    def test_same_customer_quote_and_takeaway_rejects(self) -> None:
        old = self.concept(
            "OLD",
            "same_takeaway",
            primary_ref="authorized_customer_cases_or_feedback",
            customer_story_ref="quote:001",
        )
        new = self.concept(
            "NEW",
            "same_takeaway",
            primary_ref="authorized_customer_cases_or_feedback",
            customer_story_ref="quote:001",
        )
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        reasons = semantic_duplicate_reasons(new, old)
        self.assertIn("same_customer_story_or_quote_and_takeaway", reasons)

    def test_supporting_fact_reuse_is_allowed(self) -> None:
        old = self.concept(
            "OLD",
            "old_claim",
            primary_ref="pricing_facts",
            supporting_fact_refs=["included_service_facts"],
        )
        new = self.concept(
            "NEW",
            "new_claim",
            primary_ref="service_time_facts",
            supporting_fact_refs=["included_service_facts"],
        )
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        novelty = novelty_evaluation(new, [self.ledger_entry(old)])
        self.assertFalse(novelty["hard_duplicate"])
        self.assertFalse(
            any(
                item.get("fact_ref") == "included_service_facts"
                and item["code"] == "recent_primary_fact_overuse"
                for item in novelty["strong_penalties"]
            )
        )

    def test_primary_fact_overuse_receives_penalty(self) -> None:
        old = self.concept("OLD", "old_claim", primary_ref="pricing_facts")
        new = self.concept("NEW", "new_claim", primary_ref="pricing_facts")
        new["semantic_signature"] = semantic_signature(new, self.BUSINESS_ID)
        novelty = novelty_evaluation(new, [self.ledger_entry(old)])
        self.assertTrue(
            any(
                item["code"] == "recent_primary_fact_overuse"
                for item in novelty["strong_penalties"]
            )
        )

    def test_narrow_price_repaint_is_rejected_when_bundle_was_fully_covered(self) -> None:
        old = self.concept(
            "OLD",
            "all_prices",
            central_claim="加工费按菜品类型区分，素菜8-10元，清蒸15元，红烧18元。",
            exclusive_anchor={
                "kind": "specific_price",
                "value": "素菜8-10元、清蒸15元、红烧18元",
                "fact_refs": ["pricing_facts"],
            },
        )
        old_entry = self.ledger_entry(old)
        old_entry["narration"] = "素菜八到十块，清蒸十五块，红烧十八块，价格公开清晰。"
        new = self.concept(
            "NEW",
            "vegetable_price_only",
            central_claim="素菜加工费通常是8-10元。",
            exclusive_anchor={
                "kind": "specific_price",
                "value": "素菜8-10元",
                "fact_refs": ["pricing_facts"],
            },
        )
        reasons = semantic_duplicate_reasons(new, old_entry)
        self.assertIn("same_primary_fact_takeaway_already_covered", reasons)

    def test_same_number_for_different_price_categories_is_not_hard_duplicate(self) -> None:
        vegetable = self.concept(
            "VEGETABLE",
            "vegetable_price",
            central_claim="素菜加工费约15元。",
            exclusive_anchor={
                "kind": "specific_price",
                "value": "素菜15元",
                "fact_refs": ["pricing_facts"],
            },
        )
        fish = self.concept(
            "FISH",
            "fish_price",
            central_claim="鱼类加工费约15元。",
            exclusive_anchor={
                "kind": "specific_price",
                "value": "鱼类15元",
                "fact_refs": ["pricing_facts"],
            },
        )
        self.assertFalse(semantic_duplicate_reasons(vegetable, fish))

    def test_semantic_uncertain_candidate_is_not_auto_selected(self) -> None:
        candidates = [
            self.concept(
                "A",
                "volume_regular_day",
                primary_ref="business_volume_fact",
                central_claim="平日一餐能接待20余位客人，节假日生意通常更好。",
            ),
            self.concept(
                "B",
                "volume_peak_queue",
                primary_ref="business_volume_fact",
                central_claim="平日一餐能接待20余位客人，高峰期可能排队。",
            ),
        ]
        plan = build_content_plan(
            request={"request_id": "r", "quantity": 2, "profile": "mix"},
            business_id=self.BUSINESS_ID,
            speaker_id=self.SPEAKER_ID,
            speaker_type="frontline_expert",
            allowed_fact_refs={"business_volume_fact"},
            allowed_speaker_fact_refs={"speaker_role_facts"},
            ledger=self.ledger(),
            raw_candidates=candidates,
            case_rotation=["case_001"],
            pattern_id="pattern_001",
            source_lineage={},
            config={"minimum_editorial_score": 0},
        )
        self.assertEqual(plan["capacity"]["selected_quantity"], 1)
        self.assertTrue(
            any(
                item.get("gate_decision") == "semantic_uncertain_review_required"
                for item in plan["novelty_gate"]["rejected_candidates"]
            )
        )

    def test_rejected_or_generated_draft_does_not_poison_ledger(self) -> None:
        old = self.concept("OLD", "same_claim")
        new = self.concept("NEW", "same_claim")
        novelty = novelty_evaluation(
            new,
            [self.ledger_entry(old, status="generated")],
        )
        self.assertFalse(novelty["hard_duplicate"])

    def test_approved_historical_item_enters_strong_memory(self) -> None:
        old = self.concept("OLD", "same_claim")
        new = self.concept("NEW", "same_claim")
        novelty = novelty_evaluation(new, [self.ledger_entry(old, status="approved")])
        self.assertTrue(novelty["hard_duplicate"])

    def test_capacity_limited_is_valid_and_does_not_pad(self) -> None:
        request = {"request_id": "request_001", "quantity": 3, "profile": "mix"}
        candidates = [
            self.concept("A", "claim_a"),
            self.concept("B", "claim_b", primary_ref="service_time_facts"),
        ]
        plan = build_content_plan(
            request=request,
            business_id=self.BUSINESS_ID,
            speaker_id=self.SPEAKER_ID,
            speaker_type="frontline_expert",
            allowed_fact_refs={"pricing_facts", "service_time_facts"},
            allowed_speaker_fact_refs={"speaker_role_facts"},
            ledger=self.ledger(),
            raw_candidates=candidates,
            case_rotation=["case_001"],
            pattern_id="pattern_001",
            source_lineage={},
            config={"minimum_editorial_score": 0, "candidate_pool_size": 30},
        )
        self.assertEqual(plan["capacity"]["status"], "capacity_limited")
        self.assertEqual(plan["capacity"]["high_quality_novel_capacity"], 2)
        self.assertEqual(plan["capacity"]["selected_quantity"], 2)
        self.assertFalse(plan["capacity"]["padding_generated"])
        self.assertTrue(plan["validation"]["passed"])

    def test_unknown_and_requires_review_facts_remain_excluded(self) -> None:
        candidate = self.concept("A", "claim_a", primary_ref="unknown_fact")
        valid, errors = validate_candidate_authority(
            candidate,
            {"pricing_facts"},
            {"speaker_role_facts"},
        )
        self.assertIsNone(valid)
        self.assertTrue(any("non_known_or_ineligible" in error for error in errors))

        invented = self.concept(
            "B",
            "claim_b",
            central_claim="加工只要99元",
        )
        valid, errors = validate_candidate_authority(
            invented,
            {"pricing_facts"},
            {"speaker_role_facts"},
            {"pricing_facts": ["加工约10元"]},
            {"speaker_role_facts": ["负责窗口加工"]},
        )
        self.assertIsNone(valid)
        self.assertTrue(any("unsupported_numeric_fact" in error for error in errors))

    def test_speaker_authority_remains_enforced(self) -> None:
        candidate = self.concept(
            "A",
            "claim_a",
            speaker_fact_refs=["founder_story"],
        )
        valid, errors = validate_candidate_authority(
            candidate,
            {"pricing_facts"},
            {"speaker_role_facts"},
        )
        self.assertIsNone(valid)
        self.assertTrue(any("speaker_fact_refs" in error for error in errors))

    def test_case_facts_cannot_transfer(self) -> None:
        candidate = self.concept("A", "claim_a", primary_ref="case_specific_fact")
        valid, errors = validate_candidate_authority(
            candidate,
            {"pricing_facts"},
            {"speaker_role_facts"},
        )
        self.assertIsNone(valid)
        self.assertTrue(any("non_known_or_ineligible" in error for error in errors))

    def test_pattern_effectiveness_remains_unused_and_storyboard_is_internal(self) -> None:
        plan = build_content_plan(
            request={"request_id": "r", "quantity": 1, "profile": "mix"},
            business_id=self.BUSINESS_ID,
            speaker_id=self.SPEAKER_ID,
            speaker_type="frontline_expert",
            allowed_fact_refs={"pricing_facts"},
            allowed_speaker_fact_refs={"speaker_role_facts"},
            ledger=self.ledger(),
            raw_candidates=[self.concept("A", "claim_a")],
            case_rotation=["case_001"],
            pattern_id="pattern_001",
            source_lineage={},
            config={"minimum_editorial_score": 0},
        )
        self.assertFalse(plan["authority"]["pattern_effectiveness_used"])
        self.assertFalse(plan["opportunity_structure"]["case_determines_topic"])
        storyboard = build_storyboard_plan(plan)
        self.assertEqual(storyboard["profile"], "mix")
        self.assertEqual(
            storyboard["storyboard_contract_shape"],
            "narration_to_visual_many_to_many",
        )
        self.assertFalse(storyboard["authority"]["excel_contract_changed"])
        self.assertFalse(
            storyboard["authority"]["storyboard_diversity_resets_semantic_novelty"]
        )

    def test_selected_script_cannot_drift_into_historical_duplicate(self) -> None:
        historical = self.concept("OLD", "old_claim")
        selected = self.concept(
            "NEW",
            "new_claim",
            primary_ref="pricing_facts",
            central_claim="真正的新结论",
        )
        generated = {
            "concept_ref": "NEW",
            "central_claim": historical["central_claim"],
            "central_claim_key": "old_claim",
            "persona_fact_refs_used": ["pricing_facts"],
            "title": "换了标题",
            "narration": "换了措辞，但回到了旧结论。",
        }
        errors = validate_script_against_plan(
            generated,
            selected,
            [self.ledger_entry(historical)],
        )
        self.assertTrue(any("drift" in error for error in errors))
        self.assertTrue(any("historical_semantic_duplicate" in error for error in errors))

    def test_append_only_ledger_rejects_duplicate_id(self) -> None:
        concept = self.concept("OLD", "old_claim")
        entry = self.ledger_entry(concept)
        with self.assertRaisesRegex(ValueError, "append-only"):
            append_ledger_entries(self.ledger([entry]), [entry])

    def test_privacy_gate_prepares_only_known_projection_before_planning(self) -> None:
        context = {
            "request": {
                "request_id": "r",
                "quantity": 1,
                "profile": "mix",
                "content_quality_v1": {"enabled": True},
            },
            "persona": {
                "persona_id": self.BUSINESS_ID,
                "facts": {
                    "pricing_facts": {"state": "known", "value": ["约10元"]},
                    "business_address": {
                        "state": "known",
                        "value": "上海市测试路99号",
                    },
                    "information_requiring_human_review": {
                        "state": "requires_review",
                        "value": ["手机号 13800138000"],
                    },
                },
            },
            "speaker_persona": None,
        }
        safe, prompt, audit = prepare_content_plan_egress(context, self.ledger())
        self.assertIn("pricing_facts", safe["business_persona"]["facts"])
        self.assertNotIn("上海市测试路99号", prompt)
        self.assertNotIn("13800138000", prompt)
        self.assertEqual(audit["privacy_state"], "safe_for_external_model")

    def quality_context(self, root: Path) -> dict:
        persona = {
            "persona_id": self.BUSINESS_ID,
            "revision": 1,
            "facts": {
                "pricing_facts": {"state": "known", "value": ["加工约10元"]},
                "service_time_facts": {"state": "known", "value": ["约5分钟"]},
            },
        }
        request = {
            "request_id": "quality_request",
            "profile": "mix",
            "quantity": 1,
            "content_intent": "mixed",
            "cta_intent": "none",
            "content_quality_v1": {
                "enabled": True,
                "candidate_pool_size": 1,
                "minimum_editorial_score": 0,
            },
        }
        source_plan = {
            "selected_patterns": [{"pattern_id": "pattern_001"}],
            "eligible_case_pool": [
                {"case_id": "case_001", "fingerprint_sha": "fingerprint-sha"}
            ],
            "rotation": {"case_rotation_order": ["case_001"]},
        }
        pattern = {"pattern_id": "pattern_001"}
        paths = {}
        for name, value in (
            ("persona", persona),
            ("request", request),
            ("source_plan", source_plan),
            ("pattern", pattern),
        ):
            path = root / f"{name}.json"
            write_json(path, value)
            paths[name] = path
        fingerprint_path = root / "fingerprint.json"
        write_json(fingerprint_path, {"case_id": "case_001"})
        return {
            "paths": paths,
            "persona": persona,
            "request": request,
            "source_plan": source_plan,
            "pattern": pattern,
            "speaker_persona": None,
            "fingerprints": {
                "case_001": {
                    "path": str(fingerprint_path),
                    "sha256": "fingerprint-sha",
                    "surrogate_ref": "CASE_REF_001",
                    "projection": {
                        "structural_ref": "CASE_REF_001",
                        "narrative_structure": {"stage_sequence": ["hook", "payoff"]},
                    },
                }
            },
        }

    def test_quality_plan_to_existing_generator_is_traceable_and_review_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = self.quality_context(Path(directory))
            ledger = self.ledger()
            candidate = self.concept(
                "CONCEPT_001",
                "new_price_detail",
                speaker_fact_refs=[],
                central_claim="加工价格有一个经批准的具体数字。",
            )

            def planning_transport(_prompt: str) -> dict:
                payload = {"candidates": [candidate]}
                return {
                    "payload": payload,
                    "response_sha256": canonical_sha256(payload),
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "elapsed_seconds": 0.01,
                }

            plan = generate_content_plan_v1(
                context,
                ledger,
                transport=planning_transport,
                created_at="2026-09-11T00:00:00+00:00",
            )
            selected = plan["selected_concepts"][0]

            def script_transport(_prompt: str) -> dict:
                payload = {
                    "items": [
                        {
                            "slot_id": "SLOT_001",
                            "concept_ref": selected["concept_id"],
                            "central_claim": selected["central_claim"],
                            "central_claim_key": selected["semantic_signature"]["central_claim_key"],
                            "title": "具体价格怎么理解",
                            "narration": "加工价格有经批准的具体信息，实际表达保留约字限定。",
                            "persona_fact_refs_used": ["pricing_facts"],
                            "speaker_fact_refs_used": [],
                            "claim_candidates": [],
                            "customer_feedback_provenance": [],
                            "cta": {"present": False, "text": None},
                        }
                    ]
                }
                return {
                    "payload": payload,
                    "response_sha256": canonical_sha256(payload),
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "elapsed_seconds": 0.01,
                }

            batch = generate_batch(
                context,
                transport=script_transport,
                created_at="2026-09-11T00:00:01+00:00",
                content_plan=plan,
                content_ledger=ledger,
            )
            self.assertEqual(batch["status"], "review_required")
            self.assertEqual(batch["generated_count"], 1)
            self.assertEqual(batch["contents"][0]["concept_ref"], "CONCEPT_001")
            self.assertTrue(batch["validation"]["script_level_novelty_passed"])
            self.assertFalse(batch["authority"]["case_facts_transferred"])
            self.assertFalse(batch["authority"]["pattern_effectiveness_used"])

    def test_historical_supporting_fact_promoted_to_primary_is_not_novel(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "PROMOTED",
            "time_efficiency_fact",
            "从购买食材到菜品上桌，全程约30分钟",
        )
        exposure = historical_exposure_evaluation(candidate, ledger)
        self.assertEqual(exposure["decision"], "duplicate")
        self.assertFalse(exposure["material_information_gain"])
        self.assertIn("B0-C006", {
            unit["source_content_id"] for unit in exposure["historical_unit_matches"]
        })

    def test_b0_30_minute_fact_blocks_same_information_concept(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "TIME",
            "time_efficiency_fact",
            "买好菜到上桌全程约30分钟",
        )
        self.assertEqual(
            historical_exposure_evaluation(candidate, ledger)["decision"],
            "duplicate",
        )

    def test_b0_open_kitchen_exposure_blocks_same_information_concept(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "VISIBLE",
            "differentiators",
            "明厨亮灶，加工过程看得见",
        )
        self.assertEqual(
            historical_exposure_evaluation(candidate, ledger)["decision"],
            "duplicate",
        )

    def test_b0_customer_selection_exposure_blocks_same_information_concept(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "SELECT",
            "differentiators",
            "食材由顾客自己选择",
        )
        self.assertEqual(
            historical_exposure_evaluation(candidate, ledger)["decision"],
            "duplicate",
        )

    def test_b0_price_transparency_exposure_blocks_same_information_concept(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "PRICE",
            "differentiators",
            "加工价格公开清晰",
        )
        self.assertEqual(
            historical_exposure_evaluation(candidate, ledger)["decision"],
            "duplicate",
        )

    def test_new_fact_with_old_supporting_fact_can_remain_novel(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "VOLUME",
            "business_volume_fact",
            "平日一餐服务20余位客人，节假日通常生意更好",
            supporting_fact_refs=["service_process"],
            why_publish="顾客把买好的食材送至代炒菜窗口，帮助理解服务现场。",
        )
        exposure = historical_exposure_evaluation(candidate, ledger)
        self.assertEqual(exposure["decision"], "materially_different")
        self.assertTrue(exposure["material_information_gain"])
        self.assertEqual(exposure["historical_supporting_fact_reuse_ratio"], 1.0)

    def test_atomic_fact_ids_are_stable_and_do_not_mutate_persona_authority(self) -> None:
        persona = self.v1_1_persona()
        before = json.loads(json.dumps(persona, ensure_ascii=False))
        first = build_fact_atom_catalog(persona, "persona-sha-v1")
        second = build_fact_atom_catalog(persona, "persona-sha-v1")
        self.assertEqual(
            [item["fact_atom_id"] for item in first],
            [item["fact_atom_id"] for item in second],
        )
        self.assertEqual(persona, before)
        self.assertTrue(all(item["authority"] == "derived_planning_identity_only" for item in first))
        self.assertFalse(any(item["field"] in {"unknown_fact", "review_fact"} for item in first))

    def test_audience_need_hypothesis_is_labeled_and_not_max_relevance(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "VOLUME",
            "business_volume_fact",
            "平日一餐服务20余位客人，节假日通常生意更好",
        )
        origin = infer_audience_need_origin(candidate)
        exposure = historical_exposure_evaluation(candidate, ledger)
        fit = speaker_fit_evaluation(candidate, "frontline_expert")
        anchor = novel_exclusive_anchor_evaluation(candidate, ledger)
        score = editorial_score_v1_1(candidate, exposure, origin, fit, anchor)
        self.assertEqual(origin["origin"], "editorial_hypothesis")
        self.assertFalse(origin["customer_need_claimed_as_known"])
        self.assertLess(score["dimensions"]["audience_relevance"], 5.0)

    def test_speaker_authority_pass_does_not_imply_max_speaker_fit(self) -> None:
        candidate = self.exposure_concept(
            "PRINCIPLES",
            "business_principles",
            "通过菜场配套服务提升市集便民属性",
        )
        fit = speaker_fit_evaluation(candidate, "frontline_expert")
        self.assertTrue(fit["authority_pass"])
        self.assertLess(fit["score"], 5.0)

    def test_historical_supporting_reuse_dilutes_single_focus(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "VOLUME",
            "business_volume_fact",
            "平日一餐服务20余位客人，节假日通常生意更好",
            supporting_fact_refs=["service_process"],
            why_publish="顾客把买好的食材送至代炒菜窗口。",
        )
        origin = infer_audience_need_origin(candidate)
        fit = speaker_fit_evaluation(candidate, "frontline_expert")
        anchor = novel_exclusive_anchor_evaluation(candidate, ledger)
        reused = historical_exposure_evaluation(candidate, ledger)
        clean = dict(reused, historical_supporting_fact_reuse_ratio=0.0)
        reused_score = editorial_score_v1_1(candidate, reused, origin, fit, anchor)
        clean_score = editorial_score_v1_1(candidate, clean, origin, fit, anchor)
        self.assertGreater(reused_score["single_focus_dilution"], clean_score["single_focus_dilution"])
        self.assertLess(
            reused_score["dimensions"]["single_focus"],
            clean_score["dimensions"]["single_focus"],
        )

    def test_novel_exclusive_anchor_requires_no_historical_exposure(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        historical = self.exposure_concept(
            "OLD_ANCHOR",
            "time_efficiency_fact",
            "从购买食材到菜品上桌，全程约30分钟",
        )
        novel = self.exposure_concept(
            "NEW_ANCHOR",
            "business_volume_fact",
            "平日一餐服务20余位客人，节假日通常生意更好",
        )
        self.assertFalse(
            novel_exclusive_anchor_evaluation(historical, ledger)[
                "novel_exclusive_anchor"
            ]
        )
        self.assertTrue(
            novel_exclusive_anchor_evaluation(novel, ledger)[
                "novel_exclusive_anchor"
            ]
        )

    def test_v1_1_reranking_is_offline_and_does_not_generate_scripts(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        candidate = self.exposure_concept(
            "VOLUME",
            "business_volume_fact",
            "平日一餐服务20余位客人，节假日通常生意更好",
        )
        v1_plan = {
            "speaker_id": self.SPEAKER_ID,
            "candidate_pool": {
                "configured_size": 1,
                "received_size": 1,
                "candidates": [candidate],
            },
        }
        request = {
            "request_id": "offline_v1_1",
            "quantity": 10,
            "content_quality_v1": {"minimum_editorial_score": 0},
        }
        plan = build_content_plan_v1_1(
            v1_plan=v1_plan,
            ledger=ledger,
            request=request,
            speaker_type="frontline_expert",
            authorized_fact_values=self.v1_1_persona()["facts"],
            source_artifact_hashes={"content_plan_v1": "preserved"},
            created_at="2026-09-11T00:00:00+00:00",
        )
        self.assertFalse(plan["remote_model_call"]["performed"])
        self.assertEqual(plan["remote_model_call"]["call_count"], 0)
        self.assertFalse(plan["capacity"]["script_generation_performed"])
        self.assertFalse(plan["capacity"]["padding_generated"])
        self.assertTrue(plan["candidate_pool"]["source_pool_fully_accounted_for"])

    def test_unsupported_physical_location_detail_is_flagged(self) -> None:
        candidate = self.exposure_concept(
            "PRICE_LOCATION",
            "differentiators",
            "加工价格就贴在窗口",
            visual_anchor="站在窗口外就能看到价目表",
        )
        flags = unsupported_detail_flags_v1_1(
            candidate,
            {"differentiators": ["加工价格公开清晰", "明厨亮灶，加工过程可见"]},
        )
        self.assertIn("unsupported_price_display_location", flags)
        self.assertIn("unsupported_observer_location", flags)

    def test_remote_failure_telemetry_preserves_cost_and_parse_failure_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request_path = root / "data" / "generation_requests" / "r" / "request.json"
            write_json(request_path, {"request_id": "r"})
            context = {
                "paths": {"request": request_path},
                "request": {"request_id": "r"},
            }
            exc = RemoteAttemptError(
                "truncated",
                {
                    "error_type": "truncated_json_response",
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 200,
                        "total_tokens": 300,
                    },
                    "elapsed_seconds": 1.25,
                    "response_sha256": "response-hash",
                    "finish_reason": "length",
                    "artifact_written": False,
                },
            )
            path = persist_remote_failure_telemetry(
                context,
                "content_planning",
                1,
                exc,
                {
                    "rendered_prompt_sha256": "prompt-hash",
                    "safe_input_sha256": "input-hash",
                },
            )
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["provider_usage"]["total_tokens"], 300)
            self.assertEqual(record["elapsed_seconds"], 1.25)
            self.assertEqual(record["response_sha256"], "response-hash")
            self.assertEqual(record["error_type"], "truncated_json_response")
            self.assertFalse(record["artifact_written"])

    def test_audience_label_change_alone_is_not_material_information_gain(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        concept = self.exposure_concept(
            "AUDIENCE_RELABEL",
            "core_audience",
            "不太会做饭的年轻夫妻，可以把买好的食材送到代炒菜窗口加工",
            supporting_fact_refs=["customer_pains", "customer_use_cases"],
            audience_need="想知道年轻夫妻不会做饭能不能用这个服务",
            content_job="目标人群适用场景说明",
        )
        concept["historical_exposure_summary"] = historical_exposure_evaluation(
            concept, ledger
        )
        concept["novel_exclusive_anchor_summary"] = (
            novel_exclusive_anchor_evaluation(concept, ledger)
        )
        decision = material_information_gain_v1_1_1(concept, ledger)
        self.assertTrue(decision["only_new_audience_labels"])
        self.assertTrue(decision["historical_functional_information_covered"])
        self.assertEqual(
            decision["decision"], "insufficient_material_information_gain"
        )

    def test_known_audience_plus_historical_use_case_is_not_automatically_novel(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        concept = self.exposure_concept(
            "KNOWN_AUDIENCE_OLD_USE",
            "core_audience",
            "周边居民不想处理食材时，可以送到代炒菜窗口加工",
            supporting_fact_refs=["customer_pains", "customer_use_cases"],
            audience_need="周边居民是否适合使用已有代炒服务",
            content_job="把旧使用方式绑定到已知客群",
        )
        concept["historical_exposure_summary"] = historical_exposure_evaluation(
            concept, ledger
        )
        concept["novel_exclusive_anchor_summary"] = (
            novel_exclusive_anchor_evaluation(concept, ledger)
        )
        self.assertFalse(
            material_information_gain_v1_1_1(concept, ledger)[
                "material_information_gain"
            ]
        )

    def test_service_decision_need_requires_stable_fact_atom_source_refs(self) -> None:
        ledger, atoms = self.v1_1_ledger()
        concept = self.exposure_concept(
            "PRICE_DECISION",
            "differentiators",
            "加工价格公开清晰",
            audience_need="想知道加工价格是否公开清晰",
        )
        lineage = audience_need_lineage_v1_1_1(concept, atoms)
        self.assertEqual(lineage["origin"], "service_decision_need")
        self.assertTrue(lineage["audience_need_source_refs"])
        stable_ids = {atom["fact_atom_id"] for atom in atoms}
        self.assertTrue(
            set(lineage["audience_need_source_refs"]).issubset(stable_ids)
        )
        self.assertTrue(lineage["service_decision_need_source_valid"])

    def test_missing_audience_need_source_refs_downgrades_to_hypothesis(self) -> None:
        _ledger, atoms = self.v1_1_ledger()
        concept = self.exposure_concept(
            "VAGUE_DECISION",
            "service_process",
            "这是一个值得了解的服务话题",
            audience_need="想了解一个新的兴趣点",
            content_job="兴趣说明",
        )
        lineage = audience_need_lineage_v1_1_1(concept, atoms)
        self.assertEqual(lineage["origin"], "editorial_hypothesis")
        self.assertEqual(lineage["audience_need_source_refs"], [])
        self.assertEqual(lineage["source_type"], "hypothesis")
        self.assertEqual(lineage["authority"], "editorial_only")

    def test_known_use_case_need_lineage_points_to_exact_fact_atom(self) -> None:
        _ledger, atoms = self.v1_1_ledger()
        concept = self.exposure_concept(
            "SEAFOOD",
            "customer_use_cases",
            "购买梭子蟹等水产后可以直接加工",
            audience_need="想知道梭子蟹等水产能不能直接加工",
        )
        lineage = audience_need_lineage_v1_1_1(concept, atoms)
        self.assertEqual(lineage["origin"], "known_use_case")
        self.assertEqual(len(lineage["audience_need_source_refs"]), 1)
        source = lineage["source_lineage"][0]
        self.assertEqual(source["source_ref"], source["fact_atom_id"])
        self.assertEqual(source["field"], "customer_use_cases")
        self.assertEqual(source["persona_sha256"], "persona-sha-v1")

    def test_actual_v1_1_1_capacity_can_fall_from_three_to_two_offline(self) -> None:
        v1_1_path = (
            ROOT
            / "data"
            / "content_plans"
            / "real_shufang_mix_002"
            / "revisions"
            / "v1_1"
            / "content_plan_v1_1.json"
        )
        ledger_path = (
            ROOT
            / "data"
            / "content_ledgers"
            / "shufang_zhiyuan_community_canteen"
            / "content_ledger_v1.json"
        )
        request_path = (
            ROOT
            / "data"
            / "generation_requests"
            / "real_shufang_mix_002"
            / "generation_request_v1.json"
        )
        v1_1 = json.loads(v1_1_path.read_text(encoding="utf-8"))
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        request = json.loads(request_path.read_text(encoding="utf-8"))
        plan = build_content_plan_v1_1_1(
            v1_1_plan=v1_1,
            ledger=ledger,
            request=request,
            source_artifact_hashes={
                "content_plan_v1_1": sha256(v1_1_path),
                "content_ledger_v1": sha256(ledger_path),
            },
            created_at="2026-09-11T00:00:00+00:00",
        )
        self.assertEqual(v1_1["capacity"]["high_quality_novel_capacity"], 3)
        self.assertEqual(plan["capacity"]["high_quality_novel_capacity"], 2)
        self.assertEqual(plan["capacity"]["novelty_surviving_capacity"], 3)
        self.assertEqual(
            plan["closure_calibration"]["concept_018_final_decision"],
            "insufficient_material_information_gain",
        )
        self.assertEqual(plan["remote_model_call"]["call_count"], 0)
        self.assertFalse(plan["capacity"]["script_generation_performed"])
        self.assertFalse(plan["capacity"]["padding_generated"])
        self.assertEqual(
            plan["audience_need_lineage_summary"][
                "service_decision_need_without_source_refs"
            ],
            0,
        )

    def test_content_gap_report_is_read_only_and_uses_only_known_fact_atoms(self) -> None:
        ledger, _atoms = self.v1_1_ledger()
        persona = self.v1_1_persona()
        speaker = {
            "speaker_type": "frontline_expert",
            "facts": {
                "speaker_role_facts": {
                    "state": "known",
                    "value": ["负责现场加工"],
                },
                "private_unknown": {
                    "state": "unknown",
                    "value": "UNKNOWN_SENTINEL_MUST_NOT_APPEAR",
                },
                "private_review": {
                    "state": "requires_review",
                    "value": "REVIEW_SENTINEL_MUST_NOT_APPEAR",
                },
            },
        }
        ledger_before = json.loads(json.dumps(ledger, ensure_ascii=False))
        persona_before = json.loads(json.dumps(persona, ensure_ascii=False))
        minimal_plan = {
            "business_id": self.BUSINESS_ID,
            "speaker_id": self.SPEAKER_ID,
            "capacity": {
                "requested_quantity": 10,
                "high_quality_novel_capacity": 2,
            },
            "selected_concepts": [],
            "editorial_ranking_v1_1_1": {"revision_required_concepts": []},
            "novelty_gate_v1_1_1": {
                "insufficient_material_information_gain_candidates": []
            },
        }
        report = build_content_gap_report_v1(
            content_plan_v1_1_1=minimal_plan,
            ledger=ledger,
            speaker_persona=speaker,
            source_artifact_hashes={
                "content_plan_v1_1_1": "plan-sha",
                "content_ledger_v1": "ledger-sha",
            },
            created_at="2026-09-11T00:00:00+00:00",
        )
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertEqual(ledger, ledger_before)
        self.assertEqual(persona, persona_before)
        self.assertNotIn("UNKNOWN_SENTINEL_MUST_NOT_APPEAR", serialized)
        self.assertNotIn("REVIEW_SENTINEL_MUST_NOT_APPEAR", serialized)
        self.assertFalse(report["authority"]["new_persona_facts_created"])
        self.assertFalse(report["collection_boundary"]["persona_writeback"])
        self.assertEqual(
            report["lineage"]["source_fact_states_consumed"], ["known"]
        )
        self.assertTrue(report["content_gap_categories"])
        self.assertTrue(
            all(
                item["expected_capacity_gain"]["disclaimer"]
                == "heuristic_not_performance_prediction"
                for item in report["content_gap_categories"]
            )
        )

    def actual_replenishment_inputs(self) -> dict:
        business_path = (
            ROOT
            / "data"
            / "personas"
            / "shufang_zhiyuan_community_canteen"
            / "revision_0001"
            / "persona_v1.json"
        )
        business_approval_path = business_path.parent / "approval_receipt.json"
        speaker_path = (
            ROOT
            / "data"
            / "personas"
            / "lin_dongfang_frontline_chef"
            / "revision_0001"
            / "persona_v1.json"
        )
        speaker_approval_path = speaker_path.parent / "approval_receipt.json"
        ledger_path = (
            ROOT
            / "data"
            / "content_ledgers"
            / "shufang_zhiyuan_community_canteen"
            / "content_ledger_v1.json"
        )
        gap_path = (
            ROOT
            / "data"
            / "content_gap_reports"
            / "real_shufang_mix_002"
            / "content_gap_report_v1.json"
        )
        business, business_ref = approved_persona_ref(
            persona_path=business_path,
            approval_receipt_path=business_approval_path,
            expected_scope="business",
        )
        speaker, speaker_ref = approved_persona_ref(
            persona_path=speaker_path,
            approval_receipt_path=speaker_approval_path,
            expected_scope="speaker",
        )
        return {
            "business": business,
            "business_ref": business_ref,
            "speaker": speaker,
            "speaker_ref": speaker_ref,
            "ledger": json.loads(ledger_path.read_text(encoding="utf-8")),
            "ledger_path": ledger_path,
            "gap": json.loads(gap_path.read_text(encoding="utf-8")),
            "gap_path": gap_path,
        }

    def build_actual_replenishment_intake(self, inputs: dict | None = None) -> dict:
        inputs = inputs or self.actual_replenishment_inputs()
        return build_content_capacity_replenishment_intake_v1(
            intake_id="intake_0001",
            business_persona=inputs["business"],
            business_persona_ref=inputs["business_ref"],
            speaker_persona=inputs["speaker"],
            speaker_persona_ref=inputs["speaker_ref"],
            ledger=inputs["ledger"],
            ledger_ref={
                "path": str(inputs["ledger_path"]),
                "sha256": sha256(inputs["ledger_path"]),
                "schema_version": inputs["ledger"].get("schema_version"),
            },
            gap_report=inputs["gap"],
            gap_report_ref=str(inputs["gap_path"]),
            gap_report_sha256=sha256(inputs["gap_path"]),
            created_at="2026-09-11T00:00:00+00:00",
        )

    def test_replenishment_intake_is_gap_driven_and_skips_covered_basics(self) -> None:
        inputs = self.actual_replenishment_inputs()
        intake = self.build_actual_replenishment_intake(inputs)
        questions = [
            question
            for group in intake["question_groups"]
            for question in group["questions"]
        ]
        question_text = "\n".join(item["question_text"] for item in questions)
        self.assertNotIn("代炒菜多少钱", question_text)
        self.assertNotIn("是否支持少盐少辣", question_text)
        self.assertNotIn("油盐酱料是否免费", question_text)
        self.assertNotIn("米饭是否免费", question_text)
        self.assertNotIn("代炒菜基本流程是什么", question_text)
        self.assertNotIn("一般要等多久", question_text)
        self.assertNotIn("是否明厨亮灶", question_text)
        self.assertNotIn("顾客是否自己选食材", question_text)
        gap_categories = {
            item["category"] for item in inputs["gap"]["content_gap_categories"]
        }
        self.assertTrue(all(item["gap_category"] in gap_categories for item in questions))
        matrix_refs = {
            question_id
            for row in intake["gap_coverage_matrix"]
            for key in ("core_question_refs", "optional_question_refs")
            for question_id in row[key]
        }
        self.assertEqual(matrix_refs, {item["question_id"] for item in questions})
        self.assertEqual(
            next(
                group["question_count"]
                for group in intake["question_groups"]
                if group["group_id"] == "core_interview"
            ),
            12,
        )

    def test_replenishment_intake_routes_questions_to_natural_roles(self) -> None:
        intake = self.build_actual_replenishment_intake()
        questions = [
            question
            for group in intake["question_groups"]
            for question in group["questions"]
        ]
        strategic = [
            item
            for item in questions
            if item["gap_category"] in {"business_decisions", "brand_context"}
        ]
        self.assertTrue(strategic)
        self.assertTrue(
            all(item["recommended_target_role"] != "frontline_chef" for item in strategic)
        )
        business_decision = next(
            item for item in questions if item["gap_category"] == "business_decisions"
        )
        self.assertEqual(business_decision["recommended_target_role"], "brand_operator")
        frontline_text = "\n".join(
            item["question_text"]
            for item in questions
            if item["recommended_target_role"] == "frontline_chef"
        )
        self.assertNotIn("品牌战略", frontline_text)

    def test_replenishment_intake_preserves_authority_and_defaults_answers(self) -> None:
        inputs = self.actual_replenishment_inputs()
        inputs["business"]["facts"]["private_unknown_test"] = {
            "state": "unknown",
            "value": "UNKNOWN_INTAKE_SENTINEL",
        }
        inputs["speaker"]["facts"]["private_review_test"] = {
            "state": "requires_review",
            "value": "REVIEW_INTAKE_SENTINEL",
        }
        business_before = json.loads(json.dumps(inputs["business"], ensure_ascii=False))
        speaker_before = json.loads(json.dumps(inputs["speaker"], ensure_ascii=False))
        ledger_before = json.loads(json.dumps(inputs["ledger"], ensure_ascii=False))
        intake = self.build_actual_replenishment_intake(inputs)
        markdown = render_content_capacity_replenishment_intake_markdown(
            intake,
            business_persona=inputs["business"],
            speaker_persona=inputs["speaker"],
        )
        questions = [
            question
            for group in intake["question_groups"]
            for question in group["questions"]
        ]
        serialized = json.dumps(intake, ensure_ascii=False)
        self.assertEqual(inputs["business"], business_before)
        self.assertEqual(inputs["speaker"], speaker_before)
        self.assertEqual(inputs["ledger"], ledger_before)
        self.assertNotIn("UNKNOWN_INTAKE_SENTINEL", serialized)
        self.assertNotIn("REVIEW_INTAKE_SENTINEL", serialized)
        self.assertNotIn("UNKNOWN_INTAKE_SENTINEL", markdown)
        self.assertNotIn("REVIEW_INTAKE_SENTINEL", markdown)
        self.assertTrue(all(item["answer_status"] == "unanswered" for item in questions))
        self.assertTrue(
            all(item["authority_state"] == "raw_input_pending_review" for item in questions)
        )
        self.assertTrue(all(item["creates_persona_fact"] is False for item in questions))
        story_questions = [
            item for item in questions if item["gap_category"] == "customer_stories"
        ]
        self.assertTrue(story_questions)
        self.assertTrue(
            all(item["reuse_authorization_required"] is True for item in story_questions)
        )
        self.assertTrue(intake["answer_contract"]["answer_never_becomes_known_automatically"])
        self.assertFalse(intake["authority_notice"]["new_persona_facts_created"])
        self.assertFalse(
            intake["authority_notice"]["unknown_or_requires_review_consumed_as_known"]
        )
        self.assertNotIn("source_content_plan_ref", intake)
        self.assertEqual(intake["remote_model_telemetry"]["calls"], 0)

    def test_replenishment_human_pack_hides_internal_lineage(self) -> None:
        inputs = self.actual_replenishment_inputs()
        intake = self.build_actual_replenishment_intake(inputs)
        markdown = render_content_capacity_replenishment_intake_markdown(
            intake,
            business_persona=inputs["business"],
            speaker_persona=inputs["speaker"],
        )
        self.assertIn("# 林东方｜内容补充采访单", markdown)
        self.assertIn("【为什么问】", markdown)
        self.assertIn("【客户回答】", markdown)
        self.assertNotIn("SHA", markdown)
        self.assertNotIn("fact_atom", markdown)
        self.assertNotIn("::", markdown)
        self.assertIsNone(__import__("re").search(r"\b[0-9a-f]{64}\b", markdown))

    def test_current_v1_diagnostic_artifacts_remain_unchanged(self) -> None:
        expected = {
            ROOT / "data" / "content_plans" / "real_shufang_mix_002" / "content_plan_v1.json": "2f046c06acfb3e5101251e5fd01fbaa098ba05a35c1b1f6106dfbce65658eaa7",
            ROOT / "data" / "generation_batches" / "real_shufang_mix_002" / "generation_batch_v1.json": "cfd78730f3b85f8f0c1a3c4360f3c43bce289411a1c08799b4f191ba8aa262b1",
            ROOT / "data" / "generation_batches" / "real_shufang_mix_002" / "generation_review_pack_v1.md": "ff6844f9c676c4b5804f72ad94ef741abbebad3ec0fbd28bbb25692f9c803b2e",
            ROOT / "data" / "comparisons" / "real_shufang_mix_002" / "b0_vs_v1_content_quality_scorecard.json": "8293ea43b6194460f90232311e67075713620947207058376fb4609a22992856",
            ROOT / "data" / "content_plans" / "real_shufang_mix_002" / "revisions" / "v1_1" / "content_plan_v1_1.json": "0293516e3b1c7300dbc225810bb4a09d96d61933cf118bd82de43ed3ff54c868",
            ROOT / "data" / "content_reviews" / "real_shufang_mix_002" / "v1_diagnostic_human_review_v1_1.json": "1678ae2634271021c6d5a588b840e54ddc0024c1d3ff4694727a1006f5b9bc06",
            ROOT / "data" / "comparisons" / "real_shufang_mix_002" / "v1_vs_v1_1_content_quality_scorecard.json": "db637d40c9d0fd144495a67d61f0c12d1a9f56fffe49ce6da2d7121962acb75e",
            ROOT / "data" / "content_plans" / "real_shufang_mix_002" / "revisions" / "v1_1_1" / "content_plan_v1_1_1.json": "6b2e4be58076902ae6f5173a656b7c560573de24e61893d02ea19d1a70dad3b5",
            ROOT / "data" / "content_gap_reports" / "real_shufang_mix_002" / "content_gap_report_v1.json": "6fe68fa78d12ea48ceb7674582188372722b037a1fea8473988fd25a75cf734c",
            ROOT / "data" / "comparisons" / "real_shufang_mix_002" / "v1_vs_v1_1_vs_v1_1_1_content_quality_scorecard.json": "41e42a28b32730da0dad842d7512f91b2862df9c9c1c78f5d7990552bf9e7f6e",
        }
        for path, digest in expected.items():
            self.assertTrue(path.exists(), path)
            self.assertEqual(sha256(path), digest, path)
        ledger_path = (
            ROOT
            / "data"
            / "content_ledgers"
            / "shufang_zhiyuan_community_canteen"
            / "content_ledger_v1.json"
        )
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        self.assertEqual(len(ledger["entries"]), 17)
        history = ledger["extensions"]["presentation_history_v1"]
        self.assertEqual(history["storage_policy"], "append_only")
        self.assertFalse(history["semantic_novelty_authority"])
        self.assertEqual(len(history["entries"]), 1)
        presentation = history["entries"][0]
        self.assertEqual(
            presentation["source_content_ref"], "real_shufang_mix_001-C003"
        )
        self.assertFalse(presentation["semantic_novelty"])
        self.assertFalse(presentation["communicated_information_units_created"])

    def test_replenishment_sources_keep_approved_persona_hashes(self) -> None:
        expected = {
            ROOT / "data" / "personas" / "shufang_zhiyuan_community_canteen" / "revision_0001" / "persona_v1.json": "afe96d4df60634040f88c9c33959ede228c3f6f5c559c243b856f16d421c04d0",
            ROOT / "data" / "personas" / "lin_dongfang_frontline_chef" / "revision_0001" / "persona_v1.json": "4f9a14f4694e966afcf90dea9b27121ff5a29092a26dca6d98475d569bdbc00b",
        }
        for path, digest in expected.items():
            self.assertEqual(sha256(path), digest, path)

    def test_old_b0_hashes_remain_unchanged(self) -> None:
        source = ROOT / "data" / "generation_batches" / "real_shufang_mix_001" / "revisions" / "revision_0005" / "generation_batch_v1.json"
        approved = source.parent / "approved_generation_batch_v1.json"
        excel = ROOT / "output" / "real_shufang_mix_001_approved_mix_scripts.xlsx"
        frozen = verify_frozen_hashes(
            source,
            approved,
            excel,
            "446a1b07b041e9d8bf7748a9d2895b9b54950c65c77df6c571a3f5e347622a98",
            "a3ccc68991df5a16483bf6c2d81db362aaaa2976fd58e19362e54e2edbc0235a",
            "1c64d2f46c5878506ad5880f8ca137fda34d3860759a66791ec1b3aa1a54a910",
        )
        self.assertEqual(len(frozen), 3)


if __name__ == "__main__":
    unittest.main()
