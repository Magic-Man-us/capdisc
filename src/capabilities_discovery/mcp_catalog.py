from __future__ import annotations

import subprocess
from typing import Any

from pydantic import TypeAdapter, ValidationError, model_validator

from .base import InputModel
from .catalog import CatalogMcpServer, McpServerRef, catalog_id

_MCP_LIST = ("claude", "mcp", "list")
SERVER_REF: TypeAdapter[McpServerRef] = TypeAdapter(
    McpServerRef
)  # the one place a server name becomes a ref


class _ConnectedServerLine(InputModel):
    """One `claude mcp list` line, kept only when it names a `Connected` server. The
    command/URL after the name (which can carry credentials) is split off and never modeled."""

    name: str

    @model_validator(mode="before")
    @classmethod
    def _parse_line(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data
        if ": " not in data or " - " not in data:
            raise ValueError("not a 'name: command - status' line")
        if "Connected" not in data.rsplit(" - ", 1)[-1]:
            raise ValueError("server is not Connected")
        return {"name": data.split(": ", 1)[0].strip()}


def parse_mcp_servers(list_output: str) -> list[CatalogMcpServer]:
    """Parse `claude mcp list` output into cards for the connected servers.

    Only the server name is kept; the command/URL after it (which can carry credentials) is
    split off and never indexed. The MCP config file is never read.

    Args:
        list_output: The stdout of `claude mcp list`.

    Returns:
        One card per distinct connected server (de-duplicated by id), skipping disconnected
        lines and names that don't validate.
    """
    servers: list[CatalogMcpServer] = []
    seen: set[str] = set()
    for line in list_output.splitlines():
        try:
            name = _ConnectedServerLine.model_validate(line).name
        except ValidationError:
            continue
        try:
            ref = SERVER_REF.validate_python(name)
        except ValidationError:
            continue
        try:
            card = CatalogMcpServer(
                id=catalog_id("mcp", ref), ref=ref, description=f"MCP server: {name}"
            )
        except ValidationError:
            continue
        # dedupe by id, not ref: two distinct refs can still truncate to the same catalog_id
        if card.id in seen:
            continue
        seen.add(card.id)
        servers.append(card)
    return servers


def enumerate_mcp_servers() -> list[CatalogMcpServer]:
    """Enumerate connected MCP servers by running `claude mcp list`.

    Spawned as an argv array (no shell); the config file is never touched.

    Returns:
        The connected server cards, or `[]` if the CLI is missing, times out, or errors.
    """
    try:
        result = subprocess.run(  # noqa: S603 — fixed argv tuple, no shell, no untrusted input
            _MCP_LIST, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_mcp_servers(result.stdout)
