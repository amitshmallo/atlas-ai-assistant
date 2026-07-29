"""Standalone MCP server exposing Microsoft Graph email tools.

Run as a subprocess over stdio — see app/infrastructure/mcp_tool_provider.py
for the client side. This is what "the orchestrator becomes a generic MCP
client" means in practice: application/chat.py has no idea this file, or
Microsoft Graph, exists at all.

The Graph access token is never exposed to the model as a tool argument —
it's injected via the GRAPH_ACCESS_TOKEN environment variable when the
client spawns this process (a fresh, short-lived token per chat turn).
"""

import json
import os
import sys
from pathlib import Path

# Allow `import app....` when this file is run directly as a subprocess,
# since it lives outside the `app` package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.infrastructure.graph_calendar_client import HttpxGraphCalendarClient  # noqa: E402
from app.infrastructure.graph_mail_client import HttpxGraphMailClient  # noqa: E402
from app.infrastructure.telemetry import configure_telemetry, traced_subprocess_span  # noqa: E402

configure_telemetry(service_name="atlas-mcp-graph")

mcp = FastMCP("graph")
_mail_client = HttpxGraphMailClient()
_calendar_client = HttpxGraphCalendarClient()


def _access_token() -> str:
    token = os.environ.get("GRAPH_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GRAPH_ACCESS_TOKEN was not set for this MCP server process")
    return token


@mcp.tool()
async def list_recent_emails(top: int = 5, unread_only: bool = True) -> str:
    """List the user's most recent emails, optionally filtered to unread only."""
    with traced_subprocess_span("atlas-mcp-graph", "list_recent_emails"):
        summaries = await _mail_client.list_recent_emails(_access_token(), top=top, unread_only=unread_only)
        return json.dumps([s.model_dump() for s in summaries])


@mcp.tool()
async def search_emails(query: str, top: int = 10) -> str:
    """Full-text search the user's mailbox by keyword — matches subject,
    body, and sender, not just the most recent messages. Use this instead
    of list_recent_emails when the user asks to find a specific email
    rather than "what's new"."""
    with traced_subprocess_span("atlas-mcp-graph", "search_emails"):
        summaries = await _mail_client.search_emails(_access_token(), query=query, top=top)
        return json.dumps([s.model_dump() for s in summaries])


@mcp.tool()
async def read_email(message_id: str) -> str:
    """Read the full subject and body of one email by its id."""
    with traced_subprocess_span("atlas-mcp-graph", "read_email"):
        email = await _mail_client.get_email(_access_token(), message_id)
        return json.dumps(email.model_dump())


@mcp.tool()
async def draft_reply(message_id: str, body: str) -> str:
    """Create a reply draft for an email in the user's Drafts folder.
    This never sends the email — it only saves a draft for the user to
    review and send themselves."""
    with traced_subprocess_span("atlas-mcp-graph", "draft_reply"):
        draft = await _mail_client.create_draft_reply(_access_token(), message_id, body)
        return json.dumps(draft.model_dump())


@mcp.tool()
async def list_calendar_events(top: int = 10) -> str:
    """List the user's upcoming calendar events (next 30 days), soonest
    first. Read-only — safe to call directly, unlike creating an event."""
    with traced_subprocess_span("atlas-mcp-graph", "list_calendar_events"):
        events = await _calendar_client.list_upcoming_events(_access_token(), top=top)
        return json.dumps([e.model_dump() for e in events])


@mcp.tool()
async def propose_calendar_event(subject: str, start: str, end: str, attendees: list[str] | None = None) -> str:
    """Propose a calendar event to the user. This does NOT create anything —
    it only returns the proposal so you can present it and ask the user to
    explicitly confirm before it's actually created."""
    with traced_subprocess_span("atlas-mcp-graph", "propose_calendar_event"):
        return json.dumps(
            {
                "subject": subject,
                "start": start,
                "end": end,
                "attendees": attendees or [],
                "status": "proposed — not created; ask the user to confirm via the app",
            }
        )


@mcp.tool()
async def check_free_busy(emails: list[str], start: str, end: str) -> str:
    """Check whether the given people (email addresses, include the user's
    own address if you want to check their own availability too) are busy
    between start and end. Read-only — use this BEFORE proposing a meeting
    time with attendees, so you don't propose a time someone's already
    booked. Returns each person's busy periods in that window; an empty
    list means they're free the whole time."""
    with traced_subprocess_span("atlas-mcp-graph", "check_free_busy"):
        results = await _calendar_client.get_free_busy(_access_token(), emails=emails, start=start, end=end)
        return json.dumps([r.model_dump() for r in results])


@mcp.tool()
async def propose_reschedule_event(
    event_id: str, subject: str | None = None, start: str | None = None, end: str | None = None
) -> str:
    """Propose a change to an EXISTING event (found via list_calendar_events
    — event_id must come from there, never invented). This does NOT modify
    anything — it only returns the proposal so the user can review and
    confirm. Leave subject/start/end as null for whatever isn't changing."""
    with traced_subprocess_span("atlas-mcp-graph", "propose_reschedule_event"):
        return json.dumps(
            {
                "event_id": event_id,
                "subject": subject,
                "start": start,
                "end": end,
                "status": "proposed — not changed; ask the user to confirm via the app",
            }
        )


@mcp.tool()
async def propose_cancel_event(event_id: str, subject: str | None = None) -> str:
    """Propose cancelling an EXISTING event (event_id from
    list_calendar_events, never invented). This does NOT cancel anything —
    it only returns the proposal for the user to confirm. `subject` is
    just for display in the confirmation card, so the user can see which
    event they're about to cancel."""
    with traced_subprocess_span("atlas-mcp-graph", "propose_cancel_event"):
        return json.dumps(
            {
                "event_id": event_id,
                "subject": subject,
                "status": "proposed — not cancelled; ask the user to confirm via the app",
            }
        )


@mcp.tool()
async def propose_send_email(to: str, subject: str, body: str, attachment_filename: str | None = None) -> str:
    """Propose an email to send. This does NOT send anything — it only
    returns the proposal so you can present it and ask the user to
    explicitly confirm before it's actually sent. `to` should be a real
    email address: if the user only gave you a name, check whether
    remember_preference has already stored that name's address (it would
    show up as a contact_email_<name> preference in your context) before
    asking the user for it. attachment_filename, if given, must be a
    filename the user mentioned or one found via search_documents — never
    invent one; the actual file is looked up server-side by filename, not
    by anything you supply here."""
    with traced_subprocess_span("atlas-mcp-graph", "propose_send_email"):
        return json.dumps(
            {
                "to": to,
                "subject": subject,
                "body": body,
                "attachment_filename": attachment_filename,
                "status": "proposed — not sent; ask the user to confirm via the app",
            }
        )


if __name__ == "__main__":
    mcp.run()
