"""Client for the Claude API through the official Anthropic SDK.

The agent loop speaks the chat-completions message format (see agent/llm.py).
This client translates that format to the Messages API and back, so the loop,
the tools and the tests don't change when AI_PROVIDER=anthropic.

Each assistant reply keeps Claude's own content blocks (thinking, text,
tool_use) and they are sent back unchanged on the next request: Claude's
thinking blocks have to be replayed as they came for a tool loop to continue.
"""

from typing import Any

import anthropic

from agent.llm import LLMError, LLMReply, ToolCall, Usage

# Thinking is always on for Claude Opus 5.5 and counts toward max_tokens,
# so this is far above the chat-completions client's limit.
MAX_OUTPUT_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicClient:
    """POST /v1/messages via AsyncAnthropic. The SDK retries 408/409/429/5xx and
    network errors itself."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        effort: str = "medium",
        timeout: float = 60,
        client: anthropic.AsyncAnthropic | None = None,  # tests can pass their own
    ):
        self.model = model
        self._effort = effort
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=timeout, max_retries=2
        )

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        system, converted = to_anthropic_messages(messages)
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": converted,
            "output_config": {"effort": self._effort},
            # System prompt and tools are the same on every call: cache them.
            "cache_control": {"type": "ephemeral"},
            # If a safety classifier declines, the API retries on a fallback model.
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = to_anthropic_tools(tools)
        try:
            response = await self._client.beta.messages.create(**params)
        except anthropic.APIStatusError as exc:
            raise LLMError(
                f"Claude API returned {exc.status_code}: {exc.message[:300]}"
                f" (request id {exc.request_id})"
            ) from exc
        except anthropic.APIConnectionError as exc:  # includes timeouts
            raise LLMError(f"Claude API unreachable: {exc!r}") from exc
        return parse_response(response)


def parse_response(response: Any) -> LLMReply:
    """Text and tool calls for the loop, plus the raw blocks to replay."""
    text: list[str] = []
    calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            text.append(block.text)
        elif block.type == "tool_use":
            arguments = block.input if isinstance(block.input, dict) else None
            calls.append(ToolCall(id=block.id, name=block.name, arguments=arguments))

    if response.stop_reason == "max_tokens":
        calls = []  # the last tool call may be cut off; answer with the text so far

    usage = response.usage
    input_tokens = (
        (usage.input_tokens or 0)
        + (usage.cache_read_input_tokens or 0)
        + (usage.cache_creation_input_tokens or 0)
    )
    return LLMReply(
        # On a refusal the text is empty and the loop answers with its fallback message.
        content="" if response.stop_reason == "refusal" else "".join(text),
        tool_calls=calls,
        usage=Usage(input_tokens=input_tokens, output_tokens=usage.output_tokens or 0, calls=1),
        provider_content=[block.to_dict() for block in response.content],
    )


def to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """{"type": "function", "function": {name, description, parameters}} -> Claude tools."""
    out = []
    for tool in tools:
        function = tool.get("function") or {}
        out.append(
            {
                "name": function["name"],
                "description": function.get("description") or "",
                "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Chat-completions messages -> (system prompt, Messages API messages).

    - system messages become the top-level system prompt
    - an assistant turn Claude produced is replayed as its original blocks
    - consecutive tool results go into one user message, as Claude expects
    """
    system: list[str] = []
    out: list[dict[str, Any]] = []

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "system":
            if content:
                system.append(str(content))
        elif role == "tool":
            result = {
                "type": "tool_result",
                "tool_use_id": message["tool_call_id"],
                "content": str(content or ""),
            }
            last = out[-1] if out else None
            if last and last["role"] == "user" and _is_tool_results(last["content"]):
                last["content"].append(result)
            else:
                out.append({"role": "user", "content": [result]})
        elif role == "assistant":
            blocks = message.get("provider_content")
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            elif content:  # an earlier answer from the client's history
                out.append({"role": "assistant", "content": str(content)})
        elif role == "user":
            out.append({"role": "user", "content": str(content or "")})

    return "\n\n".join(system), out


def _is_tool_results(content: Any) -> bool:
    return (
        isinstance(content, list)
        and bool(content)
        and all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
    )
