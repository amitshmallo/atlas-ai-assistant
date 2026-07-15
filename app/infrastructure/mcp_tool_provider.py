from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.domain.entities import ToolCallRequest
from app.infrastructure.mcp_registry import MCP_SERVER_REGISTRY, McpServerConfig


class UnknownToolError(Exception):
    pass


class McpToolProvider:
    """Concrete domain.ToolProvider implementation: talks to MCP servers
    over stdio instead of importing tool code directly. application only
    ever calls get_tool_specs()/execute_tool() — it has no idea Graph, or
    any external process, is involved.

    Each call spawns a fresh subprocess for whichever server owns the tool
    being discovered/executed. That's a deliberate simplicity-over-performance
    tradeoff for this phase — a persistent per-session server pool would be
    a reasonable Phase 10-style hardening step, not needed to prove the
    architecture works.
    """

    def __init__(self, registry: list[McpServerConfig] | None = None) -> None:
        self._registry = registry if registry is not None else MCP_SERVER_REGISTRY
        self._tool_to_server: dict[str, McpServerConfig] = {}
        self._cached_specs: list[dict[str, Any]] | None = None

    @asynccontextmanager
    async def _session(
        self, server: McpServerConfig, graph_access_token: str | None
    ) -> AsyncIterator[ClientSession]:
        env = {key: graph_access_token for key in server.env_keys if graph_access_token}
        params = StdioServerParameters(command=server.command, args=server.args, env=env or None)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    async def get_tool_specs(self) -> list[dict[str, Any]]:
        if self._cached_specs is not None:
            return self._cached_specs

        specs: list[dict[str, Any]] = []
        for server in self._registry:
            async with self._session(server, graph_access_token=None) as session:
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    self._tool_to_server[tool.name] = server
                    specs.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description or "",
                                "parameters": tool.inputSchema,
                            },
                        }
                    )

        self._cached_specs = specs
        return specs

    async def execute_tool(self, tool_call: ToolCallRequest, graph_access_token: str) -> str:
        if not self._tool_to_server:
            await self.get_tool_specs()

        server = self._tool_to_server.get(tool_call.name)
        if server is None:
            raise UnknownToolError(tool_call.name)

        async with self._session(server, graph_access_token=graph_access_token) as session:
            result = await session.call_tool(tool_call.name, tool_call.arguments)
            text_parts = [block.text for block in result.content if hasattr(block, "text")]
            return "\n".join(text_parts) if text_parts else "{}"
