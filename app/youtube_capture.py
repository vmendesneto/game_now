"""GN-031 groundwork: resolve permitted public YouTube Live audio using yt-dlp.

Not marked complete until a permitted real live URL is tested. No cookies, DRM,
logins or browser sessions are used. The resulting signed URL is ephemeral and
is not stored or exposed through the web API.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from datetime import datetime, timezone
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
    input_has_video: bool = False


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
        available = metadata.get("formats")
        if not isinstance(available, list):
            raise CaptureError("yt-dlp metadata has no valid formats list")
        # Some public live HLS manifests expose audio only inside a
        # combined video/audio rendition. Prefer separate audio if offered.
        # In the fallback, FFmpeg -vn outputs PCM audio only; the input
        # transport can still transfer video bytes (never stored or served).
        sound_formats = [
            item for item in available
            if isinstance(item, dict) and not item.get("has_drm")
            and item.get("acodec") not in (None, "none")
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
            selected = max(audio_only, key=lambda item: bitrate(item, "abr"))
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
        )
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


async def youtube_diagnostic(
    source: AudioSource, *, duration: float = 5.0, yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg",
) -> dict:
    """Verify actual PCM decoding without saving or returning audio/media URLs."""
    if not 0 < duration <= 60:
        raise CaptureError("Diagnostic duration must be >0 and <=60 seconds")
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
        raise CaptureError("YouTube Live delivered no PCM samples")
    return {
        "source_id": source.id, "captured_at": datetime.now(timezone.utc).isoformat(),
        "sample_rate": 16_000, "channels": 1, "format": "s16le",
        "seconds": received / (16_000 * 2), "bytes": received, "chunks": blocks,
        "audio_retransmitted": False,
    }


def main() -> None:
    """Explicit opt-in live capture smoke test; no API endpoint for media."""
    import argparse
    parser = argparse.ArgumentParser(
        description="GN-031: check permitted public YouTube Live audio (no playback)"
    )
    parser.add_argument("--url", required=True, help="Authorized public YouTube Live URL")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()
    source = AudioSource(
        id="youtube-diagnostic", name="Live diagnostic", kind="youtube",
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
