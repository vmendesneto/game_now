"""Browser capture lifecycle with artificial sources, no external network/model."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.asr import BYTES_PER_SECOND
from app.audio_capture import CaptureError
from app.capture_runtime import CaptureRequest
from app.gn083_live import ASRCapacityError, LiveObservation, LivePreviewRegistry
from app.main import create_app
from app.youtube_capture import YouTubeResolutionError


MATCH = {"id": "capture-match", "home": {"id": "team-azul", "name": "Azul", "short_name": "AZU",
    "color": "#112233", "attack_direction": "left_to_right"}, "away": {
    "id": "team-rubro", "name": "Rubro", "short_name": "RUB", "color": "#ff2233",
    "attack_direction": "right_to_left"}}
SOURCE = {"id": "capture-source", "name": "Fonte artificial", "kind": "youtube",
          "url": "https://www.youtube.com/watch?v=test", "enabled": True}
BASE = "/api/matches/capture-match"


def setup(client):
    assert client.post("/api/matches", json=MATCH).status_code == 201
    assert client.put(BASE + "/sources", json=[SOURCE]).status_code == 200


def options(**changes):
    return {"source_id": SOURCE["id"], "permission_confirmed": True, **changes}


def until(client, expected):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get(BASE + "/capture").json()
        if status["state"] == expected:
            return status
        time.sleep(.01)
    pytest.fail(f"Capture did not reach {expected}: {status}")


def test_start_stream_two_clients_stop_restart_and_readonly_state(tmp_path):
    closed = []

    async def runner(url, match, **kwargs):
        assert url == SOURCE["url"] and kwargs["window_settings"].window_ms == 12000
        try:
            await asyncio.sleep(.02)
            for index, text in enumerate(("Começou o jogo", "Azul com a bola no meio-campo pela direita")):
                kwargs["on_pcm"](6 * BYTES_PER_SECOND)
                await kwargs["on_observation"]({"source_id": SOURCE["id"], "sequence": index,
                    "start_seconds": index * 6, "end_seconds": (index + 1) * 6, "text": text})
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    app = create_app(tmp_path / "state.sqlite3", capture_runner=runner)
    with TestClient(app) as client:
        setup(client)
        persisted = client.get(BASE + "/state").json()
        demo = client.get("/api/state").json()
        assert client.get(BASE + "/capture").json()["state"] == "idle"
        with client.websocket_connect("/ws/matches/capture-match/transcripts") as first:
            with client.websocket_connect("/ws/matches/capture-match/transcripts") as second:
                assert first.receive_json()["kind"] == "snapshot"
                assert second.receive_json()["kind"] == "snapshot"
                assert client.post(BASE + "/capture/start", json=options()).status_code == 202
                deadline = time.monotonic() + 3
                while len(client.get(BASE + "/transcripts").json()["entries"]) != 2:
                    assert time.monotonic() < deadline
                    time.sleep(.01)
                for socket in (first, second):
                    messages = [socket.receive_json()]
                    while not (messages[-1]["kind"] == "transcript" and messages[-1]["data"]["sequence"] == 1):
                        assert len(messages) < 15
                        messages.append(socket.receive_json())
                    assert messages[0]["kind"] == "snapshot"  # epoch reset
                    assert messages[-1]["kind"] == "transcript"
                    assert "Azul com a bola" in messages[-1]["data"]["text"]
                assert client.get("/health").status_code == 200
                assert client.post(BASE + "/capture/start", json=options()).status_code == 409
                assert client.put(BASE + "/sources", json=[]).status_code == 409
                assert client.put(BASE + "/players", json=[]).status_code == 409
                assert client.delete(BASE).status_code == 409
                preview = client.get(BASE + "/live/preview").json()
                assert preview["phase"] == "in_play" and preview["ball"]["zone"] == {"band": 3, "lane": "right"}
                assert client.post(BASE + "/capture/stop").status_code == 202
                until(client, "stopped")
                assert client.get(BASE + "/live/preview").json() is None
                assert client.get(BASE + "/state").json() == persisted
                assert client.get("/api/state").json() == demo
        assert client.post(BASE + "/capture/start", json=options()).status_code == 202
        until(client, "running")
        assert len(client.get(BASE + "/transcripts").json()["entries"]) == 2
    assert len(closed) == 2  # lifespan closes active workers
    assert not app.state.capture_runtime.active(MATCH["id"])


def test_confirmation_disabled_source_bad_inputs_and_error_sanitization(tmp_path):
    calls = []

    async def runner(*args, **kwargs):
        calls.append(True)
        raise RuntimeError("secret signed URL https://example.org?token=private")

    with TestClient(create_app(tmp_path / "bad.sqlite3", capture_runner=runner)) as client:
        setup(client)
        for changes in ({"permission_confirmed": False}, {"permission_confirmed": "true"},
                        {"start_seconds": -1}, {"start_seconds": True}, {"seconds": True},
                        {"seconds": 601}, {"window_seconds": 31},
                        {"url": "http://127.0.0.1"}):
            assert client.post(BASE + "/capture/start", json=options(**changes)).status_code == 422
        assert calls == []
        assert client.put(BASE + "/sources", json=[{**SOURCE, "enabled": False}]).status_code == 200
        assert client.post(BASE + "/capture/start", json=options()).status_code == 409
        assert calls == []
        assert client.put(BASE + "/sources", json=[SOURCE]).status_code == 200
        assert client.post(BASE + "/capture/start", json=options()).status_code == 202
        status = until(client, "error")
        assert status["error_code"] == "capture_failed"
        assert "private" not in str(status) and "https://" not in str(status)
        assert client.post(BASE + "/capture/stop").status_code == 202


@pytest.mark.parametrize("failure, expected", [
    (ASRCapacityError("private https://cdn.example.org?token=secret"), "asr_capacity_exceeded"),
    (YouTubeResolutionError("private https://cdn.example.org?token=secret"), "youtube_resolution_failed"),
    (CaptureError("decoder failed https://cdn.example.org?token=secret"), "capture_failed"),
    (CaptureError("upstream_http_403 https://cdn.example.org?token=secret"), "upstream_http_403"),
    (RuntimeError("youtube_resolution_failed https://cdn.example.org?token=secret"), "capture_failed"),
])
def test_capture_failure_stage_is_typed_and_private_details_are_hidden(tmp_path, failure, expected):
    async def runner(*args, **kwargs):
        raise failure

    with TestClient(create_app(tmp_path / "stage.sqlite3", capture_runner=runner)) as client:
        setup(client)
        before = client.get(BASE + "/state").json()
        assert client.post(BASE + "/capture/start", json=options()).status_code == 202
        status = until(client, "error")
        assert status["error_code"] == expected
        assert "secret" not in str(status) and "https://" not in str(status)
        assert client.get(BASE + "/state").json() == before


def test_delayed_local_audio_cannot_move_the_ball():
    from app.contracts import Match
    registry = LivePreviewRegistry()
    match = Match.model_validate(MATCH)
    registry.receive(match, LiveObservation(source_id="source-test", sequence=0,
        start_seconds=0, end_seconds=6, text="Começou o jogo", local_capture_age_seconds=0))
    preview = registry.receive(match, LiveObservation(source_id="source-test", sequence=1,
        start_seconds=6, end_seconds=12, text="Azul com a bola no meio-campo pela direita",
        local_capture_age_seconds=6))
    assert preview["phase"] == "in_play" and preview["ball"] is None


def test_cancel_before_worker_first_turn_and_no_automatic_restore(tmp_path):
    from app.capture_runtime import CaptureRuntime
    from app.configuration import MatchConfig
    from app.contracts import AudioSource
    from app.storage import SQLiteStore
    from app.transcription_feed import TranscriptFeed

    async def runner(*args, **kwargs):
        pytest.fail("Worker should have been cancelled before running")

    async def scenario():
        store = SQLiteStore(tmp_path / "cancel.sqlite3")
        store.create_match(MatchConfig.model_validate(MATCH))
        store.replace_sources(MATCH["id"], [AudioSource.model_validate(SOURCE)])
        runtime = CaptureRuntime(store, TranscriptFeed(), LivePreviewRegistry(), runner=runner)
        await runtime.start(MATCH["id"], CaptureRequest(**options()))
        await runtime.stop(MATCH["id"])
        await runtime.close()
        assert runtime.status(MATCH["id"])["state"] == "stopped"
        fresh = CaptureRuntime(store, TranscriptFeed(), LivePreviewRegistry(), runner=runner)
        assert fresh.status(MATCH["id"])["state"] == "idle"
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["radio", "youtube"])
def test_real_orchestrator_routes_registered_source_through_the_safe_capture_adapter(tmp_path, monkeypatch, kind):
    from app.asr import ASRResult
    from app.gn083_live import follow_youtube_narration

    source = {**SOURCE, "kind": kind}
    if kind == "radio":
        source["url"] = "https://radio.example.org/audio.mp3"
    called, closed = [], []

    class ASR:
        def transcribe_pcm(self, pcm):
            return ASRResult(model="base", language="pt", seconds=len(pcm) / BYTES_PER_SECOND,
                             text="Narração artificial para teste", segments=())

    async def capture(item, **kwargs):
        called.append(item.kind)
        assert item.url == source["url"] and kwargs["realtime"] is True
        assert ("yt_dlp_binary" in kwargs) == (kind == "youtube")
        try:
            for _ in range(12):
                yield b"\x00\x00" * 8000
                await asyncio.sleep(0)
        finally:
            closed.append(True)

    async def runner(*args, **kwargs):
        return await follow_youtube_narration(*args, **kwargs, transcriber=ASR())

    monkeypatch.setattr("app.capture_runtime." + ("pcm_chunks" if kind == "radio" else "youtube_pcm_chunks"), capture)
    with TestClient(create_app(tmp_path / "adapter.sqlite3", capture_runner=runner)) as client:
        setup(client)
        client.put(BASE + "/sources", json=[source])
        assert client.post(BASE + "/capture/start", json=options(seconds=6, window_seconds=6)).status_code == 202
        status = until(client, "finished")
        assert status["captured_seconds"] == 6 and status["observations"] == 1
        assert len(client.get(BASE + "/transcripts").json()["entries"]) == 1
        assert called == [kind] and closed == [True]
