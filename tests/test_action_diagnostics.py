"""Reanalysis is bounded, read-only and distinguishable from original decisions."""
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.asr_windows import WindowTranscript
from app.contracts import AudioSource
from app.action_diagnostics import diagnose_actions
from app.action_diagnostics import archive_path, load_saved_diagnostics, MAX_ARCHIVE_BYTES
import json
from app.main import create_app
from tests.test_narration_tracking import game


def test_reanalysis_preserves_phrase_source_and_explicit_uncertainty_without_mutating_snapshot():
    entry={"source_id":"radio-one","sequence":1,"start_seconds":6,"end_seconds":12,
           "text":"Caio recebeu. Beto recuperou.","captured_at":"2026-11-12T00:00:00Z","processed_at":"2026-11-12T00:00:01Z"}
    snapshot={"entries":[entry,{**entry,"source_id":"not-registered"}]}
    source=AudioSource(id="radio-one",name="Fonte",kind="youtube",url="https://www.youtube.com/watch?v=test")
    report=diagnose_actions(game(),snapshot,[source],{"source_id":"radio-one","requested_start_seconds":575})
    assert len(report["windows"])==1 and report["windows"][0]["text"]==entry["text"]
    assert [a["player_id"] for a in report["windows"][0]["actions"]]==["caio","beto"]
    assert report["windows"][0]["requested_video_start_seconds"]==581
    assert not report["runtime_selection_reconstructed"] and not report["video_seek_verified"]
    assert not report["persisted"] and "actions" not in entry


def test_diagnostic_endpoint_uses_retained_text_after_stop_and_never_writes_match(tmp_path):
    match=game();app=create_app(tmp_path/"audit.sqlite3")
    with TestClient(app) as client:
        data=match.model_dump(mode="json");players=data.pop("players")
        assert client.post("/api/matches",json=data).status_code==201
        base="/api/matches/"+match.id
        assert client.put(base+"/players",json=players).status_code==200
        assert client.put(base+"/sources",json=[{"id":"radio-one","name":"Fonte","kind":"youtube","url":"https://www.youtube.com/watch?v=test"}]).status_code==200
        app.state.transcript_feed.publish(match.id,"radio-one",WindowTranscript(source_id="radio-one",sequence=0,
            start_seconds=0,end_seconds=12,language="pt",raw_text="Caio recebeu",new_text="Caio recebeu"),captured_at=datetime.now(timezone.utc))
        app.state.transcript_feed.set_state(match.id,"radio-one","stopped")
        before=client.get(base+"/state").json()
        report=client.get(base+"/actions/diagnostics").json()
        assert report["windows"][0]["actions"][0]["player_id"]=="caio"
        assert report["basis"]=="reanalysis_of_retained_text_with_current_roster"
        assert not report["original_context_verified"]
        assert client.get(base+"/state").json()==before
        assert client.get("/api/matches/missing/actions/diagnostics").status_code==404


def test_action_geometry_and_ui_script_order_run_in_node():
    node=shutil.which("node")
    if not node:pytest.skip("Node available in CI")
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([node,"--test",str(root/"tests/test_action_audit.cjs")],capture_output=True,text=True,encoding="utf-8",timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    html=(root/"app/static/index.html").read_text(encoding="utf-8")
    assert html.index("ball_marker.js")<html.index("action_audit.js")<html.index("app.js")


def test_saved_analysis_is_opt_in_survives_stop_and_filters_removed_sources(tmp_path):
    match=game();source=AudioSource(id="radio-one",name="Fonte",kind="youtube",url="https://www.youtube.com/watch?v=test")
    report=diagnose_actions(match,{"entries":[]},[source],{})
    report["windows"]=[{"source_id":"radio-one"},{"source_id":"removed-source"}]
    root=tmp_path/"action-audits";root.mkdir()
    path=archive_path(root,match.id);path.write_text(json.dumps(report),encoding="utf-8")
    loaded=load_saved_diagnostics(root,match,[source])
    assert loaded["saved_report"] and loaded["current_context_matches"]
    assert loaded["windows"]==[{"source_id":"radio-one"}]
    match.players[0].name="Novo nome"
    assert not load_saved_diagnostics(root,match,[source])["current_context_matches"]
    assert path.read_text(encoding="utf-8")==json.dumps(report)


def test_archive_rejects_wrong_match_malformed_or_oversized_files(tmp_path):
    match=game();path=archive_path(tmp_path,match.id)
    path.write_text('{"match_id":"another","windows":[]}',encoding="utf-8")
    with pytest.raises(ValueError):load_saved_diagnostics(tmp_path,match,[])
    path.write_text('broken',encoding="utf-8")
    with pytest.raises(ValueError):load_saved_diagnostics(tmp_path,match,[])
    with path.open('wb') as stream:stream.truncate(MAX_ARCHIVE_BYTES+1)
    with pytest.raises(ValueError):load_saved_diagnostics(tmp_path,match,[])
