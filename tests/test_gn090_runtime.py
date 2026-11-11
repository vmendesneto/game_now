"""GN-090: secure relay is actually used by production radio/YouTube PCM path."""
from __future__ import annotations

import asyncio
from contextlib import aclosing
import io
from pathlib import Path
import shutil
import subprocess

import pytest

from app import audio_capture, secure_ingest
from app.contracts import AudioSource
from app.source_validation import validate_source_urls
from app.storage import StoreConflict


def radio(url="https://radio.example.org/audio.mp3"):
    return AudioSource(id="radio-secure", name="Test radio", kind="radio",
                       url=url, enabled=True, status="offline")


@pytest.mark.parametrize("url", [
    "http://127.1/live", "http://localhost/live", "http://10.1.2.3/stream",
    "http://169.254.169.254/latest/meta-data/",
    "https://radio.example.org/space here", "https://radio.example.org/hi\r\nInjected: bad",
    "https://radio.example.org\\@public.example.org/stream",
])
def test_source_storage_fails_closed_on_local_or_ambiguous_urls(url):
    with pytest.raises(StoreConflict):
        validate_source_urls([radio(url)])


def test_windows_launcher_does_not_open_lan_listener():
    launcher = (Path(__file__).parents[1] / "iniciar_windows.bat").read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in launcher
    assert "--host 0.0.0.0" not in launcher


def test_network_capture_uses_loopback_not_original_url(monkeypatch):
    launched = []
    entered = []

    class Relay:
        def __init__(self, url, *, http_headers=None):
            assert url == "https://radio.example.org/audio.mp3"
            assert http_headers == {"User-Agent": "Test"}
        def __enter__(self):
            entered.append("start")
            return self
        @property
        def input_url(self):
            return "http://127.0.0.1:43210/token/media.mp3"
        def __exit__(self, *_args):
            entered.append("stop")

    class Process:
        returncode = 0
        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stdout.feed_data(b"\x01\x00" * 8000)
            self.stdout.feed_eof()
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_eof()
        async def wait(self):
            return 0

    async def fake_exec(*args, **kwargs):
        launched.extend(args)
        assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
        return Process()

    monkeypatch.setattr(audio_capture, "SafeMediaRelay", Relay)
    monkeypatch.setattr(audio_capture.shutil, "which", lambda binary: "/usr/bin/ffmpeg")
    monkeypatch.setattr(audio_capture.asyncio, "create_subprocess_exec", fake_exec)

    async def collect():
        async with aclosing(audio_capture.pcm_chunks(
            radio(), chunk_ms=500, http_headers={"User-Agent": "Test"},
        )) as stream:
            return [block async for block in stream]

    assert sum(map(len, asyncio.run(collect()))) == 16000
    assert "https://radio.example.org/audio.mp3" not in launched
    assert launched[launched.index("-i") + 1].startswith("http://127.0.0.1:")
    assert launched[launched.index("-protocol_whitelist") + 1] == "http,tcp,crypto"
    assert "-headers" not in launched
    assert entered == ["start", "stop"]


def test_mp3_decoding_via_relay_fulfills_pcm_contract(monkeypatch, tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "FFmpeg must be installed in CI"
    media = tmp_path / "audio.mp3"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=620:duration=1",
        "-c:a", "libmp3lame", str(media),
    ], check=True, capture_output=True)
    content = media.read_bytes()
    requests = []

    class Response:
        status = 200
        def __init__(self):
            self.stream = io.BytesIO(content)
        def getheader(self, key):
            return "audio/mpeg" if key == "Content-Type" else None
        def read(self, count=-1):
            return self.stream.read(count)

    class Connection:
        def close(self):
            pass

    def fake_remote(url, headers):
        requests.append(url)
        return Connection(), Response(), url

    monkeypatch.setattr(secure_ingest, "_open_redirects", fake_remote)

    async def capture():
        async with aclosing(audio_capture.pcm_chunks(radio(), chunk_ms=250)) as stream:
            return [part async for part in stream]

    blocks = asyncio.run(capture())
    assert sum(map(len, blocks)) >= 25000
    assert all(len(part) <= 8000 and len(part) % 2 == 0 for part in blocks)
    assert requests and set(requests) == {"https://radio.example.org/audio.mp3"}
