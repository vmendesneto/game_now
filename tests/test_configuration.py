"""GN-020, GN-021 and GN-023 regression and restart tests."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app


def config(match_id="match-001"):
    return {
        "id": match_id,
        "home": {"id": "club-a", "name": "Azul", "short_name": "AZU",
                 "color": "#1122FF", "attack_direction": "left_to_right"},
        "away": {"id": "club-b", "name": "Vermelho", "short_name": "VER",
                 "color": "#FF2211", "attack_direction": "right_to_left"},
        "period": "first_half", "match_seconds": 0,
        "home_score": 0, "away_score": 0,
    }


def player(id_, team, number, starter=True):
    return {"id": id_, "team_id": team, "name": "Atleta " + str(number),
            "number": number, "aliases": ["Camisa " + str(number)],
            "starter": starter, "position": "forward"}


def test_match_crud_validation_and_deletion(tmp_path):
    with TestClient(create_app(tmp_path / "crud.sqlite3")) as client:
        assert client.get("/api/matches").json() == []
        assert client.post("/api/matches", json=config()).status_code == 201
        assert client.post("/api/matches", json=config()).status_code == 409
        assert len(client.get("/api/matches").json()) == 1
        assert client.get("/api/matches/match-001").json()["home"]["name"] == "Azul"
        edited = config()
        edited["home"]["name"] = "Azul FC"
        edited["home_score"] = 2
        edited["period"] = "second_half"
        edited["match_seconds"] = 4000
        assert client.put("/api/matches/match-001", json=edited).json()["home_score"] == 2
        assert client.get("/api/matches/match-001").json()["period"] == "second_half"
        invalid = config("match-bad")
        invalid["away"]["attack_direction"] = "left_to_right"
        assert client.post("/api/matches", json=invalid).status_code == 422
        invalid = config("match-bad")
        invalid["home_score"] = -1
        assert client.post("/api/matches", json=invalid).status_code == 422
        invalid = config("match-bad")
        invalid["home"]["color"] = "blue"
        assert client.post("/api/matches", json=invalid).status_code == 422
        assert client.put("/api/matches/match-001", json=config("wrong-id")).status_code == 409
        assert client.get("/api/matches/missing").status_code == 404
        assert client.delete("/api/matches/match-001").status_code == 204
        assert client.get("/api/matches/match-001").status_code == 404
        assert client.delete("/api/matches/match-001").status_code == 404


def test_roster_two_teams_duplicate_shirts_and_atomic_rejection(tmp_path):
    with TestClient(create_app(tmp_path / "roster.sqlite3")) as client:
        client.post("/api/matches", json=config())
        roster = [player("player-a", "club-a", 10), player("player-b", "club-b", 10, False)]
        assert client.put("/api/matches/match-001/players", json=roster).status_code == 200
        assert client.get("/api/matches/match-001").json()["players"][0]["id"] == "player-a"
        assert client.get("/api/matches/match-001/players").json() == roster
        duplicate = [player("player-a", "club-a", 10), player("player-c", "club-a", 10)]
        assert client.put("/api/matches/match-001/players", json=duplicate).status_code == 409
        foreign = [player("player-foreign", "club-c", 9)]
        assert client.put("/api/matches/match-001/players", json=foreign).status_code == 409
        wrong_id = [player("player-a", "club-a", 10), player("player-a", "club-b", 11)]
        assert client.put("/api/matches/match-001/players", json=wrong_id).status_code == 409
        invalid = [player("player-a", "club-a", 0)]
        assert client.put("/api/matches/match-001/players", json=invalid).status_code == 422
        too_many = [player("starter-%02d" % i, "club-a", i) for i in range(1, 13)]
        assert client.put("/api/matches/match-001/players", json=too_many).status_code == 409
        assert client.get("/api/matches/match-001/players").json() == roster
        assert client.put("/api/matches/match-001", json={
            **config(), "home": {**config()["home"], "id": "new-club"},
        }).status_code == 409


def test_sqlite_persists_match_roster_sources_and_event_history_on_restart(tmp_path):
    db = tmp_path / "restart" / "game_now.sqlite3"
    with TestClient(create_app(db)) as client:
        assert client.post("/api/matches", json=config()).status_code == 201
        assert client.put("/api/matches/match-001/players",
                          json=[player("player-a", "club-a", 9)]).status_code == 200
        source = {"id": "radio-01", "name": "Rádio de teste", "kind": "radio",
                  "url": None, "enabled": True, "status": "offline"}
        assert client.put("/api/matches/match-001/sources", json=[source]).status_code == 200
        snapshot = client.get("/api/matches/match-001/state").json()
        stamp = datetime.now(timezone.utc).isoformat()
        snapshot["segments"] = [{
            "id": "segment-01", "source_id": "radio-01", "text": "Gol do Azul",
            "category": "live_play", "captured_at": stamp, "transcribed_at": stamp,
            "match_seconds": 50, "text_confidence": 0.9,
        }]
        snapshot["events"] = [{
            "id": "event-01", "kind": "goal", "source_ids": ["radio-01"],
            "segment_ids": ["segment-01"], "observed_at": stamp,
            "match_seconds": 50, "team_id": "club-a", "player_id": "player-a",
            "zone": {"band": 5, "lane": "center"},
            "confidences": {"team": 0.9, "player": 0.8, "zone": 0.7, "action": 0.9, "timing": 0.8},
            "uncertainty": "estimated",
        }]
        snapshot["ball"] = {
            "last_event_id": "event-01", "team_id": "club-a", "player_id": "player-a",
            "zone": {"band": 5, "lane": "center"}, "confidences": snapshot["events"][0]["confidences"],
            "uncertainty": "estimated", "updated_at": stamp, "expires_at": None,
        }
        response = client.put("/api/matches/match-001/state", json=snapshot)
        assert response.status_code == 200
        snapshot = response.json()
        assert client.put("/api/matches/match-001/sources", json=[]).status_code == 409
        assert client.put("/api/matches/match-001/players", json=[]).status_code == 409
        assert client.get("/api/matches/match-001/state").json() == snapshot
    with TestClient(create_app(db)) as client:
        assert client.get("/health").json()["storage"] == "sqlite_persistent"
        assert client.get("/api/matches/match-001/players").json()[0]["position"] == "forward"
        assert client.get("/api/matches/match-001/sources").json() == [source]
        assert client.get("/api/matches/match-001/state").json() == snapshot
        assert client.get("/api/state").json()["mode"] == "synthetic_demo"
        assert client.delete("/api/matches/match-001").status_code == 204
        assert client.get("/api/matches/match-001/state").status_code == 404



def test_snapshot_rejects_references_and_config_changes(tmp_path):
    with TestClient(create_app(tmp_path / "snapshot.sqlite3")) as client:
        client.post("/api/matches", json=config())
        state = client.get("/api/matches/match-001/state").json()
        changed = {**state, "match": {**state["match"], "home_score": 1}}
        assert client.put("/api/matches/match-001/state", json=changed).status_code == 409
        invalid = {**state, "sources": [{
            "id": "source-one", "name": "Fonte um", "kind": "radio",
            "url": None, "enabled": True, "status": "offline",
        }, {
            "id": "source-one", "name": "Fonte dois", "kind": "radio",
            "url": None, "enabled": True, "status": "offline",
        }]}
        assert client.put("/api/matches/match-001/state", json=invalid).status_code == 422
        assert client.get("/api/matches/match-001/state").json() == state
        page = client.get("/").text
        assert 'id="match-form"' in page
        assert 'id="player-form"' in page
