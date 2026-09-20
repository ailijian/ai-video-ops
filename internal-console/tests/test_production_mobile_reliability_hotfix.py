from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from app.douyin_source_input import SourceInputError, resolve_douyin_source_input
from conftest import login_and_change_password

CASE_ID = "7999999999999999901"
FULL_URL = f"https://www.douyin.com/video/{CASE_ID}"
SHORT_URL = "https://v.douyin.com/OUUqMAZ3SvY/"
SHARE_TEXT = (
    "8.71 复制打开抖音，看看【天台SASA服饰的作品】我们会用心倾听，"
    "每一位顾客的需求 # 同城好店推荐... "
    f"{SHORT_URL} RXZ:/ N@j.cN 08/10 :8pm"
)


def redirect_to_case(url: str) -> tuple[int, str]:
    assert url == SHORT_URL
    return 302, FULL_URL


@pytest.mark.parametrize(
    ("raw", "kind"),
    [(FULL_URL, "full_url"), (f"https://www.iesdouyin.com/share/video/{CASE_ID}/", "full_url"),
     (SHORT_URL, "short_url"), (SHARE_TEXT, "share_text"),
     (SHARE_TEXT.replace(SHORT_URL, f"[{SHORT_URL}]({SHORT_URL})"), "share_text"),
     (f"复制，{SHORT_URL}。", "share_text"),
     (f"复制{SHORT_URL}查看视频", "share_text")],
)
def test_source_input_resolves_one_canonical_video(raw, kind):
    result = resolve_douyin_source_input(raw, request_location=redirect_to_case)
    assert result.input_kind == kind
    assert result.canonical_url == FULL_URL
    assert result.video_id == CASE_ID


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("没有链接", "CASE_URL_INVALID"),
        ("https://example.com/video/7999999999999999901", "CASE_URL_INVALID"),
        (f"{FULL_URL} https://www.douyin.com/video/7999999999999999902", "CASE_MULTIPLE_SOURCE_URLS"),
        (f"{FULL_URL},https://www.douyin.com/video/7999999999999999902", "CASE_MULTIPLE_SOURCE_URLS"),
        ("https://www.douyin.com/", "CASE_SOURCE_IDENTITY_UNRESOLVED"),
    ],
)
def test_source_input_fails_closed_for_ambiguous_or_unidentified_input(raw, code):
    with pytest.raises(SourceInputError, match=".") as error:
        resolve_douyin_source_input(raw, request_location=redirect_to_case)
    assert error.value.code == code


@pytest.mark.parametrize("destination", [
    "https://example.com/video/7999999999999999901",
    "http://www.douyin.com/video/7999999999999999901",
    "http://127.0.0.1/video/7999999999999999901",
    "file:///etc/passwd",
    "data:text/plain,hello",
])
def test_short_link_rejects_unsafe_redirects(destination):
    with pytest.raises(SourceInputError) as error:
        resolve_douyin_source_input(SHORT_URL, request_location=lambda _: (302, destination))
    assert error.value.code == "CASE_URL_INVALID"


def test_short_link_rejects_redirect_loop():
    with pytest.raises(SourceInputError) as error:
        resolve_douyin_source_input(SHORT_URL, request_location=lambda _: (302, SHORT_URL))
    assert error.value.code == "CASE_SOURCE_REDIRECT_LOOP"


def test_short_link_rejects_redirect_limit():
    count = 0

    def next_hop(_):
        nonlocal count
        count += 1
        return 302, f"https://v.douyin.com/hop{count}/"

    with pytest.raises(SourceInputError) as error:
        resolve_douyin_source_input(SHORT_URL, request_location=next_hop)
    assert error.value.code == "CASE_SOURCE_REDIRECT_LIMIT"


def test_short_link_timeout_and_missing_video_id_fail_closed():
    def timeout(_):
        raise socket.timeout("mock timeout")

    with pytest.raises(SourceInputError) as error:
        resolve_douyin_source_input(SHORT_URL, request_location=timeout)
    assert error.value.code == "CASE_SOURCE_RESOLUTION_FAILED"

    def no_identity(url):
        return (302, "https://www.douyin.com/") if url == SHORT_URL else (200, None)

    with pytest.raises(SourceInputError) as error:
        resolve_douyin_source_input(SHORT_URL, request_location=no_identity)
    assert error.value.code == "CASE_SOURCE_IDENTITY_UNRESOLVED"


def test_short_link_dns_private_address_is_rejected(monkeypatch):
    import app.douyin_source_input as resolver

    monkeypatch.setattr(resolver.socket, "getaddrinfo", lambda *_args, **_kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    with pytest.raises(SourceInputError) as error:
        resolver._public_address("v.douyin.com")
    assert error.value.code == "CASE_SOURCE_UNSAFE_REDIRECT"


def test_all_three_input_forms_hit_one_approved_case(client: TestClient, monkeypatch):
    import app.douyin_source_input as resolver

    monkeypatch.setattr(resolver, "_request_location", redirect_to_case)
    csrf = login_and_change_password(client)
    for raw in (FULL_URL, SHORT_URL, SHARE_TEXT):
        response = client.post(
            "/api/cases/analyze",
            headers={"X-CSRF-Token": csrf},
            json={"url": raw, "operator_profile_hint": "news"},
        )
        assert response.status_code == 200
        assert response.json()["duplicate_kind"] == "source_identity"
        assert response.json()["case_id"] == CASE_ID
    assert client.get("/api/tasks").json()["tasks"] == []


def test_all_three_input_forms_hit_one_active_task(client: TestClient, monkeypatch):
    import app.douyin_source_input as resolver

    case_id = "7999999999999999999"
    canonical = f"https://www.douyin.com/video/{case_id}"
    monkeypatch.setattr(resolver, "_request_location", lambda _: (302, canonical))
    csrf = login_and_change_password(client)
    tasks = []
    for raw in (canonical, SHORT_URL, SHARE_TEXT):
        response = client.post(
            "/api/cases/analyze",
            headers={"X-CSRF-Token": csrf},
            json={"url": raw, "operator_profile_hint": "news"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["case_id"] == case_id
        tasks.append((body.get("task") or body.get("existing_task"))["task_id"])
    assert len(set(tasks)) == 1
    assert len(client.get("/api/tasks").json()["tasks"]) == 1


def test_css_and_js_are_revalidated_but_images_keep_existing_cache_policy(client: TestClient):
    for asset in ("styles.css", "app.js", "task-progress.js"):
        response = client.get(f"/assets/{asset}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"
    image = client.get("/assets/brand/logo.png")
    assert image.status_code == 200
    assert image.headers.get("cache-control") != "no-cache, max-age=0, must-revalidate"
