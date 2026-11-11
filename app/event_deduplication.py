"""GN-062: conservative, read-only deduplication of aligned event candidates.

Only explicitly typed live-play candidates can be grouped. GN-061's alignment
is supplied by the caller; neither this function nor its endpoint determines
whether two spoken phrases really refer to the same real-world incident.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import EventKind, Id, StrictModel, require_aware
from app.source_delay import SourceDelayEstimate

# Fast and repeatable actions need the same resolved player to avoid merging
# distinct passes or shots simply because they happened near each other.
PLAYER_REQUIRED = frozenset({
    EventKind.PASS, EventKind.CROSS, EventKind.SHOT, EventKind.THROW_IN,
})


class EventCandidate(StrictModel):
    segment_id: Id
    source_id: Id
    kind: EventKind
    captured_at: datetime
    received_at: datetime
    team_id: Id | None = None
    player_id: Id | None = None
    current_live_play: bool = True

    @model_validator(mode="after")
    def check_times(self) -> "EventCandidate":
        require_aware(self.captured_at)
        require_aware(self.received_at)
        if self.received_at < self.captured_at:
            raise ValueError("Reception cannot precede capture")
        return self


class EventDeduplicationRequest(StrictModel):
    candidates: list[EventCandidate] = Field(min_length=1, max_length=80)
    source_delays: list[SourceDelayEstimate] = Field(min_length=1, max_length=8)
    maximum_separation_seconds: float = Field(default=2.0, ge=0.1, le=5.0)

    @model_validator(mode="after")
    def check_candidates(self) -> "EventDeduplicationRequest":
        segment_ids = [candidate.segment_id for candidate in self.candidates]
        if len(set(segment_ids)) != len(segment_ids):
            raise ValueError("Duplicate segment IDs")
        sources = {candidate.source_id for candidate in self.candidates}
        delays = [estimate.source_id for estimate in self.source_delays]
        if len(set(delays)) != len(delays):
            raise ValueError("Duplicate source delay estimates")
        if len(sources) > 8 or not sources.issubset(set(delays)):
            raise ValueError("Every source must have exactly one supplied delay status")
        if sum(item.status == "reference" for item in self.source_delays) != 1:
            raise ValueError("Exactly one source must be the reference")
        for item in self.source_delays:
            if item.status == "reference" and item.relative_delay_seconds != 0:
                raise ValueError("Reference delay must be zero")
            if item.status == "aligned":
                if (item.relative_delay_seconds is None
                        or not isfinite(item.relative_delay_seconds)
                        or abs(item.relative_delay_seconds) > 900
                        or item.common_events < 2):
                    raise ValueError("Aligned source requires a bounded delay and two common events")
            if item.status not in ("reference", "aligned") and item.relative_delay_seconds is not None:
                raise ValueError("Unaligned sources cannot provide an offset")
        return self


class EventGroup(StrictModel):
    representative_segment_id: Id
    kind: EventKind
    team_id: Id | None
    player_id: Id | None
    aligned_at: datetime | None
    source_ids: list[Id]
    segment_ids: list[Id]
    merged: bool


class EventDeduplicationResponse(StrictModel):
    groups: list[EventGroup]
    discarded_non_live: list[Id]
    input_candidates: int = Field(ge=0)
    output_groups: int = Field(ge=0)
    persisted: Literal[False] = False


def _compatible(candidate: EventCandidate, other: EventCandidate) -> bool:
    if candidate.source_id == other.source_id:
        return False
    if candidate.kind != other.kind:
        return False
    if candidate.team_id is None or candidate.team_id != other.team_id:
        return False
    if (candidate.player_id is not None and other.player_id is not None
            and candidate.player_id != other.player_id):
        return False
    if candidate.kind in PLAYER_REQUIRED:
        return (candidate.player_id is not None
                and candidate.player_id == other.player_id)
    return True


def preview_event_deduplication(
    request: EventDeduplicationRequest,
) -> EventDeduplicationResponse:
    """Group compatible, time-aligned observations without mutating match state.

    All members must agree pairwise with the group, preventing transitive
    chains or merging two observations from the same source. Unaligned
    sources remain separate; no event is discarded because sync is unknown.
    """
    offsets = {
        item.source_id: item.relative_delay_seconds
        for item in request.source_delays
        if item.status in ("reference", "aligned")
    }
    live_candidates = [item for item in request.candidates if item.current_live_play]
    discarded = sorted(
        item.segment_id for item in request.candidates if not item.current_live_play
    )

    def aligned_at(item: EventCandidate) -> datetime | None:
        offset = offsets.get(item.source_id)
        return (item.captured_at - timedelta(seconds=offset)
                if offset is not None else None)

    # Sort by capture time in a common domain; unknown alignment is isolated.
    ordered = sorted(
        live_candidates,
        key=lambda item: (
            aligned_at(item) or item.captured_at,
            item.source_id, item.segment_id,
        ),
    )
    clusters: list[list[EventCandidate]] = []
    for candidate in ordered:
        event_time = aligned_at(candidate)
        selected: list[EventCandidate] | None = None
        for cluster in clusters:
            if event_time is None:
                break
            if all(
                _compatible(candidate, other)
                and aligned_at(other) is not None
                and abs((event_time - aligned_at(other)).total_seconds())
                <= request.maximum_separation_seconds
                for other in cluster
            ):
                selected = cluster
                break
        if selected is None:
            clusters.append([candidate])
        else:
            selected.append(candidate)

    result: list[EventGroup] = []
    for cluster in clusters:
        times = [aligned_at(item) for item in cluster]
        players = {item.player_id for item in cluster if item.player_id is not None}
        result.append(EventGroup(
            representative_segment_id=cluster[0].segment_id,
            kind=cluster[0].kind,
            team_id=cluster[0].team_id,
            player_id=next(iter(players)) if len(players) == 1 else None,
            aligned_at=times[0],
            source_ids=[item.source_id for item in cluster],
            segment_ids=[item.segment_id for item in cluster],
            merged=len(cluster) > 1,
        ))

    return EventDeduplicationResponse(
        groups=result,
        discarded_non_live=discarded,
        input_candidates=len(request.candidates),
        output_groups=len(result),
    )
