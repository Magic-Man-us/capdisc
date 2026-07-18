"""Tiny HTML-escaping and markup primitives shared by the report and scope-inventory renderers.

Lives at the package root (not inside `report/` or `scope/`) because both packages need it and
`report/` already depends on `scope/` — putting it in `scope/` would make the reverse import
circular.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

_FULL_MATCH_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9\-_.+/=]{8,}"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
)
_KEY_VALUE_SECRET_PATTERN = re.compile(
    r"(?i)\b((?:api[-_]?key|secret|token|password|passwd|auth)\w*)"
    r"([\"'=:\s]{1,3})([A-Za-z0-9\-_./+=]{6,})"
)
_REDACTED = "[redacted]"


def e(value: object) -> str:
    """Escape any value for safe HTML text/attribute interpolation."""
    return escape("" if value is None else str(value))


def redact_home(value: object) -> str:
    """Render `value` with the user's home directory prefix collapsed to `~`.

    Applied to every path rendered into the discovery report so a shared report doesn't
    disclose the OS username via each scanned/captured path."""
    text = "" if value is None else str(value)
    home = str(Path.home())
    if home not in ("", "/") and text.startswith(home):
        return "~" + text[len(home) :]
    return text


def redact_secrets(text: str) -> str:
    """Best-effort scrub of secret-shaped substrings from arbitrary preview text: bearer/basic
    auth headers, common provider API key prefixes, and `token=`/`secret=`-style key-value pairs.

    Pattern-based, not a guarantee — a secret in an unusual shape can still slip through. Applied
    to raw file-content previews (e.g. a hook's command string) that this tool didn't author,
    before they're rendered into a report meant to be shared."""
    redacted = text
    for pattern in _FULL_MATCH_SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return _KEY_VALUE_SECRET_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", redacted)


def pill(label: str, css: str = "sc") -> str:
    """A small uppercase badge; `css` picks its colour class."""
    return f'<span class="pill {css}">{e(label)}</span>'


def preview(text: str) -> str:
    """A collapsible content preview; the toggle button only flips a CSS class.

    Runs `redact_secrets` before escaping — a content preview of a file this tool didn't author
    (a hook's command, a settings JSON slice) may carry a literal credential."""
    if not text:
        return ""
    return (
        '<button class="toggle" onclick="this.parentElement.classList.toggle(\'open\')">'
        "&#9656; preview</button>"
        f'<div class="preview">{e(redact_secrets(text))}</div>'
    )
