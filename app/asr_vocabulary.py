"""GN-046: bounded initial ASR vocabulary from a saved football match."""
from __future__ import annotations

import re
import unicodedata

from app.contracts import Match

FOOTBALL_TERMS = (
    "goleiro", "impedimento", "escanteio", "pênalti", "lateral",
    "cruzamento", "meio-campo", "acréscimos", "chute", "gol",
)


def _safe_text(value: str) -> str:
    # Remove control characters, preserve Portuguese accents and word spacing.
    chars = "".join(
        char if not unicodedata.category(char).startswith("C") else " "
        for char in value
    )
    return re.sub(r"\s+", " ", chars).strip(" ,.;:-")[:70]


def build_vocabulary_prompt(match: Match, *, max_chars: int = 500) -> str:
    """Build conservative model hints; not prompts for an LLM or results.

    The model is *not* forced to output these names. Short, clean hints prevent
    very large rosters or malicious newlines from swelling the whisper context.
    """
    if not 200 <= max_chars <= 600:
        raise ValueError("max_chars must be between 200 and 600")
    header = "Transcrição de narração de futebol em português brasileiro."
    pieces = [header]

    def add(label: str, values: list[str]) -> None:
        seen: set[str] = set()
        accepted: list[str] = []
        for item in values:
            word = _safe_text(item)
            key = word.casefold()
            if not word or key in seen:
                continue
            fragment = f"{label}: " + ", ".join(accepted + [word]) + "."
            candidate = " ".join(pieces + [fragment])
            if len(candidate) > max_chars:
                break
            seen.add(key)
            accepted.append(word)
        if accepted:
            pieces.append(f"{label}: " + ", ".join(accepted) + ".")

    add("Clubes", [match.home.name, match.away.name])
    add("Termos", list(FOOTBALL_TERMS))
    # Prefer starters and shirt order. Names and aliases are configuration,
    # not claims that an athlete actually touched the ball.
    players = sorted(match.players, key=lambda p: (not p.starter, p.number, p.name))
    add("Atletas", [name for player in players for name in (player.name, *player.aliases)])
    return " ".join(pieces)
