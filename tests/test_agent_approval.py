"""Agent-level tests for human-in-the-loop approval and session memory.

These exercise the Agent Framework approval semantics directly (before the A2A
layer): a run pauses with ``user_input_requests`` and only proceeds once an
approval response is supplied. They also show that history — including the paused
tool call — persists across freshly created sessions that share a ``session_id``,
which is exactly what the A2A executor relies on.
"""

from __future__ import annotations

from agent_framework import Message


async def _ask_weather(agent, session):
    return await agent.run("What's the weather in Paris?", session=session)


async def test_run_pauses_for_approval(scripted_agent, open_meteo):
    session = scripted_agent.create_session(session_id="ctx-1")
    response = await _ask_weather(scripted_agent, session)

    # The run paused: it surfaced an approval request and did not answer.
    assert len(response.user_input_requests) == 1
    request = response.user_input_requests[0]
    assert request.type == "function_approval_request"
    assert request.function_call.name == "get_current_weather"
    assert request.function_call.arguments == {"city": "Paris"}

    # The tool has NOT run yet — no Open-Meteo calls were made.
    geocode_route = open_meteo.routes[0]
    assert not geocode_route.called


async def test_approval_runs_tool_and_persists_history(scripted_agent, open_meteo):
    # Turn 1: ask, and pause for approval.
    request = (
        await _ask_weather(scripted_agent, scripted_agent.create_session(session_id="ctx-1"))
    ).user_input_requests[0]

    # Turn 2: approve on a *fresh* session object with the same id. This only
    # works because InMemoryHistoryProvider persisted the paused call by session id.
    approval = Message(role="user", contents=[request.to_function_approval_response(True)])
    result = await scripted_agent.run(
        approval, session=scripted_agent.create_session(session_id="ctx-1")
    )

    assert not result.user_input_requests  # fully resolved
    assert "Paris, France" in result.text
    assert "partly cloudy" in result.text
    assert open_meteo.routes[0].called  # the approved tool actually ran


async def test_denial_blocks_tool(scripted_agent, open_meteo):
    request = (
        await _ask_weather(scripted_agent, scripted_agent.create_session(session_id="ctx-1"))
    ).user_input_requests[0]

    denial = Message(role="user", contents=[request.to_function_approval_response(False)])
    result = await scripted_agent.run(
        denial, session=scripted_agent.create_session(session_id="ctx-1")
    )

    assert not open_meteo.routes[0].called  # tool never ran
    assert "reject" in result.text.lower()


async def test_sessions_are_isolated_by_context_id(scripted_agent):
    # A pending approval in one context must not leak into another.
    r1 = await _ask_weather(scripted_agent, scripted_agent.create_session(session_id="ctx-A"))
    r2 = await _ask_weather(scripted_agent, scripted_agent.create_session(session_id="ctx-B"))

    call_a = r1.user_input_requests[0].function_call.call_id
    call_b = r2.user_input_requests[0].function_call.call_id
    assert call_a != call_b
