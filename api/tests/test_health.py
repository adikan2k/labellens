from fastapi.testclient import TestClient

from api.app.main import app

client = TestClient(app)


def test_health_returns_ok_with_versions_and_source() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["versions"]["api"]
    assert body["versions"]["python"].startswith("3.12")
    assert body["source"]["name"] == "Open Food Facts"
    assert body["source"]["licence"] == "ODbL-1.0"
    assert "snapshot_date" in body["source"]
