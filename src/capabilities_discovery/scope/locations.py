from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, JsonValue, TypeAdapter, ValidationError

from ..base import FrozenModel
from .types import (
    ARTIFACT_CONTENT_MAX_CHARS,
    ArtifactContents,
    ArtifactKind,
    ArtifactName,
    ArtifactPath,
    ArtifactSubdir,
    CliFlag,
    GlobPattern,
    JsonKey,
    ResolutionMode,
    ScopeKind,
    ScopeRoot,
    SettingsFile,
    Shareability,
)


class CaptureHit(FrozenModel):
    """One concrete definition a storage shape found under a real base path."""

    path: ArtifactPath
    name: ArtifactName
    contents: ArtifactContents


def _safe_read(path: Path, base: Path) -> str | None:
    """Contents of `path` if it resolves inside `base`, is readable UTF-8, and fits the cap;
    None to skip it. A dangling symlink, permission-denied, or non-UTF-8 file skips itself —
    one bad file must never abort the scan.

    Bounded to `ARTIFACT_CONTENT_MAX_CHARS` (the `ArtifactContents` cap) so an enormous file
    cannot OOM the scan before validation; over-limit or symlink-escaping files are skipped,
    not partially read."""
    if not path.resolve().is_relative_to(base.resolve()):
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            text = handle.read(ARTIFACT_CONTENT_MAX_CHARS + 1)
    except (OSError, UnicodeDecodeError):
        return None
    return None if len(text) > ARTIFACT_CONTENT_MAX_CHARS else text


_JSON_OBJECT: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def _extract_entry(text: str, key: JsonKey | None) -> str | None:
    """The JSON slice a settings-entry artifact captures: the whole object when `key` is None
    (a bare hooks.json), or that key's value (a `hooks` block inside settings.json). None when
    the text is not a JSON object or the key is absent."""
    try:
        data = _JSON_OBJECT.validate_json(text)
    except ValidationError:
        return None
    if key is None:
        return text
    if key not in data:
        return None
    return _JSON_VALUE.dump_json(data[key]).decode()


# --- Axis 1: storage shape ------------------------------------------------------------
# How a definition is physically stored — independent of which scope it sits in. Each shape
# renders an abstract place (for the taxonomy) and discovers concrete hits (for a scan).


class StandaloneFile(FrozenModel):
    """A file of its own under <root>/<subdir>/ — agents, skills, commands."""

    storage_kind: Literal["standalone_file"] = "standalone_file"
    subdir: ArtifactSubdir
    glob: GlobPattern
    name_from: Literal["stem", "parent"] = "stem"

    def discover(self, base: Path) -> list[CaptureHit]:
        """Capture every file matching this shape's glob under `base/<subdir>`.

        Args:
            base: The scanned scope root; each hit's path must resolve inside it.

        Returns:
            One hit per readable, in-bounds file, named by stem or parent dir per `name_from`;
            files that escape `base` or exceed the size cap are skipped.
        """
        directory = base / self.subdir
        hits: list[CaptureHit] = []
        for path in sorted(directory.glob(self.glob)):
            contents = _safe_read(path, base)
            if contents is None:
                continue
            name = path.parent.name if self.name_from == "parent" else path.stem
            hits.append(CaptureHit(path=path, name=name, contents=contents))
        return hits


class SettingsEntry(FrozenModel):
    """A key inside a JSON settings file — hooks, MCP servers, permissions. A None `key` means
    the file's root object is the entry (a plugin's bare hooks.json), not a nested key."""

    storage_kind: Literal["settings_entry"] = "settings_entry"
    file: SettingsFile
    key: JsonKey | None = None

    def discover(self, base: Path) -> list[CaptureHit]:
        """Capture this shape's settings entry from `base/<file>`.

        Args:
            base: The scanned scope root; the file's path must resolve inside it.

        Returns:
            A single hit holding the extracted entry (the whole object when `key` is None, else
            that key's value), or `[]` if the file is missing, out of bounds, not JSON, or the
            key is absent.
        """
        path = base / self.file
        if not path.is_file():
            return []
        text = _safe_read(path, base)
        if text is None:
            return []
        entry = _extract_entry(text, self.key)
        if entry is None:
            return []
        return [CaptureHit(path=path, name=self.key or self.file, contents=entry)]


class HostFrontmatter(FrozenModel):
    """Embedded in another component's frontmatter — a hook defined inside a skill or agent."""

    storage_kind: Literal["host_frontmatter"] = "host_frontmatter"
    key: JsonKey

    def discover(self, base: Path) -> list[CaptureHit]:  # noqa: ARG002 — uniform Storage interface
        """Always empty — a frontmatter-embedded hook is captured with its host, not standalone."""
        return []


class InMemoryFlag(FrozenModel):
    """Supplied as JSON on a launch flag — the --agents session form."""

    storage_kind: Literal["in_memory_flag"] = "in_memory_flag"
    flag: CliFlag

    def discover(self, base: Path) -> list[CaptureHit]:  # noqa: ARG002 — uniform Storage interface
        """Always empty — a launch-flag definition lives in process memory, not on disk."""
        return []


Storage = Annotated[
    StandaloneFile | SettingsEntry | HostFrontmatter | InMemoryFlag,
    Field(discriminator="storage_kind"),
]


# --- Axis 2: location -----------------------------------------------------------------
# A concrete place a definition can live: a scope, how it is shared, the root it sits under,
# and the storage shape. Scope is a property of location, not the organizing axis. Precedence
# is NOT a property of a scope: it differs by artifact kind, so it lives in the order each
# artifact lists its locations (Axis 3), not in a table here.


class Location(FrozenModel):
    """Where a definition lives, and what that implies — scope, shareability, storage shape."""

    scope: ScopeKind
    shareable: Shareability
    root: ScopeRoot
    storage: Storage


# --- Axis 3: artifact -----------------------------------------------------------------
# What is stored. Each kind declares the locations it can live in — listed highest-precedence
# first, so the order *is* the name-collision precedence. That order differs by kind: subagents
# rank project over user, skills and commands the reverse; only subagents have the --agents
# session scope; commands have no managed/enterprise location.


def _standalone(
    subdir: ArtifactSubdir, glob: GlobPattern, name_from: Literal["stem", "parent"]
) -> StandaloneFile:
    """A standalone-file storage shape under `<root>/<subdir>` matching `glob`."""
    return StandaloneFile(subdir=subdir, glob=glob, name_from=name_from)


def _managed(shape: StandaloneFile) -> Location:
    """The managed (admin) location for `shape`, under `<managed>/.claude`."""
    return Location(
        scope=ScopeKind.managed,
        shareable=Shareability.admin,
        root="<managed>/.claude",
        storage=shape,
    )


def _project(shape: StandaloneFile) -> Location:
    """The project (committed) location for `shape`, under `.claude`."""
    return Location(
        scope=ScopeKind.project, shareable=Shareability.committed, root=".claude", storage=shape
    )


def _user(shape: StandaloneFile) -> Location:
    """The user (machine-local) location for `shape`, under `~/.claude`."""
    return Location(
        scope=ScopeKind.user, shareable=Shareability.machine_local, root="~/.claude", storage=shape
    )


def _plugin(shape: StandaloneFile) -> Location:
    """The plugin (bundled) location for `shape`, under the plugin root."""
    return Location(
        scope=ScopeKind.plugin, shareable=Shareability.bundled, root="<plugin>", storage=shape
    )


def _session() -> Location:
    """The session (ephemeral) `--agents` location — an in-memory flag, no disk root."""
    return Location(
        scope=ScopeKind.session,
        shareable=Shareability.ephemeral,
        root="(--agents)",
        storage=InMemoryFlag(flag="--agents"),
    )


_AGENT_FILE = _standalone("agents", "**/*.md", "stem")
_SKILL_FILE = _standalone("skills", "**/SKILL.md", "parent")
_COMMAND_FILE = _standalone("commands", "**/*.md", "stem")


class Subagent(FrozenModel):
    """The subagent artifact `.md` files, on a collision; locations are highest-precedence first
    (managed, then the `--agents` session scope, then project over user, then plugin)."""

    kind: Literal[ArtifactKind.agent] = ArtifactKind.agent
    resolution: Literal[ResolutionMode.collision] = ResolutionMode.collision
    locations: list[Location] = [
        _managed(_AGENT_FILE),
        _session(),
        _project(_AGENT_FILE),
        _user(_AGENT_FILE),
        _plugin(_AGENT_FILE),
    ]


class Skill(FrozenModel):
    """The skill `SKILL.md` files, on a collision; locations are highest-precedence first
    (managed, then user over project — the reverse of subagents — then plugin)."""

    kind: Literal[ArtifactKind.skill] = ArtifactKind.skill
    resolution: Literal[ResolutionMode.collision] = ResolutionMode.collision
    locations: list[Location] = [
        _managed(_SKILL_FILE),
        _user(_SKILL_FILE),
        _project(_SKILL_FILE),
        _plugin(_SKILL_FILE),
    ]


class Command(FrozenModel):
    """The command `.md` files, on a collision; locations are highest-precedence first (user,
    project, plugin) — commands have no managed/enterprise location."""

    kind: Literal[ArtifactKind.command] = ArtifactKind.command
    resolution: Literal[ResolutionMode.collision] = ResolutionMode.collision
    locations: list[Location] = [
        _user(_COMMAND_FILE),
        _project(_COMMAND_FILE),
        _plugin(_COMMAND_FILE),
    ]


class Hook(FrozenModel):
    """A hook is never a file of its own: it is a settings entry, a bundled hooks.json, or a
    key in a host component's frontmatter. Its scope follows where it is written."""

    kind: Literal[ArtifactKind.hook] = ArtifactKind.hook
    resolution: Literal[ResolutionMode.additive] = ResolutionMode.additive
    locations: list[Location] = [
        Location(
            scope=ScopeKind.user,
            shareable=Shareability.machine_local,
            root="~/.claude",
            storage=SettingsEntry(file="settings.json", key="hooks"),
        ),
        Location(
            scope=ScopeKind.project,
            shareable=Shareability.committed,
            root=".claude",
            storage=SettingsEntry(file="settings.json", key="hooks"),
        ),
        Location(
            scope=ScopeKind.project,
            shareable=Shareability.gitignored,
            root=".claude",
            storage=SettingsEntry(file="settings.local.json", key="hooks"),
        ),
        Location(
            scope=ScopeKind.managed,
            shareable=Shareability.admin,
            root="<managed>",
            storage=SettingsEntry(file="managed-settings.json", key="hooks"),
        ),
        Location(
            scope=ScopeKind.plugin,
            shareable=Shareability.bundled,
            root="<plugin>",
            storage=SettingsEntry(file="hooks/hooks.json", key=None),
        ),
        Location(
            scope=ScopeKind.component,
            shareable=Shareability.in_component,
            root="(host)",
            storage=HostFrontmatter(key="hooks"),
        ),
    ]


Artifact = Annotated[Subagent | Skill | Command | Hook, Field(discriminator="kind")]
"""A scoped artifact kind, dispatched on `kind`."""
