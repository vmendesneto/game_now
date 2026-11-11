"""GN-055: transparent evidence-strength scores, NOT calibrated probabilities.

Scores are deterministic rules for assessing the available text and its
caller-provided age. They cannot validate the broadcast or move the ball.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.contracts import EventKind, Id, Match, Probability, StrictModel, Zone
from app.event_detection import EventRequest, detect_event
from app.field_regions import RegionRequest, detect_region
from app.narration_entities import NarrationResolveRequest, resolve_narration


class ConfidenceRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2048)
    team_id: Id | None = None
    observed_age_seconds: float | None = Field(default=None, ge=0, le=86400)


class ComponentScores(StrictModel):
    player: Probability
    team: Probability
    region: Probability
    event: Probability
    freshness: Probability


class ConfidenceEvidence(StrictModel):
    mode: Literal["heuristic_strength_not_calibrated_v1"] = "heuristic_strength_not_calibrated_v1"
    eligible_for_live_state: bool
    player_id: Id | None = None
    team_id: Id | None = None
    zone: Zone | None = None
    event_kind: EventKind | None = None
    scores: ComponentScores
    reasons: dict[str, str]


def _freshness(age_seconds: float | None) -> tuple[float, str]:
    # Age is supplied by the caller, not verified against a clock or audio PTS.
    if age_seconds is None:
        return 0.0, "age_not_provided"
    if age_seconds <= 5:
        return 1.0, "recent_by_caller_age"
    if age_seconds >= 30:
        return 0.0, "stale_by_caller_age"
    return round((30 - age_seconds) / 25, 3), "decaying_by_caller_age"


def assess_confidence(match: Match, request: ConfidenceRequest) -> ConfidenceEvidence:
    """Separately score explicit actor/team/zone/event and textual freshness.

    Values 1.0, 0.5 and 0.0 are rule strengths, NEVER observed accuracy.
    No single combined score: weak/absent region must not be masked by a goal.
    """
    valid_teams = {match.home.id, match.away.id}
    if request.team_id is not None and request.team_id not in valid_teams:
        raise ValueError("Unknown team")
    narration = resolve_narration(match, NarrationResolveRequest(text=request.text))
    live = narration.eligible_for_live_state and match.period in ("first_half", "second_half")
    zeros = ComponentScores(player=0.0, team=0.0, region=0.0,
                            event=0.0, freshness=0.0)
    if not live:
        return ConfidenceEvidence(
            eligible_for_live_state=False, scores=zeros,
            reasons={k: "not_current_live_play" for k in ComponentScores.model_fields},
        )

    relevant = [m for m in narration.mentions
                if m.kind in ("player", "team", "pronoun", "unknown")]
    ambiguous = any(m.status != "resolved" for m in relevant)
    players = {m.player_id for m in relevant
               if m.kind == "player" and m.status == "resolved" and m.player_id is not None}
    mentioned_teams = {m.team_id for m in relevant
                       if m.kind in ("team", "player") and m.status == "resolved"
                       and m.team_id is not None}
    conflicting_context = (
        request.team_id is not None and mentioned_teams
        and request.team_id not in mentioned_teams
    )
    player_id = next(iter(players)) if len(players) == 1 and not ambiguous else None
    if ambiguous:
        player_reason = "ambiguous_mention"
    elif player_id is None:
        player_reason = "no_unique_explicit_player"
    else:
        player_reason = "unique_explicit_player"

    team_id = None
    team_score = 0.0
    if ambiguous:
        team_reason = "ambiguous_mention"
    elif len(mentioned_teams) > 1:
        team_reason = "conflicting_team_mentions"
    elif conflicting_context:
        team_reason = "conflicting_caller_context"
    elif len(mentioned_teams) == 1:
        team_id = next(iter(mentioned_teams))
        team_score = 1.0
        team_reason = "explicit_text_team"
    elif request.team_id is not None:
        team_id = request.team_id
        team_score = 0.5
        team_reason = "caller_supplied_team_only"
    else:
        team_reason = "no_explicit_team"

    region = detect_region(match, RegionRequest(
        text=request.text, team_id=request.team_id))
    region_score = (1.0 if region.team_evidence == "text" else 0.5
                    if region.status == "explicit" else 0.0)
    region_reason = (region.reason if region.status != "explicit"
                     else "explicit_zone_with_" + region.team_evidence)
    event = detect_event(match, EventRequest(text=request.text))
    event_score = 1.0 if event.status == "explicit" else 0.0
    freshness, freshness_reason = _freshness(request.observed_age_seconds)
    return ConfidenceEvidence(
        eligible_for_live_state=True, player_id=player_id, team_id=team_id,
        zone=region.zone if region.status == "explicit" else None,
        event_kind=event.kind if event.status == "explicit" else None,
        scores=ComponentScores(
            player=1.0 if player_id is not None else 0.0,
            team=team_score, region=region_score, event=event_score,
            freshness=freshness,
        ),
        reasons={"player": player_reason, "team": team_reason,
                 "region": region_reason, "event": event.reason,
                 "freshness": freshness_reason},
    )
