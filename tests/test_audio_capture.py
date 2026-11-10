"""GN-030: decode reproducible MP3/AAC/HLS fixtures without radio network access."""
import asyncio
from contextlib import aclosing
import math
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import wave

import pytest

from app.audio_capture import (CaptureError, SAMPLE_RATE, check_public_destination,
                               diagnostic, pcm_chunks)
from app.contracts import AudioSource


def radio(url=None):
    return AudioSource(id="radio-test", name="Radio", kind="radio",
                       url=url, enabled=True, status="offline")


def make_audio_fixture(tmp_path: Path, codec: str) -> Path:
    wav = tmp_path / "input.wav"
    with wave.open(str(wav), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        frames = bytearray()
        for i in range(8000):
            sample = int(math.sin(2 * math.pi * 440 * i / 8000) * 10_000)
            frames.extend(struct.pack("<hh", sample, sample))
        writer.writeframes(bytes(frames))
    if codec == "mp3":
        output = tmp_path / "fixture.mp3"
        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
                   "-c:a", "libmp3lame", str(output)]
    elif codec == "aac":
        output = tmp_path / "fixture.aac"
        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
                   "-c:a", "aac", "-f", "adts", str(output)]
    elif codec == "hls":
        output = tmp_path / "fixture.m3u8"
        command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
                   "-c:a", "aac", "-f", "hls", "-hls_time", "0.5", "-hls_list_size", "0",
                   str(output)]
    else:
        raise ValueError(codec)
    subprocess.run(command, check=True, capture_output=True)
    assert output.exists()
    return output


@pytest.mark.parametrize("codec", ["mp3", "aac", "hls"])
def test_ffmpeg_decodes_radio_formats_to_pcm_s16le_16khz(tmp_path, codec):
    assert shutil.which("ffmpeg"), "FFmpeg must be present in CI"
    media = make_audio_fixture(tmp_path, codec)

    async def read_all():
        blocks = []
        async with aclosing(pcm_chunks(radio(), fixture_file=media, chunk_ms=200)) as stream:
            async for block in stream:
                blocks.append(block)
        return blocks

    blocks = asyncio.run(read_all())
    assert len(blocks) >= 4
    assert all(len(chunk) <= 6400 and len(chunk) % 2 == 0 for chunk in blocks)
    total = sum(len(chunk) for chunk in blocks)
    # AAC/HLS carry codec priming/padding samples; PCM format remains exact.
    assert 30_000 <= total <= 40_000, (codec, total)
    assert any(value != 0 for block in blocks for value in block)
    summary = asyncio.run(diagnostic(radio(), fixture_file=media, duration=0.4))
    assert summary["sample_rate"] == SAMPLE_RATE
    assert summary["channels"] == 1
    assert summary["format"] == "s16le"
    assert summary["bytes"] == 12_800
    assert summary["audio_retransmitted"] is False


def test_disabled_nonradio_missing_ffmpeg_and_bad_chunk_bounds(tmp_path):
    fixture = make_audio_fixture(tmp_path, "mp3")

    async def collect(source, **kwargs):
        async with aclosing(pcm_chunks(source, fixture_file=kwargs.pop("fixture_file", fixture), **kwargs)) as stream:
            return [block async for block in stream]

    with pytest.raises(CaptureError, match="Only enabled radio"):
        asyncio.run(collect(radio().model_copy(update={"enabled": False})))
    with pytest.raises(CaptureError, match="Only enabled radio"):
        asyncio.run(collect(radio().model_copy(update={"kind": "youtube"})))
    with pytest.raises(CaptureError, match="chunk_ms"):
        asyncio.run(collect(radio(), chunk_ms=99))
    with pytest.raises(CaptureError, match="not found"):
        asyncio.run(collect(radio(), ffmpeg_binary="missing-ffmpeg-game-now"))
    with pytest.raises(CaptureError, match="safe public-stream"):
        asyncio.run(collect(radio(), http_headers={"Authorization": "secret"}))
    with pytest.raises(CaptureError, match="safe public-stream"):
        asyncio.run(collect(radio(), http_headers={"Referer": "ok\r\nCookie: secret"}))
    with pytest.raises(CaptureError, match="no URL"):
        asyncio.run(collect(radio(), fixture_file=None))
    with pytest.raises(CaptureError, match="duration"):
        asyncio.run(diagnostic(radio(), fixture_file=fixture, duration=0))


def test_dns_public_check_rejects_private_resolution(monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()
        async def private_addrinfo(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.2.3.4", 443))]
        monkeypatch.setattr(loop, "getaddrinfo", private_addrinfo)
        with pytest.raises(CaptureError, match="non-public IP"):
            await check_public_destination("https://radio.example.org/live")
    asyncio.run(scenario())
