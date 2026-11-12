"""GN-083 direct permitted YouTube -> ASR pipeline, fully mocked media/ASR."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.asr import ASRResult, BYTES_PER_SECOND
from app.contracts import Match, Player, Team
from app.gn083_stream import YoutubeTranscriptionRun, transcribe_youtube_source
from scripts.gn083_audit import main


def game():
    return Match(
        id="match-stream-083",
        home=Team(id="team-home", name="Azul", short_name="AZU",
                  color="#112233", attack_direction="left_to_right"),
        away=Team(id="team-away", name="Vermelho", short_name="VER",
                  color="#BB3322", attack_direction="right_to_left"),
        players=[Player(id="player-caio", team_id="team-home",
                        name="Caio Silva", number=9)],
    )


class FakeASR:
    def __init__(self):
        self.calls = 0

    def transcribe_pcm(self, pcm):
        self.calls += 1
        assert 0 < len(pcm) <= 6 * BYTES_PER_SECOND
        text = ("Caio Silva do Azul recebe a bola no meio-campo pela direita"
                if self.calls == 1 else "O Azul com a bola no meio-campo pela esquerda")
        return ASRResult(model="tiny", language="pt",
                         seconds=len(pcm) / BYTES_PER_SECOND, text=text, segments=())


def test_direct_stream_reuses_safe_capture_and_feeds_asr_without_saving_media():
    closed = []
    captured = []

    async def fake_capture(source, **options):
        assert source.kind == "youtube" and source.id == "youtube-083"
        assert source.url == "https://www.youtube.com/watch?v=Ls4qkPrh4Tk"
        assert options == {"yt_dlp_binary": "yt-dlp-test", "ffmpeg_binary": "ffmpeg-test"}
        try:
            for index in range(15):
                captured.append(index)
                yield b"\x01\x02" * 8000  # 0.5 seconds PCM
        finally:
            closed.append(True)

    fake = FakeASR()
    run = asyncio.run(transcribe_youtube_source(
        "https://www.youtube.com/watch?v=Ls4qkPrh4Tk",
        game(), seconds=7, yt_dlp_binary="yt-dlp-test",
        ffmpeg_binary="ffmpeg-test", transcriber=fake,
        capture_factory=fake_capture,
    ))
    assert run.complete and run.processed_seconds == 7
    assert run.processed_bytes == 7 * BYTES_PER_SECOND
    assert len(captured) == 14 and closed == [True]
    assert fake.calls == 2
    assert len(run.observations) == 2
    assert all("pcm" not in row and "url" not in row for row in run.observations)
    assert run.observations[0]["source_id"] == "youtube-083"
    assert run.observations[1]["end_seconds"] == 7


def test_short_recording_reports_incomplete_instead_of_false_300_second_success():
    async def source(_source, **_options):
        for _ in range(4):
            yield b"\x00\x00" * 8000

    result = asyncio.run(transcribe_youtube_source(
        "https://www.youtube.com/watch?v=Ls4qkPrh4Tk", game(),
        seconds=300, capture_factory=source, transcriber=FakeASR(),
    ))
    assert result.processed_seconds == 2
    assert not result.complete and result.requested_seconds == 300


def test_requested_media_start_does_not_change_clip_relative_annotation_times():
    async def capture(source, **options):
        assert options["start_seconds"] == 575
        yield b"\x00\x00" * 16000 * 6

    result = asyncio.run(transcribe_youtube_source(
        "https://www.youtube.com/watch?v=Ls4qkPrh4Tk", game(), seconds=6,
        start_seconds=575, capture_first=True, capture_factory=capture, transcriber=FakeASR(),
    ))
    assert result.requested_media_start_seconds == 575
    assert result.processed_seconds == 6 and result.complete
    assert result.observations[0]["start_seconds"] == 0
    assert result.observations[0]["end_seconds"] == 6


@pytest.mark.parametrize("seconds", [0, 4.99, 601, True])
def test_invalid_duration_rejected_before_capture(seconds):
    async def fail(_source, **_options):
        pytest.fail("Capture started")
        yield b"x"
    with pytest.raises(ValueError, match="duration"):
        asyncio.run(transcribe_youtube_source(
            "https://www.youtube.com/watch?v=Ls4qkPrh4Tk", game(),
            seconds=seconds, capture_factory=fail, transcriber=FakeASR(),
        ))


def test_private_url_rejected_before_capture():
    async def fail(_source, **_options):
        pytest.fail("Capture started")
        yield b"x"
    with pytest.raises(ValueError, match="Invalid"):
        asyncio.run(transcribe_youtube_source(
            "http://127.0.0.1/secret", game(), seconds=5,
            capture_factory=fail, transcriber=FakeASR(),
        ))


def test_invalid_stream_pcm_rejected_and_generator_closed():
    closed = []
    async def invalid(_source, **_options):
        try:
            yield b"x"
        finally:
            closed.append(True)
    with pytest.raises(ValueError, match="invalid PCM"):
        asyncio.run(transcribe_youtube_source(
            "https://www.youtube.com/watch?v=Ls4qkPrh4Tk", game(),
            seconds=5, capture_factory=invalid, transcriber=FakeASR(),
        ))
    assert closed == [True]


def test_cli_direct_url_requires_permission_and_emits_safe_metadata(tmp_path: Path, monkeypatch):
    match_file = tmp_path / "match.json"
    match_file.write_text(game().model_dump_json(), encoding="utf-8")
    report_file = tmp_path / "report.json"
    url = "https://www.youtube.com/watch?v=Ls4qkPrh4Tk"
    arguments = ["--youtube-url", url, "--match-json", str(match_file),
                 "--output", str(report_file)]
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert not report_file.exists()

    calls = []
    async def fake_source(source_url, current_match, **kwargs):
        calls.append((source_url, current_match, kwargs))
        return YoutubeTranscriptionRun(
            source_id="youtube-083", requested_seconds=300,
            processed_seconds=300, processed_bytes=9_600_000, complete=True,
            observations=({
                "source_id": "youtube-083", "sequence": 0,
                "start_seconds": 0, "end_seconds": 6,
                "text": "Caio Silva do Azul com a bola no meio-campo pela direita",
            },),
            requested_media_start_seconds=kwargs.get("start_seconds", 0),
        )
    monkeypatch.setattr("scripts.gn083_audit.transcribe_youtube_source", fake_source)
    assert main(arguments + ["--permission-confirmed", "--start-seconds", "575"]) == 0
    result = json.loads(report_file.read_text(encoding="utf-8"))
    assert len(calls) == 1 and calls[0][0] == url
    assert calls[0][1].id == "match-stream-083"
    assert calls[0][2]["start_seconds"] == 575
    assert result["requested_media_start_seconds"] == 575
    assert result["media_start_verified"] is False
    assert result["observation_time_origin"] == "clip_start"
    assert result["input_type"] == "youtube_stream_asr"
    assert result["audio_seconds_processed"] == 300
    assert result["audio_duration_complete"] is True
    assert result["metrics"] is None
    assert result["source"] == "youtube-083"
    assert url not in str(result)
    assert "text" not in result["predictions"][0]
    assert result["persisted"] is False and result["audio_retransmitted"] is False


def test_cli_seek_rejected_for_offline_input_before_reading_files(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(["--wav", str(tmp_path / "missing.wav"), "--match-json",
              str(tmp_path / "missing.json"), "--start-seconds", "575"])
    assert error.value.code == 2
