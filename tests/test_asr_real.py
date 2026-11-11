"""GN-040: opt-in real faster-whisper CPU inference from synthesized PT speech.

Uses an offline espeak-ng voice (not a radio, user recording, or live stream).
Intended to run in the dedicated GitHub Actions ASR smoke workflow.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import unicodedata

import pytest

from app.asr import ASRSettings, CPUTranscriber, read_pcm_wav
from app.asr_windows import RollingASRProcessor, WindowSettings


@pytest.mark.skipif(os.getenv("GAME_NOW_REAL_ASR") != "1", reason="Heavy opt-in CPU test")
def test_real_portuguese_speech_on_cpu(tmp_path: Path):
    assert shutil.which("espeak-ng"), "Install espeak-ng to generate Portuguese speech"
    assert shutil.which("ffmpeg"), "Install FFmpeg to normalize the fixture"
    original = tmp_path / "speech-original.wav"
    normalized = tmp_path / "speech-16k.wav"
    phrase = "O jogo de futebol começou agora. A bola está no meio do campo. O atacante chutou e fez um gol."
    subprocess.run(
        ["espeak-ng", "-v", "pt-br", "-s", "130", "-w", str(original), phrase],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(original),
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(normalized)],
        check=True, capture_output=True,
    )
    pcm = read_pcm_wav(normalized, max_seconds=20)
    model = CPUTranscriber(ASRSettings(model="base", cpu_threads=2, beam_size=5, max_seconds=20))
    result = model.transcribe_pcm(pcm)
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", result.text.casefold())
        if not unicodedata.combining(char)
    )
    print("REAL_CPU_ASR_RESULT:", result.text)
    assert result.language == "pt"
    assert result.segments and len(result.text) >= 8
    assert any(word in plain for word in ("futebol", "bola", "campo", "gol")), plain

    # GN-041: same real CPU backend over partially overlapping windows.
    rolling = RollingASRProcessor(
        model, WindowSettings(window_ms=5000, overlap_ms=2000, min_tail_ms=500)
    )
    windows = []
    for index in range(0, len(pcm), 16_000):  # PCM bytes = 0.5s
        windows.extend(rolling.push("synthetic-pt", pcm[index:index + 16_000]))
    windows.extend(rolling.finish("synthetic-pt"))
    assert len(windows) >= 2
    assert any(window.raw_text.strip() for window in windows)
    assert all(window.language == "pt" for window in windows)
    print("REAL_ROLLING_CPU_ASR_WINDOWS:", len(windows))
    print("REAL_ROLLING_CPU_ASR_TEXT:", " ".join(item.new_text for item in windows))
