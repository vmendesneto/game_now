"""Reproducible window assembly microbenchmark (NOT ASR accuracy/performance).

Run python -m scripts.benchmark_asr_windows; no streams/models/network required.
"""
from __future__ import annotations

from time import perf_counter
import json

from app.asr_windows import PCMWindowAssembler, WindowSettings


def main() -> None:
    settings = WindowSettings()
    processor = PCMWindowAssembler(settings)
    block = b"\x00\x00" * (16_000 // 2)
    sources = ("radio", "youtube")
    chunks_per_source = 1200
    counts = {source: 0 for source in sources}
    start = perf_counter()
    for _ in range(chunks_per_source):
        for source in sources:
            counts[source] += len(processor.push(source, block))
    elapsed = perf_counter() - start
    print(json.dumps({
        "kind": "window_assembly_only_not_asr",
        "minutes_per_source": 10,
        "sources": len(sources),
        "window_ms": settings.window_ms,
        "overlap_ms": settings.overlap_ms,
        "windows_by_source": counts,
        "pending_pcm_bytes_by_source": processor.pending_sizes(),
        "wall_seconds": round(elapsed, 4),
        "engine_inference": False,
        "actual_windows_tested": False,
    }))


if __name__ == "__main__":
    main()
