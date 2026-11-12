"""GN-031: resolve public YouTube live or recorded media via yt-dlp.

CLI diagnostics may process an authorized VOD/archived livestream without waiting
for a live game. No cookies, DRM, logins or browser sessions are used; temporary
signed CDN URLs are never saved or exposed via the web API.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
from dataclasses import dataclass
import json
import shutil
from typing import AsyncIterator
from urllib.parse import urlsplit

from app.audio_capture import CaptureError, pcm_chunks, validate_start_seconds
from app.contracts import AudioSource
from app.source_validation import validate_source_urls
from app.storage import StoreConflict


@dataclass(frozen=True, slots=True)
class ResolvedLiveAudio:
    """Kept for backwards compatibility; now also represents recorded media."""

    url: str
    format_id: str
    headers: dict[str, str]
    input_has_video: bool = False
    is_recording: bool = False


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
        executable, "--ignore-config", "--no-cache-dir", "--no-playlist", "--skip-download",
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
            raise CaptureError("YouTube media resolution timed out") from exc
        if process.returncode != 0:
            raise CaptureError("YouTube media unavailable or restricted; no login/DRM bypass attempted")
        if len(stdout) > 4_000_000:
            raise CaptureError("YouTube metadata response is too large")
        try:
            metadata = json.loads(stdout)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CaptureError("yt-dlp returned invalid metadata") from exc
        if not isinstance(metadata, dict):
            raise CaptureError("yt-dlp returned invalid metadata")
        # VOD is a first-class test source: standard recordings are not_live
        # and archived live streams are was_live. Upcoming/processing videos
        # are not decodable yet. If older yt-dlp versions omit live_status,
        # require an explicit live flag or a positive finite VOD duration.
        live_status = metadata.get("live_status")
        if live_status in {"is_upcoming", "post_live"}:
            raise CaptureError("The YouTube video is not yet available for playback")
        duration = metadata.get("duration")
        is_recording_without_status = (
            live_status is None
            and metadata.get("is_live") is False
            and isinstance(duration, (int, float))
            and not isinstance(duration, bool)
            and 0 < duration < float("inf")
        )
        if live_status not in {"is_live", "was_live", "not_live"} and not (
            live_status is None and metadata.get("is_live") is True
        ) and not is_recording_without_status:
            raise CaptureError("YouTube media is not a confirmed live or recorded video")
        if metadata.get("has_drm") is True or metadata.get("availability") in {
            "private", "premium_only", "subscriber_only", "needs_auth"
        }:
            raise CaptureError("YouTube media is restricted; no login/DRM bypass attempted")
        available = metadata.get("formats")
        if not isinstance(available, list):
            raise CaptureError("yt-dlp metadata has no valid formats list")
        # Prefer audio-only for both VOD and live. Some live HLS manifests
        # expose audio only inside a combined video/audio rendition.
        # In the fallback, FFmpeg -vn outputs PCM audio only; the input
        # transport can still transfer video bytes (never stored or served).
        def contains_audio(item: dict) -> bool:
            codec = item.get("acodec")
            if codec == "none":
                return False  # Explicitly silent, including video-only variants.
            if codec not in (None, ""):
                return True
            # YouTube HLS audio-only variants (e.g. format 233/234) can report
            # acodec=None. yt-dlp correctly labels them "audio only" because
            # vcodec="none". FFmpeg will verify the actual audio on decode.
            return (
                item.get("vcodec") == "none"
                and item.get("protocol") in ("m3u8", "m3u8_native")
            )

        sound_formats = [
            item for item in available
            if isinstance(item, dict) and not item.get("has_drm")
            and contains_audio(item)
            and isinstance(item.get("url"), str)
        ]
        audio_only = [
            item for item in sound_formats
            if item.get("vcodec") in (None, "none")
        ]
        muxed = [
            item for item in sound_formats
            if item.get("vcodec") not in (None, "none")
        ]
        if not audio_only and not muxed:
            raise CaptureError("No publicly accessible format containing audio was offered")

        def bitrate(item: dict, key: str) -> float:
            try:
                value = float(item.get(key) or 0)
                return value if 0 <= value < float("inf") else 0.0
            except (TypeError, ValueError):
                return 0.0

        if audio_only:
            # yt-dlp lists preferred qualities last; when HLS has no
            # advertised bitrate, choose the last one (234 over 233).
            selected = max(
                enumerate(audio_only),
                key=lambda pair: (
                    bitrate(pair[1], "abr"),
                    bitrate(pair[1], "tbr"),
                    pair[0],
                ),
            )[1]
            input_has_video = False
        else:
            # Lowest reported combined bitrate limits unnecessary transfer.
            selected = min(muxed, key=lambda item: bitrate(item, "tbr") or float("inf"))
            input_has_video = True
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
        raw_headers = selected.get("http_headers") or {}
        if not isinstance(raw_headers, dict):
            raise CaptureError("Invalid audio request headers in yt-dlp metadata")
        for key, value in raw_headers.items():
            if (key.lower() in {"user-agent", "referer", "origin", "accept"}
                    and isinstance(value, str) and "\r" not in value and "\n" not in value):
                headers[key] = value
        return ResolvedLiveAudio(
            url=url, format_id=str(selected.get("format_id", "audio")),
            headers=headers, input_has_video=input_has_video,
            is_recording=(live_status in {"was_live", "not_live"} or is_recording_without_status)
                         and metadata.get("is_live") is not True,
        )
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def _needs_playback_wait(url: str) -> bool:
    """Respect the wait yt-dlp uses for newly issued Googlevideo media URLs.

    Some public videoplayback URLs return HTTP 403 during the first ~5 seconds
    after extraction. This is not a retry or a workaround for restricted media.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https"
            and (host == "googlevideo.com" or host.endswith(".googlevideo.com"))
            and parts.path.rstrip("/").endswith("/videoplayback"))


async def youtube_pcm_chunks(
    source: AudioSource, *, yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg", chunk_ms: int = 500,
    start_seconds: float = 0,
) -> AsyncIterator[bytes]:
    """Decode audio from a public live broadcast or recorded YouTube video."""
    start_seconds = validate_start_seconds(start_seconds)
    live = await resolve_live_audio(source, yt_dlp_binary=yt_dlp_binary)
    if start_seconds and not live.is_recording:
        raise CaptureError("start_seconds requires a confirmed recorded video")
    if _needs_playback_wait(live.url):
        # The yt-dlp downloader waits before its first network read, but our
        # metadata-only resolver (--skip-download) would otherwise skip it.
        await asyncio.sleep(5.5)
    audio_source = AudioSource(id=source.id, name=source.name, kind="radio",
                               url=live.url, enabled=True, status="offline")
    seek = {"start_seconds": start_seconds} if start_seconds else {}
    async with aclosing(pcm_chunks(audio_source, ffmpeg_binary=ffmpeg_binary,
                                   chunk_ms=chunk_ms, http_headers=live.headers, **seek)) as pcm:
        async for chunk in pcm:
            yield chunk


async def youtube_diagnostic(
    source: AudioSource, *, duration: float = 5.0, yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg",
) -> dict:
    """Verify actual PCM decoding without saving or returning audio/media URLs."""
    if not 0 < duration <= 600:
        raise CaptureError("Diagnostic duration must be >0 and <=600 seconds")
    target_bytes = int(duration * 16_000 * 2)
    received = 0
    blocks = 0
    async with aclosing(youtube_pcm_chunks(
        source, yt_dlp_binary=yt_dlp_binary, ffmpeg_binary=ffmpeg_binary,
    )) as stream:
        async for block in stream:
            received += min(len(block), target_bytes - received)
            blocks += 1
            if received >= target_bytes:
                break
    if received == 0:
        raise CaptureError("YouTube media delivered no PCM samples")
    return {
        "source_id": source.id, "captured_at": datetime.now(timezone.utc).isoformat(),
        "sample_rate": 16_000, "channels": 1, "format": "s16le",
        "seconds": received / (16_000 * 2), "bytes": received, "chunks": blocks,
        "audio_retransmitted": False,
    }


def main() -> None:
    """Explicit CLI diagnostic for permitted live or recorded audio, no API media."""
    import argparse
    parser = argparse.ArgumentParser(
        description="GN-031: check public YouTube live or recorded audio (no playback)"
    )
    parser.add_argument("--url", required=True, help="Permitted public YouTube live/video URL")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    source = AudioSource(
        id="youtube-diagnostic", name="YouTube diagnostic", kind="youtube",
        url=args.url, enabled=True, status="offline",
    )
    try:
        stats = asyncio.run(youtube_diagnostic(
            source, duration=args.seconds, yt_dlp_binary=args.yt_dlp,
            ffmpeg_binary=args.ffmpeg,
        ))
        print(json.dumps(stats))
    except (CaptureError, OSError) as exc:
        parser.exit(status=1, message=f"Capture error: {exc}\n")


if __name__ == "__main__":
    main()
