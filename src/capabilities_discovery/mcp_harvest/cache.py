from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from ..catalog import CatalogMcpServer
from ..settings import get_settings
from .config import all_server_configs
from .connect import harvest_servers

logger = logging.getLogger(__name__)

_CACHE_TTL = 12 * 3600  # seconds; MCP tool inventories shift rarely, so a soft half-day is plenty
_refresh_lock = threading.Lock()  # one background refresh per process at a time

_CACHE: TypeAdapter[list[CatalogMcpServer]] = TypeAdapter(list[CatalogMcpServer])


def read_mcp_cache(path: Path | None = None) -> list[CatalogMcpServer]:
    """Read the cached, tool-enriched MCP server cards.

    Args:
        path: Cache file to read; the settings' `mcp_cache` when None.

    Returns:
        The cached cards, or `[]` when there is no valid cache yet.
    """
    path = path if path is not None else get_settings().mcp_cache
    try:
        return _CACHE.validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return []


def write_mcp_cache(servers: list[CatalogMcpServer], path: Path | None = None) -> None:
    """Persist harvested server cards as the cache that recall reads.

    Written atomically (write a sibling temp file, then rename it over the destination) so a
    concurrent `read_mcp_cache` — e.g. `build_report` while a background refresh is writing —
    never observes a truncated file; it sees either the old cache or the new one, never neither.

    Args:
        servers: The cards to write.
        path: Destination cache file; parent dirs are created. The settings' `mcp_cache`
            when None.
    """
    path = path if path is not None else get_settings().mcp_cache
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(_CACHE.dump_json(servers, indent=2).decode(), encoding="utf-8")
    tmp.replace(path)


def refresh_mcp_cache(
    plugins_root: Path | None = None,
    path: Path | None = None,
    project_dir: Path | None = None,
    claude_json: Path | None = None,
    oauth: bool = False,
) -> list[CatalogMcpServer]:
    """Harvest every MCP server across scopes and write the cache.

    The impure refresh step: network and process spawning live here, never on the recall path.
    A server's config (including any secrets in `env`) is used only to spawn it; only tool names,
    descriptions, and parameters are cached.

    Args:
        plugins_root: Root of installed plugins; the settings' `plugins_root` when None.
        path: Cache file to write; the settings' `mcp_cache` when None.
        project_dir: Project root for project/local scope; the cwd when None.
        claude_json: Path to `~/.claude.json`; the settings' `claude_json` when None.
        oauth: Allow the interactive OAuth flow for HTTP servers with a pre-registered client.
            Leave False on any background or hook path — it may open a browser.

    Returns:
        The freshly harvested cards (also written to `path`).
    """
    plugins_root = plugins_root if plugins_root is not None else get_settings().plugins_root
    claude_json = claude_json if claude_json is not None else get_settings().claude_json
    configs = all_server_configs(plugins_root, project_dir or Path.cwd(), claude_json)
    cards = asyncio.run(harvest_servers(configs, oauth))
    write_mcp_cache(cards, path)
    return cards


def cache_is_stale(path: Path | None = None, ttl_seconds: float = _CACHE_TTL) -> bool:
    """Report whether the cache is due for a refresh.

    Args:
        path: Cache file to check; the settings' `mcp_cache` when None.
        ttl_seconds: Maximum age before the cache is considered stale. Defaults to `_CACHE_TTL`.

    Returns:
        True if the cache is missing or older than `ttl_seconds`.
    """
    path = path if path is not None else get_settings().mcp_cache
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return True
    return age > ttl_seconds


def refresh_in_background(
    plugins_root: Path | None = None,
    path: Path | None = None,
    project_dir: Path | None = None,
    claude_json: Path | None = None,
) -> threading.Thread | None:
    """Run a one-shot cache refresh in a daemon thread and return immediately.

    The harvest spawns MCP servers and does network I/O, so it must never run on the recall path;
    this is how callers trigger it off that path. Best-effort: any failure is logged and swallowed,
    never surfaced to the recall caller.

    Args:
        plugins_root: Root of installed plugins; the settings' `plugins_root` when None.
        path: Cache file to write; the settings' `mcp_cache` when None.
        project_dir: Project root for project/local scope; the cwd when None.
        claude_json: Path to `~/.claude.json`; the settings' `claude_json` when None.

    Returns:
        The started daemon thread, or None if a refresh is already running in this process.
    """
    if not _refresh_lock.acquire(blocking=False):
        return None

    def _run() -> None:
        try:
            refresh_mcp_cache(plugins_root, path, project_dir, claude_json)
        except Exception:
            logger.exception("background MCP cache refresh failed")
        finally:
            _refresh_lock.release()

    thread = threading.Thread(target=_run, name="mcp-cache-refresh", daemon=True)
    thread.start()
    return thread
