# Weather A2A Agent

> [!NOTE]
> **This is an example / reference project.** It exists to be read, copied, and
> adapted — a worked example of building a fully A2A-compliant agent with the
> Microsoft Agent Framework. It is intentionally small and heavily commented, and
> is **not** a production service (no auth, rate limiting, persistence, or
> deployment hardening). Lift the patterns into your own codebase rather than
> depending on this package directly.

A **reference implementation** of a fully [A2A](https://a2a-protocol.org/)-compliant
agent built with the [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/)
for Python.

**Web stack:** the A2A endpoint is a plain [Starlette](https://www.starlette.io/)
ASGI app (assembled from the `a2a-sdk` route builders) served by
[uvicorn](https://www.uvicorn.org/). It does **not** use FastAPI.

It demonstrates four things end to end:

1. **Two tools that call a real service**, with different approval postures —
   `get_current_weather` geocodes a city with [Open-Meteo](https://open-meteo.com/)
   and returns the current conditions, while `get_geocode_location` exposes just
   the geocoding step (city → name/country/coordinates) as its own read-only tool.
   Both share the same `geocode_city` lookup.
2. **Full A2A compliance** — the agent is exposed over the A2A protocol with an
   AgentCard and a JSON-RPC endpoint, using the framework's `A2AExecutor`.
3. **In-memory session state** — conversation history is retained per A2A
   `context_id` using the framework's built-in `InMemoryHistoryProvider`.
4. **Human-in-the-loop approval** — `get_current_weather` is declared
   `@tool(approval_mode="always_require")`, and the server enforces an
   allow/deny decision over A2A using the `input-required` task state.
   `get_geocode_location` is declared `@tool(approval_mode="never_require")`
   since it's a read-only lookup with no side effects, so it runs immediately.

## How it fits together

```
A2A client ──JSON-RPC──▶ Starlette app ──▶ DefaultRequestHandler
                                              │
                                              ▼
                                   ApprovalA2AExecutor  (weather_agent/a2a_executor.py)
                                              │  session_id = A2A context_id
                                              ▼
                                    Agent (weather_agent/agent.py)
                             ├─ InMemoryHistoryProvider  (session state)
                             ├─ get_current_weather      (approval-gated tool)
                             └─ get_geocode_location     (never needs approval)
```

| Concern | Where | Key API |
| --- | --- | --- |
| Weather tool (approval-gated) | `weather_agent/weather.py` | `@tool(approval_mode="always_require")` |
| Geocode tool (no approval) | `weather_agent/weather.py` | `@tool(approval_mode="never_require")` |
| Agent + memory | `weather_agent/agent.py` | `Agent(..., context_providers=[InMemoryHistoryProvider()])` |
| A2A HITL executor | `weather_agent/a2a_executor.py` | `TaskUpdater.requires_input()`, `TaskState.TASK_STATE_INPUT_REQUIRED` |
| Approval wire format | `weather_agent/a2a_encoding.py` | message `metadata` |
| AgentCard | `weather_agent/agent_card.py` | `AgentCard` / `AgentSkill` |
| Server | `weather_agent/server.py` | `create_agent_card_routes`, `create_jsonrpc_routes` |

## The human-in-the-loop flow

Because `get_current_weather` requires approval (unlike `get_geocode_location`,
which runs immediately), a single weather question becomes a **two-message A2A
exchange** that shares one `context_id`:

1. **Client → server**: `message:send` with `"What's the weather in Paris?"`.
   The agent decides to call `get_current_weather`, but the tool is approval-gated,
   so the run pauses. The executor records the pending call and returns a task in
   the **`input-required`** state. The message carries the pending call in
   `metadata` (`weather_agent/kind = function_approval_request`).
2. **Client → server**: a second `message:send` (same `context_id` / `task_id`)
   whose `metadata` carries the decision
   (`weather_agent/kind = function_approval_response`, `approved: true|false`).
   The executor rebuilds the framework approval-response content, resumes the run,
   and the task moves to **`completed`** — running the tool only if approved.

The server is authoritative about *what* is being approved: the tool name and
arguments come from the executor's pending-approval registry, not from the client
(the client only sends `call_id` + `approved`). A plain-text `approve` / `deny`
reply is also accepted for humans poking the endpoint by hand.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install --pre -e ".[dev,openai]"
```

### Run offline (no API key)

A deterministic, LLM-free client drives the agent so you can see the whole A2A
flow without any credentials:

```bash
python -m weather_agent.server --demo
# AgentCard:  http://localhost:9999/.well-known/agent-card.json
```

### Run against a real LLM

```bash
cp .env.example .env   # set OPENAI_API_KEY
export $(grep -v '^#' .env | xargs)
python -m weather_agent.server
```

Any Agent Framework chat client works — pass your own to `build_weather_agent()`
or edit `create_chat_client()` in `weather_agent/agent.py`.

## Tests

```bash
pytest
```

The suite runs fully offline (Open-Meteo HTTP calls are mocked with `respx`, and
the LLM is the scripted client). It covers both tools (including that
`get_geocode_location` never triggers approval), the approval semantics for
`get_current_weather` (approve **and** deny), session-state persistence across
A2A turns, the wire encoding, the executor's `input-required` round-trip, and
the served AgentCard.
