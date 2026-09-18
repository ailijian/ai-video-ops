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

from news_slot_recommendation_v1 import (
    MAX_SLOTS,
    MIN_SLOTS,
    NewsSlotRecommendationError,
    build_recommendation,
)


REQUEST_SCHEMA = "news-delivery-request-v1.0"
PLAN_SCHEMA = "news-delivery-plan-v1.0"
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
        value = json.loads(path.read_text(encoding="utf-8"))
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
    with path.open("rb") as handle:
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


def export_dynamic_news_xlsx(
    *,
    template_path: Path,
    output_path: Path,
    titles: list[str],
) -> dict[str, Any]:
    count = len(titles)
    if not MIN_SLOTS <= count <= MAX_SLOTS:
        raise NewsDeliveryError(
            "NEWS_EXCEL_SLOT_COUNT_INVALID",
            (
                "News Excel requires between "
                f"{MIN_SLOTS} and {MAX_SLOTS} approved titles."
            ),
        )

    template_path = template_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()

    if not template_path.is_file():
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_MISSING",
            f"News Excel template is missing: {template_path}",
        )
    if output_path.exists():
        raise NewsDeliveryError(
            "NEWS_EXCEL_OUTPUT_EXISTS",
            f"News Excel output already exists: {output_path}",
        )

    template_sha_before = sha256_file(
        template_path
    )
    last_column = _column_letter(count)
    headers = [
        f"标题{index}"
        for index in range(1, count + 1)
    ]

    with tempfile.TemporaryDirectory(
        prefix="news_xlsx_"
    ) as temporary:
        temp_root = Path(temporary)
        with zipfile.ZipFile(
            template_path,
            "r",
        ) as source:
            source.extractall(temp_root)

        sheet_path = (
            temp_root
            / "xl"
            / "worksheets"
            / "sheet1.xml"
        )
        tree = ET.parse(sheet_path)
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
        tree.write(
            sheet_path,
            encoding="utf-8",
            xml_declaration=True,
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with zipfile.ZipFile(
            output_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as target:
            for path in sorted(
                temp_root.rglob("*")
            ):
                if path.is_file():
                    target.write(
                        path,
                        path.relative_to(
                            temp_root
                        ).as_posix(),
                    )

    if sha256_file(template_path) != template_sha_before:
        output_path.unlink(
            missing_ok=True
        )
        raise NewsDeliveryError(
            "NEWS_EXCEL_TEMPLATE_MUTATED",
            "News Excel source template changed during export.",
        )

    exported_headers = _xlsx_sheet_values(
        output_path,
        row_number=4,
        max_columns=count,
    )
    exported_titles = _xlsx_sheet_values(
        output_path,
        row_number=5,
        max_columns=count,
    )

    if exported_headers != headers:
        raise NewsDeliveryError(
            "NEWS_EXCEL_HEADER_VALIDATION_FAILED",
            "Dynamic News Excel headers do not match approved slot count.",
        )
    if exported_titles != titles:
        raise NewsDeliveryError(
            "NEWS_EXCEL_TITLE_VALIDATION_FAILED",
            "Dynamic News Excel titles do not match Human-approved content.",
        )

    return {
        "slot_count": count,
        "headers": headers,
        "titles": titles,
        "template_sha256": template_sha_before,
        "output_sha256": sha256_file(
            output_path
        ),
        "validation_passed": True,
    }


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

    for entry in (
        ledger.get("entries") or []
    ):
        content_id = str(
            entry.get("content_id")
            or ""
        )
        if not content_id:
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
        "already_presented_source_count": len(
            already_presented
        ),
        "already_presented_sources": (
            already_presented
        ),
        "authority": {
            "frozen_registry_mutated": False,
            "novel_news_globally_ready": False,
            "price_offer_path_production_validated": True,
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


def create_news_delivery_request(
    *,
    pipeline_root: Path,
    business_id: str,
    speaker_id: str,
    source_content_id: str,
    idempotency_key: str,
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

    preview = preview_news_delivery(
        pipeline_root=pipeline_root,
        business_id=business_id,
        speaker_id=speaker_id,
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

    identity = "|".join(
        (
            business_id,
            speaker_id,
            source_content_id,
            idempotency_key,
        )
    )
    request_id = (
        "news_"
        + sha256_text(
            identity
        )[:20]
    )
    path = _request_path(
        pipeline_root,
        request_id,
    )

    if path.is_file():
        existing = read_json(path)
        expected = {
            "business_id": business_id,
            "speaker_id": speaker_id,
            "source_content_id": source_content_id,
            "idempotency_key_sha256": (
                sha256_text(
                    idempotency_key
                )
            ),
        }
        actual = {
            key: existing.get(key)
            for key in expected
        }
        if actual != expected:
            raise NewsDeliveryError(
                "NEWS_DELIVERY_IDEMPOTENCY_CONFLICT",
                (
                    "Existing News Delivery Request "
                    "does not match this idempotency identity."
                ),
            )
        return existing, True

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
        != REQUEST_SCHEMA
        or request.get(
            "request_id"
        )
        != request_id
    ):
        raise NewsDeliveryError(
            "NEWS_DELIVERY_REQUEST_INVALID",
            "News Delivery Request schema or identity is invalid.",
        )
    return path, request


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
        not in _normalize(title)
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
    write_new_json(
        plan_path,
        plan,
    )
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


def approve_news_delivery(
    *,
    pipeline_root: Path,
    request_id: str,
    review_path: Path,
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
    if (
        plan.get(
            "schema_version"
        )
        != PLAN_SCHEMA
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
        write_new_json(
            canonical_review_path,
            incoming,
        )

    if approved_path.is_file():
        existing = read_json(
            approved_path
        )
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


def _append_presentation_history(
    *,
    ledger_path: Path,
    source_content_id: str,
    entry: dict[str, Any],
) -> tuple[
    dict[str, Any],
    bool,
]:
    current = read_json(
        ledger_path
    )
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

    entries.append(
        entry
    )
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
        raise NewsDeliveryError(
            "NEWS_PRESENTATION_TEMP_CONFLICT",
            "Presentation History temporary path already exists.",
        )

    with temporary.open(
        "xb"
    ) as handle:
        handle.write(
            payload
        )

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
        temporary.unlink(
            missing_ok=True
        )
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


def export_news_delivery(
    *,
    pipeline_root: Path,
    request_id: str,
) -> tuple[
    dict[str, Any],
    bool,
]:
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

    if (
        receipt_path.is_file()
        and closure_path.is_file()
    ):
        receipt = read_json(
            receipt_path
        )
        closure = read_json(
            closure_path
        )
        if (
            receipt.get(
                "validation_passed"
            )
            is True
            and closure.get(
                "validation",
                {},
            ).get(
                "passed"
            )
            is True
            and output_path.is_file()
            and receipt.get(
                "output_sha256"
            )
            == sha256_file(
                output_path
            )
        ):
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
                "stop_point_reached": True,
                "remote_model_called": False,
            }, True

        raise NewsDeliveryError(
            "NEWS_DELIVERY_EXPORT_RECOVERY_CONFLICT",
            "Existing News export artifacts failed recovery validation.",
        )

    if output_path.is_file():
        validation = {
            "slot_count": len(
                titles
            ),
            "headers": _xlsx_sheet_values(
                output_path,
                row_number=4,
                max_columns=len(
                    titles
                ),
            ),
            "titles": _xlsx_sheet_values(
                output_path,
                row_number=5,
                max_columns=len(
                    titles
                ),
            ),
            "template_sha256": (
                expected_template_sha
            ),
            "output_sha256": (
                sha256_file(
                    output_path
                )
            ),
            "validation_passed": False,
        }
        expected_headers = [
            f"标题{index}"
            for index in range(
                1,
                len(titles) + 1,
            )
        ]
        validation[
            "validation_passed"
        ] = (
            validation[
                "headers"
            ]
            == expected_headers
            and validation[
                "titles"
            ]
            == titles
        )
        if not validation[
            "validation_passed"
        ]:
            raise NewsDeliveryError(
                "NEWS_DELIVERY_EXISTING_OUTPUT_INVALID",
                "Existing News Excel output differs from Human-approved titles.",
            )
    else:
        validation = (
            export_dynamic_news_xlsx(
                template_path=template_path,
                output_path=output_path,
                titles=titles,
            )
        )

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

    exported_at = now_iso()
    presentation = {
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
        "schema_version": (
            EXPORT_RECEIPT_SCHEMA
        ),
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
            "presentation_recovered": (
                presentation_recovered
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
        existing = read_json(
            receipt_path
        )
        if (
            canonical_sha256(
                existing
            )
            != canonical_sha256(
                receipt
            )
        ):
            raise NewsDeliveryError(
                "NEWS_DELIVERY_EXPORT_RECEIPT_CONFLICT",
                "Existing News export receipt differs from recovered export.",
            )
    else:
        write_new_json(
            receipt_path,
            receipt,
        )

    closure = {
        "schema_version": (
            CLOSURE_SCHEMA
        ),
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

    if (
        receipt_path.is_file()
        and closure_path.is_file()
    ):
        next_action = (
            "NEWS_EXCEL_EXPORTED"
        )
    elif approved_path.is_file():
        next_action = (
            "EXPORT_NEWS_EXCEL"
        )
    elif plan_path.is_file():
        next_action = (
            "HUMAN_REVIEW"
        )
    else:
        next_action = (
            "RESOLVE_NEWS_PLAN"
        )

    return {
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
        "exported": (
            receipt_path.is_file()
        ),
        "presentation_history_closed": (
            closure_path.is_file()
        ),
        "next_action": (
            next_action
        ),
        "stop_point_reached": (
            receipt_path.is_file()
            and closure_path.is_file()
        ),
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
        result, recovered = (
            export_news_delivery(
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
