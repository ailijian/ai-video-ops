"""Historical industry labels are separate from immutable approved Case facts."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from conftest import login_and_change_password


CASE_ID = "7999999999999999901"
URL = f"/api/cases/{CASE_ID}/industry-annotation"


def paths(settings):
    root = settings.pipeline_root / "data"
    return (
        root / "cases" / CASE_ID / "case_v1.json",
        root / "cases" / CASE_ID / "approval_receipt.json",
        root / "fingerprints" / CASE_ID / "case_fingerprint_v1.json",
        root / "case_governance" / "cases" / CASE_ID / "case_industry_annotation_v1.json",
    )


def make_legacy_industry_case(settings):
    case_path, receipt_path, *_ = paths(settings)
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["identity"]["industry"] = "待分类"
    case_path.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(case_path.read_bytes()).hexdigest()
    for key in ("case_sha256", "case_sha256_after_approval"):
        if key in receipt:
            receipt[key] = digest
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")


def body(client, industry="餐饮"):
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    return {
        "industry": industry,
        "approved_case_sha256": detail["approved_case_sha256"],
        "expected_annotation_sha256": detail["industry_annotation_sha256"],
        "note": "人工对照原视频补充",
    }


def test_legacy_industry_annotation_is_attributed_and_does_not_edit_approved_artifacts(client, settings):
    make_legacy_industry_case(settings)
    case_path, receipt_path, fingerprint_path, annotation_path = paths(settings)
    before = {path: path.read_bytes() for path in (case_path, receipt_path, fingerprint_path)}
    case_sha = hashlib.sha256(before[case_path]).hexdigest()
    csrf = login_and_change_password(client)
    request = body(client)
    assert not annotation_path.exists(), "reading must not backfill an annotation"
    response = client.post(URL, headers={"X-CSRF-Token": csrf}, json={
        **request,
        "annotated_by_user_id": 999,
        "annotated_by_phone": "forged",
        "authority": {"annotation_changes_matching": True},
    })
    assert response.status_code == 200, response.text
    detail = response.json()["case"]
    saved = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert saved == detail["industry_annotation"]
    assert saved["case_id"] == CASE_ID
    assert saved["approved_case_sha256"] == case_sha
    assert saved["industry"] == "餐饮"
    assert saved["annotated_by_user_id"] != 999
    assert saved["annotated_by_phone"] == "13800000000"
    assert saved["annotated_at"]
    assert saved["note"] == "人工对照原视频补充"
    assert saved["authority"] == {
        "annotation_is_operator_label": True,
        "annotation_changes_case_industry": False,
        "annotation_changes_matching": False,
        "approved_case_modified": False,
        "fingerprint_modified": False,
    }
    assert detail["industry"] == "待分类"
    listed = next(item for item in client.get("/api/cases").json()["cases"] if item["case_id"] == CASE_ID)
    assert listed["industry"] == "待分类"
    assert listed["industry_annotation"] == saved
    for path, original in before.items():
        assert path.read_bytes() == original
    assert hashlib.sha256(case_path.read_bytes()).hexdigest() == case_sha


def test_known_industry_is_primary_and_cannot_be_overridden(client, settings):
    csrf = login_and_change_password(client)
    detail = client.get(f"/api/cases/{CASE_ID}").json()
    assert detail["industry"] == "餐饮"
    assert detail["industry_annotation"] is None
    assert detail["can_annotate_industry"] is False
    response = client.post(URL, headers={"X-CSRF-Token": csrf}, json={
        "industry": "零售", "approved_case_sha256": "0" * 64,
        "expected_annotation_sha256": None,
    })
    assert response.status_code == 409
    assert not paths(settings)[3].exists()


def test_industry_annotation_requires_fresh_version(client, settings):
    make_legacy_industry_case(settings)
    csrf = login_and_change_password(client)
    request = body(client)
    assert client.post(URL, headers={"X-CSRF-Token": csrf}, json=request).status_code == 200
    annotation_path = paths(settings)[3]
    before = annotation_path.read_bytes()
    stale = client.post(URL, headers={"X-CSRF-Token": csrf}, json={**request, "industry": "零售"})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "AUTHORITY_CHANGED_REFRESH_REQUIRED"
    assert annotation_path.read_bytes() == before
    updated = client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client, "零售"))
    assert updated.status_code == 200
    assert updated.json()["case"]["industry_annotation"]["industry"] == "零售"


def test_simultaneous_industry_updates_do_not_silently_overwrite(client, settings):
    make_legacy_industry_case(settings)
    csrf = login_and_change_password(client)
    request = body(client)
    barrier = Barrier(2)

    def submit(industry):
        barrier.wait(timeout=10)
        return client.post(URL, headers={"X-CSRF-Token": csrf}, json={**request, "industry": industry})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["餐饮", "零售"]))
    assert sorted(result.status_code for result in results) == [200, 409]


def test_industry_annotation_rejects_invalid_approval_binding(client, settings):
    make_legacy_industry_case(settings)
    csrf = login_and_change_password(client)
    request = body(client)
    receipt_path = paths(settings)[1]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["case_sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    response = client.post(URL, headers={"X-CSRF-Token": csrf}, json=request)
    assert response.status_code in {409, 503}
    assert not paths(settings)[3].exists()


def test_industry_annotation_requires_auth_csrf_and_specific_label(client, settings):
    make_legacy_industry_case(settings)
    assert client.post(URL, json={
        "industry": "餐饮", "approved_case_sha256": "0" * 64,
        "expected_annotation_sha256": None,
    }).status_code == 401
    csrf = login_and_change_password(client)
    assert client.post(URL, json=body(client)).status_code == 403
    for invalid in (" ", "待分类", "unknown"):
        response = client.post(URL, headers={"X-CSRF-Token": csrf}, json=body(client, invalid))
        assert response.status_code in {409, 422}
    bad_id = client.post(
        "/api/cases/not-a-case/industry-annotation",
        headers={"X-CSRF-Token": csrf}, json=body(client),
    )
    assert bad_id.status_code == 409
    assert bad_id.json()["detail"]["code"] == "CASE_INDUSTRY_ANNOTATION_BLOCKED"
    assert not paths(settings)[3].exists()
