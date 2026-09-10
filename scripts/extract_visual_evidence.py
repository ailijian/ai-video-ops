import argparse
import hashlib
import json
import re
from pathlib import Path

import cv2
import numpy as np
from scenedetect import open_video, SceneManager
from scenedetect.detectors import AdaptiveDetector


def format_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)

    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def extract_case_id(source: Path) -> str:
    """
    Prefer Douyin aweme_id from filename.
    Fall back to a stable short hash if no ID exists.
    """

    matches = re.findall(
        r"(?<!\d)(\d{15,25})(?!\d)",
        source.stem,
    )

    if matches:
        return matches[-1]

    return hashlib.sha1(
        str(source).encode("utf-8")
    ).hexdigest()[:16]


def save_jpeg_unicode(path: Path, frame) -> None:
    """
    Windows-safe image saving.

    Avoid cv2.imwrite(path) because Unicode/special-character
    paths can fail silently on Windows.
    """

    success, encoded = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, 95],
    )

    if not success:
        raise RuntimeError(
            f"JPEG encoding failed: {path}"
        )

    path.write_bytes(encoded.tobytes())

    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(
            f"Image write failed: {path}"
        )


def visual_signature(frame):
    """
    Prepare a frame for perceptual comparison.

    Resize + grayscale + blur suppress:
    - compression noise
    - tiny pixel fluctuations
    - insignificant encoding differences
    """

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY,
    )

    gray = cv2.resize(
        gray,
        (320, 180),
        interpolation=cv2.INTER_AREA,
    )

    gray = cv2.GaussianBlur(
        gray,
        (5, 5),
        0,
    )

    return gray.astype(np.float32) / 255.0


def changed_ratio(reference, current):
    """
    Compare two frames after compensating for small:
    - translations
    - zoom
    - affine motion

    Returns the ratio of meaningfully changed pixels.
    """

    warp_matrix = np.eye(
        2,
        3,
        dtype=np.float32,
    )

    criteria = (
        cv2.TERM_CRITERIA_EPS
        | cv2.TERM_CRITERIA_COUNT,
        50,
        1e-5,
    )

    try:
        _, warp_matrix = cv2.findTransformECC(
            reference,
            current,
            warp_matrix,
            cv2.MOTION_AFFINE,
            criteria,
            None,
            1,
        )

        aligned = cv2.warpAffine(
            current,
            warp_matrix,
            (
                reference.shape[1],
                reference.shape[0],
            ),
            flags=(
                cv2.INTER_LINEAR
                | cv2.WARP_INVERSE_MAP
            ),
            borderMode=cv2.BORDER_REFLECT,
        )

    except cv2.error:
        # Alignment failure usually means
        # the visual state changed substantially.
        return 1.0

    diff = np.abs(
        reference - aligned
    )

    # Ignore small compression / luminance noise.
    meaningful_change = (
        diff >= 0.06
    )

    return float(
        np.mean(meaningful_change)
    )

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract visual evidence frames "
            "from short-video cases."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        help="MP4 input path",
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help=(
            "Periodic sampling interval in seconds. "
            "Use 0.5 for dense short-video sampling."
        ),
    )

    parser.add_argument(
        "--duplicate-threshold",
        type=float,
        default=0.01,
        help=(
            "Minimum changed-pixel ratio required "
            "to retain another frame."
        ),
    )

    parser.add_argument(
        "--keep-duplicates",
        action="store_true",
        help="Keep visually duplicate sampled frames.",
    )

    parser.add_argument(
        "--output-root",
        default=None,
        help="Optional visual evidence output root.",
    )

    args = parser.parse_args()

    source = Path(
        args.input
    ).expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(
            f"Input not found: {source}"
        )

    case_id = extract_case_id(source)

    project_root = (
        Path(__file__)
        .resolve()
        .parents[1]
    )

    if args.output_root:
        output_root = (
            Path(args.output_root)
            .expanduser()
            .resolve()
        )
    else:
        output_root = (
            project_root
            / "data"
            / "visual"
        )

    # IMPORTANT:
    # Canonical directory is aweme_id,
    # not the Chinese video title.
    output_dir = (
        output_root
        / case_id
    )

    frames_dir = (
        output_dir
        / "frames"
    )

    frames_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Case ID: {case_id}")
    print(f"Source: {source}")
    print(f"Output: {output_dir}")

    # -----------------------------------------
    # Open video
    # -----------------------------------------

    cap = cv2.VideoCapture(
        str(source)
    )

    if not cap.isOpened():
        raise RuntimeError(
            f"OpenCV cannot open video: {source}"
        )

    fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    frame_count = int(
        cap.get(
            cv2.CAP_PROP_FRAME_COUNT
        )
    )

    if fps <= 0:
        raise RuntimeError(
            f"Invalid video FPS: {fps}"
        )

    duration = (
        frame_count / fps
        if frame_count > 0
        else 0
    )

    if duration <= 0:
        raise RuntimeError(
            "Invalid video duration."
        )

    print(f"FPS: {fps:.3f}")
    print(f"Frames: {frame_count}")
    print(f"Duration: {duration:.3f}s")

    # -----------------------------------------
    # Scene detection
    # -----------------------------------------

    print("Detecting scenes...")

    video = open_video(
        str(source)
    )

    scene_manager = SceneManager()

    scene_manager.add_detector(
        AdaptiveDetector()
    )

    scene_manager.detect_scenes(
        video,
        show_progress=True,
    )

    scenes = scene_manager.get_scene_list(
        start_in_scene=True,
    )

    print(
        f"Scenes detected: {len(scenes)}"
    )

    # -----------------------------------------
    # Candidate timestamps
    # -----------------------------------------

    candidates = {}

    last_valid_second = max(
        0,
        duration - (1 / fps),
    )

    def add_candidate(
        seconds,
        reason,
    ):
        seconds = max(
            0,
            min(
                float(seconds),
                last_valid_second,
            ),
        )

        ms = int(
            round(seconds * 1000)
        )

        if ms not in candidates:
            candidates[ms] = {
                "timestamp_seconds": seconds,
                "reasons": [],
            }

        if (
            reason
            not in candidates[ms]["reasons"]
        ):
            candidates[ms][
                "reasons"
            ].append(reason)

    # Always include beginning/end.
    add_candidate(
        0,
        "video_start",
    )

    add_candidate(
        last_valid_second,
        "video_end",
    )

    # Periodic evidence sampling.
    t = 0.0

    while t <= last_valid_second:
        add_candidate(
            t,
            "periodic_sample",
        )
        t += args.interval

    # Scene-based candidates.
    for index, scene in enumerate(
        scenes,
        start=1,
    ):
        start, end = scene

        start_sec = (
            start.get_seconds()
        )

        end_sec = (
            end.get_seconds()
        )

        if end_sec <= start_sec:
            continue

        end_sec = min(
            end_sec,
            last_valid_second,
        )

        midpoint = (
            start_sec + end_sec
        ) / 2

        add_candidate(
            start_sec,
            f"scene_{index}_start",
        )

        add_candidate(
            midpoint,
            f"scene_{index}_middle",
        )

        add_candidate(
            end_sec,
            f"scene_{index}_end",
        )

    # -----------------------------------------
    # Extract frames + duplicate filtering
    # -----------------------------------------

    kept_frames = []
    duplicate_frames = []
    failed_frames = []

    previous_signature = None

    for ms, item in sorted(
        candidates.items()
    ):
        seconds = item[
            "timestamp_seconds"
        ]

        cap.set(
            cv2.CAP_PROP_POS_MSEC,
            seconds * 1000,
        )

        success, frame = cap.read()

        if not success:
            failed_frames.append(
                {
                    "timestamp_ms": ms,
                    "timestamp_seconds": seconds,
                    "reasons": item["reasons"],
                    "error": "frame_read_failed",
                }
            )

            print(
                "WARNING: "
                f"Could not read "
                f"{seconds:.3f}s"
            )
            continue

        signature = visual_signature(
            frame
        )

        difference = None

        if previous_signature is not None:
            difference = changed_ratio(
                previous_signature,
                signature,
            )

        duplicate = (
            previous_signature is not None
            and difference
            < args.duplicate_threshold
        )

        if (
            duplicate
            and not args.keep_duplicates
        ):
            duplicate_frames.append(
                {
                    "timestamp_ms": ms,
                    "timestamp_seconds": seconds,
                    "timestamp": format_timestamp(
                        seconds
                    ),
                    "difference_ratio": difference,
                    "reasons": item["reasons"],
                }
            )
            continue

        filename = (
            f"frame_{ms:09d}ms.jpg"
        )

        destination = (
            frames_dir
            / filename
        )

        save_jpeg_unicode(
            destination,
            frame,
        )

        kept_frames.append(
            {
                "filename": filename,
                "timestamp_ms": ms,
                "timestamp_seconds": seconds,
                "timestamp": format_timestamp(
                    seconds
                ),
                "difference_ratio_from_previous_kept": (
                    difference
                ),
                "reasons": item["reasons"],
            }
        )

        previous_signature = signature

        print(
            "Saved: "
            f"{filename} "
            f"@ {seconds:.3f}s"
        )

    cap.release()

    # -----------------------------------------
    # Manifest
    # -----------------------------------------

    manifest = {
        "case_id": case_id,
        "source_video": str(source),
        "source_title": source.stem,
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": duration,
        "scene_count": len(scenes),
        "sampling": {
            "interval_seconds": (
                args.interval
            ),
            "duplicate_threshold": (
                args.duplicate_threshold
            ),
        },
        "candidate_count": len(
            candidates
        ),
        "evidence_frame_count": len(
            kept_frames
        ),
        "duplicate_frame_count": len(
            duplicate_frames
        ),
        "failed_frame_count": len(
            failed_frames
        ),
        "frames": kept_frames,
        "duplicates": duplicate_frames,
        "failures": failed_frames,
    }

    manifest_path = (
        output_dir
        / "visual_evidence_manifest.json"
    )

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Done.")
    print(
        f"Candidates: "
        f"{len(candidates)}"
    )
    print(
        f"Evidence frames: "
        f"{len(kept_frames)}"
    )
    print(
        f"Duplicates removed: "
        f"{len(duplicate_frames)}"
    )
    print(
        f"Failed reads: "
        f"{len(failed_frames)}"
    )
    print(
        f"Output: {output_dir}"
    )


if __name__ == "__main__":
    main()