"""GN-030: bounded FFmpeg capture to mono 16-kHz signed 16-bit PCM.

No browser media endpoints. Use contextlib.aclosing() when stopping early.
YouTube resolution is intentionally excluded (GN-031). A full network policy
for HTTP redirects/HLS subrequests is still required in GN-090.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import aclosing, suppress
from datetime import datetime, timezone
import ipaddress
from pathlib import Path
import shutil
import socket
from typing import AsyncIterator
from urllib.parse import urlsplit

from app.contracts import AudioSource
from app.source_validation import validate_source_urls
from app.storage import StoreConflict

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
DEFAULT_CHUNK_MS = 500


class CaptureError(RuntimeError):
    """Source cannot be captured safely or FFmpeg failed to decode it."""


async def check_public_destination(url: str) -> None:
    """Reject DNS results resolving to private/loopback addresses before launch."""
    hostname = urlsplit(url).hostname
    if not hostname:
        raise CaptureError("Missing stream hostname")
    try:
        responses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(
                hostname, urlsplit(url).port or (443 if url.startswith("https:") else 80),
                type=socket.SOCK_STREAM,
            ),
            timeout=8,
        )
    except (OSError, ValueError, asyncio.TimeoutError) as exc:
        raise CaptureError("Cannot resolve radio hostname") from exc
    if not responses or any(
        not ipaddress.ip_address(response[4][0]).is_global for response in responses
    ):
        raise CaptureError("Radio hostname resolves to a non-public IP")


async def _drain_errors(stream: asyncio.StreamReader) -> str:
    tail = bytearray()
    while True:
        part = await stream.read(4096)
        if not part:
            break
        tail.extend(part)
        if len(tail) > 4096:
            del tail[:-4096]
    return tail.decode("utf-8", errors="replace").strip()


async def _shutdown(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


async def pcm_chunks(
    source: AudioSource,
    *,
    ffmpeg_binary: str = "ffmpeg",
    chunk_ms: int = DEFAULT_CHUNK_MS,
    fixture_file: Path | None = None,
    http_headers: dict[str, str] | None = None,
) -> AsyncIterator[bytes]:
    """Decode a radio stream into chunks of PCM s16le/mono/16k.

    fixture_file bypasses remote URL lookup **only** for internal offline tests
    and local CLI diagnostics. It is never passed through HTTP endpoints.
    """
    if source.kind != "radio" or not source.enabled:
        raise CaptureError("Only enabled radio sources can use GN-030")
    if not (100 <= chunk_ms <= 5000):
        raise CaptureError("chunk_ms must be between 100 and 5000")
    chunk_bytes = SAMPLE_RATE * SAMPLE_WIDTH * chunk_ms // 1000
    if chunk_bytes % SAMPLE_WIDTH:
        raise CaptureError("PCM chunks must be sample-aligned")
    if fixture_file is not None:
        media = Path(fixture_file).resolve(strict=True)
        if not media.is_file():
            raise CaptureError("Fixture must be a regular file")
        input_uri = str(media)
    else:
        try:
            validate_source_urls([source])
        except StoreConflict as exc:
            raise CaptureError(str(exc)) from exc
        if not source.url:
            raise CaptureError("Radio source has no URL")
        await check_public_destination(source.url)
        input_uri = source.url

    if shutil.which(ffmpeg_binary) is None:
        raise CaptureError("FFmpeg not found; install it and add it to PATH")

    args = [
        ffmpeg_binary, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto,data",
    ]
    if http_headers:
        allowed = {"user-agent", "referer", "origin", "accept"}
        if any(key.lower() not in allowed or "\\r" in value or "\\n" in value
               or len(value) > 1024 for key, value in http_headers.items()):
            raise CaptureError("Only safe public-stream request headers are supported")
        args += ["-headers", "".join(f"{key}: {value}\\r\\n" for key, value in http_headers.items())]
    args += [
        "-i", input_uri, "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError) as exc:
        raise CaptureError("Could not start FFmpeg") from exc
    assert proc.stdout is not None and proc.stderr is not None
    errors = asyncio.create_task(_drain_errors(proc.stderr))
    pending = bytearray()
    yielded = 0
    try:
        while True:
            piece = await proc.stdout.read(chunk_bytes)
            if not piece:
                break
            pending.extend(piece)
            while len(pending) >= chunk_bytes:
                yield bytes(pending[:chunk_bytes])
                del pending[:chunk_bytes]
                yielded += 1
        if pending:
            if len(pending) % SAMPLE_WIDTH != 0:
                raise CaptureError("FFmpeg returned unaligned PCM data")
            yield bytes(pending)
            yielded += 1
        code = await proc.wait()
        diagnosis = await errors
        if code != 0:
            raise CaptureError("FFmpeg failed to decode stream: " + (diagnosis[-300:] or f"code {code}"))
        if not yielded:
            raise CaptureError("FFmpeg produced no PCM samples")
    finally:
        await _shutdown(proc)
        if not errors.done():
            errors.cancel()
            with suppress(asyncio.CancelledError):
                await errors


async def diagnostic(source: AudioSource, *, fixture_file: Path | None = None,
                     duration: float = 5.0) -> dict:
    """Capture at most a requested duration; do not store or transmit the audio."""
    if duration <= 0 or duration > 60:
        raise CaptureError("Diagnostic duration must be >0 and <=60 seconds")
    maximum = int(duration * SAMPLE_RATE * SAMPLE_WIDTH)
    total = 0
    chunks = 0
    async with aclosing(pcm_chunks(source, fixture_file=fixture_file)) as audio:
        async for block in audio:
            total += min(len(block), maximum - total)
            chunks += 1
            if total >= maximum:
                break
    return {
        "source_id": source.id, "captured_at": datetime.now(timezone.utc).isoformat(),
        "format": "s16le", "sample_rate": SAMPLE_RATE, "channels": CHANNELS,
        "bytes": total, "chunks": chunks, "seconds": total / (SAMPLE_RATE * SAMPLE_WIDTH),
        "audio_retransmitted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GN-030: radio -> PCM 16 kHz diagnostic")
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--url", help="Public MP3/AAC/HLS radio URL")
    options.add_argument("--file", type=Path, help="Local audio test fixture")
    parser.add_argument("--seconds", type=float, default=5.0)
    args = parser.parse_args()
    source = AudioSource(id="radio-diagnostic", name="Radio diagnostic",
                         kind="radio", url=args.url, enabled=True, status="offline")
    import json
    try:
        print(json.dumps(asyncio.run(diagnostic(source, fixture_file=args.file,
                                                duration=args.seconds))))
    except (CaptureError, OSError) as exc:
        parser.exit(status=1, message=f"Capture error: {exc}\n")


if __name__ == "__main__":
    main()
