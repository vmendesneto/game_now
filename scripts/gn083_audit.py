"""GN-083 offline diagnostic CLI. Never captures/downloads remote media or writes game state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from app.asr import ASRError
from app.gn083_offline import analyze_observations, evaluate, transcribe_file


def _array(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON input must be an array")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-083: local ASR and narration audit")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--wav", type=Path, help="Local PCM mono 16000 Hz s16le WAV")
    inputs.add_argument("--raw-pcm", type=Path, help="Local raw mono 16000 Hz s16le PCM")
    inputs.add_argument("--transcripts", type=Path, help="Existing text-window JSON array")
    game = parser.add_mutually_exclusive_group(required=True)
    game.add_argument("--match-json", type=Path, help="Local Match JSON with team/roster")
    game.add_argument("--match-id", help="Saved match ID in local SQLite")
    parser.add_argument("--source-id", default="audio-local")
    parser.add_argument("--permission-confirmed", action="store_true",
                        help="Confirm permission to process supplied local audio")
    parser.add_argument("--model", choices=("tiny", "base", "small", "medium"), default="tiny")
    parser.add_argument("--reference", type=Path, help="Independent human annotations JSON")
    parser.add_argument("--include-text", action="store_true", help="Include private ASR text")
    parser.add_argument("--output", type=Path, help="Optional local JSON report")
    args = parser.parse_args(argv)
    try:
        if args.match_json is not None:
            from app.contracts import Match
            match = Match.model_validate_json(args.match_json.read_text(encoding="utf-8"))
        else:
            from app.storage import SQLiteStore
            match = SQLiteStore().get_match(args.match_id)
            if match is None:
                raise ValueError("Match not found")
        if args.transcripts is not None:
            observations = _array(args.transcripts)
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
            "task": "GN-083", "mode": "offline_diagnostic",
            "input_type": "transcripts" if args.transcripts else "local_audio_asr",
            "source": "per_observation" if args.transcripts else args.source_id,
            "asr_model": None if args.transcripts else args.model,
            "observations": len(predictions),
            "reference_evaluated": metrics is not None,
            "metrics": metrics, "predictions": predictions,
            "persisted": False, "audio_retransmitted": False,
        }
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(content, encoding="utf-8")
        else:
            print(content, end="")
    except (ValueError, OSError, json.JSONDecodeError, ASRError, ValidationError) as exc:
        parser.exit(2, f"GN-083: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
