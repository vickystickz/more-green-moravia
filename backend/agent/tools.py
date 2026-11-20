"""The agent's tools: typed, read-only questions it can ask the GI index.

Each tool validates its arguments, runs on the read-only DuckDB file and
returns two views of the result: a compact one for the model, and the full
data for the user ("how I got this"), plus a map layer the app can draw.
Problems the model can fix come back to it as an error message.

To add a tool (an administrative-area lookup, a geocoder for place names in
Olomouc ...), write an async `run(db, ctx, spec)` returning a QueryResult and
add a Tool to TOOLS.
"""

import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import cache
from typing import Any

import duckdb
from pydantic import BaseModel, ValidationError

from agent.catalog import AgentContext
from agent.llm import ToolCall
from agent.query import (
    DescribeSpec,
    DetailSpec,
    OverviewSpec,
    QueryResult,
    RankSpec,
    SummarizeSpec,
    ToolError,
    describe,
    detail,
    overview,
    rank,
    summarize,
)
from app.database import Database

logger = logging.getLogger(__name__)

MODEL_ROWS = 30  # rows the model sees
MODEL_CHARS = 5000  # rough cap on one tool result sent to the model


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[BaseModel]
    run: Callable[[Database, AgentContext, Any], Awaitable[QueryResult]]
    label: Callable[[Any], str]


@dataclass
class ToolResult:
    ok: bool
    label: str  # what was done, for people: "Ranked microzones by Lack of green"
    for_model: str  # compact JSON sent back to the model
    data: dict[str, Any] | None = None  # columns, rows, summary, truncated
    layer: dict[str, Any] | None = None  # body for POST /api/agent/map
    error: str | None = None
    ms: int = 0


def _rank_label(spec: RankSpec) -> str:
    what = "hexagons" if spec.level.value == "hex" else "microzones"
    label = f"Ranked {what} by {spec.metric}" + (
        " (lowest first)" if spec.order.value == "asc" else ""
    )
    return label + (" (filtered)" if spec.filters else "")


SCORING_HELP = (
    " 'score' uses the Balance weights unless you pass a preset (cool-street, "
    "protect-vulnerable, pocket-parks, quick-wins), custom weights {he, v, gd} or only_buildable."
)

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        Tool(
            name="index_overview",
            description=(
                "The big picture for Olomouc: number of hexagons and microzones, residents, "
                "the green infrastructure need score's mean / median / max, how many hexagons "
                "fall in each score band, and the 5 microzones with the highest mean score. "
                "Good first call for general questions." + SCORING_HELP
            ),
            args=OverviewSpec,
            run=overview,
            label=lambda spec: "Looked at the city overview",
        ),
        Tool(
            name="rank_areas",
            description=(
                "The top (or bottom) hexagons or microzones by any metric, with filters. Use it "
                "for 'where', 'which', 'top', 'worst', 'best' questions, e.g. the hottest "
                "microzones, hexagons with the most need where people live (filter "
                "raw_residents gt 0), or places with space to build. show adds more metrics "
                "per row." + SCORING_HELP
            ),
            args=RankSpec,
            run=rank,
            label=_rank_label,
        ),
        Tool(
            name="summarize_areas",
            description=(
                "Count the hexagons that match the filters and total or average metrics over "
                "them: how many, how many residents, what share of the city, mean values. "
                "by_microzone gives one row per microzone. Use it for 'how many', 'how much', "
                "'what share' questions, e.g. hexagons with sealing over 60% and tree cover "
                "under 10%." + SCORING_HELP
            ),
            args=SummarizeSpec,
            run=summarize,
            label=lambda spec: (
                "Summarized matching hexagons" + (" by microzone" if spec.by_microzone else "")
            ),
        ),
        Tool(
            name="describe_metric",
            description=(
                "One metric across the city (or the filtered hexagons): min, quartiles, max, "
                "mean, missing values, the score bands, and how it is computed. Use it to "
                "explain a metric or say what counts as high or low."
            ),
            args=DescribeSpec,
            run=describe,
            label=lambda spec: f"Described {spec.metric}",
        ),
        Tool(
            name="area_detail",
            description=(
                "Everything about one place: a hexagon (h3_index), a microzone (by name, "
                "accents optional) or the hexagon at a point (lon, lat). Gives the score, its "
                "three factors, space to build and the key indicators, each with its rank in "
                "the city. Use it for 'why is X high', 'tell me about X'."
            ),
            args=DetailSpec,
            run=detail,
            label=lambda spec: (
                "Looked up " + (spec.microzone or spec.h3_index or "the place at the point")
            ),
        ),
    )
}


@cache
def tool_schemas() -> list[dict[str, Any]]:
    """The tools in the chat-completions format, with flat parameter schemas."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": flat_schema(tool.args),
            },
        }
        for tool in TOOLS.values()
    ]


async def run_tool(call: ToolCall, ctx: AgentContext, db: Database) -> ToolResult:
    """Validate and run one tool call; never raises for problems the model can fix."""
    started = time.monotonic()
    tool = TOOLS.get(call.name)
    if tool is None:
        return _failed(call.name, f"unknown tool {call.name!r}; use one of {', '.join(TOOLS)}")
    if call.arguments is None:
        return _failed(call.name, "the arguments were not a JSON object")
    try:
        spec = tool.args.model_validate(call.arguments)
    except ValidationError as exc:
        return _failed(call.name, "invalid arguments: " + _validation_message(exc))

    try:
        label = tool.label(spec)
        result = await tool.run(db, ctx, spec)
    except ToolError as exc:
        return _failed(call.name, str(exc), started)
    except duckdb.Error:
        logger.warning("Agent tool %s failed", call.name, exc_info=True)
        return _failed(call.name, "the query failed; try other arguments", started)

    return ToolResult(
        ok=True,
        label=label,
        for_model=_for_model(result),
        data={
            "columns": result.columns,
            "rows": result.rows,
            "summary": result.summary,
            "truncated": result.truncated,
        },
        layer=result.layer.model_dump(mode="json", exclude_none=True) if result.layer else None,
        ms=_ms(started),
    )


def flat_schema(model: type[BaseModel]) -> dict[str, Any]:
    """
    The model's JSON schema with `$ref`s inlined, `Optional[X]` reduced to X, and
    titles and null defaults dropped. Many providers and small models reject or
    stumble on `$ref` / `anyOf`.
    """
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            rest = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**definitions[node["$ref"].rsplit("/", 1)[-1]], **rest})
        options = [o for o in node.get("anyOf", []) if o.get("type") != "null"]
        if "anyOf" in node and len(options) == 1:
            rest = {k: v for k, v in node.items() if k != "anyOf"}
            return walk({**options[0], **rest})
        flat: dict[str, Any] = {}
        for key, value in node.items():
            if key == "title" or (key == "default" and value is None):
                continue
            if key == "properties":
                flat[key] = {name: walk(prop) for name, prop in value.items()}
            else:
                flat[key] = walk(value)
        return flat

    flat = walk(schema)
    flat.setdefault("properties", {})
    return flat


def _for_model(result: QueryResult) -> str:
    payload: dict[str, Any] = {}
    if result.summary:
        payload["summary"] = result.summary
    rows = result.rows[:MODEL_ROWS]
    more = result.truncated or len(rows) < len(result.rows)
    while True:
        if result.rows:
            payload["rows"] = rows
        if more:
            payload["more_rows_not_shown"] = True
        text = _dump(payload)
        if len(text) <= MODEL_CHARS or not rows:
            return text
        rows, more = rows[: len(rows) // 2], True


def _failed(label: str, message: str, started: float | None = None) -> ToolResult:
    return ToolResult(
        ok=False,
        label=label,
        for_model=_dump({"error": message}),
        error=message,
        ms=_ms(started) if started else 0,
    )


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'arguments'}: {error['msg']}"
        for error in exc.errors()[:5]
    )


def _dump(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False, separators=(",", ":"))


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
