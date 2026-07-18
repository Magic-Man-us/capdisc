from __future__ import annotations

import re

import yaml
from pydantic import JsonValue, TypeAdapter, ValidationError

# \r?\n: CRLF-authored files (git core.autocrlf) must not silently lose their frontmatter.
_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---", re.DOTALL)
_BOM = "\ufeff"
_MAPPING: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


def load[T](text: str, shape: TypeAdapter[T]) -> T | None:
    """Parse YAML or JSON text into `shape`.

    No format sniffing is needed: YAML is a superset of JSON, so one `yaml.safe_load` reads both.
    When the text is known to be JSON, prefer `shape.validate_json(text)` — stricter and faster.

    Args:
        text: The YAML/JSON source.
        shape: The adapter to validate the parsed value into.

    Returns:
        The validated value, or None if `text` is neither valid YAML/JSON nor that shape.
    """
    try:
        return shape.validate_python(yaml.safe_load(text))
    except (yaml.YAMLError, ValidationError, RecursionError):
        # RecursionError: deeply nested YAML in untrusted repo content must skip itself,
        # not abort the scan.
        return None


def read_frontmatter(text: str) -> dict[str, JsonValue] | None:
    """Extract the leading `--- … ---` frontmatter block as a mapping.

    The single frontmatter-parsing boundary; callers validate the mapping into their own typed
    model.

    Args:
        text: The document body, which may open with a frontmatter block.

    Returns:
        The frontmatter as a mapping, or None when the text has no such block or it isn't a
        mapping.
    """
    match = _FRONTMATTER.match(text.removeprefix(_BOM))
    return load(match.group(1), _MAPPING) if match else None
