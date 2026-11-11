"""GN-090: loopback-only relay for untrusted remote radio/HLS content.

FFmpeg sees only an ephemeral localhost URL. Every HTTP(S) request, including
redirects, HLS segments, keys and nested playlists, is resolved and connected
by this relay with a public-IP check and a DNS-pinned socket. No cookies or
user credentials are forwarded. This is not a substitute for an OS egress
firewall when processing arbitrary adversarial media with native decoders.
"""
from __future__ import annotations

import base64
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import re
import secrets
import socket
import threading
from urllib.parse import urljoin, urlsplit

MAX_REDIRECTS = 5
MAX_PLAYLIST_BYTES = 1_000_000
MAX_URL_BYTES = 4096
_CHUNK_BYTES = 64 * 1024
_URI_ATTRIBUTE = re.compile(r'(?P<name>\b(?:URI|SERVER-URI))="(?P<value>[^"\r\n]*)"', re.I)


class IngestSecurityError(ValueError):
    """Blocked network destination or unsupported unsafe media reference."""


class UpstreamStatusError(IngestSecurityError):
    """Remote HTTP response unavailable for playback, without sensitive data."""

    def __init__(self, status: int):
        self.status = status
        super().__init__("Remote media HTTP error")


def _parse_public_url(url: str):
    if (not isinstance(url, str) or len(url.encode("utf-8")) > MAX_URL_BYTES
            or not url or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url)):
        raise IngestSecurityError("Invalid or unsafe stream URL")
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise IngestSecurityError("Malformed stream URL") from exc
    try:
        literal_ip = ipaddress.ip_address(host.rstrip(".")) if host else None
    except ValueError:
        literal_ip = None
    if (parts.scheme not in {"https", "http"} or not host or parts.fragment
            or parts.username is not None or parts.password is not None
            or port == 0 or ("." not in host and literal_ip is None)):
        raise IngestSecurityError("Only public HTTP(S) destinations are allowed")
    host = host.rstrip(".").lower()
    if (not host or host in {"localhost", "localhost.localdomain"}
            or host.endswith((".localhost", ".local", ".internal"))):
        raise IngestSecurityError("Local destinations are forbidden")
    try:
        parsed_ip = ipaddress.ip_address(host)
    except ValueError:
        parsed_ip = None
    if parsed_ip is not None and not parsed_ip.is_global:
        raise IngestSecurityError("Non-public IP address forbidden")
    return parts, host, port or (443 if parts.scheme == "https" else 80)


def _public_addresses(host: str, port: int) -> list[str]:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise IngestSecurityError("Could not resolve public stream host") from exc
    if not records:
        raise IngestSecurityError("No stream DNS results")
    addresses = [record[4][0] for record in records]
    try:
        parsed = [ipaddress.ip_address(address) for address in addresses]
    except ValueError as exc:
        raise IngestSecurityError("Invalid DNS result") from exc
    if any(not address.is_global for address in parsed):
        raise IngestSecurityError("Non-public DNS result forbidden")
    return addresses


def _connect_pinned(url: str, headers: dict[str, str]):
    parts, host, port = _parse_public_url(url)
    ip = _public_addresses(host, port)[0]
    connection_type = (http.client.HTTPSConnection if parts.scheme == "https"
                       else http.client.HTTPConnection)
    connection = connection_type(host, port, timeout=10)
    # The HTTP Host and TLS SNI/certificate identity remain the original host,
    # while the actual TCP connection is pinned to the checked public address.
    connection._create_connection = lambda address, timeout, source_address=None: (  # noqa: SLF001
        socket.create_connection((ip, port), timeout, source_address)
    )
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    try:
        connection.request("GET", path, headers={
            "User-Agent": "GameNow/1.0", "Accept": "*/*", **headers,
        })
        return connection, connection.getresponse()
    except Exception:
        connection.close()
        raise


def _open_redirects(url: str, headers: dict[str, str]):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        connection, response = _connect_pinned(current, headers)
        if response.status not in {301, 302, 303, 307, 308}:
            return connection, response, current
        location = response.getheader("Location")
        connection.close()
        if not location:
            raise IngestSecurityError("Redirect without destination")
        current = urljoin(current, location)
        _parse_public_url(current)
    raise IngestSecurityError("Too many remote redirects")


def _encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")


def _relay_path(url: str) -> str:
    filename = urlsplit(url).path.rsplit("/", 1)[-1]
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not re.fullmatch(r"[a-z0-9]{1,6}", extension or ""):
        extension = "ts"  # HLS segments sometimes have extensionless signed URLs.
    return f"{_encode_url(url)}/media.{extension}"


def _decode_url(encoded: str) -> str:
    if not encoded or len(encoded) > 5500 or not re.fullmatch(r"[A-Za-z0-9_-]+", encoded):
        raise IngestSecurityError("Invalid relay URL")
    try:
        url = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_",
                               validate=True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise IngestSecurityError("Invalid encoded relay URL") from exc
    _parse_public_url(url)
    return url


def _rewrite_playlist(payload: bytes, base_url: str, relay_prefix: str) -> bytes:
    if len(payload) > MAX_PLAYLIST_BYTES:
        raise IngestSecurityError("HLS playlist exceeds safe limit")
    try:
        contents = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise IngestSecurityError("HLS playlist is not UTF-8") from exc
    if not contents.startswith("#EXTM3U"):
        raise IngestSecurityError("Not a valid HLS playlist")
    if "{$" in contents or "#EXT-X-DEFINE" in contents:
        raise IngestSecurityError("Variable HLS URL references are not supported")

    def relay_uri(reference: str) -> str:
        target = urljoin(base_url, reference)
        _parse_public_url(target)
        return f"{relay_prefix}/{_relay_path(target)}"

    lines = []
    for line in contents.splitlines(keepends=True):
        text = line.strip()
        if not text:
            lines.append(line)
        elif text.startswith("#"):
            # HLS URI attributes can appear on encryption keys, maps, parts,
            # audio renditions, prefetches and nested variant manifests.
            updated = _URI_ATTRIBUTE.sub(
                lambda match: f'{match.group("name")}="{relay_uri(match.group("value"))}"',
                line,
            )
            # Reject unknown URL attributes rather than letting FFmpeg fetch
            # a network address outside the relay.
            if re.search(r'(?i)\b(?:https?://|ftp://)', updated.replace(relay_prefix, "")):
                raise IngestSecurityError("Unrewritten HLS network reference")
            lines.append(updated)
        else:
            trailing = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            lines.append(relay_uri(text) + trailing)
    return "".join(lines).encode("utf-8")


class SafeMediaRelay:
    """Private, disposable local ingress; use as a context manager for FFmpeg."""

    def __init__(self, url: str, *, http_headers: dict[str, str] | None = None):
        _parse_public_url(url)
        self._url = url
        self._headers: dict[str, str] = {}
        for key, value in (http_headers or {}).items():
            if (not isinstance(key, str) or key.lower() not in
                    {"user-agent", "referer", "origin", "accept"} or
                    not isinstance(value, str) or len(value) > 1024 or
                    any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise IngestSecurityError("Unsupported media request header")
            self._headers[key] = value
        self._token = secrets.token_urlsafe(24)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._failure: str | None = None

    @property
    def failure_reason(self) -> str | None:
        """Safe diagnostic code, never a URL, hostname, header or token."""
        return self._failure

    def __enter__(self) -> "SafeMediaRelay":
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return  # Never log signed stream URLs or capability tokens.

            def do_GET(self):
                try:
                    prefix = f"/{relay._token}/"
                    if not self.path.startswith(prefix):
                        self.send_error(404)
                        return
                    target = _decode_url(self.path[len(prefix):].split("/", 1)[0])
                    forward_headers = dict(relay._headers)
                    ranges = self.headers.get("Range")
                    if ranges is not None:
                        if len(ranges) > 128 or re.fullmatch(r"bytes=\d+-\d*", ranges) is None:
                            raise IngestSecurityError("Invalid byte range")
                        forward_headers["Range"] = ranges
                    connection, upstream, final_url = _open_redirects(target, forward_headers)
                    try:
                        if upstream.status not in (200, 206):
                            raise UpstreamStatusError(upstream.status)
                        media_type = (upstream.getheader("Content-Type") or "").lower()
                        opening = upstream.read(7)
                        playlist = (urlsplit(final_url).path.lower().endswith(".m3u8")
                                    or "mpegurl" in media_type or opening == b"#EXTM3U")
                        if playlist:
                            data = opening + upstream.read(MAX_PLAYLIST_BYTES + 1 - len(opening))
                            if len(data) > MAX_PLAYLIST_BYTES:
                                raise IngestSecurityError("HLS playlist exceeds safe limit")
                            prefix_url = f"http://127.0.0.1:{relay._server.server_port}{prefix[:-1]}"
                            body = _rewrite_playlist(data, final_url, prefix_url)
                            self.send_response(200)
                            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                            self.send_header("Content-Length", str(len(body)))
                            self.send_header("Cache-Control", "no-store")
                            self.end_headers()
                            self.wfile.write(body)
                        else:
                            self.send_response(upstream.status)
                            self.send_header("Content-Type", "application/octet-stream")
                            for name in ("Content-Length", "Content-Range", "Accept-Ranges"):
                                value = upstream.getheader(name)
                                if value:
                                    self.send_header(name, value)
                            self.send_header("Cache-Control", "no-store")
                            self.end_headers()
                            if opening:
                                self.wfile.write(opening)
                            while True:
                                chunk = upstream.read(_CHUNK_BYTES)
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                    finally:
                        connection.close()
                except (IngestSecurityError, OSError, http.client.HTTPException,
                        UnicodeError, ValueError) as exc:
                    # Diagnose the source without exposing signed URLs, tokens,
                    # hostnames or arbitrary response content.
                    if isinstance(exc, UpstreamStatusError):
                        relay._failure = f"upstream_http_{exc.status}"
                    elif isinstance(exc, IngestSecurityError):
                        relay._failure = "destination_or_playlist_rejected"
                    else:
                        relay._failure = "transport_error"
                    try:
                        self.send_error(502, "Remote media rejected")
                    except OSError:
                        pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def input_url(self) -> str:
        if self._server is None:
            raise RuntimeError("Relay not started")
        return f"http://127.0.0.1:{self._server.server_port}/{self._token}/{_relay_path(self._url)}"

    def __exit__(self, *_exc):
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None
