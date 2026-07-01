"""Agent construction.

Builds the weather :class:`~agent_framework.Agent`, wiring in:

* the approval-gated ``get_current_weather`` tool, and
* an :class:`~agent_framework.InMemoryHistoryProvider` so that conversation
  history is retained per session.

The A2A layer creates a session with ``session_id = A2A context_id`` on every
request (see :mod:`weather_agent.a2a_executor`). ``InMemoryHistoryProvider``
keys stored messages by that session id, so re-using a ``context_id`` across
A2A calls continues the same conversation — including a pending, not-yet-approved
tool call.
"""

from __future__ import annotations

import os

from agent_framework import Agent, BaseChatClient, InMemoryHistoryProvider

from .weather import get_current_weather, get_geocode_location

INSTRUCTIONS = (
    "You are a helpful weather assistant. "
    "When a user asks about the weather, call the get_current_weather tool with the city name. "
    "That tool requires human approval before it runs, so it may pause; once you receive the "
    "result, answer the user in a friendly, concise sentence. "
    "If the tool reports it could not find a location, ask the user to clarify the city. "
    "If a user only asks for a city's coordinates or location (not the weather), use the "
    "get_geocode_location tool instead — it never requires approval."
)


def build_weather_agent(chat_client: BaseChatClient | None = None) -> Agent:
    """Build the weather agent.

    Args:
        chat_client: The LLM chat client to drive the agent. When omitted, one is
            created from the environment via :func:`create_chat_client`. Tests and
            the offline demo inject a deterministic client instead.
    """
    client = chat_client or create_chat_client()
    return Agent(
        client=client,
        name="Weather Agent",
        description="Provides current weather for any city, with human approval before each lookup.",
        instructions=INSTRUCTIONS,
        tools=[get_current_weather, get_geocode_location],
        # The built-in in-memory history provider keeps session state keyed by
        # session id (which the A2A executor sets to the A2A context_id).
        context_providers=[InMemoryHistoryProvider()],
    )


def create_chat_client() -> BaseChatClient:
    """Create a chat client from environment configuration.

    Defaults to OpenAI (``OPENAI_API_KEY`` / ``OPENAI_CHAT_MODEL``). Swap this for
    any other Agent Framework chat client (Azure OpenAI, Foundry, Anthropic, ...).
    """
    try:
        from agent_framework.openai import OpenAIChatClient
    except ImportError as exc:  # pragma: no cover - exercised only without the extra installed
        raise RuntimeError(
            "No chat client available. Install the 'openai' extra "
            "(`pip install weather-a2a-agent[openai]`) and set OPENAI_API_KEY, "
            "or pass your own chat client to build_weather_agent()."
        ) from exc

    return OpenAIChatClient(model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"))
