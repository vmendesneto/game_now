"""GN-061: simulated source-relative delays, contradictions and read-only API."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.source_delay import (
    RelativeDelayRequest, SourceEventObservation, preview_relative_delays,
)
from test_narration_entities import match

T0 = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)


def sample(source, event, captured, received=None):
    if received is None:
        received = captured + 5
    return SourceEventObservation(
        source_id=source,
        common_event_id=event if len(event) >= 3 else f"evt-{event}",
        captured_at=T0 + timedelta(seconds=captured),
        received_at=T0 + timedelta(seconds=received),
    )


def request(*observations, **options):
    return RelativeDelayRequest(
        reference_source_id="radio-a", observations=list(observations), **options,
    )


def indexed(result):
    return {estimate.source_id: estimate for estimate in result.estimates}


def test_two_shared_events_estimate_lag_eight_seconds():
    result = preview_relative_delays(request(
        sample("radio-a", "goal", 10),
        sample("youtube-b", "goal", 18),
        sample("radio-a", "corner", 40),
        sample("youtube-b", "corner", 48),
    ))
    offsets = indexed(result)
    assert offsets["radio-a"].status == "reference"
    assert offsets["radio-a"].relative_delay_seconds == 0
    assert offsets["youtube-b"].status == "aligned"
    assert offsets["youtube-b"].relative_delay_seconds == 8
    assert offsets["youtube-b"].common_events == 2
    assert result.persisted is False


def test_receipt_delay_and_out_of_order_inputs_do_not_change_offset():
    a = [sample("radio-a", "e1", 10, 200),
         sample("radio-a", "e2", 30, 230)]
    b = [sample("youtube-b", "e1", 17, 18),
         sample("youtube-b", "e2", 37, 300)]
    result = preview_relative_delays(request(*(a + b)))
    reversed_result = preview_relative_delays(request(*(b[::-1] + a[::-1])))
    assert indexed(result)["youtube-b"].relative_delay_seconds == 7
    assert indexed(reversed_result)["youtube-b"] == indexed(result)["youtube-b"]


def test_early_source_has_negative_delay_and_three_sources_are_isolated():
    result = preview_relative_delays(request(
        sample("radio-a", "a", 50), sample("radio-a", "b", 100),
        sample("youtube-b", "a", 62), sample("youtube-b", "b", 112),
        sample("radio-c", "a", 47), sample("radio-c", "b", 97),
    ))
    assert indexed(result)["youtube-b"].relative_delay_seconds == 12
    assert indexed(result)["radio-c"].relative_delay_seconds == -3


def test_one_common_event_and_unmatched_event_do_not_estimate():
    result = preview_relative_delays(request(
        sample("radio-a", "goal", 10), sample("radio-a", "corner", 30),
        sample("youtube-b", "goal", 14), sample("youtube-b", "other", 25),
    ))
    estimate = indexed(result)["youtube-b"]
    assert estimate.status == "insufficient_common_events"
    assert estimate.common_events == 1
    assert estimate.relative_delay_seconds is None


def test_conflicting_offsets_are_rejected_not_averaged_into_false_sync():
    result = preview_relative_delays(request(
        sample("radio-a", "a", 10), sample("youtube-b", "a", 18),
        sample("radio-a", "b", 30), sample("youtube-b", "b", 58),
        sample("radio-a", "c", 50), sample("youtube-b", "c", 58),
    ))
    estimate = indexed(result)["youtube-b"]
    assert estimate.status == "inconsistent_observations"
    assert estimate.max_deviation_seconds > 2
    assert estimate.relative_delay_seconds is None


def test_small_timestamp_jitter_is_tolerated():
    result = preview_relative_delays(request(
        sample("radio-a", "a", 10), sample("youtube-b", "a", 18),
        sample("radio-a", "b", 30), sample("youtube-b", "b", 39),
        sample("radio-a", "c", 50), sample("youtube-b", "c", 58),
    ))
    estimate = indexed(result)["youtube-b"]
    assert estimate.status == "aligned"
    assert estimate.relative_delay_seconds == 8
    assert estimate.max_deviation_seconds == 1


def test_out_of_range_offsets_not_used_even_with_consistent_pairing():
    result = preview_relative_delays(request(
        sample("radio-a", "a", 10), sample("youtube-b", "a", 150),
        sample("radio-a", "b", 30), sample("youtube-b", "b", 170),
    ))
    estimate = indexed(result)["youtube-b"]
    assert estimate.status == "out_of_range"
    assert estimate.relative_delay_seconds is None


def test_old_capture_outside_window_is_excluded_regardless_of_arrival():
    result = preview_relative_delays(request(
        sample("radio-a", "old", 0, 2000), sample("youtube-b", "old", 8, 2000),
        sample("radio-a", "recent", 990, 2000),
        sample("youtube-b", "recent", 998, 2000),
        sample("radio-a", "new", 1010, 2000),
        sample("youtube-b", "new", 1018, 2000),
        window_seconds=60,
    ))
    estimate = indexed(result)["youtube-b"]
    assert result.discarded_outside_window == 2
    assert result.observations_in_window == 4
    assert estimate.common_events == 2
    assert estimate.relative_delay_seconds == 8


def test_source_not_present_in_recent_window_has_no_inferred_offset():
    result = preview_relative_delays(request(
        sample("radio-a", "a", 1000),
        sample("radio-a", "b", 1010),
        sample("youtube-b", "old", 0),
        window_seconds=30,
    ))
    estimate = indexed(result)["youtube-b"]
    assert estimate.status == "insufficient_common_events"
    assert estimate.common_events == 0


@pytest.mark.parametrize("values", [
    [sample("radio-a", "e", 10), sample("radio-a", "e", 20)],
    [sample("radio-a", "e", 10), sample("youtube-b", "e", 20)],
])
def test_duplicate_pair_or_unknown_reference_fails_validation(values):
    if values[0].source_id == values[1].source_id:
        with pytest.raises(ValidationError):
            request(*values)
    else:
        with pytest.raises(ValidationError):
            RelativeDelayRequest(reference_source_id="missing", observations=values)


def test_unaware_or_impossible_timestamps_rejected():
    with pytest.raises((ValidationError, ValueError)):
        SourceEventObservation(
            source_id="radio-a", common_event_id="e",
            captured_at=T0.replace(tzinfo=None), received_at=T0,
        )
    with pytest.raises((ValidationError, ValueError)):
        sample("radio-a", "e", 50, 40)


def test_bounded_validation():
    base = sample("radio-a", "start", 0)
    with pytest.raises(ValidationError):
        request(base)
    with pytest.raises(ValidationError):
        request(*(sample("radio-a", f"e{i}", i) for i in range(81)))
    many = request(*(sample("radio-a" if i == 0 else f"radio-{i}", "e", i) for i in range(25)))
    assert len(many.observations) == 25
    with pytest.raises(ValidationError):
        request(base, sample("youtube-b", "start", 1), window_seconds=0)


def test_api_is_read_only_and_match_is_required(tmp_path):
    from app.main import create_app

    game = match()
    observations = [
        sample("radio-a", "e1", 10), sample("youtube-b", "e1", 18),
        sample("radio-a", "e2", 30), sample("youtube-b", "e2", 38),
    ]
    data = request(*observations).model_dump(mode="json")
    with TestClient(create_app(tmp_path / "delay.sqlite3")) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        response = client.post("/api/matches/match-051/sources/delay/preview", json=data)
        assert response.status_code == 200, response.text
        assert response.json()["persisted"] is False
        assert response.json()["estimates"][1]["relative_delay_seconds"] == 8
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post("/api/matches/absent/sources/delay/preview",
                           json=data).status_code == 404
        assert client.post("/api/matches/match-051/sources/delay/preview",
                           json={"reference_source_id": "radio-a",
                                 "observations": []}).status_code == 422
