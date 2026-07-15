import json

import pytest

from app.application.graph_tools import GraphToolExecutor, UnknownToolError
from app.domain.entities import EmailDraft, EmailMessage, EmailSummary, ToolCallRequest


class FakeGraphMailClient:
    def __init__(self) -> None:
        self.last_call: tuple[str, ...] | None = None

    async def list_recent_emails(self, access_token, top, unread_only):
        self.last_call = ("list_recent_emails", access_token, top, unread_only)
        return [
            EmailSummary(id="msg-1", subject="Hello", from_address="a@example.com", preview="hi"),
        ]

    async def get_email(self, access_token, message_id):
        self.last_call = ("get_email", access_token, message_id)
        return EmailMessage(id=message_id, subject="Hello", body="Full body text")

    async def create_draft_reply(self, access_token, message_id, body):
        self.last_call = ("create_draft_reply", access_token, message_id, body)
        return EmailDraft(id="draft-1")


async def test_list_recent_emails_dispatches_and_serializes():
    mail_client = FakeGraphMailClient()
    executor = GraphToolExecutor(mail_client)
    tool_call = ToolCallRequest(id="call-1", name="list_recent_emails", arguments={"top": 3, "unread_only": True})

    result = await executor.execute(tool_call, access_token="graph-token")

    assert mail_client.last_call == ("list_recent_emails", "graph-token", 3, True)
    parsed = json.loads(result)
    assert parsed[0]["id"] == "msg-1"


async def test_read_email_dispatches_and_serializes():
    mail_client = FakeGraphMailClient()
    executor = GraphToolExecutor(mail_client)
    tool_call = ToolCallRequest(id="call-2", name="read_email", arguments={"message_id": "msg-1"})

    result = await executor.execute(tool_call, access_token="graph-token")

    assert mail_client.last_call == ("get_email", "graph-token", "msg-1")
    assert json.loads(result)["body"] == "Full body text"


async def test_draft_reply_never_sends_and_returns_draft_status():
    mail_client = FakeGraphMailClient()
    executor = GraphToolExecutor(mail_client)
    tool_call = ToolCallRequest(
        id="call-3", name="draft_reply", arguments={"message_id": "msg-1", "body": "Sounds good"}
    )

    result = await executor.execute(tool_call, access_token="graph-token")

    assert mail_client.last_call == ("create_draft_reply", "graph-token", "msg-1", "Sounds good")
    assert "not sent" in json.loads(result)["status"]


async def test_propose_calendar_event_never_calls_graph():
    mail_client = FakeGraphMailClient()
    executor = GraphToolExecutor(mail_client)
    tool_call = ToolCallRequest(
        id="call-4",
        name="propose_calendar_event",
        arguments={"subject": "Sync", "start": "2026-07-20T10:00:00", "end": "2026-07-20T10:30:00"},
    )

    result = await executor.execute(tool_call, access_token="graph-token")

    assert mail_client.last_call is None  # no Graph call was made
    parsed = json.loads(result)
    assert parsed["subject"] == "Sync"
    assert "not created" in parsed["status"]


async def test_unknown_tool_raises():
    executor = GraphToolExecutor(FakeGraphMailClient())
    tool_call = ToolCallRequest(id="call-5", name="delete_everything", arguments={})

    with pytest.raises(UnknownToolError):
        await executor.execute(tool_call, access_token="graph-token")
