"""Isolated fixtures only: a historical operator hint must not edit Authority."""
from __future__ import annotations

import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from app.canonical_gateway import get_case_detail
from app.operation_lock import authority_operation_lock
from conftest import login_and_change_password


CASE_ID = "7999999999999999901"
URL = f"/api/cases/{CASE_ID}/profile-annotation"


def paths(settings):
    root = settings.pipeline_root / "data"
    return (
        root / "cases" / CASE_ID / "case_v1.json",
        root / "cases" / CASE_ID / "approval_receipt.json",
        root / "fingerprints" / CASE_ID / "case_fingerprint_v1.json",
        root / "case_governance" / "cases" / CASE_ID / "case_source_governance_companion_v1.json",
    )


def annotation_path(settings):
    return paths(settings)[3].with_name("case_profile_annotation_v1.json")


def body(client, hint="news"):
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    return {
        "operator_profile_hint": hint,
        "approved_case_sha256": detail["approved_case_sha256"],
        "expected_annotation_sha256": detail["profile_annotation_sha256"],
        "note": "人工对照原视频补充",
    }


def write_fixture_case(settings, **values):
    case_path, receipt_path, *_ = paths(settings)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case.update(values)
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["case_sha256"] = hashlib.sha256(case_path.read_bytes()).hexdigest()
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")


@pytest.mark.parametrize("hint", ["mix", "news", "hybrid", "uncertain"])
def test_legacy_annotation_preserves_all_approved_artifacts_and_attribution(client, settings, hint):
    before = {path: path.read_bytes() for path in paths(settings)}
    case_sha = hashlib.sha256(before[paths(settings)[0]]).hexdigest()
    csrf = login_and_change_password(client)
    response = client.post(URL, headers={"X-CSRF-Token": csrf}, json={
        **body(client, hint),
        "annotated_by_user_id": 999,
        "annotated_by_phone": "forged",
        "annotated_at": "forged",
        "authority": {"annotation_grants_profile_compatibility": True},
        "compatible_generation_profiles": ["news"],
    })
    assert response.status_code == 200, response.text
    result = response.json()["case"]
    saved = json.loads(annotation_path(settings).read_text(encoding="utf-8"))
    assert saved == result["profile_annotation"]
    assert saved["case_id"] == CASE_ID
    assert saved["approved_case_sha256"] == case_sha
    assert saved["operator_profile_hint"] == hint
    account = client.get("/api/tasks/activity").json()["accounts"][0]
    assert saved["annotated_by_user_id"] == account["user_id"]
    assert saved["annotated_by_phone"] == "13800000000"
    assert saved["annotated_at"] != "forged"
    assert saved["note"] == "人工对照原视频补充"
    assert saved["authority"] == {
        "annotation_is_operator_hint": True,
        "annotation_grants_profile_compatibility": False,
        "approved_case_modified": False,
    }
    assert "compatible_generation_profiles" not in saved
    assert result["operator_profile_hint"] is None
    assert get_case_detail(settings, CASE_ID)["profile_annotation"] == saved
    listed = next(item for item in client.get("/api/cases").json()["cases"] if item["case_id"] == CASE_ID)
    assert listed["profile_annotation"] == saved
    assert result["media_rights"]["production_authorized"] is False
    for path, original in before.items():
        assert path.read_bytes() == original  # Case / receipt / fingerprint / governance
    assert hashlib.sha256(paths(settings)[0].read_bytes()).hexdigest() == case_sha


def test_read_never_backfills_or_copies_system_observation(client, settings):
    write_fixture_case(settings, profile_analysis={"observed_source_profile": "news"})
    login_and_change_password(client)
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    assert detail["observed_source_profile"] == "news"
    assert detail["operator_profile_hint"] is None
    assert detail["profile_annotation"] is None
    assert detail["can_annotate_profile"] is True
    client.get("/api/cases")
    assert not annotation_path(settings).exists()


def test_new_submission_hint_cannot_be_overridden_even_by_existing_annotation(client, settings):
    csrf = login_and_change_password(client)
    request = body(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=request).status_code == 200
    write_fixture_case(settings, operator_profile_hint="mix", profile_analysis={"observed_source_profile": "hybrid"})
    before = {path: path.read_bytes() for path in (*paths(settings), annotation_path(settings))}
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    assert detail["operator_profile_hint"] == "mix"
    assert detail["observed_source_profile"] == "hybrid"
    assert detail["profile_annotation"] is None
    assert detail["can_annotate_profile"] is False
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=request).status_code == 409
    for path, original in before.items():
        assert path.read_bytes() == original


def test_annotation_update_requires_fresh_version(client, settings):
    csrf = login_and_change_password(client)
    first = body(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=first).status_code == 200
    before = annotation_path(settings).read_bytes()
    stale = client.post(URL, headers={"X-CSRF-Token": csrf}, json={**first, "operator_profile_hint": "mix"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "AUTHORITY_CHANGED_REFRESH_REQUIRED"
    assert annotation_path(settings).read_bytes() == before
    updated = client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client, "hybrid"))
    assert updated.status_code == 200
    assert updated.json()["case"]["profile_annotation"]["operator_profile_hint"] == "hybrid"


def test_annotation_projection_hash_matches_the_exact_bytes_read(client, settings, monkeypatch):
    csrf = login_and_change_password(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client)).status_code == 200
    target = annotation_path(settings)
    original = target.read_bytes()
    replacement = json.loads(original)
    replacement["operator_profile_hint"] = "mix"
    read_bytes = Path.read_bytes

    def concurrent_replace(path):
        value = read_bytes(path)
        if path == target:
            target.write_text(json.dumps(replacement), encoding="utf-8")
        return value

    monkeypatch.setattr(Path, "read_bytes", concurrent_replace)
    detail = get_case_detail(settings, CASE_ID)
    assert detail["profile_annotation"]["operator_profile_hint"] == "news"
    assert detail["profile_annotation_sha256"] == hashlib.sha256(original).hexdigest()


def test_two_simultaneous_annotations_do_not_silently_overwrite(client):
    csrf = login_and_change_password(client)
    request = body(client)
    barrier = Barrier(2)

    def submit(hint):
        barrier.wait(timeout=10)
        return client.post(URL, headers={"X-CSRF-Token": csrf}, json={**request, "operator_profile_hint": hint})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["news", "mix"]))
    assert sorted(result.status_code for result in results) == [200, 409]
    winner = next(result.json()["case"]["profile_annotation"] for result in results if result.status_code == 200)
    assert client.get(f"/api/cases/{CASE_ID}").json()["profile_annotation"] == winner


def test_annotation_shares_case_lock_with_approval(client, settings):
    csrf = login_and_change_password(client)
    request = body(client)
    with authority_operation_lock(settings, "case", CASE_ID):
        result = client.post(URL, headers={"X-CSRF-Token": csrf}, json=request)
    assert result.status_code == 409
    assert result.json()["detail"]["code"] == "OPERATION_IN_PROGRESS"
    assert not annotation_path(settings).exists()


@pytest.mark.parametrize("invalid", ["stale_sha", "receipt_sha", "not_approved", "missing_receipt"])
def test_annotation_fails_closed_on_invalid_approval_binding(client, settings, invalid):
    csrf = login_and_change_password(client)
    request = body(client)
    case_path, receipt_path, *_ = paths(settings)
    if invalid == "stale_sha":
        request["approved_case_sha256"] = "0" * 64
    elif invalid == "receipt_sha":
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["case_sha256"] = "0" * 64
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    elif invalid == "not_approved":
        write_fixture_case(settings, lifecycle={"status": "review_required", "approved": False})
    else:
        receipt_path.unlink()
    before = case_path.read_bytes()
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=request).status_code in {409, 503}
    assert not annotation_path(settings).exists()
    assert case_path.read_bytes() == before


def test_current_receipt_hash_field_is_supported(client, settings):
    receipt_path = paths(settings)[1]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["case_sha256_after_approval"] = receipt.pop("case_sha256")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    csrf = login_and_change_password(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client)).status_code == 200


def test_real_profile_compatibility_consumer_ignores_annotation(client, settings, tmp_path):
    from production_profile_v1 import audit_case_profile_compatibility_v1

    case_path, receipt_path, fingerprint_path, *_ = paths(settings)
    digest = hashlib.sha256(case_path.read_bytes()).hexdigest()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["case_sha256_after_approval"] = receipt.pop("case_sha256")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    fingerprint_path.write_text(json.dumps({
        "case_id": CASE_ID,
        "source_case": {"sha256": digest},
        "narration_features": {"speech_to_video_ratio": 0.8},
        "visual_shot_features": {"shot_count": 10},
        "audio_visual_features": {
            "narration_and_shots_are_separate_tracks": True,
            "shot_to_narration_cardinality": "many_to_many",
        },
    }), encoding="utf-8")
    storyboard = tmp_path / "reverse_storyboard_v1.json"
    storyboard.write_text(json.dumps({"case_id": CASE_ID}), encoding="utf-8")

    def assess():
        return audit_case_profile_compatibility_v1(
            case_path=case_path, case_approval_receipt_path=receipt_path,
            fingerprint_path=fingerprint_path, storyboard_path=storyboard,
            legacy_mix_case_ids=set(),
        )

    before = assess()
    csrf = login_and_change_password(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client, "news")).status_code == 200
    after = assess()
    assert before["approved_compatible_generation_profiles"] == after["approved_compatible_generation_profiles"] == []
    assert before["observed_source_profile"] == after["observed_source_profile"] == "mix"
    assert after["operator_profile_hint"] is None
    assert after["authority"]["operator_hint_used_as_eligibility"] is False


def test_annotation_read_rejects_wrong_sha_and_compatibility_grant(client, settings):
    csrf = login_and_change_password(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client)).status_code == 200
    saved = json.loads(annotation_path(settings).read_text(encoding="utf-8"))
    for corrupt in (
        {**saved, "approved_case_sha256": "0" * 64},
        {**saved, "authority": {**saved["authority"], "annotation_grants_profile_compatibility": True}},
    ):
        annotation_path(settings).write_text(json.dumps(corrupt), encoding="utf-8")
        assert client.get(f"/api/cases/{CASE_ID}").status_code == 409
        assert client.get("/api/cases").status_code == 409


def test_annotation_requires_auth_csrf_and_valid_hint(client, settings):
    payload = {"operator_profile_hint": "news", "approved_case_sha256": "0" * 64, "expected_annotation_sha256": None}
    assert client.post(URL, json=payload).status_code == 401
    csrf = login_and_change_password(client)
    assert client.post(URL, json=body(client)).status_code == 403
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json={**body(client), "operator_profile_hint": "invalid"}).status_code == 422
    assert client.post("/api/cases/not-a-case/profile-annotation", headers={"X-CSRF-Token": csrf}, json=payload).status_code == 409
    assert not annotation_path(settings).exists()


def test_annotation_js_projection_and_flow():
    script = Path(__file__).parent / "js" / "case-profile-annotation.test.mjs"
    result = subprocess.run(["node", str(script)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr or result.stdout
