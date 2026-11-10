"""HTTP + WebSocket entry point. No audio or video is ever served."""
from __future__ import annotations

from pathlib import Path
import shutil

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.configuration import MatchConfig, RosterPlayer
from app.contracts import AudioSource, ContractBundle, Match
from app.demo import DemoEngine
from app.entities import ResolveRequest, ResolveResult, resolve_player
from app.match_flow import MatchAction, MatchFlowService
from app.storage import SQLiteStore, StoreConflict

STATIC = Path(__file__).resolve().parent / "static"


def create_app(database_path: str | Path | None = None) -> FastAPI:
    application = FastAPI(title="Game Now", version="0.2.0")
    engine = DemoEngine()
    store = SQLiteStore(database_path)
    flow = MatchFlowService(store)
    application.state.store = store
    clients: set[WebSocket] = set()

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
            "asr": "not_installed_or_configured",
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
        snapshot = engine.step()
        await publish(snapshot)
        return snapshot

    @application.post("/api/demo/reset")
    async def reset_demo():
        snapshot = engine.reset()
        await publish(snapshot)
        return snapshot

    @application.websocket("/ws")
    async def websocket(socket: WebSocket):
        await socket.accept()
        clients.add(socket)
        try:
            await socket.send_json(engine.snapshot())
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(socket)

    return application


app = create_app()
