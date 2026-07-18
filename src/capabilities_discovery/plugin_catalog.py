from __future__ import annotations

from pathlib import Path

from pydantic import Field, TypeAdapter, ValidationError

from .base import InputModel
from .catalog import CatalogPlugin, McpServerRef, PluginRef, SkillRef, Tag, catalog_id
from .discovery import skill_ref
from .mcp_catalog import SERVER_REF

# one place a plugin name becomes a ref
_PLUGIN_REF: TypeAdapter[PluginRef] = TypeAdapter(PluginRef)
_TAG: TypeAdapter[Tag] = TypeAdapter(Tag)  # one place a keyword becomes a tag
_INSTALLED = "installed_plugins.json"
_MANIFEST = ".claude-plugin/plugin.json"
_MCP_CONFIG = ".mcp.json"
_MCP_WRAPPER_KEY = "mcpServers"


class _PluginManifest(InputModel):
    """The `.claude-plugin/plugin.json` of one installed plugin — name, description, keywords."""

    name: str | None = None
    description: str | None = None
    keywords: list[str] = []


class _InstalledEntry(InputModel):
    install_path: Path | None = Field(default=None, alias="installPath")


class _InstalledPlugins(InputModel):
    """The `installed_plugins.json` registry: each `name@marketplace` key maps to its installs."""

    plugins: dict[str, list[_InstalledEntry]] = {}


class _OpaqueServer(InputModel):
    """One `.mcp.json` server entry, modeled empty: `InputModel` is `extra="ignore"`, so validation
    parses and drops the command/url/headers/credentials. Only the name (map key) survives."""


class _McpConfig(InputModel):
    """The `mcpServers`-wrapped `.mcp.json` shape; the flat shape is that same map at top level."""

    mcpServers: dict[str, _OpaqueServer] = {}


_INSTALLED_ADAPTER = TypeAdapter(_InstalledPlugins)
_MANIFEST_ADAPTER = TypeAdapter(_PluginManifest)
_MCP_WRAPPED_ADAPTER = TypeAdapter(_McpConfig)
_MCP_FLAT_ADAPTER = TypeAdapter(dict[str, _OpaqueServer])


def _first_install_path(installs: list[_InstalledEntry]) -> Path | None:
    """Pick a plugin's install directory from its registry records.

    Args:
        installs: A plugin's install records; a registry can list several and some carry no path.

    Returns:
        The first record's install directory, or None if none carries one.
    """
    return next((entry.install_path for entry in installs if entry.install_path), None)


def _skill_refs(install_path: Path) -> list[SkillRef]:
    """Derive the skill refs a plugin bundles from its `skills/*/SKILL.md` files.

    Derived the same way the skill index derives them, so these refs join to the plugin's
    `CatalogSkill` entries.

    Args:
        install_path: The plugin's install directory; its `skills/` tree is walked.

    Returns:
        The bundled skill refs, de-duplicated in first-seen order.
    """
    refs: list[SkillRef] = []
    for skill_md in sorted((install_path / "skills").rglob("SKILL.md")):
        ref = skill_ref(skill_md)
        if ref and ref not in refs:
            refs.append(ref)
    return refs


def _mcp_refs(install_path: Path) -> list[McpServerRef]:
    """Derive the MCP server refs a plugin declares in its `.mcp.json`.

    Only the server names (keys) are kept; `_OpaqueServer` drops the values, so a
    command/URL/credential never lands on a card. The file comes in two shapes — a `mcpServers`
    wrapper or the servers map at the top level — so the wrapper is tried first, falling back to
    the flat map.

    Args:
        install_path: The plugin's install directory holding `.mcp.json`.

    Returns:
        The declared server refs, de-duplicated in first-seen order; `[]` if the file is absent,
        unparseable, or holds no valid names.
    """
    try:
        raw = (install_path / _MCP_CONFIG).read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        servers = _MCP_WRAPPED_ADAPTER.validate_json(
            raw
        ).mcpServers or _MCP_FLAT_ADAPTER.validate_json(raw)
    except ValidationError:
        return []
    refs: list[McpServerRef] = []
    for name in servers:
        if name == _MCP_WRAPPER_KEY:
            continue
        try:
            ref = SERVER_REF.validate_python(name)
        except ValidationError:
            continue
        if ref not in refs:
            refs.append(ref)
    return refs


def _tags(keywords: list[str]) -> list[Tag]:
    """Fold a plugin's keywords into valid `Tag`s for lexical recall.

    Each keyword goes through the `Tag` normalizer, the one slug owner.

    Args:
        keywords: The plugin's declared keywords.

    Returns:
        The normalized tags, de-duplicated in first-seen order, dropping any that don't survive
        slugging.
    """
    out: list[Tag] = []
    for kw in keywords:
        try:
            tag = _TAG.validate_python(kw)
        except ValidationError:
            continue
        if tag not in out:
            out.append(tag)
    return out


def _plugin_card(
    plugin_key: str, manifest: _PluginManifest, install_path: Path
) -> CatalogPlugin | None:
    """Build one plugin card, including the skills and MCP servers it bundles.

    Args:
        plugin_key: The registry key `name@marketplace`; the marketplace suffix is dropped (and
            the `name` field preferred over it) so the ref is the bare plugin name.
        manifest: The plugin's parsed manifest; a plugin with no description is skipped.
        install_path: The plugin's install directory, scanned for bundled skills and servers.

    Returns:
        The card, or None when the manifest has no description or the fields don't validate.
    """
    if not manifest.description:
        return None
    try:
        ref = _PLUGIN_REF.validate_python(manifest.name or plugin_key.split("@", 1)[0])
        return CatalogPlugin(
            id=catalog_id("plugin", ref),
            ref=ref,
            description=manifest.description,
            tags=_tags(manifest.keywords),
            skills=_skill_refs(install_path),
            mcp_servers=_mcp_refs(install_path),
        )
    except ValidationError:
        return None


def _read_manifest(install_path: Path) -> _PluginManifest | None:
    """Read one plugin's `.claude-plugin/plugin.json` manifest.

    Args:
        install_path: The plugin's install directory.

    Returns:
        The parsed manifest, or None when the file is missing or unparseable.
    """
    try:
        raw = (install_path / _MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return _MANIFEST_ADAPTER.validate_json(raw)
    except ValidationError:
        return None


def _read_registry(plugins_root: Path) -> _InstalledPlugins | None:
    """Read the installed-plugins registry.

    Args:
        plugins_root: Root holding `installed_plugins.json`.

    Returns:
        The parsed registry, or None when the file is missing or unparseable.
    """
    try:
        raw = (plugins_root / _INSTALLED).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return _INSTALLED_ADAPTER.validate_json(raw)
    except ValidationError:
        return None


def installed_plugins(plugins_root: Path) -> dict[str, Path]:
    """Map each installed plugin to its install directory.

    The source for reading a plugin's bundled config (e.g. its `.mcp.json`).

    Args:
        plugins_root: Root holding `installed_plugins.json`.

    Returns:
        `{name@marketplace: install_dir}`, omitting plugins whose records carry no path; `{}`
        when the registry is missing.
    """
    registry = _read_registry(plugins_root)
    if registry is None:
        return {}
    found: dict[str, Path] = {}
    for key, installs in registry.plugins.items():
        install_path = _first_install_path(installs)
        if install_path is not None:
            found[key] = install_path
    return found


def installed_plugin_dirs(plugins_root: Path) -> list[Path]:
    """List every plugin install directory, for `ScopeRoots.discover(plugin_dirs=…)`.

    Feeds the scan so plugin-bundled skills are indexed. These are scan roots only — never
    indexed into a card, since an install path is a local absolute path.

    Args:
        plugins_root: Root holding `installed_plugins.json`.

    Returns:
        The install directories, de-duplicated in first-seen order.
    """
    seen: list[Path] = []
    for path in installed_plugins(plugins_root).values():
        if path not in seen:
            seen.append(path)
    return seen


def enumerate_plugins_with_paths(plugins_root: Path) -> list[tuple[CatalogPlugin, Path]]:
    """Enumerate installed plugins as catalog cards, paired with the install directory each was
    built from.

    The install path a card actually came from — not re-derived later by matching the card's
    ref back against the registry keys, which can mismatch (and silently drop the plugin) when a
    plugin's manifest `name` differs from its registry key.

    Args:
        plugins_root: Root holding `installed_plugins.json`.

    Returns:
        One `(card, install_path)` per plugin with a usable manifest, de-duplicated by id; `[]`
        if the registry is missing or unreadable.
    """
    registry = _read_registry(plugins_root)
    if registry is None:
        return []

    cards: list[tuple[CatalogPlugin, Path]] = []
    seen: set[str] = set()
    for plugin_key, installs in registry.plugins.items():
        install_path = _first_install_path(installs)
        if install_path is None:
            continue
        manifest = _read_manifest(install_path)
        if manifest is None:
            continue
        card = _plugin_card(plugin_key, manifest, install_path)
        # dedupe by id, not ref: two distinct refs can still truncate to the same catalog_id
        if card is None or card.id in seen:
            continue
        seen.add(card.id)
        cards.append((card, install_path))
    return cards


def enumerate_plugins(plugins_root: Path) -> list[CatalogPlugin]:
    """Enumerate installed plugins as catalog cards.

    Reads each plugin's manifest for its description and keywords. Never executes plugin code.

    Args:
        plugins_root: Root holding `installed_plugins.json`.

    Returns:
        One card per plugin with a usable manifest, de-duplicated by ref; `[]` if the registry
        is missing or unreadable.
    """
    return [card for card, _ in enumerate_plugins_with_paths(plugins_root)]
