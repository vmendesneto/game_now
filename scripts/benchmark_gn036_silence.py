"""GN-036: deterministic offline *synthetic* silence-gating benchmark.

No real voice, ASR model, YouTube/radio stream, speech accuracy or Windows CPU
claim. Labels are simulated: the "commercial" sample is energy like narration.
"""
from __future__ import annotations

import json
import math
import struct

from app.asr import ASRResult
from app.asr_windows import RollingASRProcessor, WindowSettings
from app.silence_gate import PCMSilenceGate, SilenceGateSettings


class _CountingModel:
    def __init__(self):
        self.calls = 0

    def transcribe_pcm(self, pcm: bytes) -> ASRResult:
        self.calls += 1
        return ASRResult(model="synthetic-model", language="pt",
                         seconds=len(pcm)/32000, text="fala simulada", segments=())


def fixtures() -> list[tuple[str, bytes]]:
    def tone(freq: int) -> bytes:
        return b"".join(struct.pack("<h",
            int(6000 * math.sin(2 * math.pi * freq * n / 16000)))
            for n in range(16000))
    blank = b"\x00\x00" * 16000
    return [
        ("silence_pre", blank),
        ("narration_like_tone", tone(420)),
        ("commercial_like_tone", tone(680)),
        ("silence_post", blank),
    ]


def benchmark() -> dict[str, object]:
    settings = WindowSettings(window_ms=1000, overlap_ms=1, min_tail_ms=500)
    corpus = fixtures()
    baseline_model = _CountingModel()
    gated_model = _CountingModel()
    baseline = RollingASRProcessor(baseline_model, settings)
    gated = RollingASRProcessor(
        gated_model, settings,
        silence_gate=PCMSilenceGate(SilenceGateSettings()),
    )
    baseline_records = []
    gated_records = []
    for _label, pcm in corpus:
        baseline_records.extend(baseline.push("synthetic",pcm))
        gated_records.extend(gated.push("synthetic",pcm))
    dropped = baseline_model.calls - gated_model.calls
    return {
        "kind":"synthetic_pcm_energy_only_not_speech_benchmark",
        "sample_labels":[name for name, _ in corpus],
        "baseline_inference_calls":baseline_model.calls,
        "gated_inference_calls":gated_model.calls,
        "calls_avoided":dropped,
        "calls_avoided_percent":round(100*dropped/max(1,baseline_model.calls),1),
        "gated_sequences":[item.sequence for item in gated_records],
        "advertisement_detected":False,
        "real_asr_model_used":False,
        "actual_windows_tested":False,
        "time_alignment_preserved":all(
            first.start_seconds < second.start_seconds
            for first,second in zip(gated_records,gated_records[1:])
        ),
    }


def main() -> None:
    print(json.dumps(benchmark(),ensure_ascii=False))


if __name__ == "__main__":
    main()
