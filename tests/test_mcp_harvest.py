from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from pathlib import Path

import pytest
from fastmcp.client.auth import OAuth
from pydantic import JsonValue

from capabilities_discovery.catalog import CatalogMcpServer, McpTool
from capabilities_discovery.mcp_harvest import (
    cache_is_stale,
    read_mcp_cache,
    refresh_in_background,
    write_mcp_cache,
)
from capabilities_discovery.mcp_harvest import connect as connect_module
from capabilities_discovery.mcp_harvest.auth import bare_name, ensure_private_dir, server_auth
from capabilities_discovery.mcp_harvest.config import (
    all_server_configs,
    claude_json_scopes,
    manifest_server_configs,
    read_plugin_configs,
    resolve_placeholders,
    scope_server_configs,
    server_configs,
    user_config_subs,
)
from capabilities_discovery.mcp_harvest.connect import harvest_servers, to_mcp_tool
from capabilities_discovery.settings import get_settings


def test_resolve_substitutes_known_placeholders_and_recurses() -> None:
    cfg = {
        "command": "${CLAUDE_PLUGIN_ROOT}/bin/x",
        "args": ["-m", "${MISSING}"],
        "env": {"P": "${CLAUDE_PLUGIN_ROOT}"},
    }
    out = resolve_placeholders(cfg, {"CLAUDE_PLUGIN_ROOT": "/root"})
    assert out == {
        "command": "/root/bin/x",
        "args": ["-m", "${MISSING}"],  # unknown placeholder left as-is → server just won't connect
        "env": {"P": "/root"},
    }


def test_to_mcp_tool_maps_and_drops_invalid_params() -> None:
    tool = to_mcp_tool(
        "browser_navigate", "Navigate the browser", {"properties": {"url": {}, "bad name": {}}}
    )
    assert tool is not None
    assert tool.name == "browser_navigate"
    assert tool.params == ["url"]  # "bad name" (space) dropped, tool kept


def test_to_mcp_tool_rejects_invalid_name_and_truncates_description() -> None:
    assert to_mcp_tool("has space", "x", None) is None
    long = to_mcp_tool("t", "x" * 5000, None)
    assert long is not None and len(long.description) == 4000


def test_to_mcp_tool_preserves_full_input_schema() -> None:
    schema: dict = {
        "type": "object",
        "properties": {"url": {"type": "string"}, "timeout": {"type": "integer"}},
        "required": ["url"],
    }
    tool = to_mcp_tool("browser_navigate", "Navigate", schema)
    assert tool is not None
    assert tool.input_schema == schema
    assert tool.params == ["url", "timeout"]  # params still derived from properties


def test_to_mcp_tool_input_schema_none_when_absent() -> None:
    tool = to_mcp_tool("ping", "Ping a host", None)
    assert tool is not None
    assert tool.input_schema is None


def test_to_mcp_tool_drops_tool_with_oversized_input_schema() -> None:
    # security: a malicious/misbehaving server's list_tools() response must not be able to
    # inflate the on-disk cache without limit
    huge_schema: dict = {
        "type": "object",
        "properties": {f"p{i}": {"type": "string"} for i in range(5000)},
    }
    assert to_mcp_tool("browser_navigate", "Navigate", huge_schema) is None


def test_to_mcp_tool_drops_tool_with_too_many_params() -> None:
    huge_schema: dict = {"properties": {f"p{i}": {} for i in range(300)}}
    assert to_mcp_tool("browser_navigate", "Navigate", huge_schema) is None


def test_user_config_subs_keeps_scalars_drops_the_rest() -> None:
    subs = user_config_subs({"runtime": "wasm", "timeout": 30, "net": True, "tags": ["a"]})
    assert subs == {
        "user_config.runtime": "wasm",
        "user_config.timeout": "30",
        "user_config.net": "true",  # bool → json-style literal; list value dropped (non-scalar)
    }


def test_resolve_substitutes_user_config_placeholder() -> None:
    out = resolve_placeholders(
        {"args": ["--rt", "${user_config.runtime}"]}, {"user_config.runtime": "wasm"}
    )
    assert out == {"args": ["--rt", "wasm"]}


def test_read_plugin_configs_reads_options_only(tmp_path: Path) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text('{"pluginConfigs": {"x@local": {"options": {"runtime": "wasm"}}}}')
    configs = read_plugin_configs(settings)
    assert configs["x@local"].options == {"runtime": "wasm"}
    assert read_plugin_configs(tmp_path / "absent.json") == {}  # no settings → empty


def test_bare_name_strips_plugin_prefix() -> None:
    assert bare_name("plugin:github:github") == "github"
    assert bare_name("github") == "github"


def test_server_auth_stdio_and_unconfigured_get_none(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"github": {"env": "CAPDISC_TEST_TOKEN", "host": "h"}}',
    )
    try:
        assert server_auth("x", {"command": "run"}, oauth=True) is None  # stdio: never auth
        monkeypatch.delenv("CAPDISC_TEST_TOKEN", raising=False)
        assert server_auth("plugin:github:github", {"url": "https://h/mcp"}, oauth=False) is None
    finally:
        get_settings.cache_clear()


def test_server_auth_bearer_from_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"github": {"env": "CAPDISC_TEST_TOKEN", "host": "h"}}',
    )
    monkeypatch.setenv("CAPDISC_TEST_TOKEN", "tok-123")
    try:
        auth = server_auth("plugin:github:github", {"url": "https://h/mcp"}, oauth=False)
        assert auth == "tok-123"
    finally:
        get_settings.cache_clear()


def test_server_auth_bearer_unset_env_logs_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # a configured-but-unset bearer env var must be diagnosable, not a silent fall-through
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"github": {"env": "CAPDISC_TEST_TOKEN_UNSET", "host": "h"}}',
    )
    monkeypatch.delenv("CAPDISC_TEST_TOKEN_UNSET", raising=False)
    try:
        with caplog.at_level(logging.WARNING):
            auth = server_auth("plugin:github:github", {"url": "https://h/mcp"}, oauth=False)
        assert auth is None
        assert "CAPDISC_TEST_TOKEN_UNSET" in caplog.text
    finally:
        get_settings.cache_clear()


def test_server_auth_bearer_wins_over_oauth_when_both_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"github": {"env": "CAPDISC_TEST_TOKEN", "host": "h"}}',
    )
    monkeypatch.setenv("CAPDISC_TEST_TOKEN", "tok-123")
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_OAUTH_CLIENTS",
        '{"github": {"client_id": "abc", "host": "h", "scopes": []}}',
    )
    monkeypatch.setenv("CAPABILITIES_DISCOVERY_OAUTH_TOKEN_DIR", str(tmp_path / "tokens"))
    try:
        auth = server_auth("plugin:github:github", {"url": "https://h/mcp"}, oauth=True)
        assert auth == "tok-123"
    finally:
        get_settings.cache_clear()


def test_server_auth_bearer_rejected_when_host_mismatches(monkeypatch: pytest.MonkeyPatch) -> None:
    # a same-named server pointed at a different host must never receive the credential
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"github": {"env": "CAPDISC_TEST_TOKEN", "host": "api.githubcopilot.com"}}',
    )
    monkeypatch.setenv("CAPDISC_TEST_TOKEN", "tok-123")
    try:
        auth = server_auth("plugin:evil:github", {"url": "https://evil.example/mcp"}, oauth=False)
        assert auth is None
    finally:
        get_settings.cache_clear()


def test_server_auth_rejects_non_https_non_local(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"github": {"env": "CAPDISC_TEST_TOKEN", "host": "h"}}',
    )
    monkeypatch.setenv("CAPDISC_TEST_TOKEN", "tok-123")
    try:
        assert server_auth("plugin:github:github", {"url": "http://h/mcp"}, oauth=False) is None
    finally:
        get_settings.cache_clear()


def test_server_auth_allows_http_over_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_BEARER_ENV",
        '{"dev": {"env": "CAPDISC_TEST_TOKEN", "host": "localhost"}}',
    )
    monkeypatch.setenv("CAPDISC_TEST_TOKEN", "tok-123")
    try:
        auth = server_auth("dev", {"url": "http://localhost:8000/mcp"}, oauth=False)
        assert auth == "tok-123"
    finally:
        get_settings.cache_clear()


def test_server_auth_oauth_client_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_OAUTH_CLIENTS",
        '{"github": {"client_id": "abc", "host": "h", "scopes": ["read:user"]}}',
    )
    monkeypatch.setenv("CAPABILITIES_DISCOVERY_OAUTH_TOKEN_DIR", str(tmp_path / "tokens"))
    try:
        assert server_auth("plugin:github:github", {"url": "https://h/mcp"}, oauth=False) is None
        auth = server_auth("plugin:github:github", {"url": "https://h/mcp"}, oauth=True)
        assert isinstance(auth, OAuth)
        assert (tmp_path / "tokens").stat().st_mode & 0o777 == 0o700
    finally:
        get_settings.cache_clear()


def test_server_auth_oauth_rejected_when_host_mismatches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv(
        "CAPABILITIES_DISCOVERY_MCP_OAUTH_CLIENTS",
        '{"github": {"client_id": "abc", "host": "api.githubcopilot.com", "scopes": []}}',
    )
    monkeypatch.setenv("CAPABILITIES_DISCOVERY_OAUTH_TOKEN_DIR", str(tmp_path / "tokens"))
    try:
        auth = server_auth("plugin:evil:github", {"url": "https://evil.example/mcp"}, oauth=True)
        assert auth is None
    finally:
        get_settings.cache_clear()


def test_ensure_private_dir_fixes_preexisting_loose_permissions(tmp_path: Path) -> None:
    loose = tmp_path / "tokens"
    loose.mkdir(mode=0o755)
    ensure_private_dir(loose)
    assert loose.stat().st_mode & 0o777 == 0o700


def test_manifest_server_configs_inline_map(tmp_path: Path) -> None:
    manifest = tmp_path / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text(
        '{"name": "p", "mcpServers": {"dq": {"command": "${CLAUDE_PLUGIN_ROOT}/x"}}}'
    )
    assert manifest_server_configs(tmp_path) == {"dq": {"command": "${CLAUDE_PLUGIN_ROOT}/x"}}


def test_manifest_server_configs_path_forms(tmp_path: Path) -> None:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "servers.json").write_text('{"mcpServers": {"a": {"command": "x"}}}')
    manifest = tmp_path / ".claude-plugin" / "plugin.json"
    manifest.write_text('{"name": "p", "mcpServers": "./servers.json"}')
    assert manifest_server_configs(tmp_path) == {"a": {"command": "x"}}
    manifest.write_text('{"name": "p", "mcpServers": ["./servers.json", "./absent.json"]}')
    assert manifest_server_configs(tmp_path) == {"a": {"command": "x"}}  # missing file skipped


def test_manifest_server_configs_rejects_path_traversal(tmp_path: Path) -> None:
    # security: a manifest's declared mcpServers path must stay inside the plugin's own install
    # dir — a plugin must never be able to read an arbitrary file (e.g. ~/.claude.json) via ../
    # or an absolute path and have its contents harvested as if they were the plugin's servers.
    outside = tmp_path / "outside.json"
    outside.write_text('{"mcpServers": {"evil": {"command": "sh"}}}')
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / ".claude-plugin").mkdir(parents=True)
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"

    manifest.write_text('{"name": "p", "mcpServers": "../outside.json"}')
    assert manifest_server_configs(plugin_dir) == {}

    manifest.write_text(f'{{"name": "p", "mcpServers": {str(outside)!r}}}')
    assert manifest_server_configs(plugin_dir) == {}


def test_manifest_server_configs_absent_or_undeclared(tmp_path: Path) -> None:
    assert manifest_server_configs(tmp_path) == {}  # no manifest at all
    manifest = tmp_path / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir()
    manifest.write_text('{"name": "p"}')
    assert manifest_server_configs(tmp_path) == {}  # manifest without mcpServers


def test_server_configs_accepts_wrapped_and_flat() -> None:
    assert server_configs('{"mcpServers": {"a": {"command": "x"}}}') == {"a": {"command": "x"}}
    assert server_configs('{"a": {"command": "x"}}') == {"a": {"command": "x"}}
    assert server_configs("not json at all") == {}


def test_repo_committed_mcp_json_is_not_harvested(tmp_path: Path) -> None:
    # security: a repo-committed .mcp.json is untrusted — connecting would spawn its command,
    # so it must never enter the harvest set (only the user's own ~/.claude.json servers do).
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".mcp.json").write_text('{"mcpServers": {"evil": {"command": "sh", "args": ["-c"]}}}')
    assert scope_server_configs(proj, tmp_path / "absent.json") == {}
    assert all_server_configs(tmp_path / "no-plugins", proj, tmp_path / "absent.json") == []


def test_claude_json_scopes_splits_user_global_and_project_private(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    cj = tmp_path / ".claude.json"
    cj.write_text(
        '{"mcpServers": {"glob": {"command": "g"}}, '
        '"projects": {"' + str(proj.resolve()) + '": {"mcpServers": {"priv": {"command": "p"}}}}}'
    )
    user, private = claude_json_scopes(cj, proj)
    assert user == {"glob": {"command": "g"}}
    assert private == {"priv": {"command": "p"}}
    assert claude_json_scopes(cj, tmp_path / "other")[1] == {}  # no matching project → no private
    assert claude_json_scopes(tmp_path / "absent.json", proj) == ({}, {})  # no file → both empty


def test_scope_precedence_local_over_user(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    cj = tmp_path / ".claude.json"
    cj.write_text(
        '{"mcpServers": {"s": {"command": "user"}, "u": {"command": "user-only"}}, '
        '"projects": {"' + str(proj.resolve()) + '": {"mcpServers": {"s": {"command": "local"}}}}}'
    )
    out = scope_server_configs(proj, cj)
    assert out["s"] == {"command": "local"}  # project-private (local) > user on a name clash
    assert out["u"] == {"command": "user-only"}  # user-only server still surfaces


def test_scope_resolves_project_dir_placeholder(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    cj = tmp_path / ".claude.json"
    cj.write_text('{"mcpServers": {"s": {"args": ["${CLAUDE_PROJECT_DIR}/x"]}}}')
    out = scope_server_configs(proj, cj)
    assert out["s"]["args"] == [str(proj) + "/x"]


def test_all_server_configs_keys_scope_servers_by_plain_name(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    cj = tmp_path / ".claude.json"
    cj.write_text('{"mcpServers": {"gh": {"command": "x"}}}')
    out = all_server_configs(tmp_path / "no-plugins", proj, cj)
    assert out == [("gh", {"command": "x"})]  # no plugins → just scope servers, plain-named


def test_cache_is_stale_on_missing_and_aged_out(tmp_path: Path) -> None:
    cache = tmp_path / "mcp-tools.json"
    assert cache_is_stale(cache)  # missing → stale
    cache.write_text("[]")
    assert not cache_is_stale(cache, ttl_seconds=3600)  # just written → fresh
    aged = time.time() - 7200
    os.utime(cache, (aged, aged))
    assert cache_is_stale(cache, ttl_seconds=3600)  # 2h old past a 1h ttl → stale


def test_refresh_in_background_writes_cache_and_guards_concurrent_runs(tmp_path: Path) -> None:
    cache = tmp_path / "mcp-tools.json"
    # no plugins, no project file, no ~/.claude.json → zero servers → a no-op harvest (no network)
    thread = refresh_in_background(
        plugins_root=tmp_path / "no-plugins",
        path=cache,
        project_dir=tmp_path / "no-project",
        claude_json=tmp_path / "absent.json",
    )
    assert thread is not None
    thread.join(timeout=10)
    assert read_mcp_cache(cache) == []  # ran to completion and wrote the (empty) cache
    assert not cache_is_stale(cache, ttl_seconds=3600)  # freshly written → not stale


def test_harvest_runs_servers_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _slow_harvest_one(
        name: str, config: dict[str, JsonValue], auth: object = None
    ) -> list[McpTool]:
        await asyncio.sleep(0.2)
        return []

    monkeypatch.setattr(connect_module, "harvest_one", _slow_harvest_one)
    configs: list[tuple[str, dict[str, JsonValue]]] = [
        (f"srv{i}", {"command": "x"}) for i in range(6)
    ]
    start = time.monotonic()
    cards = asyncio.run(harvest_servers(configs))
    elapsed = time.monotonic() - start
    assert len(cards) == 6
    # sequential would take 6 * 0.2s = 1.2s; concurrent (bounded, well under the limit) is ~0.2s
    assert elapsed < 0.6


def test_harvest_dedupes_first_occurrence_regardless_of_completion_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _tagged_harvest_one(
        name: str, config: dict[str, JsonValue], auth: object = None
    ) -> list[McpTool]:
        # the later duplicate "finishes" first — first-occurrence-wins must not depend on this
        await asyncio.sleep(0.02 if config["tag"] == "first" else 0.0)
        return [McpTool(name=str(config["tag"]), description="d", params=[])]

    monkeypatch.setattr(connect_module, "harvest_one", _tagged_harvest_one)
    configs: list[tuple[str, dict[str, JsonValue]]] = [
        ("dup", {"tag": "first"}),
        ("dup", {"tag": "second"}),
    ]
    cards = asyncio.run(harvest_servers(configs))
    assert len(cards) == 1
    assert cards[0].tools[0].name == "first"


def test_cache_write_survives_concurrent_writers_in_one_process(tmp_path: Path) -> None:
    path = tmp_path / "mcp-tools.json"
    server = CatalogMcpServer(id="mcp.a", ref="a", description="the server", tools=[])
    errors: list[BaseException] = []

    def _write() -> None:
        try:
            write_mcp_cache([server], path)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=_write) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []  # each thread's temp path must be its own, not just the pid's
    assert read_mcp_cache(path) == [server]


def test_cache_round_trips(tmp_path: Path) -> None:
    server = CatalogMcpServer(
        id="mcp.pw",
        ref="playwright",
        description="An MCP server.",
        tools=[McpTool(name="browser_click", description="Click an element", params=["element"])],
    )
    path = tmp_path / "mcp-tools.json"
    write_mcp_cache([server], path)
    assert read_mcp_cache(path) == [server]
    assert read_mcp_cache(tmp_path / "absent.json") == []  # no cache yet → empty


def test_cache_write_is_atomic_no_partial_read_and_no_tmp_leftover(tmp_path: Path) -> None:
    path = tmp_path / "mcp-tools.json"
    old = CatalogMcpServer(id="mcp.a", ref="a", description="the old server", tools=[])
    new = CatalogMcpServer(id="mcp.b", ref="b", description="the new server", tools=[])
    write_mcp_cache([old], path)

    real_replace = Path.replace
    seen_during_replace: list[CatalogMcpServer] = []

    def _spy_replace(self: Path, target: Path) -> Path:
        # a reader racing the write must see either the old file or the new one, never a
        # truncated one — check right before the rename actually lands
        seen_during_replace.extend(read_mcp_cache(path))
        return real_replace(self, target)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "replace", _spy_replace)
        write_mcp_cache([new], path)

    assert seen_during_replace == [old]  # reader mid-write saw the old cache intact
    assert read_mcp_cache(path) == [new]  # write completed
    assert list(tmp_path.glob("*.tmp-*")) == []  # no leftover temp file
