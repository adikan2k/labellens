import pytest
from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.db import Database
from api.app.main import Lazy, create_app


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


def test_warm_builds_the_lazy_services_once() -> None:
    built: list[str] = []
    app = create_app(Settings(_env_file=None, database_url=None))  # pyright: ignore[reportCallIssue]
    with TestClient(app) as client:
        app.state.ask = Lazy("Ask service", lambda: built.append("ask") or object())
        app.state.label = Lazy("Label reader", lambda: built.append("label"))
        first = client.get("/warm")
        second = client.get("/warm")

    assert first.status_code == 200
    # The fake label reader builds to None: not configured, and still built only once.
    body = first.json()
    assert (body["ask_configured"], body["label_configured"]) == (True, False)
    assert body["source"]["licence"] == "ODbL-1.0"
    assert second.json() == body
    assert built == ["ask", "label"]


def test_warm_never_asks_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    # The keep-warm ping runs every 5 minutes; a query each time would keep Neon from pausing.
    def no_database(*_: object, **__: object) -> None:
        raise AssertionError("/warm reached the database")

    monkeypatch.setattr(Database, "snapshot_date", no_database)
    monkeypatch.setattr(Database, "connection", no_database)
    app = create_app(Settings(_env_file=None, database_url=None))  # pyright: ignore[reportCallIssue]
    with TestClient(app) as client:
        response = client.get("/warm")

    assert response.status_code == 200
    body = response.json()
    assert (body["ask_configured"], body["label_configured"]) == (False, False)
    assert body["source"]["snapshot_date"] is None
