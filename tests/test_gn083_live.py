"""GN-083 ephemeral live preview + continuous fake PCM; no real broadcast."""
from __future__ import annotations

import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

from app.asr import ASRResult, BYTES_PER_SECOND
from app.contracts import Match, Team
from app.gn083_live import LiveObservation, LivePreviewRegistry, follow_youtube_narration
from app.main import create_app


def test_stop_waits_for_cpu_inference_and_closes_capture():
    started, release, ended = threading.Event(), threading.Event(), threading.Event()
    capture_closed = []

    class BlockingASR:
        def transcribe_pcm(self, pcm):
            started.set()
            assert release.wait(3)
            ended.set()
            return ASRResult(model="tiny", language="pt", seconds=6, text="Teste", segments=())

    async def capture(*args, **kwargs):
        try:
            for _ in range(12):
                yield b"\x00\x00" * 8000
                await asyncio.sleep(0)
            await asyncio.Event().wait()
        finally:
            capture_closed.append(True)

    async def scenario():
        task = asyncio.create_task(follow_youtube_narration(
            "https://www.youtube.com/watch?v=test", game(), max_seconds=60,
            on_observation=lambda row: None, transcriber=BlockingASR(), capture_factory=capture))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(.01)
            assert not task.done() and not ended.is_set()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=2)
            assert ended.is_set() and capture_closed == [True]
        finally:
            release.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    asyncio.run(scenario())


def game(name="match-live-083"):
    return Match(
        id=name,
        home=Team(id="team-azul", name="Azul", short_name="AZU",
                  color="#2266AA", attack_direction="left_to_right"),
        away=Team(id="team-rubro", name="Rubro", short_name="RUB",
                  color="#DD3344", attack_direction="right_to_left"),
    )


def row(n, phrase, source="source-083"):
    return LiveObservation(
        source_id=source, sequence=n, start_seconds=n * 6,
        end_seconds=n * 6 + 6, text=phrase,
    )


def test_live_registry_gates_ball_before_start_during_break_and_on_staleness():
    clock = [0.]
    registry = LivePreviewRegistry(clock=lambda: clock[0])
    match = game()
    assert registry.receive(match, row(0, "A bola vai rolar"))["phase"] == "pre_game"
    assert registry.receive(match, row(1, "Começou o jogo"))["phase"] == "probable_start"
    assert registry.get(match.id)["ball"] is None
    confirmed = registry.receive(match, row(
        2, "Azul com a bola no meio-campo pela direita",
    ))
    assert confirmed["phase"] == "in_play"
    assert confirmed["ball"] is not None
    assert confirmed["ball"]["team_id"] == "team-azul"
    assert confirmed["ball"]["zone"] == {"band": 3, "lane": "right"}
    assert confirmed["persisted"] is False and confirmed["audio_retransmitted"] is False

    clock[0] = 9.
    assert registry.get(match.id)["ball"] is None
    assert registry.get(match.id)["active"]
    interval = registry.receive(match, row(3, "Terminou o primeiro tempo"))
    assert interval["phase"] == "half_time" and interval["ball"] is None
    assert registry.receive(match, row(4, "Começa o segundo tempo"))["ball"] is None
    second = registry.receive(match, row(5, "Azul com a bola no meio-campo pela direita"))
    assert second["phase"] == "second_half"
    assert second["ball"] is not None
    clock[0] = 45.
    assert registry.get(match.id)["active"] is False
    assert registry.get(match.id)["ball"] is None


def test_registry_isolates_sources_matches_and_does_not_persist():
    registry = LivePreviewRegistry()
    first = game()
    other = game("other-live-083")
    registry.receive(first, row(0, "Começou o jogo"))
    assert registry.get(other.id) is None
    assert registry.receive(first, row(0, "A bola vai rolar", "other-source"))["phase"] == "pre_game"
    assert registry.get(first.id)["phase"] == "pre_game" or registry.get(first.id)["phase"] == "probable_start"
    registry.clear_match(first.id)
    assert registry.get(first.id) is None


def test_api_preview_does_not_change_sqlite_or_demo(tmp_path):
    with TestClient(create_app(tmp_path / "gn083.sqlite3")) as client:
        match=game()
        payload = match.model_dump(mode="json", exclude={"players"})
        assert client.post("/api/matches", json=payload).status_code == 201
        base = f"/api/matches/{match.id}"
        original = client.get(base + "/state").json()
        demo = client.get("/api/state").json()
        assert client.get(base + "/live/preview").json() is None
        assert client.post(base + "/live/observation", json=row(
            0, "Começou o jogo",
        ).model_dump()).json()["phase"] == "probable_start"
        current = client.post(base + "/live/observation", json=row(
            1, "Azul com a bola no meio-campo pela direita",
        ).model_dump())
        assert current.status_code == 200
        assert current.json()["phase"] == "in_play"
        assert current.json()["ball"]["zone"] == {"band": 3, "lane": "right"}
        assert client.get(base + "/live/preview").json()["active"]
        assert client.get(base + "/state").json() == original
        assert client.get("/api/state").json() == demo
        bad = client.post(base + "/live/observation", json=row(
            1, "Outro texto",
        ).model_dump())
        assert bad.status_code == 422
        assert client.delete(base).status_code == 204
        assert client.get(base + "/live/preview").status_code == 404


def test_follow_live_uses_safe_youtube_capture_and_overlapping_asr():
    received, captured, closed = [], [], []

    class ASR:
        calls = 0
        def transcribe_pcm(self, pcm):
            self.calls += 1
            sentence = "Começou o jogo" if self.calls == 1 else (
                "Azul com a bola no meio-campo pela direita"
            )
            return ASRResult(
                model="tiny", language="pt", seconds=len(pcm) / BYTES_PER_SECOND,
                text=sentence, segments=(),
            )

    async def capture(source, **kwargs):
        assert source.kind == "youtube"
        assert kwargs["yt_dlp_binary"] == "yt-dlp-test"
        try:
            for i in range(17):
                captured.append(i)
                yield b"\x01\x02" * 8000
                await asyncio.sleep(0.001)
        finally:
            closed.append(True)

    async def listener(observation):
        received.append(observation)

    result = asyncio.run(follow_youtube_narration(
        "https://www.youtube.com/watch?v=Ls4qkPrh4Tk", game(),
        model="tiny", yt_dlp_binary="yt-dlp-test",
        max_seconds=7, on_observation=listener,
        transcriber=ASR(), capture_factory=capture,
    ))
    assert result.stopped_at_limit
    assert result.captured_seconds == 7
    assert result.audio_bytes == 7 * BYTES_PER_SECOND
    assert len(captured) == 14 and closed == [True]
    assert result.observations == 2
    assert "pcm" not in received[0] and "url" not in received[0]
    detector = LivePreviewRegistry()
    for observation in received:
        detected = detector.receive(game(), LiveObservation(**observation))
    assert detected["phase"] == "in_play"


@pytest.mark.parametrize("limit", [0, 4.9, 601, True])
def test_invalid_live_test_limit_rejected_without_capture(limit):
    async def capture(*_args, **_kwargs):
        pytest.fail("Should not capture")
        yield b"\x00\x00"

    with pytest.raises(ValueError, match="duration"):
        asyncio.run(follow_youtube_narration(
            "https://www.youtube.com/watch?v=Ls4qkPrh4Tk",
            game(), max_seconds=limit, on_observation=lambda row: None,
            capture_factory=capture,
        ))
