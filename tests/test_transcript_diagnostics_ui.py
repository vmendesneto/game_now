"""GN-075: text-only diagnostics in HTML and source-aware API/WebSocket."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.asr_windows import WindowTranscript

ROOT=Path(__file__).resolve().parents[1]
MATCH={"id":"match-075","home":{"id":"club-a","name":"Azul","short_name":"AZU",
 "color":"#4990FF","attack_direction":"left_to_right"},
 "away":{"id":"club-b","name":"Vermelho","short_name":"VER",
 "color":"#F26C69","attack_direction":"right_to_left"},
 "period":"first_half","match_seconds":0,"home_score":0,"away_score":0}
SOURCES=[{"id":"source-a","name":"Rádio Azul","kind":"radio","url":None,
 "enabled":True,"status":"offline"},{"id":"source-b","name":"Rádio Vermelha",
 "kind":"radio","url":None,"enabled":False,"status":"offline"}]

def test_transcript_http_websocket_and_page_are_text_only(tmp_path):
 with TestClient(create_app(tmp_path/"feed.sqlite3")) as client:
  page=client.get("/").text
  for element in ("transcripts-panel","transcript-source-filter","transcript-source-status",
                  "transcript-entry-list","transcript-event-list","transcript-connection"):
   assert f'id="{element}"' in page
  assert page.index("transcript_diagnostics.js")<page.index("app.js")
  assert "<audio" not in page and "<video" not in page
  assert client.post("/api/matches",json=MATCH).status_code==201
  assert client.put("/api/matches/match-075/sources",json=SOURCES).status_code==200
  with client.websocket_connect("/ws/matches/match-075/transcripts") as ws:
   assert ws.receive_json()["kind"]=="snapshot"
   feed=client.app.state.transcript_feed
   now=datetime.now(timezone.utc)
   feed.set_state("match-075","source-a","processing")
   assert ws.receive_json()["kind"]=="status"
   entry=WindowTranscript(source_id="source-a",sequence=0,start_seconds=0,
      end_seconds=6,language="pt",raw_text="Bola com Azul",new_text="Bola com Azul")
   feed.publish("match-075","source-a",entry,captured_at=now)
   response=ws.receive_json()
   assert response["kind"]=="transcript"
   assert response["data"]["text"]=="Bola com Azul"
   ws.send_text("close")
  http=client.get("/api/matches/match-075/transcripts").json()
  assert http["mode"]=="volatile_text_only"
  assert http["entries"][0]["source_id"]=="source-a"
  assert "url" not in str(http)
  assert "audio_base64" not in str(http)

def test_javascript_diagnostics_and_static_bindings():
 content=(ROOT/"app/static/app.js").read_text(encoding="utf-8")
 assert "GameNowTranscript.apply(" in content
 assert "GameNowTranscript.present(" in content
 node=shutil.which("node")
 if not node: pytest.skip("Node.js unavailable; CI executes browser model tests")
 process=subprocess.run([node,"--test",str(ROOT/"tests/test_transcript_diagnostics.cjs")],
  capture_output=True,text=True,timeout=20)
 assert process.returncode==0,process.stdout+"\n"+process.stderr
 assert "# fail 0" in process.stdout
