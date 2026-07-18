"""Discovery of Claude Code capabilities: skills, agents, plugins, MCP servers, hooks.

Scans the environment's scope roots into a typed inventory, harvests plugin and MCP
metadata, and assembles capability catalogs and the environment report.
"""

from __future__ import annotations

from .catalog import (
    Catalog,
    CatalogEntry,
    CatalogMcpServer,
    CatalogPlugin,
    CatalogSkill,
    CatalogTool,
    McpTool,
)
from .discovery import BUILTIN_TOOLS, scan_environment, scan_indexed_skills, scan_skills
from .mcp_catalog import enumerate_mcp_servers
from .mcp_harvest import (
    cache_is_stale,
    read_mcp_cache,
    refresh_in_background,
    refresh_mcp_cache,
    write_mcp_cache,
)
from .plugin_catalog import (
    enumerate_plugins,
    enumerate_plugins_with_paths,
    installed_plugin_dirs,
    installed_plugins,
)
from .report import EnvironmentReport, build_report, write_report, write_report_on_start
from .scope import ScopeInventory, ScopeRoots, default_managed_dir
from .settings import DiscoverySettings, ExtraSourceDir, get_settings

__all__ = [
    "BUILTIN_TOOLS",
    "Catalog",
    "CatalogEntry",
    "CatalogMcpServer",
    "CatalogPlugin",
    "CatalogSkill",
    "CatalogTool",
    "DiscoverySettings",
    "EnvironmentReport",
    "ExtraSourceDir",
    "McpTool",
    "ScopeInventory",
    "ScopeRoots",
    "build_report",
    "cache_is_stale",
    "default_managed_dir",
    "enumerate_mcp_servers",
    "enumerate_plugins",
    "enumerate_plugins_with_paths",
    "get_settings",
    "installed_plugin_dirs",
    "installed_plugins",
    "read_mcp_cache",
    "refresh_in_background",
    "refresh_mcp_cache",
    "scan_environment",
    "scan_indexed_skills",
    "scan_skills",
    "write_mcp_cache",
    "write_report",
    "write_report_on_start",
]
