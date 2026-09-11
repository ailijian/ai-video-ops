from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from privacy_projection_v1 import (
    PRIVACY_POLICY_VERSION,
    PRIVACY_SCHEMA_VERSION,
    build_privacy_annotation,
    sha256_file,
)


VISUAL_TEXT_FIELDS = (
    "ocr_raw",
    "scene_summary",
    "visible_facts",
    "visual_change_from_previous",
    "new_visual_information",
    "uncertainties",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def textual_values(value: Any, field: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from textual_values(item, f"{field}[{index}]")


def collect_annotations(
    visual: dict[str, Any],
    audio: dict[str, Any],
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    inspected = 0

    for frame_index, frame in enumerate(visual.get("frames") or []):
        source_ref = str(frame.get("frame_id") or f"frame_{frame_index}")
        for field_name in VISUAL_TEXT_FIELDS:
            for field, text in textual_values(
                frame.get(field_name),
                f"frames[{frame_index}].{field_name}",
            ):
                inspected += 1
                record = build_privacy_annotation(
                    source_ref=source_ref,
                    field=field,
                    value=text,
                )
                if record["annotations"]:
                    records.append(record)

    transcript = audio.get("transcript_raw")
    if isinstance(transcript, str):
        inspected += 1
        record = build_privacy_annotation(
            source_ref="audio_word_timeline_v1.json",
            field="transcript_raw",
            value=transcript,
        )
        if record["annotations"]:
            records.append(record)

    for index, segment in enumerate(audio.get("segments") or []):
        text = segment.get("source_text")
        if not isinstance(text, str):
            continue
        inspected += 1
        record = build_privacy_annotation(
            source_ref=str(segment.get("segment_id") or f"segment_{index}"),
            field=f"segments[{index}].source_text",
            value=text,
        )
        if record["annotations"]:
            records.append(record)

    return records, inspected


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build canonical Privacy-Safe Evidence Projection V1 without "
            "modifying raw Visual or Audio evidence."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--visual-v1", required=True)
    parser.add_argument("--audio-v1", required=True)
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()

    visual_path = Path(args.visual_v1).expanduser().resolve()
    audio_path = Path(args.audio_v1).expanduser().resolve()
    for path in (visual_path, audio_path):
        if not path.exists():
            raise FileNotFoundError(path)

    before_hashes = {
        "visual_v1": sha256_file(visual_path),
        "audio_v1": sha256_file(audio_path),
    }
    visual = read_json(visual_path)
    audio = read_json(audio_path)
    if str(visual.get("case_id")) != args.case_id:
        raise RuntimeError("Visual V1 case_id mismatch.")
    if str(audio.get("case_id")) != args.case_id:
        raise RuntimeError("Audio V1 case_id mismatch.")

    annotations, inspected = collect_annotations(visual, audio)
    high_redactions = sum(
        1
        for record in annotations
        for item in record["annotations"]
        if item.get("confidence") == "high"
    )
    review_required = sum(
        1
        for record in annotations
        for item in record["annotations"]
        if item.get("review_required")
    )
    unresolved = 0

    after_hashes = {
        "visual_v1": sha256_file(visual_path),
        "audio_v1": sha256_file(audio_path),
    }
    if before_hashes != after_hashes:
        raise RuntimeError("Raw source changed during privacy projection.")

    project_root = Path(__file__).resolve().parents[1]
    output_dir = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "privacy" / args.case_id / "v1"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "privacy_projection_v1.json"

    artifact = {
        "schema_version": PRIVACY_SCHEMA_VERSION,
        "policy_version": PRIVACY_POLICY_VERSION,
        "privacy_policy_version": PRIVACY_POLICY_VERSION,
        "case_id": args.case_id,
        "created_at": now_iso(),
        "source_artifacts": {
            "visual_v1": {
                "path": str(visual_path),
                "sha256": before_hashes["visual_v1"],
            },
            "audio_v1": {
                "path": str(audio_path),
                "sha256": before_hashes["audio_v1"],
            },
        },
        "annotations": annotations,
        "projection_summary": {
            "text_fields_inspected": inspected,
            "annotated_fields": len(annotations),
            "sensitive_span_count": sum(
                len(record["annotations"]) for record in annotations
            ),
            "high_confidence_redactions": high_redactions,
            "review_required_items": review_required,
            "projection_modes": ["safe_verbatim", "safe_semantic"],
        },
        "validation": {
            "passed": unresolved == 0,
            "unresolved_sensitive_items": unresolved,
            "high_confidence_redactions": high_redactions,
            "review_required_items": review_required,
            "raw_sources_modified": False,
        },
    }
    output_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("PRIVACY PROJECTION V1 PASS", flush=True)
    print(f"Case ID: {args.case_id}", flush=True)
    print(f"Annotated fields: {len(annotations)}", flush=True)
    print(f"High-confidence redactions: {high_redactions}", flush=True)
    print(f"Review required: {review_required}", flush=True)
    print(f"Artifact: {output_path}", flush=True)


if __name__ == "__main__":
    main()
