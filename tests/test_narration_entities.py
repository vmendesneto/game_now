"""GN-051: entity resolution must be explicit and ambiguity-safe."""
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app.contracts import Match, Player, Team
from app.narration_entities import (
    NarrationResolveRequest, resolve_narration,
)


def match():
    return Match(
        id="match-051",
        home=Team(id="team-azul", name="Azul", short_name="AZU", color="#1234AB",
                  attack_direction="left_to_right"),
        away=Team(id="team-vermelho", name="Vermelho", short_name="VER", color="#ED1234",
                  attack_direction="right_to_left"),
        players=[
            Player(id="azul-9", team_id="team-azul", name="João Silva", number=9,
                   aliases=["João"]),
            Player(id="ver-9", team_id="team-vermelho", name="João Silva", number=9,
                   aliases=["João"]),
            Player(id="azul-10", team_id="team-azul", name="Caio Ventura", number=10,
                   aliases=["Caio"]),
            Player(id="ver-10", team_id="team-vermelho", name="Bruno Costa", number=10,
                   aliases=["Bruno", "Caio"]),
        ],
    )


def resolve(text, **kwargs):
    return resolve_narration(match(), NarrationResolveRequest(text=text, **kwargs))


def test_explicit_club_and_player_names_and_utf8_offsets():
    text = "João Silva do Azul recebe a bola; Vermelho avança."
    result = resolve(text)
    found = result.mentions
    assert result.eligible_for_live_state
    assert [(m.kind, m.status, m.team_id) for m in found] == [
        ("player", "resolved", "team-azul"), ("team", "resolved", "team-azul"),
        ("team", "resolved", "team-vermelho"),
    ]
    assert found[0].player_id == "azul-9"
    assert all(m.text == text[m.start:m.end] for m in found)
    assert resolve("ver recebe a bola").mentions == []  # short-name vs verb
    assert resolve("VER recebe a bola").mentions[0].team_id == "team-vermelho"


def test_no_cross_team_guess_or_accidental_subwords():
    for text in ("JOÃO SILVA com a bola", "camisa nove com a bola", "Camisa 9 com a bola"):
        result = resolve(text)
        assert result.mentions[0].status == "ambiguous"
        assert result.mentions[0].player_id is None
        assert result.mentions[0].candidate_ids == ["azul-9", "ver-9"]
    assert resolve("Joãozinho com a bola").mentions == []
    assert resolve("nove com a bola").mentions == []
    assert resolve("camisa 100 com a bola").mentions == []


def test_shirts_in_words_or_digits_only_with_explicit_club():
    for text in ("camisa nove do Azul recebe a bola", "camisa 9 do Azul recebe a bola",
                 "camisa vinte e três do Azul com a bola"):
        result = resolve(text)
        player = result.mentions[0]
        if "três" in text:
            assert player.status == "unknown"  # no #23 registered
        else:
            assert player.status == "resolved"
            assert player.player_id == "azul-9"
    assert resolve("Número 10 do Vermelho com a bola").mentions[0].player_id == "ver-10"


def test_pronoun_requires_unique_local_antecedent():
    one = resolve("João do Azul com a bola, ele chuta")
    assert one.mentions[-1].kind == "pronoun"
    assert one.mentions[-1].player_id == "azul-9"
    assert one.mentions[-1].evidence == "local_antecedent"
    two = resolve("João do Azul com a bola, Bruno passa, ele chuta")
    assert two.mentions[-1].status == "unknown"
    assert resolve("Ele chuta").mentions[-1].status == "unknown"
    assert resolve("João do Azul com a bola. Ele chuta").mentions[-1].status == "unknown"


def test_previous_context_must_be_same_source_contiguous_recent_and_match():
    previous = resolve("João do Azul recebe a bola", source_id="radio-1",
                       sequence=3, start_seconds=12, end_seconds=18).next_context
    assert previous and previous.player_id == "azul-9"
    ok = resolve("Ele recebe a bola", source_id="radio-1", sequence=4,
                 start_seconds=21, end_seconds=27, previous=previous)
    assert ok.mentions[0].player_id == "azul-9"
    assert ok.mentions[0].evidence == "prior_context"
    assert ok.next_context is None  # pronouns cannot extend the window indefinitely
    for changes in (
        {"source_id": "radio-2"}, {"sequence": 5},
        {"start_seconds": 40, "end_seconds": 45},
    ):
        request = dict(source_id="radio-1", sequence=4, start_seconds=21,
                       end_seconds=27, previous=previous)
        request.update(changes)
        assert resolve("Ele recebe a bola", **request).mentions[0].status == "unknown"
    assert resolve("Ele recebe a bola", source_id="radio-1", sequence=4,
                   start_seconds=21,
                   previous=previous.model_copy(update={"match_id": "other-match"})).mentions[0].status == "unknown"


def test_no_previous_context_for_ads_replays_unknown_or_multiple_names():
    common = dict(source_id="radio-1", sequence=1, start_seconds=0, end_seconds=6)
    assert resolve("No replay João do Azul recebe a bola", **common).next_context is None
    assert resolve("João do Azul marcou o gol, oferecimento da loja", **common).next_context is None
    assert resolve("João do Azul recebeu um presente", **common).next_context is None
    assert resolve("João do Azul e Bruno recebem a bola", **common).next_context is None
    replay = resolve("No replay João do Azul recebe a bola e ele avança")
    assert replay.mentions[-1].status == "unknown"
    assert replay.eligible_for_live_state is False


def test_input_bounds_and_validation():
    with pytest.raises(ValidationError):
        NarrationResolveRequest(text="a" * 2049)
    with pytest.raises(ValidationError):
        NarrationResolveRequest(text="ok", start_seconds=4, end_seconds=3)


def test_api_reads_persisted_roster_and_leaves_match_state_unchanged(tmp_path):
    from app.main import create_app
    db = tmp_path / "game.sqlite3"
    game = match()
    with TestClient(create_app(db)) as client:
        assert client.post("/api/matches", json=game.model_dump(mode="json", exclude={"players"})).status_code == 201
        roster = [{**p.model_dump(mode="json"), "position": "forward"} for p in game.players]
        assert client.put("/api/matches/match-051/players", json=roster).status_code == 200
        original_state = client.get("/api/matches/match-051/state").json()
        response = client.post("/api/matches/match-051/resolve-narration",
                               json={"text": "João do Azul recebe a bola, ele chuta"})
        assert response.status_code == 200, response.text
        assert response.json()["mentions"][0]["player_id"] == "azul-9"
        assert response.json()["mentions"][-1]["player_id"] == "azul-9"
        assert client.get("/api/matches/match-051/state").json() == original_state
        assert client.post("/api/matches/absent/resolve-narration", json={"text": "ele"}).status_code == 404
        assert client.post("/api/matches/match-051/resolve-narration",
                           json={"text": "x" * 2049}).status_code == 422
    with TestClient(create_app(db)) as client:
        response = client.post("/api/matches/match-051/resolve-narration",
                               json={"text": "camisa 9 com a bola"})
        assert response.json()["mentions"][0]["status"] == "ambiguous"
