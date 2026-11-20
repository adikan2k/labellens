"""LabelLens API. Contract: docs/openapi.yaml.

    uv run fastapi dev api/app/main.py

Endpoints are plain (sync) functions on a psycopg connection pool; FastAPI runs them in a
thread pool. psycopg's async mode needs a selector event loop, which Windows does not use by
default, so sync keeps local development working everywhere.
"""

import hashlib
import logging
import platform
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import SecretStr
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUpload
from starlette.exceptions import HTTPException

from api.app import additive_guide as guide_module
from api.app import graph as graph_module
from api.app import products
from api.app import search as search_module
from api.app import swaps as swaps_module
from api.app.ask import service as ask_module
from api.app.config import Settings, get_settings
from api.app.db import UNAVAILABLE, Database, DatabaseNotConfigured, DictConnection
from api.app.label import images as label_images
from api.app.mcp.server import create_mcp
from api.app.schemas import (
    AdditiveGuide,
    AdditiveList,
    AskRequest,
    Error,
    GraphNeighborhood,
    Health,
    LabelResponse,
    ProductResponse,
    Ready,
    SearchResponse,
    Source,
    StatsOverview,
    SwapsResponse,
    Versions,
    Warm,
)

API_VERSION = "0.3.0"
WAKING_UP = "Search is waking up. Try again in a few seconds."
GRAPH_UNAVAILABLE = "The graph is waking up or being reloaded. Try again in a minute."
ASK_NOT_CONFIGURED = "The ask agent is not configured."
LABEL_NOT_CONFIGURED = "The label reader is not configured."
# Uvicorn's own logger, so these lines reach Cloud Run's log without logging setup of our own.
log = logging.getLogger("uvicorn.error")


class Lazy:
    """A service built on first use rather than at startup: the ask agent and the label reader.

    Their libraries (anthropic, langfuse with OpenTelemetry) take seconds to import, and on a
    fresh Cloud Run instance far longer: an hour-idle cold start spent 16 s in startup
    (evals/results/cold_start.md). A search never needs them, so only the first question or
    label after a quiet spell pays (or GET /warm and GET /ready, which build both on
    purpose)."""

    def __init__(
        self,
        name: str,
        build: Callable[[], Any],
        close: Callable[[Any], None] = lambda service: None,
    ) -> None:
        self._name = name
        self._build = build
        self._close = close
        self._lock = threading.Lock()
        self._built = False
        self._service: Any = None

    def get(self) -> Any:
        if not self._built:
            with self._lock:
                if not self._built:
                    started = time.perf_counter()
                    self._service = self._build()
                    self._built = True
                    log.info("%s ready in %.2f s", self._name, time.perf_counter() - started)
        return self._service

    def close(self) -> None:
        if self._service is not None:
            self._close(self._service)


def get_connection(request: Request) -> Iterator[DictConnection]:
    yield from request.app.state.db.connection()


Conn = Annotated[DictConnection, Depends(get_connection)]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        started = time.perf_counter()
        url = settings.database_url.get_secret_value() if settings.database_url else None
        app.state.db = Database.open(url, timeout=settings.db_pool_timeout)
        if not hasattr(app.state, "graph"):  # tests may set one
            password = (
                settings.neo4j_password.get_secret_value() if settings.neo4j_password else None
            )
            app.state.graph = graph_module.Graph.open(
                settings.neo4j_uri, settings.neo4j_user, password
            )
        app.state.ask = Lazy(
            "Ask service", lambda: _open_ask(app, settings), lambda s: s.readonly.close()
        )
        app.state.label = Lazy("Label reader", lambda: _open_label(app, settings))
        try:
            # A mounted route's own lifespan never runs, so the MCP session manager runs here.
            async with app.state.mcp.server.session_manager.run():
                log.info("Startup took %.2f s", time.perf_counter() - started)
                yield
        finally:
            app.state.db.close()
            app.state.graph.close()
            app.state.ask.close()
            app.state.label.close()

    app = FastAPI(title="LabelLens API", version=API_VERSION, lifespan=lifespan)
    # The MCP server reads app.state.db per call; the pool opens in the lifespan.
    app.state.mcp = create_mcp(
        lambda: app.state.db,
        settings.public_web_url,
        per_minute=settings.mcp_rate_limit_per_minute,
    )
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
        service = request.app.state.ask.get()
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

    @app.post(
        "/label",
        response_model=LabelResponse,
        responses={
            413: {"model": Error},
            422: {"model": Error},
            429: {"model": Error},
            503: {"model": Error},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["images"],
                            "properties": {
                                "images": {
                                    "type": "array",
                                    "minItems": 1,
                                    "maxItems": label_images.MAX_IMAGES,
                                    "items": {"type": "string", "format": "binary"},
                                }
                            },
                        }
                    }
                },
            }
        },
    )
    async def label(request: Request) -> Any:
        service = await run_in_threadpool(request.app.state.label.get)
        if service is None:
            raise HTTPException(503, LABEL_NOT_CONFIGURED)
        length = int(request.headers.get("content-length") or 0)
        if length > label_images.MAX_IMAGES * label_images.MAX_BYTES + 64 * 1024:
            return error(request, 413, "The photos are too large. Each must be under 5 MB.")
        peer = request.client.host if request.client else None
        address = ask_module.client_address(request.headers.get("x-forwarded-for"), peer)
        who = ask_module.client_hash(service.hash_key, address)
        wait = await run_in_threadpool(service.retry_after, who)
        if wait is not None:
            minutes = max(1, round(wait / 60))
            limited = error(
                request,
                429,
                f"That's {service.limits.per_hour} labels this hour from here. "
                f"Try again in about {minutes} minute{'s' if minutes != 1 else ''}.",
            )
            limited.headers["Retry-After"] = str(wait)
            return limited
        try:
            form = await request.form(max_files=label_images.MAX_IMAGES + 1, max_fields=4)
            files = [f for f in form.getlist("images") if isinstance(f, StarletteUpload)]
            data = [await f.read(label_images.MAX_BYTES + 1) for f in files]
            images = label_images.check(data)
        except label_images.ImageError as problem:
            return error(request, 422, str(problem))
        except Exception:  # not multipart, or more files than allowed
            return error(request, 422, "Send one or two photos as the form field 'images'.")
        from api.app.label.service import LabelError, OverCap

        try:
            return await run_in_threadpool(service.read, images, who)
        except OverCap as over:
            return error(request, 503, str(over))
        except LabelError as failure:
            return error(request, failure.status, str(failure))

    @app.get("/warm")
    def warm(request: Request) -> Warm:
        """For the scheduled ping (scripts/keep_warm.py): builds the lazy services, so the
        first question or label on a new instance does not wait for their libraries. It runs
        no database query, so a ping never wakes Neon, and no model call."""
        return Warm(
            ask_configured=request.app.state.ask.get() is not None,
            label_configured=request.app.state.label.get() is not None,
            source=Source(snapshot_date=request.app.state.db.known_snapshot_date()),
        )

    @app.get("/ready", responses={503: {"model": Error}})
    def ready(request: Request, conn: Conn) -> Ready:
        """For a demo's warm-up: builds the lazy services and says what is left today."""
        ask_service = request.app.state.ask.get()
        label_service = request.app.state.label.get()
        database_url = _secret(settings.database_url) or ""
        peer = request.client.host if request.client else None
        address = ask_module.client_address(request.headers.get("x-forwarded-for"), peer)
        who = ask_module.client_hash(client_hash_key(database_url), address)

        def used(kind: str) -> int:
            row = conn.execute(ask_module.RATE_SQL, [who, kind]).fetchone()
            return int(row["n"]) if row else 0

        spent = conn.execute(ask_module.SPENT_SQL).fetchone()
        return Ready(
            ask_configured=ask_service is not None,
            label_configured=label_service is not None,
            questions_left=max(0, settings.ask_rate_limit_per_hour - used("ask")),
            label_reads_left=max(0, settings.label_rate_limit_per_hour - used("label")),
            spent_today_usd=round(float(spent["spent"]) if spent else 0.0, 4),
            daily_cap_usd=settings.ask_daily_spend_cap_usd,
            source=source(request),
        )

    @app.get("/additives", responses={503: {"model": Error}})
    def additives(request: Request, response: Response, conn: Conn) -> AdditiveList:
        """Every additive at least one named US product lists, most common first."""
        response.headers["Cache-Control"] = "public, max-age=3600"
        return AdditiveList(
            additives=guide_module.list_additives(conn),  # type: ignore[arg-type]
            source=source(request),
        )

    @app.get(
        "/additives/{slug}",
        responses={404: {"model": Error}, 422: {"model": Error}, 503: {"model": Error}},
    )
    def additive(
        request: Request,
        response: Response,
        conn: Conn,
        slug: Annotated[str, Path(min_length=1, max_length=120)],
    ) -> AdditiveGuide:
        """One additive: what it is, how common it is, where it is used, example products."""
        found = guide_module.get_guide(conn, slug)
        if found is None:
            raise HTTPException(404, f"No additive {slug} in this snapshot.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return AdditiveGuide(**found, source=source(request))

    @app.get("/stats/overview", responses={503: {"model": Error}})
    def stats(request: Request, response: Response, conn: Conn) -> StatsOverview:
        doc = products.get_stats(conn)
        if doc is None:
            raise HTTPException(503, "Dashboard figures are not loaded yet.")
        response.headers["Cache-Control"] = "public, max-age=3600"
        return StatsOverview(**doc, source=source(request))

    return app


def client_hash_key(database_url: str) -> bytes:
    """The key for the keyed hash of client addresses; it never leaves the server."""
    return hashlib.sha256(b"labellens-ask-client|" + database_url.encode()).digest()


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value else None


def _open_label(app: FastAPI, settings: Settings) -> Any:
    """The label reader, or None without a model key or database."""
    import anthropic

    from api.app.ask.tracing import Tracer
    from api.app.label.service import LabelLimits, LabelService

    database_url = _secret(settings.database_url)
    client = getattr(app.state, "label_client", None)
    if client is None and settings.anthropic_api_key:
        client = anthropic.Anthropic(api_key=_secret(settings.anthropic_api_key), max_retries=1)
    if client is None or not database_url:
        return None
    tracer = getattr(app.state, "tracer", None) or Tracer.from_keys(
        settings.langfuse_public_key,
        _secret(settings.langfuse_secret_key),
        settings.langfuse_base_url,
    )
    db = app.state.db
    return LabelService(
        db=db,
        client=client,
        model=settings.model_default,
        tracer=tracer,
        limits=LabelLimits(settings.label_rate_limit_per_hour, settings.ask_daily_spend_cap_usd),
        hash_key=client_hash_key(database_url),
        snapshot=lambda: Source(snapshot_date=db.snapshot_date()).model_dump(mode="json"),
    )


def _open_ask(app: FastAPI, settings: Settings) -> ask_module.AskService | None:
    """The ask service, or None without a model key, database or read-only database."""
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
        hash_key=client_hash_key(database_url),
        replays=getattr(app.state, "ask_replays", None) or ask_module.load_replays(),
        snapshot=lambda: Source(snapshot_date=db.snapshot_date()).model_dump(mode="json"),
    )


app = create_app()
