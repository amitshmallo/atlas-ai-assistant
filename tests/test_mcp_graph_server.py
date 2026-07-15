"""Unit tests for the graph MCP server's tool functions.

These call the plain async functions directly — no subprocess, no stdio
transport — since FastMCP's @mcp.tool() decorator leaves the underlying
function callable. The actual transport is covered separately by
test_mcp_tool_provider.py, which spawns a real subprocess.
"""

import json

import pytest

from app.domain.entities import EmailDraft, EmailMessage, EmailSummary
from mcp_servers import graph_server


class FakeGraphMailClient:
    def __init__(self) -> None:
        self.last_call: tuple | None = None

    async def list_recent_emails(self, access_token, top, unread_only):
        self.last_call = ("list_recent_emails", access_token, top, unread_only)
        return [EmailSummary(id="msg-1", subject="Hello", preview="hi")]

    async def get_email(self, access_token, message_id):
        self.last_call = ("get_email", access_token, message_id)
        return EmailMessage(id=message_id, subject="Hello", body="Full body")

    async def create_draft_reply(self, access_token, message_id, body):
        self.last_call = ("create_draft_reply", access_token, message_id, body)
        return EmailDraft(id="draft-1")


@pytest.fixture(autouse=True)
def fake_mail_client(monkeypatch):
    fake = FakeGraphMailClient()
    monkeypatch.setattr(graph_server, "_mail_client", fake)
    return fake


@pytest.fixture(autouse=True)
def graph_access_token_env(monkeypatch):
    monkeypatch.setenv("GRAPH_ACCESS_TOKEN", "graph-token-xyz")


async def test_list_recent_emails_uses_env_token(fake_mail_client):
    result = await graph_server.list_recent_emails(top=3, unread_only=True)

    assert fake_mail_client.last_call == ("list_recent_emails", "graph-token-xyz", 3, True)
    assert json.loads(result)[0]["id"] == "msg-1"


async def test_read_email_uses_env_token(fake_mail_client):
    result = await graph_server.read_email(message_id="msg-1")

    assert fake_mail_client.last_call == ("get_email", "graph-token-xyz", "msg-1")
    assert json.loads(result)["body"] == "Full body"


async def test_draft_reply_never_sends(fake_mail_client):
    result = await graph_server.draft_reply(message_id="msg-1", body="Sounds good")

    assert fake_mail_client.last_call == ("create_draft_reply", "graph-token-xyz", "msg-1", "Sounds good")
    assert json.loads(result)["id"] == "draft-1"


async def test_propose_calendar_event_never_touches_mail_client(fake_mail_client):
    result = await graph_server.propose_calendar_event(
        subject="Sync", start="2026-07-20T10:00:00", end="2026-07-20T10:30:00"
    )

    assert fake_mail_client.last_call is None  # no Graph call was made
    parsed = json.loads(result)
    assert parsed["subject"] == "Sync"
    assert "not created" in parsed["status"]


async def test_missing_env_token_raises(monkeypatch, fake_mail_client):
    monkeypatch.delenv("GRAPH_ACCESS_TOKEN", raising=False)

    with pytest.raises(RuntimeError):
        await graph_server.read_email(message_id="msg-1")
