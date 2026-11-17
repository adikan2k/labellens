"""LabelLens API. Contract: docs/openapi.yaml.

    uv run fastapi dev api/app/main.py

Endpoints are plain (sync) functions on a psycopg connection pool; FastAPI runs them in a
thread pool. psycopg's async mode needs a selector event loop, which Windows does not use by
default, so sync keeps local development working everywhere.
"""

import platform
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api.app import search as search_module
from api.app.config import Settings, get_settings
from api.app.db import UNAVAILABLE, Database, DatabaseNotConfigured, DictConnection
from api.app.schemas import Error, Health, SearchResponse, Source, Versions

API_VERSION = "0.2.0"
WAKING_UP = "Search is waking up. Try again in a few seconds."


def get_connection(request: Request) -> Iterator[DictConnection]:
    yield from request.app.state.db.connection()


Conn = Annotated[DictConnection, Depends(get_connection)]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = settings.database_url.get_secret_value() if settings.database_url else None
        app.state.db = Database.open(url, timeout=settings.db_pool_timeout)
        try:
            yield
        finally:
            app.state.db.close()

    app = FastAPI(title="LabelLens API", version=API_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def source(request: Request) -> Source:
        return Source(snapshot_date=request.app.state.db.snapshot_date())

    def error(request: Request, status: int, detail: str) -> JSONResponse:
        body = Error(detail=detail, source=source(request))
        return JSONResponse(body.model_dump(mode="json"), status_code=status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error(request, exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:]) or 'request'}: {e['msg']}"
            for e in exc.errors()
        )
        return error(request, 422, f"Invalid request. {problems}")

    async def unavailable(request: Request, exc: Exception) -> JSONResponse:
        return error(request, 503, WAKING_UP)

    for exc_class in UNAVAILABLE:  # Neon waking from idle, or unreachable
        app.add_exception_handler(exc_class, unavailable)

    @app.exception_handler(DatabaseNotConfigured)
    async def not_configured(request: Request, exc: DatabaseNotConfigured) -> JSONResponse:
        return error(request, 503, "The database is not configured.")

    @app.get("/health")
    def health(request: Request) -> Health:
        return Health(
            status="ok",
            versions=Versions(api=API_VERSION, python=platform.python_version()),
            source=source(request),
        )

    @app.get("/search", responses={422: {"model": Error}, 503: {"model": Error}})
    def search(
        request: Request,
        response: Response,
        conn: Conn,
        q: Annotated[str, Query(min_length=1, max_length=200)],
        limit: Annotated[int, Query(ge=1, le=50)] = 10,
    ) -> SearchResponse:
        results = search_module.search(conn, q, limit)
        response.headers["Cache-Control"] = "public, max-age=60"
        return SearchResponse(query=q, results=results, source=source(request))  # type: ignore[arg-type]

    return app


app = create_app()
