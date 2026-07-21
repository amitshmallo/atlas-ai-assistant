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

from app.infrastructure.graph_mail_client import HttpxGraphMailClient  # noqa: E402
from app.infrastructure.telemetry import configure_telemetry, traced_subprocess_span  # noqa: E402

configure_telemetry(service_name="atlas-mcp-graph")

mcp = FastMCP("graph")
_mail_client = HttpxGraphMailClient()


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


if __name__ == "__main__":
    mcp.run()
