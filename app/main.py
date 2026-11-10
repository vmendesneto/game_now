"""HTTP + WebSocket entry point. No audio or video is ever served."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.contracts import ContractBundle
from app.demo import DemoEngine

STATIC = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    application = FastAPI(title="Game Now", version="0.1.0")
    engine = DemoEngine()
    clients: set[WebSocket] = set()

    application.mount("/static", StaticFiles(directory=STATIC), name="static")

    @application.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC / "index.html")

    @application.get("/health")
    async def health():
        return {
            "status": "ok",
            "mode": "synthetic_demo",
            "ffmpeg": {"available": shutil.which("ffmpeg") is not None,
                       "path": shutil.which("ffmpeg")},
            "asr": "not_installed_or_configured",
            "storage": "volatile_memory_only",
            "sources": "synthetic_only",
            "windows_hardware_tested": False,
        }

    @application.get("/api/schema")
    async def schema():
        return ContractBundle.model_json_schema()

    @application.get("/api/state")
    async def state():
        return engine.snapshot()

    async def publish(state: dict):
        disconnected = []
        for socket in tuple(clients):
            try:
                await socket.send_json(state)
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
