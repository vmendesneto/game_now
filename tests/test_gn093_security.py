"""GN-093: fail-closed LAN HTTP/WebSocket, login and browser session."""
from __future__ import annotations

import asyncio
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.network_security import (
    NetworkSecurityMiddleware, NetworkSecuritySettings, SESSION_COOKIE,
    _session_cookie, _session_valid, is_loopback_peer,
)
from scripts.serve_secure import validate_server

TOKEN = "t" * 40
SECRET = "s" * 40


def test_network_settings_fail_closed_and_require_independent_secrets(monkeypatch):
    for key in ("GAME_NOW_REMOTE_ACCESS", "GAME_NOW_ACCESS_TOKEN", "GAME_NOW_SESSION_SECRET"):
        monkeypatch.delenv(key, raising=False)
    assert NetworkSecuritySettings.from_environment().remote_access is False
    monkeypatch.setenv("GAME_NOW_REMOTE_ACCESS", "1")
    with pytest.raises(ValueError, match="token"):
        NetworkSecuritySettings.from_environment()
    monkeypatch.setenv("GAME_NOW_ACCESS_TOKEN", "weak")
    with pytest.raises(ValueError, match="token"):
        NetworkSecuritySettings.from_environment()
    monkeypatch.setenv("GAME_NOW_ACCESS_TOKEN", TOKEN)
    with pytest.raises(ValueError, match="session secret"):
        NetworkSecuritySettings.from_environment()
    monkeypatch.setenv("GAME_NOW_SESSION_SECRET", TOKEN)
    with pytest.raises(ValueError, match="session secret"):
        NetworkSecuritySettings.from_environment()
    monkeypatch.setenv("GAME_NOW_SESSION_SECRET", SECRET)
    assert NetworkSecuritySettings.from_environment().remote_access
    monkeypatch.setenv("GAME_NOW_REMOTE_ACCESS", "unexpected")
    with pytest.raises(ValueError, match="GAME_NOW_REMOTE_ACCESS"):
        NetworkSecuritySettings.from_environment()


def test_loopback_and_server_bind_policy(tmp_path):
    local = NetworkSecuritySettings()
    remote = NetworkSecuritySettings(True, TOKEN, SECRET)
    for addr in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "testclient"):
        assert is_loopback_peer(addr)
    for addr in ("192.0.2.4", "10.10.1.2", "unknown", ""):
        assert not is_loopback_peer(addr)
    validate_server("127.0.0.1", None, None, local)
    with pytest.raises(ValueError, match="Non-loopback"):
        validate_server("0.0.0.0", None, None, local)
    with pytest.raises(ValueError, match="TLS"):
        validate_server("0.0.0.0", None, None, remote)
    with pytest.raises(ValueError, match="numeric"):
        validate_server("example.com", None, None, remote)
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert.write_text("test")
    key.write_text("test")
    validate_server("0.0.0.0", str(cert), str(key), remote)


async def _raw_rejection(scope_type: str, peer: str):
    async def app(scope, receive, send):
        raise AssertionError("Insecure remote traffic must never reach the app")
    guard = NetworkSecurityMiddleware(app, settings=NetworkSecuritySettings())
    sent = []
    scope = {
        "type": scope_type,
        "client": (peer, 55123),
        "path": "/health" if scope_type == "http" else "/ws",
        "method": "GET",
        "scheme": "http" if scope_type == "http" else "ws",
        "headers": [(b"host", b"localhost:8000")],
    }
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(msg):
        sent.append(msg)
    await guard(scope, receive, send)
    return sent


def test_direct_remote_access_denied_even_when_server_bound_widely():
    assert asyncio.run(_raw_rejection("http", "192.0.2.1"))[0]["status"] == 403
    assert asyncio.run(_raw_rejection("websocket", "192.0.2.1"))[0]["code"] == 1008


def test_default_local_http_and_websocket_compatible(tmp_path):
    with TestClient(create_app(tmp_path / "local.sqlite3")) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health", headers={"Host": "attacker.invalid"}).status_code == 400
        assert client.post("/api/demo/next", headers={"Origin": "https://evil.test"}).status_code == 403
        with client.websocket_connect("/ws") as sock:
            assert sock.receive_json()
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect("/ws", headers={"Origin": "http://evil.test"}):
                pass
        assert closed.value.code == 1008


def test_remote_tls_login_bearer_cookie_origin_and_websocket(monkeypatch, tmp_path):
    monkeypatch.setenv("GAME_NOW_REMOTE_ACCESS", "1")
    monkeypatch.setenv("GAME_NOW_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("GAME_NOW_SESSION_SECRET", SECRET)
    app = create_app(tmp_path / "remote.sqlite3")

    with TestClient(app, base_url="http://testserver") as plain:
        assert plain.get("/health").status_code == 403
        assert plain.get("/_auth/login").status_code == 403

    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/health").status_code == 401
        response = client.get("/", headers={"Accept": "text/html"}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/_auth/login"
        assert "password" in client.get("/_auth/login").text
        assert client.post("/_auth/login", data={"token": TOKEN},
                           headers={"Origin": "https://evil.test"}).status_code == 403
        assert client.post("/_auth/login", data={"token": "á"},
                           headers={"Origin": "https://testserver"}).status_code == 401
        assert client.post("/_auth/login", data={"token": "wrong"},
                           headers={"Origin": "https://testserver"}).status_code == 401
        response = client.post(
            "/_auth/login", data={"token": TOKEN},
            headers={"Origin": "https://testserver"}, follow_redirects=False,
        )
        assert response.status_code == 303
        cookie = response.headers["set-cookie"]
        assert SESSION_COOKIE in cookie
        assert all(part in cookie for part in ("Secure", "HttpOnly", "SameSite=Strict"))
        assert TOKEN not in cookie
        assert response.headers["strict-transport-security"]
        assert client.get("/health").status_code == 200
        assert client.get("/api/state").status_code == 200
        assert client.post("/api/demo/next").status_code == 403
        assert client.post("/api/demo/next",
                           headers={"Origin": "https://evil.test"}).status_code == 403
        assert client.post("/api/demo/next",
                           headers={"Origin": "https://testserver"}).status_code == 200

        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect("wss://testserver/ws", headers={"Origin": "https://evil.test"}):
                pass
        assert closed.value.code == 1008
        with client.websocket_connect("wss://testserver/ws", headers={"Origin": "https://testserver"}) as sock:
            assert sock.receive_json()
        assert client.post("/_auth/logout",
                           headers={"Origin": "https://testserver"},
                           follow_redirects=False).status_code == 303
        assert client.get("/api/state").status_code == 401

    with TestClient(app, base_url="https://testserver") as api:
        assert api.get("/health", headers={"Authorization": "Bearer " + TOKEN}).status_code == 200
        assert api.post("/api/demo/next", headers={"Authorization": "Bearer " + TOKEN}).status_code == 200
        with api.websocket_connect("wss://testserver/ws", headers={"Authorization": "Bearer " + TOKEN}) as ws:
            assert ws.receive_json()
        assert api.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_session_expiration_signature_and_secrets():
    settings = NetworkSecuritySettings(True, TOKEN, SECRET)
    now = int(datetime(2026, 11, 11).timestamp())
    value = _session_cookie(settings, now=now)
    assert SESSION_COOKIE.startswith("__Host-")
    assert _session_valid(settings, value, now=now)
    assert not _session_valid(settings, value, now=now + 8 * 3600)
    assert not _session_valid(settings, value + "bad", now=now)
    assert not _session_valid(settings, value + "é", now=now)
    assert not _session_valid(NetworkSecuritySettings(True, TOKEN, "z" * 40), value, now=now)
