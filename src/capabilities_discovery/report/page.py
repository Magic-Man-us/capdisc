"""Page assembly: sections into tabs, tabs into one self-contained HTML document."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..base import FrozenModel
from ..html import e, redact_home
from .assets import SCRIPT, STYLE
from .models import EnvironmentReport
from .sections import (
    render_inventory_section,
    render_mcp_section,
    render_overview_section,
    render_plugins_section,
    render_roots_section,
    render_skills_section,
    render_tools_section,
)
from .types import SectionCount, SectionId, SectionLabel


class _Section(FrozenModel):
    """One tab: its nav id and label, the rendered body, an optional count, and whether it gets a
    client-side filter box (the overview does not)."""

    id: SectionId
    label: SectionLabel
    body: str
    count: SectionCount | None = None
    searchable: bool = True


def _nav_button(section: _Section) -> str:
    count = "" if section.count is None else str(section.count)
    return (
        f'<button data-v="{e(section.id)}">{e(section.label)}'
        f'<span class="cnt">{e(count)}</span></button>'
    )


def _section_html(section: _Section) -> str:
    search = (
        f'<input class="search" placeholder="filter {e(section.label.lower())}…">'
        if section.searchable
        else ""
    )
    return f'<section class="section" id="sec-{e(section.id)}">{search}{section.body}</section>'


def _page(sections: list[_Section], generated: datetime, cwd: Path) -> str:
    nav = "".join(_nav_button(s) for s in sections)
    main = "".join(_section_html(s) for s in sections)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>capabilities-discovery · discovery report</title>"
        f"<style>{STYLE}</style></head><body>"
        "<header><h1>capabilities-discovery · discovery report</h1>"
        '<div class="meta">what the engine harvests from this machine · generated '
        f"<b>{e(generated.isoformat(timespec='seconds'))}</b> · "
        f"<b>{e(redact_home(cwd))}</b></div></header>"
        f'<div class="layout"><nav>{nav}</nav><main>{main}</main></div>'
        '<div id="backdrop"></div>'
        '<div id="drawer"><div class="dhead"><span class="dtitle"></span>'
        '<button class="dclose" aria-label="close">&times;</button></div>'
        '<div class="dbody"></div></div>'
        f"<script>{SCRIPT}</script></body></html>"
    )


def render_environment_html(report: EnvironmentReport) -> str:
    """Render an `EnvironmentReport` as one self-contained HTML document.

    Pure over the snapshot: every dynamic value comes from `report` and is escaped. Existence of
    each scan root is read from disk as it is rendered.

    Args:
        report: The gathered harvest, as produced by `build_report`.

    Returns:
        A complete `<!doctype html>` page with inline styles and script and no external resources.
    """
    sections = [
        _Section(
            id="overview",
            label="Overview",
            body=render_overview_section(report),
            searchable=False,
        ),
        _Section(
            id="roots",
            label="Scan roots",
            body=render_roots_section(report.scan_roots, report.plugin_dirs),
            count=report.scan_root_count,
        ),
        _Section(
            id="inventory",
            label="Disk inventory",
            body=render_inventory_section(report.inventory),
            count=report.capture_count,
        ),
        _Section(
            id="skills",
            label="Skills",
            body=render_skills_section(report.skills),
            count=report.skill_count,
        ),
        _Section(
            id="tools",
            label="Builtin tools",
            body=render_tools_section(report.builtin_tools),
            count=report.tool_count,
        ),
        _Section(
            id="plugins",
            label="Plugins",
            body=render_plugins_section(report.plugins, report.inventory, report.mcp_servers),
            count=report.plugin_count,
        ),
        _Section(
            id="mcp",
            label="MCP servers",
            body=render_mcp_section(report.mcp_servers),
            count=report.mcp_server_count,
        ),
    ]
    return _page(sections, report.generated_at, report.cwd)
