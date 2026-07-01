"""A2A server hosting the weather agent.

Wires the agent, the approval-aware executor, and an in-memory A2A task store
into a Starlette ASGI app that serves:

* the AgentCard at ``/.well-known/agent-card.json``, and
* the JSON-RPC A2A endpoint at ``/`` (``message:send`` etc.).
"""

from __future__ import annotations

import argparse
import os

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from agent_framework import Agent
from starlette.applications import Starlette

from .agent import build_weather_agent
from .agent_card import build_agent_card
from .a2a_executor import ApprovalA2AExecutor


def create_app(
    *,
    agent: Agent | None = None,
    agent_card: AgentCard | None = None,
    task_store: InMemoryTaskStore | None = None,
    url: str = "http://localhost:9999/",
) -> Starlette:
    """Create the Starlette ASGI app for the A2A server.

    Every dependency is injectable so tests can supply a deterministic agent and
    inspect the in-memory task store.
    """
    agent = agent or build_weather_agent()
    agent_card = agent_card or build_agent_card(url)

    request_handler = DefaultRequestHandler(
        agent_executor=ApprovalA2AExecutor(agent),
        task_store=task_store or InMemoryTaskStore(),
        agent_card=agent_card,
    )

    return Starlette(
        routes=[
            *create_agent_card_routes(agent_card),
            *create_jsonrpc_routes(request_handler, "/"),
        ]
    )


def _build_demo_app(url: str) -> Starlette:
    """Build an app backed by the offline, LLM-free scripted client."""
    from .scripted_client import ScriptedChatClient, weather_demo_script

    agent = build_weather_agent(ScriptedChatClient(weather_demo_script))
    return create_app(agent=agent, url=url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the weather A2A agent server.")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "9999")))
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with a deterministic, LLM-free client (no API key required).",
    )
    args = parser.parse_args()

    url = f"http://localhost:{args.port}/"
    app = _build_demo_app(url) if args.demo else create_app(url=url)

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
