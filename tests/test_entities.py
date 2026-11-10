"""GN-022: never confuse same-name/number players from different clubs."""
from fastapi.testclient import TestClient

from app.contracts import Match, Player, Team
from app.entities import normalize_mention, resolve_player
from app.main import create_app


def example_match():
    return Match(
        id="match-entity",
        home=Team(id="team-azul", name="Azul", short_name="AZU",
                  color="#1234AB", attack_direction="left_to_right"),
        away=Team(id="team-vermelho", name="Vermelho", short_name="VER",
                  color="#ED1234", attack_direction="right_to_left"),
        players=[
            Player(id="player-azul-10", team_id="team-azul", name="João Silva",
                   number=10, aliases=["J. Silva", "Joao"], starter=True),
            Player(id="player-ver-10", team_id="team-vermelho", name="João Silva",
                   number=10, aliases=["J. Silva"], starter=True),
            Player(id="player-azul-11", team_id="team-azul", name="José Sousa",
                   number=11, aliases=["Joao"], starter=False),
        ],
    )


def test_normalize_accents_and_word_boundaries():
    assert normalize_mention("  JOÃO-SILVA!  ") == "joao silva"
    assert normalize_mention("  Camisa Nº 10  ") == "camisa no 10"
    match = example_match()
    assert resolve_player(match, "Camisa 1").status == "unknown"
    assert resolve_player(match, "JOÃOzinho", "team-azul").status == "unknown"
    assert resolve_player(match, "camisa 100").status == "unknown"


def test_ambiguity_no_cross_team_guess_and_team_context():
    match = example_match()
    for mention in ("João Silva", "  J. SILVA ", "CAMISA #10", "número 10", "Camisa Nº 10"):
        result = resolve_player(match, mention)
        assert result.status == "ambiguous"
        assert result.player_id is None
        assert result.team_id is None
        assert result.candidate_ids == ["player-azul-10", "player-ver-10"]
        resolved = resolve_player(match, mention, "team-vermelho")
        assert resolved.status == "resolved"
        assert resolved.player_id == "player-ver-10"
    assert resolve_player(match, "camisa 10", "team-azul").player_id == "player-azul-10"
    assert resolve_player(match, "camisa 11", "team-vermelho").status == "unknown"
    assert resolve_player(match, "Joao", "team-azul").status == "ambiguous"
    assert resolve_player(match, "José Sousa", "team-azul").player_id == "player-azul-11"


def test_resolver_api_honors_saved_roster_after_restart(tmp_path):
    path = tmp_path / "resolve.sqlite3"
    match = example_match()
    config = match.model_dump(mode="json", exclude={"players"})
    roster = [{**p.model_dump(mode="json"), "position": "midfielder"} for p in match.players]
    with TestClient(create_app(path)) as client:
        assert client.post("/api/matches", json=config).status_code == 201
        assert client.put("/api/matches/match-entity/players", json=roster).status_code == 200
        unknown_team = client.post("/api/matches/match-entity/resolve-player",
                                   json={"mention": "camisa 10", "team_id": "team-other"})
        assert unknown_team.status_code == 422
    with TestClient(create_app(path)) as client:
        ambiguous = client.post("/api/matches/match-entity/resolve-player",
                                json={"mention": "camisa 10"})
        assert ambiguous.status_code == 200
        assert ambiguous.json()["status"] == "ambiguous"
        assert len(ambiguous.json()["candidate_ids"]) == 2
        resolved = client.post("/api/matches/match-entity/resolve-player",
                               json={"mention": "João Silva", "team_id": "team-vermelho"})
        assert resolved.status_code == 200
        assert resolved.json()["player_id"] == "player-ver-10"
        assert client.post("/api/matches/missing/resolve-player",
                           json={"mention": "camisa 10"}).status_code == 404
