"""A corridor cited in current narration, never a ball-state replacement.

Missing longitudinal location remains missing. A corridor covers all five bands;
no point, possession, actor or complete 5x3 zone is manufactured from it.
"""
from __future__ import annotations

import re
import unicodedata

from app.contracts import Match
from app.match_start_detection import current_play_cue
from app.narration_entities import NarrationResolveRequest, resolve_narration

_CORRIDORS = re.compile(
    r"\b(?:(?:lado|corredor|setor) (?P<side>esquerd[ao]|direit[ao])|"
    r"ponta (?P<wing>esquerd[ao]|direit[ao])|faixa (?P<band>esquerd[ao]|direit[ao]|central)|"
    r"corredor (?P<center>central)|pela (?P<bare>esquerda|direita))\b", re.IGNORECASE
)


def spatial_mention(match: Match, text: str) -> dict:
    """Quote the last explicit corridor of a current-play window, not its ball.

    Center is orientation-invariant. Left/right require one locally resolved
    team before mapping attack-relative language onto the configured pitch.
    Ads, replay, analysis, denied/future/historical narration remain vetoed.
    """
    if match.period not in ("first_half", "second_half"):
        return {"status": "unknown", "reason": "not_playing"}
    if not isinstance(text, str) or not text.strip() or len(text) > 2048:
        return {"status": "unknown", "reason": "invalid_text"}
    # Retain original character positions for the entity resolver.
    folded = "".join(char for char in unicodedata.normalize("NFKD", text)
                     if not unicodedata.combining(char))
    if not current_play_cue(text):
        return {"status": "unknown", "reason": "not_current_play"}
    cues = list(_CORRIDORS.finditer(folded))
    if not cues:
        return {"status": "unknown", "reason": "no_explicit_corridor"}
    cue = cues[-1]
    word = next(value for value in cue.groupdict().values() if value is not None).casefold()
    lane = "center" if word == "central" else "left" if word.startswith("esquerd") else "right"
    # Deaccenting can change string length. Use normalized text consistently
    # for BOTH mention resolution and the corresponding context indices.
    context = folded[max(0, cue.start() - 100):cue.end()]
    resolution = resolve_narration(match, NarrationResolveRequest(text=context))
    relevant = [m for m in resolution.mentions if m.kind in ("player", "team", "unknown", "pronoun")]
    teams = {m.team_id for m in relevant if m.status == "resolved" and m.team_id is not None}
    ambiguous = any(m.status != "resolved" for m in relevant)
    team_id = next(iter(teams)) if len(teams) == 1 and not ambiguous else None
    direction = next((team.attack_direction for team in (match.home, match.away)
                      if team.id == team_id), None)
    if lane != "center" and direction is None:
        return {"status": "unknown", "reason": "corridor_direction_unknown", "lane": lane}
    return {
        "status": "partial", "lane": lane, "team_id": team_id,
        "attack_direction": direction,  # None remains unknown; center is orientation-invariant.
        "band": None, "possession_confirmed": False,
        "basis": "last_corridor_mentioned_not_ball_position",
        "reason": "longitudinal_band_not_determined",
    }
