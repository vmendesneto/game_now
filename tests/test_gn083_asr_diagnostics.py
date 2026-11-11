"""GN-083: diagnostics for Windows ASR inference and local smoke check."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.asr import ASRError
from app.asr_diagnostics import asr_failure_details, sanitize_asr_message
from scripts.gn083_asr_check import main


def test_shows_root_cause_without_leaking_signed_urls_or_credentials():
    try:
        try:
            raise RuntimeError(
                "Cannot load DLL at https://cdn.test/model?token=hf_secretSECRET "
                "Bearer abcdef123456 access_token=hf_privateToken123"
            )
        except RuntimeError as internal:
            raise ASRError("CPU ASR inference failed") from internal
    except ASRError as error:
        details = asr_failure_details(error)
    assert details["exception_type"] == "RuntimeError"
    assert "Cannot load DLL" in details["exception_message"]
    assert "cdn.test" not in str(details)
    assert "abcdef123456" not in str(details)
    assert "hf_privateToken123" not in str(details)


def test_sanitizes_whitespace_and_long_errors():
    assert sanitize_asr_message(" \n x  y \n") == "x y"
    assert len(sanitize_asr_message("A" * 2000)) == 300


def test_smoke_check_success_has_no_transcription_text(monkeypatch, capsys):
    class FakeTranscriber:
        def __init__(self, settings):
            self.settings = settings

        def transcribe_pcm(self, pcm):
            assert len(pcm) == 6 * 32000
            return SimpleNamespace(
                model=self.settings.model, seconds=6.0,
                segments=(SimpleNamespace(text="do not print me"),)
            )

    monkeypatch.setattr("scripts.gn083_asr_check.CPUTranscriber", FakeTranscriber)
    assert main(["--model", "tiny"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": True, "model": "tiny", "seconds": 6.0,
        "segments": 1, "external_media_processed": False,
    }


def test_smoke_check_failure_displays_only_sanitized_root_cause(monkeypatch, capsys):
    class FailedTranscriber:
        def __init__(self, settings):
            pass

        def transcribe_pcm(self, pcm):
            try:
                raise OSError("Native error; see https://example.test/private?token=hf_XYZxyzxyz")
            except OSError as internal:
                raise ASRError("CPU ASR inference failed") from internal

    monkeypatch.setattr("scripts.gn083_asr_check.CPUTranscriber", FailedTranscriber)
    assert main([]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "CPU ASR inference failed"
    assert payload["root_cause"]["exception_type"] == "OSError"
    assert "Native error" in payload["root_cause"]["exception_message"]
    assert "example.test" not in str(payload)
    assert payload["external_media_processed"] is False


def test_cli_opt_in_diagnostics_no_media(monkeypatch, tmp_path, capsys):
    from scripts.gn083_audit import main as audit
    from app.contracts import Match, Team

    match = Match(
        id="match-test", home=Team(id="casa", name="Casa", short_name="CAS",
                                  color="#113366", attack_direction="left_to_right"),
        away=Team(id="fora", name="Fora", short_name="FOR",
                  color="#CC3355", attack_direction="right_to_left"),
    )
    match_file = tmp_path / "match.json"
    match_file.write_text(match.model_dump_json(), encoding="utf-8")
    async def failing(_url, _match, **_kwargs):
        try:
            raise RuntimeError("Missing DLL from https://secret.test/a")
        except RuntimeError as cause:
            raise ASRError("CPU ASR inference failed") from cause

    monkeypatch.setattr("scripts.gn083_audit.transcribe_youtube_source", failing)
    args = [
        "--match-json", str(match_file),
        "--youtube-url", "https://www.youtube.com/watch?v=Ls4qkPrh4Tk",
        "--permission-confirmed",
    ]
    with pytest.raises(SystemExit) as no_details:
        audit(args)
    assert no_details.value.code == 2
    assert "Missing DLL" not in capsys.readouterr().err
    with pytest.raises(SystemExit) as debug:
        audit(args + ["--diagnose-asr"])
    assert debug.value.code == 2
    msg = capsys.readouterr().err
    assert "Missing DLL" in msg
    assert "secret.test" not in msg
