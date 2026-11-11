"""GN-035: bounded text/PCM metadata per source; never retains media.

A PCM callback proves receipt by the processor, not that a remote station is
online. Content is a text-classification hint; processing delay is not station skew.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
import time
from typing import Callable


@dataclass(slots=True)
class _Metrics:
    last_pcm_at: str | None = None
    last_pcm_tick: float | None = None
    last_text_tick: float | None = None
    content: str = "unknown"
    processing_delay_seconds: float | None = None
    stopped: bool = False
    missing_pcm: bool = False


class SourceTelemetry:
    """In-memory registry; the owning feed bounds sources and owns the lock."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] | None = None,
                 stale_seconds: float = 8.0, content_ttl_seconds: float = 20.0):
        if not math.isfinite(stale_seconds) or stale_seconds <= 0:
            raise ValueError("stale_seconds must be positive and finite")
        if not math.isfinite(content_ttl_seconds) or content_ttl_seconds <= 0:
            raise ValueError("content_ttl_seconds must be positive and finite")
        self._clock = clock
        self._utcnow = utcnow or (lambda: datetime.now(timezone.utc))
        self._stale_seconds = stale_seconds
        self._content_ttl_seconds = content_ttl_seconds
        self._records: dict[tuple[str, str], _Metrics] = {}

    def observe_pcm(self, match_id: str, source_id: str, byte_count: int) -> bool:
        """Return whether the PCM signal changed for sparse WebSocket notifications."""
        if not isinstance(byte_count, int) or isinstance(byte_count, bool) or byte_count < 0:
            raise ValueError("PCM byte count must be nonnegative")
        key = (match_id, source_id)
        metrics = self._records.setdefault(key, _Metrics())
        before = self._signal(metrics, self._clock())
        metrics.stopped = False
        if byte_count == 0:
            metrics.missing_pcm = True
        else:
            metrics.last_pcm_tick = self._clock()
            metrics.last_pcm_at = self._utcnow().astimezone(timezone.utc).isoformat()
            metrics.missing_pcm = False
        return before != self._signal(metrics, self._clock())

    def observe_text(self, match_id: str, source_id: str, kind: str, *,
                     captured_at: datetime, processed_at: datetime) -> None:
        metrics = self._records.setdefault((match_id, source_id), _Metrics())
        metrics.content = {
            "live_play": "narrating", "ad": "commercial",
            "conversation": "other", "analysis": "other", "replay": "other",
        }.get(kind, "unknown")
        metrics.last_text_tick = self._clock()
        if captured_at.tzinfo is None or processed_at.tzinfo is None:
            metrics.processing_delay_seconds = None
        else:
            delta = (processed_at - captured_at).total_seconds()
            metrics.processing_delay_seconds = round(delta, 3) if 0 <= delta <= 3600 else None

    def stop(self, match_id: str, source_id: str) -> None:
        self._records.setdefault((match_id, source_id), _Metrics()).stopped = True

    def clear_match(self, match_id: str) -> None:
        for key in list(self._records):
            if key[0] == match_id:
                del self._records[key]

    def _signal(self, metrics: _Metrics, now: float) -> str:
        if metrics.stopped:
            return "stopped"
        if metrics.missing_pcm:
            return "no_audio"
        if metrics.last_pcm_tick is None:
            return "unobserved"
        return "online" if 0 <= now - metrics.last_pcm_tick <= self._stale_seconds else "no_audio"

    def snapshot(self, match_id: str, source_id: str) -> dict[str, object]:
        metrics = self._records.get((match_id, source_id), _Metrics())
        now = self._clock()
        signal = self._signal(metrics, now)
        recent_text = metrics.last_text_tick is not None and (
            0 <= now - metrics.last_text_tick <= self._content_ttl_seconds
        )
        return {
            "signal": signal,
            "content": metrics.content if signal == "online" and recent_text else "unknown",
            "last_pcm_at": metrics.last_pcm_at,
            "stale_after_seconds": self._stale_seconds,
            "processing_delay_seconds": metrics.processing_delay_seconds,
            "relative_delay_seconds": None,  # GN-061 needs independent common events
            "delay_kind": "capture_to_processing_not_inter_source",
        }
