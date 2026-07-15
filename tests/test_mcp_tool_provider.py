"""Integration test: spawns the real notes_server.py subprocess over real
stdio transport and drives it through McpToolProvider. Deliberately uses
the trivial notes server (no Graph credentials needed) rather than the
graph server, so this proves the MCP protocol/transport plumbing works
without depending on any live Azure/Graph access.
"""

import sys
from pathlib import Path

import pytest

from app.domain.entities import ToolCallRequest
from app.infrastructure.mcp_registry import McpServerConfig
from app.infrastructure.mcp_tool_provider import McpToolProvider, UnknownToolError

_MCP_SERVERS_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"

_NOTES_ONLY_REGISTRY = [
    McpServerConfig(
        name="notes",
        command=sys.executable,
        args=[str(_MCP_SERVERS_DIR / "notes_server.py")],
    )
]


async def test_get_tool_specs_discovers_real_subprocess_tool():
    provider = McpToolProvider(registry=_NOTES_ONLY_REGISTRY)

    specs = await provider.get_tool_specs()

    names = [spec["function"]["name"] for spec in specs]
    assert "remember_note" in names


async def test_execute_tool_calls_real_subprocess():
    provider = McpToolProvider(registry=_NOTES_ONLY_REGISTRY)
    await provider.get_tool_specs()

    tool_call = ToolCallRequest(id="call-1", name="remember_note", arguments={"text": "buy milk"})
    result = await provider.execute_tool(tool_call, context={})

    assert "buy milk" in result


async def test_execute_tool_raises_for_unknown_tool_name():
    provider = McpToolProvider(registry=_NOTES_ONLY_REGISTRY)
    await provider.get_tool_specs()

    tool_call = ToolCallRequest(id="call-1", name="not_a_real_tool", arguments={})

    with pytest.raises(UnknownToolError):
        await provider.execute_tool(tool_call, context={})
