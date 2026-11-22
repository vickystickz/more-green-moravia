"""The Claude client's translation to and from the Messages API, with a fake SDK client."""

from typing import Any

from anthropic.types.beta import BetaMessage

from agent.llm_anthropic import AnthropicClient, to_anthropic_messages

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rank_microzones",
            "description": "Rank microzones.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}},
        },
    }
]


def _message(content: list[dict[str, Any]], stop_reason: str) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 5,
                "cache_read_input_tokens": 90,
                "cache_creation_input_tokens": 0,
            },
        }
    )


class FakeSDK:
    def __init__(self, replies: list[BetaMessage]):
        self.replies = replies
        self.requests: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self

    async def create(self, **params: Any) -> BetaMessage:
        self.requests.append(params)
        return self.replies.pop(0)


async def test_tool_loop_round_trip():
    thinking = {"type": "thinking", "thinking": "", "signature": "sig"}
    tool_use = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "rank_microzones",
        "input": {"limit": 3},
    }
    sdk = FakeSDK(
        [
            _message([thinking, tool_use], "tool_use"),
            _message([{"type": "text", "text": "Done."}], "end_turn"),
        ]
    )
    llm = AnthropicClient(model="claude-opus-5-5", client=sdk)  # type: ignore[arg-type]

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are the GI agent."},
        {"role": "user", "content": "Where is need highest?"},
    ]
    reply = await llm.chat(messages, TOOLS)
    assert [c.name for c in reply.tool_calls] == ["rank_microzones"]
    assert reply.tool_calls[0].arguments == {"limit": 3}
    assert reply.usage.input_tokens == 100

    first = sdk.requests[0]
    assert first["system"] == "You are the GI agent."
    assert first["tools"][0]["input_schema"]["properties"] == {"limit": {"type": "integer"}}
    assert "temperature" not in first

    messages.append(reply.as_message())
    messages.append({"role": "tool", "tool_call_id": "toolu_1", "content": '{"rows": []}'})
    reply = await llm.chat(messages, TOOLS)
    assert reply.content == "Done."

    sent = sdk.requests[1]["messages"]
    assert sent[1]["content"][0]["type"] == "thinking"  # replayed unchanged
    assert sent[1]["content"][1]["id"] == "toolu_1"
    assert sent[2] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"rows": []}'}],
    }


def test_parallel_tool_results_share_one_message():
    _, out = to_anthropic_messages(
        [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": None,
                "provider_content": [{"type": "text", "text": "x"}],
            },
            {"role": "tool", "tool_call_id": "a", "content": "1"},
            {"role": "tool", "tool_call_id": "b", "content": "2"},
            {"role": "user", "content": "Stop calling tools."},
        ]
    )
    assert [m["role"] for m in out] == ["user", "assistant", "user", "user"]
    assert [r["tool_use_id"] for r in out[2]["content"]] == ["a", "b"]


async def test_refusal_gives_empty_answer():
    sdk = FakeSDK([_message([{"type": "text", "text": "partial"}], "refusal")])
    llm = AnthropicClient(model="claude-opus-5-5", client=sdk)  # type: ignore[arg-type]
    reply = await llm.chat([{"role": "user", "content": "q"}], [])
    assert reply.content == "" and not reply.tool_calls
    assert "tools" not in sdk.requests[0]
