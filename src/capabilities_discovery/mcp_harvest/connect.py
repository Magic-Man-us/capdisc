from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastmcp import Client
from fastmcp.client.auth import OAuth
from pydantic import TypeAdapter, ValidationError

from ..catalog import (
    MCP_TOOL_DESCRIPTION_MAX,
    CatalogMcpServer,
    McpInputSchema,
    McpServerRef,
    McpTool,
    McpToolName,
    catalog_id,
)
from .auth import server_auth
from .config import scalar_str
from .types import ServerConfig

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 30.0
_OAUTH_TIMEOUT = 300.0  # interactive: covers the browser round-trip on first authorization

_MAX_CONCURRENT_HARVESTS = 8  # bounds simultaneous connects/spawns; also caps concurrent oauth

_SERVER_REF: TypeAdapter[McpServerRef] = TypeAdapter(McpServerRef)
_TOOL_PARAM_NAME: TypeAdapter[McpToolName] = TypeAdapter(McpToolName)


def _is_valid_param_name(name: str) -> bool:
    """Whether `name` validates as an `McpToolName` — the same constraint a tool's own name
    must satisfy, reused here so the two can never drift apart."""
    try:
        _TOOL_PARAM_NAME.validate_python(name)
    except ValidationError:
        return False
    return True


def to_mcp_tool(
    name: str, description: str | None, input_schema: McpInputSchema | None
) -> McpTool | None:
    """Convert one harvested tool into an `McpTool`.

    Args:
        name: The tool's name; the whole tool is dropped if it will not validate as one.
        description: The tool's description; None becomes empty, then truncated to
            `MCP_TOOL_DESCRIPTION_MAX`.
        input_schema: The tool's JSON input schema; its `properties` keys become param names.
            Params whose names don't validate are dropped individually (one odd param shouldn't
            lose the whole tool).

    Returns:
        The `McpTool`, or None if the name will not validate.
    """
    props = (input_schema or {}).get("properties", {})
    names = list(props) if isinstance(props, dict) else []
    params = [p for p in names if _is_valid_param_name(p)]
    try:
        return McpTool(
            name=name,
            description=(description or "")[:MCP_TOOL_DESCRIPTION_MAX],
            params=params,
            input_schema=input_schema,
        )
    except ValidationError:
        return None


async def harvest_one(
    name: str, config: ServerConfig, auth: str | OAuth | None = None
) -> list[McpTool]:
    """Connect to one server and list its tools.

    Args:
        name: The server name, used as the single key of the spawned client config.
        config: The server's spawn config (command/args/env or url), passed to the MCP client.
        auth: Bearer token or OAuth handler for an HTTP server; None connects as configured.

    Returns:
        The server's tools as `McpTool`s, dropping any that fail to validate.

    Raises:
        Exception: Any connect or list-tools failure propagates; the caller skips the server.
    """
    client: Client[Any]  # Any: the two branches infer different transport generics, same API
    url = scalar_str(config.get("url")) if auth is not None else None
    if auth is not None and url is not None:
        client = Client(url, auth=auth)
    else:
        client = Client({"mcpServers": {name: config}})
    async with client:
        raw_tools = await client.list_tools()
    harvested = (to_mcp_tool(t.name, t.description, t.inputSchema) for t in raw_tools)
    return [tool for tool in harvested if tool is not None]


def _dedupe_first_wins(
    configs: list[tuple[str, ServerConfig]],
) -> list[tuple[McpServerRef, str, ServerConfig]]:
    """Resolve each entry's ref and drop repeats, keeping the first occurrence of each ref.

    Done up front, before any concurrent connect, so which config wins a collision depends only
    on input order — never on which connection happens to finish first.

    Args:
        configs: `(name, config)` pairs; a name that fails `McpServerRef` validation is dropped.

    Returns:
        `(ref, name, config)` triples, one per distinct ref, first occurrence kept.
    """
    seen: set[McpServerRef] = set()
    out: list[tuple[McpServerRef, str, ServerConfig]] = []
    for name, config in configs:
        try:
            ref = _SERVER_REF.validate_python(name)
        except ValidationError:
            continue
        if ref in seen:
            continue
        seen.add(ref)
        out.append((ref, name, config))
    return out


async def _harvest_card(
    ref: McpServerRef,
    name: str,
    config: ServerConfig,
    oauth: bool,
    limit: asyncio.Semaphore,
) -> CatalogMcpServer | None:
    """Connect to one server, bounded by `limit`, and build its card — or None on any failure.

    Args:
        ref: The server's validated, deduplicated ref.
        name: The server's raw name/ref as configured, used to spawn the client.
        config: The server's spawn config (command/args/env or url).
        oauth: Allow the interactive OAuth flow for HTTP servers with a pre-registered client.
        limit: Bounds how many servers connect at once (process spawns, network connects,
            and any interactive OAuth browser flow all count against it).

    Returns:
        The harvested card, or None if the server failed to connect or list tools within its
        timeout. The failure reason is logged by type only — never the exception's message,
        which for an authenticated server could otherwise leak a token or credential-bearing URL.
    """
    async with limit:
        try:
            auth = server_auth(name, config, oauth)
            timeout = _OAUTH_TIMEOUT if isinstance(auth, OAuth) else _CONNECT_TIMEOUT
            tools = await asyncio.wait_for(harvest_one(name, config, auth), timeout=timeout)
        except Exception as exc:
            logger.warning("skipped MCP server %s: %s", name, type(exc).__name__)
            return None
    return CatalogMcpServer(
        id=catalog_id("mcp", ref), ref=ref, description=f"MCP server: {name}", tools=tools
    )


async def harvest_servers(
    configs: list[tuple[str, ServerConfig]], oauth: bool = False
) -> list[CatalogMcpServer]:
    """Connect to every server concurrently (bounded) and build its harvested card.

    Args:
        configs: `(ref, config)` pairs to connect to; refs that don't validate or repeat are
            skipped, so the first occurrence of each server wins.
        oauth: Allow the interactive OAuth flow for HTTP servers with a pre-registered client.

    Returns:
        One `CatalogMcpServer` per reachable, distinct server, in input order. Any server that
        fails to connect or list tools within its timeout is skipped. Servers connect up to
        `_MAX_CONCURRENT_HARVESTS` at a time, so N servers no longer cost N times a single
        server's timeout.
    """
    limit = asyncio.Semaphore(_MAX_CONCURRENT_HARVESTS)
    unique = _dedupe_first_wins(configs)
    cards = await asyncio.gather(
        *(_harvest_card(ref, name, config, oauth, limit) for ref, name, config in unique)
    )
    return [card for card in cards if card is not None]
