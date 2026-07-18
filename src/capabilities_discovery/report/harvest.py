"""The impure harvest: scans this machine into an `EnvironmentReport` and persists it."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from ..catalog import CatalogMcpServer
from ..discovery import BUILTIN_TOOLS, scan_indexed_skills
from ..mcp_catalog import enumerate_mcp_servers
from ..mcp_harvest import cache_is_stale, read_mcp_cache, refresh_mcp_cache
from ..plugin_catalog import enumerate_plugins_with_paths, installed_plugin_dirs
from ..scope import ScopeInventory, ScopeRoots, default_managed_dir
from ..settings import get_settings
from .models import EnvironmentReport, IndexedPlugin, IndexedSkill, McpSource
from .page import render_environment_html

logger = logging.getLogger(__name__)

REPORT_JSON_NAME = "discovery-report.json"
REPORT_HTML_NAME = "discovery-report.html"

_MCP_SOURCE_CACHE: McpSource = "tool-enriched cache"
_MCP_SOURCE_FRESH: McpSource = "fresh harvest"
_MCP_SOURCE_STALE: McpSource = "stale cache (refresh failed)"
_MCP_SOURCE_LIVE: McpSource = "live (claude mcp list)"


def _harvest_mcp_servers(oauth: bool = False) -> tuple[list[CatalogMcpServer], McpSource]:
    """Return the MCP server cards and the source they came from.

    Fresh cache → use it. Stale or missing cache → synchronous refresh (this runs in a
    short-lived CLI process, so a background thread would die before finishing). Refresh
    failure → the stale cache if any, else the unenriched live listing. `oauth` always
    refreshes — the point of passing it is to reach servers the cached run could not.
    """
    cached = read_mcp_cache()
    if cached and not cache_is_stale() and not oauth:
        return cached, _MCP_SOURCE_CACHE
    try:
        return refresh_mcp_cache(oauth=oauth), _MCP_SOURCE_FRESH
    except Exception:
        logger.exception("MCP cache refresh failed")
    if cached:
        return cached, _MCP_SOURCE_STALE
    return enumerate_mcp_servers(), _MCP_SOURCE_LIVE


def build_report(oauth: bool = False) -> EnvironmentReport:
    """Scan this machine's discovery surface into one `EnvironmentReport`.

    Runs exactly what the runtime runs — scope discovery, the disk inventory, the skill index,
    the built-in tools, the plugin catalog, and the MCP harvest (cache first, live fallback).

    Args:
        oauth: Allow the interactive OAuth flow for HTTP MCP servers with a pre-registered
            client (settings `mcp_oauth_clients`); forces a fresh harvest. Never set this on
            a background path — it may open a browser.

    Returns:
        The gathered harvest, ready to render or persist.
    """
    cwd = Path.cwd()
    home = Path.home()
    managed_dir = default_managed_dir()
    plugins_root = get_settings().plugins_root
    plugin_dirs = installed_plugin_dirs(plugins_root)
    roots = ScopeRoots.discover(
        start=cwd,
        home_dir=home,
        managed_dir=managed_dir,
        plugin_dirs=plugin_dirs,
    )
    inventory = ScopeInventory.scan(roots)
    skills = [IndexedSkill(card=card, path=path) for card, path in scan_indexed_skills(roots)]
    plugins = [
        IndexedPlugin(card=card, path=path)
        for card, path in enumerate_plugins_with_paths(plugins_root)
    ]
    mcp_servers, mcp_source = _harvest_mcp_servers(oauth)
    return EnvironmentReport(
        generated_at=datetime.now(UTC),
        cwd=cwd,
        home=home,
        plugins_root=plugins_root,
        managed_dir=managed_dir,
        mcp_source=mcp_source,
        scan_roots=roots.roots,
        plugin_dirs=plugin_dirs,
        inventory=inventory,
        skills=skills,
        builtin_tools=BUILTIN_TOOLS,
        plugins=plugins,
        mcp_servers=mcp_servers,
    )


def write_report(
    report: EnvironmentReport,
    *,
    json_path: Path | None = None,
    html_path: Path | None = None,
) -> None:
    """Persist a report as both its JSON snapshot and its rendered HTML.

    Args:
        report: The report to persist.
        json_path: Destination for the machine-readable snapshot; parent dirs are created.
            Under the settings' `report_dir` when None.
        html_path: Destination for the rendered document; parent dirs are created.
            Under the settings' `report_dir` when None.
    """
    json_path = (
        json_path if json_path is not None else get_settings().report_dir / REPORT_JSON_NAME
    )
    html_path = (
        html_path if html_path is not None else get_settings().report_dir / REPORT_HTML_NAME
    )
    # The report can embed raw scanned file contents (e.g. a hook's command string), so its
    # directory is kept private the same way mcp_harvest.auth.ensure_private_dir locks down
    # the OAuth token store — mkdir(mode=...) alone only applies to a dir it newly creates.
    for parent in {json_path.parent, html_path.parent}:
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent.chmod(0o700)
    json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    html_path.write_text(render_environment_html(report), encoding="utf-8")


def write_report_on_start() -> EnvironmentReport | None:
    """Build and persist the discovery report to the default paths, best-effort.

    Called from always-on startup paths, so it never raises or blocks — any failure is logged and
    swallowed. Local writes only; no network, no threads.

    Returns:
        The built report (so a caller can also stash it, e.g. to serve it), or None when the build
        failed. A write failure is logged but does not affect the return value — the report is
        still returned so a caller can serve it even when the on-disk copy is stale or missing.
    """
    try:
        report = build_report()
    except Exception:
        logger.exception("discovery report generation failed")
        return None
    try:
        write_report(report)
    except Exception:
        logger.exception("discovery report write failed")
    return report
