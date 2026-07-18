from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from capabilities_discovery.mcp_harvest import cache_is_stale, read_mcp_cache, write_mcp_cache
from capabilities_discovery.settings import get_settings


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Clear the settings cache around a test so env overrides are seen and never leak."""
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_env_override_applies_before_first_use(
    tmp_path: Path, fresh_settings: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "mcp-tools.json"
    fresh_settings.setenv("CAPABILITIES_DISCOVERY_MCP_CACHE", str(cache))
    assert get_settings().mcp_cache == cache


def test_cache_path_default_resolves_at_call_time(
    tmp_path: Path, fresh_settings: pytest.MonkeyPatch
) -> None:
    # the whole point of the lazy accessor: defaults must not be frozen at import
    cache = tmp_path / "mcp-tools.json"
    fresh_settings.setenv("CAPABILITIES_DISCOVERY_MCP_CACHE", str(cache))
    assert cache_is_stale()  # missing file counts as stale
    write_mcp_cache([])
    assert cache.exists()
    assert read_mcp_cache() == []
    assert not cache_is_stale()


def test_cwd_env_file_is_ignored(tmp_path: Path, fresh_settings: pytest.MonkeyPatch) -> None:
    # a cloned/untrusted repo's own .env must never override claude_json/plugins_root — only
    # ~/.claude/capabilities-discovery/.env (never the process cwd) is trusted for this
    (tmp_path / ".env").write_text(
        "CAPABILITIES_DISCOVERY_CLAUDE_JSON=/tmp/attacker-controlled-claude.json\n"
    )
    fresh_settings.chdir(tmp_path)
    assert get_settings().claude_json != Path("/tmp/attacker-controlled-claude.json")  # noqa: S108
