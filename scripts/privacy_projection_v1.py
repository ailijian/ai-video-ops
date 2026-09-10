from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PRIVACY_SCHEMA_VERSION = "privacy-projection-v1"
PRIVACY_POLICY_VERSION = "privacy-policy-v1.0"
SAFE_FOR_EXTERNAL_MODEL = "safe_for_external_model"

REPLACEMENTS = {
    "person_name_private": "[姓名]",
    "phone": "[电话]",
    "email_private": "[邮箱]",
    "precise_private_address": "[地址]",
    "id_card": "[身份证号]",
    "bank_card": "[银行卡号]",
    "order_id": "[订单号]",
    "waybill_id": "[运单号]",
    "private_account_id": "[账号]",
}

PUBLIC_CONTACT_MARKERS = (
    "官方",
    "客服",
    "门店",
    "店铺",
    "公司",
    "企业",
)

PRIVATE_NAME_PATTERN = re.compile(
    r"(?:收件人|联系人|收货人|顾客姓名|订单姓名)\s*[:：]?\s*"
    r"(?P<value>[\u4e00-\u9fff·]{2,6})"
)
PRIVATE_ADDRESS_PATTERN = re.compile(
    r"(?:收件地址|收货地址|配送地址|送货地址|详细地址)\s*[:：]?\s*"
    r"(?P<value>[^,，;；\n]{6,100}?)"
    r"(?=(?:[,，;；]\s*(?:手机|手机号|电话|联系电话|订单号|运单号))|$)"
)
MOBILE_PATTERN = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LANDLINE_PATTERN = re.compile(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)")
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
ID_CARD_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
BANK_CARD_PATTERN = re.compile(
    r"(?:银行卡号|银行卡|卡号)\s*[:：]?\s*"
    r"(?P<value>(?:\d[ -]?){15,18}\d)"
)
ORDER_ID_PATTERN = re.compile(
    r"(?:订单号|订单编号|订单ID|订单id)\s*[:：#]?\s*"
    r"(?P<value>[A-Za-z0-9-]{6,40})",
    re.IGNORECASE,
)
WAYBILL_ID_PATTERN = re.compile(
    r"(?:运单号|快递单号|物流单号)\s*[:：#]?\s*"
    r"(?P<value>[A-Za-z0-9-]{6,40})",
    re.IGNORECASE,
)
PRIVATE_ACCOUNT_PATTERN = re.compile(
    r"(?:私人账号|个人账号|账户ID|用户ID|会员号)\s*[:：#]?\s*"
    r"(?P<value>[A-Za-z0-9_-]{5,40})",
    re.IGNORECASE,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _span(
    kind: str,
    start: int,
    end: int,
    *,
    confidence: str = "high",
    review_required: bool = False,
) -> dict[str, Any]:
    return {
        "type": kind,
        "start": start,
        "end": end,
        "confidence": confidence,
        "review_required": review_required,
    }


def _is_public_contact_context(text: str, start: int) -> bool:
    prefix = text[max(0, start - 12) : start]
    return any(marker in prefix for marker in PUBLIC_CONTACT_MARKERS)


def detect_sensitive_spans(value: Any) -> list[dict[str, Any]]:
    text = str(value)
    candidates: list[dict[str, Any]] = []

    for match in PRIVATE_NAME_PATTERN.finditer(text):
        candidates.append(
            _span(
                "person_name_private",
                match.start("value"),
                match.end("value"),
            )
        )

    for match in PRIVATE_ADDRESS_PATTERN.finditer(text):
        candidates.append(
            _span(
                "precise_private_address",
                match.start("value"),
                match.end("value"),
            )
        )

    for match in MOBILE_PATTERN.finditer(text):
        if not _is_public_contact_context(text, match.start()):
            candidates.append(_span("phone", match.start(), match.end()))

    for match in LANDLINE_PATTERN.finditer(text):
        if not _is_public_contact_context(text, match.start()):
            candidates.append(_span("phone", match.start(), match.end()))

    for match in EMAIL_PATTERN.finditer(text):
        if _is_public_contact_context(text, match.start()):
            candidates.append(
                _span(
                    "email_private",
                    match.start(),
                    match.end(),
                    confidence="medium",
                    review_required=True,
                )
            )
        else:
            candidates.append(
                _span("email_private", match.start(), match.end())
            )

    for match in ID_CARD_PATTERN.finditer(text):
        candidates.append(_span("id_card", match.start(), match.end()))

    for kind, pattern in (
        ("bank_card", BANK_CARD_PATTERN),
        ("order_id", ORDER_ID_PATTERN),
        ("waybill_id", WAYBILL_ID_PATTERN),
        ("private_account_id", PRIVATE_ACCOUNT_PATTERN),
    ):
        for match in pattern.finditer(text):
            candidates.append(
                _span(kind, match.start("value"), match.end("value"))
            )

    candidates.sort(
        key=lambda item: (
            int(item["start"]),
            -(int(item["end"]) - int(item["start"])),
        )
    )
    accepted: list[dict[str, Any]] = []
    for item in candidates:
        if any(
            int(item["start"]) < int(old["end"])
            and int(item["end"]) > int(old["start"])
            for old in accepted
        ):
            continue
        accepted.append(item)
    return accepted


def project_safe_verbatim(value: Any) -> str:
    text = str(value)
    spans = detect_sensitive_spans(text)
    for item in reversed(spans):
        start = int(item["start"])
        end = int(item["end"])
        text = (
            text[:start]
            + REPLACEMENTS[str(item["type"])]
            + text[end:]
        )
    return text


def project_safe_semantic(value: Any) -> str:
    source = str(value)
    spans = detect_sensitive_spans(source)
    if not spans:
        return source

    safe = project_safe_verbatim(source)
    kinds = {str(item["type"]) for item in spans}
    order_context = any(
        marker in source
        for marker in (
            "订单",
            "运单",
            "收件",
            "收货",
            "配送地址",
            "送货地址",
        )
    )
    if order_context:
        if any(
            marker in source
            for marker in ("包装", "购物袋", "标签", "面单")
        ):
            return "购物袋上有订单标签（个人信息已隐藏）"
        return "订单标签包含收件信息（个人信息已隐藏）"
    if kinds <= {"phone", "email_private", "private_account_id"}:
        return "文本包含联系信息（个人信息已隐藏）"
    return safe


def project_value(value: Any, projection: str) -> Any:
    if projection not in {"safe_verbatim", "safe_semantic"}:
        raise ValueError(f"Unknown privacy projection: {projection}")
    if isinstance(value, dict):
        return {
            key: project_value(item, projection)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [project_value(item, projection) for item in value]
    if isinstance(value, tuple):
        return [project_value(item, projection) for item in value]
    if isinstance(value, str):
        if projection == "safe_verbatim":
            return project_safe_verbatim(value)
        return project_safe_semantic(value)
    return value


def build_privacy_annotation(
    *,
    source_ref: str,
    field: str,
    value: Any,
) -> dict[str, Any]:
    text = str(value)
    spans = detect_sensitive_spans(text)
    return {
        "source_ref": source_ref,
        "field": field,
        "annotations": spans,
        "safe_verbatim": project_safe_verbatim(text),
        "safe_semantic": project_safe_semantic(text),
        "redaction_applied": bool(spans),
    }


def assert_safe_for_external_model(rendered_prompt: str) -> None:
    remaining = [
        item
        for item in detect_sensitive_spans(rendered_prompt)
        if item.get("confidence") == "high"
    ]
    if remaining:
        kinds = sorted({str(item["type"]) for item in remaining})
        raise RuntimeError(
            "Remote Model Egress Gate blocked high-confidence PII: "
            + ", ".join(kinds)
        )


def load_privacy_projection(
    path_value: str | Path,
    *,
    expected_case_id: str,
) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if str(artifact.get("case_id")) != str(expected_case_id):
        raise RuntimeError("Privacy projection case_id mismatch.")
    if artifact.get("validation", {}).get("passed") is not True:
        raise RuntimeError("Privacy projection validation is not passed.")
    if (
        artifact.get("validation", {}).get("raw_sources_modified")
        is not False
    ):
        raise RuntimeError(
            "Privacy projection does not attest raw_sources_modified=false."
        )
    if artifact.get("privacy_policy_version") != PRIVACY_POLICY_VERSION:
        raise RuntimeError("Privacy policy version mismatch.")
    return {
        "path": str(path),
        "artifact": artifact,
        "privacy_projection_sha256": sha256_file(path),
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
    }


def require_privacy_projection_for_egress(
    privacy_context: dict[str, Any] | None,
) -> None:
    if privacy_context is None:
        raise RuntimeError(
            "A validated --privacy-projection artifact is required "
            "before any remote model call."
        )


def build_egress_audit(
    *,
    safe_input: Any,
    rendered_prompt: str,
    privacy_context: dict[str, Any] | None,
) -> dict[str, Any]:
    assert_safe_for_external_model(rendered_prompt)
    return {
        "privacy_state": SAFE_FOR_EXTERNAL_MODEL,
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "privacy_projection_sha256": (
            privacy_context.get("privacy_projection_sha256")
            if privacy_context
            else None
        ),
        "safe_input_sha256": sha256_json(safe_input),
        "rendered_prompt_sha256": sha256_text(rendered_prompt),
    }


def scan_sensitive_values(value: Any, path: str = "$") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(scan_sensitive_values(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(scan_sensitive_values(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        spans = detect_sensitive_spans(value)
        if spans:
            found.append({"field": path, "annotations": spans})
    return found


def forbidden_raw_fields(value: Any, path: str = "$") -> list[str]:
    forbidden = {
        "ocr_raw",
        "transcript_raw",
        "source_text",
        "source_full_text",
        "reviewed_text",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in forbidden and isinstance(item, str):
                found.append(child)
            found.extend(forbidden_raw_fields(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(forbidden_raw_fields(item, f"{path}[{index}]"))
    return found


def build_case_privacy_gate(
    *,
    privacy_context: dict[str, Any],
    derived_artifact: Any,
) -> dict[str, Any]:
    artifact = privacy_context["artifact"]
    validation = artifact.get("validation", {})
    sensitive = scan_sensitive_values(derived_artifact)
    raw_fields = forbidden_raw_fields(derived_artifact)
    unresolved = int(validation.get("unresolved_sensitive_items") or 0)
    review_required = int(validation.get("review_required_items") or 0)
    scan_passed = not sensitive and not raw_fields
    library_safe = (
        validation.get("passed") is True
        and unresolved == 0
        and review_required == 0
        and scan_passed
    )
    return {
        "library_safe": library_safe,
        "unresolved_sensitive_items": unresolved,
        "review_required_items": review_required,
        "source_projection_ref": privacy_context["path"],
        "source_projection_sha256": privacy_context[
            "privacy_projection_sha256"
        ],
        "policy_version": PRIVACY_POLICY_VERSION,
        "derived_artifact_scan_passed": scan_passed,
        "derived_sensitive_item_count": len(sensitive),
        "forbidden_raw_field_count": len(raw_fields),
    }


def validate_case_privacy_gate(case: dict[str, Any]) -> None:
    gate = case.get("privacy_gate")
    if not isinstance(gate, dict):
        raise RuntimeError("Case has no privacy_gate.")
    if gate.get("library_safe") is not True:
        raise RuntimeError("Case privacy_gate.library_safe is not true.")
    if int(gate.get("unresolved_sensitive_items") or 0) != 0:
        raise RuntimeError(
            "Case privacy gate has unresolved sensitive items."
        )
    if gate.get("derived_artifact_scan_passed") is not True:
        raise RuntimeError("Case derived artifact privacy scan is not passed.")
    if gate.get("policy_version") != PRIVACY_POLICY_VERSION:
        raise RuntimeError("Case privacy policy version mismatch.")
