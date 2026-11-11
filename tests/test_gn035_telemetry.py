"""GN-035: metadata reaches existing HTTP/WebSocket without audio leakage."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from app.asr_windows import WindowTranscript
from app.main import create_app

MATCH = {
 "id":"match-035","home":{"id":"club-a","name":"Azul","short_name":"AZU",
 "color":"#4990FF","attack_direction":"left_to_right"},
 "away":{"id":"club-b","name":"Vermelho","short_name":"VER",
 "color":"#F26C69","attack_direction":"right_to_left"},
 "period":"first_half","match_seconds":0,"home_score":0,"away_score":0,
}
SOURCE = {"id":"radio-035","name":"Rádio Azul","kind":"radio",
 "url":None,"enabled":True,"status":"offline"}


def test_telemetry_http_websocket_and_isolation(tmp_path):
    with TestClient(create_app(tmp_path/"game.sqlite3")) as client:
        assert client.post("/api/matches",json=MATCH).status_code == 201
        assert client.put("/api/matches/match-035/sources",json=[SOURCE]).status_code == 200
        feed = client.app.state.transcript_feed
        with client.websocket_connect("/ws/matches/match-035/transcripts") as ws:
            first=ws.receive_json()
            assert first["kind"] == "snapshot"
            feed.observe_pcm("match-035","radio-035",32000)
            notice=ws.receive_json()
            assert notice["kind"] == "status"
            assert notice["data"]["telemetry"]["signal"] == "online"
            assert "url" not in str(notice)
            now=datetime.now(timezone.utc)
            item=WindowTranscript(source_id="radio-035",sequence=0,start_seconds=0,
                end_seconds=6,language="pt",raw_text="Gol do Azul!",
                new_text="Gol do Azul!")
            feed.publish("match-035","radio-035",item,
                         captured_at=now-timedelta(seconds=1))
            update=ws.receive_json()
            assert update["kind"] == "transcript"
            assert update["data"]["telemetry"]["content"] == "narrating"
            assert update["data"]["telemetry"]["relative_delay_seconds"] is None
            ws.send_text("close")
        source=client.get("/api/matches/match-035/transcripts").json()["sources"][0]
        assert source["telemetry"]["processing_delay_seconds"] >= 1
        assert "audio" not in str(source).lower()
        feed.observe_pcm("match-035","not-registered",32000)
        visible=client.get("/api/matches/match-035/transcripts").json()
        assert [row["source_id"] for row in visible["sources"]] == ["radio-035"]
        assert client.delete("/api/matches/match-035").status_code == 204
        assert feed.snapshot("match-035")["sources"] == []
