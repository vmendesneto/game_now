"""GN-034: bounded, independent in-memory PCM buffers with capture timestamps.

Audio is never persisted to SQLite or sent to the browser. The frames are
signed 16-bit mono PCM at 16 kHz, produced by GN-030 or future GN-031.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import RLock

SAMPLE_RATE = 16_000
SAMPLE_BYTES = 2
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_BYTES


class BufferError(ValueError):
    """Invalid audio frame or source buffer capacity exceeded."""


@dataclass(frozen=True, slots=True)
class AudioFrame:
    source_id: str
    captured_at: datetime
    pcm: bytes

    @property
    def seconds(self) -> float:
        return len(self.pcm) / BYTES_PER_SECOND


class MultiSourceAudioBuffer:
    """Per-source ring with both time-window and byte-size eviction.

    append() and snapshot() are protected by a lock, so reading from a
    future ASR worker never observes half-appended frames.
    """

    def __init__(self, *, window_seconds: float = 30.0,
                 max_bytes_per_source: int = 1_280_000,
                 max_sources: int = 8) -> None:
        if (window_seconds <= 0 or max_bytes_per_source < SAMPLE_BYTES
                or max_bytes_per_source % SAMPLE_BYTES or max_sources < 1):
            raise BufferError("Invalid audio buffer bounds")
        self.window_seconds = window_seconds
        self.max_bytes_per_source = max_bytes_per_source
        self.max_sources = max_sources
        self._lock = RLock()
        self._frames: dict[str, deque[AudioFrame]] = {}
        self._bytes: dict[str, int] = {}

    def append(self, source_id: str, pcm: bytes, captured_at: datetime) -> None:
        if not source_id or not source_id.strip():
            raise BufferError("Source ID cannot be blank")
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise BufferError("Audio timestamp must include UTC offset")
        if not isinstance(pcm, bytes) or not pcm or len(pcm) % SAMPLE_BYTES:
            raise BufferError("Audio must be nonempty sample-aligned PCM bytes")
        if len(pcm) > self.max_bytes_per_source:
            raise BufferError("Single audio chunk exceeds configured capacity")
        frame = AudioFrame(source_id=source_id, captured_at=captured_at, pcm=pcm)
        with self._lock:
            if source_id not in self._frames:
                if len(self._frames) >= self.max_sources:
                    raise BufferError("Maximum number of independent sources exceeded")
                self._frames[source_id] = deque()
                self._bytes[source_id] = 0
            queue = self._frames[source_id]
            if queue and frame.captured_at < queue[-1].captured_at:
                raise BufferError("Audio timestamps cannot move backwards per source")
            queue.append(frame)
            self._bytes[source_id] += len(pcm)
            threshold = captured_at - timedelta(seconds=self.window_seconds)
            while queue and (queue[0].captured_at < threshold
                             or self._bytes[source_id] > self.max_bytes_per_source):
                oldest = queue.popleft()
                self._bytes[source_id] -= len(oldest.pcm)

    def snapshot(self, source_id: str, since: datetime | None = None) -> tuple[AudioFrame, ...]:
        with self._lock:
            frames = tuple(self._frames.get(source_id, ()))
        if since is None:
            return frames
        if since.tzinfo is None or since.utcoffset() is None:
            raise BufferError("Query timestamp must include UTC offset")
        return tuple(frame for frame in frames if frame.captured_at >= since)

    def status(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {
                source_id: {"frames": len(queue), "bytes": self._bytes[source_id]}
                for source_id, queue in self._frames.items()
            }

    def clear(self, source_id: str | None = None) -> None:
        with self._lock:
            if source_id is None:
                self._frames.clear()
                self._bytes.clear()
            else:
                self._frames.pop(source_id, None)
                self._bytes.pop(source_id, None)
