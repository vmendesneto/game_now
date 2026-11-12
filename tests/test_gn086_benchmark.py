"""GN-086: reproducible benchmarks using fake CPU work (not real ASR)."""
from __future__ import annotations

import asyncio

import pytest

from scripts.benchmark_gn086 import benchmark


@pytest.mark.parametrize("sources", [2, 3])
def test_concurrent_source_benchmark_is_bounded_and_reports_cpu_memory(sources):
    result = asyncio.run(benchmark(
        sources=sources, seconds=4, window_ms=1000,
        overlap_ms=250, buffer_seconds=1,
    ))
    assert result["engine"] == "synthetic_mock_not_asr"
    assert result["sources"] == sources
    assert result["total_inference_calls"] >= 3 * sources
    assert result["max_overlapping_inferences"] >= 1
    assert result["peak_buffer_bytes_per_source"] <= 32_000
    assert result["max_configured_buffer_bytes_per_source"] == 32_000
    assert result["process_cpu_seconds"] >= 0
    assert result["wall_seconds"] >= 0
    assert result["peak_python_tracemalloc_mb"] >= 0
    assert len(result["source_states"]) == sources
    assert set(result["source_states"].values()) == {"stopped"}
    assert result["speech_accuracy_measured"] is False
    assert result["real_windows_or_radio_test"] is False
    assert "pcm" not in result
    assert "text" not in result


@pytest.mark.parametrize("kwargs", [
    {"sources": 1}, {"sources": 5},
    {"buffer_seconds": 0}, {"buffer_seconds": 31},
    {"seconds": 0}, {"seconds": 31},
    {"window_ms": 500}, {"overlap_ms": 2000},
    {"engine": "not-real"}, {"engine": "real"},
    {"engine": "synthetic", "pcm": b"\x00\x00"},
    {"engine": "real", "pcm": b"\x00"},
])
def test_invalid_benchmark_configurations_rejected(kwargs):
    with pytest.raises(ValueError):
        asyncio.run(benchmark(**kwargs))
