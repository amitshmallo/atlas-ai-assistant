from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.domain.entities import ToolCallRequest
from app.infrastructure.mcp_registry import MCP_SERVER_REGISTRY, McpServerConfig
from app.infrastructure.telemetry import inject_trace_context


class UnknownToolError(Exception):
    pass


class McpToolProvider:
    """Concrete domain.ToolProvider implementation: talks to MCP servers
    over stdio instead of importing tool code directly. application only
    ever calls get_tool_specs()/execute_tool() — it has no idea Graph,
    Azure AI Search, or any external process, is involved.

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
        self, server: McpServerConfig, context: dict[str, str]
    ) -> AsyncIterator[ClientSession]:
        env = {key: context[key] for key in server.env_keys if key in context}
        # Every server gets the current trace context, regardless of
        # env_keys — this is what makes a chat turn's tool call show up as
        # one connected distributed trace in Application Insights instead
        # of an orphaned span in the subprocess.
        trace_context = inject_trace_context()
        if "traceparent" in trace_context:
            env["TRACEPARENT"] = trace_context["traceparent"]
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
            async with self._session(server, context={}) as session:
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

    async def execute_tool(self, tool_call: ToolCallRequest, context: dict[str, str]) -> str:
        if not self._tool_to_server:
            await self.get_tool_specs()

        server = self._tool_to_server.get(tool_call.name)
        if server is None:
            raise UnknownToolError(tool_call.name)

        async with self._session(server, context=context) as session:
            result = await session.call_tool(tool_call.name, tool_call.arguments)
            text_parts = [block.text for block in result.content if hasattr(block, "text")]
            return "\n".join(text_parts) if text_parts else "{}"
