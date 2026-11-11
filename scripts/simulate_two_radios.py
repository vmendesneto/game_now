"""GN-082: reproducible, synthetic two-radio fusion diagnostics.

The timeline deliberately calls existing *preview* components. Capture times
share an invented UTC clock, and common event IDs are provided explicitly;
this is not stream synchronization, live ASR, or a state-writing orchestrator.
Run: python -m scripts.simulate_two_radios
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from app.ball_freshness import BallFreshnessRequest, preview_ball_freshness
from app.contracts import EventKind, Zone
from app.event_deduplication import (
    EventCandidate, EventDeduplicationRequest, preview_event_deduplication,
)
from app.fusion_conflicts import (
    FusionConflictRequest, FusionObservation, preview_fusion_conflicts,
)
from app.source_delay import (
    RelativeDelayRequest, SourceEventObservation, preview_relative_delays,
)
from app.source_selection import (
    SourceSelectionObservation, SourceSelectionRequest, preview_active_source,
)

_ORIGIN = datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc)
_RADIO_A = "radio-a"
_RADIO_B = "radio-b"
_TEAM_HOME = "team-home"
_PLAYER_HOME = "player-home"
_ZONE = Zone(band=3, lane="left")


def at(seconds: float) -> datetime:
    return _ORIGIN + timedelta(seconds=seconds)


def delay_observation(source_id: str, event_id: str, second: int) -> SourceEventObservation:
    return SourceEventObservation(
        source_id=source_id, common_event_id=event_id,
        captured_at=at(second), received_at=at(second + 1),
    )


def selection_observation(
    source_id: str, second: int, kind: str, strength: float,
) -> SourceSelectionObservation:
    return SourceSelectionObservation(
        source_id=source_id, connection_status="online",
        narration_kind=kind, captured_at=at(second),
        received_at=at(second + 1), signal_strength=strength,
    )


def run_scenario() -> dict:
    """Run the same four explicit phases on every invocation."""
    delay = preview_relative_delays(RelativeDelayRequest(
        reference_source_id=_RADIO_A,
        observations=[
            delay_observation(_RADIO_A, "common-one", 10),
            delay_observation(_RADIO_B, "common-one", 18),
            delay_observation(_RADIO_A, "common-two", 20),
            delay_observation(_RADIO_B, "common-two", 28),
        ],
    ))
    dedup = preview_event_deduplication(EventDeduplicationRequest(
        candidates=[
            EventCandidate(
                segment_id="goal-a", source_id=_RADIO_A, kind=EventKind.GOAL,
                captured_at=at(44), received_at=at(45),
                team_id=_TEAM_HOME, player_id=_PLAYER_HOME,
            ),
            EventCandidate(
                segment_id="goal-b", source_id=_RADIO_B, kind=EventKind.GOAL,
                captured_at=at(52), received_at=at(53),
                team_id=_TEAM_HOME, player_id=_PLAYER_HOME,
            ),
            EventCandidate(
                segment_id="ad-a", source_id=_RADIO_A, kind=EventKind.GOAL,
                captured_at=at(57), received_at=at(58),
                team_id=_TEAM_HOME, player_id=_PLAYER_HOME,
                current_live_play=False,
            ),
        ],
        source_delays=delay.estimates,
    ))

    phases = [
        # The same play is captured eight seconds later on radio B.
        ("aligned_live", 53, (44, "live_play", 0.98), (52, "live_play", 0.65)),
        # A strong commercial on A must lose against live play on B.
        ("commercial_failover", 58, (57, "ad", 0.99), (57, "live_play", 0.90)),
        # B's eight-second delay is removed *before* comparing reports.
        ("contradictory_reports", 71, (62, "live_play", 1.00), (70, "live_play", 0.60)),
        ("both_silent", 95, (62, "unknown", 0.00), (70, "unknown", 0.00)),
    ]
    rows = []
    active = None
    last_play = None
    for name, evaluated_second, a, b in phases:
        selection = preview_active_source(SourceSelectionRequest(
            evaluated_at=at(evaluated_second),
            previous_source_id=active,
            observations=[
                selection_observation(_RADIO_A, *a),
                selection_observation(_RADIO_B, *b),
            ],
        ))
        active = selection.active_source_id

        if name == "aligned_live":
            observations = [
                FusionObservation(
                    source_id=_RADIO_A, segment_id="goal-a",
                    aligned_at=at(44), team_id=_TEAM_HOME,
                    player_id=_PLAYER_HOME, zone=_ZONE, event_kind=EventKind.GOAL,
                ),
                FusionObservation(
                    source_id=_RADIO_B, segment_id="goal-b",
                    aligned_at=at(44), team_id=_TEAM_HOME,
                    player_id=_PLAYER_HOME, zone=_ZONE, event_kind=EventKind.GOAL,
                ),
            ]
        elif name == "commercial_failover":
            observations = [
                FusionObservation(
                    source_id=_RADIO_A, segment_id="ad-a",
                    current_live_play=False, aligned_at=at(57),
                ),
                FusionObservation(
                    source_id=_RADIO_B, segment_id="live-b",
                    aligned_at=at(49), team_id=_TEAM_HOME, zone=None,
                ),
            ]
        elif name == "contradictory_reports":
            observations = [
                FusionObservation(
                    source_id=_RADIO_A, segment_id="dispute-a",
                    aligned_at=at(62), team_id=_TEAM_HOME,
                    player_id=_PLAYER_HOME, zone=_ZONE, event_kind=EventKind.SHOT,
                ),
                FusionObservation(
                    source_id=_RADIO_B, segment_id="dispute-b",
                    aligned_at=at(62), team_id="team-away",
                    zone=Zone(band=3, lane="right"), event_kind=EventKind.SHOT,
                ),
            ]
        else:
            observations = []

        fusion = preview_fusion_conflicts(FusionConflictRequest(
            evaluated_at=at(evaluated_second), active_source_id=active,
            observations=observations, previous_play=last_play,
        ))
        # This is a local hypothesis for the next preview only. Never a
        # database write or permission to move the public-facing ball.
        if fusion.accepted_for_preview:
            last_play = fusion.proposed_play
        ball = preview_ball_freshness(BallFreshnessRequest(
            evaluated_at=at(evaluated_second),
            last_play=last_play, active_source_id=active,
            uncertain_after_seconds=10, expire_after_seconds=20,
        ))
        rows.append({
            "phase": name,
            "evaluated_at": at(evaluated_second).isoformat(),
            "selection": selection.model_dump(mode="json"),
            "fusion": fusion.model_dump(mode="json"),
            "ball": ball.model_dump(mode="json"),
        })
    return {
        "mode": "synthetic_two_radio_diagnostics",
        "scenario_version": 1,
        "clock_domain": "fixed_simulated_utc_capture_times",
        "source_ids": [_RADIO_A, _RADIO_B],
        "delay": delay.model_dump(mode="json"),
        "deduplication": dedup.model_dump(mode="json"),
        "timeline": rows,
        "persisted": False,
        "real_audio_tested": False,
    }


if __name__ == "__main__":
    print(json.dumps(run_scenario(), ensure_ascii=False, sort_keys=True, indent=2))
