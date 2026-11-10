from fastapi.testclient import TestClient

from app.main import create_app


def test_health_and_schema_and_no_media_endpoints():
    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        data = health.json()
        assert data["status"] == "ok"
        assert data["sources"] == "synthetic_only"
        assert data["storage"] == "volatile_memory_only"
        assert data["windows_hardware_tested"] is False
        assert client.get("/api/schema").json()["title"] == "ContractBundle"
        assert client.get("/").status_code == 200
        assert "/static/app.js" in client.get("/").text


def test_two_websocket_clients_see_identical_demo_updates():
    with TestClient(create_app()) as client:
        with client.websocket_connect("/ws") as left:
            with client.websocket_connect("/ws") as right:
                assert left.receive_json()["step"] == 0
                assert right.receive_json()["step"] == 0
                response = client.post("/api/demo/next")
                assert response.status_code == 200
                one = left.receive_json()
                two = right.receive_json()
                assert one == two == response.json()
                assert one["step"] == 1
                reset = client.post("/api/demo/reset").json()
                assert left.receive_json() == reset
                assert right.receive_json() == reset
                assert reset["data"]["events"] == []
