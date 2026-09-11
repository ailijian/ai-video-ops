from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import cv2
from ollama import chat

SCRIPT_VERSION = "analyze_visual_timeline_v1.py@1.5"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    return json.loads(text)


def normalize_timestamp(item: dict[str, Any]) -> float:
    value = item.get("timestamp_seconds")
    if value is None:
        value = item.get("timestamp")
    return float(value)


def sanitize_chunk_result(result: dict[str, Any], expected_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    frames = result.get("frames")
    if not isinstance(frames, list):
        raise RuntimeError("Model JSON does not contain a 'frames' array.")

    returned_ids = [str(x.get("frame_id")) for x in frames]
    expected_set = set(expected_ids)

    duplicates = [fid for fid in expected_ids if returned_ids.count(fid) > 1]
    if duplicates:
        raise RuntimeError("Expected frame IDs duplicated: " + ", ".join(duplicates))

    filtered = [x for x in frames if str(x.get("frame_id")) in expected_set]
    filtered_ids = [str(x.get("frame_id")) for x in filtered]

    missing = [fid for fid in expected_ids if fid not in filtered_ids]
    if missing:
        raise RuntimeError("Expected frame IDs missing: " + ", ".join(missing))

    if filtered_ids != expected_ids:
        raise RuntimeError(
            "Expected frame order mismatch after removing unexpected IDs.\n"
            f"Expected: {expected_ids}\nFiltered: {filtered_ids}\nRaw returned: {returned_ids}"
        )

    warnings: list[str] = []
    unexpected = [fid for fid in returned_ids if fid not in expected_set]
    if unexpected:
        warnings.append("Dropped unexpected model-generated frame IDs: " + ", ".join(unexpected))

    for item in filtered:
        fid = str(item.get("frame_id"))
        if item.get("information_change") not in {"YES", "NO", "UNCERTAIN"}:
            raise RuntimeError(f"Invalid information_change for {fid}: {item.get('information_change')!r}")
        for key in ("visible_facts", "new_visual_information", "uncertainties"):
            if not isinstance(item.get(key, []), list):
                raise RuntimeError(f"{key} must be an array for {fid}")

    return filtered, warnings


def normalize_frames_to_manifest(frames_output: list[dict[str, Any]], primary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest_by_id = {str(x["filename"]): x for x in primary}
    for frame in frames_output:
        source = manifest_by_id[str(frame["frame_id"])]
        model_ts = frame.get("timestamp_seconds")
        true_ts = normalize_timestamp(source)
        frame["model_reported_timestamp_seconds"] = model_ts
        frame["timestamp_seconds"] = true_ts
        frame["timestamp_authority"] = "visual_manifest"
        frame["observation_authority"] = "qwen3-vl"
    return frames_output


def try_recover_raw(raw_path: Path, expected_ids: list[str], primary: list[dict[str, Any]]):
    if not raw_path.exists():
        return None
    try:
        parsed = parse_json_content(raw_path.read_text(encoding="utf-8"))
        frames, warnings = sanitize_chunk_result(parsed, expected_ids)
        frames = normalize_frames_to_manifest(frames, primary)
        return frames, warnings
    except Exception:
        return None



def image_shape(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Unable to read image: {path}")
    h, w = image.shape[:2]
    return w, h


def ensure_proxy(source: Path, proxy: Path, max_edge: int) -> Path:
    if proxy.exists():
        return proxy

    image = cv2.imread(str(source))
    if image is None:
        raise RuntimeError(f"Unable to read image: {source}")

    h, w = image.shape[:2]
    longest = max(w, h)

    if longest <= max_edge:
        resized = image
    else:
        scale = max_edge / longest
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(
            image,
            (new_w, new_h),
            interpolation=cv2.INTER_AREA,
        )

    proxy.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(
        str(proxy),
        resized,
        [int(cv2.IMWRITE_JPEG_QUALITY), 90],
    )
    if not ok:
        raise RuntimeError(f"Failed to write proxy image: {proxy}")

    return proxy


def run_proxy_probe(
    *,
    case_id: str,
    candidates: list[dict[str, Any]],
    frames_dir: Path,
    output_dir: Path,
    chunk_no: int,
    chunk_size: int,
    max_image_edge: int,
    model: str,
    num_ctx: int,
    max_retries: int,
) -> None:
    total_chunks = (len(candidates) + chunk_size - 1) // chunk_size
    if chunk_no < 1 or chunk_no > total_chunks:
        raise ValueError(
            f"--only-chunk {chunk_no} outside 1..{total_chunks}"
        )

    start = (chunk_no - 1) * chunk_size
    primary = candidates[start:start + chunk_size]
    context_frame = candidates[start - 1] if start > 0 else None
    expected_ids = [str(x["filename"]) for x in primary]

    proxy_dir = (
        output_dir
        / "proxies"
        / f"edge_{max_image_edge}"
        / "frames"
    )
    diagnostics_dir = output_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    image_items: list[tuple[str, Path, float, str]] = []
    source_paths: list[Path] = []
    analysis_paths: list[Path] = []

    ordered = []
    if context_frame is not None:
        ordered.append(("CONTEXT_ONLY", context_frame))
    ordered.extend(("PRIMARY", x) for x in primary)

    for role, item in ordered:
        source = frames_dir / str(item["filename"])
        proxy = proxy_dir / str(item["filename"])
        analysis = ensure_proxy(source, proxy, max_image_edge)
        source_paths.append(source)
        analysis_paths.append(analysis)
        image_items.append(
            (
                role,
                analysis,
                normalize_timestamp(item),
                str(item["filename"]),
            )
        )

    mapping = "\\n".join(
        f"- {fid} | {ts:.3f}s | {role}"
        for role, _, ts, fid in image_items
    )
    allowed = json.dumps(expected_ids, ensure_ascii=False)

    prompt = f"""
你正在分析一个短视频的连续视觉证据帧。
Case ID: {case_id}

所有图片已按时间顺序输入。

图片映射：
{mapping}

本次 PRIMARY 恰好 {len(expected_ids)} 张。
必须恰好返回 {len(expected_ids)} 个结果。
只允许输出这些 frame_id：
{allowed}

规则：
1. CONTEXT_ONLY 只用于比较，不得输出。
2. 每张 PRIMARY 必须输出且仅输出一次。
3. 不得创建、猜测或补全不存在的 frame_id。
4. frame_id 必须逐字复制允许列表。
5. 输出顺序必须与允许列表完全一致。
6. 这里只做 Evidence Observation，不做 Hook、Pattern、Proof、CTA 或商业效果判断。
7. 不推断人物真实身份、职业、店铺归属、商业成功或因果关系。
8. OCR 尽量逐字保留，不润色。
9. information_change 判断观看者是否获得新的视觉信息，而不是像素是否变化。
10. 不确定时使用 UNCERTAIN。

只输出 JSON：
{{
  "frames": [
    {{
      "frame_id": "必须来自允许列表",
      "timestamp_seconds": 0.0,
      "ocr_raw": "",
      "visible_facts": [],
      "scene_summary": "",
      "visual_change_from_previous": "",
      "information_change": "YES|NO|UNCERTAIN",
      "new_visual_information": [],
      "uncertainties": [],
      "confidence": {{
        "ocr": "high|medium|low",
        "observation": "high|medium|low"
      }}
    }}
  ]
}}
""".strip()

    image_paths = [str(x[1]) for x in image_items]
    attempts_total = 1 + max_retries
    total_qwen_elapsed = 0.0
    last_error: Exception | None = None
    last_raw = ""

    print(
        f"PROXY PROBE chunk {chunk_no}/{total_chunks}",
        flush=True,
    )
    print(
        f"Max image edge: {max_image_edge}",
        flush=True,
    )
    print(
        f"Context: {num_ctx}",
        flush=True,
    )
    print(
        f"Original first image: {image_shape(source_paths[0])}",
        flush=True,
    )
    print(
        f"Analysis first image: {image_shape(analysis_paths[0])}",
        flush=True,
    )

    for attempt in range(1, attempts_total + 1):
        print(
            f"[{chunk_no}/{total_chunks}] PROBE START "
            f"attempt {attempt}/{attempts_total}",
            flush=True,
        )
        started = time.perf_counter()

        response = chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                    "images": image_paths,
                }
            ],
            format="json",
            options={
                "temperature": 0,
                "num_ctx": num_ctx,
                "num_predict": 6000,
            },
            keep_alive=0,
        )

        elapsed = time.perf_counter() - started
        total_qwen_elapsed += elapsed
        response_metrics = ollama_response_metrics(response)
        last_raw = response.message.content or ""

        try:
            parsed = parse_json_content(last_raw)
            frames_output, warnings = sanitize_chunk_result(
                parsed,
                expected_ids,
            )
            frames_output = normalize_frames_to_manifest(
                frames_output,
                primary,
            )
        except Exception as exc:
            last_error = exc
            print(
                f"[{chunk_no}/{total_chunks}] PROBE INVALID "
                f"elapsed={elapsed:.2f}s: {exc}",
                flush=True,
            )
            continue

        result = {
            "mode": "proxy_benchmark",
            "tool_version": SCRIPT_VERSION,
            "case_id": case_id,
            "chunk_no": chunk_no,
            "chunk_size": chunk_size,
            "model": model,
            "num_ctx": num_ctx,
            "max_image_edge": max_image_edge,
            "expected_frame_ids": expected_ids,
            "qwen_elapsed_seconds": round(total_qwen_elapsed, 6),
            "ollama_response_metrics": response_metrics,
            "attempts_used": attempt,
            "sanitization_warnings": warnings,
            "original_image_sizes": [
                image_shape(x) for x in source_paths
            ],
            "analysis_image_sizes": [
                image_shape(x) for x in analysis_paths
            ],
            "frames": frames_output,
        }

        stem = (
            f"chunk_{chunk_no:03d}"
            f"_edge{max_image_edge}"
            f"_ctx{num_ctx}"
        )
        result_path = diagnostics_dir / f"{stem}.json"
        raw_path = diagnostics_dir / f"{stem}_raw.txt"

        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raw_path.write_text(last_raw, encoding="utf-8")

        print(
            f"[{chunk_no}/{total_chunks}] PROBE PASS "
            f"elapsed={total_qwen_elapsed:.2f}s "
            f"({total_qwen_elapsed / 60:.2f} min)",
            flush=True,
        )
        print(
            "OLLAMA "
            f"load={response_metrics.get('load_duration_seconds')}s "
            f"prompt_eval={response_metrics.get('prompt_eval_duration_seconds')}s "
            f"prompt_tokens={response_metrics.get('prompt_eval_count')} "
            f"eval={response_metrics.get('eval_duration_seconds')}s "
            f"eval_tokens={response_metrics.get('eval_count')} "
            f"total={response_metrics.get('total_duration_seconds')}s",
            flush=True,
        )
        for warning in warnings:
            print(
                f"PROBE WARNING: {warning}",
                flush=True,
            )
        print(
            f"Diagnostic JSON: {result_path}",
            flush=True,
        )
        return

    raise RuntimeError(
        f"Proxy probe failed after {attempts_total} attempts: {last_error}"
    )



def ollama_response_metrics(response: Any) -> dict[str, Any]:
    """Extract Ollama timing/token metrics. Duration fields are nanoseconds."""
    def get(name: str) -> Any:
        try:
            return getattr(response, name)
        except Exception:
            return None

    def sec(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value) / 1_000_000_000, 6)
        except Exception:
            return None

    return {
        "total_duration_seconds": sec(get("total_duration")),
        "load_duration_seconds": sec(get("load_duration")),
        "prompt_eval_count": get("prompt_eval_count"),
        "prompt_eval_duration_seconds": sec(get("prompt_eval_duration")),
        "eval_count": get("eval_count"),
        "eval_duration_seconds": sec(get("eval_duration")),
        "done_reason": get("done_reason"),
    }


def main() -> None:
    run_started = time.perf_counter()
    parser = argparse.ArgumentParser(description="Chunked Qwen visual analysis with cache resume, raw recovery, retries, and timing.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--model", default="qwen3-vl:4b-instruct")
    parser.add_argument("--chunk-size", type=int, default=6)
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--max-new-chunks", type=int, default=None)
    parser.add_argument("--max-image-edge", type=int, default=None)
    parser.add_argument("--only-chunk", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.max_image_edge is not None and args.max_image_edge < 256:
        raise ValueError("--max-image-edge must be >= 256")

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = read_json(manifest_path)
    case_id = str(manifest.get("case_id") or manifest_path.parent.name)
    case_dir = manifest_path.parent
    frames_dir = case_dir / "frames"
    candidates = sorted(list(manifest.get("frames") or []), key=normalize_timestamp)
    if not candidates:
        raise RuntimeError("No candidate frames found in visual manifest.")

    for item in candidates:
        image_path = frames_dir / item["filename"]
        if not image_path.exists():
            raise FileNotFoundError(image_path)

    output_dir = case_dir / "visual_v1"
    chunks_dir = output_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    proxy_frames_dir = None
    if args.max_image_edge is not None:
        proxy_frames_dir = (
            output_dir
            / "proxies"
            / f"edge_{args.max_image_edge}"
            / "frames"
        )

    all_results: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []
    total_chunks = (len(candidates) + args.chunk_size - 1) // args.chunk_size

    print(f"Tool version: {SCRIPT_VERSION}", flush=True)
    print(f"Case ID: {case_id}", flush=True)
    print(f"Candidate frames: {len(candidates)}", flush=True)
    print(f"Chunk size: {args.chunk_size}", flush=True)
    print(f"Total chunks: {total_chunks}", flush=True)
    print(f"Model: {args.model}", flush=True)
    print(f"Context: {args.num_ctx}", flush=True)
    print(
        f"Analysis image max edge: "
        f"{args.max_image_edge if args.max_image_edge is not None else 'original'}",
        flush=True,
    )
    print(f"Max retries: {args.max_retries}", flush=True)
    if args.max_new_chunks is not None:
        print(f"Diagnostic max new chunks: {args.max_new_chunks}", flush=True)
    print(flush=True)

    if args.only_chunk is not None:
        if args.max_image_edge is None:
            raise ValueError(
                "--only-chunk diagnostic mode requires --max-image-edge."
            )
        run_proxy_probe(
            case_id=case_id,
            candidates=candidates,
            frames_dir=frames_dir,
            output_dir=output_dir,
            chunk_no=args.only_chunk,
            chunk_size=args.chunk_size,
            max_image_edge=args.max_image_edge,
            model=args.model,
            num_ctx=args.num_ctx,
            max_retries=args.max_retries,
        )
        return

    new_chunks_completed = 0

    for chunk_no, start in enumerate(range(0, len(candidates), args.chunk_size), start=1):
        primary = candidates[start:start + args.chunk_size]
        context_frame = candidates[start - 1] if start > 0 else None
        expected_ids = [str(x["filename"]) for x in primary]
        chunk_json_path = chunks_dir / f"chunk_{chunk_no:03d}.json"
        chunk_raw_path = chunks_dir / f"chunk_{chunk_no:03d}_raw.txt"

        if chunk_json_path.exists() and not args.force:
            cached = read_json(chunk_json_path)
            cached_meta = dict(cached.get("chunk", {}))

            cached_edge = cached_meta.get("analysis_image_max_edge")
            cached_ctx = cached_meta.get("num_ctx")
            cached_model = cached_meta.get("model")

            profile_matches = (
                cached_edge == args.max_image_edge
                and int(cached_ctx or 0) == int(args.num_ctx)
                and str(cached_model or "") == str(args.model)
            )

            if not profile_matches:
                print(
                    f"[{chunk_no}/{total_chunks}] CACHE PROFILE MISMATCH "
                    f"(cached edge={cached_edge}, ctx={cached_ctx}, model={cached_model}; "
                    f"wanted edge={args.max_image_edge}, ctx={args.num_ctx}, model={args.model}) "
                    f"-> rerun",
                    flush=True,
                )
            else:
                try:
                    cached_frames, _ = sanitize_chunk_result(
                        cached["model_output"],
                        expected_ids,
                    )
                except Exception as exc:
                    print(
                        f"[{chunk_no}/{total_chunks}] Cached chunk invalid, "
                        f"re-running: {exc}",
                        flush=True,
                    )
                else:
                    print(
                        f"[{chunk_no}/{total_chunks}] "
                        f"SKIP validated cached chunk "
                        f"({len(cached_frames)} frames)",
                        flush=True,
                    )
                    all_results.extend(cached_frames)
                    chunk_records.append(cached_meta)
                    continue

        # Raw recovery is only safe for the original-image legacy profile.
        # Profile-specific proxy runs must never recover an unlabelled old raw response.
        if (
            not args.force
            and args.max_image_edge is None
            and not chunk_json_path.exists()
        ):
            recovered = try_recover_raw(chunk_raw_path, expected_ids, primary)
            if recovered is not None:
                frames_output, recovery_warnings = recovered
                chunk_record = {
                    "chunk_id": f"C{chunk_no:03d}",
                    "primary_frame_ids": expected_ids,
                    "context_frame_id": str(context_frame["filename"]) if context_frame else None,
                    "model": args.model,
                    "num_ctx": args.num_ctx,
                    "analysis_image_max_edge": None,
                    "status": "success",
                    "recovered_from_raw": True,
                    "qwen_elapsed_seconds": None,
                    "sanitization_warnings": recovery_warnings,
                }
                chunk_json_path.write_text(json.dumps({"chunk": chunk_record, "model_output": {"frames": frames_output}}, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"[{chunk_no}/{total_chunks}] RECOVER previous raw output -> {chunk_json_path.name}", flush=True)
                for warning in recovery_warnings:
                    print(f"[{chunk_no}/{total_chunks}] RECOVERY WARNING: {warning}", flush=True)
                all_results.extend(frames_output)
                chunk_records.append(chunk_record)
                continue

        image_items: list[tuple[str, Path, float, str]] = []
        original_image_sizes: list[tuple[int, int]] = []
        analysis_image_sizes: list[tuple[int, int]] = []

        ordered_items: list[tuple[str, dict[str, Any]]] = []
        if context_frame is not None:
            ordered_items.append(("CONTEXT_ONLY", context_frame))
        ordered_items.extend(("PRIMARY", item) for item in primary)

        for role, item in ordered_items:
            source_path = frames_dir / str(item["filename"])

            if args.max_image_edge is None:
                analysis_path = source_path
            else:
                assert proxy_frames_dir is not None
                proxy_path = proxy_frames_dir / str(item["filename"])
                analysis_path = ensure_proxy(
                    source_path,
                    proxy_path,
                    args.max_image_edge,
                )

            original_image_sizes.append(image_shape(source_path))
            analysis_image_sizes.append(image_shape(analysis_path))

            image_items.append(
                (
                    role,
                    analysis_path,
                    normalize_timestamp(item),
                    str(item["filename"]),
                )
            )

        mapping = "\n".join(
            f"- {fid} | {ts:.3f}s | {role}"
            for role, _, ts, fid in image_items
        )
        expected_ids_json = json.dumps(expected_ids, ensure_ascii=False)

        prompt = f"""
你正在分析一个短视频的连续视觉证据帧。
Case ID: {case_id}
所有图片已按时间顺序输入。

图片映射：
{mapping}

本次 PRIMARY 恰好 {len(expected_ids)} 张，必须恰好返回 {len(expected_ids)} 个结果。
允许输出的 frame_id 只有：
{expected_ids_json}

规则：
1. CONTEXT_ONLY 只用于比较，不得输出。
2. 每张 PRIMARY 必须输出且仅输出一次。
3. 不得创建、猜测、补全不存在的 frame_id。
4. 输出顺序必须与允许列表完全一致。
5. 这是 Evidence Observation，不做 Hook、Pattern、Proof、CTA 或商业效果判断。
6. 不推断人物真实身份、职业、店铺归属、商业成功或因果关系。
7. OCR 尽量逐字保留，不润色。
8. information_change 判断观看者是否获得新视觉信息；不确定则 UNCERTAIN。

只输出 JSON：
{{
  "frames": [
    {{
      "frame_id": "必须来自允许列表",
      "timestamp_seconds": 0.0,
      "ocr_raw": "",
      "visible_facts": [],
      "scene_summary": "",
      "visual_change_from_previous": "",
      "information_change": "YES|NO|UNCERTAIN",
      "new_visual_information": [],
      "uncertainties": [],
      "confidence": {{"ocr": "high|medium|low", "observation": "high|medium|low"}}
    }}
  ]
}}

再次强调：必须恰好输出 {len(expected_ids)} 个 frames；只允许这些 ID：{expected_ids_json}
"""

        image_paths = [str(x[1]) for x in image_items]
        attempts_total = 1 + args.max_retries
        successful = False
        frames_output: list[dict[str, Any]] = []
        sanitization_warnings: list[str] = []
        qwen_elapsed = 0.0
        last_error: Exception | None = None
        used_attempt = 0

        for attempt in range(1, attempts_total + 1):
            used_attempt = attempt
            print(f"[{chunk_no}/{total_chunks}] START attempt {attempt}/{attempts_total} ({len(primary)} primary" + (" + 1 context" if context_frame else "") + ")", flush=True)
            t0 = time.perf_counter()
            response = chat(
                model=args.model,
                messages=[{"role": "user", "content": prompt, "images": image_paths}],
                format="json",
                options={"temperature": 0, "num_ctx": args.num_ctx, "num_predict": 6000},
                keep_alive=600,
            )
            elapsed = time.perf_counter() - t0
            qwen_elapsed += elapsed
            response_metrics = ollama_response_metrics(response)
            raw_content = response.message.content or ""
            raw_path = chunk_raw_path if attempt == 1 else chunks_dir / f"chunk_{chunk_no:03d}_attempt_{attempt:02d}_raw.txt"
            raw_path.write_text(raw_content, encoding="utf-8")

            try:
                model_output = parse_json_content(raw_content)
                frames_output, sanitization_warnings = sanitize_chunk_result(model_output, expected_ids)
                frames_output = normalize_frames_to_manifest(frames_output, primary)
            except Exception as exc:
                last_error = exc
                print(f"[{chunk_no}/{total_chunks}] INVALID attempt {attempt} elapsed={elapsed:.2f}s: {exc}", flush=True)
                continue

            successful = True
            print(f"[{chunk_no}/{total_chunks}] PASS attempt {attempt} elapsed={elapsed:.2f}s", flush=True)
            for warning in sanitization_warnings:
                print(f"[{chunk_no}/{total_chunks}] SANITIZE WARNING: {warning}", flush=True)
            break

        if not successful:
            raise RuntimeError(f"Chunk {chunk_no} failed after {attempts_total} attempts: {last_error}")

        chunk_record = {
            "chunk_id": f"C{chunk_no:03d}",
            "primary_frame_ids": expected_ids,
            "context_frame_id": str(context_frame["filename"]) if context_frame else None,
            "model": args.model,
            "num_ctx": args.num_ctx,
            "analysis_image_max_edge": args.max_image_edge,
            "analysis_image_sizes": analysis_image_sizes,
            "original_image_sizes": original_image_sizes,
            "status": "success",
            "recovered_from_raw": False,
            "qwen_elapsed_seconds": round(qwen_elapsed, 6),
            "ollama_response_metrics": response_metrics,
            "attempts_used": used_attempt,
            "sanitization_warnings": sanitization_warnings,
        }
        chunk_json_path.write_text(json.dumps({"chunk": chunk_record, "model_output": {"frames": frames_output}}, ensure_ascii=False, indent=2), encoding="utf-8")
        all_results.extend(frames_output)
        chunk_records.append(chunk_record)
        new_chunks_completed += 1
        print(f"[{chunk_no}/{total_chunks}] SAVED -> {chunk_json_path.name}", flush=True)

        if args.max_new_chunks is not None and new_chunks_completed >= args.max_new_chunks and chunk_no < total_chunks:
            elapsed = time.perf_counter() - run_started
            print("\nVISUAL TIMELINE V1 PARTIAL", flush=True)
            print(f"Completed through chunk: {chunk_no}/{total_chunks}", flush=True)
            print(f"New Qwen chunks this run: {new_chunks_completed}", flush=True)
            print(f"Run elapsed: {elapsed:.2f}s ({elapsed/60:.2f} min)", flush=True)
            print("Resume by running the same command without --max-new-chunks.", flush=True)
            return

    expected_all = [str(x["filename"]) for x in candidates]
    returned_all = [str(x["frame_id"]) for x in all_results]
    if returned_all != expected_all:
        raise RuntimeError("Candidate-complete validation failed.")

    result = {
        "schema_version": "visual-timeline-v1.1-draft",
        "tool_version": SCRIPT_VERSION,
        "case_id": case_id,
        "source_manifest": str(manifest_path),
        "model": args.model,
        "analysis_mode": "candidate_complete_chunked",
        "chunk_size": args.chunk_size,
        "num_ctx": args.num_ctx,
        "analysis_image_max_edge": args.max_image_edge,
        "coverage": {
            "candidate_frame_count": len(candidates),
            "analyzed_frame_count": len(all_results),
            "coverage_ratio": 1.0,
            "coverage_label": "candidate_complete",
        },
        "frames": all_results,
        "chunks": chunk_records,
        "authority": {
            "source_pixels": "original_frames",
            "analysis_pixels": (
                "original_frames"
                if args.max_image_edge is None
                else f"derived_proxy_max_edge_{args.max_image_edge}"
            ),
            "frame_id_and_timestamp": "visual_manifest",
            "ocr_and_observation": "qwen3-vl",
            "semantic_video_understanding": "not_performed_here",
        },
        "validation": {
            "all_candidate_frames_analyzed_exactly_once": True,
            "frame_order_preserved": True,
            "model_cannot_modify_timestamps": True,
            "unexpected_model_frame_ids_are_dropped_only_if_all_expected_frames_are_present_exactly_once_in_order": True,
        },
        "timing": {
            "run_elapsed_seconds": round(time.perf_counter() - run_started, 6),
            "chunk_qwen_elapsed_seconds": {str(x.get("chunk_id")): x.get("qwen_elapsed_seconds") for x in chunk_records},
        },
    }

    output_path = output_dir / "visual_timeline_v1.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = output_dir / "visual_timeline_v1_summary.txt"
    summary_path.write_text(
        "\n".join([
            "VISUAL TIMELINE V1 PASS",
            f"Case ID: {case_id}",
            f"Candidate frames: {len(candidates)}",
            f"Analyzed frames: {len(all_results)}",
            "Coverage: 100%",
            f"Chunks: {total_chunks}",
            f"Chunk size: {args.chunk_size}",
            f"Model: {args.model}",
            f"Output: {output_path}",
        ]),
        encoding="utf-8",
    )

    print("\nVISUAL TIMELINE V1 PASS", flush=True)
    print(f"Candidate frames: {len(candidates)}", flush=True)
    print(f"Analyzed frames: {len(all_results)}", flush=True)
    print("Coverage: 100% (candidate_complete)", flush=True)
    print(f"Chunks: {total_chunks}", flush=True)
    print(
        f"Analysis image max edge: "
        f"{args.max_image_edge if args.max_image_edge is not None else 'original'}",
        flush=True,
    )
    print(f"JSON: {output_path}", flush=True)
    print(f"Summary: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
