"""Tests for the approval wire encoding (message metadata <-> decisions)."""

from __future__ import annotations

from agent_framework import Content

from weather_agent import a2a_encoding as enc


def _approval_request_content(call_id="call_1", city="Paris"):
    call = Content.from_function_call(call_id=call_id, name="get_current_weather", arguments={"city": city})
    return Content.from_function_approval_request(id=call_id, function_call=call)


def test_pending_from_request():
    pending = enc.pending_from_request(_approval_request_content())
    assert pending.call_id == "call_1"
    assert pending.function_name == "get_current_weather"
    assert pending.arguments == {"city": "Paris"}


def test_request_metadata_shape():
    pending = [enc.PendingApproval("call_1", "get_current_weather", {"city": "Paris"})]
    metadata = enc.build_request_metadata(pending)
    assert metadata[enc.KIND_KEY] == enc.KIND_REQUEST
    assert metadata[enc.APPROVALS_KEY][0]["call_id"] == "call_1"
    assert metadata[enc.APPROVALS_KEY][0]["function_name"] == "get_current_weather"
    assert "get_current_weather" in enc.build_request_text(pending)


def test_client_response_round_trips_through_decode():
    decisions = [enc.ApprovalDecision("call_1", True), enc.ApprovalDecision("call_2", False)]
    message = enc.build_client_response_message(decisions, context_id="ctx-1", task_id="task-1")

    decoded = enc.decode_decisions(message)
    assert decoded == decisions
    assert message.context_id == "ctx-1"
    assert message.task_id == "task-1"


def test_decode_ignores_non_approval_messages():
    from tests.conftest import user_text_message

    message = user_text_message("just a normal question", context_id="ctx-1")
    assert enc.decode_decisions(message) == []


def test_parse_plaintext_decision():
    assert enc.parse_plaintext_decision("approve") is True
    assert enc.parse_plaintext_decision("YES") is True
    assert enc.parse_plaintext_decision("deny") is False
    assert enc.parse_plaintext_decision("no") is False
    assert enc.parse_plaintext_decision("maybe later") is None


def test_build_approval_response_content():
    pending = enc.PendingApproval("call_1", "get_current_weather", {"city": "Paris"})
    content = enc.build_approval_response_content(enc.ApprovalDecision("call_1", True), pending)
    assert content.type == "function_approval_response"
    assert content.approved is True
