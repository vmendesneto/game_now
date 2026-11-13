"""GN-031 partial: deterministic yt-dlp resolver behavior; NOT a live stream proof."""
import asyncio
from contextlib import aclosing
import json
from pathlib import Path

import pytest

from app.audio_capture import CaptureError
from app.contracts import AudioSource
import app.youtube_capture as youtube_capture

pytestmark = pytest.mark.usefixtures("python_script_launchers")


@pytest.mark.parametrize("recorded", [True, False])
def test_seek_is_forwarded_only_for_confirmed_recordings(monkeypatch, recorded):
    async def resolve(*args, **kwargs):
        return youtube_capture.ResolvedLiveAudio(
            url="https://cdn.example.org/audio", format_id="test", headers={},
            is_recording=recorded,
        )
    calls = []

    async def decode(item, **options):
        calls.append(options)
        yield b"\x00\x00"

    monkeypatch.setattr(youtube_capture, "resolve_live_audio", resolve)
    monkeypatch.setattr(youtube_capture, "pcm_chunks", decode)

    async def collect():
        async with aclosing(youtube_capture.youtube_pcm_chunks(source(), start_seconds=575)) as stream:
            return [block async for block in stream]

    if recorded:
        assert asyncio.run(collect()) == [b"\x00\x00"]
        assert calls[0]["start_seconds"] == 575
    else:
        with pytest.raises(CaptureError, match="confirmed recorded"):
            asyncio.run(collect())
        assert calls == []


def source(name="normal"):
    return AudioSource(id="youtube-test", name="YouTube", kind="youtube",
                       url=f"https://www.youtube.com/live/{name}",
                       enabled=True, status="offline")


def test_pcm_resolution_failure_is_typed_and_does_not_start_decoder(monkeypatch):
    async def resolve(*args, **kwargs):
        raise CaptureError("private https://cdn.example.org?token=secret")

    async def decode(*args, **kwargs):
        pytest.fail("Decoder must not start when resolution fails")
        yield b""

    monkeypatch.setattr(youtube_capture, "resolve_live_audio", resolve)
    monkeypatch.setattr(youtube_capture, "pcm_chunks", decode)

    async def collect():
        async with aclosing(youtube_capture.youtube_pcm_chunks(source())) as stream:
            return [block async for block in stream]

    with pytest.raises(youtube_capture.YouTubeResolutionError) as caught:
        asyncio.run(collect())
    assert str(caught.value) == "YouTube media resolution failed"


def test_decoder_failure_is_not_reported_as_youtube_resolution_failure(monkeypatch):
    async def resolve(*args, **kwargs):
        return youtube_capture.ResolvedLiveAudio(
            url="https://cdn.example.org/audio", format_id="test", headers={})

    async def decode(*args, **kwargs):
        raise CaptureError("upstream_http_403")
        yield b""

    monkeypatch.setattr(youtube_capture, "resolve_live_audio", resolve)
    monkeypatch.setattr(youtube_capture, "pcm_chunks", decode)

    async def collect():
        async with aclosing(youtube_capture.youtube_pcm_chunks(source())) as stream:
            return [block async for block in stream]

    with pytest.raises(CaptureError, match="upstream_http_403") as caught:
        asyncio.run(collect())
    assert not isinstance(caught.value, youtube_capture.YouTubeResolutionError)


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
if "onlyvideo" in link:
    formats=[{"format_id":"silent", "vcodec":"h264", "acodec":"none",
              "url":"https://cdn.example.org/silent.m3u8"}]
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
    assert resolved.is_recording is False
    assert resolved.url=="https://cdn.example.org/audio-high.m3u8"
    assert resolved.headers=={"User-Agent":"GameNow-Test"}
    assert "Cookie" not in resolved.headers


@pytest.mark.parametrize("name,error", [
    ("restricted", "unavailable or restricted"),
    ("onlyvideo", "containing audio"),
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


def fake_metadata_resolver(tmp_path, metadata):
    """Local fake yt-dlp process with a controlled metadata response."""
    binary = tmp_path / "metadata-yt-dlp"
    data = json.dumps(metadata)
    binary.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.stdout.write(" +
        repr(data) + ")\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return str(binary)


@pytest.mark.parametrize("formats,needle", [
    ({}, "valid formats list"),
    ([{"url": "https://cdn.example.org/media", "vcodec": "none",
       "acodec": "aac", "has_drm": True}], "containing audio"),
    ([{"url": "https://cdn.example.org/video", "vcodec": "h264",
       "acodec": "none"}], "containing audio"),
])
def test_fail_closed_on_invalid_or_drm_only_formats(tmp_path, formats, needle):
    binary = fake_metadata_resolver(
        tmp_path, {"live_status": "is_live", "formats": formats},
    )
    with pytest.raises(CaptureError, match=needle):
        asyncio.run(youtube_capture.resolve_live_audio(
            source(), yt_dlp_binary=binary,
        ))


def test_nonnumeric_bitrate_keeps_usable_audio(tmp_path):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": True, "formats": [
            {"format_id": "audio", "vcodec": "none", "acodec": "opus",
             "url": "https://cdn.example.org/audio", "abr": "unknown"},
        ],
    })
    result = asyncio.run(youtube_capture.resolve_live_audio(
        source(), yt_dlp_binary=binary,
    ))
    assert result.format_id == "audio"


def test_live_diagnostic_emits_only_json_safe_statistics(monkeypatch):
    async def fake_pcm(item, **kwargs):
        yield b"\x01\x00" * 8000
        yield b"\x02\x00" * 8000
    monkeypatch.setattr(youtube_capture, "youtube_pcm_chunks", fake_pcm)
    result = asyncio.run(youtube_capture.youtube_diagnostic(source(), duration=.6))
    assert result["bytes"] == 19_200
    assert result["chunks"] == 2
    assert result["seconds"] == pytest.approx(.6)
    assert result["audio_retransmitted"] is False
    assert all(field not in result for field in ("url", "pcm", "audio", "headers"))
    with pytest.raises(CaptureError, match="duration"):
        asyncio.run(youtube_capture.youtube_diagnostic(source(), duration=601))


def test_live_diagnostic_rejects_no_audio(monkeypatch):
    async def fake_pcm(item, **kwargs):
        if False:
            yield b"\x00\x00"
    monkeypatch.setattr(youtube_capture, "youtube_pcm_chunks", fake_pcm)
    with pytest.raises(CaptureError, match="no PCM"):
        asyncio.run(youtube_capture.youtube_diagnostic(source(), duration=.5))


def test_muxed_live_fallback_is_audio_output_only(tmp_path, monkeypatch):
    """YouTube may offer video+audio HLS but no separate audio rendition."""
    executable = fake_metadata_resolver(tmp_path, {
        "live_status": "is_live",
        "formats": [
            {"format_id": "hd", "vcodec": "h264", "acodec": "aac",
             "tbr": 2200, "url": "https://cdn.example.org/hd.m3u8"},
            {"format_id": "low", "vcodec": "h264", "acodec": "aac",
             "tbr": 300, "url": "https://cdn.example.org/low.m3u8",
             "http_headers": {"User-Agent": "Test", "Cookie": "secret"}},
        ],
    })
    resolved = asyncio.run(youtube_capture.resolve_live_audio(
        source(), yt_dlp_binary=executable,
    ))
    assert resolved.format_id == "low"
    assert resolved.url.endswith("/low.m3u8")
    assert resolved.input_has_video is True
    assert resolved.headers == {"User-Agent": "Test"}

    captured = []
    async def fake_pcm(item, **kwargs):
        captured.append((item, kwargs))
        yield b"\x11\x00" * 1600
    monkeypatch.setattr(youtube_capture, "pcm_chunks", fake_pcm)
    async def consume():
        async with aclosing(youtube_capture.youtube_pcm_chunks(
            source(), yt_dlp_binary=executable,
        )) as pcm:
            return [block async for block in pcm]
    assert asyncio.run(consume()) == [b"\x11\x00" * 1600]
    assert captured[0][0].url.endswith("/low.m3u8")
    assert captured[0][1]["http_headers"] == {"User-Agent": "Test"}


def test_audio_only_still_preferred_over_muxed(tmp_path):
    executable = fake_metadata_resolver(tmp_path, {
        "is_live": True,
        "formats": [
            {"format_id": "combined", "vcodec": "h264", "acodec": "aac",
             "tbr": 80, "url": "https://cdn.example.org/combined.m3u8"},
            {"format_id": "audio", "vcodec": "none", "acodec": "aac",
             "abr": 64, "url": "https://cdn.example.org/audio.m3u8"},
        ],
    })
    resolved = asyncio.run(youtube_capture.resolve_live_audio(
        source(), yt_dlp_binary=executable,
    ))
    assert resolved.format_id == "audio"
    assert resolved.input_has_video is False


def test_hls_audio_only_with_missing_codec_is_accepted(tmp_path):
    """Real yt-dlp -F labels YouTube Live 233/234 as audio only, codec unknown."""
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": True,
        "formats": [
            {"format_id": "233", "vcodec": "none", "acodec": None,
             "protocol": "m3u8_native",
             "url": "https://cdn.example.org/audio-233.m3u8"},
            {"format_id": "234", "vcodec": "none",
             "protocol": "m3u8_native",
             "url": "https://cdn.example.org/audio-234.m3u8",
             "http_headers": {"User-Agent": "UnitTest", "Cookie": "discard"}},
            {"format_id": "269", "vcodec": "avc1.42C00B",
             "protocol": "m3u8_native",
             "url": "https://cdn.example.org/silent-video.m3u8"},
        ],
    })
    resolved = asyncio.run(youtube_capture.resolve_live_audio(
        source(), yt_dlp_binary=binary,
    ))
    assert resolved.format_id == "234"
    assert resolved.input_has_video is False
    assert resolved.url.endswith("audio-234.m3u8")
    assert resolved.headers == {"User-Agent": "UnitTest"}


@pytest.mark.parametrize("format_info", [
    {"vcodec": "avc1.42C00B", "acodec": None, "protocol": "m3u8_native"},
    {"vcodec": "none", "acodec": "none", "protocol": "m3u8_native"},
    {"vcodec": "none", "acodec": None, "protocol": "https"},
    {"vcodec": "none", "acodec": None, "protocol": "m3u8_native",
     "has_drm": True},
])
def test_unknown_codec_not_accepted_without_audio_only_hls_evidence(
    tmp_path, format_info,
):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": True,
        "formats": [{**format_info, "format_id": "blocked",
                     "url": "https://cdn.example.org/blocked.m3u8"}],
    })
    with pytest.raises(CaptureError, match="containing audio"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source(), yt_dlp_binary=binary,
        ))



def test_recorded_video_is_accepted_even_when_not_live(tmp_path):
    """Regression: previously all VODs failed solely because is_live=False."""
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": False, "live_status": "not_live", "duration": 5400,
        "formats": [{
            "format_id": "m4a", "vcodec": "none", "acodec": "mp4a.40.2",
            "protocol": "https", "url": "https://cdn.example.org/game.m4a",
        }],
    })
    result = asyncio.run(youtube_capture.resolve_live_audio(
        source("recorded"), yt_dlp_binary=binary,
    ))
    assert result.format_id == "m4a"
    assert result.is_recording is True
    assert result.url.endswith("/game.m4a")
    assert result.input_has_video is False


def test_recorded_livestream_is_accepted(tmp_path):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": False, "live_status": "was_live",
        "formats": [{
            "format_id": "archive", "vcodec": "none", "acodec": "opus",
            "url": "https://cdn.example.org/archive.webm",
        }],
    })
    result = asyncio.run(youtube_capture.resolve_live_audio(
        source("archived"), yt_dlp_binary=binary,
    ))
    assert result.format_id == "archive"
    assert result.is_recording is True


@pytest.mark.parametrize("status", ["is_upcoming", "post_live", "unavailable", "unknown"])
def test_unavailable_and_unknown_statuses_fail_closed(tmp_path, status):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": False, "live_status": status,
        "formats": [{
            "format_id": "audio", "vcodec": "none", "acodec": "aac",
            "url": "https://cdn.example.org/audio.m4a",
        }],
    })
    with pytest.raises(CaptureError, match="not yet available|not a confirmed"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source("unready"), yt_dlp_binary=binary,
        ))


@pytest.mark.parametrize("availability", [
    "private", "premium_only", "subscriber_only", "needs_auth",
])
def test_restricted_recordings_fail_closed_even_with_an_audio_format(tmp_path, availability):
    binary = fake_metadata_resolver(tmp_path, {
        "live_status": "not_live", "availability": availability,
        "formats": [{
            "format_id": "audio", "vcodec": "none", "acodec": "aac",
            "url": "https://cdn.example.org/audio.m4a",
        }],
    })
    with pytest.raises(CaptureError, match="restricted"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source("restricted-recording"), yt_dlp_binary=binary,
        ))


def test_recording_with_global_drm_flag_fails_closed(tmp_path):
    binary = fake_metadata_resolver(tmp_path, {
        "live_status": "was_live", "has_drm": True,
        "formats": [{
            "format_id": "audio", "vcodec": "none", "acodec": "aac",
            "url": "https://cdn.example.org/audio.m4a",
        }],
    })
    with pytest.raises(CaptureError, match="restricted"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source("drm-recording"), yt_dlp_binary=binary,
        ))


def test_recorded_media_pcm_flow_has_same_privacy_guarantees(tmp_path, monkeypatch):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": False, "live_status": "not_live",
        "formats": [{
            "format_id": "audio", "vcodec": "none", "acodec": "opus",
            "url": "https://cdn.example.org/game.webm",
        }],
    })
    requests = []
    async def fake_pcm(item, **kwargs):
        requests.append((item, kwargs))
        yield b"\x00\x00" * 8000
    monkeypatch.setattr(youtube_capture, "pcm_chunks", fake_pcm)
    async def collect():
        async with aclosing(youtube_capture.youtube_pcm_chunks(
            source("recording"), yt_dlp_binary=binary,
        )) as stream:
            return [block async for block in stream]
    assert asyncio.run(collect()) == [b"\x00\x00" * 8000]
    assert requests[0][0].kind == "radio"
    assert requests[0][0].url.endswith("game.webm")
    assert "Cookie" not in requests[0][1].get("http_headers", {})


def test_diagnostic_accepts_five_to_ten_minutes_without_saving_media(monkeypatch):
    async def fake_pcm(item, **kwargs):
        for _ in range(600):
            yield b"\x01\x00" * 8000  # 0.5 s, no real audio or network
    monkeypatch.setattr(youtube_capture, "youtube_pcm_chunks", fake_pcm)
    stats = asyncio.run(youtube_capture.youtube_diagnostic(
        source("recorded"), duration=300,
    ))
    assert stats["seconds"] == 300
    assert stats["bytes"] == 9_600_000
    assert stats["chunks"] == 600
    assert stats["audio_retransmitted"] is False
    assert set(stats).isdisjoint({"pcm", "url", "media", "headers", "audio"})


def test_older_metadata_without_live_status_can_identify_finite_vod(tmp_path):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": False, "duration": 3600,
        "formats": [{
            "format_id": "recording", "vcodec": "none", "acodec": "mp4a.40.2",
            "url": "https://cdn.example.org/rec.m4a",
        }],
    })
    result = asyncio.run(youtube_capture.resolve_live_audio(
        source("older-metadata"), yt_dlp_binary=binary,
    ))
    assert result.format_id == "recording"


@pytest.mark.parametrize("duration", [None, 0, -1, float("inf"), float("nan")])
def test_missing_status_needs_known_recording_duration(tmp_path, duration):
    binary = fake_metadata_resolver(tmp_path, {
        "is_live": False, "duration": duration,
        "formats": [{
            "format_id": "recording", "vcodec": "none", "acodec": "opus",
            "url": "https://cdn.example.org/rec.webm",
        }],
    })
    with pytest.raises(CaptureError, match="not a confirmed"):
        asyncio.run(youtube_capture.resolve_live_audio(
            source("unknown-duration"), yt_dlp_binary=binary,
        ))
