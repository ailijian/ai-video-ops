from __future__ import annotations

import argparse
import difflib
import getpass
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI
from privacy_projection_v1 import (
    assert_safe_for_external_model,
    build_egress_audit,
    detect_sensitive_spans,
    load_privacy_projection,
    project_value,
    require_privacy_projection_for_egress,
)
from speech_evidence_v1 import (
    SPEECH_NOT_DETECTED,
    require_audio_speech_evidence,
)


SCRIPT_VERSION = "build_narration_review_v1.py@1.1"
SCHEMA_VERSION = "narration-review-v1.1-draft"
PROMPT_VERSION = "narration-review-prompt-v1.0"

DECISIONS = {"unchanged", "corrected", "uncertain"}
CONFIDENCES = {"high", "medium", "low"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_client() -> OpenAI:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        key = getpass.getpass("DeepSeek API Key: ")
    return OpenAI(
        api_key=key,
        base_url="https://api.deepseek.com",
    )


def normalize_text(text: str) -> str:
    # Keep CJK, letters and digits; remove punctuation/whitespace.
    return "".join(
        ch.lower()
        for ch in str(text)
        if (
            "\u4e00" <= ch <= "\u9fff"
            or ch.isalpha()
            or ch.isdigit()
        )
    )


def sha256_json(data: Any) -> str:
    blob = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def sequence_metrics(a: str, b: str) -> tuple[float, float, int]:
    a_n = normalize_text(a)
    b_n = normalize_text(b)

    if not a_n or not b_n:
        return 0.0, 0.0, 0

    matcher = difflib.SequenceMatcher(
        None,
        a_n,
        b_n,
        autojunk=False,
    )
    ratio = matcher.ratio()
    longest = matcher.find_longest_match(
        0, len(a_n), 0, len(b_n)
    ).size
    shorter = min(len(a_n), len(b_n))
    coverage = longest / shorter if shorter else 0.0

    return ratio, coverage, longest


def split_ocr_lines(text: str) -> list[str]:
    pieces = re.split(r"[\r\n]+", str(text))
    out: list[str] = []

    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue

        normalized = normalize_text(piece)
        if len(normalized) < 2:
            continue

        # Avoid huge non-subtitle blobs.
        if len(normalized) > 50:
            continue

        out.append(piece)

    return out


def supporting_ocr_for_segment(
    segment: dict[str, Any],
    frames: list[dict[str, Any]],
    *,
    window_seconds: float,
    max_items: int,
) -> list[dict[str, Any]]:
    start = float(segment["start"]) - window_seconds
    end = float(segment["end"]) + window_seconds
    source_text = str(segment["source_text"])

    candidates: list[dict[str, Any]] = []

    for frame in frames:
        ts = float(frame["timestamp_seconds"])
        if ts < start or ts > end:
            continue

        for line in split_ocr_lines(
            str(frame.get("ocr_raw") or "")
        ):
            ratio, coverage, longest = sequence_metrics(
                source_text,
                line,
            )

            relevant = (
                ratio >= 0.34
                or (coverage >= 0.55 and longest >= 3)
                or (
                    len(normalize_text(line)) <= 8
                    and longest >= 3
                )
            )
            if not relevant:
                continue

            # Do not send nearby shipping/order-label PII merely because
            # it was visible in the same frame. Only allow it when it is
            # extremely close to the spoken segment itself.
            if detect_sensitive_spans(line) and ratio < 0.82:
                continue

            candidates.append(
                {
                    "frame_ref": str(frame["frame_id"]),
                    "timestamp_seconds": ts,
                    "text": line,
                    "similarity_ratio": round(ratio, 4),
                    "longest_match_coverage": round(
                        coverage, 4
                    ),
                }
            )

    # Deduplicate identical OCR text; keep the strongest/closest item.
    deduped: dict[str, dict[str, Any]] = {}

    for item in candidates:
        key = normalize_text(item["text"])

        if key not in deduped:
            deduped[key] = item
            continue

        old = deduped[key]
        old_score = (
            float(old["similarity_ratio"]),
            -abs(
                float(old["timestamp_seconds"])
                - float(segment["start"])
            ),
        )
        new_score = (
            float(item["similarity_ratio"]),
            -abs(
                float(item["timestamp_seconds"])
                - float(segment["start"])
            ),
        )

        if new_score > old_score:
            deduped[key] = item

    ranked = sorted(
        deduped.values(),
        key=lambda x: (
            -float(x["similarity_ratio"]),
            -float(x["longest_match_coverage"]),
            abs(
                float(x["timestamp_seconds"])
                - float(segment["start"])
            ),
        ),
    )

    return ranked[:max_items]


def low_confidence_words(
    segment: dict[str, Any],
    word_by_id: dict[str, dict[str, Any]],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for word_id in segment.get("word_refs", []):
        word = word_by_id.get(str(word_id))
        if not word:
            continue

        probability = word.get("probability")
        if probability is None:
            continue

        probability = float(probability)

        if probability < threshold:
            out.append(
                {
                    "word_ref": str(word_id),
                    "text": str(word.get("text", "")),
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                    "probability": probability,
                }
            )

    return out


def usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)

    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }

    return {
        "prompt_tokens": getattr(
            usage, "prompt_tokens", None
        ),
        "completion_tokens": getattr(
            usage, "completion_tokens", None
        ),
        "total_tokens": getattr(
            usage, "total_tokens", None
        ),
    }


def build_prompt(
    case_id: str,
    inputs: list[dict[str, Any]],
) -> str:
    expected_ids = [
        str(item["segment_id"])
        for item in inputs
    ]

    return f"""
你正在做“短视频旁白转写校对”，不是文案改写。

Case ID: {case_id}

下面每个 segment 包含：
- source_text：faster-whisper 原始 ASR；
- 时间范围：不可修改；
- low_confidence_words：ASR 低置信度词，只是风险提示；
- supporting_ocr：同一时间附近、且经过程序相似度过滤后的画面字幕候选。

你的唯一任务：
判断 source_text 是否存在“明确可由 supporting_ocr 支持”的识别错误。

严格规则：

1. 禁止润色、改写语气、补充信息、删减口语、改变句式。
2. 不得合并或拆分 segment。
3. 不得修改 segment_id、时间戳或 word_refs。
4. corrected 只能用于 supporting_ocr 足以直接支持的修正。
5. 如果只是“上下文觉得更通顺”，但 OCR 不足以证明，必须 unchanged 或 uncertain。
6. supporting_ocr 可能包含画面标题、品牌字、非旁白文字；只有与 source_text 明显对应的字幕才可采用。
7. 不要把品牌、人物身份、地址、订单、电话等画面信息加入旁白。
8. reviewed_text 不要添加标点，尽量保持 source_text 原始字序，只修正错误字符/词。
9. decision=unchanged 时 reviewed_text 必须与 source_text 完全一致。
10. decision=uncertain 时 reviewed_text 也必须与 source_text 完全一致，交给人工决定。
11. decision=corrected 时 evidence_frame_refs 必须至少 1 个，且只能引用该 segment 的 supporting_ocr 中实际提供的 frame_ref。
12. confidence 只能是 high / medium / low。
13. 必须恰好返回以下 segment_id，顺序完全一致：
{json.dumps(expected_ids, ensure_ascii=False)}

输入：
{json.dumps(inputs, ensure_ascii=False)}

只输出 JSON：

{{
  "segments": [
    {{
      "segment_id": "A001",
      "reviewed_text": "校对后的文本",
      "decision": "unchanged|corrected|uncertain",
      "confidence": "high|medium|low",
      "evidence_frame_refs": [],
      "note": "一句简短说明"
    }}
  ]
}}
""".strip()


def sanitize_model_output(
    payload: dict[str, Any],
    chunk_inputs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_segments = payload.get("segments")

    if not isinstance(raw_segments, list):
        raise RuntimeError(
            "Model output missing segments array."
        )

    expected_ids = [
        str(x["segment_id"]) for x in chunk_inputs
    ]
    input_by_id = {
        str(x["segment_id"]): x
        for x in chunk_inputs
    }

    returned_ids = [
        str(x.get("segment_id"))
        for x in raw_segments
    ]
    expected_set = set(expected_ids)

    duplicated = [
        segment_id
        for segment_id in expected_ids
        if returned_ids.count(segment_id) > 1
    ]
    if duplicated:
        raise RuntimeError(
            "Expected segment IDs duplicated: "
            + ", ".join(duplicated)
        )

    filtered = [
        item
        for item in raw_segments
        if str(item.get("segment_id")) in expected_set
    ]
    filtered_ids = [
        str(x.get("segment_id"))
        for x in filtered
    ]

    missing = [
        x for x in expected_ids
        if x not in filtered_ids
    ]
    if missing:
        raise RuntimeError(
            "Expected segment IDs missing: "
            + ", ".join(missing)
        )

    if filtered_ids != expected_ids:
        raise RuntimeError(
            "Segment order mismatch."
        )

    warnings: list[str] = []
    unexpected = [
        x for x in returned_ids
        if x not in expected_set
    ]
    if unexpected:
        warnings.append(
            "Dropped unexpected model-generated segment IDs: "
            + ", ".join(unexpected)
        )

    out: list[dict[str, Any]] = []

    for item in filtered:
        segment_id = str(item["segment_id"])
        source = input_by_id[segment_id]
        source_text = str(source["source_text"])
        reviewed_text = str(
            item.get("reviewed_text", "")
        )
        decision = str(item.get("decision", ""))
        confidence = str(item.get("confidence", ""))
        evidence_refs = [
            str(x)
            for x in (
                item.get("evidence_frame_refs") or []
            )
        ]

        if decision not in DECISIONS:
            raise RuntimeError(
                f"{segment_id}: invalid decision={decision!r}"
            )

        if confidence not in CONFIDENCES:
            raise RuntimeError(
                f"{segment_id}: invalid confidence={confidence!r}"
            )

        if not reviewed_text:
            raise RuntimeError(
                f"{segment_id}: reviewed_text is empty."
            )

        if decision in {"unchanged", "uncertain"}:
            if reviewed_text != source_text:
                raise RuntimeError(
                    f"{segment_id}: {decision} must keep "
                    "reviewed_text exactly equal to source_text."
                )

        allowed_refs = {
            str(x["frame_ref"])
            for x in source["supporting_ocr"]
        }

        if any(
            ref not in allowed_refs
            for ref in evidence_refs
        ):
            raise RuntimeError(
                f"{segment_id}: evidence_frame_refs contains "
                "a frame not supplied for this segment."
            )

        if decision == "corrected":
            # Safe recovery for a common model bookkeeping error:
            # the model may label a segment "corrected" while returning
            # exactly the original text (or only punctuation/whitespace
            # differences). In that case there is no actual correction,
            # so canonicalize it to unchanged instead of wasting retries.
            if (
                reviewed_text == source_text
                or normalize_text(reviewed_text)
                == normalize_text(source_text)
            ):
                warnings.append(
                    f"{segment_id}: model labeled corrected but made no "
                    "substantive text change; canonicalized to uncertain "
                    "for explicit review."
                )
                decision = "uncertain"
                confidence = "low"
                reviewed_text = source_text
                evidence_refs = []

            elif not evidence_refs:
                raise RuntimeError(
                    f"{segment_id}: corrected requires OCR evidence."
                )

            if decision == "corrected":
                # Conservative anti-hallucination check:
                # any newly introduced alphanumeric/CJK character must occur
                # in the OCR evidence supplied to this segment.
                source_chars = set(
                    normalize_text(source_text)
                )
                reviewed_chars = set(
                    normalize_text(reviewed_text)
                )
                ocr_chars = set(
                    normalize_text(
                        "".join(
                            str(x["text"])
                            for x in source[
                                "supporting_ocr"
                            ]
                        )
                    )
                )

                unsupported_new_chars = (
                    reviewed_chars
                    - source_chars
                    - ocr_chars
                )
                if unsupported_new_chars:
                    raise RuntimeError(
                        f"{segment_id}: corrected text introduces "
                        "characters unsupported by ASR/OCR: "
                        + "".join(
                            sorted(unsupported_new_chars)
                        )
                    )

        out.append(
            {
                "segment_id": segment_id,
                "reviewed_text": reviewed_text,
                "decision": decision,
                "confidence": confidence,
                "evidence_frame_refs": evidence_refs,
                "note": str(item.get("note", "")),
            }
        )

    return out, warnings


def deterministic_diff(
    source_text: str,
    reviewed_text: str,
) -> list[dict[str, Any]]:
    matcher = difflib.SequenceMatcher(
        None,
        source_text,
        reviewed_text,
        autojunk=False,
    )

    ops: list[dict[str, Any]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        ops.append(
            {
                "operation": tag,
                "source_span": [i1, i2],
                "source_text": source_text[i1:i2],
                "reviewed_span": [j1, j2],
                "reviewed_text": reviewed_text[j1:j2],
            }
        )

    return ops


def main() -> None:
    started_total = time.perf_counter()

    parser = argparse.ArgumentParser(
        description=(
            "Build a traceable narration correction layer from "
            "Whisper ASR + time-aligned OCR evidence. "
            "Raw word timestamps are never modified."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--audio-v1", required=True)
    parser.add_argument("--visual-v1", required=True)
    parser.add_argument(
        "--model",
        default="deepseek-v4-flash",
    )
    parser.add_argument(
        "--segment-chunk-size",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--ocr-window-seconds",
        type=float,
        default=0.8,
    )
    parser.add_argument(
        "--max-ocr-items",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--low-confidence-threshold",
        type=float,
        default=0.80,
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--privacy-projection", required=True)
    parser.add_argument(
        "--review-file",
        default=None,
        help=(
            "Optional explicit narration review decisions JSON. "
            "Applied after model/cached review; raw ASR evidence remains "
            "immutable."
        ),
    )
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()
    privacy_context = load_privacy_projection(
        args.privacy_projection,
        expected_case_id=args.case_id,
    )

    if args.segment_chunk_size < 1:
        raise ValueError(
            "--segment-chunk-size must be >= 1"
        )
    if args.ocr_window_seconds < 0:
        raise ValueError(
            "--ocr-window-seconds must be >= 0"
        )
    if args.max_ocr_items < 1:
        raise ValueError(
            "--max-ocr-items must be >= 1"
        )
    if not 0 <= args.low_confidence_threshold <= 1:
        raise ValueError(
            "--low-confidence-threshold must be 0..1"
        )
    if args.max_retries < 0:
        raise ValueError(
            "--max-retries must be >= 0"
        )

    audio_path = Path(
        args.audio_v1
    ).expanduser().resolve()
    visual_path = Path(
        args.visual_v1
    ).expanduser().resolve()

    for path in (audio_path, visual_path):
        if not path.exists():
            raise FileNotFoundError(path)

    audio = read_json(audio_path)
    visual = read_json(visual_path)

    if str(audio.get("case_id")) != args.case_id:
        raise RuntimeError(
            "audio_v1 case_id mismatch."
        )
    if str(visual.get("case_id")) != args.case_id:
        raise RuntimeError(
            "visual_v1 case_id mismatch."
        )
    if not audio.get("validation", {}).get("passed"):
        raise RuntimeError(
            "audio_v1 validation is not passed."
        )
    if (
        visual.get("coverage", {}).get(
            "coverage_label"
        )
        != "candidate_complete"
    ):
        raise RuntimeError(
            "visual_v1 must be candidate_complete."
        )

    segments = list(audio.get("segments") or [])
    words = list(audio.get("words") or [])
    frames = list(visual.get("frames") or [])
    speech_evidence_status = require_audio_speech_evidence(audio)

    if not frames:
        raise RuntimeError(
            "visual_v1 contains no frames."
        )

    if speech_evidence_status == SPEECH_NOT_DETECTED:
        if args.review_file:
            raise RuntimeError(
                "A narration review file is not applicable when speech was not detected."
            )
        project_root = Path(__file__).resolve().parents[1]
        output_dir = (
            Path(args.output_root).expanduser().resolve()
            if args.output_root
            else project_root / "data" / "narration" / args.case_id / "v1"
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        total_elapsed = time.perf_counter() - started_total
        result = {
            "schema_version": SCHEMA_VERSION,
            "tool_version": SCRIPT_VERSION,
            "prompt_version": None,
            "case_id": args.case_id,
            "source_audio_artifact": str(audio_path),
            "source_visual_artifact": str(visual_path),
            "model": None,
            "review_mode": "no_detected_speech",
            "speech_evidence_status": SPEECH_NOT_DETECTED,
            "review_policy": {
                "purpose": "record the absence of detected usable speech evidence",
                "raw_word_timeline_immutable": True,
                "no_narration_inferred_from_ocr_or_visual_evidence": True,
            },
            "source_transcript_raw": "",
            "reviewed_transcript_raw": "",
            "segments": [],
            "chunks": [],
            "explicit_review": {
                "applied": False,
                "source_file": None,
                "reviewer": None,
                "decision_source": None,
                "decision_count": 0,
            },
            "summary": {
                "segment_count": 0,
                "raw_word_count": 0,
                "remote_model_calls": 0,
                "corrected_segment_count": 0,
                "uncertain_segment_count": 0,
                "manual_review_item_count": 0,
            },
            "manual_review": {
                "required": False,
                "item_count": 0,
                "items": [],
            },
            "authority": {
                "raw_audio_words_and_timestamps": "faster-whisper audio_v1",
                "reviewed_narration_text": "not_applicable_no_detected_speech",
                "ocr_or_visual_as_narration": "prohibited",
            },
            "timing": {
                "artifact_model_compute_seconds": 0.0,
                "current_run_model_compute_seconds": 0.0,
                "reused_chunk_count": 0,
                "fresh_chunk_count": 0,
                "total_elapsed_seconds": round(total_elapsed, 6),
            },
            "validation": {
                "passed": True,
                "segment_count_preserved": True,
                "segment_order_preserved": True,
                "segment_timestamps_preserved": True,
                "word_refs_preserved": True,
                "raw_word_count_preserved": True,
                "raw_words_modified": False,
                "no_narration_inferred_from_visual_evidence": True,
            },
        }
        output_json = output_dir / "narration_review_v1.json"
        write_json(output_json, result)
        (output_dir / "narration_review_v1_summary.md").write_text(
            "# Narration Review V1\n\n"
            f"- Case ID: `{args.case_id}`\n"
            "- Review mode: `no_detected_speech`\n"
            "- Segments: `0`\n"
            "- Raw words (immutable): `0`\n"
            "- Manual review required: `False`\n"
            "- DeepSeek time: `0.00s`\n",
            encoding="utf-8",
        )
        print("NARRATION REVIEW V1 PASS", flush=True)
        print("Review mode: no_detected_speech", flush=True)
        print("Remote model calls: 0", flush=True)
        print(f"JSON: {output_json}", flush=True)
        return

    if not segments:
        raise RuntimeError(
            "audio_v1 contains no segments."
        )
    if not words:
        raise RuntimeError(
            "audio_v1 contains no words."
        )

    word_by_id = {
        str(x["word_id"]): x
        for x in words
    }

    review_data: dict[str, Any] | None = None
    review_path: Path | None = None
    review_by_segment: dict[str, dict[str, Any]] = {}

    if args.review_file:
        review_path = Path(args.review_file).expanduser().resolve()
        if not review_path.exists():
            raise FileNotFoundError(review_path)

        review_data = read_json(review_path)

        if str(review_data.get("case_id", "")) != args.case_id:
            raise RuntimeError("review_file case_id mismatch.")

        decisions = review_data.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            raise RuntimeError(
                "review_file.decisions must be a non-empty array."
            )

        valid_segment_ids = {
            str(x["segment_id"]) for x in segments
        }

        for item in decisions:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "Each narration review decision must be an object."
                )

            segment_id = str(item.get("segment_id", ""))
            action = str(item.get("action", "")).lower()

            if segment_id not in valid_segment_ids:
                raise RuntimeError(
                    f"Unknown review segment_id: {segment_id!r}"
                )
            if segment_id in review_by_segment:
                raise RuntimeError(
                    f"Duplicate review decision for {segment_id}."
                )
            if action not in {"keep", "correct"}:
                raise RuntimeError(
                    f"{segment_id}: action must be keep or correct."
                )

            if action == "correct":
                corrected_text = str(item.get("corrected_text", ""))
                if not corrected_text:
                    raise RuntimeError(
                        f"{segment_id}: corrected_text is required."
                    )

                allowed_frames = {
                    str(x["frame_id"]) for x in frames
                }
                evidence_refs = [
                    str(x)
                    for x in item.get("evidence_frame_refs", [])
                ]
                if not evidence_refs:
                    raise RuntimeError(
                        f"{segment_id}: correct requires evidence_frame_refs."
                    )
                unknown_frames = [
                    x for x in evidence_refs
                    if x not in allowed_frames
                ]
                if unknown_frames:
                    raise RuntimeError(
                        f"{segment_id}: unknown evidence frames: "
                        + ", ".join(unknown_frames)
                    )

            review_by_segment[segment_id] = {
                **item,
                "segment_id": segment_id,
                "action": action,
            }

    prepared_inputs: list[dict[str, Any]] = []

    for segment in segments:
        prepared_inputs.append(
            {
                "segment_id": str(
                    segment["segment_id"]
                ),
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "source_text": str(
                    segment["source_text"]
                ),
                "word_refs": [
                    str(x)
                    for x in segment.get(
                        "word_refs", []
                    )
                ],
                "low_confidence_words": (
                    low_confidence_words(
                        segment,
                        word_by_id,
                        threshold=(
                            args.low_confidence_threshold
                        ),
                    )
                ),
                "supporting_ocr": (
                    supporting_ocr_for_segment(
                        segment,
                        frames,
                        window_seconds=(
                            args.ocr_window_seconds
                        ),
                        max_items=args.max_ocr_items,
                    )
                ),
            }
        )

    project_root = (
        Path(__file__).resolve().parents[1]
    )
    output_dir = (
        Path(args.output_root)
        .expanduser()
        .resolve()
        if args.output_root
        else (
            project_root
            / "data"
            / "narration"
            / args.case_id
            / "v1"
        )
    )
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_chunks = (
        len(prepared_inputs)
        + args.segment_chunk_size
        - 1
    ) // args.segment_chunk_size

    print(
        f"Tool version: {SCRIPT_VERSION}",
        flush=True,
    )
    print(
        f"Case ID: {args.case_id}",
        flush=True,
    )
    print(
        f"Audio segments: {len(segments)}",
        flush=True,
    )
    print(
        f"Audio words (immutable): {len(words)}",
        flush=True,
    )
    print(
        f"Visual frames: {len(frames)}",
        flush=True,
    )
    print(
        f"Segment chunk size: "
        f"{args.segment_chunk_size}",
        flush=True,
    )
    print(
        f"Narration chunks: {total_chunks}",
        flush=True,
    )
    print(
        f"Model: {args.model}",
        flush=True,
    )
    print(
        f"OCR window: ±{args.ocr_window_seconds}s",
        flush=True,
    )
    print()

    client: OpenAI | None = None
    all_model_results: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    current_run_model_seconds = 0.0
    reused_chunk_count = 0

    for chunk_no, start_index in enumerate(
        range(
            0,
            len(prepared_inputs),
            args.segment_chunk_size,
        ),
        start=1,
    ):
        chunk_inputs = prepared_inputs[
            start_index:
            start_index + args.segment_chunk_size
        ]
        safe_chunk_inputs = project_value(
            chunk_inputs,
            "safe_verbatim",
        )
        prompt = build_prompt(
            args.case_id,
            safe_chunk_inputs,
        )
        egress_audit = build_egress_audit(
            safe_input=safe_chunk_inputs,
            rendered_prompt=prompt,
            privacy_context=privacy_context,
        )

        input_hash = sha256_json(
            {
                "prompt_version": PROMPT_VERSION,
                "inputs": safe_chunk_inputs,
            }
        )

        cache_path = (
            chunks_dir
            / f"narration_chunk_{chunk_no:03d}.json"
        )
        raw_path = (
            chunks_dir
            / f"narration_chunk_{chunk_no:03d}_raw.json"
        )

        if cache_path.exists() and not args.force:
            cached = read_json(cache_path)
            meta = dict(cached.get("chunk", {}))

            profile_matches = (
                str(meta.get("model"))
                == str(args.model)
                and int(
                    meta.get(
                        "segment_chunk_size"
                    )
                    or 0
                )
                == args.segment_chunk_size
                and str(
                    meta.get("prompt_version")
                )
                == PROMPT_VERSION
                and str(
                    meta.get("input_sha256")
                )
                == input_hash
                and all(
                    meta.get(key) == value
                    for key, value in egress_audit.items()
                )
            )

            if profile_matches:
                try:
                    cached_results, _ = (
                        sanitize_model_output(
                            {
                                "segments": cached.get(
                                    "segments", []
                                )
                            },
                            chunk_inputs,
                        )
                    )
                except Exception as exc:
                    print(
                        f"[{chunk_no}/{total_chunks}] "
                        f"Cached chunk invalid -> rerun: "
                        f"{exc}",
                        flush=True,
                    )
                else:
                    print(
                        f"[{chunk_no}/{total_chunks}] "
                        f"SKIP validated cached narration "
                        f"chunk "
                        f"({len(cached_results)} segments)",
                        flush=True,
                    )
                    all_model_results.extend(
                        cached_results
                    )
                    chunk_records.append(meta)
                    reused_chunk_count += 1
                    continue

        success = False
        last_error: Exception | None = None
        final_results: list[
            dict[str, Any]
        ] = []
        final_warnings: list[str] = []
        elapsed_total = 0.0
        response_usage: dict[str, Any] = {}

        for attempt in range(
            1,
            args.max_retries + 2,
        ):
            print(
                f"[{chunk_no}/{total_chunks}] "
                f"START attempt "
                f"{attempt}/{args.max_retries + 1} "
                f"({len(chunk_inputs)} segments)",
                flush=True,
            )

            require_privacy_projection_for_egress(privacy_context)
            assert_safe_for_external_model(prompt)
            if client is None:
                client = get_client()

            started = time.perf_counter()

            response = (
                client.chat.completions.create(
                    model=args.model,
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    response_format={
                        "type": "json_object"
                    },
                    temperature=0,
                    max_tokens=6000,
                    extra_body={
                        "thinking": {
                            "type": "disabled"
                        }
                    },
                )
            )

            elapsed = (
                time.perf_counter() - started
            )
            elapsed_total += elapsed
            current_run_model_seconds += elapsed
            response_usage = usage_dict(response)

            content = (
                response
                .choices[0]
                .message
                .content
            )

            if not content:
                last_error = RuntimeError(
                    "DeepSeek returned empty content."
                )
                print(
                    f"[{chunk_no}/{total_chunks}] "
                    f"INVALID attempt {attempt} "
                    f"elapsed={elapsed:.2f}s: "
                    f"empty content",
                    flush=True,
                )
                continue

            raw_path.write_text(
                content,
                encoding="utf-8",
            )

            try:
                payload = json.loads(content)
                parsed, warnings = (
                    sanitize_model_output(
                        payload,
                        chunk_inputs,
                    )
                )
            except Exception as exc:
                last_error = exc
                print(
                    f"[{chunk_no}/{total_chunks}] "
                    f"INVALID attempt {attempt} "
                    f"elapsed={elapsed:.2f}s: "
                    f"{exc}",
                    flush=True,
                )
                continue

            final_results = parsed
            final_warnings = warnings
            success = True

            print(
                f"[{chunk_no}/{total_chunks}] "
                f"PASS attempt {attempt} "
                f"elapsed={elapsed:.2f}s "
                f"tokens="
                f"{response_usage.get('total_tokens')}",
                flush=True,
            )

            for warning in warnings:
                print(
                    f"[{chunk_no}/{total_chunks}] "
                    f"SANITIZE WARNING: {warning}",
                    flush=True,
                )

            break

        if not success:
            raise RuntimeError(
                f"Narration chunk {chunk_no} "
                f"failed after "
                f"{args.max_retries + 1} attempts: "
                f"{last_error}"
            )

        chunk_record = {
            "chunk_id": f"N{chunk_no:03d}",
            "model": args.model,
            "prompt_version": PROMPT_VERSION,
            "segment_chunk_size": (
                args.segment_chunk_size
            ),
            "segment_ids": [
                x["segment_id"]
                for x in chunk_inputs
            ],
            "input_sha256": input_hash,
            "input_content_hash": input_hash,
            "elapsed_seconds": round(
                elapsed_total, 6
            ),
            "attempts_used": attempt,
            "usage": response_usage,
            "sanitization_warnings": (
                final_warnings
            ),
            "status": "success",
            **egress_audit,
        }

        write_json(
            cache_path,
            {
                "chunk": chunk_record,
                "segments": final_results,
            },
        )

        all_model_results.extend(
            final_results
        )
        chunk_records.append(chunk_record)

    expected_ids = [
        x["segment_id"]
        for x in prepared_inputs
    ]
    returned_ids = [
        x["segment_id"]
        for x in all_model_results
    ]

    if returned_ids != expected_ids:
        raise RuntimeError(
            "Global narration segment "
            "IDs/order mismatch."
        )

    prepared_by_id = {
        x["segment_id"]: x
        for x in prepared_inputs
    }

    reviewed_segments: list[
        dict[str, Any]
    ] = []
    manual_review_items: list[
        dict[str, Any]
    ] = []

    correction_count = 0
    uncertainty_count = 0

    for model_item in all_model_results:
        segment_id = model_item["segment_id"]
        source = prepared_by_id[segment_id]
        source_text = source["source_text"]

        model_reviewed_text = model_item["reviewed_text"]
        model_decision = model_item["decision"]
        model_confidence = model_item["confidence"]

        reviewed_text = model_reviewed_text
        effective_decision = model_decision
        effective_confidence = model_confidence
        review_action = None
        review_reason = ""
        review_evidence_refs: list[str] = []

        explicit_review = review_by_segment.get(segment_id)

        if explicit_review is not None:
            review_action = explicit_review["action"]
            review_reason = str(explicit_review.get("reason", ""))
            review_evidence_refs = [
                str(x)
                for x in explicit_review.get(
                    "evidence_frame_refs", []
                )
            ]

            if review_action == "correct":
                reviewed_text = str(
                    explicit_review["corrected_text"]
                )
                effective_decision = "corrected"
                effective_confidence = "high"
            elif review_action == "keep":
                reviewed_text = source_text
                effective_decision = "unchanged"
                effective_confidence = "high"

        changed = reviewed_text != source_text

        if changed:
            correction_count += 1

        if effective_decision == "uncertain":
            uncertainty_count += 1

        needs_human_review = (
            effective_decision == "uncertain"
            or effective_confidence != "high"
        )

        if needs_human_review:
            manual_review_items.append(
                {
                    "segment_id": segment_id,
                    "start": source["start"],
                    "end": source["end"],
                    "source_text": source_text,
                    "reviewed_text": reviewed_text,
                    "decision": effective_decision,
                    "confidence": effective_confidence,
                    "note": model_item["note"],
                    "evidence_frame_refs": (
                        review_evidence_refs
                        if review_action is not None
                        else model_item["evidence_frame_refs"]
                    ),
                }
            )

        reviewed_segments.append(
            {
                "segment_id": segment_id,
                "start": source["start"],
                "end": source["end"],
                "source_text": source_text,
                "reviewed_text": reviewed_text,
                "changed": changed,
                "decision": effective_decision,
                "confidence": effective_confidence,
                "model_review": {
                    "reviewed_text": model_reviewed_text,
                    "decision": model_decision,
                    "confidence": model_confidence,
                    "evidence_frame_refs": model_item[
                        "evidence_frame_refs"
                    ],
                    "note": model_item["note"],
                },
                "explicit_review": {
                    "applied": review_action is not None,
                    "action": review_action,
                    "reason": review_reason,
                    "evidence_frame_refs": review_evidence_refs,
                },
                "word_refs": source[
                    "word_refs"
                ],
                "low_confidence_words": (
                    source[
                        "low_confidence_words"
                    ]
                ),
                "supporting_ocr": (
                    source["supporting_ocr"]
                ),
                "evidence_frame_refs": (
                    review_evidence_refs
                    if review_action is not None
                    else model_item["evidence_frame_refs"]
                ),
                "note": (
                    review_reason
                    if review_action is not None
                    else model_item["note"]
                ),
                "diff": deterministic_diff(
                    source_text,
                    reviewed_text,
                ),
            }
        )

    source_transcript = "\n".join(
        str(x["source_text"])
        for x in segments
    )
    reviewed_transcript = "\n".join(
        str(x["reviewed_text"])
        for x in reviewed_segments
    )

    total_elapsed = (
        time.perf_counter() - started_total
    )

    result = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": SCRIPT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "case_id": args.case_id,
        "source_audio_artifact": (
            str(audio_path)
        ),
        "source_visual_artifact": (
            str(visual_path)
        ),
        "model": args.model,
        "review_policy": {
            "purpose": (
                "human-readable narration correction "
                "without altering raw ASR evidence"
            ),
            "raw_word_timeline_immutable": True,
            "segment_timestamps_immutable": True,
            "segment_word_refs_immutable": True,
            "correction_requires_ocr_evidence": True,
            "no_paraphrase": True,
            "no_style_rewrite": True,
            "uncertain_keeps_source_text": True,
            "ocr_window_seconds": (
                args.ocr_window_seconds
            ),
            "low_confidence_threshold": (
                args.low_confidence_threshold
            ),
        },
        "source_transcript_raw": (
            source_transcript
        ),
        "reviewed_transcript_raw": (
            reviewed_transcript
        ),
        "segments": reviewed_segments,
        "chunks": chunk_records,
        "explicit_review": {
            "applied": bool(review_by_segment),
            "source_file": str(review_path) if review_path else None,
            "reviewer": (
                review_data.get("reviewer")
                if review_data is not None
                else None
            ),
            "decision_source": (
                review_data.get("decision_source")
                if review_data is not None
                else None
            ),
            "decision_count": len(review_by_segment),
        },
        "summary": {
            "segment_count": len(
                reviewed_segments
            ),
            "raw_word_count": len(words),
            "corrected_segment_count": (
                correction_count
            ),
            "uncertain_segment_count": (
                uncertainty_count
            ),
            "manual_review_item_count": (
                len(manual_review_items)
            ),
        },
        "manual_review": {
            "required": bool(
                manual_review_items
            ),
            "item_count": len(
                manual_review_items
            ),
            "items": manual_review_items,
        },
        "authority": {
            "raw_audio_words_and_timestamps": (
                "faster-whisper audio_v1"
            ),
            "ocr_candidate_text": (
                "qwen visual_v1"
            ),
            "reviewed_narration_text": (
                args.model
            ),
            "correction_acceptance_constraint": (
                "programmatic OCR-evidence validation"
            ),
        },
        "timing": {
            "artifact_model_compute_seconds": round(
                sum(
                    float(
                        x.get(
                            "elapsed_seconds"
                        )
                        or 0
                    )
                    for x in chunk_records
                ),
                6,
            ),
            "current_run_model_compute_seconds": round(
                current_run_model_seconds, 6
            ),
            "reused_chunk_count": reused_chunk_count,
            "fresh_chunk_count": total_chunks - reused_chunk_count,
            "total_elapsed_seconds": round(
                total_elapsed, 6
            ),
        },
        "validation": {
            "passed": True,
            "segment_count_preserved": True,
            "segment_order_preserved": True,
            "segment_timestamps_preserved": True,
            "word_refs_preserved": True,
            "raw_word_count_preserved": True,
            "raw_words_modified": False,
        },
    }

    output_json = (
        output_dir
        / "narration_review_v1.json"
    )
    write_json(output_json, result)

    summary_lines = [
        "# Narration Review V1",
        "",
        f"- Case ID: `{args.case_id}`",
        f"- Segments: `{len(reviewed_segments)}`",
        f"- Raw words (immutable): `{len(words)}`",
        f"- Corrected segments: `{correction_count}`",
        f"- Explicit review decisions applied: `{len(review_by_segment)}`",
        f"- Uncertain segments: `{uncertainty_count}`",
        (
            f"- Manual review required: "
            f"`{bool(manual_review_items)}`"
        ),
        (
            f"- Manual review items: "
            f"`{len(manual_review_items)}`"
        ),
        (
            f"- DeepSeek time: "
            f"`{result['timing']['artifact_model_compute_seconds']:.2f}s`"
        ),
        "",
        "## Corrections",
        "",
    ]

    corrected = [
        x for x in reviewed_segments
        if x["changed"]
    ]

    if not corrected:
        summary_lines.append(
            "- No corrections."
        )
    else:
        for item in corrected:
            summary_lines.append(
                f"- `{item['segment_id']}` "
                f"{item['start']:.2f}–"
                f"{item['end']:.2f}s: "
                f"`{item['source_text']}` "
                f"→ `{item['reviewed_text']}` "
                f"({item['confidence']})"
            )

    if manual_review_items:
        summary_lines += [
            "",
            "## Manual Review",
            "",
        ]

        for item in manual_review_items:
            summary_lines.append(
                f"- `{item['segment_id']}` "
                f"{item['start']:.2f}–"
                f"{item['end']:.2f}s — "
                f"{item['decision']} / "
                f"{item['confidence']} — "
                f"{item['note']}"
            )

    summary_path = (
        output_dir
        / "narration_review_v1_summary.md"
    )
    summary_path.write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
    )

    print()
    print(
        "NARRATION REVIEW V1 PASS",
        flush=True,
    )
    print(
        f"Case ID: {args.case_id}",
        flush=True,
    )
    print(
        f"Segments: {len(reviewed_segments)}",
        flush=True,
    )
    print(
        f"Raw words unchanged: {len(words)}",
        flush=True,
    )
    print(
        f"Corrected segments: "
        f"{correction_count}",
        flush=True,
    )
    print(
        f"Explicit review decisions applied: "
        f"{len(review_by_segment)}",
        flush=True,
    )
    print(
        f"Uncertain segments: "
        f"{uncertainty_count}",
        flush=True,
    )
    print(
        f"Manual review required: "
        f"{bool(manual_review_items)} "
        f"({len(manual_review_items)} items)",
        flush=True,
    )
    print(
        f"Artifact model compute: "
        f"{result['timing']['artifact_model_compute_seconds']:.2f}s",
        flush=True,
    )
    print(
        f"Current run model compute: "
        f"{result['timing']['current_run_model_compute_seconds']:.2f}s "
        f"(reused chunks: {reused_chunk_count}/{total_chunks})",
        flush=True,
    )
    print(
        f"Total elapsed: "
        f"{total_elapsed:.2f}s",
        flush=True,
    )
    print(
        f"JSON: {output_json}",
        flush=True,
    )
    print(
        f"Summary: {summary_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
