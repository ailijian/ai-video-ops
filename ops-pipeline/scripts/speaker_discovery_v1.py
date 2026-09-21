from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "speaker-discovery-candidates-v1.0"
PROMPT_PATH = Path(__file__).resolve().parents[1] / "speaker_prompt.md"

ALLOWED_CANDIDATE_STATUSES = {
    "explicit_speaker",
    "potential_representative",
}

ALLOWED_SPEAKER_TYPES = {
    "owner_founder",
    "frontline_expert",
    "brand",
    "generic",
    None,
}


class SpeakerDiscoveryError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _identity_text(value: str | None) -> str:
    return "".join(str(value or "").split()).casefold()


def _quote_list(
    value: Any,
    *,
    safe_materials: str,
    required: bool,
) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for item in value:
        quote = str(item or "").strip()
        if not quote or quote not in safe_materials:
            continue
        if quote not in result:
            result.append(quote)
    if required and not result:
        return None
    return result


def build_prompt(privacy_projection: dict[str, Any]) -> str:
    try:
        template = PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_PROMPT_MISSING",
            "Speaker Discovery prompt is unavailable.",
        ) from exc

    projection = privacy_projection.get("projection") or {}
    prompt = template.replace(
        "{customer_name}",
        str(projection.get("customer_name_safe_semantic") or ""),
    ).replace(
        "{industry}",
        str(projection.get("industry_safe_semantic") or ""),
    ).replace(
        "{privacy_safe_customer_materials}",
        str(projection.get("materials_safe_semantic") or ""),
    )
    return prompt.strip()


def _candidate_id(
    *,
    intake_id: str,
    name: str | None,
    public_role: str | None,
    evidence_quotes: list[str],
) -> str:
    evidence_hash = canonical_sha256(evidence_quotes)
    identity = "|".join(
        (
            intake_id,
            _identity_text(name),
            _identity_text(public_role),
            evidence_hash,
        )
    )
    return "speaker_candidate_" + hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:18]


def _validate_candidate(
    raw: Any,
    *,
    safe_materials: str,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    status = str(raw.get("candidate_status") or "").strip()
    if status not in ALLOWED_CANDIDATE_STATUSES:
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_STATUS_INVALID",
            "Speaker candidate status is invalid.",
        )

    speaker_type = _normalized_optional_text(raw.get("speaker_type_hint"))
    if speaker_type not in ALLOWED_SPEAKER_TYPES:
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_TYPE_INVALID",
            "Speaker candidate type is invalid.",
        )

    evidence = _quote_list(
        raw.get("evidence_quotes"),
        safe_materials=safe_materials,
        required=True,
    )
    if evidence is None:
        return None

    personal = _quote_list(
        raw.get("personal_material_quotes") or [],
        safe_materials=safe_materials,
        required=False,
    )
    if personal is None:
        personal = []

    forbidden = _quote_list(
        raw.get("explicit_forbidden_claims") or [],
        safe_materials=safe_materials,
        required=False,
    )
    if forbidden is None:
        forbidden = []

    return {
        "name": _normalized_optional_text(raw.get("name")),
        "public_role": _normalized_optional_text(raw.get("public_role")),
        "speaker_type_hint": speaker_type,
        "candidate_status": status,
        "evidence_quotes": evidence,
        "personal_material_quotes": personal,
        "explicit_forbidden_claims": forbidden,
    }


def _dedupe_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    collapsed: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for candidate in candidates:
        name_key = _identity_text(candidate.get("name"))
        role_key = _identity_text(candidate.get("public_role"))
        if name_key or role_key:
            key = f"identity:{name_key}|{role_key}"
        else:
            key = "evidence:" + canonical_sha256(
                candidate.get("evidence_quotes") or []
            )

        if key not in collapsed:
            collapsed[key] = candidate
            order.append(key)
            continue

        current = collapsed[key]
        if candidate["candidate_status"] == "explicit_speaker":
            current["candidate_status"] = "explicit_speaker"
        if current.get("speaker_type_hint") is None:
            current["speaker_type_hint"] = candidate.get("speaker_type_hint")
        for field in (
            "evidence_quotes",
            "personal_material_quotes",
            "explicit_forbidden_claims",
        ):
            for item in candidate.get(field) or []:
                if item not in current[field]:
                    current[field].append(item)

    return [collapsed[key] for key in order]


def build_candidate_artifact(
    *,
    business_id: str,
    intake_id: str,
    created_at: str,
    extracted: dict[str, Any],
    privacy_projection: dict[str, Any],
    customer_intake_path: Path,
    privacy_projection_path: Path,
) -> dict[str, Any]:
    if not isinstance(extracted, dict):
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_RESULT_INVALID",
            "Speaker Discovery result must be an object.",
        )
    raw_candidates = extracted.get("speaker_candidates")
    if not isinstance(raw_candidates, list):
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_RESULT_INVALID",
            "speaker_candidates must be a list.",
        )
    if len(raw_candidates) > 5:
        raise SpeakerDiscoveryError(
            "SPEAKER_DISCOVERY_TOO_MANY_CANDIDATES",
            "Speaker Discovery returned more than five candidates.",
        )

    safe_materials = str(
        (privacy_projection.get("projection") or {}).get(
            "materials_safe_semantic"
        )
        or ""
    )
    validated = []
    for raw in raw_candidates:
        candidate = _validate_candidate(raw, safe_materials=safe_materials)
        if candidate is not None:
            validated.append(candidate)

    validated = _dedupe_candidates(validated)
    for candidate in validated:
        candidate["candidate_id"] = _candidate_id(
            intake_id=intake_id,
            name=candidate.get("name"),
            public_role=candidate.get("public_role"),
            evidence_quotes=candidate["evidence_quotes"],
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "business_id": business_id,
        "intake_id": intake_id,
        "created_at": created_at,
        "speaker_discovery_status": "completed",
        "speaker_candidates": validated,
        "source": {
            "customer_intake_ref": {
                "path": str(customer_intake_path.resolve()),
                "sha256": file_sha256(customer_intake_path),
            },
            "privacy_projection_ref": {
                "path": str(privacy_projection_path.resolve()),
                "sha256": file_sha256(privacy_projection_path),
            },
        },
        "model": str(extracted.get("model") or "test-extractor"),
        "usage": extracted.get("usage") or {},
        "authority": {
            "discovery_is_speaker_truth": False,
            "discovery_is_speaker_persona": False,
            "human_confirmation_required": True,
            "business_fact_not_promoted_to_speaker_fact": True,
        },
    }


def build_failed_artifact(
    *,
    business_id: str,
    intake_id: str,
    created_at: str,
    failure_code: str,
    customer_intake_path: Path,
    privacy_projection_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "business_id": business_id,
        "intake_id": intake_id,
        "created_at": created_at,
        "speaker_discovery_status": "failed",
        "speaker_candidates": [],
        "failure": {"code": failure_code},
        "source": {
            "customer_intake_ref": {
                "path": str(customer_intake_path.resolve()),
                "sha256": file_sha256(customer_intake_path),
            },
            "privacy_projection_ref": {
                "path": str(privacy_projection_path.resolve()),
                "sha256": file_sha256(privacy_projection_path),
            },
        },
        "authority": {
            "discovery_is_speaker_truth": False,
            "discovery_is_speaker_persona": False,
            "human_confirmation_required": True,
            "business_fact_not_promoted_to_speaker_fact": True,
        },
    }
