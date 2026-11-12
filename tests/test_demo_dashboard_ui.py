"""GN-072: verify complete demo score/event/clock UI against real API snapshots."""
from pathlib import Path
import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_demo_dashboard_wiring_and_safe_text_rendering():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert html.index("demo_scoreboard.js") < html.index("app.js")
    for element_id in (
        "home-score", "away-score", "clock", "direction", "action",
        "last-confirmed-event", "last-text", "possession", "player",
        "confidence", "ball-status",
    ):
        assert f'id="{element_id}"' in html
    assert 'GameNowScoreboard.summary(snapshot)' in js
    assert 'summary.currentAction' in js
    assert 'summary.latestConfirmed' in js
    assert 'summary.clock' in js
    assert '.textContent=summary.lastText' in js
    assert 'aria-label="Placar da demonstração"' in html


def test_node_dashboard_presenter_unit_cases():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed; GitHub Actions provides Node")
    tests = ROOT / "tests" / "test_demo_scoreboard.cjs"
    check = subprocess.run(
        [node, "--check", str(STATIC / "demo_scoreboard.js")],
        capture_output=True, text=True, timeout=15,
    )
    assert check.returncode == 0, check.stderr
    run = subprocess.run(
        [node, "--test", str(tests)], capture_output=True, text=True, timeout=30,
    )
    assert run.returncode == 0, run.stdout + "\n" + run.stderr
    assert "# fail 0" in run.stdout


def test_real_demo_http_scenario_matches_every_visible_step(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed; GitHub Actions provides Node")
    with TestClient(create_app(tmp_path / "ui-demo.sqlite3")) as client:
        first = client.get("/api/state")
        assert first.status_code == 200
        snapshots = [first.json()]
        for step in range(1, 9):
            response = client.post("/api/demo/next")
            assert response.status_code == 200
            snapshots.append(response.json())
            assert snapshots[-1]["step"] == step
        assert client.post("/api/demo/reset").json()["step"] == 0

    js = (
        "const fs=require('node:fs');"
        "const mod=require(process.argv[1]);"
        "const list=JSON.parse(fs.readFileSync(0,'utf8'));"
        "process.stdout.write(JSON.stringify(list.map(mod.summary)))"
    )
    proc = subprocess.run(
        [node, "-e", js, str(STATIC / "demo_scoreboard.js")],
        input=json.dumps(snapshots), text=True, encoding="utf-8",
        capture_output=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    summaries = json.loads(proc.stdout)
    assert [entry["currentAction"] for entry in summaries] == [
        "Aguardando o primeiro lance",
        "Posse identificada",
        "Relato repetido · lance já contabilizado",
        "Intervalo comercial · sem novo lance",
        "Cruzamento",
        "GOL!",
        "Relato repetido · lance já contabilizado",
        "Replay · sem novo lance",
        "Sem novo lance confirmado",
    ]
    assert [entry["homeScore"] for entry in summaries] == [0,0,0,0,0,1,1,1,1]
    assert [entry["awayScore"] for entry in summaries] == [0]*9
    assert [entry["clock"] for entry in summaries] == [
        "00:00 · 1º tempo", "12:10 · 1º tempo", "12:10 · 1º tempo",
        "12:10 · 1º tempo", "12:36 · 1º tempo", "13:31 · 1º tempo",
        "13:31 · 1º tempo", "13:31 · 1º tempo", "13:40 · 1º tempo",
    ]
    assert "GOL!" in summaries[-1]["latestConfirmed"]
    assert "GOL!" in summaries[7]["latestConfirmed"]
