"""GN-081: API + two WebSocket clients + SQLite end-to-end regression.

All text and event inputs are synthetic. The transcript feed is volatile and
does not represent an ASR or live capture pipeline; the /ws demo is separate
from /ws/matches/{id}/transcripts and persisted /api/matches/{id}/state.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.asr_windows import WindowTranscript
from app.main import create_app


def match_config(match_id: str, suffix: str) -> dict:
    return {
        "id": match_id,
        "home": {
            "id": f"home-{suffix}", "name": "Azul", "short_name": "AZU",
            "color": "#1268AA", "attack_direction": "left_to_right",
        },
        "away": {
            "id": f"away-{suffix}", "name": "Vermelho", "short_name": "VER",
            "color": "#DD5544", "attack_direction": "right_to_left",
        },
        "period": "first_half", "match_seconds": 0,
        "home_score": 0, "away_score": 0,
    }


def roster(suffix: str) -> list[dict]:
    return [
        {
            "id": f"player-home-{suffix}", "team_id": f"home-{suffix}",
            "name": "Caio", "number": 9, "aliases": [], "starter": True,
            "position": "forward",
        },
        {
            "id": f"player-away-{suffix}", "team_id": f"away-{suffix}",
            "name": "Rafael", "number": 1, "aliases": [], "starter": True,
            "position": "goalkeeper",
        },
    ]


def source(source_id: str) -> dict:
    return {
        "id": source_id, "name": "Rádio sintética", "kind": "radio",
        "url": None, "enabled": True, "status": "offline",
    }


def window(source_id: str, text: str) -> WindowTranscript:
    return WindowTranscript(
        source_id=source_id, sequence=0,
        start_seconds=0, end_seconds=5, language="pt",
        raw_text=text, new_text=text,
    )


def register(client: TestClient, match_id: str, suffix: str, source_id: str) -> None:
    base = f"/api/matches/{match_id}"
    assert client.post("/api/matches", json=match_config(match_id, suffix)).status_code == 201
    assert client.put(base + "/players", json=roster(suffix)).status_code == 200
    assert client.put(base + "/sources", json=[source(source_id)]).status_code == 200


def test_live_text_fanout_canonical_state_and_restart_are_consistent(tmp_path):
    database = tmp_path / "gn081.sqlite3"
    match_id = "match-081-main"
    other_id = "match-081-other"
    source_id = "source-radio-081"
    other_source_id = "source-other-081"
    base = f"/api/matches/{match_id}"
    other_base = f"/api/matches/{other_id}"
    observed = datetime.now(timezone.utc)
    statement = "Caio do Azul recebe a bola"

    with TestClient(create_app(database)) as client:
        register(client, match_id, "081a", source_id)
        register(client, other_id, "081b", other_source_id)
        initial = client.get(base + "/state").json()
        assert initial["schema_version"] == "1.0.0"
        assert initial["events"] == [] and initial["ball"]["team_id"] is None
        demo_initial = client.get("/api/state").json()
        assert demo_initial["mode"] == "synthetic_demo"
        assert demo_initial["data"]["match"]["id"] != match_id

        # A text result reaches two independent WebSocket connections and HTTP,
        # but must not silently become a canonical event or change the ball.
        with client.websocket_connect(f"/ws/matches/{match_id}/transcripts") as first:
            with client.websocket_connect(f"/ws/matches/{match_id}/transcripts") as second:
                a = first.receive_json()
                b = second.receive_json()
                assert a == b
                assert a["kind"] == "snapshot"
                assert a["data"]["entries"] == []
                feed = client.app.state.transcript_feed
                feed.publish(
                    match_id, source_id, window(source_id, statement),
                    captured_at=observed,
                )
                update_a = first.receive_json()
                update_b = second.receive_json()
                assert update_a == update_b
                assert update_a["kind"] == "transcript"
                assert update_a["data"]["source_id"] == source_id
                assert update_a["data"]["text"] == statement

                feed.publish(
                    other_id, other_source_id,
                    window(other_source_id, "Rafael com a bola"),
                    captured_at=observed,
                )
                assert [entry["source_id"] for entry in client.get(
                    base + "/transcripts"
                ).json()["entries"]] == [source_id]
                assert [entry["source_id"] for entry in client.get(
                    other_base + "/transcripts"
                ).json()["entries"]] == [other_source_id]
                first.send_text("close")
                second.send_text("close")

        assert client.get(base + "/state").json() == initial
        resolved = client.post(base + "/resolve-narration", json={"text": statement})
        assert resolved.status_code == 200
        assert resolved.json()["mentions"][0]["player_id"] == "player-home-081a"
        assert client.get(base + "/state").json() == initial

        # An explicit operator state override is the ONLY persistence step.
        saved = copy.deepcopy(initial)
        stamp = observed.isoformat()
        saved["segments"] = [{
            "id": "seg-081", "source_id": source_id, "text": statement,
            "category": "live_play", "captured_at": stamp,
            "transcribed_at": stamp, "match_seconds": 35,
            "text_confidence": 0.8,
        }]
        saved["events"] = [{
            "id": "event-081", "kind": "possession",
            "source_ids": [source_id], "segment_ids": ["seg-081"],
            "observed_at": stamp, "match_seconds": 35,
            "team_id": "home-081a", "player_id": "player-home-081a",
            "zone": {"band": 3, "lane": "center"},
            "confidences": {"team": 0.8, "player": 0.8, "zone": 0.7,
                            "action": 0.7, "timing": 0.9},
            "uncertainty": "estimated",
        }]
        saved["ball"].update(
            last_event_id="event-081", team_id="home-081a",
            player_id="player-home-081a", zone={"band": 3, "lane": "center"},
            uncertainty="estimated", updated_at=stamp,
            expires_at=(observed + timedelta(seconds=10)).isoformat(),
        )
        response = client.put(base + "/state", json=saved)
        assert response.status_code == 200, response.text
        assert client.get(base + "/state").json()["events"][0]["id"] == "event-081"
        assert client.get(other_base + "/state").json()["events"] == []

        correction = client.post(base + "/corrections", json={
            "kind": "score", "reason": "Operador confirmou o placar",
            "actor": "mesa", "home_score": 1, "away_score": 0,
        })
        assert correction.status_code == 201, correction.text
        change_half = client.post(base + "/actions", json={
            "kind": "half_time", "match_seconds": 2700,
        })
        assert change_half.status_code == 200, change_half.text
        final_state = client.get(base + "/state").json()
        assert final_state["match"]["period"] == "half_time"
        assert final_state["match"]["home_score"] == 1
        assert final_state["ball"]["team_id"] is None
        assert final_state["ball"]["player_id"] is None
        assert final_state["ball"]["zone"] is None
        assert final_state["ball"]["uncertainty"] == "uncertain"
        assert final_state["events"][0]["id"] == "event-081"
        audit = client.get(base + "/corrections").json()
        flow = client.get(base + "/flow").json()
        assert [entry["kind"] for entry in audit] == ["state_override", "score"]
        assert [entry["kind"] for entry in flow["operations"]] == ["half_time"]
        assert client.get("/api/state").json() == demo_initial

    # A fresh app instance restores SQLite, not in-memory transcripts or demo.
    with TestClient(create_app(database)) as client:
        assert client.get(base + "/state").json() == final_state
        assert client.get(base + "/corrections").json() == audit
        assert client.get(base + "/flow").json() == flow
        assert client.get(other_base + "/state").json()["events"] == []
        assert client.get(base + "/transcripts").json()["entries"] == []
        with client.websocket_connect(f"/ws/matches/{match_id}/transcripts") as ws:
            frame = ws.receive_json()
            assert frame["kind"] == "snapshot"
            assert frame["data"]["entries"] == []
            ws.send_text("close")

        # A rejected write cannot partially replace the SQLite snapshot/audit.
        invalid = copy.deepcopy(final_state)
        invalid["events"][0]["segment_ids"] = ["orphan-segment"]
        rejected = client.put(base + "/state", json=invalid)
        assert rejected.status_code == 422
        assert client.get(base + "/state").json() == final_state
        assert client.get(base + "/corrections").json() == audit
        assert client.get("/api/state").json()["mode"] == "synthetic_demo"


def test_delete_and_recreate_same_match_does_not_leak_volatile_feed(tmp_path):
    database = tmp_path / "gn081-delete.sqlite3"
    match_id = "match-081-reused"
    source_id = "source-081-reused"
    base = f"/api/matches/{match_id}"
    with TestClient(create_app(database)) as client:
        register(client, match_id, "081c", source_id)
        client.app.state.transcript_feed.publish(
            match_id, source_id, window(source_id, "Caio recebe a bola"),
            captured_at=datetime.now(timezone.utc),
        )
        assert len(client.get(base + "/transcripts").json()["entries"]) == 1
        assert client.delete(base).status_code == 204
        assert client.get(base + "/state").status_code == 404
        register(client, match_id, "081c", source_id)
        assert client.get(base + "/transcripts").json()["entries"] == []
        assert client.get(base + "/state").json()["events"] == []
        with client.websocket_connect(f"/ws/matches/{match_id}/transcripts") as ws:
            snapshot = ws.receive_json()
            assert snapshot["kind"] == "snapshot"
            assert snapshot["data"]["entries"] == []
            ws.send_text("close")
