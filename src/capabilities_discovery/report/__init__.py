"""Render the full discovery harvest of this machine as one self-contained HTML document.

A developer tool for eyeballing what the discovery layer aggregates — scan roots, the on-disk
scope inventory, indexed skills, built-in tools, installed plugins, and connected MCP servers —
not a product feature. `build_report` scans the machine into an `EnvironmentReport` (the
machine-readable snapshot, which round-trips through Pydantic JSON); `render_environment_html`
renders that snapshot to HTML. `write_report` persists both; `python -m
capabilities_discovery.report` writes them to the default paths.

All markup is built here in Python and every dynamic value is escaped; the inline JS only toggles
classes and `style.display` and reads input values, so the page renders untrusted paths and file
contents safely.
"""

from __future__ import annotations

from .cli import main
from .components import ComponentGroup, PluginComponents, plugin_components
from .harvest import build_report, write_report, write_report_on_start
from .models import EnvironmentReport, IndexedPlugin, IndexedSkill, McpSource
from .page import render_environment_html

__all__ = [
    "ComponentGroup",
    "EnvironmentReport",
    "IndexedPlugin",
    "IndexedSkill",
    "McpSource",
    "PluginComponents",
    "build_report",
    "main",
    "plugin_components",
    "render_environment_html",
    "write_report",
    "write_report_on_start",
]
