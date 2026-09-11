from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "audio-word-timeline-v1.0-draft"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_text(text: str) -> str:
    return re.sub(r"[\s，。！？、；：,.!?;:'\"“”‘’（）()\[\]【】]", "", text or "")


def main() -> None:
    started = time.perf_counter()

    parser = argparse.ArgumentParser(
        description="Build a word-level audio evidence timeline."
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--gap-threshold", type=float, default=0.35)
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    raw = read_json(audio_path)
    source_segments = list(raw.get("segments") or [])
    if not source_segments:
        raise RuntimeError("No audio segments found.")

    words = []
    segment_views = []
    errors = []
    warnings = []
    previous_word_end = None
    word_counter = 0

    for segment_index, segment in enumerate(source_segments, start=1):
        segment_id = f"A{segment_index:03d}"
        segment_words = list(segment.get("words") or [])

        if not segment_words:
            errors.append(f"{segment_id} has no word timestamps.")
            continue

        word_refs = []
        reconstructed_parts = []

        for local_index, word in enumerate(segment_words, start=1):
            word_counter += 1
            word_id = f"W{word_counter:06d}"

            start = word.get("start")
            end = word.get("end")
            text = str(word.get("word", ""))

            if start is None or end is None:
                errors.append(f"{word_id} missing start/end")
                continue

            start = float(start)
            end = float(end)

            if end < start:
                errors.append(f"{word_id} has end < start: {start} -> {end}")

            if previous_word_end is not None and start < previous_word_end - 0.02:
                warnings.append(
                    f"{word_id} starts before previous word ended "
                    f"({start:.3f} < {previous_word_end:.3f})."
                )

            item = {
                "word_id": word_id,
                "segment_id": segment_id,
                "segment_word_index": local_index,
                "start": start,
                "end": end,
                "midpoint": round((start + end) / 2, 6),
                "duration": round(end - start, 6),
                "text": text,
                "probability": word.get("probability"),
            }

            words.append(item)
            word_refs.append(word_id)
            reconstructed_parts.append(text)
            previous_word_end = max(previous_word_end or end, end)

        source_text = str(segment.get("text", "")).strip()
        reconstructed_text = "".join(reconstructed_parts).strip()
        text_match = normalize_text(source_text) == normalize_text(reconstructed_text)

        if not text_match:
            warnings.append(
                f"{segment_id} reconstructed text differs: "
                f"segment={source_text!r}, words={reconstructed_text!r}"
            )

        segment_views.append(
            {
                "segment_id": segment_id,
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "source_text": source_text,
                "word_refs": word_refs,
                "word_reconstruction": reconstructed_text,
                "word_reconstruction_matches_segment": text_match,
            }
        )

    if errors:
        print("\nAUDIO WORD TIMELINE BUILD FAILED")
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(2)

    silence_gaps = []
    for previous, current in zip(words, words[1:]):
        gap = float(current["start"]) - float(previous["end"])
        if gap >= args.gap_threshold:
            silence_gaps.append(
                {
                    "start": previous["end"],
                    "end": current["start"],
                    "duration": round(gap, 6),
                    "previous_word_ref": previous["word_id"],
                    "next_word_ref": current["word_id"],
                }
            )

    transcript_raw_path = audio_path.parent / "transcript_raw.txt"
    transcript_raw = (
        transcript_raw_path.read_text(encoding="utf-8")
        if transcript_raw_path.exists()
        else "\n".join(x["source_text"] for x in segment_views)
    )

    source_duration = raw.get("duration")
    if source_duration is None:
        source_duration = max(float(words[-1]["end"]), float(source_segments[-1].get("end", 0)))
    source_duration = float(source_duration)

    project_root = Path(__file__).resolve().parents[1]
    output_dir = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "audio" / args.case_id / "audio_v1"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "schema_version": SCHEMA_VERSION,
        "case_id": args.case_id,
        "source_audio_artifact": str(audio_path),
        "engine": "faster-whisper",
        "model": raw.get("model"),
        "device": raw.get("device"),
        "compute_type": raw.get("compute_type"),
        "language": raw.get("language"),
        "language_probability": raw.get("language_probability"),
        "duration_seconds": source_duration,
        "transcript_raw": transcript_raw,
        "segments": segment_views,
        "words": words,
        "silence_gaps": silence_gaps,
        "future_shot_projection_policy": {
            "rule": "word_midpoint_exactly_once",
            "description": (
                "Assign each word to exactly one visual shot by word midpoint. "
                "Use half-open shot intervals [start,end), except the final shot."
            ),
            "reason": "Prevents cross-cut Whisper segments from duplicating into multiple shots.",
        },
        "coverage": {
            "source_segment_count": len(source_segments),
            "segment_count": len(segment_views),
            "word_count": len(words),
            "speech_start": min(float(x["start"]) for x in words),
            "speech_end": max(float(x["end"]) for x in words),
            "silence_gap_count": len(silence_gaps),
            "silence_gap_threshold": args.gap_threshold,
        },
        "authority": {
            "word_text_and_timestamps": "faster-whisper raw output",
            "midpoint": "deterministic_python",
            "silence_gaps": "deterministic_python",
            "no_semantic_rewrite_performed": True,
        },
        "validation": {
            "passed": True,
            "errors": [],
            "warnings": warnings,
            "all_segments_have_word_refs": all(bool(x["word_refs"]) for x in segment_views),
            "all_words_have_valid_timestamps": all(x["end"] >= x["start"] for x in words),
            "word_ids_unique": len({x["word_id"] for x in words}) == len(words),
        },
    }

    output_json = output_dir / "audio_word_timeline_v1.json"
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - started
    summary = [
        "AUDIO WORD TIMELINE V1 PASS",
        f"Case ID: {args.case_id}",
        f"Segments: {len(segment_views)}",
        f"Words: {len(words)}",
        f"Silence gaps >= {args.gap_threshold:.2f}s: {len(silence_gaps)}",
        f"Source duration: {source_duration:.3f}s",
        f"Build elapsed: {elapsed:.3f}s",
        "Future shot assignment: word_midpoint_exactly_once",
        f"JSON: {output_json}",
    ]
    if warnings:
        summary += ["", "WARNINGS"] + [f"- {w}" for w in warnings]

    output_summary = output_dir / "audio_word_timeline_v1_summary.txt"
    output_summary.write_text("\n".join(summary), encoding="utf-8")

    print()
    for line in summary:
        print(line)


if __name__ == "__main__":
    main()
