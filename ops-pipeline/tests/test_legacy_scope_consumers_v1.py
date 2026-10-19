"""Real consumer gates on a wholly synthetic, formally approved historical Golden."""
import json
from pathlib import Path
import sqlite3
import sys
import uuid

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "ops-pipeline/scripts"))
sys.path.insert(0, str(REPO / "internal-console/tests"))
import customer_constraints_v1 as constraints
import legacy_constraint_scope_v1 as scope
from legacy_scope_fixture import seed, BID, EXTERNAL, write
from generate_mix_scripts_v1 import safe_persona_projection, validate_generated_item
from export_mix_excel_v1 import export_mix_excel
from review_generation_batch_v2 import review_generation_batch_v2


@pytest.fixture()
def scoped(tmp_path):
    data = seed(tmp_path)
    database = tmp_path / "synthetic.sqlite3"
    actor = {"namespace": "a" * 32, "user_id": 1}
    with sqlite3.connect(database) as db:
        db.executescript("CREATE TABLE console_principal_namespace(singleton INTEGER,namespace TEXT); CREATE TABLE users(id INTEGER,status TEXT,must_change_password INTEGER);")
        db.execute("INSERT INTO console_principal_namespace VALUES(1,?)", (actor["namespace"],))
        db.execute("INSERT INTO users VALUES(1,'active',0)")
    scope.manage_reviewer(tmp_path, actor, action="grant", operator="synthetic-operator", reason="Explicit synthetic grant")
    evidence = scope.evidence_bundle(tmp_path, BID, data["target"], ["OPTIONAL_Q09"])
    scope.adjudicate(tmp_path, database, BID, actor, {"target": data["target"], "decision": "external_claims_only",
        "raw_answer_refs": ["OPTIONAL_Q09"], "blocked_terms": evidence["required_terms"],
        "reason": "关系未核实，仅排除精确外部主张", "operation_id": uuid.uuid4().hex, "context_sha256": scope.context_digest(evidence, None)})
    return tmp_path, data


def test_matching_atoms_and_model_context_do_not_consume_excluded_sources(scoped):
    from match_generation_sources_v1 import load_approved_persona
    from content_quality_v1 import build_fact_atom_catalog
    root, data = scoped
    persona, sha = load_approved_persona(data["business_path"])
    safe = safe_persona_projection(persona)
    atoms = build_fact_atom_catalog(persona, sha, set(safe["facts"]))
    text = json.dumps(atoms, ensure_ascii=False)
    assert "information_requiring_human_review" not in safe["facts"]
    assert "四五十" not in text and EXTERNAL not in text and "B-R2-016" not in text
    assert any("20余位" in json.dumps(atom, ensure_ascii=False) for atom in atoms)
    assert "evidence_quote" not in json.dumps(safe, ensure_ascii=False)


@pytest.mark.parametrize("text", ["市场给予食堂长期扶持", "我们午市四五十单", "出租方为我们减轻房租负担", "中午接待50单", "一天接待一百位客人"])
def test_generation_and_regeneration_validator_rejects_external_claims(scoped, text):
    _, data = scoped
    safe = safe_persona_projection(constraints.read(data["business_path"]))
    _, errors, _ = validate_generated_item({"title": "合成内容", "narration": text, "persona_fact_refs_used": ["process_facts"]},
        set(safe["facts"]), safe, [], None)
    assert any("forbidden" in error for error in errors)


@pytest.mark.parametrize("decision", ["approved", "revised"])
def test_human_review_and_editorial_revision_cannot_approve_external_claims(scoped, decision):
    root, data = scoped
    batch = {"schema_version": "generation-batch-v1.0", "request_id": "synthetic_review", "status": "review_required", "profile": "mix",
        "validation": {"passed": True}, "lineage": {"persona": {"path": str(data["business_path"]), "sha256": constraints.file_sha(data["business_path"])}},
        "contents": [{"content_id": "synthetic-C001", "title": "合成内容", "narration": "市场给予食堂长期扶持"}]}
    path = write(root / "synthetic-review/generation_batch_v1.json", batch)
    review_item = {"content_id": "synthetic-C001", "decision": decision}
    if decision == "revised":
        review_item.update(revised_title="合成修改", revised_narration="出租方为我们减轻房租负担", meaning_preserved=True, new_facts_added=False)
    review = write(root / "synthetic-review/input.json", {"schema_version": "generation-batch-review-input-v2.0", "reviewer": "synthetic-human", "note": "explicit", "items": [review_item]})
    with pytest.raises(RuntimeError, match="FORBIDDEN"):
        review_generation_batch_v2(batch_path=path, review_input_path=review)
    assert not (path.parent / "generation_human_review_v2.json").exists()


@pytest.mark.parametrize("field", ["narration", "central_claim"])
def test_export_rechecks_scope_before_writing_output(scoped, field):
    root, data = scoped
    batch = write(root / "synthetic-export/approved.json", {"status": "approved", "profile": "mix",
        "human_review": {"all_export_items_human_approved": True},
        "lineage": {"persona": {"path": str(data["business_path"]), "sha256": constraints.file_sha(data["business_path"])}},
        "contents": [{"status": "human_approved", "title": "合成内容", field: "市场给予食堂长期扶持"}]})
    template = root / "synthetic-export/template.xlsx"; template.write_bytes(b"unused: gate runs before workbook load")
    output = root / "synthetic-export/output.xlsx"
    with pytest.raises(RuntimeError, match="FORBIDDEN"):
        export_mix_excel(batch, template, output)
    assert not output.exists()


def test_claim_metadata_cannot_smuggle_external_source_into_ledger(scoped):
    _, data = scoped
    safe = safe_persona_projection(constraints.read(data["business_path"]))
    _, errors, _ = validate_generated_item({"title": "合成内容", "narration": "先确认口味，再加工食材。", "central_claim": EXTERNAL + "支持我们经营",
        "persona_fact_refs_used": ["process_facts"]}, set(safe["facts"]), safe, [], None)
    assert "legacy_scope_forbidden_external_claim" in errors
