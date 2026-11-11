"""GN-060: logical match clock driven by captured presentation times.

Delivery/arrival timestamps are recorded for diagnostics, never used to move
the clock. No live clock synchronization or multi-source delay is assumed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import Id, StrictModel, require_aware

MatchPeriod = Literal["first_half", "half_time", "second_half", "finished"]
MAX_SECONDS = 14400.0  # Explicit safety bound, not an official match length.


class ClockObservation(StrictModel):
    source_id: Id
    captured_at: datetime
    received_at: datetime
    reported_match_seconds: float = Field(ge=0, le=MAX_SECONDS)

    @model_validator(mode="after")
    def check_times(self) -> "ClockObservation":
        require_aware(self.captured_at)
        require_aware(self.received_at)
        if self.received_at < self.captured_at:
            raise ValueError("Reception cannot precede capture")
        return self


class ClockState(StrictModel):
    period: MatchPeriod
    source_id: Id | None = None
    anchor_captured_at: datetime | None = None
    anchor_match_seconds: float | None = Field(default=None, ge=0, le=MAX_SECONDS)

    @model_validator(mode="after")
    def check_anchor(self) -> "ClockState":
        present = (self.source_id is not None,
                   self.anchor_captured_at is not None,
                   self.anchor_match_seconds is not None)
        if len(set(present)) != 1:
            raise ValueError("Clock anchor must have all fields or none")
        if self.anchor_captured_at is not None:
            require_aware(self.anchor_captured_at)
        return self


class ClockView(StrictModel):
    status: Literal["unanchored", "running", "paused"]
    reason: str
    match_seconds: float | None = None
    period: MatchPeriod
    source_id: Id | None = None


class ClockUpdate(StrictModel):
    accepted: bool
    reason: str
    state: ClockState


class ClockPreviewRequest(StrictModel):
    observations: list[ClockObservation] = Field(min_length=1, max_length=40)
    project_at_captured_at: datetime

    @model_validator(mode="after")
    def check_project_at(self) -> "ClockPreviewRequest":
        require_aware(self.project_at_captured_at)
        return self


class ClockPreviewResponse(StrictModel):
    updates: list[ClockUpdate]
    projection: ClockView
    state: ClockState
    persisted: Literal[False] = False


class LogicalMatchClock:
    """One source/period, not a cross-radio fusion algorithm (GN-061 pending)."""

    def __init__(self, period: MatchPeriod = "first_half") -> None:
        self.state = ClockState(period=period)

    def project(self, at_captured: datetime) -> ClockView:
        require_aware(at_captured)
        state = self.state
        if state.anchor_match_seconds is None or state.anchor_captured_at is None:
            return ClockView(
                status="unanchored", reason="no_explicit_clock_anchor",
                period=state.period,
            )
        if state.period in ("half_time", "finished"):
            return ClockView(
                status="paused", reason="period_not_running",
                match_seconds=state.anchor_match_seconds,
                period=state.period, source_id=state.source_id,
            )
        delta = (at_captured - state.anchor_captured_at).total_seconds()
        return ClockView(
            status="running", reason="captured_time_projection",
            match_seconds=round(
                min(MAX_SECONDS, state.anchor_match_seconds + max(0.0, delta)), 3,
            ),
            period=state.period, source_id=state.source_id,
        )

    def observe(self, observation: ClockObservation) -> ClockUpdate:
        state = self.state

        def reject(reason: str) -> ClockUpdate:
            return ClockUpdate(
                accepted=False, reason=reason, state=self.state.model_copy(deep=True),
            )

        if state.period not in ("first_half", "second_half"):
            return reject("period_not_running")
        if state.source_id is not None and observation.source_id != state.source_id:
            return reject("source_alignment_not_implemented")
        if (state.anchor_captured_at is not None
                and observation.captured_at < state.anchor_captured_at):
            return reject("out_of_order_capture")
        projected = self.project(observation.captured_at)
        if (projected.match_seconds is not None
                and observation.reported_match_seconds + 1e-6 < projected.match_seconds):
            return reject("observation_would_rewind")
        self.state = ClockState(
            period=state.period, source_id=observation.source_id,
            anchor_captured_at=observation.captured_at,
            anchor_match_seconds=observation.reported_match_seconds,
        )
        return ClockUpdate(
            accepted=True, reason="explicit_anchor_accepted",
            state=self.state.model_copy(deep=True),
        )

    def change_period(self, period: MatchPeriod, at_captured: datetime) -> ClockUpdate:
        """Freeze on stoppage; resume without inventing a second-half clock."""
        require_aware(at_captured)
        current = self.state.period
        transitions = {
            "first_half": "half_time",
            "half_time": "second_half",
            "second_half": "finished",
        }
        if transitions.get(current) != period:
            return ClockUpdate(
                accepted=False, reason="invalid_period_transition",
                state=self.state.model_copy(deep=True),
            )
        if period == "second_half":
            # A new capture observation must establish the resumed time.
            self.state = ClockState(period="second_half")
        else:
            projected = self.project(at_captured).match_seconds
            self.state = (
                ClockState(period=period)
                if projected is None else ClockState(
                    period=period, source_id=self.state.source_id,
                    anchor_captured_at=at_captured, anchor_match_seconds=projected,
                )
            )
        return ClockUpdate(
            accepted=True, reason="period_transition",
            state=self.state.model_copy(deep=True),
        )


def preview_clock(period: MatchPeriod, request: ClockPreviewRequest) -> ClockPreviewResponse:
    """Bounded, read-only simulation to exercise the clock without any stream."""
    clock = LogicalMatchClock(period)
    updates = [clock.observe(observation) for observation in request.observations]
    return ClockPreviewResponse(
        updates=updates, projection=clock.project(request.project_at_captured_at),
        state=clock.state.model_copy(deep=True),
    )
