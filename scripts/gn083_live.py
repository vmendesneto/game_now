"""GN-083 continuous monitor: no manual kickoff offset and no saved media.

Run the local Game Now server separately. The monitor sends only text windows
to a loopback-only, in-memory diagnostic preview. It never writes the score.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.asr import ASRError
from app.audio_capture import CaptureError
from app.gn083_live import follow_youtube_narration
from app.match_start_detection import MatchStartDetector
from app.storage import SQLiteStore


def _request(url: str, payload: dict | None = None) -> dict | None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers={"Content-Type": "application/json"}
                      if data is not None else {}, method="POST" if data is not None else "GET")
    with urlopen(request, timeout=4) as response:
        return json.loads(response.read(8192))


async def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GN-083: follow authorized YouTube narration until stopped or stream ends",
    )
    parser.add_argument("--youtube-url", required=True)
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--source-id", default="youtube-083")
    parser.add_argument("--model", choices=("tiny", "base", "small", "medium"), default="tiny")
    parser.add_argument("--yt-dlp", default="yt-dlp")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--permission-confirmed", action="store_true")
    parser.add_argument("--seconds", type=float, default=None,
                        help="Optional 5-600 s limited test; omit for continuous live monitoring")
    parser.add_argument("--local-port", type=int, default=8000)
    parser.add_argument("--diagnostic-only", action="store_true",
                        help="Report phases on CLI without updating local website preview")
    args = parser.parse_args(argv)
    if not args.permission_confirmed:
        parser.error("Audio transcription requires --permission-confirmed")
    if not 1 <= args.local_port <= 65535:
        parser.error("Invalid local port")
    match = SQLiteStore().get_match(args.match_id)
    if match is None:
        parser.error("Match not found in local SQLite (run seed script first)")
    base = f"http://127.0.0.1:{args.local_port}/api/matches/{match.id}"
    if not args.diagnostic_only:
        try:
            await asyncio.to_thread(_request, base + "/live/preview")
        except (HTTPError, URLError, OSError, ValueError) as exc:
            parser.error("Local Game Now server unavailable: start it before live monitoring")
    detector = MatchStartDetector()
    previous_phase = None
    previous_ball = None

    async def observation_callback(row: dict) -> None:
        nonlocal previous_phase, previous_ball
        local = detector.consume(row)
        if args.diagnostic_only:
            preview = {**local, "ball": None, "last_audio_seconds": row["end_seconds"]}
        else:
            preview = await asyncio.to_thread(_request, base + "/live/observation", row)
        phase = preview["phase"]
        ball = preview.get("ball")
        if phase != previous_phase or ball != previous_ball:
            print(json.dumps({
                "phase": phase, "confidence": preview["confidence"],
                "reason": preview["reason"],
                "at_audio_seconds": row["end_seconds"],
                "first_play_audio_seconds": preview["first_play_audio_seconds"],
                "ball": ball,
                "confidence_calibrated": False,
            }, ensure_ascii=False), flush=True)
        previous_phase, previous_ball = phase, ball

    try:
        result = await follow_youtube_narration(
            args.youtube_url, match, source_id=args.source_id,
            model=args.model, yt_dlp_binary=args.yt_dlp,
            ffmpeg_binary=args.ffmpeg, max_seconds=args.seconds,
            on_observation=observation_callback,
        )
        print(json.dumps({
            "captured_seconds": result.captured_seconds,
            "observations": result.observations,
            "stopped_at_test_limit": result.stopped_at_limit,
            "final_phase": detector.phase, "validated_on_real_broadcast": False,
            "audio_retransmitted": False, "persisted": False,
        }, ensure_ascii=False), flush=True)
    except (ValueError, RuntimeError, ASRError, CaptureError, HTTPError, URLError, OSError) as exc:
        parser.exit(2, f"GN-083 live monitor: {type(exc).__name__}: {exc}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(argv))
    except KeyboardInterrupt:
        print("GN-083: monitor stopped; no video/audio saved.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
