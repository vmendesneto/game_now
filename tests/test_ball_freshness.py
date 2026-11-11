"""GN-065: silence and source loss never display an old ball location."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ball_freshness import (
    BallFreshnessRequest, preview_ball_freshness,
)
from app.contracts import EventKind, Zone
from app.fusion_conflicts import FusionPlay
from test_narration_entities import match

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def last_play(age=1):
    return FusionPlay(
        source_id="radio-a", segment_id="segment-001",
        aligned_at=T0-timedelta(seconds=age),
        team_id="team-azul", player_id="player-caio",
        zone=Zone(band=4, lane="right"), event_kind=EventKind.PASS,
    )


def preview(age=1, *, source="radio-a", **settings):
    return preview_ball_freshness(BallFreshnessRequest(
        evaluated_at=T0, last_play=last_play(age),
        active_source_id=source, **settings,
    ))


def test_recent_explicit_play_keeps_estimate_but_is_never_persisted():
    result = preview(1)
    assert result.uncertainty == "estimated"
    assert result.display_label == "posição estimada"
    assert result.zone == Zone(band=4, lane="right")
    assert result.team_id == "team-azul"
    assert result.reason == "recent_explicit_play"
    assert not result.persisted and not result.eligible_for_state_update


def test_silence_masks_location_and_player_instead_of_reusing_stale_estimate():
    result = preview(6)
    assert result.uncertainty == "uncertain"
    assert result.reason == "narration_silent"
    assert result.display_label == "posição incerta"
    assert result.zone is None and result.team_id is None and result.player_id is None
    assert result.age_seconds == 6


def test_after_ttl_position_is_expired_without_recovery_by_wall_clock():
    result = preview(16)
    assert result.uncertainty == "expired"
    assert result.reason == "ttl_expired"
    assert result.zone is None
    assert result.expires_at == T0 - timedelta(seconds=1)
    assert result.display_label == "posição incerta"


@pytest.mark.parametrize("age,expected", [
    (0, "estimated"), (5, "estimated"),
    (5.001, "uncertain"), (15, "uncertain"),
    (15.001, "expired"),
])
def test_exact_time_boundaries(age, expected):
    assert preview(age).uncertainty == expected


@pytest.mark.parametrize("source", [None, "youtube-b"])
def test_source_loss_or_transition_immediately_marks_uncertain(source):
    result = preview(1, source=source)
    assert result.uncertainty == "uncertain"
    assert result.reason == "source_unavailable_or_changed"
    assert result.zone is None


def test_expiry_takes_precedence_even_if_source_missing():
    result = preview(99, source=None)
    assert result.uncertainty == "expired"
    assert result.zone is None


def test_without_any_previous_valid_play_region_remains_unknown():
    result = preview_ball_freshness(BallFreshnessRequest(
        evaluated_at=T0, active_source_id="radio-a",
    ))
    assert result.reason == "no_explicit_play"
    assert result.uncertainty == "uncertain"
    assert result.zone is None and result.team_id is None
    assert result.age_seconds is None and result.expires_at is None


def test_new_explicit_play_restores_estimated_region_after_old_one_expired():
    old = preview(40)
    new = preview(0.5)
    assert old.uncertainty == "expired"
    assert new.uncertainty == "estimated"
    assert new.zone is not None


def test_configurable_silence_and_expiry():
    args = {"uncertain_after_seconds": 2, "expire_after_seconds": 8}
    assert preview(1, **args).uncertainty == "estimated"
    assert preview(3, **args).uncertainty == "uncertain"
    assert preview(9, **args).uncertainty == "expired"


def test_expiry_does_not_depend_on_delayed_delivery_or_recent_api_access():
    # The same old capture timestamp cannot become fresh via reevaluation.
    old = last_play(20)
    first = preview_ball_freshness(BallFreshnessRequest(
        evaluated_at=T0, last_play=old, active_source_id="radio-a",
    ))
    second = preview_ball_freshness(BallFreshnessRequest(
        evaluated_at=T0+timedelta(seconds=30),
        last_play=old, active_source_id="radio-a",
    ))
    assert first.uncertainty == "expired"
    assert second.uncertainty == "expired"
    assert second.age_seconds == 50


def test_rejects_future_or_naive_timestamps_and_unbounded_ttl():
    with pytest.raises(ValidationError):
        BallFreshnessRequest(
            evaluated_at=T0, last_play=last_play(-1),
            active_source_id="radio-a",
        )
    with pytest.raises((ValidationError, ValueError)):
        BallFreshnessRequest(evaluated_at=T0.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        BallFreshnessRequest(
            evaluated_at=T0, uncertain_after_seconds=20, expire_after_seconds=20,
        )
    with pytest.raises(ValidationError):
        BallFreshnessRequest(
            evaluated_at=T0, uncertain_after_seconds=0,
        )
    with pytest.raises(ValidationError):
        BallFreshnessRequest(
            evaluated_at=T0, expire_after_seconds=1000,
        )


def test_api_is_preview_only_even_when_old_source_has_expired(tmp_path):
    from app.main import create_app

    game = match()
    payload = BallFreshnessRequest(
        evaluated_at=T0, last_play=last_play(20),
        active_source_id="radio-a",
    ).model_dump(mode="json")
    with TestClient(create_app(tmp_path / "fresh.sqlite3")) as client:
        assert client.post(
            "/api/matches", json=game.model_dump(mode="json", exclude={"players"}),
        ).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        response = client.post("/api/matches/match-051/ball/freshness/preview", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["uncertainty"] == "expired"
        assert response.json()["display_label"] == "posição incerta"
        assert response.json()["zone"] is None
        assert response.json()["persisted"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(
            "/api/matches/absent/ball/freshness/preview", json=payload,
        ).status_code == 404
        assert client.post(
            "/api/matches/match-051/ball/freshness/preview",
            json={"evaluated_at": "not-a-date"},
        ).status_code == 422
