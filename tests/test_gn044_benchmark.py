"""GN-044: benchmark/metric tests with mock text (not real Windows or ASR)."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from app.asr import ASRResult
from scripts import benchmark_gn044_whisper as gn044


def sample_pcm(seconds=1):
    return b"\x01\x00" * (16000 * seconds)


def write_fixture(tmp_path: Path, *, reference: str = "A bola está com o time") -> Path:
    wav_file = tmp_path / "test.wav"
    with wave.open(str(wav_file), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(sample_pcm())
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"wav": "test.wav", "reference_text": reference}]), encoding="utf-8")
    return manifest


def test_manifest_is_local_bounded_and_input_validated(tmp_path):
    manifest = write_fixture(tmp_path)
    samples = gn044.load_manifest(manifest)
    assert len(samples) == 1
    assert samples[0].pcm == sample_pcm()
    assert samples[0].reference_text == "A bola está com o time"
    for rows in (
        [], [{"wav": "https://example.com/x.wav", "reference_text": "ok"}],
        [{"wav": "test.wav", "reference_text": "?!?"}],
        [{"wav": "test.wav", "reference_text": ""}],
        [{"wav": "test.wav", "reference_text": "ok", "extra": 1}],
        [{"wav": "test.wav", "reference_text": "ok"}] * 9,
    ):
        manifest.write_text(json.dumps(rows), encoding="utf-8")
        with pytest.raises(ValueError):
            gn044.load_manifest(manifest)
    manifest.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        gn044.load_manifest(manifest)


def test_score_measures_wer_and_duration_without_leaking_prediction():
    class Fake:
        def __init__(self):
            self.calls = 0
        def transcribe_pcm(self, pcm):
            self.calls += 1
            return ASRResult("fake", "pt", len(pcm) / 32000,
                             "A bola esta com equipe", ())
    times = iter([1.0, 1.25, 2.0, 2.75])
    rows = [gn044.BenchmarkSample(sample_pcm(), "A bola está com o time")] * 2
    model = Fake()
    result = gn044.score_samples(rows, model, clock=lambda: next(times))
    assert model.calls == 2
    assert result["reference_words"] == 12
    assert result["word_errors"] == 4
    assert result["wer"] == round(4 / 12, 4)
    assert result["audio_seconds"] == 2.0
    assert result["latency_median_seconds"] == .25
    assert result["latency_p95_seconds"] == .75
    assert result["inference_wall_seconds_per_audio_second"] == .5
    assert "text" not in result and "pcm" not in result


def test_empty_samples_and_bad_model_settings_rejected():
    with pytest.raises(ValueError):
        gn044.score_samples([], None)
    for kwargs in ({"model": "large", "device": "cpu", "cpu_threads": 2, "beam_size": 1},
                   {"model": "tiny", "device": "metal", "cpu_threads": 2, "beam_size": 1},
                   {"model": "tiny", "device": "cpu", "cpu_threads": 0, "beam_size": 1}):
        with pytest.raises(ValueError):
            gn044.make_transcriber(**kwargs)


def test_independent_process_per_model_and_safe_output(monkeypatch, tmp_path):
    manifest = write_fixture(tmp_path)
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        assert command[-1] == "--_worker"
        assert "--permission-confirmed" in command
        model = command[command.index("--models") + 1]
        device = command[command.index("--device") + 1]
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            {"model": model, "device": device, "wer": 0.5}
        ), stderr="")
    monkeypatch.setattr(gn044.subprocess, "run", fake_run)
    output = gn044.run_independent_models(manifest, models=["tiny", "base"])
    assert len(commands) == 2
    assert output["independent_process_per_model"] is True
    assert [m["model"] for m in output["measurements"]] == ["tiny", "base"]
    assert output["text_included"] is False
    for selection in (["tiny", "tiny"], ["large"], []):
        with pytest.raises(ValueError):
            gn044.run_independent_models(manifest, models=selection)


def test_failing_subprocess_does_not_leak_private_stderr(monkeypatch, tmp_path):
    manifest = write_fixture(tmp_path)
    monkeypatch.setattr(gn044.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(returncode=1, stdout="", stderr="SECRET-PCM-TEXT"))
    with pytest.raises(RuntimeError) as exc:
        gn044.run_independent_models(manifest, models=["tiny"])
    assert "SECRET" not in str(exc.value)


def test_worker_reports_real_model_with_mock_backend(monkeypatch, capsys, tmp_path):
    manifest = write_fixture(tmp_path)
    class Fake:
        def transcribe_pcm(self, pcm):
            return ASRResult("mock", "pt", len(pcm) / 32000,
                             "A bola está com o time", ())
    monkeypatch.setattr(gn044, "make_transcriber", lambda *a, **k: Fake())
    assert gn044.main([
        "--manifest", str(manifest), "--models", "tiny",
        "--permission-confirmed", "--_worker",
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["wer"] == 0.0
    assert result["model"] == "tiny"
    assert result["samples"] == 1
    assert not any(k in result for k in ("text", "pcm", "reference_text"))
    assert result["peak_process_rss_mb"] is None or result["peak_process_rss_mb"] > 0


def test_cli_requires_confirmation(tmp_path):
    with pytest.raises(SystemExit) as error:
        gn044.main(["--manifest", str(write_fixture(tmp_path))])
    assert error.value.code == 2
