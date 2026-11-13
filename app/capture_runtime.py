"""Explicit browser-controlled capture. Only text/metadata reach clients.

Up to two explicitly aligned sources; no implicit fusion of unknown clocks.
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

from pydantic import Field, StrictBool, field_validator, model_validator

from app.asr import ASRError, ASRSettings, CPUTranscriber, BYTES_PER_SECOND, asr_diagnostics
from app.asr_vocabulary import build_vocabulary_prompt
from app.asr_windows import WindowSettings, WindowTranscript
from app.audio_capture import CaptureError, pcm_chunks
from app.contracts import Id, StrictModel
from app.gn083_live import LiveObservation, follow_youtube_narration, wait_for_cpu
from app.source_validation import validate_source_urls
from app.youtube_capture import YouTubeResolutionError, youtube_pcm_chunks


class ParallelCaptureSource(StrictModel):
    source_id: Id
    start_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False, strict=True)
    kickoff_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False, strict=True)


class CaptureRequest(StrictModel):
    source_id: Id
    permission_confirmed: StrictBool
    model: Literal["tiny", "base", "small", "medium"] = "base"
    start_seconds: float = Field(default=0, ge=0, le=86400, allow_inf_nan=False, strict=True)
    seconds: float | None = Field(default=60, ge=5, le=600, allow_inf_nan=False, strict=True)
    window_seconds: int = Field(default=12, ge=6, le=30, strict=True)
    cpu_threads: int = Field(default=min(4, os.cpu_count() or 1), ge=1, le=16, strict=True)
    kickoff_seconds: float | None = Field(default=None, ge=0, le=86400, allow_inf_nan=False, strict=True)
    parallel_sources: list[ParallelCaptureSource] = Field(default_factory=list, max_length=1)

    @model_validator(mode="after")
    def aligned_starts(self):
        if self.parallel_sources:
            if self.kickoff_seconds is None:
                raise ValueError("Informe o apito inicial nas duas gravações")
            for source in self.parallel_sources:
                if source.source_id == self.source_id:
                    raise ValueError("Escolha duas fontes diferentes")
                if abs((self.start_seconds-self.kickoff_seconds)-(source.start_seconds-source.kickoff_seconds)) > .25:
                    raise ValueError("Os inícios precisam representar o mesmo tempo após o apito")
        return self

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
        self.sessions: dict[tuple[str, str], dict] = {}
        self.closed = False

    def active(self, match_id: str) -> bool:
        return any(key[0] == match_id and not session["task"].done() for key, session in self.sessions.items())

    def require_idle(self, match_id: str) -> None:
        if self.active(match_id):
            raise CaptureConflict("Pare a captura antes de editar ou excluir esta partida/fontes/elenco")

    def status(self, match_id: str) -> dict:
        sessions = [item for key, item in self.sessions.items() if key[0] == match_id]
        if not sessions:
            return {"state": "idle", "source_id": None, "captured_seconds": 0,
                    "observations": 0, "error_code": None, "audio_retransmitted": False}
        rows = [{key: value for key, value in session.items()
                 if key not in {"task", "captures", "clock", "captured_at"}} for session in sessions]
        if len(rows) == 1:
            return rows[0]
        states = {row["state"] for row in rows}
        state = next((value for value in ("stopping", "running", "starting") if value in states),
                     "error" if states == {"error"} else "stopped" if "stopped" in states else "finished")
        usable_rows = [row for row in rows if row["state"] != "error"] or rows
        return {**rows[0], "state": state, "parallel": True, "streams": rows,
                "captured_seconds": min(row["captured_seconds"] for row in usable_rows),
                "observations": sum(row["observations"] for row in rows),
                "error_code": None if state in ("running", "starting") else rows[0]["error_code"]}

    async def start(self, match_id: str, request: CaptureRequest) -> dict:
        if self.closed:
            raise CaptureConflict("O servidor está encerrando")
        self.require_idle(match_id)
        requests = [request.model_copy(update={"parallel_sources": []})] + [
            request.model_copy(update={"source_id": source.source_id, "start_seconds": source.start_seconds,
                "kickoff_seconds": source.kickoff_seconds, "parallel_sources": []}) for source in request.parallel_sources]
        if sum(not item["task"].done() for item in self.sessions.values()) + len(requests) > 2:
            raise CaptureConflict("Limite de duas capturas simultâneas neste servidor")
        sources = {source.id: source for source in self.store.get_sources(match_id) or []}
        for item in requests:
            source = sources.get(item.source_id)
            if source is None or not source.enabled or not source.url:
                raise CaptureConflict("Selecione uma fonte cadastrada, habilitada e com URL")
            if len(requests) > 1 and source.kind != "youtube":
                raise CaptureConflict("Alinhamento por apito exige duas gravações YouTube")
            validate_source_urls([source])
        for old_key in tuple(self.sessions):
            if old_key[0] == match_id:
                del self.sessions[old_key]
        self.feed.reset_match(match_id)
        self.previews.clear_match(match_id)
        group_id = None
        if len(requests) > 1:
            group_id = self.previews.set_alignment(match_id, {item.source_id: item.start_seconds-item.kickoff_seconds for item in requests})
        try:
            for item in requests:
                await self._start_one(match_id, item, group_id=group_id)
        except Exception:
            await self.stop(match_id)
            raise
        return self.status(match_id)

    async def _start_one(self, match_id: str, request: CaptureRequest, *, group_id: str | None = None) -> None:
        key = (match_id, request.source_id)
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
        if len(self.sessions) >= 32 and key not in self.sessions:
            for old_id in tuple(self.sessions):
                if self.sessions[old_id]["task"].done():
                    del self.sessions[old_id]
                    break
        session = {"state": "starting", "source_id": source.id, "model": request.model,
                   "requested_start_seconds": request.start_seconds,
                   "requested_seconds": request.seconds, "window_seconds": request.window_seconds,
                   "kickoff_seconds": request.kickoff_seconds,
                   "cpu_threads": request.cpu_threads,
                   "captured_seconds": 0., "observations": 0, "error_code": None,
                   "audio_retransmitted": False, "captures": deque(maxlen=256)}
        self.sessions[key] = session
        if group_id is not None:
            session["visual_context"] = group_id
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
                if isinstance(exc, YouTubeResolutionError):
                    code = "youtube_resolution_failed"
                denied = re.search(r"\bupstream_http_(403|404|429|5\d\d)\b", str(exc))
                if isinstance(exc, CaptureError) and denied:
                    code = denied.group(0)
                session.update(state="error", error_code=code)
                self.feed.set_state(match_id, source.id, "error", error_code=(
                    "asr_error" if isinstance(exc, ASRError) else "capture_error"))
            finally:
                session["captures"].clear()
                self.previews.clear_source(match_id, source.id)
                if session["state"] != "error":
                    self.feed.set_state(match_id, source.id, "stopped")

        session["task"] = asyncio.create_task(work())
        def completed(task):
            # A task cancelled before its first turn never enters work/finally.
            if task.cancelled() and self.sessions.get(key) is session:
                session["state"] = "stopped"
                session["captures"].clear()
                self.previews.clear_source(match_id, source.id)
                self.feed.set_state(match_id, source.id, "stopped")
            if not self.active(match_id):
                self.previews.clear_match(match_id)
        session["task"].add_done_callback(completed)

    async def stop(self, match_id: str) -> dict:
        for key, session in self.sessions.items():
            if key[0] != match_id or session["task"].done():
                continue
            if session["state"] != "stopping":
                session["state"] = "stopping"
                session["task"].cancel()
            self.previews.clear_match(match_id)
        return self.status(match_id)

    async def close(self):
        self.closed = True
        for match_id in {key[0] for key in self.sessions}:
            await self.stop(match_id)
        await asyncio.gather(*(item["task"] for item in self.sessions.values()), return_exceptions=True)
