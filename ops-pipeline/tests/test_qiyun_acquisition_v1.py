from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("qiyun_acquisition_v1", SCRIPTS / "qiyun_acquisition_v1.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

CASE_ID = "7687296010611280827"
SOURCE_URL = f"https://www.douyin.com/video/{CASE_ID}"
SHORT_URL = "https://v.douyin.com/OUUqMAZ3SvY/"
SIGNED_URL = "https://v26-luna.douyinvod.com/source.mp4?signature=must-not-be-retained"


def test_api_response_and_download_are_sanitized_and_bound_to_canonical_identity(tmp_path, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["url"] == SHORT_URL
            assert body["appId"] == "test-id"
            assert body["appKey"] == "test-key"
            return httpx.Response(200, json={"code": 200, "data": {
                "video_url": SIGNED_URL, "music_url": "https://music.example.test/private",
                "title": "测试标题", "author": {"name": "测试作者"},
            }})
        assert request.url == SIGNED_URL
        return httpx.Response(200, content=b"synthetic-mp4", headers={"Content-Length": "13"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setenv("QYAPI_APP_ID", "test-id")
    monkeypatch.setenv("QYAPI_APP_KEY", "test-key")
    monkeypatch.setattr(module, "_pace_provider_calls", lambda _: None)
    monkeypatch.setattr(module, "_safe_media_url", lambda url: url)
    monkeypatch.setattr(module.httpx, "Client", lambda **_: client)
    monkeypatch.setattr(module, "inspect_video", lambda _: {
        "duration_seconds": 13.3, "width": 2160, "height": 3840,
        "audio_present": True, "container": "mov,mp4", "video_codec": "hevc",
    })
    monkeypatch.setattr(module, "_audio_decodable", lambda _: True)
    root = tmp_path / "pipeline"
    attempt = root / "data" / "case_analysis_attempts" / CASE_ID / "attempt_0001"
    result = module.acquire_qiyun_media(
        pipeline_root=root, source_url=SOURCE_URL, case_id=CASE_ID,
        attempt_root=attempt, provider_source_url=SHORT_URL,
    )
    assert len(requests) == 2
    assert Path(result["video"]).read_bytes() == b"synthetic-mp4"
    assert result["metadata"]["canonical_source_url"] == SOURCE_URL
    assert result["metadata"]["stable_video_id"] == CASE_ID
    assert "must-not-be-retained" not in json.dumps(result)
    assert "test-key" not in json.dumps(result)
    assert "music.example.test" not in json.dumps(result)


def test_rate_limit_has_safe_error_without_retry():
    with pytest.raises(module.QiyunAcquisitionError) as error:
        module._parse_response(httpx.Response(400, json={"code": 3001, "msg": "secret provider text"}))
    assert error.value.code == "SOURCE_PROVIDER_RATE_LIMITED"
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("value", [
    "http://cdn.example.test/video.mp4", "file:///tmp/video.mp4",
    "https://127.0.0.1/video.mp4", "https://user:pass@cdn.example.test/video.mp4",
    "https://example.test/video.mp4",
])
def test_unsafe_media_urls_are_rejected(value, monkeypatch):
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (None, None, None, None, ("127.0.0.1", 443))
    ])
    with pytest.raises(module.QiyunAcquisitionError) as error:
        module._safe_media_url(value)
    assert error.value.code == "SOURCE_MEDIA_URL_UNSAFE"


def test_redirect_to_private_network_fails_closed(tmp_path, monkeypatch):
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
        302, headers={"Location": "http://127.0.0.1/internal"},
    )))
    monkeypatch.setattr(module.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (None, None, None, None, ("8.8.8.8", 443))
    ])
    with pytest.raises(module.QiyunAcquisitionError) as error:
        module._download(client, SIGNED_URL, tmp_path / "source.mp4")
    assert error.value.code == "SOURCE_MEDIA_URL_UNSAFE"


def test_missing_credentials_and_short_input_validation(tmp_path, monkeypatch):
    monkeypatch.delenv("QYAPI_APP_ID", raising=False)
    monkeypatch.delenv("QYAPI_APP_KEY", raising=False)
    with pytest.raises(module.QiyunAcquisitionError) as error:
        module.acquire_qiyun_media(pipeline_root=tmp_path, source_url=SOURCE_URL,
                                    case_id=CASE_ID, attempt_root=tmp_path / "attempt")
    assert error.value.code == "SOURCE_PROVIDER_NOT_CONFIGURED"


def test_cross_process_pacing_records_call_start_before_next_request(tmp_path, monkeypatch):
    clock = [1000.0]
    slept = []
    monkeypatch.setattr(module.time, "time", lambda: clock[0])

    def fake_sleep(seconds):
        slept.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    module._pace_provider_calls(tmp_path)
    module._pace_provider_calls(tmp_path)
    assert slept == [60.0]
    assert float((tmp_path / "data" / ".provider_rate" / "qiyun_last_call").read_text()) == 1060.0
