"""Per-plugin component inventory and token-cost estimation."""

from __future__ import annotations

from typing import Literal

from pydantic import TypeAdapter, ValidationError, computed_field

from ..base import FrozenModel, InputModel
from ..catalog import CatalogMcpServer
from ..frontmatter import read_frontmatter
from ..html import e
from ..scope import ArtifactKind, CapturedArtifact, ScopeInventory
from ..tokens import TokenCount, estimate_tokens
from .html import group_label
from .models import IndexedPlugin
from .types import ComponentCount

GroupName = Literal["Skills", "Agents", "Hooks", "MCP servers"]


class _Frontmatter(InputModel):
    """Just the description from an artifact's frontmatter — the part that loads every session."""

    description: str | None = None


_FRONTMATTER: TypeAdapter[_Frontmatter] = TypeAdapter(_Frontmatter)


def _description_tokens(contents: str) -> int:
    """The always-on cost of one artifact: the tokens of its frontmatter description (what loads
    into every session), or 0 when it declares none."""
    data = read_frontmatter(contents)
    if data is None:
        return 0
    try:
        return estimate_tokens(_FRONTMATTER.validate_python(data).description or "")
    except ValidationError:
        return 0


class ComponentGroup(FrozenModel):
    """One component group a plugin contributes — its count and estimated token cost split into
    always-on (loaded every session) and on-demand (loaded only when a component is invoked)."""

    name: GroupName
    count: ComponentCount
    always_on_tokens: TokenCount
    on_demand_tokens: TokenCount


class PluginComponents(FrozenModel):
    """A plugin's component inventory: the per-group counts and token estimates."""

    groups: list[ComponentGroup]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_always_on(self) -> TokenCount:
        """Tokens this plugin adds to every session — the sum of its groups' always-on cost."""
        return sum(group.always_on_tokens for group in self.groups)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_on_demand(self) -> TokenCount:
        """Tokens loaded only when this plugin's components are invoked."""
        return sum(group.on_demand_tokens for group in self.groups)


def _capture_group(name: GroupName, captures: list[CapturedArtifact]) -> ComponentGroup:
    """A group from captured artifacts: always-on is each one's frontmatter description, on-demand
    is its full body."""
    return ComponentGroup(
        name=name,
        count=len(captures),
        always_on_tokens=sum(_description_tokens(c.contents) for c in captures),
        on_demand_tokens=sum(estimate_tokens(c.contents) for c in captures),
    )


def _mcp_group(servers: list[CatalogMcpServer]) -> ComponentGroup:
    """The MCP-servers group: always-on is each server's tool names (what a deferred-tool setup
    loads), on-demand is each tool's full serialized schema (loaded when fetched)."""
    names = sum(estimate_tokens(" ".join(t.name for t in s.tools)) for s in servers)
    schemas = sum(estimate_tokens(t.model_dump_json()) for s in servers for t in s.tools)
    return ComponentGroup(
        name="MCP servers", count=len(servers), always_on_tokens=names, on_demand_tokens=schemas
    )


def plugin_components(
    plugin: IndexedPlugin, inventory: ScopeInventory, mcp_servers: list[CatalogMcpServer]
) -> PluginComponents:
    """The component inventory one plugin contributes, grouped and token-costed.

    Components are attributed by install directory: a captured artifact belongs to the plugin when
    its path sits under the plugin's install path. Skills and commands fold into one "Skills" group
    (the user-facing grouping); agents and hooks each get their own; MCP servers are the plugin's
    declared servers found in the harvest.

    Args:
        plugin: The plugin and its install directory.
        inventory: The full disk inventory; its captures are attributed by path.
        mcp_servers: The harvested MCP servers, matched to the plugin's declared refs.

    Returns:
        The grouped, token-costed component inventory.
    """
    owned = [c for c in inventory.artifacts if plugin.path in c.path.parents]
    skills = [c for c in owned if c.kind in (ArtifactKind.skill, ArtifactKind.command)]
    agents = [c for c in owned if c.kind is ArtifactKind.agent]
    hooks = [c for c in owned if c.kind is ArtifactKind.hook]
    servers = [s for s in mcp_servers if s.ref in plugin.card.mcp_servers]
    return PluginComponents(
        groups=[
            _capture_group("Skills", skills),
            _capture_group("Agents", agents),
            _capture_group("Hooks", hooks),
            _mcp_group(servers),
        ]
    )


def components_block(components: PluginComponents) -> str:
    """The component-cost block appended inside a plugin card: a clean per-group table of counts
    and token estimates, with a totals row."""
    rows = "".join(
        f"<tr><td>{e(g.name)}</td><td class='num'>{e(g.count)}</td>"
        f"<td class='num'>~{e(g.always_on_tokens)}</td>"
        f"<td class='num'>~{e(g.on_demand_tokens)}</td></tr>"
        for g in components.groups
    )
    total = (
        "<tr class='total'><td>Total</td><td class='num'></td>"
        f"<td class='num'>~{e(components.total_always_on)}</td>"
        f"<td class='num'>~{e(components.total_on_demand)}</td></tr>"
    )
    return (
        group_label("context cost") + "<div class='tblwrap'><table class='tbl'><thead><tr>"
        "<th>component</th><th class='num'>count</th>"
        "<th class='num'>tok/session</th><th class='num'>on-demand</th>"
        f"</tr></thead><tbody>{rows}{total}</tbody></table></div>"
    )
