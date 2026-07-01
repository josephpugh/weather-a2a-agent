"""End-to-end tests for the human-in-the-loop A2A executor.

These drive :class:`ApprovalA2AExecutor` exactly as the A2A request handler would,
across the two-message round-trip, and assert the A2A task-state transitions:

    submit -> working -> input-required   (turn 1: pause for approval)
    submit -> working -> completed        (turn 2: approve and finish)
"""

from __future__ import annotations

import pytest
from google.protobuf.json_format import MessageToDict

from weather_agent import a2a_encoding as enc
from weather_agent.a2a_executor import ApprovalA2AExecutor

from tests.conftest import FakeRequestContext, RecordingEventQueue, TaskState, user_text_message


def _pending_from_input_required(queue: RecordingEventQueue) -> dict:
    """Pull the approval request metadata out of the input-required event."""
    message = queue.message_for_state(TaskState.TASK_STATE_INPUT_REQUIRED)
    assert message is not None, "expected an input-required status message"
    metadata = MessageToDict(message.metadata)
    assert metadata[enc.KIND_KEY] == enc.KIND_REQUEST
    return metadata[enc.APPROVALS_KEY][0]


async def _run_turn(executor, context) -> RecordingEventQueue:
    queue = RecordingEventQueue()
    await executor.execute(context, queue)
    return queue


async def test_turn_one_pauses_with_input_required(scripted_agent, open_meteo):
    executor = ApprovalA2AExecutor(scripted_agent)
    context = FakeRequestContext(
        context_id="ctx-1",
        message=user_text_message("What's the weather in Paris?", context_id="ctx-1"),
    )

    queue = await _run_turn(executor, context)

    assert queue.final_state() == TaskState.TASK_STATE_INPUT_REQUIRED
    approval = _pending_from_input_required(queue)
    assert approval["function_name"] == "get_current_weather"
    # Tool must not have run before approval.
    assert not open_meteo.routes[0].called


async def test_full_approve_round_trip(scripted_agent, open_meteo):
    executor = ApprovalA2AExecutor(scripted_agent)

    # --- Turn 1: ask, receive input-required ---
    ctx1 = FakeRequestContext(
        context_id="ctx-1",
        message=user_text_message("What's the weather in Paris?", context_id="ctx-1"),
    )
    q1 = await _run_turn(executor, ctx1)
    task = q1.created_task
    call_id = _pending_from_input_required(q1)["call_id"]

    # --- Turn 2: approve (same context_id + task), receive completed ---
    approval_message = enc.build_client_response_message(
        [enc.ApprovalDecision(call_id=call_id, approved=True)],
        context_id="ctx-1",
        task_id=task.id,
    )
    ctx2 = FakeRequestContext(context_id="ctx-1", message=approval_message, current_task=task)
    q2 = await _run_turn(executor, ctx2)

    assert q2.final_state() == TaskState.TASK_STATE_COMPLETED
    assert open_meteo.routes[0].called  # approved tool ran
    assert "Paris, France" in q2.all_text()


async def test_full_deny_round_trip(scripted_agent, open_meteo):
    executor = ApprovalA2AExecutor(scripted_agent)

    ctx1 = FakeRequestContext(
        context_id="ctx-1",
        message=user_text_message("What's the weather in Paris?", context_id="ctx-1"),
    )
    q1 = await _run_turn(executor, ctx1)
    task = q1.created_task
    call_id = _pending_from_input_required(q1)["call_id"]

    deny_message = enc.build_client_response_message(
        [enc.ApprovalDecision(call_id=call_id, approved=False)],
        context_id="ctx-1",
        task_id=task.id,
    )
    ctx2 = FakeRequestContext(context_id="ctx-1", message=deny_message, current_task=task)
    q2 = await _run_turn(executor, ctx2)

    assert q2.final_state() == TaskState.TASK_STATE_COMPLETED
    assert not open_meteo.routes[0].called  # denied tool never ran
    assert "reject" in q2.all_text().lower()


async def test_plaintext_approval_is_accepted(scripted_agent, open_meteo):
    executor = ApprovalA2AExecutor(scripted_agent)

    ctx1 = FakeRequestContext(
        context_id="ctx-1",
        message=user_text_message("Weather in Paris?", context_id="ctx-1"),
    )
    q1 = await _run_turn(executor, ctx1)
    task = q1.created_task

    # A human replies with plain "approve" (no structured metadata).
    ctx2 = FakeRequestContext(
        context_id="ctx-1",
        message=user_text_message("approve", context_id="ctx-1", task_id=task.id),
        current_task=task,
    )
    q2 = await _run_turn(executor, ctx2)

    assert q2.final_state() == TaskState.TASK_STATE_COMPLETED
    assert open_meteo.routes[0].called


async def test_missing_context_id_raises(scripted_agent):
    executor = ApprovalA2AExecutor(scripted_agent)
    context = FakeRequestContext(
        context_id="ctx-x",
        message=user_text_message("hi", context_id="ctx-x"),
    )
    context.context_id = None  # simulate a malformed request
    with pytest.raises(ValueError):
        await executor.execute(context, RecordingEventQueue())
