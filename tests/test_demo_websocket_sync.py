"""GN-073: real HTTP/WebSocket demo delivery to two independent clients."""
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def _assert_safe_demo(snapshot: dict) -> None:
    assert set(snapshot) == {
        "mode", "stream_id", "revision", "step", "total_steps", "data"
    }
    assert snapshot["mode"] == "synthetic_demo"
    assert snapshot["stream_id"]
    assert isinstance(snapshot["revision"], int)
    assert set(snapshot["data"]) == {"schema_version", "match", "sources", "segments", "events", "ball"}
    # No base64 content, PCM/audio samples, media playback or binary frames.
    forbidden = {"audio_base64", "pcm_bytes", "raw_audio", "video_frame",
                 "video_base64", "media_payload", "stream_bytes"}
    def walk(value):
        if isinstance(value, dict):
            assert not (forbidden & set(value))
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(snapshot)


def test_two_clients_receive_identical_ordered_updates_and_reset(tmp_path):
    with TestClient(create_app(tmp_path / "gn073.sqlite3")) as client:
        initial = client.get("/api/state").json()
        _assert_safe_demo(initial)
        with client.websocket_connect("/ws") as browser_a:
            with client.websocket_connect("/ws") as browser_b:
                assert browser_a.receive_json() == initial
                assert browser_b.receive_json() == initial
                stream_id = initial["stream_id"]
                revision = initial["revision"]
                for step in range(1, 5):
                    reply = client.post("/api/demo/next")
                    assert reply.status_code == 200
                    snapshot = reply.json()
                    _assert_safe_demo(snapshot)
                    assert snapshot["stream_id"] == stream_id
                    assert snapshot["revision"] == revision + step
                    assert browser_a.receive_json() == snapshot
                    assert browser_b.receive_json() == snapshot
                    assert client.get("/api/state").json() == snapshot
                reset = client.post("/api/demo/reset").json()
                assert reset["step"] == 0
                assert reset["revision"] == revision + 5
                assert browser_a.receive_json() == reset
                assert browser_b.receive_json() == reset
                assert reset["data"]["events"] == []


def test_restarting_app_changes_stream_epoch(tmp_path):
    with TestClient(create_app(tmp_path / "stream.sqlite3")) as first:
        previous = first.get("/api/state").json()
        first.post("/api/demo/next")
    with TestClient(create_app(tmp_path / "stream.sqlite3")) as second:
        restarted = second.get("/api/state").json()
    assert previous["stream_id"] != restarted["stream_id"]
    assert restarted["revision"] == 0
    assert restarted["step"] == 0


def test_browser_script_order_and_two_client_node_simulation():
    static = ROOT / "app" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    app_js = (static / "app.js").read_text(encoding="utf-8")
    assert html.index("demo_sync.js") < html.index("app.js")
    assert "GameNowSync.createSync(" in app_js
    assert "const snapshot=await response.json();" in app_js
    assert "demoSync.accept(snapshot)" in app_js
    assert "demoSync.start()" in app_js
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed; CI runs browser-sync simulations")
    check = subprocess.run(
        [node, "--check", str(static / "demo_sync.js")],
        capture_output=True, text=True, timeout=15,
    )
    assert check.returncode == 0, check.stderr
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests" / "test_demo_sync.cjs")],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "# fail 0" in result.stdout
