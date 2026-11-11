"""GN-057: local LLM is optional, JSON strict and always read-only."""
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts import Zone
from app.llm_local import (
    LLMCompareRequest, compare_language, parse_strict_suggestion,
    query_local_ollama,
)
from test_narration_entities import match

COMPLEX = "O Azul encontrou espaço na intermediária ofensiva pelo lado direito"
VALID = {
    "status": "explicit", "team_id": "team-azul", "player_id": None,
    "zone": {"band": 4, "lane": "right"}, "event_kind": None,
    "reason": "Hipótese de faixa ofensiva pelo lado direito",
}


def response(data=VALID):
    return json.dumps(data, ensure_ascii=False)


def test_disabled_is_rules_only_and_never_calls_model():
    def never(*_):
        raise AssertionError("disabled must not contact localhost")

    outcome = compare_language(match(), LLMCompareRequest(text=COMPLEX), transport=never)
    assert outcome.status == "disabled"
    assert outcome.baseline.category == "unknown"
    assert outcome.baseline.region.zone is None
    assert outcome.suggestion is None
    assert outcome.eligible_for_state_update is False


def test_complex_language_comparison_exposes_unverified_diagnostic_suggestion():
    calls = []

    def fake(prompt, model, timeout):
        calls.append((prompt, model, timeout))
        return response()

    result = compare_language(match(), LLMCompareRequest(
        text=COMPLEX, use_local_llm=True, model="qwen2.5:3b",
    ), transport=fake)
    assert result.status == "suggestion"
    assert result.baseline.region.status == "unknown"
    assert result.baseline.possession.status == "unknown"
    assert result.suggestion.zone == Zone(band=4, lane="right")
    assert result.eligible_for_state_update is False
    assert len(calls) == 1 and '"id": "team-azul"' in calls[0][0]
    assert calls[0][1:] == ("qwen2.5:3b", 8.0)


@pytest.mark.parametrize("phrase", [
    "No replay, Azul com a bola na própria área pela esquerda",
    "Oferecimento da loja: Azul com a bola",
    "Na minha opinião o Azul chuta na área",
    "Meu amigo, o Azul chuta",
])
def test_non_live_is_blocked_without_even_contacting_local_model(phrase):
    def never(*_):
        raise AssertionError("non-live must not contact model")

    out = compare_language(match(), LLMCompareRequest(
        text=phrase, use_local_llm=True), transport=never)
    assert out.status == "blocked"
    assert out.suggestion is None
    assert out.eligible_for_state_update is False


def test_stoppage_rejects_a_request_before_contacting_model():
    game = match()
    game.period = "half_time"
    result = compare_language(game, LLMCompareRequest(
        text=COMPLEX, use_local_llm=True),
        transport=lambda *_: pytest.fail("should not call"))
    assert result.status == "blocked" and result.reason == "not_playing"


@pytest.mark.parametrize("raw", [
    "not json",
    "```json\n" + response() + "\n```",
    '[1, 2, 3]',
    '{"status": "explicit", "status": "unknown", "reason": "duplicate"}',
    response({**VALID, "extra": "not accepted"}),
    response({**VALID, "zone": {"band": "4", "lane": "right"}}),
    response({**VALID, "zone": {"band": 16, "lane": "right"}}),
    response({**VALID, "zone": {"band": 4, "lane": "diagonal"}}),
    response({**VALID, "event_kind": "var"}),
    response({**VALID, "status": "unknown"}),
    response({**VALID, "status": "explicit", "team_id": None, "zone": None}),
    response({**VALID, "player_id": "fake-player"}),
    response({**VALID, "team_id": "nonexistent"}),
    response({**VALID, "player_id": "ver-9"}),
    " " * 8193,
])
def test_invalid_json_hallucinations_and_inconsistent_ids_are_rejected(raw):
    out = compare_language(
        match(), LLMCompareRequest(text=COMPLEX, use_local_llm=True),
        transport=lambda *_: raw,
    )
    assert out.status == "rejected", (raw[:80], out.status)
    assert out.suggestion is None
    assert out.eligible_for_state_update is False


def test_strict_parser_rejects_nonfinite_and_accepts_genuine_json():
    assert parse_strict_suggestion(response()).zone.band == 4
    with pytest.raises(ValueError):
        parse_strict_suggestion(response().replace('"band": 4', '"band": NaN'))


def test_abstention_is_not_an_assertion():
    unknown = {"status": "unknown", "team_id": None, "player_id": None,
               "zone": None, "event_kind": None, "reason": "Sem evidência"}
    out = compare_language(match(), LLMCompareRequest(
        text=COMPLEX, use_local_llm=True),
        transport=lambda *_: response(unknown))
    assert out.status == "unknown" and out.suggestion is None


def test_explicit_rules_override_conflicting_local_model_suggestions():
    text = "Azul com a bola na própria área pela esquerda"
    bad = {**VALID, "zone": {"band": 4, "lane": "right"}}
    out = compare_language(match(), LLMCompareRequest(
        text=text, use_local_llm=True), transport=lambda *_: response(bad))
    assert out.baseline.region.zone == Zone(band=1, lane="left")
    assert out.status == "rejected" and out.suggestion is None

    bad = {**VALID, "zone": {"band": 1, "lane": "left"}, "team_id": "team-vermelho"}
    assert compare_language(match(), LLMCompareRequest(
        text=text, use_local_llm=True),
        transport=lambda *_: response(bad)).reason == "contradicts_explicit_rule_possession"


def test_model_errors_are_sanitized_and_do_not_break_fallback():
    def failure(*_):
        raise OSError("Sensitive local path /tmp/private:9999")

    out = compare_language(match(), LLMCompareRequest(
        text=COMPLEX, use_local_llm=True), transport=failure)
    assert out.status == "unavailable" and out.reason == "local_model_failed"
    assert "private" not in out.model_dump_json()


def test_local_http_transport_fixed_loopback_no_redirects(monkeypatch):
    captured = {}

    class Response:
        status = 200

        def read(self, length):
            captured["limit"] = length
            return json.dumps({"response": response()}).encode()

    class Connection:
        def __init__(self, host, port, timeout):
            captured["address"] = (host, port, timeout)

        def request(self, method, path, body, headers):
            captured.update(method=method, path=path,
                            data=json.loads(body), headers=headers)

        def getresponse(self):
            return Response()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr("app.llm_local.http.client.HTTPConnection", Connection)
    raw = query_local_ollama("prompt without credentials", "qwen2.5:3b", 2)
    assert parse_strict_suggestion(raw).zone == Zone(band=4, lane="right")
    assert captured["address"] == ("127.0.0.1", 11434, 2)
    assert captured["method"] == "POST" and captured["path"] == "/api/generate"
    assert captured["data"]["stream"] is False
    assert captured["data"]["format"] == "json"
    assert captured["closed"] and captured["limit"] == 16385


@pytest.mark.parametrize("payload", [
    {"text": ""},
    {"text": "x" * 2049},
    {"text": COMPLEX, "model": "http://example.org"},
    {"text": COMPLEX, "model": "model with spaces"},
    {"text": COMPLEX, "timeout_seconds": 0},
    {"text": COMPLEX, "timeout_seconds": 21},
])
def test_input_validation(payload):
    with pytest.raises(ValidationError):
        LLMCompareRequest(**payload)


def test_read_only_api_and_optional_model_switch(monkeypatch, tmp_path):
    from app.main import create_app
    game = match()
    monkeypatch.setattr("app.llm_local.query_local_ollama",
                        lambda *_: response())
    endpoint = "/api/matches/match-051/compare-language"
    with TestClient(create_app(tmp_path / "game.db")) as client:
        assert client.post("/api/matches", json=game.model_dump(
            mode="json", exclude={"players"})).status_code == 201
        before = client.get("/api/matches/match-051/state").json()
        disabled = client.post(endpoint, json={"text": COMPLEX})
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "disabled"
        enabled = client.post(endpoint, json={"text": COMPLEX, "use_local_llm": True})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["status"] == "suggestion"
        assert enabled.json()["eligible_for_state_update"] is False
        assert client.get("/api/matches/match-051/state").json() == before
        assert client.post(endpoint, json={
            "text": "x" * 2049, "use_local_llm": True,
        }).status_code == 422
        assert client.post("/api/matches/missing/compare-language",
                           json={"text": COMPLEX}).status_code == 404
