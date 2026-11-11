"""GN-040: fast deterministic unit coverage without a model download."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import struct
from types import SimpleNamespace
import wave

import pytest

from app.asr import (
    ASRError, ASRSettings, BYTES_PER_SECOND, CPUTranscriber, asr_diagnostics,
    read_pcm_wav,
)


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        with wave.open(audio, "rb") as input_wav:
            assert input_wav.getnchannels() == 1
            assert input_wav.getsampwidth() == 2
            assert input_wav.getframerate() == 16_000
            self.calls.append((input_wav.readframes(input_wav.getnframes()), kwargs))
        segments = (
            SimpleNamespace(start=0.1, end=0.5, text=" A bola "),
            SimpleNamespace(start=0.5, end=0.9, text=" chegou ao gol. "),
        )
        return iter(segments), SimpleNamespace(language="pt")


def test_cpu_transcriber_lazily_initializes_model_once_and_forces_pt():
    model = FakeModel()
    creations = []
    def factory(name, **options):
        creations.append((name, options))
        return model
    transcriber = CPUTranscriber(ASRSettings(model="base", cpu_threads=4), model_factory=factory)
    assert not creations
    pcm = struct.pack("<h", 1200) * 16_000
    first = transcriber.transcribe_pcm(pcm)
    second = transcriber.transcribe_pcm(pcm)
    assert first == second
    assert first.language == "pt"
    assert first.text == "A bola chegou ao gol."
    assert first.seconds == 1.0
    assert len(first.segments) == 2
    assert creations == [("base", {
        "device": "cpu", "compute_type": "int8", "cpu_threads": 4, "num_workers": 1,
    })]
    assert model.calls[0][0] == pcm
    assert model.calls[0][1] == {
        "language": "pt", "beam_size": 3,
        "vad_filter": False, "condition_on_previous_text": False,
    }


@pytest.mark.parametrize("bad", [b"", b"x", "not bytes"])
def test_invalid_pcm_rejected_before_loading_model(bad):
    transcriber = CPUTranscriber(model_factory=lambda *a, **k: pytest.fail("loaded model"))
    with pytest.raises(ValueError, match="PCM"):
        transcriber.transcribe_pcm(bad)


def test_maximum_duration_bounded_before_loading():
    transcriber = CPUTranscriber(
        ASRSettings(max_seconds=1), model_factory=lambda *a, **k: pytest.fail("loaded")
    )
    with pytest.raises(ValueError, match="max_seconds"):
        transcriber.transcribe_pcm(b"\0" * (BYTES_PER_SECOND + 2))


@pytest.mark.parametrize("settings", [
    {"model": "large"}, {"cpu_threads": 0}, {"cpu_threads": 17},
    {"beam_size": 0}, {"max_seconds": 0}, {"max_seconds": 121},
])
def test_invalid_cpu_configuration(settings):
    with pytest.raises(ValueError):
        ASRSettings(**settings)


def test_read_wav_and_reject_wrong_format(tmp_path: Path):
    filename = tmp_path / "pt.wav"
    pcm = struct.pack("<h", 100) * 8_000
    with wave.open(str(filename), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(pcm)
    assert read_pcm_wav(filename) == pcm
    with pytest.raises(ValueError, match="max_seconds"):
        read_pcm_wav(filename, max_seconds=0)
    with wave.open(str(filename), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(pcm)
    with pytest.raises(ValueError, match="mono"):
        read_pcm_wav(filename)


def test_engine_failures_do_not_leak_model_urls_or_details():
    def bad_factory(*args, **kwargs):
        raise RuntimeError("private user URL https://example.test/key")
    with pytest.raises(ASRError, match="could not be initialized") as err:
        CPUTranscriber(model_factory=bad_factory).transcribe_pcm(b"\0\0" * 16_000)
    assert "example.test" not in str(err.value)


def test_health_probe_does_not_import_model():
    data = asr_diagnostics()
    assert data["device"] == "cpu"
    assert data["compute_type"] == "int8"
    assert data["model_loaded"] is False
    assert isinstance(data["installed"], bool)
