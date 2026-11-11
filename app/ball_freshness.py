"""GN-065: expire stale ball-region hypotheses after narration silence.

This is a pure, bounded presentation preview over GN-064's explicit last play.
No timer is started, no event is inferred and no match state is persisted.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, model_validator

from app.contracts import Id, StrictModel, Zone, require_aware
from app.fusion_conflicts import FusionPlay


class BallFreshnessRequest(StrictModel):
    evaluated_at: datetime
    last_play: FusionPlay | None = None
    active_source_id: Id | None = None
    uncertain_after_seconds: float = Field(
        default=5.0, ge=0.5, le=60.0, allow_inf_nan=False,
    )
    expire_after_seconds: float = Field(
        default=15.0, ge=1.0, le=300.0, allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def check_time_bounds(self) -> "BallFreshnessRequest":
        require_aware(self.evaluated_at)
        if self.expire_after_seconds <= self.uncertain_after_seconds:
            raise ValueError("Expiry must occur after uncertainty threshold")
        if self.last_play is not None and self.last_play.aligned_at > self.evaluated_at:
            raise ValueError("A last play cannot occur after evaluation")
        return self


class BallFreshnessResponse(StrictModel):
    uncertainty: Literal["estimated", "uncertain", "expired"]
    display_label: Literal["posição estimada", "posição incerta"]
    reason: Literal[
        "recent_explicit_play", "no_explicit_play", "source_unavailable_or_changed",
        "narration_silent", "ttl_expired",
    ]
    active_source_id: Id | None
    last_aligned_at: datetime | None
    age_seconds: float | None
    expires_at: datetime | None
    team_id: Id | None
    zone: Zone | None
    player_id: Id | None
    persisted: Literal[False] = False
    eligible_for_state_update: Literal[False] = False


def preview_ball_freshness(request: BallFreshnessRequest) -> BallFreshnessResponse:
    """Only a recent play from the still-active source may show an estimated zone.

    After a short silence (or immediately upon losing/changing the source),
    mask all stale team/player/zone hints. The hypothesis is expired after TTL;
    later texts cannot revive it without an explicitly new accepted play.
    Source health itself is not inferred here: the caller passes the active
    source from GN-063. Both the age and TTL use aligned capture time.
    """
    play = request.last_play
    if play is None:
        return BallFreshnessResponse(
            uncertainty="uncertain", display_label="posição incerta",
            reason="no_explicit_play", active_source_id=request.active_source_id,
            last_aligned_at=None, age_seconds=None, expires_at=None,
            team_id=None, player_id=None, zone=None,
        )

    age = (request.evaluated_at - play.aligned_at).total_seconds()
    expires_at = play.aligned_at + timedelta(seconds=request.expire_after_seconds)
    if age > request.expire_after_seconds:
        uncertainty, reason = "expired", "ttl_expired"
    elif request.active_source_id != play.source_id:
        uncertainty, reason = "uncertain", "source_unavailable_or_changed"
    elif age > request.uncertain_after_seconds:
        uncertainty, reason = "uncertain", "narration_silent"
    else:
        uncertainty, reason = "estimated", "recent_explicit_play"
    show_position = uncertainty == "estimated"
    return BallFreshnessResponse(
        uncertainty=uncertainty,
        display_label="posição estimada" if show_position else "posição incerta",
        reason=reason,
        active_source_id=request.active_source_id,
        last_aligned_at=play.aligned_at,
        age_seconds=round(age, 3),
        expires_at=expires_at,
        team_id=play.team_id if show_position else None,
        player_id=play.player_id if show_position else None,
        zone=play.zone if show_position else None,
    )
