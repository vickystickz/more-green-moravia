# =============================================================
# Backend (FastAPI + DuckDB) for Render, or any Docker host.
#
# Build from the REPO ROOT, not backend/: the database is built
# from the GeoJSON exports in frontend/data/.
#
#   docker build -f backend/Dockerfile -t moravia-api .
#   docker run --rm -p 8000:8000 --env-file backend/.env moravia-api
#
# Render sets $PORT; locally it falls back to 8000.
# =============================================================

FROM python:3.12-slim-bookworm AS build

# Same uv as used locally (uv.lock needs a recent uv).
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app/backend

# Dependencies first, so code changes don't reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY frontend/data/olomouc_gi_h3_r9.geojson \
     frontend/data/olomouc_gi_h3_r9_metadata.json \
     frontend/data/olomouc_microzones.geojson \
     /app/frontend/data/

# Build the DuckDB file now, so the server starts fast and the
# container needs no write access at run time.
RUN .venv/bin/python -m app.ingest --force


FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    PORT=8000

RUN useradd --create-home --uid 1000 app
WORKDIR /app/backend

# Code, venv and the built database. The GeoJSON is not needed at
# run time: the server only rebuilds when the .duckdb file is missing.
COPY --from=build --chown=app:app /app/backend /app/backend

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=4)"

# --proxy-headers: Render terminates HTTPS in front of the app.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
