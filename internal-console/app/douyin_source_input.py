"""Resolve one operator-supplied Douyin video to a stable, canonical identity.

This module does not download media. Short-link requests only inspect bounded
HTTP response headers, and every network hop is restricted to public Douyin
addresses with a verified TLS connection.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qs, urljoin, urlsplit

ALLOWED_HOSTS = frozenset({
    "douyin.com", "www.douyin.com", "v.douyin.com",
    "iesdouyin.com", "www.iesdouyin.com",
})
URL_RE = re.compile(r"https?://(?:(?!https?://)[A-Za-z0-9._~:/?#@!$&'*+,;=%-])+", re.IGNORECASE)
VIDEO_PATH_RE = re.compile(r"/(?:share/)?video/(\d{10,24})(?:/|$)")
VIDEO_ID_RE = re.compile(r"\d{10,24}")
MAX_INPUT_LENGTH = 4096
MAX_REDIRECTS = 5
HOP_TIMEOUT_SECONDS = 4


class SourceInputError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DouyinSourceInput:
    input_kind: str
    extracted_url: str
    canonical_url: str
    video_id: str


def _validated_url(url: str, *, network: bool = False) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise SourceInputError("CASE_URL_INVALID", "抖音视频链接无效。") from exc
    if (parts.scheme.lower() not in {"http", "https"}
            or (network and parts.scheme.lower() != "https")
            or host not in ALLOWED_HOSTS or port is not None
            or parts.username is not None or parts.password is not None):
        raise SourceInputError("CASE_URL_INVALID", "暂时没有识别到抖音视频链接。")
    return host, parts.path


def video_id_from_url(url: str) -> str | None:
    _validated_url(url)
    parts = urlsplit(url)
    matches = []
    path_match = VIDEO_PATH_RE.search(parts.path)
    if path_match:
        matches.append(path_match.group(1))
    query = parse_qs(parts.query)
    for key in ("video_id", "modal_id"):
        matches.extend(value for value in query.get(key, []) if VIDEO_ID_RE.fullmatch(value))
    distinct = set(matches)
    if len(distinct) > 1:
        raise SourceInputError("CASE_SOURCE_IDENTITY_UNRESOLVED", "链接包含多个视频编号。")
    return next(iter(distinct), None)


def _reject_non_video_page(url: str) -> None:
    path = urlsplit(url).path
    if re.match(r"^/(?:share/)?user(?:/|$)", path):
        raise SourceInputError(
            "CASE_SOURCE_NOT_VIDEO",
            "这是抖音用户主页链接，不是单条视频。请打开具体视频，点击分享后复制视频链接。",
        )


def _public_address(host: str) -> str:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        public = [item[4][0] for item in addresses
                  if ipaddress.ip_address(item[4][0]).is_global]
    except (OSError, ValueError) as exc:
        raise SourceInputError("CASE_SOURCE_RESOLUTION_FAILED", "短链接暂时无法解析，请稍后重试。") from exc
    if not public or len(public) != len(addresses):
        raise SourceInputError("CASE_SOURCE_UNSAFE_REDIRECT", "短链接跳转到了不安全的地址。")
    return public[0]


def _request_location(url: str) -> tuple[int, str | None]:
    host, path = _validated_url(url, network=True)
    parts = urlsplit(url)
    address = _public_address(host)
    target = path or "/"
    if parts.query:
        target += "?" + parts.query
    # Pin the validated public address while retaining the hostname for SNI,
    # certificate verification, and the HTTP Host header (no DNS rebind gap).
    connection = http.client.HTTPSConnection(host, timeout=HOP_TIMEOUT_SECONDS)
    try:
        raw = socket.create_connection((address, 443), timeout=HOP_TIMEOUT_SECONDS)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        except BaseException:
            raw.close()
            raise
        connection.request("HEAD", target, headers={"Host": host, "Accept": "*/*"})
        response = connection.getresponse()
        status, location = response.status, response.getheader("Location")
        return status, location
    except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
        raise SourceInputError("CASE_SOURCE_RESOLUTION_FAILED", "短链接暂时无法解析，请稍后重试。") from exc
    finally:
        connection.close()


def resolve_douyin_source_input(
    raw_input: str,
    *,
    request_location: Callable[[str], tuple[int, str | None]] | None = None,
) -> DouyinSourceInput:
    request_location = request_location or _request_location
    raw = raw_input.strip()
    if not raw or len(raw) > MAX_INPUT_LENGTH:
        raise SourceInputError("CASE_URL_INVALID", "暂时没有识别到抖音视频链接。")
    candidates = [match.group(0).rstrip(",.，。；;：:！!？?、\"'」》】")
                  for match in URL_RE.finditer(raw)]
    supported = []
    for candidate in candidates:
        try:
            _validated_url(candidate)
        except SourceInputError:
            continue
        if candidate not in supported:
            supported.append(candidate)
    if not supported:
        raise SourceInputError("CASE_URL_INVALID", "暂时没有识别到抖音视频链接。")
    if len(supported) != 1:
        raise SourceInputError("CASE_MULTIPLE_SOURCE_URLS", "检测到多个视频链接，请只保留一个视频后重新提交。")
    extracted = supported[0]
    host, _ = _validated_url(extracted)
    input_kind = "share_text" if raw != extracted else "short_url" if host == "v.douyin.com" else "full_url"
    current = extracted
    if host == "v.douyin.com":
        current = "https://" + current.removeprefix("http://").removeprefix("https://")
        seen = set()
        first_hop = True
        for _ in range(MAX_REDIRECTS + 1):
            _validated_url(current, network=True)
            if current in seen:
                raise SourceInputError("CASE_SOURCE_REDIRECT_LOOP", "短链接发生循环跳转。")
            seen.add(current)
            if not first_hop:
                video_id = video_id_from_url(current)
                if video_id:
                    break
                _reject_non_video_page(current)
            first_hop = False
            try:
                status, location = request_location(current)
            except TimeoutError as exc:
                raise SourceInputError("CASE_SOURCE_RESOLUTION_FAILED", "短链接暂时无法解析，请稍后重试。") from exc
            if not (300 <= status < 400 and location):
                raise SourceInputError("CASE_SOURCE_IDENTITY_UNRESOLVED", "暂时无法确认这个视频的编号。")
            current = urljoin(current, location)
            _validated_url(current, network=True)
        else:
            raise SourceInputError("CASE_SOURCE_REDIRECT_LIMIT", "短链接跳转次数过多。")
    else:
        video_id = video_id_from_url(current)
    if not video_id:
        _reject_non_video_page(current)
        raise SourceInputError("CASE_SOURCE_IDENTITY_UNRESOLVED", "暂时无法确认这个视频的编号。")
    return DouyinSourceInput(
        input_kind=input_kind,
        extracted_url=extracted,
        canonical_url=f"https://www.douyin.com/video/{video_id}",
        video_id=video_id,
    )
