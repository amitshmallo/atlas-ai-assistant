"""Standalone MCP server exposing a single write tool for durable user
preferences. Reading preferences is deliberately NOT a tool here — that
would require the model to remember to call it, and a brand-new
conversation would have no reason to. Instead SendChatMessageUseCase loads
preferences directly via PreferenceRepository and injects them into the
system prompt on every turn (see app/application/chat.py). This server
only handles the write side: the model deciding a preference is worth
remembering.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from app.infrastructure.database import async_session_factory  # noqa: E402
from app.infrastructure.preference_repository import SqlAlchemyPreferenceRepository  # noqa: E402
from app.infrastructure.telemetry import configure_telemetry, traced_subprocess_span  # noqa: E402

configure_telemetry(service_name="atlas-mcp-memory")

mcp = FastMCP("memory")


def _user_oid() -> str:
    oid = os.environ.get("USER_OID")
    if not oid:
        raise RuntimeError("USER_OID was not set for this MCP server process")
    return oid


async def _set_preference(user_oid: str, key: str, value: str) -> None:
    async with async_session_factory() as session:
        repository = SqlAlchemyPreferenceRepository(session)
        await repository.set_preference(user_oid, key, value)


@mcp.tool()
async def remember_preference(key: str, value: str) -> str:
    """Remember a durable user preference or fact that should influence
    behavior in this AND future conversations — not just this message.
    Use a short snake_case key, e.g. key="reply_style", value="concise"."""
    with traced_subprocess_span("atlas-mcp-memory", "remember_preference"):
        await _set_preference(_user_oid(), key, value)
        return f"Remembered: {key} = {value}"


if __name__ == "__main__":
    mcp.run()
