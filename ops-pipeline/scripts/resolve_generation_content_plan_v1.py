"""Resolve one canonical Content Plan through the frozen V1.1.1 quality baseline.

Pipeline:
Generation Request -> Generation Source Plan -> remote V1 candidate planning
-> offline V1.1 historical-exposure calibration
-> offline V1.1.1 material-information-gain closure
-> STOP.

Only the V1 candidate-planning step may call DeepSeek. V1.1 and V1.1.1 are
fully deterministic and reuse the existing frozen content-quality implementation.
No script is generated, no Generation Batch is created, and no Content Ledger is
written by this operation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from content_creation_entry_v1 import (
    ContentCreationEntryError,
    has_ledger_worthy_historical_exposure,
)
from content_quality_v1 import (
    LEDGER_SCHEMA_VERSION,
    PLAN_SCHEMA_VERSION,
    PLAN_V1_1_SCHEMA_VERSION,
    PLAN_V1_1_1_SCHEMA_VERSION,
    STRONG_MEMORY_STATUSES,
    build_content_plan_v1_1,
    build_content_plan_v1_1_1,
    build_fact_atom_catalog,
    canonical_sha256,
    is_strong_memory,
    write_new_json,
)
from customer_onboarding_analysis_v1 import load_deepseek_runtime_config
from generate_mix_scripts_v1 import (
    generate_content_plan_v1,
    safe_persona_projection,
    validate_content_plan_input,
    validate_generation_inputs,
)
from generation_request_handoff_v1 import _business_generation_lock
from show_customer_status_v1 import AuthorityResolutionError, load_content_ledger


REQUEST_SCHEMA_VERSION = "generation-request-v1.0"
SOURCE_PLAN_SCHEMA_VERSION = "generation-source-plan-v1.0"
RUNTIME_CONTRACT_SCHEMA_VERSION = "content-planning-runtime-contract-v1.0"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ContentPlanResolutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_ARTIFACT_INVALID",
            f"Cannot read JSON artifact: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_ARTIFACT_INVALID",
            f"Artifact must be a JSON object: {path}",
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_recorded_path(pipeline_root: Path, raw_path: Any) -> Path:
    text = str(raw_path or "").strip()
    if not text:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            "Recorded lineage path is missing.",
        )

    candidate = Path(text)
    if candidate.is_file():
        return candidate.resolve()

    normalized = text.replace("\\", "/")
    marker = "/ops-pipeline/"
    marker_index = normalized.lower().find(marker)
    if marker_index >= 0:
        relative = normalized[marker_index + len(marker) :]
        relocated = pipeline_root / Path(relative)
        if relocated.is_file():
            return relocated.resolve()

    relative_candidate = pipeline_root / Path(normalized)
    if relative_candidate.is_file():
        return relative_candidate.resolve()

    raise ContentPlanResolutionError(
        "CONTENT_PLAN_AUTHORITY_MISSING",
        f"Recorded lineage artifact does not exist: {text}",
    )


def verify_lineage_ref(
    pipeline_root: Path,
    reference: dict[str, Any],
    label: str,
) -> Path:
    if not isinstance(reference, dict):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            f"{label} lineage reference is invalid.",
        )

    raw_path = str(reference.get("path") or "")
    expected_sha = str(
        reference.get("file_sha256") or reference.get("sha256") or ""
    )
    if not raw_path or not expected_sha:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            f"{label} lineage requires an explicit path and SHA-256.",
        )

    path = resolve_recorded_path(pipeline_root, raw_path)
    if sha256_file(path) != expected_sha:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            f"{label} SHA-256 does not match the immutable lineage.",
        )
    return path


def load_request_and_source_plan(
    pipeline_root: Path,
    request_id: str,
) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    if not REQUEST_ID_RE.fullmatch(request_id or ""):
        raise ContentPlanResolutionError(
            "GENERATION_REQUEST_ID_INVALID",
            f"Generation Request id is not machine-safe: {request_id!r}",
        )

    request_path = (
        pipeline_root
        / "data"
        / "generation_requests"
        / request_id
        / "generation_request_v1.json"
    )
    source_plan_path = (
        pipeline_root
        / "data"
        / "production_plans"
        / request_id
        / "generation_source_plan_v1.json"
    )

    if not request_path.is_file():
        raise ContentPlanResolutionError(
            "GENERATION_REQUEST_NOT_FOUND",
            f"Generation Request does not exist: {request_id}",
        )
    if not source_plan_path.is_file():
        raise ContentPlanResolutionError(
            "GENERATION_SOURCE_PLAN_REQUIRED",
            f"Generation Source Plan is missing for {request_id}.",
        )

    request = read_json(request_path)
    source_plan = read_json(source_plan_path)

    if (
        request.get("schema_version") != REQUEST_SCHEMA_VERSION
        or str(request.get("request_id") or "") != request_id
    ):
        raise ContentPlanResolutionError(
            "GENERATION_REQUEST_LINEAGE_MISMATCH",
            "Generation Request schema or request_id is invalid.",
        )

    lifecycle = request.get("lifecycle") or {}
    authority = request.get("authority") or {}
    if str(lifecycle.get("status") or "") != "created":
        raise ContentPlanResolutionError(
            "CONTENT_PLANNING_LIFECYCLE_CLOSED",
            "Generation Request is not in the created lifecycle state.",
        )
    if (
        lifecycle.get("generation_started") is True
        or authority.get("script_generation_performed") is True
        or authority.get("generation_batch_created") is True
    ):
        raise ContentPlanResolutionError(
            "CONTENT_PLANNING_STAGE_CLOSED",
            "Script generation already started; Content Planning is closed.",
        )

    batch_root = pipeline_root / "data" / "generation_batches" / request_id
    if batch_root.exists() and any(batch_root.rglob("generation_batch_v1.json")):
        raise ContentPlanResolutionError(
            "CONTENT_PLANNING_STAGE_CLOSED",
            "A Generation Batch already exists for this Request.",
        )

    if (
        source_plan.get("schema_version") != SOURCE_PLAN_SCHEMA_VERSION
        or str(source_plan.get("request_id") or "") != request_id
    ):
        raise ContentPlanResolutionError(
            "GENERATION_SOURCE_PLAN_LINEAGE_MISMATCH",
            "Generation Source Plan schema or request_id is invalid.",
        )

    plan_request = source_plan.get("request") or {}
    if str(plan_request.get("request_sha") or "") != sha256_file(request_path):
        raise ContentPlanResolutionError(
            "GENERATION_SOURCE_PLAN_LINEAGE_MISMATCH",
            (
                "Generation Source Plan does not reference the current immutable "
                "Generation Request SHA-256."
            ),
        )

    coverage = source_plan.get("coverage") or {}
    if coverage.get("status") != "supported":
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_SOURCE_COVERAGE_UNSUPPORTED",
            str(
                coverage.get("reason")
                or coverage.get("code")
                or "Generation Source Plan coverage is not supported."
            ),
        )

    return request_path, request, source_plan_path, source_plan


def resolve_pattern_path(
    pipeline_root: Path,
    source_plan: dict[str, Any],
) -> Path:
    selected = source_plan.get("selected_patterns") or []
    if (
        not isinstance(selected, list)
        or len(selected) != 1
        or not isinstance(selected[0], dict)
    ):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_PATTERN_AUTHORITY_INVALID",
            "Generation Source Plan must select exactly one Approved Pattern.",
        )

    pattern_id = str(selected[0].get("pattern_id") or "")
    expected_sha = str(selected[0].get("approved_pattern_sha") or "")
    if not pattern_id or not expected_sha:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_PATTERN_AUTHORITY_INVALID",
            "Selected Pattern requires pattern_id and approved_pattern_sha.",
        )

    pattern_root = pipeline_root / "data" / "patterns" / "approved"
    matches: list[Path] = []
    for path in pattern_root.rglob("pattern_v1.json"):
        artifact = read_json(path)
        if str(artifact.get("pattern_id") or "") == pattern_id:
            matches.append(path)

    if len(matches) != 1:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_PATTERN_AUTHORITY_AMBIGUITY",
            f"Selected Approved Pattern cannot be uniquely resolved: {pattern_id}",
        )

    path = matches[0]
    if sha256_file(path) != expected_sha:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            "Selected Approved Pattern SHA-256 does not match Generation Source Plan.",
        )
    return path


def resolve_fingerprint_paths(
    pipeline_root: Path,
    source_plan: dict[str, Any],
) -> list[Path]:
    pool = source_plan.get("eligible_case_pool") or []
    if not isinstance(pool, list) or not pool:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_CASE_AUTHORITY_MISSING",
            "Generation Source Plan has no eligible Case pool.",
        )

    resolved: list[Path] = []
    seen: set[str] = set()
    for item in pool:
        if not isinstance(item, dict):
            raise ContentPlanResolutionError(
                "CONTENT_PLAN_CASE_AUTHORITY_INVALID",
                "Eligible Case entry must be an object.",
            )
        case_id = str(item.get("case_id") or "")
        expected_sha = str(item.get("fingerprint_sha") or "")
        if not case_id or not expected_sha or case_id in seen:
            raise ContentPlanResolutionError(
                "CONTENT_PLAN_CASE_AUTHORITY_INVALID",
                "Eligible Case requires a unique case_id and fingerprint_sha.",
            )

        path = (
            pipeline_root
            / "data"
            / "fingerprints"
            / case_id
            / "case_fingerprint_v1.json"
        )
        if not path.is_file():
            raise ContentPlanResolutionError(
                "CONTENT_PLAN_CASE_AUTHORITY_MISSING",
                f"Eligible Case Fingerprint is missing: {case_id}",
            )
        fingerprint = read_json(path)
        if (
            str(fingerprint.get("case_id") or "") != case_id
            or sha256_file(path) != expected_sha
        ):
            raise ContentPlanResolutionError(
                "CONTENT_PLAN_LINEAGE_MISMATCH",
                f"Eligible Case Fingerprint lineage mismatch: {case_id}",
            )
        seen.add(case_id)
        resolved.append(path)

    return resolved


def content_quality_contract(
    request: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    raw = request.get("content_quality_v1")
    if raw is not None:
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            raise ContentPlanResolutionError(
                "CONTENT_QUALITY_NOT_ENABLED",
                "Generation Request explicitly does not enable Content Quality V1.",
            )
        return dict(raw), "generation_request"

    quantity = int(request.get("quantity") or 0)
    if quantity < 1:
        raise ContentPlanResolutionError(
            "GENERATION_REQUEST_INVALID",
            "Generation Request quantity must be positive.",
        )

    candidate_pool_size = min(30, max(8, quantity * 4))
    return (
        {
            "enabled": True,
            "candidate_pool_size": candidate_pool_size,
            "candidate_call_batch_size": min(10, candidate_pool_size),
            "minimum_editorial_score": 3.25,
            "capacity_stop_rule": "no_semantic_duplicate_or_low_quality_padding",
            "effective_gate_accessor_required": True,
        },
        "console_v1_runtime_default",
    )


def resolve_base_planning_memory(
    pipeline_root: Path,
    request: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    """Return the exact memory shape consumed by the remote V1 candidate planner."""
    business_id = str(request.get("persona_id") or "")
    if not business_id:
        raise ContentPlanResolutionError(
            "GENERATION_REQUEST_INVALID",
            "Generation Request persona_id is missing.",
        )

    ledger_path = (
        pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )
    if ledger_path.is_file():
        try:
            ledger = load_content_ledger(pipeline_root, business_id)
        except AuthorityResolutionError as exc:
            raise ContentPlanResolutionError(exc.code, str(exc)) from exc
        return ledger["artifact"], "canonical_content_ledger"

    try:
        historical = has_ledger_worthy_historical_exposure(
            pipeline_root,
            business_id,
        )
    except ContentCreationEntryError as exc:
        raise ContentPlanResolutionError(exc.code, str(exc)) from exc

    if historical:
        raise ContentPlanResolutionError(
            "CONTENT_HISTORY_WITHOUT_LEDGER",
            (
                "Approved and exported content exists but the canonical Content "
                "Ledger is missing."
            ),
        )

    return (
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "created_at": str(request.get("created_at") or ""),
            "business_id": business_id,
            "storage_policy": "append_only_entries_v1",
            "novelty_authority": {
                "strong_memory_statuses": sorted(STRONG_MEMORY_STATUSES),
                (
                    "generated_or_rejected_drafts_"
                    "permanently_reserve_semantic_space"
                ): False,
            },
            "entries": [],
        },
        "ephemeral_empty_history_projection",
    )


def build_runtime_contract(
    *,
    request_path: Path,
    source_plan_path: Path,
    base_planning_memory: dict[str, Any],
    content_memory_source: str,
    quality_contract: dict[str, Any],
    quality_contract_source: str,
) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_CONTRACT_SCHEMA_VERSION,
        "generation_request_sha256": sha256_file(request_path),
        "generation_source_plan_sha256": sha256_file(source_plan_path),
        "content_memory_source": content_memory_source,
        "content_memory_sha256": canonical_sha256(base_planning_memory),
        "content_quality_contract_source": quality_contract_source,
        "content_quality_v1": quality_contract,
    }


def build_context(
    *,
    pipeline_root: Path,
    request_path: Path,
    request: dict[str, Any],
    source_plan_path: Path,
    source_plan: dict[str, Any],
    quality_contract: dict[str, Any],
) -> dict[str, Any]:
    lineage = request.get("lineage") or {}
    persona_path = verify_lineage_ref(
        pipeline_root,
        lineage.get("business_persona_ref") or {},
        "Business Persona",
    )
    speaker_path = verify_lineage_ref(
        pipeline_root,
        lineage.get("speaker_persona_ref") or {},
        "Speaker Persona",
    )
    pattern_path = resolve_pattern_path(pipeline_root, source_plan)
    fingerprint_paths = resolve_fingerprint_paths(pipeline_root, source_plan)

    try:
        context = validate_generation_inputs(
            persona_path,
            request_path,
            source_plan_path,
            pattern_path,
            fingerprint_paths,
            speaker_path,
        )
    except (RuntimeError, FileNotFoundError) as exc:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_INPUT_VALIDATION_FAILED",
            f"Canonical generation input validation failed: {exc}",
        ) from exc

    runtime_request = dict(context["request"])
    runtime_request["content_quality_v1"] = dict(quality_contract)
    context = dict(context)
    context["request"] = runtime_request
    return context


def build_closure_memory(
    *,
    base_memory: dict[str, Any],
    context: dict[str, Any],
    content_memory_source: str,
) -> dict[str, Any]:
    """Prepare the V1.1.1 read-only planning memory without mutating a ledger."""
    memory = copy.deepcopy(base_memory)
    entries = list(memory.get("entries") or [])
    strong_entries = [entry for entry in entries if is_strong_memory(entry)]

    existing_catalog = memory.get("fact_atom_catalog")
    if existing_catalog:
        if not isinstance(existing_catalog, list):
            raise ContentPlanResolutionError(
                "CONTENT_LEDGER_CLOSURE_AUTHORITY_INVALID",
                "Content Ledger fact_atom_catalog must be a list.",
            )
    elif strong_entries:
        raise ContentPlanResolutionError(
            "CONTENT_LEDGER_CLOSURE_AUTHORITY_INCOMPLETE",
            (
                "Strong historical Content exists but the Content Ledger has no "
                "Fact Atom catalog required by the frozen V1.1.1 quality baseline."
            ),
        )
    else:
        safe_fields = set(safe_persona_projection(context["persona"])["facts"])
        memory["fact_atom_catalog"] = build_fact_atom_catalog(
            context["persona"],
            sha256_file(Path(context["paths"]["persona"])),
            safe_fields,
        )

    if strong_entries:
        missing_units = [
            str(entry.get("content_id") or "unknown")
            for entry in strong_entries
            if not isinstance(entry.get("communicated_information_units"), list)
        ]
        if missing_units:
            raise ContentPlanResolutionError(
                "CONTENT_LEDGER_CLOSURE_AUTHORITY_INCOMPLETE",
                (
                    "Strong historical Content lacks communicated-information "
                    "units required by V1.1.1: " + ", ".join(missing_units)
                ),
            )

    memory["planning_projection"] = {
        "mode": "read_only_v1_1_1_closure",
        "source": content_memory_source,
        "written_to_content_ledger": False,
    }
    return memory


def validate_v1_plan(
    *,
    context: dict[str, Any],
    base_memory: dict[str, Any],
    plan: dict[str, Any],
    immutable_request: dict[str, Any],
    runtime_contract: dict[str, Any],
) -> None:
    try:
        validate_content_plan_input(context, plan, base_memory)
    except RuntimeError as exc:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_VALIDATION_FAILED",
            f"V1 Content Plan failed canonical validation: {exc}",
        ) from exc

    if (
        plan.get("schema_version") != PLAN_SCHEMA_VERSION
        or str(plan.get("request_id") or "")
        != str(immutable_request.get("request_id") or "")
    ):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            "V1 Content Plan schema or request_id is invalid.",
        )

    selected = plan.get("selected_concepts") or []
    capacity = plan.get("capacity") or {}
    if not isinstance(selected, list) or not isinstance(capacity, dict):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_INVALID",
            "V1 Content Plan selected_concepts/capacity is invalid.",
        )
    if int(capacity.get("selected_quantity") or 0) != len(selected):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_QUANTITY_INVALID",
            "V1 Content Plan selected quantity is inconsistent.",
        )
    if int(capacity.get("selected_quantity") or 0) > int(
        immutable_request.get("quantity") or 0
    ):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_QUANTITY_INVALID",
            "V1 Content Plan exceeds confirmed Generation Request quantity.",
        )
    if capacity.get("padding_generated") is not False:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_PADDING_FORBIDDEN",
            "Content Plan must never generate Padding.",
        )

    if (plan.get("planning_runtime_contract") or {}) != runtime_contract:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_LINEAGE_MISMATCH",
            "V1 Content Plan runtime contract does not match current Authority.",
        )


def write_or_validate_same(
    path: Path,
    value: dict[str, Any],
    *,
    conflict_code: str,
) -> tuple[dict[str, Any], bool]:
    """Write one immutable JSON artifact or recover an identical existing one."""
    if path.is_file():
        existing = read_json(path)
        if canonical_sha256(existing) != canonical_sha256(value):
            raise ContentPlanResolutionError(
                conflict_code,
                f"Existing immutable Content Plan stage differs: {path}",
            )
        return existing, True

    try:
        write_new_json(path, value)
        return value, False
    except FileExistsError:
        existing = read_json(path)
        if canonical_sha256(existing) != canonical_sha256(value):
            raise ContentPlanResolutionError(
                conflict_code,
                f"Content Plan stage was created concurrently with different content: {path}",
            )
        return existing, True


def validate_final_plan(
    *,
    plan: dict[str, Any],
    request: dict[str, Any],
    v1_1_path: Path,
    closure_memory: dict[str, Any],
    runtime_contract: dict[str, Any],
) -> None:
    if (
        plan.get("schema_version") != PLAN_V1_1_1_SCHEMA_VERSION
        or str(plan.get("request_id") or "") != str(request.get("request_id") or "")
    ):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_LINEAGE_MISMATCH",
            "V1.1.1 Content Plan schema or request_id is invalid.",
        )

    lineage = plan.get("lineage") or {}
    if lineage.get("source_v1_1_content_plan_sha256") != sha256_file(v1_1_path):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_LINEAGE_MISMATCH",
            "V1.1.1 Content Plan does not reference the current V1.1 plan.",
        )
    if lineage.get("content_ledger_sha256") != canonical_sha256(closure_memory):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_LINEAGE_MISMATCH",
            "V1.1.1 Content Plan closure-memory SHA mismatch.",
        )

    selected = plan.get("selected_concepts") or []
    capacity = plan.get("capacity") or {}
    if not isinstance(selected, list) or not isinstance(capacity, dict):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_INVALID",
            "V1.1.1 selected_concepts/capacity is invalid.",
        )
    if int(capacity.get("selected_quantity") or 0) != len(selected):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_QUANTITY_INVALID",
            "V1.1.1 selected quantity is inconsistent.",
        )
    if int(capacity.get("selected_quantity") or 0) > int(request.get("quantity") or 0):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_QUANTITY_INVALID",
            "V1.1.1 selected quantity exceeds the Generation Request.",
        )
    if capacity.get("padding_generated") is not False:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_PADDING_FORBIDDEN",
            "V1.1.1 Content Plan must never generate Padding.",
        )
    if capacity.get("script_generation_performed") is not False:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_STAGE_BOUNDARY_CROSSED",
            "V1.1.1 Content Plan unexpectedly generated scripts.",
        )
    if any(
        item.get("v1_1_1_gate_decision") != "high_quality_novel"
        for item in selected
    ):
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_INVALID_SELECTION",
            "V1.1.1 selected a Concept that did not pass the final quality gate.",
        )
    if (plan.get("planning_runtime_contract") or {}) != runtime_contract:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_LINEAGE_MISMATCH",
            "V1.1.1 runtime contract does not match current Authority.",
        )


def build_v1_1_and_v1_1_1(
    *,
    plan_root: Path,
    v1_path: Path,
    v1_plan: dict[str, Any],
    context: dict[str, Any],
    closure_memory: dict[str, Any],
    runtime_contract: dict[str, Any],
    created_at: str,
) -> tuple[Path, dict[str, Any], bool, Path, dict[str, Any], bool]:
    authorized_fact_values = safe_persona_projection(context["persona"])["facts"]

    v1_1_path = plan_root / "content_plan_v1_1.json"
    try:
        v1_1 = build_content_plan_v1_1(
            v1_plan=v1_plan,
            ledger=closure_memory,
            request=context["request"],
            speaker_type=(context.get("speaker_persona") or {}).get("speaker_type"),
            authorized_fact_values=authorized_fact_values,
            source_artifact_hashes={
                "content_plan_v1": sha256_file(v1_path),
                "content_ledger_v1": canonical_sha256(closure_memory),
                "generation_request_v1": sha256_file(Path(context["paths"]["request"])),
                "generation_source_plan_v1": sha256_file(Path(context["paths"]["source_plan"])),
            },
            created_at=created_at,
        )
    except Exception as exc:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_REEVALUATION_FAILED",
            f"Frozen V1.1 reevaluation failed: {exc}",
        ) from exc
    v1_1 = dict(v1_1)
    v1_1["planning_runtime_contract"] = runtime_contract
    v1_1, v1_1_recovered = write_or_validate_same(
        v1_1_path,
        v1_1,
        conflict_code="CONTENT_PLAN_V1_1_CONFLICT",
    )

    v1_1_1_path = plan_root / "content_plan_v1_1_1.json"
    try:
        v1_1_1 = build_content_plan_v1_1_1(
            v1_1_plan=v1_1,
            ledger=closure_memory,
            request=context["request"],
            source_artifact_hashes={
                "content_plan_v1": sha256_file(v1_path),
                "content_plan_v1_1": sha256_file(v1_1_path),
                "content_ledger_v1": canonical_sha256(closure_memory),
                "generation_request_v1": sha256_file(Path(context["paths"]["request"])),
                "generation_source_plan_v1": sha256_file(Path(context["paths"]["source_plan"])),
            },
            created_at=created_at,
        )
    except Exception as exc:
        raise ContentPlanResolutionError(
            "CONTENT_PLAN_V1_1_1_REEVALUATION_FAILED",
            f"Frozen V1.1.1 closure failed: {exc}",
        ) from exc
    v1_1_1 = dict(v1_1_1)
    v1_1_1["planning_runtime_contract"] = runtime_contract
    v1_1_1["source_remote_planning"] = {
        "source_content_plan_v1_sha256": sha256_file(v1_path),
        "performed": bool(
            (v1_plan.get("planning_call") or {}).get("remote_model_call_performed")
        ),
        "call_count": int(
            (v1_plan.get("planning_call") or {}).get("remote_model_call_count") or 0
        ),
        "model": (v1_plan.get("planning_call") or {}).get("model"),
    }
    v1_1_1, v1_1_1_recovered = write_or_validate_same(
        v1_1_1_path,
        v1_1_1,
        conflict_code="CONTENT_PLAN_V1_1_1_CONFLICT",
    )

    validate_final_plan(
        plan=v1_1_1,
        request=context["request"],
        v1_1_path=v1_1_path,
        closure_memory=closure_memory,
        runtime_contract=runtime_contract,
    )
    return (
        v1_1_path,
        v1_1,
        v1_1_recovered,
        v1_1_1_path,
        v1_1_1,
        v1_1_1_recovered,
    )


def result_from_plans(
    *,
    v1_path: Path,
    v1_plan: dict[str, Any],
    v1_recovered: bool,
    v1_1_path: Path,
    v1_1_plan: dict[str, Any],
    v1_1_recovered: bool,
    final_path: Path,
    final_plan: dict[str, Any],
    final_recovered: bool,
    content_memory_source: str,
    remote_model_called: bool,
) -> dict[str, Any]:
    final_capacity = final_plan.get("capacity") or {}
    selected = final_plan.get("selected_concepts") or []
    candidate_pool = v1_plan.get("candidate_pool") or {}
    planning_call = v1_plan.get("planning_call") or {}

    return {
        "ok": True,
        "request_id": final_plan.get("request_id"),
        "quality_baseline": "v1.1.1",
        "candidate_plan_path": str(v1_path.resolve()),
        "candidate_plan_sha256": sha256_file(v1_path),
        "v1_1_plan_path": str(v1_1_path.resolve()),
        "v1_1_plan_sha256": sha256_file(v1_1_path),
        "content_plan_path": str(final_path.resolve()),
        "content_plan_sha256": sha256_file(final_path),
        "candidate_quantity": int(candidate_pool.get("received_size") or 0),
        "v1_selected_quantity": int(
            (v1_plan.get("capacity") or {}).get("selected_quantity") or 0
        ),
        "v1_1_selected_quantity": int(
            (v1_1_plan.get("capacity") or {}).get("selected_quantity") or 0
        ),
        "selected_quantity": int(final_capacity.get("selected_quantity") or 0),
        "selected_concept_ids": [
            str(concept.get("concept_id") or "") for concept in selected
        ],
        "capacity_status": final_capacity.get("status"),
        "content_memory_source": content_memory_source,
        "model": planning_call.get("model"),
        "plan_remote_model_call_count": int(
            planning_call.get("remote_model_call_count") or 0
        ),
        "candidate_plan_recovered": v1_recovered,
        "v1_1_plan_recovered": v1_1_recovered,
        "final_plan_recovered": final_recovered,
        "remote_model_called": remote_model_called,
        "script_generation_performed": False,
        "generation_batch_created": False,
        "content_ledger_written": False,
    }


def resolve_generation_content_plan(
    *,
    pipeline_root: Path,
    request_id: str,
    transport: Callable[[str], dict[str, Any]] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    pipeline_root = pipeline_root.expanduser().resolve()
    request_path, request, source_plan_path, source_plan = (
        load_request_and_source_plan(pipeline_root, request_id)
    )
    business_id = str(request.get("persona_id") or "")
    if not business_id:
        raise ContentPlanResolutionError(
            "GENERATION_REQUEST_INVALID",
            "Generation Request persona_id is missing.",
        )

    with _business_generation_lock(pipeline_root, business_id):
        request_path, request, source_plan_path, source_plan = (
            load_request_and_source_plan(pipeline_root, request_id)
        )
        quality_contract, quality_contract_source = content_quality_contract(request)
        base_memory, content_memory_source = resolve_base_planning_memory(
            pipeline_root,
            request,
        )
        context = build_context(
            pipeline_root=pipeline_root,
            request_path=request_path,
            request=request,
            source_plan_path=source_plan_path,
            source_plan=source_plan,
            quality_contract=quality_contract,
        )
        runtime_contract = build_runtime_contract(
            request_path=request_path,
            source_plan_path=source_plan_path,
            base_planning_memory=base_memory,
            content_memory_source=content_memory_source,
            quality_contract=quality_contract,
            quality_contract_source=quality_contract_source,
        )
        closure_memory = build_closure_memory(
            base_memory=base_memory,
            context=context,
            content_memory_source=content_memory_source,
        )

        plan_root = pipeline_root / "data" / "content_plans" / request_id
        v1_path = plan_root / "content_plan_v1.json"
        remote_model_called = False
        v1_recovered = False

        if v1_path.is_file():
            v1_plan = read_json(v1_path)
            validate_v1_plan(
                context=context,
                base_memory=base_memory,
                plan=v1_plan,
                immutable_request=request,
                runtime_contract=runtime_contract,
            )
            v1_recovered = True
        else:
            resolved_model = str(model or "").strip()
            if transport is None:
                try:
                    api_key, env_model = load_deepseek_runtime_config()
                except Exception as exc:
                    raise ContentPlanResolutionError(
                        "DEEPSEEK_RUNTIME_CONFIG_INVALID",
                        str(exc),
                    ) from exc
                os.environ["DEEPSEEK_API_KEY"] = api_key
                os.environ["DEEPSEEK_MODEL"] = env_model
                resolved_model = resolved_model or env_model
            elif not resolved_model:
                resolved_model = "test-content-planner"

            try:
                v1_plan = generate_content_plan_v1(
                    context,
                    base_memory,
                    model=resolved_model,
                    transport=transport,
                    created_at=str(request.get("created_at") or ""),
                )
            except Exception as exc:
                raise ContentPlanResolutionError(
                    "CONTENT_PLAN_GENERATION_FAILED",
                    f"Content Concept planning failed: {exc}",
                ) from exc
            if not isinstance(v1_plan, dict):
                raise ContentPlanResolutionError(
                    "CONTENT_PLAN_INVALID",
                    "Content Plan generator did not return an object.",
                )
            v1_plan = dict(v1_plan)
            v1_plan["planning_runtime_contract"] = runtime_contract
            validate_v1_plan(
                context=context,
                base_memory=base_memory,
                plan=v1_plan,
                immutable_request=request,
                runtime_contract=runtime_contract,
            )
            try:
                write_new_json(v1_path, v1_plan)
            except FileExistsError:
                existing = read_json(v1_path)
                if canonical_sha256(existing) != canonical_sha256(v1_plan):
                    raise ContentPlanResolutionError(
                        "CONTENT_PLAN_V1_CONFLICT",
                        "V1 candidate plan was created concurrently with different content.",
                    )
                v1_plan = existing
                v1_recovered = True
            else:
                remote_model_called = True

        (
            v1_1_path,
            v1_1_plan,
            v1_1_recovered,
            final_path,
            final_plan,
            final_recovered,
        ) = build_v1_1_and_v1_1_1(
            plan_root=plan_root,
            v1_path=v1_path,
            v1_plan=v1_plan,
            context=context,
            closure_memory=closure_memory,
            runtime_contract=runtime_contract,
            created_at=str(request.get("created_at") or ""),
        )

        return result_from_plans(
            v1_path=v1_path,
            v1_plan=v1_plan,
            v1_recovered=v1_recovered,
            v1_1_path=v1_1_path,
            v1_1_plan=v1_1_plan,
            v1_1_recovered=v1_1_recovered,
            final_path=final_path,
            final_plan=final_plan,
            final_recovered=final_recovered,
            content_memory_source=content_memory_source,
            remote_model_called=remote_model_called,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve Content Plan through frozen V1.1.1 without generating scripts."
        )
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument(
        "--pipeline-root",
        default=str(Path(__file__).resolve().parents[1]),
    )
    args = parser.parse_args()

    try:
        result = resolve_generation_content_plan(
            pipeline_root=Path(args.pipeline_root),
            request_id=str(args.request_id).strip(),
        )
    except ContentPlanResolutionError as exc:
        print(
            json.dumps(
                {"ok": False, "code": exc.code, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
