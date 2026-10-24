"""Accepted CASE protocol regressions extracted without Persona/Legacy fixtures."""
import hashlib
import json
from pathlib import Path
from review_protocol import post_review
from app.database import connect
from test_case_library_security_v1 import node, ready, analyze, approve, CASE_ID


def hashes(root):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*.json")}



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



def test_classified_owner_cannot_approve_and_reviewer_can_without_new_attempt(node):
    _, task, candidate, evidence, _, _ = ready(node)
    before = hashes(node[0].pipeline_root)
    owner, owner_headers, _ = node[1]["A"]
    detail = owner.get(f"/api/cases/{CASE_ID}").json()
    assert detail["classification"]["status"] == "confirmed"
    assert not detail["permissions"]["can_review"] and not detail["review"]["can_review"]
    assert detail["evidence_review"]["required"]
    denied = post_review(owner, f"/api/cases/{CASE_ID}/review", headers=owner_headers,
                        json={"decision":"approve", "evidence_review":evidence})
    assert denied.status_code == 403
    assert hashes(node[0].pipeline_root) == before
    approve(node,evidence)
    after = owner.get(f"/api/cases/{CASE_ID}").json()
    assert after["review"]["approved"]
    assert after["classification"]["status"] == "confirmed"
    assert after["review"]["attempt_id"] == task["task_id"]
