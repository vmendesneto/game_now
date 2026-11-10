"""Validated configuration DTOs. ContractBundle v1 stays frozen."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.contracts import Id, Match, NonNegativeSeconds, Player, StrictModel, Team


class MatchConfig(StrictModel):
    id: Id
    home: Team
    away: Team
    period: Literal["first_half", "half_time", "second_half", "finished"] = "first_half"
    match_seconds: NonNegativeSeconds = 0
    home_score: int = Field(default=0, ge=0)
    away_score: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def check_match(self) -> "MatchConfig":
        Match.model_validate(self.model_dump())
        return self


Position = Literal["goalkeeper", "defender", "midfielder", "forward", "other"]


class RosterPlayer(Player):
    """Position is configuration metadata, not a change to the v1 event contract."""
    position: Position = "other"

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Player name cannot be blank")
        return value

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("Aliases cannot be blank")
        if len({alias.casefold() for alias in cleaned}) != len(cleaned):
            raise ValueError("Duplicate aliases for one player")
        return cleaned
