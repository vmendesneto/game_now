"""GN-083: fixture de elencos fornecidos pelo usuário."""
from __future__ import annotations

import pytest

from app.configuration import RosterPlayer
from app.storage import SQLiteStore, StoreConflict
from scripts.seed_cruzeiro_bahia import MATCH_ID, match_config, roster, seed


def test_players_teams_and_uniform_numbers():
    game = match_config()
    players = roster()
    assert game.id == MATCH_ID
    assert (game.home.name, game.away.name) == ("Cruzeiro", "Bahia")
    assert game.home.attack_direction != game.away.attack_direction
    assert len(players) == 46
    for club in ("cruzeiro", "bahia"):
        group = [p for p in players if p.team_id == club]
        assert len(group) == 23
        assert sum(p.starter for p in group) == 11
        assert len({p.number for p in group}) == 23
    assert len({p.id for p in players}) == 46
    assert any(p.name == "Kaio Jorge" and p.starter and p.number == 19 for p in players)
    assert any(p.name == "Everton Ribeiro" and p.starter and p.number == 10 for p in players)


def test_seed_persists_across_restart_and_is_idempotent(tmp_path):
    db = tmp_path / "match.sqlite3"
    store = SQLiteStore(db)
    assert seed(store) == "created"
    assert seed(SQLiteStore(db)) == "already_exists"
    match = SQLiteStore(db).get_match(MATCH_ID)
    assert match is not None and len(match.players) == 46
    assert match.home_score == 0 and match.away_score == 0
    assert SQLiteStore(db).get_roster(MATCH_ID) == roster()
    assert len(SQLiteStore(db).list_matches()) == 1


def test_does_not_overwrite_manual_roster(tmp_path):
    store = SQLiteStore(tmp_path / "match.sqlite3")
    assert seed(store) == "created"
    changed = roster()
    changed[0] = RosterPlayer.model_validate({**changed[0].model_dump(), "name": "Nome corrigido"})
    store.replace_roster(MATCH_ID, changed)
    with pytest.raises(StoreConflict, match="refusing to overwrite"):
        seed(store)
    assert store.get_roster(MATCH_ID)[0].name == "Nome corrigido"


def test_can_complete_empty_roster(tmp_path):
    store = SQLiteStore(tmp_path / "match.sqlite3")
    store.create_match(match_config())
    assert seed(store) == "roster_added"
    assert len(store.get_roster(MATCH_ID)) == 46
