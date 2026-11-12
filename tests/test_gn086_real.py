"""GN-086: opt-in genuine dual-model CPU run on offline synthesized pt-BR speech.

Executed only in dedicated GitHub Actions ASR workflow. Never uses radio,
YouTube, cloud recognition or user-provided media.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from app.asr import read_pcm_wav
from scripts.benchmark_gn086 import benchmark
from scripts.synthetic_tts import synthesize_wav


@pytest.mark.skipif(os.getenv("GAME_NOW_REAL_ASR") != "1", reason="Opt-in real CPU ASR")
def test_two_concurrent_real_cpu_models_report_resource_use(tmp_path: Path):
    assert shutil.which("ffmpeg")
    original = tmp_path / "original.wav"
    normalized = tmp_path / "normalized.wav"
    synthesize_wav(
        "O time azul passa a bola para o atacante. A partida começou.",
        original, language="pt-br", words_per_minute=140,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(original), "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", str(normalized)],
        check=True, capture_output=True,
    )
    pcm = read_pcm_wav(normalized, max_seconds=30)
    result = asyncio.run(benchmark(
        engine="real", pcm=pcm, sources=2,
        model="tiny", cpu_threads=2, window_ms=2000, overlap_ms=500,
        buffer_seconds=3,
    ))
    print("GN086_REAL_CPU_BENCHMARK:", json.dumps(result, ensure_ascii=False))
    assert result["engine"] == "real_faster_whisper_cpu_int8"
    assert result["sources"] == 2
    assert result["total_inference_calls"] >= 2
    assert result["peak_buffer_bytes_per_source"] <= 96_000
    assert result["process_cpu_seconds"] >= 0
    assert result["process_peak_rss_mb"] is not None  # CI is Linux
    assert result["max_overlapping_inferences"] >= 1
    assert set(result["source_states"].values()) == {"stopped"}
    assert result["speech_accuracy_measured"] is False
