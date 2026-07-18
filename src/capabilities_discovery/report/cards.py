"""Catalog-entry cards, dispatched on the discriminated union."""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

from ..catalog import (
    CatalogEntry,
    CatalogMcpServer,
    CatalogPlugin,
    CatalogSkill,
    CatalogTool,
    McpTool,
)
from ..html import e, pill
from .components import PluginComponents, components_block
from .html import (
    CLASS_MCP,
    CLASS_SKILL,
    CLASS_TOOL,
    card_block,
    desc_block,
    id_span,
    path_block,
    ref_span,
    row_block,
    search_key,
    tag_chips,
)

# A tool list longer than this moves out of the card into a bottom drawer, so a server with a
# large surface (playwright, dq) doesn't blow the card open.
_TOOLS_INLINE_MAX = 6


def _skill_card(skill: CatalogSkill, path: Path | None) -> str:
    head = pill("skill", CLASS_SKILL) + ref_span(skill.ref) + id_span(skill.id)
    inner = row_block(head) + desc_block(skill.description) + tag_chips(list(skill.tags))
    if path is not None:
        inner += path_block(path)
    return card_block(search_key(skill.ref, skill.search_text), inner)


def _tool_card(tool: CatalogTool) -> str:
    facets = [pill("read-only" if tool.read_only else "writes")]
    if tool.needs_network:
        facets.append(pill("network"))
    head = pill("tool", CLASS_TOOL) + ref_span(tool.ref) + "".join(facets) + id_span(tool.id)
    inner = row_block(head) + desc_block(tool.description) + tag_chips(list(tool.tags))
    return card_block(search_key(tool.ref, tool.search_text), inner)


def _tools_table(tools: list[McpTool]) -> str:
    rows = "".join(
        f"<tr><td class='toolname'>{e(t.name)}</td>"
        f"<td class='mono params'>{e(', '.join(t.params))}</td>"
        f"<td>{e(t.description)}</td></tr>"
        for t in tools
    )
    return (
        "<div class='tblwrap'><table class='tbl'><thead><tr>"
        "<th>tool</th><th>params</th><th>description</th>"
        f"</tr></thead><tbody>{rows}</tbody></table></div>"
    )


def _mcp_card(server: CatalogMcpServer) -> str:
    head = pill("mcp", CLASS_MCP) + ref_span(server.ref) + id_span(f"{len(server.tools)} tools")
    inner = row_block(head) + desc_block(server.description) + tag_chips(list(server.tags))
    if server.tools:
        table = _tools_table(server.tools)
        if len(server.tools) > _TOOLS_INLINE_MAX:
            inner += (
                f"<button class='more' data-title='{e(server.ref)} · {len(server.tools)} tools'>"
                f"{len(server.tools)} tools &#9656;</button>"
                f"<div class='popup-src'>{table}</div>"
            )
        else:
            inner += table
    return card_block(search_key(server.ref, server.search_text), inner)


def plugin_card(plugin: CatalogPlugin, components: PluginComponents | None = None) -> str:
    head = pill("plugin") + ref_span(plugin.ref) + id_span(plugin.id)
    inner = row_block(head) + desc_block(plugin.description) + tag_chips(list(plugin.tags))
    if plugin.skills:
        inner += f'<div class="path"><b>skills:</b> {e(", ".join(plugin.skills))}</div>'
    if plugin.mcp_servers:
        inner += f'<div class="path"><b>mcp:</b> {e(", ".join(plugin.mcp_servers))}</div>'
    if components is not None:
        inner += components_block(components)
    return card_block(search_key(plugin.ref, plugin.search_text), inner)


def entry_card(entry: CatalogEntry, location: Path | None) -> str:
    """Render one catalog entry as a card, dispatched by its variant. `location` is a skill's
    SKILL.md path and is ignored for the other variants."""
    match entry:
        case CatalogSkill():
            return _skill_card(entry, location)
        case CatalogTool():
            return _tool_card(entry)
        case CatalogMcpServer():
            return _mcp_card(entry)
        case CatalogPlugin():
            return plugin_card(entry)
        case _ as unreachable:
            assert_never(unreachable)
