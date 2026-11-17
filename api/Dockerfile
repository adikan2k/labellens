# LabelLens API for Cloud Run. Build from the repo root:
#   docker build -f api/Dockerfile -t labellens-api .
# Installs only the main dependency group (no dbt, Dagster, DuckDB or dev tools).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-default-groups --no-install-project

COPY api ./api

RUN useradd --system --uid 10001 app
USER app

# Cloud Run sets PORT. One worker: Cloud Run scales by instances, and the pool is per process.
CMD ["sh", "-c", "exec uvicorn api.app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
