from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .canonical_gateway import CanonicalOperationError
from .config import Settings


REQUEST_SCHEMA = "generation-request-v1.0"
CONTENT_PLAN_SCHEMA = "content-plan-v1.1.1"
GENERATION_BATCH_SCHEMA = "generation-batch-v1.0"
APPROVED_BATCH_SCHEMA = "approved-generation-batch-v1.0"
REVIEWED_BATCH_SCHEMA = "reviewed-generation-batch-v1.0"

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,128}$")


def _validate_request_id(request_id: str) -> str:
    value = str(request_id or "").strip()
    if not REQUEST_ID_RE.fullmatch(value):
        raise CanonicalOperationError(
            "CONTENT_DELIVERY_REQUEST_ID_INVALID",
            "Generation Request ID 不合法。",
            "请从当前创作流程恢复正确的 Request 后继续。",
        )
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalOperationError(
            "CONTENT_DELIVERY_ARTIFACT_INVALID",
            f"无法读取 canonical artifact：{path.name}",
            "停止继续处理并检查当前 Request 的 canonical artifacts。",
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalOperationError(
            "CONTENT_DELIVERY_ARTIFACT_INVALID",
            f"canonical artifact 不是 JSON object：{path.name}",
            "停止继续处理并修复该 artifact。",
        )
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_json_output(stdout: str) -> dict[str, Any] | None:
    for line in reversed((stdout or "").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _pipeline_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _run_pipeline_command(
    settings: Settings,
    command: list[str],
    *,
    timeout_seconds: int = 240,
) -> dict[str, Any]:
    try:
        process = subprocess.run(
            command,
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=_pipeline_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanonicalOperationError(
            "CONTENT_DELIVERY_OPERATION_UNAVAILABLE",
            "内容交付操作暂时无法完成。",
            "请保留当前 canonical artifacts，稍后从当前阶段恢复。",
        ) from exc

    parsed = _parse_json_output(process.stdout)
    if process.returncode != 0:
        raise CanonicalOperationError(
            str((parsed or {}).get("code") or "CONTENT_DELIVERY_OPERATION_FAILED"),
            str((parsed or {}).get("message") or "内容交付操作没有完成。"),
            "不要重复创建 Request；请从当前 canonical 状态恢复后继续。",
        )
    if parsed is None:
        raise CanonicalOperationError(
            "CONTENT_DELIVERY_INVALID_OUTPUT",
            "内容交付操作返回了无法识别的结果。",
            "请检查对应 canonical operation 的输出。",
        )
    return parsed


def _request_paths(settings: Settings, request_id: str) -> dict[str, Path]:
    request_id = _validate_request_id(request_id)
    batch_root = (
        settings.pipeline_root
        / "data"
        / "generation_batches"
        / request_id
    )
    legacy_output = (
        settings.pipeline_root
        / "output"
        / f"{request_id}_approved_mix_scripts.xlsx"
    )
    return {
        "request": (
            settings.pipeline_root
            / "data"
            / "generation_requests"
            / request_id
            / "generation_request_v1.json"
        ),
        "source_plan": (
            settings.pipeline_root
            / "data"
            / "production_plans"
            / request_id
            / "generation_source_plan_v1.json"
        ),
        "content_plan_v1": (
            settings.pipeline_root
            / "data"
            / "content_plans"
            / request_id
            / "content_plan_v1.json"
        ),
        "content_plan_v1_1": (
            settings.pipeline_root
            / "data"
            / "content_plans"
            / request_id
            / "content_plan_v1_1.json"
        ),
        "content_plan": (
            settings.pipeline_root
            / "data"
            / "content_plans"
            / request_id
            / "content_plan_v1_1_1.json"
        ),
        "batch_root": batch_root,
        "generation_batch": (
            batch_root / "generation_batch_v1.json"
        ),
        "human_review": (
            batch_root / "generation_human_review_v1.json"
        ),
        "approved_batch": (
            batch_root / "approved_generation_batch_v1.json"
        ),
        "reviewed_batch": (
            batch_root / "reviewed_generation_batch_v1.json"
        ),
        "approval_receipt": (
            batch_root
            / "generation_batch_approval_receipt.json"
        ),
        "export_closure": (
            batch_root
            / "generation_export_closure_v1.json"
        ),
        "legacy_excel": legacy_output,
        "legacy_excel_receipt": (
            legacy_output.with_suffix(
                ".export_receipt.json"
            )
        ),
        "mix_template": (
            settings.pipeline_root
            / "output"
            / "素材混剪&数字人口播混剪文案导入模板.xlsx"
        ),
    }


def _known_fact_value(
    persona: dict[str, Any],
    field: str,
) -> str | None:
    fact = (persona.get("facts") or {}).get(field) or {}
    if fact.get("state") != "known":
        return None
    value = fact.get("value")
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _lineage_persona(
    request: dict[str, Any],
    key: str,
    label: str,
) -> dict[str, Any]:
    ref = (request.get("lineage") or {}).get(key) or {}
    path = Path(
        str(ref.get("path") or "")
    ).expanduser().resolve()
    expected_sha = str(
        ref.get("file_sha256") or ""
    )
    if (
        not path.is_file()
        or not expected_sha
        or _sha256_file(path) != expected_sha
    ):
        raise CanonicalOperationError(
            "CONTENT_DELIVERY_PERSONA_LINEAGE_INVALID",
            f"{label} lineage 无法安全恢复。",
            "停止继续导出并恢复 immutable Generation Request 对应的人设。",
        )
    return _read_json(path)


def _safe_filename_part(
    value: Any,
    *,
    fallback: str,
    max_length: int = 40,
) -> str:
    text = str(value or "").strip()
    text = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "",
        text,
    )
    text = re.sub(r"\s+", "", text)
    text = text.strip(" ._")
    if not text:
        text = fallback
    return text[:max_length]


def _delivery_display_metadata(
    request: dict[str, Any],
) -> dict[str, str]:
    business = _lineage_persona(
        request,
        "business_persona_ref",
        "Business Persona",
    )
    speaker = _lineage_persona(
        request,
        "speaker_persona_ref",
        "Speaker Persona",
    )

    business_name = (
        _known_fact_value(
            business,
            "public_display_name",
        )
        or _known_fact_value(
            business,
            "company_short_name",
        )
        or str(
            request.get("persona_id") or "客户"
        )
    )
    speaker_name = (
        _known_fact_value(
            speaker,
            "public_display_name",
        )
        or str(
            request.get("speaker_persona")
            or "出镜人"
        )
    )

    profile = str(
        request.get("target_profile")
        or request.get("profile")
        or ""
    )
    profile_label = {
        "mix": "Mix 混剪",
        "news": "News 新闻体",
    }.get(
        profile,
        profile or "未知类型",
    )
    filename_profile = {
        "mix": "Mix混剪",
        "news": "News新闻体",
    }.get(
        profile,
        profile or "视频",
    )

    return {
        "business_display_name": business_name,
        "speaker_display_name": speaker_name,
        "profile_label": profile_label,
        "filename_profile": filename_profile,
    }


def _request_date_stamp(
    request: dict[str, Any],
) -> str:
    raw = str(
        request.get("created_at") or ""
    )
    match = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})",
        raw,
    )
    if match:
        return "".join(match.groups())
    return "undated"


def export_filename_for_request(
    request: dict[str, Any],
) -> str:
    metadata = _delivery_display_metadata(
        request
    )
    request_id = str(
        request.get("request_id") or ""
    )
    short_request = (
        request_id.removeprefix("gen_")[:6]
        or "batch"
    )
    quantity = int(
        request.get("quantity") or 0
    )

    parts = [
        _safe_filename_part(
            metadata["business_display_name"],
            fallback="客户",
        ),
        _safe_filename_part(
            metadata["speaker_display_name"],
            fallback="出镜人",
        ),
        _safe_filename_part(
            metadata["filename_profile"],
            fallback="视频",
        ),
        f"{quantity}条",
        _request_date_stamp(request),
        _safe_filename_part(
            short_request,
            fallback="batch",
            max_length=12,
        ),
    ]
    return "_".join(parts) + ".xlsx"


def _resolve_export_artifacts(
    settings: Settings,
    request_id: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    desired_name = (
        export_filename_for_request(
            request
        )
    )
    desired_path = (
        settings.pipeline_root
        / "output"
        / desired_name
    )
    desired_receipt = (
        desired_path.with_suffix(
            ".export_receipt.json"
        )
    )

    paths = _request_paths(
        settings,
        request_id,
    )
    legacy_path = paths["legacy_excel"]
    legacy_receipt = (
        paths["legacy_excel_receipt"]
    )

    if desired_path.is_file():
        actual_path = desired_path
        receipt_path = desired_receipt
        legacy_recovered = False
    elif legacy_path.is_file():
        actual_path = legacy_path
        receipt_path = legacy_receipt
        legacy_recovered = True
    else:
        actual_path = desired_path
        receipt_path = desired_receipt
        legacy_recovered = False

    return {
        "desired_name": desired_name,
        "desired_path": desired_path,
        "actual_path": actual_path,
        "receipt_path": receipt_path,
        "legacy_recovered": (
            legacy_recovered
        ),
    }


def _load_request(settings: Settings, request_id: str) -> tuple[Path, dict[str, Any]]:
    paths = _request_paths(settings, request_id)
    path = paths["request"]
    if not path.is_file():
        raise CanonicalOperationError(
            "GENERATION_REQUEST_NOT_FOUND",
            "Generation Request 不存在。",
            "请返回创作入口重新确认本轮生成。",
        )
    request = _read_json(path)
    if (
        request.get("schema_version") != REQUEST_SCHEMA
        or str(request.get("request_id") or "") != request_id
    ):
        raise CanonicalOperationError(
            "GENERATION_REQUEST_LINEAGE_MISMATCH",
            "Generation Request lineage 不一致。",
            "停止继续处理并恢复正确的 immutable Request。",
        )
    return path, request


def _project_content_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ready": False,
            "schema_version": None,
            "selected_quantity": 0,
            "capacity_status": None,
            "selected_concepts": [],
        }
    plan = _read_json(path)
    if plan.get("schema_version") != CONTENT_PLAN_SCHEMA:
        raise CanonicalOperationError(
            "CONTENT_PLAN_SCHEMA_INVALID",
            "最终 Content Plan 不是 V1.1.1。",
            "停止生成脚本并恢复冻结的 V1.1.1 Content Plan。",
        )
    capacity = plan.get("capacity") or {}
    selected = plan.get("selected_concepts") or []
    return {
        "ready": True,
        "schema_version": plan.get("schema_version"),
        "sha256": _sha256_file(path),
        "selected_quantity": int(capacity.get("selected_quantity") or 0),
        "capacity_status": capacity.get("status"),
        "padding_generated": bool(capacity.get("padding_generated")),
        "selected_concepts": [
            {
                "concept_id": item.get("concept_id"),
                "audience_need": item.get("audience_need"),
                "content_job": item.get("content_job"),
                "primary_topic": item.get("primary_topic"),
                "central_claim": item.get("central_claim"),
                "effective_gate_decision": (
                    item.get("v1_1_1_gate_decision")
                    or item.get("v1_1_gate_decision")
                    or item.get("gate_decision")
                ),
            }
            for item in selected
        ],
    }


def _project_generation_batch(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "ready": False,
            "status": None,
            "generated_count": 0,
            "contents": [],
        }
    batch = _read_json(path)
    if batch.get("schema_version") != GENERATION_BATCH_SCHEMA:
        raise CanonicalOperationError(
            "GENERATION_BATCH_SCHEMA_INVALID",
            "Generation Batch schema 不合法。",
            "停止审核并恢复正确的 Generation Batch。",
        )
    return {
        "ready": True,
        "status": batch.get("status"),
        "sha256": _sha256_file(path),
        "generated_count": len(batch.get("contents") or []),
        "model": batch.get("model"),
        "validation_passed": (batch.get("validation") or {}).get("passed") is True,
        "contents": [
            {
                "content_id": item.get("content_id"),
                "concept_ref": item.get("concept_ref"),
                "title": item.get("title"),
                "narration": item.get("narration"),
                "central_claim": item.get("central_claim"),
                "potential_review_flags": item.get("potential_review_flags") or [],
            }
            for item in batch.get("contents") or []
        ],
    }


def _project_review(paths: dict[str, Path]) -> dict[str, Any]:
    approved_path = paths["approved_batch"]
    reviewed_path = paths["reviewed_batch"]
    approval_receipt = paths["approval_receipt"]

    if approved_path.is_file():
        batch = _read_json(approved_path)
        if batch.get("schema_version") != APPROVED_BATCH_SCHEMA:
            raise CanonicalOperationError(
                "APPROVED_GENERATION_BATCH_INVALID",
                "Approved Generation Batch schema 不合法。",
                "停止导出并恢复正确的 Human Approval artifact。",
            )
        return {
            "completed": True,
            "status": "approved",
            "approved": True,
            "approved_item_count": (
                (batch.get("human_review") or {}).get("approved_item_count")
            ),
            "rejected_item_count": (
                (batch.get("human_review") or {}).get("rejected_item_count")
            ),
            "sha256": _sha256_file(approved_path),
            "receipt_ready": approval_receipt.is_file(),
        }

    if reviewed_path.is_file():
        batch = _read_json(reviewed_path)
        if batch.get("schema_version") != REVIEWED_BATCH_SCHEMA:
            raise CanonicalOperationError(
                "REVIEWED_GENERATION_BATCH_INVALID",
                "Reviewed Generation Batch schema 不合法。",
                "请恢复正确的 Human Review artifact。",
            )
        return {
            "completed": True,
            "status": batch.get("status"),
            "approved": False,
            "approved_item_count": (
                (batch.get("human_review") or {}).get("approved_item_count")
            ),
            "rejected_item_count": (
                (batch.get("human_review") or {}).get("rejected_item_count")
            ),
            "sha256": _sha256_file(reviewed_path),
            "receipt_ready": approval_receipt.is_file(),
        }

    return {
        "completed": False,
        "status": None,
        "approved": False,
        "approved_item_count": 0,
        "rejected_item_count": 0,
        "receipt_ready": False,
    }


def _project_export(
    settings: Settings,
    request_id: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    artifacts = _resolve_export_artifacts(
        settings,
        request_id,
        request,
    )
    output = artifacts["actual_path"]
    receipt = artifacts["receipt_path"]

    if not output.is_file():
        return {
            "completed": False,
            "output_name": (
                artifacts["desired_name"]
            ),
            "receipt_ready": False,
            "legacy_recovered": False,
        }

    if not receipt.is_file():
        raise CanonicalOperationError(
            "EXCEL_EXPORT_RECEIPT_MISSING",
            "Excel 已存在但 Export Receipt 缺失。",
            "不要重新导出；请先恢复对应 Export Receipt。",
        )

    export_receipt = _read_json(
        receipt
    )
    if (
        export_receipt.get(
            "validation_passed"
        )
        is not True
        or export_receipt.get(
            "output_sha256"
        )
        != _sha256_file(output)
    ):
        raise CanonicalOperationError(
            "EXCEL_EXPORT_LINEAGE_MISMATCH",
            "Excel 与 Export Receipt lineage 不一致。",
            "停止交付并恢复正确的导出文件与 Receipt。",
        )

    return {
        "completed": True,
        "output_name": (
            artifacts["desired_name"]
        ),
        "actual_output_name": (
            output.name
        ),
        "output_sha256": (
            export_receipt.get(
                "output_sha256"
            )
        ),
        "exported_row_count": (
            export_receipt.get(
                "exported_row_count"
            )
        ),
        "receipt_ready": True,
        "legacy_recovered": bool(
            artifacts[
                "legacy_recovered"
            ]
        ),
    }


def _project_export_closure(
    settings: Settings,
    request_id: str,
    request: dict[str, Any],
    export: dict[str, Any],
) -> dict[str, Any]:
    paths = _request_paths(
        settings,
        request_id,
    )
    closure_path = paths[
        "export_closure"
    ]

    if not closure_path.is_file():
        return {
            "completed": False,
            "content_ledger_written": False,
            "appended_content_ids": [],
        }

    closure = _read_json(
        closure_path
    )
    if (
        closure.get("schema_version")
        != "generation-export-closure-v1.0"
        or closure.get("request_id")
        != request_id
        or (
            closure.get("validation")
            or {}
        ).get("passed")
        is not True
    ):
        raise CanonicalOperationError(
            "EXPORT_CLOSURE_INVALID",
            "Export Closure artifact 不合法。",
            "停止下一批创作并恢复正确的 Export Closure。",
        )

    business_id = str(
        request.get("persona_id") or ""
    )
    ledger_path = (
        settings.pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )
    ledger_ref = (
        closure.get("content_ledger")
        or {}
    )

    if (
        not ledger_path.is_file()
        or ledger_ref.get(
            "sha256_after"
        )
        != _sha256_file(
            ledger_path
        )
    ):
        raise CanonicalOperationError(
            "EXPORT_CLOSURE_LEDGER_LINEAGE_MISMATCH",
            "Export Closure 与当前 Content Ledger lineage 不一致。",
            "停止下一批创作并恢复 Content Ledger closure。",
        )

    return {
        "completed": True,
        "content_ledger_written": True,
        "closure_sha256": (
            _sha256_file(
                closure_path
            )
        ),
        "content_ledger_sha256": (
            _sha256_file(
                ledger_path
            )
        ),
        "appended_content_ids": (
            ledger_ref.get(
                "appended_content_ids"
            )
            or []
        ),
        "export_verified": bool(
            export.get("completed")
        ),
    }


def get_content_delivery_state(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    request_id = _validate_request_id(
        request_id
    )
    _request_path, request = (
        _load_request(
            settings,
            request_id,
        )
    )
    paths = _request_paths(
        settings,
        request_id,
    )

    source_plan_ready = paths[
        "source_plan"
    ].is_file()
    content_plan = _project_content_plan(
        paths["content_plan"]
    )
    generation = (
        _project_generation_batch(
            paths["generation_batch"]
        )
    )
    review = _project_review(paths)
    export = _project_export(
        settings,
        request_id,
        request,
    )
    export_closure = (
        _project_export_closure(
            settings,
            request_id,
            request,
            export,
        )
    )
    metadata = (
        _delivery_display_metadata(
            request
        )
    )

    if (
        export["completed"]
        and export_closure["completed"]
    ):
        next_action = "EXCEL_EXPORTED"
    elif review["approved"]:
        next_action = "EXPORT_EXCEL"
    elif generation["ready"]:
        next_action = "HUMAN_REVIEW"
    elif content_plan["ready"]:
        next_action = "GENERATE_SCRIPTS"
    elif source_plan_ready:
        next_action = "CREATE_CONTENT_PLAN"
    else:
        next_action = (
            "RESOLVE_GENERATION_SOURCES"
        )

    return {
        "request_id": request_id,
        "business_id": (
            request.get("persona_id")
        ),
        "speaker_id": (
            request.get(
                "speaker_persona"
            )
        ),
        "business_display_name": (
            metadata[
                "business_display_name"
            ]
        ),
        "speaker_display_name": (
            metadata[
                "speaker_display_name"
            ]
        ),
        "profile": (
            request.get(
                "target_profile"
            )
            or request.get("profile")
        ),
        "profile_label": (
            metadata["profile_label"]
        ),
        "confirmed_quantity": int(
            request.get("quantity") or 0
        ),
        "source_plan_ready": (
            source_plan_ready
        ),
        "content_plan": content_plan,
        "generation": generation,
        "review": review,
        "export": export,
        "export_closure": (
            export_closure
        ),
        "next_action": next_action,
        "stop_point_reached": (
            export["completed"]
            and export_closure[
                "completed"
            ]
        ),
    }


def resolve_content_plan(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    request_id = _validate_request_id(request_id)
    _load_request(settings, request_id)
    paths = _request_paths(settings, request_id)

    if paths["content_plan"].is_file():
        return {
            "recovered": True,
            "remote_model_called": False,
            "state": get_content_delivery_state(settings, request_id),
        }

    executable = settings.pipeline_python_executable or settings.python_executable
    result = _run_pipeline_command(
        settings,
        [
            executable,
            str(
                settings.pipeline_root
                / "scripts"
                / "resolve_generation_content_plan_v1.py"
            ),
            "--request-id",
            request_id,
            "--pipeline-root",
            str(settings.pipeline_root),
        ],
        timeout_seconds=300,
    )

    if (
        result.get("script_generation_performed") is not False
        or result.get("generation_batch_created") is not False
        or result.get("content_ledger_written") is not False
    ):
        raise CanonicalOperationError(
            "CONTENT_PLAN_BOUNDARY_CROSSED",
            "Content Plan 阶段越过了允许边界。",
            "停止继续处理并检查 Content Plan operation。",
        )

    return {
        "recovered": bool(result.get("final_plan_recovered")),
        "remote_model_called": bool(result.get("remote_model_called")),
        "result": result,
        "state": get_content_delivery_state(settings, request_id),
    }


def generate_scripts(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    request_id = _validate_request_id(request_id)
    _load_request(settings, request_id)
    paths = _request_paths(settings, request_id)

    if not paths["content_plan"].is_file():
        raise CanonicalOperationError(
            "CONTENT_PLAN_REQUIRED",
            "尚未形成最终 Content Plan V1.1.1。",
            "请先完成 Content Plan，再生成脚本。",
        )

    if paths["generation_batch"].is_file():
        return {
            "recovered": True,
            "remote_model_called": False,
            "state": get_content_delivery_state(settings, request_id),
        }

    executable = settings.pipeline_python_executable or settings.python_executable
    result = _run_pipeline_command(
        settings,
        [
            executable,
            str(
                settings.pipeline_root
                / "scripts"
                / "resolve_generation_batch_v1.py"
            ),
            "--request-id",
            request_id,
            "--pipeline-root",
            str(settings.pipeline_root),
            "--max-attempts",
            "3",
        ],
        timeout_seconds=300,
    )

    if (
        result.get("ok") is not True
        or result.get("ready_for_human_review") is not True
        or result.get("generation_batch_created") is not True
        or result.get("content_ledger_written") is not False
        or result.get("excel_exported") is not False
    ):
        raise CanonicalOperationError(
            "SCRIPT_GENERATION_RESULT_INVALID",
            "Script Generation 没有到达 Human Review Gate。",
            "保留当前 candidate / batch artifacts，并从当前阶段恢复。",
        )

    return {
        "recovered": bool(
            result.get("recovered")
            or result.get("candidate_recovered")
        ),
        "remote_model_called": bool(result.get("remote_model_called")),
        "result": result,
        "state": get_content_delivery_state(settings, request_id),
    }


def submit_generation_review(
    settings: Settings,
    request_id: str,
    *,
    reviewer: str,
    items: list[dict[str, Any]],
    note: str = "",
) -> dict[str, Any]:
    request_id = _validate_request_id(request_id)
    _load_request(settings, request_id)
    paths = _request_paths(settings, request_id)

    if paths["approved_batch"].is_file() or paths["reviewed_batch"].is_file():
        return {
            "recovered": True,
            "state": get_content_delivery_state(settings, request_id),
        }

    batch_path = paths["generation_batch"]
    if not batch_path.is_file():
        raise CanonicalOperationError(
            "GENERATION_BATCH_REQUIRED",
            "尚未形成可审核的 Generation Batch。",
            "请先完成 Script Generation。",
        )

    batch = _read_json(batch_path)
    if (
        batch.get("schema_version") != GENERATION_BATCH_SCHEMA
        or batch.get("status") != "review_required"
        or (batch.get("validation") or {}).get("passed") is not True
    ):
        raise CanonicalOperationError(
            "GENERATION_BATCH_NOT_REVIEWABLE",
            "当前 Generation Batch 不可进入人工批准。",
            "请先解决 Batch validation 或 status 问题。",
        )

    source_ids = [
        str(item.get("content_id") or "")
        for item in batch.get("contents") or []
    ]
    review_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        content_id = str(item.get("content_id") or "").strip()
        decision = str(item.get("decision") or "").strip()
        if (
            not content_id
            or decision not in {"approved", "rejected"}
            or content_id in review_by_id
        ):
            raise CanonicalOperationError(
                "GENERATION_REVIEW_INVALID",
                "人工审核决定不合法或存在重复 Content ID。",
                "请对每条生成内容准确选择批准或拒绝。",
            )
        review_by_id[content_id] = {
            "content_id": content_id,
            "decision": decision,
            "note": str(item.get("note") or "").strip(),
        }

    if set(review_by_id) != set(source_ids):
        raise CanonicalOperationError(
            "GENERATION_REVIEW_INCOMPLETE",
            "人工审核必须覆盖当前 Batch 的每一条内容。",
            "请逐条完成批准或拒绝后再提交。",
        )

    review = {
        "schema_version": "generation-batch-review-v1.0",
        "request_id": request_id,
        "batch_sha256": _sha256_file(batch_path),
        "reviewer": str(reviewer or "").strip(),
        "decision": "approve_items",
        "note": str(note or "").strip(),
        "items": [review_by_id[content_id] for content_id in source_ids],
    }
    if not review["reviewer"]:
        raise CanonicalOperationError(
            "GENERATION_REVIEWER_REQUIRED",
            "人工审核人不能为空。",
            "请重新登录后提交审核。",
        )

    review_path = paths["human_review"]
    review_path.parent.mkdir(parents=True, exist_ok=True)
    if review_path.exists():
        existing = _read_json(review_path)
        if _canonical_sha256(existing) != _canonical_sha256(review):
            raise CanonicalOperationError(
                "GENERATION_REVIEW_CONFLICT",
                "当前 Batch 已存在不同的不可变 Human Review 决定。",
                "不要覆盖旧 Review；请先检查当前 Review Authority。",
            )
    else:
        payload = json.dumps(review, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            with review_path.open("xb") as handle:
                handle.write(payload)
        except FileExistsError as exc:
            existing = _read_json(review_path)
            if _canonical_sha256(existing) != _canonical_sha256(review):
                raise CanonicalOperationError(
                    "GENERATION_REVIEW_CONFLICT",
                    "Human Review 被并发创建且内容不同。",
                    "请刷新当前审核状态后继续。",
                ) from exc

    executable = settings.pipeline_python_executable or settings.python_executable
    try:
        process = subprocess.run(
            [
                executable,
                str(
                    settings.pipeline_root
                    / "scripts"
                    / "approve_generation_batch_v1.py"
                ),
                "--batch",
                str(batch_path),
                "--review-file",
                str(review_path),
            ],
            cwd=settings.repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
            env=_pipeline_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CanonicalOperationError(
            "GENERATION_APPROVAL_UNAVAILABLE",
            "Human Approval operation 暂时无法完成。",
            "Review 已保留；请稍后从同一 Review 恢复批准。",
        ) from exc

    if process.returncode != 0:
        raise CanonicalOperationError(
            "GENERATION_APPROVAL_FAILED",
            (process.stderr or process.stdout or "Human Approval 没有完成。").strip(),
            "不要覆盖 Human Review；请修复 Approval 阶段后重试。",
        )

    state = get_content_delivery_state(settings, request_id)
    return {
        "recovered": False,
        "approved": state["review"]["approved"],
        "state": state,
    }


def export_mix_excel(
    settings: Settings,
    request_id: str,
) -> dict[str, Any]:
    request_id = _validate_request_id(
        request_id
    )
    _request_path, request = (
        _load_request(
            settings,
            request_id,
        )
    )
    paths = _request_paths(
        settings,
        request_id,
    )

    profile = (
        request.get("target_profile")
        or request.get("profile")
    )
    if profile != "mix":
        raise CanonicalOperationError(
            "MIX_EXPORT_PROFILE_REQUIRED",
            "当前 Request 不是 Mix Profile。",
            "请使用对应 Profile 的正式导出流程。",
        )

    if not paths[
        "approved_batch"
    ].is_file():
        raise CanonicalOperationError(
            "APPROVED_GENERATION_BATCH_REQUIRED",
            "Excel 导出需要 Approved Generation Batch。",
            "请先完成人工审核，并确保所有导出项均已批准。",
        )

    if not paths[
        "mix_template"
    ].is_file():
        raise CanonicalOperationError(
            "MIX_EXCEL_TEMPLATE_MISSING",
            "Mix Excel 模板不存在。",
            "请恢复冻结的素材混剪/数字人口播导入模板。",
        )

    artifacts = (
        _resolve_export_artifacts(
            settings,
            request_id,
            request,
        )
    )
    output_path = artifacts[
        "actual_path"
    ]
    excel_recovered = (
        output_path.is_file()
    )

    if not excel_recovered:
        output_path = artifacts[
            "desired_path"
        ]
        executable = (
            settings.pipeline_python_executable
            or settings.python_executable
        )

        try:
            process = subprocess.run(
                [
                    executable,
                    str(
                        settings.pipeline_root
                        / "scripts"
                        / "export_mix_excel_v1.py"
                    ),
                    "--batch",
                    str(
                        paths[
                            "approved_batch"
                        ]
                    ),
                    "--template",
                    str(
                        paths[
                            "mix_template"
                        ]
                    ),
                    "--output",
                    str(output_path),
                ],
                cwd=settings.repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
                env=_pipeline_env(),
            )
        except (
            OSError,
            subprocess.TimeoutExpired,
        ) as exc:
            raise CanonicalOperationError(
                "MIX_EXCEL_EXPORT_UNAVAILABLE",
                "Mix Excel 导出暂时无法完成。",
                "请保留 Approved Batch，稍后恢复导出。",
            ) from exc

        if process.returncode != 0:
            raise CanonicalOperationError(
                "MIX_EXCEL_EXPORT_FAILED",
                (
                    process.stderr
                    or process.stdout
                    or "Mix Excel 导出失败。"
                ).strip(),
                "不要修改 Approved Batch；请修复导出阶段后重试。",
            )

    export_state = _project_export(
        settings,
        request_id,
        request,
    )
    if not export_state["completed"]:
        raise CanonicalOperationError(
            "MIX_EXCEL_EXPORT_NOT_VERIFIED",
            "Excel 已执行但没有通过 Receipt 验证。",
            "停止交付并检查 Excel / Export Receipt lineage。",
        )

    # Existing legacy exports are intentionally
    # not renamed. They are downloaded with the
    # new operator-friendly filename, while the
    # immutable receipt continues to reference
    # the original path.
    actual_output_path = (
        _resolve_export_artifacts(
            settings,
            request_id,
            request,
        )["actual_path"]
    )

    executable = (
        settings.pipeline_python_executable
        or settings.python_executable
    )
    closure_result = (
        _run_pipeline_command(
            settings,
            [
                executable,
                str(
                    settings.pipeline_root
                    / "scripts"
                    / "close_generation_export_v1.py"
                ),
                "--request-id",
                request_id,
                "--pipeline-root",
                str(
                    settings.pipeline_root
                ),
                "--excel",
                str(
                    actual_output_path
                ),
            ],
            timeout_seconds=120,
        )
    )

    if (
        closure_result.get("ok")
        is not True
        or closure_result.get(
            "stop_point_reached"
        )
        is not True
        or closure_result.get(
            "remote_model_called"
        )
        is not False
    ):
        raise CanonicalOperationError(
            "MIX_EXPORT_CLOSURE_INVALID",
            "Excel 已生成，但 Content Ledger closure 没有完成。",
            "不要开始下一批创作；请恢复当前 Export Closure。",
        )

    state = (
        get_content_delivery_state(
            settings,
            request_id,
        )
    )
    if not state[
        "stop_point_reached"
    ]:
        raise CanonicalOperationError(
            "MIX_EXPORT_STOP_POINT_NOT_REACHED",
            "Excel 已导出，但本轮交付事实链仍未闭合。",
            "请检查 Export Receipt 与 Content Ledger Closure。",
        )

    return {
        "recovered": bool(
            excel_recovered
        ),
        "ledger_closure_recovered": (
            bool(
                closure_result.get(
                    "recovered"
                )
            )
        ),
        "state": state,
    }


def exported_excel_path(
    settings: Settings,
    request_id: str,
) -> Path:
    request_id = _validate_request_id(
        request_id
    )
    _request_path, request = (
        _load_request(
            settings,
            request_id,
        )
    )
    artifacts = (
        _resolve_export_artifacts(
            settings,
            request_id,
            request,
        )
    )
    path = artifacts[
        "actual_path"
    ]
    if not path.is_file():
        raise CanonicalOperationError(
            "EXPORTED_EXCEL_NOT_FOUND",
            "正式 Excel 尚未导出。",
            "请先完成人工批准和 Excel Export。",
        )
    return path


def exported_excel_filename(
    settings: Settings,
    request_id: str,
) -> str:
    request_id = _validate_request_id(
        request_id
    )
    _request_path, request = (
        _load_request(
            settings,
            request_id,
        )
    )
    return export_filename_for_request(
        request
    )

