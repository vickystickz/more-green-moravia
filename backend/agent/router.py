"""HTTP API of the agent: ask a question (streamed or not) and draw a step on the map."""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from agent import maps, service
from agent.catalog import AgentContext
from agent.llm import LLMClient, get_llm
from agent.query import LayerSpec, ToolError
from agent.schemas import (
    CHAT_EXAMPLES,
    SSE_EXAMPLE,
    SUGGESTIONS,
    AgentStatus,
    ChatRequest,
    MetricOut,
    Suggestion,
)
from app.config import settings
from app.database import Database, get_db

router = APIRouter()

HEARTBEAT_SECONDS = 15.0
ERROR_STATUS = {"busy": 503, "model_unavailable": 503, "internal": 500}


def get_context(request: Request) -> AgentContext:
    return request.app.state.agent_context


def require_agent() -> None:
    if not settings.agent_configured:
        raise HTTPException(503, "The AI agent is not enabled: set AI_BASE_URL and AI_MODEL")


@router.get("/status", response_model=AgentStatus)
async def agent_status(ctx: AgentContext = Depends(get_context)):
    """Whether the agent is enabled, and which model answers. Use it to show or hide "Ask AI"."""
    return AgentStatus(
        enabled=settings.agent_configured,
        model=settings.AI_MODEL if settings.agent_configured else None,
        hexagons=ctx.hex_count,
        microzones=len(ctx.microzones),
    )


@router.get("/suggestions", response_model=list[Suggestion])
async def agent_suggestions():
    """Starter questions for an empty chat."""
    return SUGGESTIONS


@router.get("/metrics", response_model=list[MetricOut])
async def agent_metrics(ctx: AgentContext = Depends(get_context)):
    """Every metric the agent (and /map) can use, with its label and unit."""
    return [
        MetricOut(
            name=m.name, label=m.label, description=m.description, group=m.group, unit=m.shown_unit
        )
        for m in ctx.metrics.values()
    ]


@router.post(
    "/chat",
    responses={
        200: {
            "description": "Server-sent events (`stream: true`), or the whole answer as JSON",
            "content": {"text/event-stream": {"example": SSE_EXAMPLE}},
        },
        503: {"description": "The agent is not enabled, busy, or the model is unavailable"},
    },
)
async def chat(
    payload: ChatRequest = Body(openapi_examples=CHAT_EXAMPLES),
    _: None = Depends(require_agent),
    ctx: AgentContext = Depends(get_context),
    db: Database = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
):
    """
    Ask a question about the Olomouc GI index. The agent answers by running
    read-only queries on the index; every number in the answer comes from one.

    **Body:** `message`, optional `history` (earlier turns, for follow-ups;
    nothing is stored on the server) and `stream`.

    **`stream: true` (default):** `text/event-stream`, one event per stage:

    | event | data |
    |---|---|
    | `step` | a query the agent ran: `{tool, label, arguments, ok, error, result, layer, ms}`; `result` holds `{columns, rows, summary, truncated}`; `layer` is the body for `POST /map` |
    | `answer` | `{text, model}`: markdown |
    | `done` | `{elapsed_ms, usage}`, last |
    | `error` | `{code, message}`, last, instead of `answer` / `done` |

    While the model is thinking a `: ping` comment arrives every 15 s.

    **`stream: false`:** the same in one response: `{answer, steps, elapsed_ms, usage}`.
    """
    history = [turn.model_dump() for turn in payload.history]
    events = service.ask(llm, ctx, db, history, payload.message)
    if payload.stream:
        return StreamingResponse(
            _sse(events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await _collect(events)


@router.post("/map", response_model=maps.MapLayer)
async def map_layer(
    spec: LayerSpec,
    ctx: AgentContext = Depends(get_context),
    db: Database = Depends(get_db),
):
    """
    A GeoJSON layer for one step of an answer ("Show on map"): send the step's
    `layer` as the body. Works without the model, so it can also colour the map
    by any metric directly.

    Feature properties: `id` (h3_index or microzone name), `name` (microzone),
    `value` (scores 0-100, shares in %), `rank` (when `ids` were given) and
    `hexagons` (microzones). `legend.breaks` are the upper bounds of the first
    four of five classes: 20/40/60/80 for scores, quantiles otherwise.
    """
    try:
        return await maps.build(db, ctx, spec)
    except ToolError as exc:
        raise HTTPException(400, str(exc)) from exc


async def _collect(events: AsyncGenerator[service.Event, None]) -> JSONResponse:
    """All events as one JSON response; an error event becomes an error status."""
    result: dict[str, Any] = {"steps": []}
    async with contextlib.aclosing(events):
        async for event, data in events:
            if event == "step":
                result["steps"].append(data)
            elif event == "answer":
                result.update(answer=data["text"], model=data["model"])
            elif event == "done":
                result.update(data)
            elif event == "error":
                return JSONResponse(
                    {"error": data, **result}, status_code=ERROR_STATUS[data["code"]]
                )
    return JSONResponse(result)


async def _sse(events: AsyncGenerator[service.Event, None]) -> AsyncIterator[str]:
    """
    Frame events as server-sent events. While the next event is pending, send a
    comment line every HEARTBEAT_SECONDS so proxies don't drop the connection.
    On disconnect the pending work is cancelled and the agent's generator closed.
    """
    pending: asyncio.Future[service.Event] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(anext(events))
            done, _ = await asyncio.wait({pending}, timeout=HEARTBEAT_SECONDS)
            if not done:
                yield ": ping\n\n"
                continue
            finished, pending = pending, None
            try:
                event, data = finished.result()
            except StopAsyncIteration:
                return
            payload = json.dumps(data, default=str, ensure_ascii=False, separators=(",", ":"))
            yield f"event: {event}\ndata: {payload}\n\n"
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending
        await events.aclose()
