"""GN-040: optional, bounded faster-whisper transcription on CPU.

Input is PCM s16le mono 16 kHz from GN-030/GN-031. Only text and metadata
leave this module; no network endpoint exposes the underlying audio.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from io import BytesIO
import json
from pathlib import Path
from typing import Any, Callable
import wave

SAMPLE_RATE = 16_000
BYTES_PER_SECOND = SAMPLE_RATE * 2
AVAILABLE_MODELS = ("tiny", "base", "small", "medium")


class ASRError(RuntimeError):
    """Transcription cannot proceed with the selected CPU configuration."""


@dataclass(frozen=True, slots=True)
class ASRSettings:
    model: str = "tiny"
    cpu_threads: int = 2
    beam_size: int = 3
    max_seconds: int = 30

    def __post_init__(self) -> None:
        if self.model not in AVAILABLE_MODELS:
            raise ValueError("Model must be one of: " + ", ".join(AVAILABLE_MODELS))
        if not 1 <= self.cpu_threads <= 16:
            raise ValueError("cpu_threads must be between 1 and 16")
        if not 1 <= self.beam_size <= 10:
            raise ValueError("beam_size must be between 1 and 10")
        if not 1 <= self.max_seconds <= 120:
            raise ValueError("max_seconds must be between 1 and 120")


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class ASRResult:
    model: str
    language: str
    seconds: float
    text: str
    segments: tuple[SpeechSegment, ...]


def asr_diagnostics() -> dict[str, object]:
    """Safe availability probe: no model download or inference during /health."""
    try:
        installed = find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        installed = False
    return {
        "engine": "faster-whisper", "installed": installed,
        "device": "cpu", "compute_type": "int8",
        "mode": "optional_cli", "model_loaded": False,
    }


def _default_model_factory() -> Callable[..., Any]:
    try:
        from faster_whisper import WhisperModel
    except (ImportError, OSError) as exc:
        raise ASRError(
            "faster-whisper is unavailable; install requirements-asr.txt"
        ) from exc
    return WhisperModel


class CPUTranscriber:
    """Lazy model initialization: the offline demo never downloads model weights."""

    def __init__(
        self,
        settings: ASRSettings | None = None,
        *,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings or ASRSettings()
        self._factory = model_factory
        self._model: Any = None

    def _load_model(self) -> Any:
        if self._model is None:
            factory = self._factory or _default_model_factory()
            try:
                self._model = factory(
                    self.settings.model,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=self.settings.cpu_threads,
                    num_workers=1,
                )
            except Exception as exc:
                raise ASRError(
                    "CPU model could not be initialized; check the model download/cache "
                    "and free RAM"
                ) from exc
        return self._model

    def transcribe_pcm(self, pcm: bytes) -> ASRResult:
        if not isinstance(pcm, bytes) or not pcm or len(pcm) % 2:
            raise ValueError("Expected nonempty sample-aligned PCM s16le bytes")
        if len(pcm) > self.settings.max_seconds * BYTES_PER_SECOND:
            raise ValueError("PCM exceeds max_seconds; split audio into windows")
        # A WAV file-like object is accepted by PyAV (used inside faster-whisper).
        # Keeping it in RAM avoids media files and keeps the input private.
        audio = BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm)
        audio.seek(0)
        duration = len(pcm) / BYTES_PER_SECOND
        try:
            segments, info = self._load_model().transcribe(
                audio,
                language="pt",
                beam_size=self.settings.beam_size,
                vad_filter=False,  # GN-036 will evaluate VAD independently.
                condition_on_previous_text=False,
            )
            # faster-whisper returns a generator: iteration performs inference.
            parsed: list[SpeechSegment] = []
            for segment in segments:
                text = str(segment.text).strip()
                if not text:
                    continue
                start = max(0.0, float(segment.start))
                end = max(start, float(segment.end))
                parsed.append(SpeechSegment(start=start, end=end, text=text))
            language = str(getattr(info, "language", "pt") or "pt")
        except ASRError:
            raise
        except Exception as exc:
            raise ASRError("CPU ASR inference failed") from exc
        return ASRResult(
            model=self.settings.model,
            language=language,
            seconds=duration,
            text=" ".join(part.text for part in parsed),
            segments=tuple(parsed),
        )


def read_pcm_wav(path: Path, *, max_seconds: int = 30) -> bytes:
    """Read only a bounded 16-kHz mono 16-bit WAV from local CLI, never a URL."""
    try:
        with wave.open(str(path), "rb") as wav:
            if (wav.getcomptype() != "NONE" or wav.getnchannels() != 1
                    or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE):
                raise ValueError("WAV must be PCM s16le mono 16000 Hz")
            if wav.getnframes() == 0 or wav.getnframes() > max_seconds * SAMPLE_RATE:
                raise ValueError("WAV is empty or exceeds max_seconds")
            return wav.readframes(wav.getnframes())
    except (OSError, EOFError, wave.Error) as exc:
        raise ValueError("Invalid or inaccessible WAV file") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="GN-040: local pt-BR CPU speech recognition")
    parser.add_argument("--file", type=Path, required=True, help="Local PCM mono 16 kHz WAV")
    parser.add_argument("--model", choices=AVAILABLE_MODELS, default="tiny")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--beam-size", type=int, default=3)
    parser.add_argument("--max-seconds", type=int, default=30)
    args = parser.parse_args()
    try:
        settings = ASRSettings(
            model=args.model, cpu_threads=args.cpu_threads,
            beam_size=args.beam_size, max_seconds=args.max_seconds,
        )
        pcm = read_pcm_wav(args.file, max_seconds=settings.max_seconds)
        result = CPUTranscriber(settings).transcribe_pcm(pcm)
    except (ValueError, ASRError) as exc:
        parser.exit(1, f"ASR error: {exc}\n")
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
