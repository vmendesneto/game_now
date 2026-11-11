"""GN-062: two narrations yield one diagnostic event, never a saved goal."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts import EventKind
from app.event_deduplication import (
    EventCandidate, EventDeduplicationRequest, preview_event_deduplication,
)
from app.source_delay import SourceDelayEstimate
from test_narration_entities import match

T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def candidate(segment, source, kind, captured, *, team="team-azul",
              player=None, received=None, current=True):
    return EventCandidate(
        segment_id=segment, source_id=source, kind=kind,
        captured_at=T0 + timedelta(seconds=captured),
        received_at=T0 + timedelta(seconds=received if received is not None else captured+1),
        team_id=team, player_id=player, current_live_play=current,
    )


def delay(source, status, seconds, common=2):
    return SourceDelayEstimate(
        source_id=source, status=status,
        relative_delay_seconds=seconds, common_events=common,
    )


def request(*events, delays=None, **options):
    return EventDeduplicationRequest(
        candidates=list(events),
        source_delays=delays or [delay("radio-a", "reference", 0),
                                 delay("youtube-b", "aligned", 8)],
        **options,
    )


def test_two_narrations_one_goal_when_valid_delay_is_supplied():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10, player="player-caio"),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18, player="player-caio"),
    ))
    assert result.output_groups == 1
    assert result.input_candidates == 2
    assert result.persisted is False
    event = result.groups[0]
    assert event.merged is True
    assert event.kind == EventKind.GOAL
    assert event.source_ids == ["radio-a", "youtube-b"]
    assert event.segment_ids == ["seg-a", "seg-b"]
    assert event.aligned_at == T0 + timedelta(seconds=10)


def test_delivery_times_do_not_affect_deduplication():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10, received=1000),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18, received=1200),
    ))
    assert result.output_groups == 1


def test_distinct_later_goal_is_not_merged_with_first_goal():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18),
        candidate("seg-c", "radio-a", EventKind.GOAL, 60),
    ))
    assert result.output_groups == 2
    assert result.groups[0].merged
    assert not result.groups[1].merged


def test_same_source_repeated_goal_is_not_collapsed():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10),
        candidate("seg-b", "radio-a", EventKind.GOAL, 11),
    ))
    assert result.output_groups == 2


@pytest.mark.parametrize("event_b", [
    {"kind": EventKind.CORNER},
    {"team": "team-vermelho"},
    {"player": "player-outro"},
])
def test_contradicting_event_kind_team_or_player_stays_separate(event_b):
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10,
                  player="player-caio"),
        candidate("seg-b", "youtube-b", event_b.get("kind", EventKind.GOAL), 18,
                  team=event_b.get("team", "team-azul"),
                  player=event_b.get("player", "player-caio")),
    ))
    assert result.output_groups == 2


def test_no_team_or_ambiguous_pass_without_player_cannot_be_merged():
    no_team = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10, team=None),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18, team=None),
    ))
    assert no_team.output_groups == 2
    pass_unknown = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.PASS, 10),
        candidate("seg-b", "youtube-b", EventKind.PASS, 18),
    ))
    assert pass_unknown.output_groups == 2


def test_pass_with_same_explicit_player_can_be_deduplicated():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.PASS, 10, player="player-caio"),
        candidate("seg-b", "youtube-b", EventKind.PASS, 18, player="player-caio"),
    ))
    assert result.output_groups == 1


def test_unaligned_source_remains_separate_instead_of_fusing():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18),
        delays=[delay("radio-a", "reference", 0),
                delay("youtube-b", "inconsistent_observations", None)],
    ))
    assert result.output_groups == 2
    assert all(not group.merged for group in result.groups)


def test_non_live_candidate_does_not_create_event():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10, current=False),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18),
    ))
    assert result.output_groups == 1
    assert result.discarded_non_live == ["seg-a"]
    assert not result.groups[0].merged


def test_nearby_but_beyond_time_window_kept_distinct():
    result = preview_event_deduplication(request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 22),
        maximum_separation_seconds=2,
    ))
    assert result.output_groups == 2


def test_missing_alignment_duplicate_segment_and_invalid_source_data_rejected():
    first = candidate("seg-a", "radio-a", EventKind.GOAL, 10)
    with pytest.raises(ValidationError):
        request(first, first)
    with pytest.raises(ValidationError):
        request(first, delays=[delay("youtube-b", "reference", 0)])
    with pytest.raises(ValidationError):
        request(first, delays=[delay("radio-a", "aligned", None)])
    with pytest.raises(ValidationError):
        request(first, delays=[delay("radio-a", "reference", 5)])


def test_invalid_timestamps_or_size_constraints():
    with pytest.raises((ValidationError, ValueError)):
        candidate("seg-a", "radio-a", EventKind.GOAL, 10, received=9)
    with pytest.raises(ValidationError):
        request(*(candidate(f"seg-{i}", "radio-a", EventKind.GOAL, i)
                  for i in range(81)))


def test_preview_api_does_not_persist_canonical_event_or_score(tmp_path):
    from app.main import create_app

    game = match()
    data = request(
        candidate("seg-a", "radio-a", EventKind.GOAL, 10),
        candidate("seg-b", "youtube-b", EventKind.GOAL, 18),
    ).model_dump(mode="json")
    with TestClient(create_app(tmp_path / "events.sqlite3")) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        response = client.post(
            "/api/matches/match-051/events/deduplicate/preview", json=data,
        )
        assert response.status_code == 200, response.text
        assert response.json()["output_groups"] == 1
        assert response.json()["persisted"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post("/api/matches/unknown/events/deduplicate/preview",
                           json=data).status_code == 404
        assert client.post("/api/matches/match-051/events/deduplicate/preview",
                           json={"candidates": [], "source_delays": []}
                           ).status_code == 422
