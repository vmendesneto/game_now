"""GN-051: conservative entity mentions in text-only football narration.

Uses only registered match teams/rosters. This module never changes possession,
score, events or ball position; a name match is not evidence of a live touch.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from pydantic import Field, model_validator

from app.contracts import Id, Match, StrictModel
from app.narration_classifier import MAX_TEXT_CHARS, classify_narration

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_UNITS = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
          "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9}
_SMALL = {**_UNITS, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
          "quatorze": 14, "catorze": 14, "quinze": 15, "dezesseis": 16,
          "dezessete": 17, "dezoito": 18, "dezenove": 19}
_TENS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
         "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90}
_LINKS = frozenset({"do", "da", "pelo", "pela"})
_PRONOUNS = frozenset({"ele", "dele"})
_BANNED_ALIASES = frozenset({"ele", "dele", "camisa", "jogador", "bola", "time"})


class Mention(StrictModel):
    text: str
    kind: str  # player, team, pronoun
    status: str  # resolved, ambiguous, unknown
    start: int
    end: int
    player_id: Id | None = None
    team_id: Id | None = None
    candidate_ids: list[Id] = Field(default_factory=list)
    evidence: str  # explicit_name, shirt_number, explicit_team, local_antecedent, prior_context


class NarrationContext(StrictModel):
    """Caller-provided per-source context; accepted only for the next nearby window."""
    match_id: Id
    source_id: Id
    sequence: int = Field(ge=0)
    end_seconds: float = Field(ge=0)
    player_id: Id


class NarrationResolveRequest(StrictModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    source_id: Id | None = None
    sequence: int | None = Field(default=None, ge=0)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, ge=0)
    previous: NarrationContext | None = None

    @model_validator(mode="after")
    def validate_window(self) -> "NarrationResolveRequest":
        if self.end_seconds is not None and self.start_seconds is not None:
            if self.end_seconds < self.start_seconds:
                raise ValueError("end_seconds must not precede start_seconds")
        return self


class NarrationResolution(StrictModel):
    narration_kind: str
    eligible_for_live_state: bool
    mentions: list[Mention]
    next_context: NarrationContext | None = None


@dataclass(frozen=True)
class _Token:
    word: str
    start: int
    end: int


def _fold(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in folded if not unicodedata.combining(c))


def _tokens(value: str) -> list[_Token]:
    return [_Token(_fold(m.group()), m.start(), m.end()) for m in _WORD.finditer(value)]


def _number(words: list[str], pos: int) -> tuple[int, int] | None:
    if pos >= len(words):
        return None
    first = words[pos]
    if first.isascii() and first.isdecimal():
        number = int(first)
        return (number, pos + 1) if 1 <= number <= 99 else None
    if first in _SMALL:
        return _SMALL[first], pos + 1
    if first in _TENS:
        number = _TENS[first]
        if pos + 2 < len(words) and words[pos + 1] == "e" and words[pos + 2] in _UNITS:
            return number + _UNITS[words[pos + 2]], pos + 3
        return number, pos + 1
    return None


def _shirt(words: list[str], pos: int) -> tuple[int, int] | None:
    if words[pos] not in ("camisa", "numero"):
        return None
    number_pos = pos + 1
    if number_pos < len(words) and words[number_pos] in ("numero", "n"):
        number_pos += 1
    return _number(words, number_pos)


def _aliases(match: Match) -> dict[tuple[str, ...], set[str]]:
    result: dict[tuple[str, ...], set[str]] = {}
    for player in match.players:
        for value in (player.name, *player.aliases):
            if len(value) > 150:
                continue
            key = tuple(token.word for token in _tokens(value))
            if key and " ".join(key) not in _BANNED_ALIASES:
                result.setdefault(key, set()).add(player.id)
    return result


def _teams(match: Match) -> dict[tuple[str, ...], set[str]]:
    result: dict[tuple[str, ...], set[str]] = {}
    for team in (match.home, match.away):
        for value in (team.name, team.short_name):
            key = tuple(token.word for token in _tokens(value))
            # Three-letter abbreviations must be written in uppercase, checked
            # separately in the scanner so e.g. "ver" is not a club.
            if key:
                result.setdefault(key, set()).add(team.id)
    return result


def resolve_narration(match: Match, request: NarrationResolveRequest) -> NarrationResolution:
    """Resolve explicit names/shirts, then *strictly local* pronouns.

    Ambiguous references stay ambiguous. A previous-window antecedent is valid
    only for the same match/source, immediately following sequence and <=8s gap.
    Non-live text never uses or issues cross-window antecedents.
    """
    decision = classify_narration(request.text)
    live = decision.is_current_play
    tokens = _tokens(request.text)
    words = [t.word for t in tokens]
    names, teams = _aliases(match), _teams(match)
    ids = {player.id: player for player in match.players}
    found: list[tuple[int, int, str, set[str], str]] = []
    i = 0
    while i < len(tokens):
        shirt = _shirt(words, i)
        options: list[tuple[int, str, set[str], str]] = []
        if shirt is not None:
            number, end = shirt
            matches = {p.id for p in match.players if p.number == number}
            options.append((end, "player", matches, "shirt_number"))
        for key, values in names.items():
            if tuple(words[i:i + len(key)]) == key:
                options.append((i + len(key), "player", values, "explicit_name"))
        for key, values in teams.items():
            if tuple(words[i:i + len(key)]) == key:
                # Abbreviations are accepted only when uppercase in the original.
                raw = request.text[tokens[i].start:tokens[i + len(key) - 1].end]
                short = any(_fold(t.short_name) == " ".join(key) for t in (match.home, match.away))
                if not short or len(key) > 1 or len(raw) > 3 or raw.isupper():
                    options.append((i + len(key), "team", values, "explicit_team"))
        if options:
            length = max(option[0] for option in options)
            longest = [o for o in options if o[0] == length]
            # Same surface as team and player is unsafe: emit no inferred identity.
            kinds = {o[1] for o in longest}
            if len(kinds) > 1:
                found.append((i, length, "unknown", set(), "ambiguous_surface"))
            else:
                kind = longest[0][1]
                found.append((i, length, kind,
                              set().union(*(o[2] for o in longest)), longest[0][3]))
            i = length
            continue
        if words[i] in _PRONOUNS:
            found.append((i, i + 1, "pronoun", set(), "pronoun"))
        i += 1

    def make(index: int, end: int, kind: str, candidate: set[str], reason: str,
             *, team: str | None = None) -> Mention:
        if kind == "player" and team is not None:
            candidate = {pid for pid in candidate if ids[pid].team_id == team}
        ordered = sorted(candidate)
        status = "resolved" if len(ordered) == 1 else ("ambiguous" if ordered else "unknown")
        player_id = ordered[0] if status == "resolved" and kind in ("player", "pronoun") else None
        team_id = (ids[player_id].team_id if player_id is not None else
                   ordered[0] if status == "resolved" and kind == "team" else None)
        return Mention(text=request.text[tokens[index].start:tokens[end-1].end],
                       kind=kind, status=status, start=tokens[index].start,
                       end=tokens[end-1].end, player_id=player_id, team_id=team_id,
                       candidate_ids=ordered, evidence=reason)

    mentions: list[Mention] = []
    for start, end, kind, candidates, reason in found:
        if kind == "pronoun":
            if not live:
                mentions.append(make(start, end, kind, set(), "non_live_context"))
                continue
            # Anaphora cannot jump sentences or choose between two player names.
            preceding = [m for m in mentions if m.kind == "player"
                         and m.end < tokens[start].start
                         and not any(mark in request.text[m.end:tokens[start].start] for mark in ".!?")]
            distinct = {m.player_id for m in preceding if m.status == "resolved"}
            blockers = any(m.status != "resolved" for m in preceding)
            if len(distinct) == 1 and not blockers:
                pid = next(iter(distinct))
                mentions.append(make(start, end, kind, {pid}, "local_antecedent"))
                continue
            previous = request.previous
            valid_previous = (
                not preceding and previous is not None
                and not any(m.kind in ("player", "unknown")
                            and m.end <= tokens[start].start for m in mentions)
                and request.source_id == previous.source_id
                and request.sequence is not None and request.sequence == previous.sequence + 1
                and request.start_seconds is not None
                and -2 <= request.start_seconds - previous.end_seconds <= 8
                and previous.match_id == match.id and previous.player_id in ids
                and not any(m.kind == "team" and m.status == "resolved"
                            and m.team_id != ids[previous.player_id].team_id for m in mentions)
            )
            if valid_previous:
                mentions.append(make(start, end, kind, {previous.player_id}, "prior_context"))
            else:
                mentions.append(make(start, end, kind, set(), "no_unique_antecedent"))
        elif kind == "player":
            team_context = None
            for t_start, t_end, t_kind, t_ids, _ in found:
                if t_kind == "team" and t_start == end + 1 and end < len(words):
                    if words[end] in _LINKS and len(t_ids) == 1:
                        team_context = next(iter(t_ids))
            mentions.append(make(start, end, kind, candidates, reason, team=team_context))
        else:
            mentions.append(make(start, end, kind, candidates, reason))

    # Carry *only* a unique, explicitly named player, and only from live text.
    # A pronoun or a shirt number by itself cannot refresh this context forever.
    explicit = [m for m in mentions if m.kind == "player" and m.evidence == "explicit_name"]
    next_context = None
    if (live and len(explicit) == 1 and explicit[0].player_id is not None
            and sum(m.kind == "player" for m in mentions) == 1
            and request.source_id is not None and request.sequence is not None
            and request.end_seconds is not None):
        next_context = NarrationContext(
            match_id=match.id, source_id=request.source_id,
            sequence=request.sequence, end_seconds=request.end_seconds,
            player_id=explicit[0].player_id,
        )
    return NarrationResolution(narration_kind=decision.label.value,
                               eligible_for_live_state=live,
                               mentions=mentions, next_context=next_context)
