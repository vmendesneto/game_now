"""GN-031 partial: deterministic yt-dlp resolver behavior; NOT a live stream proof."""
import asyncio
from contextlib import aclosing
import json
from pathlib import Path

import pytest

from app.audio_capture import CaptureError
from app.contracts import AudioSource
import app.youtube_capture as youtube_capture


def source(name="normal"):
    return AudioSource(id="youtube-test", name="YouTube", kind="youtube",
                       url=f"https://www.youtube.com/live/{name}",
                       enabled=True, status="offline")


def fake_ytdlp(tmp_path: Path):
    executable = tmp_path / "fake-yt-dlp"
    executable.write_text('''#!/usr/bin/env python3
import json,sys,time
link=sys.argv[-1]
if "restricted" in link:
    print("Broadcast unavailable",file=sys.stderr)
    sys.exit(3)
if "sleeping" in link:
    time.sleep(2)
if "invalidjson" in link:
    print("{not-json")
    sys.exit(0)
live=not ("notlive" in link)
formats=[
    {"format_id":"video","vcodec":"avc1","acodec":"aac",
     "url":"https://cdn.example.org/video.mp4","abr":1000},
    {"format_id":"audio-low","vcodec":"none","acodec":"aac",
     "url":"https://cdn.example.org/audio-low.m3u8","abr":48},
    {"format_id":"audio-high","vcodec":"none","acodec":"aac",
     "url":"https://cdn.example.org/audio-high.m3u8","abr":128,
     "http_headers":{"User-Agent":"GameNow-Test","Cookie":"do-not-forward"}},
]
if "noaudio" in link:
    formats=formats[:1]
if "privatecdn" in link:
    formats[-1]["url"]="http://127.0.0.1/private"
print(json.dumps({"is_live":live,"live_status":"is_live" if live else "not_live",
                  "formats":formats}))
''', encoding="utf-8")
    executable.chmod(0o755)
    return str(executable)


def test_live_audio_only_selection_excludes_cookies(tmp_path):
    executable=fake_ytdlp(tmp_path)
    resolved=asyncio.run(youtube_capture.resolve_live_audio(
        source(),yt_dlp_binary=executable))
    assert resolved.format_id=="audio-high"
    assert resolved.url=="https://cdn.example.org/audio-high.m3u8"
    assert resolved.headers=={"User-Agent":"GameNow-Test"}
    assert "Cookie" not in resolved.headers


@pytest.mark.parametrize("name,error", [
    ("restricted", "unavailable or restricted"),
    ("notlive", "not currently live"),
    ("noaudio", "audio-only"),
    ("privatecdn", "non-public"),
    ("invalidjson", "invalid metadata"),
])
def test_resolver_fails_closed_when_stream_cannot_be_used(tmp_path,name,error):
    binary=fake_ytdlp(tmp_path)
    with pytest.raises(CaptureError,match=error):
        asyncio.run(youtube_capture.resolve_live_audio(
            source(name),yt_dlp_binary=binary))


def test_missing_binary_disabled_source_and_timeout(tmp_path):
    binary=fake_ytdlp(tmp_path)
    with pytest.raises(CaptureError,match="yt-dlp not found"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source(),yt_dlp_binary="missing-yt-dlp-game-now"))
    disabled=source().model_copy(update={"enabled":False})
    with pytest.raises(CaptureError,match="enabled"):
        asyncio.run(youtube_capture.resolve_live_audio(disabled,yt_dlp_binary=binary))
    with pytest.raises(CaptureError,match="timed out"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source("sleeping"),yt_dlp_binary=binary,timeout=0.05))


def test_youtube_pcm_uses_resolved_audio_not_video(tmp_path,monkeypatch):
    executable=fake_ytdlp(tmp_path)
    parameters=[]
    async def fake_pcm(audio_source,**kwargs):
        parameters.append((audio_source,kwargs))
        yield b"\x00\x00" * 1600
    monkeypatch.setattr(youtube_capture,"pcm_chunks",fake_pcm)
    async def collect():
        async with aclosing(youtube_capture.youtube_pcm_chunks(
                source(),yt_dlp_binary=executable)) as stream:
            return [chunk async for chunk in stream]
    blocks=asyncio.run(collect())
    assert blocks==[b"\x00\x00"*1600]
    assert parameters[0][0].kind=="radio"
    assert parameters[0][0].url.endswith("audio-high.m3u8")
    assert parameters[0][1]["http_headers"]=={"User-Agent":"GameNow-Test"}
