"""GN-094: retention expiry, capacity, fail-fast settings and endpoint."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.asr_windows import WindowTranscript
from app.main import create_app
from app.retention_policy import TranscriptRetention
from app.transcription_feed import TranscriptFeed


def win(seq, text):
    return WindowTranscript(source_id="radio",sequence=seq,start_seconds=seq*4,
                           end_seconds=seq*4+6,language="pt",
                           raw_text=text,new_text=text)


def test_retention_expiry_prunes_memory_and_rejects_replayed_sequence():
    clock = [datetime(2026, 11, 11, tzinfo=timezone.utc)]
    feed = TranscriptFeed(retention_seconds=60,max_entries_per_source=2,
                          now=lambda: clock[0])
    feed.publish("m","radio",win(0,"primeiro"),captured_at=clock[0])
    assert len(feed.snapshot("m")["entries"]) == 1
    clock[0] += timedelta(seconds=61)
    assert feed.snapshot("m")["entries"] == []
    with pytest.raises(ValueError,match="backwards"):
        feed.publish("m","radio",win(0,"replay"),captured_at=clock[0])
    feed.publish("m","radio",win(1,"segundo"),captured_at=clock[0])
    feed.publish("m","radio",win(2,"terceiro"),captured_at=clock[0])
    feed.publish("m","radio",win(3,"quarto"),captured_at=clock[0])
    snap=feed.snapshot("m")
    assert [x["text"] for x in snap["entries"]]==["terceiro","quarto"]
    assert snap["retention_seconds"]==60
    assert "primeiro" not in str(snap)


def test_environment_policy_defaults_borders_and_invalid_cases():
    assert TranscriptRetention.from_environment({})==TranscriptRetention()
    assert TranscriptRetention.from_environment({
        "GAME_NOW_TRANSCRIPT_TTL_SECONDS":"60",
        "GAME_NOW_TRANSCRIPT_MAX_ENTRIES":"1",
    }).max_entries_per_source==1
    for key,value in (
        ("GAME_NOW_TRANSCRIPT_TTL_SECONDS","0"),
        ("GAME_NOW_TRANSCRIPT_TTL_SECONDS","604801"),
        ("GAME_NOW_TRANSCRIPT_TTL_SECONDS","oops"),
        ("GAME_NOW_TRANSCRIPT_MAX_ENTRIES","501"),
        ("GAME_NOW_TRANSCRIPT_MAX_ENTRIES","-1"),
    ):
        with pytest.raises(ValueError,match=key):
            TranscriptRetention.from_environment({key:value})


def test_api_uses_configured_retention_and_filters_snapshot(tmp_path,monkeypatch):
    monkeypatch.setenv("GAME_NOW_TRANSCRIPT_TTL_SECONDS","120")
    monkeypatch.setenv("GAME_NOW_TRANSCRIPT_MAX_ENTRIES","2")
    match={
        "id":"match-retention","home":{"id":"club-a","name":"Azul","short_name":"AZU",
            "color":"#0088FF","attack_direction":"left_to_right"},
        "away":{"id":"club-b","name":"Vermelho","short_name":"VER",
            "color":"#FF1122","attack_direction":"right_to_left"},
        "period":"first_half","match_seconds":0,"home_score":0,"away_score":0,
    }
    source={"id":"radio","name":"Rádio","kind":"radio","url":None,
        "enabled":True,"status":"offline"}
    with TestClient(create_app(tmp_path/"retention.sqlite3")) as client:
        assert client.post("/api/matches",json=match).status_code==201
        assert client.put("/api/matches/match-retention/sources",json=[source]).status_code==200
        feed=client.app.state.transcript_feed
        now=datetime.now(timezone.utc)
        for i in range(3):
            feed.publish("match-retention","radio",win(i,f"fala {i}"),captured_at=now)
        response=client.get("/api/matches/match-retention/transcripts").json()
        assert response["retention_seconds"]==120
        assert [e["text"] for e in response["entries"]]==["fala 1","fala 2"]


def test_documented_direct_requirements_are_in_inventory():
    root=Path(__file__).resolve().parents[1]
    policy=(root/"docs/GN-094.md").read_text(encoding="utf-8")
    for name in ("fastapi","pydantic","uvicorn","pytest","httpx","jsonschema",
                 "faster-whisper","av","imageio-ffmpeg","yt-dlp","FFmpeg"):
        assert name in policy
