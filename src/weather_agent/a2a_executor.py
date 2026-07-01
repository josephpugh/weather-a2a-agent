"""A2A executor with human-in-the-loop tool approval.

The stock :class:`agent_framework.a2a.A2AExecutor` runs an agent and always drives
the task to ``completed``. It does not know how to surface an Agent Framework
*function approval request* over A2A. This subclass adds exactly that behaviour
while reusing the base class for everything else:

* Each request opens a session keyed by the A2A ``context_id`` (so history,
  including a paused tool call, is retained by ``InMemoryHistoryProvider``).
* After running the agent, if it produced approval requests, the executor
  registers them and moves the task to A2A's ``input-required`` state instead of
  completing — carrying the details in message metadata (see
  :mod:`weather_agent.a2a_encoding`).
* When the client replies (same ``context_id`` / ``task_id``) with an approval
  decision, the executor rebuilds the framework approval-response content from
  the tracked pending call and resumes the run. The resumed run may complete or,
  for multi-tool turns, ask for approval again.

The pending-approval registry lives on the executor instance, which is the right
scope: a single long-lived executor handles both turns of the round-trip.
"""

from __future__ import annotations

import logging
from asyncio import CancelledError

from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState
from agent_framework import AgentSession, Message
from agent_framework.a2a import A2AExecutor

from . import a2a_encoding as enc

logger = logging.getLogger("weather_agent.a2a")


class ApprovalA2AExecutor(A2AExecutor):
    """An :class:`A2AExecutor` that pauses for human approval of tool calls."""

    def __init__(self, agent, run_kwargs=None):
        super().__init__(agent, stream=False, run_kwargs=run_kwargs)
        # context_id -> {call_id -> PendingApproval}
        self._pending: dict[str, dict[str, enc.PendingApproval]] = {}
        # context_id -> AgentSession, so conversation history (including a
        # paused tool call awaiting approval) survives across A2A requests.
        # ``Agent.create_session`` always returns a fresh, empty session, so
        # the executor itself must hold onto sessions between calls.
        self._sessions: dict[str, AgentSession] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.context_id is None:
            raise ValueError("Context ID must be provided in the RequestContext")
        if context.message is None:
            raise ValueError("Message must be provided in the RequestContext")

        task = context.current_task
        if not task:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, context.context_id)
        await updater.submit()

        try:
            await updater.start_work()

            # Session is keyed on the A2A context_id; reusing the same
            # AgentSession instance across calls is what lets the
            # InMemoryHistoryProvider retain prior turns (including any
            # paused tool call) — ``create_session`` itself always returns
            # a fresh, empty session.
            session = self._sessions.setdefault(
                context.context_id, self._agent.create_session(session_id=context.context_id)
            )

            query = self._build_query(context)
            response = await self._agent.run(query, session=session, **self._run_kwargs)

            approval_requests = response.user_input_requests
            if approval_requests:
                await self._request_approval(context.context_id, approval_requests, updater)
                return  # leave the task in input-required; do NOT complete

            await self._complete_with_answer(response, updater)

        except CancelledError:
            await updater.update_status(state=TaskState.TASK_STATE_CANCELED)
        except Exception as exc:  # noqa: BLE001 - surface any failure as a failed task
            logger.exception("ApprovalA2AExecutor error", exc_info=exc)
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=updater.new_agent_message([Part(text=str(exc))]),
            )

    # ----------------------------------------------------------------- #
    # Input handling
    # ----------------------------------------------------------------- #

    def _build_query(self, context: RequestContext):
        """Turn the incoming A2A message into agent input.

        If it carries approval decisions for calls we paused, rebuild the
        framework approval-response content(s); otherwise treat it as plain text.
        """
        context_id = context.context_id
        message = context.message
        pending_for_context = self._pending.get(context_id, {})

        decisions = enc.decode_decisions(message)
        # Fallback: a human typed "approve"/"deny" with no structured metadata.
        if not decisions and pending_for_context:
            verdict = enc.parse_plaintext_decision(enc.message_text(message))
            if verdict is not None:
                decisions = [
                    enc.ApprovalDecision(call_id=call_id, approved=verdict)
                    for call_id in pending_for_context
                ]

        if not decisions:
            return context.get_user_input()

        contents = []
        for decision in decisions:
            pending = pending_for_context.pop(decision.call_id, None)
            if pending is None:
                logger.warning("Ignoring approval for unknown call_id %s", decision.call_id)
                continue
            contents.append(enc.build_approval_response_content(decision, pending))
        if not pending_for_context:
            self._pending.pop(context_id, None)

        return Message(role="user", contents=contents)

    async def _request_approval(self, context_id: str, approval_requests, updater: TaskUpdater) -> None:
        """Register paused calls and move the task to input-required."""
        pending = [enc.pending_from_request(request) for request in approval_requests]
        registry = self._pending.setdefault(context_id, {})
        for item in pending:
            registry[item.call_id] = item

        message = updater.new_agent_message(
            parts=[Part(text=enc.build_request_text(pending))],
            metadata=enc.build_request_metadata(pending),
        )
        await updater.requires_input(message=message)

    async def _complete_with_answer(self, response, updater: TaskUpdater) -> None:
        """Finish the task, attaching the agent's answer as an artifact + completion message.

        Placing the text in both an A2A artifact and the completion message means
        clients that read only the final ``Task`` snapshot still receive the answer
        (non-streaming clients don't observe intermediate ``working`` updates).
        """
        answer = response.text
        if not answer:
            await updater.complete()
            return
        parts = [Part(text=answer)]
        await updater.add_artifact(parts, name="weather")
        await updater.complete(message=updater.new_agent_message(parts))
