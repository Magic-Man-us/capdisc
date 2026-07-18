from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ..base import FrozenModel
from .types import (
    MCP_TOOL_PARAMS_MAX,
    CatalogEntryId,
    EntryDescription,
    McpInputSchema,
    McpServerRef,
    McpToolDescription,
    McpToolName,
    NeedsNetworkFlag,
    PluginRef,
    ReadOnlyFlag,
    SkillRef,
    Tag,
    ToolRef,
)


class _Card(FrozenModel):
    """Fields every catalog entry shares: its id, description, and recall tags."""

    id: CatalogEntryId
    description: EntryDescription
    tags: list[Tag] = []

    @property
    def search_text(self) -> str:
        """The text recall ranks this entry on — its description and tags."""
        return " ".join((self.description, *self.tags))


class McpTool(FrozenModel):
    """One tool a connected MCP server provides, harvested from its `list_tools()`: its name,
    input-parameter names, full input schema, and description — the content that lets recall
    rank a server by what its tools actually do, not just its name."""

    name: McpToolName
    description: McpToolDescription = ""
    params: list[McpToolName] = Field(default_factory=list, max_length=MCP_TOOL_PARAMS_MAX)
    input_schema: McpInputSchema | None = None


class _Tool(_Card):
    """Shared execution-constraint facets (`read_only`, `needs_network`) for tool-like entries."""

    ref: ToolRef
    read_only: ReadOnlyFlag = True
    needs_network: NeedsNetworkFlag = False


class CatalogSkill(_Card):
    """A skill an agent can load."""

    kind: Literal["skill"] = "skill"
    ref: SkillRef


class CatalogTool(_Tool):
    """A built-in tool an agent can be granted, with its execution-constraint facets."""

    kind: Literal["tool"] = "tool"


class CatalogMcpServer(_Card):
    """A connected MCP server an agent can be wired to, with its harvested tools."""

    kind: Literal["mcp_server"] = "mcp_server"
    ref: McpServerRef
    tools: list[McpTool] = []

    @property
    def search_text(self) -> str:
        """The server's own description/tags plus each harvested tool's name, parameters, and
        description — so a task matches what the server's tools do, fixing name-only ranking."""
        tools = " ".join(f"{t.name} {' '.join(t.params)} {t.description}" for t in self.tools)
        return f"{super().search_text} {tools}".strip()


class CatalogPlugin(_Card):
    """An installed plugin an agent can draw from, with the skills and MCP servers it bundles."""

    kind: Literal["plugin"] = "plugin"
    ref: PluginRef
    skills: list[SkillRef] = []
    mcp_servers: list[McpServerRef] = []


CatalogEntry = Annotated[
    CatalogSkill | CatalogTool | CatalogMcpServer | CatalogPlugin,
    Field(discriminator="kind"),
]


class Catalog(FrozenModel):
    """The full set of capabilities — skills, tools, MCP servers, and plugins — the generator
    can draw from when building an agent."""

    entries: list[CatalogEntry]
