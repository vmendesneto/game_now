"""GN-055: positive and negative per-component scores, freshness and API."""
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.confidence import ConfidenceRequest, assess_confidence
from test_narration_entities import match


def assess(text, **kwargs):
    return assess_confidence(match(), ConfidenceRequest(text=text, **kwargs))


def test_all_explicit_components_with_recent_evidence():
    result = assess("João do Azul chuta na área adversária pela direita",
                    observed_age_seconds=0)
    assert result.eligible_for_live_state
    assert result.mode == "heuristic_strength_not_calibrated_v1"
    assert result.player_id == "azul-9" and result.team_id == "team-azul"
    assert result.zone.band == 5 and result.zone.lane == "right"
    assert result.event_kind == "shot"
    assert result.scores.model_dump() == {
        "player": 1.0, "team": 1.0, "region": 1.0,
        "event": 1.0, "freshness": 1.0,
    }


def test_missing_clues_do_not_inherit_a_high_score_from_other_components():
    result = assess("Azul com a bola", observed_age_seconds=1)
    assert result.scores.model_dump() == {
        "player": 0.0, "team": 1.0, "region": 0.0,
        "event": 0.0, "freshness": 1.0,
    }
    assert result.zone is None and result.event_kind is None
    assert result.reasons["region"] == "no_explicit_band"


def test_unresolved_player_and_conflicting_team_are_not_scored_as_unique():
    ambiguous = assess("João Silva chuta na própria área pela esquerda",
                       observed_age_seconds=2)
    assert ambiguous.scores.player == 0 and ambiguous.scores.team == 0
    assert ambiguous.scores.region == 0 and ambiguous.scores.event == 1
    assert ambiguous.player_id is None
    conflict = assess("Azul com a bola na própria área pela direita",
                      team_id="team-vermelho")
    assert conflict.team_id is None
    assert conflict.scores.team == 0 and conflict.scores.region == 0


def test_caller_supplied_team_is_half_strength_and_not_possession():
    result = assess("Recebe a bola na intermediária defensiva pelo centro",
                    team_id="team-vermelho")
    assert result.scores.team == 0.5 and result.scores.region == 0.5
    assert result.scores.event == 0 and result.scores.player == 0
    assert result.reasons["team"] == "caller_supplied_team_only"
    assert result.reasons["region"] == "explicit_zone_with_caller_context"


@pytest.mark.parametrize(("age", "expected"), [
    (None, 0.0), (0.0, 1.0), (5.0, 1.0), (17.5, 0.5), (30.0, 0.0), (60.0, 0.0),
])
def test_freshness_is_explicitly_bounded_and_not_calibrated(age, expected):
    result = assess("Azul com a bola na própria área pela esquerda",
                    observed_age_seconds=age)
    assert result.scores.freshness == expected
    assert result.scores.region == 1.0  # linguistic evidence unchanged


@pytest.mark.parametrize("text", [
    "No replay, João do Azul chutou na área adversária pela direita",
    "Oferecimento: Azul marcou o gol",
    "Meu amigo, Azul com a bola",
    "Na minha opinião Azul chutou",
])
def test_non_live_gating_is_zero_even_if_text_is_recent(text):
    result = assess(text, observed_age_seconds=0)
    assert not result.eligible_for_live_state
    assert all(value == 0 for value in result.scores.model_dump().values())
    assert result.zone is None and result.event_kind is None


def test_periods_and_bounds():
    for period in ("half_time", "finished"):
        game = match()
        game.period = period
        result = assess_confidence(game, ConfidenceRequest(
            text="Azul chuta na área adversária pela direita",
            observed_age_seconds=0))
        assert not result.eligible_for_live_state
        assert result.scores.freshness == 0
    with pytest.raises(ValidationError):
        ConfidenceRequest(text="x", observed_age_seconds=-1)
    with pytest.raises(ValidationError):
        ConfidenceRequest(text="x", observed_age_seconds=86401)
    with pytest.raises(ValidationError):
        ConfidenceRequest(text="x" * 2049)
    with pytest.raises(ValueError, match="Unknown team"):
        assess("Azul com a bola", team_id="not-a-team")


def test_api_is_read_only_and_never_persists_scores(tmp_path):
    from app.main import create_app
    game = match()
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        assert client.put("/api/matches/match-051/players", json=[
            {**p.model_dump(mode="json"), "position": "forward"}
            for p in game.players
        ]).status_code == 200
        before = client.get("/api/matches/match-051/state").json()
        endpoint = "/api/matches/match-051/resolve-confidence"
        response = client.post(endpoint, json={
            "text": "João do Azul chutou na área adversária pela direita",
            "observed_age_seconds": 2,
        })
        assert response.status_code == 200, response.text
        assert response.json()["scores"]["player"] == 1.0
        assert response.json()["scores"]["region"] == 1.0
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(endpoint, json={"text": "Azul com a bola",
                                          "team_id": "not-a-team"}).status_code == 422
        assert client.post(endpoint, json={"text": "x" * 2049}).status_code == 422
        assert client.post("/api/matches/absent/resolve-confidence",
                           json={"text": "Azul com a bola"}).status_code == 404
