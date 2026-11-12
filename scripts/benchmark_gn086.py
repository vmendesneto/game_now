"""GN-086: concurrent source ASR CPU/memory benchmark.

Default engine uses a clearly labeled synthetic *mock*, not speech recognition.
Opt-in real engine consumes an authorized local 16-kHz mono PCM WAV and loads a
separate faster-whisper CPU int8 model per source. No streams or media uploads.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import platform
import sys
from threading import Lock
from time import perf_counter, process_time
import tracemalloc

from app.asr import ASRResult, ASRSettings, BYTES_PER_SECOND, CPUTranscriber, read_pcm_wav
from app.asr_windows import RollingASRProcessor, WindowSettings
from app.audio_buffer import MultiSourceAudioBuffer
from app.transcription_feed import TranscriptFeed
from app.transcription_runtime import AsyncSourceTranscriber


class _CallMonitor:
    def __init__(self) -> None:
        self._lock = Lock()
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.total_inference_wall_seconds = 0.0

    def measure(self, transcriber, pcm: bytes) -> ASRResult:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        start = perf_counter()
        try:
            return transcriber.transcribe_pcm(pcm)
        finally:
            elapsed = perf_counter() - start
            with self._lock:
                self.calls += 1
                self.total_inference_wall_seconds += elapsed
                self.active -= 1


class _MeasuredTranscriber:
    def __init__(self, inner, monitor: _CallMonitor) -> None:
        self.inner = inner
        self.monitor = monitor

    def transcribe_pcm(self, pcm: bytes) -> ASRResult:
        return self.monitor.measure(self.inner, pcm)


class _SyntheticMock:
    """SHA-256 work for smoke tests; MUST NOT be reported as ASR inference."""

    def transcribe_pcm(self, pcm: bytes) -> ASRResult:
        fingerprint = hashlib.sha256(pcm).hexdigest()[:8]
        return ASRResult(
            model="synthetic-mock-not-asr", language="pt",
            seconds=len(pcm) / BYTES_PER_SECOND,
            text="relato artificial " + fingerprint, segments=(),
        )


def _peak_rss_mb() -> float | None:
    """Whole-process high-water RSS when supported, including native model RAM."""
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (ImportError, OSError):
        return None
    if sys.platform == "darwin":
        return round(value / (1024 * 1024), 2)
    if sys.platform.startswith("linux"):
        return round(value / 1024, 2)
    return None


async def benchmark(
    *, engine: str = "synthetic", sources: int = 2,
    pcm: bytes | None = None, seconds: int = 6,
    model: str = "tiny", cpu_threads: int = 2,
    window_ms: int = 2000, overlap_ms: int = 500,
    buffer_seconds: int = 3,
) -> dict[str, object]:
    """Run independent processors concurrently over the same in-memory test PCM.

    CPU percent is process CPU time / wall time *100 (may exceed 100%).
    RSS is the process high-water mark, not an allocation delta.
    """
    if engine not in ("synthetic", "real"):
        raise ValueError("engine must be synthetic or real")
    if not 2 <= sources <= 4:
        raise ValueError("sources must be between 2 and 4")
    if not 1 <= seconds <= 30:
        raise ValueError("seconds must be between 1 and 30")
    if not 1 <= buffer_seconds <= 30:
        raise ValueError("buffer_seconds must be between 1 and 30")
    settings = WindowSettings(
        window_ms=window_ms, overlap_ms=overlap_ms,
        max_sources=sources,
    )
    if engine == "real":
        if pcm is None:
            raise ValueError("real engine requires a local authorized WAV")
    elif pcm is not None:
        raise ValueError("synthetic engine cannot claim to benchmark a WAV")
    if pcm is None:
        pcm = b"\x01\x00" * (16_000 * seconds)
    if not pcm or len(pcm) % 2 or len(pcm) > 30 * BYTES_PER_SECOND:
        raise ValueError("PCM must contain 1..30 seconds of aligned samples")

    buffer_bytes = buffer_seconds * BYTES_PER_SECOND
    buffers = MultiSourceAudioBuffer(
        window_seconds=buffer_seconds, max_bytes_per_source=buffer_bytes,
        max_sources=sources,
    )
    feed = TranscriptFeed(max_sources_per_match=sources)
    monitor = _CallMonitor()
    sessions: list[AsyncSourceTranscriber] = []
    for index in range(sources):
        inner = (
            CPUTranscriber(ASRSettings(
                model=model, cpu_threads=cpu_threads,
                beam_size=1, max_seconds=min(120, (window_ms + 999) // 1000),
            )) if engine == "real" else _SyntheticMock()
        )
        source = f"bench-{index + 1}"
        processor = RollingASRProcessor(
            _MeasuredTranscriber(inner, monitor), settings,
        )
        sessions.append(AsyncSourceTranscriber("bench", source, processor, feed))

    start_rss = _peak_rss_mb()
    tracemalloc.start()
    tracemalloc.reset_peak()
    start_cpu = process_time()
    start_wall = perf_counter()
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        # Half-second blocks match the production ingestion granularity.
        # Each batch is scheduled together; the internal per-source lock
        # ensures sequential windows for that source without API-loop blocking.
        for pos in range(0, len(pcm), 16_000):
            chunk = pcm[pos:pos + 16_000]
            captured_at = origin + timedelta(seconds=pos / BYTES_PER_SECOND)
            for session in sessions:
                buffers.append(session.source_id, chunk, captured_at)
            await asyncio.gather(*(
                session.push(chunk, captured_at=captured_at)
                for session in sessions
            ))
        await asyncio.gather(*(session.finish() for session in sessions))
    finally:
        wall_seconds = perf_counter() - start_wall
        cpu_seconds = process_time() - start_cpu
        _current, py_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    status = buffers.status()
    max_pending = max(
        (len(session.processor.assembler.pending_sizes()) for session in sessions),
        default=0,
    )
    # A completed source must have released its rolling window.
    assert max_pending == 0
    recorded_sources = feed.snapshot("bench")["sources"]
    return {
        "task": "GN-086",
        "engine": "real_faster_whisper_cpu_int8" if engine == "real" else "synthetic_mock_not_asr",
        "platform": platform.system(),
        "python": platform.python_version(),
        "model": model if engine == "real" else None,
        "cpu_threads_per_source": cpu_threads if engine == "real" else None,
        "sources": sources,
        "pcm_seconds_per_source": round(len(pcm) / BYTES_PER_SECOND, 3),
        "window_ms": window_ms,
        "overlap_ms": overlap_ms,
        "buffer_seconds": buffer_seconds,
        "peak_buffer_bytes_per_source": max(row["bytes"] for row in status.values()),
        "max_configured_buffer_bytes_per_source": buffer_bytes,
        "total_inference_calls": monitor.calls,
        "max_overlapping_inferences": monitor.max_active,
        "inference_wall_seconds_sum": round(monitor.total_inference_wall_seconds, 3),
        "wall_seconds": round(wall_seconds, 3),
        "process_cpu_seconds": round(cpu_seconds, 3),
        "process_cpu_percent_of_one_core": round(
            100 * cpu_seconds / max(wall_seconds, 0.000001), 1
        ),
        "throughput_audio_seconds_per_wall_second": round(
            (sources * len(pcm) / BYTES_PER_SECOND) / max(wall_seconds, 0.000001), 2
        ),
        "process_rss_before_mb": start_rss,
        "process_peak_rss_mb": _peak_rss_mb(),
        "peak_python_tracemalloc_mb": round(py_peak / (1024 * 1024), 2),
        "source_states": {row["source_id"]: row["state"] for row in recorded_sources},
        "real_windows_or_radio_test": False,
        "speech_accuracy_measured": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GN-086 concurrent CPU/memory benchmark")
    parser.add_argument("--engine", choices=("synthetic", "real"), default="synthetic")
    parser.add_argument("--wav", help="Local authorized 16-kHz 16-bit mono WAV (real mode only)")
    parser.add_argument("--sources", type=int, default=2)
    parser.add_argument("--seconds", type=int, default=6, help="Synthetic duration (s)")
    parser.add_argument("--model", choices=("tiny", "base", "small", "medium"), default="tiny")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--window-ms", type=int, default=2000)
    parser.add_argument("--overlap-ms", type=int, default=500)
    parser.add_argument("--buffer-seconds", type=int, default=3)
    args = parser.parse_args()
    if (args.engine == "real") != (args.wav is not None):
        parser.error("real engine requires --wav; synthetic engine forbids --wav")
    try:
        from pathlib import Path
        pcm = read_pcm_wav(Path(args.wav), max_seconds=30) if args.wav else None
        report = asyncio.run(benchmark(
            engine=args.engine, sources=args.sources,
            pcm=pcm, seconds=args.seconds, model=args.model,
            cpu_threads=args.cpu_threads, window_ms=args.window_ms,
            overlap_ms=args.overlap_ms, buffer_seconds=args.buffer_seconds,
        ))
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"Benchmark error: {exc}\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
