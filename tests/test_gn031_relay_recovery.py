"""GN-031/GN-090 regression: recorded YouTube, early CDN 403 and safe diagnostics.

All upstream connections are mocked. These tests do NOT access YouTube or
make assumptions about permissions or availability of the supplied video.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing
import io
import shutil
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from app import secure_ingest, youtube_capture
from app.audio_capture import CaptureError, pcm_chunks
from app.contracts import AudioSource


def youtube_source():
    return AudioSource(id="youtube-test", name="Recording", kind="youtube",
                       url="https://www.youtube.com/watch?v=EXAMPLE",
                       enabled=True, status="offline")


@pytest.mark.parametrize(("url", "expected"), [
    ("https://rr1---sn-foo.googlevideo.com/videoplayback?expire=123", True),
    ("https://googlevideo.com/videoplayback?key=abc", True),
    ("https://rr1---sn-foo.googlevideo.com/api/manifest/hls_playlist", False),
    ("https://notgooglevideo.com/videoplayback", False),
    ("http://rr1.googlevideo.com/videoplayback", False),
    ("https://cdn.example.org/audio.m4a", False),
])
def test_only_fresh_googlevideo_media_needs_initial_wait(url, expected):
    assert youtube_capture._needs_playback_wait(url) is expected


@pytest.mark.parametrize("cdn", [
    "https://rr1---sn-foo.googlevideo.com/videoplayback?expire=123",
    "https://cdn.example.org/audio.m4a",
])
def test_playback_wait_happens_before_first_pcm_request(monkeypatch, cdn):
    events = []
    async def fake_resolve(*args, **kwargs):
        events.append("resolved")
        return youtube_capture.ResolvedLiveAudio(
            cdn, "251", {"User-Agent": "Test"}
        )
    async def fake_sleep(seconds):
        events.append(("wait", seconds))
    async def fake_pcm(source, **kwargs):
        events.append(("pcm", source.url))
        yield b"\x00\x00" * 200

    monkeypatch.setattr(youtube_capture, "resolve_live_audio", fake_resolve)
    monkeypatch.setattr(youtube_capture.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(youtube_capture, "pcm_chunks", fake_pcm)

    async def collect():
        async with aclosing(youtube_capture.youtube_pcm_chunks(
            youtube_source(),
        )) as stream:
            return [chunk async for chunk in stream]

    assert asyncio.run(collect()) == [b"\x00\x00" * 200]
    assert events[0] == "resolved"
    if "googlevideo.com" in cdn:
        assert events[1] == ("wait", 5.5)
        assert events[2] == ("pcm", cdn)
    else:
        assert events[1] == ("pcm", cdn)


class Response:
    status = 403
    def getheader(self, name):
        return None
    def read(self, n=-1):
        return b""


class Connection:
    def close(self):
        pass


def test_upstream_403_is_not_retried_or_exposed_in_relay_response(monkeypatch):
    remote = "https://cdn.example.org/video.m4a?sig=SECRET_TOKEN_DO_NOT_LOG"
    requests = []
    def blocked(url, headers):
        requests.append(url)
        return Connection(), Response(), url
    monkeypatch.setattr(secure_ingest, "_open_redirects", blocked)
    with secure_ingest.SafeMediaRelay(remote) as relay:
        with pytest.raises(HTTPError) as exc:
            urlopen(relay.input_url)
        assert exc.value.code == 502
        body = exc.value.read().decode("utf-8", errors="replace")
        assert "SECRET_TOKEN_DO_NOT_LOG" not in body
        assert "cdn.example.org" not in body
        assert relay.failure_reason == "upstream_http_403"
    assert requests == [remote]


def test_pcm_surfaces_safe_upstream_error_instead_of_generic_local_5xx(monkeypatch):
    assert shutil.which("ffmpeg"), "CI must provide FFmpeg"
    signed_url = "https://cdn.example.org/media.m4a?sig=DO_NOT_LEAK"

    def blocked(url, headers):
        return Connection(), Response(), url

    monkeypatch.setattr(secure_ingest, "_open_redirects", blocked)
    source = AudioSource(id="radio-test", name="Radio", kind="radio",
                         url=signed_url, enabled=True, status="offline")

    async def collect():
        async with aclosing(pcm_chunks(source)) as stream:
            return [chunk async for chunk in stream]

    with pytest.raises(CaptureError) as err:
        asyncio.run(collect())
    message = str(err.value)
    assert "upstream_http_403" in message
    assert "DO_NOT_LEAK" not in message
    assert "cdn.example.org" not in message
    assert "127.0.0.1" not in message
