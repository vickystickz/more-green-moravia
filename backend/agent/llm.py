"""Chat-completions client for any OpenAI-compatible API.

One client covers hosted providers (OpenRouter, DeepInfra, Groq, Google AI
Studio's OpenAI endpoint) and self-hosted servers (vLLM, Ollama). Switching
between them only changes AI_BASE_URL, AI_API_KEY and AI_MODEL.
"""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.config import settings

TEMPERATURE = 0.1
MAX_OUTPUT_TOKENS = 1024
RETRIES = 2  # extra attempts after a 429, a 5xx or a network error
RETRY_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}
MAX_RETRY_WAIT = 10.0  # seconds; a longer Retry-After is capped

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


class LLMError(Exception):
    """The model API failed or answered with something unusable."""


@dataclass
class ToolCall:
    id: str
    name: str
    # None when the model sent arguments that are not a JSON object.
    arguments: dict[str, Any] | None

    @property
    def key(self) -> str:
        """Identifies a repeated call, so the same query is not run twice."""
        return f"{self.name}:{json.dumps(self.arguments, sort_keys=True, default=str)}"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.calls += other.calls


@dataclass
class LLMReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def as_message(self) -> dict[str, Any]:
        """The assistant message to append to the conversation."""
        message: dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    # Re-serialized: some providers reject history holding invalid JSON.
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments or {})},
                }
                for call in self.tool_calls
            ]
        return message


class LLMClient(Protocol):
    model: str

    async def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> LLMReply: ...


class OpenAICompatibleClient:
    """POST {base_url}/chat/completions, retrying rate limits and server errors."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,  # tests pass a MockTransport
    ):
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout
        self._transport = transport

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        if tools:  # some providers reject an empty list
            payload["tools"] = tools
        return parse_reply(await self._post(payload))

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for attempt in range(RETRIES + 1):
                last = attempt == RETRIES
                try:
                    response = await client.post(self._url, json=payload, headers=self._headers)
                except httpx.TransportError as exc:  # includes timeouts
                    if last:
                        raise LLMError(f"model API unreachable: {exc!r}") from exc
                    await asyncio.sleep(_backoff(attempt))
                    continue
                if response.status_code in RETRY_STATUSES and not last:
                    await asyncio.sleep(_retry_after(response) or _backoff(attempt))
                    continue
                if response.status_code >= 400:
                    raise LLMError(
                        f"model API returned {response.status_code}: {response.text[:300]}"
                    )
                try:
                    body = response.json()
                except ValueError as exc:
                    raise LLMError("model API returned a body that is not JSON") from exc
                if not isinstance(body, dict):
                    raise LLMError("model API returned an unexpected body")
                return body
        raise LLMError("model API retries exhausted")  # unreachable: the loop returns or raises


def parse_reply(body: dict[str, Any]) -> LLMReply:
    """Read the first choice of a chat-completions response."""
    try:
        message = body["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"unexpected model response: {str(body)[:300]}") from exc

    calls = []
    for raw in message.get("tool_calls") or []:
        function = raw.get("function") or {}
        calls.append(
            ToolCall(
                id=raw.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=str(function.get("name") or ""),
                arguments=_arguments(function.get("arguments")),
            )
        )

    usage = body.get("usage") or {}
    return LLMReply(
        content=_text(message.get("content")),
        tool_calls=calls,
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            calls=1,
        ),
    )


def get_llm() -> LLMClient:
    """FastAPI dependency; tests override it with a scripted fake."""
    if not settings.AI_BASE_URL or not settings.AI_MODEL:
        raise LLMError("AI_BASE_URL and AI_MODEL must be set")
    return OpenAICompatibleClient(
        base_url=settings.AI_BASE_URL,
        model=settings.AI_MODEL,
        api_key=settings.AI_API_KEY,
        timeout=settings.AI_TIMEOUT_SECONDS,
    )


def _arguments(raw: Any) -> dict[str, Any] | None:
    """Tool arguments arrive as a JSON string (some servers send an object)."""
    if isinstance(raw, dict):
        return raw
    if raw is None or raw == "":
        return {}
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(_FENCE.sub("", raw))
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _text(content: Any) -> str:
    """Message content is a string, null, or a list of typed parts."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _backoff(attempt: int) -> float:
    return float(2**attempt)


def _retry_after(response: httpx.Response) -> float | None:
    """Seconds from a numeric Retry-After header, capped; None when absent."""
    try:
        return min(float(response.headers["retry-after"]), MAX_RETRY_WAIT)
    except (KeyError, ValueError):
        return None
