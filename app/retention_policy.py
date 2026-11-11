"""GN-094: fail-fast, bounded retention settings for volatile ASR text."""
from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


def _bounded(env: Mapping[str, str], name: str, default: int,
             minimum: int, maximum: int) -> int:
    raw = env.get(name, str(default)).strip()
    if not raw.isascii() or not raw.isdecimal():
        raise ValueError(f"{name} must be a decimal integer")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class TranscriptRetention:
    ttl_seconds: int = 3600
    max_entries_per_source: int = 100

    @classmethod
    def from_environment(cls, env: Mapping[str, str] | None = None) -> "TranscriptRetention":
        source = os.environ if env is None else env
        return cls(
            ttl_seconds=_bounded(source, "GAME_NOW_TRANSCRIPT_TTL_SECONDS",
                                 3600, 60, 604800),
            max_entries_per_source=_bounded(
                source, "GAME_NOW_TRANSCRIPT_MAX_ENTRIES", 100, 1, 500),
        )
