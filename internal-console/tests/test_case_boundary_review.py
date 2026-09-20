import hashlib
import json
from pathlib import Path

from app.task_service import update_task
from conftest import login_and_change_password


CASE_ID = "7999999999999999811"
URL = f"https://www.douyin.com/video/{CASE_ID}"


def seed_pending_review(client, settings, csrf):
    response = client.post("/api/cases/analyze", headers={"X-CSRF-Token": csrf}, json={
        "url": URL, "operator_profile_hint": "hybrid",
    })
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    root = settings.pipeline_root / "data" / "case_analysis_attempts" / CASE_ID / task["task_id"]
    shots_dir = root / "evidence" / "shots"
    shots_dir.mkdir(parents=True)
    media = root / "source_media" / "source.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"fixture-media")
    (root / "source_acquisition_v1.json").write_text(json.dumps({
        "video": str(media), "source_video_sha256": hashlib.sha256(media.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    (root / "case_analysis_attempt_v1.json").write_text(json.dumps({
        "case_id": CASE_ID, "attempt_id": task["task_id"], "status": "failed",
        "source": {"canonical_url": URL},
    }), encoding="utf-8")
    shots = shots_dir / "shot_boundaries_v1_1.json"
    shots.write_text(json.dumps({
        "case_id": CASE_ID, "validation": {"passed": True},
        "manual_review": {"required": True, "items": [
            {"type": "short_shot", "boundary_frame_id": "frame_000003000ms.jpg", "start": 3, "end": 3.3},
            {"type": "short_shot", "boundary_frame_id": "frame_000008000ms.jpg", "start": 8, "end": 8.4},
        ]},
    }), encoding="utf-8")
    update_task(settings.database_path, task["task_id"], status="failed", progress=90, error_code="PIPELINE_STAGE_FAILED")
    return task["task_id"], shots_dir, hashlib.sha256(shots.read_bytes()).hexdigest()


def test_human_boundary_review_resumes_same_attempt_without_changing_shots(client, settings):
    csrf = login_and_change_password(client)
    task_id, shots_dir, sha = seed_pending_review(client, settings, csrf)
    shots_before = (shots_dir / "shot_boundaries_v1_1.json").read_bytes()
    detail = client.get(f"/api/tasks/{task_id}")
    assert detail.status_code == 200
    review = detail.json()["boundary_review"]
    assert review["shot_sha256"] == sha
    assert len(review["items"]) == 2
    decisions = [
        {"frame_id": "frame_000003000ms.jpg", "action": "reject"},
        {"frame_id": "frame_000008000ms.jpg", "action": "keep"},
    ]
    response = client.post(f"/api/tasks/{task_id}/boundary-review", headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": decisions,
    })
    assert response.status_code == 200, response.text
    assert response.json()["task"]["status"] == "queued"
    receipt = json.loads((shots_dir / "boundary_review_001.json").read_text(encoding="utf-8"))
    assert receipt["decisions"] == [
        {**decisions[0], "reason": "人工对照原视频确认合并分镜"},
        {**decisions[1], "reason": "人工对照原视频确认保留分镜"},
    ]
    assert receipt["reviewed_by_user_id"] > 0
    assert receipt["reviewed_by_phone"] == "13800000000"
    assert (shots_dir / "shot_boundaries_v1_1.json").read_bytes() == shots_before


def test_boundary_review_fails_closed_on_stale_hash_or_incomplete_decisions(client, settings):
    csrf = login_and_change_password(client)
    task_id, shots_dir, sha = seed_pending_review(client, settings, csrf)
    endpoint = f"/api/tasks/{task_id}/boundary-review"
    one = [{"frame_id": "frame_000003000ms.jpg", "action": "keep"}]
    assert client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": "0" * 64, "decisions": one,
    }).status_code == 409
    assert client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": one,
    }).status_code == 409
    assert list(shots_dir.glob("boundary_review_*.json")) == []
    assert client.get(f"/api/tasks/{task_id}").json()["task"]["status"] == "failed"


def test_boundary_review_requires_auth_and_csrf(client, settings):
    csrf = login_and_change_password(client)
    task_id, shots_dir, sha = seed_pending_review(client, settings, csrf)
    response = client.post(f"/api/tasks/{task_id}/boundary-review", json={
        "shot_sha256": sha,
        "decisions": [{"frame_id": "frame_000003000ms.jpg", "action": "keep"}],
    })
    assert response.status_code in {401, 403}
    assert list(shots_dir.glob("boundary_review_*.json")) == []


def test_second_review_round_keeps_prior_receipt_and_decisions(client, settings):
    csrf = login_and_change_password(client)
    task_id, shots_dir, sha = seed_pending_review(client, settings, csrf)
    endpoint = f"/api/tasks/{task_id}/boundary-review"
    first_decisions = [
        {"frame_id": "frame_000003000ms.jpg", "action": "reject"},
        {"frame_id": "frame_000008000ms.jpg", "action": "keep"},
    ]
    assert client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": first_decisions,
    }).status_code == 200
    receipt_before = (shots_dir / "boundary_review_001.json").read_bytes()
    update_task(settings.database_path, task_id, status="failed", progress=84, error_code="SHOT_BOUNDARY_REVIEW_REQUIRED")
    shots = shots_dir / "shot_boundaries_v1_1.json"
    shots.write_text(json.dumps({
        "case_id": CASE_ID, "validation": {"passed": True},
        "manual_review": {"required": True, "items": [
            {"type": "short_shot", "boundary_frame_id": "frame_000010000ms.jpg", "start": 10, "end": 10.3},
        ]},
    }), encoding="utf-8")
    second_sha = hashlib.sha256(shots.read_bytes()).hexdigest()
    response = client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": second_sha,
        "decisions": [{"frame_id": "frame_000010000ms.jpg", "action": "reject"}],
    })
    assert response.status_code == 200, response.text
    assert (shots_dir / "boundary_review_001.json").read_bytes() == receipt_before
    latest = json.loads((shots_dir / "boundary_review_002.json").read_text(encoding="utf-8"))
    assert [item["frame_id"] for item in latest["decisions"]] == [
        "frame_000003000ms.jpg", "frame_000008000ms.jpg", "frame_000010000ms.jpg",
    ]


def test_review_correction_preserves_old_receipt_and_rejects_ineffective_repeat(client, settings):
    csrf = login_and_change_password(client)
    task_id, shots_dir, sha = seed_pending_review(client, settings, csrf)
    endpoint = f"/api/tasks/{task_id}/boundary-review"
    first = [
        {"frame_id": "frame_000003000ms.jpg", "action": "reject"},
        {"frame_id": "frame_000008000ms.jpg", "action": "keep"},
    ]
    assert client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": first,
    }).status_code == 200
    prior = (shots_dir / "boundary_review_001.json").read_bytes()
    update_task(settings.database_path, task_id, status="failed", error_code="SHOT_BOUNDARY_REVIEW_REQUIRED")
    repeated = client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": first,
    })
    assert repeated.status_code == 409
    assert not (shots_dir / "boundary_review_002.json").exists()
    corrected = [dict(first[0], action="keep"), first[1]]
    response = client.post(endpoint, headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": corrected,
    })
    assert response.status_code == 200, response.text
    assert (shots_dir / "boundary_review_001.json").read_bytes() == prior
    new = json.loads((shots_dir / "boundary_review_002.json").read_text(encoding="utf-8"))
    assert new["supersedes_review"] == "boundary_review_001.json"
    assert {item["frame_id"]: item["action"] for item in new["decisions"]} == {
        item["frame_id"]: item["action"] for item in corrected
    }


def test_review_never_rejects_mandatory_video_start(client, settings):
    csrf = login_and_change_password(client)
    task_id, shots_dir, _ = seed_pending_review(client, settings, csrf)
    shots = shots_dir / "shot_boundaries_v1_1.json"
    data = json.loads(shots.read_text(encoding="utf-8"))
    data["manual_review"]["items"] = [{
        "type": "short_shot", "boundary_frame_id": "frame_000000000ms.jpg",
        "start": 0, "end": 0.28, "merge_allowed": False,
    }]
    shots.write_text(json.dumps(data), encoding="utf-8")
    sha = hashlib.sha256(shots.read_bytes()).hexdigest()
    response = client.post(f"/api/tasks/{task_id}/boundary-review", headers={"X-CSRF-Token": csrf}, json={
        "shot_sha256": sha, "decisions": [{"frame_id": "frame_000000000ms.jpg", "action": "reject"}],
    })
    assert response.status_code == 409
    assert not list(shots_dir.glob("boundary_review_*.json"))
