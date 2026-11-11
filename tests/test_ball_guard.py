"""GN-056: ball movement must fail closed and never mutate the saved state."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.ball_guard import BallGuardRequest, guard_ball_movement
from app.contracts import Confidences, EstimatedBallState, Zone
from test_narration_entities import match

UTC = timezone.utc
GOOD = "Azul com a bola na própria área pela esquerda"


def ball():
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    return EstimatedBallState(
        last_event_id="old-event-1", team_id="team-vermelho",
        player_id="ver-9", zone=Zone(band=3, lane="center"),
        confidences=Confidences(team=0.8, player=0.6, zone=0.9),
        uncertainty="estimated", updated_at=now,
        expires_at=now + timedelta(seconds=10),
    )


def decide(text, *, age=1.0, previous=None, game=None):
    return guard_ball_movement(
        game or match(), previous or ball(),
        BallGuardRequest(text=text, observed_age_seconds=age),
    )


def test_unique_live_team_possession_and_full_zone_is_only_a_candidate():
    previous = ball()
    copy = previous.model_dump(mode="json")
    result = decide(GOOD, previous=previous)
    assert result.decision == "candidate"
    assert result.reason == "unique_current_possession_team_and_zone"
    assert result.candidate_zone == Zone(band=1, lane="left")
    assert result.team_id == "team-azul" and result.player_id is None
    assert result.field_band == 1 and result.field_lane == "left"
    assert result.freshness_basis == "caller_reported_unverified"
    assert result.current_ball.model_dump(mode="json") == copy
    assert previous.model_dump(mode="json") == copy  # pure decision, no write


@pytest.mark.parametrize(("text", "expected"), [
    ("A bola está por aqui", "not_current_live_play"),
    ("Azul está atacando pela direita", "not_current_live_play"),
    ("Azul com a bola no campo de ataque pela direita", "region_no_explicit_band"),
    ("Azul com a bola na própria área", "region_no_explicit_lane"),
    ("Azul com a bola na própria área pela esquerda e pela direita", "region_conflicting_lanes"),
    ("Azul com a bola no meio-campo pela esquerda e na área adversária", "region_conflicting_bands"),
    ("Azul chuta na própria área pela esquerda", "possession_no_unique_possession_cue"),
    ("João Silva com a bola na própria área pela esquerda", "possession_no_unique_entity_near_cue"),
    ("No replay, Azul com a bola na própria área pela esquerda", "not_current_live_play"),
    ("Oferecimento da loja: Azul com a bola na própria área pela esquerda", "not_current_live_play"),
    ("Na minha opinião, Azul com a bola na própria área pela esquerda", "not_current_live_play"),
    ("Meu amigo, Azul com a bola na própria área pela esquerda", "not_current_live_play"),
    ("Azul com a bola na própria área pela esquerda e Vermelho recebe a bola", "possession_no_unique_possession_cue"),
    ("Azul com a bola na própria área pela esquerda; Vermelho corre", "region_conflicting_teams"),
    ("Azul não está com a bola na própria área pela esquerda", "negated_or_speculative"),
    ("Azul quase com a bola na própria área pela esquerda", "negated_or_speculative"),
    ("Azul talvez com a bola na própria área pela esquerda", "negated_or_speculative"),
    ("Azul poderia estar com a bola na própria área pela esquerda", "negated_or_speculative"),
])
def test_vague_non_live_conflicting_and_speculative_text_holds_exact_ball(text, expected):
    previous = ball()
    before = previous.model_dump(mode="json")
    result = decide(text, previous=previous)
    assert result.decision == "hold", (text, result)
    assert result.reason == expected
    assert result.candidate_zone is None and result.team_id is None
    assert result.field_band is None and result.field_lane is None
    assert result.current_ball.model_dump(mode="json") == before
    assert previous.model_dump(mode="json") == before


@pytest.mark.parametrize(("age", "reason"), [
    (None, "age_not_provided"),
    (5.001, "not_recent_by_caller_age"),
    (15, "not_recent_by_caller_age"),
    (30, "not_recent_by_caller_age"),
])
def test_unverifiable_or_stale_age_never_proposes_move(age, reason):
    outcome = decide(GOOD, age=age)
    assert outcome.decision == "hold" and outcome.reason == reason
    assert outcome.candidate_zone is None


def test_recent_boundary_is_inclusive_only_through_five_seconds():
    assert decide(GOOD, age=0).decision == "candidate"
    assert decide(GOOD, age=5).decision == "candidate"
    assert decide(GOOD, age=5.001).decision == "hold"


def test_same_team_and_zone_do_not_generate_a_new_move():
    previous = ball().model_copy(update={
        "team_id": "team-azul", "zone": Zone(band=1, lane="left"),
    })
    result = decide(GOOD, previous=previous)
    assert result.decision == "hold"
    assert result.reason == "already_in_reported_zone"
    assert result.current_ball == previous


def test_period_and_direction_follow_current_match_without_guessing():
    for period in ("half_time", "finished"):
        game = match().model_copy(update={"period": period})
        assert decide(GOOD, game=game).reason == "not_playing"
    game = match()
    game.period = "second_half"
    game.home.attack_direction = "right_to_left"
    game.away.attack_direction = "left_to_right"
    result = decide(GOOD, game=game)
    assert result.decision == "candidate"
    assert result.candidate_zone == Zone(band=1, lane="left")
    assert result.field_band == 5 and result.field_lane == "right"


def test_event_score_cannot_replace_missing_ball_or_zone_evidence():
    assert decide("Azul marcou o gol na área adversária pela direita").decision == "hold"
    assert decide("Azul com a bola pela direita, chuta").decision == "hold"


def test_invalid_input_is_rejected():
    for payload in (
        {"text": ""}, {"text": "a" * 2049},
        {"text": GOOD, "observed_age_seconds": -1},
        {"text": GOOD, "observed_age_seconds": 86401},
    ):
        with pytest.raises(ValidationError):
            BallGuardRequest(**payload)


def test_http_sqlite_integration_never_writes_a_candidate_or_rejection(tmp_path):
    from app.main import create_app

    game = match()
    path = tmp_path / "game.sqlite3"
    endpoint = "/api/matches/match-051/guard-ball"
    with TestClient(create_app(path)) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        assert client.put("/api/matches/match-051/players", json=[
            {**p.model_dump(mode="json"), "position": "forward"}
            for p in game.players
        ]).status_code == 200

        original = client.get("/api/matches/match-051/state").json()
        for text, expected in (
            (GOOD, "candidate"),
            ("No replay, " + GOOD, "hold"),
            ("O jogo está equilibrado", "hold"),
            ("Oferecimento! " + GOOD, "hold"),
        ):
            response = client.post(endpoint, json={
                "text": text, "observed_age_seconds": 2,
            })
            assert response.status_code == 200, response.text
            assert response.json()["decision"] == expected
            assert response.json()["current_ball"] == original["ball"]
            assert client.get("/api/matches/match-051/state").json() == original

        assert client.post(endpoint, json={"text": GOOD}).json()["decision"] == "hold"
        assert client.post(endpoint, json={"text": ""}).status_code == 422
        assert client.post(endpoint, json={"text": "x" * 2049}).status_code == 422
        assert client.post("/api/matches/absent/guard-ball", json={
            "text": GOOD, "observed_age_seconds": 1,
        }).status_code == 404

    with TestClient(create_app(path)) as client:
        assert client.get("/api/matches/match-051/state").json() == original
