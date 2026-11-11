"""GN-042: bounded, per-match/source *text-only* transcription feed.

No audio, source URLs, model weights or secrets reach this feed. Entries are
volatile diagnostics until a future ingestion controller wires real sources.
Thread-safe publication also notifies WebSocket listeners without blocking CPU
workers or the FastAPI event loop.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from app.asr_windows import WindowTranscript
from app.narration_classifier import classify_narration

_ALLOWED_STATES = frozenset({"idle", "buffering", "processing", "ready", "error", "stopped"})


@dataclass(frozen=True, slots=True)
class FeedEntry:
    match_id: str
    source_id: str
    sequence: int
    captured_at: datetime
    processed_at: datetime
    start_seconds: float
    end_seconds: float
    language: str
    text: str
    narration_kind: str
    classification_reason: str
    eligible_for_live_state: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "match_id": self.match_id, "source_id": self.source_id,
            "sequence": self.sequence, "captured_at": self.captured_at.isoformat(),
            "processed_at": self.processed_at.isoformat(),
            "start_seconds": self.start_seconds, "end_seconds": self.end_seconds,
            "language": self.language, "text": self.text,
            "narration_kind": self.narration_kind,
            "classification_reason": self.classification_reason,
            "eligible_for_live_state": self.eligible_for_live_state,
        }


class TranscriptFeed:
    """Bounded in-memory feed; publish from async or background worker threads."""

    def __init__(
        self, *, max_matches: int = 16, max_sources_per_match: int = 8,
        max_entries_per_source: int = 100, queue_size: int = 32,
    ) -> None:
        if min(max_matches, max_sources_per_match, max_entries_per_source, queue_size) < 1:
            raise ValueError("All feed capacities must be positive")
        self._max_matches = max_matches
        self._max_sources = max_sources_per_match
        self._max_entries = max_entries_per_source
        self._queue_size = queue_size
        self._lock = RLock()
        self._records: dict[tuple[str, str], deque[FeedEntry]] = {}
        self._states: dict[tuple[str, str], dict[str, object]] = {}
        self._subscribers: dict[str, dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def _register(self, match_id: str, source_id: str) -> tuple[str, str]:
        if not match_id or not source_id:
            raise ValueError("Match and source IDs cannot be blank")
        key = (match_id, source_id)
        if key not in self._states:
            matches = {m for m, _ in self._states}
            if match_id not in matches and len(matches) >= self._max_matches:
                raise ValueError("Too many active transcript matches")
            if sum(m == match_id for m, _ in self._states) >= self._max_sources:
                raise ValueError("Too many transcript sources per match")
            self._states[key] = {
                "match_id": match_id, "source_id": source_id,
                "state": "idle", "last_error": None, "last_sequence": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._records[key] = deque(maxlen=self._max_entries)
        return key

    @staticmethod
    def _deliver(queue: asyncio.Queue, message: dict) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(message)

    def _notify(self, match_id: str, payload: dict) -> None:
        with self._lock:
            targets = tuple(self._subscribers.get(match_id, {}).values())
        for loop, queue in targets:
            try:
                loop.call_soon_threadsafe(self._deliver, queue, payload)
            except RuntimeError:
                # Listener event loop ended between publication and dispatch.
                pass

    def set_state(
        self, match_id: str, source_id: str, state: str, *,
        error_code: str | None = None,
    ) -> None:
        if state not in _ALLOWED_STATES:
            raise ValueError("Unsupported ASR processing state")
        if error_code is not None and error_code not in ("asr_error", "queue_full"):
            raise ValueError("Only safe error codes are exposed")
        with self._lock:
            key = self._register(match_id, source_id)
            info = self._states[key]
            info.update(
                state=state, last_error=error_code,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            payload = {"kind": "status", "data": dict(info)}
        self._notify(match_id, payload)

    def publish(
        self, match_id: str, source_id: str,
        update: WindowTranscript, *, captured_at: datetime,
    ) -> FeedEntry | None:
        if update.source_id != source_id:
            raise ValueError("Transcription cannot be assigned to another source")
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("Capture timestamp must be timezone-aware")
        if not update.new_text.strip():
            # Repeated text in an overlapping window is not emitted again.
            return None
        # Classifier metadata is advisory; it NEVER mutates match state.
        # Oversize ASR output remains visible, but is not treated as live.
        try:
            decision = classify_narration(update.new_text)
            kind = decision.label.value
            reason = decision.matched_cue or "no_explicit_cue"
            eligible = decision.is_current_play
        except ValueError:
            kind, reason, eligible = "unknown", "text_exceeds_classifier_limit", False
        entry = FeedEntry(
            match_id=match_id, source_id=source_id,
            sequence=update.sequence, captured_at=captured_at,
            processed_at=datetime.now(timezone.utc),
            start_seconds=update.start_seconds,
            end_seconds=update.end_seconds, language=update.language,
            text=update.new_text.strip(),
            narration_kind=kind,
            classification_reason=reason,
            eligible_for_live_state=eligible,
        )
        with self._lock:
            key = self._register(match_id, source_id)
            previous = self._records[key]
            if previous and entry.sequence <= previous[-1].sequence:
                raise ValueError("Transcript window sequence cannot move backwards")
            previous.append(entry)
            self._states[key].update(
                state="ready", last_error=None, last_sequence=entry.sequence,
                updated_at=entry.processed_at.isoformat(),
            )
        self._notify(match_id, {"kind": "transcript", "data": entry.as_dict()})
        return entry

    def snapshot(
        self, match_id: str, *, source_id: str | None = None, limit: int = 50,
        allowed_sources: set[str] | None = None,
    ) -> dict[str, object]:
        if not 1 <= limit <= 200:
            raise ValueError("Feed limit must be between 1 and 200")
        with self._lock:
            keys = [
                key for key in self._states
                if key[0] == match_id
                and (source_id is None or key[1] == source_id)
                and (allowed_sources is None or key[1] in allowed_sources)
            ]
            statuses = [dict(self._states[key]) for key in sorted(keys)]
            records = sorted(
                (record for key in keys for record in self._records[key]),
                key=lambda item: (item.processed_at, item.source_id, item.sequence),
            )[-limit:]
        return {
            "match_id": match_id, "mode": "volatile_text_only",
            "sources": statuses, "entries": [entry.as_dict() for entry in records],
        }

    def subscribe(self, match_id: str) -> tuple[str, asyncio.Queue]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        token = uuid4().hex
        with self._lock:
            self._subscribers.setdefault(match_id, {})[token] = (loop, queue)
        return token, queue

    def unsubscribe(self, match_id: str, token: str) -> None:
        with self._lock:
            subscribers = self._subscribers.get(match_id)
            if subscribers:
                subscribers.pop(token, None)
                if not subscribers:
                    self._subscribers.pop(match_id, None)

    def clear_match(self, match_id: str) -> None:
        with self._lock:
            for key in list(self._states):
                if key[0] == match_id:
                    self._states.pop(key, None)
                    self._records.pop(key, None)
