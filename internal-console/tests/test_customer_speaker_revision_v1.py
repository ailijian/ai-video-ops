from __future__ import annotations

import json
import subprocess
import pytest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.database import connect
from app.persona_authority import (
    resolve_persona_authority,
    validate_speaker_business_binding,
)
from app.task_service import update_task
from conftest import login_and_change_password
from test_customer_speaker_smart_intake_v1 import (
    settings,
    seed_customer,
    review_payload,
    sha,
)


def analyze_supplement(settings, task, *, facts=None):
    facts = (
        facts
        if facts is not None
        else [
            {
                "topic": "service_process",
                "value": ["先预约，再进行真实皮肤检测"],
                "evidence_quote": "先预约，再进行真实皮肤检测",
            }
        ]
    )
    code = """
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
from customer_onboarding_analysis_v1 import analyze_customer_onboarding
analyze_customer_onboarding(request=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')),
    pipeline_root=Path(sys.argv[1]),extractor=lambda _:{'facts':json.loads(sys.argv[3]),'model':'synthetic-offline'},
    speaker_discovery_extractor=lambda _:{'speaker_candidates':[],'model':'synthetic-offline'})
"""
    result = subprocess.run(
        [
            str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"),
            "-X",
            "utf8",
            "-c",
            code,
            str(settings.pipeline_root),
            task["payload"]["request_path"],
            json.dumps(facts, ensure_ascii=False),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    update_task(
        settings.database_path,
        task["task_id"],
        status="awaiting_review",
        progress=99,
        stage="等待确认",
    )


def review_current(client, business, csrf):
    detail = client.get(f"/api/customers/{business}").json()
    payload = {
        "decisions": [
            {"candidate_id": item["candidate_id"], "decision": "approve"}
            for item in detail["fact_candidates"]
            if item["state"] == "requires_review"
        ],
        "note": "Synthetic incremental Human review",
    }
    response = client.post(
        f"/api/customers/{business}/facts/review",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert response.status_code == 200, response.text
    return response.json()


def approved_customer(client, settings, csrf):
    body, _ = seed_customer(client, settings, csrf)
    business = body["business_id"]
    review_current(client, business, csrf)
    result = client.post(
        f"/api/customers/{business}/persona/approve",
        headers={"X-CSRF-Token": csrf},
        json={"note": "Synthetic Human R1 approval"},
    )
    assert result.status_code == 200, result.text
    return business


def approved_speaker(client, settings, csrf, business):
    materials = "王琳是小爪宠物店店主，日常由她亲自接待顾客，检查宠物皮肤和毛发状态，并根据现场情况确认洗护方案。她可以分享自己在门店接待、宠物洗护前判断和日常服务中的实际经验。"
    result = client.post(
        f"/api/customers/{business}/speakers/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "speaker_name": "王琳",
            "public_role": "店主",
            "speaker_type": "owner_founder",
            "materials": materials,
            "forbidden_claims": [],
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    task = body["task"]
    speaker = body["speaker_id"]
    code = """
import json,sys,runpy
from pathlib import Path
fixture=runpy.run_path(str(Path(sys.argv[1])/'ops-pipeline/tests/test_speaker_persona_vertical_slice_v1.py'))
fixture['analysis'].analyze_speaker_onboarding(request=json.loads(Path(sys.argv[3]).read_text(encoding='utf-8')),
    pipeline_root=Path(sys.argv[2]),extractor=fixture['fixture_extractor'])
"""
    execution = subprocess.run(
        [
            str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"),
            "-X",
            "utf8",
            "-c",
            code,
            str(settings.repo_root),
            str(settings.pipeline_root),
            task["payload"]["request_path"],
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert execution.returncode == 0, execution.stderr
    update_task(
        settings.database_path,
        task["task_id"],
        status="awaiting_review",
        progress=99,
        stage="等待确认",
    )
    detail = client.get(f"/api/customers/{business}/speakers/{speaker}").json()
    reviewed = client.post(
        f"/api/customers/{business}/speakers/{speaker}/facts/review",
        headers={"X-CSRF-Token": csrf},
        json={
            "decisions": [
                {"candidate_id": item["candidate_id"], "decision": "approve"}
                for item in detail["fact_candidates"]
                if item["state"] == "requires_review"
            ],
            "note": "Synthetic personal fact review",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    approved = client.post(
        f"/api/customers/{business}/speakers/{speaker}/persona/approve",
        headers={"X-CSRF-Token": csrf},
        json={"note": "Synthetic independent Human Speaker approval"},
    )
    assert approved.status_code == 200, approved.text
    return speaker


def test_minimal_name_only_and_stable_identity(client, settings):
    csrf = login_and_change_password(client)
    headers = {"X-CSRF-Token": csrf}
    saved = client.post(
        "/api/customers/analyze",
        headers=headers,
        json={
            "customer_name": "稍后补充客户",
            "save_only": True,
            "submission_key": "draft-key-0001",
        },
    )
    assert saved.status_code == 200, saved.text
    business = saved.json()["business_id"]
    assert saved.json()["saved_only"] is True
    connection = connect(settings.database_path)
    assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
    connection.close()
    detail = client.get(f"/api/customers/{business}").json()
    assert detail["status"] == "draft" and detail["business_persona"] is None
    assert detail["industry"] == "待确认"
    rejected = client.post(f"/api/customers/{business}/retry", headers=headers)
    assert rejected.status_code != 200
    connection = connect(settings.database_path)
    assert connection.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
    connection.close()
    path = (
        settings.pipeline_root
        / "data/customer_intakes"
        / business
        / "intake_0001/customer_onboarding_request_v1.json"
    )
    old = sha(path)
    blank = client.post(
        "/api/customers/analyze", headers=headers, json={"customer_name": "无事实客户"}
    )
    assert blank.status_code != 200
    again = client.post(
        "/api/customers/analyze",
        headers=headers,
        json={
            "customer_name": "稍后补充客户",
            "save_only": True,
            "submission_key": "draft-key-0001",
        },
    )
    assert again.json()["business_id"] == business
    response = client.post(
        f"/api/customers/{business}/reanalyze",
        headers=headers,
        json={
            "customer_name": "稍后补充客户",
            "materials": "提供真实宠物洗护，服务附近养宠家庭。",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["task"]["subject_ref"] == business
    assert sha(path) == old
    # Later industry input remains the same business namespace and URL.
    task = response.json()["task"]
    update_task(
        settings.database_path,
        task["task_id"],
        status="failed",
        error_code="SYNTHETIC",
        error_message="合成失败",
    )
    changed = client.post(
        f"/api/customers/{business}/reanalyze",
        headers=headers,
        json={
            "customer_name": "稍后补充客户",
            "industry": "本地生活",
            "materials": "新增真实资料。",
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["task"]["subject_ref"] == business


def test_no_industry_does_not_forge_candidate(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed_customer(client, settings, csrf, industry=None)
    assert all(item["field"] != "industry" for item in detail["fact_candidates"])
    reviewed = review_current(client, body["business_id"], csrf)
    assert reviewed["review"]["status"] == "completed_persona_review_required"
    assert (
        client.get(f'/api/customers/{body["business_id"]}').json()["business_persona"][
            "approved"
        ]
        is False
    )


def test_same_name_requires_check_or_explicit_separate_identity(client, settings):
    csrf = login_and_change_password(client)
    headers = {"X-CSRF-Token": csrf}
    first = client.post(
        "/api/customers/analyze",
        headers=headers,
        json={"customer_name": "同名门店", "save_only": True},
    ).json()
    conflict = client.post(
        "/api/customers/analyze",
        headers=headers,
        json={"customer_name": "同名门店", "materials": "另一家门店的真实资料。"},
    ).json()
    assert conflict["existing_customer_check_required"] is True
    assert conflict["business_id"] == first["business_id"]
    payload = {
        "customer_name": "同名门店",
        "save_only": True,
        "create_separate": True,
        "submission_key": "different-business-0001",
    }
    other = client.post("/api/customers/analyze", headers=headers, json=payload).json()
    assert other["business_id"] != first["business_id"]
    repeated = client.post(
        "/api/customers/analyze", headers=headers, json=payload
    ).json()
    assert repeated["business_id"] == other["business_id"]


def own_business_history(settings, business, *, create=False):
    """Declared synthetic historical Mix/News records; canonical Ledger writer.

    These fixture records never represent a real published/exported customer.
    """
    code = r"""
import json,sys
from pathlib import Path
root=Path(sys.argv[1]);business=sys.argv[2]
sys.path.insert(0,str(root/'scripts'))
import content_quality_v1 as q
path=root/'data/content_ledgers'/business/'content_ledger_v1.json'
concept={'concept_id':'synthetic-history','central_claim':'洗护前先检查毛发','primary_topic':'服务流程','audience_need':'理解服务','content_job':'解释流程','primary_fact_refs':['service_process'],'exclusive_anchor':'洗护前检查毛发'}
concept['semantic_signature']=q.semantic_signature(concept,business)
if sys.argv[3]=='create':
    ledger={'schema_version':'content-ledger-v1.0','fixture_only':True,'business_id':business,'entries':[]}
    ledger=q.append_ledger_entries(ledger,[{**concept,'content_id':'synthetic-'+profile,'business_id':business,'production_profile':profile,'status':'exported'} for profile in ['mix','news']])
    path.parent.mkdir(parents=True,exist_ok=True)
    q.write_new_json(path,ledger)
ledger=q.read_json(path)
print(json.dumps({profile:q.novelty_evaluation({**concept,'production_profile':profile},ledger['entries']) for profile in ['mix','news']}))
"""
    result = subprocess.run(
        [
            str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"),
            "-X",
            "utf8",
            "-c",
            code,
            str(settings.pipeline_root),
            business,
            "create" if create else "read",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_approved_revision_full_http_and_speaker_explicit_revalidation(
    client, settings
):
    csrf = login_and_change_password(client)
    headers = {"X-CSRF-Token": csrf}
    business = approved_customer(client, settings, csrf)
    speaker = approved_speaker(client, settings, csrf, business)
    novelty_before = own_business_history(settings, business, create=True)
    assert all(result["duplicate_matches"] for result in novelty_before.values())
    old_business = resolve_persona_authority(settings, business, "business").current
    old_speaker = resolve_persona_authority(settings, speaker, "speaker").current
    protected = [
        old_business["path"],
        old_business["path"].parent / "approval_receipt.json",
        old_speaker["path"],
        old_speaker["path"].parent / "approval_receipt.json",
    ]
    history = {path: sha(path) for path in protected}
    history.update(
        {
            path: sha(path)
            for folder in [
                "content_ledgers",
                "generation_requests",
                "generation_batches",
            ]
            for path in (settings.pipeline_root / "data" / folder).rglob("*")
            if path.is_file()
        }
    )
    request = {
        "answers": [
            {
                "target_gap": "additional_materials",
                "raw_answer": "新增真实流程：先预约，再进行真实皮肤检测。",
            }
        ]
    }
    response = client.post(
        f"/api/customers/{business}/gaps/supplement", headers=headers, json=request
    )
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    analyze_supplement(settings, task)
    reviewed = review_current(client, business, csrf)
    assert reviewed["review"]["business_persona"]["revision"] == 2
    current = resolve_persona_authority(settings, business, "business")
    assert (
        current.current["revision"] == 1 and current.review_candidate["revision"] == 2
    )
    options = client.get("/api/create/options").json()
    assert any(
        item["business_id"] == business and item["creation_ready"]
        for item in options["customers"]
    )
    r2 = current.review_candidate["path"]
    r2_sha = sha(r2)
    repeated = review_current(client, business, csrf)
    assert sha(r2) == r2_sha
    approved = client.post(
        f"/api/customers/{business}/persona/approve",
        headers=headers,
        json={"note": "Synthetic Human Business R2 approval"},
    )
    assert approved.status_code == 200, approved.text
    assert (
        resolve_persona_authority(settings, business, "business").current["revision"]
        == 2
    )
    stale = client.get(f"/api/customers/{business}/speakers/{speaker}").json()
    assert stale["status"] == "revalidation_required"
    assert (
        client.get(f"/api/customers/{business}").json()["creation_entry_ready"] is False
    )
    from app.canonical_gateway import CanonicalOperationError

    with pytest.raises(CanonicalOperationError, match="当前已批准"):
        validate_speaker_business_binding(
            old_speaker,
            resolve_persona_authority(settings, business, "business").current,
        )
    evidence = stale["revalidation_evidence"]
    payload = {key: evidence[key] for key in ["business_sha256", "speaker_sha256"]}
    denied = client.post(
        f"/api/customers/{business}/speakers/{speaker}/revalidation/review",
        headers=headers,
        json={**payload, "confirmed": False},
    )
    assert denied.status_code != 200
    stale_request = client.post(
        f"/api/customers/{business}/speakers/{speaker}/revalidation/review",
        headers=headers,
        json={**payload, "confirmed": True, "business_sha256": "0" * 64},
    )
    assert stale_request.status_code != 200
    assert (
        resolve_persona_authority(settings, speaker, "speaker").review_candidate is None
    )
    confirmed = client.post(
        f"/api/customers/{business}/speakers/{speaker}/revalidation/review",
        headers=headers,
        json={**payload, "confirmed": True, "note": "已独立复核本人事实未变"},
    )
    assert confirmed.status_code == 200, confirmed.text
    speaker_pending = resolve_persona_authority(settings, speaker, "speaker")
    assert (
        speaker_pending.current["revision"] == 1
        and speaker_pending.review_candidate["revision"] == 2
    )
    assert (
        speaker_pending.review_candidate["artifact"]["business_persona_ref"]["revision"]
        == 2
    )
    assert (
        speaker_pending.review_candidate["artifact"]["facts"]
        == old_speaker["artifact"]["facts"]
    )
    review_sha = sha(speaker_pending.review_candidate["path"])
    replay = client.post(
        f"/api/customers/{business}/speakers/{speaker}/revalidation/review",
        headers=headers,
        json={**payload, "confirmed": True, "note": "已独立复核本人事实未变"},
    )
    assert replay.status_code == 200, replay.text
    assert sha(speaker_pending.review_candidate["path"]) == review_sha
    speaker_approval_response = client.post(
        f"/api/customers/{business}/speakers/{speaker}/persona/approve",
        headers=headers,
        json={"note": "Synthetic independent Speaker R2 approval"},
    )
    assert speaker_approval_response.status_code == 200, speaker_approval_response.text
    assert (
        client.get(f"/api/customers/{business}").json()["creation_entry_ready"] is True
    )
    assert all(sha(path) == value for path, value in history.items())
    assert own_business_history(settings, business) == novelty_before


def test_empty_additive_review_does_not_create_empty_revision(client, settings):
    csrf = login_and_change_password(client)
    business = approved_customer(client, settings, csrf)
    task = client.post(
        f"/api/customers/{business}/gaps/supplement",
        headers={"X-CSRF-Token": csrf},
        json={
            "answers": [
                {"target_gap": "additional_materials", "raw_answer": "暂无更多事实。"}
            ]
        },
    ).json()["task"]
    analyze_supplement(settings, task, facts=[])
    result = review_current(client, business, csrf)
    assert result["review"]["status"] == "completed_no_new_facts"
    authority = resolve_persona_authority(settings, business, "business")
    assert authority.current["revision"] == 1 and authority.review_candidate is None


def test_concurrent_supplement_and_review_do_not_collide(client, settings):
    csrf = login_and_change_password(client)
    business = approved_customer(client, settings, csrf)
    url = f"/api/customers/{business}/gaps/supplement"
    payload = {
        "answers": [
            {
                "target_gap": "additional_materials",
                "raw_answer": "先预约，再进行真实皮肤检测。",
            }
        ]
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: client.post(
                    url, headers={"X-CSRF-Token": csrf}, json=payload
                ),
                range(2),
            )
        )
    assert any(r.status_code == 200 for r in responses)
    assert all(r.status_code != 500 for r in responses)
    roots = list(
        (settings.pipeline_root / "data/customer_intakes" / business).glob("intake_*")
    )
    assert len(roots) == 2
    task = next(
        r.json()["task"]
        for r in responses
        if r.status_code == 200 and r.json().get("task")
    )
    analyze_supplement(settings, task)
    detail = client.get(f"/api/customers/{business}").json()
    review = {
        "decisions": [
            {"candidate_id": c["candidate_id"], "decision": "approve"}
            for c in detail["fact_candidates"]
            if c["state"] == "requires_review"
        ],
        "note": "Same concurrent Human review",
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    f"/api/customers/{business}/facts/review",
                    headers={"X-CSRF-Token": csrf},
                    json=review,
                ),
                range(2),
            )
        )
    assert any(r.status_code == 200 for r in results)
    assert all(r.status_code != 500 for r in results)
    authority = resolve_persona_authority(settings, business, "business")
    assert (
        authority.current["revision"] == 1
        and authority.review_candidate["revision"] == 2
    )
    assert (
        len(
            list(
                (settings.pipeline_root / "data/personas" / business).glob(
                    "*/persona_v1.json"
                )
            )
        )
        == 2
    )


def test_scalar_conflict_preserves_approved_truth(client, settings):
    csrf = login_and_change_password(client)
    business = approved_customer(client, settings, csrf)
    before = resolve_persona_authority(settings, business, "business").current
    saved = sha(before["path"])
    task = client.post(
        f"/api/customers/{business}/gaps/supplement",
        headers={"X-CSRF-Token": csrf},
        json={
            "answers": [
                {"target_gap": "additional_materials", "raw_answer": "现在改称餐饮。"}
            ]
        },
    ).json()["task"]
    analyze_supplement(
        settings,
        task,
        facts=[{"topic": "industry", "value": "餐饮", "evidence_quote": "餐饮"}],
    )
    detail = client.get(f"/api/customers/{business}").json()
    response = client.post(
        f"/api/customers/{business}/facts/review",
        headers={"X-CSRF-Token": csrf},
        json={
            "decisions": [
                {"candidate_id": c["candidate_id"], "decision": "approve"}
                for c in detail["fact_candidates"]
                if c["state"] == "requires_review"
            ],
            "note": "Synthetic conflicting fact",
        },
    )
    assert response.status_code != 200
    assert response.json()["detail"]["code"] == "SCALAR_FACT_CONFLICT"
    assert "冲突" in response.json()["detail"]["message"]
    assert "不能覆盖已批准事实" in response.json()["detail"]["next_action"]
    assert sha(before["path"]) == saved
    authority = resolve_persona_authority(settings, business, "business")
    assert authority.current["revision"] == 1 and authority.review_candidate is None
    root = Path(task["payload"]["request_path"]).parent
    assert not (root / "customer_fact_review_v1.json").exists()
    conflicts = list((root / "fact_conflicts").glob("*.json"))
    assert len(conflicts) == 1
    conflict_sha = sha(conflicts[0])
    assert len(json.loads(conflicts[0].read_text(encoding="utf-8"))["review_fingerprint"]) == 64
    # A new explicit decision resolves the pending conflict; no approved or
    # finalized review is edited to simulate repair.
    resolved = client.post(
        f"/api/customers/{business}/facts/review",
        headers={"X-CSRF-Token": csrf},
        json={
            "decisions": [
                {"candidate_id": c["candidate_id"], "decision": "reject"}
                for c in detail["fact_candidates"]
                if c["state"] == "requires_review"
            ],
            "note": "Explicitly reject conflicting new fact",
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert sha(conflicts[0]) == conflict_sha and sha(before["path"]) == saved


def test_manual_unapproved_draft_has_actor_and_no_approval(client, settings):
    csrf = login_and_change_password(client)
    customer = client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": csrf},
        json={"customer_name": "待补充客户", "save_only": True},
    ).json()["business_id"]
    created = client.post(
        f"/api/customers/{customer}/speakers/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "speaker_name": "真实人物",
            "public_role": "员工",
            "speaker_type": "frontline_expert",
            "materials": "本人亲自接待。",
        },
    ).json()
    detail = client.get(
        f'/api/customers/{customer}/speakers/{created["speaker_id"]}'
    ).json()
    assert detail["submitted_by"]["phone"] == "13800000000"
    assert detail["status"] == "pending_customer_profile"
    assert detail["speaker_persona"] is None


@pytest.mark.parametrize("discovery_failed", [True, False])
@pytest.mark.parametrize("facts_reviewed", [True, False])
def test_discovery_retry_reuses_customer_evidence_and_privacy(client, settings, discovery_failed, facts_reviewed):
    csrf = login_and_change_password(client)
    headers = {"X-CSRF-Token": csrf}
    body, detail = seed_customer(client, settings, csrf, discovery_failed=discovery_failed,
        discovery_empty=not discovery_failed)
    business = body["business_id"]
    assert detail["speaker_discovery_status"] == ("failed" if discovery_failed else "completed")
    if facts_reviewed:
        review_current(client, business, csrf)
    root = Path(body["task"]["payload"]["request_path"]).parent
    protected = {path: sha(path) for path in root.glob("*.json")}
    denied = client.post(f"/api/customers/{business}/speaker-discovery/retry")
    assert denied.status_code == 403
    started = client.post(
        f"/api/customers/{business}/speaker-discovery/retry", headers=headers
    )
    assert started.status_code == 200, started.text
    task = started.json()["task"]
    assert task["payload"]["intake_id"] == body["task"]["payload"]["intake_id"]
    repeat = client.post(
        f"/api/customers/{business}/speaker-discovery/retry", headers=headers
    ).json()
    assert repeat["existing_task"]["task_id"] == task["task_id"]
    assert (
        client.get(f"/api/customers/{business}").json()["status"]
        == ("persona_review_required" if facts_reviewed else "fact_review_required")
    )
    code = """
import sys
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1])/'scripts'))
import customer_onboarding_analysis_v1 as m
# Any attempted Customer model call makes this retry fail.
m.extract_remote_facts=lambda *_: (_ for _ in ()).throw(AssertionError('Customer model repeated'))
kwargs=dict(request_path=Path(sys.argv[2]),pipeline_root=Path(sys.argv[1]),extractor=lambda _: {'model':'synthetic-offline','speaker_candidates':[]})
m.retry_speaker_discovery(**kwargs)
kwargs['extractor']=lambda _: (_ for _ in ()).throw(AssertionError('Discovery repeated'))
m.retry_speaker_discovery(**kwargs)
"""
    result = subprocess.run(
        [
            str(settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"),
            "-X",
            "utf8",
            "-c",
            code,
            str(settings.pipeline_root),
            task["payload"]["discovery_retry_request"],
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    update_task(
        settings.database_path,
        task["task_id"],
        status="completed",
        progress=100,
        stage="人物发现完成",
    )
    after = client.get(f"/api/customers/{business}").json()
    assert (
        after["speaker_discovery_status"] == "completed"
        and after["speaker_candidates"] == []
    )
    assert all(sha(path) == value for path, value in protected.items())
    # A new explicit empty-result retry is separate; it cannot overwrite the
    # previous discovery or any Customer fact/approval artifact.
    output = Path(task["payload"]["discovery_retry_request"]).parent / "speaker_discovery_candidates_v1.json"
    protected_output = sha(output)
    next_retry = client.post(f"/api/customers/{business}/speaker-discovery/retry", headers=headers).json()
    assert next_retry["task"]["task_id"] != task["task_id"]
    assert sha(output) == protected_output
    assert all(sha(path) == value for path, value in protected.items())


def test_discovery_retry_does_not_repeat_nonempty_result(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed_customer(client, settings, csrf)
    response = client.post(f'/api/customers/{body["business_id"]}/speaker-discovery/retry',
        headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    assert response.json()["already_available"] is True
    after = client.get(f'/api/customers/{body["business_id"]}').json()
    assert after["speaker_candidates"] == detail["speaker_candidates"]
    assert after["status"] == "fact_review_required"


STRUCTURED_FORM = """第一部分：品牌与业务【必填资料】
1. 公司基本信息
- 公司或品牌简称：隔离表单样本
2. 你们主要做什么？
我们提供真实餐饮服务。
3. 哪些客户会来？
有聚会用餐需求的客人。
8. 差异化？
按客人忌口调整菜单。
第二部分：视频人物【必填资料】
每个人填写一份“视频人物资料”。
视频人物资料
1. 基本信息
- 姓名：测试人物甲
- 性别：男
- 出生年月：1988年5月
- 和品牌的关系：创始人
- 平时主要负责：菜单设计。
2. TA亲自做过哪些事情？
- 我亲自设计过菜单。
3. TA想讲什么？
- 我选择食材的经验。
4. 说话风格？
- 温和。
第三部分：补充内容【选填资料】
另一家餐厅获得过奖项，不属于出镜人经历。
"""


def test_structured_offline_fixture_keeps_personal_evidence_separate():
    from browser_customer_speaker_intake_v1 import structured_form_outputs

    output = structured_form_outputs(STRUCTURED_FORM)
    assert output["recognized"] is True
    assert {fact["topic"] for fact in output["facts"]} == {"primary_service", "core_audience", "differentiator"}
    assert len(output["speaker_candidates"]) == 1
    person = output["speaker_candidates"][0]
    assert person["name"] == "测试人物甲"
    assert person["candidate_status"] == "explicit_speaker"
    for quote in person["evidence_quotes"] + person["personal_material_quotes"]:
        assert quote in STRUCTURED_FORM
    personal = "\n\n".join(person["personal_material_quotes"])
    assert "1988" not in personal and "性别" not in personal and "奖项" not in personal
    assert {fact["topic"] for fact in structured_form_outputs(personal)["personal_facts"]} == {"speaker_practice", "speaker_allowed_topics"}
    two = structured_form_outputs(STRUCTURED_FORM.replace("第三部分：", "视频人物资料\n1. 基本信息\n- 姓名：测试人物乙\n- 和品牌的关系：员工\n2. 本人经历\n我亲自接待过客人。\n第三部分："))
    assert [person["name"] for person in two["speaker_candidates"]] == ["测试人物甲", "测试人物乙"]
    assert structured_form_outputs("普通自由文本，尚未运行真实 AI。")["recognized"] is False


def test_structured_fixture_uses_canonical_candidates_without_approval(client, settings):
    from browser_customer_speaker_intake_v1 import EXTRACT_CODE

    csrf = login_and_change_password(client)
    body = client.post("/api/customers/analyze", headers={"X-CSRF-Token": csrf},
        json={"customer_name": "隔离表单样本", "materials": STRUCTURED_FORM}).json()
    task = body["task"]
    result = subprocess.run([settings.pipeline_python_executable, "-X", "utf8", "-c", EXTRACT_CODE,
        str(settings.pipeline_root), str(settings.repo_root), "customer_analysis", task["payload"]["request_path"]],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    update_task(settings.database_path, task["task_id"], status="awaiting_review", stage="等待人工确认")
    detail = client.get(f'/api/customers/{body["business_id"]}').json()
    assert detail["status"] == "fact_review_required"
    assert len(detail["fact_candidates"]) >= 4  # identity + three literal answers
    assert detail["speaker_candidates"][0]["name"] == "测试人物甲"
    assert detail["speaker_candidates"][0]["default_selected"] is False
    assert not detail.get("business_persona")
    assert detail["speaker_count"] == 0
    root = Path(task["payload"]["request_path"]).parent
    assert not (root / "customer_fact_review_v1.json").exists()
    assert not (root / "speaker_discovery_confirmation_v1.json").exists()


def test_manual_harness_explicitly_marks_simulated_html(settings):
    from browser_customer_speaker_intake_v1 import add_fixture_notice
    from app.main import build_app
    from fastapi.testclient import TestClient

    application = build_app(settings)
    add_fixture_notice(application)
    with TestClient(application) as browser:
        response = browser.get("/login")
        assert response.status_code == 200
        assert '/isolated-fixture-notice.js' in response.text
        script = browser.get('/isolated-fixture-notice.js')
        assert "隔离验收：规则模拟解析" in script.text
        assert script.headers['content-type'].startswith('application/javascript')
        assert response.headers["content-length"] == str(len(response.content))
        assert "data-isolated-fixture" not in browser.get("/assets/app.js").text


def test_insufficient_then_new_fact_review_preserves_old_review(client, settings):
    csrf = login_and_change_password(client)
    headers = {"X-CSRF-Token": csrf}
    body = client.post(
        "/api/customers/analyze",
        headers=headers,
        json={"customer_name": "隔离资料不足客户", "materials": "提供宠物洗护。"},
    ).json()
    task = body["task"]
    business = body["business_id"]
    analyze_supplement(
        settings,
        task,
        facts=[
            {
                "topic": "primary_service",
                "value": ["宠物洗护"],
                "evidence_quote": "提供宠物洗护",
            }
        ],
    )
    first = review_current(client, business, csrf)
    assert first["review"]["status"] == "completed_persona_blocked"
    old_root = Path(task["payload"]["request_path"]).parent
    protected = {path: sha(path) for path in old_root.glob("*.json")}
    detail = client.get(f"/api/customers/{business}").json()
    answers = [
        {
            "target_gap": gap["gap_id"],
            "raw_answer": "服务附近养宠家庭。先检查毛发再洗护。",
        }
        for gap in detail["readiness_gaps"]
    ]
    newer = client.post(
        f"/api/customers/{business}/gaps/supplement",
        headers=headers,
        json={"answers": answers},
    )
    assert newer.status_code == 200, newer.text
    facts = [
        {
            "topic": "core_audience",
            "value": ["附近养宠家庭"],
            "evidence_quote": "服务附近养宠家庭",
        },
        {
            "topic": "service_process",
            "value": ["先检查毛发再洗护"],
            "evidence_quote": "先检查毛发再洗护",
        },
    ]
    analyze_supplement(settings, newer.json()["task"], facts=facts)
    new_detail = client.get(f"/api/customers/{business}").json()
    assert all(
        c["field"] != "primary_products_or_services"
        for c in new_detail["fact_candidates"]
        if c["state"] == "requires_review"
    )
    reviewed = review_current(client, business, csrf)
    assert reviewed["review"]["status"] == "completed_persona_review_required"
    approval = client.post(
        f"/api/customers/{business}/persona/approve",
        headers=headers,
        json={"note": "Synthetic independent approval after gaps"},
    )
    assert approval.status_code == 200, approval.text
    assert all(sha(path) == value for path, value in protected.items())
    assert client.get(f"/api/customers/{business}").json()["status"] == "approved"


def test_manual_industry_review_distinguishes_absent_uncertain_and_confirmed(
    client, settings
):
    csrf = login_and_change_password(client)
    headers = {"X-CSRF-Token": csrf}
    for label, choice in [
        ("未提供", None),
        ("人工不确定", {"decision": "uncertain", "value": None}),
        ("人工选择", {"decision": "confirm", "value": "本地生活"}),
    ]:
        body, detail = seed_customer(
            client, settings, csrf, name="行业区分" + label, industry=None
        )
        business = body["business_id"]
        original = (
            Path(body["task"]["payload"]["request_path"]).parent
            / "persona_fact_candidates_v1.json"
        )
        original_sha = sha(original)
        payload = {
            "decisions": [
                {"candidate_id": c["candidate_id"], "decision": "approve"}
                for c in detail["fact_candidates"]
                if c["state"] == "requires_review"
            ],
            "note": "Explicit Human industry audit",
        }
        if choice is not None:
            payload["industry_review"] = choice
        response = client.post(
            f"/api/customers/{business}/facts/review", headers=headers, json=payload
        )
        assert response.status_code == 200, response.text
        detail = client.get(f"/api/customers/{business}").json()
        assert detail["fact_review"].get("industry_review") == choice
        industry = next(
            (c for c in detail["reviewed_fact_candidates"] if c["field"] == "industry"),
            None,
        )
        if choice is None:
            assert industry is None
        elif choice["decision"] == "uncertain":
            assert industry["state"] == "unknown" and industry["value"] is None
        else:
            assert (
                industry["state"] == "known_candidate"
                and industry["value"] == "本地生活"
            )
        assert detail["business_persona"]["approved"] is False
        assert sha(original) == original_sha
