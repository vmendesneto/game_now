"""Bounded operational measurements. These are not accuracy or broadcast delay."""
from __future__ import annotations

from collections import OrderedDict
import math
import time
from threading import Lock
from typing import Callable
from uuid import uuid4


class DelayDistribution:
    """Streaming totals and fixed histogram, independent of match duration."""

    limits = (.1, .25, .5, 1., 2., 5., 10., 15., 30., 60., 120.)

    def __init__(self):
        self.count = 0
        self.total = 0.
        self.minimum: float | None = None
        self.maximum: float | None = None
        self.buckets = [0] * (len(self.limits) + 1)

    def add(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("Delay must be finite and nonnegative")
        self.count += 1
        self.total += seconds
        self.minimum = min(self.minimum, seconds) if self.minimum is not None else seconds
        self.maximum = max(self.maximum, seconds) if self.maximum is not None else seconds
        bucket = next((i for i, limit in enumerate(self.limits) if seconds <= limit), len(self.limits))
        self.buckets[bucket] += 1

    def snapshot(self) -> dict:
        def percentile(fraction):
            target = math.ceil(self.count * fraction)
            cumulative = 0
            for index, count in enumerate(self.buckets):
                cumulative += count
                if cumulative >= target:
                    return {"lower_seconds": 0 if index == 0 else self.limits[index-1],
                            "upper_seconds": self.limits[index] if index < len(self.limits) else None}
            return None
        return {"samples": self.count, "minimum_seconds": self.minimum,
                "maximum_seconds": self.maximum,
                "mean_seconds": self.total / self.count if self.count else None,
                "p50_interval": percentile(.5) if self.count else None,
                "p95_interval": percentile(.95) if self.count else None,
                "percentiles_are_histogram_intervals": True}


class CaptureMetrics:
    """Counters persist for a run; only recent render receipts occupy memory."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.epoch = uuid4().hex
        self.started = clock()
        self.ended: float | None = None
        self.text_windows = 0
        self.processed_audio_windows = 0
        self.windows_without_new_text = 0
        self.text_windows_rejected_for_length = 0
        self.last_processed_sequence: int | None = None
        self.last_processed_audio_end_seconds = 0.
        self.windows_with_named_actions = 0
        self.windows_with_partial_region = 0
        self.windows_with_full_ball = 0
        self.phase_changes = 0
        self.last_phase: str | None = None
        self.last_sequence: int | None = None
        self.sequence_gaps = 0
        self.asr_delay = DelayDistribution()
        self.render_delay = DelayDistribution()
        self.recognition_wall = DelayDistribution()
        self._recognition_lock = Lock()
        self.maximum_queued_pcm_bytes = 0
        self.backlog_samples = 0
        self._recent: OrderedDict[int, tuple[float, bool]] = OrderedDict()

    def recognition_finished(self, seconds: float) -> None:
        with self._recognition_lock:
            self.recognition_wall.add(seconds)

    def observe_backlog(self, queued_bytes: int) -> None:
        self.maximum_queued_pcm_bytes = max(self.maximum_queued_pcm_bytes, queued_bytes)
        self.backlog_samples += 1

    def processed(self, sequence: int, audio_end_seconds: float, *, has_new_text: bool) -> None:
        if self.last_processed_sequence is not None and sequence <= self.last_processed_sequence:
            raise ValueError("Processed windows must advance")
        self.last_processed_sequence = sequence
        self.last_processed_audio_end_seconds = audio_end_seconds
        self.processed_audio_windows += 1
        self.windows_without_new_text += not has_new_text

    def observe(self, sequence: int, *, captured_tick: float | None, phase: str,
                named_actions: bool, partial_region: bool, full_ball: bool) -> None:
        if self.last_sequence is not None:
            if sequence <= self.last_sequence:
                raise ValueError("Metrics require increasing transcript sequences")
            self.sequence_gaps += max(0, sequence - self.last_sequence - 1)
        self.last_sequence = sequence
        self.text_windows += 1
        self.windows_with_named_actions += bool(named_actions)
        self.windows_with_partial_region += bool(partial_region)
        self.windows_with_full_ball += bool(full_ball)
        if phase != self.last_phase:
            self.phase_changes += self.last_phase is not None
            self.last_phase = phase
        if captured_tick is not None:
            self.asr_delay.add(max(0., self.clock() - captured_tick))
            self._recent[sequence] = (captured_tick, False)
            while len(self._recent) > 512:
                self._recent.popitem(last=False)

    def acknowledge_render(self, epoch: str, sequence: int) -> bool:
        if epoch != self.epoch or sequence not in self._recent:
            return False
        captured_tick, acknowledged = self._recent[sequence]
        if acknowledged:
            return False
        self.render_delay.add(max(0., self.clock() - captured_tick))
        self._recent[sequence] = (captured_tick, True)
        return True

    def finish(self) -> None:
        if self.ended is None:
            self.ended = self.clock()

    def snapshot(self) -> dict:
        with self._recognition_lock:
            recognition = self.recognition_wall.snapshot()
        return {"epoch": self.epoch,
                "elapsed_seconds": max(0., (self.ended if self.ended is not None else self.clock()) - self.started),
                "text_windows": self.text_windows,
                "processed_audio_windows": self.processed_audio_windows,
                "last_processed_audio_end_seconds": self.last_processed_audio_end_seconds,
                "windows_without_new_text": self.windows_without_new_text,
                "text_windows_rejected_for_length": self.text_windows_rejected_for_length,
                "windows_with_named_actions": self.windows_with_named_actions,
                "windows_with_partial_region": self.windows_with_partial_region,
                "windows_with_full_ball": self.windows_with_full_ball,
                "phase_changes": self.phase_changes, "last_phase": self.last_phase,
                "sequence_gaps": self.sequence_gaps,
                "sequence_gaps_are_not_proven_audio_loss": True,
                "pcm_to_text": self.asr_delay.snapshot(),
                "pcm_to_first_render_ack": self.render_delay.snapshot(),
                "recognition_call_wall_time": recognition,
                "maximum_queued_pcm_seconds": self.maximum_queued_pcm_bytes / 32000,
                "backlog_samples": self.backlog_samples,
                "render_receipts_retained": len(self._recent),
                "measurement_origin": "pcm_window_end_available_at_server",
                "render_ack_includes_return_request": True,
                "broadcast_to_browser_latency_seconds": None,
                "accuracy_metrics": None,
                "coverage_is_textual_output_not_ground_truth": True}
