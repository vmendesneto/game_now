"""GN-076: demo run/pause/restart controls and persistent manual corrections."""
from pathlib import Path
import shutil
import subprocess
import pytest
from fastapi.testclient import TestClient
from app.main import create_app

ROOT=Path(__file__).resolve().parents[1]
MATCH={"id":"match-076",
 "home":{"id":"club-home","name":"Azul","short_name":"AZU","color":"#4990FF","attack_direction":"left_to_right"},
 "away":{"id":"club-away","name":"Vermelho","short_name":"VER","color":"#F26C69","attack_direction":"right_to_left"},
 "period":"first_half","match_seconds":0,"home_score":0,"away_score":0}

def test_demo_controls_are_separate_from_persisted_manual_corrections(tmp_path):
 with TestClient(create_app(tmp_path/"gn076.sqlite3")) as client:
  html=client.get("/").text
  for key in ("demo-start","demo-pause","reset","next","demo-playback-state","correction-form"):
   assert f'id="{key}"' in html
  assert html.index("demo_playback.js")<html.index("app.js")
  assert client.post("/api/matches",json=MATCH).status_code==201
  assert client.get("/api/state").json()["step"]==0
  assert client.post("/api/demo/next").json()["step"]==1
  assert client.post("/api/demo/reset").json()["step"]==0
  result=client.post("/api/matches/match-076/corrections",json={
   "kind":"score","reason":"Placar revisado pela mesa", "actor":"operador",
   "home_score":1,"away_score":0})
  assert result.status_code==201,result.text
  assert client.get("/api/matches/match-076/state").json()["match"]["home_score"]==1
  assert client.get("/api/state").json()["data"]["match"]["home_score"]==0
  assert len(client.get("/api/matches/match-076/corrections").json())==1

def test_playback_js_respects_one_timer_and_waits_for_pending_request():
 js=(ROOT/"app/static/app.js").read_text(encoding="utf-8")
 for name in ("GameNowPlayback.create(","pauseAndDrain()","demoPlayback.observe(snapshot)"):
  assert name in js
 node=shutil.which("node")
 if not node:pytest.skip("Node.js unavailable locally; CI executes unit scenarios")
 result=subprocess.run([node,"--test",str(ROOT/"tests/test_demo_playback.cjs")],
                       capture_output=True,text=True,timeout=20)
 assert result.returncode==0,result.stdout+"\n"+result.stderr
 assert "# fail 0" in result.stdout
