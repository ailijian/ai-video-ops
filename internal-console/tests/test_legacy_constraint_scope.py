import copy
import json
import uuid
import subprocess

import pytest
from conftest import login_and_change_password
from app.case_library_access import principal
from app.operation_lock import authority_operation_lock
import customer_constraints_v1 as constraints
import legacy_constraint_scope_v1 as scope
from content_creation_entry_v1 import build_content_creation_entry, ContentCreationEntryError
from legacy_scope_fixture import seed, BID, SID, EXTERNAL, write


@pytest.fixture()
def golden(client, settings):
    csrf = login_and_change_password(client)
    data = seed(settings.pipeline_root)
    actor = principal(settings, 1)
    return client, settings, csrf, data, actor


def grant(golden, action="grant"):
    _, settings, _, _, actor = golden
    return scope.manage_reviewer(settings.pipeline_root, actor, action=action,
        operator="fictional-local-operator", reason="Explicit isolated Golden reviewer")


def payload(golden, decision="external_claims_only"):
    _, settings, _, data, _ = golden
    evidence = scope.evidence_bundle(settings.pipeline_root, BID, data["target"], ["OPTIONAL_Q09"])
    history = scope.receipts(settings.pipeline_root, BID)
    return {"target": data["target"], "decision": decision, "raw_answer_refs": ["OPTIONAL_Q09"],
        "blocked_terms": [EXTERNAL, "示例丁"],
        "reason": "仅裁决外部来源适用范围，关系仍未核实，禁止相关主张和派生关系。",
        "operation_id": uuid.uuid4().hex, "context_sha256": scope.context_digest(evidence, history[-1]["sha256"] if history else None)}


def post(golden, request):
    client, _, csrf, _, _ = golden
    return client.post(f"/api/customers/{BID}/legacy-scope", headers={"X-CSRF-Token": csrf}, json=request)


def hashes(root):
    return {str(p): constraints.file_sha(p) for p in root.rglob("*.json")}


def test_no_adjudication_and_ai_fields_cannot_release(golden):
    _, settings, _, data, _ = golden
    persona = constraints.read(data["business_path"])
    with pytest.raises(RuntimeError, match="BUSINESS_CONSTRAINT_BLOCKED"):
        constraints.assert_production_allowed(persona, data["business_path"])
    grant(golden)
    request = {**payload(golden), "actor": {"user_id": 999}, "auto_approval": True}
    assert post(golden, request).status_code == 409
    assert not scope.receipts(settings.pipeline_root, BID)


@pytest.mark.parametrize("decision", ["insufficient_evidence", "core_identity_unresolved"])
def test_b_c_keep_business_blocked(golden, decision):
    _, settings, _, data, _ = golden; grant(golden)
    saved = post(golden, payload(golden, decision)); assert saved.status_code == 200, saved.text
    assert saved.json()["receipt"]["relationship_status"] == "unresolved"
    with pytest.raises(RuntimeError, match="BUSINESS_CONSTRAINT_BLOCKED"):
        constraints.assert_production_allowed(constraints.read(data["business_path"]), data["business_path"])


def test_authorization_csrf_actor_revocation_and_lock(golden):
    client, settings, _, _, actor = golden
    request = payload(golden)
    assert post(golden, request).status_code == 403
    assert client.post(f"/api/customers/{BID}/legacy-scope", json=request).status_code == 403
    grant(golden)
    with authority_operation_lock(settings, "business", BID):
        assert post(golden, request).status_code == 409
    grant(golden, "revoke")
    assert post(golden, request).status_code == 403
    assert not scope.receipts(settings.pipeline_root, BID)


@pytest.mark.parametrize("field", ["source_intake_id", "raw_answers_sha256", "constraint_sha256"])
def test_wrong_source_binding_rejected(golden, field):
    grant(golden); request = copy.deepcopy(payload(golden)); request["target"][field] = "wrong"
    assert post(golden, request).status_code == 409


def test_formal_typed_identity_conflict_not_eligible(golden):
    _, settings, _, data, _ = golden; grant(golden); request = payload(golden)
    path = data["directory"] / "customer_intake_v1.json"; intake = constraints.read(path)
    intake["conflicts"][0].update(scope="business", constraint_type="identity_conflict")
    write(path, intake); request["target"]["constraint_sha256"] = constraints.digest(intake["conflicts"][0])
    assert post(golden, request).status_code == 409


def test_a_immutable_replay_truth_speaker_and_remaining_gates(golden):
    client, settings, _, data, actor = golden; grant(golden)
    before = hashes(settings.pipeline_root)
    request = payload(golden); response = post(golden, request); assert response.status_code == 200, response.text
    receipt = response.json()["receipt"]
    assert receipt["actor"] == actor and receipt["human_gate"] and receipt["relationship_status"] == "unresolved"
    assert all(constraints.file_sha(__import__('pathlib').Path(p)) == sha for p,sha in before.items())
    assert post(golden, request).json()["receipt"] == receipt
    assert len(scope.receipts(settings.pipeline_root, BID)) == 1
    rules = constraints.assert_production_allowed(constraints.read(data["business_path"]), data["business_path"])
    assert not rules["blockers"] and rules["derived_authority_constraints"]
    persona = constraints.read(data["business_path"])
    projected = constraints.truth_projection(persona, path=data["business_path"])
    assert projected["facts"]["business_volume_fact"]["value"] == ["平日一餐20余位客人"]
    assert "独立菜单套餐100元" in projected["facts"]["pricing_facts"]["value"]
    run = subprocess.run([str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"), "-X", "utf8", "-c",
        "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from generate_mix_scripts_v1 import safe_persona_projection;print(json.dumps(safe_persona_projection(json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))),ensure_ascii=False))",
        str(settings.pipeline_root / "scripts"), str(data["business_path"])], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert run.returncode == 0, run.stderr
    safe = run.stdout
    assert "午市四五十单" not in safe and "我们推动市场转型" not in safe and "evidence_quote" not in safe
    assert constraints.read(data["speaker_path"])["persona_control_layer"]["derived_authority_constraints"][0]["constraint_id"] == "S-R2-011"
    for consumer in ("news", "novel_news", "news_repurpose"):
        with pytest.raises(RuntimeError, match="CONSUMER_UNSUPPORTED"):
            constraints.assert_production_allowed(persona, data["business_path"], consumer=consumer)
    try:
        entry = build_content_creation_entry(pipeline_root=settings.pipeline_root, business_id=BID, speaker_id=SID, profile="mix", requested_quantity=1)
    except (ContentCreationEntryError, RuntimeError) as exc:
        assert "BUSINESS_CONSTRAINT_BLOCKED" not in str(exc)
    assert not (settings.pipeline_root / "data/generation_requests" / BID).exists()
    history = client.get(f"/api/customers/{BID}/legacy-scope"); assert history.status_code == 200, history.text
    assert history.json()["items"][0]["receipts"][0]["sha256"] == receipt["sha256"]
    detail = client.get(f"/api/customers/{BID}"); assert detail.status_code == 200, detail.text
    assert detail.json()["latest_intake_id"] == constraints.read(data["directory"] / "customer_intake_v1.json")["intake_id"]
    assert not detail.json()["creation_constraints"]["blocked"]


@pytest.mark.parametrize("text", ["我们午市四五十单", "我们每天100人", "合成星湾便民市场与我们合作",
    "市场一直扶持食堂的发展", "我们获得了运营方的支持", "出租方帮我们减轻房租负担", "食堂是管理方旗下的窗口"])
def test_prohibited_claims_and_relationship_paraphrases(golden, text):
    _, _, _, data, _ = golden; grant(golden); assert post(golden, payload(golden)).status_code == 200
    with pytest.raises(RuntimeError, match="FORBIDDEN"):
        constraints.assert_publication_allowed(constraints.read(data["business_path"]), data["business_path"], [text])


def test_unrelated_legacy_and_same_id_different_intake_not_released(golden):
    _, settings, _, data, _ = golden; grant(golden); assert post(golden, payload(golden)).status_code == 200
    other = constraints.read(data["directory"] / "customer_intake_v1.json"); other["intake_id"] = "another_intake"
    write(data["directory"].parent / "intake_0002/customer_intake_v1.json", other)
    pending = constraints.unresolved_legacy_constraints(settings.pipeline_root, BID, constraints.collect(settings.pipeline_root, BID))
    assert len(pending) == 1 and pending[0]["source_intake_id"] == "another_intake"
    with pytest.raises(RuntimeError, match="BUSINESS_CONSTRAINT_BLOCKED"):
        constraints.assert_production_allowed(constraints.read(data["business_path"]), data["business_path"])


def test_crash_after_receipt_commit_exact_replay_and_changed_intent(golden, monkeypatch):
    _, settings, _, _, _ = golden; grant(golden); request = payload(golden); original = scope.write_once
    def crash(path, value):
        original(path, value); raise OSError("synthetic interruption after atomic receipt commit")
    monkeypatch.setattr(scope, "write_once", crash)
    assert post(golden, request).status_code == 409
    monkeypatch.setattr(scope, "write_once", original)
    assert post(golden, request).status_code == 200
    assert len(scope.receipts(settings.pipeline_root, BID)) == 1
    assert post(golden, {**request, "reason": "different intent"}).status_code == 409


def test_missing_external_names_and_stale_context_fail_closed(golden):
    grant(golden)
    request = payload(golden); request["blocked_terms"] = ["免租"]
    assert post(golden, request).status_code == 409
    request = payload(golden); request["context_sha256"] = "0" * 64
    assert post(golden, request).status_code == 409


def test_other_business_and_new_unrelated_conflict_stay_blocked(golden):
    client, settings, csrf, data, _ = golden; grant(golden)
    request = payload(golden)
    assert client.post("/api/customers/another_business/legacy-scope", headers={"X-CSRF-Token":csrf}, json=request).status_code == 409
    other = constraints.read(data["directory"] / "customer_intake_v1.json")
    other["intake_id"] = "other_critical_source"; other["conflicts"][0]["conflict_id"] = "independent_core_identity"
    write(data["directory"].parent / "intake_0002/customer_intake_v1.json", other)
    assert post(golden, request).status_code == 409
    assert not scope.receipts(settings.pipeline_root, BID)


def test_only_supported_historical_review_and_matching_proof_are_eligible(golden):
    _, settings, _, data, _ = golden; grant(golden); request = payload(golden)
    path = data["directory"] / "persona_revision_2_human_review_decision_v1.json"
    decision = constraints.read(path); decision["business"]["excluded_review_refs"].remove("B-R2-018")
    write(path, decision)
    assert post(golden, request).status_code == 409
    assert not scope.receipts(settings.pipeline_root, BID)


def test_concurrent_stale_scope_cannot_overwrite_latest_decision(golden):
    _, settings, _, _, _ = golden; grant(golden)
    stale = payload(golden, "insufficient_evidence")
    assert post(golden, payload(golden)).status_code == 200
    assert post(golden, stale).status_code == 409
    assert len(scope.receipts(settings.pipeline_root, BID)) == 1


def test_reviewer_grant_revoke_lock_covers_receipt_commit(golden):
    from operation_lock_v1 import operation_lock
    _, settings, _, _, actor = golden; grant(golden); request = payload(golden)
    with operation_lock(settings.pipeline_root, "legacy-scope-reviewer:" + scope.principal_key(actor)):
        assert post(golden, request).status_code == 409
    assert not scope.receipts(settings.pipeline_root, BID)
    assert post(golden, request).status_code == 200
