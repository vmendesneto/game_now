"""GN-041: independent continuous windows, overlaps, de-duplication, memory."""
from __future__ import annotations

from collections import deque
import struct

import pytest

from app.asr import ASRResult, BYTES_PER_SECOND
from app.asr_windows import (
    PCMWindowAssembler, RollingASRProcessor, TextOverlapDeduplicator,
    WindowSettings,
)


def pcm(milliseconds: int) -> bytes:
    return struct.pack("<h", 1234) * (16 * milliseconds)


def test_overlapping_windows_have_deterministic_offsets_and_pcm():
    assembler = PCMWindowAssembler(WindowSettings(window_ms=1000, overlap_ms=250))
    for _ in range(3):
        assert assembler.push("radio", pcm(250)) == ()
    first, = assembler.push("radio", pcm(250))
    assert (first.sequence, first.start_seconds, first.end_seconds) == (0, 0, 1)
    assert first.pcm == pcm(1000)
    assert assembler.pending_sizes()["radio"] == len(pcm(250))
    for _ in range(2):
        assert assembler.push("radio", pcm(250)) == ()
    second, = assembler.push("radio", pcm(250))
    assert (second.sequence, second.start_seconds, second.end_seconds) == (1, 0.75, 1.75)
    assert second.pcm == pcm(1000)
    assert assembler.pending_sizes()["radio"] <= len(pcm(1000))


def test_sources_remain_isolated_and_finish_drops_redundant_overlap():
    assembler = PCMWindowAssembler(WindowSettings(
        window_ms=1000, overlap_ms=250, min_tail_ms=100, max_sources=2,
    ))
    assert assembler.push("a", pcm(1000))[0].sequence == 0
    assert assembler.push("b", pcm(1000))[0].sequence == 0
    assert assembler.finish("a") is None  # residual overlap has no new samples
    assert assembler.pending_sizes() == {"b": len(pcm(250))}
    assert assembler.push("a", pcm(1000))[0].start_seconds == 0
    assert assembler.finish("b") is None


def test_finish_keeps_partial_new_tail_once():
    assembler = PCMWindowAssembler(WindowSettings(
        window_ms=1000, overlap_ms=250, min_tail_ms=100,
    ))
    assembler.push("a", pcm(1000))
    assembler.push("a", pcm(125))
    tail = assembler.finish("a")
    assert tail is not None
    assert (tail.sequence, tail.start_seconds, tail.end_seconds) == (1, 0.75, 1.125)
    assert len(tail.pcm) == len(pcm(375))
    assert assembler.finish("a") is None


@pytest.mark.parametrize("source,block", [
    ("", pcm(250)), ("radio", b""), ("radio", b"x"), ("radio", "bad"),
])
def test_invalid_inputs_are_rejected(source, block):
    assembler = PCMWindowAssembler(WindowSettings(window_ms=1000, overlap_ms=250))
    with pytest.raises(ValueError):
        assembler.push(source, block)


def test_chunk_and_source_bounds():
    assembler = PCMWindowAssembler(WindowSettings(
        window_ms=1000, overlap_ms=250, max_sources=1,
    ))
    with pytest.raises(ValueError, match="capacity"):
        assembler.push("a", pcm(1001))
    assert assembler.push("a", pcm(500)) == ()
    with pytest.raises(ValueError, match="sources"):
        assembler.push("b", pcm(500))


def test_text_deduplicates_only_multiword_suffix_prefix():
    dedup = TextOverlapDeduplicator(max_history_words=8)
    assert dedup.consume("radio", "A bola está no meio do campo.") == "A bola está no meio do campo."
    assert dedup.consume("radio", "meio do campo chegou ao gol") == "chegou ao gol"
    assert dedup.consume("other", "meio do campo chegou ao gol") == "meio do campo chegou ao gol"
    assert dedup.consume("radio", "gol") == "gol"
    assert dedup.consume("radio", "  ") == ""
    dedup.clear("radio")
    assert dedup.consume("radio", "meio do campo") == "meio do campo"


class FakeASR:
    def __init__(self):
        self.texts = deque([
            "A bola está no meio do campo",
            "no meio do campo o atacante chutou",
            "Gol do atacante",
        ])
        self.calls = 0

    def transcribe_pcm(self, block: bytes) -> ASRResult:
        self.calls += 1
        return ASRResult(
            model="tiny", language="pt", seconds=len(block) / BYTES_PER_SECOND,
            text=self.texts.popleft(), segments=(),
        )


def test_pipeline_transcribes_without_repeating_overlapped_phrases():
    fake = FakeASR()
    proc = RollingASRProcessor(fake, WindowSettings(
        window_ms=1000, overlap_ms=500, min_tail_ms=250,
    ))
    assert proc.push("radio", pcm(500)) == ()
    first, = proc.push("radio", pcm(500))
    second, = proc.push("radio", pcm(500))
    assert first.new_text == "A bola está no meio do campo"
    assert second.new_text == "o atacante chutou"
    assert first.raw_text != second.raw_text
    assert (first.start_seconds, second.start_seconds) == (0, 0.5)
    last, = proc.push("radio", pcm(500))
    assert last.new_text == "Gol do atacante"
    assert fake.calls == 3
    assert proc.finish("radio") == ()


def test_long_two_source_session_has_bounded_pending_audio():
    settings = WindowSettings(window_ms=6000, overlap_ms=2000)
    assembler = PCMWindowAssembler(settings)
    block = pcm(500)
    counts = {"radio": 0, "youtube": 0}
    for _ in range(1200):  # 10 minutes of PCM chunks per source
        for source in counts:
            counts[source] += len(assembler.push(source, block))
            assert assembler.pending_sizes()[source] < assembler.window_bytes
    assert counts["radio"] == counts["youtube"] == 149
    assert all(value <= assembler.window_bytes for value in assembler.pending_sizes().values())


def test_invalid_window_settings():
    for kwargs in ({"window_ms": 999}, {"window_ms": 61000},
                   {"overlap_ms": 0}, {"overlap_ms": 6000},
                   {"min_tail_ms": 50}, {"max_sources": 0},
                   {"max_history_words": 1}):
        with pytest.raises(ValueError):
            WindowSettings(**kwargs)
