"""Trivial second MCP server, existing purely to prove the extensibility
claim from the Phase 7 plan: adding a tool means adding an entry to
app/infrastructure/mcp_registry.py, with zero changes to the orchestrator
(application/chat.py) or the MCP client adapter that talks to it.

Not wired into any real feature — the in-memory notes list doesn't even
persist across process restarts. That's fine; its only job is to exist.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.infrastructure.telemetry import configure_telemetry, traced_subprocess_span  # noqa: E402

configure_telemetry(service_name="atlas-mcp-notes")

mcp = FastMCP("notes")

_notes: list[str] = []


@mcp.tool()
async def remember_note(text: str) -> str:
    """Remember a short note for later in this conversation."""
    with traced_subprocess_span("atlas-mcp-notes", "remember_note"):
        _notes.append(text)
        return f"Noted ({len(_notes)} total): {text}"


if __name__ == "__main__":
    mcp.run()
