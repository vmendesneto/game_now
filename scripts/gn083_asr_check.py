"""Check faster-whisper inference in the local CPU without YouTube/FFmpeg.

Synthetic silence tests model loading and the underlying CPU inference path; it
does not measure transcription quality and never accesses a broadcast.
"""
from __future__ import annotations

import argparse
import json

from app.asr import ASRError, ASRSettings, BYTES_PER_SECOND, CPUTranscriber
from app.asr_diagnostics import asr_failure_details


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-083: check local CPU ASR engine")
    parser.add_argument("--model", choices=("tiny", "base", "small", "medium"),
                        default="tiny")
    parser.add_argument("--cpu-threads", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        transcriber = CPUTranscriber(ASRSettings(
            model=args.model, cpu_threads=args.cpu_threads, max_seconds=10,
        ))
        # Six seconds of synthesized silence, no third-party media.
        result = transcriber.transcribe_pcm(b"\x00\x00" * (BYTES_PER_SECOND // 2 * 6))
    except (ASRError, ValueError, OSError) as exc:
        print(json.dumps({
            "ok": False, "model": args.model, "error": (
                str(exc) if isinstance(exc, ASRError) else type(exc).__name__
            ), "root_cause": asr_failure_details(exc),
            "external_media_processed": False,
        }, ensure_ascii=False))
        return 1
    print(json.dumps({
        "ok": True, "model": result.model, "seconds": result.seconds,
        "segments": len(result.segments), "external_media_processed": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
