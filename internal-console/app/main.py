from __future__ import annotations

import os
import re
import json
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from fastapi import Query
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .case_uploads import receive_upload, validate_for_submission
from .case_boundary_review import (
    BoundaryReviewError,
    pending_boundary_review,
    submit_boundary_review,
)

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
from .generation_recovery_gateway import preview as preview_generation_retry, confirm as confirm_generation_retry
from .content_delivery_gateway import completed_mix_export, submit_mix_export
from .canonical_gateway import (
    CanonicalOperationError,
    case_cover_path,
    case_analysis_capability,
    find_duplicate_case,
    resolve_case_source_duplicate,
    approve_case_candidate,
    annotate_case_profile,
    annotate_case_industry,
    case_media_path,
    get_case_detail,
    get_customer_status,
    list_cases,
    record_case_review_decision,
)
from .customer_gateway import (
    approve_business_persona,
    confirm_speaker_discovery,
    get_customer_detail,
    get_customer_input,
    list_customers,
    prepare_customer_gap_supplement_request,
    prepare_customer_onboarding_request,
    prepare_customer_reanalysis_request,
    prepare_saved_source_recovery,
    recheck_customer_readiness,
    review_customer_facts,
    record_speaker_discovery_intent,
    prepare_speaker_discovery_retry,
    customer_review_context,
    validate_customer_review_context,
)
from .customer_task_service import (
    CustomerTaskRunner,
    create_customer_task,
    find_active_customer_task,
    mark_customer_task_reviewed,
)
from .config import Settings
from .case_classification import classification_state, classification_summary, confirm_classification
from .case_intake_service import create_group, dispatch_groups, get_group, list_groups
from .case_library_access import (
    principal as case_principal, reviewer_authorization, is_reviewer, can_read_task,
    can_read_private_case, can_read_group, require_private_case, require_task,
    not_visible, record_submission, safe_case_task,
)
from .case_shared_display import shared_projection, shared_cover_path, publication_context, change_publication
from .case_list_projection import case_cards
from .dashboard_projection import dashboard
from .legacy_scope_gateway import scope_projection, submit_scope
from .database import transaction
from .douyin_source_input import DouyinSourceInput
from .database import apply_migrations
from .douyin_source_input import SourceInputError, resolve_douyin_source_input
from .operator_projection import case_reanalysis_hint, operator_activity, original_task_actor, persona_approval_actor
from .operation_lock import authority_mutation_barrier, authority_operation_lock, operation_lock
from .task_service import (
    CaseTaskRunner,
    create_case_task,
    ensure_task_capacity,
    find_active_case_task,
    get_task,
    list_tasks,
    latest_subject_task,
    mark_task_reviewed,
    TaskSubmissionError,
)
from .speaker_gateway import (
    approve_speaker_persona,
    get_speaker_detail,
    list_speakers,
    prepare_speaker_gap_supplement_request,
    prepare_speaker_draft_analysis,
    prepare_speaker_onboarding_request,
    record_speaker_auto_handoff_status,
    review_speaker_facts,
    recheck_speaker_readiness,
    revalidate_speaker_business,
    speaker_attention_count,
)

from .speaker_task_service import (
    SpeakerTaskRunner,
    create_speaker_task,
    find_active_speaker_task,
    mark_speaker_task_reviewed,
)

from .content_operations_gateway import get_content_operations_view
from .customer_operations_projection import list_customer_operations, creation_record_index, request_navigation_context

from .content_gateway import (
    abandon_generation_request,
    confirm_content_creation,
    get_active_generation_request,
    list_creation_options,
    preview_content_creation,
    resolve_generation_sources,
)

from .content_delivery_gateway import (
    delivery_authorization,
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
from .novel_news_gateway import (
    preview_novel_news, novel_news_state, review_novel_news, novel_news_excel,
)
from .novel_news_rollout import novel_news_available, require_if_novel_request, require_novel_news


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

    forbidden_claims: list[str] = Field(default_factory=list, max_length=50)


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
    review_context: str | None = Field(default=None, max_length=50000)
    decisions: list[SpeakerFactDecision]

    note: str = Field(
        default="",
        max_length=2000,
    )


class SpeakerPersonaApprovalRequest(BaseModel):
    review_context: str | None = Field(default=None, max_length=50000)
    note: str = Field(
        default="",
        max_length=2000,
    )


class SpeakerFinalDecision(SpeakerFactDecision):
    model_config = {"extra": "forbid"}


class SpeakerFinalPreviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    review_context: str = Field(max_length=50000)
    decisions: list[SpeakerFinalDecision] = Field(default_factory=list, max_length=100)
    note: str = Field(default="", max_length=2000)


class SpeakerFinalConfirmationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    review_context: str = Field(max_length=200000)
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation: Literal["approve_speaker_profile"]


class GenerationRecoveryPreviewRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    operation_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class GenerationRecoveryConfirmRequest(GenerationRecoveryPreviewRequest):
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class LoginRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class CaseAnalysisRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    operator_profile_hint: Literal["mix", "news", "hybrid", "uncertain"] | None = None
    industry: str | None = Field(default=None, max_length=30)
    reanalyze: bool = False
    reason: str = Field(default="", max_length=1000)
    source_upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class CaseIntakeGroupRequest(BaseModel):
    text: str = Field(min_length=1, max_length=40000)
    client_request_id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    source_upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class CaseClassificationRequest(BaseModel):
    attempt_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,128}$")
    industry: str | None = Field(default=None, max_length=30)
    profile: Literal["mix", "news", "hybrid", "uncertain"]
    candidate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_confirmation_sha256: str | None = Field(..., pattern=r"^[0-9a-f]{64}$")


class CaseEvidenceDecision(BaseModel):
    item_id: str = Field(min_length=1, max_length=80)
    action: Literal["keep"]


class CaseEvidenceReviewRequest(BaseModel):
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    narration_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    shot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    narration_decisions: list[CaseEvidenceDecision] = Field(default_factory=list, max_length=100)
    shot_decisions: list[CaseEvidenceDecision] = Field(default_factory=list, max_length=100)


class CaseFinalEvidenceReviewRequest(BaseModel):
    model_config = {"extra":"forbid"}
    schema_version: Literal['case-evidence-final-review-v2.0']
    confirmation_mode: Literal['final_bulk_keep']
    scope_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    explicit_keep_ids: list[str] = Field(default_factory=list,max_length=200)


class CaseSharingDecision(BaseModel):
    model_config = {"extra":"forbid"}
    schema_version: Literal['case-human-display-decision-v1.0']
    decision: Literal['publish_exact_preview','approve_only']
    preview_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    preview: dict[str, Any]
    blocker_sha256: str | None = Field(...,pattern=r'^[a-f0-9]{64}$')
    origin: Literal['human_joint_final_confirmation']


class CaseSharePreviewRequest(BaseModel):
    model_config = {"extra":"forbid"}
    title: str | None = Field(default=None,max_length=120)
    structure_summary: str | None = Field(default=None,max_length=1000)


class CaseReviewRequest(BaseModel):
    model_config = {"extra":"forbid"}
    review_context: str | None = Field(default=None, max_length=50000)
    decision: Literal["reject", "reanalyze", "approve"]
    reason: str = Field(default="", max_length=1000)
    operator_profile_hint: Literal["mix", "news", "hybrid", "uncertain"] | None = None
    industry: str | None = Field(default=None, max_length=30)
    source_upload_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    evidence_review: CaseFinalEvidenceReviewRequest | CaseEvidenceReviewRequest | None = None
    quality_decision: dict[str, Any] | None = None
    sharing_decision: CaseSharingDecision | None = None


class CaseProfileAnnotationRequest(BaseModel):
    operator_profile_hint: Literal["mix", "news", "hybrid", "uncertain"]
    approved_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_annotation_sha256: str | None = Field(..., pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=1000)


class CaseCoverClearanceRequest(BaseModel):
    reference: str = Field(min_length=1,max_length=1000)
    statement: str = Field(min_length=1,max_length=1000)
    display_rights_confirmed: Literal[True]


class CasePublicationRequest(BaseModel):
    action: Literal["publish","withdraw"]
    title: str = Field(default="",max_length=120)
    structure_summary: str = Field(default="",max_length=1000)
    approved_case_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approval_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_display_receipt_sha256: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")
    cover_evidence: CaseCoverClearanceRequest | None = None


class CaseIndustryAnnotationRequest(BaseModel):
    industry: str = Field(min_length=1, max_length=30)
    approved_case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_annotation_sha256: str | None = Field(..., pattern=r"^[0-9a-f]{64}$")
    note: str = Field(default="", max_length=1000)


class CaseBoundaryDecision(BaseModel):
    frame_id: str = Field(pattern=r"^frame_\d{9}ms\.jpg$")
    action: Literal["keep", "reject"]


class CaseBoundaryReviewRequest(BaseModel):
    shot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decisions: list[CaseBoundaryDecision] = Field(min_length=1, max_length=100)


class CustomerAnalysisRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    materials: str = Field(default="", max_length=50000)
    save_only: bool = False
    create_separate: bool = False
    submission_key: str | None = Field(default=None, min_length=8, max_length=64)


class SpeakerGapSupplementRequest(BaseModel):
    answers: dict[str, str]


class CustomerGapAnswer(BaseModel):
    target_gap: str = Field(min_length=1, max_length=256)
    raw_answer: str = Field(min_length=1, max_length=12000)


class CustomerGapSupplementRequest(BaseModel):
    answers: list[CustomerGapAnswer] = Field(min_length=1, max_length=8)


class CustomerSavedSourceRecoveryRequest(BaseModel):
    source_intake_id: str = Field(pattern=r"^intake_\d{4}$")
    targets: list[str] = Field(min_length=1, max_length=5)
    execution_identity: str = Field(min_length=8, max_length=64)


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


class SpeakerDiscoveryConfirmation(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    selected: bool = False
    speaker_name: str | None = Field(default=None, max_length=200)
    public_role: str | None = Field(default=None, max_length=200)
    speaker_type: Literal[
        "owner_founder",
        "frontline_expert",
        "brand",
        "generic",
    ] | None = None


class SpeakerDiscoveryConfirmRequest(BaseModel):
    decisions: list[SpeakerDiscoveryConfirmation] = Field(
        default_factory=list, max_length=5
    )


class SpeakerRevalidationRequest(BaseModel):
    confirmed: bool
    business_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    speaker_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    note: str = Field(default="", max_length=2000)


class SpeakerJointFactDecision(CustomerFactDecision):
    model_config={"extra":"forbid"}


class SpeakerJointFactReview(BaseModel):
    model_config={"extra":"forbid"}
    candidate_id:str=Field(min_length=1,max_length=128)
    decisions:list[SpeakerJointFactDecision]=Field(max_length=30)


class CustomerFactReviewRequest(BaseModel):
    review_context: str | None = Field(default=None, max_length=8192)
    resume_review: bool = False
    joint_speaker_review: bool = False
    business_only: bool = False
    retry_preparation: bool = False
    speaker_fact_decisions: list[SpeakerJointFactReview] = Field(default_factory=list,max_length=5)
    decisions: list[CustomerFactDecision]
    constraint_decisions: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    industry_review: dict[str, Any] | None = None
    speaker_confirmations: list[SpeakerDiscoveryConfirmation] = Field(
        default_factory=list,
        max_length=5,
    )
    note: str = Field(
        default="",
        max_length=2000,
    )


class CustomerFinalPreviewRequest(CustomerFactReviewRequest):
    model_config={"extra":"forbid"}


class CustomerPersonaApprovalRequest(BaseModel):
    review_context: str | None = Field(default=None, max_length=50000)
    note: str = Field(
        default="",
        max_length=2000,
    )


class NovelNewsGenerateRequest(BaseModel):
    model_config = {"extra": "forbid"}


class NovelNewsRetryRequest(BaseModel):
    model_config = {"extra": "forbid"}
    parent_intent_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    confirmation: Literal['retry_unknown_generation_with_possible_additional_cost']


class CustomerFinalConfirmationRequest(BaseModel):
    model_config = {"extra": "forbid"}
    review_context: str = Field(max_length=200000)
    preview_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    confirmation: Literal["approve_business_profile", "save_review_progress", "approve_customer_and_speakers"]


class PersonaAmendmentRequest(BaseModel):
    review_context: str | None = Field(default=None, max_length=50000)
    action: Literal["correct", "rebase"]
    reason: str = Field(min_length=1, max_length=2000)
    changes: list[dict[str, Any]] = Field(default_factory=list, max_length=40)


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
    creative_style_id: str | None = Field(default=None,min_length=1,max_length=32)
    configuration: dict[str,Any] | None = None


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

    selected_opportunity_id: str | None = Field(default=None, min_length=8, max_length=128)
    creative_style_id: str | None = Field(default=None, min_length=1, max_length=32)
    configuration: dict[str, Any] | None = None
    style_preflight_sha256: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')


class CreationConfigurationDraftRequest(BaseModel):
    revision: int = Field(ge=0,strict=True)
    payload: dict[str,Any]


class CreationBatchPreviewRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    business_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    speaker_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    configuration: dict[str, Any]
    operation_id: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


class CreationBatchConfirmRequest(CreationBatchPreviewRequest):
    preflight_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class CreationBatchControlRequest(BaseModel):
    model_config = {'extra': 'forbid'}
    action: Literal['pause', 'resume', 'end']
    operation_id: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


class CreationBatchHumanCommand(BaseModel):
    model_config = {'extra': 'forbid'}
    scope: Literal['native_content_review', 'publish_copy_confirmation']
    items: list[dict[str, Any]] = Field(min_length=1, max_length=40)
    operation_id: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class CreationBatchDeliveryScope(BaseModel):
    model_config = {'extra': 'forbid'}
    scope: Literal['complete_target', 'explicit_legal_subset']
    slot_ids: list[str] = Field(min_length=1, max_length=40)


class CreationBatchDeliveryCommand(CreationBatchDeliveryScope):
    operation_id: str = Field(min_length=8, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


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


class NovelNewsReviewItem(BaseModel):
    beat_id: str = Field(min_length=1, max_length=64)
    decision: Literal["approved", "revised", "rejected"]
    revised_text: str | None = Field(default=None, max_length=200)


class NovelNewsReviewRequest(BaseModel):
    decisions: list[NovelNewsReviewItem] = Field(min_length=4, max_length=8)


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


def selected_case_industry(value: str | None, fallback: str = "待分类") -> str:
    """Accept an explicit operator label without changing legacy API requests."""
    if value is None:
        return fallback.strip() or "待分类"
    industry = value.strip()
    if not industry or industry.lower() in {"待分类", "unknown"}:
        raise HTTPException(
            status_code=422,
            detail=error_detail("CASE_INDUSTRY_REQUIRED", "请选择案例所属行业。", "填写行业后重新提交。"),
        )
    return industry


def public_user(session: SessionContext) -> dict[str, Any]:
    return {
        "phone": session.user["phone"],
        "must_change_password": session.user["must_change_password"],
        "status": session.user["status"],
    }


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()

    def project_case_task_statuses(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep attempt history intact while showing the current approved Case."""
        contexts: dict[str, tuple[bool, str | None, str | None]] = {}
        projected = []
        for task in tasks:
            if task["task_type"] != "case_analysis":
                projected.append(task)
                continue
            case_id = str(task.get("subject_ref") or "")
            if not case_id:
                projected.append(task)
                continue
            if case_id not in contexts:
                approved = False
                approved_attempt = None
                try:
                    detail = get_case_detail(settings, case_id)
                except CanonicalOperationError:
                    pass
                else:
                    review = detail.get("review") or {}
                    approved = (
                        detail.get("status") == "approved"
                        and review.get("approved") is True
                    )
                    if approved:
                        approved_attempt = str(review.get("attempt_id") or "") or None
                active = find_active_case_task(settings.database_path, case_id)
                active_task_id = active["task_id"] if active else None
                if active_task_id == approved_attempt:
                    active_task_id = None
                contexts[case_id] = (approved, approved_attempt, active_task_id)
            approved, approved_attempt, active_task_id = contexts[case_id]
            current = {**task}
            if approved:
                current["current_case_status"] = "approved"
            if approved_attempt == task["task_id"] and task["status"] != "completed":
                current.update(
                    status="completed", progress=100, stage="已批准入库",
                    error_code=None, error_message=None,
                )
            elif (task["status"] in {"failed", "completed"} and active_task_id
                    and active_task_id != task["task_id"]
                    and not task["payload"].get("evidence_revision")):
                current["current_active_task_id"] = active_task_id
            projected.append(current)
        return projected

    def case_capability() -> dict[str, Any]:
        return case_analysis_capability(
            settings.case_acquisition_provider,
            qiyun_configured=bool(os.environ.get("QYAPI_APP_ID") and os.environ.get("QYAPI_APP_KEY")),
        )

    throttle = LoginThrottle()
    migrations_path = settings.console_root / "migrations"
    static_path = settings.console_root / "static"
    index_path = static_path / "index.html"
    task_runner = CaseTaskRunner(settings)
    customer_task_runner = CustomerTaskRunner(settings)
    speaker_task_runner = SpeakerTaskRunner(settings)
    background_task_runner = BackgroundTaskRunner(settings)

    def auto_handoff_confirmed_speaker_drafts(
        business_id: str,
        *,
        created_by_user_id: int,
    ) -> dict[str, Any]:
        outcome: dict[str, Any] = {
            "started": [],
            "existing": [],
            "failed": [],
        }
        for speaker in list_speakers(settings, business_id):
            if not speaker.get("human_confirmed_discovery"):
                continue
            if speaker.get("status") != "analysis_pending":
                continue
            speaker_id = str(speaker["speaker_id"])
            active = find_active_speaker_task(
                settings.database_path,
                speaker_id,
            )
            if active is not None:
                outcome["existing"].append(active)
                try:
                    record_speaker_auto_handoff_status(
                        settings,
                        business_id=business_id,
                        speaker_id=speaker_id,
                        status="analysis_pending",
                        task_id=active["task_id"],
                    )
                except Exception:
                    pass
                continue
            try:
                # The approval command already holds the Business/backup barrier.
                prepared = prepare_speaker_draft_analysis(settings, business_id=business_id, speaker_id=speaker_id)
                task = create_speaker_task(
                    settings.database_path,
                    business_id=business_id,
                    speaker_id=speaker_id,
                    intake_id=prepared["intake_id"],
                    request_path=prepared["request_path"],
                    speaker_name=prepared["speaker_name"],
                    public_role=prepared["public_role"],
                    created_by_user_id=created_by_user_id,
                    queue_max=settings.task_queue_max,
                )
                try:
                    record_speaker_auto_handoff_status(
                        settings,
                        business_id=business_id,
                        speaker_id=speaker_id,
                        status="analysis_pending",
                        task_id=task["task_id"],
                    )
                except Exception:
                    pass
                speaker_task_runner.schedule(task["task_id"])
                outcome["started"].append(task)
            except Exception as exc:
                code = str(getattr(exc, "code", "SPEAKER_AUTO_HANDOFF_FAILED"))
                try:
                    record_speaker_auto_handoff_status(
                        settings,
                        business_id=business_id,
                        speaker_id=speaker_id,
                        status="retry_required",
                        error_code=code,
                    )
                except Exception:
                    pass
                outcome["failed"].append(
                    {"speaker_id": speaker_id, "error_code": code}
                )
        outcome["task_count"] = len(outcome["started"]) + len(
            outcome["existing"]
        )
        return outcome

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
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif (request.url.path.startswith("/assets/")
              and request.url.path.lower().endswith((".css", ".js", ".mjs"))):
            response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        return response

    from delivery_receipt_recovery_v1 import ReceiptRecoveryError
    from generation_recovery_v1 import RecoveryError

    @app.exception_handler(RecoveryError)
    async def recovery_lineage_error_handler(_: Request, exc: RecoveryError):
        return JSONResponse(status_code=409,content={'detail':error_detail(exc.code,'原操作的来源或文件身份已变化。','请保留原记录并重新核对来源，不会自动继续审核或导出。')})

    @app.exception_handler(ReceiptRecoveryError)
    async def receipt_recovery_error_handler(_: Request, exc: ReceiptRecoveryError):
        return JSONResponse(status_code=403 if exc.code in {'DELIVERY_AUTHORIZATION_REQUIRED','DELIVERY_ACTOR_CONFLICT'} else 409,
            content={'detail':error_detail(exc.code,'原操作的来源、授权或文件尚未通过核对。',
                '请保留原文件，使用原审核身份核对当前来源；不会自动批准或交付。')})

    @app.exception_handler(CanonicalOperationError)
    async def canonical_error_handler(
        _: Request, exc: CanonicalOperationError
    ) -> JSONResponse:
        status_code = 404 if exc.code in {"CASE_OBJECT_NOT_FOUND", "CASE_NOT_FOUND", "CUSTOMER_NOT_FOUND", "SPEAKER_NOT_FOUND"} else 422 if exc.code in {"INVALID_BUSINESS_ID", "INVALID_SPEAKER_ID", "GENERATION_RECOVERY_SCHEMA_INVALID"} else 403 if exc.code in {"DELIVERY_AUTHORIZATION_REQUIRED","DELIVERY_ACTOR_CONFLICT","CASE_REVIEWER_REQUIRED", "BUSINESS_SCOPE_REVIEWER_REQUIRED", "NOVEL_NEWS_NOT_AVAILABLE", "REVIEW_ACTOR_MISMATCH", "GENERATION_RECOVERY_AUTHORIZATION_REQUIRED"} else 409 if exc.code in {
            'DELIVERY_SOURCE_CHANGED','DELIVERY_INTENT_CONFLICT','HUMAN_BUNDLE_INVALID','EXPORT_PUBLICATION_INVALID','EXPORT_LEGACY_UNBOUND_ORPHAN',
            "GENERATION_RECOVERY_CONFLICT", "GENERATION_RECOVERY_GRAPH_INVALID", "GENERATION_RECOVERY_SOURCE_CHANGED",
            "GENERATION_RECOVERY_SCOPE_UNSUPPORTED", "GENERATION_RECOVERY_OUTCOME_UNKNOWN", "GENERATION_RECOVERY_PENDING",
            "GENERATION_BATCH_NOT_REVIEWABLE",
            "GENERATION_IDEMPOTENCY_CONFLICT",
            "EXPORT_ALREADY_CLOSED",
            "SPEAKER_BUSINESS_LINEAGE_MISMATCH",
            "LEGACY_SCOPE_REVIEW_BLOCKED", "PERSONA_APPROVAL_BLOCKED", "PERSONA_AMENDMENT_BLOCKED", "SCALAR_FACT_CONFLICT",
            "CASE_DISPLAY_CONFLICT",
            "CUSTOMER_CONFIRMATION_STALE", "CUSTOMER_CONFIRMATION_PENDING", "CUSTOMER_CONFIRMATION_REQUIRED",
            "CUSTOMER_PREVIEW_BLOCKED", "FACT_REVIEW_DECISION_IMMUTABLE", "REVIEW_COMMIT_CONFLICT",
            "SPEAKER_PREPARATION_REQUIRED", "SPEAKER_REVIEW_INCOMPLETE",
            "SPEAKER_CONFIRMATION_STALE", "SPEAKER_CONFIRMATION_PENDING", "SPEAKER_CONFIRMATION_REQUIRED",
            "SPEAKER_REVIEW_UNKNOWN_CANDIDATE", "SPEAKER_PREVIEW_BLOCKED",
            "REVIEW_CONTEXT_STALE", "REVIEW_CONTEXT_REQUIRED", "REVIEW_REPLAY_CONFLICT", "INVALID_REVIEW_CONTEXT",
            "OPERATION_IN_PROGRESS",
            "AUTHORITY_CHANGED_REFRESH_REQUIRED",
            "CONFIGURED_CUSTOMER_NOT_FOUND",
            "CURRENT_CUSTOMER_REQUIRED",
            "CASE_ALREADY_APPROVED",
            "APPROVED_CASE_IMMUTABLE",
            "CASE_REVIEW_NOT_READY",
            "CASE_APPROVAL_BLOCKED",
            "CASE_SOURCE_GOVERNANCE_BLOCKED",
            "CASE_APPROVAL_RECOVERY_REQUIRED",
            "CASE_EVIDENCE_REVIEW_REQUIRED", "CASE_EVIDENCE_REVIEW_NOT_REQUIRED",
            "CASE_EVIDENCE_REVIEW_INCOMPLETE", "CASE_EVIDENCE_REVIEW_STALE", "CASE_EVIDENCE_REVIEW_CONFLICT", "CASE_QUALITY_DECISION_REQUIRED",
            "REVIEW_COMMIT_CONFLICT", "REVIEW_COMMIT_BINDING_REQUIRED",
            "CASE_PROFILE_ANNOTATION_BLOCKED",
            "CASE_INDUSTRY_ANNOTATION_BLOCKED",
            "CASE_CLASSIFICATION_CONFLICT",
            "CASE_CLASSIFICATION_INVALID",
            "CONTENT_PLAN_SOURCE_COVERAGE_UNSUPPORTED",
            "PERSONA_LACKS_PATTERN_CAPABILITY",
            "NO_APPROVED_PATTERN_FOR_PROFILE",
            "NO_PATTERN_SUPPORTED_CASE",
            "CASE_PROFILE_COMPATIBILITY_NOT_APPROVED",
            "NO_APPROVED_COMPATIBLE_CASE",
        } else 503
        if exc.code.startswith('CASE_REVISION_') or exc.code in {'CASE_EVIDENCE_SCOPE_STALE','CASE_EVIDENCE_SCOPE_UNAVAILABLE','CASE_EVIDENCE_RISK_UNRESOLVED'}:
            status_code = 422 if exc.code in {'CASE_REVISION_ID_INVALID','CASE_REVISION_EDIT_INVALID','CASE_REVISION_SEGMENT_INVALID',
                'CASE_REVISION_BOUNDARY_INVALID','CASE_REVISION_TIMELINE_INVALID'} else 409
        if exc.code.startswith('CASE_SHARE_'):
            status_code = 503 if exc.code=='CASE_SHARE_PUBLICATION_PENDING' else 409
        if exc.code.startswith(('PUBLISH_COPY_', 'LEDGER_HISTORY_')):
            status_code = 503 if exc.code in {'PUBLISH_COPY_DISABLED','PUBLISH_COPY_OPERATION_UNAVAILABLE'} else 409
        if exc.code.startswith('CREATIVE_STYLE_'):
            status_code = 409
        if exc.code.startswith(('CREATION_BATCH_', 'CONTENT_INTENT_', 'CONTENT_RESERVATION_')):
            status_code = 409
        detail = error_detail(exc.code, exc.message, exc.next_action)
        detail.update(exc.details)
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
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
                    {"TASK_QUEUE_FULL":"任务队列已满，请稍后继续原操作。",
                     "GPU_PENDING_LIMIT_REACHED":"你已有多条待执行任务，请等待现有任务后继续。",
                     "OPERATION_ALREADY_ACTIVE":"已有相同业务的任务正在处理，请查看原任务。"}.get(exc.code, str(exc)),
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
        allow_pending_review: bool = False,
        **kwargs: Any,
    ) -> Any:
        parent_business = identity.split(':',1)[0] if scope=='persona' and ':' in identity else kwargs.get('business_id') if scope=='persona' else None
        def guard_pending(business_id):
            if not allow_pending_review:
                from .customer_confirmation import guard
                guard(settings,business_id)
        if scope == "persona" and parent_business:
            # Business approval and dependent Speaker writes share the same order.
            with authority_operation_lock(settings, "business", parent_business, timeout_seconds=0.0):
                guard_pending(parent_business)
                if ':' in identity:
                    from .speaker_confirmation import guard as speaker_guard
                    speaker_guard(settings, identity.split(':',1)[1])
                with operation_lock(settings.pipeline_root, f"{scope}:{identity}", timeout_seconds=0.0):
                    return operation(*args, **kwargs)
        with authority_operation_lock(settings, scope, identity, timeout_seconds=0.0):
            if scope=='business':guard_pending(identity)
            return operation(*args, **kwargs)

    from . import review_commands, persona_review_gateway

    def review_command(kind, identity, session, payload, request_path, execute, *, business_id=None, preflight=None):
        review_commands.reject_borrowed_context(payload.review_context,{"actor":case_principal(settings,int(session.user["id"]))})
        intent_payload=payload.model_dump(exclude={"review_context"},exclude_none=True)
        # In the revision contract null is an explicit CAS against the original
        # head. Preserve it in durable recovery; legacy payload encoding stays v1.
        if 'expected_revision_sha256' in type(payload).model_fields:
            intent_payload['expected_revision_sha256']=payload.expected_revision_sha256
        if getattr(payload,'sharing_decision',None) is not None:
            intent_payload['sharing_decision']=payload.sharing_decision.model_dump()
        def perform():
            command = review_commands.begin(settings, kind, identity, int(session.user["id"]),
                payload.review_context, {"request_path": request_path,
                    "payload": intent_payload}, business_id=business_id, validate_only=preflight is not None)
            joint=kind=='case' and command['context']['version']==review_commands.JOINT_CASE_VERSION and intent_payload.get('decision')=='approve'
            if joint and command['result'] is not None:
                reviewer_authorization(settings,case_principal(settings,int(session.user['id'])))
                approved=review_commands.committed_case_result(settings,command)
                return review_commands.present_joint(settings,review_commands.validate_joint_result(settings,command,approved))
            if kind == "case":
                recovered = review_commands.committed_case_result(settings, command)
                if recovered is not None:
                    if joint:
                        return review_commands.present_joint(settings,review_commands.complete_joint(settings,command,recovered))
                    return review_commands.finish(command, recovered)
            coordinated = (kind == 'business' and command['context']['version'] in {review_commands.BUSINESS_VERSION,review_commands.CUSTOMER_SPEAKER_VERSION}
                or kind == 'speaker' and command['context']['version'] == review_commands.SPEAKER_VERSION)
            if command["result"] is not None and not coordinated:
                if command["result"].get("status") == "cancelled_before_commit":
                    raise review_commands.blocked("REVIEW_REPLAY_CONFLICT", "这次未保存的提交已取消，请重新核对后提交。")
                return command["result"]
            if preflight is not None and not command["saved"]:
                preflight(command)
                command = review_commands.begin(settings, kind, identity, int(session.user["id"]), payload.review_context,
                    {"request_path": request_path, "payload": intent_payload}, business_id=business_id)
            if joint:
                from .case_shared_display import validate_sharing_decision
                validate_sharing_decision(settings,command,intent_payload.get('sharing_decision'))
            executed=execute(command)
            if coordinated:
                return executed  # The existing Business owners close their exact staged operation.
            if joint:
                return review_commands.present_joint(settings,review_commands.complete_joint(settings,command,executed))
            return review_commands.finish(command, executed)
        return locked_authority_call("case" if kind == "case" else "business",
            identity if kind != "speaker" else business_id, perform,allow_pending_review=True)

    @app.get("/api/review-commands/{kind}/{identity}")
    def pending_review_commands(kind: Literal["case", "business", "speaker"], identity: str,
            session: SessionContext = Depends(require_console_access)):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identity):
            raise HTTPException(404)
        if kind == "case" and not is_reviewer(settings, int(session.user["id"])):
            return {"operations": []}
        if kind == "case":
            return {"operations": locked_authority_call("case", identity, review_commands.pending,
                settings, kind, identity, int(session.user["id"]))}
        return {"operations": review_commands.pending(settings, kind, identity, int(session.user["id"]))}

    @app.post('/api/profile-compatibility/preview')
    def profile_compatibility_preview(payload: dict[str, Any],
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token')):
        require_csrf(session, x_csrf_token)
        from . import profile_compatibility_gateway as compatibility
        from profile_compatibility_contract_v1_1 import CompatibilityError
        if set(payload) != {'operation_id', 'decisions'}:
            raise HTTPException(422, detail='需要明确的审核操作和逐项目标。')
        try:
            return compatibility.preview(settings, int(session.user['id']), payload['operation_id'], payload['decisions'])
        except CompatibilityError as exc:
            raise HTTPException(409, detail=error_detail(exc.code, str(exc), '请检查独立审核授权、资料版本和 Pattern 范围后重新核对。')) from exc

    @app.post('/api/profile-compatibility/confirm')
    def profile_compatibility_confirm(payload: dict[str, Any],
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token')):
        require_csrf(session, x_csrf_token)
        from . import profile_compatibility_gateway as compatibility
        from profile_compatibility_contract_v1_1 import CompatibilityError
        if set(payload) != {'operation_id', 'preview_sha256'}:
            raise HTTPException(422, detail='需要当前预览和明确确认。')
        try:
            return compatibility.confirm(settings, int(session.user['id']), payload['operation_id'], payload['preview_sha256'])
        except CompatibilityError as exc:
            raise HTTPException(409, detail=error_detail(exc.code, str(exc), '请刷新并重新核对；已保存的独立记录会保留。')) from exc

    @app.post("/api/customers/{business_id}/review-amendments")
    def amend_business_review(business_id: str, payload: PersonaAmendmentRequest,
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
        require_csrf(session, x_csrf_token)
        return review_command("business", business_id, session, payload,
            f"/api/customers/{business_id}/review-amendments",
            lambda command: persona_review_gateway.amend(settings, command, "business", business_id,
                business_id, payload.action, payload.reason, payload.changes))

    @app.post("/api/review-commands/{kind}/{identity}/{operation_id}/cancel")
    def cancel_uncommitted_review(kind: Literal["case", "business", "speaker"], identity: str, operation_id: str,
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
        require_csrf(session, x_csrf_token)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identity) or not re.fullmatch(r"[a-f0-9]{32}", operation_id):
            raise HTTPException(404)
        if kind == "case": reviewer_authorization(settings, case_principal(settings, int(session.user["id"])))
        operations = review_commands.pending(settings, kind, identity, int(session.user["id"]))
        operation = next((v for v in operations if v["operation_id"] == operation_id), None)
        if not operation: raise HTTPException(404)
        from human_review_operations_v1 import read, write_once
        directory = settings.pipeline_root / "data/review_operations" / kind / identity / operation_id
        value = read(directory / "intent.json")
        def cancel():
            if not review_commands.can_discard(settings, directory, value):
                raise review_commands.blocked(message="这次操作已有保存结果，必须继续恢复，不能取消历史决定。")
            result = {"status": "cancelled_before_commit"}
            write_once(directory / "result.json", result)
            return result
        return locked_authority_call("case" if kind == "case" else "business",
            value["context"]["business_id"] if kind == "speaker" else identity, cancel,allow_pending_review=True)

    @app.post("/api/customers/{business_id}/speakers/{speaker_id}/review-amendments")
    def amend_speaker_review(business_id: str, speaker_id: str, payload: PersonaAmendmentRequest,
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
        require_csrf(session, x_csrf_token)
        return review_command("speaker", speaker_id, session, payload,
            f"/api/customers/{business_id}/speakers/{speaker_id}/review-amendments",
            lambda command: persona_review_gateway.amend(settings, command, "speaker", speaker_id,
                business_id, payload.action, payload.reason, payload.changes), business_id=business_id)

    def visible_case_task(task, user_id):
        """Private Case scope and duplicate/current-attempt links never bypass access."""
        result=safe_case_task(settings,user_id,project_case_task_statuses([task])[0])
        active=result.get("current_active_task_id")
        if active and not can_read_task(settings,user_id,get_task(settings.database_path,active)):
            result.pop("current_active_task_id",None)
        if result.get("task_type")=="case_analysis":
            result={**result,"payload":dict(result.get("payload") or {})}
            if not (can_read_private_case(settings,user_id,str(result.get("subject_ref") or ""))
                    or shared_projection(settings,str(result.get("subject_ref") or ""))):
                result.pop("current_case_status",None)
        return result

    def visible_tasks(user_id,limit=50):
        rows=list_tasks(settings.database_path,limit=limit,case_actor_user_id=user_id,
                        case_reviewer=is_reviewer(settings,user_id))
        return [visible_case_task(task,user_id) for task in rows if can_read_task(settings,user_id,task)]

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
        using_configured_default = not (
            business_id and business_id.strip()
        )
        selected_business_id = (
            business_id.strip()
            if business_id and business_id.strip()
            else settings.default_business_id
        )
        if not selected_business_id:
            raise CanonicalOperationError(
                "CURRENT_CUSTOMER_REQUIRED",
                "当前请求没有指定客户。",
                "请显式提供 business_id，或从客户列表选择客户。",
            )
        if using_configured_default:
            customer_ids = {
                str(customer.get("business_id") or "")
                for customer in list_customers(settings)
            }
            if selected_business_id not in customer_ids:
                raise CanonicalOperationError(
                    "CONFIGURED_CUSTOMER_NOT_FOUND",
                    "配置的默认客户不存在。",
                    "请移除或修正 AIVO_DEFAULT_BUSINESS_ID。",
                )
        return get_customer_status(settings, selected_business_id)

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

        speakers = list_speakers(
            settings,
            business_id,
        )

        for speaker in speakers:
            speaker["submitted_by"] = original_task_actor(settings.database_path, "speaker_analysis", speaker["speaker_id"]) or speaker.get("submitted_by")
            task = latest_subject_task(
                settings.database_path,
                "speaker_analysis",
                speaker["speaker_id"],
                intake_id=speaker.get("latest_intake_id"),
            )

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
            "analysis_allowed": business_persona_approved,
            "blocker": (
                None
                if business_persona_approved
                else "BUSINESS_PERSONA_NOT_APPROVED_FOR_ANALYSIS"
            ),
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
            created_by={"user_id": int(session.user["id"]), "phone": str(session.user["phone"])},
        )

        speaker_id = prepared["speaker_id"]

        if prepared.get("draft_saved"):
            return {
                "duplicate": False,
                "draft_saved": True,
                "business_id": business_id,
                "speaker_id": speaker_id,
                "state": "pending_customer_profile",
                "next_action": "客户档案确认后，可以继续确认这位出镜人的资料。",
            }

        active = find_active_speaker_task(
            settings.database_path,
            speaker_id,
        )

        if active is not None:
            return {
                "input_differs": bool(prepared.get("input_differs")),
                "materials_saved": not bool(prepared.get("input_differs")),
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
                "input_differs": bool(prepared.get("input_differs")),
                "materials_saved": not bool(prepared.get("input_differs")),
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

    @app.post(
        "/api/customers/{business_id}/speakers/{speaker_id}/analyze"
    )
    def analyze_saved_speaker_draft(
        business_id: str,
        speaker_id: str,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        active = find_active_speaker_task(settings.database_path, speaker_id)
        if active is not None:
            return {"started": False, "existing_task": active}
        prepared = locked_authority_call(
            "persona",
            speaker_id,
            prepare_speaker_draft_analysis,
            settings,
            business_id=business_id,
            speaker_id=speaker_id,
        )
        task = create_speaker_task(
            settings.database_path,
            business_id=business_id,
            speaker_id=speaker_id,
            intake_id=prepared["intake_id"],
            request_path=prepared["request_path"],
            speaker_name=prepared["speaker_name"],
            public_role=prepared["public_role"],
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
        )
        speaker_task_runner.schedule(task["task_id"])
        return {"started": True, "task": task}

    @app.get("/api/customers/{business_id}/speakers/{speaker_id}")
    def speaker_detail(
        business_id: str,
        speaker_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        detail = get_speaker_detail(
            settings,
            business_id,
            speaker_id,
        )
        detail["submitted_by"] = original_task_actor(settings.database_path, "speaker_analysis", speaker_id) or detail.get("submitted_by")
        detail["reviewed_by"] = ({"phone": str(detail["fact_review"]["reviewer"])}
            if (detail.get("fact_review") or {}).get("reviewer") else None)
        detail["approved_by"] = persona_approval_actor(settings.pipeline_root, detail.get("speaker_persona"))

        latest_task = latest_subject_task(
            settings.database_path,
            "speaker_analysis",
            speaker_id,
            intake_id=detail.get("latest_intake_id"),
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

        detail["approval_context"] = review_commands.issue(settings, "speaker", speaker_id, int(session.user["id"]), business_id=business_id)
        detail['unified_confirmation_enabled'] = detail['status'] in {'fact_review_required','persona_review_required'}
        if detail['unified_confirmation_enabled']:
            from .speaker_confirmation import review_policy, sourced_scope
            from .speaker_gateway import _latest_intake_dir
            from human_review_operations_v1 import read
            intake = _latest_intake_dir(settings, business_id, speaker_id)
            candidates = read(intake/'speaker_fact_candidates_v1.json') if intake else {}
            source = read(intake/'speaker_intake_v1.json') if intake else {}
            policies = {v['fact_candidate_id']:review_policy(v,
                source_verified=sourced_scope(v, candidates, source, business_id, speaker_id))
                for v in candidates.get('fact_candidates',[])}
            for item in detail['fact_candidates']:
                item.update(policies.get(item['candidate_id'],{}))
        from persona_review_lifecycle_v1 import amendable_fields
        detail["amendable_fields"] = amendable_fields("speaker")
        return detail

    @app.post("/api/customers/{business_id}/speakers/{speaker_id}/revalidation/review")
    def review_speaker_business_update(business_id: str, speaker_id: str, payload: SpeakerRevalidationRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access)) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        return locked_authority_call("persona", f"{business_id}:{speaker_id}", revalidate_speaker_business, settings,
            business_id=business_id, speaker_id=speaker_id, confirmed=payload.confirmed,
            business_sha256=payload.business_sha256, speaker_sha256=payload.speaker_sha256,
            reviewer=str(session.user["phone"]), note=payload.note)

    @app.post('/api/customers/{business_id}/speakers/{speaker_id}/review-preview')
    def preview_speaker_confirmation(business_id: str, speaker_id: str, payload: SpeakerFinalPreviewRequest,
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token')):
        require_csrf(session, x_csrf_token)
        from . import speaker_confirmation
        def prepare():
            try:
                return speaker_confirmation.preview(settings,business_id,speaker_id,int(session.user['id']),
                    str(session.user['phone']),payload.model_dump(exclude_none=True))
            except (RuntimeError, ValueError) as exc:
                if isinstance(exc, CanonicalOperationError):raise
                raise speaker_confirmation.fail('SPEAKER_PREVIEW_BLOCKED','暂不能建立人物确认范围：'+str(exc)) from exc
        return locked_authority_call('persona',f'{business_id}:{speaker_id}',prepare)

    @app.post('/api/customers/{business_id}/speakers/{speaker_id}/confirm')
    def confirm_speaker_profile(business_id: str, speaker_id: str, payload: SpeakerFinalConfirmationRequest,
            session: SessionContext = Depends(require_console_access),
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token')):
        require_csrf(session,x_csrf_token)
        from . import speaker_confirmation
        def preflight(command):
            if command['context']['version'] != review_commands.SPEAKER_VERSION:
                raise speaker_confirmation.fail('SPEAKER_CONFIRMATION_REQUIRED','请使用当前人物资料的准确确认范围。')
            speaker_confirmation.validate_decision({**command,'intent':payload.model_dump(exclude={'review_context'})})
        try:
            result=review_command('speaker',speaker_id,session,payload,
                f'/api/customers/{business_id}/speakers/{speaker_id}/confirm',
                lambda command:speaker_confirmation.execute(settings,command,str(session.user['phone'])),
                business_id=business_id,preflight=preflight)
        except OSError as exc:
            raise CanonicalOperationError('SPEAKER_CONFIRMATION_INTERRUPTED','出镜人确认尚未完成，已保存记录会保留。',
                '请查看当前状态并继续原操作；不会重复审核或批准。') from exc
        return {'execution':result,'speaker':get_speaker_detail(settings,business_id,speaker_id)}

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
        require_csrf(session, x_csrf_token)
        def execute(command):
            result = review_speaker_facts(settings, business_id=business_id, speaker_id=speaker_id,
                intake_id=command["context"]["snapshot"]["intake_id"],
                decisions=[item.model_dump(exclude_none=True) for item in payload.decisions],
                reviewer=str(session.user["phone"]), note=payload.note)
            mark_speaker_task_reviewed(settings.database_path, speaker_id)
            return {"review": result}
        return review_command("speaker", speaker_id, session, payload,
            f"/api/customers/{business_id}/speakers/{speaker_id}/facts/review", execute, business_id=business_id)

    @app.post(
        "/api/customers/{business_id}/speakers/{speaker_id}/gaps/supplement"
    )
    def supplement_speaker_gaps(
        business_id: str,
        speaker_id: str,
        payload: SpeakerGapSupplementRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        active = find_active_speaker_task(settings.database_path, speaker_id)
        if active is not None:
            return {"started": False, "existing_task": active}
        prepared = locked_authority_call(
            "persona",
            f"{business_id}:{speaker_id}",
            prepare_speaker_gap_supplement_request,
            settings,
            business_id=business_id,
            speaker_id=speaker_id,
            answers=payload.answers,
            created_by_user_id=int(session.user["id"]),
            created_by_phone=str(session.user["phone"]),
        )
        task = create_speaker_task(
            settings.database_path,
            business_id=business_id,
            speaker_id=speaker_id,
            intake_id=prepared["intake_id"],
            request_path=prepared["request_path"],
            speaker_name=prepared["speaker_name"],
            public_role=prepared["public_role"],
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
        )
        speaker_task_runner.schedule(task["task_id"])
        return {"started": True, "task": task}

    @app.post(
        "/api/customers/{business_id}/speakers/{speaker_id}/readiness/recheck"
    )
    def recheck_existing_speaker_facts(
        business_id: str,
        speaker_id: str,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        result = locked_authority_call(
            "persona",
            f"{business_id}:{speaker_id}",
            recheck_speaker_readiness,
            settings,
            business_id=business_id,
            speaker_id=speaker_id,
            reviewer=str(session.user["phone"]),
        )
        return {"recheck": result}

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
        require_csrf(session, x_csrf_token)
        def execute(command):
            persona_review_gateway.approve(settings, command, "speaker", speaker_id, business_id,
                str(session.user["phone"]), payload.note.strip() or "Internal Console Human Review approved the Speaker Persona.")
            return {"speaker": get_speaker_detail(settings, business_id, speaker_id)}
        return review_command("speaker", speaker_id, session, payload,
            f"/api/customers/{business_id}/speakers/{speaker_id}/persona/approve", execute, business_id=business_id)

    @app.get("/api/create/options")
    def creation_options(
        session: SessionContext = Depends(require_console_access),
        business_id: str | None = None,
    ) -> dict[str, Any]:
        projection = list_creation_options(settings, business_id=business_id) if business_id else list_creation_options(settings)
        projection["novel_news"] = {
            "available": novel_news_available(settings, str(session.user["phone"])),
            "verification_badge": settings.novel_news_rollout == "validation",
        }
        return projection

    @app.get("/api/create/active-request")
    def active_generation_request(
        business_id: str,
        profile: Literal["mix", "news"] = "mix",
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        if profile == "news":
            if not novel_news_available(settings, str(session.user["phone"])):
                return {"active_request": None, "novel_news_unavailable": True}
            return get_active_generation_request(settings, business_id, profile)
        return get_active_generation_request(settings, business_id)

    @app.get("/api/create/request-context")
    def creation_request_context(
        request_id: str,
        mode: Literal["mix", "repurpose", "novel"] | None = None,
        business_id: str | None = None,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
        return request_navigation_context(settings, request_id, mode, business_id)

    @app.post("/api/create/novel-news/preview")
    def novel_news_preview_route(
        payload: NewsPreviewRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        require_novel_news(settings, str(session.user["phone"]))
        return {"projection": preview_novel_news(settings, payload.business_id, payload.speaker_id)}

    @app.get("/api/create/novel-news/{request_id}/state")
    def novel_news_state_route(
        request_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        if not novel_news_available(settings, str(session.user["phone"])):
            return {"state": {"stage": "unavailable", "message": "该能力当前未开放；已有记录仍会保留。"}}
        return {"state": novel_news_state(settings, request_id)}

    @app.post("/api/create/novel-news/{request_id}/generate")
    def novel_news_generate_route(
        request_id: str,
        payload: NovelNewsGenerateRequest | None = None,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        require_novel_news(settings, str(session.user["phone"]))
        from .novel_news_generation_gateway import submit
        result = submit(settings, request_id, int(session.user['id']), delivery_authorization(settings, session))
        if result['accepted']:
            background_task_runner.schedule(result['task']['task_id'])
        return result

    @app.post('/api/create/novel-news/{request_id}/retry-generation')
    def novel_news_retry_route(request_id: str, payload: NovelNewsRetryRequest,
        x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
        session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        require_novel_news(settings, str(session.user['phone']))
        from .novel_news_generation_gateway import submit
        result = submit(settings, request_id, int(session.user['id']), delivery_authorization(settings, session),
                        expected_parent=payload.parent_intent_sha256)
        if result['accepted']:
            background_task_runner.schedule(result['task']['task_id'])
        return result

    @app.post("/api/create/novel-news/{request_id}/review")
    def novel_news_review_route(
        request_id: str, payload: NovelNewsReviewRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        require_novel_news(settings, str(session.user["phone"]))
        return {"result": locked_authority_call(
            "request", request_id, review_novel_news, settings, request_id,
            decisions=[item.model_dump() for item in payload.decisions],
            reviewer=str(session.user["phone"]),
        )}

    @app.post("/api/create/novel-news/{request_id}/export")
    def novel_news_export_route(
        request_id: str,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        require_novel_news(settings, str(session.user["phone"]))
        from .news_export_gateway import submit as submit_news_export
        result = locked_authority_call('request', request_id, submit_news_export, settings,
            request_id, int(session.user['id']), delivery_authorization(settings,session), novel=True)
        if result.get('accepted'):
            background_task_runner.schedule(result['task']['task_id'])
        return result

    @app.get("/api/create/novel-news/{request_id}/excel")
    def novel_news_excel_route(
        request_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> FileResponse:
        require_novel_news(settings, str(session.user["phone"]))
        path = novel_news_excel(settings, request_id)
        return FileResponse(
            path=path, filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def require_batch_news(configuration, session):
        quantities = configuration.get('quantities')
        if isinstance(quantities, dict) and quantities.get('novel'):
            require_novel_news(settings, str(session.user['phone']))

    @app.post('/api/create/batches/preview')
    def preview_creation_batch(payload: CreationBatchPreviewRequest,
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        require_batch_news(payload.configuration, session)
        from .creation_batch_gateway import preview
        return {'preview': preview(settings, payload.business_id, payload.speaker_id, payload.configuration,
                                   delivery_authorization(settings, session), payload.operation_id)}

    @app.post('/api/create/batches/confirm')
    def confirm_creation_batch(payload: CreationBatchConfirmRequest,
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        require_batch_news(payload.configuration, session)
        from .creation_batch_gateway import confirm
        with authority_mutation_barrier(settings, timeout_seconds=0.0):
            result = confirm(settings, payload.business_id, payload.speaker_id, payload.configuration,
                             delivery_authorization(settings, session), payload.operation_id, payload.preflight_sha256)
        if settings.background_worker_enabled:
            # The confirmed canonical intent survives a crash before this kick;
            # existing maintenance discovers it without another user confirm.
            from .creation_batch_gateway import advance_batches
            advance_batches(settings)
            background_task_runner.schedule()
        return {'result': result}

    @app.get('/api/create/batches')
    def creation_batch_history(business_id:str,session:SessionContext=Depends(require_console_access)):
        from .creation_batch_gateway import history
        return history(settings,business_id,delivery_authorization(settings,session))

    @app.get('/api/create/batches/{batch_id}')
    def creation_batch_state(batch_id: str, session: SessionContext = Depends(require_console_access)):
        from .creation_batch_gateway import state
        epoch=background_task_runner.batch_read_epoch()
        result=state(settings,batch_id,delivery_authorization(settings,session))
        if settings.background_worker_enabled:
            background_task_runner.note_batch_read(batch_id,epoch,complete=result['completion_proven'])
        return {'state': result}

    @app.post('/api/create/batches/{batch_id}/control')
    def control_creation_batch(batch_id: str, payload: CreationBatchControlRequest,
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        from .creation_batch_gateway import control
        result = control(settings, batch_id, payload.action, delivery_authorization(settings, session), payload.operation_id)
        if payload.action == 'resume' and settings.background_worker_enabled:
            from .creation_batch_gateway import advance_batches
            advance_batches(settings)
            background_task_runner.schedule()
        return {'result': result}

    @app.get('/api/create/batches/{batch_id}/human-options')
    def creation_batch_human_options(batch_id: str,
            scope: Literal['native_content_review', 'publish_copy_confirmation'] = 'native_content_review',
            session: SessionContext = Depends(require_console_access)):
        from .creation_batch_delivery_gateway import owner
        return {'preview': owner(settings, batch_id, 'options', delivery_authorization(settings, session), scope=scope)}

    @app.get('/api/create/batches/{batch_id}/human-commands')
    def creation_batch_human_commands(batch_id: str, session: SessionContext = Depends(require_console_access)):
        from .creation_batch_delivery_gateway import owner
        return {'history': owner(settings, batch_id, 'commands', delivery_authorization(settings, session))}

    @app.post('/api/create/batches/{batch_id}/human-command')
    def creation_batch_human_command(batch_id: str, payload: CreationBatchHumanCommand,
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        from .creation_batch_delivery_gateway import owner
        result = owner(settings, batch_id, 'execute', delivery_authorization(settings, session), **payload.model_dump())
        if settings.background_worker_enabled:
            background_task_runner.request_batch_advance(batch_id)
        return {'result': result}

    @app.post('/api/create/batches/{batch_id}/delivery-preview')
    def creation_batch_delivery_preview(batch_id: str, payload: CreationBatchDeliveryScope,
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        from .creation_batch_delivery_gateway import owner
        return {'preview': owner(settings, batch_id, 'composite-preview', delivery_authorization(settings, session), **payload.model_dump())}

    @app.post('/api/create/batches/{batch_id}/delivery-export')
    def creation_batch_delivery_export(batch_id: str, payload: CreationBatchDeliveryCommand,
            x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        from .creation_batch_delivery_gateway import submit_export
        result = submit_export(settings, batch_id, delivery_authorization(settings, session), **payload.model_dump())
        if result['accepted']: background_task_runner.schedule(result['task']['task_id'])
        return result

    @app.get('/api/create/batches/{batch_id}/deliveries/{delivery_id}/{profile}')
    def creation_batch_delivery_download(batch_id: str, delivery_id: str, profile: Literal['news', 'mix'],
            session: SessionContext = Depends(require_console_access)):
        from .creation_batch_delivery_gateway import owner
        result = owner(settings, batch_id, 'composite-version', delivery_authorization(settings, session), delivery_id=delivery_id)
        file = next((f for f in result['files'] if f['profile'] == profile), None)
        if file is None: raise HTTPException(404, detail={'code': 'CREATION_BATCH_PROFILE_NOT_DELIVERED', 'message': '本版本没有该类型交付文件。'})
        return FileResponse(file['path'], filename=('新闻体' if profile == 'news' else 'Mix') + '_本批创作.xlsx',
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.get('/api/create/configuration/{business_id}')
    def read_creation_configuration(business_id:str,session:SessionContext=Depends(require_console_access)):
        from .creation_configuration import draft
        result=draft(settings,int(session.user['id']),business_id)
        if result.get('operation_id') and result.get('draft'):
            from .creation_batch_gateway import confirmed_configuration
            try:
                confirmed=confirmed_configuration(settings,business_id,delivery_authorization(settings,session),
                    result['operation_id'],result['draft'])
                if confirmed is not None:
                    result['confirmed_batch']=confirmed
            except CanonicalOperationError as exc:
                # An old confirmation cannot grant current authority. Its
                # failure must not make the operator's editable draft unusable.
                result['confirmed_batch']=None
                result['confirmation_blocked']={'code':exc.code}
        return result

    @app.put('/api/create/configuration/{business_id}')
    def save_creation_configuration(business_id:str,payload:CreationConfigurationDraftRequest,
            x_csrf_token:str|None=Header(default=None,alias='X-CSRF-Token'),session:SessionContext=Depends(require_console_access)):
        require_csrf(session,x_csrf_token)
        from .creation_configuration import draft
        return draft(settings,int(session.user['id']),business_id,payload=payload.payload,expected_revision=payload.revision)

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
        if payload.profile == "news":
            require_novel_news(settings, str(session.user["phone"]))

        style_arguments={}
        if payload.creative_style_id is not None:
            style_arguments={'creative_style_id':payload.creative_style_id,'configuration':payload.configuration}
        preview = preview_content_creation(
            settings,
            business_id=(payload.business_id),
            speaker_id=(payload.speaker_id),
            profile=(payload.profile),
            quantity=(payload.quantity),
            **style_arguments,
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
        if payload.profile == "news" or payload.selected_opportunity_id is not None:
            require_novel_news(settings, str(session.user["phone"]))

        # The child operation already owns the business-scoped lock. The shared
        # barrier still prevents an offline backup from racing this mutation.
        with authority_mutation_barrier(settings, timeout_seconds=0.0):
            novel_selection = (
                {"selected_opportunity_id": payload.selected_opportunity_id}
                if payload.selected_opportunity_id is not None else {}
            )
            if payload.creative_style_id is not None:
                novel_selection["creative_style_id"] = payload.creative_style_id
                novel_selection["configuration"] = payload.configuration
                novel_selection["authorization_context"] = delivery_authorization(settings, session)
                novel_selection['style_preflight_sha256'] = payload.style_preflight_sha256
            result = confirm_content_creation(
                settings,
                business_id=(payload.business_id),
                speaker_id=(payload.speaker_id),
                profile=(payload.profile),
                requested_quantity=(payload.requested_quantity),
                confirmed_quantity=(payload.confirmed_quantity),
                idempotency_key=(payload.idempotency_key),
                created_by_user_id=int(session.user["id"]),
                created_by_phone=str(session.user["phone"]),
                **novel_selection,
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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))

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

    @app.post("/api/create/{request_id}/abandon")
    def abandon_generation_request_route(
        request_id: str,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
        result = locked_authority_call(
            "request",
            request_id,
            abandon_generation_request,
            settings,
            request_id=request_id,
            reviewer=str(session.user["phone"]),
        )
        return {"result": result}

    @app.get("/api/create/{request_id}/delivery")
    def content_delivery_state(
        request_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
        task = create_background_task(
            settings,
            operation="script_generation",
            request_id=request_id,
            created_by_user_id=int(session.user["id"]),
        )
        background_task_runner.schedule(task["task_id"])
        return {"accepted": True, "task": task}

    @app.post('/api/create/{request_id}/generation-recovery/preview')
    def preview_generation_retry_route(request_id: str, payload: GenerationRecoveryPreviewRequest,
        x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
        session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        require_if_novel_request(settings, request_id, str(session.user['phone']))
        return locked_authority_call('request', request_id, preview_generation_retry,
            settings, request_id, session, payload.operation_id)

    @app.post('/api/create/{request_id}/generation-recovery/confirm')
    def confirm_generation_retry_route(request_id: str, payload: GenerationRecoveryConfirmRequest,
        x_csrf_token: str | None = Header(default=None, alias='X-CSRF-Token'),
        session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        require_if_novel_request(settings, request_id, str(session.user['phone']))
        task = locked_authority_call('request', request_id, confirm_generation_retry,
            settings, request_id, session, payload.operation_id, payload.preview_sha256)
        background_task_runner.schedule(task['task_id'])
        return {'accepted': True, 'task': task}

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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
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
                authorization_context=delivery_authorization(settings,session),
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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
        completed = completed_mix_export(settings, request_id)
        if completed is not None:
            return completed
        result = locked_authority_call('request', request_id, submit_mix_export, settings, request_id, int(session.user['id']), delivery_authorization(settings,session))
        if result.get('accepted'):
            background_task_runner.schedule(result['task']['task_id'])
        return result

    @app.get("/api/create/{request_id}/exported-excel")
    def download_exported_excel(
        request_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> FileResponse:
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
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
                created_by_user_id=int(session.user["id"]),
                created_by_phone=str(session.user["phone"]),
            )
        }

    @app.get("/api/create/news/{request_id}/delivery")
    def news_delivery_state_route(
        request_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))

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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))

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
        require_if_novel_request(settings, request_id, str(session.user["phone"]))

        from .news_export_gateway import submit as submit_news_export
        result = locked_authority_call('request', request_id, submit_news_export, settings,
            request_id, int(session.user['id']), delivery_authorization(settings,session), novel=False)
        if result.get('accepted'):
            background_task_runner.schedule(result['task']['task_id'])
        return result

    @app.get("/api/create/news/{request_id}/excel")
    def download_news_excel_route(
        request_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> FileResponse:
        require_if_novel_request(settings, request_id, str(session.user["phone"]))
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

    @app.get("/api/dashboard")
    def operations_home(
        session: SessionContext = Depends(require_console_access),
        section: Literal["overview", "attention", "materials", "running", "recent"] = "overview",
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
    ) -> dict[str, Any]:
        return dashboard(settings, int(session.user["id"]), section=section, page=page, page_size=page_size)

    @app.get("/api/workbench")
    def workbench(
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        customers = list_customers(settings)
        configured_business_id = settings.default_business_id
        selected_business_id: str | None = None
        selection_source = "none"
        selection_error: dict[str, str] | None = None

        if configured_business_id:
            configured_customer = next(
                (
                    customer
                    for customer in customers
                    if customer.get("business_id") == configured_business_id
                ),
                None,
            )
            if configured_customer is not None:
                selected_business_id = configured_business_id
                selection_source = "configured_default"
            else:
                selection_error = error_detail(
                    "CONFIGURED_CUSTOMER_NOT_FOUND",
                    "配置的默认客户不存在，工作台未选择任何客户。",
                    "请移除或修正 AIVO_DEFAULT_BUSINESS_ID。",
                )
        elif len(customers) == 1:
            only_customer = next(iter(customers))
            selected_business_id = str(only_customer["business_id"])
            selection_source = "only_customer"
        elif len(customers) > 1:
            selection_error = error_detail(
                "CURRENT_CUSTOMER_REQUIRED",
                "存在多个客户，工作台不会静默选择其中一个。",
                "请从客户列表显式选择客户。",
            )

        status = None
        if selected_business_id:
            try:
                status = get_customer_status(settings, selected_business_id)
            except CanonicalOperationError as exc:
                selection_error = error_detail(
                    exc.code,
                    exc.message,
                    exc.next_action,
                )

        user_id=int(session.user["id"])
        case_query = case_cards(settings,user_id,view="review" if is_reviewer(settings,user_id) else "shared",page_size=50)
        tasks = visible_tasks(user_id,limit=10)
        try:
            creation_options = list_creation_options(settings)
            ready_customer_count = int(
                creation_options.get("ready_customer_count") or 0
            )
            creation_blocker = None
        except CanonicalOperationError as exc:
            ready_customer_count = 0
            creation_blocker = error_detail(
                exc.code,
                exc.message,
                exc.next_action,
            )
        return {
            "has_customers": bool(customers),
            "status": status,
            "customers": customers,
            "summary": {
                "customer_count": len(customers),
                "approved_customer_count": sum(
                    customer.get("status") == "approved" for customer in customers
                ),
                "case_count": case_query["total"],
                "approved_case_count": case_query["status_counts"].get("approved", 0),
                "ready_customer_count": ready_customer_count,
            },
            "customer_selection": {
                "configured_business_id": configured_business_id,
                "selected_business_id": selected_business_id,
                "source": selection_source,
                "error": selection_error,
            },
            "attention": {
                "case_reviews": case_query["status_counts"].get("awaiting_review", 0),
                "persona_reviews": (
                    sum(
                        customer.get("status")
                        in {
                            "fact_review_required",
                            "persona_review_required",
                        }
                        for customer in customers
                    )
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
            "capabilities": {
                "case_analysis": case_capability(),
                "add_case": {
                    "available": True,
                    "path": "/cases/new",
                },
                "new_customer": {
                    "available": True,
                    "path": "/customers/new",
                },
                "content_creation": {
                    "available": ready_customer_count > 0,
                    "path": "/create" if ready_customer_count > 0 else None,
                    "ready_customer_count": ready_customer_count,
                    "blocker": creation_blocker,
                },
            },
        }

    @app.get("/api/customers/operations")
    def customer_operations(
        session: SessionContext = Depends(require_console_access),
        search: str = Query("", max_length=100),
        filter_by: Literal["all", "pending", "ready"] = "all",
        sort_by: Literal["action", "updated"] = "action",
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
    ) -> dict[str, Any]:
        return list_customer_operations(settings, search=search, filter_by=filter_by, sort_by=sort_by, page=page, page_size=page_size, actor_phone=str(session.user["phone"]))

    @app.get("/api/customers/{business_id}/creation-records")
    def customer_creation_records(
        business_id: str,
        _: SessionContext = Depends(require_console_access),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
    ) -> dict[str, Any]:
        customer = get_customer_detail(settings, business_id)
        try:
            rows = creation_record_index(settings).get(business_id, [])
        except (ValueError, OSError, RuntimeError) as exc:
            raise CanonicalOperationError("CREATION_HISTORY_UNAVAILABLE", "创作记录暂时无法可靠读取。", "请查看任务或恢复原记录后重试。") from exc
        return {"customer": {"business_id": business_id, "display_name": customer["display_name"]},
                "records": rows[(page-1)*page_size:page*page_size], "total": len(rows), "page": page, "page_size": page_size}

    @app.get("/api/customers")
    def customers(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        projected = list_customers(settings)

        for customer in projected:
            customer["submitted_by"] = original_task_actor(settings.database_path, "customer_analysis", customer["business_id"]) or customer.get("submitted_by")
            task = latest_subject_task(
                settings.database_path,
                "customer_analysis",
                customer["business_id"],
                intake_id=customer.get("latest_intake_id"),
            )

            if task is None:
                continue

            customer["task"] = task

            if task["status"] in {
                "queued",
                "running",
            }:
                if not (task["payload"].get("discovery_retry_request") or task['payload'].get('speaker_preparation_request')):
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
            "customer-intake-admission",
            prepare_customer_onboarding_request,
            settings,
            customer_name=(payload.customer_name),
            industry=payload.industry,
            materials=payload.materials,
            save_only=payload.save_only, create_separate=payload.create_separate,
            submission_key=payload.submission_key,
            created_by_user_id=int(session.user["id"]),
            created_by_phone=str(session.user["phone"]),
        )

        business_id = prepared["business_id"]

        if payload.save_only:
            return {"saved_only": True, "duplicate": prepared.get("duplicate", False),
                "business_id": business_id, "state": (prepared.get("existing_customer") or {}).get("status", "draft")}
        if prepared.get("existing_customer_check_required") and prepared.get("input_differs"):
            return {**prepared, "state": prepared["existing_customer"]["status"]}

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

    @app.post("/api/customers/{business_id}/gaps/supplement")
    def supplement_customer_gaps(
        business_id: str,
        payload: CustomerGapSupplementRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        def submit_supplement():
            active = find_active_customer_task(settings.database_path, business_id)
            if active is not None:
                return {"supplemented": False, "existing_task": active}
            detail = get_customer_detail(settings, business_id)
            request_path = settings.pipeline_root / "data/customer_intakes" / business_id / str(detail.get("latest_intake_id")) / "customer_onboarding_request_v1.json"
            existing = json.loads(request_path.read_text(encoding="utf-8")) if request_path.is_file() else {}
            answers = [item.model_dump() for item in payload.answers]
            if detail["status"] == "analysis_pending" and existing.get("intake_type") == "gap_supplement" and existing.get("gap_answers") == answers:
                prepared = {**existing, "request_path": str(request_path.resolve())}
            else:
                prepared = prepare_customer_gap_supplement_request(settings,
                    business_id=business_id, answers=answers,
                    created_by_user_id=int(session.user["id"]), created_by_phone=str(session.user["phone"]))
            task = create_customer_task(settings.database_path, business_id=business_id,
                intake_id=prepared["intake_id"], request_path=prepared["request_path"],
                customer_name=prepared["customer_name"], industry=prepared["industry"],
                created_by_user_id=int(session.user["id"]), queue_max=settings.task_queue_max)
            return {"supplemented": True, "business_id": business_id,
                "intake_id": prepared["intake_id"], "target_gaps": prepared["target_gaps"], "task": task}
        result = locked_authority_call("business", business_id, submit_supplement)
        if result.get("task"):
            customer_task_runner.schedule(result["task"]["task_id"])
        return result

    @app.post("/api/customers/{business_id}/intake/recover")
    def recover_saved_customer_source(business_id: str, payload: CustomerSavedSourceRecoveryRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access)) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        def admit_recovery():
            active = find_active_customer_task(settings.database_path, business_id)
            if active is not None:
                return {"recovered": False, "existing_task": active}
            prepared = prepare_saved_source_recovery(settings, business_id=business_id,
                source_intake_id=payload.source_intake_id, targets=payload.targets,
                execution_identity=payload.execution_identity, created_by_user_id=int(session.user["id"]),
                created_by_phone=str(session.user["phone"]))
            if prepared["replayed"]:
                previous = latest_subject_task(settings.database_path, "customer_analysis", business_id,
                    intake_id=prepared["intake_id"])
                if previous is not None:
                    return {"recovered": False, "replayed": True, "existing_task": previous}
            task = create_customer_task(settings.database_path, business_id=business_id,
                intake_id=prepared["intake_id"], request_path=prepared["request_path"],
                customer_name=prepared["customer_name"], industry=prepared["industry"],
                created_by_user_id=int(session.user["id"]), queue_max=settings.task_queue_max)
            return {"recovered": True, "intake_id": prepared["intake_id"], "task": task}
        result = locked_authority_call("business", business_id, admit_recovery)
        if result.get("task"):
            customer_task_runner.schedule(result["task"]["task_id"])
        return result

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

        def admit():
            active = find_active_customer_task(settings.database_path, business_id)
            if active is not None:
                return {"reanalyze": False, "existing_task": active}
            prepared = prepare_customer_reanalysis_request(settings, business_id=business_id,
                customer_name=payload.customer_name, industry=payload.industry, materials=payload.materials)
            task = create_customer_task(settings.database_path, business_id=business_id,
                intake_id=prepared["intake_id"], request_path=prepared["request_path"],
                customer_name=prepared["customer_name"], industry=prepared["industry"],
                created_by_user_id=int(session.user["id"]), queue_max=settings.task_queue_max)
            return {"reanalyze": True, "new_intake": not prepared.get("same_input", False),
                "intake_id": prepared["intake_id"], "task": task}
        result = locked_authority_call("business", business_id, admit)
        if result.get("task"):
            customer_task_runner.schedule(result["task"]["task_id"])
        return result

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

        def admit():
            active = find_active_customer_task(settings.database_path, business_id)
            if active is not None:
                return {"resumed": False, "existing_task": active}
            source = get_customer_input(settings, business_id)
            if not str(source.get("materials") or "").strip():
                raise CanonicalOperationError("CUSTOMER_MATERIALS_REQUIRED", "客户已保存，尚未提供资料。", "请先填写客户资料，再开始整理。")
            task = create_customer_task(settings.database_path, business_id=business_id,
                intake_id=source["intake_id"], request_path=source["request_path"],
                customer_name=source["customer_name"], industry=source["industry"],
                created_by_user_id=int(session.user["id"]), queue_max=settings.task_queue_max)
            return {"resumed": True, "task": task}
        result = locked_authority_call("business", business_id, admit)
        if result.get("task"):
            customer_task_runner.schedule(result["task"]["task_id"])
        return result

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
        speaker_id: str | None = None,
        _: SessionContext = Depends(
            require_console_access
        ),
    ) -> dict[str, Any]:
        return get_content_operations_view(
            settings,
            business_id,
            speaker_id=speaker_id,
        )

    @app.get("/api/customers/{business_id}")
    def customer_detail(
        business_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        detail = get_customer_detail(
            settings,
            business_id,
        )
        detail["submitted_by"] = original_task_actor(settings.database_path, "customer_analysis", business_id) or detail.get("submitted_by")
        detail["reviewed_by"] = ({"phone": str(detail["fact_review"]["reviewer"])}
            if (detail.get("fact_review") or {}).get("reviewer") else None)
        detail["approved_by"] = persona_approval_actor(settings.pipeline_root, detail.get("business_persona"))

        latest_task = latest_subject_task(
            settings.database_path,
            "customer_analysis",
            business_id,
            intake_id=detail.get("latest_intake_id"),
        )

        if latest_task is not None:
            detail["task"] = latest_task

            if latest_task["status"] in {
                "queued",
                "running",
            }:
                if not (latest_task["payload"].get("discovery_retry_request") or latest_task['payload'].get('speaker_preparation_request')):
                    detail["status"] = "analyzing"

            elif (
                latest_task["status"] == "failed"
                and detail["status"] == "analysis_pending"
            ):
                detail["status"] = "failed"

        # Raw Speaker Intake may be collected in parallel. Analysis and
        # Production authority remain gated by the approved Business Persona.
        business_persona = detail.get("business_persona") or {}

        business_persona_approved = business_persona.get("approved") is True

        speakers = list_speakers(
            settings,
            business_id,
        )

        for speaker in speakers:
            task = latest_subject_task(
                settings.database_path,
                "speaker_analysis",
                speaker["speaker_id"],
                intake_id=speaker.get("latest_intake_id"),
            )
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

        detail["speakers"] = speakers

        detail["creation_entry_ready"] = not detail.get("production_constraint_blocked", False) and bool((detail.get("current_business_persona") or business_persona).get("approved")) and any(
            speaker.get("approved_for_current_business", speaker.get("status") == "approved") for speaker in speakers
        )

        detail["approval_context"] = review_commands.issue(settings, "business", business_id, int(session.user["id"]))
        from persona_review_lifecycle_v1 import amendable_fields
        detail["amendable_fields"] = amendable_fields("business")
        detail["media_rights_established"] = False
        detail["review_context"] = customer_review_context(settings, business_id,
            int(session.user["id"]), str(session.user["phone"]))
        detail["unified_confirmation_enabled"] = True
        detail['joint_speaker_confirmation_enabled'] = True

        return detail

    def confirm_discovery_step(business_id, decisions, session, *, lock_held=False):
        try:
            values = [item.model_dump(exclude_none=True) if hasattr(item, 'model_dump') else item for item in decisions]
            if lock_held:
                return confirm_speaker_discovery(settings, business_id=business_id, decisions=values,
                    confirmed_by_user_id=int(session.user['id']), confirmed_by_phone=str(session.user['phone']))
            return locked_authority_call(
                "business",
                business_id,
                confirm_speaker_discovery,
                settings,
                business_id=business_id,
                decisions=values,
                confirmed_by_user_id=int(session.user["id"]),
                confirmed_by_phone=str(session.user["phone"]),
            )
        except (CanonicalOperationError, OSError) as exc:
            return {
                "status": "failed",
                "retry_required": True,
                "error_code": getattr(exc, "code", "SPEAKER_CONFIRMATION_UNAVAILABLE"),
                "message": "客户信息已保存。出镜人资料暂未建立成功，可以继续处理。",
                "drafts": [],
            }

    @app.post("/api/customers/{business_id}/speaker-discovery/retry")
    def retry_person_discovery(business_id: str,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access)) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        def admit():
            active = find_active_customer_task(settings.database_path, business_id,
                include_awaiting_review=False)
            if active is not None:
                return {"existing_task": active}
            prepared = prepare_speaker_discovery_retry(settings, business_id, actor=str(session.user["phone"]))
            if prepared.get("already_available"):
                return prepared
            task = create_customer_task(settings.database_path, **prepared,
                created_by_user_id=int(session.user["id"]), queue_max=settings.task_queue_max)
            return {"task": task}
        result = locked_authority_call("business", business_id, admit)
        if result.get("task"):
            customer_task_runner.schedule(result["task"]["task_id"])
        return result

    @app.post("/api/customers/{business_id}/speaker-discovery/confirm")
    def retry_speaker_discovery_confirmation(
        business_id: str,
        payload: SpeakerDiscoveryConfirmRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        return {
            "speaker_confirmation": confirm_discovery_step(
                business_id, payload.decisions, session
            )
        }

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
        require_csrf(session, x_csrf_token)

        review_commands.reject_borrowed_context(payload.review_context,{"actor_id":int(session.user["id"]),"actor":str(session.user["phone"])})

        def save_customer_step():
            from .customer_confirmation import guard
            guard(settings, business_id)
            submission = None
            if payload.review_context:
                submission = validate_customer_review_context(settings, business_id,
                    payload.review_context, int(session.user["id"]), str(session.user["phone"]),
                    payload.model_dump(exclude_none=True, exclude={"review_context"}))
            else:
                raise CanonicalOperationError("REVIEW_CONTEXT_REQUIRED", "请使用当前审核页面提交，不能省略对象版本。", "请刷新后重新核对。")
            record_speaker_discovery_intent(
                settings,
                business_id=business_id,
                decisions=[
                    item.model_dump(exclude_none=True)
                    for item in payload.speaker_confirmations
                ],
                confirmed_by_user_id=int(session.user["id"]),
                confirmed_by_phone=str(session.user["phone"]),
            )
            try:
                result = review_customer_facts(
                    settings,
                    business_id=business_id,
                    decisions=[item.model_dump(exclude_none=True) for item in payload.decisions],
                    reviewer=str(session.user["phone"]),
                    note=payload.note,
                    industry_review=payload.industry_review,
                    constraint_decisions=payload.constraint_decisions,
                    submission=submission,
                )
            except (CanonicalOperationError, OSError) as exc:
                if not submission:
                    raise
                from customer_fact_review_v1 import read_review_progress
                state = read_review_progress(settings.pipeline_root / "data/customer_intakes" / business_id / submission["intake_id"])
                if not state["receipts"] or (submission.get("operation_id") and not any(v["operation_id"] == submission["operation_id"] for v in state["receipts"])):
                    raise
                return {"status": "review_completion_interrupted", "authority": {"fact_review_completed": False, "persona_approved": False},
                    "saved_count": len(state["decisions"]) + len(state["constraint_decisions"]),
                    "pending_count": len(state["pending_ids"]) + len(state["pending_constraint_ids"]),
                    "recovery_required": True, "error_code": getattr(exc, "code", "REVIEW_COMPLETION_INTERRUPTED")}
            if result.get("authority", {}).get("fact_review_completed") is True:
                mark_customer_task_reviewed(settings.database_path, business_id)
            return result

        result = locked_authority_call(
            "business",
            business_id,
            save_customer_step,
        )

        speaker_confirmation = confirm_discovery_step(
            business_id, payload.speaker_confirmations, session
        )

        return {
            "review": result,
            "speaker_confirmation": speaker_confirmation,
        }

    @app.get("/api/customers/{business_id}/legacy-scope")
    def read_legacy_scope(business_id: str,
        session: SessionContext = Depends(require_console_access)) -> dict[str, Any]:
        return scope_projection(settings, business_id, int(session.user["id"]))

    @app.post("/api/customers/{business_id}/review-preview")
    def preview_customer_confirmation(business_id: str, payload: CustomerFinalPreviewRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        from .customer_confirmation import preview, fail
        from customer_fact_review_v1 import CustomerFactReviewError
        def prepare():
            try:
                if payload.joint_speaker_review:
                    from .customer_speaker_confirmation import preview as joint_preview
                    return joint_preview(settings,business_id,int(session.user['id']),str(session.user['phone']),
                        payload.model_dump(exclude_none=True))
                values=payload.model_dump(exclude_none=True)
                for key in ('joint_speaker_review','business_only','retry_preparation','speaker_fact_decisions'):values.pop(key,None)
                return preview(settings, business_id, int(session.user['id']), str(session.user['phone']),
                    values)
            except CustomerFactReviewError as exc:
                raise fail(exc.code, str(exc)) from exc
            except (ValueError, RuntimeError) as exc:
                if isinstance(exc, CanonicalOperationError):
                    raise
                raise fail('CUSTOMER_PREVIEW_BLOCKED', '暂不能建立最终审核摘要：' + str(exc)) from exc
        return locked_authority_call('business', business_id, prepare)

    @app.post('/api/customers/{business_id}/review-preparation')
    def prepare_customer_speakers(business_id:str,payload:CustomerFinalPreviewRequest,
        x_csrf_token:str|None=Header(default=None,alias='X-CSRF-Token'),
        session:SessionContext=Depends(require_console_access)):
        require_csrf(session,x_csrf_token)
        from .customer_speaker_confirmation import preparation_request,preparation_status,enqueue_preparation
        def admit():
            path,_=preparation_request(settings,business_id,int(session.user['id']),str(session.user['phone']),payload.model_dump(exclude_none=True))
            result=preparation_status(settings,path)
            if result['state']=='prepared':return result
            task=enqueue_preparation(settings,path,business_id,int(session.user['id']),retry=payload.retry_preparation)
            return {**result,'state':'failed' if task['status']=='failed' else 'pending',
                'task':{'task_id':task['task_id'],'status':task['status'],'stage':task['stage']}}
        result=locked_authority_call('business',business_id,admit)
        if result.get('task') and result['state']!='failed':customer_task_runner.schedule(result['task']['task_id'])
        return result

    @app.post("/api/customers/{business_id}/confirm")
    def confirm_customer_profile(business_id: str, payload: CustomerFinalConfirmationRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access)):
        require_csrf(session, x_csrf_token)
        from . import customer_confirmation
        def preflight(command):
            if command['context']['version'] not in {review_commands.BUSINESS_VERSION,review_commands.CUSTOMER_SPEAKER_VERSION}:
                raise customer_confirmation.fail('CUSTOMER_CONFIRMATION_REQUIRED', '请使用本页准确的最终确认摘要。')
            customer_confirmation.validate_decision({**command, 'intent':payload.model_dump(exclude={'review_context'})})
        def execute(command):
            if command['context']['version'] not in {review_commands.BUSINESS_VERSION,review_commands.CUSTOMER_SPEAKER_VERSION}:
                raise customer_confirmation.fail('CUSTOMER_CONFIRMATION_REQUIRED', '旧审核不能替代明确的联合确认。')
            def save_people():
                bundle=command['context']['confirmation']
                if command['context']['version']==review_commands.CUSTOMER_SPEAKER_VERSION:bundle=bundle['business']
                decisions = bundle['review_payload'].get('speaker_confirmations', [])
                record_speaker_discovery_intent(settings, business_id=business_id, decisions=decisions,
                    confirmed_by_user_id=int(session.user['id']), confirmed_by_phone=str(session.user['phone']))
                people = confirm_discovery_step(business_id, decisions, session, lock_held=True)
                from customer_fact_review_v1 import read_review_progress
                intake = settings.pipeline_root/'data/customer_intakes'/business_id/bundle['intake_id']
                if read_review_progress(intake)['complete']:
                    mark_customer_task_reviewed(settings.database_path, business_id)
                return people
            if command['context']['version']==review_commands.CUSTOMER_SPEAKER_VERSION:
                from .customer_speaker_confirmation import execute as execute_joint
                return execute_joint(settings,command,str(session.user['phone']),on_review=save_people)
            return customer_confirmation.execute(settings, command, str(session.user['phone']), on_review=save_people,
                on_approved=lambda:auto_handoff_confirmed_speaker_drafts(business_id, created_by_user_id=int(session.user['id'])))
        try:
            result = review_command('business', business_id, session, payload,
                f'/api/customers/{business_id}/confirm', execute, preflight=preflight)
        except OSError as exc:
            raise CanonicalOperationError('CUSTOMER_CONFIRMATION_INTERRUPTED', '客户确认尚未完成，已保存的记录会保留。',
                '请刷新并继续原操作；不会重复审核、批准或建立出镜人。') from exc
        return {'execution':result, 'customer':get_customer_detail(settings, business_id)}

    @app.post("/api/customers/{business_id}/legacy-scope")
    def adjudicate_legacy_scope(business_id: str, payload: dict[str, Any],
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access)) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        return {"receipt": locked_authority_call("business", business_id, submit_scope,
            settings, business_id, int(session.user["id"]), payload)}

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
        require_csrf(session, x_csrf_token)
        def execute(command):
            persona_review_gateway.approve(settings, command, "business", business_id, business_id,
                str(session.user["phone"]), payload.note.strip() or "Internal Console Human Review approved the Business Persona.")
            return {"customer": get_customer_detail(settings, business_id),
                "speaker_handoff": auto_handoff_confirmed_speaker_drafts(business_id, created_by_user_id=int(session.user["id"]))}
        return review_command("business", business_id, session, payload,
            f"/api/customers/{business_id}/persona/approve", execute)

    @app.post("/api/customers/{business_id}/readiness/recheck")
    def recheck_customer_existing_information(
        business_id: str,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        result = locked_authority_call(
            "business",
            business_id,
            recheck_customer_readiness,
            settings,
            business_id=business_id,
        )
        return {"review": result}

    @app.get("/api/cases")
    def cases(
        session: SessionContext = Depends(require_console_access),
        view: Literal["shared","mine","review"] = "shared",
        search: str = Query("",max_length=120),
        industry: str = Query("",max_length=30),
        video_type: str = Query("",max_length=30),
        status: str = Query("",max_length=40),
        page: int = Query(1,ge=1),
        page_size: int = Query(20,ge=1,le=50),
    ) -> dict[str, Any]:
        return {**case_cards(settings,int(session.user["id"]),view=view,search=search,industry=industry,
            video_type=video_type,status=status,page=page,page_size=page_size),"analysis":case_capability()}

    @app.get("/api/case-library/{case_id}")
    def shared_case_detail(case_id: str, _: SessionContext = Depends(require_console_access)):
        row=shared_projection(settings,case_id)
        if row is None: not_visible()
        return row

    @app.get("/api/case-library/{case_id}/cover")
    def shared_case_cover(case_id: str, _: SessionContext = Depends(require_console_access)):
        if shared_projection(settings,case_id) is None: not_visible()
        path=shared_cover_path(settings,case_id)
        if path is None: not_visible()
        return FileResponse(path,headers={"Cache-Control":"private, no-store"})

    @app.post("/api/cases/{case_id}/publication")
    def publish_case(case_id: str,payload: CasePublicationRequest,
                     session: SessionContext = Depends(require_console_access),
                     x_csrf_token: str | None = Header(default=None,alias="X-CSRF-Token")):
        require_csrf(session,x_csrf_token)
        actor=case_principal(settings,int(session.user["id"]))
        reviewer_authorization(settings,actor)
        return locked_authority_call("case",case_id,change_publication,settings,case_id,
                                     actor=actor,**payload.model_dump())

    @app.post("/api/cases/source-files")
    async def upload_case_source(
        request: Request,
        url: str,
        suffix: str,
        rights_confirmed: bool = False,
        source_match_confirmed: bool = False,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        if len(url) > 4096:
            raise HTTPException(422, detail="来源链接过长。")
        try:
            source = await run_in_threadpool(resolve_douyin_source_input, url)
        except SourceInputError as exc:
            raise HTTPException(422, detail=error_detail(exc.code, exc.message, exc.message)) from exc
        return await receive_upload(
            request, settings, source=source, user=session.user, suffix=suffix,
            rights_confirmed=rights_confirmed, source_match_confirmed=source_match_confirmed,
        )

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
        if payload.source_upload_id:
            # Serialize claim with orphan cleanup. Task insertion separately
            # enforces one task per upload and the existing canonical case identity.
            with operation_lock(settings.pipeline_root, f"source-upload:{payload.source_upload_id}"):
                return submit_case_analysis(payload, int(session.user["id"]))
        return submit_case_analysis(payload, int(session.user["id"]))

    def submit_case_analysis(payload: CaseAnalysisRequest, actor_user_id: int, source_input=None) -> dict[str, Any]:
        try:
            source = source_input or resolve_douyin_source_input(payload.url)
        except SourceInputError as exc:
            raise HTTPException(
                status_code=422,
                detail=error_detail(
                    exc.code,
                    exc.message,
                    exc.message,
                ),
            ) from exc
        normalized_url = source.canonical_url
        case_id = source.video_id
        provider_source_url = (
            source.extracted_url.split("?", 1)[0].split("#", 1)[0]
            if source.extracted_url.startswith("https://v.douyin.com/") else None
        )

        duplicate = resolve_case_source_duplicate(
            settings,
            normalized_url,
        )

        # The task table owns progress and navigation. An older attempt file may
        # still say "running" while a newer task for the same source is active.
        active = find_active_case_task(settings.database_path, case_id)
        if active is not None and not can_read_task(settings,actor_user_id,active):
            return {"duplicate":True,"case_id":case_id,"state":"submitted","message":"投稿已记录，无需重复创建解析任务。"}
        if duplicate is not None and not is_reviewer(settings,actor_user_id):
            prior=get_task(settings.database_path,str(duplicate.get("attempt_id") or ""))
            permitted=can_read_private_case(settings,actor_user_id,case_id) or can_read_task(settings,actor_user_id,prior)
            if not permitted:
                shared=shared_projection(settings,case_id)
                return {"duplicate":True,"case_id":case_id,"state":"approved" if shared else "submitted",
                        "message":"投稿已记录，无需重复创建解析任务。",**({"existing_case":shared} if shared else {})}
        if active is not None and (duplicate is None or duplicate.get("state") != "approved"):
            awaiting_review = active["status"] == "awaiting_review"
            return {
                "duplicate": True,
                "duplicate_kind": "source_identity",
                "state": "awaiting_review" if awaiting_review else "running",
                "case_id": case_id,
                "attempt_id": active["task_id"],
                "existing_task": active,
                "can_reanalyze": False,
                "reanalyze_blocked": bool(payload.reanalyze),
                "message": (
                    "这个视频已经分析完成，正在等待审核。"
                    if awaiting_review else "这个视频正在分析。"
                ),
            }

        if duplicate is None:
            with transaction(settings.database_path) as connection:
                previous = connection.execute(
                    "SELECT task_id,status FROM tasks WHERE task_type='case_analysis' AND subject_ref=? ORDER BY created_at DESC,task_id DESC LIMIT 1",
                    (case_id,),
                ).fetchone()
            if previous and previous["status"] == "failed":
                if not can_read_task(settings,actor_user_id,get_task(settings.database_path,previous["task_id"])):
                    return {"duplicate":True,"case_id":case_id,"state":"submitted","message":"投稿已记录，无需重复创建解析任务。"}
                duplicate = {"duplicate": True, "state": "failed", "case_id": case_id,
                             "attempt_id": previous["task_id"], "message": "这个视频已有失败任务，请恢复原任务。"}

        hint = payload.operator_profile_hint
        if payload.reanalyze and hint is None:
            hint = case_reanalysis_hint(settings.database_path, case_id)
            if hint is None:
                try:
                    hint = get_case_detail(settings, case_id).get("operator_profile_hint")
                except CanonicalOperationError:
                    pass

        def source_upload() -> dict | None:
            if not payload.source_upload_id:
                return None
            return validate_for_submission(settings, payload.source_upload_id, normalized_url, actor_user_id)

        def require_media_provider() -> None:
            if not payload.source_upload_id and settings.case_acquisition_provider == "upload_only":
                raise HTTPException(422, detail=error_detail(
                    "SOURCE_UPLOAD_REQUIRED", "当前需要上传本地视频。", "请上传与来源链接对应的视频文件。",
                ))
            if (not payload.source_upload_id and settings.case_acquisition_provider == "qiyun"
                    and not (os.environ.get("QYAPI_APP_ID") and os.environ.get("QYAPI_APP_KEY"))):
                raise HTTPException(503, detail=error_detail(
                    "SOURCE_PROVIDER_NOT_CONFIGURED", "自动获取视频暂不可用。",
                    "请上传本地视频，或联系管理员配置视频解析服务。",
                ))

        if duplicate is not None:
            state = str(duplicate.get("state") or "")
            if state in {"queued", "running"}:
                raise HTTPException(
                    status_code=409,
                    detail=error_detail(
                        "CASE_TASK_PROGRESS_UNAVAILABLE",
                        "暂时无法恢复这条案例分析进度。",
                        "请到任务记录查看状态；如果没有对应任务，请联系管理员。",
                    ),
                )
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

            prior_task = get_task(settings.database_path, str(duplicate.get("attempt_id"))) if duplicate.get("attempt_id") else None
            prior_industry = (
                (prior_task or {}).get("payload", {}).get("industry")
                or (duplicate.get("existing_case") or {}).get("industry")
                or "待分类"
            )
            require_media_provider()
            task = create_case_task(
                settings.database_path,
                source_url=normalized_url,
                case_id=case_id,
                operator_profile_hint=hint,
                industry=selected_case_industry(payload.industry, str(prior_industry)),
                source_upload=source_upload(),
                acquisition_provider=settings.case_acquisition_provider,
                provider_source_url=provider_source_url,
                reanalyze=True,
                reason=reason,
                created_by_user_id=actor_user_id,
                queue_max=settings.task_queue_max,
                gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
            )
            task_runner.schedule(task["task_id"])

            record_submission(settings,actor_user_id,task=task)

            return {
                "duplicate": False,
                "reanalyze": True,
                "task": task,
                "case_id": case_id,
                "next_action": ("新的分析 Attempt 已建立；" "原有分析记录不会被覆盖。"),
            }

        require_media_provider()
        task = create_case_task(
            settings.database_path,
            source_url=normalized_url,
            case_id=case_id,
            operator_profile_hint=hint,
            industry=selected_case_industry(payload.industry),
            source_upload=source_upload(),
            acquisition_provider=settings.case_acquisition_provider,
            provider_source_url=provider_source_url,
            created_by_user_id=actor_user_id,
            queue_max=settings.task_queue_max,
            gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
        )
        task_runner.schedule(task["task_id"])

        record_submission(settings,actor_user_id,task=task)

        return {
            "duplicate": False,
            "task": task,
            "case_id": case_id,
            "next_action": "请前往任务进度查看；离开页面后任务会继续。",
        }

    intake_dispatch_lock = threading.RLock()

    def submit_group_item(item):
        source = DouyinSourceInput("full_url", item["source_url"], item["canonical_url"], item["case_id"])
        payload = CaseAnalysisRequest(url=item["canonical_url"], source_upload_id=item["source_upload_id"])
        if payload.source_upload_id:
            with operation_lock(settings.pipeline_root, f"source-upload:{payload.source_upload_id}"):
                return submit_case_analysis(payload, item["created_by_user_id"], source)
        return submit_case_analysis(payload, item["created_by_user_id"], source)

    def dispatch_intake():
        with intake_dispatch_lock:
            dispatch_groups(settings.database_path, submit_group_item)

    task_runner.intake_dispatch = dispatch_intake
    app.state.intake_dispatch = dispatch_intake

    def intake_group_projection(group_id,user_id):
        group = get_group(settings.database_path, group_id)
        if not can_read_group(settings,user_id,group): not_visible()
        for item in group["items"]:
            if item["task"]:
                if not can_read_task(settings,user_id,item["task"]):
                    item["task"],item["task_id"]=None,None
                    item["message"]="投稿已记录，无需重复创建解析任务。"
                    item["error_code"]=None
                else: item["task"] = visible_case_task(item["task"],user_id)
            item["case"] = None
            item["classification"] = None
            if item["case_id"] and item["state"] != "input_duplicate":
                try:
                    attempt_id=item.get("task_id")
                    if not can_read_private_case(settings,user_id,item["case_id"],attempt_id):
                        item["case"]=shared_projection(settings,item["case_id"])
                        continue
                    detail = get_case_detail(settings, item["case_id"],attempt_id=attempt_id)
                    item["case"] = {k: detail.get(k) for k in ("case_id", "title", "duration_seconds", "platform", "status", "source_url")}
                    item["case"]["cover_url"] = (f"/api/cases/{item['case_id']}/cover" + (f"?attempt_id={attempt_id}" if attempt_id else "")) if case_cover_path(settings, item["case_id"],attempt_id=attempt_id) else None
                    item["classification"] = classification_state(settings, item["case_id"], attempt_id=attempt_id)
                except CanonicalOperationError as exc:
                    if exc.code != "CASE_NOT_FOUND":
                        item["message"] = exc.message
                        item["error_code"] = exc.code
        return group

    @app.post("/api/case-intake/groups")
    def create_intake_group(payload: CaseIntakeGroupRequest,
                            session: SessionContext = Depends(require_console_access),
                            x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
        require_csrf(session, x_csrf_token)
        try:
            group_id = create_group(settings.database_path, client_request_id=payload.client_request_id,
                                    user_id=int(session.user["id"]), raw=payload.text,
                                    resolve=resolve_douyin_source_input, source_upload_id=payload.source_upload_id)
        except SourceInputError as exc:
            raise HTTPException(422, detail=error_detail(exc.code, exc.message, exc.message)) from exc
        record_submission(settings,int(session.user["id"]),group=get_group(settings.database_path,group_id))
        dispatch_intake()
        return intake_group_projection(group_id,int(session.user["id"]))

    @app.get("/api/case-intake/groups")
    def intake_groups(session: SessionContext = Depends(require_console_access)):
        user_id=int(session.user["id"])
        return {"groups":[row for row in list_groups(settings.database_path,user_id=user_id,
            reviewer=is_reviewer(settings,user_id)) if can_read_group(settings,user_id,get_group(settings.database_path,row["group_id"]))]}

    @app.get("/api/case-intake/groups/{group_id}")
    def intake_group(group_id: str, session: SessionContext = Depends(require_console_access)):
        return intake_group_projection(group_id,int(session.user["id"]))

    @app.get("/api/cases/{case_id}/classification")
    def case_classification(case_id: str, session: SessionContext = Depends(require_console_access), attempt_id: str | None = None):
        require_private_case(settings,int(session.user["id"]),case_id,attempt_id)
        return classification_state(settings, case_id,attempt_id=attempt_id)

    @app.get("/api/cases/{case_id}/cover")
    def case_cover(case_id: str, session: SessionContext = Depends(require_console_access),attempt_id: str | None = None):
        user_id=int(session.user["id"])
        if not can_read_private_case(settings,user_id,case_id,attempt_id):
            if attempt_id is not None or shared_projection(settings,case_id) is None: not_visible()
            path=shared_cover_path(settings,case_id)
        else: path = case_cover_path(settings, case_id,attempt_id=attempt_id)
        if path is None:
            raise HTTPException(404, detail="没有可用封面。")
        return FileResponse(path, headers={"Cache-Control": "private, no-store"})

    @app.post("/api/cases/{case_id}/classification")
    def confirm_case_classification(case_id: str, payload: CaseClassificationRequest,
                                    session: SessionContext = Depends(require_console_access),
                                    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
        require_csrf(session, x_csrf_token)
        require_private_case(settings,int(session.user["id"]),case_id,payload.attempt_id)
        return locked_authority_call("case", case_id, confirm_classification, settings, case_id,
                                     **payload.model_dump(), actor_user_id=int(session.user["id"]),
                                     actor_phone=str(session.user["phone"]))

    @app.get("/api/cases/{case_id}")
    def case_detail(
        case_id: str,
        session: SessionContext = Depends(require_console_access),
        attempt_id: str | None = None,
    ) -> dict[str, Any]:
        user_id=int(session.user["id"])
        if not can_read_private_case(settings,user_id,case_id,attempt_id):
            shared=shared_projection(settings,case_id) if attempt_id is None else None
            if shared is None: not_visible()
            return shared
        detail = get_case_detail(settings, case_id,attempt_id=attempt_id)
        intake_task = get_task(settings.database_path, str(detail["review"].get("attempt_id") or ""))
        detail["submitted_by"] = intake_task.get("created_by") if intake_task else None
        detail["classification"] = classification_summary(settings, case_id,attempt_id=attempt_id)
        detail["classification_required"] = bool(intake_task and not intake_task["payload"].get("operator_profile_hint")
            and not intake_task["payload"].get("profile") and not detail["review"].get("approved") and not detail["review"].get("decision"))
        reviewer=is_reviewer(settings,user_id)
        detail["review"]["can_review"] = detail["review"]["can_review"] and reviewer
        detail["can_annotate_profile"] = bool(detail.get("can_annotate_profile") and reviewer)
        detail["can_annotate_industry"] = bool(detail.get("can_annotate_industry") and reviewer)
        detail["permissions"]={"can_review":reviewer,"can_publish":reviewer and detail["review"]["approved"],
            "can_reanalyze":detail["review"].get("decision")=="reject" and bool(detail.get("source_url"))}
        if reviewer and detail["review"]["approved"]:
            detail["publication_context"]=publication_context(settings,case_id)
            detail["shared_display"]=shared_projection(settings,case_id)
        if detail['review']['approved']:
            from .case_shared_display import sharing_status
            detail.update(sharing_status(settings,case_id))
        sharing=None
        if detail['review']['can_review']:
            try:
                require_case_classification(case_id)
                from .case_shared_display import share_preview
                sharing=share_preview(settings,case_id,case_principal(settings,user_id))
            except HTTPException as exc:
                if exc.status_code!=409 or not isinstance(exc.detail,dict) or exc.detail.get('code')!='CASE_CLASSIFICATION_REQUIRED':
                    raise
                detail['share_preview_error']={'message':exc.detail['message'],'next_action':exc.detail['next_action']}
            except CanonicalOperationError as exc:
                detail['share_preview_error']={'message':exc.message,'next_action':exc.next_action}
            except (OSError,ValueError,RuntimeError,TypeError,KeyError):
                detail['share_preview_error']={'message':'安全展示预览暂不可核对，请恢复来源或重新分析。','next_action':'原修订和审核记录保留，暂不能批准。'}
        detail['share_preview']=sharing
        detail["approval_context"] = review_commands.issue(settings, "case", case_id, user_id,sharing=sharing,joint=True) if detail["review"]["can_review"] else None
        if detail["approval_context"] and not detail["review"].get("approval_recovery_required"):
            from case_human_review_v2 import quality_context
            from .canonical_gateway import _find_case_path
            try:
                detail["quality_context"] = quality_context(_find_case_path(settings, case_id)[0])
            except (OSError, ValueError, KeyError, TypeError):
                detail["quality_context"] = None  # Incomplete evidence can be read, never approved.
        detail["visibility"]="private"
        if reviewer and detail['review']['can_review'] and not detail['review'].get('approval_recovery_required'):
            from .case_evidence_review import workspace
            detail['evidence_workspace']=workspace(settings,case_id,detail['review']['attempt_id'])
        return detail

    @app.post('/api/cases/{case_id}/share-preview')
    def case_share_preview(case_id: str, payload: CaseSharePreviewRequest,
            x_csrf_token: str | None = Header(default=None,alias='X-CSRF-Token'),
            session: SessionContext = Depends(require_console_access)):
        require_csrf(session,x_csrf_token)
        actor=case_principal(settings,int(session.user['id']))
        reviewer_authorization(settings,actor)
        require_private_case(settings,actor['user_id'],case_id)
        def prepare():
            require_case_classification(case_id)
            from .case_shared_display import share_preview
            sharing=share_preview(settings,case_id,actor,**payload.model_dump())
            return {'share_preview':sharing,'approval_context':review_commands.issue(settings,'case',case_id,actor['user_id'],sharing=sharing,joint=True)}
        return locked_authority_call('case',case_id,prepare)

    @app.get("/api/cases/{case_id}/media")
    def case_media(
        case_id: str,
        session: SessionContext = Depends(require_console_access),
        attempt_id: str | None = None,
    ) -> FileResponse:
        require_private_case(settings,int(session.user["id"]),case_id,attempt_id)
        path = case_media_path(settings, case_id,attempt_id=attempt_id)
        return FileResponse(
            path,
            media_type="video/webm" if path.suffix.lower() == ".webm" else "video/mp4",
            headers={"Cache-Control": "private, no-store"},
        )

    @app.post("/api/cases/{case_id}/profile-annotation")
    def case_profile_annotation(
        case_id: str,
        payload: CaseProfileAnnotationRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        reviewer_authorization(settings,case_principal(settings,int(session.user["id"])))
        return {"case": locked_authority_call(
            "case", case_id, annotate_case_profile, settings, case_id,
            operator_profile_hint=payload.operator_profile_hint,
            approved_case_sha256=payload.approved_case_sha256,
            expected_annotation_sha256=payload.expected_annotation_sha256,
            actor_user_id=int(session.user["id"]),
            actor_phone=str(session.user["phone"]),
            note=payload.note,
        )}

    @app.post("/api/cases/{case_id}/industry-annotation")
    def case_industry_annotation(
        case_id: str,
        payload: CaseIndustryAnnotationRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        reviewer_authorization(settings,case_principal(settings,int(session.user["id"])))
        return {"case": locked_authority_call(
            "case", case_id, annotate_case_industry, settings, case_id,
            industry=payload.industry,
            approved_case_sha256=payload.approved_case_sha256,
            expected_annotation_sha256=payload.expected_annotation_sha256,
            actor_user_id=int(session.user["id"]),
            actor_phone=str(session.user["phone"]),
            note=payload.note,
        )}

    def require_case_classification(case_id):
        with transaction(settings.database_path) as connection:
            latest = connection.execute("SELECT task_id FROM tasks WHERE task_type='case_analysis' AND json_extract(payload_json,'$.evidence_revision') IS NULL AND subject_ref=? ORDER BY created_at DESC,task_id DESC LIMIT 1", (case_id,)).fetchone()
        latest_task = get_task(settings.database_path, latest["task_id"]) if latest else None
        if latest_task and not (latest_task["payload"].get("operator_profile_hint") or latest_task["payload"].get("profile")):
            current = get_case_detail(settings, case_id)
            intake_task = get_task(settings.database_path, str(current["review"].get("attempt_id") or ""))
            if (intake_task and not intake_task["payload"].get("operator_profile_hint")
                    and not intake_task["payload"].get("profile")
                    and not current["review"].get("approval_recovery_required")
                    and classification_state(settings, case_id)["status"] != "confirmed"):
                raise HTTPException(409, detail=error_detail("CASE_CLASSIFICATION_REQUIRED", "请先检查并确认分类。", "确认分类后继续案例审核；分类确认不会批准入库。"))

    @app.post("/api/cases/{case_id}/review")
    def review_case(
        case_id: str,
        payload: CaseReviewRequest,
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        reviewer_authorization(settings, case_principal(settings, int(session.user["id"])))
        upload_cache = None

        def preflight(_command):
            nonlocal upload_cache
            if payload.decision=='approve' and _command['context']['version']==review_commands.JOINT_CASE_VERSION:
                require_case_classification(case_id)
                from case_evidence_revision_v1 import require_confirmation_contract, RevisionError
                try:
                    require_confirmation_contract(_command['context'],payload.evidence_review.model_dump() if payload.evidence_review else None)
                except RevisionError as exc:
                    raise CanonicalOperationError(exc.code,str(exc),'请恢复准确审核范围后继续。') from exc
                from .case_shared_display import validate_sharing_decision
                validate_sharing_decision(settings,_command,payload.sharing_decision.model_dump() if payload.sharing_decision else None)
            if payload.decision in {"reject", "reanalyze"} and not payload.reason.strip():
                raise HTTPException(422, detail=error_detail("CASE_REVIEW_REASON_REQUIRED", "请填写不收录或重新分析的原因。", "补充原因后再次提交。"))
            if payload.source_upload_id and payload.decision != "reanalyze":
                raise HTTPException(422, detail="只有重新分析可以提交新视频文件。")
            if payload.decision != "reanalyze": return
            source_detail = get_case_detail(settings, case_id)
            if not source_detail.get("source_url"):
                raise HTTPException(422, detail=error_detail("CASE_SOURCE_URL_MISSING", "原始视频链接缺失，暂时不能重新分析。", "请恢复准确来源后再继续。"))
            if payload.source_upload_id:
                upload_cache = validate_for_submission(settings, payload.source_upload_id, str(source_detail["source_url"]), int(session.user["id"]))
            elif source_detail.get("review_media", {}).get("operator_uploaded") or settings.case_acquisition_provider == "upload_only":
                raise HTTPException(422, detail=error_detail("SOURCE_UPLOAD_REQUIRED", "请重新上传与来源对应的视频文件。", "请从添加案例页上传。"))
            elif settings.case_acquisition_provider == "qiyun" and not (os.environ.get("QYAPI_APP_ID") and os.environ.get("QYAPI_APP_KEY")):
                raise HTTPException(503, detail=error_detail("SOURCE_PROVIDER_NOT_CONFIGURED", "自动获取视频暂不可用。", "请上传本地视频，或联系管理员配置视频解析服务。"))

        def execute(command):
            nonlocal upload_cache
            if payload.decision == "reanalyze":
                with transaction(settings.database_path) as db:
                    prior = db.execute("SELECT task_id FROM tasks WHERE task_type='case_analysis' AND subject_ref=? AND json_extract(payload_json,'$.review_operation_id')=?", (case_id, command["context"]["operation_id"])).fetchone()
                if prior:
                    task = get_task(settings.database_path, prior["task_id"])
                    record_submission(settings, int(session.user["id"]), task=task)
                    return {"decision": "reanalyze", "task": task}
                if payload.source_upload_id:
                    from .case_uploads import reserve_review_upload
                    source_detail = get_case_detail(settings, case_id, attempt_id=command["context"]["snapshot"]["attempt_id"])
                    upload_cache = reserve_review_upload(settings, command, upload_cache, str(source_detail["source_url"]), int(session.user["id"]), payload.source_upload_id)
            return perform_case_review(case_id, payload, session, upload_cache, command)

        def submit():
            return review_command("case", case_id, session, payload, f"/api/cases/{case_id}/review", execute, preflight=preflight)
        if payload.source_upload_id:
            with operation_lock(settings.pipeline_root, f"source-upload:{payload.source_upload_id}"):
                return submit()
        return submit()

    def perform_case_review(case_id: str, payload: CaseReviewRequest, session: SessionContext,
                            source_upload: dict | None = None, command=None) -> dict[str, Any]:
        review_commands.validate_target(settings, command)
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
        reanalysis_hint = None
        reanalysis_source_url = None
        reanalysis_industry = None
        if payload.decision == "reanalyze":
            reanalysis_detail = get_case_detail(settings, case_id, attempt_id=command["context"]["snapshot"]["attempt_id"])
            reanalysis_industry = selected_case_industry(
                payload.industry, str(reanalysis_detail.get("industry") or "待分类")
            )
            reanalysis_hint = payload.operator_profile_hint or case_reanalysis_hint(settings.database_path, case_id)
            if reanalysis_hint is None:
                reanalysis_hint = reanalysis_detail.get("operator_profile_hint")
            reanalysis_source_url = reanalysis_detail.get("source_url")
            if not reanalysis_source_url:
                raise HTTPException(422, detail=error_detail(
                    "CASE_SOURCE_URL_MISSING", "原始视频链接缺失，暂时不能重新分析。",
                    "请先恢复来源链接，再发起重新分析。",
                ))
            if (source_upload is None and settings.case_acquisition_provider == "qiyun"
                    and not (os.environ.get("QYAPI_APP_ID") and os.environ.get("QYAPI_APP_KEY"))):
                raise HTTPException(503, detail=error_detail(
                    "SOURCE_PROVIDER_NOT_CONFIGURED", "自动获取视频暂不可用。",
                    "请上传本地视频，或联系管理员配置视频解析服务。",
                ))
            if source_upload is None and settings.case_acquisition_provider == "upload_only":
                raise HTTPException(422, detail=error_detail(
                    "SOURCE_UPLOAD_REQUIRED", "当前需要上传本地视频。", "请上传与来源链接对应的视频文件。",
                ))
        reviewer = str(session.user["phone"])
        if payload.decision == "approve":
            approval_kwargs: dict[str, Any] = {
                "reviewer": reviewer,
                "note": reason,
                "quality_decision": payload.quality_decision,
                "approval_principal":case_principal(settings,int(session.user["id"])),
                "expected_target": command["context"]["snapshot"],
                "review_command": command,
            }
            if payload.evidence_review is not None:
                approval_kwargs["evidence_review"] = payload.evidence_review.model_dump()
                approval_kwargs["reviewer_user_id"] = int(session.user["id"])
            require_case_classification(case_id)
            detail = approve_case_candidate(settings, case_id, **approval_kwargs)
            mark_task_reviewed(
                settings.database_path, case_id, "已批准入库",
                attempt_id=(detail.get("review") or {}).get("attempt_id"),
            )
            receipt = settings.pipeline_root / "data/cases" / case_id / "approval_receipt.json"
            return {"decision": "approved", "case": detail,
                    "approval_receipt_ref": review_commands._ref(settings, receipt)}
        decision = record_case_review_decision(settings, case_id, reviewer=reviewer,
            decision=payload.decision, reason=reason,
            review_principal=case_principal(settings, int(session.user["id"])),
            expected_target=command["context"]["snapshot"], decided_at=command["at"])
        from .task_service import end_case_revision_tasks
        end_case_revision_tasks(settings,case_id,decision['attempt_id'])
        if payload.decision == "reject":
            mark_task_reviewed(
                settings.database_path, case_id, "不收录",
                attempt_id=decision.get("attempt_id"),
            )
            return {"decision": "rejected", "review": decision}
        mark_task_reviewed(
            settings.database_path, case_id, "已退回重新分析",
            attempt_id=decision.get("attempt_id"),
        )
        task = create_case_task(
            settings.database_path,
            source_url=str(reanalysis_source_url),
            case_id=case_id,
            operator_profile_hint=reanalysis_hint,
            industry=reanalysis_industry or "待分类",
            source_upload=source_upload,
            acquisition_provider=settings.case_acquisition_provider,
            reanalyze=True,
            review_operation_id=command["context"]["operation_id"],
            reason=reason,
            created_by_user_id=int(session.user["id"]),
            queue_max=settings.task_queue_max,
            gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
        )
        task_runner.schedule(task["task_id"])
        record_submission(settings,int(session.user["id"]),task=task)
        return {"decision": "reanalyze", "task": task}

    @app.get("/api/tasks")
    def tasks(
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {"tasks":visible_tasks(int(session.user["id"]))}

    @app.get("/api/tasks/activity")
    def task_activity(
        user_id: int | None = None,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        actor_id=int(session.user["id"])
        def activity_case_access(case_id,attempt_id):
            if is_reviewer(settings,actor_id): return True
            if attempt_id:
                task=get_task(settings.database_path,attempt_id)
                return bool(task and task["subject_ref"]==case_id and can_read_task(settings,actor_id,task))
            return can_read_private_case(settings,actor_id,case_id)
        return operator_activity(settings.database_path, settings.pipeline_root, user_id,
            case_access=activity_case_access)

    @app.get("/api/tasks/{task_id}")
    def task_detail(
        task_id: str,
        session: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        task = get_task(settings.database_path, task_id)
        if task is None:
            raise HTTPException(
                status_code=404,
                detail=error_detail(
                    "TASK_NOT_FOUND", "没有找到这个任务。", "请返回任务记录重新选择。"
                ),
            )
        projected_task = visible_case_task(task,int(session.user["id"]))
        return {
            "task": projected_task,
            "boundary_review": pending_boundary_review(settings, task)
            if task["task_type"] == "case_analysis"
            and projected_task.get("current_case_status") != "approved" else None,
        }

    @app.post("/api/tasks/{task_id}/retry")
    def retry_case_task(task_id: str, session: SessionContext = Depends(require_console_access),
                        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token")):
        require_csrf(session, x_csrf_token)
        task = get_task(settings.database_path, task_id)
        if task is None or task["task_type"] != "case_analysis":
            raise HTTPException(404, detail=error_detail("TASK_NOT_FOUND", "没有找到案例解析任务。", "请返回任务列表。"))
        require_task(settings,int(session.user["id"]),task)
        with authority_operation_lock(settings, "case", str(task["subject_ref"])):
            revision=task['payload'].get('evidence_revision')
            if revision:
                from case_evidence_revision_v1 import resolve_target, RevisionError
                reviewer_authorization(settings,case_principal(settings,int(session.user['id'])))
                try:
                    target=resolve_target(settings.pipeline_root,task['subject_ref'],revision['attempt_id'])
                    if ((target.attempt_root/'human_review_decision_v1.json').exists()
                            or (settings.pipeline_root/'data/cases'/task['subject_ref']/'approval_receipt.json').exists()):
                        raise RevisionError('CASE_REVISION_TERMINAL','原投稿已结束，不能重试旧修订。')
                    if target.revision_root.name!=revision['revision_id'] or target.revision_ref['sha256']!=revision['revision_sha256'] or target.state=='validated':
                        raise RevisionError('CASE_REVISION_HEAD_STALE','该任务不再是待恢复的当前修订。')
                except RevisionError as exc:
                    raise CanonicalOperationError(exc.code,str(exc),'请刷新案例并恢复当前修订。') from exc
            duplicate = None if revision else resolve_case_source_duplicate(settings, str(task["payload"]["source_url"]))
            if duplicate and duplicate.get("state") in {"approved", "rejected", "awaiting_review"}:
                raise HTTPException(409, detail=error_detail("CASE_RETRY_BLOCKED", "这条视频已有审核结果。", "请查看已有案例。"))
            active = None if revision else find_active_case_task(settings.database_path, str(task["subject_ref"]))
            if active:
                require_task(settings,int(session.user["id"]),active)
                return {"task": active}
            with transaction(settings.database_path, immediate=True) as connection:
                row = connection.execute("SELECT status,payload_json,created_by_user_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
                latest = connection.execute("SELECT task_id FROM tasks WHERE task_type='case_analysis' AND subject_ref=? ORDER BY created_at DESC,task_id DESC LIMIT 1", (task["subject_ref"],)).fetchone()
                if not revision and latest["task_id"] != task_id:
                    raise HTTPException(409, detail=error_detail("CASE_RETRY_SUPERSEDED", "已有更新的分析记录。", "请恢复最新任务。"))
                if row["status"] != "failed":
                    raise HTTPException(409, detail=error_detail("CASE_RETRY_BLOCKED", "任务状态已变化。", "刷新后查看当前任务。"))
                if not revision and pending_boundary_review(settings, task):
                    raise HTTPException(409, detail=error_detail("CASE_BOUNDARY_REVIEW_REQUIRED", "请先确认待判断的分镜。", "进入任务详情确认分镜后继续。"))
                ensure_task_capacity(connection, queue_max=settings.task_queue_max,
                                     gpu_pending_per_user_max=settings.gpu_pending_per_user_max,
                                     execution_lane=task["execution_lane"], created_by_user_id=row["created_by_user_id"])
                payload = json.loads(row["payload_json"])
                if len(payload.get("retry_actions", [])) >= 3:
                    raise HTTPException(409, detail=error_detail(
                        "CASE_RETRY_LIMIT_REACHED", "这条任务已达到 3 次人工重试上限。",
                        "请联系管理员检查失败原因；不要反复提交以重新付费获取或分析。"))
                payload.setdefault("retry_actions", []).append({"user_id": int(session.user["id"]),
                    "phone": str(session.user["phone"]), "at": datetime.now(timezone.utc).isoformat()})
                connection.execute(
                    """UPDATE tasks SET status='queued',stage='等待继续解析',error_code=NULL,error_message=NULL,
                       payload_json=?,worker_id=NULL,heartbeat_at=NULL,lease_expires_at=NULL,updated_at=?
                       WHERE task_id=? AND status='failed'""",
                    (json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), task_id))
        task_runner.schedule(task_id)
        return {"task": get_task(settings.database_path, task_id)}

    @app.post("/api/tasks/{task_id}/boundary-review")
    def review_case_boundaries(
        task_id: str,
        payload: CaseBoundaryReviewRequest,
        session: SessionContext = Depends(require_console_access),
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, Any]:
        require_csrf(session, x_csrf_token)
        with authority_operation_lock(settings, "case", task_id):
            task = get_task(settings.database_path, task_id)
            require_task(settings,int(session.user["id"]),task)
            if task is None:
                raise HTTPException(
                    status_code=404,
                    detail=error_detail("TASK_NOT_FOUND", "没有找到这个任务。", "请返回任务记录重新选择。"),
                )
            if task['payload'].get('evidence_revision'):
                raise HTTPException(409,detail=error_detail('CASE_EVIDENCE_SCOPE_STALE','修订必须通过完整新版审核范围处理。','请返回案例审核页。'))
            try:
                resumed = submit_boundary_review(
                    settings,
                    task,
                    shot_sha256=payload.shot_sha256,
                    decisions=[item.model_dump() for item in payload.decisions],
                    user_id=int(session.user["id"]),
                    phone=str(session.user["phone"]),
                )
            except BoundaryReviewError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=error_detail("CASE_BOUNDARY_REVIEW_CONFLICT", str(exc), "刷新任务后重试。"),
                ) from exc
        task_runner.schedule(task_id)
        return {"task": resumed}

    @app.get("/api/capabilities")
    def capabilities(
        _: SessionContext = Depends(require_console_access),
    ) -> dict[str, Any]:
        return {"case_analysis": case_capability()}

    assets_path = static_path / "assets"
    from .case_evidence_review import register_routes as register_case_evidence_routes
    register_case_evidence_routes(app,settings,require_console_access,require_csrf,review_command,task_runner)
    from .publish_copy_routes import register_routes as register_publish_copy_routes
    register_publish_copy_routes(app, settings, require_console_access, require_csrf, background_task_runner)
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(index_path, headers={"Cache-Control": "no-store"})

    return app


app = build_app()
