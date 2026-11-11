"""GN-066: read-only fusion diagnostics, manual offsets and API validation."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from app.fusion_diagnostics import FusionDiagnosticRequest, preview_fusion_diagnostics
from app.main import create_app
from test_narration_entities import match

ROOT = Path(__file__).resolve().parents[1]
T = datetime(2026, 11, 11, 15, 0, 0, tzinfo=timezone.utc)


def instant(seconds):
    return (T + timedelta(seconds=seconds)).isoformat()


def payload(offset=0, *, conflicting=False):
    return {
        "selection": {
            "evaluated_at": instant(45),
            "observations": [
                {"source_id": "radio-a", "connection_status": "online",
                 "narration_kind": "live_play", "captured_at": instant(40),
                 "received_at": instant(44), "signal_strength": .9},
                {"source_id": "radio-b", "connection_status": "online",
                 "narration_kind": "live_play", "captured_at": instant(42),
                 "received_at": instant(44), "signal_strength": .8},
            ],
        },
        "fusion": {
            "evaluated_at": instant(45), "observations": [
                {"source_id": "radio-a", "segment_id": "seg-a",
                 "aligned_at": instant(30), "team_id": "team-azul",
                 "zone": {"band": 3, "lane": "left"}},
                {"source_id": "radio-b", "segment_id": "seg-b",
                 "aligned_at": instant(38),
                 "team_id": "team-vermelho" if conflicting else "team-azul",
                 "zone": {"band": 3, "lane": "left"}},
            ],
        },
        "manual_offsets": [{"source_id": "radio-b", "seconds": offset}],
    }


def diagnose(data):
    return preview_fusion_diagnostics(
        FusionDiagnosticRequest.model_validate(data),
        registered_source_ids={"radio-a", "radio-b"},
    )


def test_manual_offset_correction_changes_conflict_preview_not_state():
    aligned = diagnose(payload(offset=8))
    assert aligned.selection.active_source_id == "radio-a"
    assert aligned.fusion.accepted_for_preview is True
    assert aligned.fusion.proposed_play.source_id == "radio-a"
    assert aligned.calibration[1].manual_offset_seconds == 8
    assert aligned.calibration[1].original_aligned_at == T + timedelta(seconds=38)
    assert aligned.calibration[1].preview_aligned_at == T + timedelta(seconds=30)
    assert aligned.persisted is False and aligned.eligible_for_state_update is False
    conflicting = diagnose(payload(offset=8, conflicting=True))
    assert conflicting.fusion.reason == "conflicting_source_evidence"
    assert conflicting.fusion.conflicting_source_ids == ["radio-b"]
    assert conflicting.fusion.accepted_for_preview is False
    assert diagnose(payload(offset=0, conflicting=True)).fusion.accepted_for_preview is True


def test_manual_offsets_not_applied_to_source_selection_or_auto_delay():
    baseline = diagnose(payload(offset=0))
    shifted = diagnose(payload(offset=8))
    assert baseline.selection == shifted.selection
    assert baseline.calibration[0].preview_aligned_at == baseline.calibration[0].original_aligned_at
    assert any(entry.step == "manual_offset" and entry.source_id == "radio-b" for entry in shifted.trace)
    assert shifted.trace[-1].reason == "consistent_candidate"
    assert all("http" not in entry.reason for entry in shifted.trace)


@pytest.mark.parametrize("invalid", [
    [{"source_id": "radio-b", "seconds": 121}],
    [{"source_id": "radio-b", "seconds": float("inf")}],
    [{"source_id": "radio-b", "seconds": 5}, {"source_id": "radio-b", "seconds": 3}],
])
def test_reject_unsafe_manual_offsets(invalid):
    data = payload()
    data["manual_offsets"] = invalid
    with pytest.raises(ValueError):
        diagnose(data)


def test_unknown_source_and_wrong_clock_domain_rejected():
    data = payload()
    with pytest.raises(ValueError, match="saved match"):
        preview_fusion_diagnostics(FusionDiagnosticRequest.model_validate(data),
                                   registered_source_ids={"radio-a"})
    data = payload()
    data["fusion"]["evaluated_at"] = instant(44)
    with pytest.raises(ValueError):
        FusionDiagnosticRequest.model_validate(data)
    data = payload()
    data["fusion"]["active_source_id"] = "radio-b"
    with pytest.raises(ValueError):
        FusionDiagnosticRequest.model_validate(data)


def test_match_scoped_api_is_read_only_and_explains_reason(tmp_path: Path):
    with TestClient(create_app(tmp_path / "gn066.sqlite3")) as client:
        game = match()
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        sources = [
            {"id": "radio-a", "name": "Radio A", "kind": "radio", "url": None, "enabled": True},
            {"id": "radio-b", "name": "Radio B", "kind": "radio", "url": None, "enabled": True},
        ]
        assert client.put("/api/matches/match-051/sources", json=sources).status_code == 200
        before = client.get("/api/matches/match-051/state").json()
        response = client.post("/api/matches/match-051/fusion/diagnostics/preview",
                               json=payload(8))
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["fusion"]["reason"] == "consistent_candidate"
        assert data["selection"]["active_source_id"] == "radio-a"
        assert data["calibration"][1]["manual_offset_seconds"] == 8
        assert data["persisted"] is False and data["eligible_for_state_update"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post("/api/matches/missing/fusion/diagnostics/preview",
                           json=payload()).status_code == 404
        malformed = payload()
        malformed["selection"]["observations"][1]["source_id"] = "other-source"
        assert client.post("/api/matches/match-051/fusion/diagnostics/preview",
                           json=malformed).status_code == 422


def test_ui_has_a_diagnostics_panel_and_frontend_node_suite():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    script = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    for name in ("fusion-panel", "fusion-form", "fusion-json", "fusion-offsets",
                 "fusion-example", "fusion-result", "fusion-trace"):
        assert f'id="{name}"' in html
    assert html.index("fusion_diagnostics.js") < html.index("app.js")
    assert "GameNowFusion.prepare(" in script
    assert "GameNowFusion.describe(" in script
    assert "<audio" not in html and "<video" not in html
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable")
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests/test_fusion_diagnostics.cjs")],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
