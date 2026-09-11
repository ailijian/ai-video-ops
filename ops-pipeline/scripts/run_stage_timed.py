from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "run_stage_timed.py@0.4"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_video_duration_seconds(video: Path) -> float | None:
    try:
        import cv2  # type: ignore
        cap = cv2.VideoCapture(str(video))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        cap.release()
        if fps > 0 and frames > 0:
            return frames / fps
    except Exception:
        pass
    return None


def gpu_name() -> str | None:
    try:
        value = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
        ).strip()
        return value.splitlines()[0].strip() if value else None
    except Exception:
        return None


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def normalize_child_command(command: list[str]) -> tuple[list[str], str | None]:
    if not command:
        return command, None
    first = Path(command[0]).name.lower()
    if first in {"python", "python.exe"}:
        return [sys.executable, *command[1:]], command[0]
    return command, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generic timed stage runner with pinned Python, UTF-8, and unbuffered child output.")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--source-video", required=True)
    parser.add_argument("--metrics-root", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise RuntimeError("No child command supplied.")

    command, rewritten_from = normalize_child_command(command)
    video = Path(args.source_video).expanduser().resolve()
    if not video.exists():
        raise FileNotFoundError(video)

    project_root = Path(__file__).resolve().parents[1]
    metrics_root = Path(args.metrics_root).expanduser().resolve() if args.metrics_root else project_root / "data" / "metrics"
    duration_seconds = read_video_duration_seconds(video)

    run_id = f"{args.stage}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    child_env = os.environ.copy()
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUNBUFFERED"] = "1"

    started_at = now_iso()
    started = time.perf_counter()

    print("=" * 72, flush=True)
    print("PIPELINE STAGE TIMING START", flush=True)
    print(f"Tool version: {SCRIPT_VERSION}", flush=True)
    print(f"Run ID: {run_id}", flush=True)
    print(f"Stage: {args.stage}", flush=True)
    print(f"Case ID: {args.case_id}", flush=True)
    print(f"Wrapper Python: {sys.executable}", flush=True)
    if rewritten_from is not None:
        print(f"Child Python rewrite: {rewritten_from} -> {sys.executable}", flush=True)
    print("Child Python UTF-8 mode: ON", flush=True)
    print("Child Python unbuffered output: ON", flush=True)
    print(f"Source video: {video}", flush=True)
    if duration_seconds is not None:
        print(f"Source duration: {duration_seconds:.3f}s", flush=True)
    print("Command:", flush=True)
    print(" ".join(f'"{x}"' if " " in x else x for x in command), flush=True)
    print("=" * 72, flush=True)
    print(flush=True)

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(project_root),
        env=child_env,
    )

    output_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output_lines.append(line)
        print(line, end="", flush=True)

    return_code = process.wait()
    wall_seconds = time.perf_counter() - started
    completed_at = now_iso()
    normalized = wall_seconds / duration_seconds * 60 if duration_seconds and duration_seconds > 0 else None

    metric = {
        "tool_version": SCRIPT_VERSION,
        "run_id": run_id,
        "stage": args.stage,
        "case_id": args.case_id,
        "status": "success" if return_code == 0 else "failed",
        "return_code": return_code,
        "started_at": started_at,
        "completed_at": completed_at,
        "wall_elapsed_seconds": round(wall_seconds, 6),
        "wall_elapsed_minutes": round(wall_seconds / 60, 6),
        "source_video": str(video),
        "source_video_duration_seconds": round(duration_seconds, 6) if duration_seconds is not None else None,
        "normalized_wall_seconds_per_60s_source_video": round(normalized, 6) if normalized is not None else None,
        "normalized_wall_minutes_per_60s_source_video": round(normalized / 60, 6) if normalized is not None else None,
        "wrapper_python": sys.executable,
        "child_python_rewritten_from": rewritten_from,
        "child_python_env": {
            "PYTHONUTF8": child_env.get("PYTHONUTF8"),
            "PYTHONIOENCODING": child_env.get("PYTHONIOENCODING"),
            "PYTHONUNBUFFERED": child_env.get("PYTHONUNBUFFERED"),
        },
        "command": command,
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "gpu": gpu_name(),
        },
        "stdout_tail": "".join(output_lines[-60:]),
    }

    case_dir = metrics_root / "cases" / args.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    run_path = case_dir / f"{run_id}.json"
    run_path.write_text(json.dumps(metric, ensure_ascii=False, indent=2), encoding="utf-8")
    global_log = metrics_root / "pipeline_stage_runs.jsonl"
    append_jsonl(global_log, metric)

    print("\n" + "=" * 72, flush=True)
    print("PIPELINE STAGE TIMING RESULT", flush=True)
    print(f"Status: {metric['status']}", flush=True)
    print(f"Stage: {args.stage}", flush=True)
    print(f"Wall time: {wall_seconds:.2f}s ({wall_seconds / 60:.2f} min)", flush=True)
    if duration_seconds is not None:
        print(f"Source video: {duration_seconds:.2f}s", flush=True)
    if normalized is not None:
        print(f"Normalized per 60s source video: {normalized:.2f}s ({normalized / 60:.2f} min)", flush=True)
    print(f"Run metrics: {run_path}", flush=True)
    print(f"Global metrics: {global_log}", flush=True)
    print("=" * 72, flush=True)

    if return_code != 0:
        raise SystemExit(return_code)


if __name__ == "__main__":
    main()
