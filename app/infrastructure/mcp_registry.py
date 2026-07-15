import sys
from dataclasses import dataclass, field
from pathlib import Path

_MCP_SERVERS_DIR = Path(__file__).resolve().parent.parent.parent / "mcp_servers"


@dataclass(frozen=True)
class McpServerConfig:
    name: str
    command: str
    args: list[str]
    # Which env vars this server's process needs injected at spawn time —
    # e.g. the graph server needs GRAPH_ACCESS_TOKEN, the notes server (or
    # any future tool with no external credential) needs none.
    env_keys: list[str] = field(default_factory=list)


def _server_script(filename: str) -> str:
    return str(_MCP_SERVERS_DIR / filename)


# Adding a new tool means adding an entry here — nothing in
# app/infrastructure/mcp_tool_provider.py or app/application/chat.py needs
# to change. See mcp_servers/notes_server.py for a trivial proof of this.
MCP_SERVER_REGISTRY: list[McpServerConfig] = [
    McpServerConfig(
        name="graph",
        command=sys.executable,
        args=[_server_script("graph_server.py")],
        env_keys=["GRAPH_ACCESS_TOKEN"],
    ),
    McpServerConfig(
        name="notes",
        command=sys.executable,
        args=[_server_script("notes_server.py")],
    ),
    McpServerConfig(
        name="docs",
        command=sys.executable,
        args=[_server_script("docs_server.py")],
        # Isolation, not credentials — every user's chunks live in the same
        # Azure AI Search index, filtered by user_oid at query time.
        env_keys=["USER_OID"],
    ),
]
