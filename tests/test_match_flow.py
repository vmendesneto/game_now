"""GN-024: substitutions, dismissal, half-time, sides and stoppage time."""
from fastapi.testclient import TestClient

from app.main import create_app


def match_config():
    return {
        "id": "match-024",
        "home": {"id": "team-home", "name": "Casa", "short_name": "CAS",
                 "color": "#2255AA", "attack_direction": "left_to_right"},
        "away": {"id": "team-away", "name": "Fora", "short_name": "FOR",
                 "color": "#AA5522", "attack_direction": "right_to_left"},
        "period": "first_half", "match_seconds": 0, "home_score": 0, "away_score": 0,
    }


def roster():
    return [
        {"id": f"player-h-{number}", "team_id": "team-home", "name": f"Home {number}",
         "number": number, "aliases": [], "starter": number <= 11,
         "position": "midfielder"}
        for number in range(1, 14)
    ] + [
        {"id": f"player-a-{number}", "team_id": "team-away", "name": f"Away {number}",
         "number": number, "aliases": [], "starter": number <= 11,
         "position": "midfielder"}
        for number in range(1, 13)
    ]


def start(client):
    assert client.post("/api/matches", json=match_config()).status_code == 201
    assert client.put("/api/matches/match-024/players", json=roster()).status_code == 200


def act(client, kind, **args):
    return client.post("/api/matches/match-024/actions", json={"kind": kind, **args})


def test_full_match_operations_and_sqlite_restart(tmp_path):
    db = tmp_path / "flow.sqlite3"
    with TestClient(create_app(db)) as client:
        start(client)
        base = "/api/matches/match-024"
        before = client.get(base + "/flow").json()
        assert len(before["active_player_ids"]) == 22
        assert before["operations"] == []
        assert act(client, "added_time", seconds=240, match_seconds=2700).status_code == 200
        assert act(client, "substitution", player_out_id="player-h-2",
                   player_in_id="player-h-12", match_seconds=2750).status_code == 200
        assert act(client, "red_card", player_id="player-a-4", match_seconds=2800).status_code == 200
        assert act(client, "half_time", match_seconds=2940).status_code == 200
        assert client.get(base).json()["period"] == "half_time"
        assert act(client, "substitution", player_out_id="player-a-3",
                   player_in_id="player-a-12").status_code == 200
        assert act(client, "second_half", match_seconds=3000).status_code == 200
        match = client.get(base).json()
        assert match["period"] == "second_half"
        assert match["home"]["attack_direction"] == "right_to_left"
        assert match["away"]["attack_direction"] == "left_to_right"
        assert client.get(base + "/state").json()["match"] == match
        assert act(client, "added_time", seconds=360, match_seconds=5400).status_code == 200
        assert act(client, "finish", match_seconds=5760).status_code == 200
        flow = client.get(base + "/flow").json()
        assert flow["period"] == "finished"
        assert flow["match_seconds"] == 5760
        assert flow["added_time_seconds"] == {"first_half": 240, "second_half": 360}
        assert flow["sent_off_ids"] == ["player-a-4"]
        assert len(flow["active_player_ids"]) == 21
        assert "player-h-12" in flow["active_player_ids"]
        assert "player-h-2" not in flow["active_player_ids"]
        assert "player-a-12" in flow["active_player_ids"]
        assert len(flow["operations"]) == 8
        assert len({op["id"] for op in flow["operations"]}) == 8
        assert client.get(base + "/players").json() == roster()
    with TestClient(create_app(db)) as client:
        assert client.get(base + "/flow").json() == flow
        assert client.get(base + "/state").json()["match"]["period"] == "finished"
        assert client.delete(base).status_code == 204
        assert client.get(base + "/flow").status_code == 404


def test_invalid_actions_are_atomic_and_roster_is_locked(tmp_path):
    with TestClient(create_app(tmp_path / "conflict.sqlite3")) as client:
        start(client)
        base = "/api/matches/match-024"
        assert act(client, "second_half").status_code == 409
        assert act(client, "red_card", player_id="player-h-12").status_code == 409
        assert act(client, "substitution", player_out_id="player-h-2",
                   player_in_id="player-a-12").status_code == 409
        assert act(client, "added_time", seconds=-1).status_code == 422
        assert act(client, "red_card", player_id="player-h-1", seconds=10).status_code == 422
        assert act(client, "substitution", player_out_id="player-h-1",
                   player_in_id="player-h-1").status_code == 422
        assert client.get(base + "/flow").json()["operations"] == []
        assert act(client, "substitution", player_out_id="player-h-2",
                   player_in_id="player-h-12", match_seconds=100).status_code == 200
        assert act(client, "substitution", player_out_id="player-h-2",
                   player_in_id="player-h-13").status_code == 409
        assert act(client, "substitution", player_out_id="player-h-12",
                   player_in_id="player-h-2").status_code == 409
        assert act(client, "red_card", player_id="player-h-2").status_code == 409
        assert act(client, "added_time", seconds=10, match_seconds=99).status_code == 409
        assert client.put(base + "/players", json=roster()[:-1]).status_code == 409
        changed = match_config()
        changed["period"] = "second_half"
        assert client.put(base, json=changed).status_code == 409
        unchanged = client.get(base).json()
        assert unchanged["period"] == "first_half"
        assert unchanged["match_seconds"] == 100
        assert len(client.get(base + "/flow").json()["operations"]) == 1
        assert act(client, "half_time").status_code == 200
        assert act(client, "half_time").status_code == 409
        assert act(client, "red_card", player_id="player-h-1").status_code == 409
        assert act(client, "second_half").status_code == 200
        assert act(client, "red_card", player_id="player-h-12").status_code == 200
        assert act(client, "substitution", player_out_id="player-h-12",
                   player_in_id="player-h-13").status_code == 409
        assert act(client, "added_time", seconds=30).status_code == 200
        assert act(client, "added_time", seconds=20).status_code == 409
        assert client.get("/api/matches/missing/flow").status_code == 404
        assert client.post("/api/matches/missing/actions", json={"kind": "finish"}).status_code == 404


def test_halftime_discards_stale_possession_but_keeps_history(tmp_path):
    with TestClient(create_app(tmp_path / "ball.sqlite3")) as client:
        start(client)
        base = "/api/matches/match-024"
        bundle = client.get(base + "/state").json()
        bundle["ball"]["team_id"] = "team-home"
        bundle["ball"]["player_id"] = "player-h-1"
        bundle["ball"]["uncertainty"] = "estimated"
        assert client.put(base + "/state", json=bundle).status_code == 200
        assert act(client, "half_time").status_code == 200
        ball = client.get(base + "/state").json()["ball"]
        assert ball["player_id"] is None
        assert ball["team_id"] is None
        assert ball["zone"] is None
        assert ball["uncertainty"] == "uncertain"
