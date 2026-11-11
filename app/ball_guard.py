"""GN-056: fail-closed gate for *candidate* ball movement from narrated text.

A candidate is not a tracked ball, a persisted position or proof of an actual
broadcast. The production ingestion/fusion pipeline has not been connected.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field

from app.confidence import ConfidenceRequest, assess_confidence
from app.contracts import EstimatedBallState, Id, Match, StrictModel, Zone
from app.field_regions import RegionRequest, detect_region
from app.narration_classifier import classify_narration
from app.possession import PossessionRequest, detect_possession


# Negation, speculation and historic or conditional statements cannot establish
# a current touch, even when a separate rule finds team/ball/zone keywords.
_NON_FACTUAL = re.compile(
    r"\b(?:nao|nem|nunca|jamais|quase|talvez|aparentemente|parece|"
    r"parecia|teria|teriam|poderia|poderiam|deveria|tentou|simulou|"
    r"anulado|anulada|invalidado|invalidada|se tivesse|disse que)\b"
)
MAX_CANDIDATE_AGE_SECONDS = 5.0


class BallGuardRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2048)
    # This age is caller-reported and NOT verified against broadcast/audio time.
    # It is a conservative temporary input until GN-060/GN-061.
    observed_age_seconds: float | None = Field(default=None, ge=0, le=86400)


class BallGuardDecision(StrictModel):
    decision: Literal["hold", "candidate"]
    reason: str
    current_ball: EstimatedBallState
    candidate_zone: Zone | None = None
    team_id: Id | None = None
    player_id: Id | None = None
    field_band: int | None = Field(default=None, ge=1, le=5)
    field_lane: Literal["left", "center", "right"] | None = None
    freshness_basis: Literal["caller_reported_unverified"] = "caller_reported_unverified"


def _fold(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def guard_ball_movement(
    match: Match, current_ball: EstimatedBallState, request: BallGuardRequest,
) -> BallGuardDecision:
    """Only propose a location with independently explicit, consistent evidence.

    Always preserve the original ball. 'candidate' is not a state transition:
    callers MUST NOT persist it without later verified timing and fusion.
    In particular a high event/player score cannot replace missing zone evidence.
    """
    def hold(reason: str) -> BallGuardDecision:
        return BallGuardDecision(
            decision="hold", reason=reason, current_ball=current_ball.model_copy(deep=True),
        )

    if match.period not in ("first_half", "second_half"):
        return hold("not_playing")
    if not classify_narration(request.text).is_current_play:
        return hold("not_current_live_play")
    if _NON_FACTUAL.search(_fold(request.text)):
        return hold("negated_or_speculative")
    if request.observed_age_seconds is None:
        return hold("age_not_provided")
    if request.observed_age_seconds > MAX_CANDIDATE_AGE_SECONDS:
        return hold("not_recent_by_caller_age")

    possession = detect_possession(
        match, PossessionRequest(text=request.text, previous_team_id=current_ball.team_id),
    )
    if possession.status != "explicit" or possession.team_id is None:
        return hold("possession_" + possession.reason)

    # Never fall back to previous possession or caller-provided team context:
    # the current phrase must explicitly name ONE team and ONE full zone.
    region = detect_region(match, RegionRequest(text=request.text))
    if region.status != "explicit" or region.zone is None:
        return hold("region_" + region.reason)
    if region.team_id != possession.team_id:
        return hold("contradictory_possession_and_region")

    evidence = assess_confidence(
        match, ConfidenceRequest(
            text=request.text, observed_age_seconds=request.observed_age_seconds,
        ),
    )
    if (not evidence.eligible_for_live_state
            or evidence.scores.team != 1.0
            or evidence.scores.region != 1.0
            or evidence.scores.freshness != 1.0
            or evidence.team_id != possession.team_id
            or evidence.zone != region.zone):
        return hold("insufficient_independent_evidence")

    if current_ball.zone == region.zone and current_ball.team_id == possession.team_id:
        return hold("already_in_reported_zone")

    return BallGuardDecision(
        decision="candidate",
        reason="unique_current_possession_team_and_zone",
        current_ball=current_ball.model_copy(deep=True),
        candidate_zone=region.zone,
        team_id=possession.team_id,
        player_id=possession.player_id,
        field_band=region.field_band,
        field_lane=region.field_lane,
    )
