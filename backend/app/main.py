"""The FastAPI app.

    uv run uvicorn app.main:app --reload     # from backend/

On start it builds the DuckDB file from the GeoJSON exports if it is missing,
opens it read-only and reads the metric catalog.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.catalog import build_context
from agent.router import router as agent_router
from app.config import settings
from app.database import close_database, open_database
from app.ingest import ensure_database

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    path = ensure_database()
    db = open_database(path)
    app.state.agent_context = build_context(db)
    logger.info(
        "Index loaded from %s: %d hexagons, %d metrics. Agent %s.",
        path,
        app.state.agent_context.hex_count,
        len(app.state.agent_context.metrics),
        f"on ({settings.AI_PROVIDER}: {settings.agent_model})"
        if settings.agent_configured
        else f"off ({settings.agent_setup_hint})",
    )
    yield
    close_database()


app = FastAPI(
    title=settings.APP_NAME,
    description="Ask questions about the Olomouc green infrastructure index.",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX or None,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(agent_router, prefix="/api/agent", tags=["agent"])


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
