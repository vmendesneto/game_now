"""HTTP + WebSocket entry point. No audio or video is ever served."""
from __future__ import annotations

from pathlib import Path
import asyncio
import shutil
import time
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.asr import asr_diagnostics
from app.configuration import MatchConfig, RosterPlayer
from app.corrections import CorrectionService, ManualCorrection
from app.contracts import AudioSource, ContractBundle, Match
from app.demo import DemoEngine
from app.entities import ResolveRequest, ResolveResult, resolve_player
from app.narration_entities import NarrationResolveRequest, NarrationResolution, resolve_narration
from app.possession import PossessionRequest, PossessionEvidence, detect_possession
from app.field_regions import RegionRequest, RegionEvidence, detect_region
from app.event_detection import EventRequest, EventEvidence, detect_event
from app.confidence import ConfidenceRequest, ConfidenceEvidence, assess_confidence
from app.ball_guard import BallGuardRequest, BallGuardDecision, guard_ball_movement
from app.llm_local import LLMCompareRequest, LLMComparison, compare_language
from app.logical_clock import ClockPreviewRequest, ClockPreviewResponse, preview_clock
from app.source_delay import RelativeDelayRequest, RelativeDelayResponse, preview_relative_delays
from app.event_deduplication import EventDeduplicationRequest, EventDeduplicationResponse, preview_event_deduplication
from app.source_selection import SourceSelectionRequest, SourceSelectionResponse, preview_active_source
from app.fusion_conflicts import FusionConflictRequest, FusionConflictResponse, preview_fusion_conflicts
from app.ball_freshness import BallFreshnessRequest, BallFreshnessResponse, preview_ball_freshness
from app.match_flow import MatchAction, MatchFlowService
from app.logging_setup import request_logger
from app.storage import SQLiteStore, StoreConflict
from app.transcription_feed import TranscriptFeed

STATIC = Path(__file__).resolve().parent / "static"


def create_app(database_path: str | Path | None = None) -> FastAPI:
    application = FastAPI(title="Game Now", version="0.2.0")
    engine = DemoEngine()
    store = SQLiteStore(database_path)
    flow = MatchFlowService(store)
    corrections = CorrectionService(store)
    transcript_feed = TranscriptFeed()
    application.state.transcript_feed = transcript_feed
    application.state.store = store
    logger = request_logger()
    clients: set[WebSocket] = set()
    demo_lock = asyncio.Lock()  # Serializes snapshots, updates and subscriber joins.

    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        request_id = uuid4().hex
        details = {"request_id": request_id, "method": request.method,
                   "route": request.url.path}
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error("http_request", extra={"safe_details": {
                **details, "status": 500, "error_type": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            }})
            raise
        logger.info("http_request", extra={"safe_details": {
            **details, "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }})
        response.headers["X-Request-ID"] = request_id
        return response

    application.mount("/static", StaticFiles(directory=STATIC), name="static")

    def require_match(match_id: str) -> Match:
        match = store.get_match(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return match

    def conflict(exc: StoreConflict) -> None:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    @application.get("/health")
    async def health():
        return {
            "status": "ok", "mode": "synthetic_demo",
            "ffmpeg": {"available": shutil.which("ffmpeg") is not None,
                       "path": shutil.which("ffmpeg")},
            "asr": asr_diagnostics(),
            "storage": "sqlite_persistent",
            "demo_state": "volatile_memory_only",
            "sources": "synthetic_only",
            "windows_hardware_tested": False,
        }

    @application.get("/api/schema")
    async def schema():
        return ContractBundle.model_json_schema()

    @application.get("/api/state")
    async def state():
        async with demo_lock:
            return engine.snapshot()

    @application.get("/api/matches", response_model=list[Match])
    async def list_matches():
        return store.list_matches()

    @application.post("/api/matches", response_model=Match, status_code=201)
    async def create_match(config: MatchConfig):
        try:
            return store.create_match(config)
        except StoreConflict as exc:
            conflict(exc)

    @application.get("/api/matches/{match_id}", response_model=Match)
    async def get_match(match_id: str):
        return require_match(match_id)

    @application.put("/api/matches/{match_id}", response_model=Match)
    async def edit_match(match_id: str, config: MatchConfig):
        try:
            match = store.update_match(match_id, config)
        except StoreConflict as exc:
            conflict(exc)
        if match is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return match

    @application.delete("/api/matches/{match_id}", status_code=204)
    async def remove_match(match_id: str):
        if not store.delete_match(match_id):
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        transcript_feed.clear_match(match_id)
        return Response(status_code=204)

    @application.get("/api/matches/{match_id}/players", response_model=list[RosterPlayer])
    async def get_players(match_id: str):
        result = store.get_roster(match_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.put("/api/matches/{match_id}/players", response_model=list[RosterPlayer])
    async def save_players(match_id: str, roster: list[RosterPlayer]):
        try:
            result = store.replace_roster(match_id, roster)
        except StoreConflict as exc:
            conflict(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.post("/api/matches/{match_id}/resolve-player", response_model=ResolveResult)
    async def resolve_mention(match_id: str, request: ResolveRequest):
        match = require_match(match_id)
        try:
            return resolve_player(match, request.mention, request.team_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/matches/{match_id}/resolve-narration", response_model=NarrationResolution)
    async def resolve_narration_text(match_id: str, request: NarrationResolveRequest):
        # Read-only diagnostic: no event, possession, ball or transcript mutation.
        return resolve_narration(require_match(match_id), request)

    @application.post("/api/matches/{match_id}/resolve-possession", response_model=PossessionEvidence)
    async def resolve_possession(match_id: str, request: PossessionRequest):
        # Explicit text evidence only. No state change, even if a turnover is detected.
        try:
            return detect_possession(require_match(match_id), request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/matches/{match_id}/resolve-region", response_model=RegionEvidence)
    async def resolve_region(match_id: str, request: RegionRequest):
        # Text-only diagnostic, never updates the persistent ball, events or feed.
        try:
            return detect_region(require_match(match_id), request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/matches/{match_id}/resolve-event", response_model=EventEvidence)
    async def resolve_event(match_id: str, request: EventRequest):
        # Diagnostics only: an inferred event never alters score or match history.
        return detect_event(require_match(match_id), request)

    @application.post("/api/matches/{match_id}/resolve-confidence", response_model=ConfidenceEvidence)
    async def resolve_confidence(match_id: str, request: ConfidenceRequest):
        # Heuristic evidence strength: no calibration, capture or state mutation.
        try:
            return assess_confidence(require_match(match_id), request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/matches/{match_id}/guard-ball", response_model=BallGuardDecision)
    async def guard_ball(match_id: str, request: BallGuardRequest):
        # Read-only decision: a candidate is NEVER persisted or sent to the demo.
        # Unverified age is not a real broadcast clock (GN-060/061 pending).
        state = store.get_state(match_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return guard_ball_movement(state.match, state.ball, request)

    @application.post("/api/matches/{match_id}/compare-language", response_model=LLMComparison)
    async def compare_language_text(match_id: str, request: LLMCompareRequest):
        # Opt-in only. Local model I/O is offloaded; result is always read-only.
        match = require_match(match_id)
        return await asyncio.to_thread(compare_language, match, request)

    @application.post("/api/matches/{match_id}/clock/preview", response_model=ClockPreviewResponse)
    async def preview_logical_clock(match_id: str, request: ClockPreviewRequest):
        # A bounded diagnostic, not live clock sync or a persisted event.
        match = require_match(match_id)
        return preview_clock(match.period, request)

    @application.post(
        "/api/matches/{match_id}/sources/delay/preview",
        response_model=RelativeDelayResponse,
    )
    async def preview_source_delays(match_id: str, request: RelativeDelayRequest):
        # GN-061: explicit paired events only; no writes or live source alignment.
        require_match(match_id)
        return preview_relative_delays(request)

    @application.post(
        "/api/matches/{match_id}/events/deduplicate/preview",
        response_model=EventDeduplicationResponse,
    )
    async def preview_events_deduplicated(
        match_id: str, request: EventDeduplicationRequest,
    ):
        # GN-062: pairs are candidate observations, never persisted events.
        require_match(match_id)
        return preview_event_deduplication(request)

    @application.post(
        "/api/matches/{match_id}/sources/selection/preview",
        response_model=SourceSelectionResponse,
    )
    async def preview_source_selection(match_id: str, request: SourceSelectionRequest):
        # GN-063: diagnostic only, no capture started and no match state changed.
        require_match(match_id)
        return preview_active_source(request)

    @application.post(
        "/api/matches/{match_id}/events/fusion/preview",
        response_model=FusionConflictResponse,
    )
    async def preview_conflicting_events(match_id: str, request: FusionConflictRequest):
        # GN-064: caller-provided aligned text, diagnostic only, never a state write.
        require_match(match_id)
        return preview_fusion_conflicts(request)

    @application.post(
        "/api/matches/{match_id}/ball/freshness/preview",
        response_model=BallFreshnessResponse,
    )
    async def preview_ball_age(match_id: str, request: BallFreshnessRequest):
        # GN-065: capture-time TTL diagnostic; no timer or SQLite write.
        require_match(match_id)
        return preview_ball_freshness(request)

    @application.get("/api/matches/{match_id}/flow")
    async def get_match_flow(match_id: str):
        result = flow.get(match_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.post("/api/matches/{match_id}/actions")
    async def apply_match_action(match_id: str, action: MatchAction):
        try:
            result = flow.apply(match_id, action)
        except StoreConflict as exc:
            conflict(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.get("/api/matches/{match_id}/corrections")
    async def get_match_corrections(match_id: str):
        result = corrections.list(match_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.post("/api/matches/{match_id}/corrections", status_code=201)
    async def apply_match_correction(match_id: str, correction: ManualCorrection):
        try:
            result = corrections.apply(match_id, correction)
        except StoreConflict as exc:
            conflict(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.get("/api/matches/{match_id}/sources", response_model=list[AudioSource])
    async def get_sources(match_id: str):
        result = store.get_sources(match_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.put("/api/matches/{match_id}/sources", response_model=list[AudioSource])
    async def save_sources(match_id: str, sources: list[AudioSource]):
        try:
            result = store.replace_sources(match_id, sources)
        except StoreConflict as exc:
            conflict(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.get("/api/matches/{match_id}/transcripts")
    async def get_transcripts(
        match_id: str,
        source_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ):
        require_match(match_id)
        registered = {source.id for source in store.get_sources(match_id) or []}
        if source_id is not None and source_id not in registered:
            raise HTTPException(status_code=404, detail="Fonte não encontrada")
        return transcript_feed.snapshot(
            match_id, source_id=source_id, limit=limit,
            allowed_sources=registered,
        )

    @application.websocket("/ws/matches/{match_id}/transcripts")
    async def transcript_websocket(match_id: str, socket: WebSocket):
        if store.get_match(match_id) is None:
            await socket.close(code=1008)
            return
        await socket.accept()
        token, queue = transcript_feed.subscribe(match_id)
        allowed = {source.id for source in store.get_sources(match_id) or []}
        await socket.send_json({
            "kind": "snapshot",
            "data": transcript_feed.snapshot(match_id, allowed_sources=allowed),
        })
        receive_task = asyncio.create_task(socket.receive_text())
        try:
            while True:
                update_task = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {update_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receive_task in done:
                    update_task.cancel()
                    await asyncio.gather(update_task, return_exceptions=True)
                    message_from_client = receive_task.result()  # may raise WebSocketDisconnect
                    if message_from_client == "close":
                        break
                    receive_task = asyncio.create_task(socket.receive_text())
                    continue
                message = update_task.result()
                allowed = {source.id for source in store.get_sources(match_id) or []}
                if message["data"]["source_id"] in allowed:
                    await socket.send_json(message)
        except (WebSocketDisconnect, RuntimeError, OSError, asyncio.CancelledError):
            pass
        finally:
            if 'update_task' in locals() and not update_task.done():
                update_task.cancel()
                await asyncio.gather(update_task, return_exceptions=True)
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
            transcript_feed.unsubscribe(match_id, token)

    @application.get("/api/matches/{match_id}/state", response_model=ContractBundle)
    async def get_persisted_state(match_id: str):
        result = store.get_state(match_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    @application.put("/api/matches/{match_id}/state", response_model=ContractBundle)
    async def save_persisted_state(match_id: str, snapshot: ContractBundle):
        try:
            result = store.replace_state(match_id, snapshot)
        except StoreConflict as exc:
            conflict(exc)
        if result is None:
            raise HTTPException(status_code=404, detail="Partida não encontrada")
        return result

    async def publish(snapshot: dict):
        disconnected = []
        for socket in tuple(clients):
            try:
                await socket.send_json(snapshot)
            except (RuntimeError, WebSocketDisconnect, OSError):
                disconnected.append(socket)
        for socket in disconnected:
            clients.discard(socket)

    @application.post("/api/demo/next")
    async def next_demo():
        async with demo_lock:
            snapshot = engine.step()
            await publish(snapshot)
            return snapshot

    @application.post("/api/demo/reset")
    async def reset_demo():
        async with demo_lock:
            snapshot = engine.reset()
            await publish(snapshot)
            return snapshot

    @application.websocket("/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        # Joining and first state must be atomic relative to broadcasts, or
        # a newly opened browser can receive a new event before an older state.
        async with demo_lock:
            clients.add(socket)
            try:
                await socket.send_json(engine.snapshot())
            except (RuntimeError, WebSocketDisconnect, OSError):
                clients.discard(socket)
                return
        try:
            while True:
                await socket.receive_text()
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
        finally:
            clients.discard(socket)

    return application


app = create_app()
