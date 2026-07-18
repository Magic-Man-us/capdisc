from __future__ import annotations

import json
from pathlib import Path

from capabilities_discovery.plugin_catalog import enumerate_plugins, enumerate_plugins_with_paths
from helpers import touch


def _install(
    root: Path,
    key: str,
    name: str,
    manifest: dict[str, object],
    skills: dict[str, str] | None = None,
    mcp_json: dict[str, object] | None = None,
) -> Path:
    install_path = root / "cache" / name
    touch(install_path / ".claude-plugin" / "plugin.json", json.dumps(manifest))
    for skill_name, body in (skills or {}).items():
        touch(install_path / "skills" / skill_name / "SKILL.md", body)
    if mcp_json is not None:
        touch(install_path / ".mcp.json", json.dumps(mcp_json))
    registry_path = root / "installed_plugins.json"
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.exists()
        else {"plugins": {}}
    )
    registry["plugins"][key] = [{"installPath": str(install_path), "version": "0.1.0"}]
    touch(registry_path, json.dumps(registry))
    return install_path


def test_enumerates_installed_plugins(tmp_path: Path) -> None:
    _install(
        tmp_path,
        "agentforge@local",
        "agentforge",
        {
            "name": "agentforge",
            "description": "Deterministic generator for Claude Code agents and skills.",
            "keywords": ["agents", "codegen", "claude-code"],
        },
    )
    cards = enumerate_plugins(tmp_path)
    assert [c.ref for c in cards] == ["agentforge"]
    assert cards[0].id == "plugin.agentforge"
    assert "claude-code" in cards[0].tags


def _skill_md(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n\nDo the thing, then stop."


def test_plugin_declares_the_skills_and_mcp_servers_it_bundles(tmp_path: Path) -> None:
    _install(
        tmp_path,
        "dq-toolkit@local",
        "dq-toolkit",
        {"name": "dq-toolkit", "description": "Local code and documentation search."},
        skills={
            "code-search": _skill_md("code-search", "Find where a symbol is defined."),
            "doc-search": _skill_md("doc-search", "Answer library questions from indexed docs."),
        },
        mcp_json={"mcpServers": {"dq": {"command": "dq-mcp"}}},
    )
    card = enumerate_plugins(tmp_path)[0]
    assert card.skills == ["code-search", "doc-search"]
    assert card.mcp_servers == ["dq"]


def test_mcp_servers_parse_the_top_level_shape(tmp_path: Path) -> None:
    # playwright/github ship `.mcp.json` as the servers map directly, with no `mcpServers` wrapper
    _install(
        tmp_path,
        "playwright@local",
        "playwright",
        {"name": "playwright", "description": "Browser automation server."},
        mcp_json={"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}},
    )
    assert enumerate_plugins(tmp_path)[0].mcp_servers == ["playwright"]


def test_mcp_server_values_never_leak_credentials(tmp_path: Path) -> None:
    # a plugin's `.mcp.json` values can carry tokens; only the server name (key) may be indexed
    _install(
        tmp_path,
        "github@local",
        "github",
        {"name": "github", "description": "Drive GitHub."},
        mcp_json={
            "github": {
                "url": "https://api.githubcopilot.com/mcp/",
                "headers": {"Authorization": "Bearer ${GITHUB_PERSONAL_ACCESS_TOKEN}"},
            }
        },
    )
    card = enumerate_plugins(tmp_path)[0]
    assert card.mcp_servers == ["github"]
    blob = card.model_dump_json()
    assert "Bearer" not in blob
    assert "githubcopilot" not in blob


def test_marketplace_suffix_is_stripped_from_the_ref(tmp_path: Path) -> None:
    _install(
        tmp_path,
        "github@claude-plugins-official",
        "github",
        {"name": "github", "description": "Drive GitHub from the CLI."},
    )
    assert enumerate_plugins(tmp_path)[0].ref == "github"


def test_plugin_without_description_is_skipped(tmp_path: Path) -> None:
    _install(tmp_path, "blank@local", "blank", {"name": "blank"})
    assert enumerate_plugins(tmp_path) == []


def test_missing_registry_returns_empty(tmp_path: Path) -> None:
    assert enumerate_plugins(tmp_path) == []


def test_paths_pair_up_even_when_manifest_name_differs_from_registry_key(tmp_path: Path) -> None:
    # the ref comes from manifest.name, not the registry key — pairing must use the same
    # install_path the card was actually built from, never re-derive it by matching the ref
    # back against a slugified key (which fails whenever they differ, as here)
    install_path = _install(
        tmp_path,
        "MyPlugin@some-marketplace",
        "my-plugin-dir",
        {"name": "My Actual Plugin", "description": "A plugin registered under another name."},
    )
    pairs = enumerate_plugins_with_paths(tmp_path)
    assert len(pairs) == 1
    card, path = pairs[0]
    assert card.ref == "my-actual-plugin"
    assert path == install_path
    assert enumerate_plugins(tmp_path) == [card]


def test_never_indexes_the_install_path(tmp_path: Path) -> None:
    # the install path is an absolute filesystem location; it must not leak into any card
    _install(
        tmp_path,
        "agentforge@local",
        "agentforge",
        {"name": "agentforge", "description": "Generate agents."},
    )
    for card in enumerate_plugins(tmp_path):
        blob = card.model_dump_json()
        assert "/home/" not in blob
        assert str(tmp_path) not in blob
