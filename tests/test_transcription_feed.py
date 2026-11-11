"""GN-042/043: per-source feed, websocket fanout and async CPU isolation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from dataclasses import replace
import struct
import time
from threading import Event, Thread

from fastapi.testclient import TestClient
import pytest

from app.asr import ASRResult
from app.asr_windows import RollingASRProcessor, WindowSettings, WindowTranscript
from app.main import create_app
from app.transcription_feed import TranscriptFeed
from app.transcription_runtime import AsyncSourceTranscriber

def config(match_id="match-001"):
    return {
        "id": match_id,
        "home": {"id": "club-a", "name": "Azul", "short_name": "AZU",
                 "color": "#1122FF", "attack_direction": "left_to_right"},
        "away": {"id": "club-b", "name": "Vermelho", "short_name": "VER",
                 "color": "#FF2211", "attack_direction": "right_to_left"},
        "period": "first_half", "match_seconds": 0,
        "home_score": 0, "away_score": 0,
    }


def window(source: str, sequence: int, text: str) -> WindowTranscript:
    return WindowTranscript(
        source_id=source, sequence=sequence,
        start_seconds=sequence * 4.0, end_seconds=sequence * 4.0 + 6,
        language="pt", raw_text=text, new_text=text,
    )


def test_feed_bounded_independent_with_status_and_timestamps():
    feed = TranscriptFeed(max_entries_per_source=2, max_sources_per_match=2)
    now = datetime.now(timezone.utc)
    feed.set_state("match", "radio", "processing")
    for i in range(3):
        feed.publish("match", "radio", window("radio", i, f"texto {i}"), captured_at=now)
    feed.publish("match", "youtube", window("youtube", 0, "gol"), captured_at=now)
    snapshot = feed.snapshot("match")
    assert len(snapshot["entries"]) == 3
    assert [e["text"] for e in snapshot["entries"] if e["source_id"] == "radio"] == [
        "texto 1", "texto 2",
    ]
    assert len(snapshot["sources"]) == 2
    assert all(e["captured_at"] == now.isoformat() for e in snapshot["entries"])
    assert len(feed.snapshot("match", source_id="youtube")["entries"]) == 1
    assert feed.snapshot("match", allowed_sources={"radio"})["sources"][0]["source_id"] == "radio"
    assert all(e["source_id"] == "radio" for e in feed.snapshot(
        "match", allowed_sources={"radio"}
    )["entries"])
    with pytest.raises(ValueError, match="sources"):
        feed.set_state("match", "third", "idle")
    assert feed.snapshot("other")["entries"] == []


def test_feed_rejects_untrusted_codes_ids_and_backwards_sequences():
    feed = TranscriptFeed()
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="another source"):
        feed.publish("match", "radio", window("youtube", 0, "fake"), captured_at=now)
    with pytest.raises(ValueError, match="timezone"):
        feed.publish("match", "radio", window("radio", 0, "fake"),
                     captured_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="safe"):
        feed.set_state("match", "radio", "error", error_code="PRIVATE URL")
    feed.publish("match", "radio", window("radio", 1, "ok"), captured_at=now)
    with pytest.raises(ValueError, match="backwards"):
        feed.publish("match", "radio", window("radio", 1, "same"), captured_at=now)
    assert feed.publish("match", "radio", replace(window("radio", 2, "repeat"), new_text=""), captured_at=now) is None


def test_http_feed_and_two_websocket_clients_receive_same_text(tmp_path):
    with TestClient(create_app(tmp_path / "feed.sqlite3")) as client:
        assert client.post("/api/matches", json=config()).status_code == 201
        url = "/api/matches/match-001/transcripts"
        assert client.get(url).json()["entries"] == []
        assert client.get("/api/matches/missing/transcripts").status_code == 404
        feed = client.app.state.transcript_feed
        now = datetime.now(timezone.utc)
        source = {"id": "radio-01", "name": "Rádio", "kind": "radio",
                  "url": None, "enabled": True, "status": "offline"}
        assert client.put("/api/matches/match-001/sources", json=[source]).status_code == 200
        with client.websocket_connect("/ws/matches/match-001/transcripts") as left:
            with client.websocket_connect("/ws/matches/match-001/transcripts") as right:
                assert left.receive_json()["kind"] == "snapshot"
                assert right.receive_json()["kind"] == "snapshot"
                feed.publish("match-001", "radio-01", window("radio-01", 0, "Bola na área"), captured_at=now)
                from_left = left.receive_json()
                from_right = right.receive_json()
                assert from_left == from_right
                assert from_left["kind"] == "transcript"
                assert from_left["data"]["text"] == "Bola na área"
        assert client.get(url).json()["entries"][0]["text"] == "Bola na área"
        # Internal entries for unregistered sources are never exposed via HTTP.
        feed.publish("match-001", "unknown", window("unknown", 0, "não autorizado"), captured_at=now)
        assert [entry["source_id"] for entry in client.get(url).json()["entries"]] == ["radio-01"]
        assert client.get(url + "?source_id=missing").status_code == 404
        assert client.get(url + "?limit=1000").status_code == 422


class SlowFakeASR:
    def __init__(self, text: str, delay: float = 0.12):
        self.text = text
        self.delay = delay

    def transcribe_pcm(self, block: bytes) -> ASRResult:
        time.sleep(self.delay)  # deliberately blocking code
        return ASRResult(
            model="tiny", language="pt", seconds=len(block) / 32000,
            text=self.text, segments=(),
        )


def test_async_worker_does_not_block_event_loop_and_keeps_sources_isolated():
    async def scenario():
        feed = TranscriptFeed()
        settings = WindowSettings(window_ms=1000, overlap_ms=250)
        left = AsyncSourceTranscriber(
            "match", "radio", RollingASRProcessor(SlowFakeASR("Gol do azul"), settings), feed,
        )
        right = AsyncSourceTranscriber(
            "match", "youtube", RollingASRProcessor(SlowFakeASR("Bola com o vermelho"), settings), feed,
        )
        pcm = struct.pack("<h", 100) * 16_000
        now = datetime.now(timezone.utc)
        marker = Event()

        async def responsive_loop():
            await asyncio.sleep(0.03)
            marker.set()

        pending = [
            asyncio.create_task(left.push(pcm, captured_at=now)),
            asyncio.create_task(right.push(pcm, captured_at=now)),
        ]
        await responsive_loop()
        assert marker.is_set()
        assert not all(task.done() for task in pending)
        await asyncio.gather(*pending)
        snapshot = feed.snapshot("match")
        assert {e["source_id"] for e in snapshot["entries"]} == {"radio", "youtube"}
        assert {e["language"] for e in snapshot["entries"]} == {"pt"}
        assert all(s["state"] == "ready" for s in snapshot["sources"])
        await asyncio.gather(left.finish(), right.finish())
        assert all(s["state"] == "stopped" for s in feed.snapshot("match")["sources"])

    asyncio.run(scenario())


def test_worker_errors_are_safe_and_stopping_is_idempotent():
    class BrokenASR:
        def transcribe_pcm(self, block: bytes):
            raise RuntimeError("secret signed URL https://media.test/private")
    async def scenario():
        feed = TranscriptFeed()
        session = AsyncSourceTranscriber(
            "match", "radio",
            RollingASRProcessor(BrokenASR(), WindowSettings(window_ms=1000, overlap_ms=250)),
            feed,
        )
        with pytest.raises(RuntimeError, match="secret signed"):
            await session.push(struct.pack("<h", 1) * 16_000,
                               captured_at=datetime.now(timezone.utc))
        snapshot = feed.snapshot("match")
        assert snapshot["sources"][0]["last_error"] == "asr_error"
        assert "media.test" not in str(snapshot)
        await session.finish()
        await session.finish()
        with pytest.raises(RuntimeError, match="stopped"):
            await session.push(struct.pack("<h", 1) * 16_000,
                               captured_at=datetime.now(timezone.utc))
    asyncio.run(scenario())
