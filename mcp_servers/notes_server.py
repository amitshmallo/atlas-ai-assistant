"""Trivial second MCP server, existing purely to prove the extensibility
claim from the Phase 7 plan: adding a tool means adding an entry to
app/infrastructure/mcp_registry.py, with zero changes to the orchestrator
(application/chat.py) or the MCP client adapter that talks to it.

Not wired into any real feature — the in-memory notes list doesn't even
persist across process restarts. That's fine; its only job is to exist.
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("notes")

_notes: list[str] = []


@mcp.tool()
async def remember_note(text: str) -> str:
    """Remember a short note for later in this conversation."""
    _notes.append(text)
    return f"Noted ({len(_notes)} total): {text}"


if __name__ == "__main__":
    mcp.run()
