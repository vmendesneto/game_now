"""GN-090: deterministic SSRF, HLS-relay and FFmpeg integration tests."""
from __future__ import annotations

import io
import socket
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen

import pytest

from app import secure_ingest as secure


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "https://localhost/a", "http://127.0.0.1/a",
    "http://169.254.169.254/latest/meta-data/", "http://[::1]/a",
    "http://user:pass@radio.example.com/live", "https://radio.example.com\\@127.0.0.1/",
    "https://radio.example.com/%0a\nHello", "https://radio.example.com/#fragment",
    "https://radio.example.com:0/a", "https://radio.example.com:99999/a",
    "http://radio.example.com\r\nHost:internal/", "http://radio.example.com/a b",
])
def test_invalid_source_rejected(url):
    with pytest.raises(secure.IngestSecurityError):
        secure._parse_public_url(url)


def test_dns_rebinding_and_mixed_public_private_fail_before_connect(monkeypatch):
    def lookup(host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
    monkeypatch.setattr(secure.socket, "getaddrinfo", lookup)
    with pytest.raises(secure.IngestSecurityError, match="Non-public DNS"):
        secure._connect_pinned("http://radio.example.com/live", {})


def test_public_dns_result_is_used_for_pinned_connection(monkeypatch):
    calls = []
    monkeypatch.setattr(secure.socket, "getaddrinfo", lambda host, port, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", port))])
    monkeypatch.setattr(secure.socket, "create_connection", lambda dest, timeout, source_address=None: calls.append(dest))
    class FakeConnection:
        def __init__(self, host, port, timeout):
            self.host, self.port = host, port
        def request(self, method, path, headers):
            assert self.host == "radio.example.com"
            assert method == "GET"
            self._create_connection((self.host, self.port), 10)
        def getresponse(self):
            return object()
        def close(self):
            pass
    monkeypatch.setattr(secure.http.client, "HTTPConnection", FakeConnection)
    secure._connect_pinned("http://radio.example.com/live", {})
    assert calls == [("1.1.1.1", 80)]


def test_redirect_target_rechecked_and_rejected(monkeypatch):
    visited = []
    class FakeResponse:
        status = 302
        def getheader(self, name):
            return "http://169.254.169.254/latest/meta-data/" if name == "Location" else None
    class FakeConnection:
        def close(self):
            pass
    def fake_connect(url, headers):
        visited.append(url)
        return FakeConnection(), FakeResponse()
    monkeypatch.setattr(secure, "_connect_pinned", fake_connect)
    with pytest.raises(secure.IngestSecurityError):
        secure._open_redirects("https://radio.example.com/live", {})
    assert visited == ["https://radio.example.com/live"]


class FakeResponse:
    status = 200
    def __init__(self, data, content_type):
        self.data = io.BytesIO(data)
        self.content_type = content_type
    def getheader(self, name):
        return self.content_type if name == "Content-Type" else None
    def read(self, n=-1):
        return self.data.read(n)


class FakeConnection:
    def close(self):
        pass


def test_hls_nested_playlists_segments_and_uri_attributes_use_loopback(monkeypatch):
    master = b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=64000\nsub/live.m3u8\n'
    variant = (b'#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n'
               b'#EXT-X-KEY:METHOD=AES-128,URI="https://media.example.org/key"\n'
               b'#EXTINF:4,\n../seg.ts?sig=xyz\n')
    contents = {
        "https://radio.example.org/live.m3u8": (master, "application/octet-stream"),
        "https://radio.example.org/sub/live.m3u8": (variant, "application/x-mpegURL"),
        "https://radio.example.org/sub/init.mp4": (b"initdata", "application/octet-stream"),
        "https://radio.example.org/seg.ts?sig=xyz": (b"segmentdata", "application/octet-stream"),
        "https://media.example.org/key": (b"keydata", "application/octet-stream"),
    }
    requested = []
    def fake_open(url, headers):
        requested.append(url)
        data, content_type = contents[url]
        return FakeConnection(), FakeResponse(data, content_type), url
    monkeypatch.setattr(secure, "_open_redirects", fake_open)
    with secure.SafeMediaRelay("https://radio.example.org/live.m3u8") as relay:
        assert relay.input_url.startswith("http://127.0.0.1:")
        top = urlopen(relay.input_url).read().decode()
        sub_url = top.splitlines()[-1]
        assert sub_url.startswith("http://127.0.0.1:")
        child = urlopen(sub_url).read().decode()
        assert "https://media.example.org" not in child
        assert '#EXT-X-MAP:URI="http://127.0.0.1:' in child
        part_url = child.splitlines()[-1]
        assert urlopen(part_url).read() == b"segmentdata"
    assert "https://radio.example.org/seg.ts?sig=xyz" in requested


def test_hls_with_unrewritten_url_reference_is_rejected():
    with pytest.raises(secure.IngestSecurityError, match="Unrewritten"):
        secure._rewrite_playlist(
            b"#EXTM3U\n#EXT-X-UNKNOWN:URL=https://169.254.169.254/a\n",
            "https://radio.example.org/list.m3u8", "http://127.0.0.1:1234/secret",
        )


def test_hls_variables_and_oversized_playlist_are_rejected():
    for data in [b"#EXTM3U\n#EXT-X-DEFINE:NAME=a,VALUE=b\n", b"#EXTM3U\n{$host}\n",
                 b"#EXTM3U\n" + b"a" * (secure.MAX_PLAYLIST_BYTES + 1)]:
        with pytest.raises(secure.IngestSecurityError):
            secure._rewrite_playlist(data, "https://radio.example.org/a.m3u8", "http://127.0.0.1")


def test_relay_secret_required_even_on_localhost(monkeypatch):
    monkeypatch.setattr(secure, "_open_redirects", lambda *args: (FakeConnection(), FakeResponse(b"hello", "audio/mpeg"), args[0]))
    with secure.SafeMediaRelay("https://radio.example.org/stream") as relay:
        with pytest.raises(HTTPError) as err:
            urlopen(relay.input_url.replace(relay._token, "invalid"))
        assert err.value.code == 404
        assert urlopen(relay.input_url).read() == b"hello"


def test_relay_rejects_headers_and_range_injection():
    with pytest.raises(secure.IngestSecurityError):
        secure.SafeMediaRelay("https://radio.example.org/live", http_headers={"Cookie": "secret"})
    with pytest.raises(secure.IngestSecurityError):
        secure.SafeMediaRelay("https://radio.example.org/live", http_headers={"User-Agent": "foo\r\nCookie: bar"})


def test_ffmpeg_can_decode_hls_through_relay_without_direct_network(tmp_path, monkeypatch):
    import subprocess
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg
    manifest = tmp_path / "live.m3u8"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=500:duration=1",
        "-c:a", "aac", "-f", "hls", "-hls_time", "0.25", "-hls_list_size", "0",
        str(manifest),
    ], check=True, capture_output=True)
    def fake_open(url, headers):
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        suffix = tmp_path / name
        return FakeConnection(), FakeResponse(suffix.read_bytes(),
            "application/vnd.apple.mpegurl" if suffix.suffix == ".m3u8"
            else "video/mp2t"), url
    monkeypatch.setattr(secure, "_open_redirects", fake_open)
    with secure.SafeMediaRelay("https://radio.example.org/live.m3u8") as relay:
        proc = subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-protocol_whitelist", "http,tcp,crypto", "-i", relay.input_url,
            "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "pipe:1",
        ], capture_output=True, timeout=15)
    assert proc.returncode == 0, proc.stderr.decode()[-1500:]
    assert len(proc.stdout) >= 25000
