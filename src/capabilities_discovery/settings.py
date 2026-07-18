from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from .base import InputModel
from .hooks import EnvVarName

ExtraSourceDir = Annotated[
    Path,
    Field(
        title="Extra source directory",
        description=(
            "A filesystem directory contributed to discovery as a cataloged source. "
            "These dirs are cataloged as discovery data only — never honored as active "
            "hooks or MCP servers; that boundary is enforced upstream."
        ),
        examples=["/home/user/my-org-skills", "/opt/shared-agents"],
    ),
]
ExactHostname = Annotated[
    str,
    Field(
        title="Exact hostname",
        description="Hostname a server's url must resolve to before a credential is attached.",
        examples=["api.githubcopilot.com"],
    ),
]
OAuthClientId = Annotated[
    str,
    Field(
        title="OAuth client id",
        description="Pre-registered OAuth client id for an authorization server without dynamic "
        "client registration.",
        examples=["abc123"],
    ),
]
OAuthScope = Annotated[
    str,
    Field(
        title="OAuth scope",
        description="One OAuth scope requested for a pre-registered client.",
        examples=["read:user"],
    ),
]
CallbackPort = Annotated[
    int,
    Field(
        title="OAuth callback port",
        description="Fixed localhost callback port for an OAuth app registered with an exact "
        "redirect URL.",
        ge=1,
        le=65535,
        examples=[8765],
    ),
]
PluginsRootPath = Annotated[
    Path,
    Field(title="Plugins root", description="Root holding installed_plugins.json."),
]
ClaudeJsonPath = Annotated[
    Path,
    Field(
        title="Claude JSON path",
        description="User/project MCP server config (~/.claude.json).",
    ),
]
UserSettingsPath = Annotated[
    Path,
    Field(
        title="User settings path",
        description="User settings.json, read for plugin user_config options.",
    ),
]
McpCachePath = Annotated[
    Path,
    Field(title="MCP cache path", description="Tool-enriched MCP server cache."),
]
ReportDirPath = Annotated[
    Path,
    Field(
        title="Report directory",
        description="Directory the discovery report (json + html) is written to.",
    ),
]
OAuthTokenDirPath = Annotated[
    Path,
    Field(
        title="OAuth token directory",
        description="OAuth token cache for `--oauth` harvests. Plaintext files, dir mode 0700.",
    ),
]

DEFAULT_CONFIG_PATH: Path = Path.home() / ".claude" / "capabilities-discovery" / "config.json"
DEFAULT_YAML_CONFIG_PATH: Path = Path.home() / ".claude" / "capabilities-discovery" / "config.yaml"


class McpBearerAuth(InputModel):
    """A bearer credential for one HTTP MCP server, bound to the exact host it may be sent to.

    Keyed by bare server name (matched case-insensitively), but the name alone never grants the
    credential — a plugin cannot receive it by simply declaring a same-named server, since the
    server's own `url` must resolve to `host` before the token is attached."""

    env: EnvVarName
    host: ExactHostname


class McpOAuthClient(InputModel):
    """A pre-registered OAuth client for one HTTP MCP server, used by the opt-in `--oauth`
    harvest. Required for authorization servers without dynamic client registration (GitHub).
    The secret itself is never stored here — only the name of the env var that holds it.

    Bound to `host` for the same reason as `McpBearerAuth`: the bare-name key alone must never
    be enough for a same-named server to receive the client credentials."""

    client_id: OAuthClientId
    host: ExactHostname
    scopes: list[OAuthScope] = Field(default_factory=list)
    secret_env: EnvVarName | None = Field(
        default=None,
        description="Name of the env var holding the client secret; omit for PKCE-only clients.",
    )
    callback_port: CallbackPort | None = Field(
        default=None,
        description="Omit to use a random free port.",
    )


class DiscoverySettings(BaseSettings):
    """Paths and source dirs the discovery layer reads from and writes to.

    Precedence (highest to lowest): init args > env vars > .env file > JSON config file >
    YAML config file > defaults. Env vars use the ``CAPABILITIES_DISCOVERY_`` prefix; the
    .env, JSON, and YAML files are all read from ``~/.claude/capabilities-discovery/`` (any
    or all may be absent = empty, never an error) — never from the process's current working
    directory, so running this tool from inside an untrusted checkout can't override
    ``claude_json``/``plugins_root`` via a repo-committed ``.env`` and defeat the harvest's own
    exclusion of untrusted project config (see ``scope_server_configs``). For a scalar or list
    field set in both JSON and YAML, the JSON value wins outright. For a dict-typed field
    (``mcp_bearer_env``, ``mcp_oauth_clients``), the two files are deep-merged instead — keys
    present in both compose recursively, and only an actual leaf conflict picks JSON's value.
    Subclasses may override ``model_config`` to change the prefix or config file paths.

    ``extra_scan_dirs`` and ``extra_plugin_dirs`` are cataloged as discovery data only —
    never honored as active hooks or MCP servers; that boundary is enforced upstream.
    """

    model_config = SettingsConfigDict(
        env_prefix="CAPABILITIES_DISCOVERY_",
        env_file=DEFAULT_CONFIG_PATH.parent / ".env",
        extra="ignore",
        json_file=DEFAULT_CONFIG_PATH,
        yaml_file=DEFAULT_YAML_CONFIG_PATH,
    )

    extra_scan_dirs: list[ExtraSourceDir] = Field(default_factory=list[ExtraSourceDir])
    extra_plugin_dirs: list[ExtraSourceDir] = Field(default_factory=list[ExtraSourceDir])

    # Locations discovery reads from / writes to; each independently overridable.
    plugins_root: PluginsRootPath = Field(
        default_factory=lambda: Path.home() / ".claude" / "plugins"
    )
    claude_json: ClaudeJsonPath = Field(default_factory=lambda: Path.home() / ".claude.json")
    user_settings: UserSettingsPath = Field(
        default_factory=lambda: Path.home() / ".claude" / "settings.json"
    )
    mcp_cache: McpCachePath = Field(
        default_factory=lambda: (
            Path.home() / ".claude" / "capabilities-discovery" / "mcp-tools.json"
        )
    )
    report_dir: ReportDirPath = Field(
        default_factory=lambda: Path.home() / ".claude" / "capabilities-discovery"
    )

    # Auth for HTTP MCP servers the anonymous probe can't reach. Keyed by bare server name
    # (the last segment of the ref, e.g. "github" for plugin:github:github). The name is only
    # a lookup key, not a trust boundary — `host` is what actually gates the credential.
    mcp_bearer_env: dict[str, McpBearerAuth] = Field(
        default_factory=dict,
        description="Server name → {env, host} for a bearer token, e.g. "
        '{"github": {"env": "GH_TOKEN", "host": "api.githubcopilot.com"}}. Non-interactive; '
        "used whenever the var is set and the server's url matches host.",
    )
    mcp_oauth_clients: dict[str, McpOAuthClient] = Field(
        default_factory=dict,
        description="Server name → pre-registered OAuth client, used only under `--oauth` "
        "(interactive browser flow; never in background paths).",
    )
    oauth_token_dir: OAuthTokenDirPath = Field(
        default_factory=lambda: Path.home() / ".claude" / "capabilities-discovery" / "oauth-tokens"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,  # noqa: ARG003
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            YamlConfigSettingsSource(settings_cls),
        )


@cache
def get_settings() -> DiscoverySettings:
    """The process-wide settings, resolved lazily on first use from env/.env/JSON/YAML config.

    Lazy so importing the package never reads config files or raises on a malformed
    environment, and so configuration applied before first use is honored. The default
    source for discovery/report/mcp path defaults."""
    return DiscoverySettings()
