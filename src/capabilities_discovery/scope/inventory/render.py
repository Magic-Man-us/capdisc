"""Render a `ScopeInventory` snapshot as plain text or a self-contained HTML page."""

from __future__ import annotations

from ...html import e, pill, preview, redact_home
from ..types import ScopeKind
from .assets import INVENTORY_SCRIPT, INVENTORY_STYLE, PREVIEW_CHARS
from .capture import CapturedArtifact, ScopeInventory


def render_inventory(inventory: ScopeInventory) -> str:
    """Render a snapshot as human-readable text. Pure — returns text, prints nothing.

    Args:
        inventory: The snapshot to render.

    Returns:
        A multi-line report: every capture grouped by scope (in precedence order), then the
        effective set and the hook events in effect.
    """
    order = {scope: index for index, scope in enumerate(ScopeKind)}
    captures = sorted(
        inventory.artifacts,
        key=lambda c: (order[c.scope], c.kind.value, c.precedence, c.name),
    )
    lines = [f"ScopeInventory — {len(inventory.artifacts)} artifacts"]
    current_scope: ScopeKind | None = None
    for capture in captures:
        if capture.scope is not current_scope:
            current_scope = capture.scope
            lines.append(f"\n[{capture.scope.value}]")
        lines.append(
            f"  {capture.kind.value:<7} {capture.name:<22} {capture.shareable.value:<13}"
            f" rank={capture.precedence}  {capture.path}"
        )

    lines.append("\neffective (what Claude Code uses):")
    for capture in sorted(inventory.effective, key=lambda c: (c.kind.value, c.name)):
        lines.append(
            f"  {capture.kind.value:<7} {capture.name:<22} <- {capture.scope.value}/"
            f"{capture.shareable.value}"
        )

    events = sorted({event.value for config in inventory.hook_configs for event in config.root})
    lines.append(
        f"\nhook configs: {len(inventory.hook_configs)}  events: {', '.join(events) or '(none)'}"
    )
    return "\n".join(lines)


def _artifact_card(capture: CapturedArtifact, is_effective: bool) -> str:
    """One capture rendered as a card: header pills, path, and a content preview.

    Args:
        capture: The capture to render; every dynamic value is escaped.
        is_effective: Whether this capture is in the effective set (wins resolution).

    Returns:
        The card markup, tagged with a lowercased `data-s` search string for the filter.
    """
    marker = (
        pill("effective", "eff-b")
        if is_effective
        else f'<span class="id">rank {e(capture.precedence)} (shadowed)</span>'
    )
    head = (
        pill(capture.kind.value, f"k-{capture.kind.value}")
        + f'<span class="ref">{e(capture.name)}</span>'
        + pill(f"{capture.scope.value}/{capture.shareable.value}")
        + marker
        + pill(capture.resolution.value)
    )
    path_line = f'<div class="path">{e(redact_home(capture.path))}</div>'
    inner = f'<div class="row">{head}</div>{path_line}' + preview(capture.contents[:PREVIEW_CHARS])
    terms = (capture.name, capture.kind.value, capture.scope.value, redact_home(capture.path))
    search = e(" ".join(terms).lower())
    klass = "eff" if is_effective else "shadow"
    return f'<div class="card {klass}" data-s="{search}">{inner}</div>'


def render_inventory_html(inventory: ScopeInventory) -> str:
    """Render a snapshot as one self-contained HTML document. Pure — returns the markup
    string, prints nothing, does no I/O.

    All markup is built here in Python and every dynamic value is escaped; the inline
    script only toggles classes, sets `style.display`, and reads the filter input — it
    never assigns markup. Inline `<style>` and `<script>` only, no external assets.

    Args:
        inventory: The snapshot to render.

    Returns:
        A standalone HTML document: every capture grouped by scope (in precedence order)
        as a card, then the effective set and the hook events in effect.
    """
    effective = set(inventory.effective)
    order = {scope: index for index, scope in enumerate(ScopeKind)}
    captures = sorted(
        inventory.artifacts,
        key=lambda c: (order[c.scope], c.kind.value, c.precedence, c.name),
    )
    cards: list[str] = []
    current_scope: ScopeKind | None = None
    for capture in captures:
        if capture.scope is not current_scope:
            current_scope = capture.scope
            cards.append(f'<div class="grp">{e(capture.scope.value)}</div>')
        cards.append(_artifact_card(capture, capture in effective))
    captures_html = "".join(cards) or '<div class="empty">nothing captured on disk</div>'

    effective_rows = (
        "".join(
            f'<div class="card eff"><div class="row">'
            f"{pill(c.kind.value, f'k-{c.kind.value}')}"
            f'<span class="ref">{e(c.name)}</span>'
            f"{pill(f'{c.scope.value}/{c.shareable.value}')}</div></div>"
            for c in sorted(inventory.effective, key=lambda c: (c.kind.value, c.name))
        )
        or '<div class="empty">nothing effective</div>'
    )

    events = sorted({event.value for config in inventory.hook_configs for event in config.root})
    event_bar = (
        '<div class="eventbar">'
        + "".join(f'<span class="event">{e(ev)}</span>' for ev in events)
        + "</div>"
        if events
        else '<div class="empty">no hook events in effect</div>'
    )

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>ScopeInventory</title>"
        f"<style>{INVENTORY_STYLE}</style></head><body>"
        "<header><h1>ScopeInventory</h1>"
        f'<div class="meta"><b>{e(len(inventory.artifacts))}</b> artifacts · '
        f"<b>{e(len(inventory.effective))}</b> effective · "
        f"<b>{e(len(inventory.hook_configs))}</b> hook configs</div></header>"
        "<main>"
        '<input class="search" placeholder="filter captures…">'
        f'<div class="grp">captures by scope</div>{captures_html}'
        f'<div class="grp">effective (what Claude Code uses)</div>{effective_rows}'
        f'<div class="grp">hook events in effect '
        f"({e(len(inventory.hook_configs))} configs)</div>"
        f"{event_bar}"
        "</main>"
        f"<script>{INVENTORY_SCRIPT}</script></body></html>"
    )
