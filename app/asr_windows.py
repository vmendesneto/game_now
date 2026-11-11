"""GN-041: bounded overlapping PCM windows and conservative transcript de-duplication.

Pure synchronous processing: future GN-043 must schedule inference off the API
event loop. Window times are relative to each source, not match-clock times.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Protocol

from app.asr import ASRResult, BYTES_PER_SECOND
from app.silence_gate import PCMSilenceGate


@dataclass(frozen=True, slots=True)
class WindowSettings:
    window_ms: int = 6000
    overlap_ms: int = 2000
    min_tail_ms: int = 500
    max_sources: int = 8
    max_history_words: int = 64

    def __post_init__(self) -> None:
        if not 1000 <= self.window_ms <= 60_000:
            raise ValueError("window_ms must be between 1000 and 60000")
        if not 0 < self.overlap_ms < self.window_ms:
            raise ValueError("overlap_ms must be positive and smaller than window_ms")
        if not 100 <= self.min_tail_ms <= self.window_ms:
            raise ValueError("min_tail_ms must be between 100 and window_ms")
        if not 1 <= self.max_sources <= 32:
            raise ValueError("max_sources must be between 1 and 32")
        if not 2 <= self.max_history_words <= 512:
            raise ValueError("max_history_words must be between 2 and 512")


@dataclass(frozen=True, slots=True)
class SpeechWindow:
    source_id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    pcm: bytes


class PCMWindowAssembler:
    """Incremental rolling window assembler. PCM is never persisted."""

    def __init__(self, settings: WindowSettings | None = None) -> None:
        self.settings = settings or WindowSettings()
        self._pending: dict[str, bytearray] = {}
        self._offset: dict[str, int] = {}
        self._total: dict[str, int] = {}
        self._last_emitted_end: dict[str, int] = {}
        self._sequence: dict[str, int] = {}

    @property
    def window_bytes(self) -> int:
        return self.settings.window_ms * BYTES_PER_SECOND // 1000

    @property
    def stride_bytes(self) -> int:
        return (self.settings.window_ms - self.settings.overlap_ms) * BYTES_PER_SECOND // 1000

    def push(self, source_id: str, pcm: bytes) -> tuple[SpeechWindow, ...]:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id cannot be blank")
        if not isinstance(pcm, bytes) or not pcm or len(pcm) % 2:
            raise ValueError("PCM must be nonempty sample-aligned bytes")
        # A capture worker normally gives 0.5-second chunks. Refusing huge
        # submissions avoids an unbounded burst of windows in one call.
        if len(pcm) > self.window_bytes:
            raise ValueError("PCM chunk exceeds window capacity")
        if source_id not in self._pending:
            if len(self._pending) >= self.settings.max_sources:
                raise ValueError("Too many independent ASR sources")
            self._pending[source_id] = bytearray()
            self._offset[source_id] = 0
            self._total[source_id] = 0
            self._last_emitted_end[source_id] = 0
            self._sequence[source_id] = 0
        data = self._pending[source_id]
        data.extend(pcm)
        self._total[source_id] += len(pcm)
        ready: list[SpeechWindow] = []
        while len(data) >= self.window_bytes:
            start = self._offset[source_id]
            end = start + self.window_bytes
            seq = self._sequence[source_id]
            ready.append(SpeechWindow(
                source_id=source_id,
                sequence=seq,
                start_seconds=start / BYTES_PER_SECOND,
                end_seconds=end / BYTES_PER_SECOND,
                pcm=bytes(data[:self.window_bytes]),
            ))
            del data[:self.stride_bytes]
            self._offset[source_id] += self.stride_bytes
            self._last_emitted_end[source_id] = end
            self._sequence[source_id] = seq + 1
        return tuple(ready)

    def finish(self, source_id: str) -> SpeechWindow | None:
        """Flush a meaningful final tail, then release source buffer memory."""
        if source_id not in self._pending:
            return None
        data = self._pending.pop(source_id)
        offset = self._offset.pop(source_id)
        total = self._total.pop(source_id)
        last_end = self._last_emitted_end.pop(source_id)
        sequence = self._sequence.pop(source_id)
        min_new_bytes = self.settings.min_tail_ms * BYTES_PER_SECOND // 1000
        # After a complete window, the residual overlap alone is not new data.
        if total - last_end < min_new_bytes or len(data) < min_new_bytes:
            return None
        return SpeechWindow(
            source_id=source_id, sequence=sequence,
            start_seconds=offset / BYTES_PER_SECOND,
            end_seconds=total / BYTES_PER_SECOND,
            pcm=bytes(data),
        )

    def pending_sizes(self) -> dict[str, int]:
        return {source: len(data) for source, data in self._pending.items()}


def _normalized(word: str) -> str:
    folded = unicodedata.normalize("NFKD", word.casefold())
    return re.sub(r"[^a-z0-9]", "", "".join(
        char for char in folded if not unicodedata.combining(char)
    ))


class TextOverlapDeduplicator:
    """Remove only matching suffix/prefix of 2+ normalized words per source.

    Single-word matches are retained; a repeated 'gol' could be a new event.
    Limited history prevents transcript strings from growing indefinitely.
    """

    def __init__(self, *, max_history_words: int = 64) -> None:
        if max_history_words < 2:
            raise ValueError("max_history_words must be >= 2")
        self.max_history_words = max_history_words
        self._history: dict[str, list[str]] = {}

    def consume(self, source_id: str, text: str) -> str:
        if not source_id or not source_id.strip():
            raise ValueError("source_id cannot be blank")
        incoming = text.split()
        if not incoming:
            return ""
        old = self._history.get(source_id, [])
        prev_norm = [_normalized(token) for token in old]
        next_norm = [_normalized(token) for token in incoming]
        matched = 0
        for n in range(min(len(old), len(incoming)), 1, -1):
            if prev_norm[-n:] == next_norm[:n] and all(next_norm[:n]):
                matched = n
                break
        new_words = incoming[matched:]
        self._history[source_id] = (old + new_words)[-self.max_history_words:]
        return " ".join(new_words)

    def clear(self, source_id: str) -> None:
        self._history.pop(source_id, None)


class Transcriber(Protocol):
    def transcribe_pcm(self, pcm: bytes) -> ASRResult: ...


@dataclass(frozen=True, slots=True)
class WindowTranscript:
    source_id: str
    sequence: int
    start_seconds: float
    end_seconds: float
    language: str
    raw_text: str
    new_text: str


class RollingASRProcessor:
    """Runs sync inference over emitted windows, returning only text/metadata."""

    def __init__(
        self, transcriber: Transcriber, settings: WindowSettings | None = None,
        *, silence_gate: PCMSilenceGate | None = None,
    ):
        self.settings = settings or WindowSettings()
        self.silence_gate = silence_gate
        self.assembler = PCMWindowAssembler(self.settings)
        self.deduplicator = TextOverlapDeduplicator(
            max_history_words=self.settings.max_history_words
        )
        self.transcriber = transcriber

    def _transcribe(self, windows: tuple[SpeechWindow, ...]) -> tuple[WindowTranscript, ...]:
        updates = []
        for window in windows:
            if self.silence_gate is not None and self.silence_gate.assess(window.pcm).skip_asr:
                # Keep original sequence/time offsets: skip an inference, never
                # delete PCM from the assembler or compress the match clock.
                self.deduplicator.clear(window.source_id)
                continue
            result = self.transcriber.transcribe_pcm(window.pcm)
            updates.append(WindowTranscript(
                source_id=window.source_id, sequence=window.sequence,
                start_seconds=window.start_seconds, end_seconds=window.end_seconds,
                language=result.language, raw_text=result.text,
                new_text=self.deduplicator.consume(window.source_id, result.text),
            ))
        return tuple(updates)

    def push(self, source_id: str, pcm: bytes) -> tuple[WindowTranscript, ...]:
        return self._transcribe(self.assembler.push(source_id, pcm))

    def finish(self, source_id: str) -> tuple[WindowTranscript, ...]:
        tail = self.assembler.finish(source_id)
        updates = self._transcribe((tail,)) if tail is not None else ()
        self.deduplicator.clear(source_id)
        return updates
