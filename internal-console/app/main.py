from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth_service import (
    SessionContext,
    authenticate,
    change_password,
    create_session,
    delete_session,
    resolve_session,
)
from .canonical_gateway import (
    CanonicalOperationError,
    case_analysis_capability,
    find_duplicate_case,
    approve_case_candidate,
    case_media_path,
    get_case_detail,
    get_customer_status,
    list_cases,
    normalize_source_url,
    record_case_review_decision,
    source_case_id,
)
from .config import Settings
from .database import apply_migrations
from .task_service import (
    CaseTaskRunner,
    create_case_task,
    find_active_case_task,
    get_task,
    list_tasks,
    mark_task_reviewed,
)


class LoginRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class CaseAnalysisRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class CaseReviewRequest(BaseModel):
    decision: Literal["reject", "reanalyze", "approve"]
    reason: str = Field(default="", max_length=1000)


class LoginThrottle:
    def __init__(self, limit: int = 8, window_seconds: int = 300):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allowed(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            attempts = self._attempts[key]
            while attempts and now - attempts[0] > self.window_seconds:
                attempts.popleft()
            return len(attempts) < self.limit

    def failure(self, key: str) -> None:
        with self._lock:
            self._attempts[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def error_detail(code: str, message: str, next_action: str) -> dict[str, str]:
    return {"code": code, "message": message, "next_action": next_action}


def public_user(session: SessionContext) -> dict[str, Any]:
    return {
        "phone": session.user["phone"],
        "must_change_password": session.user["must_change_password"],
        "status": session.user["status"],
    }


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    throttle = LoginThrottle()
    migrations_path = settings.console_root / "migrations"
    static_path = settings.console_root / "static"
    index_path = static_path / "index.html"
    task_runner = CaseTaskRunner(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        apply_migrations(settings.database_path, migrations_path)
        task_runner.start()
        try:
            yield
        finally:
            task_runner.close()

    app = FastAPI(
        title="AI Video Ops Internal Console",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(CanonicalOperationError)
    async def canonical_error_handler(
        _: Request, exc: CanonicalOperationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": error_detail(exc.code, exc.message, exc.next_action)},
        )

    def require_session(request: Request) -> SessionContext:
        token = request.cookies.get(settings.session_cookie_name)
        session = resolve_session(settings.database_path, token)
        if session is None:
            raise HTTPException(
                status_code=401,
                detail=error_detail(
                    "AUTH_REQUIRED",
                    "登录状态已失效。",
                    "请重新登录后继续。",
                ),
            )
        return session

    def require_console_access(
        session: SessionContext = Depends(require_session),
    ) -> SessionContext:
        if session.user["must_change_password"]:
            raise HTTPException(
                status_code=403,
                detail=error_detail(
                    "PASSWORD_CHANGE_REQUIRED",
                    "首次登录必须先修改密码。",
                    "请设置新密码后进入工作台。",
                ),
            )
        return session

    def require_csrf(session: SessionContext, supplied: str | None) -> None:
        if not supplied or supplied != session.csrf_token:
            raise HTTPException(
                status_code=403,
                detail=error_detail(
                    "CSRF_CHECK_FAILED",
                    "本次操作的安全校验已失效。",
                    "请刷新页面后重试。",
                ),
            )

    def set_session_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            key=settings.session_cookie_name,
            value=token,
            max_age=settings.session_hours * 3600,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="strict",
            path="/",
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        client_host = request.client.host if request.client else "unknown"
        throttle_key = f"{client_host}:{payload.phone.strip()}"
        if not throttle.allowed(throttle_key):
            raise HTTPException(
                status_code=429,
                detail=error_detail(
                    "LOGIN_RATE_LIMITED",
                    "登录尝试过于频繁。",
                    "请稍后再试。",
                ),
            )
        user = authenticate(settings.database_path, payload.phone, payload.password)
        if user is None:
            throttle.failure(throttle_key)
            raise HTTPException(
                status_code=401,
                detail=error_detail(
                    "INVALID_CREDENTIALS",
                    "手机号或密码不正确。",
                    "请检查后重新输入。",
                ),
            )
        throttle.success(throttle_key)
        token, session = create_session(settings.database_path, user["id"], settings.session_hours)
        set_session_cookie(response, token)
        return {"user": public_user(session), "csrf_token": session.csrf_token}

    @app.get("/api/auth/me")
    def me(
        session: SessionContext = Depends(require_session),
    ) -> dict[str, Any]:
        return {"user": public_user(session), "csrf_token": session.csrf_token}

    @app.post("/api/auth/change-password")
    def update_password(
        payload: ChangePasswordRequest,
        response: Response,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_session),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        if payload.new_password != payload.confirm_password:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "PASSWORD_CONFIRMATION_MISMATCH",
                    "两次输入的新密码不一致。",
                    "请重新确认新密码。",
                ),
            )
        try:
            token, new_session = change_password(
                settings.database_path,
                session,
                payload.current_password,
                payload.new_password,
                settings.session_hours,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "PASSWORD_CHANGE_REJECTED",
                    str(exc),
                    "请修改输入后重试。",
                ),
            ) from exc
        set_session_cookie(response, token)
        return {"user": public_user(new_session), "csrf_token": new_session.csrf_token}

    @app.post("/api/auth/logout")
    def logout(
        response: Response,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_session),
    ) -> dict[str, bool]:
        require_csrf(session, x_csrf_token)
        delete_session(settings.database_path, session.token_hash)
        response.delete_cookie(
            settings.session_cookie_name,
            path="/",
            secure=settings.secure_cookies,
            httponly=True,
            samesite="strict",
        )
        return {"ok": True}

    @app.get("/api/status/current")
    def current_status(
        business_id: str | None = None,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return get_customer_status(settings, business_id or settings.default_business_id)

    @app.get("/api/workbench")
    def workbench(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        status = get_customer_status(settings, settings.default_business_id)
        cases = list_cases(settings)
        tasks = list_tasks(settings.database_path, limit=10)
        return {
            "status": status,
            "attention": {
                "case_reviews": sum(case["status"] == "awaiting_review" for case in cases),
                "persona_reviews": 0,
                "content_reviews": sum(
                    task["task_type"] == "content_generation"
                    and task["status"] == "awaiting_review"
                    for task in tasks
                ),
                "running_tasks": sum(task["status"] in {"queued", "running"} for task in tasks),
            },
            "recent_tasks": tasks[:5],
            "capabilities": {"case_analysis": case_analysis_capability()},
        }

    @app.get("/api/cases")
    def cases(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {"cases": list_cases(settings), "analysis": case_analysis_capability()}

    @app.post("/api/cases/analyze")
    def analyze_case(
        payload: CaseAnalysisRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        try:
            normalized_url = normalize_source_url(payload.url)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "CASE_URL_INVALID",
                    "暂时无法识别这个视频链接。",
                    "请检查链接，并使用抖音视频链接重新尝试。",
                ),
            ) from exc
        duplicate = find_duplicate_case(settings, normalized_url)
        if duplicate is not None:
            return {
                "duplicate": True,
                "message": "这个案例已经分析过了。",
                "existing_case": duplicate,
            }
        try:
            case_id = source_case_id(normalized_url)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "CASE_SOURCE_IDENTITY_UNRESOLVED",
                    "暂时无法从这个链接确认唯一的视频。",
                    "请使用包含视频编号的完整抖音视频链接。",
                ),
            ) from exc
        active = find_active_case_task(settings.database_path, case_id)
        if active is not None:
            return {
                "duplicate": True,
                "message": "这个案例正在分析或等待审核。",
                "existing_task": active,
            }
        task = create_case_task(
            settings.database_path,
            source_url=normalized_url,
            case_id=case_id,
        )
        task_runner.schedule(task["task_id"])
        return {
            "duplicate": False,
            "task": task,
            "case_id": case_id,
            "next_action": "可以留在当前页面查看进度，也可以稍后从任务记录继续。",
        }

    @app.get("/api/cases/{case_id}")
    def case_detail(
        case_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return get_case_detail(settings, case_id)

    @app.get("/api/cases/{case_id}/media")
    def case_media(
        case_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> FileResponse:
        return FileResponse(
            case_media_path(settings, case_id),
            media_type="video/mp4",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/cases/{case_id}/review")
    def review_case(
        case_id: str,
        payload: CaseReviewRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        reason = payload.reason.strip()
        if payload.decision in {"reject", "reanalyze"} and not reason:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "CASE_REVIEW_REASON_REQUIRED",
                    "请填写不收录或重新分析的原因。",
                    "补充原因后再次提交。",
                ),
            )
        reviewer = str(session.user["phone"])
        if payload.decision == "approve":
            detail = approve_case_candidate(
                settings,
                case_id,
                reviewer=reviewer,
                note=reason or "人工已对照原视频完成结构研究审核。",
            )
            mark_task_reviewed(settings.database_path, case_id, "已批准入库")
            return {"decision": "approved", "case": detail}
        decision = record_case_review_decision(
            settings,
            case_id,
            reviewer=reviewer,
            decision=payload.decision,
            reason=reason,
        )
        if payload.decision == "reject":
            mark_task_reviewed(settings.database_path, case_id, "不收录")
            return {"decision": "rejected", "review": decision}
        detail = get_case_detail(settings, case_id)
        source_url = detail.get("source_url")
        if not source_url:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "CASE_SOURCE_URL_MISSING",
                    "原始视频链接缺失，暂时不能重新分析。",
                    "请先恢复来源链接，再发起重新分析。",
                ),
            )
        mark_task_reviewed(settings.database_path, case_id, "已退回重新分析")
        task = create_case_task(
            settings.database_path,
            source_url=str(source_url),
            case_id=case_id,
            reanalyze=True,
            reason=reason,
        )
        task_runner.schedule(task["task_id"])
        return {"decision": "reanalyze", "task": task}

    @app.get("/api/tasks")
    def tasks(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {"tasks": list_tasks(settings.database_path)}

    @app.get("/api/tasks/{task_id}")
    def task_detail(
        task_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        task = get_task(settings.database_path, task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=error_detail(
                    "TASK_NOT_FOUND", "没有找到这个任务。", "请返回任务记录重新选择。"
                ),
            )
        return {"task": task}

    @app.get("/api/capabilities")
    def capabilities(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {"case_analysis": case_analysis_capability()}

    assets_path = static_path / "assets"
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index_path, headers={"Cache-Control": "no-store"})

    return app


app = build_app()
