"""GN-031 groundwork: resolve permitted public YouTube Live audio using yt-dlp.

Not marked complete until a permitted real live URL is tested. No cookies, DRM,
logins or browser sessions are used. The resulting signed URL is ephemeral and
is not stored or exposed through the web API.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass
import json
import shutil
from typing import AsyncIterator

from app.audio_capture import CaptureError, pcm_chunks
from app.contracts import AudioSource
from app.source_validation import validate_source_urls
from app.storage import StoreConflict


@dataclass(frozen=True, slots=True)
class ResolvedLiveAudio:
    url: str
    format_id: str
    headers: dict[str, str]


async def resolve_live_audio(
    source: AudioSource, *, yt_dlp_binary: str = "yt-dlp", timeout: float = 35
) -> ResolvedLiveAudio:
    if source.kind != "youtube" or not source.enabled or not source.url:
        raise CaptureError("An enabled public YouTube source URL is required")
    try:
        validate_source_urls([source])
    except StoreConflict as exc:
        raise CaptureError(str(exc)) from exc
    executable = shutil.which(yt_dlp_binary)
    if executable is None:
        raise CaptureError("yt-dlp not found; install it and add it to PATH")
    command = [
        executable, "--ignore-config", "--no-playlist", "--skip-download",
        "--dump-single-json", "--no-warnings", "--", source.url,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise CaptureError("Could not start yt-dlp") from exc
    try:
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise CaptureError("YouTube live resolution timed out") from exc
        if process.returncode != 0:
            raise CaptureError("YouTube Live unavailable or restricted; no login/DRM bypass attempted")
        if len(stdout) > 4_000_000:
            raise CaptureError("YouTube metadata response is too large")
        try:
            metadata = json.loads(stdout)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CaptureError("yt-dlp returned invalid metadata") from exc
        if metadata.get("is_live") is not True and metadata.get("live_status") != "is_live":
            raise CaptureError("The YouTube broadcast is not currently live")
        formats = [
            item for item in metadata.get("formats", [])
            if item.get("acodec") not in (None, "none")
            and item.get("vcodec") in (None, "none") and item.get("url")
        ]
        if not formats:
            raise CaptureError("No publicly accessible audio-only format was offered")
        selected = max(formats, key=lambda item: float(item.get("abr") or 0))
        url = selected["url"]
        if not isinstance(url, str):
            raise CaptureError("Invalid yt-dlp audio URL")
        stream_source = AudioSource(
            id=source.id, name=source.name, kind="radio", url=url,
            enabled=True, status="offline",
        )
        try:
            validate_source_urls([stream_source])
        except StoreConflict as exc:
            raise CaptureError("yt-dlp returned a non-public/non-HTTP stream") from exc
        headers = {}
        for key, value in selected.get("http_headers", {}).items():
            if (key.lower() in {"user-agent", "referer", "origin", "accept"}
                    and isinstance(value, str) and "\r" not in value and "\n" not in value):
                headers[key] = value
        return ResolvedLiveAudio(url=url, format_id=str(selected.get("format_id", "audio")),
                                 headers=headers)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def youtube_pcm_chunks(
    source: AudioSource, *, yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg", chunk_ms: int = 500,
) -> AsyncIterator[bytes]:
    """Resolve a live audio-only URL and pass it through GN-030's PCM converter."""
    live = await resolve_live_audio(source, yt_dlp_binary=yt_dlp_binary)
    audio_source = AudioSource(id=source.id, name=source.name, kind="radio",
                               url=live.url, enabled=True, status="offline")
    async with aclosing(pcm_chunks(audio_source, ffmpeg_binary=ffmpeg_binary,
                                   chunk_ms=chunk_ms, http_headers=live.headers)) as pcm:
        async for chunk in pcm:
            yield chunk
