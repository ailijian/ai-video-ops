"""Lifecycle regressions: real auth/CSRF/owners, synthetic extraction only."""
import hashlib
import json
from pathlib import Path

import pytest

from conftest import login_and_change_password
from review_protocol import post_review
from test_customer_speaker_smart_intake_v1 import settings, seed_customer
from test_customer_speaker_revision_v1 import approved_customer, approved_speaker, review_current, analyze_supplement
from app.persona_authority import resolve_persona_authority
from app.database import connect
from app import review_commands


def hashes(root):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.json")}


def amend(client, bid, csrf, *, sid=None, field="public_display_name", value="澄禾新名称", action="correct", context=None):
    url=f"/api/customers/{bid}" + (f"/speakers/{sid}" if sid else "")
    detail=client.get(url).json()
    response=client.post(url+"/review-amendments",headers={"X-CSRF-Token":csrf},json={
        "review_context": context or detail["approval_context"]["token"], "action":action,
        "reason":"虚构审核：根据新的准确本人资料更正，并核对当前客户关联。",
        "changes":[] if action=="rebase" else [{"field":field,"value":value,"evidence":"虚构本人提供的新资料，已由操作员记录，仍待独立核对。"}]})
    assert response.status_code==200,response.text
    return response.json()


def finish_speaker_review(client,bid,sid,csrf):
    detail=client.get(f"/api/customers/{bid}/speakers/{sid}").json()
    response=post_review(client,f"/api/customers/{bid}/speakers/{sid}/facts/review",headers={"X-CSRF-Token":csrf},json={
        "decisions":[{"candidate_id":v["candidate_id"],"decision":"approve"} for v in detail["fact_candidates"] if v["state"]=="requires_review"]})
    assert response.status_code==200,response.text


def test_missing_forged_and_stale_final_approval_cannot_mutate(client,settings):
    csrf=login_and_change_password(client);body,_=seed_customer(client,settings,csrf);bid=body["business_id"]
    review_current(client,bid,csrf);url=f"/api/customers/{bid}"
    detail=client.get(url).json();before=hashes(settings.pipeline_root)
    denied=client.request("POST",url+"/persona/approve",headers={"X-CSRF-Token":csrf},json={"note":"old client"})
    assert denied.status_code==409 and denied.json()["detail"]["code"]=="REVIEW_CONTEXT_REQUIRED"
    forged=detail["approval_context"]["token"][:-1]+("0" if detail["approval_context"]["token"][-1]!="0" else "1")
    assert client.post(url+"/persona/approve",headers={"X-CSRF-Token":csrf},json={"review_context":forged}).status_code==409
    assert hashes(settings.pipeline_root)==before
    old=detail["approval_context"]["token"]
    amend(client,bid,csrf)
    snapshot=hashes(settings.pipeline_root)
    stale=client.post(url+"/persona/approve",headers={"X-CSRF-Token":csrf},json={"review_context":old})
    assert stale.status_code==409
    assert hashes(settings.pipeline_root)==snapshot


def test_customer_return_correct_approve_preserves_all_historical_bytes(client,settings):
    csrf=login_and_change_password(client);body,_=seed_customer(client,settings,csrf);bid=body["business_id"]
    review_current(client,bid,csrf)
    old=resolve_persona_authority(settings,bid,"business").review_candidate
    old_sha=hashlib.sha256(old["path"].read_bytes()).hexdigest()
    amend(client,bid,csrf)
    assert resolve_persona_authority(settings,bid,"business").review_candidate is None
    assert hashlib.sha256(old["path"].read_bytes()).hexdigest()==old_sha
    assert (old["path"].parent/"review_disposition_v1.json").is_file()
    from approve_persona_v1 import approve_persona
    with pytest.raises(RuntimeError,match="Returned"):
        approve_persona(old["path"],"offline-reviewer","must not bypass return")
    result=review_current(client,bid,csrf)
    assert result["review"]["status"]=="completed_persona_review_required"
    candidate=resolve_persona_authority(settings,bid,"business").review_candidate
    assert candidate["revision"]==1 and candidate["path"]!=old["path"]
    approved=post_review(client,f"/api/customers/{bid}/persona/approve",headers={"X-CSRF-Token":csrf},json={"note":"Human approves corrected candidate"})
    assert approved.status_code==200,approved.text
    assert resolve_persona_authority(settings,bid,"business").current["artifact"]["facts"]["public_display_name"]["value"]=="澄禾新名称"
    assert hashlib.sha256(old["path"].read_bytes()).hexdigest()==old_sha


def test_approved_speaker_correction_keeps_identity_and_receipt_then_new_revision(client,settings):
    csrf=login_and_change_password(client);bid=approved_customer(client,settings,csrf)
    sid=approved_speaker(client,settings,csrf,bid)
    old=resolve_persona_authority(settings,sid,"speaker").current
    protected={p:p.read_bytes() for p in (old["path"],old["receipt_path"])}
    amend(client,bid,csrf,sid=sid,field="public_role",value="门店服务负责人")
    detail=client.get(f"/api/customers/{bid}/speakers/{sid}").json()
    assert detail["status"]=="fact_review_required" and detail["approved_for_current_business"]
    assert resolve_persona_authority(settings,sid,"speaker").current["revision"]==1
    finish_speaker_review(client,bid,sid,csrf)
    pending=resolve_persona_authority(settings,sid,"speaker").review_candidate
    assert pending["revision"]==2
    response=post_review(client,f"/api/customers/{bid}/speakers/{sid}/persona/approve",headers={"X-CSRF-Token":csrf},json={"note":"Independent Human approval"})
    assert response.status_code==200,response.text
    current=resolve_persona_authority(settings,sid,"speaker").current
    assert current["artifact"]["facts"]["public_role"]["value"]=="门店服务负责人"
    assert all(p.read_bytes()==v for p,v in protected.items())


def test_final_approval_replay_survives_restart_and_rejects_changed_intent(client,settings,monkeypatch):
    csrf=login_and_change_password(client);body,_=seed_customer(client,settings,csrf);bid=body["business_id"]
    review_current(client,bid,csrf);url=f"/api/customers/{bid}/persona/approve"
    token=client.get(f"/api/customers/{bid}").json()["approval_context"]["token"]
    payload={"review_context":token,"note":"Exact Human intent"}
    first=client.post(url,headers={"X-CSRF-Token":csrf},json=payload);assert first.status_code==200,first.text
    before=hashes(settings.pipeline_root);monkeypatch.setattr(review_commands,"_KEY",b"a different process key")
    replay=client.post(url,headers={"X-CSRF-Token":csrf},json=payload)
    assert replay.status_code==200 and replay.json()==first.json()
    assert hashes(settings.pipeline_root)==before
    changed=client.post(url,headers={"X-CSRF-Token":csrf},json={**payload,"note":"Another decision"})
    assert changed.status_code==409 and hashes(settings.pipeline_root)==before


def test_durable_approval_recovers_missing_receipt_without_new_human_decision(client,settings,monkeypatch):
    import approve_persona_v1 as owner
    csrf=login_and_change_password(client);body,_=seed_customer(client,settings,csrf);bid=body["business_id"]
    review_current(client,bid,csrf);url=f"/api/customers/{bid}/persona/approve"
    token=client.get(f"/api/customers/{bid}").json()["approval_context"]["token"]
    import human_review_operations_v1 as storage
    original=storage.write_once
    def fail_receipt(path,value):
        if Path(path).name=="approval_receipt.json":raise OSError("synthetic interruption after approved bytes")
        return original(path,value)
    with monkeypatch.context() as patch:
        patch.setattr(storage,"write_once",fail_receipt)
        with pytest.raises(OSError):client.post(url,headers={"X-CSRF-Token":csrf},json={"review_context":token,"note":"Exact recovery intent"})
    pending=client.get(f"/api/review-commands/business/{bid}").json()["operations"]
    assert len(pending)==1 and pending[0]["payload"]["review_context"]==token
    response=client.post(pending[0]["request_path"],headers={"X-CSRF-Token":csrf},json=pending[0]["payload"])
    assert response.status_code==200,response.text
    assert not client.get(f"/api/review-commands/business/{bid}").json()["operations"]


def test_duplicate_speaker_different_materials_are_explicitly_not_saved(client,settings):
    csrf=login_and_change_password(client);bid=approved_customer(client,settings,csrf);sid=approved_speaker(client,settings,csrf,bid)
    before=hashes(settings.pipeline_root)
    response=client.post(f"/api/customers/{bid}/speakers/analyze",headers={"X-CSRF-Token":csrf},json={
        "speaker_name":"王琳","public_role":"店主","speaker_type":"owner_founder","materials":"NEW DIFFERENT PERSONAL MATERIALS","forbidden_claims":[]})
    assert response.status_code==200,response.text
    assert response.json()["speaker_id"]==sid and response.json()["input_differs"] and not response.json()["materials_saved"]
    assert hashes(settings.pipeline_root)==before


def test_business_update_rebases_first_unapproved_speaker_without_null_evidence(client,settings):
    csrf=login_and_change_password(client);bid=approved_customer(client,settings,csrf)
    sid=approved_speaker(client,settings,csrf,bid,approve=False)
    original=resolve_persona_authority(settings,sid,"speaker").review_candidate
    old_bytes=original["path"].read_bytes()
    amend(client,bid,csrf,field="public_display_name",value="澄禾更新客户名称")
    review_current(client,bid,csrf)
    response=post_review(client,f"/api/customers/{bid}/persona/approve",headers={"X-CSRF-Token":csrf},json={"note":"Human approves Business R2"})
    assert response.status_code==200,response.text
    detail=client.get(f"/api/customers/{bid}/speakers/{sid}").json()
    assert detail["status"]=="binding_review_required"
    dashboard = client.get("/api/dashboard").json()
    assert "speaker_binding_review" in json.dumps(dashboard)
    assert resolve_persona_authority(settings,sid,"speaker").current is None
    amend(client,bid,csrf,sid=sid,action="rebase")
    finish_speaker_review(client,bid,sid,csrf)
    latest=resolve_persona_authority(settings,sid,"speaker").review_candidate
    assert latest["path"]!=original["path"] and latest["artifact"]["business_persona_ref"]["revision"]==2
    response=post_review(client,f"/api/customers/{bid}/speakers/{sid}/persona/approve",headers={"X-CSRF-Token":csrf},json={"note":"Independent rebased Speaker approval"})
    assert response.status_code==200,response.text
    assert client.get(f"/api/customers/{bid}").json()["creation_entry_ready"]
    assert original["path"].read_bytes()==old_bytes


from test_case_library_security_v1 import node, ready, analyze, CASE_ID


def test_case_reanalysis_queue_fault_recovers_one_task_and_immutable_decision(node,monkeypatch):
    import app.main as main
    from app.task_service import TaskSubmissionError
    settings,accounts,tmp=node;_,task,candidate,evidence,_,_=ready(node)
    c,headers,_=accounts["C"]
    payload={"decision":"reanalyze","reason":"Synthetic explicit Human request",
        "review_context":c.get(f"/api/cases/{CASE_ID}").json()["approval_context"]["token"]}
    with monkeypatch.context() as patch:
        patch.setattr(main,"create_case_task",lambda *a,**k:(_ for _ in ()).throw(TaskSubmissionError("TASK_QUEUE_FULL","synthetic queue full")))
        failed=c.post(f"/api/cases/{CASE_ID}/review",headers=headers,json=payload)
        assert failed.status_code==429,failed.text
    receipt=candidate.parents[2]/"human_review_decision_v1.json";protected=receipt.read_bytes()
    closed=c.get(f"/api/cases/{CASE_ID}").json()
    assert closed["status"]=="returned" and closed["review"]["can_review"] is False
    pending=c.get(f"/api/review-commands/case/{CASE_ID}").json()["operations"]
    assert len(pending)==1
    resumed=c.post(pending[0]["request_path"],headers=headers,json=pending[0]["payload"])
    assert resumed.status_code==200,resumed.text
    replay=c.post(pending[0]["request_path"],headers=headers,json=pending[0]["payload"])
    assert replay.status_code==200 and replay.json()["task"]["task_id"]==resumed.json()["task"]["task_id"]
    assert receipt.read_bytes()==protected
    db=connect(settings.database_path)
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE task_type='case_analysis'").fetchone()[0]==2
    db.close()
    assert not accounts["A"][0].get(f"/api/review-commands/case/{CASE_ID}").json()["operations"]


def test_duplicate_foreign_group_has_terminal_neutral_projection(node):
    _,accounts,_=node;ready(node)
    group,task=analyze(node,"B")
    assert task is None and group["items"][0]["state"]=="linked"
    assert group["items"][0]["classification"] is None and group["items"][0]["case"] is None
    assert accounts["B"][0].get(f"/api/cases/{CASE_ID}").status_code==404


def test_case_stale_classification_context_and_borrowed_actor_cannot_approve(node):
    settings,accounts,_=node;_,task,candidate,evidence,_,_=ready(node)
    c,hc,_=accounts["C"];a,ha,_=accounts["A"]
    old=c.get(f"/api/cases/{CASE_ID}").json()["approval_context"]["token"]
    denied=a.post(f"/api/cases/{CASE_ID}/review",headers=ha,json={"decision":"approve","review_context":old,"evidence_review":evidence})
    assert denied.status_code==403
    state=a.get(f"/api/cases/{CASE_ID}/classification").json()
    changed=a.post(f"/api/cases/{CASE_ID}/classification",headers=ha,json={"industry":"零售","profile":"mix",
        "candidate_sha256":state["candidate_sha256"],"expected_confirmation_sha256":state["confirmation_sha256"]})
    assert changed.status_code==200,changed.text
    before=hashes(settings.pipeline_root)
    denied=c.post(f"/api/cases/{CASE_ID}/review",headers=hc,json={"decision":"approve","review_context":old,"evidence_review":evidence})
    assert denied.status_code==409 and hashes(settings.pipeline_root)==before


def test_revoked_reviewer_cannot_resume_saved_reanalysis(node,monkeypatch):
    import app.main as main
    from app.task_service import TaskSubmissionError
    from app.case_library_access import manage_reviewer
    settings,accounts,_=node;ready(node);c,hc,_=accounts["C"]
    token=c.get(f"/api/cases/{CASE_ID}").json()["approval_context"]["token"]
    payload={"decision":"reanalyze","reason":"Human synthetic retry","review_context":token}
    with monkeypatch.context() as patch:
        patch.setattr(main,"create_case_task",lambda *a,**k:(_ for _ in ()).throw(TaskSubmissionError("TASK_QUEUE_FULL","fixture full")))
        assert c.post(f"/api/cases/{CASE_ID}/review",headers=hc,json=payload).status_code==429
    manage_reviewer(settings,3,action="revoke",operator="synthetic-admin",reason="Explicit fixture revocation")
    before=hashes(settings.pipeline_root)
    assert c.post(f"/api/cases/{CASE_ID}/review",headers=hc,json=payload).status_code==403
    assert not c.get(f"/api/review-commands/case/{CASE_ID}").json()["operations"]
    assert hashes(settings.pipeline_root)==before


def test_ordinary_correction_cannot_replace_expression_prohibitions(client,settings):
    csrf=login_and_change_password(client);bid=approved_customer(client,settings,csrf);sid=approved_speaker(client,settings,csrf,bid)
    url=f"/api/customers/{bid}/speakers/{sid}"
    detail=client.get(url).json()
    assert "first_person_forbidden_claims" not in detail["amendable_fields"]
    response=client.post(url+"/review-amendments",headers={"X-CSRF-Token":csrf},json={
        "review_context":detail["approval_context"]["token"],"action":"correct","reason":"Cannot waive a restriction",
        "changes":[{"field":"first_person_forbidden_claims","value":["随意使用所有主张"],"evidence":"synthetic unsafe weakening"}]})
    assert response.status_code==409
    assert resolve_persona_authority(settings,sid,"speaker").current["revision"]==1
    pending=client.get(f"/api/review-commands/speaker/{sid}").json()["operations"]
    assert pending[0]["can_discard"]
    discarded=client.post(f"/api/review-commands/speaker/{sid}/{pending[0]['operation_id']}/cancel",headers={"X-CSRF-Token":csrf})
    assert discarded.status_code==200 and not client.get(f"/api/review-commands/speaker/{sid}").json()["operations"]


def test_speaker_old_fact_page_is_rejected_after_business_update(client,settings):
    csrf=login_and_change_password(client);bid=approved_customer(client,settings,csrf);sid=approved_speaker(client,settings,csrf,bid)
    amend(client,bid,csrf,sid=sid,field="public_role",value="负责人")
    url=f"/api/customers/{bid}/speakers/{sid}"
    old=client.get(url).json()
    amend(client,bid,csrf,field="public_display_name",value="澄禾新客户名")
    review_current(client,bid,csrf)
    approved=post_review(client,f"/api/customers/{bid}/persona/approve",headers={"X-CSRF-Token":csrf},json={})
    assert approved.status_code==200,approved.text
    before=hashes(settings.pipeline_root)
    denied=client.post(url+"/facts/review",headers={"X-CSRF-Token":csrf},json={"review_context":old["approval_context"]["token"],
        "decisions":[{"candidate_id":v["candidate_id"],"decision":"approve"} for v in old["fact_candidates"] if v["state"]=="requires_review"]})
    assert denied.status_code==409 and hashes(settings.pipeline_root)==before
    amend(client,bid,csrf,sid=sid,action="rebase")
    fresh=client.get(url).json()
    role=next(v for v in fresh["fact_candidates"] if v["field"]=="public_role")
    assert role["value"]=="负责人" and role["state"]=="requires_review"


def test_interrupted_approval_rechecks_authority_before_finishing(client, settings, monkeypatch):
    import approve_persona_v1 as owner
    import human_review_operations_v1 as storage
    csrf = login_and_change_password(client)
    body, _ = seed_customer(client, settings, csrf)
    bid = body["business_id"]
    review_current(client, bid, csrf)
    token = client.get(f"/api/customers/{bid}").json()["approval_context"]["token"]
    payload = {"review_context": token, "note": "Human decision interrupted before receipt"}
    url = f"/api/customers/{bid}/persona/approve"
    original = storage.write_once
    def interrupt(path, value):
        if Path(path).name == "approval_receipt.json":
            raise OSError("synthetic receipt interruption")
        return original(path, value)
    with monkeypatch.context() as patch:
        patch.setattr(storage, "write_once", interrupt)
        with pytest.raises(OSError):
            client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    before = hashes(settings.pipeline_root)
    with monkeypatch.context() as patch:
        patch.setattr(owner, "validate_approval_authority", lambda *a: ["current source/constraint gate unavailable"])
        blocked = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
        assert blocked.status_code == 409, blocked.text
    assert hashes(settings.pipeline_root) == before
    resumed = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert resumed.status_code == 200, resumed.text


def test_saved_reanalysis_reserves_exact_upload_across_queue_wait_and_cleanup(node, monkeypatch):
    from test_case_library_security_v1 import ready, CASE_ID
    from app import main, case_uploads
    from app.task_service import TaskSubmissionError
    from datetime import datetime, timedelta
    settings, accounts, _ = node
    _, _, _, _, _, _ = ready(node)
    c, headers, _ = accounts["C"]
    upload_id = "b" * 32
    directory = settings.pipeline_root / "data/case_source_uploads" / upload_id
    directory.mkdir(parents=True)
    video = directory / f"{CASE_ID}.mp4"
    video.write_bytes(b"synthetic local decoder-boundary fixture")
    source = f"https://www.douyin.com/video/{CASE_ID}"
    receipt = {"schema_version":"case-source-upload-v1.0", "upload_id":upload_id, "case_id":CASE_ID,
        "source_url":source,"filename":video.name,"source_video_sha256":hashlib.sha256(video.read_bytes()).hexdigest(),
        "size_bytes":video.stat().st_size,"uploaded_by_user_id":3,"uploaded_at":datetime.now(case_uploads.timezone.utc).isoformat(),
        "rights_confirmed":True,"source_match_confirmed":True,"binding_method":"operator_attestation"}
    (directory / case_uploads.RECEIPT).write_text(json.dumps(receipt),encoding="utf-8")
    token=c.get(f"/api/cases/{CASE_ID}").json()["approval_context"]["token"]
    payload={"review_context":token,"decision":"reanalyze","reason":"Fictional source correction","source_upload_id":upload_id}
    def full(*a,**kw):raise TaskSubmissionError("TASK_QUEUE_FULL","synthetic queue full")
    with monkeypatch.context() as patch:
        patch.setattr(main,"create_case_task",full)
        failed=c.post(f"/api/cases/{CASE_ID}/review",headers=headers,json=payload)
        assert failed.status_code==429,failed.text
    before=hashes(settings.pipeline_root)
    class Later(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.now(tz)+timedelta(days=2)
    with monkeypatch.context() as patch:
        patch.setattr(case_uploads,"datetime",Later)
        case_uploads.cleanup_unused_uploads(settings)
        assert video.is_file()
        resumed=c.post(f"/api/cases/{CASE_ID}/review",headers=headers,json=payload)
        assert resumed.status_code==200,resumed.text
    after=hashes(settings.pipeline_root)
    immutable_names = {"human_review_decision_v1.json", "case_v1.json", "source_upload_receipt_v1.json", "source_upload_reservation_v1.json", "intent.json"}
    assert all(after.get(p)==sha for p,sha in before.items() if Path(p).name in immutable_names)
    task=resumed.json()["task"]
    assert task["payload"]["source_upload"]["upload_id"]==upload_id
    replay=c.post(f"/api/cases/{CASE_ID}/review",headers=headers,json=payload)
    assert replay.status_code==200 and replay.json()["task"]["task_id"]==task["task_id"]
