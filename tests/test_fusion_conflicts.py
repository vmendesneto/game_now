"""GN-064: two sources cannot contradict/rewind a proposed ball region."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts import EventKind, Zone
from app.fusion_conflicts import (
    FusionConflictRequest, FusionObservation, FusionPlay, preview_fusion_conflicts,
)
from app.source_selection import SourceSelectionObservation, SourceSelectionRequest, preview_active_source
from test_narration_entities import match

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
CENTER = Zone(band=3, lane="center")
RIGHT = Zone(band=4, lane="right")


def obs(source, *, seconds=-5, team="team-azul", zone=CENTER,
        player="player-caio", kind=EventKind.PASS, live=True, segment=None):
    return FusionObservation(
        source_id=source, segment_id=segment or f"seg-{source}",
        aligned_at=None if seconds is None else T0 + timedelta(seconds=seconds),
        current_live_play=live,
        team_id=team, player_id=player, zone=zone, event_kind=kind,
    )


def prev(*, seconds=-10):
    return FusionPlay(
        source_id="radio-previous", segment_id="seg-prev",
        aligned_at=T0 + timedelta(seconds=seconds),
        team_id="team-azul", player_id="player-caio",
        zone=CENTER, event_kind=EventKind.PASS,
    )


def assess(*rows, active="radio-a", previous=None, **options):
    return preview_fusion_conflicts(FusionConflictRequest(
        evaluated_at=T0, active_source_id=active, observations=list(rows),
        previous_play=previous, **options,
    ))


def test_consistent_sources_propose_only_explicit_evidence_without_persisting():
    result = assess(obs("radio-a"), obs("youtube-b"), previous=prev())
    assert result.accepted_for_preview
    assert result.reason == "consistent_candidate"
    assert result.proposed_play.zone == CENTER
    assert result.proposed_play.team_id == "team-azul"
    assert result.proposed_play.aligned_at == T0 - timedelta(seconds=5)
    assert result.persisted is False and result.eligible_for_state_update is False


@pytest.mark.parametrize("other", [
    {"team": "team-vermelho"},
    {"zone": RIGHT},
    {"player": "player-outro"},
    {"kind": EventKind.SHOT},
])
def test_nearby_contradiction_prevents_any_new_play(other):
    result = assess(obs("radio-a"), obs("youtube-b", **other), previous=prev())
    assert not result.accepted_for_preview
    assert result.reason == "conflicting_source_evidence"
    assert result.conflicting_source_ids == ["youtube-b"]
    assert result.proposed_play is None


def test_multiple_conflicts_report_sorted_source_ids():
    result = assess(
        obs("radio-a"), obs("youtube-z", team="team-vermelho"),
        obs("radio-b", zone=RIGHT),
    )
    assert result.conflicting_source_ids == ["radio-b", "youtube-z"]


def test_late_observation_never_rewinds_an_existing_position():
    result = assess(obs("radio-a", seconds=-11), previous=prev(seconds=-10))
    assert not result.accepted_for_preview
    assert result.reason == "would_rewind_or_repeat"
    assert result.proposed_play is None
    same = assess(obs("radio-a", seconds=-10), previous=prev(seconds=-10))
    assert same.reason == "would_rewind_or_repeat"


def test_newer_explicit_play_can_change_region():
    result = assess(obs("radio-a", zone=RIGHT), previous=prev())
    assert result.accepted_for_preview
    assert result.proposed_play.zone == RIGHT


@pytest.mark.parametrize("missing", [{"team": None}, {"zone": None}])
def test_missing_selected_team_or_zone_never_gets_invented_from_other_source(missing):
    result = assess(obs("radio-a", **missing), obs("youtube-b"))
    assert not result.accepted_for_preview
    assert result.reason == "missing_explicit_team_or_zone"
    assert result.proposed_play is None


def test_unknown_other_source_fields_are_not_invented_as_agreement():
    result = assess(
        obs("radio-a"),
        obs("youtube-b", team=None, zone=None, player=None, kind=None),
    )
    assert result.accepted_for_preview
    assert result.proposed_play.team_id == "team-azul"
    assert result.proposed_play.zone == CENTER


def test_distant_other_event_is_not_mistaken_for_simultaneous_conflict():
    result = assess(
        obs("radio-a", seconds=-2),
        obs("youtube-b", seconds=-9, team="team-vermelho"),
    )
    assert result.accepted_for_preview


def test_unaligned_and_replay_observations_cannot_vote_against_current_play():
    result = assess(
        obs("radio-a"),
        obs("youtube-b", seconds=None, zone=RIGHT),
        obs("radio-c", live=False, zone=RIGHT),
    )
    assert result.accepted_for_preview


def test_selected_source_missing_or_unaligned_is_not_substituted():
    no_active = assess(obs("radio-a"), active=None)
    assert no_active.reason == "no_active_source"
    missing = assess(obs("radio-a"), active="youtube-b")
    assert missing.reason == "no_active_observation"
    unaligned = assess(obs("radio-a", seconds=None))
    assert unaligned.reason == "unaligned_active_observation"
    assert all(item.proposed_play is None for item in [no_active, missing, unaligned])


def test_selected_replay_future_or_non_live_is_rejected():
    assert assess(obs("radio-a", live=False)).reason == "not_live_play"
    assert assess(obs("radio-a", seconds=1)).reason == "future_aligned_timestamp"


def test_input_order_does_not_change_conflict_result():
    rows = [
        obs("radio-a"), obs("youtube-b", zone=RIGHT),
        obs("radio-c", team="team-vermelho"),
    ]
    assert assess(*rows) == assess(*reversed(rows))


def test_safe_handoff_from_gn063_selection_still_blocks_contradiction():
    choice = preview_active_source(SourceSelectionRequest(
        evaluated_at=T0,
        observations=[
            SourceSelectionObservation(
                source_id="radio-a", connection_status="online", narration_kind="live_play",
                captured_at=T0-timedelta(seconds=1),
                received_at=T0, signal_strength=0.9,
            ),
            SourceSelectionObservation(
                source_id="youtube-b", connection_status="online", narration_kind="live_play",
                captured_at=T0-timedelta(seconds=1),
                received_at=T0, signal_strength=0.7,
            ),
        ],
    ))
    assert choice.active_source_id == "radio-a"
    result = assess(
        obs("radio-a"), obs("youtube-b", zone=RIGHT),
        active=choice.active_source_id,
    )
    assert result.reason == "conflicting_source_evidence"
    assert not result.accepted_for_preview


def test_strict_validation_of_source_ids_and_timestamps():
    with pytest.raises(ValidationError):
        FusionConflictRequest(evaluated_at=T0, observations=[
            obs("radio-a"), obs("radio-a", segment="second"),
        ])
    with pytest.raises(ValidationError):
        FusionConflictRequest(evaluated_at=T0, observations=[
            obs("radio-a"), obs("youtube-b", segment="seg-radio-a"),
        ])
    with pytest.raises((ValidationError, ValueError)):
        FusionConflictRequest(evaluated_at=T0.replace(tzinfo=None), observations=[])
    with pytest.raises((ValidationError, ValueError)):
        FusionObservation(
            source_id="radio-a", segment_id="seg-a",
            aligned_at=T0.replace(tzinfo=None),
        )
    with pytest.raises(ValidationError):
        FusionConflictRequest(evaluated_at=T0, observations=[], previous_play=prev(seconds=1))
    with pytest.raises(ValidationError):
        FusionConflictRequest(evaluated_at=T0, observations=[], conflict_window_seconds=30)
    with pytest.raises(ValidationError):
        FusionConflictRequest(
            evaluated_at=T0,
            observations=[obs(f"radio-{i}") for i in range(9)],
        )


def test_preview_api_does_not_modify_match_or_insert_balls(tmp_path):
    from app.main import create_app

    game = match()
    payload = FusionConflictRequest(
        evaluated_at=T0, active_source_id="radio-a",
        observations=[obs("radio-a"), obs("youtube-b", zone=RIGHT)],
        previous_play=prev(),
    ).model_dump(mode="json")
    with TestClient(create_app(tmp_path / "fusion.sqlite3")) as client:
        assert client.post(
            "/api/matches", json=game.model_dump(mode="json", exclude={"players"}),
        ).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        result = client.post("/api/matches/match-051/events/fusion/preview", json=payload)
        assert result.status_code == 200, result.text
        assert result.json()["reason"] == "conflicting_source_evidence"
        assert result.json()["persisted"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(
            "/api/matches/absent/events/fusion/preview", json=payload,
        ).status_code == 404
        assert client.post(
            "/api/matches/match-051/events/fusion/preview",
            json={"evaluated_at": T0.isoformat(), "observations": [
                {"source_id": "radio-a"}
            ]},
        ).status_code == 422
