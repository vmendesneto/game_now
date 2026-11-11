"""GN-074: end-to-end registration API flow and visible UI contract."""
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
MATCH = {"id": "gn074-match",
 "home":{"id":"club-h","name":"Azul","short_name":"AZU","color":"#4990FF","attack_direction":"left_to_right"},
 "away":{"id":"club-a","name":"Vermelho","short_name":"VER","color":"#F26C69","attack_direction":"right_to_left"},
 "period":"first_half","match_seconds":0,"home_score":0,"away_score":0}
PLAYERS = [
 {"id":"player-1","team_id":"club-h","name":"João","number":10,"aliases":[],"starter":True,"position":"forward"},
 {"id":"player-2","team_id":"club-a","name":"Pedro","number":9,"aliases":[],"starter":True,"position":"forward"}]
SOURCES = [
 {"id":"source-radio","name":"Rádio teste","kind":"radio","url":"https://radio.example.org/live","enabled":True,"status":"offline"},
 {"id":"source-youtube","name":"YouTube teste","kind":"youtube","url":"https://youtu.be/AbCdEf12345","enabled":False,"status":"offline"}]

def test_configure_in_three_steps_and_reopen_sqlite(tmp_path):
 db=tmp_path/"setup.sqlite3"
 with TestClient(create_app(db)) as client:
  html=client.get("/").text
  for element in ("setup-panel","setup-progress","setup-match","setup-roster","setup-sources",
                  "match-form","player-form","source-form"):
   assert f'id="{element}"' in html
  assert html.index("setup_progress.js")<html.index("app.js")
  assert "<audio" not in html and "<video" not in html
  assert client.post("/api/matches",json=MATCH).status_code==201
  assert client.put("/api/matches/gn074-match/players",json=PLAYERS).status_code==200
  assert client.put("/api/matches/gn074-match/sources",json=SOURCES).status_code==200
  assert client.get("/api/matches/gn074-match/players").json()==PLAYERS
  assert client.get("/api/matches/gn074-match/sources").json()==SOURCES
  assert client.get("/health").json()["sources"]=="synthetic_only"
 with TestClient(create_app(db)) as client:
  assert client.get("/api/matches/gn074-match").json()["home"]["name"]=="Azul"
  assert len(client.get("/api/matches/gn074-match/players").json())==2
  assert [s["kind"] for s in client.get("/api/matches/gn074-match/sources").json()]==["radio","youtube"]
  assert client.get("/api/state").json()["mode"]=="synthetic_demo"

def test_frontend_setup_counter_module():
 app_js=(ROOT/"app/static/app.js").read_text(encoding="utf-8")
 assert "GameNowSetup.describe(" in app_js
 assert "updateSetupProgress();" in app_js
 node=shutil.which("node")
 if not node: pytest.skip("Node.js unavailable locally; CI runs node tests")
 result=subprocess.run([node,"--test",str(ROOT/"tests/test_setup_progress.cjs")],
                       capture_output=True,text=True,timeout=20)
 assert result.returncode==0,result.stdout+"\n"+result.stderr
 assert "# fail 0" in result.stdout
