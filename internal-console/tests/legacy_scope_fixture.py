"""Entirely fictional historical Golden; approvals use the real Persona owner."""
import copy
import json

from approve_persona_v1 import approve_persona
from build_persona_v1 import build_persona
import customer_constraints_v1 as constraints

BID = "golden_scope_business"
SID = "golden_scope_speaker"
NAME = "合成蓝禾社区食堂"
EXTERNAL = "合成星湾便民市场"
STAMP = "2026-10-01T08:00:00+00:00"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def seed(root):
    directory = root / "data/customer_intakes" / BID / "intake_0001"
    answer = {"answer_id": "OPTIONAL_Q09", "answer_text": f"我是{EXTERNAL}的示例丁。{NAME}的服务是我们推动市场转型的一部分。我们提供租金优惠、免租，午市四五十单、晚市三四十单，每日约100人。", "source_ref": "synthetic-interview#OPTIONAL_Q09"}
    values = [
        {"entity": EXTERNAL, "claims": ["午市四五十单", "晚市三四十单", "单日约100人"], "entity_binding": "unresolved"},
        {"entity": EXTERNAL, "claims": ["租金优惠", "免租"], "entity_binding": "unresolved"},
        {"speaker_or_source_entity": f"示例丁 / {EXTERNAL}", "target_business": NAME, "required_decision": "confirm_same_entity_or_define_relationship_and_data_scope"},
    ]
    ids = ["B-R2-016", "B-R2-017", "B-R2-018"]
    control = {"constraint_id": "S-R2-011", "type": "derived_speaker_authority_constraint",
        "normalized_constraint": ["本人不得以第一人称确认另一市场的整体经营或租金数据"],
        "fact_atom_eligible": False, "content_capacity_eligible": False, "new_customer_truth": False}
    reviewed = {"schema_version": "persona-fact-candidates-v1.0", "status": "human_review_closed",
        "intake_ref": {"intake_id": "golden_historical_materials_001", "raw_answers_sha256": constraints.digest([answer])},
        "fact_candidates": [{"fact_candidate_id": identity, "persona_scope": "business", "target_field": "information_requiring_human_review",
            "normalized_value": value, "source_excerpt": f"我是{EXTERNAL}的示例丁。", "raw_answer_ref": answer["answer_id"],
            "source_ref": answer["source_ref"], "candidate_state": "requires_review", "production_authority_eligible": False,
            "human_review": {"decision": "keep_requires_review", "reviewer": "fictional_human", "reviewed_at": STAMP}}
            for identity, value in zip(ids, values)], "derived_authority_constraints": [control]}
    decision = {"schema_version": "persona-revision-2-human-review-decision-v1.0", "reviewer": "fictional_human", "reviewed_at": STAMP,
        "decision": "approve_with_exclusions_and_constraints", "business": {"approved_delta_refs": [], "excluded_review_refs": ids},
        "speaker": {"derived_constraint_refs": [control["constraint_id"]]}}
    decision_path = write(directory / "persona_revision_2_human_review_decision_v1.json", decision)
    write(directory / "fact_candidates_human_reviewed_v1.json", reviewed)
    metadata = {"decision_artifact_ref": {"path": str(decision_path), "sha256": constraints.file_sha(decision_path)}, "excluded_review_refs": ids}
    def known(value):
        return {"state": "known", "value": value, "source_refs": ["synthetic-independent-customer-interview"]}
    facts = {"public_display_name": known(NAME), "primary_products_or_services": known(["代炒菜服务"]),
        "core_audience": known(["社区居民"]), "pricing_facts": known(["素菜加工费8元", "独立菜单套餐100元"]),
        "process_facts": known(["先确认口味再加工"]), "industry": known("餐饮服务"),
        "business_volume_fact": known(["平日一餐20余位客人"])}
    for revision in (1, 2):
        source = {"persona_id": BID, "persona_scope": "business", "revision": revision, "fixture_only": True,
            "source_type": "synthetic_human_reviewed", "source_ref": "synthetic-independent-customer-interview", "facts": copy.deepcopy(facts)}
        if revision == 2:
            source["facts"]["information_requiring_human_review"] = {"state": "requires_review", "value": values,
                "source_refs": [answer["source_ref"]], "review_note": "外部来源归属未核实，不得用于生产。"}
        input_path = write(root / "data/persona_inputs" / BID / f"business_{revision}.json", source)
        path, _ = build_persona(input_path, root / "data/personas", previous_persona_path=previous if revision == 2 else None)
        approve_persona(path, "fictional_human", "Explicit fictional historical approval", STAMP,
            decision_metadata=metadata if revision == 2 else None)
        previous = path
    speaker_input = {"persona_id": SID, "persona_scope": "speaker", "revision": 1, "fixture_only": True,
        "speaker_type": "frontline_expert", "business_persona_ref": BID,
        "source_type": "synthetic_human_reviewed", "source_ref": "synthetic-speaker-interview",
        "facts": {"public_display_name": known("合成厨师小禾"), "public_role": known("厨师"),
            "speaker_role_facts": known(["亲自确认口味并加工"]), "first_person_allowed_topics": known(["本人加工实践"])},
        "persona_control_layer": {"derived_authority_constraints": [control]}}
    speaker_path, _ = build_persona(write(root / "data/persona_inputs" / SID / "speaker_1.json", speaker_input),
        root / "data/personas", business_persona_path=path)
    approve_persona(speaker_path, "fictional_human", "Explicit fictional Speaker approval", STAMP,
        decision_metadata={"decision_artifact_ref": metadata["decision_artifact_ref"], "derived_constraint_refs": [control["constraint_id"]]})
    intake = {"schema_version": "customer-intake-v1.0", "intake_id": "golden_historical_materials_001", "provisional_business_id": BID,
        "raw_answers": [answer], "raw_input_contract": {"raw_answers_sha256": constraints.digest([answer])},
        "conflicts": [{"conflict_id": "external_entity_binding", "severity": "critical", "resolved": False,
            "topic": f"{EXTERNAL}与{NAME}的实体/数据口径关系", "resolution_question": "请核实外部来源的数据归属。"}],
        "created_at": STAMP, "updated_at": STAMP}
    original = root / "data/content_replenishment" / BID / "source.md"
    original.parent.mkdir(parents=True, exist_ok=True); original.write_text(answer["answer_text"], encoding="utf-8")
    intake["input_sources"] = [{"source_path": str(original), "source_sha256": constraints.file_sha(original), "immutable": True}]
    write(directory / "customer_intake_v1.json", intake)
    legacy = constraints.legacy_critical_constraints(root, BID)[0]
    target = {k: legacy[k] for k in ("constraint_id", "source_intake_id", "raw_answers_sha256")}
    target["constraint_sha256"] = constraints.digest(legacy["record"])
    return {"business_path": path, "speaker_path": speaker_path, "target": target, "directory": directory}
