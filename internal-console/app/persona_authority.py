from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical_gateway import CanonicalOperationError
from .config import Settings


_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "ops-pipeline" / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from show_customer_status_v1 import (  # noqa: E402
    AuthorityResolutionError,
    resolve_current_persona as resolve_canonical_current_persona,
)


PersonaArtifact = dict[str, Any]


@dataclass(frozen=True)
class PersonaAuthority:
    """Console projection over the canonical approved-Persona resolver."""

    current: PersonaArtifact | None
    review_candidate: PersonaArtifact | None

    @property
    def projected(self) -> PersonaArtifact | None:
        return self.review_candidate or self.current


def _authority_error(exc: AuthorityResolutionError) -> CanonicalOperationError:
    return CanonicalOperationError(
        exc.code,
        "Persona Authority 无法唯一解析。",
        "请修复 Persona lifecycle、approval receipt 或 revision lineage 后刷新。",
    )


def _read_persona(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalOperationError(
            "INVALID_AUTHORITY_ARTIFACT",
            "Persona Authority artifact 无法读取。",
            "请修复 Persona artifact 后刷新。",
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalOperationError(
            "INVALID_AUTHORITY_ARTIFACT",
            "Persona Authority artifact 格式无效。",
            "请修复 Persona artifact 后刷新。",
        )
    return value


def _artifact(path: Path, persona: dict[str, Any]) -> PersonaArtifact:
    return {
        "persona_id": persona.get("persona_id"),
        "revision": persona.get("revision"),
        "scope": persona.get("persona_scope", "business"),
        "path": path,
        "artifact": persona,
    }


def resolve_persona_authority(
    settings: Settings,
    persona_id: str,
    expected_scope: str,
) -> PersonaAuthority:
    """
    Resolve approved current Authority canonically and keep a review candidate
    separate from it. Filename ordering never participates in either decision.
    """

    root = settings.pipeline_root / "data" / "personas" / persona_id
    if not root.is_dir():
        return PersonaAuthority(current=None, review_candidate=None)

    try:
        current = resolve_canonical_current_persona(
            settings.pipeline_root,
            persona_id,
            expected_scope,
        )
    except AuthorityResolutionError as exc:
        if exc.code in {"PERSONA_NOT_FOUND", "APPROVED_PERSONA_NOT_FOUND"}:
            current = None
        else:
            raise _authority_error(exc) from exc

    active_review_candidates: list[PersonaArtifact] = []
    for path in root.glob("*/persona_v1.json"):
        persona = _read_persona(path)
        lifecycle = persona.get("lifecycle") or {}
        status = lifecycle.get("status")
        approved = lifecycle.get("approved")

        if persona.get("persona_id") != persona_id:
            raise CanonicalOperationError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                "Persona 目录中存在 identity 不一致的 artifact。",
                "请修复 Persona identity 后刷新。",
            )
        if persona.get("persona_scope", "business") != expected_scope:
            raise CanonicalOperationError(
                "PERSONA_SCOPE_MISMATCH",
                "Persona scope 与当前 Authority 不一致。",
                "请修复 Persona scope 后刷新。",
            )
        revision = persona.get("revision")
        if not isinstance(revision, int) or revision < 1:
            raise CanonicalOperationError(
                "INVALID_PERSONA_REVISION",
                "Persona revision 无效。",
                "请修复显式 revision 后刷新。",
            )

        if status == "approved" or approved is True:
            if status != "approved" or approved is not True:
                raise CanonicalOperationError(
                    "CURRENT_AUTHORITY_AMBIGUITY",
                    "Persona approved lifecycle 声明不一致。",
                    "请修复 lifecycle 后刷新。",
                )
            continue

        if status == "review_required" or approved is False:
            if status != "review_required" or approved is not False:
                raise CanonicalOperationError(
                    "CURRENT_AUTHORITY_AMBIGUITY",
                    "Persona review lifecycle 声明不一致。",
                    "请修复 lifecycle 后刷新。",
                )
            active_review_candidates.append(_artifact(path, persona))

    current_revision = int(current["revision"]) if current else 0
    candidates = [
        item
        for item in active_review_candidates
        if int(item["revision"]) > current_revision
    ]
    if len(candidates) > 1:
        raise CanonicalOperationError(
            "CURRENT_AUTHORITY_AMBIGUITY",
            "存在多个同时待审核的 Persona revision。",
            "请先修复 revision lineage，再继续审核。",
        )

    review_candidate = candidates[0] if candidates else None
    if review_candidate is not None:
        revision = int(review_candidate["revision"])
        previous_ref = (
            review_candidate["artifact"].get("revision_lineage") or {}
        ).get("previous_approved_revision")
        if current is None:
            valid_lineage = revision == 1 and previous_ref is None
        else:
            valid_lineage = (
                revision == current_revision + 1
                and isinstance(previous_ref, dict)
                and previous_ref.get("revision") == current_revision
                and previous_ref.get("sha256") == current.get("file_sha256")
                and previous_ref.get("content_sha256")
                == current.get("content_sha256")
            )
        if not valid_lineage:
            raise CanonicalOperationError(
                "CURRENT_AUTHORITY_AMBIGUITY",
                "待审核 Persona revision lineage 无法连接当前已批准 revision。",
                "请修复 revision lineage 后刷新。",
            )

    return PersonaAuthority(
        current=current,
        review_candidate=review_candidate,
    )


def validate_speaker_business_binding(
    speaker: PersonaArtifact,
    business: PersonaArtifact,
) -> None:
    reference = speaker["artifact"].get("business_persona_ref") or {}
    valid = (
        reference.get("persona_id") == business.get("persona_id")
        and reference.get("revision") == business.get("revision")
        and reference.get("sha256") == business.get("file_sha256")
        and reference.get("content_sha256") == business.get("content_sha256")
        and reference.get("status") == "approved"
    )
    if not valid:
        raise CanonicalOperationError(
            "SPEAKER_BUSINESS_LINEAGE_MISMATCH",
            "出镜人 Persona 未绑定当前已批准 Business Persona。",
            "请重新分析出镜人或修复 Persona lineage 后刷新。",
        )
