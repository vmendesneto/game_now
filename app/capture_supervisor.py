"""GN-033: bounded, reconnecting PCM capture worker, independent per source.

No media reaches FastAPI or SQLite. YouTube is re-resolved on *each* attempt,
so signed media URLs from a previous session are never reused.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import AsyncIterator, Callable

from app.audio_buffer import BufferError as AudioBufferError, MultiSourceAudioBuffer
from app.audio_capture import CaptureError, pcm_chunks
from app.contracts import AudioSource
from app.youtube_capture import youtube_pcm_chunks

CaptureFactory = Callable[[AudioSource], AsyncIterator[bytes]]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    initial_seconds: float = 1.0
    maximum_seconds: float = 30.0
    idle_seconds: float = 20.0
    healthy_chunks: int = 8

    def __post_init__(self) -> None:
        if (self.initial_seconds <= 0 or self.maximum_seconds < self.initial_seconds
                or self.idle_seconds <= 0 or self.healthy_chunks < 1):
            raise ValueError("Invalid reconnect/idle policy")


@dataclass(frozen=True, slots=True)
class CaptureStatus:
    source_id: str
    state: str = "offline"
    attempts: int = 0
    reconnects: int = 0
    pcm_bytes: int = 0
    last_audio_at: datetime | None = None
    last_error: str | None = None


async def _next_or_stop(
    iterator: AsyncIterator[bytes], stop: asyncio.Event, timeout: float
) -> bytes | None:
    """Stop immediately even when FFmpeg or yt-dlp is waiting for network data."""
    audio_task = asyncio.create_task(anext(iterator))
    stop_task = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait(
            {audio_task, stop_task}, timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if stop_task in done:
            return None
        if audio_task in done:
            return audio_task.result()
        raise CaptureError("No PCM received before the idle deadline")
    finally:
        for task in (audio_task, stop_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(audio_task, stop_task, return_exceptions=True)


async def _pause_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


class CaptureSupervisor:
    """Run one cancellable worker per source, with independent failure budgets.

    This is a capture primitive, not a web/API start button (future GN-035/074).
    Status deliberately contains no request URLs, exception text or signed tokens.
    """

    def __init__(
        self, buffer: MultiSourceAudioBuffer, *,
        policy: RetryPolicy | None = None,
        radio_capture: CaptureFactory = pcm_chunks,
        youtube_capture: CaptureFactory = youtube_pcm_chunks,
        pause: Callable[[asyncio.Event, float], object] = _pause_or_stop,
    ) -> None:
        self.buffer = buffer
        self.policy = policy or RetryPolicy()
        self._factories = {"radio": radio_capture, "youtube": youtube_capture}
        self._pause = pause
        self._states: dict[str, CaptureStatus] = {}
        self._active: set[str] = set()

    def status(self, source_id: str) -> CaptureStatus | None:
        return self._states.get(source_id)

    def statuses(self) -> tuple[CaptureStatus, ...]:
        return tuple(self._states.values())

    async def run(self, source: AudioSource, stop: asyncio.Event) -> None:
        if not source.enabled or not source.url:
            raise ValueError("Only enabled sources with URLs can be captured")
        if source.id in self._active:
            raise ValueError("Source already has an active capture worker")
        self._active.add(source.id)
        state = CaptureStatus(source_id=source.id)
        self._states[source.id] = state
        failures = 0
        factory = self._factories[source.kind]
        try:
            while not stop.is_set():
                state = replace(
                    state, state="connecting" if state.attempts == 0 else "reconnecting",
                    attempts=state.attempts + 1,
                    reconnects=max(0, state.attempts),
                )
                self._states[source.id] = state
                session_chunks = 0
                error_code = "stream_ended"
                try:
                    # For YouTube this creates a NEW yt-dlp resolution on every
                    # iteration, never a replay of an expired signed stream URL.
                    async with aclosing(factory(source)) as iterator:
                        while not stop.is_set():
                            try:
                                block = await _next_or_stop(
                                    iterator, stop, self.policy.idle_seconds
                                )
                            except StopAsyncIteration:
                                break
                            if block is None:
                                break
                            if not isinstance(block, bytes) or not block or len(block) % 2:
                                error_code = "invalid_pcm"
                                raise CaptureError("Invalid PCM chunk")
                            now = datetime.now(timezone.utc)
                            if state.last_audio_at is not None:
                                now = max(now, state.last_audio_at)
                            self.buffer.append(source.id, block, now)
                            session_chunks += 1
                            state = replace(
                                state, state="online", pcm_bytes=state.pcm_bytes + len(block),
                                last_audio_at=now, last_error=None,
                            )
                            self._states[source.id] = state
                except asyncio.CancelledError:
                    raise
                except AudioBufferError:
                    error_code = "buffer_error"
                except CaptureError:
                    if error_code != "invalid_pcm":
                        error_code = "capture_error"
                except OSError:
                    error_code = "io_error"
                except Exception:
                    # Third-party extractors must not leak signed URLs to status.
                    error_code = "capture_error"

                if stop.is_set():
                    break
                state = replace(state, state="reconnecting", last_error=error_code)
                self._states[source.id] = state
                failures = 0 if session_chunks >= self.policy.healthy_chunks else failures
                delay = min(
                    self.policy.maximum_seconds,
                    self.policy.initial_seconds * (2 ** min(failures, 20)),
                )
                failures += 1
                await self._pause(stop, delay)
        finally:
            self._states[source.id] = replace(state, state="stopped")
            self._active.remove(source.id)
