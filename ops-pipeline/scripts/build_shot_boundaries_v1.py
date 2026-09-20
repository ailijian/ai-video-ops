from __future__ import annotations

import argparse
import getpass
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from privacy_projection_v1 import (
    assert_safe_for_external_model,
    build_egress_audit,
    load_privacy_projection,
    project_value,
    require_privacy_projection_for_egress,
)
from speech_evidence_v1 import require_audio_speech_evidence


SCRIPT_VERSION = "build_shot_boundaries_v1.py@1.6"
SCHEMA_VERSION = "shot-boundaries-v1.5-draft"
PROMPT_VERSION = "shot-boundary-prompt-v1.0"

REASON_TYPES = {
    "video_start",
    "same_shot_motion",
    "text_overlay_change_only",
    "scene_or_location_change",
    "camera_view_change",
    "subject_or_action_discontinuity",
    "uncertain",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_client() -> OpenAI:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        key = getpass.getpass("DeepSeek API Key: ")
    return OpenAI(api_key=key, base_url="https://api.deepseek.com")


def uniq(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def word_midpoint(word: dict[str, Any]) -> float:
    if word.get("midpoint") is not None:
        return float(word["midpoint"])
    return (float(word["start"]) + float(word["end"])) / 2.0


def belongs(ts: float, start: float, end: float, is_last: bool) -> bool:
    if is_last:
        return start <= ts <= end + 1e-6
    return start <= ts < end


def short_shot_review_item(shots: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    shot = shots[index]
    # Removing the next shot's start boundary merges this short shot forward;
    # the first shot's mandatory video-start boundary must not be rejected.
    merge_boundary = (
        shots[index + 1]["boundary"] if index + 1 < len(shots)
        else shot["boundary"]
    )
    if float(shot["duration"]) >= 0.5 or merge_boundary.get("review_action") == "keep":
        return None
    return {
        "type": "short_shot",
        "shot_id": shot["shot_id"],
        "start": shot["start"],
        "end": shot["end"],
        "duration": shot["duration"],
        "boundary_frame_id": merge_boundary["selected_from_frame_ref"],
        "merge_allowed": index + 1 < len(shots) or index > 0,
    }


def usage_dict(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def prepare_boundary_egress(
    *,
    case_id: str,
    context_frame: dict[str, Any] | None,
    primary_frames: list[dict[str, Any]],
    privacy_context: dict[str, Any] | None,
    speech_evidence_status: str = "detected",
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    require_privacy_projection_for_egress(privacy_context)
    safe_primary = project_value(primary_frames, "safe_verbatim")
    safe_context = (
        project_value(context_frame, "safe_verbatim")
        if context_frame is not None
        else None
    )
    safe_input = {
        "context_frame": safe_context,
        "primary_frames": safe_primary,
    }
    if speech_evidence_status != "detected":
        safe_input["speech_evidence_status"] = speech_evidence_status
    prompt = build_prompt(
        case_id=case_id,
        context_frame=safe_context,
        primary_frames=safe_primary,
        speech_evidence_status=speech_evidence_status,
    )
    pre_call_audit = build_egress_audit(
        safe_input=safe_input,
        rendered_prompt=prompt,
        privacy_context=privacy_context,
    )
    return safe_input, prompt, pre_call_audit


def invoke_boundary_transport(
    *,
    safe_input: dict[str, Any],
    rendered_prompt: str,
    privacy_context: dict[str, Any] | None,
    pre_call_audit: dict[str, Any],
    transport: Callable[[], Any],
) -> tuple[Any, dict[str, Any]]:
    require_privacy_projection_for_egress(privacy_context)
    assert_safe_for_external_model(rendered_prompt)
    response = transport()
    post_call_audit = build_egress_audit(
        safe_input=safe_input,
        rendered_prompt=rendered_prompt,
        privacy_context=privacy_context,
    )
    if post_call_audit != pre_call_audit:
        raise RuntimeError("Boundary egress audit changed across network call.")
    return response, post_call_audit


def sanitize_decisions(
    payload: dict[str, Any],
    expected_ids: list[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise RuntimeError("Model output missing decisions array.")

    returned_ids = [str(x.get("frame_id")) for x in decisions]
    expected_set = set(expected_ids)

    duplicated = [
        frame_id
        for frame_id in expected_ids
        if returned_ids.count(frame_id) > 1
    ]
    if duplicated:
        raise RuntimeError(
            "Expected frame IDs duplicated: " + ", ".join(duplicated)
        )

    filtered = [
        item for item in decisions
        if str(item.get("frame_id")) in expected_set
    ]
    filtered_ids = [str(x.get("frame_id")) for x in filtered]

    missing = [x for x in expected_ids if x not in filtered_ids]
    if missing:
        raise RuntimeError(
            "Expected frame IDs missing: " + ", ".join(missing)
        )

    if filtered_ids != expected_ids:
        raise RuntimeError(
            "Expected frame order mismatch.\n"
            f"Expected: {expected_ids}\n"
            f"Filtered: {filtered_ids}\n"
            f"Raw: {returned_ids}"
        )

    warnings: list[str] = []
    unexpected = [x for x in returned_ids if x not in expected_set]
    if unexpected:
        warnings.append(
            "Dropped unexpected model-generated frame IDs: "
            + ", ".join(unexpected)
        )

    for item in filtered:
        frame_id = str(item["frame_id"])

        if not isinstance(item.get("boundary_before"), bool):
            raise RuntimeError(
                f"{frame_id}: boundary_before must be true/false"
            )

        reason_type = item.get("reason_type")
        if reason_type not in REASON_TYPES:
            raise RuntimeError(
                f"{frame_id}: invalid reason_type={reason_type!r}"
            )

        confidence = item.get("confidence")
        if confidence not in {"high", "medium", "low"}:
            raise RuntimeError(
                f"{frame_id}: invalid confidence={confidence!r}"
            )

    return filtered, warnings


def compact_frame(
    frame: dict[str, Any],
    manifest_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    frame_id = str(frame["frame_id"])
    mf = manifest_by_id.get(frame_id, {})

    pixel_difference_signal = mf.get("difference_ratio_from_previous_kept")
    if isinstance(pixel_difference_signal, (int, float)):
        pixel_difference_signal = round(float(pixel_difference_signal), 6)

    return {
        "frame_id": frame_id,
        "timestamp_seconds": float(frame["timestamp_seconds"]),
        "ocr_raw": frame.get("ocr_raw", ""),
        "scene_summary": frame.get("scene_summary", ""),
        "visual_change_from_previous": frame.get(
            "visual_change_from_previous", ""
        ),
        "information_change": frame.get(
            "information_change", "UNCERTAIN"
        ),
        "pyscenedetect_reasons": mf.get("reasons", []),
        "pixel_difference_signal": pixel_difference_signal,
    }


def build_prompt(
    *,
    case_id: str,
    context_frame: dict[str, Any] | None,
    primary_frames: list[dict[str, Any]],
    speech_evidence_status: str = "detected",
) -> str:
    expected_ids = [x["frame_id"] for x in primary_frames]

    context_text = (
        json.dumps(context_frame, ensure_ascii=False)
        if context_frame is not None
        else "NONE (this is the beginning of the video)"
    )

    case_context = f"Case ID: {case_id}"
    if speech_evidence_status != "detected":
        case_context += (
            f"\nSpeech evidence status: {speech_evidence_status}\n\n"
            "`not_detected` 只表示 ASR 未检测到可用语音证据；"
            "不得从 OCR 或画面补造旁白。"
        )

    return f"""
你正在做短视频“真实视觉 Shot Boundary 选择”。

{case_context}

你看到的是已经按真实时间排序的视觉 Observation。
你不看原视频像素，只基于这些机器 Observation 判断：
“当前 PRIMARY 帧之前，是否已经发生了新的连续视觉镜头切换？”

CONTEXT_ONLY（只用于比较，不输出）：
{context_text}

PRIMARY：
{json.dumps(primary_frames, ensure_ascii=False)}

允许输出的 frame_id 恰好只有：
{json.dumps(expected_ids, ensure_ascii=False)}

【Shot Boundary 定义】

boundary_before=true：
当前帧已经属于新的连续视觉镜头，例如：
- 场景/地点明显切换；
- 摄像机视角或构图发生离散切换；
- 主体、背景或动作出现明显不连续；
- 从一个拍摄片段硬切到另一个拍摄片段。

boundary_before=false：
仍属于同一个连续拍摄，例如：
- 同一人物/物体的自然动作；
- 同机位连续运动；
- 相机连续移动；
- 仅字幕/OCR文字变化；
- 同一画面轻微抖动、缩放、曝光变化。

严格规则：

1. 你只能返回现有 frame_id；不得生成或修改时间戳。
2. CONTEXT_ONLY 永远不得出现在输出。
3. 必须恰好返回 {len(expected_ids)} 个 decisions，顺序与 PRIMARY 完全一致。
4. OCR/字幕变化本身绝不能构成 Shot Boundary。
5. Qwen 的 information_change 不是 Shot Boundary 真源，只能作为辅助信号。
6. PySceneDetect 只是辅助信号，可能漏检或误检。
7. 如果场景/人物/背景明显不连续，即使 PySceneDetect 没标记，也应 boundary_before=true。
8. 不判断 Hook、Proof、Pattern、CTA 或商业效果。
9. 不判断人物真实身份、职业、店铺归属。
10. 对于不确定是否发生真实切镜的情况，reason_type=uncertain，并给 low/medium confidence。
11. 如果这是整条视频第一帧，必须 boundary_before=true，reason_type=video_start。

reason_type 只能使用：
- video_start
- same_shot_motion
- text_overlay_change_only
- scene_or_location_change
- camera_view_change
- subject_or_action_discontinuity
- uncertain

只输出 JSON：
{{
  "decisions": [
    {{
      "frame_id": "来自允许列表",
      "boundary_before": true,
      "reason_type": "scene_or_location_change",
      "reason": "一句简短说明，只描述相邻视觉 Observation 的变化",
      "confidence": "high|medium|low"
    }}
  ]
}}
""".strip()


def main() -> None:
    total_started = time.perf_counter()

    parser = argparse.ArgumentParser(
        description=(
            "Chunked/resumable Shot Boundary selection for long videos. "
            "DeepSeek selects only existing frame IDs; Python owns timestamps "
            "and projects every visual frame/audio word exactly once."
        )
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--visual-v1", required=True)
    parser.add_argument("--visual-manifest", required=True)
    parser.add_argument("--audio-v1", required=True)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--privacy-projection", required=True)
    parser.add_argument(
        "--decision-chunk-size",
        type=int,
        default=24,
        help="Primary visual observations per DeepSeek call. Default: 24.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Additional retries per invalid chunk. Default: 2.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--review-file",
        default=None,
        help=(
            "Optional explicit boundary review JSON. Review decisions are "
            "applied after model selection and before Shot construction. "
            "Raw model decisions remain unchanged for auditability."
        ),
    )
    parser.add_argument("--output-root", default=None)
    args = parser.parse_args()
    privacy_context = load_privacy_projection(
        args.privacy_projection,
        expected_case_id=args.case_id,
    )

    if args.decision_chunk_size < 4:
        raise ValueError("--decision-chunk-size must be >= 4")
    if args.max_retries < 0:
        raise ValueError("--max-retries must be >= 0")

    visual_path = Path(args.visual_v1).expanduser().resolve()
    manifest_path = Path(args.visual_manifest).expanduser().resolve()
    audio_path = Path(args.audio_v1).expanduser().resolve()

    for p in (visual_path, manifest_path, audio_path):
        if not p.exists():
            raise FileNotFoundError(p)

    visual = read_json(visual_path)
    manifest = read_json(manifest_path)
    audio = read_json(audio_path)

    for name, data in (
        ("visual_v1", visual),
        ("visual_manifest", manifest),
        ("audio_v1", audio),
    ):
        found = data.get("case_id")
        if found is not None and str(found) != args.case_id:
            raise RuntimeError(
                f"{name}.case_id={found!r} does not match {args.case_id!r}"
            )

    coverage = visual.get("coverage", {})
    if coverage.get("coverage_label") != "candidate_complete":
        raise RuntimeError(
            "visual_v1 must be candidate_complete before Shot Boundary."
        )

    if not audio.get("validation", {}).get("passed"):
        raise RuntimeError("audio_v1 validation is not passed.")

    frames = list(visual.get("frames") or [])
    words = list(audio.get("words") or [])
    speech_evidence_status = require_audio_speech_evidence(audio)

    review_data: dict[str, Any] | None = None
    review_path: Path | None = None
    review_actions_by_frame: dict[str, dict[str, Any]] = {}

    if args.review_file:
        review_path = Path(args.review_file).expanduser().resolve()
        if not review_path.exists():
            raise FileNotFoundError(review_path)

        review_data = read_json(review_path)

        review_case_id = str(review_data.get("case_id", ""))
        if review_case_id != args.case_id:
            raise RuntimeError(
                f"review_file.case_id={review_case_id!r} does not match "
                f"{args.case_id!r}"
            )

        decisions = review_data.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            raise RuntimeError(
                "review_file.decisions must be a non-empty array."
            )

        for item in decisions:
            if not isinstance(item, dict):
                raise RuntimeError(
                    "Each review decision must be a JSON object."
                )

            frame_id = str(item.get("frame_id", ""))
            action = str(item.get("action", "")).lower()

            if not frame_id:
                raise RuntimeError(
                    "Review decision missing frame_id."
                )
            if action not in {"keep", "reject"}:
                raise RuntimeError(
                    f"{frame_id}: review action must be keep or reject."
                )
            if frame_id in review_actions_by_frame:
                raise RuntimeError(
                    f"Duplicate review decision for {frame_id}."
                )

            review_actions_by_frame[frame_id] = {
                **item,
                "frame_id": frame_id,
                "action": action,
            }

    if not frames:
        raise RuntimeError("visual_v1 contains no frames.")

    manifest_by_id = {
        str(x["filename"]): x
        for x in (manifest.get("frames") or [])
    }

    compact_frames = [
        compact_frame(frame, manifest_by_id)
        for frame in frames
    ]

    project_root = Path(__file__).resolve().parents[1]
    output_dir = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else project_root / "data" / "shots" / args.case_id / "shot_v1_1"
    )
    chunks_dir = output_dir / "boundary_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    total_chunks = (
        len(compact_frames) + args.decision_chunk_size - 1
    ) // args.decision_chunk_size

    client: OpenAI | None = None

    print(f"Tool version: {SCRIPT_VERSION}", flush=True)
    print(f"Case ID: {args.case_id}", flush=True)
    print(f"Visual observations: {len(compact_frames)}", flush=True)
    print(f"Audio words: {len(words)}", flush=True)
    print(f"Decision chunk size: {args.decision_chunk_size}", flush=True)
    print(f"Boundary chunks: {total_chunks}", flush=True)
    print(f"Model: {args.model}", flush=True)
    print(flush=True)

    all_decisions: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []

    for chunk_no, start in enumerate(
        range(0, len(compact_frames), args.decision_chunk_size),
        start=1,
    ):
        primary = compact_frames[
            start : start + args.decision_chunk_size
        ]
        context = compact_frames[start - 1] if start > 0 else None
        expected_ids = [x["frame_id"] for x in primary]
        safe_input, prompt, egress_audit = prepare_boundary_egress(
            case_id=args.case_id,
            context_frame=context,
            primary_frames=primary,
            privacy_context=privacy_context,
            speech_evidence_status=speech_evidence_status,
        )

        cache_path = chunks_dir / f"boundary_chunk_{chunk_no:03d}.json"
        raw_path = chunks_dir / f"boundary_chunk_{chunk_no:03d}_raw.json"

        if cache_path.exists() and not args.force:
            cached = read_json(cache_path)
            meta = cached.get("chunk", {})

            profile_matches = (
                str(meta.get("model")) == str(args.model)
                and int(meta.get("decision_chunk_size") or 0)
                == args.decision_chunk_size
                and str(meta.get("prompt_version")) == PROMPT_VERSION
                and all(
                    meta.get(key) == value
                    for key, value in egress_audit.items()
                )
            )

            if profile_matches:
                try:
                    cached_decisions, _ = sanitize_decisions(
                        {"decisions": cached.get("decisions", [])},
                        expected_ids,
                    )
                except Exception as exc:
                    print(
                        f"[{chunk_no}/{total_chunks}] Cached chunk invalid -> rerun: {exc}",
                        flush=True,
                    )
                else:
                    print(
                        f"[{chunk_no}/{total_chunks}] "
                        f"SKIP validated cached boundary chunk "
                        f"({len(cached_decisions)} decisions)",
                        flush=True,
                    )
                    all_decisions.extend(cached_decisions)
                    chunk_records.append(meta)
                    continue

        success = False
        last_error: Exception | None = None
        final_decisions: list[dict[str, Any]] = []
        final_warnings: list[str] = []
        elapsed_total = 0.0
        response_usage: dict[str, Any] = {}
        post_call_egress_audit_passed = False

        for attempt in range(1, args.max_retries + 2):
            print(
                f"[{chunk_no}/{total_chunks}] START "
                f"attempt {attempt}/{args.max_retries + 1} "
                f"({len(primary)} primary"
                + (" + 1 context" if context is not None else "")
                + ")",
                flush=True,
            )

            started = time.perf_counter()
            def transport() -> Any:
                nonlocal client
                if client is None:
                    client = get_client()
                return client.chat.completions.create(
                    model=args.model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=12000,
                    extra_body={"thinking": {"type": "disabled"}},
                )

            response, post_call_audit = invoke_boundary_transport(
                safe_input=safe_input,
                rendered_prompt=prompt,
                privacy_context=privacy_context,
                pre_call_audit=egress_audit,
                transport=transport,
            )
            post_call_egress_audit_passed = (
                post_call_audit == egress_audit
            )

            elapsed = time.perf_counter() - started
            elapsed_total += elapsed
            response_usage = usage_dict(response)

            content = response.choices[0].message.content
            if not content:
                last_error = RuntimeError("DeepSeek returned empty content.")
                print(
                    f"[{chunk_no}/{total_chunks}] INVALID "
                    f"attempt {attempt} elapsed={elapsed:.2f}s: empty content",
                    flush=True,
                )
                continue

            raw_path.write_text(content, encoding="utf-8")

            try:
                payload = json.loads(content)
                decisions, warnings = sanitize_decisions(
                    payload,
                    expected_ids,
                )
            except Exception as exc:
                last_error = exc
                print(
                    f"[{chunk_no}/{total_chunks}] INVALID "
                    f"attempt {attempt} elapsed={elapsed:.2f}s: {exc}",
                    flush=True,
                )
                continue

            final_decisions = decisions
            final_warnings = warnings
            success = True

            print(
                f"[{chunk_no}/{total_chunks}] PASS "
                f"attempt {attempt} elapsed={elapsed:.2f}s "
                f"tokens={response_usage.get('total_tokens')}",
                flush=True,
            )
            break

        if not success:
            raise RuntimeError(
                f"Boundary chunk {chunk_no} failed after "
                f"{args.max_retries + 1} attempts: {last_error}"
            )

        if start == 0:
            final_decisions[0]["boundary_before"] = True
            final_decisions[0]["reason_type"] = "video_start"
            final_decisions[0]["reason"] = "整条视频第一帧。"
            final_decisions[0]["confidence"] = "high"

        chunk_record = {
            "chunk_id": f"B{chunk_no:03d}",
            "model": args.model,
            "decision_chunk_size": args.decision_chunk_size,
            "prompt_version": PROMPT_VERSION,
            "input_content_hash": egress_audit["safe_input_sha256"],
            "primary_frame_ids": expected_ids,
            "context_frame_id": (
                context["frame_id"] if context is not None else None
            ),
            "elapsed_seconds": round(elapsed_total, 6),
            "attempts_used": attempt,
            "usage": response_usage,
            "sanitization_warnings": final_warnings,
            "status": "success",
            "post_call_egress_audit_passed": (
                post_call_egress_audit_passed
            ),
            **egress_audit,
        }

        cache_path.write_text(
            json.dumps(
                {
                    "chunk": chunk_record,
                    "decisions": final_decisions,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        all_decisions.extend(final_decisions)
        chunk_records.append(chunk_record)

    expected_all_ids = [x["frame_id"] for x in compact_frames]
    returned_all_ids = [str(x["frame_id"]) for x in all_decisions]

    if returned_all_ids != expected_all_ids:
        raise RuntimeError(
            "Global boundary decision frame IDs/order mismatch."
        )

    frame_by_id = {
        x["frame_id"]: x for x in compact_frames
    }

    selected_boundaries: list[dict[str, Any]] = []
    manual_review_items: list[dict[str, Any]] = []
    applied_review_decisions: list[dict[str, Any]] = []
    effective_boundary_decisions: list[dict[str, Any]] = []

    model_selected_ids = {
        str(d["frame_id"])
        for d in all_decisions
        if d.get("boundary_before") is True
    }

    unknown_review_targets = [
        frame_id
        for frame_id in review_actions_by_frame
        if frame_id not in model_selected_ids
    ]
    if unknown_review_targets:
        raise RuntimeError(
            "Review file targets frame IDs that are not currently selected "
            "model boundaries: " + ", ".join(unknown_review_targets)
        )

    for decision in all_decisions:
        frame_id = str(decision["frame_id"])
        frame = frame_by_id[frame_id]
        model_boundary = bool(decision["boundary_before"])
        review_item = review_actions_by_frame.get(frame_id)

        effective_boundary = model_boundary
        review_action = None

        if review_item is not None:
            review_action = review_item["action"]

            if review_action == "reject":
                effective_boundary = False
            elif review_action == "keep":
                effective_boundary = True

            applied_review_decisions.append(
                {
                    "frame_id": frame_id,
                    "timestamp_seconds": frame["timestamp_seconds"],
                    "model_boundary_before": model_boundary,
                    "action": review_action,
                    "effective_boundary_before": effective_boundary,
                    "reason": review_item.get("reason", ""),
                    "evidence_frame_refs": review_item.get(
                        "evidence_frame_refs", []
                    ),
                }
            )

        effective_boundary_decisions.append(
            {
                **decision,
                "timestamp_seconds": frame["timestamp_seconds"],
                "model_boundary_before": model_boundary,
                "review_action": review_action,
                "effective_boundary_before": effective_boundary,
            }
        )

        # Review gating is computed after Shots are built so selected
        # non-high-confidence boundaries and very short Shots can both be
        # surfaced without changing unresolved model decisions.

        if effective_boundary:
            selected_boundaries.append(
                {
                    "frame_id": frame_id,
                    "timestamp_seconds": frame["timestamp_seconds"],
                    "reason_type": decision["reason_type"],
                    "reason": decision.get("reason", ""),
                    "confidence": decision["confidence"],
                    "review_action": review_action,
                }
            )

    if not selected_boundaries:
        raise RuntimeError("No Shot Boundary selected.")

    if abs(float(selected_boundaries[0]["timestamp_seconds"])) > 1e-9:
        raise RuntimeError("First Shot Boundary must be at 0.0s.")

    boundary_times: list[float] = []
    boundary_by_time: dict[float, dict[str, Any]] = {}

    for item in selected_boundaries:
        ts = float(item["timestamp_seconds"])
        if ts not in boundary_by_time:
            boundary_times.append(ts)
            boundary_by_time[ts] = item

    durations = [
        float(x)
        for x in (
            manifest.get("duration_seconds"),
            audio.get("duration_seconds"),
        )
        if x is not None
    ]
    if not durations:
        raise RuntimeError("Could not determine source duration.")
    video_duration = max(durations)

    shots: list[dict[str, Any]] = []
    assigned_frame_ids: list[str] = []
    assigned_word_ids: list[str] = []

    for index, shot_start in enumerate(boundary_times, start=1):
        shot_end = (
            boundary_times[index]
            if index < len(boundary_times)
            else video_duration
        )
        is_last = index == len(boundary_times)

        shot_frames = [
            frame for frame in frames
            if belongs(
                float(frame["timestamp_seconds"]),
                shot_start,
                shot_end,
                is_last,
            )
        ]

        shot_words = [
            word for word in words
            if belongs(
                word_midpoint(word),
                shot_start,
                shot_end,
                is_last,
            )
        ]

        assigned_frame_ids.extend(
            str(x["frame_id"]) for x in shot_frames
        )
        assigned_word_ids.extend(
            str(x["word_id"]) for x in shot_words
        )

        information_states: list[dict[str, Any]] = []
        previous_ocr_norm: str | None = None

        for frame in shot_frames:
            ocr = str(frame.get("ocr_raw") or "")
            ocr_norm = "".join(ocr.split())

            ocr_changed = (
                previous_ocr_norm is None
                or ocr_norm != previous_ocr_norm
            )
            model_info_changed = (
                frame.get("information_change") == "YES"
            )

            if (
                not information_states
                or ocr_changed
                or model_info_changed
            ):
                triggers = []
                if not information_states:
                    triggers.append("shot_start")
                if ocr_changed:
                    triggers.append("ocr_change")
                if model_info_changed:
                    triggers.append("model_information_change")

                information_states.append(
                    {
                        "frame_ref": frame["frame_id"],
                        "timestamp_seconds": float(
                            frame["timestamp_seconds"]
                        ),
                        "ocr_raw": ocr,
                        "scene_summary": frame.get(
                            "scene_summary", ""
                        ),
                        "trigger": triggers,
                    }
                )

            previous_ocr_norm = ocr_norm

        start_boundary = boundary_by_time[shot_start]

        shots.append(
            {
                "shot_id": f"S{index:03d}",
                "start": round(shot_start, 6),
                "end": round(shot_end, 6),
                "duration": round(shot_end - shot_start, 6),
                "boundary": {
                    "selected_from_frame_ref": start_boundary["frame_id"],
                    "candidate_timestamp_seconds": shot_start,
                    "selector": args.model,
                    "selection_mode": "chunked_text_semantic",
                    "reason_type": start_boundary["reason_type"],
                    "reason": start_boundary["reason"],
                    "confidence": start_boundary["confidence"],
                    "review_action": start_boundary.get("review_action"),
                    "timestamp_authority": "visual_candidate_frame",
                    "precision_note": (
                        "Selected existing visual-candidate timestamp; Case-analysis grade, not editing-frame exact."
                    ),
                },
                "audio_projection": {
                    "policy": "word_midpoint_exactly_once",
                    "speech_evidence_status": speech_evidence_status,
                    "word_refs": [x["word_id"] for x in shot_words],
                    "segment_refs": uniq(
                        [
                            str(x["segment_id"])
                            for x in shot_words
                            if x.get("segment_id")
                        ]
                    ),
                    "voiceover_exact": "".join(
                        str(x.get("text", ""))
                        for x in shot_words
                    ),
                },
                "visual_projection": {
                    "frame_refs": [x["frame_id"] for x in shot_frames],
                    "information_states": information_states,
                },
                "interpretation": None,
            }
        )

    # Final review gate.
    # PySceneDetect remains advisory only. It never moves a semantic
    # boundary timestamp. The selected existing visual frame remains the
    # current Case-analysis timing authority.
    manual_review_items = []

    for boundary in selected_boundaries:
        if (
            boundary.get("confidence") != "high"
            and boundary.get("review_action") != "keep"
        ):
            manual_review_items.append(
                {
                    "type": "selected_non_high_confidence_boundary",
                    "frame_id": boundary["frame_id"],
                    "timestamp_seconds": boundary["timestamp_seconds"],
                    "confidence": boundary["confidence"],
                    "reason_type": boundary["reason_type"],
                    "reason": boundary.get("reason", ""),
                }
            )

    for index, shot in enumerate(shots):
        item = short_shot_review_item(shots, index)
        if item is not None:
            manual_review_items.append(item)

    expected_frame_ids = [str(x["frame_id"]) for x in frames]
    expected_word_ids = [str(x["word_id"]) for x in words]

    if assigned_frame_ids != expected_frame_ids:
        raise RuntimeError(
            "Visual frame exact-once/order projection failed."
        )

    if assigned_word_ids != expected_word_ids:
        raise RuntimeError(
            "Audio word exact-once/order projection failed."
        )

    total_elapsed = time.perf_counter() - total_started

    result = {
        "schema_version": SCHEMA_VERSION,
        "tool_version": SCRIPT_VERSION,
        "case_id": args.case_id,
        "duration_seconds": video_duration,
        "speech_evidence_status": speech_evidence_status,
        "design_decision": {
            "shot_boundary_definition": (
                "Shot = continuous visual camera segment. "
                "Text/OCR changes alone do not create new Shots."
            ),
            "boundary_candidate_source": "existing_visual_candidate_frames",
            "boundary_selector": args.model,
            "boundary_selector_mode": "chunked_resumable",
            "decision_chunk_size": args.decision_chunk_size,
            "detector_role": (
                "advisory_candidate_generation_only; never rewrites "
                "semantic boundary timestamps"
            ),
            "review_override_policy": (
                "explicit review file may keep/reject selected model "
                "boundaries; raw model decisions remain immutable"
            ),
            "model_cannot_invent_timestamps": True,
            "audio_projection": "word_midpoint_exactly_once",
            "current_boundary_precision": "candidate_frame_approximate",
        },
        "boundary_decisions": [
            {
                **decision,
                "timestamp_seconds": frame_by_id[
                    str(decision["frame_id"])
                ]["timestamp_seconds"],
            }
            for decision in all_decisions
        ],
        "effective_boundary_decisions": effective_boundary_decisions,
        "boundary_review": {
            "applied": bool(applied_review_decisions),
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
            "applied_count": len(applied_review_decisions),
            "decisions": applied_review_decisions,
        },
        "selected_boundaries": selected_boundaries,
        "shots": shots,
        "boundary_chunks": chunk_records,
        "manual_review": {
            "required": bool(manual_review_items),
            "item_count": len(manual_review_items),
            "items": manual_review_items,
        },
        "timing": {
            "deepseek_boundary_selection_seconds": round(
                sum(
                    float(x.get("elapsed_seconds") or 0)
                    for x in chunk_records
                ),
                6,
            ),
            "total_elapsed_seconds": round(total_elapsed, 6),
        },
        "validation": {
            "passed": True,
            "visual_frame_count": len(frames),
            "audio_word_count": len(words),
            "speech_evidence_status": speech_evidence_status,
            "boundary_decision_count": len(all_decisions),
            "shot_count": len(shots),
            "review_decisions_applied": len(applied_review_decisions),
            "all_visual_frames_assigned_exactly_once": True,
            "all_audio_words_assigned_exactly_once": True,
            "frame_order_preserved": True,
            "word_order_preserved": True,
            "no_model_generated_timestamps": True,
        },
    }

    output_json = output_dir / "shot_boundaries_v1_1.json"
    output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = [
        "# Shot Boundaries V1.4",
        "",
        f"- Case ID: `{args.case_id}`",
        f"- Duration: `{video_duration:.3f}s`",
        f"- Visual observations: `{len(frames)}`",
        f"- Audio words: `{len(words)}`",
        f"- Boundary chunks: `{total_chunks}`",
        f"- Selected Shots: `{len(shots)}`",
        f"- Review decisions applied: `{len(applied_review_decisions)}`",
        f"- Manual review required: `{bool(manual_review_items)}`",
        f"- DeepSeek boundary time: `{result['timing']['deepseek_boundary_selection_seconds']:.2f}s`",
        f"- Total stage time: `{total_elapsed:.2f}s`",
        "",
        "| Shot | 时间 | 时长 | Audio Words | Visual Frames | Boundary Reason |",
        "|---|---|---:|---:|---:|---|",
    ]

    for shot in shots:
        summary.append(
            f"| {shot['shot_id']} | "
            f"{shot['start']:.3f}–{shot['end']:.3f}s | "
            f"{shot['duration']:.3f}s | "
            f"{len(shot['audio_projection']['word_refs'])} | "
            f"{len(shot['visual_projection']['frame_refs'])} | "
            f"{shot['boundary']['reason_type']} |"
        )

    if applied_review_decisions:
        summary += ["", "## Applied Boundary Review Decisions", ""]

        for item in applied_review_decisions:
            summary.append(
                f"- `{item['frame_id']}` @ "
                f"{float(item['timestamp_seconds']):.3f}s — "
                f"{item['action']} — "
                f"{item.get('reason', '')}"
            )

    if manual_review_items:
        summary += ["", "## Manual Review Candidates", ""]

        for item in manual_review_items:
            item_type = item.get("type")

            if item_type == "selected_non_high_confidence_boundary":
                summary.append(
                    f"- **Non-high-confidence boundary** — "
                    f"`{item['frame_id']}` @ "
                    f"{float(item['timestamp_seconds']):.3f}s — "
                    f"{item.get('reason_type', 'unknown')} / "
                    f"{item.get('confidence', 'unknown')} — "
                    f"{item.get('reason', '')}"
                )

            elif item_type == "short_shot":
                summary.append(
                    f"- **Short shot** — "
                    f"`{item['shot_id']}` "
                    f"{float(item['start']):.3f}–"
                    f"{float(item['end']):.3f}s "
                    f"({float(item['duration']):.3f}s) — "
                    f"boundary frame "
                    f"`{item.get('boundary_frame_id', 'unknown')}`"
                )

            else:
                # Forward-compatible fallback: never crash the stage merely
                # because a future review-item type has a different shape.
                summary.append(
                    "- **Review item** — "
                    + json.dumps(item, ensure_ascii=False, sort_keys=True)
                )

    summary_path = output_dir / "shot_boundaries_v1_1_summary.md"
    summary_path.write_text(
        "\n".join(summary),
        encoding="utf-8",
    )

    print()
    print("SHOT BOUNDARY V1.4 PASS", flush=True)
    print(f"Case ID: {args.case_id}", flush=True)
    print(f"Boundary chunks: {total_chunks}", flush=True)
    print(f"Visual decisions: {len(all_decisions)}", flush=True)
    print(f"Selected shots: {len(shots)}", flush=True)
    print(
        f"Boundary review decisions applied: "
        f"{len(applied_review_decisions)}",
        flush=True,
    )
    print(
        f"Visual frames assigned exactly once: {len(frames)}",
        flush=True,
    )
    print(
        f"Audio words assigned exactly once: {len(words)}",
        flush=True,
    )
    print(
        f"Manual review required: {bool(manual_review_items)} "
        f"({len(manual_review_items)} items)",
        flush=True,
    )
    print(
        f"DeepSeek boundary selection: "
        f"{result['timing']['deepseek_boundary_selection_seconds']:.2f}s",
        flush=True,
    )
    print(f"Total elapsed: {total_elapsed:.2f}s", flush=True)
    print(f"JSON: {output_json}", flush=True)
    print(f"Summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
