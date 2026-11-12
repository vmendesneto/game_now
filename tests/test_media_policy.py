"""GN-037: source/media privacy guardrails (offline, deterministic checks)."""
import asyncio
from pathlib import Path
import re

import pytest

from app.contracts import AudioSource
from app.source_validation import validate_source_urls
from app.storage import StoreConflict
from app.youtube_capture import resolve_live_audio

pytestmark = pytest.mark.usefixtures("python_script_launchers")


def youtube(url):
    return AudioSource(id="youtube-check", name="Test", kind="youtube",
                       url=url, enabled=True, status="offline")


@pytest.mark.parametrize("url", [
    "http://www.youtube.com/watch?v=abc",
    "https://www.youtube.com@evil.example/live/abc",
    "https://127.0.0.1/watch?v=abc",
    "https://youtube.com/live/abc#fragment",
    "https://youtube.com:443@private.example/live/abc",
])
def test_youtube_rejects_insecure_or_ambiguous_endpoints(url):
    with pytest.raises(StoreConflict):
        validate_source_urls([youtube(url)])


def test_frontend_does_not_embed_media_players():
    root = Path(__file__).resolve().parents[1] / "app" / "static"
    html = (root / "index.html").read_text(encoding="utf-8")
    js = (root / "app.js").read_text(encoding="utf-8")
    assert re.search(r"<(audio|video|iframe)\b", html, re.IGNORECASE) is None
    assert re.search(r"new\s+Audio\s*\(|getUserMedia\s*\(|new\s+MediaSource\s*\(", js) is None


def test_ytdlp_is_invoked_without_cache_download_or_credentials(tmp_path):
    executable = tmp_path / "mock-yt-dlp"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "assert '--ignore-config' in args\n"
        "assert '--no-cache-dir' in args\n"
        "assert '--skip-download' in args\n"
        "assert '--dump-single-json' in args\n"
        "assert '--no-playlist' in args\n"
        "assert '--' in args\n"
        "assert not any('cookie' in arg for arg in args)\n"
        "print(json.dumps({'is_live': True, 'formats': "
        "[{'format_id': 'audio', 'acodec':'aac', 'vcodec':'none',"
        "'url':'https://cdn.example.org/audio.m3u8'}]}))\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    before = sorted(p.name for p in tmp_path.iterdir())
    result = asyncio.run(resolve_live_audio(
        youtube("https://www.youtube.com/live/test"),
        yt_dlp_binary=str(executable),
    ))
    assert result.format_id == "audio"
    assert sorted(p.name for p in tmp_path.iterdir()) == before
