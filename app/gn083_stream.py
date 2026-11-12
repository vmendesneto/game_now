"""GN-083: permitted YouTube audio -> rolling ASR -> text evidence, no media files.

This is an actual transcription path, NOT another PCM capture diagnostic.
The same GN-031/GN-090 secure stream code is used; inference runs off-loop.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass
from typing import AsyncIterator, Callable

from app.asr import ASRSettings, BYTES_PER_SECOND, CPUTranscriber
from app.audio_capture import CaptureError, validate_start_seconds
from app.asr_vocabulary import build_vocabulary_prompt
from app.asr_windows import RollingASRProcessor, WindowSettings
from app.contracts import AudioSource, Match
from app.source_validation import validate_source_urls
from app.storage import StoreConflict
from app.youtube_capture import youtube_pcm_chunks


@dataclass(frozen=True, slots=True)
class YoutubeTranscriptionRun:
    source_id: str
    processed_seconds: float
    processed_bytes: int
    requested_seconds: float
    complete: bool
    observations: tuple[dict, ...]
    requested_media_start_seconds: float = 0


async def transcribe_youtube_source(
    url: str, match: Match, *,
    seconds: float = 300,
    source_id: str = "youtube-083",
    yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg",
    model: str = "tiny",
    capture_first: bool = False,
    start_seconds: float = 0,
    transcriber=None,
    capture_factory: Callable[..., AsyncIterator[bytes]] | None = None,
) -> YoutubeTranscriptionRun:
    """Consume exactly one bounded public stream, retaining text and diagnostics.

    No audio is persisted, sent to a browser or returned. When capture_first
    is enabled, collect at most 600 seconds (19.2 MB PCM) in process RAM before
    CPU inference, so heavy ASR does not stall media reading. This is not
    an access workaround and never retries a denied remote request.
    The caller must independently establish authorization.
    """
    start_seconds = validate_start_seconds(start_seconds)
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or not 5 <= seconds <= 600:
        raise ValueError("YouTube ASR duration must be between 5 and 600 seconds")
    if not isinstance(url, str):
        raise ValueError("A permitted public YouTube URL is required")
    source = AudioSource(
        id=source_id, name="YouTube ASR diagnostic", kind="youtube",
        url=url, enabled=True, status="offline",
    )
    try:
        validate_source_urls([source])
    except StoreConflict as exc:
        raise ValueError("Invalid or unavailable public YouTube source") from exc
    processor = RollingASRProcessor(
        transcriber or CPUTranscriber(ASRSettings(
            model=model, max_seconds=60, initial_prompt=build_vocabulary_prompt(match),
        )),
        WindowSettings(),
    )
    rows: list[dict] = []

    def collect(updates) -> None:
        for item in updates:
            if item.new_text.strip():
                rows.append({
                    "source_id": item.source_id, "sequence": item.sequence,
                    "start_seconds": item.start_seconds, "end_seconds": item.end_seconds,
                    "text": item.new_text,
                })

    maximum = int(seconds * BYTES_PER_SECOND) // 2 * 2
    total = 0
    factory = capture_factory or youtube_pcm_chunks
    # Explicitly bounded to <=19,200,000 PCM bytes: local diagnostic, one source.
    # By keeping ingestion separate from model inference, a slow first download
    # or CPU-heavy Whisper window cannot hold the FFmpeg pipe unread.
    captured = bytearray() if capture_first else None
    try:
        seek = {"start_seconds": start_seconds} if start_seconds else {}
        async with aclosing(factory(
            source, yt_dlp_binary=yt_dlp_binary, ffmpeg_binary=ffmpeg_binary,
            **seek,
        )) as stream:
            async for block in stream:
                if not isinstance(block, bytes) or not block or len(block) % 2:
                    raise ValueError("Stream returned invalid PCM samples")
                remaining = maximum - total
                if remaining <= 0:
                    break
                limited = block[:remaining]
                if limited:
                    if captured is not None:
                        captured.extend(limited)
                    else:
                        # The original low-memory streaming mode remains available.
                        collect(await asyncio.to_thread(processor.push, source_id, limited))
                    total += len(limited)
                if total >= maximum:
                    break
    except CaptureError as exc:
        # Report progress, without URLs/headers/audio data, to distinguish an
        # immediate 403 from one received after successful PCM delivery.
        raise CaptureError(
            f"{exc} (PCM captured before failure: "
            f"{total / BYTES_PER_SECOND:.1f}s; "
            f"mode: {'capture-first' if capture_first else 'streaming'})"
        ) from exc
    if not total:
        raise ValueError("Source delivered no PCM to ASR")
    if captured is not None:
        # Reuse the existing rolling/de-duplication path after capture finishes;
        # each synthetic 500 ms piece is below the assembler's input bound.
        for offset in range(0, len(captured), BYTES_PER_SECOND // 2):
            piece = bytes(captured[offset:offset + BYTES_PER_SECOND // 2])
            collect(await asyncio.to_thread(processor.push, source_id, piece))
        captured.clear()
    collect(await asyncio.to_thread(processor.finish, source_id))
    return YoutubeTranscriptionRun(
        source_id=source_id, processed_seconds=total / BYTES_PER_SECOND,
        processed_bytes=total, requested_seconds=seconds, complete=total >= maximum,
        observations=tuple(rows),
        requested_media_start_seconds=start_seconds,
    )
