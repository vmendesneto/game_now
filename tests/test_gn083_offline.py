"""GN-083 synthetic regression tests. Never claim synthetic data is real accuracy."""
from __future__ import annotations

import json
from pathlib import Path
import wave

import pytest

from app.asr import ASRResult, BYTES_PER_SECOND
from app.contracts import Match, Player, Team
from app.gn083_offline import (
    analyze_observations, evaluate, pcm_chunks, transcribe_file, validate_observations,
)
from scripts.gn083_audit import main


def game():
    return Match(
        id="match-083",
        home=Team(id="team-azul", name="Azul", short_name="AZU", color="#112233",
                  attack_direction="left_to_right"),
        away=Team(id="team-rubro", name="Rubro", short_name="RUB", color="#BB3322",
                  attack_direction="right_to_left"),
        players=[
            Player(id="player-caio", team_id="team-azul", name="Caio Silva", number=9),
            Player(id="player-bruno", team_id="team-rubro", name="Bruno Costa", number=10),
        ],
    )


def item(seq, phrase):
    return {"source_id": "source-083", "sequence": seq, "start_seconds": seq * 6,
            "end_seconds": seq * 6 + 6, "text": phrase}


def test_text_analysis_is_read_only_and_reuses_existing_football_rules():
    match = game()
    before = match.model_dump(mode="json")
    inputs = [
        item(0, "Caio Silva do Azul recebe a bola no meio-campo pela direita"),
        item(1, "No replay Caio Silva do Azul recebe a bola na área adversária pela direita"),
        item(2, "Oferecimento: Bruno Costa do Rubro marcou o gol"),
        item(3, "Bruno Costa do Rubro chutou"),
        item(4, "Caio Silva do Azul com a bola na intermediária ofensiva pela esquerda"),
    ]
    output = analyze_observations(match, inputs)
    assert output[0]["team_id"] == "team-azul"
    assert output[0]["player_id"] == "player-caio"
    assert output[0]["possession_team_id"] == "team-azul"
    assert output[0]["zone"] == {"band": 3, "lane": "right"}
    assert output[0]["event_kind"] is None
    assert output[1]["narration_kind"] == "replay"
    assert output[2]["narration_kind"] == "ad"
    for row in output[1:3]:
        assert row["team_id"] is None and row["player_id"] is None
        assert row["zone"] is None and row["event_kind"] is None
    assert output[3]["event_kind"] == "shot"
    assert output[4]["zone"] == {"band": 4, "lane": "left"}
    assert all(row["state_updated"] is False and "text" not in row for row in output)
    assert match.model_dump(mode="json") == before


def test_ambiguous_player_never_becomes_confirmed_team():
    match = game()
    match.players.append(Player(id="other-caio", team_id="team-rubro",
                                name="Caio Silva", number=19))
    output = analyze_observations(
        match, [item(0, "Caio Silva com a bola no meio-campo pela direita")])[0]
    assert output["player_id"] is None and output["team_id"] is None
    assert output["zone"] is None


def test_reference_scoring_covers_errors_abstentions_and_unmatched():
    predictions = analyze_observations(game(), [
        item(0, "Caio Silva do Azul recebe a bola no meio-campo pela direita"),
        item(1, "No replay Bruno Costa do Rubro recebe a bola"),
        item(2, "Bruno Costa do Rubro chutou"),
    ], include_text=True)
    reference = [
        {"source_id": "source-083", "start_seconds": 0, "end_seconds": 6,
         "team_id": "team-azul", "player_id": "player-caio",
         "zone": {"band": 3, "lane": "right"}, "event_kind": None,
         "reference_text": "Caio Silva do Azul recebe a bola no meio-campo pela direita"},
        {"source_id": "source-083", "start_seconds": 6, "end_seconds": 12,
         "team_id": None, "player_id": None, "zone": None, "event_kind": None},
        {"source_id": "source-083", "start_seconds": 12, "end_seconds": 18,
         "team_id": "team-rubro", "player_id": "player-bruno",
         "zone": None, "event_kind": "goal"},
    ]
    result = evaluate(predictions, reference)
    assert result["aligned_segments"] == 3
    assert result["metrics"]["team_id"]["correct"] == 2
    assert result["metrics"]["event_kind"]["false_positives"] == 1
    assert result["metrics"]["event_kind"]["false_negatives"] == 1
    assert result["metrics"]["event_kind"]["precision"] == 0.0
    assert result["word_error_rate"] == 0.0
    assert evaluate(predictions[:1], reference)["metrics"]["team_id"]["false_negatives"] == 1
    assert evaluate(predictions, reference[:1])["unmatched_predictions"] == 2
    assert evaluate(predictions, [{"source_id": "other-083", "start_seconds": 0,
                                   "end_seconds": 6, "team_id": "team-azul"}])["aligned_segments"] == 0


def test_time_pairing_never_chooses_correct_label_instead_of_nearest():
    predictions = [
        {"source_id": "source-083", "start_seconds": 0, "end_seconds": 6, "team_id": "bad"},
        {"source_id": "source-083", "start_seconds": .5, "end_seconds": 6.5, "team_id": "good"},
    ]
    reference = [{"source_id": "source-083", "start_seconds": 0, "end_seconds": 6,
                  "team_id": "good"}]
    result = evaluate(predictions, reference)
    assert result["metrics"]["team_id"]["correct"] == 0
    assert result["unmatched_predictions"] == 1


@pytest.mark.parametrize("broken", [
    [item(0, "ok"), item(0, "duplicate")],
    [item(1, "ok"), item(0, "out of order")],
    [{**item(0, "ok"), "end_seconds": 601}],
    [{**item(0, "ok"), "text": ""}],
    [{**item(0, "ok"), "source_id": "x"}],
])
def test_invalid_window_rejected(broken):
    with pytest.raises(ValueError):
        validate_observations(broken)


def test_pcm_streaming_validates_format_alignment_and_duration(tmp_path: Path):
    pcm = b"\x11\x22" * 16000
    raw = tmp_path / "sample.pcm"
    raw.write_bytes(pcm)
    assert len(list(pcm_chunks(raw, raw=True))) == 2
    assert b"".join(pcm_chunks(raw, raw=True)) == pcm
    with pytest.raises(ValueError):
        list(pcm_chunks(raw, raw=True, max_seconds=0))
    raw.write_bytes(pcm + b"x")
    with pytest.raises(ValueError, match="aligned"):
        list(pcm_chunks(raw, raw=True))
    wav = tmp_path / "sample.wav"
    with wave.open(str(wav), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(pcm)
    assert b"".join(pcm_chunks(wav)) == pcm
    with wave.open(str(wav), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(pcm)
    with pytest.raises(ValueError, match="mono"):
        list(pcm_chunks(wav))


def test_offline_audio_passes_bounded_windows_to_existing_asr(tmp_path: Path):
    wav = tmp_path / "seven.wav"
    with wave.open(str(wav), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x01\x02" * (7 * 16000))

    class FakeTranscriber:
        def __init__(self):
            self.calls = 0

        def transcribe_pcm(self, pcm):
            self.calls += 1
            assert 0 < len(pcm) <= 6 * BYTES_PER_SECOND
            text = "Azul com a bola" if self.calls == 1 else "no meio-campo pela direita"
            return ASRResult(model="tiny", language="pt",
                             seconds=len(pcm) / BYTES_PER_SECOND, text=text, segments=())

    fake = FakeTranscriber()
    result = transcribe_file(wav, game(), source_id="source-083", transcriber=fake)
    assert fake.calls == 2
    assert [row["sequence"] for row in result] == [0, 1]
    assert result[0]["start_seconds"] == 0
    assert result[1]["end_seconds"] == 7
    assert all("pcm" not in row for row in result)


def test_cli_transcripts_do_not_claim_metrics_without_reference(tmp_path: Path):
    match_file = tmp_path / "game.json"
    match_file.write_text(game().model_dump_json(), encoding="utf-8")
    observations_file = tmp_path / "text.json"
    observations_file.write_text(json.dumps([item(0, "Azul com a bola no meio-campo pela direita")]),
                                 encoding="utf-8")
    output_file = tmp_path / "report.json"
    args = ["--match-json", str(match_file), "--transcripts", str(observations_file),
            "--output", str(output_file)]
    assert main(args) == 0
    report = json.loads(output_file.read_text(encoding="utf-8"))
    assert report["observations"] == 1 and report["metrics"] is None
    assert report["reference_evaluated"] is False
    assert report["persisted"] is False and report["audio_retransmitted"] is False
    assert "text" not in report["predictions"][0]
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps([{"source_id": "source-083", "start_seconds": 0,
                                "end_seconds": 6, "zone": {"band": 3, "lane": "right"}}]),
                    encoding="utf-8")
    assert main(args + ["--reference", str(gold)]) == 0
    scored = json.loads(output_file.read_text(encoding="utf-8"))
    assert scored["metrics"]["metrics"]["zone"]["correct"] == 1


def test_cli_requires_explicit_permission_before_opening_audio(tmp_path: Path):
    game_file = tmp_path / "match.json"
    game_file.write_text(game().model_dump_json(), encoding="utf-8")
    audio_file = tmp_path / "audio.wav"
    audio_file.write_bytes(b"not-a-wav")
    with pytest.raises(SystemExit) as exc:
        main(["--match-json", str(game_file), "--wav", str(audio_file)])
    assert exc.value.code == 2
