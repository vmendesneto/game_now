"""GN-083 local or permitted public-stream ASR CLI. Never saves raw audio or game state."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from pydantic import ValidationError

from app.asr import ASRError
from app.gn083_offline import analyze_observations, evaluate, transcribe_file
from app.gn083_stream import transcribe_youtube_source
from app.audio_capture import CaptureError


def _array(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON input must be an array")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-083: authorized local/YouTube ASR audit")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--wav", type=Path, help="Local PCM mono 16000 Hz s16le WAV")
    inputs.add_argument("--raw-pcm", type=Path, help="Local raw mono 16000 Hz s16le PCM")
    inputs.add_argument("--transcripts", type=Path, help="Existing text-window JSON array")
    inputs.add_argument("--youtube-url", help="Permitted public YouTube video/live URL to transcribe directly")
    game = parser.add_mutually_exclusive_group(required=True)
    game.add_argument("--match-json", type=Path, help="Local Match JSON with team/roster")
    game.add_argument("--match-id", help="Saved match ID in local SQLite")
    parser.add_argument("--source-id", default="audio-local")
    parser.add_argument("--permission-confirmed", action="store_true",
                        help="Confirm permission to process supplied local audio")
    parser.add_argument("--model", choices=("tiny", "base", "small", "medium"), default="tiny")
    parser.add_argument("--seconds", type=float, default=300, help="Maximum YouTube stream duration (5-600)")
    parser.add_argument("--start-seconds", type=float, default=0,
                        help="Requested recorded-video seek (0-86400); observation times stay clip-relative")
    parser.add_argument("--yt-dlp", default="yt-dlp", help="yt-dlp executable")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable")
    parser.add_argument("--reference", type=Path, help="Independent human annotations JSON")
    parser.add_argument("--include-text", action="store_true", help="Include private ASR text")
    parser.add_argument("--capture-first", action="store_true",
                        help="Receive up to 600 seconds PCM in bounded RAM before running CPU ASR")
    parser.add_argument("--diagnose-asr", action="store_true",
                        help="On failure, show sanitized native ASR error details locally")
    parser.add_argument("--output", type=Path, help="Optional local JSON report")
    args = parser.parse_args(argv)
    try:
        if args.start_seconds != 0 and args.youtube_url is None:
            raise ValueError("--start-seconds requires --youtube-url")
        if args.match_json is not None:
            from app.contracts import Match
            match = Match.model_validate_json(args.match_json.read_text(encoding="utf-8"))
        else:
            from app.storage import SQLiteStore
            match = SQLiteStore().get_match(args.match_id)
            if match is None:
                raise ValueError("Match not found")
        run = None
        if args.transcripts is not None:
            observations = _array(args.transcripts)
        elif args.youtube_url is not None:
            if not args.permission_confirmed:
                raise ValueError("YouTube ASR requires --permission-confirmed")
            run = asyncio.run(transcribe_youtube_source(
                args.youtube_url, match, seconds=args.seconds,
                source_id="youtube-083" if args.source_id == "audio-local" else args.source_id,
                yt_dlp_binary=args.yt_dlp, ffmpeg_binary=args.ffmpeg,
                model=args.model, capture_first=args.capture_first,
                **({"start_seconds": args.start_seconds} if args.start_seconds else {}),
            ))
            observations = list(run.observations)
        else:
            if not args.permission_confirmed:
                raise ValueError("Local audio requires --permission-confirmed")
            observations = transcribe_file(
                args.wav or args.raw_pcm, match, raw=args.raw_pcm is not None,
                source_id=args.source_id, model=args.model,
            )
        # Retain text only within this process for optional WER.
        predictions = analyze_observations(match, observations, include_text=True)
        metrics = evaluate(predictions, _array(args.reference)) if args.reference else None
        if not args.include_text:
            for row in predictions:
                row.pop("text", None)
        report = {
            "task": "GN-083", "mode": "direct_stream_asr" if run else "offline_diagnostic",
            "input_type": ("transcripts" if args.transcripts else
                           "youtube_stream_asr" if run else "local_audio_asr"),
            "source": ("per_observation" if args.transcripts else
                       run.source_id if run else args.source_id),
            "asr_model": None if args.transcripts else args.model,
            "observations": len(predictions),
            "reference_evaluated": metrics is not None,
            "metrics": metrics, "predictions": predictions,
            "persisted": False, "audio_retransmitted": False,
        }
        if run is not None:
            report["audio_seconds_processed"] = run.processed_seconds
            report["audio_bytes_processed"] = run.processed_bytes
            report["requested_seconds"] = run.requested_seconds
            report["audio_duration_complete"] = run.complete
            report["requested_media_start_seconds"] = run.requested_media_start_seconds
            report["media_start_verified"] = False
            report["observation_time_origin"] = "clip_start"
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
    except (ValueError, OSError, json.JSONDecodeError, ASRError, CaptureError, ValidationError) as exc:
        if isinstance(exc, ASRError) and args.diagnose_asr:
            from app.asr_diagnostics import asr_failure_details
            import sys
            print("GN-083 ASR diagnostic: " + json.dumps(
                asr_failure_details(exc), ensure_ascii=False,
            ), file=sys.stderr)
        parser.exit(2, f"GN-083: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
