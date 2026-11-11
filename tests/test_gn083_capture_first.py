"""GN-083: capture-first mode avoids CPU stalls and respects source access."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.asr import ASRResult, BYTES_PER_SECOND
from app.audio_capture import CaptureError
from app.contracts import Match, Team
from app.gn083_stream import YoutubeTranscriptionRun, transcribe_youtube_source
from scripts.gn083_audit import main


def game() -> Match:
    return Match(
        id="cruzeiro-bahia-test",
        home=Team(id="cruzeiro", name="Cruzeiro", short_name="CRU",
                  color="#003399", attack_direction="left_to_right"),
        away=Team(id="bahia", name="Bahia", short_name="BAH",
                  color="#CC3344", attack_direction="right_to_left"),
    )


class ASR:
    def __init__(self, events: list):
        self.events = events

    def transcribe_pcm(self, pcm):
        self.events.append(("inference", len(pcm)))
        return ASRResult(
            model="base", language="pt", seconds=len(pcm) / BYTES_PER_SECOND,
            text="Cruzeiro com a bola", segments=(),
        )


def test_capture_first_finishes_media_before_cpu_inference():
    events = []

    async def fake_capture(_source, **_opts):
        try:
            for index in range(15):
                events.append(("capture", index))
                yield b"\x01\x00" * 8000  # 0.5 seconds
        finally:
            events.append(("closed",))

    run = asyncio.run(transcribe_youtube_source(
        "https://www.youtube.com/watch?v=Ls4qkPrh4Tk",
        game(), seconds=7, model="base", capture_first=True,
        transcriber=ASR(events), capture_factory=fake_capture,
    ))
    assert run.complete and run.processed_seconds == 7
    assert run.processed_bytes == 7 * BYTES_PER_SECOND
    assert [e for e in events if e[0] == "capture"] == [
        ("capture", index) for index in range(14)
    ]
    close_at = events.index(("closed",))
    assert all(e[0] != "inference" for e in events[:close_at])
    assert len([e for e in events if e[0] == "inference"]) == 2
    assert len(run.observations) == 1  # text overlap is de-duplicated
    assert all("pcm" not in item for item in run.observations)


@pytest.mark.parametrize("capture_first", [False, True])
def test_http_403_is_not_retried_and_reports_safe_received_duration(capture_first):
    calls = []
    events = []

    async def blocked(_source, **_opts):
        calls.append(True)
        try:
            for _ in range(4):
                yield b"\x00\x00" * 8000
            raise CaptureError("Remote media request failed (upstream_http_403); check source access")
        finally:
            events.append("closed")

    with pytest.raises(CaptureError, match=r"upstream_http_403.*2\.0s") as err:
        asyncio.run(transcribe_youtube_source(
            "https://www.youtube.com/watch?v=Ls4qkPrh4Tk",
            game(), seconds=300, capture_first=capture_first,
            transcriber=ASR(events), capture_factory=blocked,
        ))
    assert calls == [True] and events == ["closed"]
    assert "www.youtube.com" not in str(err.value)


def test_capture_first_cli_passes_flag_without_persisting_audio(tmp_path, monkeypatch):
    match_file = tmp_path / "match.json"
    match_file.write_text(game().model_dump_json(), encoding="utf-8")
    output_file = tmp_path / "report.json"
    calls = []

    async def fake_run(_url, _match, **options):
        calls.append(options)
        return YoutubeTranscriptionRun(
            source_id="youtube-083", requested_seconds=7.0,
            processed_seconds=7.0, processed_bytes=7 * BYTES_PER_SECOND,
            complete=True, observations=(),
        )

    monkeypatch.setattr("scripts.gn083_audit.transcribe_youtube_source", fake_run)
    assert main([
        "--youtube-url", "https://www.youtube.com/watch?v=Ls4qkPrh4Tk",
        "--match-json", str(match_file), "--permission-confirmed",
        "--capture-first", "--seconds", "7", "--output", str(output_file),
    ]) == 0
    assert calls[0]["capture_first"] is True
    report = json.loads(output_file.read_text(encoding="utf-8"))
    assert report["audio_seconds_processed"] == 7
    assert report["audio_retransmitted"] is False
    assert report["predictions"] == []
