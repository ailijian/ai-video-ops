"""Offline intake acceptance. No provider/model calls or production data."""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth_service import provision_user
from app.case_classification import recommend_classification
from app.database import transaction
from app.operator_projection import operator_activity
from app.main import build_app
from app.task_service import update_task
from conftest import login_and_change_password

ID = "7999999999999999801"
URL = f"https://www.douyin.com/video/{ID}"


def group(client, csrf, text=URL, request_id=None):
    return client.post("/api/case-intake/groups", headers={"X-CSRF-Token": csrf},
                       json={"text": text, "client_request_id": request_id or uuid.uuid4().hex})


def evidence_case(case_id=ID):
    return {
        "case_id": case_id, "identity": {"platform": "douyin", "source_url": f"https://www.douyin.com/video/{case_id}",
            "duration_seconds": 20, "industry": "待分类"},
        "lifecycle": {"status": "review_required", "approved": False},
        "validation": {"passed": True, "privacy_gate_passed": True, "auto_approved": False},
        "audio_evidence": {"speech_evidence_status": "detected"},
        "storyboard": {
            "narration_track": [{"segment_id": "A001", "start": 0, "end": 16, "text_safe_verbatim": "介绍菜品"}],
            "shots": [{"shot_id": f"S00{i}", "start": (i-1)*10, "end": i*10,
                       "evidence": {"observable_scene_safe_verbatim": ["餐厅厨房正在制作菜品"]},
                       "interpretation": {}} for i in (1,2)],
            "video_understanding": {},
        },
    }


def candidate(settings, task, case=None):
    case = copy.deepcopy(case or evidence_case(task["subject_ref"]))
    case_id = task["subject_ref"]
    root = settings.pipeline_root / "data" / "case_analysis_attempts" / case_id / task["task_id"]
    path = root / "candidate_cases" / case_id / "case_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    board = root / "reverse_storyboard_v1.json"
    board.write_text(json.dumps({"case_id": case_id, "validation": {"passed": True},
                                "narration_track": case["storyboard"].pop("narration_track", [])}), encoding="utf-8")
    case["storyboard"]["artifact"] = {"path": str(board), "sha256": hashlib.sha256(board.read_bytes()).hexdigest()}
    case["analysis_lineage"] = {"attempt_id": task["task_id"]}
    path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    (root / "case_analysis_attempt_v1.json").write_text(json.dumps({
        "case_id": case_id, "attempt_id": task["task_id"], "status": "awaiting_review",
        "source": {"canonical_url": f"https://www.douyin.com/video/{case_id}"},
        "artifacts": {"case_candidate_v1": str(path)},
    }), encoding="utf-8")
    update_task(settings.database_path, task["task_id"], status="awaiting_review", stage="等待人工审核")
    return path


@pytest.mark.parametrize("text,code", [
    (" ", "CASE_URL_INVALID"), ("乱写内容", "CASE_URL_INVALID"),
    ("https://www.douyin.com/user/123", "CASE_SOURCE_NOT_VIDEO"),
    ("https://www.xiaohongshu.com/explore/abc", "CASE_PLATFORM_UNSUPPORTED"),
    ("https://www.douyin.com/video/1", "CASE_SOURCE_IDENTITY_UNRESOLVED"),
])
def test_invalid_and_unsupported_links_do_not_create_tasks(client, text, code):
    csrf = login_and_change_password(client)
    response = group(client, csrf, text)
    if response.status_code == 200:
        assert response.json()["items"][0]["error_code"] == code
    else:
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == code
    assert client.get("/api/tasks").json()["tasks"] == []


def test_share_text_internal_identity_duplicates_and_double_click(client):
    csrf = login_and_change_password(client)
    key = uuid.uuid4().hex
    raw = f"分享视频：\n{URL}?share=1\n\n无关文字 {URL}。\n"
    one = group(client, csrf, raw, key)
    assert one.status_code == 200, one.text
    items = one.json()["items"]
    assert len(items) == 2 and items[1]["state"] == "input_duplicate"
    assert "operator_profile_hint" not in items[0]["task"]["payload"]
    assert items[0]["task"]["payload"]["industry"] == "待分类"
    assert group(client, csrf, raw, key).json()["group_id"] == one.json()["group_id"]
    other = group(client, csrf, URL)
    assert other.json()["items"][0]["task"]["task_id"] == items[0]["task"]["task_id"]
    assert len(client.get("/api/tasks").json()["tasks"]) == 1
    assert group(client, csrf, URL + "?other=1", key).status_code == 422


def test_ten_items_use_existing_admission_limit_and_persist_across_restart(client, settings):
    csrf = login_and_change_password(client)
    urls = [f"https://www.douyin.com/video/{7999999999999999800+i}" for i in range(10)]
    result = group(client, csrf, "\n".join(urls))
    assert result.status_code == 200, result.text
    initial = result.json()
    assert sum(i["state"] == "pending" for i in initial["items"]) == 7
    assert len(client.get("/api/tasks").json()["tasks"]) == 3
    # One failure frees admission capacity; every other video remains independent.
    failed = next(i["task"] for i in initial["items"] if i["task"])
    update_task(settings.database_path, failed["task_id"], status="failed", error_code="SOURCE_ACQUISITION_FAILED")
    restarted = build_app(settings)
    with TestClient(restarted) as other:
        login_and_change_password_if_needed(other)
        restarted.state.intake_dispatch()
        restored = other.get(f"/api/case-intake/groups/{initial['group_id']}").json()
        assert len(restored["items"]) == 10
        assert sum(i["task"] is not None for i in restored["items"]) == 4
        assert any(i["task"] and i["task"]["status"] == "failed" for i in restored["items"])
        assert other.get("/api/case-intake/groups").json()["groups"][0]["group_id"] == initial["group_id"]


def login_and_change_password_if_needed(client):
    login = client.post("/api/auth/login", json={"phone": "13800000000", "password": "ReviewConsole2026!"})
    assert login.status_code == 200
    return login.json()["csrf_token"]


def test_eleven_valid_items_are_rejected_before_task_creation(client):
    csrf = login_and_change_password(client)
    text = "\n".join(f"https://www.douyin.com/video/{7999999999999999800+i}" for i in range(11))
    response = group(client, csrf, text)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CASE_BATCH_LIMIT"
    assert client.get("/api/tasks").json()["tasks"] == []


def test_failed_task_retry_keeps_attempt_identity_and_checkpoint(client, settings):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    root = settings.pipeline_root / "data" / "case_analysis_attempts" / ID / task["task_id"]
    root.mkdir(parents=True)
    checkpoint = root / "checkpoint.json"
    checkpoint.write_text('{"completed":"visual"}')
    update_task(settings.database_path, task["task_id"], status="failed", error_code="SOURCE_ACQUISITION_FAILED")
    repeated = group(client, csrf).json()["items"][0]
    assert repeated["task"]["task_id"] == task["task_id"]
    response = client.post(f"/api/tasks/{task['task_id']}/retry", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    assert response.json()["task"]["task_id"] == task["task_id"]
    again = client.post(f"/api/tasks/{task['task_id']}/retry", headers={"X-CSRF-Token": csrf})
    assert again.json()["task"]["task_id"] == task["task_id"]
    assert len(client.get("/api/tasks").json()["tasks"]) == 1
    assert checkpoint.read_text() == '{"completed":"visual"}'


def test_failed_task_retry_is_bounded_and_audited_without_new_attempt(client, settings):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    route = f"/api/tasks/{task['task_id']}/retry"
    assert client.post(route).status_code == 403
    for count in range(1, 4):
        update_task(settings.database_path, task["task_id"], status="failed", error_code="SOURCE_ACQUISITION_FAILED")
        result = client.post(route, headers={"X-CSRF-Token": csrf})
        assert result.status_code == 200, result.text
        retried = result.json()["task"]
        assert retried["task_id"] == task["task_id"]
        actions = retried["payload"]["retry_actions"]
        assert len(actions) == count
        assert actions[-1]["phone"] == "13800000000" and actions[-1]["user_id"]
        # Double-clicks while queued do not consume another retry or make another task.
        assert client.post(route, headers={"X-CSRF-Token": csrf}).json()["task"]["payload"]["retry_actions"] == actions
    update_task(settings.database_path, task["task_id"], status="failed", error_code="SOURCE_ACQUISITION_FAILED")
    blocked = client.post(route, headers={"X-CSRF-Token": csrf})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "CASE_RETRY_LIMIT_REACHED"
    duplicate = group(client, csrf).json()["items"][0]["task"]
    assert duplicate["task_id"] == task["task_id"] and duplicate["status"] == "failed"
    assert len(duplicate["payload"]["retry_actions"]) == 3
    assert len(client.get("/api/tasks").json()["tasks"]) == 1


def test_classification_changes_only_companion_and_keeps_ai_original(client, settings):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    path = candidate(settings, task)
    original_bytes = path.read_bytes()
    state = client.get(f"/api/cases/{ID}/classification").json()
    assert state["suggestion"]["industry"] == "餐饮"
    assert state["suggestion"]["observed_source_profile"] == "mix"
    def confirm(state, industry, profile):
        return client.post(f"/api/cases/{ID}/classification", headers={"X-CSRF-Token": csrf}, json={
            "industry": industry, "profile": profile, "candidate_sha256": state["candidate_sha256"],
            "expected_confirmation_sha256": state["confirmation_sha256"],
            "actor_user_id": 999, "actor_phone": "forged",
        })
    first = confirm(state, "零售", "news")
    assert first.status_code == 200, first.text
    assert first.json()["human"]["confirmed_by_phone"] == "13800000000"
    assert first.json()["human"]["confirmed_by_user_id"] != 999
    second = confirm(first.json(), "宠物服务", "uncertain")
    assert second.status_code == 200
    assert second.json()["suggestion"] == state["suggestion"]
    assert second.json()["human"]["industry"] == "宠物服务"
    assert path.read_bytes() == original_bytes
    assert json.loads(path.read_text(encoding="utf-8"))["lifecycle"]["approved"] is False
    assert not (path.parent / "approval_receipt.json").exists()
    assert not (settings.pipeline_root / "data" / "fingerprints" / ID).exists()
    assert all(second.json()["authority"][k] is False for k in ("case_approval", "profile_compatibility_approval", "media_rights_granted", "customer_facts_created"))
    assert confirm(state, "餐饮", "mix").status_code == 409
    events = operator_activity(settings.database_path, settings.pipeline_root)["events"]
    assert sum(e["kind"] == "确认案例分类" for e in events) == 2
    # Another device/operator reads the same human confirmation.
    with TestClient(build_app(settings)) as other:
        login_and_change_password_if_needed(other)
        assert other.get(f"/api/cases/{ID}/classification").json()["human"] == second.json()["human"]


def test_smart_case_cannot_skip_classification_or_final_evidence_gate(client, settings):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    path = candidate(settings, task)
    response = client.post(f"/api/cases/{ID}/review", headers={"X-CSRF-Token": csrf}, json={"decision": "approve"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CASE_CLASSIFICATION_REQUIRED"
    assert json.loads(path.read_text(encoding="utf-8"))["lifecycle"]["approved"] is False


def test_suggestions_require_evidence_not_titles_and_allow_unknown():
    case = evidence_case()
    assert recommend_classification(case, "a"*64)["observed_source_profile"] == "mix"
    case["storyboard"]["narration_track"] = []
    case["source_metadata"] = {"desc": "新闻 餐厅厨房菜品"}
    case["storyboard"]["shots"] = []
    unknown = recommend_classification(case, "a"*64)
    assert unknown["industry"] is None and unknown["observed_source_profile"] == "uncertain"
    assert unknown["needs_human_judgment"]
    assert unknown["remote_model_called"] is False


def test_group_and_confirmation_require_auth_and_csrf(client):
    assert client.get("/api/case-intake/groups").status_code == 401
    csrf = login_and_change_password(client)
    assert client.post("/api/case-intake/groups", json={"text": URL, "client_request_id": uuid.uuid4().hex}).status_code == 403
    assert group(client, csrf).status_code == 200


def test_approved_duplicate_does_not_create_task_or_change_immutable_bytes(client, settings):
    csrf = login_and_change_password(client)
    root = settings.pipeline_root / "data"
    protected = [root / "cases" / "7999999999999999901" / "case_v1.json",
                 root / "cases" / "7999999999999999901" / "approval_receipt.json",
                 root / "fingerprints" / "7999999999999999901" / "case_fingerprint_v1.json"]
    before = [p.read_bytes() for p in protected]
    result = group(client, csrf, "https://www.douyin.com/video/7999999999999999901")
    assert result.json()["items"][0]["case"]["status"] == "approved"
    assert result.json()["items"][0]["task"] is None
    assert client.get("/api/tasks").json()["tasks"] == []
    assert [p.read_bytes() for p in protected] == before


def test_bound_real_storyboard_hash_mismatch_returns_uncertain(client, settings):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    path = candidate(settings, task)
    case = json.loads(path.read_text(encoding="utf-8"))
    assert "narration_track" not in case["storyboard"]
    assert client.get(f"/api/cases/{ID}/classification").json()["suggestion"]["observed_source_profile"] == "mix"
    Path(case["storyboard"]["artifact"]["path"]).write_text('{}', encoding="utf-8")
    assert client.get(f"/api/cases/{ID}/classification").json()["suggestion"]["observed_source_profile"] == "uncertain"


def test_retry_does_not_bypass_original_queue_capacity(client, settings):
    csrf = login_and_change_password(client)
    failed = group(client, csrf).json()["items"][0]["task"]
    update_task(settings.database_path, failed["task_id"], status="failed")
    result = group(client, csrf, "\n".join(f"https://www.douyin.com/video/{7999999999999999810+i}" for i in range(3)))
    assert result.status_code == 200
    response = client.post(f"/api/tasks/{failed['task_id']}/retry", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 429
    assert response.json()["detail"]["code"] == "GPU_PENDING_LIMIT_REACHED"
    assert client.get(f"/api/tasks/{failed['task_id']}").json()["task"]["status"] == "failed"


def test_confirmed_labels_still_cannot_bypass_case_approval_gates(client, settings):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    path = candidate(settings, task)
    state = client.get(f"/api/cases/{ID}/classification").json()
    response = client.post(f"/api/cases/{ID}/classification", headers={"X-CSRF-Token": csrf}, json={
        "industry":"餐饮", "profile":"mix", "candidate_sha256":state["candidate_sha256"],
        "expected_confirmation_sha256":None})
    assert response.status_code == 200
    before = path.read_bytes()
    blocked = client.post(f"/api/cases/{ID}/review", headers={"X-CSRF-Token":csrf}, json={"decision":"approve"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "CASE_APPROVAL_BLOCKED"
    assert path.read_bytes() == before


def test_short_share_identity_and_unresolvable_duplicate_are_not_guessed():
    from app.case_intake_service import prepare_items
    from app.douyin_source_input import DouyinSourceInput, SourceInputError
    calls = []
    def resolver(url):
        calls.append(url)
        if "unresolved" in url:
            raise SourceInputError("CASE_SOURCE_IDENTITY_UNRESOLVED", "无法可靠识别来源视频。")
        return DouyinSourceInput("short_url", url, URL, ID)
    items = prepare_items(f"完整分享 https://v.douyin.com/abc/。\n{URL}?share=1\nhttps://v.douyin.com/unresolved/", resolver)
    assert items[1]["state"] == "input_duplicate"
    assert items[2]["error_code"] == "CASE_SOURCE_IDENTITY_UNRESOLVED"
    assert len(calls) == 3


def test_cover_requires_bound_local_asset_and_authenticated_access(client, settings, tmp_path):
    csrf = login_and_change_password(client)
    task = group(client, csrf).json()["items"][0]["task"]
    path = candidate(settings, task)
    case = json.loads(path.read_text(encoding="utf-8"))
    cover = path.parent / "cover.jpg"
    cover.write_bytes(b"synthetic-cover-test")
    case["source_evidence"] = {"cover": {"path":str(cover), "sha256":hashlib.sha256(cover.read_bytes()).hexdigest()}}
    path.write_text(json.dumps(case), encoding="utf-8")
    assert client.get(f"/api/cases/{ID}/cover").status_code == 200
    cover.write_bytes(b"changed")
    assert client.get(f"/api/cases/{ID}/cover").status_code == 404
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    case["source_evidence"]["cover"] = {"path":str(outside), "sha256":hashlib.sha256(outside.read_bytes()).hexdigest()}
    path.write_text(json.dumps(case), encoding="utf-8")
    assert client.get(f"/api/cases/{ID}/cover").status_code == 404


def test_colleague_recovers_shared_group_without_new_attempt(client, settings):
    csrf = login_and_change_password(client)
    batch = group(client, csrf).json()
    task = batch["items"][0]["task"]
    candidate(settings, task)
    provision_user(settings.database_path, "13800000001")
    with TestClient(build_app(settings)) as colleague:
        login = colleague.post("/api/auth/login", json={"phone":"13800000001", "password":"123456"})
        changed = colleague.post("/api/auth/change-password", headers={"X-CSRF-Token":login.json()["csrf_token"]}, json={
            "current_password":"123456", "new_password":"ReviewConsole2026!", "confirm_password":"ReviewConsole2026!"})
        assert changed.status_code == 200
        restored = colleague.get(f"/api/case-intake/groups/{batch['group_id']}").json()
        assert restored["items"][0]["task"]["task_id"] == task["task_id"]
        assert restored["items"][0]["classification"]["status"] == "needs_confirmation"
        assert len(colleague.get("/api/tasks").json()["tasks"]) == 1
