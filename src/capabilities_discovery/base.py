from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic.fields import ComputedFieldInfo, FieldInfo

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def humanize_field_title(field_name: str, _info: FieldInfo | ComputedFieldInfo) -> str:
    """A clean, alias-independent JSON-Schema title from a field's Python name.

    Splits snake_case, kebab-case, and camelCase into words and renders them sentence-cased
    (`status_message` -> `Status message`). Avoids the mangled titles Pydantic derives from a
    camelCase/hyphenated alias when a schema is exported `by_alias` (`statusMessage` -> the broken
    `Statusmessage`). Set as `field_title_generator`, so it drives the field-level `title` only;
    a domain-primitive alias's own `title` on the inner type is untouched.
    """
    spaced = _CAMEL_BOUNDARY.sub(" ", field_name.replace("_", " ").replace("-", " "))
    return " ".join(spaced.split()).capitalize()


class FrozenModel(BaseModel):
    """Immutable, strict domain model — the single config preset for this package."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FrozenWireModel(BaseModel):
    """Immutable model whose snake_case fields bind to the camelCase JSON keys of a Claude Code
    config file — accepts either spelling on load, emits camelCase on dump. Tolerant of unknown
    keys (`extra="ignore"`): this is the ingest boundary for config written by a Claude Code that
    may be newer than us, so a field we don't model yet is dropped, never a parse failure."""

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        field_title_generator=humanize_field_title,
    )


class MutableModel(BaseModel):
    """Strict but mutable domain model — for in-place accumulators that fill across a loop."""

    model_config = ConfigDict(extra="forbid")


class InputModel(BaseModel):
    """Lenient boundary model — ignores unknown keys from external sources."""

    model_config = ConfigDict(extra="ignore")
