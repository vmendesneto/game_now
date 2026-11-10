"""Game Now event contract v1 — explicit unknowns instead of guessed coordinates."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"
Id = Annotated[str, Field(min_length=3, max_length=128, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$")]
Probability = Annotated[float, Field(ge=0.0, le=1.0)]
NonNegativeSeconds = Annotated[float, Field(ge=0.0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Category(StrEnum):
    LIVE_PLAY = "live_play"
    AD = "ad"
    ANALYSIS = "analysis"
    REPLAY = "replay"
    UNKNOWN = "unknown"


class EventKind(StrEnum):
    PASS = "pass"
    CROSS = "cross"
    SHOT = "shot"
    SAVE = "save"
    GOAL = "goal"
    CORNER = "corner"
    THROW_IN = "throw_in"
    OFFSIDE = "offside"
    FOUL = "foul"
    PENALTY = "penalty"
    GOAL_KICK = "goal_kick"
    POSSESSION = "possession"
    UNKNOWN = "unknown"


class Zone(StrictModel):
    """15 zones, relative to the attacking team's direction; not GPS coordinates."""
    band: Literal[1, 2, 3, 4, 5]
    lane: Literal["left", "center", "right"]


class Team(StrictModel):
    id: Id
    name: str = Field(min_length=1)
    short_name: str = Field(min_length=1, max_length=12)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    attack_direction: Literal["left_to_right", "right_to_left"]


class Player(StrictModel):
    id: Id
    team_id: Id
    name: str = Field(min_length=1)
    number: int = Field(ge=1, le=99)
    aliases: list[str] = Field(default_factory=list)
    starter: bool = True


class Match(StrictModel):
    id: Id
    home: Team
    away: Team
    players: list[Player] = Field(default_factory=list)
    period: Literal["first_half", "half_time", "second_half", "finished"] = "first_half"
    match_seconds: NonNegativeSeconds = 0
    home_score: int = Field(default=0, ge=0)
    away_score: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_teams(self) -> "Match":
        if self.home.id == self.away.id:
            raise ValueError("Home and away teams must be different")
        if self.home.attack_direction == self.away.attack_direction:
            raise ValueError("Teams must attack in opposite directions")
        player_ids = [player.id for player in self.players]
        if len(player_ids) != len(set(player_ids)):
            raise ValueError("Player IDs must be unique")
        if any(player.team_id not in (self.home.id, self.away.id) for player in self.players):
            raise ValueError("Every player must belong to one of the match teams")
        return self


class AudioSource(StrictModel):
    id: Id
    name: str = Field(min_length=1)
    kind: Literal["radio", "youtube"]
    url: str | None = None
    enabled: bool = True
    status: Literal["offline", "connecting", "online", "error"] = "offline"


class TranscriptSegment(StrictModel):
    id: Id
    source_id: Id
    text: str = Field(min_length=1)
    category: Category
    captured_at: datetime
    transcribed_at: datetime
    match_seconds: NonNegativeSeconds | None = None
    text_confidence: Probability = 0.0

    @model_validator(mode="after")
    def check_timestamps(self) -> "TranscriptSegment":
        require_aware(self.captured_at)
        require_aware(self.transcribed_at)
        if self.transcribed_at < self.captured_at:
            raise ValueError("Transcription cannot precede capture")
        return self


class Confidences(StrictModel):
    team: Probability = 0.0
    player: Probability = 0.0
    zone: Probability = 0.0
    action: Probability = 0.0
    timing: Probability = 0.0


class FootballEvent(StrictModel):
    """One canonical ID can consolidate several source observations."""
    id: Id
    kind: EventKind
    source_ids: list[Id] = Field(min_length=1)
    segment_ids: list[Id] = Field(min_length=1)
    observed_at: datetime
    match_seconds: NonNegativeSeconds | None = None
    team_id: Id | None = None
    player_id: Id | None = None
    zone: Zone | None = None
    confidences: Confidences
    uncertainty: Literal["estimated", "uncertain", "expired"] = "uncertain"

    @model_validator(mode="after")
    def check_event(self) -> "FootballEvent":
        require_aware(self.observed_at)
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Duplicate source IDs in a canonical event")
        if len(set(self.segment_ids)) != len(self.segment_ids):
            raise ValueError("Duplicate segment IDs in a canonical event")
        return self


class EstimatedBallState(StrictModel):
    last_event_id: Id | None = None
    team_id: Id | None = None
    player_id: Id | None = None
    zone: Zone | None = None
    confidences: Confidences = Field(default_factory=Confidences)
    uncertainty: Literal["estimated", "uncertain", "expired"] = "uncertain"
    updated_at: datetime
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def check_expiry(self) -> "EstimatedBallState":
        require_aware(self.updated_at)
        if self.expires_at is not None:
            require_aware(self.expires_at)
            if self.expires_at < self.updated_at:
                raise ValueError("Expiration cannot precede state update")
        return self


class ContractBundle(StrictModel):
    schema_version: Literal["1.0.0"] = SCHEMA_VERSION
    match: Match
    sources: list[AudioSource] = Field(default_factory=list)
    segments: list[TranscriptSegment] = Field(default_factory=list)
    events: list[FootballEvent] = Field(default_factory=list)
    ball: EstimatedBallState

    @model_validator(mode="after")
    def check_references(self) -> "ContractBundle":
        source_ids = {item.id for item in self.sources}
        segment_ids = {item.id for item in self.segments}
        event_ids = {item.id for item in self.events}
        team_ids = {self.match.home.id, self.match.away.id}
        player_ids = {player.id for player in self.match.players}
        for values, label in (
            ([s.id for s in self.sources], "source"),
            ([s.id for s in self.segments], "segment"),
            ([e.id for e in self.events], "event"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {label} IDs")
        if any(s.source_id not in source_ids for s in self.segments):
            raise ValueError("Segment references missing source")
        for event in self.events:
            if not set(event.source_ids) <= source_ids or not set(event.segment_ids) <= segment_ids:
                raise ValueError("Event references missing source or segment")
            if any(self_segment.source_id not in event.source_ids
                   for self_segment in self.segments if self_segment.id in event.segment_ids):
                raise ValueError("Event source IDs and segment source IDs disagree")
            self._validate_entity(event.team_id, event.player_id, team_ids, player_ids)
        self._validate_entity(self.ball.team_id, self.ball.player_id, team_ids, player_ids)
        if self.ball.last_event_id is not None and self.ball.last_event_id not in event_ids:
            raise ValueError("Ball references missing event")
        return self

    def _validate_entity(self, team_id: str | None, player_id: str | None,
                         teams: set[str], players: set[str]) -> None:
        if team_id is not None and team_id not in teams:
            raise ValueError("Unknown team ID")
        if player_id is not None and player_id not in players:
            raise ValueError("Unknown player ID")
        if player_id is not None and team_id is not None:
            player = next(p for p in self.match.players if p.id == player_id)
            if player.team_id != team_id:
                raise ValueError("Player does not belong to event team")


def require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("All timestamps must include timezone offset")
