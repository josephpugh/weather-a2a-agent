"""A fully A2A-compliant weather agent built with the Microsoft Agent Framework.

Highlights:

* :mod:`weather_agent.weather` - an approval-gated ``get_current_weather`` tool
  backed by the Open-Meteo geocoding + forecast APIs.
* :mod:`weather_agent.agent` - the agent, with ``InMemoryHistoryProvider`` for
  per-session (per ``context_id``) conversation state.
* :mod:`weather_agent.a2a_executor` - an ``A2AExecutor`` that pauses for human
  approval using A2A's ``input-required`` task state.
* :mod:`weather_agent.server` - the Starlette ASGI app exposing the A2A endpoint.
"""

from .agent import build_weather_agent, create_chat_client
from .agent_card import build_agent_card
from .a2a_executor import ApprovalA2AExecutor
from .server import create_app
from .weather import WeatherError, get_current_weather, get_weather_report

__all__ = [
    "ApprovalA2AExecutor",
    "WeatherError",
    "build_agent_card",
    "build_weather_agent",
    "create_app",
    "create_chat_client",
    "get_current_weather",
    "get_weather_report",
]
