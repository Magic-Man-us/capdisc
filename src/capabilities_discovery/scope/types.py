from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import Field

ARTIFACT_CONTENT_MAX_CHARS = 200_000  # length cap of ArtifactContents; _safe_read enforces it


class ScopeKind(StrEnum):
    """Who sees a definition. Not every artifact supports every scope — session is subagents
    via --agents, component is a hook living in a skill/agent's frontmatter."""

    managed = "managed"
    session = "session"
    project = "project"
    user = "user"
    plugin = "plugin"
    component = "component"


class Shareability(StrEnum):
    """How a definition is (or is not) shared — the mechanism behind the docs' Shareable column."""

    committed = "committed"  # in-repo, e.g. .claude/settings.json, .claude/agents/
    gitignored = "gitignored"  # .claude/settings.local.json
    machine_local = "machine_local"  # ~/.claude/*, this machine only
    admin = "admin"  # managed policy, admin-controlled
    bundled = "bundled"  # shipped inside a plugin
    in_component = "in_component"  # embedded in a host component's frontmatter
    ephemeral = "ephemeral"  # in-memory only, e.g. --agents JSON


class ArtifactKind(StrEnum):
    """A kind of scoped artifact Claude Code loads. Storage differs by kind: agents/skills/
    commands are standalone files, hooks are settings entries or frontmatter."""

    agent = "agent"
    skill = "skill"
    command = "command"
    hook = "hook"


class ResolutionMode(StrEnum):
    """How same-named definitions across scopes combine. Collision: the highest-precedence one
    wins (agents, skills, commands). Additive: every matching one fires (hooks)."""

    collision = "collision"
    additive = "additive"


ScopeRoot = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        title="Scope root",
        description="Filesystem root a scope's artifacts live under.",
        examples=[".claude", "~/.claude"],
    ),
]
ArtifactSubdir = Annotated[
    str,
    Field(
        pattern=r"^[a-z]+$",
        title="Artifact subdir",
        description="Subdirectory under a scope root that holds one artifact kind.",
        examples=["agents", "skills"],
    ),
]
GlobPattern = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        title="Glob pattern",
        description="Glob, relative to an artifact's subdir, that matches its entry files.",
        examples=["**/*.md", "**/SKILL.md"],
    ),
]
SettingsFile = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        title="Settings file",
        description="Name of the JSON file a settings-entry artifact lives inside.",
        examples=["settings.json", "settings.local.json", "hooks/hooks.json"],
    ),
]
JsonKey = Annotated[
    str,
    Field(
        pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$",
        title="JSON key",
        description="Top-level key, inside a settings file or frontmatter, holding the entries.",
        examples=["hooks", "mcpServers"],
    ),
]
CliFlag = Annotated[
    str,
    Field(
        pattern=r"^--[a-z][a-z-]*$",
        title="CLI flag",
        description="Launch flag that supplies an in-memory definition.",
        examples=["--agents"],
    ),
]
ArtifactName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        title="Artifact name",
        description="Path-derived label for a captured artifact; its true identity is the "
        "name frontmatter inside contents.",
        examples=["code-reviewer"],
    ),
]
ArtifactPath = Annotated[
    Path,
    Field(
        title="Artifact path",
        description="Exact filesystem path of a captured artifact (None when supplied in-memory).",
        examples=["~/.claude/agents/code-reviewer.md"],
    ),
]
ArtifactContents = Annotated[
    str,
    Field(
        max_length=ARTIFACT_CONTENT_MAX_CHARS,
        title="Artifact contents",
        description="Raw text of a captured artifact file.",
    ),
]
ResolutionRank = Annotated[
    int,
    Field(
        ge=0,
        title="Resolution rank",
        description="Precedence position when names collide — 0 is highest, larger loses. "
        "Encodes both cross-scope order and nearest-first depth within project scope.",
    ),
]
ScanBasePath = Annotated[
    Path,
    Field(
        title="Scan base path",
        description="Concrete filesystem directory scanned for a scope's artifacts.",
        examples=["~/.claude", "/repo/.claude"],
    ),
]
