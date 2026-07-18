from __future__ import annotations

from typing import Annotated

from pydantic import Field, JsonValue

ServerConfig = Annotated[
    dict[str, JsonValue],
    Field(
        title="MCP server config",
        description=(
            "One server's spawn config (command/args/env, or url), passed straight to the MCP "
            "client — an opaque mapping; its shape is the client's concern, not ours."
        ),
        examples=[{"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]}],
    ),
]
ServerMap = Annotated[
    dict[str, ServerConfig],
    Field(
        title="MCP server map",
        description=(
            "`{server_name: config}`, as found in a `.mcp.json` or a manifest's `mcpServers`."
        ),
        examples=[
            {"github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"]}}
        ],
    ),
]
