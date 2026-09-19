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
    cleanup_expired_sessions,
    delete_session,
    resolve_session,
)
from .background_task_service import BackgroundTaskRunner, create_background_task
from .canonical_gateway import (
    CanonicalOperationError,
    case_analysis_capability,
    find_duplicate_case,
    resolve_case_source_duplicate,
    approve_case_candidate,
    case_media_path,
    get_case_detail,
    get_customer_status,
    list_cases,
    normalize_source_url,
    record_case_review_decision,
    source_case_id,
)
from .customer_gateway import (
    approve_business_persona,
    customer_attention_count,
    get_customer_detail,
    get_customer_input,
    list_customers,
    prepare_customer_onboarding_request,
    prepare_customer_reanalysis_request,
    review_customer_facts,
)
from .customer_task_service import (
    CustomerTaskRunner,
    create_customer_task,
    find_active_customer_task,
    mark_customer_task_reviewed,
)
from .config import Settings
from .database import apply_migrations
from .operation_lock import authority_mutation_barrier, authority_operation_lock
from .task_service import (
    CaseTaskRunner,
    create_case_task,
    find_active_case_task,
    get_task,
    list_tasks,
    mark_task_reviewed,
    TaskSubmissionError,
)
from .speaker_gateway import (
    approve_speaker_persona,
    get_speaker_detail,
    list_speakers,
    prepare_speaker_onboarding_request,
    review_speaker_facts,
    speaker_attention_count,
)

from .speaker_task_service import (
    SpeakerTaskRunner,
    create_speaker_task,
    find_active_speaker_task,
    mark_speaker_task_reviewed,
)

from .content_operations_gateway import get_content_operations_view

from .content_gateway import (
    confirm_content_creation,
    get_active_generation_request,
    list_creation_options,
    preview_content_creation,
    resolve_generation_sources,
)

from .content_delivery_gateway import (
    export_mix_excel,
    exported_excel_filename,
    exported_excel_path,
    generate_scripts,
    get_content_delivery_state,
    resolve_content_plan,
    submit_generation_review,
)

from .news_delivery_gateway import (
    create_news_request,
    export_news_excel,
    exported_news_excel_filename,
    exported_news_excel_path,
    get_active_news_request,
    get_news_delivery_state,
    preview_news_creation,
    resolve_news_plan,
    submit_news_review,
)


class SpeakerAnalysisRequest(BaseModel):
    speaker_name: str = Field(
        min_length=1,
        max_length=200,
    )

    public_role: str = Field(
        min_length=1,
        max_length=200,
    )

    speaker_type: Literal[
        "owner_founder",
        "frontline_expert",
        "brand",
        "generic",
    ]

    materials: str = Field(
        min_length=1,
        max_length=50000,
    )

    forbidden_claims: list[str]


class SpeakerFactDecision(BaseModel):
    candidate_id: str = Field(
        min_length=1,
        max_length=256,
    )

    decision: Literal[
        "approve",
        "reject",
        "edit",
    ]

    edited_value: Any | None = None

    note: str = Field(
        default="",
        max_length=1000,
    )


class SpeakerFactReviewRequest(BaseModel):
    decisions: list[SpeakerFactDecision]

    note: str = Field(
        default="",
        max_length=2000,
    )


class SpeakerPersonaApprovalRequest(BaseModel):
    note: str = Field(
        default="",
        max_length=2000,
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
    reanalyze: bool = False
    reason: str = Field(default="", max_length=1000)


class CaseReviewRequest(BaseModel):
    decision: Literal["reject", "reanalyze", "approve"]
    reason: str = Field(default="", max_length=1000)


class CustomerAnalysisRequest(BaseModel):
    customer_name: str = Field(
        min_length=1,
        max_length=200,
    )
    industry: str = Field(
        min_length=1,
        max_length=120,
    )
    materials: str = Field(
        min_length=1,
        max_length=50000,
    )


class CustomerFactDecision(BaseModel):
    candidate_id: str = Field(
        min_length=1,
        max_length=256,
    )
    decision: Literal[
        "approve",
        "reject",
        "edit",
    ]
    edited_value: Any | None = None
    note: str = Field(
        default="",
        max_length=1000,
    )


class CustomerFactReviewRequest(BaseModel):
    decisions: list[CustomerFactDecision]
    note: str = Field(
        default="",
        max_length=2000,
    )


class CustomerPersonaApprovalRequest(BaseModel):
    note: str = Field(
        default="",
        max_length=2000,
    )


class ContentCapacityPreviewRequest(BaseModel):
    business_id: str = Field(
        min_length=2,
        max_length=128,
    )

    speaker_id: str = Field(
        min_length=2,
        max_length=128,
    )

    profile: Literal[
        "mix",
        "news",
    ]

    quantity: int = Field(
        ge=1,
        le=20,
    )


class ContentGenerationConfirmRequest(BaseModel):
    business_id: str = Field(
        min_length=2,
        max_length=128,
    )

    speaker_id: str = Field(
        min_length=2,
        max_length=128,
    )

    profile: Literal[
        "mix",
        "news",
    ]

    requested_quantity: int = Field(
        ge=1,
        le=20,
    )

    confirmed_quantity: int = Field(
        ge=1,
        le=20,
    )

    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class ContentReviewItem(BaseModel):
    content_id: str = Field(
        min_length=1,
        max_length=256,
    )
    decision: Literal[
        "approved",
        "revised",
        "rejected",
    ]
    revised_title: str | None = Field(
        default=None,
        max_length=120,
    )
    revised_narration: str | None = Field(
        default=None,
        max_length=3000,
    )
    note: str = Field(
        default="",
        max_length=2000,
    )


class ContentReviewRequest(BaseModel):
    items: list[ContentReviewItem]
    note: str = Field(
        default="",
        max_length=4000,
    )


class NewsPreviewRequest(BaseModel):
    business_id: str = Field(
        min_length=2,
        max_length=128,
    )
    speaker_id: str = Field(
        min_length=2,
        max_length=128,
    )


class NewsCreateRequest(BaseModel):
    business_id: str = Field(
        min_length=2,
        max_length=128,
    )
    speaker_id: str = Field(
        min_length=2,
        max_length=128,
    )
    source_content_id: str = Field(
        min_length=1,
        max_length=256,
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
    )


class NewsReviewItem(BaseModel):
    slot_id: str = Field(
        min_length=1,
        max_length=64,
    )
    decision: Literal[
        "approved",
        "revised",
        "rejected",
    ]
    revised_text: str | None = Field(
        default=None,
        max_length=200,
    )
    approved_text: str | None = Field(
        default=None,
        max_length=200,
    )
    note: str = Field(
        default="",
        max_length=1000,
    )


class NewsReviewRequest(BaseModel):
    items: list[NewsReviewItem]


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
    customer_task_runner = CustomerTaskRunner(settings)
    speaker_task_runner = SpeakerTaskRunner(settings)
    background_task_runner = BackgroundTaskRunner(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        apply_migrations(settings.database_path, migrations_path)
        cleanup_expired_sessions(settings.database_path)
        task_runner.start()
        customer_task_runner.start()
        speaker_task_runner.start()
        background_task_runner.start()

        try:
            yield

        finally:
            background_task_runner.close()
            speaker_task_runner.close()
            customer_task_runner.close()
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
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; "
            "frame-src https://open.douyin.com; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(CanonicalOperationError)
    async def canonical_error_handler(
        _: Request, exc: CanonicalOperationError
    ) -> JSONResponse:
        status_code = 409 if exc.code in {
            "OPERATION_IN_PROGRESS",
            "AUTHORITY_CHANGED_REFRESH_REQUIRED",
        } else 503
        return JSONResponse(
            status_code=status_code,
            content={"detail": error_detail(exc.code, exc.message, exc.next_action)},
        )

    @app.exception_handler(TaskSubmissionError)
    async def task_submission_error_handler(
        _: Request, exc: TaskSubmissionError
    ) -> JSONResponse:
        status_code = 409 if exc.code == "OPERATION_ALREADY_ACTIVE" else 429
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": error_detail(
                    exc.code,
                    str(exc),
                    "请查看现有任务，或等待队列释放后重试。",
                )
            },
        )

    def require_session(request: Request) -> SessionContext:
        token = request.cookies.get(settings.session_cookie_name)
        session = resolve_session(
            settings.database_path,
            token,
            last_seen_interval_seconds=settings.session_last_seen_interval_seconds,
        )
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

    def locked_authority_call(
        scope: str,
        identity: str,
        operation: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        with authority_operation_lock(settings, scope, identity, timeout_seconds=0.0):
            return operation(*args, **kwargs)

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
    def login(
        payload: LoginRequest, request: Request, response: Response
    ) -> dict[str, Any]:
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
        token, session = create_session(
            settings.database_path, user["id"], settings.session_hours
        )
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
        return get_customer_status(
            settings, business_id or settings.default_business_id
        )

    @app.get("/api/customers/{business_id}/speakers")
    def customer_speakers(
        business_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        customer = get_customer_detail(
            settings,
            business_id,
        )

        business_persona = customer.get("business_persona") or {}

        business_persona_approved = business_persona.get("approved") is True

        if not business_persona_approved:
            return {
                "speakers": [],
                "can_add_speaker": False,
                "blocker": "BUSINESS_PERSONA_NOT_APPROVED",
            }

        speakers = list_speakers(
            settings,
            business_id,
        )

        tasks_by_speaker = {
            task["subject_ref"]: task
            for task in list_tasks(
                settings.database_path,
                limit=100,
            )
            if (
                task["task_type"] == "speaker_analysis"
                and (task.get("payload", {}).get("business_id") == business_id)
            )
        }

        for speaker in speakers:
            task = tasks_by_speaker.get(speaker["speaker_id"])

            if task is None:
                continue

            speaker["task"] = task

            if task["status"] in {
                "queued",
                "running",
            }:
                speaker["status"] = "analyzing"

            elif task["status"] == "failed" and speaker["status"] == "analysis_pending":
                speaker["status"] = "failed"

        return {
            "speakers": speakers,
            "can_add_speaker": True,
            "blocker": None,
        }

    @app.post("/api/customers/{business_id}/speakers/analyze")
    def analyze_speaker(
        business_id: str,
        payload: SpeakerAnalysisRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        prepared = locked_authority_call(
            "business",
            business_id,
            prepare_speaker_onboarding_request,
            settings,
            business_id=business_id,
            speaker_name=(payload.speaker_name),
            public_role=(payload.public_role),
            speaker_type=(payload.speaker_type),
            materials=(payload.materials),
            forbidden_claims=(payload.forbidden_claims),
        )

        speaker_id = prepared["speaker_id"]

        active = find_active_speaker_task(
            settings.database_path,
            speaker_id,
        )

        if active is not None:
            return {
                "duplicate": True,
                "business_id": (business_id),
                "speaker_id": (speaker_id),
                "state": (
                    "awaiting_review"
                    if active["status"] == "awaiting_review"
                    else "running"
                ),
                "existing_task": (active),
                "existing_speaker": (
                    prepared.get("existing_speaker")
                    or get_speaker_detail(
                        settings,
                        business_id,
                        speaker_id,
                    )
                ),
            }

        if prepared.get("duplicate"):
            existing = prepared.get("existing_speaker") or get_speaker_detail(
                settings,
                business_id,
                speaker_id,
            )

            if existing.get("status") == "analysis_pending" and prepared.get(
                "request_path"
            ):
                task = create_speaker_task(
                    settings.database_path,
                    business_id=(business_id),
                    speaker_id=(speaker_id),
                    intake_id=(prepared.get("intake_id") or "intake_0001"),
                    request_path=(prepared["request_path"]),
                    speaker_name=(existing["display_name"]),
                    public_role=(existing["public_role"]),
                    created_by_user_id=int(session.user["id"]),
                    queue_max=settings.task_queue_max,
                )

                speaker_task_runner.schedule(task["task_id"])

                return {
                    "duplicate": False,
                    "resumed": True,
                    "business_id": (business_id),
                    "speaker_id": (speaker_id),
                    "task": task,
                }

            return {
                "duplicate": True,
                "business_id": (business_id),
                "speaker_id": (speaker_id),
                "state": existing["status"],
                "existing_speaker": (existing),
            }

        task = create_speaker_task(
            settings.database_path,
            business_id=(business_id),
            speaker_id=(speaker_id),
            intake_id=(prepared["intake_id"]),
            request_path=(prepared["request_path"]),
            speaker_name=(prepared["speaker_name"]),
            public_role=(prepared["public_role"]),
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
        )

        speaker_task_runner.schedule(task["task_id"])

        return {
            "duplicate": False,
            "business_id": (business_id),
            "speaker_id": (speaker_id),
            "task": task,
            "next_action": ("出镜人信息正在后台分析，" "可以离开页面后再回来继续。"),
        }

    @app.get("/api/customers/{business_id}/speakers/{speaker_id}")
    def speaker_detail(
        business_id: str,
        speaker_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        detail = get_speaker_detail(
            settings,
            business_id,
            speaker_id,
        )

        latest_task = next(
            (
                task
                for task in list_tasks(
                    settings.database_path,
                    limit=100,
                )
                if (
                    task["task_type"] == "speaker_analysis"
                    and task["subject_ref"] == speaker_id
                )
            ),
            None,
        )

        if latest_task is not None:
            detail["task"] = latest_task

            if latest_task["status"] in {
                "queued",
                "running",
            }:
                detail["status"] = "analyzing"

            elif (
                latest_task["status"] == "failed"
                and detail["status"] == "analysis_pending"
            ):
                detail["status"] = "failed"

        return detail

    @app.post("/api/customers/{business_id}/speakers/{speaker_id}/facts/review")
    def review_speaker_fact_candidates(
        business_id: str,
        speaker_id: str,
        payload: SpeakerFactReviewRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        result = locked_authority_call(
            "persona",
            f"{business_id}:{speaker_id}",
            review_speaker_facts,
            settings,
            business_id=(business_id),
            speaker_id=(speaker_id),
            decisions=[
                item.model_dump(exclude_none=True) for item in (payload.decisions)
            ],
            reviewer=str(session.user["phone"]),
            note=(payload.note),
        )

        mark_speaker_task_reviewed(
            settings.database_path,
            speaker_id,
        )

        return {
            "review": result,
        }

    @app.post("/api/customers/{business_id}/speakers/{speaker_id}/persona/approve")
    def approve_customer_speaker_persona(
        business_id: str,
        speaker_id: str,
        payload: SpeakerPersonaApprovalRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        detail = locked_authority_call(
            "persona",
            f"{business_id}:{speaker_id}",
            approve_speaker_persona,
            settings,
            business_id=(business_id),
            speaker_id=(speaker_id),
            reviewer=str(session.user["phone"]),
            note=(payload.note),
        )

        return {
            "speaker": detail,
        }

    @app.get("/api/create/options")
    def creation_options(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return list_creation_options(settings)

    @app.get("/api/create/active-request")
    def active_generation_request(
        business_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return get_active_generation_request(
            settings,
            business_id,
        )

    @app.post("/api/create/capacity-preview")
    def content_capacity_preview(
        payload: ContentCapacityPreviewRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        preview = preview_content_creation(
            settings,
            business_id=(payload.business_id),
            speaker_id=(payload.speaker_id),
            profile=(payload.profile),
            quantity=(payload.quantity),
        )

        return {
            "preview": preview,
        }

    @app.post("/api/create/confirm")
    def confirm_generation_request(
        payload: ContentGenerationConfirmRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        # The child operation already owns the business-scoped lock. The shared
        # barrier still prevents an offline backup from racing this mutation.
        with authority_mutation_barrier(settings, timeout_seconds=0.0):
            result = confirm_content_creation(
                settings,
                business_id=(payload.business_id),
                speaker_id=(payload.speaker_id),
                profile=(payload.profile),
                requested_quantity=(payload.requested_quantity),
                confirmed_quantity=(payload.confirmed_quantity),
                idempotency_key=(payload.idempotency_key),
            )

        return {
            "result": result,
        }

    @app.post("/api/create/{request_id}/resolve-sources")
    def resolve_generation_source_plan(
        request_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        result = locked_authority_call(
            "request",
            request_id,
            resolve_generation_sources,
            settings,
            request_id,
        )

        return {
            "result": result,
        }

    @app.get("/api/create/{request_id}/delivery")
    def content_delivery_state(
        request_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {
            "state": get_content_delivery_state(
                settings,
                request_id,
            )
        }

    @app.post("/api/create/{request_id}/resolve-content-plan")
    def resolve_content_plan_route(
        request_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        task = create_background_task(
            settings,
            operation="content_plan",
            request_id=request_id,
            created_by_user_id=int(session.user["id"]),
        )
        background_task_runner.schedule(task["task_id"])
        return {"accepted": True, "task": task}

    @app.post("/api/create/{request_id}/generate-scripts")
    def generate_scripts_route(
        request_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        task = create_background_task(
            settings,
            operation="script_generation",
            request_id=request_id,
            created_by_user_id=int(session.user["id"]),
        )
        background_task_runner.schedule(task["task_id"])
        return {"accepted": True, "task": task}

    @app.post("/api/create/{request_id}/review")
    def generation_review_route(
        request_id: str,
        payload: ContentReviewRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        return {
            "result": locked_authority_call(
                "request",
                request_id,
                submit_generation_review,
                settings,
                request_id,
                reviewer=str(session.user["phone"]),
                items=[
                    item.model_dump()
                    for item in payload.items
                ],
                note=payload.note,
            )
        }

    @app.post("/api/create/{request_id}/export-mix")
    def export_mix_route(
        request_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        task = create_background_task(
            settings,
            operation="mix_export",
            request_id=request_id,
            created_by_user_id=int(session.user["id"]),
        )
        background_task_runner.schedule(task["task_id"])
        return {"accepted": True, "task": task}

    @app.get("/api/create/{request_id}/exported-excel")
    def download_exported_excel(
        request_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> FileResponse:
        path = exported_excel_path(
            settings,
            request_id,
        )
        return FileResponse(
            path=path,
            filename=exported_excel_filename(
                settings,
                request_id,
            ),
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

    @app.get("/api/create/news/active")
    def active_news_request(
        business_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return get_active_news_request(
            settings,
            business_id,
        )

    @app.post("/api/create/news/preview")
    def news_preview_route(
        payload: NewsPreviewRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        return {
            "preview": preview_news_creation(
                settings,
                business_id=payload.business_id,
                speaker_id=payload.speaker_id,
            )
        }

    @app.post("/api/create/news/request")
    def create_news_request_route(
        payload: NewsCreateRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        return {
            "result": locked_authority_call(
                "business",
                payload.business_id,
                create_news_request,
                settings,
                business_id=payload.business_id,
                speaker_id=payload.speaker_id,
                source_content_id=payload.source_content_id,
                idempotency_key=payload.idempotency_key,
            )
        }

    @app.get("/api/create/news/{request_id}/delivery")
    def news_delivery_state_route(
        request_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {
            "state": get_news_delivery_state(
                settings,
                request_id,
            )
        }

    @app.post("/api/create/news/{request_id}/resolve-plan")
    def resolve_news_plan_route(
        request_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        task = create_background_task(
            settings,
            operation="news_plan",
            request_id=request_id,
            created_by_user_id=int(session.user["id"]),
        )
        background_task_runner.schedule(task["task_id"])
        return {"accepted": True, "task": task}

    @app.post("/api/create/news/{request_id}/review")
    def review_news_route(
        request_id: str,
        payload: NewsReviewRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        return {
            "result": locked_authority_call(
                "request",
                request_id,
                submit_news_review,
                settings,
                request_id,
                reviewer=str(session.user["phone"]),
                items=[
                    item.model_dump()
                    for item in payload.items
                ],
            )
        }

    @app.post("/api/create/news/{request_id}/export")
    def export_news_route(
        request_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        task = create_background_task(
            settings,
            operation="news_export",
            request_id=request_id,
            created_by_user_id=int(session.user["id"]),
        )
        background_task_runner.schedule(task["task_id"])
        return {"accepted": True, "task": task}

    @app.get("/api/create/news/{request_id}/excel")
    def download_news_excel_route(
        request_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> FileResponse:
        path = exported_news_excel_path(
            settings,
            request_id,
        )

        return FileResponse(
            path=path,
            filename=exported_news_excel_filename(
                settings,
                request_id,
            ),
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
        )

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
                "case_reviews": sum(
                    case["status"] == "awaiting_review" for case in cases
                ),
                "persona_reviews": (
                    customer_attention_count(settings)
                    + speaker_attention_count(settings)
                ),
                "content_reviews": sum(
                    task["task_type"] == "content_generation"
                    and task["status"] == "awaiting_review"
                    for task in tasks
                ),
                "running_tasks": sum(
                    task["status"] in {"queued", "running"} for task in tasks
                ),
            },
            "recent_tasks": tasks[:5],
            "capabilities": {"case_analysis": case_analysis_capability()},
        }

    @app.get("/api/customers")
    def customers(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        projected = list_customers(settings)

        customer_tasks = {
            task["subject_ref"]: task
            for task in list_tasks(
                settings.database_path,
                limit=100,
            )
            if (task["task_type"] == "customer_analysis")
        }

        for customer in projected:
            task = customer_tasks.get(customer["business_id"])

            if task is None:
                continue

            customer["task"] = task

            if task["status"] in {
                "queued",
                "running",
            }:
                customer["status"] = "analyzing"

            elif (
                task["status"] == "failed" and customer["status"] == "analysis_pending"
            ):
                customer["status"] = "failed"

        return {
            "customers": projected,
        }

    @app.post("/api/customers/analyze")
    def analyze_customer(
        payload: CustomerAnalysisRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        prepared = locked_authority_call(
            "business",
            payload.customer_name.strip().casefold(),
            prepare_customer_onboarding_request,
            settings,
            customer_name=(payload.customer_name),
            industry=payload.industry,
            materials=payload.materials,
        )

        business_id = prepared["business_id"]

        active = find_active_customer_task(
            settings.database_path,
            business_id,
        )

        if active is not None:
            return {
                "duplicate": True,
                "business_id": business_id,
                "state": (
                    "awaiting_review"
                    if active["status"] == "awaiting_review"
                    else "running"
                ),
                "existing_task": active,
                "existing_customer": (
                    prepared.get("existing_customer")
                    or get_customer_detail(
                        settings,
                        business_id,
                    )
                ),
            }

        if prepared.get("duplicate"):
            existing = prepared.get("existing_customer") or get_customer_detail(
                settings,
                business_id,
            )

            # Durable request exists, but task projection
            # may have been lost. Resume from canonical input.
            if existing.get("status") == "analysis_pending" and prepared.get(
                "request_path"
            ):
                task = create_customer_task(
                    settings.database_path,
                    business_id=business_id,
                    intake_id=(prepared.get("intake_id") or "intake_0001"),
                    request_path=prepared["request_path"],
                    customer_name=(existing["display_name"]),
                    industry=(existing["industry"]),
                    created_by_user_id=int(session.user["id"]),
                    queue_max=settings.task_queue_max,
                )

                customer_task_runner.schedule(task["task_id"])

                return {
                    "duplicate": False,
                    "resumed": True,
                    "business_id": (business_id),
                    "task": task,
                }

            return {
                "duplicate": True,
                "business_id": business_id,
                "state": existing["status"],
                "existing_customer": (existing),
            }

        task = create_customer_task(
            settings.database_path,
            business_id=business_id,
            intake_id=prepared["intake_id"],
            request_path=prepared["request_path"],
            customer_name=prepared["customer_name"],
            industry=prepared["industry"],
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
        )

        customer_task_runner.schedule(task["task_id"])

        return {
            "duplicate": False,
            "business_id": business_id,
            "task": task,
            "next_action": ("客户信息正在后台分析，" "可以离开页面后再回来继续。"),
        }

    @app.post("/api/customers/{business_id}/reanalyze")
    def reanalyze_customer(
        business_id: str,
        payload: CustomerAnalysisRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        active = find_active_customer_task(
            settings.database_path,
            business_id,
        )

        if active is not None:
            return {
                "reanalyze": False,
                "existing_task": active,
            }

        prepared = locked_authority_call(
            "business",
            business_id,
            prepare_customer_reanalysis_request,
            settings,
            business_id=business_id,
            customer_name=(payload.customer_name),
            industry=(payload.industry),
            materials=(payload.materials),
        )

        task = create_customer_task(
            settings.database_path,
            business_id=business_id,
            intake_id=prepared["intake_id"],
            request_path=prepared["request_path"],
            customer_name=(prepared["customer_name"]),
            industry=prepared["industry"],
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
        )

        customer_task_runner.schedule(task["task_id"])

        return {
            "reanalyze": True,
            "new_intake": (
                not prepared.get(
                    "same_input",
                    False,
                )
            ),
            "intake_id": (prepared["intake_id"]),
            "task": task,
        }

    @app.post("/api/customers/{business_id}/retry")
    def retry_customer_analysis(
        business_id: str,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        active = find_active_customer_task(
            settings.database_path,
            business_id,
        )

        if active is not None:
            return {
                "resumed": False,
                "existing_task": active,
            }

        source = get_customer_input(
            settings,
            business_id,
        )

        task = create_customer_task(
            settings.database_path,
            business_id=business_id,
            intake_id=source["intake_id"],
            request_path=source["request_path"],
            customer_name=source["customer_name"],
            industry=source["industry"],
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
        )

        customer_task_runner.schedule(task["task_id"])

        return {
            "resumed": True,
            "task": task,
        }

    @app.get("/api/customers/{business_id}/input")
    def customer_input(
        business_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {
            "input": get_customer_input(
                settings,
                business_id,
            )
        }

    @app.get(
        "/api/customers/{business_id}/content-operations"
    )
    def customer_content_operations(
        business_id: str,
        _: SessionContext = Depends(
            require_console_access
        ),
    ) -> dict[str, Any]:
        return get_content_operations_view(
            settings,
            business_id,
        )

    @app.get("/api/customers/{business_id}")
    def customer_detail(
        business_id: str,
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        detail = get_customer_detail(
            settings,
            business_id,
        )

        latest_task = next(
            (
                task
                for task in list_tasks(
                    settings.database_path,
                    limit=100,
                )
                if (
                    task["task_type"] == "customer_analysis"
                    and task["subject_ref"] == business_id
                )
            ),
            None,
        )

        if latest_task is not None:
            detail["task"] = latest_task

            if latest_task["status"] in {
                "queued",
                "running",
            }:
                detail["status"] = "analyzing"

            elif (
                latest_task["status"] == "failed"
                and detail["status"] == "analysis_pending"
            ):
                detail["status"] = "failed"

        # Speaker listing is only meaningful after the Business Persona
        # itself has been explicitly Human Approved.
        #
        # Customer Detail, however, must remain readable during:
        # - analysis
        # - failure / retry
        # - Fact Review
        # - Business Persona Review
        business_persona = detail.get("business_persona") or {}

        business_persona_approved = business_persona.get("approved") is True

        if business_persona_approved:
            speakers = list_speakers(
                settings,
                business_id,
            )
        else:
            speakers = []

        detail["speakers"] = speakers

        detail["creation_entry_ready"] = business_persona_approved and any(
            speaker.get("status") == "approved" for speaker in speakers
        )

        detail["media_rights_established"] = False

        return detail

    @app.post("/api/customers/{business_id}/facts/review")
    def review_customer_fact_candidates(
        business_id: str,
        payload: CustomerFactReviewRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        result = locked_authority_call(
            "business",
            business_id,
            review_customer_facts,
            settings,
            business_id=business_id,
            decisions=[
                item.model_dump(exclude_none=True) for item in (payload.decisions)
            ],
            reviewer=str(session.user["phone"]),
            note=payload.note,
        )

        mark_customer_task_reviewed(
            settings.database_path,
            business_id,
        )

        return {
            "review": result,
        }

    @app.post("/api/customers/{business_id}/persona/approve")
    def approve_customer_persona(
        business_id: str,
        payload: CustomerPersonaApprovalRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(
            session,
            x_csrf_token,
        )

        detail = locked_authority_call(
            "persona",
            business_id,
            approve_business_persona,
            settings,
            business_id=business_id,
            reviewer=str(session.user["phone"]),
            note=payload.note,
        )

        return {
            "customer": detail,
        }

    @app.get("/api/cases")
    def cases(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {"cases": list_cases(settings), "analysis": case_analysis_capability()}

    @app.post("/api/cases/analyze")
    def analyze_case(
        payload: CaseAnalysisRequest,
        x_csrf_token: str | None = Header(
            default=None,
            alias="X-CSRF-Token",
        ),
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

        try:
            case_id = source_case_id(payload.url)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    "CASE_SOURCE_IDENTITY_UNRESOLVED",
                    "暂时无法从这个链接确认唯一的视频。",
                    "请使用包含视频编号的完整抖音视频链接。",
                ),
            ) from exc

        duplicate = resolve_case_source_duplicate(
            settings,
            payload.url,
        )

        if duplicate is not None:
            state = str(duplicate.get("state") or "")
            allowed_reanalysis = state in {
                "failed",
                "rejected",
            }

            if not payload.reanalyze:
                existing_task = None
                attempt_id = duplicate.get("attempt_id")

                if attempt_id:
                    existing_task = get_task(
                        settings.database_path,
                        str(attempt_id),
                    )

                return {
                    **duplicate,
                    "existing_task": existing_task,
                }

            if not allowed_reanalysis:
                return {
                    **duplicate,
                    "reanalyze_blocked": True,
                }

            reason = payload.reason.strip()

            if state == "rejected" and not reason:
                raise HTTPException(
                    status_code=422,
                    detail=error_detail(
                        "CASE_REANALYSIS_REASON_REQUIRED",
                        "这个案例之前已由人工决定不收录。",
                        "请填写重新分析的原因后继续。",
                    ),
                )

            if not reason:
                reason = "分析失败后由运营人员显式重新分析。"

            task = create_case_task(
                settings.database_path,
                source_url=normalized_url,
                case_id=case_id,
                reanalyze=True,
                reason=reason,
                created_by_user_id=int(session.user["id"]),
                queue_max=settings.task_queue_max,
                gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
            )
            task_runner.schedule(task["task_id"])

            return {
                "duplicate": False,
                "reanalyze": True,
                "task": task,
                "case_id": case_id,
                "next_action": ("新的分析 Attempt 已建立；" "原有分析记录不会被覆盖。"),
            }

        active = find_active_case_task(
            settings.database_path,
            case_id,
        )

        if active is not None:
            return {
                "duplicate": True,
                "duplicate_kind": "source_identity",
                "state": (
                    "awaiting_review"
                    if active["status"] == "awaiting_review"
                    else "running"
                ),
                "case_id": case_id,
                "existing_task": active,
                "can_reanalyze": False,
                "message": (
                    "这个视频已经分析完成，正在等待审核。"
                    if active["status"] == "awaiting_review"
                    else "这个视频正在分析。"
                ),
            }

        task = create_case_task(
            settings.database_path,
            source_url=normalized_url,
            case_id=case_id,
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
            gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
        )
        task_runner.schedule(task["task_id"])

        return {
            "duplicate": False,
            "task": task,
            "case_id": case_id,
            "next_action": ("可以留在当前页面查看进度，" "也可以稍后从任务记录继续。"),
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
            detail = locked_authority_call(
                "case",
                case_id,
                approve_case_candidate,
                settings,
                case_id,
                reviewer=reviewer,
                note=reason or "人工已对照原视频完成结构研究审核。",
            )
            mark_task_reviewed(settings.database_path, case_id, "已批准入库")
            return {"decision": "approved", "case": detail}
        decision = locked_authority_call(
            "case",
            case_id,
            record_case_review_decision,
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
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
            gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
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
