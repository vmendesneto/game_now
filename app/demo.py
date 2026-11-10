"""Deterministic, media-free synthetic narration for the first UI/API smoke tests.

The scenario's duplicate keys are supplied by its author, NOT inferred by fusion.
Live audio, ASR, source alignment and general football NLP are not implemented.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from app.contracts import (
    AudioSource, Category, Confidences, ContractBundle, EstimatedBallState,
    EventKind, FootballEvent, Match, TranscriptSegment, Zone,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
UTC = timezone.utc
# The source name and event grouping are scenario metadata, not AI predictions.
SCENARIO = [
    {"source": "source-radio-a", "key": "possession-1", "seconds": 730,
     "text": "Caio recebe no meio-campo pelo corredor direito.", "team": "team-home", "player": "player-azul-9"},
    {"source": "source-youtube-b", "key": "possession-1", "seconds": 730,
     "text": "Caio recebe no meio-campo pelo corredor direito.", "team": "team-home", "player": "player-azul-9"},
    {"source": "source-radio-a", "key": None, "seconds": 730,
     "text": "Oferecimento dos nossos patrocinadores: promoção especial!"},
    {"source": "source-youtube-b", "key": "cross-1", "seconds": 756,
     "text": "Caio cruza no campo de ataque pelo meio.", "team": "team-home", "player": "player-azul-9"},
    {"source": "source-radio-a", "key": "goal-1", "seconds": 811,
     "text": "Gooool do Azul! Caio finaliza na área rival!", "team": "team-home", "player": "player-azul-9"},
    {"source": "source-youtube-b", "key": "goal-1", "seconds": 811,
     "text": "Gol do Azul, Caio marcou na área rival!", "team": "team-home", "player": "player-azul-9"},
    {"source": "source-radio-a", "key": None, "seconds": 811,
     "text": "No replay vemos o gol novamente."},
    {"source": "source-radio-a", "key": None, "seconds": 820,
     "text": "Sem informação nova sobre a bola.", "expire": True},
]


def interpret_demo_text(text: str) -> tuple[Category, EventKind | None, Zone | None]:
    """Conservative *demo-only* rules. No position without location words."""
    t = text.casefold()
    if any(word in t for word in ("patrocinador", "oferecimento", "promoção")):
        return Category.AD, None, None
    if "replay" in t or "novamente" in t:
        return Category.REPLAY, None, None
    if "análise" in t or "comentando" in t:
        return Category.ANALYSIS, None, None
    kind = None
    if "gol" in t or "gooo" in t:
        kind = EventKind.GOAL
    elif "cruza" in t or "cruzamento" in t:
        kind = EventKind.CROSS
    elif "chuta" in t or "finaliza" in t:
        kind = EventKind.SHOT
    elif "recebe" in t or "passa" in t:
        kind = EventKind.POSSESSION
    if kind is None:
        return Category.UNKNOWN, None, None

    band = (5 if "área rival" in t or "dentro da área" in t
            else 4 if "campo de ataque" in t
            else 3 if "meio-campo" in t else None)
    lane = ("right" if "direito" in t else "left" if "esquerdo" in t
            else "center" if "pelo meio" in t or "área rival" in t else None)
    zone = Zone(band=band, lane=lane) if band is not None and lane is not None else None
    return Category.LIVE_PLAY, kind, zone


class DemoEngine:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> dict:
        fixture = json.loads((FIXTURES / "two_sources_delayed.json").read_text(encoding="utf-8"))
        self.match = Match.model_validate(fixture["match"]).model_copy(
            update={"home_score": 0, "away_score": 0, "match_seconds": 0}
        )
        self.sources = [AudioSource.model_validate(item) for item in fixture["sources"]]
        self.segments: list[TranscriptSegment] = []
        self.events: list[FootballEvent] = []
        self._by_key: dict[str, FootballEvent] = {}
        self.index = 0
        self.ball = EstimatedBallState(updated_at=datetime.now(UTC))
        return self.snapshot()

    def snapshot(self) -> dict:
        bundle = ContractBundle(
            match=self.match, sources=self.sources, segments=self.segments,
            events=self.events, ball=self.ball
        )
        return {"mode": "synthetic_demo", "step": self.index, "total_steps": len(SCENARIO),
                "data": bundle.model_dump(mode="json")}

    def step(self) -> dict:
        if self.index >= len(SCENARIO):
            return self.snapshot()
        item = SCENARIO[self.index]
        self.index += 1
        observed = datetime.now(UTC)
        category, kind, zone = interpret_demo_text(item["text"])
        segment = TranscriptSegment(
            id=f"demo-seg-{self.index}", source_id=item["source"],
            text=item["text"], category=category,
            captured_at=observed, transcribed_at=observed + timedelta(milliseconds=100),
            match_seconds=item["seconds"], text_confidence=1.0
        )
        self.segments.append(segment)
        self.match.match_seconds = max(self.match.match_seconds, item["seconds"])
        key = item.get("key")
        if key and kind is not None and category == Category.LIVE_PLAY:
            if key in self._by_key:
                existing = self._by_key[key]
                existing.source_ids.append(item["source"])
                existing.segment_ids.append(segment.id)
                existing.observed_at = observed
                # A duplicate report does not increment score or move the ball.
            else:
                conf = Confidences(
                    team=0.95, player=0.9, zone=0.7 if zone else 0,
                    action=0.9, timing=0.8
                )
                event = FootballEvent(
                    id=f"demo-event-{key}", kind=kind,
                    source_ids=[item["source"]], segment_ids=[segment.id],
                    observed_at=observed, match_seconds=item["seconds"],
                    team_id=item.get("team"), player_id=item.get("player"),
                    zone=zone, confidences=conf,
                    uncertainty="estimated" if zone else "uncertain"
                )
                self.events.append(event)
                self._by_key[key] = event
                if kind == EventKind.GOAL:
                    if event.team_id == self.match.home.id:
                        self.match.home_score += 1
                    elif event.team_id == self.match.away.id:
                        self.match.away_score += 1
                if zone is not None:
                    self.ball = EstimatedBallState(
                        last_event_id=event.id, zone=zone, team_id=event.team_id,
                        player_id=event.player_id, confidences=conf,
                        uncertainty="estimated", updated_at=observed,
                        expires_at=observed + timedelta(seconds=10)
                    )
        if item.get("expire"):
            self.ball = EstimatedBallState(
                last_event_id=self.ball.last_event_id, updated_at=observed,
                uncertainty="expired"
            )
        return self.snapshot()
