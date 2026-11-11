"""GN-032: validate metadata/URLs before storing radio or public YouTube sources.

Metadata validation alone cannot stop SSRF. GN-090 adds a separate DNS-pinned
loopback relay for runtime HTTP(S) streaming, redirects and HLS references.
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from app.contracts import AudioSource
from app.storage import StoreConflict


YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
                 "music.youtube.com", "youtu.be", "www.youtu.be"}


def validate_source_urls(sources: list[AudioSource]) -> None:
    for source in sources:
        if source.url is None:
            # A placeholder is valid configuration, but cannot be captured yet.
            continue
        url = source.url
        if (not url or url != url.strip() or len(url) > 2048
                or any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in url)):
            raise StoreConflict("Source URL must be trimmed, valid and contain no control characters")
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").lower().rstrip(".")
            port = parts.port
        except ValueError as exc:
            raise StoreConflict("Malformed source URL") from exc
        if (parts.scheme not in ("http", "https") or not host
                or parts.username is not None or parts.password is not None
                or parts.fragment or port == 0):
            raise StoreConflict("Only public HTTP(S) URLs without credentials/fragments are allowed")
        if (host in ("localhost", "localhost.localdomain") or
                host.endswith((".localhost", ".local", ".internal")) or
                "." not in host):
            raise StoreConflict("Local network URLs are not supported")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is None and (re.fullmatch(r"[0-9.]+", host)
                           or host.startswith("0x")
                           or re.match(r"^0[0-9]+(?:\.|$)", host)):
            # Do not accept shortened, integer, hex or octal IPv4 spellings.
            raise StoreConflict("Ambiguous numeric host is forbidden")
        if ip is not None and not ip.is_global:
            raise StoreConflict("Non-public source IP addresses are forbidden")
        if source.kind == "youtube":
            if parts.scheme != "https" or host not in YOUTUBE_HOSTS:
                raise StoreConflict("YouTube sources require a public youtube.com or youtu.be HTTPS URL")
            if host.endswith("youtu.be"):
                valid = parts.path.strip("/") != ""
            else:
                valid = (parts.path == "/watch" and bool(parts.query)
                         or parts.path.startswith(("/live/", "/shorts/", "/@")))
            if not valid:
                raise StoreConflict("Provide a direct YouTube video/live URL")
