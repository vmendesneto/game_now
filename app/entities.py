"""Conservative, deterministic football-player mention resolution (GN-022).

Only resolves extracted *mentions*; parsing free-form live narration is GN-051.
Never chooses among identical aliases or shirt numbers across clubs without context.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field, field_validator

from app.contracts import Id, Match, StrictModel


class ResolveRequest(StrictModel):
    mention: str = Field(min_length=1, max_length=150)
    team_id: Id | None = None

    @field_validator("mention")
    @classmethod
    def clean_mention(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Mention cannot be blank")
        return value


class ResolveResult(StrictModel):
    status: Literal["resolved", "ambiguous", "unknown"]
    player_id: Id | None = None
    team_id: Id | None = None
    candidate_ids: list[Id] = Field(default_factory=list)


def normalize_mention(text: str) -> str:
    """Normalize accents, case and punctuation, retaining whole-word boundaries."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


SHIRT = re.compile(r"^(?:camisa(?: (?:numero|no|n))?|numero|no|n)\s+([0-9]{1,2})$")


def resolve_player(match: Match, mention: str, team_id: str | None = None) -> ResolveResult:
    if team_id is not None and team_id not in {match.home.id, match.away.id}:
        raise ValueError("Unknown team context")
    normalized = normalize_mention(mention)
    if not normalized:
        return ResolveResult(status="unknown")
    shirt = SHIRT.fullmatch(normalized)
    if shirt is not None:
        shirt_number = int(shirt.group(1))
        candidates = [
            p for p in match.players
            if p.number == shirt_number and (team_id is None or p.team_id == team_id)
        ]
    else:
        candidates = [
            p for p in match.players
            if (team_id is None or p.team_id == team_id)
            and normalized in {normalize_mention(p.name), *(normalize_mention(alias) for alias in p.aliases)}
        ]
    ids = sorted(p.id for p in candidates)
    if len(candidates) == 1:
        return ResolveResult(status="resolved", player_id=candidates[0].id,
                             team_id=candidates[0].team_id, candidate_ids=ids)
    if candidates:
        return ResolveResult(status="ambiguous", candidate_ids=ids)
    return ResolveResult(status="unknown")
