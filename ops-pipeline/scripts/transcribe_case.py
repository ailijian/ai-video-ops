import argparse
import json
from pathlib import Path
import os
from pathlib import Path


# Keep DLL directory handles alive for the lifetime
# of the Python process.
_DLL_DIRECTORY_HANDLES = []


def configure_windows_cuda_dlls():
    if os.name != "nt":
        return

    candidate_dirs = []

    # CUDA Toolkit installed by NVIDIA installer.
    cuda_path = os.environ.get("CUDA_PATH")

    if cuda_path:
        candidate_dirs.append(
            Path(cuda_path) / "bin"
        )

    # Optional explicit cuDNN location.
    cudnn_path = os.environ.get("CUDNN_PATH")

    if cudnn_path:
        candidate_dirs.append(
            Path(cudnn_path)
        )

    for dll_dir in candidate_dirs:
        if dll_dir.exists():
            handle = os.add_dll_directory(
                str(dll_dir)
            )
            _DLL_DIRECTORY_HANDLES.append(
                handle
            )


from faster_whisper import WhisperModel

configure_windows_cuda_dlls()

def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def find_companion(video: Path, suffix: str):
    candidate = video.with_name(video.stem + suffix)
    return str(candidate) if candidate.exists() else None


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe one short-video case with faster-whisper."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to MP4/audio file",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model, e.g. small / medium / large-v3",
    )
    parser.add_argument(
        "--language",
        default="zh",
        help="Language code. Default: zh. Use auto for auto detection.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda"],
    )
    parser.add_argument(
        "--compute-type",
        default=None,
    )

    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"Input not found: {source}")

    project_root = Path(__file__).resolve().parents[1]
    output_dir = project_root / "data" / "analysis" / source.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    compute_type = args.compute_type
    if compute_type is None:
        compute_type = "int8" if args.device == "cpu" else "float16"

    language = None if args.language.lower() == "auto" else args.language

    print(f"Source: {source}")
    print(f"Model: {args.model}")
    print(f"Device: {args.device}")
    print(f"Compute type: {compute_type}")
    print("Loading model...")

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=compute_type,
    )

    print("Transcribing...")

    segments_generator, info = model.transcribe(
        str(source),
        language=language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )

    segments = list(segments_generator)

    segment_data = []
    raw_lines = []
    srt_blocks = []

    for index, segment in enumerate(segments, start=1):
        text = segment.text.strip()

        if not text:
            continue

        raw_lines.append(text)

        words = []

        if segment.words:
            for word in segment.words:
                words.append(
                    {
                        "start": word.start,
                        "end": word.end,
                        "word": word.word,
                        "probability": getattr(word, "probability", None),
                    }
                )

        segment_data.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": text,
                "words": words,
            }
        )

        srt_blocks.append(
            f"{index}\n"
            f"{srt_time(segment.start)} --> {srt_time(segment.end)}\n"
            f"{text}\n"
        )

    transcript_text = "\n".join(raw_lines)

    raw_txt = output_dir / "transcript_raw.txt"
    segment_json = output_dir / "transcript_segments.json"
    srt_file = output_dir / "transcript.srt"
    manifest_file = output_dir / "case_manifest.json"

    raw_txt.write_text(
        transcript_text,
        encoding="utf-8",
    )

    segment_json.write_text(
        json.dumps(
            {
                "source_file": str(source),
                "model": args.model,
                "device": args.device,
                "compute_type": compute_type,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": getattr(info, "duration", None),
                "segments": segment_data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    srt_file.write_text(
        "\n".join(srt_blocks),
        encoding="utf-8",
    )

    manifest = {
        "source": {
            "video": str(source),
            "metadata_json": find_companion(source, "_data.json"),
            "music": find_companion(source, "_music.mp3"),
            "cover": find_companion(source, "_cover.jpg"),
        },
        "transcript": {
            "raw": str(raw_txt),
            "segments": str(segment_json),
            "srt": str(srt_file),
        },
        "asr": {
            "engine": "faster-whisper",
            "model": args.model,
            "language": info.language,
            "language_probability": info.language_probability,
        },
    }

    manifest_file.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("Done.")
    print(f"Detected language: {info.language}")
    print(f"Language probability: {info.language_probability:.3f}")
    print()
    print("Transcript:")
    print("-" * 60)
    print(transcript_text)
    print("-" * 60)
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()