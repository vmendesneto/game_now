"""GN-043: async bridge between continuous CPU ASR and the text-only feed.

Inference is submitted to a worker thread, never run on the FastAPI loop.
The service is an internal primitive: network source activation remains a
separate explicit step (GN-074/GN-090).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.asr_windows import RollingASRProcessor
from app.transcription_feed import TranscriptFeed


class AsyncSourceTranscriber:
    """One isolated, sequential ASR processing session per source."""

    def __init__(
        self, match_id: str, source_id: str,
        processor: RollingASRProcessor, feed: TranscriptFeed,
    ) -> None:
        if not match_id or not source_id:
            raise ValueError("Match and source IDs cannot be blank")
        self.match_id = match_id
        self.source_id = source_id
        self.processor = processor
        self.feed = feed
        self._lock = asyncio.Lock()
        self._closed = False
        feed.set_state(match_id, source_id, "idle")

    def _publish(self, updates, captured_at: datetime) -> None:
        for update in updates:
            self.feed.publish(
                self.match_id, self.source_id, update, captured_at=captured_at
            )

    async def push(self, pcm: bytes, *, captured_at: datetime) -> None:
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("Capture timestamp must have UTC offset")
        async with self._lock:
            if self._closed:
                raise RuntimeError("ASR source session has stopped")
            self.feed.set_state(self.match_id, self.source_id, "processing")
            try:
                updates = await asyncio.to_thread(self.processor.push, self.source_id, pcm)
                self._publish(updates, captured_at)
                if not updates:
                    self.feed.set_state(self.match_id, self.source_id, "buffering")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.feed.set_state(
                    self.match_id, self.source_id, "error", error_code="asr_error"
                )
                raise

    async def finish(self, *, captured_at: datetime | None = None) -> None:
        if captured_at is None:
            captured_at = datetime.now(timezone.utc)
        async with self._lock:
            if self._closed:
                return
            try:
                updates = await asyncio.to_thread(self.processor.finish, self.source_id)
                self._publish(updates, captured_at)
            finally:
                self._closed = True
                self.feed.set_state(self.match_id, self.source_id, "stopped")
