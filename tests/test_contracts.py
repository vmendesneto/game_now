import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.contracts import ContractBundle, FootballEvent, Zone

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name,segments,events", [
    ("live_play.json", 1, 1),
    ("commercial.json", 1, 0),
    ("two_sources_delayed.json", 2, 1),
])
def test_contract_fixtures(name, segments, events):
    data = json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))
    bundle = ContractBundle.model_validate(data)
    assert len(bundle.segments) == segments
    assert len(bundle.events) == events
    schema = json.loads((ROOT / "schemas" / "v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)


def test_schema_is_versioned_and_reproducible():
    committed = json.loads((ROOT / "schemas" / "v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(committed)
    assert committed == ContractBundle.model_json_schema()
    assert committed["properties"]["schema_version"]["default"] == "1.0.0"


def test_invalid_unknown_team_rejected():
    data = json.loads((ROOT / "fixtures" / "live_play.json").read_text(encoding="utf-8"))
    data["events"][0]["team_id"] = "other-team"
    with pytest.raises(ValidationError, match="Unknown team"):
        ContractBundle.model_validate(data)


def test_invalid_probability_and_zone_rejected():
    data = json.loads((ROOT / "fixtures" / "live_play.json").read_text(encoding="utf-8"))
    data["events"][0]["confidences"]["zone"] = 1.4
    with pytest.raises(ValidationError):
        ContractBundle.model_validate(data)
    with pytest.raises(ValidationError):
        Zone(band=6, lane="center")


def test_timezone_and_capture_order_rejected():
    data = json.loads((ROOT / "fixtures" / "live_play.json").read_text(encoding="utf-8"))
    data["segments"][0]["captured_at"] = "2026-11-10T16:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        ContractBundle.model_validate(data)
    data["segments"][0]["captured_at"] = "2026-11-10T16:00:00+00:00"
    data["segments"][0]["transcribed_at"] = "2026-11-10T15:59:00+00:00"
    with pytest.raises(ValidationError, match="precede"):
        ContractBundle.model_validate(data)


def test_canonical_event_has_both_source_observations():
    data = json.loads((ROOT / "fixtures" / "two_sources_delayed.json").read_text(encoding="utf-8"))
    event = FootballEvent.model_validate(data["events"][0])
    assert len(event.source_ids) == len(event.segment_ids) == 2
    assert data["segments"][0]["captured_at"] != data["segments"][1]["captured_at"]
    assert event.kind.value == "goal"
