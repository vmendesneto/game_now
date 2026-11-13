"""GN-061: conservative relative source delay from explicitly matched events.

This diagnostic never infers that two passages refer to the same play: GN-062
will handle that. Capture timestamps must share a trustworthy clock domain.
Arrival/transcription times never contribute to broadcast delay estimates.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import Id, StrictModel, require_aware

DelayStatus = Literal[
    "reference", "aligned", "insufficient_common_events",
    "inconsistent_observations", "out_of_range",
]


class SourceEventObservation(StrictModel):
    source_id: Id
    common_event_id: Id
    captured_at: datetime
    received_at: datetime

    @model_validator(mode="after")
    def check_timestamps(self) -> "SourceEventObservation":
        require_aware(self.captured_at)
        require_aware(self.received_at)
        if self.received_at < self.captured_at:
            raise ValueError("Reception cannot precede capture")
        return self


class RelativeDelayRequest(StrictModel):
    reference_source_id: Id
    observations: list[SourceEventObservation] = Field(min_length=2, max_length=80)
    window_seconds: int = Field(default=600, ge=30, le=3600)
    min_common_events: int = Field(default=2, ge=2, le=10)
    tolerance_seconds: float = Field(default=2.0, ge=0, le=10)
    max_absolute_delay_seconds: float = Field(default=120.0, ge=1, le=900)

    @model_validator(mode="after")
    def check_observations(self) -> "RelativeDelayRequest":
        pairs = [(obs.source_id, obs.common_event_id) for obs in self.observations]
        if len(set(pairs)) != len(pairs):
            raise ValueError("Duplicate common event for the same source")
        sources = {obs.source_id for obs in self.observations}
        if self.reference_source_id not in sources:
            raise ValueError("Reference source must have observations")
        return self


class SourceDelayEstimate(StrictModel):
    source_id: Id
    status: DelayStatus
    relative_delay_seconds: float | None = None
    common_events: int = Field(ge=0)
    max_deviation_seconds: float | None = None

    # Positive: this source presents a common event after the reference.
    # Negative: this source presents it before the reference.


class RelativeDelayResponse(StrictModel):
    reference_source_id: Id
    window_start_at: datetime
    observations_in_window: int = Field(ge=0)
    discarded_outside_window: int = Field(ge=0)
    estimates: list[SourceDelayEstimate]
    persisted: Literal[False] = False


def preview_relative_delays(request: RelativeDelayRequest) -> RelativeDelayResponse:
    """Bounded, order-independent estimate based only on shared event IDs.

    The observation window follows the most recent *capture* time, not arrival.
    No offset is returned for insufficient, conflicting or excessive samples.
    The calling code must not treat an offset as a verified live sync.
    """
    observations = request.observations
    latest_capture = max(item.captured_at for item in observations)
    window_start = latest_capture - timedelta(seconds=request.window_seconds)
    eligible = [item for item in observations if item.captured_at >= window_start]

    by_source: dict[str, dict[str, SourceEventObservation]] = {}
    for item in eligible:
        by_source.setdefault(item.source_id, {})[item.common_event_id] = item
    reference = by_source.get(request.reference_source_id, {})
    source_ids = sorted({item.source_id for item in observations})
    estimates: list[SourceDelayEstimate] = []

    for source_id in source_ids:
        if source_id == request.reference_source_id:
            estimates.append(SourceDelayEstimate(
                source_id=source_id, status="reference",
                relative_delay_seconds=0.0, common_events=len(reference),
                max_deviation_seconds=0.0,
            ))
            continue

        common_ids = sorted(set(reference).intersection(by_source.get(source_id, {})))
        offsets = [
            (by_source[source_id][event].captured_at
             - reference[event].captured_at).total_seconds()
            for event in common_ids
        ]
        if len(offsets) < request.min_common_events:
            estimates.append(SourceDelayEstimate(
                source_id=source_id, status="insufficient_common_events",
                common_events=len(offsets),
            ))
            continue

        midpoint = median(offsets)
        deviation = max(abs(offset - midpoint) for offset in offsets)
        if any(abs(offset) > request.max_absolute_delay_seconds for offset in offsets):
            status: DelayStatus = "out_of_range"
        elif deviation > request.tolerance_seconds:
            status = "inconsistent_observations"
        else:
            status = "aligned"
        estimates.append(SourceDelayEstimate(
            source_id=source_id,
            status=status,
            relative_delay_seconds=round(midpoint, 3) if status == "aligned" else None,
            common_events=len(offsets),
            max_deviation_seconds=round(deviation, 3),
        ))

    return RelativeDelayResponse(
        reference_source_id=request.reference_source_id,
        window_start_at=window_start,
        observations_in_window=len(eligible),
        discarded_outside_window=len(observations) - len(eligible),
        estimates=estimates,
    )
