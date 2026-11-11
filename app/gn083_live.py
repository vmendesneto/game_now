"""GN-083: bounded continuous YouTube ASR and ephemeral, text-only field preview.

The live monitor never stores audio, writes the match/score to SQLite or
asserts verified broadcast clock/coordinates. The preview is server-memory
only and disappears after the stream becomes stale.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Awaitable, Callable

from pydantic import Field

from app.asr import ASRSettings, BYTES_PER_SECOND, CPUTranscriber
from app.asr_vocabulary import build_vocabulary_prompt
from app.asr_windows import RollingASRProcessor, WindowSettings
from app.ball_guard import BallGuardRequest, guard_ball_movement
from app.contracts import AudioSource, EstimatedBallState, Match, StrictModel
from app.match_start_detection import MatchStartDetector
from app.source_validation import validate_source_urls
from app.storage import StoreConflict
from app.youtube_capture import youtube_pcm_chunks

PREVIEW_STALE_SECONDS = 30.0
BALL_TTL_SECONDS = 8.0
QUEUE_CHUNKS = 80  # Approximately 40 seconds PCM with 500 ms producer chunks.


class LiveObservation(StrictModel):
    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    sequence: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=2048)


class LivePreviewRegistry:
    """Isolated per-match and per-source phase machines; never persistent."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._sessions: dict[tuple[str, str], dict] = {}

    def receive(self, match: Match, observation: LiveObservation) -> dict:
        if observation.end_seconds < observation.start_seconds:
            raise ValueError("Observation end precedes start")
        key = (match.id, observation.source_id)
        if key not in self._sessions:
            self._sessions[key] = {
                "detector": MatchStartDetector(), "ball": None,
                "ball_time": None, "last_seen": None, "audio_end": 0.,
            }
        session = self._sessions[key]
        before = session["detector"].phase
        detected = session["detector"].consume(observation.model_dump())
        now = self.clock()
        session["last_seen"] = now
        session["audio_end"] = observation.end_seconds
        phase = detected["phase"]
        if before != phase and phase in ("half_time", "second_half"):
            session["ball"] = None
            session["ball_time"] = None
        if detected["ball_updates_allowed"]:
            # Guard GN-056 requires one explicit, current, consistent team+zone.
            # Timestamp is ingestion-relative and NOT verified capture freshness.
            current = match.model_copy(deep=True)
            if phase == "second_half":
                current.period = "second_half"
                for team in (current.home, current.away):
                    team.attack_direction = (
                        "left_to_right" if team.attack_direction == "right_to_left"
                        else "right_to_left"
                    )
            current_ball = EstimatedBallState(updated_at=datetime.now(timezone.utc))
            if session["ball"] is not None:
                current_ball = EstimatedBallState(
                    team_id=session["ball"]["team_id"],
                    player_id=session["ball"]["player_id"],
                    zone=session["ball"]["zone"],
                    updated_at=datetime.now(timezone.utc),
                )
            decision = guard_ball_movement(
                current, current_ball,
                BallGuardRequest(text=observation.text, observed_age_seconds=0),
            )
            if decision.decision == "candidate" and decision.candidate_zone is not None:
                session["ball"] = {
                    "team_id": decision.team_id, "player_id": decision.player_id,
                    "zone": decision.candidate_zone.model_dump(mode="json"),
                    "basis": "explicit_text_unverified_freshness",
                }
                session["ball_time"] = now
        return self._view(key)

    def _view(self, key: tuple[str, str]) -> dict:
        session = self._sessions[key]
        now = self.clock()
        age = now - session["last_seen"]
        detected = session["detector"].snapshot()
        ball = session["ball"] if (
            detected["ball_updates_allowed"]
            and session["ball_time"] is not None
            and now - session["ball_time"] <= BALL_TTL_SECONDS
            and age <= PREVIEW_STALE_SECONDS
        ) else None
        return {
            **detected, "match_id": key[0], "source_id": key[1],
            "active": age <= PREVIEW_STALE_SECONDS,
            "last_audio_seconds": session["audio_end"],
            "ball": ball, "audio_retransmitted": False,
            "persisted": False,
        }

    def get(self, match_id: str) -> dict | None:
        views = [self._view(key) for key in self._sessions if key[0] == match_id]
        if not views:
            return None
        # One active source only, never merge out-of-sync sources.
        return max(views, key=lambda v: (
            v["active"], self._sessions[(v["match_id"], v["source_id"])]["last_seen"]
        ))

    def clear_match(self, match_id: str) -> None:
        for key in tuple(self._sessions):
            if key[0] == match_id:
                del self._sessions[key]


@dataclass(frozen=True)
class LiveMonitorResult:
    captured_seconds: float
    audio_bytes: int
    observations: int
    stopped_at_limit: bool


async def follow_youtube_narration(
    url: str, match: Match, *,
    source_id: str = "youtube-083",
    model: str = "tiny",
    yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg",
    max_seconds: float | None = None,
    on_observation: Callable[[dict], Awaitable[None]],
    transcriber=None,
    capture_factory=None,
) -> LiveMonitorResult:
    """Consume a stream until its end / Ctrl+C, no fixed pre-game offset.

    Capture and CPU recognition run concurrently with bounded backpressure.
    If CPU stays behind for >40 s, fail explicitly rather than silently drop
    arbitrary PCM or claim real-time processing.
    """
    if max_seconds is not None and (
        type(max_seconds) not in (int, float) or not 5 <= max_seconds <= 600
    ):
        raise ValueError("Test duration must be between 5 and 600 seconds")
    if not isinstance(url, str):
        raise ValueError("A public YouTube URL is required")
    source = AudioSource(
        id=source_id, name="GN-083 live monitor", kind="youtube", url=url,
        enabled=True, status="offline",
    )
    try:
        validate_source_urls([source])
    except StoreConflict as exc:
        raise ValueError("Invalid public YouTube source") from exc
    processor = RollingASRProcessor(
        transcriber or CPUTranscriber(ASRSettings(
            model=model, max_seconds=60,
            initial_prompt=build_vocabulary_prompt(match),
        )),
        WindowSettings(),
    )
    factory = capture_factory or youtube_pcm_chunks
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=QUEUE_CHUNKS)
    byte_count = 0
    row_count = 0
    ended_at_limit = False

    async def produce() -> None:
        nonlocal byte_count, ended_at_limit
        maximum = None if max_seconds is None else int(max_seconds * BYTES_PER_SECOND) // 2 * 2
        async with aclosing(factory(
            source, yt_dlp_binary=yt_dlp_binary, ffmpeg_binary=ffmpeg_binary,
        )) as stream:
            async for block in stream:
                if not isinstance(block, bytes) or not block or len(block) % 2:
                    raise ValueError("Invalid PCM in live stream")
                if maximum is not None:
                    block = block[:max(0, maximum - byte_count)]
                if block:
                    # Limit input bursts (regular capture yields 0.5 s chunks).
                    for off in range(0, len(block), BYTES_PER_SECOND // 2):
                        piece = block[off:off + BYTES_PER_SECOND // 2]
                        if queue.full():
                            raise RuntimeError("Live ASR is too slow for bounded PCM buffer")
                        queue.put_nowait(piece)
                        await asyncio.sleep(0)
                    byte_count += len(block)
                if maximum is not None and byte_count >= maximum:
                    ended_at_limit = True
                    break
        await queue.put(None)

    async def emit(updates) -> None:
        nonlocal row_count
        for update in updates:
            if update.new_text.strip():
                row = {
                    "source_id": update.source_id, "sequence": update.sequence,
                    "start_seconds": update.start_seconds,
                    "end_seconds": update.end_seconds, "text": update.new_text,
                }
                await on_observation(row)
                row_count += 1

    async def consume() -> None:
        while True:
            block = await queue.get()
            if block is None:
                break
            await emit(await asyncio.to_thread(processor.push, source_id, block))
        await emit(await asyncio.to_thread(processor.finish, source_id))

    producer = asyncio.create_task(produce())
    consumer = asyncio.create_task(consume())
    try:
        done, pending = await asyncio.wait(
            {producer, consumer}, return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in done:
            error = task.exception()
            if error is not None:
                raise error
        await asyncio.gather(*pending)
    finally:
        for task in (producer, consumer):
            if not task.done():
                task.cancel()
        await asyncio.gather(producer, consumer, return_exceptions=True)
    return LiveMonitorResult(
        captured_seconds=byte_count / BYTES_PER_SECOND,
        audio_bytes=byte_count, observations=row_count,
        stopped_at_limit=ended_at_limit,
    )
