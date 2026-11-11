"""GN-080: deterministic unit regression matrix for parsing, entities, periods and state.

Original synthetic fixtures only. These checks do not claim radio/Windows coverage
and deliberately do not exercise the API/WebSocket/SQLite integration (GN-081).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import ContractBundle, EventKind, Match, Player
from app.entities import resolve_player
from app.event_detection import EventRequest, detect_event
from app.match_flow import MatchAction, empty_flow, flow_view, on_pitch
from app.narration_classifier import NarrationLabel, classify_narration
from app.narration_entities import NarrationResolveRequest, resolve_narration

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name: str = "live_play.json") -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def example_match() -> Match:
    return Match.model_validate(fixture()["match"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Promoção: gol do Azul, desconto hoje!", NarrationLabel.AD),
        ("No replay, Caio chutou!", NarrationLabel.REPLAY),
        ("Taticamente, o Azul passa a bola.", NarrationLabel.ANALYSIS),
        ("Boa tarde, Caio recebe a bola.", NarrationLabel.CONVERSATION),
        ("Caio recebe a bola!", NarrationLabel.LIVE_PLAY),
        ("Gooooooooool do Azul!", NarrationLabel.LIVE_PLAY),
        ("O goleiro falou de uma goleada.", NarrationLabel.UNKNOWN),
        ("Caiozinho tocou na bola.", NarrationLabel.UNKNOWN),
    ],
)
def test_parser_classification_priority_and_word_boundaries(text, expected):
    decision = classify_narration(text)
    assert decision.label == expected
    assert decision.is_current_play == (expected == NarrationLabel.LIVE_PLAY)


@pytest.mark.parametrize(
    ("text", "kind", "reason"),
    [
        ("Gooooool do Azul!", EventKind.GOAL, "unique_affirmative_live_event_cue"),
        ("O Azul chuta!", EventKind.SHOT, "unique_affirmative_live_event_cue"),
        ("Pênalti para o Azul!", EventKind.PENALTY, "unique_affirmative_live_event_cue"),
        ("O Azul chuta e cruza na área", None, "conflicting_event_cues"),
        ("O Azul chutou, mas o gol foi anulado", None, "negated_or_speculative"),
        ("No replay, Azul chutou!", None, "not_current_live_play"),
        ("Caio recebe a bola", None, "no_explicit_event_cue"),
    ],
)
def test_event_parser_never_infers_ambiguous_or_non_live_events(text, kind, reason):
    result = detect_event(example_match(), EventRequest(text=text))
    assert result.kind == kind
    assert result.reason == reason
    assert result.status == ("explicit" if kind is not None else "unknown")


def test_player_shirt_and_name_ambiguity_stays_within_club():
    game = example_match()
    game.players.append(Player(
        id="player-ver-9", team_id="team-away", name="Caio", number=9,
        aliases=["Caiô"], starter=False,
    ))
    for mention in ("Caio", "camisa 9"):
        result = resolve_player(game, mention)
        assert result.status == "ambiguous"
        assert result.player_id is None and result.team_id is None
        assert result.candidate_ids == ["player-azul-9", "player-ver-9"]
        assert resolve_player(game, mention, "team-home").player_id == "player-azul-9"
        assert resolve_player(game, mention, "team-away").player_id == "player-ver-9"
    assert resolve_player(game, "caiozinho").status == "unknown"

    sentence = resolve_narration(
        game, NarrationResolveRequest(text="Camisa 9 do Azul recebe a bola")
    )
    assert sentence.mentions[0].status == "resolved"
    assert sentence.mentions[0].player_id == "player-azul-9"
    no_club = resolve_narration(
        game, NarrationResolveRequest(text="Caio recebe a bola")
    )
    assert no_club.mentions[0].status == "ambiguous"


def test_pronoun_does_not_cross_sentence_source_or_stale_time():
    game = example_match()
    same_sentence = resolve_narration(
        game, NarrationResolveRequest(text="Caio do Azul recebe a bola, ele chuta")
    )
    assert same_sentence.mentions[-1].kind == "pronoun"
    assert same_sentence.mentions[-1].player_id == "player-azul-9"
    next_sentence = resolve_narration(
        game, NarrationResolveRequest(text="Caio do Azul recebe a bola. Ele chuta")
    )
    assert next_sentence.mentions[-1].status == "unknown"

    first = resolve_narration(game, NarrationResolveRequest(
        text="Caio do Azul recebe a bola", source_id="source-radio-a",
        sequence=1, start_seconds=2, end_seconds=7,
    ))
    assert first.next_context is not None
    for source_id, start_seconds, expected in (
        ("source-radio-a", 15, "resolved"),
        ("source-radio-a", 16, "unknown"),
        ("source-radio-b", 15, "unknown"),
    ):
        next_result = resolve_narration(game, NarrationResolveRequest(
            text="Ele chuta", source_id=source_id, sequence=2,
            start_seconds=start_seconds, end_seconds=start_seconds + 2,
            previous=first.next_context,
        ))
        assert next_result.mentions[0].status == expected
        if expected == "resolved":
            assert next_result.mentions[0].player_id == "player-azul-9"
        assert next_result.next_context is None


@pytest.mark.parametrize("period", ["first_half", "half_time", "second_half", "finished"])
def test_valid_match_periods_roundtrip_without_inventing_time(period):
    data = fixture()["match"]
    data["period"] = period
    game = Match.model_validate(data)
    again = Match.model_validate(game.model_dump(mode="json"))
    assert again.period == period
    assert again.match_seconds == 732
    assert (again.home.attack_direction, again.away.attack_direction) == (
        "left_to_right", "right_to_left"
    )


@pytest.mark.parametrize(
    "action",
    [
        {"kind": "substitution", "player_out_id": "player-azul-9"},
        {"kind": "substitution", "player_out_id": "player-azul-9",
         "player_in_id": "player-azul-9"},
        {"kind": "red_card"},
        {"kind": "red_card", "player_id": "player-azul-9", "seconds": 10},
        {"kind": "half_time", "seconds": 0},
        {"kind": "second_half", "player_id": "player-azul-9"},
        {"kind": "finish", "seconds": 0},
        {"kind": "added_time"},
        {"kind": "added_time", "seconds": -1},
        {"kind": "added_time", "seconds": 3601},
        {"kind": "finish", "match_seconds": -1},
        {"kind": "third_half"},
    ],
)
def test_action_parser_rejects_bad_fields_and_out_of_range_values(action):
    with pytest.raises(ValidationError):
        MatchAction.model_validate(action)


def test_flow_view_counts_substitutions_and_expulsion_without_mutating_match():
    game = example_match()
    game.players.append(Player(
        id="player-azul-12", team_id="team-home", name="Reserva", number=12,
        starter=False,
    ))
    before = game.model_dump(mode="json")
    flow = empty_flow()
    assert on_pitch(game, flow) == {"player-azul-9", "player-ver-1"}
    flow["substitutions"].append({
        "out": "player-azul-9", "in": "player-azul-12",
        "team_id": "team-home", "period": "first_half",
    })
    flow["sent_off_ids"].append("player-ver-1")
    view = flow_view(game, flow)
    assert view["active_player_ids"] == ["player-azul-12"]
    assert view["period"] == "first_half"
    assert view["match_seconds"] == 732
    assert game.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("schema_version",), "2.0.0"),
        (("match", "period"), "third_half"),
        (("match", "match_seconds"), -1),
        (("match", "home_score"), -1),
        (("match", "home", "attack_direction"), "right_to_left"),
        (("match", "home", "color"), "blue"),
        (("events", 0, "zone", "band"), 6),
        (("events", 0, "zone", "lane"), "middle"),
        (("events", 0, "confidences", "team"), 1.01),
        (("ball", "confidences", "zone"), -0.01),
        (("ball", "expires_at"), "2026-11-10T18:31:00+00:00"),
        (("ball", "updated_at"), "2026-11-10T18:32:02"),
        (("events", 0, "observed_at"), "2026-11-10T18:32:02"),
        (("segments", 0, "transcribed_at"), "2026-11-10T18:31:59+00:00"),
        (("events", 0, "team_id"), "team-unknown"),
        (("events", 0, "player_id"), "player-unknown"),
        (("ball", "last_event_id"), "event-unknown"),
        (("ball", "player_id"), "player-unknown"),
    ],
)
def test_contract_rejects_invalid_nested_state(path, bad_value):
    data = fixture()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = bad_value
    with pytest.raises(ValidationError):
        ContractBundle.model_validate(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_player_id",
        "foreign_player_team",
        "duplicate_source",
        "duplicate_segment",
        "duplicate_event",
        "orphan_segment_source",
        "orphan_event_segment",
        "orphan_event_source",
        "duplicate_event_sources",
        "duplicate_event_segments",
        "event_team_player_disagree",
        "ball_team_player_disagree",
        "unexpected_root_field",
    ],
)
def test_bundle_rejects_dangling_conflicting_or_duplicate_references(mutation):
    data = fixture()
    if mutation == "duplicate_player_id":
        data["match"]["players"][1]["id"] = data["match"]["players"][0]["id"]
    elif mutation == "foreign_player_team":
        data["match"]["players"][0]["team_id"] = "team-unknown"
    elif mutation == "duplicate_source":
        data["sources"].append(copy.deepcopy(data["sources"][0]))
    elif mutation == "duplicate_segment":
        data["segments"].append(copy.deepcopy(data["segments"][0]))
    elif mutation == "duplicate_event":
        data["events"].append(copy.deepcopy(data["events"][0]))
    elif mutation == "orphan_segment_source":
        data["segments"][0]["source_id"] = "source-unknown"
    elif mutation == "orphan_event_segment":
        data["events"][0]["segment_ids"] = ["seg-unknown"]
    elif mutation == "orphan_event_source":
        data["events"][0]["source_ids"] = ["source-unknown"]
    elif mutation == "duplicate_event_sources":
        data["events"][0]["source_ids"].append("source-radio-a")
    elif mutation == "duplicate_event_segments":
        data["events"][0]["segment_ids"].append("seg-shot-a")
    elif mutation == "event_team_player_disagree":
        data["events"][0]["team_id"] = "team-away"
    elif mutation == "ball_team_player_disagree":
        data["ball"]["team_id"] = "team-away"
    elif mutation == "unexpected_root_field":
        data["stream_secret"] = "must be forbidden"
    with pytest.raises(ValidationError):
        ContractBundle.model_validate(data)


def test_multiple_sources_must_match_their_own_event_segments():
    data = fixture("two_sources_delayed.json")
    assert ContractBundle.model_validate(data).events[0].source_ids == [
        "source-radio-a", "source-youtube-b"
    ]
    data["events"][0]["source_ids"] = ["source-radio-a"]
    with pytest.raises(ValidationError, match="disagree"):
        ContractBundle.model_validate(data)


def test_valid_unknown_ball_state_remains_explicit_after_serialization():
    data = fixture()
    data["ball"].update(
        last_event_id=None, team_id=None, player_id=None, zone=None,
        uncertainty="expired", expires_at=None,
    )
    data["events"] = []
    snapshot = ContractBundle.model_validate(data)
    reloaded = ContractBundle.model_validate(snapshot.model_dump(mode="json"))
    assert reloaded.ball.uncertainty == "expired"
    assert reloaded.ball.zone is None and reloaded.ball.player_id is None
    assert reloaded.events == []
