"""GN-032: validate metadata/URLs before storing radio or public YouTube sources.

This is NOT a network allowlist for FFmpeg/yt-dlp. Network ingestion must revalidate
DNS results, redirects and final destinations to prevent SSRF/rebinding (GN-090).
"""
from __future__ import annotations

import ipaddress
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
        if not url or url != url.strip() or len(url) > 2048:
            raise StoreConflict("Source URL must be nonempty, trimmed and at most 2048 chars")
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
