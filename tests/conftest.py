"""Shared test fixtures and helpers.

The whole suite runs offline:

* Open-Meteo HTTP calls are intercepted with ``respx`` (see ``open_meteo``), and
* the LLM is replaced by the deterministic :class:`ScriptedChatClient`.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import respx
from a2a.types import Message as A2AMessage
from a2a.types import Part as A2APart
from a2a.types import Role, TaskState

from weather_agent import weather
from weather_agent.agent import build_weather_agent
from weather_agent.scripted_client import ScriptedChatClient, weather_demo_script

# --------------------------------------------------------------------------- #
# Network mocking
# --------------------------------------------------------------------------- #

GEOCODE_PARIS = {
    "results": [
        {"name": "Paris", "country": "France", "latitude": 48.85, "longitude": 2.35}
    ]
}
CURRENT_PARIS = {
    "current": {
        "temperature_2m": 18.0,
        "relative_humidity_2m": 55,
        "wind_speed_10m": 12.0,
        "weather_code": 2,  # "partly cloudy"
    }
}


@pytest.fixture(autouse=True)
def open_meteo():
    """Autouse Open-Meteo mock with sensible defaults; tests may override routes."""
    with respx.mock(assert_all_called=False) as router:
        router.get(weather.GEOCODING_URL).mock(
            return_value=httpx.Response(200, json=GEOCODE_PARIS)
        )
        router.get(weather.FORECAST_URL).mock(
            return_value=httpx.Response(200, json=CURRENT_PARIS)
        )
        yield router


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #

@pytest.fixture
def scripted_agent():
    """A weather agent driven by the deterministic, LLM-free scripted client."""
    return build_weather_agent(ScriptedChatClient(weather_demo_script))


# --------------------------------------------------------------------------- #
# A2A test doubles
# --------------------------------------------------------------------------- #

class RecordingEventQueue:
    """Captures events enqueued by a ``TaskUpdater`` for assertions."""

    def __init__(self):
        self.events: list = []

    async def enqueue_event(self, event) -> None:
        self.events.append(event)

    def status_states(self) -> list[int]:
        states = []
        for event in self.events:
            state = getattr(getattr(event, "status", None), "state", None)
            if state is not None:
                states.append(state)
        return states

    def final_state(self) -> int | None:
        states = self.status_states()
        return states[-1] if states else None

    def message_for_state(self, state: int):
        """Return the status message attached to the event for a given state."""
        for event in self.events:
            status = getattr(event, "status", None)
            if status is not None and status.state == state and status.HasField("message"):
                return status.message
        return None

    def all_text(self) -> str:
        """Concatenate text from every status message (working, completed, ...)."""
        chunks = []
        for event in self.events:
            status = getattr(event, "status", None)
            if status is not None and status.HasField("message"):
                chunks.extend(p.text for p in status.message.parts if p.text)
        return "\n".join(chunks)

    @property
    def created_task(self):
        """The first enqueued Task event, if any (has ``.id`` / ``.context_id``)."""
        for event in self.events:
            if type(event).__name__ == "Task":
                return event
        return None


class FakeRequestContext:
    """Minimal stand-in for a2a's ``RequestContext`` (only what the executor reads)."""

    def __init__(self, *, context_id: str, message: A2AMessage, current_task=None):
        self.context_id = context_id
        self.message = message
        self.current_task = current_task
        self.task_id = getattr(current_task, "id", None)

    def get_user_input(self) -> str:
        return "".join(part.text for part in self.message.parts if part.text)


def user_text_message(text: str, *, context_id: str, task_id: str = "") -> A2AMessage:
    """Build an incoming A2A user text message."""
    return A2AMessage(
        message_id=str(uuid.uuid4()),
        context_id=context_id,
        task_id=task_id,
        role=Role.ROLE_USER,
        parts=[A2APart(text=text)],
    )


# Re-export commonly used symbols for tests.
__all__ = [
    "RecordingEventQueue",
    "FakeRequestContext",
    "TaskState",
    "user_text_message",
]
