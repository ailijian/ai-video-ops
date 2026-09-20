"""Transient, operator-supplied media. No downloader, model, or rights inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

UPLOAD_ID = re.compile(r"^[a-f0-9]{32}$")
MAX_BYTES = 256 * 1024 * 1024
MAX_SECONDS = 600
SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
RECEIPT = "source_upload_receipt_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_directory(pipeline_root: Path, upload_id: str) -> Path:
    if not UPLOAD_ID.fullmatch(upload_id):
        raise ValueError("Invalid upload reference")
    root = (pipeline_root / "data" / "case_source_uploads").resolve()
    directory = root / upload_id
    if directory.resolve().parent != root or directory.is_symlink():
        raise ValueError("Upload path escapes its storage root")
    return directory


def read_upload(pipeline_root: Path, upload_id: str, *, source_url: str,
                receipt_sha256: str | None = None, user_id: int | None = None,
                verify_media: bool = True) -> tuple[dict, Path]:
    directory = upload_directory(pipeline_root, upload_id)
    receipt_path = directory / RECEIPT
    if receipt_path.is_symlink() or receipt_path.stat().st_size > 32 * 1024:
        raise ValueError("Invalid upload receipt")
    if receipt_sha256 and sha256_file(receipt_path) != receipt_sha256:
        raise ValueError("Upload receipt checksum mismatch")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    case_id = receipt.get("case_id", "")
    if (receipt.get("schema_version") != "case-source-upload-v1.0"
            or receipt.get("upload_id") != upload_id
            or not re.fullmatch(r"\d{10,24}", str(case_id))
            or receipt.get("source_url") != source_url
            or source_url != f"https://www.douyin.com/video/{case_id}"
            or receipt.get("rights_confirmed") is not True
            or receipt.get("source_match_confirmed") is not True
            or receipt.get("binding_method") != "operator_attestation"
            or not isinstance(receipt.get("uploaded_by_user_id"), int)
            or (user_id is not None and receipt["uploaded_by_user_id"] != user_id)):
        raise ValueError("Upload ownership or source binding mismatch")
    filename = str(receipt.get("filename") or "")
    if Path(filename).suffix not in SUFFIXES or filename != case_id + Path(filename).suffix:
        raise ValueError("Invalid upload filename")
    video = directory / filename
    if video.is_symlink() or video.resolve().parent != directory.resolve():
        raise ValueError("Invalid upload media path")
    if verify_media and (not video.is_file() or not 0 < video.stat().st_size <= MAX_BYTES
                         or video.stat().st_size != receipt.get("size_bytes")
                         or sha256_file(video) != receipt.get("source_video_sha256")):
        raise ValueError("Upload missing or checksum mismatch; upload the file again")
    return receipt, video


def inspect_video(path: Path) -> dict:
    # Executed in a bounded child process by Console. Importing this module does
    # not load PyAV, Whisper, Qwen, CUDA, or any model.
    import av

    with path.open("rb") as handle:
        magic = handle.read(12)
    if not (magic[4:8] == b"ftyp" or magic[:4] == b"\x1a\x45\xdf\xa3"):
        raise ValueError("Only MP4/MOV/WebM containers are accepted")
    with av.open(str(path), options={
        "format_whitelist": "mov,matroska,webm",
        "protocol_whitelist": "file",
        "enable_drefs": "0", "use_absolute_path": "0",
    }) as container:
        videos = [s for s in container.streams.video if not (s.disposition & av.stream.Disposition.attached_pic)]
        if len(videos) != 1 or not container.streams.audio:
            raise ValueError("A single video track and an audio track (including silence) are required")
        video = videos[0]
        duration = float(container.duration or 0) / av.time_base
        if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
            raise ValueError("Video duration must be between 0 and 600 seconds")
        if not 0 < video.width <= 4096 or not 0 < video.height <= 4096:
            raise ValueError("Video dimensions must not exceed 4096 pixels")
        video.thread_count = 1
        frame = next(container.decode(video), None)
        if frame is None:
            raise ValueError("Video track cannot be decoded")
        return {"duration_seconds": duration, "width": video.width, "height": video.height,
                "audio_present": True, "container": container.format.name,
                "video_codec": video.codec_context.name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect local uploaded media without model calls")
    parser.add_argument("--inspect", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps({"ok": True, "media": inspect_video(args.inspect)}))
    except Exception:
        # Do not expose library diagnostics or local filesystem paths to clients.
        print(json.dumps({"ok": False, "code": "SOURCE_UPLOAD_MEDIA_INVALID"}))
        raise SystemExit(2)
