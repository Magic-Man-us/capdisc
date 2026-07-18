from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from capabilities_discovery.catalog import (
    CatalogMcpServer,
    CatalogPlugin,
    CatalogSkill,
    CatalogTool,
    McpTool,
)
from capabilities_discovery.report import (
    EnvironmentReport,
    IndexedPlugin,
    IndexedSkill,
    plugin_components,
    render_environment_html,
    write_report,
)
from capabilities_discovery.scope import ScopeInventory, ScopeRoots
from helpers import touch

_SKILL_REF = "sample-skill"
_TOOL_REF = "Read"
_SERVER_REF = "playwright"
_TOOL_NAME = "browser_navigate"
_PLUGIN_REF = "sample_plugin"
_INJECTION = "<script>evil()</script>"


def _synthetic_report(tmp_path: Path) -> EnvironmentReport:
    (tmp_path / ".git").mkdir()
    touch(tmp_path / ".claude" / "agents" / "reviewer.md", "agent body")
    roots = ScopeRoots.discover(start=tmp_path)
    inventory = ScopeInventory.scan(roots)

    skill = CatalogSkill(
        id="skill.sample",
        ref=_SKILL_REF,
        description=f"{_INJECTION} a sample skill for testing the discovery report.",
        tags=["sample"],
    )
    tool = CatalogTool(id="builtin.read", ref=_TOOL_REF, description="Read a file from disk.")
    server = CatalogMcpServer(
        id="mcp.playwright",
        ref=_SERVER_REF,
        description="MCP server: playwright browser automation.",
        tools=[McpTool(name=_TOOL_NAME, description="Navigate the browser.", params=["url"])],
    )
    plugin = CatalogPlugin(
        id="plugin.sample",
        ref=_PLUGIN_REF,
        description="A sample bundled plugin.",
        skills=[_SKILL_REF],
        mcp_servers=[_SERVER_REF],
    )
    return EnvironmentReport(
        generated_at=datetime.now(UTC),
        cwd=tmp_path,
        home=tmp_path,
        plugins_root=tmp_path / ".claude" / "plugins",
        managed_dir=None,
        mcp_source="tool-enriched cache",
        scan_roots=roots.roots,
        plugin_dirs=[],
        inventory=inventory,
        skills=[IndexedSkill(card=skill, path=tmp_path / "SKILL.md")],
        builtin_tools=[tool],
        plugins=[IndexedPlugin(card=plugin, path=tmp_path / "plug")],
        mcp_servers=[server],
    )


def test_report_is_self_contained_document(tmp_path: Path) -> None:
    html = render_environment_html(_synthetic_report(tmp_path))
    assert html.startswith("<!doctype html>")
    assert "innerHTML" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_report_renders_every_harvest_kind(tmp_path: Path) -> None:
    html = render_environment_html(_synthetic_report(tmp_path))
    assert _SKILL_REF in html
    assert _TOOL_REF in html
    assert _SERVER_REF in html
    assert _TOOL_NAME in html
    assert _PLUGIN_REF in html
    assert "reviewer" in html  # the captured agent from the disk inventory


def test_report_escapes_injected_markup(tmp_path: Path) -> None:
    html = render_environment_html(_synthetic_report(tmp_path))
    assert "&lt;script&gt;evil()" in html
    assert _INJECTION not in html


def test_report_redacts_home_directory_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    html = render_environment_html(_synthetic_report(tmp_path))
    assert str(tmp_path) not in html
    assert "~" in html


def test_report_round_trips_through_json(tmp_path: Path) -> None:
    report = _synthetic_report(tmp_path)
    restored = EnvironmentReport.model_validate_json(report.model_dump_json())
    assert restored == report


def test_write_report_creates_both_files(tmp_path: Path) -> None:
    report = _synthetic_report(tmp_path)
    json_path = tmp_path / "out" / "discovery-report.json"
    html_path = tmp_path / "out" / "discovery-report.html"
    write_report(report, json_path=json_path, html_path=html_path)

    assert json_path.exists()
    assert html_path.exists()
    assert html_path.read_text(encoding="utf-8").startswith("<!doctype html>")
    assert EnvironmentReport.model_validate_json(json_path.read_text(encoding="utf-8")) == report


def _plugin_install(tmp_path: Path) -> Path:
    """A synthetic plugin install dir bundling one of each captured kind."""
    install = tmp_path / "plug"
    agent_md = "---\nname: rev\ndescription: a review agent\n---\nbody"
    skill_md = "---\nname: foo\ndescription: a foo skill\n---\nbody"
    command_md = "---\ndescription: a bar command\n---\nbody"
    hooks_json = '{"Stop":[{"hooks":[{"type":"command","command":"x"}]}]}'
    touch(install / "agents" / "rev.md", agent_md)
    touch(install / "skills" / "foo" / "SKILL.md", skill_md)
    touch(install / "commands" / "bar.md", command_md)
    touch(install / "hooks" / "hooks.json", hooks_json)
    return install


def test_plugin_components_groups_and_costs(tmp_path: Path) -> None:
    install = _plugin_install(tmp_path)
    inventory = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path, plugin_dirs=[install]))
    plugin = CatalogPlugin(
        id="plugin.p", ref="p", description="a plugin", mcp_servers=[_SERVER_REF]
    )
    server = CatalogMcpServer(
        id="mcp.playwright",
        ref=_SERVER_REF,
        description="MCP server: playwright.",
        tools=[McpTool(name=_TOOL_NAME, description="Navigate.", params=["url"])],
    )
    components = plugin_components(IndexedPlugin(card=plugin, path=install), inventory, [server])
    groups = {group.name: group for group in components.groups}

    assert groups["Skills"].count == 2  # skills/ + commands/ fold into Skills
    assert groups["Agents"].count == 1
    assert groups["Hooks"].count == 1
    assert groups["MCP servers"].count == 1
    assert groups["Hooks"].always_on_tokens == 0  # a hooks.json has no frontmatter description
    assert groups["Hooks"].on_demand_tokens > 0
    assert groups["Agents"].always_on_tokens > 0  # its frontmatter description loads every session
    assert components.total_always_on == sum(g.always_on_tokens for g in components.groups)
    assert components.total_on_demand == sum(g.on_demand_tokens for g in components.groups)


def test_report_shows_plugin_component_cost(tmp_path: Path) -> None:
    html = render_environment_html(_synthetic_report(tmp_path))
    assert "tok/session" in html
    assert "Skills" in html
    assert "MCP servers" in html
