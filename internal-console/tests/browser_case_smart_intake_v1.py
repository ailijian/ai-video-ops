"""Full ASGI acceptance node: real auth/CSRF/static/API, isolated DB and fixtures.

Replaces the V1.0 pre-authenticated HTTP bridge. Never uses runtime Authority,
GPU, Qiyun or a model. A serial test-only fixture driver supplies recorded
analysis evidence; this is not Production/model validation or a new pipeline.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
from dataclasses import replace
from contextlib import closing
from pathlib import Path

for key in list(os.environ):
    if key.startswith(("AIVO_", "QYAPI_", "DEEPSEEK_")):
        os.environ.pop(key)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi.testclient import TestClient
from app.auth_service import provision_user
from app.main import build_app
from app.task_service import (CaseTaskRunner, claim_task, get_task, iter_queued_tasks,
                              recover_expired_tasks, update_task)
from conftest import settings as settings_fixture
from test_case_smart_intake_v1 import candidate, evidence_case

PHONES = ("19900001101", "19900001102")
PASSWORD = "OfflineReview2026!"
PREFIX = "79999999999999997"


def run_fixture_driver(settings, application, root, stop, delay):
    """Existing task claim/recovery/admission, with synthetic evidence only."""
    runner = CaseTaskRunner(settings)
    events = root / "task-events.jsonl"

    def record(task, event):
        with events.open("a", encoding="utf-8") as output:
            output.write(json.dumps({"time": time.time(), "task_id": task["task_id"],
                                     "case_id": task["subject_ref"], "event": event}) + "\n")

    try:
        while not stop.wait(0.3):
            # Source backup must be idle. Only fixture tasks can become running.
            recovered = recover_expired_tasks(settings.database_path, task_types=("case_analysis",),
                                               reconciler=runner._reconcile_business_state)
            for task_id in recovered:
                record(get_task(settings.database_path, task_id), "lease_recovered")
            application.state.intake_dispatch()
            tasks = [task for task in iter_queued_tasks(settings.database_path, task_types=("case_analysis",))
                     if str(task["subject_ref"]).startswith(PREFIX)]
            if not tasks:
                continue
            task = tasks[0]
            if not claim_task(settings.database_path, task["task_id"], worker_id="isolated-fixture-driver",
                              lease_seconds=10, stage="获取视频", task_type="case_analysis"):
                continue
            task = get_task(settings.database_path, task["task_id"])
            record(task, "claimed")
            checkpoint = root / "fixture-checkpoints" / task["task_id"]
            checkpoint.mkdir(parents=True, exist_ok=True)
            for stage in ("获取视频", "分析画面与语音", "推荐行业与视频结构"):
                mark = checkpoint / (str(("获取视频", "分析画面与语音", "推荐行业与视频结构").index(stage)) + ".done")
                if mark.exists():
                    record(task, "reused:" + stage)
                    continue
                update_task(settings.database_path, task["task_id"], status="running", stage=stage,
                            worker_id="isolated-fixture-driver", lease_seconds=10, heartbeat_interval_seconds=1)
                record(task, stage)
                if stop.wait(delay):
                    return
                first = task["attempt_count"] == 1
                failure = ((str(task["subject_ref"]).endswith("12") and stage == "获取视频")
                           or (str(task["subject_ref"]).endswith("16") and stage == "分析画面与语音"))
                if first and failure:
                    code = "SOURCE_ACQUISITION_FAILED" if stage == "获取视频" else "CASE_ANALYSIS_FAILED"
                    update_task(settings.database_path, task["task_id"], status="failed", error_code=code,
                                error_message="隔离验收：可恢复的模拟阶段失败", stage="解析失败")
                    record(task, code)
                    break
                mark.write_text("synthetic isolated fixture checkpoint", encoding="utf-8")
            else:
                case = evidence_case(task["subject_ref"])
                if str(task["subject_ref"]).endswith("20"):
                    case["storyboard"]["shots"] = []
                    case["storyboard"]["narration_track"] = []
                candidate(settings, task, case)
                record(task, "awaiting_review")
    finally:
        runner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--database-backup", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--port", type=int, default=18008)
    parser.add_argument("--stage-delay", type=float, default=2)
    args = parser.parse_args()
    root = args.workdir.resolve()
    repo = Path(__file__).resolve().parents[2]
    if root.is_relative_to(repo) or args.port == 8000 or args.stage_delay <= 0:
        parser.error("Use an outside-repository fixture directory and port; delay must be positive.")
    manifest_path = root / "browser_manifest.json"
    if args.resume:
        if not manifest_path.is_file() or not json.loads(manifest_path.read_text())["fixture_only"]:
            parser.error("Resume requires an existing fixture manifest")
        from app.config import Settings
        settings = Settings(repo_root=repo, console_root=repo / "internal-console", pipeline_root=root / "ops-pipeline",
                            database_path=root / "console.sqlite3", python_executable=sys.executable,
                            session_cookie_name="aivo_v11_fixture", secure_cookies=False,
                            case_analysis_worker_enabled=False, customer_analysis_worker_enabled=False,
                            speaker_analysis_worker_enabled=False, background_worker_enabled=False)
    else:
        if root.exists():
            parser.error("Use a new directory, or --resume for this fixture only")
        root.mkdir(parents=True)
        settings = settings_fixture.__wrapped__(root)
        if args.database_backup:
            backup = args.database_backup.resolve()
            if backup.is_relative_to(repo):
                parser.error("Use an audited backup outside the repository")
            with closing(sqlite3.connect(backup.as_uri() + "?mode=ro", uri=True)) as source:
                if source.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('queued','running')").fetchone()[0]:
                    parser.error("The backup must be from an idle queue")
                with closing(sqlite3.connect(settings.database_path)) as destination:
                    source.backup(destination)
        settings = replace(settings, session_cookie_name="aivo_v11_fixture", default_business_id=None,
                           background_worker_enabled=False)
        # Fixture account setup through real auth APIs, before the listener.
        with TestClient(build_app(settings)) as client:
            for phone in PHONES:
                provision_user(settings.database_path, phone)
                login = client.post("/api/auth/login", json={"phone": phone, "password": "123456"})
                csrf = login.json()["csrf_token"]
                changed = client.post("/api/auth/change-password", headers={"X-CSRF-Token": csrf}, json={
                    "current_password": "123456", "new_password": PASSWORD, "confirm_password": PASSWORD})
                assert changed.status_code == 200
        manifest = {"fixture_only": True, "mode": "full ASGI application; real cookies/login/CSRF",
                    "workers_enabled": False, "fixture_driver": "serial; no network/model/GPU",
                    "url": f"http://127.0.0.1:{args.port}/cases/new", "phones": PHONES,
                    "database": str(settings.database_path), "pipeline_root": str(settings.pipeline_root)}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    application = build_app(settings)
    server = uvicorn.Server(uvicorn.Config(application, host="127.0.0.1", port=args.port, workers=1,
                                           access_log=False, log_level="warning"))
    stop = threading.Event()

    def driver():
        while not server.started and not stop.wait(0.1):
            pass
        if not stop.is_set():
            run_fixture_driver(settings, application, root, stop, args.stage_delay)

    thread = threading.Thread(target=driver, name="isolated-fixture-evidence", daemon=True)
    thread.start()
    print(json.dumps({"fixture_only": True, "url": f"http://127.0.0.1:{args.port}", "workdir": str(root)}), flush=True)
    try:
        server.run()
    finally:
        stop.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
