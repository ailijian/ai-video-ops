from datetime import datetime, timedelta, timezone
import json
import os

import pytest

from app import case_uploads
from app.task_service import update_task
from conftest import login_and_change_password

CASE_ID = "7999999999999999811"
URL = f"https://www.douyin.com/video/{CASE_ID}"


def upload(client, csrf, **params):
    return client.post("/api/cases/source-files", params={
        "url": URL, "suffix": ".mp4", "rights_confirmed": True,
        "source_match_confirmed": True, **params,
    }, content=b"synthetic-video-not-a-real-case", headers={"X-CSRF-Token": csrf})


@pytest.fixture
def probe(monkeypatch):
    calls = []
    def inspect(settings, path):
        calls.append(path)
        return {"duration_seconds": 2, "width": 64, "height": 64, "audio_present": True}
    monkeypatch.setattr(case_uploads, "probe_upload", inspect)
    return calls


def test_upload_creates_no_task_until_explicit_analysis(client, settings, probe):
    csrf = login_and_change_password(client)
    result = upload(client, csrf)
    assert result.status_code == 200, result.text
    ref = result.json()
    directory = case_uploads.upload_directory(settings.pipeline_root, ref["upload_id"])
    receipt = json.loads((directory / case_uploads.RECEIPT).read_text(encoding="utf-8"))
    assert receipt["uploaded_by_user_id"] > 0
    assert receipt["uploaded_by_phone"] == "13800000000"
    assert receipt["binding_method"] == "operator_attestation"
    assert receipt["media_rights_granted"] is False
    assert receipt["platform_original_verified"] is False
    assert receipt["production_footage_pool_eligible"] is False
    assert client.get("/api/tasks").json()["tasks"] == []
    response = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "uncertain", "source_upload_id": ref["upload_id"],
    })
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    assert task["payload"]["source_upload"]["upload_id"] == ref["upload_id"]
    duplicate = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": f"复制打开抖音 {URL}", "operator_profile_hint": "news",
    }).json()
    assert duplicate["existing_task"]["task_id"] == task["task_id"]


def test_qiyun_source_only_task_records_provider_without_secret(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    object.__setattr__(settings, "case_acquisition_provider", "qiyun")
    monkeypatch.setenv("QYAPI_APP_ID", "fixture-id")
    monkeypatch.setenv("QYAPI_APP_KEY", "fixture-key")
    response = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "news",
    })
    assert response.status_code == 200, response.text
    payload = response.json()["task"]["payload"]
    assert payload["source_url"] == URL
    assert payload["acquisition_provider"] == "qiyun"
    assert "source_upload" not in payload
    assert "fixture-key" not in response.text
    duplicate = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": f"复制打开抖音 {URL}", "operator_profile_hint": "mix",
    })
    assert duplicate.status_code == 200
    assert duplicate.json()["existing_task"]["task_id"] == response.json()["task"]["task_id"]


def test_case_capability_reports_configured_acquisition_without_secret(client, settings, monkeypatch):
    login_and_change_password(client)
    legacy = client.get("/api/capabilities").json()["case_analysis"]["source_acquisition"]
    assert legacy == {"mode": "legacy_downloader", "configured": True}
    object.__setattr__(settings, "case_acquisition_provider", "qiyun")
    monkeypatch.delenv("QYAPI_APP_ID", raising=False)
    monkeypatch.delenv("QYAPI_APP_KEY", raising=False)
    missing = client.get("/api/capabilities").json()["case_analysis"]["source_acquisition"]
    assert missing == {"mode": "qiyun", "configured": False}
    monkeypatch.setenv("QYAPI_APP_ID", "fixture-id")
    monkeypatch.setenv("QYAPI_APP_KEY", "fixture-secret")
    ready = client.get("/api/capabilities").json()
    assert ready["case_analysis"]["source_acquisition"] == {"mode": "qiyun", "configured": True}
    assert "fixture-secret" not in str(ready)
    object.__setattr__(settings, "case_acquisition_provider", "upload_only")
    assert client.get("/api/capabilities").json()["case_analysis"]["source_acquisition"] == {
        "mode": "upload_only", "configured": True,
    }


def test_qiyun_missing_credentials_rejects_source_only_but_keeps_upload(client, settings, probe, monkeypatch):
    csrf = login_and_change_password(client)
    object.__setattr__(settings, "case_acquisition_provider", "qiyun")
    monkeypatch.delenv("QYAPI_APP_ID", raising=False)
    monkeypatch.delenv("QYAPI_APP_KEY", raising=False)
    response = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "mix",
    })
    assert response.status_code == 503
    assert client.get("/api/tasks").json()["tasks"] == []
    uploaded = upload(client, csrf)
    assert uploaded.status_code == 200
    result = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "mix", "source_upload_id": uploaded.json()["upload_id"],
    })
    assert result.status_code == 200
    assert result.json()["task"]["payload"]["source_upload"]["upload_id"] == uploaded.json()["upload_id"]


def test_qiyun_short_link_keeps_canonical_identity_with_operational_provider_url(client, settings, monkeypatch):
    from app import main
    from app.douyin_source_input import DouyinSourceInput

    csrf = login_and_change_password(client)
    object.__setattr__(settings, "case_acquisition_provider", "qiyun")
    monkeypatch.setenv("QYAPI_APP_ID", "fixture-id")
    monkeypatch.setenv("QYAPI_APP_KEY", "fixture-key")
    short = "https://v.douyin.com/fixture123/"
    monkeypatch.setattr(main, "resolve_douyin_source_input", lambda _raw: DouyinSourceInput(
        input_kind="share_text", extracted_url=short, canonical_url=URL, video_id=CASE_ID,
    ))
    result = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": f"复制打开抖音 {short}", "operator_profile_hint": "uncertain",
    })
    assert result.status_code == 200, result.text
    payload = result.json()["task"]["payload"]
    assert payload["source_url"] == URL
    assert payload["provider_source_url"] == short
    assert payload["acquisition_provider"] == "qiyun"


def test_upload_only_mode_rejects_source_only_without_creating_task(client, settings, probe):
    csrf = login_and_change_password(client)
    object.__setattr__(settings, "case_acquisition_provider", "upload_only")
    assert client.get("/api/capabilities").json()["case_analysis"]["upload_required"] is True
    response = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "mix",
    })
    assert response.status_code == 422
    assert client.get("/api/tasks").json()["tasks"] == []
    receipt = upload(client, csrf).json()
    accepted = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "mix", "source_upload_id": receipt["upload_id"],
    })
    assert accepted.status_code == 200


@pytest.mark.parametrize("params", [{"rights_confirmed": False}, {"source_match_confirmed": False},
                                  {"suffix": "../../bad.mp4"}, {"suffix": ".m3u8"}])
def test_invalid_attestation_and_suffix_rejected_before_read(client, settings, probe, params):
    csrf = login_and_change_password(client)
    assert upload(client, csrf, **params).status_code == 422
    assert not probe
    assert not (settings.pipeline_root / "data" / "case_source_uploads").exists()


def test_auth_csrf_size_and_invalid_container_do_not_create_task(client, settings, probe, monkeypatch):
    assert upload(client, "invalid").status_code == 401
    csrf = login_and_change_password(client)
    assert upload(client, "invalid").status_code == 403
    monkeypatch.setattr(case_uploads, "MAX_BYTES", 2)
    assert upload(client, csrf).status_code == 413
    monkeypatch.setattr(case_uploads, "MAX_BYTES", 1024)
    def fail(*args):
        raise case_uploads.upload_error("Invalid container")
    monkeypatch.setattr(case_uploads, "probe_upload", fail)
    assert upload(client, csrf).status_code == 422
    assert not list((settings.pipeline_root / "data" / "case_source_uploads").glob("*/*.mp4"))
    assert client.get("/api/tasks").json()["tasks"] == []


@pytest.mark.parametrize("tamper", ["file", "owner", "expiry", "source"])
def test_upload_binding_fails_closed(client, settings, probe, tamper):
    csrf = login_and_change_password(client)
    upload_id = upload(client, csrf).json()["upload_id"]
    directory = case_uploads.upload_directory(settings.pipeline_root, upload_id)
    path = directory / case_uploads.RECEIPT
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if tamper == "file":
        (directory / receipt["filename"]).write_bytes(b"replaced")
    elif tamper == "owner":
        receipt["uploaded_by_user_id"] = 9999
    elif tamper == "source":
        receipt["source_url"] = URL + "0"
    else:
        receipt["uploaded_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    path.write_text(json.dumps(receipt), encoding="utf-8")
    result = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "mix", "source_upload_id": upload_id,
    })
    assert result.status_code == 422
    assert client.get("/api/tasks").json()["tasks"] == []


def test_orphan_expiry_and_failed_ttl_but_not_queued(client, settings, probe):
    csrf = login_and_change_password(client)
    first = upload(client, csrf).json()["upload_id"]
    first_dir = case_uploads.upload_directory(settings.pipeline_root, first)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).timestamp()
    os.utime(first_dir, (old, old))
    case_uploads.cleanup_unused_uploads(settings)
    assert not list(first_dir.glob("*.mp4"))
    second = upload(client, csrf).json()["upload_id"]
    second_dir = case_uploads.upload_directory(settings.pipeline_root, second)
    task = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "mix", "source_upload_id": second,
    }).json()["task"]
    os.utime(second_dir, (old, old))
    case_uploads.cleanup_unused_uploads(settings)
    assert list(second_dir.glob("*.mp4"))  # active queue is protected even after 24h
    update_task(settings.database_path, task["task_id"], status="failed", stage="failed")
    case_uploads.cleanup_unused_uploads(settings)
    assert list(second_dir.glob("*.mp4"))
    connection = case_uploads.connect(settings.database_path)
    connection.execute("UPDATE tasks SET updated_at = ? WHERE task_id = ?", (
        datetime.fromtimestamp(old, timezone.utc).isoformat(), task["task_id"]))
    connection.commit()
    connection.close()
    case_uploads.cleanup_unused_uploads(settings)
    assert not list(second_dir.glob("*.mp4"))
    assert (second_dir / case_uploads.RECEIPT).exists()


def test_review_reanalysis_validates_upload_before_any_review_mutation(client, settings, probe, monkeypatch):
    from app import main
    csrf = login_and_change_password(client)
    upload_id = upload(client, csrf).json()["upload_id"]
    decisions = []
    monkeypatch.setattr(main, "get_case_detail", lambda *a: {"source_url": URL, "operator_profile_hint": "news"})
    monkeypatch.setattr(main, "record_case_review_decision", lambda *a, **kw: decisions.append(kw) or {})
    response = client.post(f"/api/cases/{CASE_ID}/review", headers={"X-CSRF-Token": csrf}, json={
        "decision": "reanalyze", "reason": "New authorized source file", "source_upload_id": upload_id,
    })
    assert response.status_code == 200, response.text
    assert response.json()["task"]["payload"]["source_upload"]["upload_id"] == upload_id
    assert len(decisions) == 1
    repeated = client.post(f"/api/cases/{CASE_ID}/review", headers={"X-CSRF-Token": csrf}, json={
        "decision": "reanalyze", "reason": "Repeated", "source_upload_id": upload_id,
    })
    assert repeated.status_code == 422
    assert len(decisions) == 1


def test_reanalysis_missing_provider_credentials_does_not_mutate_review(client, settings, monkeypatch):
    from app import main
    csrf = login_and_change_password(client)
    object.__setattr__(settings, "case_acquisition_provider", "qiyun")
    monkeypatch.delenv("QYAPI_APP_ID", raising=False)
    monkeypatch.delenv("QYAPI_APP_KEY", raising=False)
    monkeypatch.setattr(main, "get_case_detail", lambda *a: {
        "source_url": URL, "operator_profile_hint": "news", "review_media": {},
    })
    decisions = []
    monkeypatch.setattr(main, "record_case_review_decision", lambda *a, **kw: decisions.append(kw))
    response = client.post(f"/api/cases/{CASE_ID}/review", headers={"X-CSRF-Token": csrf}, json={
        "decision": "reanalyze", "reason": "重新分析",
    })
    assert response.status_code == 503
    assert decisions == []
    assert client.get("/api/tasks").json()["tasks"] == []


def test_uploads_excluded_from_authority_backup():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "backup_local_node_v1.py"
    spec = importlib.util.spec_from_file_location("backup_upload_test", path)
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)
    assert backup._excluded(Path("case_source_uploads") / ("a" * 32) / "source.mp4")
    assert backup._excluded(Path("case_analysis_attempts/case/attempt/source_media/source.mp4.part"))
    assert backup._excluded(Path(".provider_rate/qiyun_last_call"))
    assert not backup._excluded(Path("case_analysis_attempts/case/attempt/source_metadata_v1.json"))
