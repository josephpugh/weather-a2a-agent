"""Wire encoding for human-in-the-loop approvals over A2A.

A2A models a pause-for-human-input as the ``input-required`` task state: the
server sends a message asking for input and stops; the client later sends a new
message (re-using the same ``context_id`` / ``task_id``) supplying that input.

This module defines the small, self-describing convention used to carry an
approval request (server -> client) and an approval decision (client -> server)
inside A2A message ``metadata``. Keeping it in one place makes the contract easy
to read and lets both the executor and A2A clients share it.

Request metadata (server -> client)::

    {
      "weather_agent/kind": "function_approval_request",
      "weather_agent/approvals": [
        {"call_id": "call_1", "function_name": "get_current_weather",
         "arguments": {"city": "Paris"}}
      ]
    }

Response metadata (client -> server)::

    {
      "weather_agent/kind": "function_approval_response",
      "weather_agent/approvals": [
        {"call_id": "call_1", "approved": true}
      ]
    }

A plain-text ``approve`` / ``deny`` reply is also accepted as a fallback for
humans driving the endpoint by hand (see :func:`parse_plaintext_decision`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from a2a.types import Message, Part, Role
from agent_framework import Content
from google.protobuf.json_format import MessageToDict

KIND_KEY = "weather_agent/kind"
APPROVALS_KEY = "weather_agent/approvals"
KIND_REQUEST = "function_approval_request"
KIND_RESPONSE = "function_approval_response"

_APPROVE_WORDS = {"approve", "approved", "yes", "y", "allow", "ok"}
_DENY_WORDS = {"deny", "denied", "no", "n", "reject", "rejected"}


@dataclass(frozen=True)
class PendingApproval:
    """A tool call awaiting a human decision, tracked server-side."""

    call_id: str
    function_name: str
    arguments: Any  # the tool arguments (typically a dict), used to rebuild the call


@dataclass(frozen=True)
class ApprovalDecision:
    """A human decision about a single tool call, received from the client."""

    call_id: str
    approved: bool


def pending_from_request(request: Content) -> PendingApproval:
    """Extract a :class:`PendingApproval` from a framework approval-request content."""
    call = request.function_call
    return PendingApproval(call_id=call.call_id, function_name=call.name, arguments=call.arguments)


# --------------------------------------------------------------------------- #
# Server -> client: build the "please approve" message
# --------------------------------------------------------------------------- #

def build_request_text(pending: list[PendingApproval]) -> str:
    """Human-readable prompt describing what needs approval."""
    lines = ["Approval required before running the following tool call(s):"]
    for item in pending:
        lines.append(f"  - {item.function_name}({item.arguments})  [call_id={item.call_id}]")
    lines.append("Reply with an approval decision (or the text 'approve' / 'deny').")
    return "\n".join(lines)


def build_request_metadata(pending: list[PendingApproval]) -> dict[str, Any]:
    """Structured approval-request payload for A2A message metadata."""
    return {
        KIND_KEY: KIND_REQUEST,
        APPROVALS_KEY: [
            {
                "call_id": item.call_id,
                "function_name": item.function_name,
                "arguments": item.arguments,
            }
            for item in pending
        ],
    }


# --------------------------------------------------------------------------- #
# Client -> server: decode a decision from an incoming message
# --------------------------------------------------------------------------- #

def _metadata_to_dict(message: Message) -> dict[str, Any]:
    """Convert an A2A message's protobuf Struct metadata into a plain dict."""
    if not message.HasField("metadata"):
        return {}
    return MessageToDict(message.metadata)


def message_text(message: Message) -> str:
    """Concatenate the text parts of an A2A message."""
    return "".join(part.text for part in message.parts if part.text)


def decode_decisions(message: Message) -> list[ApprovalDecision]:
    """Decode structured approval decisions from an incoming A2A message.

    Returns an empty list if the message does not carry an approval response.
    """
    metadata = _metadata_to_dict(message)
    if metadata.get(KIND_KEY) != KIND_RESPONSE:
        return []
    decisions: list[ApprovalDecision] = []
    for entry in metadata.get(APPROVALS_KEY, []):
        decisions.append(
            ApprovalDecision(call_id=str(entry["call_id"]), approved=bool(entry.get("approved", False)))
        )
    return decisions


def parse_plaintext_decision(text: str) -> bool | None:
    """Interpret a free-text reply as approve (True) / deny (False) / unknown (None)."""
    token = text.strip().lower()
    if token in _APPROVE_WORDS:
        return True
    if token in _DENY_WORDS:
        return False
    return None


# --------------------------------------------------------------------------- #
# Rebuild framework content from a decision + the tracked pending call
# --------------------------------------------------------------------------- #

def build_approval_response_content(decision: ApprovalDecision, pending: PendingApproval) -> Content:
    """Rebuild the framework ``function_approval_response`` content for a decision.

    The framework matches the response to the paused call by ``call_id`` *and* the
    reconstructed function call, so the authoritative ``function_name`` / ``arguments``
    come from the server-tracked :class:`PendingApproval`, not from the client.
    """
    function_call = Content.from_function_call(
        call_id=pending.call_id,
        name=pending.function_name,
        arguments=pending.arguments,
    )
    return Content.from_function_approval_response(
        approved=decision.approved,
        id=pending.call_id,
        function_call=function_call,
    )


# --------------------------------------------------------------------------- #
# Client-side helper (also used by the end-to-end test): build the reply message
# --------------------------------------------------------------------------- #

def build_client_response_message(
    decisions: list[ApprovalDecision],
    *,
    context_id: str,
    task_id: str,
) -> Message:
    """Construct the A2A message a client sends back to approve/deny tool calls."""
    summary = ", ".join(f"{d.call_id}={'approve' if d.approved else 'deny'}" for d in decisions)
    return Message(
        message_id=str(uuid.uuid4()),
        context_id=context_id,
        task_id=task_id,
        role=Role.ROLE_USER,
        parts=[Part(text=f"Approval decision: {summary}")],
        metadata={
            KIND_KEY: KIND_RESPONSE,
            APPROVALS_KEY: [{"call_id": d.call_id, "approved": d.approved} for d in decisions],
        },
    )
