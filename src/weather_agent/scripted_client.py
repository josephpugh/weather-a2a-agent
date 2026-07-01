"""A deterministic, LLM-free chat client.

This lets the agent run in tests and in an offline demo without any API key. It
is a real Agent Framework chat client: it mixes in ``FunctionInvocationLayer`` so
the agent's tool-calling / approval machinery is fully exercised — the only thing
faked is the model's token generation.

A ``script`` callable decides what the "model" says for a given conversation.
The default :func:`weather_demo_script` emulates a model that calls
``get_current_weather`` and then summarises the tool result.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Sequence

from agent_framework import (
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)

Script = Callable[[Sequence[Message]], ChatResponse]


class ScriptedChatClient(FunctionInvocationLayer, BaseChatClient):
    """A chat client whose responses are produced by a Python ``script`` callable."""

    def __init__(self, script: Script, **kwargs):
        super().__init__(**kwargs)
        self._script = script

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        if stream:
            raise NotImplementedError("ScriptedChatClient only supports non-streaming responses.")
        return self._script(list(messages))


def _latest_user_text(messages: Sequence[Message]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            text = "".join(c.text for c in (message.contents or []) if c.type == "text" and c.text)
            if text:
                return text
    return ""


def _tool_result(messages: Sequence[Message]) -> str | None:
    for message in reversed(messages):
        for content in message.contents or []:
            if content.type == "function_result":
                return str(content.result)
    return None


def _extract_city(text: str) -> str:
    """Best-effort city extraction for the offline demo."""
    match = re.search(r"\b(?:in|for|at)\s+([A-Za-z .'-]+)", text)
    city = (match.group(1) if match else text).strip().rstrip("?.!")
    return city or "London"


def weather_demo_script(messages: Sequence[Message]) -> ChatResponse:
    """Emulate a model that looks up the weather then summarises the result."""
    result = _tool_result(messages)
    if result is not None:
        # The tool has run; produce a final natural-language answer.
        return ChatResponse(
            messages=[Message(role="assistant", contents=[Content.from_text(result)])]
        )

    # No tool result yet: ask to call the weather tool (approval will gate it).
    city = _extract_city(_latest_user_text(messages))
    call = Content.from_function_call(
        call_id=f"call_{uuid.uuid4().hex[:8]}",
        name="get_current_weather",
        arguments={"city": city},
    )
    return ChatResponse(messages=[Message(role="assistant", contents=[call])])
