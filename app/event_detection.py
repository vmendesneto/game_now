"""GN-054: text-only, unambiguous evidence for a single football action.

A rule match is not a score update, ball movement, calibrated probability,
player identity, or event from an actual broadcast.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field

from app.contracts import EventKind, Match, StrictModel
from app.narration_classifier import classify_narration


class EventRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2048)


class EventEvidence(StrictModel):
    status: Literal["explicit", "unknown"]
    kind: EventKind | None = None
    cue: str | None = None
    reason: str


# Require an affirmative expression actually used for the action. Broad nouns
# ("area", "jogador", "bola", "lance") are not sufficient event evidence.
_RULES: dict[EventKind, tuple[str, ...]] = {
    EventKind.PASS: (
        r"\bpassa a bola\b", r"\btoca de primeira\b",
    ),
    EventKind.CROSS: (
        r"\bcruza na area\b", r"\bcruza para a area\b", r"\bcruzou\b",
    ),
    EventKind.SHOT: (
        r"\bfinaliza\b", r"\bchutou\b", r"\bchuta\b",
    ),
    EventKind.SAVE: (
        r"\bgoleiro defendeu\b", r"\bdefendeu o chute\b",
        r"\bdefesa do goleiro\b",
    ),
    EventKind.GOAL: (
        r"\bmarcou o gol\b", r"\bmarca o gol\b", r"\bgol do\b", r"\bgo{3,}l\b",
    ),
    EventKind.CORNER: (
        r"\bcobrou o escanteio\b", r"\bescanteio para\b",
    ),
    EventKind.THROW_IN: (
        r"\blateral para\b",
    ),
    EventKind.OFFSIDE: (
        r"\bimpedimento marcado\b",
    ),
    EventKind.FOUL: (
        r"\bcomete a falta\b", r"\bfalta em\b",
    ),
    EventKind.PENALTY: (
        r"\bpenalti para\b",
    ),
    EventKind.GOAL_KICK: (
        r"\btiro de meta\b",
    ),
}
# Do not turn possible, denied, attempted, cancelled or hypothetical actions
# into factual events. The initial baseline deliberately favors false negatives.
_UNCERTAIN = re.compile(
    r"\b(?:nao|nunca|jamais|quase|talvez|aparentemente|parecia|teria|"
    r"poderia|tentou|simulou|anulado|anulada|invalidado|invalidada|"
    r"se tivesse|disse que)\b"
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    ascii_base = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(ascii_base.split())


def detect_event(match: Match, request: EventRequest) -> EventEvidence:
    """Return a single affirmative event type, or unknown with an explanation."""
    if match.period not in ("first_half", "second_half"):
        return EventEvidence(status="unknown", reason="not_playing")
    if not classify_narration(request.text).is_current_play:
        return EventEvidence(status="unknown", reason="not_current_live_play")
    normalized = _normalize(request.text)
    if _UNCERTAIN.search(normalized):
        return EventEvidence(status="unknown", reason="negated_or_speculative")
    cues: list[tuple[EventKind, str]] = [
        (kind, match.group(0)) for kind, patterns in _RULES.items()
        for pattern in patterns for match in re.finditer(pattern, normalized)
    ]
    if not cues:
        return EventEvidence(status="unknown", reason="no_explicit_event_cue")
    if len({kind for kind, _ in cues}) != 1:
        return EventEvidence(status="unknown", reason="conflicting_event_cues")
    kind, cue = cues[0]
    return EventEvidence(status="explicit", kind=kind, cue=cue,
                         reason="unique_affirmative_live_event_cue")
