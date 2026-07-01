"""Tests that the Starlette app is wired up and serves a valid A2A AgentCard."""

from __future__ import annotations

from starlette.testclient import TestClient

from weather_agent.server import create_app


def test_agent_card_is_served(scripted_agent):
    app = create_app(agent=scripted_agent, url="http://testserver/")
    client = TestClient(app)

    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200

    card = response.json()
    assert card["name"] == "Weather Agent"
    # skill is present (protobuf JSON uses the field name "skills")
    skill_ids = [s.get("id") for s in card.get("skills", [])]
    assert "get_current_weather" in skill_ids


def test_jsonrpc_route_is_mounted(scripted_agent):
    app = create_app(agent=scripted_agent, url="http://testserver/")
    # The A2A JSON-RPC endpoint is mounted at "/".
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/" in paths
