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

from fastapi import Depends, FastAPI, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import SecretStr
from starlette.exceptions import HTTPException

from api.app import graph as graph_module
from api.app import products
from api.app import search as search_module
from api.app import swaps as swaps_module
from api.app.ask import service as ask_module
from api.app.config import Settings, get_settings
from api.app.db import UNAVAILABLE, Database, DatabaseNotConfigured, DictConnection
from api.app.mcp.server import create_mcp
from api.app.schemas import (
    AskRequest,
    Error,
    GraphNeighborhood,
    Health,
    ProductResponse,
    SearchResponse,
    Source,
    StatsOverview,
    SwapsResponse,
    Versions,
)

API_VERSION = "0.3.0"
WAKING_UP = "Search is waking up. Try again in a few seconds."
GRAPH_UNAVAILABLE = "The graph is waking up or being reloaded. Try again in a minute."
ASK_NOT_CONFIGURED = "The ask agent is not configured."


def get_connection(request: Request) -> Iterator[DictConnection]:
    yield from request.app.state.db.connection()


Conn = Annotated[DictConnection, Depends(get_connection)]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        url = settings.database_url.get_secret_value() if settings.database_url else None
        app.state.db = Database.open(url, timeout=settings.db_pool_timeout)
        if not hasattr(app.state, "graph"):  # tests may set one
            password = (
                settings.neo4j_password.get_secret_value() if settings.neo4j_password else None
            )
            app.state.graph = graph_module.Graph.open(
                settings.neo4j_uri, settings.neo4j_user, password
            )
        app.state.ask = _open_ask(app, settings)
        try:
            # A mounted route's own lifespan never runs, so the MCP session manager runs here.
            async with app.state.mcp.server.session_manager.run():
                yield
        finally:
            app.state.db.close()
            app.state.graph.close()
            if app.state.ask is not None:
                app.state.ask.readonly.close()

    app = FastAPI(title="LabelLens API", version=API_VERSION, lifespan=lifespan)
    # The MCP server reads app.state.db per call; the pool opens in the lifespan.
    app.state.mcp = create_mcp(lambda: app.state.db, settings.public_web_url)
    # Exactly /mcp: no slash redirect, and other paths keep the API's own JSON errors.
    app.router.routes.append(app.state.mcp.route)
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

    @app.exception_handler(graph_module.GraphUnavailable)
    async def graph_unavailable(request: Request, exc: Exception) -> JSONResponse:
        return error(request, 503, GRAPH_UNAVAILABLE)

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

    @app.get(
        "/products/{code}",
        responses={404: {"model": Error}, 422: {"model": Error}, 503: {"model": Error}},
    )
    def product(
        request: Request,
        response: Response,
        conn: Conn,
        code: Annotated[str, Path(min_length=1, max_length=32)],
    ) -> ProductResponse:
        found = products.get_product(conn, code)
        if found is None:
            raise HTTPException(404, f"No product with barcode {code} in this snapshot.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return ProductResponse(product=found, source=source(request))  # type: ignore[arg-type]

    @app.get(
        "/products/{code}/swaps",
        responses={404: {"model": Error}, 422: {"model": Error}, 503: {"model": Error}},
    )
    def product_swaps(
        request: Request,
        response: Response,
        conn: Conn,
        code: Annotated[str, Path(min_length=1, max_length=32)],
        limit: Annotated[int, Query(ge=1, le=20)] = 5,
    ) -> SwapsResponse:
        found = swaps_module.find_swaps(conn, code, limit)
        if found is None:
            raise HTTPException(404, f"No product with barcode {code} in this snapshot.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return SwapsResponse(code=code, swaps=found, source=source(request))  # type: ignore[arg-type]

    @app.get(
        "/graph/neighborhood",
        responses={404: {"model": Error}, 422: {"model": Error}, 503: {"model": Error}},
    )
    def neighborhood(
        request: Request,
        response: Response,
        code: Annotated[str, Query(min_length=1, max_length=32)],
        depth: Annotated[int, Query(ge=1, le=2)] = 1,
    ) -> GraphNeighborhood:
        found = request.app.state.graph.neighborhood(code, depth)
        if found is None:
            raise HTTPException(404, f"The graph does not hold a product with barcode {code}.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return GraphNeighborhood(**found, source=source(request))

    @app.post(
        "/ask", responses={422: {"model": Error}, 429: {"model": Error}, 503: {"model": Error}}
    )
    def ask(request: Request, body: AskRequest) -> Response:
        service: ask_module.AskService | None = request.app.state.ask
        if service is None:
            raise HTTPException(503, ASK_NOT_CONFIGURED)
        peer = request.client.host if request.client else None
        address = ask_module.client_address(request.headers.get("x-forwarded-for"), peer)
        who = ask_module.client_hash(service.hash_key, address)
        wait = service.retry_after(who)
        if wait is not None:
            minutes = max(1, round(wait / 60))
            limited = error(
                request,
                429,
                f"That's {service.limits.per_hour} questions this hour from here. "
                f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}.",
            )
            limited.headers["Retry-After"] = str(wait)
            return limited
        return StreamingResponse(
            service.stream(body.question.strip(), who),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/stats/overview", responses={503: {"model": Error}})
    def stats(request: Request, response: Response, conn: Conn) -> StatsOverview:
        doc = products.get_stats(conn)
        if doc is None:
            raise HTTPException(503, "Dashboard figures are not loaded yet.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return StatsOverview(**doc, source=source(request))

    return app


def _open_ask(app: FastAPI, settings: Settings) -> ask_module.AskService | None:
    """The ask service, or None without a model key, database or read-only database."""
    import hashlib

    import anthropic

    from api.app.ask.agent import Agent
    from api.app.ask.tracing import Tracer
    from api.app.embeddings import Voyage

    def secret(value: SecretStr | None) -> str | None:
        return value.get_secret_value() if value else None

    readonly_url = secret(settings.database_url_readonly)
    database_url = secret(settings.database_url)
    client = getattr(app.state, "ask_client", None)
    if client is None and settings.anthropic_api_key:
        client = anthropic.Anthropic(api_key=secret(settings.anthropic_api_key), max_retries=1)
    if client is None or not readonly_url or not database_url:
        return None
    voyage = getattr(app.state, "voyage", None) or Voyage(
        secret(settings.embeddings_api_key), settings.embeddings_model
    )
    tracer = getattr(app.state, "tracer", None) or Tracer.from_keys(
        settings.langfuse_public_key,
        secret(settings.langfuse_secret_key),
        settings.langfuse_base_url,
    )
    db = app.state.db
    return ask_module.AskService(
        db=db,
        readonly=Database.open(readonly_url, timeout=settings.db_pool_timeout),
        graph=app.state.graph,
        voyage=voyage,
        agent=Agent(client, settings.model_default, settings.embeddings_model, tracer),
        limits=ask_module.AskLimits(
            settings.ask_rate_limit_per_hour,
            settings.ask_daily_spend_cap_usd,
            settings.ask_timeout_seconds,
        ),
        # A keyed hash of the client address; the key never leaves the server.
        hash_key=hashlib.sha256(b"labellens-ask-client|" + database_url.encode()).digest(),
        replays=getattr(app.state, "ask_replays", None) or ask_module.load_replays(),
        snapshot=lambda: Source(snapshot_date=db.snapshot_date()).model_dump(mode="json"),
    )


app = create_app()
