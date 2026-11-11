"""GN-060: capture-time monotonic clock and delayed delivery tests."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.logical_clock import (
    ClockObservation, ClockPreviewRequest, ClockState, LogicalMatchClock,
    preview_clock,
)
from test_narration_entities import match

UTC = timezone.utc
T0 = datetime(2026, 11, 11, 12, 0, 0, tzinfo=UTC)


def observation(capture, arrival, seconds, source="radio-1"):
    return ClockObservation(
        source_id=source,
        captured_at=T0 + timedelta(seconds=capture),
        received_at=T0 + timedelta(seconds=arrival),
        reported_match_seconds=seconds,
    )


def test_late_and_fast_delivery_yield_identical_game_clock():
    fast = LogicalMatchClock()
    late = LogicalMatchClock()
    assert fast.observe(observation(0, 1, 600)).accepted
    assert late.observe(observation(0, 60, 600)).accepted
    assert fast.observe(observation(20, 21, 620)).accepted
    assert late.observe(observation(20, 100, 620)).accepted
    assert fast.project(T0 + timedelta(seconds=30)).match_seconds == 630
    assert late.project(T0 + timedelta(seconds=30)).match_seconds == 630
    assert late.project(T0 + timedelta(seconds=30)).source_id == "radio-1"


def test_delayed_old_transcript_cannot_rewind_or_override_new_anchor():
    clock = LogicalMatchClock()
    assert clock.observe(observation(0, 2, 100)).accepted
    assert clock.observe(observation(20, 55, 120)).accepted
    before = clock.state.model_dump(mode="json")
    old = clock.observe(observation(5, 90, 105))
    assert not old.accepted and old.reason == "out_of_order_capture"
    assert clock.state.model_dump(mode="json") == before
    backwards = clock.observe(observation(25, 80, 121))
    assert not backwards.accepted and backwards.reason == "observation_would_rewind"
    assert clock.state.model_dump(mode="json") == before
    assert clock.project(T0 + timedelta(seconds=30)).match_seconds == 130


def test_different_sources_do_not_get_fused_before_gn061():
    clock = LogicalMatchClock()
    clock.observe(observation(0, 0, 300))
    result = clock.observe(observation(15, 50, 500, source="youtube-2"))
    assert not result.accepted and result.reason == "source_alignment_not_implemented"
    assert clock.project(T0 + timedelta(seconds=15)).match_seconds == 315


def test_unanchored_clock_does_not_invent_minute_from_wall_time():
    clock = LogicalMatchClock()
    result = clock.project(T0 + timedelta(hours=10))
    assert result.status == "unanchored"
    assert result.match_seconds is None and result.source_id is None


def test_capture_time_before_anchor_is_clamped_not_rewound():
    clock = LogicalMatchClock()
    clock.observe(observation(20, 50, 620))
    old_time = clock.project(T0)
    assert old_time.match_seconds == 620
    assert old_time.status == "running"


def test_pause_resume_requires_new_explicit_second_half_anchor():
    clock = LogicalMatchClock()
    clock.observe(observation(0, 0, 2690))
    freeze = clock.change_period("half_time", T0 + timedelta(seconds=10))
    assert freeze.accepted
    assert freeze.state.anchor_match_seconds == 2700
    assert clock.project(T0 + timedelta(hours=2)).match_seconds == 2700
    assert not clock.observe(observation(30, 40, 2720)).accepted
    assert not clock.change_period("finished", T0 + timedelta(seconds=40)).accepted
    assert clock.change_period("second_half", T0 + timedelta(seconds=100)).accepted
    assert clock.project(T0 + timedelta(seconds=101)).match_seconds is None
    assert clock.observe(observation(110, 120, 2710)).accepted
    assert clock.project(T0 + timedelta(seconds=120)).match_seconds == 2720
    assert clock.change_period("finished", T0 + timedelta(seconds=130)).accepted
    assert clock.project(T0 + timedelta(hours=5)).match_seconds == 2730


def test_no_anchor_through_break_and_early_end():
    clock = LogicalMatchClock()
    assert clock.change_period("half_time", T0).accepted
    assert clock.project(T0).match_seconds is None
    assert clock.change_period("second_half", T0).accepted
    assert clock.project(T0).match_seconds is None


def test_invalid_period_transitions_do_not_change_clock():
    clock = LogicalMatchClock()
    assert not clock.change_period("finished", T0).accepted
    assert not clock.change_period("first_half", T0).accepted
    assert clock.state.period == "first_half"


@pytest.mark.parametrize("config", [
    {"source_id": "radio-1", "captured_at": T0, "received_at": T0 - timedelta(seconds=1),
     "reported_match_seconds": 50},
    {"source_id": "radio-1", "captured_at": T0.replace(tzinfo=None),
     "received_at": T0, "reported_match_seconds": 50},
    {"source_id": "radio-1", "captured_at": T0, "received_at": T0,
     "reported_match_seconds": -1},
    {"source_id": "radio-1", "captured_at": T0, "received_at": T0,
     "reported_match_seconds": 14401},
])
def test_invalid_observations_rejected(config):
    with pytest.raises((ValidationError, ValueError)):
        ClockObservation(**config)


def test_anchor_state_must_be_complete_and_timezone_aware():
    with pytest.raises(ValidationError):
        ClockState(period="first_half", source_id="radio-1")
    with pytest.raises((ValidationError, ValueError)):
        ClockState(
            period="first_half", source_id="radio-1",
            anchor_captured_at=T0.replace(tzinfo=None), anchor_match_seconds=100,
        )


def test_read_only_preview_and_bounded_observation_set():
    request = ClockPreviewRequest(
        observations=[
            observation(0, 40, 100), observation(20, 60, 120),
            observation(5, 80, 105),
        ],
        project_at_captured_at=T0 + timedelta(seconds=30),
    )
    result = preview_clock("first_half", request)
    assert [s.accepted for s in result.updates] == [True, True, False]
    assert result.projection.match_seconds == 130
    assert result.persisted is False
    with pytest.raises(ValidationError):
        ClockPreviewRequest(observations=[], project_at_captured_at=T0)
    with pytest.raises(ValidationError):
        ClockPreviewRequest(
            observations=[observation(0, 0, 1)] * 41, project_at_captured_at=T0,
        )


def test_preview_api_does_not_persist_clock_or_modify_match(tmp_path):
    from app.main import create_app

    game = match()
    with TestClient(create_app(tmp_path / "clock.sqlite3")) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        data = ClockPreviewRequest(
            observations=[observation(0, 60, 300), observation(20, 100, 320)],
            project_at_captured_at=T0 + timedelta(seconds=25),
        )
        result = client.post("/api/matches/match-051/clock/preview",
                             json=data.model_dump(mode="json"))
        assert result.status_code == 200, result.text
        assert result.json()["projection"]["match_seconds"] == 325
        assert result.json()["persisted"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post("/api/matches/absent/clock/preview",
                           json=data.model_dump(mode="json")).status_code == 404
        assert client.post("/api/matches/match-051/clock/preview",
                           json={"observations": [], "project_at_captured_at": T0.isoformat()}
                           ).status_code == 422
