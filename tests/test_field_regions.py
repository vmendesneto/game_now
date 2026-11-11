"""GN-053: all 15 zones, attack reversal, negative evidence and read-only API."""
import pytest
from fastapi.testclient import TestClient

from app.field_regions import RegionRequest, detect_region
from test_narration_entities import match


BANDS = [
    "na própria área", "na intermediária defensiva",
    "no meio-campo", "na intermediária ofensiva", "na área adversária",
]
LANES = ["pela esquerda", "pelo meio", "pela direita"]
LANE_NAMES = ["left", "center", "right"]


@pytest.mark.parametrize(("band", "phrase"), list(enumerate(BANDS, start=1)))
@pytest.mark.parametrize(("lane", "lane_phrase"), list(zip(LANE_NAMES, LANES)))
@pytest.mark.parametrize(("team_name", "team_id", "direction"), [
    ("Azul", "team-azul", "left_to_right"),
    ("Vermelho", "team-vermelho", "right_to_left"),
])
def test_all_15_zones_in_both_directions(band, phrase, lane, lane_phrase,
                                         team_name, team_id, direction):
    text = f"{team_name} com a bola {phrase} {lane_phrase}"
    result = detect_region(match(), RegionRequest(text=text))
    assert result.status == "explicit", (text, result)
    assert (result.zone.band, result.zone.lane) == (band, lane)
    assert result.team_id == team_id and result.attack_direction == direction
    assert result.team_evidence == "text"
    assert result.field_band == (band if direction == "left_to_right" else 6 - band)
    assert result.field_lane == (lane if direction == "left_to_right" else
                                 {"left": "right", "right": "left", "center": "center"}[lane])
    assert result.band_cue and result.lane_cue


def test_second_half_uses_persisted_direction_after_side_swap():
    game = match()
    game.home.attack_direction = "right_to_left"
    game.away.attack_direction = "left_to_right"
    game.period = "second_half"
    result = detect_region(game, RegionRequest(
        text="Azul recebe a bola na própria área pela esquerda"))
    assert result.status == "explicit"
    assert result.zone.band == 1 and result.zone.lane == "left"
    assert result.field_band == 5 and result.field_lane == "right"


@pytest.mark.parametrize(("text", "reason"), [
    ("Azul com a bola no campo de ataque pela direita", "no_explicit_band"),
    ("Azul com a bola na intermediária ofensiva", "no_explicit_lane"),
    ("Azul com a bola pela direita", "no_explicit_band"),
    ("Azul com a bola na área pela direita", "no_explicit_band"),
    ("Azul com a bola no meio-campo pelo meio na área adversária", "conflicting_bands"),
    ("Azul com a bola no meio-campo pela esquerda e pela direita", "conflicting_lanes"),
    ("Azul com a bola na intermediária defensiva pela direita; "
     "Vermelho recebe a bola", "conflicting_teams"),
    ("João Silva com a bola na própria área pela direita", "ambiguous_entity"),
    ("Azul na área adversária pela esquerda", "not_current_live_play"),
    ("No replay, Azul recebe a bola na própria área pela esquerda",
     "not_current_live_play"),
    ("Oferecimento: Azul com a bola na própria área pela esquerda",
     "not_current_live_play"),
    ("O treinador deveria ter o Azul com a bola na própria área pela esquerda",
     "not_current_live_play"),
])
def test_missing_ambiguous_and_non_live_evidence(text, reason):
    result = detect_region(match(), RegionRequest(text=text))
    assert result.status == "unknown" and result.reason == reason
    assert result.zone is None and result.field_band is None and result.field_lane is None


def test_explicit_caller_context_and_conflict_do_not_assume_possession():
    game = match()
    result = detect_region(game, RegionRequest(
        text="Recebe a bola na intermediária ofensiva pela direita",
        team_id="team-vermelho"))
    assert result.status == "explicit" and result.team_evidence == "caller_context"
    assert result.zone.band == 4 and result.field_band == 2
    no_context = detect_region(game, RegionRequest(
        text="Recebe a bola na intermediária ofensiva pela direita"))
    assert no_context.reason == "no_explicit_team"
    conflict = detect_region(game, RegionRequest(
        text="Azul com a bola na própria área pela direita", team_id="team-vermelho"))
    assert conflict.reason == "conflicting_team_context"
    with pytest.raises(ValueError, match="Unknown team"):
        detect_region(game, RegionRequest(text="Azul com a bola", team_id="stranger"))


def test_stoppage_and_finished_do_not_generate_current_location():
    for period in ("half_time", "finished"):
        game = match()
        game.period = period
        result = detect_region(game, RegionRequest(
            text="Azul com a bola na própria área pela esquerda"))
        assert result.reason == "not_playing" and result.zone is None


def test_api_reads_current_match_and_preserves_persisted_ball_state(tmp_path):
    from app.main import create_app
    game = match()
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        created = client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"}))
        assert created.status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        endpoint = "/api/matches/match-051/resolve-region"
        result = client.post(endpoint, json={
            "text": "Vermelho com a bola na intermediária ofensiva pela direita",
        })
        assert result.status_code == 200, result.text
        assert result.json()["zone"] == {"band": 4, "lane": "right"}
        assert result.json()["field_band"] == 2
        assert result.json()["field_lane"] == "left"
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(endpoint, json={"text": "Azul com a bola",
                                          "team_id": "another"}).status_code == 422
        assert client.post(endpoint, json={"text": "x" * 2049}).status_code == 422
        assert client.post("/api/matches/absent/resolve-region",
                           json={"text": "Azul com a bola"}).status_code == 404
