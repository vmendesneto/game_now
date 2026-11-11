"""GN-052: possession can change only on explicit, unambiguous live text."""
from fastapi.testclient import TestClient

from app.possession import PossessionRequest, detect_possession
from test_narration_entities import match


def check(text: str, previous=None):
    return detect_possession(match(), PossessionRequest(text=text, previous_team_id=previous))


def test_explicit_player_team_and_turnover():
    first = check("João do Azul recebe a bola")
    assert first.status == "explicit" and first.team_id == "team-azul"
    assert first.player_id == "azul-9" and first.changed_team is None
    second = check("Bruno do Vermelho com a bola", first.team_id)
    assert second.status == "explicit" and second.team_id == "team-vermelho"
    assert second.changed_team is True
    assert check("Bruno do Vermelho com a bola", "team-vermelho").changed_team is False
    assert check("Vermelho com a bola").team_id == "team-vermelho"


def test_bola_com_and_no_assumption_from_pass_or_guess():
    assert check("Bola com o camisa nove do Azul").player_id == "azul-9"
    assert check("Bola com João Silva").status == "unknown"
    assert check("João Silva com a bola").status == "unknown"
    assert check("Caio passa para Bruno").status == "unknown"
    assert check("Vermelho perdeu a bola").status == "unknown"
    assert check("É gol do Azul").status == "unknown"


def test_replay_ads_past_and_conflicts_are_unknown():
    assert check("No replay, João do Azul recebe a bola").status == "unknown"
    assert check("Oferecimento: João do Azul com a bola").status == "unknown"
    assert check("João do Azul recebe a bola e Bruno do Vermelho com a bola").status == "unknown"
    assert check("Azul com a bola. Bruno do Vermelho chega").team_id == "team-azul"


def test_api_read_only_and_previous_team_validation(tmp_path):
    from app.main import create_app
    game = match()
    with TestClient(create_app(tmp_path / "db.sqlite3")) as client:
        assert client.post("/api/matches", json=game.model_dump(mode="json", exclude={"players"})).status_code == 201
        assert client.put("/api/matches/match-051/players", json=[
            {**p.model_dump(mode="json"), "position": "forward"} for p in game.players]).status_code == 200
        before = client.get("/api/matches/match-051/state").json()
        path = "/api/matches/match-051/resolve-possession"
        x = client.post(path, json={"text": "Bruno do Vermelho com a bola", "previous_team_id": "team-azul"})
        assert x.status_code == 200 and x.json()["changed_team"] is True
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(path, json={"text": "Bola com Bruno", "previous_team_id": "alien"}).status_code == 422
        assert client.post("/api/matches/no-match/resolve-possession", json={"text": "Bola com Bruno"}).status_code == 404
