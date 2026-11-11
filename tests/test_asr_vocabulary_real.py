"""GN-046: reproducible A/B context comparison with real faster-whisper CPU.

Both runs transcribe exactly the same offline synthesized Portuguese speech.
A/B scores are term recall on this fixture, not WER or natural-game quality.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import unicodedata

import pytest

from app.asr import ASRSettings, CPUTranscriber, read_pcm_wav
from app.asr_vocabulary import build_vocabulary_prompt
from app.contracts import Match
from scripts.synthetic_tts import synthesize_wav


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


@pytest.mark.skipif(os.getenv("GAME_NOW_REAL_ASR") != "1", reason="Heavy real-model opt-in A/B")
def test_real_cpu_vocabulary_ab_with_identical_portuguese_speech(tmp_path: Path):
    assert shutil.which("ffmpeg")
    wav = tmp_path / "voice.wav"
    wav16 = tmp_path / "voice16.wav"
    sentence = "Otávio Mendes passou a bola para Caio Ventura do Azul Futebol Clube. O goleiro defendeu e depois saiu um escanteio."
    synthesize_wav(sentence, wav, language="pt-br", words_per_minute=130)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", str(wav), "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(wav16)], check=True, capture_output=True)
    pcm = read_pcm_wav(wav16, max_seconds=25)
    match = Match.model_validate({
        "id": "match-001",
        "home": {"id": "azul", "name": "Azul Futebol Clube", "short_name": "AZU",
                 "color": "#123456", "attack_direction": "left_to_right"},
        "away": {"id": "vermelho", "name": "Vermelho Atlético", "short_name": "VER",
                 "color": "#654321", "attack_direction": "right_to_left"},
        "players": [
            {"id": "otavio", "team_id": "azul", "name": "Otávio Mendes",
             "number": 10, "aliases": ["Otávio"]},
            {"id": "caio", "team_id": "vermelho", "name": "Caio Ventura",
             "number": 9, "aliases": ["Caio"]},
        ],
    })
    settings = ASRSettings(model="base", cpu_threads=2, beam_size=5, max_seconds=25)
    a = CPUTranscriber(settings).transcribe_pcm(pcm)
    b = CPUTranscriber(replace(
        settings, initial_prompt=build_vocabulary_prompt(match)
    )).transcribe_pcm(pcm)
    target = ("otavio", "mendes", "caio", "ventura", "azul", "escanteio")
    score = lambda text: sum(term in _fold(text) for term in target)
    result = {
        "fixture": "synthetic_pt_br", "backend": "faster-whisper-base-cpu-int8",
        "target_terms": target, "a_without_context": a.text,
        "b_with_context": b.text, "a_term_hits": score(a.text),
        "b_term_hits": score(b.text), "term_count": len(target),
    }
    print("REAL_ASR_VOCAB_AB:", json.dumps(result, ensure_ascii=False))
    assert a.language == b.language == "pt"
    assert a.text.strip() and b.text.strip()
