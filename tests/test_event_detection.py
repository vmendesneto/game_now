"""GN-054: labeled synthetic evidence, abstention and API that never writes."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts import EventKind
from app.event_detection import EventRequest, detect_event
from test_narration_entities import match


@pytest.mark.parametrize("case", json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "events_labeled.json").read_text(
        encoding="utf-8")))
def test_labeled_synthetic_sentences(case):
    response = detect_event(match(), EventRequest(text=case["text"]))
    assert (response.kind.value if response.kind is not None else None) == case["expected"], (
        case["text"], response)
    assert response.status == ("explicit" if case["expected"] is not None else "unknown")
    if response.kind is not None:
        assert response.cue and response.reason == "unique_affirmative_live_event_cue"


def test_one_type_even_when_two_equivalent_phrases_are_present():
    result = detect_event(match(), EventRequest(text="O goleiro defendeu o chute"))
    assert result.status == "explicit" and result.kind == EventKind.SAVE


@pytest.mark.parametrize("text", [
    "Azul chuta e marca o gol",
    "Vermelho passa a bola, Azul cruza na área",
    "Bruno chutou e goleiro defendeu",
])
def test_multiple_actions_do_not_guess_one(text):
    result = detect_event(match(), EventRequest(text=text))
    assert result.status == "unknown" and result.reason == "conflicting_event_cues"
    assert result.kind is None


def test_stoppage_rejects_even_explicit_goal():
    game = match()
    game.period = "half_time"
    assert detect_event(game, EventRequest(text="Gol do Azul")).reason == "not_playing"
    game.period = "finished"
    assert detect_event(game, EventRequest(text="Gol do Azul")).reason == "not_playing"


def test_input_bounds():
    with pytest.raises(ValidationError):
        EventRequest(text="a" * 2049)
    with pytest.raises(ValidationError):
        EventRequest(text="")


def test_api_diagnostic_does_not_change_sqlite_score_or_ball(tmp_path):
    from app.main import create_app
    game = match()
    with TestClient(create_app(tmp_path / "game.sqlite3")) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        endpoint = "/api/matches/match-051/resolve-event"
        result = client.post(endpoint, json={"text": "Gooooool do Azul"})
        assert result.status_code == 200, result.text
        assert result.json()["kind"] == "goal" and result.json()["status"] == "explicit"
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(endpoint, json={"text": "x" * 2049}).status_code == 422
        assert client.post("/api/matches/missing/resolve-event",
                           json={"text": "Gol do Azul"}).status_code == 404
