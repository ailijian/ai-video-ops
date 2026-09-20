from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .database import connect
from .operation_lock import OperationLockTimeout, operation_lock
from .subprocess_env import pipeline_subprocess_env

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "ops-pipeline" / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))
from case_source_upload_v1 import (  # noqa: E402
    MAX_BYTES, RECEIPT, SUFFIXES, UPLOAD_ID, read_upload, sha256_file, upload_directory,
)


def upload_error(message: str, status: int = 422) -> HTTPException:
    return HTTPException(status, detail={"code": "CASE_SOURCE_UPLOAD_INVALID",
                                        "message": message, "next_action": message})


def probe_upload(settings: Settings, path: Path) -> dict:
    try:
        result = subprocess.run([
            settings.pipeline_python_executable or settings.python_executable,
            str(settings.pipeline_root / "scripts" / "case_source_upload_v1.py"),
            "--inspect", str(path),
        ], capture_output=True, text=True, encoding="utf-8", timeout=30,
            stdin=subprocess.DEVNULL, env=pipeline_subprocess_env(needs_deepseek=False))
        value = json.loads(result.stdout)
        if result.returncode or not value.get("ok"):
            raise ValueError("Invalid media")
        return value["media"]
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise upload_error("无法读取视频。请上传 10 分钟以内、最大 4K、保留音轨的 MP4 / MOV / WebM 文件。") from exc


async def receive_upload(request: Request, settings: Settings, *, source, user: dict,
                         suffix: str, rights_confirmed: bool, source_match_confirmed: bool) -> dict:
    if not rights_confirmed or not source_match_confirmed:
        raise upload_error("请确认你有权上传并用于本次分析，且文件与来源链接对应。")
    if suffix.lower() not in SUFFIXES:
        raise upload_error("请选择 MP4、MOV、M4V 或 WebM 视频文件。")
    length = request.headers.get("content-length", "")
    if length and (not length.isdigit() or int(length) > MAX_BYTES):
        raise upload_error("视频文件不能超过 256 MB。", 413)
    upload_id = uuid.uuid4().hex
    directory = upload_directory(settings.pipeline_root, upload_id)
    video = directory / f"{source.video_id}{suffix.lower()}"
    try:
        # One upload per operator, including across runtime processes. A crashed
        # connection releases this OS lock; cleanup never trusts client filenames.
        with operation_lock(settings.pipeline_root, f"source-upload-user:{user['id']}", timeout_seconds=0):
            root = directory.parent
            outstanding = 0
            for candidate in root.glob(f"*/{RECEIPT}"):
                try:
                    info = json.loads(candidate.read_text(encoding="utf-8"))
                    if info.get("uploaded_by_user_id") == int(user["id"]):
                        outstanding += sum(p.stat().st_size for p in candidate.parent.iterdir() if p.suffix in SUFFIXES)
                except (OSError, ValueError):
                    continue
            if outstanding >= MAX_BYTES * 4:
                raise upload_error("待处理上传较多，请等待现有分析完成后再上传。", 429)
            directory.mkdir(parents=True, exist_ok=False)
            digest = hashlib.sha256()
            size = 0
            try:
                async with asyncio.timeout(600):
                    with video.open("xb") as handle:
                        async for chunk in request.stream():
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise upload_error("视频文件不能超过 256 MB。", 413)
                            digest.update(chunk)
                            await run_in_threadpool(handle.write, chunk)
                if not size:
                    raise upload_error("视频文件为空，请重新选择。")
                media = await run_in_threadpool(probe_upload, settings, video)
                receipt = {"schema_version": "case-source-upload-v1.0", "upload_id": upload_id,
                           "case_id": source.video_id, "source_url": source.canonical_url,
                           "filename": video.name, "source_video_sha256": digest.hexdigest(),
                           "size_bytes": size, "uploaded_by_user_id": int(user["id"]),
                           "uploaded_by_phone": str(user["phone"]),
                           "uploaded_at": datetime.now(timezone.utc).isoformat(),
                           "rights_confirmed": True, "source_match_confirmed": True,
                           "binding_method": "operator_attestation", "platform_original_verified": False,
                           "media_rights_granted": False, "production_footage_pool_eligible": False,
                           "media": media}
                (directory / RECEIPT).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
            except BaseException:
                # Only this request's UUID directory and known filenames.
                video.unlink(missing_ok=True)
                (directory / RECEIPT).unlink(missing_ok=True)
                directory.rmdir()
                raise
    except OperationLockTimeout as exc:
        raise upload_error("你已有一个文件正在上传，请等待完成。", 409) from exc
    except TimeoutError as exc:
        raise upload_error("上传超时，请检查网络后重新选择视频。", 408) from exc
    return {"upload_id": upload_id, "canonical_url": source.canonical_url,
            "video_id": source.video_id, "size_bytes": size, "media": media}


def validate_for_submission(settings: Settings, upload_id: str, source_url: str, user_id: int) -> dict:
    try:
        receipt, _ = read_upload(settings.pipeline_root, upload_id, source_url=source_url, user_id=user_id)
        created = datetime.fromisoformat(receipt["uploaded_at"])
        if datetime.now(timezone.utc) - created > timedelta(hours=24):
            raise ValueError("Expired upload")
        connection = connect(settings.database_path)
        try:
            if connection.execute(
                "SELECT 1 FROM tasks WHERE task_type = 'case_analysis' "
                "AND json_extract(payload_json, '$.source_upload.upload_id') = ? LIMIT 1", (upload_id,),
            ).fetchone():
                raise ValueError("Upload has already been used by a task")
        finally:
            connection.close()
        return {"upload_id": upload_id,
                "receipt_sha256": sha256_file(upload_directory(settings.pipeline_root, upload_id) / RECEIPT)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise upload_error("上传文件已失效或与当前来源不符，请重新上传。") from exc


def cleanup_unused_uploads(settings: Settings) -> None:
    """Hourly orphan/failed-before-acquisition cleanup; never touch active tasks."""
    now = datetime.now(timezone.utc)
    root = settings.pipeline_root / "data" / "case_source_uploads"
    for directory in root.glob("*"):
        if not UPLOAD_ID.fullmatch(directory.name) or not directory.is_dir():
            continue
        try:
            directory = upload_directory(settings.pipeline_root, directory.name)
            with operation_lock(settings.pipeline_root, f"source-upload:{directory.name}", timeout_seconds=0):
                connection = connect(settings.database_path)
                try:
                    task = connection.execute(
                        "SELECT status, updated_at FROM tasks WHERE task_type = 'case_analysis' "
                        "AND json_extract(payload_json, '$.source_upload.upload_id') = ? LIMIT 1",
                        (directory.name,),
                    ).fetchone()
                finally:
                    connection.close()
                if task and task["status"] != "failed":
                    continue  # successful attempts use validated canonical retention
                threshold = (datetime.fromisoformat(task["updated_at"].replace("Z", "+00:00")) if task
                             else datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc))
                if now - threshold < timedelta(hours=24):
                    continue
                deleted = 0
                for video in directory.iterdir():
                    if video.suffix in SUFFIXES and not video.is_symlink() and video.resolve().parent == directory:
                        deleted += video.stat().st_size
                        video.unlink()
                if deleted:
                    (directory / "upload_cleanup_receipt_v1.json").write_text(json.dumps({
                        "upload_id": directory.name, "trigger": "failed_or_unused_24h",
                        "cleanup_at": now.isoformat(), "deleted_bytes": deleted,
                    }), encoding="utf-8")
        except (OSError, ValueError, OperationLockTimeout):
            continue  # retry next hour, not a business failure
