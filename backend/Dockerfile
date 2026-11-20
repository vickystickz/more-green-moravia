# =============================================================
# Backend (FastAPI + DuckDB) for Render, or any Docker host.
#
# Build from backend/ (everything it needs is in this folder,
# including the GeoJSON exports in data/):
#
#   cd backend
#   docker build -t moravia-api .
#   docker run --rm -p 8000:8000 --env-file .env moravia-api
#
# Render sets $PORT; locally it falls back to 8000.
# =============================================================

FROM python:3.12-slim-bookworm AS build

# Same uv as used locally (uv.lock needs a recent uv).
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . ./

# Build the DuckDB file now, so the server starts fast and the
# container needs no write access at run time.
RUN .venv/bin/python -m app.ingest --force


FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000

RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Code, venv and the built database.
COPY --from=build --chown=app:app /app /app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

# --proxy-headers: Render terminates HTTPS in front of the app.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
