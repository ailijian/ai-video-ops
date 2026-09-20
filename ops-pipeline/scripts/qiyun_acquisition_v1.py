"""Acquire transient Douyin media from Qiyun without making it source authority."""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from case_source_upload_v1 import MAX_BYTES, inspect_video, sha256_file
from operation_lock_v1 import operation_lock


ENDPOINT = "https://qyapi.ipaybuy.cn/api/video"
MAX_RESPONSE_BYTES = 128 * 1024
MAX_REDIRECTS = 4
MIN_CALL_INTERVAL_SECONDS = 60
MEDIA_HOST_SUFFIXES = ("douyinvod.com", "douyin.com")


class QiyunAcquisitionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _safe_media_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError:
        raise QiyunAcquisitionError("SOURCE_MEDIA_URL_UNSAFE", "视频地址无效，请上传本地视频后重试。") from None
    if (parts.scheme != "https" or not host or parts.username or parts.password
            or parts.fragment or port not in {None, 443}):
        raise QiyunAcquisitionError("SOURCE_MEDIA_URL_UNSAFE", "视频地址无效，请上传本地视频后重试。")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in MEDIA_HOST_SUFFIXES):
        raise QiyunAcquisitionError("SOURCE_MEDIA_URL_UNSAFE", "视频地址不属于抖音媒体域名，请上传本地视频后重试。")
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("non-public media address")
    except (OSError, ValueError) as exc:
        raise QiyunAcquisitionError("SOURCE_MEDIA_URL_UNSAFE", "视频地址不可安全访问，请上传本地视频后重试。") from exc
    return value


def _pace_provider_calls(pipeline_root: Path) -> None:
    """Cross-process pacing is operational only; never part of Case Authority."""
    marker = pipeline_root / "data" / ".provider_rate" / "qiyun_last_call"
    marker.parent.mkdir(parents=True, exist_ok=True)
    with operation_lock(pipeline_root, "qiyun-api-call", timeout_seconds=120):
        try:
            last_call = float(marker.read_text(encoding="ascii"))
        except (OSError, ValueError):
            last_call = 0.0
        remaining = MIN_CALL_INTERVAL_SECONDS - (time.time() - last_call)
        if remaining > 0:
            time.sleep(remaining)
        marker.write_text(str(time.time()), encoding="ascii")


def _parse_response(response: httpx.Response) -> dict:
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_INVALID", "视频解析结果无效，请上传本地视频。")
    try:
        result = response.json()
    except (ValueError, TypeError) as exc:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_INVALID", "视频解析结果无效，请上传本地视频。") from exc
    if not isinstance(result, dict):
        raise QiyunAcquisitionError("SOURCE_PROVIDER_INVALID", "视频解析结果无效，请上传本地视频。")
    code = result.get("code")
    if code == 3001:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_RATE_LIMITED", "视频解析请求过于频繁，请稍后重试或上传本地视频。")
    if code in {3002, 3003}:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_QUOTA_EXHAUSTED", "视频解析额度暂不可用，请上传本地视频。")
    if response.status_code != 200:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_UNAVAILABLE", "视频解析服务暂时不可用，请稍后重试或上传本地视频。")
    if code != 200:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_REJECTED", "暂时无法解析这个视频，请检查来源或上传本地视频。")
    data = result.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("video_url"), str) or not data["video_url"].strip():
        raise QiyunAcquisitionError("SOURCE_PROVIDER_NO_VIDEO", "未取得视频文件，请上传本地视频。")
    return data


def _download(client: httpx.Client, media_url: str, destination: Path) -> int:
    current = _safe_media_url(media_url)
    visited: set[str] = set()
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    if destination.is_symlink() or partial.is_symlink():
        raise QiyunAcquisitionError("SOURCE_MEDIA_PATH_UNSAFE", "本地视频路径无效。")
    for _ in range(MAX_REDIRECTS + 1):
        if current in visited:
            raise QiyunAcquisitionError("SOURCE_MEDIA_REDIRECT_INVALID", "视频地址跳转异常，请上传本地视频。")
        visited.add(current)
        try:
            with client.stream("GET", current, follow_redirects=False) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        break
                    current = _safe_media_url(urljoin(current, location))
                    continue
                if response.status_code != 200:
                    raise QiyunAcquisitionError("SOURCE_MEDIA_DOWNLOAD_FAILED", "视频下载失败，请稍后重试或上传本地视频。")
                declared = response.headers.get("content-length")
                if declared and declared.isdecimal() and int(declared) > MAX_BYTES:
                    raise QiyunAcquisitionError("SOURCE_MEDIA_TOO_LARGE", "视频超过 256 MB，请使用较短的视频。")
                total = 0
                deadline = time.monotonic() + 600
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes(1024 * 1024):
                        if time.monotonic() > deadline:
                            raise QiyunAcquisitionError("SOURCE_MEDIA_DOWNLOAD_TIMEOUT", "视频下载超时，请稍后重试。")
                        total += len(chunk)
                        if total > MAX_BYTES:
                            raise QiyunAcquisitionError("SOURCE_MEDIA_TOO_LARGE", "视频超过 256 MB，请使用较短的视频。")
                        handle.write(chunk)
                if not total or (declared and declared.isdecimal() and total != int(declared)):
                    raise QiyunAcquisitionError("SOURCE_MEDIA_INCOMPLETE", "视频下载不完整，请稍后重试。")
                os.replace(partial, destination)
                return total
        except httpx.HTTPError:
            # httpx exception strings may contain the signed URL. Never surface them.
            raise QiyunAcquisitionError("SOURCE_MEDIA_DOWNLOAD_FAILED", "视频下载失败，请稍后重试或上传本地视频。") from None
    raise QiyunAcquisitionError("SOURCE_MEDIA_REDIRECT_INVALID", "视频地址跳转过多，请上传本地视频。")


def _audio_decodable(video: Path) -> bool:
    import av

    with av.open(str(video), options={"protocol_whitelist": "file"}) as container:
        stream = next(iter(container.streams.audio), None)
        return stream is not None and next(container.decode(stream), None) is not None


def acquire_qiyun_media(*, pipeline_root: Path, source_url: str, case_id: str,
                        attempt_root: Path, provider_source_url: str | None = None) -> dict:
    app_id = os.environ.get("QYAPI_APP_ID", "").strip()
    app_key = os.environ.get("QYAPI_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_NOT_CONFIGURED", "视频解析服务尚未配置，请上传本地视频。")
    if source_url != f"https://www.douyin.com/video/{case_id}":
        raise QiyunAcquisitionError("SOURCE_IDENTITY_UNRESOLVED", "抖音视频身份无效。")
    provider_url = provider_source_url or source_url
    parts = urlsplit(provider_url)
    if provider_url != source_url and (
        parts.scheme != "https" or parts.hostname != "v.douyin.com" or parts.port is not None
        or parts.username or parts.password or parts.fragment or parts.query
        or not re.fullmatch(r"/[A-Za-z0-9_-]{4,128}/?", parts.path)
    ):
        raise QiyunAcquisitionError("SOURCE_PROVIDER_INPUT_INVALID", "抖音来源链接无效。")
    try:
        _pace_provider_calls(pipeline_root)
        with httpx.Client(trust_env=False, follow_redirects=False,
                          timeout=httpx.Timeout(20, connect=10)) as client:
            with client.stream("POST", ENDPOINT, json={
                "appId": app_id, "appKey": app_key, "url": provider_url,
            }) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise QiyunAcquisitionError("SOURCE_PROVIDER_INVALID", "视频解析结果无效，请上传本地视频。")
                data = _parse_response(httpx.Response(response.status_code, content=bytes(body)))
            video = attempt_root / "source_media" / "source.mp4"
            _download(client, data["video_url"], video)
    except httpx.HTTPError:
        raise QiyunAcquisitionError("SOURCE_PROVIDER_UNAVAILABLE", "视频解析服务暂时不可用，请稍后重试或上传本地视频。") from None
    try:
        inspected = inspect_video(video)
        if not _audio_decodable(video):
            raise ValueError("no decodable audio")
    except Exception:
        raise QiyunAcquisitionError("SOURCE_MEDIA_INVALID", "视频文件缺少可用画面或音轨，请上传本地视频。") from None
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    title = str(data.get("title") or "")[:1000]
    author_name = str(author.get("name") or "")[:200]
    return {
        "video": str(video),
        "source_video_sha256": sha256_file(video),
        "source_description": title,
        "source_author": author_name,
        "metadata": {
            "schema_version": "source-metadata-v1.0",
            "provider": "qiyun", "platform": "douyin",
            "stable_video_id": case_id, "canonical_source_url": source_url,
            "title": title, "author": author_name,
            "media": inspected,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        },
    }
