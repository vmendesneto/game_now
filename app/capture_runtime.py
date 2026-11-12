"""Explicit browser-controlled capture. Only text/metadata reach clients.

One selected source per match; no implicit fusion of unsynchronized broadcasts.
Workers and models are volatile and never restart just because a server starts.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import re
import os
import shutil
import sys
import time
from typing import Literal

from pydantic import Field, StrictBool, field_validator

from app.asr import ASRError, ASRSettings, CPUTranscriber, BYTES_PER_SECOND, asr_diagnostics
from app.asr_vocabulary import build_vocabulary_prompt
from app.asr_windows import WindowSettings, WindowTranscript
from app.audio_capture import CaptureError, pcm_chunks
from app.contracts import Id, StrictModel
from app.gn083_live import LiveObservation, follow_youtube_narration, wait_for_cpu
from app.source_validation import validate_source_urls
from app.youtube_capture import youtube_pcm_chunks


class CaptureRequest(StrictModel):
    source_id: Id
    permission_confirmed: StrictBool
    model: Literal["tiny", "base", "small", "medium"] = "base"
    start_seconds: float = Field(default=0, ge=0, le=86400, allow_inf_nan=False, strict=True)
    seconds: float | None = Field(default=60, ge=5, le=600, allow_inf_nan=False, strict=True)
    window_seconds: int = Field(default=12, ge=6, le=30, strict=True)
    cpu_threads: int = Field(default=min(4, os.cpu_count() or 1), ge=1, le=16, strict=True)

    @field_validator("permission_confirmed")
    @classmethod
    def require_permission(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Confirme autorização para captar e analisar esta fonte")
        return value


class CaptureConflict(ValueError):
    pass


def executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    sibling = Path(sys.executable).parent / (name + (".exe" if sys.platform == "win32" else ""))
    return str(sibling) if sibling.is_file() else name


class CaptureRuntime:
    def __init__(self, store, feed, previews, *, runner=None):
        self.store, self.feed, self.previews = store, feed, previews
        self.runner = runner or follow_youtube_narration
        self.check_tools = runner is None
        self.sessions: dict[str, dict] = {}
        self.closed = False

    def active(self, match_id: str) -> bool:
        session = self.sessions.get(match_id)
        return bool(session and not session["task"].done())

    def require_idle(self, match_id: str) -> None:
        if self.active(match_id):
            raise CaptureConflict("Pare a captura antes de editar ou excluir esta partida/fontes/elenco")

    def status(self, match_id: str) -> dict:
        session = self.sessions.get(match_id)
        if session is None:
            return {"state": "idle", "source_id": None, "captured_seconds": 0,
                    "observations": 0, "error_code": None, "audio_retransmitted": False}
        return {key: value for key, value in session.items()
                if key not in {"task", "captures", "clock", "captured_at"}}

    async def start(self, match_id: str, request: CaptureRequest) -> dict:
        if self.closed:
            raise CaptureConflict("O servidor está encerrando")
        self.require_idle(match_id)
        if sum(not item["task"].done() for item in self.sessions.values()) >= 2:
            raise CaptureConflict("Limite de duas capturas simultâneas neste servidor")
        match = self.store.get_match(match_id)
        source = next((item for item in self.store.get_sources(match_id) or []
                       if item.id == request.source_id), None)
        if match is None or source is None or not source.enabled or not source.url:
            raise CaptureConflict("Selecione uma fonte cadastrada, habilitada e com URL")
        validate_source_urls([source])
        if source.kind != "youtube" and request.start_seconds:
            raise CaptureConflict("Início no vídeo só pode ser usado com uma gravação YouTube")
        if self.check_tools:
            if not asr_diagnostics()["installed"]:
                raise CaptureConflict("Instale requirements-asr.txt para usar reconhecimento local")
            if shutil.which(executable("ffmpeg")) is None:
                raise CaptureConflict("FFmpeg não encontrado no servidor")
            if source.kind == "youtube" and shutil.which(executable("yt-dlp")) is None:
                raise CaptureConflict("yt-dlp não encontrado no servidor")
        if len(self.sessions) >= 32 and match_id not in self.sessions:
            for old_id in tuple(self.sessions):
                if not self.active(old_id):
                    del self.sessions[old_id]
                    break
        self.feed.reset_match(match_id)
        self.previews.clear_match(match_id)
        session = {"state": "starting", "source_id": source.id, "model": request.model,
                   "requested_start_seconds": request.start_seconds,
                   "requested_seconds": request.seconds, "window_seconds": request.window_seconds,
                   "cpu_threads": request.cpu_threads,
                   "captured_seconds": 0., "observations": 0, "error_code": None,
                   "audio_retransmitted": False, "captures": deque(maxlen=256)}
        self.sessions[match_id] = session
        self.feed.set_state(match_id, source.id, "buffering")

        def received(byte_count):
            session["captured_seconds"] += byte_count / BYTES_PER_SECOND
            now = datetime.now(timezone.utc)
            session["captures"].append((session["captured_seconds"], now, time.monotonic()))
            if session["state"] != "stopping":
                session["state"] = "running"
            self.feed.observe_pcm(match_id, source.id, byte_count)

        async def observation(row):
            if session["state"] == "stopping":
                return
            capture = next((item for item in session["captures"]
                            if item[0] + .001 >= row["end_seconds"]), None)
            age = max(0, time.monotonic() - capture[2]) if capture else 86400.
            if len(row["text"]) > 2048:
                return  # Do not truncate away negation or advertisement context.
            update = WindowTranscript(source_id=source.id, sequence=row["sequence"],
                                      start_seconds=row["start_seconds"], end_seconds=row["end_seconds"],
                                      language="pt", raw_text=row["text"], new_text=row["text"])
            self.feed.publish(match_id, source.id, update,
                              captured_at=capture[1] if capture else datetime.now(timezone.utc))
            self.previews.receive(match, LiveObservation(**row, local_capture_age_seconds=age))
            session["observations"] += 1

        async def capture(item, **options):
            # Pacing keeps recordings comparable to live narration and bounds backlog.
            options["realtime"] = True
            if request.start_seconds:
                options["start_seconds"] = request.start_seconds
            if source.kind == "youtube":
                stream = youtube_pcm_chunks(item, **options)
            else:
                options.pop("yt_dlp_binary", None)
                stream = pcm_chunks(item, **options)
            from contextlib import aclosing
            async with aclosing(stream):
                async for block in stream:
                    yield block

        async def work():
            try:
                model_options = {}
                if self.check_tools:
                    transcriber = CPUTranscriber(ASRSettings(
                        model=request.model, max_seconds=60,
                        cpu_threads=request.cpu_threads,
                        initial_prompt=build_vocabulary_prompt(match)))
                    await wait_for_cpu(transcriber.prepare)
                    model_options["transcriber"] = transcriber
                await self.runner(source.url, match, source_id=source.id, source_kind=source.kind,
                                  model=request.model, max_seconds=request.seconds,
                                  yt_dlp_binary=executable("yt-dlp"), ffmpeg_binary=executable("ffmpeg"),
                                  on_observation=observation, on_pcm=received, capture_factory=capture,
                                  window_settings=WindowSettings(window_ms=request.window_seconds * 1000,
                                                                 overlap_ms=2000), **model_options)
                session["state"] = "finished"
            except asyncio.CancelledError:
                session["state"] = "stopped"
            except Exception as exc:
                # Never expose exception messages: upstream errors may carry signed URLs.
                code = "asr_failed" if isinstance(exc, ASRError) else "capture_failed"
                denied = re.search(r"\bupstream_http_(403|404|429|5\d\d)\b", str(exc))
                if isinstance(exc, CaptureError) and denied:
                    code = denied.group(0)
                session.update(state="error", error_code=code)
                self.feed.set_state(match_id, source.id, "error", error_code=(
                    "asr_error" if isinstance(exc, ASRError) else "capture_error"))
            finally:
                session["captures"].clear()
                self.previews.clear_match(match_id)
                if session["state"] != "error":
                    self.feed.set_state(match_id, source.id, "stopped")

        session["task"] = asyncio.create_task(work())
        def completed(task):
            # A task cancelled before its first turn never enters work/finally.
            if task.cancelled() and self.sessions.get(match_id) is session:
                session["state"] = "stopped"
                session["captures"].clear()
                self.previews.clear_match(match_id)
                self.feed.set_state(match_id, source.id, "stopped")
        session["task"].add_done_callback(completed)
        return self.status(match_id)

    async def stop(self, match_id: str) -> dict:
        if self.active(match_id):
            session = self.sessions[match_id]
            if session["state"] != "stopping":
                session["state"] = "stopping"
                session["task"].cancel()
            self.previews.clear_match(match_id)
        return self.status(match_id)

    async def close(self):
        self.closed = True
        for match_id in tuple(self.sessions):
            await self.stop(match_id)
        await asyncio.gather(*(item["task"] for item in self.sessions.values()), return_exceptions=True)
