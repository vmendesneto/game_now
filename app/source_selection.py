"""GN-063: conservative, read-only selection of one textual source.

The caller supplies synthetic or observed source metadata with capture timestamps
from a common clock domain. These signals have not been verified against live
broadcasts. A selected source is NOT permission to change match or ball state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import Id, Probability, StrictModel, require_aware

NarrationKind = Literal[
    "live_play", "ad", "conversation", "analysis", "replay", "unknown",
]
ConnectionHealth = Literal["offline", "connecting", "online", "error"]


class SourceSelectionObservation(StrictModel):
    source_id: Id
    enabled: bool = True
    connection_status: ConnectionHealth
    narration_kind: NarrationKind
    captured_at: datetime
    received_at: datetime
    signal_strength: Probability = 0.0

    @model_validator(mode="after")
    def check_timestamps(self) -> "SourceSelectionObservation":
        require_aware(self.captured_at)
        require_aware(self.received_at)
        if self.received_at < self.captured_at:
            raise ValueError("Reception cannot precede capture")
        return self


class SourceSelectionRequest(StrictModel):
    evaluated_at: datetime
    observations: list[SourceSelectionObservation]
    previous_source_id: Id | None = None
    max_age_seconds: float = Field(default=12.0, ge=0.5, le=60, allow_inf_nan=False)
    min_signal_strength: float = Field(
        default=0.55, ge=0.0, le=1.0, allow_inf_nan=False,
    )
    switch_margin: float = Field(
        default=0.12, ge=0.0, le=0.5, allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def check_observations(self) -> "SourceSelectionRequest":
        require_aware(self.evaluated_at)
        source_ids = [item.source_id for item in self.observations]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate source observation")
        return self


class SourceSelectionDiagnostic(StrictModel):
    source_id: Id
    eligible: bool
    reason: Literal[
        "eligible", "disabled", "connection_unhealthy", "not_live_play",
        "future_timestamp", "stale_capture", "low_signal_strength",
    ]
    capture_age_seconds: float | None = None
    selection_score: float | None = None


class SourceSelectionResponse(StrictModel):
    previous_source_id: Id | None
    active_source_id: Id | None
    transition: Literal["selected", "switched", "retained", "lost", "none"]
    reason: Literal[
        "best_eligible", "higher_quality", "hysteresis_retained",
        "previous_ineligible", "no_eligible_sources",
    ]
    diagnostics: list[SourceSelectionDiagnostic]
    persisted: Literal[False] = False
    eligible_for_state_update: Literal[False] = False


def preview_active_source(request: SourceSelectionRequest) -> SourceSelectionResponse:
    """Prefer fresh live text on a healthy connection, without source flapping.

    Ads, replays, uncertainty, offline/error connections and stale captures
    are *hard* exclusions, regardless of signal strength. Arrival delay is not
    used as the age of a broadcast. Ranking scores are rules, not calibrated
    probabilities. The existing selection is retained within a quality margin;
    if it becomes ineligible, fail over immediately. Never write to SQLite.
    """
    evaluated_at = request.evaluated_at
    diagnostics: list[SourceSelectionDiagnostic] = []
    for item in sorted(request.observations, key=lambda row: row.source_id):
        age = (evaluated_at - item.captured_at).total_seconds()
        if not item.enabled:
            reason = "disabled"
        elif item.connection_status != "online":
            reason = "connection_unhealthy"
        elif item.narration_kind != "live_play":
            reason = "not_live_play"
        elif item.captured_at > evaluated_at or item.received_at > evaluated_at:
            reason = "future_timestamp"
        elif age > request.max_age_seconds:
            reason = "stale_capture"
        elif item.signal_strength < request.min_signal_strength:
            reason = "low_signal_strength"
        else:
            reason = "eligible"

        eligible = reason == "eligible"
        # Freshness is advisory within the hard age limit; it cannot make a
        # commercial or uncertain narration eligible.
        score = round(
            0.8 * item.signal_strength +
            0.2 * max(0.0, 1.0 - age / request.max_age_seconds), 6,
        ) if eligible else None
        diagnostics.append(SourceSelectionDiagnostic(
            source_id=item.source_id,
            eligible=eligible,
            reason=reason,
            capture_age_seconds=round(age, 3) if age >= 0 else None,
            selection_score=score,
        ))

    eligible_rows = sorted(
        (row for row in diagnostics if row.eligible),
        key=lambda row: (-row.selection_score, row.source_id),
    )
    current = next(
        (row for row in eligible_rows
         if row.source_id == request.previous_source_id),
        None,
    )
    if not eligible_rows:
        active = None
        transition = "lost" if request.previous_source_id else "none"
        selection_reason = "no_eligible_sources"
    else:
        best = eligible_rows[0]
        if current is not None and best.source_id != current.source_id:
            if best.selection_score > current.selection_score + request.switch_margin:
                active = best.source_id
                transition = "switched"
                selection_reason = "higher_quality"
            else:
                active = current.source_id
                transition = "retained"
                selection_reason = "hysteresis_retained"
        elif current is not None:
            active = current.source_id
            transition = "retained"
            selection_reason = "hysteresis_retained"
        else:
            active = best.source_id
            transition = "switched" if request.previous_source_id else "selected"
            selection_reason = (
                "previous_ineligible" if request.previous_source_id
                else "best_eligible"
            )

    return SourceSelectionResponse(
        previous_source_id=request.previous_source_id,
        active_source_id=active,
        transition=transition,
        reason=selection_reason,
        diagnostics=diagnostics,
    )
