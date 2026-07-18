from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from fastmcp.client.auth import OAuth
from key_value.aio.stores.filetree import FileTreeStore

from ..settings import get_settings
from .config import scalar_str
from .types import ServerConfig

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def bare_name(ref: str) -> str:
    """The bare server name from a full ref: `plugin:github:github` → `github`."""
    return ref.rsplit(":", 1)[-1]


def _host_of(url: str) -> str | None:
    """The lowercased hostname of a url, or None when it has none."""
    hostname = urlsplit(url).hostname
    return hostname.lower() if hostname else None


def _safe_for_auth(url: str) -> bool:
    """Whether credentials may be attached to `url` at all: https, or plaintext http only to
    a loopback host (local dev servers) — never a bearer token or OAuth client secret over an
    unencrypted connection to a real host."""
    scheme = urlsplit(url).scheme
    if scheme == "https":
        return True
    return scheme == "http" and _host_of(url) in _LOCAL_HOSTS


def _host_matches(url: str, expected_host: str) -> bool:
    """Whether `url` resolves to exactly `expected_host` (case-insensitive)."""
    return _host_of(url) == expected_host.lower()


def ensure_private_dir(path: Path) -> None:
    """Create `path` (with parents) and force it to mode 0700, whether newly created or
    pre-existing — `Path.mkdir(mode=...)` only applies to a directory it creates, so a
    pre-existing world-readable directory would otherwise silently hold plaintext OAuth
    tokens."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def server_auth(ref: str, config: ServerConfig, oauth: bool) -> str | OAuth | None:
    """Resolve auth for one HTTP server, or None to connect anonymously.

    A bearer token named in the settings' `mcp_bearer_env` always wins (non-interactive).
    Otherwise, when `oauth` is set and the settings pre-register a client for the server,
    the full browser flow runs, with tokens cached under `oauth_token_dir`. Stdio servers
    (no `url`) never get auth — their config already carries what they need.

    The bare server name is only a lookup key, never a trust boundary: a credential is
    attached only when the server's own `url` also matches the configured `host`, so a
    different (or malicious) server declared under the same bare name — e.g. by an
    installed plugin — cannot receive a credential meant for another server. Credentials
    are also refused entirely over a non-loopback plaintext connection.

    Args:
        ref: The server's full ref (`plugin:<plugin>:<server>` or a bare name).
        config: The server's spawn config.
        oauth: Whether the interactive OAuth flow is allowed for this run.

    Returns:
        A bearer token string, an `OAuth` flow handler, or None.
    """
    url = scalar_str(config.get("url"))
    if url is None:
        return None
    if not _safe_for_auth(url):
        logger.warning("refusing to attach credentials to non-HTTPS server %s", ref)
        return None
    name = bare_name(ref)
    settings = get_settings()
    bearer = settings.mcp_bearer_env.get(name)
    if bearer is not None:
        if not _host_matches(url, bearer.host):
            logger.warning(
                "refusing bearer token for %s: url host does not match configured %s",
                ref,
                bearer.host,
            )
        elif token := os.environ.get(bearer.env):
            return token
        else:
            logger.warning(
                "bearer env var %s is configured for %s but unset in this environment",
                bearer.env,
                ref,
            )
    client_conf = settings.mcp_oauth_clients.get(name) if oauth else None
    if client_conf is None:
        return None
    if not _host_matches(url, client_conf.host):
        logger.warning(
            "refusing OAuth client for %s: url host does not match configured %s",
            ref,
            client_conf.host,
        )
        return None
    token_dir = settings.oauth_token_dir
    ensure_private_dir(token_dir)
    return OAuth(
        mcp_url=url,
        scopes=client_conf.scopes,
        client_id=client_conf.client_id,
        client_secret=(os.environ.get(client_conf.secret_env) if client_conf.secret_env else None),
        token_storage=FileTreeStore(data_directory=token_dir),
        callback_port=client_conf.callback_port,
    )
