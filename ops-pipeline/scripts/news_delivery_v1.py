from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from human_review_operations_v1 import io_path
from profile_compatibility_consumers_v1_1 import guarded as compatibility_guarded

from news_slot_recommendation_v1 import (
    MAX_SLOTS,
    MIN_SLOTS,
    NewsSlotRecommendationError,
    build_recommendation,
)


REQUEST_SCHEMA = "news-delivery-request-v1.0"
PLAN_SCHEMA = "news-delivery-plan-v1.0"
REQUEST_SCHEMA_V1_1 = "news-delivery-request-v1.1"
REQUEST_SCHEMA_V1_2 = "news-delivery-request-v1.2"
PLAN_SCHEMA_V1_1 = "news-delivery-plan-v1.1"
REVIEW_SCHEMA = "news-delivery-human-review-v1.0"
REVIEW_SCHEMA_V1_1 = "news-delivery-human-review-v1.1"
APPROVED_SCHEMA = "approved-news-delivery-v1.0"
EXPORT_RECEIPT_SCHEMA = "news-dynamic-excel-export-receipt-v1.0"
CLOSURE_SCHEMA = "news-delivery-export-closure-v1.0"

PRICE_PATTERN_ID = "pcv1_news_price_offer_led_micro_information"

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

FORBIDDEN_STRENGTHENING = (
    "最低",
    "最便宜",
    "第一",
    "顶级",
    "全网",
    "保证",
    "绝对",
    "仅需",
    "只要",
    "超值",
    "最划算",
)

PRESERVED_QUALIFIERS = (
    "通常",
    "约",
    "左右",
    "免费",
)


class NewsDeliveryError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(io_path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_ARTIFACT_INVALID",
            f"Cannot read JSON artifact: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_ARTIFACT_INVALID",
            f"JSON artifact must be an object: {path}",
        )
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with io_path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_new_json(path: Path, value: dict[str, Any]) -> str:
    if value.get('schema_version') in {'news-dynamic-excel-export-receipt-v1.1','news-delivery-export-closure-v1.1'}:
        from profile_compatibility_decisions_v1_1 import write_once
        return write_once(path,value)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_IMMUTABLE_CONFLICT",
            f"Immutable artifact already exists: {path}",
        ) from exc
    return hashlib.sha256(payload).hexdigest()


def _normalize(value: Any) -> str:
    return re.sub(
        r"[\W_]+",
        "",
        str(value or "").lower(),
        flags=re.UNICODE,
    )


def _numbers(value: Any) -> tuple[str, ...]:
    return tuple(re.findall(r"\d+(?:\.\d+)?", str(value or "")))


def _column_letter(index: int) -> str:
    if not 1 <= index <= 26:
        raise NewsDeliveryError(
            "NEWS_EXCEL_COLUMN_RANGE_UNSUPPORTED",
            "News Delivery V1 supports only A-Z columns.",
        )
    return chr(ord("A") + index - 1)


def _inline_cell(
    address: str,
    value: str,
    *,
    style: int,
) -> ET.Element:
    cell = ET.Element(
        f"{{{MAIN_NS}}}c",
        {
            "r": address,
            "s": str(style),
            "t": "inlineStr",
        },
    )
    inline = ET.SubElement(
        cell,
        f"{{{MAIN_NS}}}is",
    )
    text = ET.SubElement(
        inline,
        f"{{{MAIN_NS}}}t",
    )
    text.text = value
    return cell


def _empty_cell(
    address: str,
    *,
    style: int,
) -> ET.Element:
    return ET.Element(
        f"{{{MAIN_NS}}}c",
        {
            "r": address,
            "s": str(style),
        },
    )


def _row_by_number(
    sheet_data: ET.Element,
    row_number: int,
) -> ET.Element:
    row = sheet_data.find(
        f"{{{MAIN_NS}}}row[@r='{row_number}']"
    )
    if row is None:
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_INVALID",
            f"Template row {row_number} is missing.",
        )
    return row


def _replace_row_cells(
    row: ET.Element,
    cells: list[ET.Element],
    *,
    span_end: int,
) -> None:
    for child in list(row):
        if child.tag == f"{{{MAIN_NS}}}c":
            row.remove(child)
    row.set("spans", f"1:{span_end}")
    for cell in cells:
        row.append(cell)


def _xlsx_sheet_values(
    path: Path,
    *,
    row_number: int,
    max_columns: int,
) -> list[str]:
    with zipfile.ZipFile(path, "r") as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(
                archive.read("xl/sharedStrings.xml")
            )
            for item in root.findall(
                f"{{{MAIN_NS}}}si"
            ):
                shared.append(
                    "".join(
                        node.text or ""
                        for node in item.iter(
                            f"{{{MAIN_NS}}}t"
                        )
                    )
                )

        sheet = ET.fromstring(
            archive.read("xl/worksheets/sheet1.xml")
        )
        row = sheet.find(
            f".//{{{MAIN_NS}}}row[@r='{row_number}']"
        )
        values: dict[int, str] = {}
        if row is None:
            return [""] * max_columns

        for cell in row.findall(
            f"{{{MAIN_NS}}}c"
        ):
            address = str(cell.get("r") or "")
            match = re.match(r"([A-Z]+)", address)
            if not match:
                continue
            letters = match.group(1)
            if len(letters) != 1:
                continue
            column = ord(letters) - ord("A") + 1
            if column > max_columns:
                continue

            cell_type = cell.get("t")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or ""
                    for node in cell.iter(
                        f"{{{MAIN_NS}}}t"
                    )
                )
            else:
                node = cell.find(
                    f"{{{MAIN_NS}}}v"
                )
                raw = node.text if node is not None else ""
                if cell_type == "s" and raw:
                    value = shared[int(raw)]
                else:
                    value = raw or ""
            values[column] = value

        return [
            values.get(index, "")
            for index in range(
                1,
                max_columns + 1,
            )
        ]


def _news_workbook_parts(template_path: Path, titles: list[str]) -> dict[str, bytes]:
    """Pure native template projection; every output member is contract-owned."""
    import io
    count = len(titles)
    if not MIN_SLOTS <= count <= MAX_SLOTS or any(not isinstance(t, str) or not t.strip() for t in titles):
        raise NewsDeliveryError("NEWS_EXCEL_SLOT_COUNT_INVALID", "News requires 4–8 approved titles.")
    with zipfile.ZipFile(template_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise NewsDeliveryError("NEWS_EXCEL_TEMPLATE_INVALID", "Invalid trusted template ZIP.")
        parts = {name: archive.read(name) for name in names}
    last_column = _column_letter(count)
    headers = [f"标题{index}" for index in range(1, count + 1)]
    tree = ET.ElementTree(ET.fromstring(parts["xl/worksheets/sheet1.xml"]))
    root = tree.getroot()

    dimension = root.find(
        f"{{{MAIN_NS}}}dimension"
    )
    if dimension is None:
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_INVALID",
            "Template dimension is missing.",
        )
    dimension.set(
        "ref",
        f"A1:{last_column}5",
    )

    cols = root.find(
        f"{{{MAIN_NS}}}cols"
    )
    if cols is None:
        cols = ET.Element(
            f"{{{MAIN_NS}}}cols"
        )
        sheet_format = root.find(
            f"{{{MAIN_NS}}}sheetFormatPr"
        )
        insert_index = (
            list(root).index(sheet_format)
            + 1
            if sheet_format is not None
            else 0
        )
        root.insert(
            insert_index,
            cols,
        )

    for child in list(cols):
        cols.remove(child)

    widths = [
        33.0769230769231,
        46.9519230769231,
        30.125,
        24.8461538461538,
        22.4615384615385,
        24.6153846153846,
        24.6153846153846,
        24.6153846153846,
    ]
    for index in range(1, count + 1):
        ET.SubElement(
            cols,
            f"{{{MAIN_NS}}}col",
            {
                "min": str(index),
                "max": str(index),
                "width": str(widths[index - 1]),
                "style": "1",
                "customWidth": "1",
            },
        )
    if count < 16384:
        ET.SubElement(
            cols,
            f"{{{MAIN_NS}}}col",
            {
                "min": str(count + 1),
                "max": "16384",
                "width": "9.23076923076923",
                "style": "1",
            },
        )

    sheet_data = root.find(
        f"{{{MAIN_NS}}}sheetData"
    )
    if sheet_data is None:
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_INVALID",
            "Template sheetData is missing.",
        )

    row1 = _row_by_number(
        sheet_data,
        1,
    )
    _replace_row_cells(
        row1,
        [
            _inline_cell(
                "A1",
                "新闻体视频文案批量导入",
                style=2,
            )
        ],
        span_end=count,
    )

    row2 = _row_by_number(
        sheet_data,
        2,
    )
    _replace_row_cells(
        row2,
        [
            _inline_cell(
                "A2",
                (
                    "填写说明：\n"
                    "1. 请勿修改表头。\n"
                    "2. 从第5行开始填写。\n"
                    "3. 一行代表一个视频，"
                    "系统按内容推荐4–8个信息标题。\n"
                    "4. 标题数量由内容容量决定，"
                    "不随机、不重复补齐。\n"
                    "5. 建议标题保持简洁，"
                    "但事实完整性优先于字数。"
                ),
                style=3,
            ),
            _empty_cell(
                "B2",
                style=4,
            ),
        ],
        span_end=max(2, count),
    )

    row3 = _row_by_number(
        sheet_data,
        3,
    )
    _replace_row_cells(
        row3,
        [
            _inline_cell(
                "A3",
                "正式内容（请勿删除表头）",
                style=5,
            )
        ],
        span_end=count,
    )

    row4 = _row_by_number(
        sheet_data,
        4,
    )
    _replace_row_cells(
        row4,
        [
            _inline_cell(
                f"{_column_letter(index)}4",
                header,
                style=6,
            )
            for index, header in enumerate(
                headers,
                start=1,
            )
        ],
        span_end=count,
    )

    row5 = _row_by_number(
        sheet_data,
        5,
    )
    _replace_row_cells(
        row5,
        [
            _inline_cell(
                f"{_column_letter(index)}5",
                title,
                style=7,
            )
            for index, title in enumerate(
                titles,
                start=1,
            )
        ],
        span_end=count,
    )

    merge_cells = root.find(
        f"{{{MAIN_NS}}}mergeCells"
    )
    if merge_cells is None:
        merge_cells = ET.SubElement(
            root,
            f"{{{MAIN_NS}}}mergeCells",
        )
    for child in list(merge_cells):
        merge_cells.remove(child)

    merges = [
        f"A1:{last_column}1",
        "A2:B2",
        f"A3:{last_column}3",
    ]
    merge_cells.set(
        "count",
        str(len(merges)),
    )
    for ref in merges:
        ET.SubElement(
            merge_cells,
            f"{{{MAIN_NS}}}mergeCell",
            {"ref": ref},
        )

    ET.register_namespace(
        "",
        MAIN_NS,
    )
    ET.register_namespace(
        "r",
        REL_NS,
    )
    buffer = io.BytesIO()
    tree.write(
        buffer,
        encoding="utf-8",
        xml_declaration=True,
    )

    parts["xl/worksheets/sheet1.xml"] = buffer.getvalue()
    return parts


def export_dynamic_news_xlsx(*, template_path: Path, output_path: Path, titles: list[str]) -> dict[str, Any]:
    template_sha = sha256_file(template_path)
    parts = _news_workbook_parts(template_path, titles)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(parts.items()):
                archive.writestr(name, content)
    except FileExistsError as exc:
        raise NewsDeliveryError("NEWS_EXCEL_OUTPUT_EXISTS", "Export output already exists.") from exc
    if sha256_file(template_path) != template_sha:
        raise NewsDeliveryError("NEWS_EXCEL_TEMPLATE_MUTATED", "Template changed during export; retain the staged evidence.")
    from news_export_recovery_v1 import validate_workbook
    validate_workbook(output_path, template_path, titles)
    return {"slot_count": len(titles), "headers": [f"标题{i}" for i in range(1, len(titles)+1)],
        "titles": titles, "template_sha256": template_sha, "output_sha256": sha256_file(output_path),
        "validation_passed": True}



def _latest_approved_persona(
    pipeline_root: Path,
    persona_id: str,
    scope: str,
) -> tuple[Path, dict[str, Any]]:
    persona_root = (
        pipeline_root
        / "data"
        / "personas"
    )
    candidates: list[
        tuple[int, Path, dict[str, Any]]
    ] = []

    for path in persona_root.rglob(
        "persona_v1.json"
    ):
        persona = read_json(path)
        if str(
            persona.get("persona_id")
            or ""
        ) != persona_id:
            continue
        if persona.get(
            "persona_scope",
            "business",
        ) != scope:
            continue
        lifecycle = (
            persona.get("lifecycle")
            or {}
        )
        if (
            lifecycle.get("status")
            != "approved"
            or lifecycle.get("approved")
            is not True
        ):
            continue
        candidates.append(
            (
                int(
                    persona.get(
                        "revision"
                    )
                    or 0
                ),
                path,
                persona,
            )
        )

    if not candidates:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_PERSONA_NOT_APPROVED",
            (
                f"No Approved {scope} Persona "
                f"exists: {persona_id}"
            ),
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            str(item[1]),
        )
    )
    _, path, persona = candidates[-1]
    if scope == "business":
        from customer_constraints_v1 import assert_production_allowed
        assert_production_allowed(persona, path, consumer="news_repurpose")
    return (
        path.resolve(),
        persona,
    )


def _known_fact_value(
    persona: dict[str, Any],
    field: str,
) -> str | None:
    fact = (
        persona.get("facts") or {}
    ).get(field) or {}
    if fact.get("state") != "known":
        return None
    value = fact.get("value")
    if (
        isinstance(value, str)
        and value.strip()
    ):
        return value.strip()
    return None


def _friendly_name(
    value: Any,
    fallback: str,
) -> str:
    text = str(value or "").strip()
    text = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "",
        text,
    )
    text = re.sub(
        r"\s+",
        "",
        text,
    ).strip(" ._")
    return (
        text[:40]
        if text
        else fallback
    )


def _coverage_source(
    pipeline_root: Path,
) -> tuple[Path, dict[str, Any]]:
    from news_runtime_v1_2 import configured,current
    if configured(pipeline_root):
        active,_=current(pipeline_root,reuse_intent='cross_profile_repurpose')
        return active['coverage_path'],active['coverage']
    coverage_root = (
        pipeline_root
        / "data"
        / "creative_coverage"
    )
    candidates: list[
        tuple[int, float, Path, dict[str, Any]]
    ] = []

    for path in coverage_root.rglob(
        "*.json"
    ):
        value = read_json(path)
        validation = (
            value.get(
                "pattern_production_validation"
            )
            or {}
        ).get(
            PRICE_PATTERN_ID,
            {},
        )
        readiness = (
            value.get(
                "news_current_readiness"
            )
            or value.get(
                "news_current_coverage"
            )
            or {}
        )
        passed = (
            validation.get("status")
            == "passed"
            or PRICE_PATTERN_ID
            in (
                readiness.get(
                    "validated_production_paths"
                )
                or []
            )
        )
        if not passed:
            continue
        score = (
            100
            if validation.get(
                "status"
            )
            == "passed"
            else 50
        )
        candidates.append(
            (
                score,
                path.stat().st_mtime,
                path.resolve(),
                value,
            )
        )

    if not candidates:
        raise NewsDeliveryError(
            "NEWS_PRICE_PATH_NOT_PRODUCTION_VALIDATED",
            (
                "No current News coverage artifact "
                "validates the Price / Offer path."
            ),
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
            str(item[2]),
        )
    )
    _, _, path, value = (
        candidates[-1]
    )
    return path, value


def _price_pattern(
    pipeline_root: Path,
) -> tuple[Path, dict[str, Any]]:
    from news_runtime_v1_2 import configured,current
    from profile_compatibility_decisions_v1_1 import resolve_ref
    if configured(pipeline_root):
        active,binding=current(pipeline_root,reuse_intent='cross_profile_repurpose')
        path=resolve_ref(active['bundle_root'],binding['pattern_ref'])
        return path,read_json(path)
    path = (
        pipeline_root
        / "data"
        / "patterns"
        / "approved"
        / PRICE_PATTERN_ID
        / "pattern_v1.json"
    )
    if not path.is_file():
        raise NewsDeliveryError(
            "NEWS_PRICE_PATTERN_MISSING",
            "Approved News Price Pattern is missing.",
        )
    pattern = read_json(path)
    if (
        pattern.get("status")
        != "approved"
        or "news"
        not in (
            pattern.get(
                "compatible_profiles"
            )
            or []
        )
    ):
        raise NewsDeliveryError(
            "NEWS_PRICE_PATTERN_INVALID",
            "News Price Pattern is not Approved for News.",
        )
    return (
        path.resolve(),
        pattern,
    )


def _ledger(
    pipeline_root: Path,
    business_id: str,
) -> tuple[Path, dict[str, Any]]:
    path = (
        pipeline_root
        / "data"
        / "content_ledgers"
        / business_id
        / "content_ledger_v1.json"
    )
    if not path.is_file():
        raise NewsDeliveryError(
            "NEWS_DELIVERY_CONTENT_LEDGER_MISSING",
            (
                "Cross-profile News repurpose "
                "requires a canonical Content Ledger."
            ),
        )
    ledger = read_json(path)
    if ledger.get(
        "business_id"
    ) != business_id:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_LEDGER_BUSINESS_MISMATCH",
            "Content Ledger business identity is invalid.",
        )
    return (
        path.resolve(),
        ledger,
    )


def _source_entry(
    ledger: dict[str, Any],
    source_content_id: str,
) -> dict[str, Any]:
    entry = next(
        (
            item
            for item in (
                ledger.get("entries")
                or []
            )
            if str(
                item.get("content_id")
                or ""
            )
            == source_content_id
        ),
        None,
    )
    if entry is None:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SOURCE_NOT_FOUND",
            (
                "Selected historical content "
                "does not exist in Content Ledger."
            ),
        )
    if str(
        entry.get("status") or ""
    ) not in {
        "approved",
        "exported",
        "published",
    }:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SOURCE_NOT_STRONG_MEMORY",
            (
                "Selected historical content "
                "is not Strong Memory."
            ),
        )
    return entry


def _verify_speaker_business_lineage(
    business_path: Path,
    business: dict[str, Any],
    speaker: dict[str, Any],
) -> None:
    reference = (
        speaker.get(
            "business_persona_ref"
        )
        or {}
    )
    if reference:
        if (
            reference.get(
                "persona_id"
            )
            != business.get(
                "persona_id"
            )
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_SPEAKER_BUSINESS_MISMATCH",
                (
                    "Speaker Persona belongs "
                    "to another Business Persona."
                ),
            )
        expected_sha = str(
            reference.get(
                "sha256"
            )
            or ""
        )
        if (
            expected_sha
            and expected_sha
            != sha256_file(
                business_path
            )
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_SPEAKER_LINEAGE_MISMATCH",
                "Speaker Persona Business lineage SHA changed.",
            )



def _news_presentation_history_for_source(
    ledger: dict[str, Any],
    source_content_id: str,
) -> list[dict[str, Any]]:
    history = (
        (
            ledger.get("extensions")
            or {}
        ).get(
            "presentation_history_v1",
            {},
        ).get(
            "entries"
        )
        or []
    )

    return [
        item
        for item in history
        if (
            item.get(
                "production_profile"
            )
            == "news"
            and item.get(
                "status"
            )
            == "exported"
            and item.get(
                "source_content_ref"
            )
            == source_content_id
            and item.get(
                "selected_pattern_ref"
            )
            == PRICE_PATTERN_ID
        )
    ]

def preview_news_delivery(
    *,
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    reservation_request_id: str | None = None,
) -> dict[str, Any]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )
    business_path, business = (
        _latest_approved_persona(
            pipeline_root,
            business_id,
            "business",
        )
    )
    speaker_path, speaker = (
        _latest_approved_persona(
            pipeline_root,
            speaker_id,
            "speaker",
        )
    )
    _verify_speaker_business_lineage(
        business_path,
        business,
        speaker,
    )
    from news_runtime_v1_2 import configured,validate_personas
    if configured(pipeline_root):
        validate_personas(pipeline_root,business_path,speaker_path,consumer='news_repurpose')
    pattern_path, _pattern = (
        _price_pattern(
            pipeline_root
        )
    )
    coverage_path, _coverage = (
        _coverage_source(
            pipeline_root
        )
    )
    ledger_path, ledger = (
        _ledger(
            pipeline_root,
            business_id,
        )
    )

    candidates: list[
        dict[str, Any]
    ] = []
    already_presented: list[
        dict[str, Any]
    ] = []

    pending_sources = pending_source_ids(pipeline_root, business_id, exclude_request_id=reservation_request_id)
    for entry in (
        ledger.get("entries") or []
    ):
        content_id = str(
            entry.get("content_id")
            or ""
        )
        if not content_id:
            continue
        if content_id in pending_sources:
            continue

        previous_presentations = (
            _news_presentation_history_for_source(
                ledger,
                content_id,
            )
        )
        if previous_presentations:
            already_presented.append(
                {
                    "source_content_id": (
                        content_id
                    ),
                    "source_title": (
                        entry.get("title")
                    ),
                    "presentation_count": len(
                        previous_presentations
                    ),
                    "latest_presentation_id": (
                        previous_presentations[
                            -1
                        ].get(
                            "presentation_id"
                        )
                    ),
                    "latest_exported_at": (
                        previous_presentations[
                            -1
                        ].get(
                            "exported_at"
                        )
                    ),
                    "reason": (
                        "already_exported_with_same_news_price_pattern"
                    ),
                }
            )
            continue

        if str(
            entry.get("status")
            or ""
        ) not in {
            "approved",
            "exported",
            "published",
        }:
            continue
        try:
            recommendation = (
                build_recommendation(
                    ledger=ledger,
                    business_id=business_id,
                    content_id=content_id,
                )
            )
        except NewsSlotRecommendationError:
            continue

        if (
            recommendation.get(
                "status"
            )
            != "supported"
        ):
            continue

        candidates.append(
            {
                "source_content_id": (
                    content_id
                ),
                "source_title": (
                    entry.get("title")
                ),
                "source_central_claim": (
                    entry.get(
                        "central_claim"
                    )
                ),
                "source_status": (
                    entry.get("status")
                ),
                "recommended_slot_count": int(
                    recommendation.get(
                        "recommended_slot_count"
                    )
                    or 0
                ),
                "recommendation_sha256": (
                    canonical_sha256(
                        recommendation
                    )
                ),
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(
                item[
                    "recommended_slot_count"
                ]
            ),
            str(
                item[
                    "source_content_id"
                ]
            ),
        )
    )

    return {
        "schema_version": (
            "news-delivery-preview-v1.0"
        ),
        "business_id": business_id,
        "business_display_name": (
            _known_fact_value(
                business,
                "public_display_name",
            )
            or _known_fact_value(
                business,
                "company_short_name",
            )
            or business_id
        ),
        "speaker_id": speaker_id,
        "speaker_display_name": (
            _known_fact_value(
                speaker,
                "public_display_name",
            )
            or speaker_id
        ),
        "target_profile": "news",
        "reuse_intent": (
            "cross_profile_repurpose"
        ),
        "validated_slice": (
            "price_offer_cross_profile_repurpose"
        ),
        "available": bool(
            candidates
        ),
        "eligible_source_count": len(
            candidates
        ),
        "eligible_sources": candidates,
        "pending_source_count": len(pending_sources),
        "already_presented_source_count": len(
            already_presented
        ),
        "already_presented_sources": (
            already_presented
        ),
        "authority": {
            "frozen_registry_mutated": False,
            "novel_news_globally_ready": False,
            "price_offer_path_production_validated": not configured(pipeline_root),
            **({'isolated_qualification_authorized':True,'production_eligibility_granted':False}
                if configured(pipeline_root) else {}),
            "scene_contrast_path_opened": False,
            "same_source_same_pattern_reexport_blocked": True,
            "remote_model_called": False,
            "content_ledger_written": False,
        },
        "lineage": {
            "business_persona": {
                "path": str(
                    business_path
                ),
                "sha256": sha256_file(
                    business_path
                ),
            },
            "speaker_persona": {
                "path": str(
                    speaker_path
                ),
                "sha256": sha256_file(
                    speaker_path
                ),
            },
            "content_ledger": {
                "path": str(
                    ledger_path
                ),
                "sha256": sha256_file(
                    ledger_path
                ),
            },
            "price_pattern": {
                "path": str(
                    pattern_path
                ),
                "sha256": sha256_file(
                    pattern_path
                ),
            },
            "coverage": {
                "path": str(
                    coverage_path
                ),
                "sha256": sha256_file(
                    coverage_path
                ),
            },
        },
    }


def request_id_for(business_id, speaker_id, source_content_id, idempotency_key):
    return 'news_' + sha256_text('|'.join((business_id, speaker_id, source_content_id, idempotency_key.strip())))[:20]


def batch_source_snapshot(root, business_id, source_content_id, *, publish=False):
    """Immutable evidence for an explicitly selected historical source, not Truth."""
    from human_review_operations_v1 import write_once
    from creative_style_v1 import digest
    import hashlib
    _, ledger = _ledger(Path(root), business_id)
    source = _source_entry(ledger, source_content_id)
    value = {'schema_version': 'news-repurpose-batch-source-v1.0', 'business_id': business_id,
             'source_content_id': source_content_id, 'source_entry': source}
    path = Path(root) / 'data/news_repurpose_source_snapshots' / business_id / (digest(value) + '.json')
    raw = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
    if publish: write_once(path, value)
    return {'owner': 'native-repurpose-source', 'id': source_content_id, 'version': '1',
            'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest()}


def pending_source_ids(root, business_id, *, exclude_request_id=None):
    """Presentation holds never enter semantic novelty or communicated memory."""
    from content_intent_reservations_v1 import directory, events
    from creative_style_v1 import pinned
    root = Path(root); result = set()
    home = directory(root, business_id, 'unused').parent
    for entry in home.iterdir() if home.is_dir() else []:
        if not entry.is_dir() or not entry.name.startswith('news_') or entry.name == exclude_request_id: continue
        chain = events(root, business_id, entry.name)
        if not chain or chain[-1][1]['event'] in ('safely_released','consumed_by_native_closure'): continue
        for reference in chain[0][1]['source_refs']:
            if reference['owner'] != 'native-repurpose-source': continue
            value = pinned(reference)
            if value['business_id'] != business_id or value['source_content_id'] != reference['id']:
                raise NewsDeliveryError('NEWS_DELIVERY_SOURCE_LINEAGE_INVALID','Pending presentation belongs to another business/source')
            result.add(reference['id'])
    for path in (root/'data/news_deliveries').glob('*/news_delivery_request_v1.json'):
        value = read_json(path); rid = value.get('request_id')
        if value.get('business_id') != business_id or rid == exclude_request_id or value.get('batch_admission_ref'): continue
        if rid != path.parent.name: raise NewsDeliveryError('NEWS_DELIVERY_SOURCE_LINEAGE_INVALID','Pending request directory differs')
        if path.with_name('news_delivery_export_closure_v1.json').is_file():
            validate_news_delivery_export(pipeline_root=root, request_id=rid)
            continue
        if request_cancelled(root,rid): continue
        result.add(value['source_content_id'])
    return result


def request_cancelled(root, request_id):
    """Historical negative proof; no current opportunity or C05-head recursion."""
    from creative_style_v1 import artifact,pinned
    import native_batch_v1 as owner
    from content_intent_reservations_v1 import _end_context
    root=Path(root); path=_request_path(root,request_id)
    target=path.with_name('news_delivery_cancellation_v1.json')
    if not target.is_file(): return False
    request=read_json(path);value=read_json(target)
    if request.get('schema_version')!=REQUEST_SCHEMA_V1_2:
        raise NewsDeliveryError('NEWS_DELIVERY_CANCELLATION_INVALID','Only the exact bounded Native request may carry this disposition')
    admission=owner.admission_binding(request.get('batch_admission_ref'),root=root,request=request)
    batch=pinned(admission['batch_intent_ref'])
    _end_context(root,batch,value.get('end_ref'))
    expected={'schema_version':'news-delivery-batch-cancellation-v1.0','disposition':'cancelled_unissued',
        'request_ref':artifact(path,'native-request',request_id,request['schema_version']),
        'batch_intent_ref':admission['batch_intent_ref'],'end_ref':value['end_ref']}
    if value!=expected:
        raise NewsDeliveryError('NEWS_DELIVERY_CANCELLATION_INVALID','Native cancellation identity changed')
    if (any(path.with_name(name).is_file() for name in ('news_delivery_plan_v1.json','news_delivery_human_review_v1.json',
            'approved_news_delivery_v1.json','news_dynamic_excel_export_receipt_v1.json','news_delivery_export_closure_v1.json'))
            or any((path.parent/'publish_copy_v1').rglob('intent.json'))):
        raise NewsDeliveryError('NEWS_DELIVERY_CANCELLATION_INVALID','Cancelled unissued work has unexpected Native execution evidence')
    return value


def cancel_unissued_batch_request(root, request_id, end_ref):
    """Called only inside original C03/C05 short mutation/Business fences."""
    from creative_style_v1 import artifact,pinned
    from human_review_operations_v1 import write_once
    from content_intent_reservations_v1 import _end_context
    import native_batch_v1 as owner
    root=Path(root);path=_request_path(root,request_id);request=read_json(path)
    admission=owner.admission_binding(request.get('batch_admission_ref'),root=root,request=request)
    batch=pinned(admission['batch_intent_ref']);_end_context(root,batch,end_ref)
    if (request.get('schema_version')!=REQUEST_SCHEMA_V1_2
            or any(path.with_name(name).is_file() for name in ('news_delivery_plan_v1.json','news_delivery_human_review_v1.json',
                'approved_news_delivery_v1.json','news_dynamic_excel_export_receipt_v1.json','news_delivery_export_closure_v1.json'))
            or any((path.parent/'publish_copy_v1').rglob('intent.json'))):
        raise NewsDeliveryError('NEWS_DELIVERY_CANCELLATION_BLOCKED','Issued or generated Native work must retain its original recovery')
    value={'schema_version':'news-delivery-batch-cancellation-v1.0','disposition':'cancelled_unissued',
        'request_ref':artifact(path,'native-request',request_id,request['schema_version']),
        'batch_intent_ref':admission['batch_intent_ref'],'end_ref':end_ref}
    target=path.with_name('news_delivery_cancellation_v1.json');write_once(target,value)
    request_cancelled(root,request_id)
    return artifact(target,'native-news-request-resolution',request_id,value['schema_version'])


def _request_root(
    pipeline_root: Path,
    request_id: str,
) -> Path:
    return (
        pipeline_root
        / "data"
        / "news_deliveries"
        / request_id
    )


def _request_path(
    pipeline_root: Path,
    request_id: str,
) -> Path:
    return (
        _request_root(
            pipeline_root,
            request_id,
        )
        / "news_delivery_request_v1.json"
    )


@compatibility_guarded
def create_news_delivery_request(
    *, pipeline_root: Path, business_id: str, speaker_id: str, source_content_id: str,
    idempotency_key: str, created_by_user_id: int | None = None, created_by_phone: str | None = None,
    batch_admission_ref: dict | None = None, authorization_context: dict | None = None,
) -> tuple[dict[str, Any], bool]:
    values = locals().copy()
    if batch_admission_ref is not None:
        from generation_request_handoff_v1 import _business_generation_lock
        with _business_generation_lock(Path(pipeline_root), business_id):
            return _create_news_delivery_request(**values)
    return _create_news_delivery_request(**values)


def _create_news_delivery_request(
    *,
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    source_content_id: str,
    idempotency_key: str,
    created_by_user_id: int | None = None,
    created_by_phone: str | None = None,
    batch_admission_ref: dict | None = None,
    authorization_context: dict | None = None,
) -> tuple[dict[str, Any], bool]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )
    idempotency_key = (
        idempotency_key.strip()
    )
    if not idempotency_key:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_IDEMPOTENCY_REQUIRED",
            "News Delivery requires an idempotency key.",
        )
    if (created_by_user_id is None) != (created_by_phone is None):
        raise NewsDeliveryError(
            "NEWS_REQUEST_CREATOR_INCOMPLETE",
            "Creator user ID and phone snapshot must be provided together.",
        )

    request_id = request_id_for(business_id, speaker_id, source_content_id, idempotency_key)
    path = _request_path(pipeline_root, request_id)
    if path.is_file():
        _, existing = _load_request(pipeline_root, request_id)
        if (existing.get('business_id') != business_id or existing.get('speaker_id') != speaker_id
                or existing.get('source_content_id') != source_content_id
                or existing.get('idempotency_key_sha256') != sha256_text(idempotency_key)
                or existing.get('batch_admission_ref') != batch_admission_ref):
            raise NewsDeliveryError('NEWS_DELIVERY_IDEMPOTENCY_CONFLICT','Original Native request identity differs')
        from news_runtime_v1_2 import configured,current
        if configured(pipeline_root):
            current(pipeline_root,reuse_intent='cross_profile_repurpose',pinned=existing.get('profile_compatibility_v1_2'))
            if existing.get('schema_version') not in (REQUEST_SCHEMA_V1_1, REQUEST_SCHEMA_V1_2):
                raise NewsDeliveryError('NEWS_DELIVERY_BINDING_REQUIRED','原请求需要重新核对新闻体资格。')
        if batch_admission_ref is not None:
            import native_batch_v1 as batch_owner
            batch_owner.validate_admission(batch_admission_ref, root=pipeline_root, context=authorization_context, request=existing)
        return existing, True
    if batch_admission_ref is not None:
        import native_batch_v1 as batch_owner
        from content_intent_reservations_v1 import assert_executable
        from delivery_receipt_recovery_v1 import actor_phone
        if (created_by_user_id!=authorization_context['actor']['user_id'] or created_by_phone!=actor_phone(authorization_context)):
            raise NewsDeliveryError('NEWS_DELIVERY_BATCH_ACTOR_INVALID','Native batch creator differs from its authenticated principal')
        batch_owner.validate_admission(batch_admission_ref, root=pipeline_root, context=authorization_context)
        original=__import__('creative_style_v1').pinned(batch_admission_ref)
        confirmed=__import__('creative_style_v1').pinned(original['batch_intent_ref'])
        batch_owner.policy_qualification(pipeline_root)
        if not batch_owner.running(pipeline_root, confirmed['batch_id']):
            raise NewsDeliveryError('NEWS_DELIVERY_BATCH_PAUSED','No unissued request after batch pause/end')
        assert_executable(pipeline_root,business_id,request_id)
    preview = preview_news_delivery(
        pipeline_root=pipeline_root,
        business_id=business_id,
        speaker_id=speaker_id,
        reservation_request_id=request_id,
    )
    selected = next(
        (
            item
            for item in (
                preview.get(
                    "eligible_sources"
                )
                or []
            )
            if item.get(
                "source_content_id"
            )
            == source_content_id
        ),
        None,
    )
    if selected is None:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SOURCE_NOT_ELIGIBLE",
            (
                "Selected historical content "
                "is not eligible for the validated "
                "News Price / Offer slice."
            ),
        )

    ledger_path, ledger = (
        _ledger(
            pipeline_root,
            business_id,
        )
    )
    source = _source_entry(
        ledger,
        source_content_id,
    )

    template_path = (
        pipeline_root
        / "output"
        / "新闻体视频制作文案导入模板.xlsx"
    )
    if not template_path.is_file():
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_MISSING",
            "Frozen News Excel template is missing.",
        )

    request = {
        "schema_version": REQUEST_SCHEMA,
        "request_id": request_id,
        "created_at": now_iso(),
        "business_id": business_id,
        "speaker_id": speaker_id,
        "target_profile": "news",
        "reuse_intent": (
            "cross_profile_repurpose"
        ),
        "validated_slice": (
            "price_offer_cross_profile_repurpose"
        ),
        "source_content_id": (
            source_content_id
        ),
        "source_content": {
            "status": (
                source.get("status")
            ),
            "title": (
                source.get("title")
            ),
            "central_claim": (
                source.get(
                    "central_claim"
                )
            ),
            "canonical_sha256": (
                canonical_sha256(
                    source
                )
            ),
        },
        "recommended_slot_count": int(
            selected[
                "recommended_slot_count"
            ]
        ),
        "slot_range": {
            "minimum": MIN_SLOTS,
            "maximum": MAX_SLOTS,
        },
        "idempotency_key_sha256": (
            sha256_text(
                idempotency_key
            )
        ),
        "constraints": {
            "random_selection_allowed": False,
            "duplicate_padding_allowed": False,
            "semantic_novelty": False,
            "new_customer_facts_allowed": False,
            "case_facts_may_become_customer_authority": False,
            "human_review_required": True,
            "excel_export_before_human_review": False,
        },
        "lineage": {
            **preview["lineage"],
            "content_ledger_at_request": {
                "path": str(
                    ledger_path
                ),
                "sha256": sha256_file(
                    ledger_path
                ),
            },
            "news_excel_template": {
                "path": str(
                    template_path.resolve()
                ),
                "sha256": sha256_file(
                    template_path
                ),
            },
        },
        "authority": {
            "generation_request_is_immutable": True,
            "frozen_registry_mutated": False,
            "semantic_content_created": False,
            "content_ledger_written": False,
            "presentation_history_written": False,
            "remote_model_called": False,
        },
        "lifecycle": {
            "status": "created",
            "human_review_required": True,
            "exported": False,
        },
    }
    if created_by_user_id is not None:
        request["created_by_user_id"] = created_by_user_id
        request["created_by_phone"] = created_by_phone
    from news_runtime_v1_2 import configured,current
    if configured(pipeline_root):
        request['schema_version']=REQUEST_SCHEMA_V1_1
        request['profile_compatibility_v1_2']=current(pipeline_root,reuse_intent='cross_profile_repurpose')[1]
    if batch_admission_ref is not None:
        request['schema_version']=REQUEST_SCHEMA_V1_2
        request['batch_admission_ref']=batch_admission_ref
        batch_owner.validate_admission(batch_admission_ref, root=pipeline_root, context=authorization_context, request=request)
    write_new_json(
        path,
        request,
    )
    return request, False


def _load_request(
    pipeline_root: Path,
    request_id: str,
) -> tuple[Path, dict[str, Any]]:
    path = _request_path(
        pipeline_root,
        request_id,
    )
    if not path.is_file():
        raise NewsDeliveryError(
            "NEWS_DELIVERY_REQUEST_NOT_FOUND",
            f"News Delivery Request does not exist: {request_id}",
        )
    request = read_json(path)
    if (
        request.get(
            "schema_version"
        )
        not in {REQUEST_SCHEMA,REQUEST_SCHEMA_V1_1,REQUEST_SCHEMA_V1_2}
        or request.get(
            "request_id"
        )
        != request_id
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_REQUEST_INVALID",
            "News Delivery Request schema or identity is invalid.",
        )
    if request.get('schema_version') in (REQUEST_SCHEMA_V1_1, REQUEST_SCHEMA_V1_2):
        from profile_compatibility_contract_v1_2 import BINDING,validate_contract
        value=validate_contract(request.get('profile_compatibility_v1_2'),BINDING)
        if value['target_profile']!='news' or value['reuse_intent']!='cross_profile_repurpose':
            raise NewsDeliveryError('NEWS_DELIVERY_BINDING_INVALID','新闻体来源版本需要重新核对。')
        from news_runtime_v1_2 import validate_request_personas
        validate_request_personas(pipeline_root,request)
    if request.get('schema_version') == REQUEST_SCHEMA_V1_2:
        from native_batch_v1 import admission_binding
        admission_binding(request.get('batch_admission_ref'), root=pipeline_root, request=request)
    return path, request


def _validate_plan_binding(root,request_id,plan):
    request_path,request=_load_request(root,request_id)
    if request.get('schema_version') in (REQUEST_SCHEMA_V1_1, REQUEST_SCHEMA_V1_2):
        if (plan.get('schema_version')!=PLAN_SCHEMA_V1_1
            or plan.get('profile_compatibility_v1_2')!=request['profile_compatibility_v1_2']
            or plan.get('request_sha256')!=sha256_file(request_path)):
            raise NewsDeliveryError('NEWS_DELIVERY_BINDING_INVALID','内容方案与原新闻体请求不一致。')


def _safe_title_projection(
    candidate: dict[str, Any],
) -> str:
    source = str(
        candidate.get(
            "original_known_fact"
        )
        or ""
    ).strip()
    compact = re.sub(
        r"\s+",
        "",
        source,
    )
    match = re.fullmatch(
        r"免费提供(.+)",
        compact,
    )
    if match:
        compact = (
            match.group(1)
            + "免费"
        )
    return compact



def _subject_anchor(value: str) -> str:
    compact = re.sub(
        r"\s+",
        "",
        str(value or ""),
    )
    compact = re.sub(
        r"\d+(?:\.\d+)?",
        "",
        compact,
    )
    for token in (
        "通常",
        "左右",
        "免费",
        "提供",
        "加工费",
        "加工价格",
        "价格",
        "费用",
        "元",
        "块",
        "约",
        "-",
        "–",
        "—",
    ):
        compact = compact.replace(
            token,
            "",
        )
    return _normalize(
        compact
    )

def _validate_title_against_fact(
    title: str,
    source_fact: str,
) -> None:
    title = str(title or "").strip()
    source_fact = str(
        source_fact or ""
    ).strip()

    if not title:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_TITLE_EMPTY",
            "News title cannot be empty.",
        )

    source_numbers = set(
        _numbers(
            source_fact
        )
    )
    title_numbers = set(
        _numbers(
            title
        )
    )

    if not source_numbers.issubset(
        title_numbers
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_TITLE_LOST_NUMERIC_FACT",
            (
                "Human-approved News title "
                "lost a numeric fact from source Authority."
            ),
        )
    if not title_numbers.issubset(
        source_numbers
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_TITLE_ADDED_NUMERIC_FACT",
            (
                "Human-approved News title "
                "introduced a numeric fact not in source Authority."
            ),
        )

    subject_anchor = _subject_anchor(
        source_fact
    )
    if (
        source_numbers
        and len(subject_anchor) >= 2
        and subject_anchor
        not in _subject_anchor(title)
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_TITLE_LOST_SUBJECT",
            (
                "Human-approved News title "
                "lost the subject anchor from source Authority."
            ),
        )

    for qualifier in (
        PRESERVED_QUALIFIERS
    ):
        if (
            qualifier
            in source_fact
            and qualifier
            not in title
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_TITLE_LOST_QUALIFIER",
                (
                    "Human-approved News title "
                    f"lost qualifier: {qualifier}"
                ),
            )

    strengthened = [
        term
        for term in (
            FORBIDDEN_STRENGTHENING
        )
        if (
            term in title
            and term not in source_fact
        )
    ]
    if strengthened:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_TITLE_STRENGTHENED_CLAIM",
            (
                "Human-approved News title "
                "strengthened source Authority: "
                + ", ".join(
                    strengthened
                )
            ),
        )

    source_norm = _normalize(
        source_fact
    )
    title_norm = _normalize(
        title
    )
    if (
        not source_numbers
        and len(title_norm) >= 4
        and len(source_norm) >= 4
        and title_norm not in source_norm
        and source_norm not in title_norm
    ):
        source_chars = set(
            source_norm
        )
        title_chars = set(
            title_norm
        )
        overlap = (
            len(
                source_chars
                & title_chars
            )
            / max(
                1,
                min(
                    len(
                        source_chars
                    ),
                    len(
                        title_chars
                    ),
                ),
            )
        )
        if overlap < 0.65:
            raise NewsDeliveryError(
                "NEWS_DELIVERY_TITLE_NOT_GROUNDED",
                (
                    "Human-approved News title "
                    "is not sufficiently grounded "
                    "in its source Fact Atom."
                ),
            )


def resolve_news_delivery_plan(
    *, pipeline_root: Path, request_id: str,
) -> tuple[dict[str, Any], bool]:
    _,request=_load_request(pipeline_root,request_id)
    if request.get('batch_admission_ref'):
        from novel_news_generation_recovery_v1 import mutation_fence
        with mutation_fence(pipeline_root):
            return _resolve_news_delivery_plan(pipeline_root=pipeline_root,request_id=request_id)
    return _resolve_news_delivery_plan(pipeline_root=pipeline_root,request_id=request_id)


@compatibility_guarded
def _resolve_news_delivery_plan(
    *,
    pipeline_root: Path,
    request_id: str,
) -> tuple[dict[str, Any], bool]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )
    request_path, request = (
        _load_request(
            pipeline_root,
            request_id,
        )
    )
    if request.get('batch_admission_ref'):
        from generation_request_handoff_v1 import _business_generation_lock
        from operation_lock_v1 import operation_lock
        import native_batch_v1 as owner
        with _business_generation_lock(pipeline_root,request['business_id']), \
                operation_lock(pipeline_root,'creation-batch-provider:'+request['business_id']):
            base=_request_root(pipeline_root,request_id)
            if not (base/'news_delivery_plan_v1.json').is_file():
                reference=request['batch_admission_ref'];admission=owner.validate_admission(reference,root=pipeline_root,request=request)
                batch=__import__('creative_style_v1').pinned(admission['batch_intent_ref'])
                owner.assert_principal(pipeline_root,batch['batch_id'],owner.current_context(pipeline_root,batch['batch_id']))
                from content_intent_reservations_v1 import assert_executable
                assert_executable(pipeline_root,request['business_id'],request_id)
                if request_cancelled(pipeline_root,request_id) or not owner.running(pipeline_root,batch['batch_id']):
                    raise NewsDeliveryError('NEWS_DELIVERY_BATCH_PAUSED','No unissued presentation work after batch pause/end')
            return _resolve_news_delivery_plan_locked(pipeline_root=pipeline_root,request_id=request_id)
    return _resolve_news_delivery_plan_locked(pipeline_root=pipeline_root,request_id=request_id)


def _resolve_news_delivery_plan_locked(*, pipeline_root: Path, request_id: str):
    request_path,request=_load_request(pipeline_root,request_id)
    root = _request_root(
        pipeline_root,
        request_id,
    )
    plan_path = (
        root
        / "news_delivery_plan_v1.json"
    )

    if plan_path.is_file():
        existing = read_json(
            plan_path
        )
        if (
            existing.get(
                "request_sha256"
            )
            != sha256_file(
                request_path
            )
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_PLAN_LINEAGE_CONFLICT",
                "Existing News Delivery Plan has different Request lineage.",
            )
        return existing, True

    ledger_path, ledger = (
        _ledger(
            pipeline_root,
            str(
                request["business_id"]
            ),
        )
    )
    source = _source_entry(
        ledger,
        str(
            request[
                "source_content_id"
            ]
        ),
    )

    if (
        canonical_sha256(
            source
        )
        != (
            request.get(
                "source_content"
            )
            or {}
        ).get(
            "canonical_sha256"
        )
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SOURCE_CHANGED",
            (
                "Historical source content changed "
                "after News Delivery Request creation."
            ),
        )

    try:
        recommendation = (
            build_recommendation(
                ledger=ledger,
                business_id=str(
                    request[
                        "business_id"
                    ]
                ),
                content_id=str(
                    request[
                        "source_content_id"
                    ]
                ),
            )
        )
    except NewsSlotRecommendationError as exc:
        raise NewsDeliveryError(
            exc.code,
            str(exc),
        ) from exc

    if (
        recommendation.get(
            "status"
        )
        != "supported"
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_RECOMMENDATION_UNSUPPORTED",
            (
                "Current historical source "
                "cannot produce a supported "
                "4–8 slot News plan."
            ),
        )

    slots: list[
        dict[str, Any]
    ] = []
    for index, candidate in enumerate(
        recommendation.get(
            "selected_candidates"
        )
        or [],
        start=1,
    ):
        title = (
            _safe_title_projection(
                candidate
            )
        )
        source_fact = str(
            candidate.get(
                "original_known_fact"
            )
            or ""
        )
        _validate_title_against_fact(
            title,
            source_fact,
        )

        field = str(
            candidate.get("field")
            or ""
        )
        if (
            index == 1
            and candidate.get(
                "is_price_or_offer_anchor"
            )
        ):
            role = (
                "price_offer_first_semantic_anchor"
            )
        elif field == "pricing_facts":
            role = (
                "price_scope_information"
            )
        elif field == (
            "included_service_facts"
        ):
            role = (
                "included_value_context"
            )
        elif field == (
            "differentiators"
        ):
            role = (
                "trust_context"
            )
        else:
            role = (
                "service_context"
            )

        slots.append(
            {
                "slot_id": (
                    f"S{index:03d}"
                ),
                "order": index,
                "semantic_role": role,
                "proposed_text": title,
                "source_fact_atom_id": (
                    candidate[
                        "fact_atom_id"
                    ]
                ),
                "source_field": field,
                "source_known_fact": source_fact,
                "source_score": (
                    candidate.get(
                        "score"
                    )
                ),
                "price_or_offer_anchor": bool(
                    candidate.get(
                        "is_price_or_offer_anchor"
                    )
                ),
                "soft_length_recommendation": {
                    "recommended_max_characters": 8,
                    "character_count": len(
                        title
                    ),
                    "warning": len(
                        title
                    )
                    > 8,
                    "hard_limit": False,
                },
            }
        )

    if not (
        MIN_SLOTS
        <= len(slots)
        <= MAX_SLOTS
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SLOT_COUNT_INVALID",
            "Resolved News plan is outside the 4–8 slot contract.",
        )

    plan = {
        "schema_version": PLAN_SCHEMA,
        "created_at": now_iso(),
        "request_id": request_id,
        "request_sha256": (
            sha256_file(
                request_path
            )
        ),
        "status": "review_required",
        "business_id": (
            request[
                "business_id"
            ]
        ),
        "speaker_id": (
            request[
                "speaker_id"
            ]
        ),
        "target_profile": "news",
        "reuse_intent": (
            "cross_profile_repurpose"
        ),
        "semantic_novelty": False,
        "source_content_id": (
            request[
                "source_content_id"
            ]
        ),
        "recommended_slot_count": len(
            slots
        ),
        "slots": slots,
        "recommendation": (
            recommendation
        ),
        "authority": {
            "known_historical_fact_atoms_only": True,
            "new_customer_fact_created": False,
            "case_facts_used_as_customer_authority": False,
            "semantic_content_created": False,
            "content_ledger_written": False,
            "presentation_history_written": False,
            "remote_model_called": False,
            "random_selection_used": False,
            "padding_generated": False,
        },
        "lineage": {
            "content_ledger": {
                "path": str(
                    ledger_path
                ),
                "sha256_at_plan": (
                    sha256_file(
                        ledger_path
                    )
                ),
            },
            "source_content_canonical_sha256": (
                canonical_sha256(
                    source
                )
            ),
        },
        "validation": {
            "passed": True,
            "slot_count_between_4_and_8": (
                MIN_SLOTS
                <= len(
                    slots
                )
                <= MAX_SLOTS
            ),
            "first_slot_is_price_or_offer_anchor": bool(
                slots
                and slots[0][
                    "price_or_offer_anchor"
                ]
            ),
            "duplicate_padding_absent": True,
            "remote_model_called": False,
        },
    }
    if request.get('schema_version') in (REQUEST_SCHEMA_V1_1, REQUEST_SCHEMA_V1_2):
        plan['schema_version']=PLAN_SCHEMA_V1_1
        plan['profile_compatibility_v1_2']=request['profile_compatibility_v1_2']
    write_new_json(plan_path,plan)
    return plan, False


def _review_path(
    pipeline_root: Path,
    request_id: str,
) -> Path:
    return (
        _request_root(
            pipeline_root,
            request_id,
        )
        / "news_delivery_human_review_v1.json"
    )


def _approved_path(
    pipeline_root: Path,
    request_id: str,
) -> Path:
    return (
        _request_root(
            pipeline_root,
            request_id,
        )
        / "approved_news_delivery_v1.json"
    )


@compatibility_guarded
def approve_news_delivery(
    *,
    pipeline_root: Path,
    request_id: str,
    review_path: Path,
    verify_only: bool = False,
) -> tuple[
    dict[str, Any],
    bool,
]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )
    root = _request_root(
        pipeline_root,
        request_id,
    )
    plan_path = (
        root
        / "news_delivery_plan_v1.json"
    )
    if not plan_path.is_file():
        raise NewsDeliveryError(
            "NEWS_DELIVERY_PLAN_REQUIRED",
            "Human Review requires a resolved News Delivery Plan.",
        )
    plan = read_json(
        plan_path
    )
    _validate_plan_binding(pipeline_root,request_id,plan)
    if (
        plan.get(
            "schema_version"
        )
        not in {PLAN_SCHEMA,PLAN_SCHEMA_V1_1}
        or plan.get(
            "request_id"
        )
        != request_id
        or plan.get(
            "status"
        )
        != "review_required"
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_PLAN_INVALID",
            "News Delivery Plan is not review-ready.",
        )

    review_path = (
        review_path
        .expanduser()
        .resolve()
    )
    incoming = read_json(
        review_path
    )
    if (
        incoming.get(
            "schema_version"
        )
        not in {
            REVIEW_SCHEMA,
            REVIEW_SCHEMA_V1_1,
        }
        or incoming.get(
            "request_id"
        )
        != request_id
        or incoming.get(
            "decision"
        )
        != "approve_items"
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_REVIEW_INVALID",
            "Human Review schema, identity, or decision is invalid.",
        )

    reviewer = str(
        incoming.get(
            "reviewer"
        )
        or ""
    ).strip()
    if not reviewer:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_REVIEWER_REQUIRED",
            "Human Review requires a reviewer identity.",
        )

    source_slots = (
        plan.get("slots") or []
    )
    source_by_id = {
        str(
            item.get("slot_id")
        ): item
        for item in source_slots
    }
    items = (
        incoming.get("items")
        or []
    )
    if (
        len(items)
        != len(source_slots)
        or {
            str(
                item.get(
                    "slot_id"
                )
            )
            for item in items
        }
        != set(
            source_by_id
        )
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_REVIEW_COVERAGE_INVALID",
            "Human Review must decide every recommended News slot exactly once.",
        )

    approved_slots: list[
        dict[str, Any]
    ] = []

    for item in items:
        slot_id = str(
            item.get("slot_id")
            or ""
        )
        decision = str(
            item.get("decision")
            or ""
        )
        if decision not in {
            "approved",
            "revised",
            "rejected",
        }:
            raise NewsDeliveryError(
                "NEWS_DELIVERY_REVIEW_DECISION_INVALID",
                (
                    "Each News slot must be approved, "
                    "revised, or rejected."
                ),
            )
        if decision == "rejected":
            continue

        source = source_by_id[
            slot_id
        ]

        source_text = str(
            source.get(
                "proposed_text"
            )
            or ""
        ).strip()

        review_schema = str(
            incoming.get(
                "schema_version"
            )
            or ""
        )

        effective_decision = decision

        if decision == "approved":
            legacy_approved_text = str(
                item.get(
                    "approved_text"
                )
                or ""
            ).strip()

            if (
                review_schema
                == REVIEW_SCHEMA
                and legacy_approved_text
                and legacy_approved_text
                != source_text
            ):
                # Backward compatibility:
                # News Human Review V1.0 represented an editorial revision
                # as decision=approved + approved_text.
                # Preserve that historical contract, but project it into
                # the V1.1 reviewed-revision semantics.
                approved_text = (
                    legacy_approved_text
                )
                effective_decision = (
                    "revised"
                )
            else:
                approved_text = source_text

        else:
            approved_text = str(
                item.get(
                    "revised_text"
                )
                or item.get(
                    "approved_text"
                )
                or ""
            ).strip()

            if not approved_text:
                raise NewsDeliveryError(
                    "NEWS_DELIVERY_REVISED_TEXT_REQUIRED",
                    "Revised News title cannot be empty.",
                )

            if approved_text == source_text:
                raise NewsDeliveryError(
                    "NEWS_DELIVERY_EMPTY_REVISION",
                    "Revised decision requires an actual title change.",
                )
        _validate_title_against_fact(
            approved_text,
            str(
                source.get(
                    "source_known_fact"
                )
                or ""
            ),
        )

        approved_slots.append(
            {
                **copy.deepcopy(
                    source
                ),
                "approved_text": (
                    approved_text
                ),
                "human_edited": (
                    approved_text
                    != str(
                        source.get(
                            "proposed_text"
                        )
                        or ""
                    )
                ),
                "human_review_decision": (
                    "revised_and_approved"
                    if effective_decision
                    == "revised"
                    else "approved"
                ),
                "human_revision": (
                    {
                        "revision_number": 1,
                        "revision_type": "human_editorial_projection",
                        "source_text": source_text,
                        "revised_text": approved_text,
                        "source_text_sha256": canonical_sha256(
                            {"text": source_text}
                        ),
                        "revised_text_sha256": canonical_sha256(
                            {"text": approved_text}
                        ),
                        "source_known_fact": source.get(
                            "source_known_fact"
                        ),
                        "guard": {
                            "source_fact_grounding_passed": True,
                            "new_customer_fact_created": False,
                            "semantic_novelty_created": False,
                        },
                    }
                    if effective_decision
                    == "revised"
                    else None
                ),
                "human_note": str(
                    item.get("note")
                    or ""
                ),
            }
        )

    if not (
        MIN_SLOTS
        <= len(
            approved_slots
        )
        <= MAX_SLOTS
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_APPROVED_SLOT_COUNT_INVALID",
            (
                "Final Human-approved News title count "
                f"must remain between {MIN_SLOTS} and {MAX_SLOTS}."
            ),
        )

    if not approved_slots[
        0
    ].get(
        "price_or_offer_anchor"
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_FIRST_ANCHOR_INVALID",
            (
                "First Human-approved News slot "
                "must remain a Price / Offer anchor."
            ),
        )

    normalized = [
        _normalize(
            item[
                "approved_text"
            ]
        )
        for item in approved_slots
    ]
    if len(
        normalized
    ) != len(
        set(
            normalized
        )
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_APPROVED_DUPLICATE",
            "Human-approved News titles contain duplicate semantic text.",
        )

    approved_path = (
        _approved_path(
            pipeline_root,
            request_id,
        )
    )
    canonical_review_path = (
        _review_path(
            pipeline_root,
            request_id,
        )
    )
    if verify_only and not (canonical_review_path.is_file() and approved_path.is_file()):
        raise NewsDeliveryError('NEWS_DELIVERY_APPROVAL_REQUIRED', 'Native Human bundle is incomplete.')

    if canonical_review_path.is_file():
        existing_review = (
            read_json(
                canonical_review_path
            )
        )
        if (
            canonical_sha256(
                existing_review
            )
            != canonical_sha256(
                incoming
            )
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_REVIEW_CONFLICT",
                "Immutable Human Review already exists with different content.",
            )
    else:
        if verify_only:
            raise NewsDeliveryError('NEWS_DELIVERY_APPROVAL_REQUIRED', 'Native Human Review is missing.')
        write_new_json(
            canonical_review_path,
            incoming,
        )

    if approved_path.is_file():
        existing = read_json(
            approved_path
        )
        expected_slots = [{**slot, 'export_header':f'标题{index}', 'export_order':index}
            for index,slot in enumerate(approved_slots,start=1)]
        if (existing.get('approved_slots') != expected_slots
            or existing.get('business_id') != plan['business_id']
            or existing.get('speaker_id') != plan['speaker_id']
            or existing.get('source_content_id') != plan['source_content_id']
            or existing.get('lineage',{}).get('plan_sha256') != sha256_file(plan_path)):
            raise NewsDeliveryError('NEWS_DELIVERY_APPROVED_CONFLICT', 'Approved content differs from the original native Human decision.')
        if (
            (
                existing.get(
                    "human_review"
                )
                or {}
            ).get(
                "review_sha256"
            )
            != sha256_file(
                canonical_review_path
            )
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_APPROVED_CONFLICT",
                "Existing Approved News Delivery has different Human Review lineage.",
            )
        return existing, True

    if verify_only:
        raise NewsDeliveryError('NEWS_DELIVERY_APPROVAL_REQUIRED', 'Native Approved content is missing.')
    approved = {
        "schema_version": (
            APPROVED_SCHEMA
        ),
        "created_at": now_iso(),
        "request_id": request_id,
        "business_id": (
            plan["business_id"]
        ),
        "speaker_id": (
            plan["speaker_id"]
        ),
        "target_profile": "news",
        "status": (
            "approved_for_export"
        ),
        "approval_scope": (
            "cross_profile_repurpose_presentation_not_novel_content"
        ),
        "source_content_id": (
            plan[
                "source_content_id"
            ]
        ),
        "reuse_declaration": {
            "reuse_intent": (
                "cross_profile_repurpose"
            ),
            "semantic_novelty": False,
            "historical_content_reused": True,
            "new_semantic_content_count_delta": 0,
            "new_central_claim_count_delta": 0,
            "new_information_gain_delta": 0,
        },
        "approved_slot_count": len(
            approved_slots
        ),
        "approved_slots": [
            {
                **slot,
                "export_header": (
                    f"标题{index}"
                ),
                "export_order": index,
            }
            for index, slot in enumerate(
                approved_slots,
                start=1,
            )
        ],
        "human_review": {
            "reviewer": reviewer,
            "reviewed_at": (
                incoming.get(
                    "reviewed_at"
                )
                or now_iso()
            ),
            "decision": "approved",
            "human_gate": True,
            "review_path": str(
                canonical_review_path
            ),
            "review_sha256": (
                sha256_file(
                    canonical_review_path
                )
            ),
        },
        "lineage": {
            "plan_path": str(
                plan_path
            ),
            "plan_sha256": (
                sha256_file(
                    plan_path
                )
            ),
        },
        "authority": {
            "approval_is_not_novel_content_approval": True,
            "new_customer_fact_created": False,
            "content_ledger_semantic_entry_to_create": False,
            "presentation_history_entry_to_create": True,
            "remote_model_called": False,
        },
        "validation": {
            "passed": True,
            "approved_slot_count_between_4_and_8": True,
            "first_slot_price_offer_anchor_recoverable": True,
            "duplicate_titles_absent": True,
        },
    }
    write_new_json(
        approved_path,
        approved,
    )
    return approved, False


def _presentation_history_entry(
    *,
    request: dict[str, Any],
    approved: dict[str, Any],
    output_path: Path,
    exported_at: str,
) -> dict[str, Any]:
    return {
        "presentation_id": (
            request[
                "request_id"
            ]
            + "-P001"
        ),
        "business_id": (
            request[
                "business_id"
            ]
        ),
        "speaker_id": (
            request[
                "speaker_id"
            ]
        ),
        "request_id": (
            request[
                "request_id"
            ]
        ),
        "production_profile": "news",
        "reuse_intent": (
            "cross_profile_repurpose"
        ),
        "semantic_novelty": False,
        "historical_content_reused": True,
        "source_content_ref": (
            request[
                "source_content_id"
            ]
        ),
        "selected_pattern_ref": (
            PRICE_PATTERN_ID
        ),
        "status": "exported",
        "approved_at": (
            approved[
                "human_review"
            ][
                "reviewed_at"
            ]
        ),
        "exported_at": exported_at,
        "novel_capacity_delta": 0,
        "new_semantic_content_count_delta": 0,
        "new_central_claim_count_delta": 0,
        "new_information_gain_delta": 0,
        "communicated_information_units_created": False,
        "approved_slot_count": (
            approved[
                "approved_slot_count"
            ]
        ),
        "approved_titles": [
            item[
                "approved_text"
            ]
            for item in (
                approved[
                    "approved_slots"
                ]
            )
        ],
        "approval_ref": {
            "path": str(
                _approved_path(
                    output_path.parents[
                        1
                    ],
                    request[
                        "request_id"
                    ],
                )
            )
            if False
            else None,
        },
        "export_ref": {
            "path": str(
                output_path
            ),
            "sha256": (
                sha256_file(
                    output_path
                )
            ),
        },
        "events": [
            {
                "status": "approved",
                "at": (
                    approved[
                        "human_review"
                    ][
                        "reviewed_at"
                    ]
                ),
                "source": (
                    "human_review"
                ),
            },
            {
                "status": "exported",
                "at": exported_at,
                "source": (
                    "news_dynamic_excel_export_v1"
                ),
            },
        ],
    }


def validate_presentation_history_chain(entries: list[dict]) -> None:
    """Legacy prefix stays immutable; every new event binds its exact prefix."""
    versioned = False
    for index, event in enumerate(entries):
        version = event.get('history_event_schema_version')
        if version is None and not versioned:
            continue
        if (version != 'news-presentation-history-event-v1.1'
            or event.get('history_parent_sha256') != canonical_sha256(entries[:index])):
            raise NewsDeliveryError('NEWS_PRESENTATION_PARENT_CHAIN_INVALID', 'Presentation History parent chain is invalid.')
        versioned = True


def historical_ledger_material(root, request_id, kind, exported_at):
    """Exact archived Native inputs for the Ledger owner's transition replay."""
    from profile_compatibility_decisions_v1_1 import ref,resolve_ref,read,file_sha
    from news_export_recovery_v1 import paths as publication_paths,check,INTENT,validate_prepared,bound_source_paths
    from close_generation_export_v1 import _build_fact_atoms
    from ledger_history_v1 import LedgerHistoryError
    novel=request_id.startswith('gen_')
    if novel:
        import novel_news_v1 as owner
        p=owner._paths(root,request_id);directory=p['approved'].parent
        native_receipt=p['receipt'];native_closure=p['closure']
    else:
        directory=_request_root(root,request_id)
        p={'request':_request_path(root,request_id),'plan':directory/'news_delivery_plan_v1.json',
           'review':_review_path(root,request_id),'approved':_approved_path(root,request_id)}
        native_receipt=directory/'news_dynamic_excel_export_receipt_v1.json';native_closure=directory/'news_delivery_export_closure_v1.json'
    pp=publication_paths(directory);intent=check(read(pp['intent']),INTENT)
    if intent['request_id']!=request_id or intent['created_at']!=exported_at:
        raise LedgerHistoryError('NATIVE_SOURCE_INVALID')
    for key in ('request','plan','review','approved'):
        if resolve_ref(root,intent['sources'][key+'_ref'])!=p[key].resolve():
            raise LedgerHistoryError('NATIVE_SOURCE_INVALID')
    business_path=resolve_ref(root,intent['sources']['business_ref'])
    speaker_path=resolve_ref(root,intent['sources']['speaker_ref'])
    template=resolve_ref(root,intent['template_ref']);output=root/intent['output_path']
    validate_prepared(root,directory,output=output,template=template,titles=intent['titles'],published=True)
    sources={key:ref(root,path) for key,path in p.items() if key in {'request','plan','review','approved'}}
    sources.update({key:ref(root,path) for key,path in {'business':business_path,'speaker':speaker_path,
        'intent':pp['intent'],'prepared':pp['prepared'],'output':output,'template':template}.items()})
    for n,path in enumerate(sorted(bound_source_paths(root,intent['sources']))):sources['lineage_'+str(n)]=ref(root,path)
    request=read(p['request']);approved=read(p['approved']);review=read(p['review']);plan=read(p['plan'])
    if request.get('request_id')!=request_id or approved.get('request_id')!=request_id:
        raise LedgerHistoryError('NATIVE_SOURCE_INVALID')
    if novel:
        if (approved.get('human_gate') is not True or approved.get('status')!='approved_for_export'
            or approved.get('plan_sha256')!=file_sha(p['plan']) or approved.get('reviewed_by')!=review.get('reviewed_by')
            or approved.get('reviewed_at')!=review.get('reviewed_at')):
            raise LedgerHistoryError('HUMAN_PROOF_REQUIRED')
        decisions={b['beat_id']:b for b in review['decisions']};expected=[]
        if len(decisions)!=len(plan['micro_information_beats']):raise LedgerHistoryError('HUMAN_PROOF_REQUIRED')
        for beat in plan['micro_information_beats']:
            decision=decisions[beat['beat_id']]
            if decision['decision']=='rejected':continue
            if decision['decision'] not in {'approved','revised'}:raise LedgerHistoryError('HUMAN_PROOF_REQUIRED')
            value=dict(beat)
            if decision['decision']=='revised':value['text']=str(decision.get('revised_text') or '').strip()
            expected.append(value)
        if expected!=approved['micro_information_beats'] or not 4<=len(expected)<=8:
            raise LedgerHistoryError('HUMAN_PROOF_REQUIRED')
        context={'paths':p,'request':request,'selected':request['selected_content']}
        entry=owner._native_ledger_entry(context,approved,expected,output,exported_at)
        if kind=='novel_semantic':
            return {'kind':kind,'request_id':request_id,'source_refs':sources,'exported_at':exported_at,'entries':[entry],
                'fact_atoms':_build_fact_atoms(read(business_path),file_sha(business_path),read(speaker_path),file_sha(speaker_path)),
                'receipt_path':native_receipt,'closure_path':native_closure}
        if kind!='novel_presentation':raise LedgerHistoryError('NATIVE_SOURCE_INVALID')
        presentation={'export_intent_ref':ref(root,pp['intent']),
            'presentation_id':request_id+'-P001','business_id':request['persona_id'],'speaker_id':request['speaker_persona'],
            'request_id':request_id,'production_profile':'news','reuse_intent':'novel_content','semantic_novelty':False,
            'semantic_content_created_separately':True,'source_content_ref':request_id+'-N001',
            'selected_pattern_ref':approved['selected_pattern_id'],'status':'exported','approved_at':approved['reviewed_at'],
            'exported_at':exported_at,'new_semantic_content_count_delta':0,'novel_capacity_delta':0,
            'communicated_information_units_created':False,'approved_titles':intent['titles'],
            'approval_ref':{'path':str(p['approved']),'sha256':file_sha(p['approved'])},
            'export_ref':{'path':str(output),'sha256':file_sha(output)}}
    else:
        if (kind!='news_presentation' or approved.get('human_review',{}).get('human_gate') is not True
            or approved['human_review']['review_sha256']!=file_sha(p['review'])
            or approved['lineage']['plan_sha256']!=file_sha(p['plan']) or plan['request_sha256']!=file_sha(p['request'])):
            raise LedgerHistoryError('HUMAN_PROOF_REQUIRED')
        presentation=_presentation_history_entry(request=request,approved=approved,output_path=output,exported_at=exported_at)
        presentation['approval_ref']={'path':str(p['approved']),'sha256':file_sha(p['approved'])}
        presentation['export_intent_ref']=ref(root,pp['intent'])
    return {'kind':kind,'request_id':request_id,'source_refs':sources,'exported_at':exported_at,
        'source_content_id':presentation['source_content_ref'],'entry':presentation,
        'receipt_path':native_receipt,'closure_path':native_closure}


def _project_presentation_history(current, source_content_id, entry):
    source = _source_entry(
        current,
        source_content_id,
    )
    if canonical_sha256(
        source
    ) != canonical_sha256(
        _source_entry(
            current,
            source_content_id,
        )
    ):
        raise NewsDeliveryError(
            "NEWS_PRESENTATION_SOURCE_LINEAGE_INVALID",
            "Historical source content cannot be recovered.",
        )

    before_entries_sha = (
        canonical_sha256(
            current.get(
                "entries"
            )
            or []
        )
    )
    before_info_units = sorted(
        str(
            unit.get(
                "information_unit_id"
            )
            or ""
        )
        for semantic_entry in (
            current.get("entries")
            or []
        )
        for unit in (
            semantic_entry.get(
                "communicated_information_units"
            )
            or []
        )
    )

    updated = copy.deepcopy(
        current
    )
    extension = (
        updated.setdefault(
            "extensions",
            {},
        ).setdefault(
            "presentation_history_v1",
            {
                "version": (
                    "content-presentation-history-v1.0"
                ),
                "storage_policy": (
                    "append_only"
                ),
                "semantic_novelty_authority": False,
                "entries": [],
            },
        )
    )
    entries = (
        extension.setdefault(
            "entries",
            [],
        )
    )
    validate_presentation_history_chain(entries)

    existing = next(
        (
            item
            for item in entries
            if item.get(
                "presentation_id"
            )
            == entry.get(
                "presentation_id"
            )
        ),
        None,
    )

    if existing is not None:
        stable_keys = (
            "business_id",
            "speaker_id",
            "request_id",
            "production_profile",
            "reuse_intent",
            "semantic_novelty",
            "source_content_ref",
            "selected_pattern_ref",
            "status",
            "approved_titles",
        )
        if any(
            existing.get(key)
            != entry.get(key)
            for key in stable_keys
        ):
            raise NewsDeliveryError(
                "NEWS_PRESENTATION_HISTORY_CONFLICT",
                "Existing Presentation History entry differs from this export.",
            )
        return current, True

    entry = {**entry, 'history_event_schema_version':'news-presentation-history-event-v1.1',
             'history_parent_sha256':canonical_sha256(entries)}
    entries.append(entry)
    updated[
        "updated_at"
    ] = entry[
        "exported_at"
    ]

    if (
        canonical_sha256(
            updated.get(
                "entries"
            )
            or []
        )
        != before_entries_sha
    ):
        raise NewsDeliveryError(
            "NEWS_PRESENTATION_MUTATED_SEMANTIC_LEDGER",
            "Presentation History changed semantic Content Ledger entries.",
        )

    after_info_units = sorted(
        str(
            unit.get(
                "information_unit_id"
            )
            or ""
        )
        for semantic_entry in (
            updated.get("entries")
            or []
        )
        for unit in (
            semantic_entry.get(
                "communicated_information_units"
            )
            or []
        )
    )
    if (
        after_info_units
        != before_info_units
    ):
        raise NewsDeliveryError(
            "NEWS_PRESENTATION_DUPLICATED_INFORMATION_UNITS",
            "Presentation History duplicated Historical Exposure units.",
        )

    return updated, False


def _append_presentation_history(
    *,
    ledger_path: Path,
    source_content_id: str,
    entry: dict[str, Any],
) -> tuple[
    dict[str, Any],
    bool,
]:
    current = read_json(ledger_path)
    updated, recovered = _project_presentation_history(current, source_content_id, entry)
    if recovered:
        return current, True
    entry = updated['extensions']['presentation_history_v1']['entries'][-1]
    from contextlib import nullcontext
    from ledger_history_v1 import transition, home, LedgerHistoryError
    root=ledger_path.parents[3];rid=entry['request_id'];business=entry['business_id']
    kind='news_presentation' if rid.startswith('news_') else 'novel_presentation'
    native_intent=(root/'data/news_deliveries'/rid/'news_export_intent_v1.json' if rid.startswith('news_') else
                   root/'data/generation_batches'/rid/'news_export_intent_v1.json')
    if not native_intent.is_file() and home(root,business).is_dir():
        raise LedgerHistoryError('NATIVE_WRITER_REQUIRED')
    scope=transition(root,business,rid,kind,current,updated,exported_at=entry['exported_at'],
        after_bytes=json.dumps(updated,ensure_ascii=False,indent=2).encode('utf-8')) if native_intent.is_file() else nullcontext()
    with scope:
        payload = json.dumps(
            updated,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        temporary = (
            ledger_path
            .with_suffix(
                ledger_path.suffix
                + ".news_presentation.tmp"
            )
        )
        if temporary.exists():
            from news_export_recovery_v1 import ledger_intent
            proof=entry.get('export_intent_ref')
            if not proof or temporary.read_bytes()!=payload:
                raise NewsDeliveryError('NEWS_PRESENTATION_TEMP_CONFLICT', 'Retained presentation temporary differs from the original operation.')
            ledger_intent(ledger_path.parents[3],proof,business_id=entry['business_id'],request_id=entry['request_id'],
                titles=entry['approved_titles'],approved_sha256=entry['approval_ref']['sha256'],
                output_sha256=entry['export_ref']['sha256'])
        else:
            with temporary.open('xb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

        if (
            canonical_sha256(
                read_json(
                    ledger_path
                )
            )
            != canonical_sha256(
                current
            )
        ):
            raise NewsDeliveryError(
                "NEWS_PRESENTATION_CONCURRENT_LEDGER_CHANGE",
                "Content Ledger changed during Presentation History append.",
            )

        temporary.replace(
            ledger_path
        )
        return updated, False


def _export_name(
    *,
    request: dict[str, Any],
    business: dict[str, Any],
    speaker: dict[str, Any],
) -> str:
    business_name = _friendly_name(
        _known_fact_value(
            business,
            "public_display_name",
        )
        or _known_fact_value(
            business,
            "company_short_name",
        )
        or request[
            "business_id"
        ],
        "客户",
    )
    speaker_name = _friendly_name(
        _known_fact_value(
            speaker,
            "public_display_name",
        )
        or request[
            "speaker_id"
        ],
        "出镜人",
    )
    created = str(
        request.get(
            "created_at"
        )
        or ""
    )
    match = re.match(
        r"^(\d{4})-(\d{2})-(\d{2})",
        created,
    )
    date_stamp = (
        "".join(
            match.groups()
        )
        if match
        else "undated"
    )
    short_id = str(
        request[
            "request_id"
        ]
    ).removeprefix(
        "news_"
    )[:6]

    return (
        f"{business_name}_"
        f"{speaker_name}_"
        "News新闻体_1条_"
        f"{date_stamp}_"
        f"{short_id}.xlsx"
    )


def export_news_delivery(*, pipeline_root: Path, request_id: str,
                         export_context: dict | None = None) -> tuple[dict[str, Any], bool]:
    from news_export_recovery_v1 import native_operation, current_authority
    _, request = _load_request(pipeline_root, request_id)
    with native_operation(pipeline_root, request["business_id"]), current_authority(pipeline_root, request.get("profile_compatibility_v1_2")):
        return _export_news_delivery_native(pipeline_root=pipeline_root,
            request_id=request_id, export_context=export_context)


def _export_news_delivery_native(*, pipeline_root: Path, request_id: str,
                                export_context: dict | None) -> tuple[dict[str, Any], bool]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )
    request_path, request = (
        _load_request(
            pipeline_root,
            request_id,
        )
    )
    approved_path = (
        _approved_path(
            pipeline_root,
            request_id,
        )
    )
    if not approved_path.is_file():
        raise NewsDeliveryError(
            "NEWS_DELIVERY_APPROVAL_REQUIRED",
            "News Excel Export requires Human-approved News Delivery.",
        )
    approved = read_json(
        approved_path
    )
    _validate_plan_binding(pipeline_root,request_id,read_json(approved_path.parent/'news_delivery_plan_v1.json'))
    if (
        approved.get(
            "schema_version"
        )
        != APPROVED_SCHEMA
        or approved.get(
            "status"
        )
        != "approved_for_export"
        or (
            approved.get(
                "human_review"
            )
            or {}
        ).get(
            "human_gate"
        )
        is not True
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_APPROVAL_INVALID",
            "Approved News Delivery is not export-authorized.",
        )

    business_path, business = (
        _latest_approved_persona(
            pipeline_root,
            str(
                request[
                    "business_id"
                ]
            ),
            "business",
        )
    )
    _speaker_path, speaker = (
        _latest_approved_persona(
            pipeline_root,
            str(
                request[
                    "speaker_id"
                ]
            ),
            "speaker",
        )
    )

    template_path = Path(
        str(
            (
                request.get(
                    "lineage"
                )
                or {}
            ).get(
                "news_excel_template",
                {},
            ).get(
                "path"
            )
            or ""
        )
    ).expanduser().resolve()

    expected_template_sha = str(
        (
            request.get(
                "lineage"
            )
            or {}
        ).get(
            "news_excel_template",
            {},
        ).get(
            "sha256"
        )
        or ""
    )
    if (
        not template_path.is_file()
        or sha256_file(
            template_path
        )
        != expected_template_sha
    ):
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_LINEAGE_MISMATCH",
            "News Excel template changed after Request creation.",
        )

    output_name = _export_name(
        request=request,
        business=business,
        speaker=speaker,
    )
    output_path = (
        pipeline_root
        / "output"
        / output_name
    )
    root = _request_root(
        pipeline_root,
        request_id,
    )
    receipt_path = (
        root
        / "news_dynamic_excel_export_receipt_v1.json"
    )
    closure_path = (
        root
        / "news_delivery_export_closure_v1.json"
    )

    titles = [
        str(
            item[
                "approved_text"
            ]
        )
        for item in (
            approved.get(
                "approved_slots"
            )
            or []
        )
    ]

    from news_export_recovery_v1 import (
        REPURPOSE_RECEIPT, REPURPOSE_CLOSURE, NewsExportError, source_snapshot, prepare_publication,
        receipt_publication, validate_receipt_publication, ledger_prefix, validate_ledger_prefix,
        bound_source_paths,
    )
    if receipt_path.is_file() and closure_path.is_file():
        validate_news_delivery_export(pipeline_root=pipeline_root, request_id=request_id)
        from ledger_history_v1 import finish_completed_news_request
        finish_completed_news_request(pipeline_root,request['business_id'],request_id,root,receipt_path,closure_path,export_context)
        return {"request_id": request_id, "output_path": str(output_path), "output_name": output_name,
            "receipt_path": str(receipt_path), "closure_path": str(closure_path), "slot_count": len(titles),
            "stop_point_reached": True, "semantic_entry_count_delta": 0, "remote_model_called": False}, True
    _verify_speaker_business_lineage(business_path, business, speaker)
    if any(request['lineage'][key].get('sha256') != sha256_file(path)
           for key,path in [('business_persona',business_path),('speaker_persona',_speaker_path)]):
        raise NewsDeliveryError('NEWS_DELIVERY_PERSONA_CHANGED_BEFORE_EXPORT', 'Customer or Speaker source changed after Request creation.')
    from news_export_recovery_v1 import verify_native_human_bundle
    verify_native_human_bundle(pipeline_root, request=request_path, plan=root / 'news_delivery_plan_v1.json',
        review=_review_path(pipeline_root, request_id), approved=approved_path, kind='repurpose')
    _, snapshot_ledger = _ledger(pipeline_root, request["business_id"])
    source_entry = _source_entry(snapshot_ledger, request["source_content_id"])
    if canonical_sha256(source_entry) != request.get("source_content", {}).get("canonical_sha256"):
        raise NewsDeliveryError("NEWS_DELIVERY_SOURCE_CHANGED_BEFORE_EXPORT", "Historical source changed before export.")
    sources = source_snapshot(pipeline_root, request=request_path, plan=root / "news_delivery_plan_v1.json",
        review=_review_path(pipeline_root, request_id), approved=approved_path, business=business_path,
        speaker=_speaker_path, structural=bound_source_paths(pipeline_root, request.get("lineage", {})),
        semantic_source=source_entry, binding=request.get("profile_compatibility_v1_2"), consumer="news_repurpose")
    intent, prepared = prepare_publication(pipeline_root, root, request_id=request_id,
        request_type="cross_profile_repurpose", business_id=request["business_id"], speaker_id=request["speaker_id"],
        sources=sources, template=template_path, output=output_path, titles=titles,
        context=export_context, renderer=export_dynamic_news_xlsx)
    validation = {"slot_count": len(titles), "headers": [f"标题{i}" for i in range(1, len(titles)+1)],
        "titles": titles, "template_sha256": expected_template_sha, "output_sha256": sha256_file(output_path),
        "validation_passed": True}
    if receipt_path.is_file():
        existing_receipt = read_json(receipt_path)
        if existing_receipt.get("schema_version") != REPURPOSE_RECEIPT:
            raise NewsExportError("NEWS_EXPORT_LEGACY_PARTIAL_REQUIRES_CONFIRMATION", "导出结果需要重新核对。")
        validate_receipt_publication(pipeline_root, root, existing_receipt, output=output_path,
            template=template_path, titles=titles)
        validate_ledger_prefix(snapshot_ledger, existing_receipt["ledger_prefix"])

    ledger_path, ledger_before = (
        _ledger(
            pipeline_root,
            str(
                request[
                    "business_id"
                ]
            ),
        )
    )
    source_before = _source_entry(
        ledger_before,
        str(
            request[
                "source_content_id"
            ]
        ),
    )
    if (
        canonical_sha256(
            source_before
        )
        != (
            request.get(
                "source_content"
            )
            or {}
        ).get(
            "canonical_sha256"
        )
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SOURCE_CHANGED_BEFORE_EXPORT",
            "Historical source content changed before News export closure.",
        )

    semantic_entries_sha_before = (
        canonical_sha256(
            ledger_before.get(
                "entries"
            )
            or []
        )
    )
    semantic_entry_count_before = len(
        ledger_before.get(
            "entries"
        )
        or []
    )

    exported_at = intent["created_at"]
    presentation = {
        "export_intent_ref": receipt_publication(pipeline_root,root)['intent_ref'],
        "presentation_id": (
            request_id
            + "-P001"
        ),
        "business_id": (
            request[
                "business_id"
            ]
        ),
        "speaker_id": (
            request[
                "speaker_id"
            ]
        ),
        "request_id": request_id,
        "production_profile": (
            "news"
        ),
        "reuse_intent": (
            "cross_profile_repurpose"
        ),
        "semantic_novelty": False,
        "historical_content_reused": True,
        "source_content_ref": (
            request[
                "source_content_id"
            ]
        ),
        "selected_pattern_ref": (
            PRICE_PATTERN_ID
        ),
        "status": "exported",
        "approved_at": (
            approved[
                "human_review"
            ][
                "reviewed_at"
            ]
        ),
        "exported_at": (
            exported_at
        ),
        "novel_capacity_delta": 0,
        "new_semantic_content_count_delta": 0,
        "new_central_claim_count_delta": 0,
        "new_information_gain_delta": 0,
        "communicated_information_units_created": False,
        "approved_slot_count": len(
            titles
        ),
        "approved_titles": titles,
        "approval_ref": {
            "path": str(
                approved_path
            ),
            "sha256": sha256_file(
                approved_path
            ),
        },
        "export_ref": {
            "path": str(
                output_path
            ),
            "sha256": sha256_file(
                output_path
            ),
        },
        "events": [
            {
                "status": "approved",
                "at": (
                    approved[
                        "human_review"
                    ][
                        "reviewed_at"
                    ]
                ),
                "source": (
                    "human_review"
                ),
            },
            {
                "status": "exported",
                "at": exported_at,
                "source": (
                    "news_dynamic_excel_export_v1"
                ),
            },
        ],
    }

    ledger_after, presentation_recovered = (
        _append_presentation_history(
            ledger_path=ledger_path,
            source_content_id=str(
                request[
                    "source_content_id"
                ]
            ),
            entry=presentation,
        )
    )

    semantic_entries_sha_after = (
        canonical_sha256(
            ledger_after.get(
                "entries"
            )
            or []
        )
    )
    semantic_entry_count_after = len(
        ledger_after.get(
            "entries"
        )
        or []
    )

    if (
        semantic_entries_sha_after
        != semantic_entries_sha_before
        or semantic_entry_count_after
        != semantic_entry_count_before
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_SEMANTIC_LEDGER_DELTA_FORBIDDEN",
            "News repurpose changed semantic Content Ledger history.",
        )

    extension_entries = (
        (
            ledger_after.get(
                "extensions"
            )
            or {}
        ).get(
            "presentation_history_v1",
            {},
        ).get(
            "entries"
        )
        or []
    )
    final_presentation = next(
        (
            item
            for item in (
                extension_entries
            )
            if item.get(
                "presentation_id"
            )
            == presentation[
                "presentation_id"
            ]
        ),
        None,
    )
    if final_presentation is None:
        raise NewsDeliveryError(
            "NEWS_DELIVERY_PRESENTATION_HISTORY_MISSING",
            "Presentation History append did not persist.",
        )

    receipt = {
        "schema_version": REPURPOSE_RECEIPT,
        "publication": receipt_publication(pipeline_root, root),
        "ledger_prefix": ledger_prefix(ledger_after),
        "created_at": (
            exported_at
        ),
        "request_id": (
            request_id
        ),
        "profile": "news",
        "reuse_intent": (
            "cross_profile_repurpose"
        ),
        "semantic_novelty": False,
        "source_content_ref": (
            request[
                "source_content_id"
            ]
        ),
        "approved_news_delivery": {
            "path": str(
                approved_path
            ),
            "sha256": sha256_file(
                approved_path
            ),
        },
        "template_path": str(
            template_path
        ),
        "template_sha256": (
            validation[
                "template_sha256"
            ]
        ),
        "output_path": str(
            output_path
        ),
        "output_name": (
            output_name
        ),
        "output_sha256": (
            validation[
                "output_sha256"
            ]
        ),
        "exported_row_count": 1,
        "slot_count": len(
            titles
        ),
        "headers": validation[
            "headers"
        ],
        "titles": validation[
            "titles"
        ],
        "content_ledger": {
            "path": str(
                ledger_path
            ),
            "sha256_after": (
                sha256_file(
                    ledger_path
                )
            ),
            "semantic_entry_count_before": (
                semantic_entry_count_before
            ),
            "semantic_entry_count_after": (
                semantic_entry_count_after
            ),
            "semantic_entries_sha256_before": (
                semantic_entries_sha_before
            ),
            "semantic_entries_sha256_after": (
                semantic_entries_sha_after
            ),
            "presentation_history_entry": (
                final_presentation
            ),
        },
        "authority": {
            "new_semantic_content_created": False,
            "communicated_information_units_created": 0,
            "case_facts_transferred": False,
            "remote_model_calls": 0,
        },
        "validation_passed": True,
    }

    if receipt_path.is_file():
        # Compare the persisted business event, not a new clock/recovered flag
        # or the entire mutable Ledger after unrelated legitimate appends.
        existing = read_json(receipt_path)
        validate_receipt_publication(pipeline_root, root, existing, output=output_path,
            template=template_path, titles=titles)
        validate_ledger_prefix(ledger_after, existing["ledger_prefix"])
        if (existing.get("approved_news_delivery") != receipt["approved_news_delivery"]
            or existing.get("titles") != titles or existing.get("source_content_ref") != request["source_content_id"]
            or existing.get("content_ledger", {}).get("presentation_history_entry") != final_presentation):
            raise NewsExportError("NEWS_EXPORT_RECEIPT_CONFLICT")
        receipt = existing
    else:
        write_new_json(receipt_path, receipt)

    closure = {
        "schema_version": REPURPOSE_CLOSURE,
        "receipt_ref": {"path": str(receipt_path), "sha256": sha256_file(receipt_path)},
        "ledger_prefix": receipt["ledger_prefix"],
        "created_at": (
            exported_at
        ),
        "request_id": (
            request_id
        ),
        "status": (
            "approved_exported_presentation_history_closed"
        ),
        "request": {
            "path": str(
                request_path
            ),
            "sha256": sha256_file(
                request_path
            ),
        },
        "approved_news_delivery": {
            "path": str(
                approved_path
            ),
            "sha256": sha256_file(
                approved_path
            ),
        },
        "excel_export": {
            "path": str(
                output_path
            ),
            "sha256": sha256_file(
                output_path
            ),
            "slot_count": len(
                titles
            ),
        },
        "presentation_history": {
            "presentation_id": (
                final_presentation[
                    "presentation_id"
                ]
            ),
            "content_ledger_sha256_after": (
                sha256_file(
                    ledger_path
                )
            ),
            "semantic_entry_count_delta": (
                semantic_entry_count_after
                - semantic_entry_count_before
            ),
            "semantic_entries_changed": (
                semantic_entries_sha_after
                != semantic_entries_sha_before
            ),
        },
        "authority": {
            "semantic_novelty": False,
            "new_semantic_content_count_delta": 0,
            "presentation_history_append_only": True,
            "remote_model_calls": 0,
        },
        "validation": {
            "passed": True,
            "excel_validation_passed": True,
            "semantic_entry_count_unchanged": (
                semantic_entry_count_after
                == semantic_entry_count_before
            ),
            "semantic_entries_sha256_unchanged": (
                semantic_entries_sha_after
                == semantic_entries_sha_before
            ),
            "presentation_history_entry_present": True,
        },
    }

    if closure_path.is_file():
        existing = read_json(
            closure_path
        )
        stable = copy.deepcopy(
            closure
        )
        # Recovery time may differ, but lineage must not.
        if (
            existing.get(
                "request_id"
            )
            != request_id
            or (
                existing.get(
                    "excel_export"
                )
                or {}
            ).get(
                "sha256"
            )
            != closure[
                "excel_export"
            ][
                "sha256"
            ]
            or (
                existing.get(
                    "presentation_history"
                )
                or {}
            ).get(
                "presentation_id"
            )
            != closure[
                "presentation_history"
            ][
                "presentation_id"
            ]
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_EXPORT_CLOSURE_CONFLICT",
                "Existing News export closure has different lineage.",
            )
    else:
        write_new_json(
            closure_path,
            closure,
        )

    from ledger_history_v1 import finish_request
    finish_request(pipeline_root,request['business_id'],request_id,receipt_path,closure_path)
    validate_news_delivery_export(pipeline_root=pipeline_root, request_id=request_id)

    return {
        "request_id": (
            request_id
        ),
        "output_path": str(
            output_path
        ),
        "output_name": (
            output_name
        ),
        "receipt_path": str(
            receipt_path
        ),
        "closure_path": str(
            closure_path
        ),
        "slot_count": len(
            titles
        ),
        "presentation_id": (
            final_presentation[
                "presentation_id"
            ]
        ),
        "semantic_entry_count_delta": 0,
        "stop_point_reached": True,
        "remote_model_called": False,
    }, False



def export_supplemental_delivery(*, pipeline_root, request_id, authorization_context, expected_draft_ref=None):
    """PC3 delegation preserves the original semantic and Presentation closure."""
    from creation_delivery_v1 import export
    root = Path(pipeline_root).resolve()
    def ensure(src):
        export_news_delivery(pipeline_root=root, request_id=request_id, export_context=authorization_context)
        validate_news_delivery_export(pipeline_root=root, request_id=request_id)
        directory = _request_root(root, request_id)
        return directory / 'news_dynamic_excel_export_receipt_v1.json', directory / 'news_delivery_export_closure_v1.json'
    return export(root, request_id, authorization_context, native_owner='news_delivery_v1', ensure_core=ensure, expected_draft_ref=expected_draft_ref)


def validate_news_delivery_export(*, pipeline_root: Path, request_id: str) -> dict:
    """Native terminal read; mutable Ledger appends do not rewrite old receipts."""
    from news_export_recovery_v1 import (REPURPOSE_RECEIPT, REPURPOSE_CLOSURE, NewsExportError,
        validate_workbook, validate_receipt_publication, validate_ledger_prefix)
    root = Path(pipeline_root).resolve()
    request_path, request = _load_request(root, request_id)
    directory = _request_root(root, request_id)
    receipt_path = directory / "news_dynamic_excel_export_receipt_v1.json"
    closure_path = directory / "news_delivery_export_closure_v1.json"
    approved_path = _approved_path(root, request_id)
    approved, receipt, closure = map(read_json, (approved_path, receipt_path, closure_path))
    from news_export_recovery_v1 import verify_native_human_bundle
    verify_native_human_bundle(root, request=request_path, plan=directory / 'news_delivery_plan_v1.json',
        review=_review_path(root, request_id), approved=approved_path, kind='repurpose')
    titles = [item["approved_text"] for item in approved["approved_slots"]]
    business_path, business = _latest_approved_persona(root, request["business_id"], "business")
    _, speaker = _latest_approved_persona(root, request["speaker_id"], "speaker")
    output = root / "output" / _export_name(request=request, business=business, speaker=speaker)
    template = Path(request["lineage"]["news_excel_template"]["path"])
    if (receipt.get("request_id") != request_id or receipt.get("validation_passed") is not True
        or receipt.get("output_path") != str(output) or receipt.get("output_sha256") != sha256_file(output)
        or receipt.get("approved_news_delivery", {}).get("sha256") != sha256_file(approved_path)
        or receipt.get("template_sha256") != sha256_file(template)
        or receipt.get("titles") != titles or receipt.get("headers") != [f"标题{i}" for i in range(1,len(titles)+1)]
        or closure.get("request", {}).get("sha256") != sha256_file(request_path)
        or closure.get("approved_news_delivery", {}).get("sha256") != sha256_file(approved_path)
        or closure.get("excel_export", {}).get("sha256") != sha256_file(output)
        or closure.get("authority", {}).get("new_semantic_content_count_delta") != 0
        or approved.get("human_review", {}).get("human_gate") is not True):
        raise NewsExportError("NEWS_EXPORT_COMPLETION_INVALID", "导出结果需要重新核对。")
    validate_workbook(output, template, titles)
    _, ledger = _ledger(root, request["business_id"])
    source = _source_entry(ledger, request["source_content_id"])
    if canonical_sha256(source) != request["source_content"]["canonical_sha256"]:
        raise NewsExportError("NEWS_EXPORT_LEDGER_HISTORY_CONFLICT")
    presentations = ledger.get("extensions", {}).get("presentation_history_v1", {}).get("entries", [])
    matches = [entry for entry in presentations if entry.get("presentation_id") == request_id + "-P001"]
    if (len(matches) != 1 or matches[0] != receipt.get("content_ledger", {}).get("presentation_history_entry")
        or matches[0].get("export_ref", {}).get("sha256") != sha256_file(output)
        or matches[0].get("approval_ref", {}).get("sha256") != sha256_file(approved_path)):
        raise NewsExportError("NEWS_EXPORT_LEDGER_HISTORY_CONFLICT")
    if receipt.get("schema_version") == REPURPOSE_RECEIPT:
        from news_export_recovery_v1 import check
        check(closure, REPURPOSE_CLOSURE)
        if closure.get('ledger_prefix') != receipt.get('ledger_prefix'):
            raise NewsExportError('NEWS_EXPORT_LEDGER_HISTORY_CONFLICT')
        if closure.get("schema_version") != REPURPOSE_CLOSURE or closure.get("receipt_ref", {}).get("sha256") != sha256_file(receipt_path):
            raise NewsExportError("NEWS_EXPORT_COMPLETION_INVALID")
        validate_receipt_publication(root, directory, receipt, output=output, template=template, titles=titles)
        validate_ledger_prefix(ledger, receipt["ledger_prefix"])
        validate_ledger_prefix(ledger, closure["ledger_prefix"])
    elif receipt.get("schema_version") != EXPORT_RECEIPT_SCHEMA or closure.get("schema_version") != CLOSURE_SCHEMA:
        raise NewsExportError("NEWS_EXPORT_CONTRACT_INVALID")
    return receipt


def status_news_delivery(
    *,
    pipeline_root: Path,
    request_id: str,
) -> dict[str, Any]:
    pipeline_root = (
        pipeline_root
        .expanduser()
        .resolve()
    )
    request_path, request = (
        _load_request(
            pipeline_root,
            request_id,
        )
    )
    root = _request_root(
        pipeline_root,
        request_id,
    )
    plan_path = (
        root
        / "news_delivery_plan_v1.json"
    )
    review_path = (
        _review_path(
            pipeline_root,
            request_id,
        )
    )
    approved_path = (
        _approved_path(
            pipeline_root,
            request_id,
        )
    )
    receipt_path = (
        root
        / "news_dynamic_excel_export_receipt_v1.json"
    )
    closure_path = (
        root
        / "news_delivery_export_closure_v1.json"
    )

    from news_export_recovery_v1 import partial_state
    business_path, business = _latest_approved_persona(pipeline_root, request["business_id"], "business")
    _, speaker = _latest_approved_persona(pipeline_root, request["speaker_id"], "speaker")
    output = pipeline_root / "output" / _export_name(request=request, business=business, speaker=speaker)
    recovery_state = partial_state(pipeline_root, root, output=output, receipt=receipt_path, closure=closure_path)
    completed = False
    cancelled=bool(request_cancelled(pipeline_root,request_id))
    if cancelled:
        next_action,recovery_state,completed='NEWS_REQUEST_CANCELLED','cancelled_unissued',False
    elif closure_path.is_file():
        validate_news_delivery_export(pipeline_root=pipeline_root, request_id=request_id)
        next_action, recovery_state, completed = "NEWS_EXCEL_EXPORTED", "completed", True
    elif recovery_state == "legacy_unbound_orphan":
        next_action = "RECHECK_EXPORT"
    elif approved_path.is_file():
        next_action = "EXPORT_NEWS_EXCEL"
    elif plan_path.is_file():
        next_action = "HUMAN_REVIEW"
    else:
        next_action = "RESOLVE_NEWS_PLAN"

    return {
        "cancelled": cancelled,
        "request_id": (
            request_id
        ),
        "request_sha256": (
            sha256_file(
                request_path
            )
        ),
        "business_id": (
            request[
                "business_id"
            ]
        ),
        "speaker_id": (
            request[
                "speaker_id"
            ]
        ),
        "source_content_id": (
            request[
                "source_content_id"
            ]
        ),
        "plan_ready": (
            plan_path.is_file()
        ),
        "review_ready": (
            review_path.is_file()
        ),
        "approved": (
            approved_path.is_file()
        ),
        "exported": completed,
        "export_recovery_state": recovery_state,
        "presentation_history_closed": completed,
        "next_action": (
            next_action
        ),
        "stop_point_reached": completed,
    }


def _parse_action(
    args: argparse.Namespace,
) -> dict[str, Any]:
    root = Path(
        args.pipeline_root
    ).expanduser().resolve()

    if args.action == "preview":
        return {
            "ok": True,
            "result": (
                preview_news_delivery(
                    pipeline_root=root,
                    business_id=args.business_id,
                    speaker_id=args.speaker_id,
                )
            ),
        }

    if args.action == "create-request":
        result, recovered = (
            create_news_delivery_request(
                pipeline_root=root,
                business_id=args.business_id,
                speaker_id=args.speaker_id,
                source_content_id=args.source_content_id,
                idempotency_key=args.idempotency_key,
                created_by_user_id=args.created_by_user_id,
                created_by_phone=args.created_by_phone,
            )
        )
        return {
            "ok": True,
            "recovered": (
                recovered
            ),
            "result": result,
        }

    if args.action == "resolve-plan":
        result, recovered = (
            resolve_news_delivery_plan(
                pipeline_root=root,
                request_id=args.request_id,
            )
        )
        return {
            "ok": True,
            "recovered": (
                recovered
            ),
            "result": result,
        }

    if args.action == "approve":
        result, recovered = (
            approve_news_delivery(
                pipeline_root=root,
                request_id=args.request_id,
                review_path=Path(
                    args.review
                ),
            )
        )
        return {
            "ok": True,
            "recovered": (
                recovered
            ),
            "result": result,
        }

    if args.action == "export":
        import sys
        from news_export_recovery_v1 import NewsExportError
        try:
            incoming = json.loads(sys.stdin.read() or '{}')
        except ValueError as exc:
            raise NewsExportError('NEWS_EXPORT_CONTEXT_INVALID') from exc
        result, recovered = (
            export_news_delivery(
                pipeline_root=root,
                request_id=args.request_id,
                export_context=incoming.get("export_context"),
            )
        )
        return {
            "ok": True,
            "recovered": (
                recovered
            ),
            "result": result,
        }

    if args.action == "status":
        return {
            "ok": True,
            "result": (
                status_news_delivery(
                    pipeline_root=root,
                    request_id=args.request_id,
                )
            ),
        }

    raise NewsDeliveryError(
        "NEWS_DELIVERY_ACTION_INVALID",
        f"Unsupported action: {args.action}",
    )


def main() -> None:
    from news_export_recovery_v1 import NewsExportError
    parser = argparse.ArgumentParser(
        description=(
            "Canonical News Delivery V1 "
            "for the production-validated "
            "Price / Offer cross-profile repurpose slice."
        )
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=(
            "preview",
            "create-request",
            "resolve-plan",
            "approve",
            "export",
            "status",
        ),
    )
    parser.add_argument(
        "--pipeline-root",
        default=str(
            Path(__file__)
            .resolve()
            .parents[1]
        ),
    )
    parser.add_argument(
        "--business-id"
    )
    parser.add_argument(
        "--speaker-id"
    )
    parser.add_argument(
        "--source-content-id"
    )
    parser.add_argument(
        "--idempotency-key"
    )
    parser.add_argument("--created-by-user-id", type=int)
    parser.add_argument("--created-by-phone")
    parser.add_argument(
        "--request-id"
    )
    parser.add_argument(
        "--review"
    )
    args = parser.parse_args()

    try:
        result = _parse_action(
            args
        )
    except (
        NewsDeliveryError,
        NewsSlotRecommendationError,
        NewsExportError,
    ) as exc:
        code = getattr(
            exc,
            "code",
            "NEWS_DELIVERY_FAILED",
        )
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": code,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(2) from exc

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
