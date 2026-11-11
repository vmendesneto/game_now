"""GN-064: conservative contradiction guard for independently aligned texts.

Works on caller-supplied event hypotheses in one common clock domain. It
never synchronizes streams, guesses ball coordinates, or applies a match state
change; GN-061/062/063 are separate diagnostics feeding a future orchestrator.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import EventKind, Id, StrictModel, Zone, require_aware


class FusionObservation(StrictModel):
    source_id: Id
    segment_id: Id
    aligned_at: datetime | None = None
    current_live_play: bool = True
    team_id: Id | None = None
    player_id: Id | None = None
    zone: Zone | None = None
    event_kind: EventKind | None = None

    @model_validator(mode="after")
    def check_time(self) -> "FusionObservation":
        if self.aligned_at is not None:
            require_aware(self.aligned_at)
        return self


class FusionPlay(StrictModel):
    """A prior or hypothetical accepted play, never a persisted ball position."""
    source_id: Id
    segment_id: Id
    aligned_at: datetime
    team_id: Id
    zone: Zone
    player_id: Id | None = None
    event_kind: EventKind | None = None

    @model_validator(mode="after")
    def check_time(self) -> "FusionPlay":
        require_aware(self.aligned_at)
        return self


class FusionConflictRequest(StrictModel):
    evaluated_at: datetime
    active_source_id: Id | None = None
    observations: list[FusionObservation] = Field(max_length=8)
    previous_play: FusionPlay | None = None
    conflict_window_seconds: float = Field(
        default=2.0, ge=0.0, le=5.0, allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def check_observations(self) -> "FusionConflictRequest":
        require_aware(self.evaluated_at)
        sources = [row.source_id for row in self.observations]
        segments = [row.segment_id for row in self.observations]
        if len(set(sources)) != len(sources):
            raise ValueError("Only one latest observation per source is allowed")
        if len(set(segments)) != len(segments):
            raise ValueError("Duplicate segment IDs")
        if self.previous_play and self.previous_play.aligned_at > self.evaluated_at:
            raise ValueError("Previous play cannot be in the future")
        return self


ConflictReason = Literal[
    "consistent_candidate", "no_active_source", "no_active_observation",
    "not_live_play", "unaligned_active_observation", "future_aligned_timestamp",
    "missing_explicit_team_or_zone", "would_rewind_or_repeat",
    "conflicting_source_evidence",
]


class FusionConflictResponse(StrictModel):
    accepted_for_preview: bool
    reason: ConflictReason
    active_source_id: Id | None
    conflicting_source_ids: list[Id]
    proposed_play: FusionPlay | None
    # Always a preview; never permission to update ball, score or the clock.
    persisted: Literal[False] = False
    eligible_for_state_update: Literal[False] = False


def preview_fusion_conflicts(request: FusionConflictRequest) -> FusionConflictResponse:
    """Reject contradictory, old or insufficient observations before proposing.

    The chosen active source is explicitly supplied (e.g. by GN-063). Other
    live, aligned observations may veto contradictions within the time window.
    An unknown team/zone from another source is not treated as agreement or a
    reason to manufacture coordinates. Old observations never rewrite a newer
    previous play, even if they arrive later.
    """
    def reject(reason: ConflictReason, *, conflicts: list[str] | None = None) -> FusionConflictResponse:
        return FusionConflictResponse(
            accepted_for_preview=False,
            reason=reason,
            active_source_id=request.active_source_id,
            conflicting_source_ids=conflicts or [],
            proposed_play=None,
        )

    if request.active_source_id is None:
        return reject("no_active_source")
    by_source = {row.source_id: row for row in request.observations}
    chosen = by_source.get(request.active_source_id)
    if chosen is None:
        return reject("no_active_observation")
    if not chosen.current_live_play:
        return reject("not_live_play")
    if chosen.aligned_at is None:
        return reject("unaligned_active_observation")
    if chosen.aligned_at > request.evaluated_at:
        return reject("future_aligned_timestamp")
    if chosen.team_id is None or chosen.zone is None:
        return reject("missing_explicit_team_or_zone")
    if (request.previous_play is not None
            and chosen.aligned_at <= request.previous_play.aligned_at):
        return reject("would_rewind_or_repeat")

    conflicts: list[Id] = []
    for other in request.observations:
        if other.source_id == chosen.source_id:
            continue
        if (not other.current_live_play or other.aligned_at is None
                or other.aligned_at > request.evaluated_at):
            continue
        if abs((other.aligned_at - chosen.aligned_at).total_seconds()) > request.conflict_window_seconds:
            continue
        if (
            (other.team_id is not None and other.team_id != chosen.team_id)
            or (other.zone is not None and other.zone != chosen.zone)
            or (
                other.player_id is not None and chosen.player_id is not None
                and other.player_id != chosen.player_id
            )
            or (
                other.event_kind not in (None, EventKind.UNKNOWN)
                and chosen.event_kind not in (None, EventKind.UNKNOWN)
                and other.event_kind != chosen.event_kind
            )
        ):
            conflicts.append(other.source_id)
    if conflicts:
        return reject("conflicting_source_evidence", conflicts=sorted(conflicts))

    return FusionConflictResponse(
        accepted_for_preview=True,
        reason="consistent_candidate",
        active_source_id=request.active_source_id,
        conflicting_source_ids=[],
        proposed_play=FusionPlay(
            source_id=chosen.source_id,
            segment_id=chosen.segment_id,
            aligned_at=chosen.aligned_at,
            team_id=chosen.team_id,
            player_id=chosen.player_id,
            zone=chosen.zone,
            event_kind=chosen.event_kind,
        ),
    )
