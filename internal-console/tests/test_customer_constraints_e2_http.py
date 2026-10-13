"""E2-A real HTTP/CSRF/lock/replay, only extractor output is synthetic."""
from __future__ import annotations

import json
import socket
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from app.operation_lock import authority_operation_lock
from app.task_service import update_task
from conftest import login_and_change_password


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch):
    original = socket.socket.connect
    def guarded(sock, address):
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("No external model transport in E2-A")
        return original(sock, address)
    monkeypatch.setattr(socket.socket, "connect", guarded)


@pytest.fixture()
def settings(settings):
    return replace(settings, pipeline_python_executable=str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"))


def seed(client, settings, csrf, *, omission=False, coverage=False, speaker_hint="none-no-speaker"):
    response = client.post("/api/customers/analyze", headers={"X-CSRF-Token": csrf}, json={
        "customer_name": "虚构限制审核餐厅", "materials": "提供地方菜堂食。附近家庭聚餐。菜单先确认人数。示例奖项尚未核实。创始人示例负责人亲自试菜并愿意出镜。"})
    assert response.status_code == 200, response.text
    body = response.json()
    task = body["task"]
    code = '''
import sys,json,socket
from pathlib import Path
def denied(*a,**k): raise AssertionError('E2 no remote provider')
socket.socket.connect=denied
socket.create_connection=denied
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from customer_onboarding_analysis_v1 import analyze_customer_onboarding
data={'facts':[{'topic':t,'value':[q],'evidence_quote':q} for t,q in [('primary_service','提供地方菜堂食'),('core_audience','附近家庭聚餐'),('service_process','菜单先确认人数')]],'constraints':[{'constraint_type':'unverified_claim','scope':'claim','evidence_quote':'示例奖项尚未核实','blocked_terms':['示例奖项'],'affected_fields':[],'related_fact_refs':[]}],'model':'synthetic-offline'}
if sys.argv[3]=='omission': data={'facts':[],'constraints':[],'model':'synthetic-historical-omission'}
if sys.argv[4]=='coverage': data['source_coverage']=[{'capability_group':g,'evidence_quote':q} for g,q in [('business_identity','提供地方菜堂食'),('customer_use_context','附近家庭聚餐'),('production_bearing_facts','菜单先确认人数')]]
people=[] if sys.argv[5]=='none-no-speaker' else [{'name':'示例负责人','public_role':'创始人','speaker_type_hint':None if sys.argv[5]=='null' else sys.argv[5],'candidate_status':'explicit_speaker','evidence_quotes':['创始人示例负责人亲自试菜并愿意出镜'],'personal_material_quotes':['创始人示例负责人亲自试菜并愿意出镜']}]
analyze_customer_onboarding(request=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')),pipeline_root=Path(sys.argv[1]),extractor=lambda _:data,speaker_discovery_extractor=lambda _:{'speaker_candidates':people})
'''
    run = subprocess.run([str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"), "-X", "utf8", "-c", code,
        str(settings.pipeline_root), task["payload"]["request_path"], "omission" if omission else "complete", "coverage" if coverage else "none", speaker_hint], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert run.returncode == 0, run.stderr
    update_task(settings.database_path, task["task_id"], status="awaiting_review", progress=99, stage="等待限制审核")
    return body, client.get(f'/api/customers/{body["business_id"]}').json()


def test_real_http_restrictions_auth_csrf_lock_human_actor_and_replay(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf)
    business = body["business_id"]
    url = f"/api/customers/{business}/facts/review"
    payload = {"decisions": [{"candidate_id": v["candidate_id"], "decision": "approve"} for v in detail["fact_candidates"] if v["state"] == "requires_review"],
        "constraint_decisions": [{"constraint_id": detail["constraint_candidates"][0]["constraint_id"], "decision": "exclude"}],
        "reviewer": "untrusted-client-actor"}
    assert client.post(url, json=payload).status_code == 403
    with authority_operation_lock(settings, "business", business):
        locked = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
        assert locked.status_code == 409
    saved = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert saved.status_code == 200, saved.text
    result = saved.json()["review"]
    assert result["status"] == "completed_persona_review_required"
    directory = Path(body["task"]["payload"]["request_path"]).parent
    canonical_review = json.loads((directory / "customer_fact_review_v1.json").read_text(encoding="utf-8"))
    reviewed = json.loads((directory / "reviewed_persona_fact_candidates_v1.json").read_text(encoding="utf-8"))
    decision = reviewed["derived_authority_constraints"][0]["human_review"]
    assert decision["reviewer"] != "untrusted-client-actor" and decision["human_gate"] is True
    path = directory / "persona_fact_candidates_v1.json"; before = path.read_bytes()
    replay = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert replay.status_code == 200
    assert json.loads((directory / "customer_fact_review_v1.json").read_text(encoding="utf-8"))["review_fingerprint"] == canonical_review["review_fingerprint"]
    assert path.read_bytes() == before
    assert not list(path.parent.rglob("approval_receipt.json"))
    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert client.post(url, headers={"X-CSRF-Token": csrf}, json=payload).status_code == 401


def test_saved_source_recovery_http_auth_lock_replay_and_history(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf, omission=True)
    business = body["business_id"]
    saved = client.post(f"/api/customers/{business}/facts/review", headers={"X-CSRF-Token": csrf}, json={
        "decisions": [{"candidate_id": v["candidate_id"], "decision": "approve"} for v in detail["fact_candidates"] if v["state"] == "requires_review"]})
    assert saved.status_code == 200, saved.text
    directory = Path(body["task"]["payload"]["request_path"]).parent
    protected = {p: p.read_bytes() for p in directory.glob("*.json")}
    projection = client.get(f"/api/customers/{business}").json()["saved_source_recovery"]
    payload = {"source_intake_id": projection["source_intake_id"], "targets": projection["targets"], "execution_identity": "fictional-http-recovery"}
    url = f"/api/customers/{business}/intake/recover"
    assert client.post(url, json=payload).status_code == 403
    with authority_operation_lock(settings, "business", business):
        assert client.post(url, headers={"X-CSRF-Token": csrf}, json=payload).status_code == 409
    first = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert first.status_code == 200, first.text
    task = first.json()["task"]
    duplicate = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert duplicate.json()["existing_task"]["task_id"] == task["task_id"]
    update_task(settings.database_path, task["task_id"], status="failed", stage="isolated failure")
    replay = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert replay.json()["replayed"] is True
    assert replay.json()["existing_task"]["task_id"] == task["task_id"]
    request = json.loads(Path(task["payload"]["request_path"]).read_text(encoding="utf-8"))
    assert request["source_lineage"]["customer_submitted_new_materials"] is False
    assert request["authority"]["approved_truth_changed"] is False
    assert all(p.read_bytes() == content for p, content in protected.items())
    assert len(list(directory.parent.glob("intake_*"))) == 2


@pytest.mark.parametrize("decision,value,label", [("confirm", "餐饮", "餐饮"), ("uncertain", None, "暂不确定")])
def test_blocked_customer_human_industry_projection_and_evidence_gap(client, settings, decision, value, label):
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf, omission=True, coverage=True)
    business = body["business_id"]
    response = client.post(f"/api/customers/{business}/facts/review", headers={"X-CSRF-Token": csrf}, json={
        "decisions": [{"candidate_id": v["candidate_id"], "decision": "approve"} for v in detail["fact_candidates"] if v["state"] == "requires_review"],
        "industry_review": {"decision": decision, "value": value}})
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/customers/{business}").json()
    assert detail["status"] == "needs_more_info" and detail["current_business_persona"] is None
    assert detail["industry"] == label
    assert detail["industry_classification"]["decision"] == decision
    assert detail["industry_classification"]["persona_approved_by_classification"] is False
    reasons = {v["capability_group"]: v for v in detail["gap_explanations"]}
    for group in ("business_identity", "customer_use_context", "production_bearing_facts"):
        assert reasons[group]["reason"] == "extraction_omission"
        assert reasons[group]["source_evidence"] and reasons[group]["projection_is_authority"] is False


@pytest.mark.parametrize("hint,selected_type,expected_drafts", [("null", None, 0), ("owner_founder", "frontline_expert", 1)])
def test_speaker_null_and_persisted_human_type_do_not_fall_back(client, settings, hint, selected_type, expected_drafts):
    csrf = login_and_change_password(client)
    body, detail = seed(client, settings, csrf, speaker_hint=hint)
    person = detail["speaker_candidates"][0]
    assert person["speaker_type_hint"] == (None if hint == "null" else hint)
    business = body["business_id"]
    saved = client.post(f"/api/customers/{business}/speaker-discovery/confirm", headers={"X-CSRF-Token": csrf}, json={
        "decisions": [{"candidate_id": person["candidate_id"], "selected": True, "speaker_type": selected_type}]})
    assert saved.status_code == 200, saved.text
    refreshed = client.get(f"/api/customers/{business}").json()
    assert len(refreshed["speakers"]) == expected_drafts
    assert refreshed["speaker_candidates"][0]["confirmation"]["speaker_type"] == selected_type
    if expected_drafts:
        assert refreshed["speakers"][0]["speaker_type"] == "frontline_expert"
        assert refreshed["speaker_candidates"][0]["confirmed"] is True
    else:
        assert refreshed["speaker_candidates"][0]["confirmation"]["outcome"] == "identity_required"
