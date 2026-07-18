"""Section bodies: each tab's HTML, assembled from cards over one slice of the report."""

from __future__ import annotations

from pathlib import Path

from ..catalog import CatalogMcpServer, CatalogTool
from ..html import e, pill, preview, redact_home
from ..scope import ArtifactKind, CapturedArtifact, ScanRoot, ScopeInventory
from .cards import entry_card, plugin_card
from .components import plugin_components
from .html import (
    card_block,
    empty_block,
    group_label,
    id_span,
    kind_class,
    kv_line,
    path_block,
    ref_span,
    row_block,
    search_key,
    stat_block,
)
from .models import EnvironmentReport, IndexedPlugin, IndexedSkill

_PREVIEW_LEN = 600


def render_roots_section(scan_roots: list[ScanRoot], plugin_dirs: list[Path]) -> str:
    cards: list[str] = []
    for root in scan_roots:
        exists = root.base.exists()
        head = (
            pill(root.scope.value)
            + f'<span class="ref mono" style="font-size:12.5px">{e(redact_home(root.base))}</span>'
            + (pill("exists", "eff-b") if exists else pill("missing"))
        )
        if root.kinds is not None:
            head += id_span("kinds: " + ", ".join(sorted(k.value for k in root.kinds)))
        cards.append(
            card_block(
                search_key(root.scope.value, redact_home(root.base)),
                row_block(head),
                "eff" if exists else "shadow",
            )
        )
    if plugin_dirs:
        cards.append(group_label(f"plugin install dirs ({len(plugin_dirs)})"))
        cards.extend(f'<div class="card">{path_block(p)}</div>' for p in plugin_dirs)
    return "".join(cards)


def _capture_card(capture: CapturedArtifact, is_effective: bool) -> str:
    head = (
        pill(capture.kind.value, kind_class(capture.kind))
        + ref_span(capture.name)
        + pill(f"{capture.scope.value}/{capture.shareable.value}")
        + (
            pill("effective", "eff-b")
            if is_effective
            else id_span(f"rank {capture.precedence} (shadowed)")
        )
        + pill(capture.resolution.value)
    )
    inner = row_block(head) + path_block(capture.path) + preview(capture.contents[:_PREVIEW_LEN])
    search = search_key(
        capture.name, capture.kind.value, capture.scope.value, redact_home(capture.path)
    )
    return card_block(search, inner, "eff" if is_effective else "shadow")


def render_inventory_section(inventory: ScopeInventory) -> str:
    effective = set(inventory.effective)
    captures = sorted(inventory.artifacts, key=lambda c: (c.kind.value, c.name, c.precedence))
    by_kind: dict[ArtifactKind, list[str]] = {}
    for capture in captures:
        by_kind.setdefault(capture.kind, []).append(_capture_card(capture, capture in effective))
    out: list[str] = []
    for kind in ArtifactKind:
        cards = by_kind.get(kind, [])
        if cards:
            out.append(group_label(f"{kind.value} ({len(cards)})"))
            out.extend(cards)
    return "".join(out) or empty_block("nothing captured on disk")


def render_skills_section(skills: list[IndexedSkill]) -> str:
    cards = [entry_card(s.card, s.path) for s in sorted(skills, key=lambda s: s.card.ref)]
    return "".join(cards) or empty_block("no skills found")


def render_tools_section(tools: list[CatalogTool]) -> str:
    return "".join(entry_card(tool, None) for tool in tools) or empty_block("no builtin tools")


def render_plugins_section(
    plugins: list[IndexedPlugin],
    inventory: ScopeInventory,
    mcp_servers: list[CatalogMcpServer],
) -> str:
    cards = [
        plugin_card(p.card, plugin_components(p, inventory, mcp_servers))
        for p in sorted(plugins, key=lambda p: p.card.ref)
    ]
    return "".join(cards) or empty_block("no plugins found")


def render_mcp_section(servers: list[CatalogMcpServer]) -> str:
    cards = [entry_card(s, None) for s in sorted(servers, key=lambda s: s.ref)]
    return "".join(cards) or empty_block("no MCP servers reachable")


def render_overview_section(report: EnvironmentReport) -> str:
    top = (
        '<div class="bigstat">'
        + stat_block(report.skill_count, "skills")
        + stat_block(report.tool_count, "builtin tools")
        + stat_block(report.plugin_count, "plugins")
        + stat_block(report.mcp_server_count, "mcp servers")
        + stat_block(report.capture_count, "captures on disk")
        + stat_block(report.hook_config_count, "hook configs")
        + stat_block(report.scan_root_count, "scan roots")
        + "</div>"
    )
    env_block = (
        group_label("environment")
        + '<div class="card">'
        + kv_line("cwd", report.cwd)
        + kv_line("home", report.home)
        + kv_line("plugins root", report.plugins_root)
        + kv_line("managed dir", report.managed_dir or "(none on this OS)")
        + kv_line("mcp source", report.mcp_source)
        + "</div>"
    )
    by_kind: dict[ArtifactKind, int] = {}
    for capture in report.inventory.artifacts:
        by_kind[capture.kind] = by_kind.get(capture.kind, 0) + 1
    kinds = (
        group_label("captures by kind")
        + '<div class="bigstat">'
        + "".join(stat_block(n, kind.value) for kind, n in by_kind.items())
        + "</div>"
    )
    events = sorted({ev.value for cfg in report.inventory.hook_configs for ev in cfg.root})
    hooks = ""
    if events:
        hooks = (
            group_label("hook events in effect")
            + '<div class="eventbar">'
            + "".join(f'<span class="event">{e(ev)}</span>' for ev in events)
            + "</div>"
        )
    return top + env_block + kinds + hooks
