"""The A2A AgentCard describing this agent to other A2A clients."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

WEATHER_SKILL = AgentSkill(
    id="get_current_weather",
    name="Current Weather",
    description=(
        "Get the current weather for a city. Requires human approval before each lookup."
    ),
    tags=["weather", "forecast", "open-meteo"],
    examples=[
        "What's the weather in Paris?",
        "Is it raining in Tokyo, Japan right now?",
    ],
)


def build_agent_card(url: str = "http://localhost:9999/") -> AgentCard:
    """Build the public AgentCard served at the A2A well-known endpoint.

    ``capabilities.streaming`` is False because this agent uses request/response
    (``message:send``) so that the human-in-the-loop ``input-required`` pause is
    easy to follow. The card advertises a JSON-RPC interface at ``url``.
    """
    return AgentCard(
        name="Weather Agent",
        description=(
            "A fully A2A-compliant weather agent built with the Microsoft Agent Framework. "
            "Retains conversation state per context_id and requires human approval before "
            "each weather lookup."
        ),
        version="0.1.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[AgentInterface(url=url, protocol_binding="JSONRPC")],
        skills=[WEATHER_SKILL],
    )
