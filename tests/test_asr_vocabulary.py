"""GN-046: deterministic roster vocabulary and optional whisper prompt."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import struct

import pytest

from app.asr import ASRSettings, CPUTranscriber
from app.asr_vocabulary import build_vocabulary_prompt
from app.contracts import Match


def sample_match():
    return Match.model_validate({
        "id": "match-001",
        "home": {"id": "azul", "name": "Azul Futebol Clube", "short_name": "AZU",
                 "color": "#123456", "attack_direction": "left_to_right"},
        "away": {"id": "vermelho", "name": "Vermelho Atlético", "short_name": "VER",
                 "color": "#654321", "attack_direction": "right_to_left"},
        "players": [
            {"id": "player-1", "team_id": "azul", "name": "Otávio Mendes",
             "number": 10, "aliases": ["Otávio"], "starter": True},
            {"id": "player-2", "team_id": "vermelho", "name": "Caio Ventura",
             "number": 9, "aliases": ["Caio"], "starter": True},
        ],
    })


def test_context_includes_clubs_players_and_football_terms():
    prompt = build_vocabulary_prompt(sample_match())
    assert "Azul Futebol Clube" in prompt
    assert "Vermelho Atlético" in prompt
    assert "Otávio Mendes" in prompt and "Caio Ventura" in prompt
    assert "escanteio" in prompt and "impedimento" in prompt
    assert len(prompt) <= 500
    assert "\n" not in prompt


def test_context_bounded_with_large_roster_and_invalid_settings():
    match = sample_match()
    for i in range(3, 95):
        match.players.append(match.players[0].model_copy(
            update={"id": f"extra-{i}", "name": f"Nome Longo de Jogador Número {i}", "number": i}
        ))
    prompt = build_vocabulary_prompt(match, max_chars=200)
    assert len(prompt) <= 200
    with pytest.raises(ValueError, match="max_chars"):
        build_vocabulary_prompt(match, max_chars=199)
    with pytest.raises(ValueError, match="initial_prompt"):
        ASRSettings(initial_prompt="invalido\nnova linha")
    with pytest.raises(ValueError, match="initial_prompt"):
        ASRSettings(initial_prompt="x" * 601)


def test_cpu_model_receives_context_only_when_configured():
    received = []
    class Fake:
        def transcribe(self, audio, **kwargs):
            received.append(kwargs)
            return iter([SimpleNamespace(start=0, end=0.5, text="Gol do Azul")]), SimpleNamespace(language="pt")
    settings = ASRSettings(initial_prompt=build_vocabulary_prompt(sample_match()))
    transcriber = CPUTranscriber(settings, model_factory=lambda *a, **k: Fake())
    pcm = struct.pack("<h", 10) * 16_000
    assert transcriber.transcribe_pcm(pcm).text == "Gol do Azul"
    assert received[-1]["initial_prompt"] == settings.initial_prompt
    assert received[-1]["language"] == "pt"
    without = CPUTranscriber(replace(settings, initial_prompt=None), model_factory=lambda *a, **k: Fake())
    without.transcribe_pcm(pcm)
    assert "initial_prompt" not in received[-1]


def test_live_profile_uses_local_vad_and_one_decoding_temperature_without_changing_model():
    received = []
    class Fake:
        def transcribe(self, audio, **kwargs):
            received.append(kwargs)
            return iter([]), SimpleNamespace(language='pt')
    settings = ASRSettings(model='small', live_mode=True)
    transcriber = CPUTranscriber(settings, model_factory=lambda *a, **k: Fake())
    result = transcriber.transcribe_pcm(struct.pack('<h', 10)*16000)
    assert result.model == 'small' and result.seconds == 1
    assert received[-1]['vad_filter'] is True and received[-1]['temperature'] == 0.0
    standard = CPUTranscriber(replace(settings, live_mode=False), model_factory=lambda *a, **k: Fake())
    standard.transcribe_pcm(struct.pack('<h', 10)*16000)
    assert received[-1]['vad_filter'] is False and 'temperature' not in received[-1]
    with pytest.raises(ValueError, match='live_mode'):
        ASRSettings(live_mode='true')
