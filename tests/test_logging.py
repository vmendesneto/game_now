"""GN-015: JSON request tracing, rotation and safe failure reporting."""
import json

from fastapi.testclient import TestClient

from app.logging_setup import request_logger
from app.main import create_app
from test_match_flow import match_config


def test_api_json_logs_no_credentials_and_request_ids(tmp_path, monkeypatch):
    logfile = tmp_path / "logs" / "game_now.jsonl"
    monkeypatch.setenv("GAME_NOW_LOG_PATH", str(logfile))
    with TestClient(create_app(tmp_path / "state.sqlite3")) as client:
        healthy = client.get("/health")
        assert healthy.status_code == 200
        assert len(healthy.headers["x-request-id"]) == 32
        created = client.post("/api/matches", json=match_config())
        assert created.status_code == 201
        bad = client.put("/api/matches/match-024/sources", json=[{
            "id": "source-001", "name": "Radio", "kind": "radio",
            "url": "https://user:secret-password@radio.example.com/live",
            "enabled": True, "status": "offline",
        }])
        assert bad.status_code == 409
        assert isinstance(bad.json()["detail"], str)
        missing = client.get("/api/matches/unknown")
        assert missing.status_code == 404
    content = logfile.read_text(encoding="utf-8")
    assert "secret-password" not in content
    assert "radio.example.com" not in content
    entries = [json.loads(row) for row in content.splitlines()]
    assert [item["status"] for item in entries] == [200, 201, 409, 404]
    assert all(item["event"] == "http_request" for item in entries)
    assert all(item["level"] == "INFO" for item in entries)
    assert all(item["duration_ms"] >= 0 for item in entries)
    assert all(len(item["request_id"]) == 32 for item in entries)
    assert all("timestamp" in item for item in entries)


def test_rotating_log_limits_disk_footprint(tmp_path):
    logfile = tmp_path / "rotating.log"
    logger = request_logger(logfile, max_bytes=250, backup_count=2)
    for i in range(40):
        logger.info("http_request", extra={"safe_details": {
            "request_id": f"request-{i}", "method": "GET",
            "route": "/health", "status": 200, "duration_ms": 1,
        }})
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    outputs = sorted(tmp_path.glob("rotating.log*"))
    assert len(outputs) == 3
    assert all(file.stat().st_size <= 250 for file in outputs)
    for file in outputs:
        for row in file.read_text(encoding="utf-8").splitlines():
            assert json.loads(row)["event"] == "http_request"
