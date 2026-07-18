"""HTML-fragment builders shared by the report's card and section renderers.

Every dynamic value passed through `e` is escaped, so callers never need to escape by hand.
"""

from __future__ import annotations

from ..html import e, redact_home
from ..scope import ArtifactKind

CLASS_SKILL = "k-skill"
_CLASS_AGENT = "k-agent"
_CLASS_COMMAND = "k-command"
_CLASS_HOOK = "k-hook"
CLASS_TOOL = "k-tool"
CLASS_MCP = "k-mcp_server"


def ref_span(text: str) -> str:
    return f'<span class="ref">{e(text)}</span>'


def id_span(text: str) -> str:
    return f'<span class="id">{e(text)}</span>'


def desc_block(text: str) -> str:
    return f'<div class="desc">{e(text)}</div>'


def path_block(value: object) -> str:
    return f'<div class="path">{e(redact_home(value))}</div>'


def row_block(inner: str) -> str:
    return f'<div class="row">{inner}</div>'


def group_label(label: str) -> str:
    return f'<div class="grp">{e(label)}</div>'


def empty_block(label: str) -> str:
    return f'<div class="empty">{e(label)}</div>'


def kv_line(label: str, value: object) -> str:
    return f'<div class="path"><b>{e(label)}:</b> {e(redact_home(value))}</div>'


def stat_block(n: object, label: str) -> str:
    return f'<div class="stat"><div class="n">{e(n)}</div><div class="l">{e(label)}</div></div>'


def tag_chips(items: list[str]) -> str:
    if not items:
        return ""
    chips = "".join(f'<span class="tag">{e(t)}</span>' for t in items)
    return f'<div class="tags">{chips}</div>'


def search_key(*parts: object) -> str:
    return e(" ".join(str(p) for p in parts if p).lower())


def card_block(search: str, inner: str, extra_class: str = "") -> str:
    return f'<div class="card {extra_class}" data-s="{search}">{inner}</div>'


def kind_class(kind: ArtifactKind) -> str:
    match kind:
        case ArtifactKind.skill:
            return CLASS_SKILL
        case ArtifactKind.agent:
            return _CLASS_AGENT
        case ArtifactKind.command:
            return _CLASS_COMMAND
        case ArtifactKind.hook:
            return _CLASS_HOOK
