"""CS gates: real app/gateways/subprocesses/locks, synthetic extraction only."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth_service import provision_user
from app.database import transaction
from app.operation_lock import authority_operation_lock
from app.task_service import latest_subject_task, update_task
from conftest import login_and_change_password


@pytest.fixture()
def settings(settings):
    return replace(
        settings,
        pipeline_python_executable=str(
            settings.repo_root / "ops-pipeline/.venv/Scripts/python.exe"
        ),
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_customer(
    client,
    settings,
    csrf,
    *,
    name="智能建档集成客户",
    missing_identity=False,
    industry="本地生活",
    discovery_failed=False,
    discovery_empty=False,
):
    body = client.post(
        "/api/customers/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "customer_name": name,
            "industry": industry,
            "materials": "提供宠物洗护。服务附近养宠家庭。先检查毛发再洗护。负责人小林亲自洗护并愿意出镜。",
        },
    ).json()
    task = body["task"]
    shutil.copy2(
        settings.repo_root / "ops-pipeline/speaker_prompt.md",
        settings.pipeline_root / "speaker_prompt.md",
    )
    code = """
import json,sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
from customer_onboarding_analysis_v1 import analyze_customer_onboarding
if sys.argv[4]=='1':
    def fail_discovery(_): raise RuntimeError('synthetic discovery unavailable')
else: fail_discovery=None
facts=[('primary_service',['宠物洗护'],'提供宠物洗护'),
       ('core_audience',['附近养宠家庭'],'服务附近养宠家庭'),
       ('service_process',['先检查毛发再洗护'],'先检查毛发再洗护')]
analyze_customer_onboarding(request=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')),
    pipeline_root=Path(sys.argv[1]),
    extractor=lambda _: {'facts':[{'topic':t,'value':v,'evidence_quote':q} for t,v,q in facts],'model':'synthetic-offline'},
    speaker_discovery_extractor=fail_discovery or (lambda _: {'model':'synthetic-offline','speaker_candidates':[] if sys.argv[5]=='1' else [
        {'name':None if sys.argv[3]=='1' else '小林','public_role':'负责人','speaker_type_hint':'frontline_expert',
         'candidate_status':'explicit_speaker','evidence_quotes':['负责人小林亲自洗护并愿意出镜'],
         'personal_material_quotes':['负责人小林亲自洗护并愿意出镜'],'explicit_forbidden_claims':[]}]}))
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
            "1" if missing_identity else "0",
            "1" if discovery_failed else "0",
            "1" if discovery_empty else "0",
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
    detail = client.get(f'/api/customers/{body["business_id"]}').json()
    return body, detail


def review_payload(detail, *, selected=True):
    return {
        "decisions": [
            {"candidate_id": item["candidate_id"], "decision": "approve"}
            for item in detail["fact_candidates"]
            if item["state"] == "requires_review"
        ],
        "note": "Synthetic integration Human review",
        "speaker_confirmations": [
            {
                "candidate_id": detail["speaker_candidates"][0]["candidate_id"],
                "selected": selected,
                "speaker_name": "小林",
                "public_role": "负责人",
                "speaker_type": "frontline_expert",
            }
        ],
    }


def test_cs0_real_http_review_and_independent_recovery(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    body, detail = seed_customer(client, settings, csrf)
    business = body["business_id"]
    import app.customer_gateway as gateway

    original = gateway.prepare_discovered_speaker_draft

    def fail_once(*args, **kwargs):
        raise OSError("synthetic unavailable storage")

    monkeypatch.setattr(gateway, "prepare_discovered_speaker_draft", fail_once)
    response = client.post(
        f"/api/customers/{business}/facts/review",
        headers={"X-CSRF-Token": csrf},
        json=review_payload(detail),
    )
    assert response.status_code == 200, response.text
    assert response.json()["review"]["status"] == "completed_persona_review_required"
    assert response.json()["speaker_confirmation"]["retry_required"] is True
    review = (
        Path(body["task"]["payload"]["request_path"]).parent
        / "customer_fact_review_v1.json"
    )
    original_sha = sha(review)
    refreshed = client.get(f"/api/customers/{business}").json()
    assert refreshed["speaker_confirmation"]["retry_required"] is True
    assert refreshed["task"]["status"] == "completed"
    assert refreshed["business_persona"]["approved"] is False
    assert refreshed["speaker_candidates"][0]["confirmation"]["selected"] is True
    monkeypatch.setattr(gateway, "prepare_discovered_speaker_draft", original)
    retry = client.post(
        f"/api/customers/{business}/speaker-discovery/confirm",
        headers={"X-CSRF-Token": csrf},
        json={"decisions": []},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["speaker_confirmation"]["retry_required"] is False
    assert sha(review) == original_sha
    confirmation = review.parent / "speaker_discovery_confirmation_v1.json"
    confirmation_sha = sha(confirmation)
    repeat = client.post(
        f"/api/customers/{business}/speaker-discovery/confirm",
        headers={"X-CSRF-Token": csrf},
        json={"decisions": []},
    )
    assert repeat.status_code == 200
    assert sha(confirmation) == confirmation_sha
    assert (
        len(client.get(f"/api/customers/{business}/speakers").json()["speakers"]) == 1
    )
    assert sha(review) == original_sha


def test_cs0_real_review_success_and_csrf_and_lock(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed_customer(client, settings, csrf)
    url = f'/api/customers/{body["business_id"]}/facts/review'
    payload = review_payload(detail)
    assert client.post(url, json=payload).status_code == 403
    with authority_operation_lock(settings, "business", body["business_id"]):
        blocked = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
        assert blocked.status_code != 200
    first = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()["speaker_confirmation"]["retry_required"] is False
    review = (
        Path(body["task"]["payload"]["request_path"]).parent
        / "customer_fact_review_v1.json"
    )
    saved = sha(review)
    repeated = client.post(url, headers={"X-CSRF-Token": csrf}, json=payload)
    assert repeated.status_code == 200
    assert sha(review) == saved


def test_cs0_two_actors_cannot_replace_review(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed_customer(client, settings, csrf)
    provision_user(settings.database_path, "13800000002")
    with TestClient(client.app) as colleague:
        logged = colleague.post(
            "/api/auth/login", json={"phone": "13800000002", "password": "123456"}
        ).json()
        other = colleague.post(
            "/api/auth/change-password",
            headers={"X-CSRF-Token": logged["csrf_token"]},
            json={
                "current_password": "123456",
                "new_password": "Colleague2026!",
                "confirm_password": "Colleague2026!",
            },
        ).json()["csrf_token"]
        url = f'/api/customers/{body["business_id"]}/facts/review'
        payload = review_payload(detail, selected=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda args: args[0].post(
                        url, headers={"X-CSRF-Token": args[1]}, json=payload
                    ),
                    [(client, csrf), (colleague, other)],
                )
            )
        assert sum(r.status_code == 200 for r in responses) == 1
        assert all(r.status_code != 500 for r in responses)
        record = client.get(f'/api/customers/{body["business_id"]}').json()
        assert record["business_persona"]["approved"] is False
        assert record["speakers"] == []


def test_cs0_subject_task_ignores_global_window_and_old_updates(client, settings):
    csrf = login_and_change_password(client)
    body, _ = seed_customer(client, settings, csrf)
    original = body["task"]
    update_task(
        settings.database_path,
        original["task_id"],
        status="failed",
        error_code="SYNTHETIC_FAILURE",
        error_message="合成失败",
    )
    retry = client.post(
        f'/api/customers/{body["business_id"]}/retry', headers={"X-CSRF-Token": csrf}
    ).json()["task"]
    # Updating historical rows and an arbitrarily crowded global list must not
    # turn the current retry back into failure.
    with transaction(settings.database_path) as connection:
        connection.execute(
            "UPDATE tasks SET updated_at='2099-01-01' WHERE task_id=?",
            (original["task_id"],),
        )
        columns = [
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)")
        ]
        row = dict(
            connection.execute(
                "SELECT * FROM tasks WHERE task_id=?", (original["task_id"],)
            ).fetchone()
        )
        for i in range(120):
            item = {
                **row,
                "task_id": f"unrelated-{i}",
                "subject_ref": f"other-{i}",
                "operation_identity": f"other-{i}",
                "status": "completed",
                "updated_at": "2099-01-01",
            }
            connection.execute(
                f"INSERT INTO tasks ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [item[key] for key in columns],
            )
    latest = latest_subject_task(
        settings.database_path, "customer_analysis", body["business_id"]
    )
    assert latest["task_id"] == retry["task_id"]
    listed = next(
        item
        for item in client.get("/api/customers").json()["customers"]
        if item["business_id"] == body["business_id"]
    )
    detail = client.get(f'/api/customers/{body["business_id"]}').json()
    assert listed["task"]["task_id"] == detail["task"]["task_id"] == retry["task_id"]
    assert listed["status"] == detail["status"] == "analyzing"


def test_cs0_speaker_retry_and_projection(client, settings):
    csrf = login_and_change_password(client)
    business = "fixture_business_001"
    created = client.post(
        f"/api/customers/{business}/speakers/analyze",
        headers={"X-CSRF-Token": csrf},
        json={
            "speaker_name": "恢复人物",
            "public_role": "洗护师",
            "speaker_type": "frontline_expert",
            "materials": "本人亲自检查毛发。",
            "forbidden_claims": [],
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    speaker = body["speaker_id"]
    original = body["task"]
    update_task(
        settings.database_path,
        original["task_id"],
        status="failed",
        error_code="SYNTHETIC_FAILURE",
        error_message="合成失败",
    )
    retry = client.post(
        f"/api/customers/{business}/speakers/{speaker}/analyze",
        headers={"X-CSRF-Token": csrf},
    )
    assert retry.status_code == 200, retry.text
    task = retry.json()["task"]
    assert task["task_id"] != original["task_id"]
    listed = next(
        s
        for s in client.get(f"/api/customers/{business}/speakers").json()["speakers"]
        if s["speaker_id"] == speaker
    )
    detail = client.get(f"/api/customers/{business}/speakers/{speaker}").json()
    embedded = next(
        s
        for s in client.get(f"/api/customers/{business}").json()["speakers"]
        if s["speaker_id"] == speaker
    )
    assert (
        listed["task"]["task_id"]
        == detail["task"]["task_id"]
        == embedded["task"]["task_id"]
        == task["task_id"]
    )
    assert listed["status"] == detail["status"] == embedded["status"] == "analyzing"


def test_cs0_missing_speaker_identity_persists_without_blocking_facts(client, settings):
    csrf = login_and_change_password(client)
    body, detail = seed_customer(client, settings, csrf, missing_identity=True)
    payload = review_payload(detail)
    payload["speaker_confirmations"][0]["speaker_name"] = ""
    payload["speaker_confirmations"][0]["public_role"] = ""
    response = client.post(
        f'/api/customers/{body["business_id"]}/facts/review',
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["speaker_confirmation"]["retry_required"] is True
    refreshed = client.get(f'/api/customers/{body["business_id"]}').json()
    assert (
        refreshed["speaker_candidates"][0]["confirmation"]["outcome"]
        == "identity_required"
    )
    assert refreshed["task"]["status"] == "completed"
    assert refreshed["speakers"] == []


def test_worker_error_projection_does_not_expose_private_subprocess_message():
    from app.customer_task_service import _parse_failure as customer_error
    from app.speaker_task_service import _parse_failure as speaker_error

    private = "private source C:/private/customer.json credential=secret"
    stdout = json.dumps({"ok": False, "code": "MODEL_ERROR", "message": private})
    for parse in (customer_error, speaker_error):
        code, message = parse(stdout)
        assert code == "MODEL_ERROR"
        assert private not in message and "private" not in message
        assert "继续分析" in message
