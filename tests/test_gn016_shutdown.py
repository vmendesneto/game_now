"""GN-016: process and worker lifecycles, without network media.

Proves cleanup in CI Linux and simulated restart. Windows physical proof GN-085
must still be performed with FFmpeg/yt-dlp installed on the user's PC.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
import os
from pathlib import Path
import time
import wave

import pytest

from app.audio_buffer import MultiSourceAudioBuffer
from app.audio_capture import pcm_chunks
from app.capture_supervisor import CaptureSessionController, CaptureSupervisor, RetryPolicy
from app.contracts import AudioSource


def radio(name: str) -> AudioSource:
    return AudioSource(id=f"radio-{name}", name=name, kind="radio",
                       url="https://radio.example.org/live", enabled=True,
                       status="offline")


def test_controller_stops_each_source_and_restart_keeps_no_old_worker():
    async def scenario():
        started = {key: asyncio.Event() for key in ("a", "b")}
        finally_closed = []

        async def capture(source):
            try:
                started[source.name].set()
                while True:
                    yield b"\x01\x00" * 512
                    await asyncio.sleep(.005)
            finally:
                finally_closed.append(source.name)

        supervisor = CaptureSupervisor(
            MultiSourceAudioBuffer(), radio_capture=capture,
            policy=RetryPolicy(idle_seconds=10)
        )
        async with CaptureSessionController(supervisor) as controller:
            await controller.start(radio("a"))
            await controller.start(radio("b"))
            await asyncio.wait_for(asyncio.gather(*(e.wait() for e in started.values())),
                                   timeout=2)
            with pytest.raises(ValueError, match="already"):
                await controller.start(radio("a"))
            await controller.stop("radio-a")
            await controller.stop("radio-a")
            assert supervisor.status("radio-a").state == "stopped"
            assert supervisor.status("radio-b").state in ("connecting", "online")
            await controller.start(radio("a"))  # safe reactivation of same ID
            await asyncio.sleep(.015)
        assert sorted(finally_closed) == ["a", "a", "b"]
        assert all(v.state == "stopped" for v in supervisor.statuses())
        assert not controller._tasks
        with pytest.raises(RuntimeError, match="closed"):
            await controller.start(radio("a"))
        # Simulate a fresh process (no persisted workers, no stale registry).
        fresh_supervisor = CaptureSupervisor(
            MultiSourceAudioBuffer(), radio_capture=capture,
            policy=RetryPolicy(idle_seconds=10)
        )
        async with CaptureSessionController(fresh_supervisor) as fresh:
            await fresh.start(radio("a"))
            await asyncio.sleep(.02)
        assert fresh_supervisor.status("radio-a").state == "stopped"

    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "posix", reason="Unix subprocess PID probe; physical Windows test remains GN-085")
def test_closing_pcm_iterator_reaps_real_child_process(tmp_path, monkeypatch):
    """The source is fake PCM, but subprocess creation/shutdown is real."""
    fake = tmp_path / "fake_ffmpeg"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys,time\n"
        "with open(os.environ['GN016_PID_FILE'],'w') as f: f.write(str(os.getpid()))\n"
        "while True:\n"
        "  sys.stdout.buffer.write(b'\\x01\\x00'*8000)\n"
        "  sys.stdout.buffer.flush()\n"
        "  time.sleep(0.02)\n",
        encoding="utf-8"
    )
    fake.chmod(0o755)
    fixture = tmp_path / "input.mp3"
    fixture.write_bytes(b"not inspected by the dummy subprocess")
    pid_file = tmp_path / "child.pid"
    monkeypatch.setenv("GN016_PID_FILE", str(pid_file))

    async def consume_one():
        async with aclosing(pcm_chunks(
            radio("a"), ffmpeg_binary=str(fake), fixture_file=fixture
        )) as stream:
            item = await asyncio.wait_for(anext(stream), timeout=3)
            assert item and len(item) % 2 == 0

    try:
        asyncio.run(consume_one())
        pid = int(pid_file.read_text(encoding="utf-8"))
        # pcm_chunks() must terminate and reap the subprocess even when
        # consumption ends before FFmpeg emits EOF.
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if pid_file.exists():
            pid = int(pid_file.read_text(encoding="utf-8"))
            try:
                os.kill(pid, 9)  # only emergency cleanup if regression occurs
            except ProcessLookupError:
                pass


def test_stop_timeout_and_bad_reopen_arguments():
    async def scenario():
        stop = asyncio.Event()
        async def stuck(source):
            try:
                while True:
                    yield b"\x00\x00" * 200
                    await asyncio.sleep(.01)
            finally:
                stop.set()
        supervisor = CaptureSupervisor(
            MultiSourceAudioBuffer(), radio_capture=stuck,
            policy=RetryPolicy(idle_seconds=5)
        )
        controller = CaptureSessionController(supervisor)
        with pytest.raises(ValueError, match="enabled"):
            await controller.start(radio("a").model_copy(update={"enabled":False}))
        with pytest.raises(ValueError, match="timeout"):
            await controller.stop("missing", timeout_seconds=0)
        await controller.start(radio("a"))
        await asyncio.sleep(.02)
        await controller.close()
        await controller.close()
        assert stop.is_set()
        assert supervisor.status("radio-a").state == "stopped"
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != "nt", reason="Native Windows FFmpeg process cleanup")
def test_windows_early_close_waits_for_real_ffmpeg(tmp_path, monkeypatch):
    """No external audio: stop native FFmpeg early and await its process handle."""
    fixture = tmp_path / "silence.wav"
    with wave.open(str(fixture), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * 16000 * 60)
    processes = []
    original = asyncio.create_subprocess_exec

    async def tracked_launch(*args, **kwargs):
        process = await original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", tracked_launch)

    async def scenario():
        async with aclosing(pcm_chunks(radio("windows"), fixture_file=fixture)) as stream:
            chunk = await asyncio.wait_for(anext(stream), timeout=5)
            assert len(chunk) > 0 and len(chunk) % 2 == 0
            assert len(processes) == 1 and processes[0].returncode is None
        # returncode is set only after asyncio observes the native process exit.
        assert processes[0].returncode is not None
        assert await asyncio.wait_for(processes[0].wait(), timeout=1) is not None

    asyncio.run(scenario())
