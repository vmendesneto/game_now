"""GN-053: conservative text evidence for one of 15 oriented football zones.

Band 1 is the defending goal end, band 5 the attacking goal end.
Lane left/right is relative to the chosen team's attack, not camera view.
No audio, coordinates, stored ball state or inferred location is produced.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import Field

from app.contracts import Id, Match, StrictModel, Zone
from app.narration_entities import NarrationResolveRequest, resolve_narration


class RegionRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2048)
    team_id: Id | None = None  # Optional explicit caller context, not persistent possession.


class RegionEvidence(StrictModel):
    status: Literal["explicit", "unknown"]
    zone: Zone | None = None
    team_id: Id | None = None
    attack_direction: Literal["left_to_right", "right_to_left"] | None = None
    field_band: int | None = Field(default=None, ge=1, le=5)
    field_lane: Literal["left", "center", "right"] | None = None
    band_cue: str | None = None
    lane_cue: str | None = None
    team_evidence: Literal["text", "caller_context"] | None = None
    reason: str


# Each horizontal band requires a distinctive longitudinal location. Terms
# like "ataque", "defesa", "area", "campo adversario" alone span multiple bands.
_BANDS: dict[int, tuple[str, ...]] = {
    1: (
        r"\b(?:na|dentro da) (?:propria|nossa) (?:grande |pequena )?area\b",
        r"\bna area defensiva\b",
    ),
    2: (r"\b(?:na|pela) intermediaria defensiva\b",),
    3: (
        r"\b(?:no|pelo) meio(?:-| )campo\b",
        r"\b(?:no|pelo) circulo central\b",
    ),
    4: (
        r"\b(?:na|pela) intermediaria ofensiva\b",
        r"\bna entrada da area adversaria\b",
    ),
    5: (
        r"\b(?:na|dentro da) (?:grande |pequena )?area adversaria\b",
        r"\b(?:na|junto a) linha de fundo adversaria\b",
    ),
}
_LANES: dict[str, tuple[str, ...]] = {
    "left": (
        r"\bpela esquerda\b", r"\bno corredor esquerdo\b",
        r"\bna faixa esquerda\b", r"\bpela ponta esquerda\b",
        r"\bpelo lado esquerdo\b",
    ),
    "center": (
        r"\bpelo meio\b", r"\bpelo centro\b",
        r"\bno corredor central\b", r"\bna faixa central\b",
    ),
    "right": (
        r"\bpela direita\b", r"\bno corredor direito\b",
        r"\bna faixa direita\b", r"\bpela ponta direita\b",
        r"\bpelo lado direito\b",
    ),
}


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _cues(text: str, rules: dict) -> list[tuple[object, str]]:
    return [(value, found.group(0)) for value, patterns in rules.items()
            for pattern in patterns for found in re.finditer(pattern, text)]


def detect_region(match: Match, request: RegionRequest) -> RegionEvidence:
    """Return a zone only when current play, team, band AND lane are unambiguous.

    Direction comes from the current persisted Match (GN-024 swaps directions
    during second_half), so the caller must not invert it again.
    """
    teams = {match.home.id: match.home, match.away.id: match.away}
    if request.team_id is not None and request.team_id not in teams:
        raise ValueError("Unknown team")
    if match.period not in ("first_half", "second_half"):
        return RegionEvidence(status="unknown", reason="not_playing")

    resolution = resolve_narration(match, NarrationResolveRequest(text=request.text))
    if not resolution.eligible_for_live_state:
        return RegionEvidence(status="unknown", reason="not_current_live_play")

    mentions = [m for m in resolution.mentions if m.kind in ("team", "player", "unknown")]
    if any(m.status != "resolved" for m in mentions):
        return RegionEvidence(status="unknown", reason="ambiguous_entity")
    explicit_teams = {m.team_id for m in mentions if m.team_id is not None}
    if len(explicit_teams) > 1:
        return RegionEvidence(status="unknown", reason="conflicting_teams")
    if request.team_id is not None and explicit_teams and request.team_id not in explicit_teams:
        return RegionEvidence(status="unknown", reason="conflicting_team_context")
    if explicit_teams:
        team_id = next(iter(explicit_teams))
        team_evidence = "text"
    elif request.team_id is not None:
        team_id = request.team_id
        team_evidence = "caller_context"
    else:
        return RegionEvidence(status="unknown", reason="no_explicit_team")

    normalized = _fold(request.text)
    band_cues = _cues(normalized, _BANDS)
    lane_cues = _cues(normalized, _LANES)
    if not band_cues:
        return RegionEvidence(status="unknown", team_id=team_id, reason="no_explicit_band")
    if len({band for band, _ in band_cues}) != 1:
        return RegionEvidence(status="unknown", team_id=team_id, reason="conflicting_bands")
    if not lane_cues:
        return RegionEvidence(status="unknown", team_id=team_id, reason="no_explicit_lane")
    if len({lane for lane, _ in lane_cues}) != 1:
        return RegionEvidence(status="unknown", team_id=team_id, reason="conflicting_lanes")

    band, band_cue = band_cues[0]
    lane, lane_cue = lane_cues[0]
    direction = teams[team_id].attack_direction
    # Absolute screen orientation assumes home LTR axis: screen left -> right.
    # A team attacking RTL sees both the longitudinal and lateral axes inverted.
    field_band = band if direction == "left_to_right" else 6 - band
    field_lane = lane if direction == "left_to_right" else {
        "left": "right", "right": "left", "center": "center",
    }[lane]
    return RegionEvidence(
        status="explicit", team_id=team_id, team_evidence=team_evidence,
        attack_direction=direction, zone=Zone(band=band, lane=lane),
        field_band=field_band, field_lane=field_lane,
        band_cue=band_cue, lane_cue=lane_cue,
        reason="unique_live_team_band_and_lane",
    )
