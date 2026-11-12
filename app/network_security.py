"""GN-093: fail-closed HTTP/WebSocket network access protection.

Default mode allows loopback clients only. Opt-in remote mode requires HTTPS,
a high-entropy token and signed HttpOnly Secure browser session cookies.
No credentials or session contents are written to application logs.
"""
from __future__ import annotations

from dataclasses import dataclass
from http.cookies import CookieError, SimpleCookie
import hashlib
import hmac
import ipaddress
import os
import secrets
import time
from urllib.parse import parse_qs

SESSION_COOKIE = "__Host-game_now_session"
SESSION_SECONDS = 8 * 3600
_SESSION_MAX_BYTES = 4096

_LOGIN_FORM = b"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Game Now - Acesso protegido</title>
<style>body{font:1rem system-ui,sans-serif;max-width:30rem;margin:10vh auto;padding:1rem}
input,button{font:inherit;padding:.65rem;width:100%;box-sizing:border-box;margin:.5rem 0}</style>
</head><body><h1>Game Now</h1><p>Informe o token de acesso ao servidor.</p>
<form action="/_auth/login" method="post" autocomplete="off">
<label for="token">Token de acesso</label><input type="password" id="token" name="token"
required autocomplete="off" maxlength="256"><button type="submit">Entrar</button>
</form></body></html>"""


@dataclass(frozen=True)
class NetworkSecuritySettings:
    remote_access: bool = False
    access_token: str | None = None
    session_secret: str | None = None

    def __post_init__(self) -> None:
        if self.remote_access:
            if (self.access_token is None or len(self.access_token) < 32
                    or len(self.access_token) > 256
                    or not all(33 <= ord(c) <= 126 for c in self.access_token)):
                raise ValueError("Remote access requires a random 32+ character printable token")
            if (self.session_secret is None or len(self.session_secret) < 32
                    or self.session_secret == self.access_token):
                raise ValueError("Remote access needs an independent 32+ character session secret")
        elif self.access_token or self.session_secret:
            raise ValueError("Remote credentials require GAME_NOW_REMOTE_ACCESS=1")

    @classmethod
    def from_environment(cls) -> "NetworkSecuritySettings":
        value = os.getenv("GAME_NOW_REMOTE_ACCESS", "0")
        if value not in ("0", "1"):
            raise ValueError("GAME_NOW_REMOTE_ACCESS must be 0 or 1")
        return cls(
            remote_access=value == "1",
            access_token=os.getenv("GAME_NOW_ACCESS_TOKEN"),
            session_secret=os.getenv("GAME_NOW_SESSION_SECRET"),
        )


def is_loopback_peer(address: str | None) -> bool:
    # Starlette's in-process TestClient uses a non-network peer.
    if address == "testclient":
        return True
    try:
        parsed = ipaddress.ip_address(address or "")
    except ValueError:
        return False
    if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped is not None:
        parsed = parsed.ipv4_mapped
    return parsed.is_loopback


def _headers(scope: dict) -> dict[str, str]:
    return {key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])}


def _local_host_allowed(host: str) -> bool:
    authority = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return authority in ("localhost", "127.0.0.1", "testserver", "[::1]")


def _is_https(scope: dict) -> bool:
    return scope.get("scheme") in ("https", "wss")


def _same_origin(scope: dict, headers: dict[str, str]) -> bool:
    origin = headers.get("origin")
    if not origin:
        return False
    scheme = "https" if _is_https(scope) else "http"
    return origin == f"{scheme}://{headers.get('host', '')}"


def _session_cookie(settings: NetworkSecuritySettings, *, now: int | None = None) -> str:
    expires = int(time.time()) + SESSION_SECONDS if now is None else now + SESSION_SECONDS
    value = f"{expires}.{secrets.token_hex(16)}"
    signature = hmac.new(
        settings.session_secret.encode("utf-8"), value.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{value}.{signature}"


def _session_valid(settings: NetworkSecuritySettings, raw: str, *, now: int | None = None) -> bool:
    if not raw or len(raw) > 256:
        return False
    fields = raw.split(".")
    if len(fields) != 3:
        return False
    timestamp, nonce, signature = fields
    try:
        expires = int(timestamp)
    except ValueError:
        return False
    current = int(time.time()) if now is None else now
    if not (current < expires <= current + SESSION_SECONDS):
        return False
    if len(nonce) != 32 or len(signature) != 64:
        return False
    signed = f"{timestamp}.{nonce}"
    expected = hmac.new(
        settings.session_secret.encode("utf-8"), signed.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _authentication(settings: NetworkSecuritySettings, headers: dict[str, str]) -> str | None:
    expected = "Bearer " + settings.access_token
    supplied = headers.get("authorization", "")
    if len(supplied) <= len(expected) + 16 and hmac.compare_digest(supplied, expected):
        return "bearer"
    try:
        cookies = SimpleCookie()
        cookies.load(headers.get("cookie", "")[:_SESSION_MAX_BYTES])
        cookie = cookies.get(SESSION_COOKIE)
    except CookieError:
        return None
    if cookie is not None and _session_valid(settings, cookie.value):
        return "cookie"
    return None


def _security_headers(remote: bool) -> list[tuple[bytes, bytes]]:
    result = [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
              (b"referrer-policy", b"no-referrer"), (b"x-frame-options", b"DENY")]
    if remote:
        result.append((b"strict-transport-security", b"max-age=31536000"))
    return result


async def _http_response(
    send, status: int, body: bytes = b"", *, remote: bool = False,
    extra: list[tuple[bytes, bytes]] | None = None, html: bool = False,
) -> None:
    headers = _security_headers(remote)
    headers.extend(extra or [])
    headers.append((
        b"content-type",
        b"text/html; charset=utf-8" if html else b"application/json; charset=utf-8",
    ))
    headers.append((b"content-length", str(len(body)).encode("ascii")))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _reject(scope: dict, send, status: int) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
    else:
        message = {
            400: b'{"detail":"Invalid host"}',
            401: b'{"detail":"Authentication required"}',
            403: b'{"detail":"Access denied"}',
            404: b'{"detail":"Not found"}',
        }.get(status, b'{"detail":"Access denied"}')
        await _http_response(send, status, message, remote=_is_https(scope))


class NetworkSecurityMiddleware:
    def __init__(self, app, *, settings: NetworkSecuritySettings) -> None:
        self.app = app
        self.settings = settings

    async def _login(self, scope, receive, send, headers) -> None:
        if not _is_https(scope):
            await _reject(scope, send, 403)
            return
        method = scope.get("method")
        if method == "GET":
            await _http_response(send, 200, _LOGIN_FORM, remote=True, html=True)
            return
        if method != "POST":
            await _reject(scope, send, 404)
            return
        if not _same_origin(scope, headers):
            await _reject(scope, send, 403)
            return
        if not headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
            await _reject(scope, send, 400)
            return
        body = bytearray()
        while True:
            event = await receive()
            if event["type"] != "http.request":
                await _reject(scope, send, 400)
                return
            body.extend(event.get("body", b""))
            if len(body) > 4096:
                await _reject(scope, send, 400)
                return
            if not event.get("more_body", False):
                break
        try:
            supplied = parse_qs(body.decode("utf-8"), strict_parsing=True).get("token", [""])[0]
        except (UnicodeDecodeError, ValueError):
            supplied = ""
        if len(supplied) > 256 or not hmac.compare_digest(supplied, self.settings.access_token):
            await _reject(scope, send, 401)
            return
        cookie = (
            f"{SESSION_COOKIE}={_session_cookie(self.settings)}; Path=/; "
            f"Max-Age={SESSION_SECONDS}; Secure; HttpOnly; SameSite=Strict"
        )
        await _http_response(
            send, 303, remote=True,
            extra=[(b"location", b"/"), (b"set-cookie", cookie.encode("ascii"))],
        )

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = _headers(scope)
        peer = (scope.get("client") or ("",))[0]
        if not self.settings.remote_access:
            if not is_loopback_peer(peer):
                await _reject(scope, send, 403)
                return
            if not _local_host_allowed(headers.get("host", "")):
                await _reject(scope, send, 400)
                return
            origin = headers.get("origin")
            unsafe_http = (scope["type"] == "http"
                           and scope.get("method") not in ("GET", "HEAD", "OPTIONS"))
            if origin and (scope["type"] == "websocket" or unsafe_http):
                if not _same_origin(scope, headers):
                    await _reject(scope, send, 403)
                    return
            await self.app(scope, receive, send)
            return

        if not _is_https(scope):
            await _reject(scope, send, 403)
            return
        if scope["type"] == "http" and scope["path"] == "/_auth/login":
            await self._login(scope, receive, send, headers)
            return
        auth = _authentication(self.settings, headers)
        if auth is None:
            if (scope["type"] == "http" and scope.get("method") == "GET"
                    and "text/html" in headers.get("accept", "")):
                await _http_response(
                    send, 303, remote=True, extra=[(b"location", b"/_auth/login")],
                )
            else:
                await _reject(scope, send, 401)
            return
        if scope["type"] == "websocket":
            # A browser automatically attaches cookies to a WebSocket request.
            # Require same-site Origin for cookie auth to block cross-site WS.
            if auth == "cookie" and not _same_origin(scope, headers):
                await _reject(scope, send, 403)
                return
            if "origin" in headers and not _same_origin(scope, headers):
                await _reject(scope, send, 403)
                return
        elif scope.get("method") not in ("GET", "HEAD", "OPTIONS"):
            if auth == "cookie" and not _same_origin(scope, headers):
                await _reject(scope, send, 403)
                return
            if "origin" in headers and not _same_origin(scope, headers):
                await _reject(scope, send, 403)
                return

        if scope["type"] == "http" and scope["path"] == "/_auth/logout":
            if scope["method"] != "POST":
                await _reject(scope, send, 404)
                return
            await _http_response(send, 303, remote=True, extra=[
                (b"location", b"/_auth/login"),
                (b"set-cookie",
                 f"{SESSION_COOKIE}=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict".encode()),
            ])
            return

        async def hardened_send(event):
            if event["type"] == "http.response.start":
                event = {**event, "headers": list(event.get("headers", [])) +
                         _security_headers(True)}
            await send(event)

        await self.app(scope, receive, hardened_send)
