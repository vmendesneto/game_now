"""GN-025: correct score, possession and canonical events with durable audit."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from test_match_flow import match_config, roster


BASE = "/api/matches/match-024"


def start(client):
    assert client.post("/api/matches", json=match_config()).status_code == 201
    assert client.put(BASE + "/players", json=roster()).status_code == 200


def correct(client, **fields):
    return client.post(BASE + "/corrections", json={"reason": "Operador conferiu o lance",
                                                     "actor": "mesa", **fields})


def test_manual_score_and_possession_correction_audit_survives_restart(tmp_path):
    db = tmp_path / "audit.sqlite3"
    with TestClient(create_app(db)) as client:
        start(client)
        assert correct(client, kind="score", home_score=2, away_score=1).status_code == 201
        assert client.get(BASE).json()["home_score"] == 2
        assert client.get(BASE + "/state").json()["match"]["away_score"] == 1
        assert correct(client, kind="possession", team_id="team-home",
                       player_id="player-h-1").status_code == 201
        ball = client.get(BASE + "/state").json()["ball"]
        assert ball["team_id"] == "team-home"
        assert ball["player_id"] == "player-h-1"
        assert ball["zone"] is None
        assert ball["uncertainty"] == "uncertain"
        assert ball["confidences"]["team"] == 0
        audit = client.get(BASE + "/corrections").json()
        assert len(audit) == 2
        assert audit[0]["before"]["match"]["home_score"] == 0
        assert audit[0]["after"]["match"]["home_score"] == 2
        assert audit[1]["before"]["ball"]["team_id"] is None
        assert audit[1]["after"]["ball"]["team_id"] == "team-home"
        assert len({entry["id"] for entry in audit}) == 2
    with TestClient(create_app(db)) as client:
        assert client.get(BASE + "/corrections").json() == audit
        assert client.get(BASE + "/state").json()["ball"] == ball
        assert correct(client, kind="possession", team_id=None).status_code == 201
        assert client.get(BASE + "/state").json()["ball"]["player_id"] is None
        assert client.delete(BASE).status_code == 204
        assert client.get(BASE + "/corrections").status_code == 404


def test_rejected_corrections_do_not_change_state_or_audit(tmp_path):
    with TestClient(create_app(tmp_path / "invalid.sqlite3")) as client:
        start(client)
        initial = client.get(BASE + "/state").json()
        assert correct(client, kind="score", home_score=-1, away_score=0).status_code == 422
        assert correct(client, kind="score", home_score=0, away_score=0).status_code == 409
        assert correct(client, kind="possession", team_id="team-third").status_code == 409
        assert correct(client, kind="possession", team_id="team-home",
                       player_id="player-a-1").status_code == 409
        assert correct(client, kind="possession", team_id=None,
                       player_id="player-h-1").status_code == 422
        assert correct(client, kind="event", event_id="event-1",
                       changes={"source_ids": []}).status_code == 422
        assert correct(client, kind="event", event_id="event-1",
                       changes={"kind": "shot"}).status_code == 409
        assert client.get(BASE + "/state").json() == initial
        assert client.get(BASE + "/corrections").json() == []
        assert client.post(BASE + "/corrections",
                           json={"kind": "score", "reason": "no",
                                 "home_score": 1, "away_score": 1}).status_code == 422
        assert client.post("/api/matches/missing/corrections",
                           json={"kind": "score", "reason": "Razão detalhada",
                                 "home_score": 1, "away_score": 1}).status_code == 404


def test_event_correction_and_legacy_mutations_leave_audit(tmp_path):
    with TestClient(create_app(tmp_path / "event.sqlite3")) as client:
        start(client)
        source = {"id": "radio-001", "name": "Rádio teste", "kind": "radio",
                  "url": None, "enabled": True, "status": "offline"}
        assert client.put(BASE + "/sources", json=[source]).status_code == 200
        state = client.get(BASE + "/state").json()
        stamp = datetime.now(timezone.utc).isoformat()
        state["segments"] = [{"id": "segment-001", "source_id": "radio-001",
                              "text": "Gol?", "category": "live_play",
                              "captured_at": stamp, "transcribed_at": stamp}]
        state["events"] = [{
            "id": "event-001", "kind": "goal", "source_ids": ["radio-001"],
            "segment_ids": ["segment-001"], "observed_at": stamp,
            "team_id": "team-home", "player_id": "player-h-1",
            "confidences": {}, "uncertainty": "uncertain",
        }]
        assert client.put(BASE + "/state", json=state).status_code == 200
        response = correct(client, kind="event", event_id="event-001",
                           changes={"kind": "shot", "team_id": "team-away",
                                    "player_id": "player-a-1"})
        assert response.status_code == 201
        assert client.get(BASE + "/state").json()["events"][0]["kind"] == "shot"
        assert client.get(BASE + "/state").json()["events"][0]["player_id"] == "player-a-1"
        assert correct(client, kind="event", event_id="event-001",
                       changes={"team_id": "team-home"}).status_code == 409
        assert client.get(BASE + "/state").json()["events"][0]["player_id"] == "player-a-1"
        edited = match_config()
        edited["home_score"] = 1
        assert client.put(BASE, json=edited).status_code == 200
        kinds = [entry["kind"] for entry in client.get(BASE + "/corrections").json()]
        assert kinds == ["state_override", "event", "score"]
        assert client.get(BASE + "/state").json()["match"]["home_score"] == 1
