from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, JsonValue, TypeAdapter
from pydantic.functional_validators import AfterValidator, BeforeValidator

from ..tokens import token_bounds

DESCRIPTION_TOKEN_MAX = 512
CATALOG_ID_MAX = 64  # length cap of CatalogEntryId; catalog_id truncates to it
MCP_TOOL_DESCRIPTION_MAX = 4000  # length cap of McpToolDescription; harvest truncates to it
MCP_TOOL_PARAMS_MAX = 200  # item cap of McpTool.params
MCP_INPUT_SCHEMA_MAX_BYTES = 20_000  # serialized size cap of McpInputSchema

_INPUT_SCHEMA_ADAPTER: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])

_SLUG_SKILL = re.compile(r"[^a-z0-9:-]+")  # skill refs keep ':' for plugin:skill
_SLUG_REF = re.compile(r"[^a-z0-9_-]+")  # server and plugin refs keep '_'
_SLUG_ID = re.compile(r"[^a-z0-9._-]+")  # catalog ids keep '.' for the 'kind.ref' shape


def _slugify(value: str, disallowed: re.Pattern[str], max_len: int) -> str:
    """Normalize an arbitrary name into a ref: lowercase, collapse disallowed runs to '-', trim
    edge punctuation so it starts and ends on a word char, and truncate."""
    return disallowed.sub("-", value.strip().lower()).strip("-:_")[:max_len]


def _to_skill_ref(value: str) -> str:
    """Slugify a name into a `SkillRef`, keeping `:` for the `plugin:skill` form (max 128)."""
    return _slugify(value, _SLUG_SKILL, 128)


def _to_underscore_ref(value: str) -> str:
    """Slugify a name into a server/plugin ref, keeping `_` (max 64)."""
    return _slugify(value, _SLUG_REF, 64)


CatalogIdPrefix = Literal["plugin", "mcp", "skill"]


def catalog_id(prefix: CatalogIdPrefix, ref: str) -> CatalogEntryId:
    """A valid `CatalogEntryId` for `prefix.ref` — folds ':' and overflow away so a valid ref
    never yields an unrepresentable id. `CatalogEntryId` itself stays strict (it is a lookup
    key); this is the one place a kind+ref is composed into an id."""
    return _slugify(f"{prefix}.{ref}", _SLUG_ID, CATALOG_ID_MAX)


class BuiltinTool(StrEnum):
    """The grant refs of the built-in Claude Code tools — the single source for both the tool
    catalog cards and the default tool set a generated agent receives."""

    read = "Read"
    write = "Write"
    edit = "Edit"
    glob = "Glob"
    grep = "Grep"
    bash = "Bash"
    web_fetch = "WebFetch"
    web_search = "WebSearch"
    task = "Task"


EntryDescription = Annotated[
    str,
    Field(
        min_length=8,
        max_length=1536,
        title="Entry description",
        description="What a catalog entry provides and when it applies.",
        examples=["Reads a file from disk."],
    ),
    token_bounds(DESCRIPTION_TOKEN_MAX),
]
ToolRef = Annotated[
    str,
    Field(
        min_length=1,
        max_length=200,
        title="Tool ref",
        description="A tool grant string, e.g. 'Read', 'Bash(git log:*)', or 'mcp__server__tool'.",
        examples=["Read", "Bash(git log:*)"],
    ),
]
McpToolName = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
        title="MCP tool name",
        description="Name of a tool (or input parameter) provided by an MCP server.",
        examples=["browser_navigate", "file_path"],
    ),
]
McpToolDescription = Annotated[
    str,
    Field(
        max_length=MCP_TOOL_DESCRIPTION_MAX,
        title="MCP tool description",
        description="What an MCP tool does, as reported by the server's `list_tools()`.",
        examples=["Navigate the browser to a url and wait for load."],
    ),
]


def _check_schema_size(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Reject a schema whose JSON serialization exceeds `MCP_INPUT_SCHEMA_MAX_BYTES` — an MCP
    server's `list_tools()` response is untrusted input, and one tool's input schema must not be
    able to inflate the on-disk cache without limit."""
    if len(_INPUT_SCHEMA_ADAPTER.dump_json(value)) > MCP_INPUT_SCHEMA_MAX_BYTES:
        raise ValueError(f"input schema exceeds {MCP_INPUT_SCHEMA_MAX_BYTES} bytes serialized")
    return value


McpInputSchema = Annotated[
    dict[str, JsonValue],
    AfterValidator(_check_schema_size),
    Field(
        title="MCP tool input schema",
        description=(
            "Full JSON Schema object for an MCP tool's input, as reported by `list_tools()`."
        ),
        examples=[
            {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            }
        ],
    ),
]
SkillRef = Annotated[
    str,
    BeforeValidator(_to_skill_ref),
    Field(
        pattern=r"^[a-z0-9][a-z0-9:-]{0,127}$",
        title="Skill ref",
        description="A skill name or plugin:skill reference; a raw name is slugified to one.",
        examples=["error-handling", "my-plugin:my-skill"],
    ),
]
McpServerRef = Annotated[
    str,
    BeforeValidator(_to_underscore_ref),
    Field(
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
        title="MCP server",
        description="An MCP server name; a raw name is slugified to one.",
        examples=["playwright"],
    ),
]
PluginRef = Annotated[
    str,
    BeforeValidator(_to_underscore_ref),
    Field(
        pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$",
        title="Plugin",
        description="An installed plugin name (marketplace suffix stripped); slugified.",
        examples=["agentforge"],
    ),
]
Tag = Annotated[
    str,
    Field(
        pattern=r"^[a-z0-9][a-z0-9-]{0,31}$",
        title="Tag",
        description="A keyword folded into a catalog entry's text for lexical recall.",
        examples=["git"],
    ),
]
CatalogEntryId = Annotated[
    str,
    Field(
        pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
        title="Catalog id",
        description=(
            "Stable id of one item in the catalog of skills, tools, and MCP servers an agent "
            "can be built from. Strict — it is a lookup key; compose ids via catalog_id()."
        ),
        examples=["tool.read"],
    ),
]
RelevanceScore = Annotated[
    float,
    Field(
        ge=0.0,
        le=1.0,
        title="Relevance",
        description="How well a catalog item matches the task, from 0 (no match) to 1 (best).",
    ),
]
RecallLimit = Annotated[
    int,
    Field(
        ge=1,
        le=200,
        title="Recall limit",
        description="Most matching catalog items the search step may return.",
    ),
]
McpToolCount = Annotated[
    int,
    Field(
        ge=0,
        title="MCP tool count",
        description="Number of tools a connected MCP server provides.",
        examples=[4],
    ),
]
ReadOnlyFlag = Annotated[
    bool,
    Field(
        title="Read-only",
        description="Whether the tool only reads state, never writes or executes.",
    ),
]
NeedsNetworkFlag = Annotated[
    bool,
    Field(
        title="Needs network",
        description="Whether the tool requires outbound network access to function.",
    ),
]

DEFAULT_RECALL_LIMIT = 30
RELEVANCE_THRESHOLD = 0.1
