"""GN-083: bounded continuous YouTube ASR and ephemeral, text-only field preview.

The live monitor never stores audio, writes the match/score to SQLite or
asserts verified broadcast clock/coordinates. The preview is server-memory
only and disappears after the stream becomes stale.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import time
from typing import Awaitable, Callable

from pydantic import Field

from app.asr import ASRError, ASRSettings, BYTES_PER_SECOND, CPUTranscriber
from app.asr_vocabulary import build_vocabulary_prompt
from app.asr_windows import RollingASRProcessor, WindowSettings
from app.ball_guard import BallGuardRequest, guard_ball_movement
from app.contracts import AudioSource, EstimatedBallState, Match, StrictModel
from app.match_start_detection import MatchStartDetector, current_play_cue
from app.source_validation import validate_source_urls
from app.storage import StoreConflict
from app.spatial_mentions import spatial_mention
from app.narration_tracking import track_narration
from app.source_selection import SourceSelectionRequest, SourceSelectionObservation, preview_active_source
from app.youtube_capture import youtube_pcm_chunks

PREVIEW_STALE_SECONDS = 30.0
BALL_TTL_SECONDS = 8.0
SPATIAL_MENTION_TTL_SECONDS = 15.0
QUEUE_CHUNKS = 80  # Approximately 40 seconds PCM with 500 ms producer chunks.


class ASRCapacityError(ASRError):
    """The bounded per-source queue filled while waiting for recognition."""


async def wait_for_cpu(function, *args):
    """Finish an in-flight native inference before acknowledging cancellation."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


class LiveObservation(StrictModel):
    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    sequence: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=2048)
    local_capture_age_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class LivePreviewRegistry:
    """Isolated per-match and per-source phase machines; never persistent."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self._sessions: dict[tuple[str, str], dict] = {}
        self._groups: dict[str, dict] = {}

    def set_alignment(self, match_id: str, offsets: dict[str, float]) -> str:
        self._groups[match_id] = {"offsets": offsets.copy(), "selected": None,
                                 "watermark": float("-inf"), "id": uuid4().hex,
                                 "phase": "pre_game", "phase_confidence": "none"}
        return self._groups[match_id]["id"]

    def add_independent_sources(self, match_id: str, source_ids: list[str]) -> str:
        """Select one source at a time without pretending their clocks align."""
        if match_id not in self._groups:
            self._groups[match_id] = {"offsets": {}, "selected": None,
                "watermark": float("-inf"), "id": uuid4().hex,
                "phase": "pre_game", "phase_confidence": "none", "independent": True}
        group = self._groups[match_id]
        for source_id in source_ids:
            group["offsets"][source_id] = None
        return group["id"]

    def _remember_phase(self, match_id: str, detected: dict) -> None:
        group = self._groups.get(match_id)
        phases = ("pre_game", "probable_start", "in_play", "half_time", "second_half")
        if group and phases.index(detected["phase"]) > phases.index(group["phase"]):
            group["phase"], group["phase_confidence"] = detected["phase"], detected["confidence"]

    def receive(self, match: Match, observation: LiveObservation) -> dict:
        if observation.end_seconds < observation.start_seconds:
            raise ValueError("Observation end precedes start")
        key = (match.id, observation.source_id)
        if key not in self._sessions:
            self._sessions[key] = {
                "detector": MatchStartDetector(), "ball": None,
                "ball_time": None, "last_seen": None, "audio_end": 0.,
                "spatial_mention": None, "spatial_time": None, "spatial_initial_age": 0.,
                "ball_diagnostic": "phase_not_confirmed",
                "action_history": [], "actions_time": None, "actions_initial_age": 0.,
                "latest_action": None,
                "latest_region_action": None,
                "current_actions": [], "observation_sequence": None,
            }
        session = self._sessions[key]
        before = session["detector"].phase
        detected = session["detector"].consume(observation.model_dump())
        self._remember_phase(match.id, detected)
        now = self.clock()
        session["last_seen"] = now
        session["audio_end"] = observation.end_seconds
        phase = detected["phase"]
        current = match.model_copy(deep=True)
        if phase == "second_half" and current.period != "second_half":
            current.period = "second_half"
            for team in (current.home, current.away):
                team.attack_direction = (
                    "left_to_right" if team.attack_direction == "right_to_left"
                    else "right_to_left"
                )
        mention = spatial_mention(current, observation.text)
        age = observation.local_capture_age_seconds
        session["current_play"] = current_play_cue(observation.text)
        actions = track_narration(current, observation.text) if phase != "half_time" else []
        session["current_actions"] = [{**item,"id":f"{observation.source_id}:{observation.sequence}:{index}",
                                      "source_id": observation.source_id,
                                      "audio_start_seconds": observation.start_seconds,
                                      "audio_end_seconds": observation.end_seconds}
                                      for index,item in enumerate(actions)]
        session["observation_sequence"] = observation.sequence
        history = session["action_history"]
        for index, action in enumerate(actions):
            # Only identical text in overlapping windows is a duplicate. This
            # does not claim event alignment across different sources.
            if any(old["text"] == action["text"] and old["kind"] == action["kind"]
                   and old["player_id"] == action["player_id"] and old["team_id"] == action["team_id"]
                   and observation.start_seconds < old["audio_end_seconds"]
                   for old in history[-32:]):
                continue
            history.append({**action, "id": f"{observation.source_id}:{observation.sequence}:{index}",
                            "audio_start_seconds": observation.start_seconds,
                            "audio_end_seconds": observation.end_seconds})
        session["action_history"] = history[-96:]
        session["latest_action"] = ({**actions[-1], "id": f"{observation.source_id}:{observation.sequence}:latest"}
                                    if actions else None)
        region_action = next((item for item in reversed(actions) if item["region"]), None)
        session["latest_region_action"] = ({**region_action, "id": f"{observation.source_id}:{observation.sequence}:region"}
                                           if region_action else None)
        session["actions_time"] = now
        session["actions_initial_age"] = age or 0.
        session["spatial_mention"] = mention if (
            # A quoted corridor is partial information with its own 15s TTL,
            # not a current ball candidate governed by the stricter 5s guard.
            # _view includes initial processing age, so no extra lifetime is added.
            mention["status"] == "partial" and (age is None or age <= SPATIAL_MENTION_TTL_SECONDS)
            and phase not in ("half_time",)
        ) else None
        session["spatial_time"] = now
        session["spatial_initial_age"] = age or 0.
        session["ball_diagnostic"] = "phase_not_confirmed" if not detected["ball_updates_allowed"] else "audio_too_old"
        if before != phase and phase in ("half_time", "second_half"):
            session["ball"] = None
            session["ball_time"] = None
        fresh = (observation.local_capture_age_seconds is None
                 or observation.local_capture_age_seconds <= 5)
        if detected["ball_updates_allowed"] and fresh:
            # Guard GN-056 requires one explicit, current, consistent team+zone.
            # Timestamp is ingestion-relative and NOT verified capture freshness.
            current_ball = EstimatedBallState(updated_at=datetime.now(timezone.utc))
            if (session["ball"] is not None and session["ball_time"] is not None
                    and now-session["ball_time"] <= BALL_TTL_SECONDS):
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
            session["ball_diagnostic"] = decision.reason
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
            and session["current_play"]
            and session["ball_time"] is not None
            and now - session["ball_time"] <= BALL_TTL_SECONDS
            and age <= PREVIEW_STALE_SECONDS
        ) else None
        mention_age = (session["spatial_initial_age"] + (now - session["spatial_time"])
                       if session["spatial_time"] is not None else float("inf"))
        mention = session["spatial_mention"] if (
            ball is None and age <= PREVIEW_STALE_SECONDS and mention_age <= SPATIAL_MENTION_TTL_SECONDS
        ) else None
        actions_fresh = (age <= PREVIEW_STALE_SECONDS and session["actions_time"] is not None
                        and session["actions_initial_age"] + now-session["actions_time"] <= SPATIAL_MENTION_TTL_SECONDS)
        return {
            **detected, "match_id": key[0], "source_id": key[1],
            "active": age <= PREVIEW_STALE_SECONDS,
            "last_audio_seconds": session["audio_end"],
            "ball": ball, "audio_retransmitted": False,
            "spatial_mention": ({**mention, "age_seconds": round(mention_age, 2),
                                 "audio_end_seconds": session["audio_end"]} if mention else None),
            "ball_diagnostic": session["ball_diagnostic"],
            "narration_actions": session["action_history"].copy(),
            "latest_narration_action": session["latest_action"] if actions_fresh else None,
            "latest_narration_region_action": session["latest_region_action"] if actions_fresh else None,
            "current_narration_actions": session["current_actions"].copy() if actions_fresh else [],
            "observation_sequence": session["observation_sequence"],
            "persisted": False,
        }

    def get(self, match_id: str) -> dict | None:
        views = [self._view(key) for key in self._sessions if key[0] == match_id]
        if not views:
            return None
        group = self._groups.get(match_id)
        if group:
            if group.get("independent"):
                return self._independent_view(match_id, views, group)
            now = datetime.now(timezone.utc)
            observations = []
            for view in views:
                session = self._sessions[(match_id, view["source_id"])]
                age = session["actions_initial_age"] + self.clock()-session["last_seen"]
                aligned = group["offsets"].get(view["source_id"], float("-inf")) + view["last_audio_seconds"]
                view["aligned_audio_seconds"] = aligned
                usable = bool(view["ball"] or view["latest_narration_action"] or view["spatial_mention"])
                usable = usable and aligned >= group["watermark"]
                observations.append(SourceSelectionObservation(source_id=view["source_id"],
                    connection_status="online" if view["active"] else "offline",
                    narration_kind="live_play" if usable else "unknown",
                    captured_at=now-timedelta(seconds=max(0,age)), received_at=now,
                    signal_strength=.85 if view["ball"] else .75 if view["spatial_mention"] else .7))
            selection = preview_active_source(SourceSelectionRequest(evaluated_at=now,
                observations=observations, previous_source_id=group["selected"], max_age_seconds=15))
            selected = next((view for view in views if view["source_id"] == selection.active_source_id), None)
            if selected is None:
                selected = max(views, key=lambda view: self._sessions[(match_id,view["source_id"])]["last_seen"])
                selected = {**selected, "ball": None, "spatial_mention": None, "latest_narration_action": None,
                            "latest_narration_region_action": None, "current_narration_actions": []}
            else:
                group["watermark"] = max(group["watermark"], selected["aligned_audio_seconds"])
            group["selected"] = selection.active_source_id
            conflicting = [view for view in views if selected["ball"] and view["ball"]
                           and view["source_id"] != selected["source_id"]
                           and abs(view["aligned_audio_seconds"]-selected["aligned_audio_seconds"]) <= 1
                           and (view["ball"]["team_id"],view["ball"]["zone"]) !=
                               (selected["ball"]["team_id"],selected["ball"]["zone"])]
            if conflicting:
                action = selected["latest_narration_action"]
                selected = {**selected, "ball": None, "spatial_mention": None, "latest_narration_region_action": None,
                            "latest_narration_action": {**action,"region":None} if action else None,
                            "current_narration_actions": []}
            return {**selected, "visual_context": group["id"],
                    "group_phase": group["phase"], "group_phase_confidence": group["phase_confidence"],
                    "visual_timeline": group["watermark"] if group["watermark"] != float("-inf") else 0,
                    "fusion": {"active_source_id": selection.active_source_id, "reason": selection.reason,
                               "alignment_basis": "user_kickoff_anchors", "alignment_verified": False,
                               "source_count": len(group["offsets"]), "conflicting_ball_sources": [v["source_id"] for v in conflicting],
                               "diagnostics": [d.model_dump(mode="json") for d in selection.diagnostics]}}
        # One active source only, never merge out-of-sync sources.
        return max(views, key=lambda v: (
            v["active"], self._sessions[(v["match_id"], v["source_id"])]["last_seen"]
        ))

    def _independent_view(self, match_id: str, views: list[dict], group: dict) -> dict:
        now = datetime.now(timezone.utc)
        observations = []
        for view in views:
            session = self._sessions[(match_id, view["source_id"])]
            age = session["actions_initial_age"] + self.clock() - session["last_seen"]
            usable = view["active"] and bool(
                view["ball"] or view["latest_narration_action"] or view["spatial_mention"])
            observations.append(SourceSelectionObservation(source_id=view["source_id"],
                connection_status="online" if view["active"] else "offline",
                narration_kind="live_play" if usable else "unknown",
                captured_at=now-timedelta(seconds=max(0, age)), received_at=now,
                signal_strength=.85 if view["ball"] else .75 if view["spatial_mention"] else .7))
        selection = preview_active_source(SourceSelectionRequest(evaluated_at=now,
            observations=observations, previous_source_id=group["selected"], max_age_seconds=15))
        selected = next((view for view in views if view["source_id"] == selection.active_source_id), None)
        if selected is None:
            selected = max(views, key=lambda view: self._sessions[(match_id, view["source_id"])]["last_seen"])
            selected = {**selected, "ball": None, "spatial_mention": None,
                "latest_narration_action": None, "latest_narration_region_action": None,
                "current_narration_actions": []}
        group["selected"] = selection.active_source_id
        # A source switch starts a new visual context. No region, actor or
        # watermark from another unaligned source is transferred to it.
        return {**selected, "visual_context": group["id"] + ":" + selected["source_id"],
            "visual_timeline": selected["last_audio_seconds"],
            "group_phase": group["phase"], "group_phase_confidence": group["phase_confidence"],
            "fusion": {"active_source_id": selection.active_source_id, "reason": selection.reason,
                "alignment_basis": "independent_sources", "alignment_verified": False,
                "source_count": len(group["offsets"]), "cross_source_chronology_verified": False,
                "diagnostics": [item.model_dump(mode="json") for item in selection.diagnostics]}}

    def clear_match(self, match_id: str) -> None:
        self._groups.pop(match_id, None)
        for key in tuple(self._sessions):
            if key[0] == match_id:
                del self._sessions[key]

    def clear_source(self, match_id: str, source_id: str) -> None:
        self._sessions.pop((match_id, source_id), None)
        group = self._groups.get(match_id)
        if group and group.get("independent"):
            group["offsets"].pop(source_id, None)


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
    source_kind: str = "youtube",
    window_settings: WindowSettings | None = None,
    on_pcm: Callable[[int], None] | None = None,
    cpu_gate: asyncio.Semaphore | None = None,
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
        id=source_id, name="GN-083 live monitor", kind=source_kind, url=url,
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
        window_settings or WindowSettings(),
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
                    if on_pcm is not None:
                        on_pcm(len(block))
                    # Limit input bursts (regular capture yields 0.5 s chunks).
                    for off in range(0, len(block), BYTES_PER_SECOND // 2):
                        piece = block[off:off + BYTES_PER_SECOND // 2]
                        if queue.full():
                            raise ASRCapacityError("Live ASR is too slow for bounded PCM buffer")
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
        async def process(function, *args):
            if cpu_gate is None:
                return await wait_for_cpu(function, *args)
            async with cpu_gate:
                return await wait_for_cpu(function, *args)
        while True:
            block = await queue.get()
            if block is None:
                break
            await emit(await process(processor.push, source_id, block))
        await emit(await process(processor.finish, source_id))

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
