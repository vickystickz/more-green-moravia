"""Request and response bodies of the agent API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_QUESTION_CHARS = 2000
MAX_HISTORY = 24


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1, max_length=MAX_QUESTION_CHARS, description="The question, in any language"
    )
    history: list[Turn] = Field(
        default_factory=list,
        max_length=MAX_HISTORY,
        description="Earlier questions and answers of this chat, oldest first, for follow-ups. "
        "Nothing is stored on the server.",
    )
    stream: bool = Field(
        True, description="true: server-sent events as the agent works; false: one JSON response"
    )

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message is empty")
        return value


class AgentStatus(BaseModel):
    enabled: bool
    model: str | None
    hexagons: int
    microzones: int


class MetricOut(BaseModel):
    name: str
    label: str
    description: str
    group: str
    unit: str


class Suggestion(BaseModel):
    question: str
    kind: str


SUGGESTIONS = [
    Suggestion(question="Which microzones need green infrastructure the most?", kind="where"),
    Suggestion(
        question="Where do many older people live in hot places with little green?", kind="where"
    ),
    Suggestion(question="With the Quick wins preset, where can we build first?", kind="where"),
    Suggestion(question="What drives the score in the city centre?", kind="explain"),
    Suggestion(question="How many residents live in hexagons scoring above 60?", kind="numbers"),
]

CHAT_EXAMPLES = {
    "stream": {
        "summary": "Ask (streamed)",
        "value": {"message": "Which microzones need green infrastructure the most?"},
    },
    "follow_up": {
        "summary": "Follow-up question",
        "value": {
            "message": "And with the Cool streets preset?",
            "history": [
                {"role": "user", "content": "Which microzones need green infrastructure the most?"},
                {
                    "role": "assistant",
                    "content": "The highest need is in **Centrum** (58 / 100) ...",
                },
            ],
        },
    },
    "json": {
        "summary": "One JSON response instead of a stream",
        "value": {
            "message": "How many residents live in hexagons scoring above 60?",
            "stream": False,
        },
    },
}

SSE_EXAMPLE = """\
event: step
data: {"tool":"rank_areas","label":"Ranked microzones by score","arguments":{"metric":"score","level":"microzone","limit":5},"ok":true,"error":null,"result":{"columns":["rank","microzone","hexagons","score","residents"],"rows":[{"rank":1,"microzone":"Mikrozóna Centrum","hexagons":9,"score":58.2,"residents":4120}],"summary":{},"truncated":true},"layer":{"level":"microzone","metric":"score","ids":["Mikrozóna Centrum"],"title":"Top 5 microzones: Green infrastructure need (map score)"},"ms":4}

event: answer
data: {"text":"The highest need is in **Centrum** (58 / 100) ...","model":"..."}

event: done
data: {"elapsed_ms":3400,"usage":{"input_tokens":5120,"output_tokens":96,"calls":2}}

"""
