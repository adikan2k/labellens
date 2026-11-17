from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app


def test_health_returns_ok_with_versions_and_source() -> None:
    # No database: health must answer even when Postgres is unreachable or unset.
    app = create_app(Settings(_env_file=None, database_url=None))  # pyright: ignore[reportCallIssue]
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["versions"]["api"]
    assert body["versions"]["python"].startswith("3.12")
    assert body["source"]["name"] == "Open Food Facts"
    assert body["source"]["licence"] == "ODbL-1.0"
    assert body["source"]["snapshot_date"] is None
