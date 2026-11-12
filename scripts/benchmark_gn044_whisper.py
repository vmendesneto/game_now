"""GN-044: authorized local Whisper model comparison, CPU and optional CUDA.

Models run in independent child processes to avoid comparing cumulative peak
memory high-water marks. No stream URLs, media storage, uploads or result text.
GN-044 remains open until physical Windows benchmark and real WER evidence.
"""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import json
import math
from io import BytesIO
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter, process_time
import wave

from app.asr import ASRError, ASRResult, ASRSettings, CPUTranscriber, BYTES_PER_SECOND, read_pcm_wav
from app.gn083_offline import _distance, _words

MODELS = ("tiny", "base", "small", "medium")
MAX_SAMPLES = 8
MAX_REFERENCE_LENGTH = 6000


@dataclass(frozen=True)
class BenchmarkSample:
    pcm: bytes
    reference_text: str


def load_manifest(path: Path) -> list[BenchmarkSample]:
    """A bounded manifest of authorized, local, <=30s PCM WAV references."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Cannot read local JSON manifest") from exc
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SAMPLES:
        raise ValueError("Manifest must contain 1..8 samples")
    samples = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"wav", "reference_text"}:
            raise ValueError("Each sample needs wav and reference_text")
        wav, reference = row["wav"], row["reference_text"]
        if (not isinstance(wav, str) or not wav.strip()
                or wav.startswith(("http:", "https:")) or "\x00" in wav
                or not isinstance(reference, str)
                or not 1 <= len(reference) <= MAX_REFERENCE_LENGTH
                or not _words(reference)):
            raise ValueError("Invalid WAV path or empty reference transcription")
        file_path = path.parent / wav
        samples.append(BenchmarkSample(
            pcm=read_pcm_wav(file_path, max_seconds=30),
            reference_text=reference,
        ))
    return samples


def score_samples(
    samples: list[BenchmarkSample], transcriber,
    *, clock=perf_counter,
) -> dict[str, object]:
    """Measure model inference and word error without returning private text."""
    if not samples:
        raise ValueError("At least one sample required")
    words = errors = pcm_seconds = 0
    latencies = []
    for sample in samples:
        started = clock()
        prediction = transcriber.transcribe_pcm(sample.pcm)
        elapsed = max(0., clock() - started)
        reference_words = _words(sample.reference_text)
        predicted_words = _words(prediction.text)
        words += len(reference_words)
        errors += _distance(reference_words, predicted_words)
        pcm_seconds += len(sample.pcm) / BYTES_PER_SECOND
        latencies.append(elapsed)
    if not words:
        raise ValueError("References contain no words")
    ordered = sorted(latencies)
    return {
        "samples": len(samples),
        "reference_words": words,
        "word_errors": errors,
        "wer": round(errors / words, 4),
        "audio_seconds": round(pcm_seconds, 3),
        "inference_wall_seconds": round(sum(latencies), 3),
        "latency_median_seconds": round(ordered[(len(ordered) - 1) // 2], 3),
        "latency_p95_seconds": round(ordered[math.ceil(.95 * len(ordered)) - 1], 3),
        "inference_wall_seconds_per_audio_second": round(sum(latencies) / pcm_seconds, 3),
    }


class _CudaTranscriber:
    """Opt-in CUDA inference, same decoding parameters as CPUTranscriber."""

    def __init__(self, model: str, beam_size: int) -> None:
        self.model = model
        self.beam_size = beam_size
        self._whisper = None

    def transcribe_pcm(self, pcm: bytes) -> ASRResult:
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(
                    self.model, device="cuda", compute_type="float16", num_workers=1,
                )
            except Exception as exc:
                raise ASRError("CUDA model cannot be initialized; inspect CUDA installation") from exc
        audio = BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16_000)
            wav.writeframes(pcm)
        audio.seek(0)
        try:
            segments, info = self._whisper.transcribe(
                audio, language="pt", beam_size=self.beam_size,
                vad_filter=False, condition_on_previous_text=False,
            )
            text = " ".join(str(segment.text).strip() for segment in segments).strip()
        except Exception as exc:
            raise ASRError("CUDA inference failed") from exc
        return ASRResult(
            model=self.model, language=str(getattr(info, "language", "pt")),
            seconds=len(pcm) / BYTES_PER_SECOND, text=text, segments=(),
        )


def make_transcriber(model: str, device: str, cpu_threads: int, beam_size: int):
    if model not in MODELS:
        raise ValueError("Unsupported model")
    if not 1 <= cpu_threads <= 16 or not 1 <= beam_size <= 10:
        raise ValueError("Invalid CPU threads or beam size")
    if device == "cpu":
        return CPUTranscriber(ASRSettings(
            model=model, cpu_threads=cpu_threads, beam_size=beam_size, max_seconds=30,
        ))
    if device == "cuda":
        return _CudaTranscriber(model, beam_size)
    raise ValueError("Device must be cpu or cuda")


def peak_rss_mb() -> float | None:
    """OS-reported process peak resident set; CUDA VRAM is excluded."""
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            kernel.GetCurrentProcess.restype = wintypes.HANDLE
            psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD,
            ]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            ok = psapi.GetProcessMemoryInfo(
                kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb,
            )
            return round(counters.PeakWorkingSetSize / (1024 * 1024), 2) if ok else None
        except (AttributeError, OSError, ValueError):
            return None
    try:
        import resource
        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round((raw if sys.platform == "darwin" else raw * 1024) / 1048576, 2)
    except (ImportError, OSError):
        return None


def benchmark_model(
    path: Path, *, model: str, device: str, cpu_threads: int = 2, beam_size: int = 3,
) -> dict[str, object]:
    samples = load_manifest(path)
    transcriber = make_transcriber(model, device, cpu_threads, beam_size)
    started = perf_counter()
    cpu_start = process_time()
    metrics = score_samples(samples, transcriber)
    wall = perf_counter() - started
    cpu = process_time() - cpu_start
    return {
        "model": model, "device": device,
        "compute_type": "int8" if device == "cpu" else "float16",
        "cpu_threads": cpu_threads if device == "cpu" else None,
        "beam_size": beam_size,
        "wall_seconds_including_first_load": round(wall, 3),
        "cpu_seconds": round(cpu, 3),
        "peak_process_rss_mb": peak_rss_mb(),
        "gpu_vram_measured": False,
        **metrics,
    }


def run_independent_models(
    manifest: Path, *, models: list[str], device: str = "cpu",
    cpu_threads: int = 2, beam_size: int = 3,
    executable: str | None = None,
) -> dict[str, object]:
    """Launch each model in a fresh process so RSS peaks are comparable."""
    if not models or len(set(models)) != len(models) or any(m not in MODELS for m in models):
        raise ValueError("Select distinct known Whisper models")
    if device not in ("cpu", "cuda") or not 1 <= cpu_threads <= 16 or not 1 <= beam_size <= 10:
        raise ValueError("Invalid benchmark settings")
    if not manifest.is_file():
        raise ValueError("Manifest file not found")
    measurements = []
    for model in models:
        command = [
            executable or sys.executable, "-m", "scripts.benchmark_gn044_whisper",
            "--manifest", str(manifest), "--models", model, "--device", device,
            "--cpu-threads", str(cpu_threads), "--beam-size", str(beam_size),
            "--permission-confirmed", "--_worker",
        ]
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=3600, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"{model}: model subprocess unavailable or timed out") from exc
        if result.returncode != 0:
            raise RuntimeError(f"{model}: model subprocess failed; check environment locally")
        try:
            report = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"{model}: invalid subprocess report") from exc
        if report.get("model") != model or report.get("device") != device:
            raise RuntimeError(f"{model}: subprocess returned mismatched measurements")
        measurements.append(report)
    return {
        "task": "GN-044", "evidence": "authorized_local_audio_reference",
        "environment": {"platform": platform.system(), "python": platform.python_version()},
        "device": device, "independent_process_per_model": True,
        "audio_recorded_or_uploaded": False, "text_included": False,
        "physical_windows_tested_automatically": False,
        "measurements": measurements,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-044: local authorized Whisper comparison")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=MODELS, default=["tiny", "base"])
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--cpu-threads", type=int, default=2)
    parser.add_argument("--beam-size", type=int, default=3)
    parser.add_argument("--permission-confirmed", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--_worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.permission_confirmed:
        parser.error("Explicit --permission-confirmed is required for local WAV")
    try:
        if args._worker:
            if len(args.models) != 1:
                raise ValueError("One model per worker")
            report = benchmark_model(
                args.manifest, model=args.models[0], device=args.device,
                cpu_threads=args.cpu_threads, beam_size=args.beam_size,
            )
        else:
            report = run_independent_models(
                args.manifest, models=args.models, device=args.device,
                cpu_threads=args.cpu_threads, beam_size=args.beam_size,
            )
    except (ValueError, ASRError, RuntimeError, OSError) as exc:
        # Avoid printing source paths and native inference exception details.
        parser.exit(2, f"GN-044: {type(exc).__name__}: benchmark did not complete\n")
    content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
