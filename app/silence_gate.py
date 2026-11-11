"""GN-036: optional, conservative PCM energy gate for windows before ASR.

Energy is not speech detection: it cannot distinguish football narration from
advertising, crowd noise or music. The gate is opt-in and never shifts timestamps.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
import sys


@dataclass(frozen=True, slots=True)
class SilenceGateSettings:
    rms_threshold: float = 120.0
    frame_ms: int = 30
    min_active_ms: int = 90

    def __post_init__(self) -> None:
        if not math.isfinite(self.rms_threshold) or not 1 <= self.rms_threshold <= 32767:
            raise ValueError("rms_threshold must be finite and in 1..32767")
        if not 10 <= self.frame_ms <= 100:
            raise ValueError("frame_ms must be 10..100")
        if not 10 <= self.min_active_ms <= 2000:
            raise ValueError("min_active_ms must be 10..2000")


@dataclass(frozen=True, slots=True)
class SilenceDecision:
    skip_asr: bool
    duration_seconds: float
    active_ms: float
    peak_rms: float
    reason: str

    @property
    def has_activity(self) -> bool:
        return not self.skip_asr


class PCMSilenceGate:
    """Energy-only alternative to VAD; no model, downloads or media retention.

    Purposefully does *not* call silence "commercial". Audio with activity
    including adverts, cheering or music must still reach the text classifier.
    """

    def __init__(self, settings: SilenceGateSettings | None = None):
        self.settings = settings or SilenceGateSettings()

    def assess(self, pcm: bytes) -> SilenceDecision:
        if not isinstance(pcm, bytes) or not pcm or len(pcm) % 2:
            raise ValueError("Input must be nonempty aligned 16-bit PCM bytes")
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        frame_samples = 16_000 * self.settings.frame_ms // 1000
        active_samples = 0
        peak = 0.0
        for start in range(0, len(samples), frame_samples):
            frame = samples[start:start + frame_samples]
            rms = math.sqrt(sum(int(v)*int(v) for v in frame) / len(frame))
            peak = max(peak, rms)
            if rms >= self.settings.rms_threshold:
                active_samples += len(frame)
        duration_seconds = len(samples) / 16_000
        active_ms = active_samples * 1000.0 / 16_000
        # Do not suppress potentially short exclamations if the entire input
        # is shorter than the configured activity minimum.
        if duration_seconds * 1000 < self.settings.min_active_ms:
            skip = peak < self.settings.rms_threshold
        else:
            skip = active_ms < self.settings.min_active_ms
        return SilenceDecision(
            skip_asr=skip,
            duration_seconds=duration_seconds,
            active_ms=round(active_ms, 3),
            peak_rms=round(peak, 3),
            reason="low_energy_only" if skip else "pcm_activity",
        )
