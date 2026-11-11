"""GN-052: explicit, diagnostic possession evidence from written live narration.

No inferred turnover from a pass alone. Never writes the persistent match or ball.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from app.contracts import Id, Match, StrictModel
from app.narration_entities import Mention, NarrationResolveRequest, resolve_narration

# Anchors must state where the ball actually is or who explicitly got it.
_BEFORE = re.compile(r"\b(com a bola|recebe a bola|recupera a bola|rouba a bola|retoma a posse)\b", re.I)
_AFTER = re.compile(r"\bbola com\b", re.I)
_END = re.compile(r"[.!?;]\s*")


class PossessionRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2048)
    previous_team_id: Id | None = None


class PossessionEvidence(StrictModel):
    status: Literal["explicit", "unknown"]
    team_id: Id | None = None
    player_id: Id | None = None
    changed_team: bool | None = None
    cue: str | None = None
    reason: str


def _best(mentions: list[Mention], start: int, end: int, *, following: bool) -> Mention | None:
    """Take one explicit, uniquely resolved reference directly beside a ball cue."""
    usable = [m for m in mentions if m.status == "resolved" and m.kind in ("player", "team")
              and ((start <= m.start < end) if following else (start <= m.start and m.end <= end))]
    if not usable:
        return None
    # When the name is followed by 'do Azul', the associated athlete is more
    # specific than the trailing team in that same local phrase.
    players = [m for m in usable if m.kind == "player"]
    if players:
        return players[-1] if not following else players[0]
    return usable[-1] if not following else usable[0]


def detect_possession(match: Match, request: PossessionRequest) -> PossessionEvidence:
    if request.previous_team_id is not None and request.previous_team_id not in {match.home.id, match.away.id}:
        raise ValueError("Unknown previous team")
    resolution = resolve_narration(match, NarrationResolveRequest(text=request.text))
    if not resolution.eligible_for_live_state:
        return PossessionEvidence(status="unknown", reason="not_current_live_play")

    # One explicit ball anchor only; avoid choosing one among conflicting claims.
    cues = [(m.start(), m.end(), m.group()) for exp in (_BEFORE, _AFTER)
            for m in exp.finditer(request.text)]
    if len(cues) != 1:
        return PossessionEvidence(status="unknown", reason="no_unique_possession_cue")
    start, end, cue = cues[0]
    following = cue.casefold() == "bola com"
    if following:
        candidate = _best(resolution.mentions, end, min(len(request.text), end + 48), following=True)
        if candidate and _END.search(request.text[end:candidate.start]):
            candidate = None
    else:
        candidate = _best(resolution.mentions, max(0, start - 50), start, following=False)
        if candidate and _END.search(request.text[candidate.end:start]):
            candidate = None

    if candidate is None:
        return PossessionEvidence(status="unknown", reason="no_unique_entity_near_cue")
    # An unresolved player between the reference and the cue blocks inference;
    # e.g. 'Azul, João Silva com a bola' cannot silently fall back to Azul.
    relevant_start, relevant_end = (end, candidate.start) if following else (candidate.end, start)
    if any(m.status != "resolved" and m.kind in ("player", "unknown", "pronoun")
           and relevant_start <= m.start < relevant_end for m in resolution.mentions):
        return PossessionEvidence(status="unknown", reason="ambiguous_entity_near_cue")
    return PossessionEvidence(
        status="explicit", team_id=candidate.team_id,
        player_id=candidate.player_id,
        changed_team=(request.previous_team_id != candidate.team_id
                      if request.previous_team_id is not None else None),
        cue=cue.casefold(), reason="explicit_ball_cue_and_unique_entity",
    )
