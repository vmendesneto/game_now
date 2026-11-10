"""GN-032: configurable independent source metadata, persistence and URL hygiene."""
from fastapi.testclient import TestClient

from app.main import create_app
from test_match_flow import match_config


BASE = "/api/matches/match-024"


def radio(source_id="radio-001", enabled=True, url="https://radio.example.com/live/stream.m3u8"):
    return {"id": source_id, "name": "Rádio Local", "kind": "radio", "url": url,
            "enabled": enabled, "status": "offline"}


def youtube():
    return {"id": "youtube-001", "name": "Transmissão pública", "kind": "youtube",
            "url": "https://www.youtube.com/live/AbCdEf12345", "enabled": True,
            "status": "offline"}


def test_sources_crud_toggle_reopen_and_no_embedded_media(tmp_path):
    db = tmp_path / "sources.sqlite3"
    with TestClient(create_app(db)) as client:
        client.post("/api/matches", json=match_config())
        two = [radio(), youtube()]
        assert client.put(BASE + "/sources", json=two).status_code == 200
        assert client.get(BASE + "/sources").json() == two
        assert client.get(BASE + "/state").json()["sources"] == two
        updated = [radio(enabled=False, url="https://radio.example.com/live.mp3"), youtube()]
        updated[1]["name"] = "YouTube alternativo"
        assert client.put(BASE + "/sources", json=updated).status_code == 200
        assert client.get(BASE + "/sources").json()[0]["enabled"] is False
        assert client.get("/health").json()["sources"] == "synthetic_only"
        page = client.get("/").text
        assert 'id="source-form"' in page
        assert "<audio" not in page and "<video" not in page
        assert client.put(BASE + "/sources", json=[updated[0]]).status_code == 200
    with TestClient(create_app(db)) as client:
        assert client.get(BASE + "/sources").json() == [updated[0]]
        assert client.get(BASE + "/state").json()["sources"] == [updated[0]]


def test_bad_radio_and_youtube_urls_are_rejected_atomically(tmp_path):
    with TestClient(create_app(tmp_path / "urls.sqlite3")) as client:
        client.post("/api/matches", json=match_config())
        valid = [radio(url=None)]
        assert client.put(BASE + "/sources", json=valid).status_code == 200
        bad_urls = [
            "file:///etc/passwd", "rtmp://radio.example.com/live",
            "http://127.0.0.1/stream", "http://192.168.0.20/live",
            "https://localhost/live", "http://server.local/live",
            "http://user:pass@radio.example.com/live",
            "http://radio.example.com/live#fragment",
            "https://radio.example.com/live ",
            "",
        ]
        for url in bad_urls:
            assert client.put(BASE + "/sources", json=[radio(url=url)]).status_code == 409, url
            assert client.get(BASE + "/sources").json() == valid
        assert client.put(BASE + "/sources",
                          json=[{**youtube(), "url": "http://youtube.com/watch?v=abc"}]).status_code == 409
        assert client.put(BASE + "/sources",
                          json=[{**youtube(), "url": "https://youtube.com"}]).status_code == 409
        assert client.put(BASE + "/sources",
                          json=[{**youtube(), "url": "https://notyoutube.com/live/abc"}]).status_code == 409
        assert client.put(BASE + "/sources",
                          json=[{**youtube(), "url": "https://youtu.be/AbCdEf12345"}]).status_code == 200
        snapshot = client.get(BASE + "/state").json()
        snapshot["sources"] = [radio(url="http://10.1.2.3/live")]
        assert client.put(BASE + "/state", json=snapshot).status_code == 409
        assert client.get(BASE + "/sources").json()[0]["kind"] == "youtube"
