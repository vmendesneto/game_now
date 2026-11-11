"""GN-082: deterministic two-radio end-to-end diagnostic, not real streams."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.simulate_two_radios import run_scenario


def test_two_radios_calibrate_and_deduplicate_but_reject_commercial():
    report = run_scenario()
    assert report["mode"] == "synthetic_two_radio_diagnostics"
    assert report["clock_domain"] == "fixed_simulated_utc_capture_times"
    assert report["real_audio_tested"] is False
    assert report["persisted"] is False
    offsets = {row["source_id"]: row for row in report["delay"]["estimates"]}
    assert offsets["radio-a"]["status"] == "reference"
    assert offsets["radio-a"]["relative_delay_seconds"] == 0
    assert offsets["radio-b"]["status"] == "aligned"
    assert offsets["radio-b"]["relative_delay_seconds"] == 8
    assert offsets["radio-b"]["common_events"] == 2

    combined = report["deduplication"]
    assert combined["input_candidates"] == 3
    assert combined["discarded_non_live"] == ["ad-a"]
    assert combined["output_groups"] == 1
    assert combined["persisted"] is False
    group = combined["groups"][0]
    assert group["merged"] is True
    assert group["source_ids"] == ["radio-a", "radio-b"]
    assert group["segment_ids"] == ["goal-a", "goal-b"]
    assert group["aligned_at"].startswith("2026-11-11T15:00:44")


def test_failover_conflict_silence_and_expiration_never_authorize_state_write():
    timeline = run_scenario()["timeline"]
    assert [step["phase"] for step in timeline] == [
        "aligned_live", "commercial_failover",
        "contradictory_reports", "both_silent",
    ]
    assert [step["selection"]["active_source_id"] for step in timeline] == [
        "radio-a", "radio-b", "radio-a", None,
    ]
    assert [step["selection"]["transition"] for step in timeline] == [
        "selected", "switched", "switched", "lost",
    ]
    assert [step["fusion"]["reason"] for step in timeline] == [
        "consistent_candidate", "missing_explicit_team_or_zone",
        "conflicting_source_evidence", "no_active_source",
    ]
    assert timeline[2]["fusion"]["conflicting_source_ids"] == ["radio-b"]
    assert [step["ball"]["uncertainty"] for step in timeline] == [
        "estimated", "uncertain", "expired", "expired",
    ]
    assert timeline[0]["ball"]["zone"] == {"band": 3, "lane": "left"}
    for step in timeline[1:]:
        assert step["ball"]["zone"] is None
        assert step["ball"]["team_id"] is None
        assert step["ball"]["player_id"] is None
    for step in timeline:
        assert step["selection"]["persisted"] is False
        assert step["fusion"]["persisted"] is False
        assert step["ball"]["persisted"] is False
        assert step["selection"]["eligible_for_state_update"] is False
        assert step["fusion"]["eligible_for_state_update"] is False
        assert step["ball"]["eligible_for_state_update"] is False


def test_scenario_is_byte_for_byte_reproducible_and_cli_is_text_only():
    report = run_scenario()
    assert report == run_scenario()
    root = Path(__file__).resolve().parents[1]
    cli = subprocess.run(
        [sys.executable, "-m", "scripts.simulate_two_radios"],
        cwd=root, capture_output=True, text=True, timeout=30,
    )
    assert cli.returncode == 0, cli.stderr
    assert json.loads(cli.stdout) == report
    serialized = json.dumps(report)
    for forbidden in ("http://", "https://", "audio_base64", "raw_pcm", "video_frame"):
        assert forbidden not in serialized
