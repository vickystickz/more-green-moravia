"""Answering one question from start to finish.

Nothing is stored: a follow-up question carries its earlier turns in the
request (`history`), so the server stays stateless.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from dataclasses import asdict
from typing import Any

from agent import loop
from agent.catalog import AgentContext
from agent.llm import LLMClient, LLMError
from app.config import settings
from app.database import Database

logger = logging.getLogger(__name__)

HISTORY_TURNS = 6  # earlier question/answer pairs the model sees
BUSY_WAIT_SECONDS = 10.0  # how long a question waits for a free slot

Event = tuple[str, dict[str, Any]]


class AgentBusy(Exception):
    """All AGENT_MAX_CONCURRENT slots stayed taken for BUSY_WAIT_SECONDS."""


class _Slots:
    """At most AGENT_MAX_CONCURRENT questions are answered at once in this process.
    The semaphore is made per event loop: tests run several loops in one process."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore = asyncio.Semaphore(1)

    @asynccontextmanager
    async def take(self) -> AsyncIterator[None]:
        running = asyncio.get_running_loop()
        if self._loop is not running:
            self._loop, self._semaphore = running, asyncio.Semaphore(settings.AGENT_MAX_CONCURRENT)
        semaphore = self._semaphore
        try:
            await asyncio.wait_for(semaphore.acquire(), BUSY_WAIT_SECONDS)
        except TimeoutError:
            raise AgentBusy from None
        try:
            yield
        finally:
            semaphore.release()


slots = _Slots()


async def ask(
    llm: LLMClient,
    ctx: AgentContext,
    db: Database,
    history: list[dict[str, Any]],
    question: str,
) -> AsyncGenerator[Event, None]:
    """Answer one question, yielding (event, data): a step per tool call, then
    answer and done. Failures end with an error event instead."""
    started = time.monotonic()
    try:
        run = loop.run(llm, ctx, db, clean_history(history), question, settings.AGENT_MAX_STEPS)
        async with slots.take(), aclosing(run) as events:
            async for event in events:
                if isinstance(event, loop.Step):
                    yield "step", step_out(event)
                    continue
                elapsed = int((time.monotonic() - started) * 1000)
                yield "answer", {"text": event.text, "model": llm.model}
                yield "done", {"elapsed_ms": elapsed, "usage": asdict(event.usage)}
    except AgentBusy:
        yield "error", _error("busy", "The agent is busy. Try again in a moment.")
    except LLMError as exc:
        logger.warning("Agent model call failed: %s", exc)
        yield (
            "error",
            _error(
                "model_unavailable", "The AI model is not available right now. Try again later."
            ),
        )
    except Exception:
        logger.exception("Agent failed to answer")
        yield "error", _error("internal", "Something went wrong while answering.")


def clean_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The last turns the client sent, as plain user/assistant text. Answers are
    sanitized again: the client could send anything."""
    turns = [
        {
            "role": turn["role"],
            "content": loop.sanitize(turn["content"])
            if turn["role"] == "assistant"
            else turn["content"],
        }
        for turn in history
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str)
    ]
    return turns[-HISTORY_TURNS * 2 :]


def step_out(step: loop.Step) -> dict[str, Any]:
    """A tool step as the client sees it."""
    return {
        "tool": step.tool,
        "label": step.result.label,
        "arguments": step.arguments,
        "ok": step.result.ok,
        "error": step.result.error,
        "result": step.result.data,
        "layer": step.result.layer,
        "ms": step.result.ms,
    }


def _error(code: str, message: str) -> dict[str, Any]:
    return {"code": code, "message": message}
