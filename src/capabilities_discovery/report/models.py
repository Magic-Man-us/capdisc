"""The report's own typed models: the machine-readable snapshot and its indexed-artifact pairs."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from ..base import FrozenModel
from ..catalog import CatalogMcpServer, CatalogPlugin, CatalogSkill, CatalogTool
from ..scope import ScanRoot, ScopeInventory

McpSource = Literal[
    "tool-enriched cache", "fresh harvest", "stale cache (refresh failed)", "live (claude mcp list)"
]


class IndexedSkill(FrozenModel):
    """One indexed skill card paired with the SKILL.md path it was loaded from."""

    card: CatalogSkill
    path: Path


class IndexedPlugin(FrozenModel):
    """One plugin card paired with its install directory — the directory the plugin's bundled
    agents/skills/commands/hooks are captured under, so its components can be attributed to it."""

    card: CatalogPlugin
    path: Path


class EnvironmentReport(FrozenModel):
    """The full discovery harvest of one machine, composed of the existing typed models. The
    machine-readable snapshot the renderer draws from — round-trips through Pydantic JSON, so it
    can be persisted and served as-is. Effective set and hook events are derived from `inventory`
    at render time, not stored."""

    generated_at: datetime
    cwd: Path
    home: Path
    plugins_root: Path
    managed_dir: Path | None
    mcp_source: McpSource
    scan_roots: list[ScanRoot]
    plugin_dirs: list[Path]
    inventory: ScopeInventory
    skills: list[IndexedSkill]
    builtin_tools: list[CatalogTool]
    plugins: list[IndexedPlugin]
    mcp_servers: list[CatalogMcpServer]

    @property
    def skill_count(self) -> int:
        """Not a `computed_field`: it would round-trip into the persisted JSON as an `extra`
        key that `model_validate_json(model_dump_json())` then rejects under `extra="forbid"`,
        and it adds no information beyond `len(skills)` a reader can already see."""
        return len(self.skills)

    @property
    def tool_count(self) -> int:
        return len(self.builtin_tools)

    @property
    def plugin_count(self) -> int:
        return len(self.plugins)

    @property
    def mcp_server_count(self) -> int:
        return len(self.mcp_servers)

    @property
    def capture_count(self) -> int:
        return len(self.inventory.artifacts)

    @property
    def hook_config_count(self) -> int:
        return len(self.inventory.hook_configs)

    @property
    def scan_root_count(self) -> int:
        return len(self.scan_roots)
