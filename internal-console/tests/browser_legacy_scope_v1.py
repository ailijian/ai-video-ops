"""Fresh synthetic ASGI node for CS-LEGACY-SCOPE-1; no live authority or models."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import shutil
import socket
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "internal-console"))
sys.path.insert(0, str(REPO / "internal-console/tests"))
sys.path.insert(0, str(REPO / "ops-pipeline/scripts"))
from app.main import build_app
from app.auth_service import provision_user
from app.case_library_access import principal
from conftest import settings as fixture_settings
from legacy_scope_fixture import seed, BID
from legacy_constraint_scope_v1 import manage_reviewer
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn

PHONES = ("19900001601", "19900001602")
PASSWORD = "ScopeGolden2026!"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18031)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(); root = args.workdir.resolve()
    project = next(p for p in REPO.parents if (p / ".git").is_dir())
    assert root.is_relative_to(project / ".local") or root.is_relative_to(project / ".verify")
    assert args.port != 8000
    original_connect = socket.socket.connect
    def local_only(sock, address):
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise RuntimeError("Synthetic node forbids external model/media transport")
        return original_connect(sock, address)
    socket.socket.connect = local_only
    if not args.resume:
        assert not root.exists(), "Fresh root required"
        root.mkdir(parents=True)
        settings = fixture_settings.__wrapped__(root)
    else:
        manifest = json.loads((root / "manifest.json").read_text())
        assert manifest["fixture_only"] and manifest["source_worktree"] == str(REPO)
        from app.config import Settings
        settings = Settings(repo_root=REPO, console_root=REPO / "internal-console", pipeline_root=root / "ops-pipeline",
            database_path=root / "console.sqlite3", python_executable=sys.executable)
        shutil.copytree(REPO / "ops-pipeline/scripts", settings.pipeline_root / "scripts", dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    settings = replace(settings, pipeline_python_executable=str(REPO / "ops-pipeline/.venv/Scripts/python.exe"),
        case_analysis_worker_enabled=False, customer_analysis_worker_enabled=False, speaker_analysis_worker_enabled=False,
        background_worker_enabled=False, default_business_id=None, session_cookie_name="aivo_scope_isolated")
    if not args.resume:
        with TestClient(build_app(settings)) as client:
            for phone in PHONES:
                provision_user(settings.database_path, phone)
                response = client.post("/api/auth/login", json={"phone":phone, "password":"123456"}); assert response.status_code == 200
                changed = client.post("/api/auth/change-password", headers={"X-CSRF-Token":response.json()["csrf_token"]},
                    json={"current_password":"123456", "new_password":PASSWORD, "confirm_password":PASSWORD}); assert changed.status_code == 200
            seed(settings.pipeline_root)
            manage_reviewer(settings.pipeline_root, principal(settings, 1), action="grant",
                operator="isolated-founder-fixture", reason="Explicit fictional scope reviewer; never a production grant")
        (root / "manifest.json").write_text(json.dumps({"fixture_only":True,"source_worktree":str(REPO),"business_id":BID,
            "database":str(settings.database_path),"canonical_root":str(settings.pipeline_root),"accounts":PHONES,
            "port":args.port,"model_calls":0,"production_data_copied":False}, indent=2), encoding="utf-8")
    app = build_app(settings)
    @app.middleware("http")
    async def evidence(request, call_next):
        started = time.perf_counter()
        if request.method == "GET" and request.url.path.endswith("/legacy-scope") and (root / "scope-read-failure.flag").exists():
            response = JSONResponse({"detail":"Synthetic read outage"},status_code=503)
        else:
            response = await call_next(request)
        if request.url.path == "/login" or (not request.url.path.startswith(("/api/", "/assets/")) and request.method == "GET"):
            if response.headers.get("content-type", "").startswith("text/html"):
                body = b"".join([chunk async for chunk in response.body_iterator]).decode()
                body = body.replace("</body>", '<aside style="position:fixed;right:8px;top:8px;font-size:11px;z-index:20;color:#53685e;pointer-events:none">隔离验收 · 全部虚构资料</aside></body>')
                response = HTMLResponse(body, headers={k:v for k,v in response.headers.items() if k.lower() not in {"content-length", "content-type"}})
        with (root / "http-trace.jsonl").open("a",encoding="utf-8") as stream:
            stream.write(json.dumps({"method":request.method,"path":request.url.path,"status":response.status_code,
                "elapsed_ms":round((time.perf_counter()-started)*1000,2)})+"\n")
        return response
    print(json.dumps({"fixture_only":True,"url":f"http://127.0.0.1:{args.port}","canonical_root":str(settings.pipeline_root)}),flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1, access_log=False)


if __name__ == "__main__":
    main()
