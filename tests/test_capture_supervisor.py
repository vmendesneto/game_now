"""GN-033: deterministic loss/recovery tests; no external streams used."""
import asyncio
from datetime import timezone

import pytest

from app.audio_buffer import MultiSourceAudioBuffer
from app.audio_capture import CaptureError
from app.capture_supervisor import CaptureSupervisor, RetryPolicy
from app.contracts import AudioSource


def source(kind="radio", name="a"):
    url = ("https://www.youtube.com/live/allowed" if kind == "youtube"
           else "https://radio.example.org/stream.mp3")
    return AudioSource(id=f"{kind}-{name}", name=name, kind=kind,
                       url=url, enabled=True, status="offline")


def test_radio_recovers_from_disconnect_and_retains_pcm():
    async def scenario():
        attempts = []
        delays = []
        stopped = asyncio.Event()

        async def radio(item):
            attempts.append(item.id)
            yield b"\x01\x00" * 1600
            if len(attempts) == 1:
                raise CaptureError("Connection lost")
            return

        async def pause(event, delay):
            delays.append(delay)
            if len(delays) == 2:
                event.set()

        buffer = MultiSourceAudioBuffer()
        supervisor = CaptureSupervisor(
            buffer, radio_capture=radio,
            pause=pause, policy=RetryPolicy(initial_seconds=.25, maximum_seconds=2),
        )
        await supervisor.run(source(), stopped)
        assert len(attempts) == 2
        assert delays == [.25, .5]
        assert len(buffer.snapshot("radio-a")) == 2
        status = supervisor.status("radio-a")
        assert status.state == "stopped"
        assert status.attempts == 2
        assert status.reconnects == 1
        assert status.pcm_bytes == 6400
        assert status.last_audio_at.tzinfo == timezone.utc
        assert status.last_error == "stream_ended"

    asyncio.run(scenario())


def test_youtube_resolves_afresh_on_every_retry_and_backoff_is_bounded():
    async def scenario():
        attempts = []
        delays = []
        stopped = asyncio.Event()

        async def youtube(item):
            attempts.append(item.url)
            raise CaptureError("https://googlevideo.example/signed?token=SECRET")
            yield b"not-reached"

        async def pause(event, delay):
            delays.append(delay)
            if len(delays) == 4:
                event.set()

        supervisor = CaptureSupervisor(
            MultiSourceAudioBuffer(), youtube_capture=youtube,
            pause=pause,
            policy=RetryPolicy(initial_seconds=.1, maximum_seconds=.4),
        )
        await supervisor.run(source("youtube"), stopped)
        assert len(attempts) == 4
        assert delays == [.1, .2, .4, .4]
        result = supervisor.status("youtube-a")
        assert result.attempts == 4
        assert result.reconnects == 3
        assert result.last_error == "capture_error"
        assert "SECRET" not in repr(result)
        assert "googlevideo" not in repr(result)

    asyncio.run(scenario())


def test_simultaneous_workers_keep_sources_isolated():
    async def scenario():
        stop_a, stop_b = asyncio.Event(), asyncio.Event()

        async def radio(item):
            yield b"\x01\x00" * 10
            await asyncio.sleep(0)
            stop_a.set()

        async def youtube(item):
            yield b"\x02\x00" * 15
            await asyncio.sleep(0)
            stop_b.set()

        buffer = MultiSourceAudioBuffer()
        supervisor = CaptureSupervisor(buffer, radio_capture=radio,
                                       youtube_capture=youtube)
        await asyncio.gather(supervisor.run(source("radio"), stop_a),
                             supervisor.run(source("youtube"), stop_b))
        assert buffer.snapshot("radio-a")[0].pcm == b"\x01\x00" * 10
        assert buffer.snapshot("youtube-a")[0].pcm == b"\x02\x00" * 15
        assert all(status.state == "stopped" for status in supervisor.statuses())

    asyncio.run(scenario())


def test_idle_stream_is_cancelled_and_retried():
    async def scenario():
        stop = asyncio.Event()
        delays = []

        async def radio(item):
            await asyncio.sleep(5)
            yield b"\x01\x00"

        async def pause(event, seconds):
            delays.append(seconds)
            event.set()

        supervisor = CaptureSupervisor(
            MultiSourceAudioBuffer(), radio_capture=radio, pause=pause,
            policy=RetryPolicy(initial_seconds=.1, maximum_seconds=1,
                               idle_seconds=.015),
        )
        await asyncio.wait_for(supervisor.run(source(), stop), timeout=.5)
        assert delays == [.1]
        assert supervisor.status("radio-a").attempts == 1
        assert supervisor.status("radio-a").pcm_bytes == 0

    asyncio.run(scenario())


def test_stop_interrupts_stalled_stream_and_no_retry():
    async def scenario():
        stop = asyncio.Event()
        calls = []

        async def radio(item):
            calls.append(1)
            await asyncio.sleep(10)
            yield b"\x00\x00"

        supervisor = CaptureSupervisor(
            MultiSourceAudioBuffer(), radio_capture=radio,
            policy=RetryPolicy(idle_seconds=30),
        )
        task = asyncio.create_task(supervisor.run(source(), stop))
        await asyncio.sleep(.02)
        stop.set()
        await asyncio.wait_for(task, timeout=.5)
        assert calls == [1]
        assert supervisor.status("radio-a").state == "stopped"

    asyncio.run(scenario())


def test_reject_invalid_policy_disabled_source_and_parallel_same_id():
    with pytest.raises(ValueError):
        RetryPolicy(initial_seconds=0)
    async def scenario():
        supervisor = CaptureSupervisor(MultiSourceAudioBuffer())
        stopped = asyncio.Event()
        disabled = source().model_copy(update={"enabled": False})
        with pytest.raises(ValueError, match="enabled"):
            await supervisor.run(disabled, stopped)

        entered = asyncio.Event()
        async def radio(item):
            entered.set()
            await asyncio.sleep(30)
            yield b"\x00\x00"

        supervisor = CaptureSupervisor(MultiSourceAudioBuffer(),
                                       radio_capture=radio)
        task = asyncio.create_task(supervisor.run(source(), stopped))
        await asyncio.wait_for(entered.wait(), timeout=.5)
        with pytest.raises(ValueError, match="already"):
            await supervisor.run(source(), asyncio.Event())
        stopped.set()
        await asyncio.wait_for(task, timeout=.5)
    asyncio.run(scenario())
