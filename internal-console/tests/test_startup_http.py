"""The public shell loads without granting business or session authority."""
import re

from conftest import login_and_change_password


def test_startup_resources_auth_and_security_headers(client):
    shell = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert shell.status_code == 200
    assert shell.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in shell.headers["content-security-policy"]
    assert shell.headers["x-content-type-options"] == "nosniff"
    loader = re.search(r'<script defer src="([^"]+)" data-app-entry="([^"]+)"', shell.text)
    assert loader
    for path in loader.groups():
        response = client.get(path)
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert "must-revalidate" in response.headers["cache-control"]
    assert client.get("/api/auth/me").status_code == 401
    csrf = login_and_change_password(client)
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_https_proxy_session_retains_secure_cookie_and_csrf(settings):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.main import build_app
    from app.auth_service import provision_user

    secure = replace(settings, secure_cookies=True)
    with TestClient(build_app(secure), base_url="https://ops.jingtang.cc",
                    headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "ops.jingtang.cc"}) as client:
        provision_user(secure.database_path, "13800000000")
        login = client.post("/api/auth/login", json={"phone": "13800000000", "password": "123456"})
        assert login.status_code == 200
        cookie = login.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=strict" in cookie
        assert client.get("/api/auth/me").status_code == 200
        assert client.post("/api/auth/logout", headers={"Origin": "https://untrusted.invalid"}).status_code == 403
        assert client.post("/api/auth/logout", headers={
            "Origin": "https://ops.jingtang.cc", "X-CSRF-Token": login.json()["csrf_token"]}).status_code == 200
        assert client.get("/api/auth/me").status_code == 401
