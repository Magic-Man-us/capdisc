from __future__ import annotations

from pathlib import Path

from pydantic import JsonValue, TypeAdapter, ValidationError

from ..base import InputModel
from ..plugin_catalog import installed_plugins
from ..settings import get_settings
from .types import ServerConfig, ServerMap

_MCP_CONFIG = ".mcp.json"

_SERVER_MAP: TypeAdapter[ServerMap] = TypeAdapter(ServerMap)


class _Wrapped(InputModel):
    """The `{"mcpServers": {...}}` shape; the flat shape is that same map at the top level."""

    mcpServers: ServerMap = {}


_WRAPPED: TypeAdapter[_Wrapped] = TypeAdapter(_Wrapped)


class _ManifestMcp(InputModel):
    """`mcpServers` in a plugin manifest — an inline map, or path(s) to `.mcp.json` files.

    A raw union, not a discriminated model: this mirrors an external plugin manifest's JSON,
    which carries no discriminator field to tag the three shapes with.
    """

    mcpServers: ServerMap | str | list[str] = {}


_MANIFEST_MCP: TypeAdapter[_ManifestMcp] = TypeAdapter(_ManifestMcp)
_PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"


class _PluginOptions(InputModel):
    """One plugin's `pluginConfigs` entry — only the non-sensitive `options` (sensitive values
    are kept in the keychain, not here)."""

    options: dict[str, JsonValue] = {}


class _Settings(InputModel):
    pluginConfigs: dict[str, _PluginOptions] = {}


_SETTINGS: TypeAdapter[_Settings] = TypeAdapter(_Settings)


class _ProjectScope(InputModel):
    """One `projects[<path>]` entry of `~/.claude.json`, narrowed to its private MCP servers."""

    mcpServers: ServerMap = {}


class _ClaudeJson(InputModel):
    """The slice of `~/.claude.json` holding MCP servers: the user-global `mcpServers` map and each
    project's private `projects[<path>].mcpServers`. Every other key is ignored."""

    mcpServers: ServerMap = {}
    projects: dict[str, _ProjectScope] = {}


_CLAUDE_JSON: TypeAdapter[_ClaudeJson] = TypeAdapter(_ClaudeJson)


def server_configs(raw: str) -> ServerMap:
    """Parse a `.mcp.json` body into its `{server_name: config}` map.

    Accepts both on-disk shapes — a `mcpServers` wrapper or the servers map at the top level.
    The wrapper is tried first, falling back to the flat map.

    Args:
        raw: Raw `.mcp.json` text, not a path.

    Returns:
        The server map, or `{}` when neither shape parses.
    """
    try:
        wrapped = _WRAPPED.validate_json(raw)
    except ValidationError:
        return {}
    if wrapped.mcpServers:
        return wrapped.mcpServers
    try:
        return _SERVER_MAP.validate_json(raw)
    except ValidationError:
        return {}


def scalar_str(value: JsonValue) -> str | None:
    """Render a JSON scalar as a `${...}` substitution string.

    Args:
        value: A user_config value of any JSON type.

    Returns:
        The string form (`bool` as `"true"`/`"false"`), or None for lists/objects/null,
        which have no scalar substitution.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def user_config_subs(options: dict[str, JsonValue]) -> dict[str, str]:
    """Build the `${user_config.KEY}` substitution map from a plugin's non-sensitive options.

    Sensitive options live in the keychain, never in settings.json, so they are absent here by
    design — the credential store is never read, and any sensitive placeholder is left unresolved.

    Args:
        options: A plugin's non-sensitive `options` mapping.

    Returns:
        `{"user_config.<key>": <scalar>}` for each scalar option; non-scalar options are skipped.
    """
    subs: dict[str, str] = {}
    for key, value in options.items():
        rendered = scalar_str(value)
        if rendered is not None:
            subs[f"user_config.{key}"] = rendered
    return subs


def read_plugin_configs(path: Path) -> dict[str, _PluginOptions]:
    """Read the `pluginConfigs` map (non-sensitive plugin options) from a settings.json.

    Args:
        path: Path to a settings.json file.

    Returns:
        The `pluginConfigs` map, or `{}` if the file is missing or unparseable.
    """
    try:
        return _SETTINGS.validate_json(path.read_text(encoding="utf-8")).pluginConfigs
    except (OSError, ValidationError):
        return {}


def resolve_placeholders(value: JsonValue, subs: dict[str, str]) -> JsonValue:
    """Substitute `${VAR}` placeholders through a JSON value, recursing into lists and objects.

    Args:
        value: Any JSON value; strings have placeholders replaced, containers are recursed.
        subs: `{var_name: replacement}` map of known placeholders.

    Returns:
        The value with known placeholders replaced. Unknown placeholders are left as-is — the
        server then simply fails to connect and is skipped downstream.
    """
    if isinstance(value, str):
        for var, replacement in subs.items():
            value = value.replace("${" + var + "}", replacement)
        return value
    if isinstance(value, list):
        return [resolve_placeholders(item, subs) for item in value]
    if isinstance(value, dict):
        return {key: resolve_placeholders(item, subs) for key, item in value.items()}
    return value


def manifest_server_configs(install_path: Path) -> ServerMap:
    """Extract a plugin manifest's declared MCP servers.

    Args:
        install_path: The plugin's install directory (holds `.claude-plugin/plugin.json`).

    Returns:
        The `{server_name: config}` map from the manifest's `mcpServers` — read inline, or from
        the `.mcp.json` file(s) it points at — or `{}` when absent, unparseable, or a declared
        path resolves outside the plugin's own install directory (rejected, not followed).
    """
    try:
        raw = (install_path / _PLUGIN_MANIFEST).read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        declared = _MANIFEST_MCP.validate_json(raw).mcpServers
    except ValidationError:
        return {}
    match declared:
        case dict():
            return declared
        case str():
            paths = [declared]
        case list():
            paths = declared
    base = install_path.resolve()
    servers: ServerMap = {}
    for rel in paths:
        target = install_path / rel
        if not target.resolve().is_relative_to(base):
            continue
        try:
            servers.update(server_configs(target.read_text(encoding="utf-8")))
        except OSError:
            continue
    return servers


def _plugin_server_configs(plugins_root: Path, project_dir: Path) -> list[tuple[str, ServerConfig]]:
    """Collect every plugin-provided MCP server, resolved and ready to spawn.

    Each server's `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}`, and the plugin's non-sensitive
    `${user_config.*}` options are substituted so the client can spawn it.

    Args:
        plugins_root: Root of installed plugins (holds `installed_plugins.json`).
        project_dir: Project root; resolves `${CLAUDE_PROJECT_DIR}` for the same project the
            scope-configured servers use, not necessarily the process cwd.

    Returns:
        `(full_ref, resolved_config)` pairs, where `full_ref` is `plugin:<plugin>:<server>` to
        match `claude mcp list` naming.
    """
    plugin_configs = read_plugin_configs(get_settings().user_settings)
    out: list[tuple[str, ServerConfig]] = []
    for key, install_path in installed_plugins(plugins_root).items():
        try:
            raw = (install_path / _MCP_CONFIG).read_text(encoding="utf-8")
        except OSError:
            raw = ""
        # a plugin declares servers in `.mcp.json`, its manifest's `mcpServers`, or both;
        # `.mcp.json` wins on a duplicate server name
        merged = manifest_server_configs(install_path) | server_configs(raw)
        if not merged:
            continue
        subs = {"CLAUDE_PLUGIN_ROOT": str(install_path), "CLAUDE_PROJECT_DIR": str(project_dir)}
        configured = plugin_configs.get(key)
        if configured is not None:
            subs.update(user_config_subs(configured.options))
        plugin = key.split("@", 1)[0]
        # resolve every field of every server through the shared helper, then key each by its
        # `plugin:<plugin>:<server>` ref (matching `claude mcp list` naming)
        resolved = _resolve_configs(merged, subs)
        out.extend((f"plugin:{plugin}:{server}", config) for server, config in resolved.items())
    return out


def _resolve_configs(configs: ServerMap, subs: dict[str, str]) -> ServerMap:
    """Apply `${VAR}` substitution to every field of every server config in a map.

    Args:
        configs: `{server_name: config}` map to resolve.
        subs: `{var_name: replacement}` map applied to each config field.

    Returns:
        A new map with the same keys and every field resolved.
    """
    return {
        name: {field: resolve_placeholders(item, subs) for field, item in config.items()}
        for name, config in configs.items()
    }


def claude_json_scopes(claude_json: Path, project_dir: Path) -> tuple[ServerMap, ServerMap]:
    """Read the user-global and project-private MCP server maps from `~/.claude.json`.

    Args:
        claude_json: Path to the `~/.claude.json` file.
        project_dir: Project whose private servers to find; the private map is
            `projects[<path>].mcpServers` for the entry whose path resolves to this dir.

    Returns:
        A `(user_global, project_private)` pair. Either is `{}` if absent; both are `{}` if the
        file is missing or unparseable.
    """
    try:
        parsed = _CLAUDE_JSON.validate_json(claude_json.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return {}, {}
    target = project_dir.resolve()
    private = next(
        (s.mcpServers for path, s in parsed.projects.items() if Path(path).resolve() == target),
        dict[str, ServerConfig](),
    )
    return parsed.mcpServers, private


def scope_server_configs(project_dir: Path, claude_json: Path) -> ServerMap:
    """Merge the trusted non-plugin MCP servers across scopes into one resolved map.

    The project's committed `.mcp.json` is deliberately excluded: connecting to a server spawns
    its command, and a repo-committed `.mcp.json` is untrusted input — auto-harvesting it would let
    a cloned repo run arbitrary code. Only the user's own servers in `~/.claude.json` (global and
    project-private) are harvested.

    Args:
        project_dir: Project root; selects the project-private servers and resolves
            `${CLAUDE_PROJECT_DIR}`.
        claude_json: Path to `~/.claude.json` for user-global and project-private servers.

    Returns:
        `{name: resolved_config}` merged across scopes. On a name clash, project-private (local)
        wins over user-global.
    """
    user, private = claude_json_scopes(claude_json, project_dir)
    merged = {**user, **private}
    return _resolve_configs(merged, {"CLAUDE_PROJECT_DIR": str(project_dir)})


def all_server_configs(
    plugins_root: Path, project_dir: Path, claude_json: Path
) -> list[tuple[str, ServerConfig]]:
    """Collect every MCP server to harvest, scope-configured and plugin-provided.

    Args:
        plugins_root: Root of installed plugins, for plugin-provided servers.
        project_dir: Project root, for project and local scope servers.
        claude_json: Path to `~/.claude.json`, for user and project-private servers.

    Returns:
        `(ref, resolved_config)` pairs: scope-configured servers (user, project, local) by plain
        name, plus plugin-provided servers by their `plugin:<p>:<s>` ref.
    """
    configs = list(scope_server_configs(project_dir, claude_json).items())
    configs += _plugin_server_configs(plugins_root, project_dir)
    return configs
