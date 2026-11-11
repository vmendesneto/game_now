"""GN-063: deterministic transitions between synthetic radio/YouTube sources."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.source_selection import (
    SourceSelectionObservation, SourceSelectionRequest, preview_active_source,
)
from test_narration_entities import match

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def source(source_id, age=1, *, kind="live_play", status="online",
           signal=0.8, enabled=True, arrival_age=None):
    return SourceSelectionObservation(
        source_id=source_id, enabled=enabled, connection_status=status,
        narration_kind=kind,
        captured_at=T0 - timedelta(seconds=age),
        received_at=T0 - timedelta(
            seconds=age if arrival_age is None else arrival_age
        ),
        signal_strength=signal,
    )


def select(*items, previous=None, **settings):
    return preview_active_source(SourceSelectionRequest(
        evaluated_at=T0, observations=list(items),
        previous_source_id=previous, **settings,
    ))


def diag(result, source_id):
    return next(row for row in result.diagnostics if row.source_id == source_id)


def test_initial_choice_is_deterministic_and_not_a_state_update():
    a = source("radio-a", signal=0.9)
    b = source("youtube-b", signal=0.75)
    result = select(b, a)
    assert result.active_source_id == "radio-a"
    assert result.transition == "selected"
    assert result.reason == "best_eligible"
    assert result.persisted is False
    assert result.eligible_for_state_update is False
    assert select(a, b) == result


def test_ad_immediately_fails_over_to_other_healthy_source():
    first = select(source("radio-a", signal=0.9), source("youtube-b"))
    assert first.active_source_id == "radio-a"
    second = select(source("radio-a", kind="ad", signal=1.0),
                    source("youtube-b"), previous=first.active_source_id)
    assert second.active_source_id == "youtube-b"
    assert second.transition == "switched"
    assert second.reason == "previous_ineligible"
    assert diag(second, "radio-a").reason == "not_live_play"


def test_previous_source_is_retained_during_small_quality_changes():
    result = select(
        source("radio-a", signal=0.80),
        source("youtube-b", signal=0.88),
        previous="radio-a",
    )
    assert result.active_source_id == "radio-a"
    assert result.transition == "retained"
    assert result.reason == "hysteresis_retained"


def test_large_quality_improvement_switches_to_other_source():
    result = select(
        source("radio-a", signal=0.60),
        source("youtube-b", signal=1.0),
        previous="radio-a",
    )
    assert result.active_source_id == "youtube-b"
    assert result.transition == "switched"
    assert result.reason == "higher_quality"


@pytest.mark.parametrize("status", ["offline", "connecting", "error"])
def test_unhealthy_connection_is_excluded_even_with_perfect_confidence(status):
    result = select(source("radio-a", status=status, signal=1.0),
                    source("youtube-b", signal=0.7), previous="radio-a")
    assert result.active_source_id == "youtube-b"
    assert diag(result, "radio-a").reason == "connection_unhealthy"


@pytest.mark.parametrize("kind", ["ad", "replay", "analysis", "conversation", "unknown"])
def test_non_live_narration_never_wins(kind):
    result = select(source("radio-a", kind=kind, signal=1.0),
                    source("youtube-b", signal=0.6))
    assert result.active_source_id == "youtube-b"


def test_stale_capture_not_rescued_by_recent_arrival():
    result = select(
        source("radio-a", age=30, arrival_age=0, signal=1.0),
        source("youtube-b", age=2, signal=0.6),
        previous="radio-a",
    )
    assert result.active_source_id == "youtube-b"
    assert diag(result, "radio-a").reason == "stale_capture"


def test_enabled_flag_and_signal_threshold_exclude_candidate():
    result = select(
        source("radio-a", signal=1.0, enabled=False),
        source("youtube-b", signal=0.3),
    )
    assert result.active_source_id is None
    assert result.transition == "none"
    assert diag(result, "radio-a").reason == "disabled"
    assert diag(result, "youtube-b").reason == "low_signal_strength"


def test_silence_or_all_unhealthy_loses_active_source_without_inventing_state():
    result = select(
        source("radio-a", age=13),
        source("youtube-b", kind="ad"),
        previous="radio-a",
    )
    assert result.active_source_id is None
    assert result.transition == "lost"
    assert result.reason == "no_eligible_sources"
    assert result.eligible_for_state_update is False
    empty = select(previous="radio-a")
    assert empty.active_source_id is None and empty.transition == "lost"


def test_recent_capture_and_quality_both_affect_ranking():
    # 0.8*confidence + 0.2*freshness, not receipt timestamp.
    result = select(
        source("radio-a", age=11, signal=0.8),
        source("youtube-b", age=1, signal=0.8),
    )
    assert result.active_source_id == "youtube-b"
    assert diag(result, "youtube-b").selection_score > diag(result, "radio-a").selection_score


def test_tie_breaker_is_stable_alphabetical_source_id():
    rows = [source("youtube-b"), source("radio-a")]
    assert select(*rows).active_source_id == "radio-a"


def test_future_capture_or_receipt_is_rejected_as_ineligible():
    capture = source("radio-a", age=-1)
    receipt = source("youtube-b", age=2, arrival_age=-1)
    result = select(capture, receipt)
    assert result.active_source_id is None
    assert all(x.reason == "future_timestamp" for x in result.diagnostics)


def test_pydantic_rejects_duplicates_naive_timestamps_and_invalid_ranges():
    with pytest.raises(ValidationError):
        SourceSelectionRequest(
            evaluated_at=T0, observations=[source("radio-a"), source("radio-a")],
        )
    with pytest.raises((ValidationError, ValueError)):
        SourceSelectionRequest(evaluated_at=T0.replace(tzinfo=None), observations=[])
    with pytest.raises((ValidationError, ValueError)):
        SourceSelectionObservation(
            source_id="radio-a", connection_status="online",
            narration_kind="live_play",
            captured_at=T0.replace(tzinfo=None), received_at=T0,
        )
    with pytest.raises((ValidationError, ValueError)):
        source("radio-a", age=1, arrival_age=2)
    with pytest.raises(ValidationError):
        SourceSelectionRequest(evaluated_at=T0, observations=[], switch_margin=-0.1)
    with pytest.raises(ValidationError):
        SourceSelectionRequest(evaluated_at=T0, observations=[], max_age_seconds=0)
    with pytest.raises(ValidationError):
        SourceSelectionRequest(
            evaluated_at=T0, observations=[source(f"radio-{i}") for i in range(9)],
        )
    with pytest.raises(ValidationError):
        SourceSelectionRequest(
            evaluated_at=T0, observations=[source("radio-a", signal=2.0)],
        )


def test_api_preview_never_modifies_match_or_persists_selection(tmp_path):
    from app.main import create_app

    game = match()
    payload = SourceSelectionRequest(
        evaluated_at=T0,
        observations=[source("radio-a", kind="ad"), source("youtube-b")],
        previous_source_id="radio-a",
    ).model_dump(mode="json")
    with TestClient(create_app(tmp_path / "active.sqlite3")) as client:
        assert client.post(
            "/api/matches",
            json=game.model_dump(mode="json", exclude={"players"}),
        ).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        response = client.post("/api/matches/match-051/sources/selection/preview", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["active_source_id"] == "youtube-b"
        assert response.json()["eligible_for_state_update"] is False
        assert response.json()["persisted"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(
            "/api/matches/absent/sources/selection/preview", json=payload,
        ).status_code == 404
        assert client.post(
            "/api/matches/match-051/sources/selection/preview",
            json={"evaluated_at": T0.isoformat(), "observations": [
                {"source_id": "radio-a", "kind": "ad"}
            ]},
        ).status_code == 422
