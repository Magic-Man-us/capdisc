from __future__ import annotations

import os
from pathlib import Path

import pytest

from capabilities_discovery.scope import (
    ArtifactKind,
    ScopeInventory,
    ScopeRoots,
    default_managed_dir,
    parse_frontmatter_hooks,
    parse_hooks,
    render_inventory,
    render_inventory_html,
)
from helpers import touch


def _agent(base: Path, name: str, body: str = "x") -> None:
    touch(base / "agents" / f"{name}.md", body)


def _skill(base: Path, name: str, body: str = "x") -> None:
    touch(base / "skills" / name / "SKILL.md", body)


def _names(inv: ScopeInventory) -> set[str]:
    return {a.name for a in inv.artifacts}


def test_walk_up_finds_every_claude_to_repo_root_nearest_wins(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _agent(tmp_path / ".claude", "rev", "ROOT")
    deep = tmp_path / "services" / "api"
    _agent(deep / ".claude", "rev", "NEAR")
    _agent(deep / ".claude", "near-only", "N")

    inv = ScopeInventory.scan(ScopeRoots.discover(start=deep))
    assert _names(inv) == {"rev", "near-only"}
    winner = next(a for a in inv.effective if a.name == "rev")
    assert winner.contents == "NEAR"  # closest to start wins


def test_skills_load_from_below_but_agents_do_not(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _skill(tmp_path / ".claude", "root-skill")
    _agent(tmp_path / ".claude", "root-agent")
    _skill(tmp_path / "sub" / ".claude", "nested-skill")
    _agent(tmp_path / "sub" / ".claude", "nested-agent")

    names = _names(ScopeInventory.scan(ScopeRoots.discover(start=tmp_path)))
    assert "nested-skill" in names  # skills scan downward
    assert "nested-agent" not in names  # agents do not


def test_noise_directories_are_pruned(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _skill(tmp_path / ".venv" / ".claude", "noise")
    _skill(tmp_path / "node_modules" / ".claude", "more-noise")
    assert _names(ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))) == set()


def test_noise_directories_are_never_descended_into(tmp_path: Path) -> None:
    # correctness (above) would pass even if a noise tree were fully walked then filtered
    # after; this proves the walk itself is pruned, not just its result
    (tmp_path / ".git").mkdir()
    _skill(tmp_path / "node_modules" / "pkg" / ".claude", "noise")
    _skill(tmp_path / "sub" / ".claude", "real")

    visited_roots: list[str] = []
    real_walk = os.walk

    def _spying_walk(top: object, **kwargs: object) -> object:
        for root, dirnames, files in real_walk(top, **kwargs):  # type: ignore[arg-type]
            visited_roots.append(root)
            yield root, dirnames, files

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(os, "walk", _spying_walk)
        roots = ScopeRoots.discover(start=tmp_path)

    nested_skill_bases = [r.base for r in roots.roots if r.kinds == frozenset({ArtifactKind.skill})]
    assert nested_skill_bases == [tmp_path / "sub" / ".claude"]
    assert not any("node_modules" in root for root in visited_roots)


def test_plugin_and_add_dir_roots(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    plugin = tmp_path / "plug"
    _agent(plugin, "plug-agent")
    added = tmp_path.parent / f"added-{tmp_path.name}"
    touch(added / ".claude" / "commands" / "deploy.md", "c")

    inv = ScopeInventory.scan(
        ScopeRoots.discover(start=tmp_path, plugin_dirs=[plugin], add_dirs=[added])
    )
    kinds_scopes = {(a.name, a.scope.value) for a in inv.artifacts}
    assert ("plug-agent", "plugin") in kinds_scopes
    assert ("deploy", "project") in kinds_scopes


def test_add_dir_symlinked_to_start_is_not_scanned_twice(tmp_path: Path) -> None:
    # a symlinked --add-dir resolving to the same physical dir as `start` must not double-scan
    # it, or every additive artifact (hooks) under it gets captured — and reported — twice
    real = tmp_path / "real"
    (real / ".git").mkdir(parents=True)
    (real / ".claude" / "settings.json").parent.mkdir(parents=True)
    (real / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": []}}')
    symlink = tmp_path / "symlink_to_real"
    symlink.symlink_to(real)

    roots = ScopeRoots.discover(start=real, add_dirs=[symlink])
    project_bases = [r.base for r in roots.roots if r.scope.value == "project"]
    assert len(project_bases) == len(set(project_bases))


def test_managed_split_settings_and_standalone(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    managed = tmp_path / "managed"
    _agent(managed / ".claude", "org-agent")  # standalone under managed/.claude/
    touch(
        managed / "managed-settings.json",
        '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"x"}]}]}}',
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path, managed_dir=managed))
    by_kind = {(a.kind.value, a.scope.value) for a in inv.artifacts}
    assert ("agent", "managed") in by_kind
    assert ("hook", "managed") in by_kind


def test_default_managed_dir_resolves_or_none() -> None:
    result = default_managed_dir()
    assert result is None or isinstance(result, Path)


def test_both_project_hook_files_capture(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(
        tmp_path / ".claude" / "settings.json",
        '{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"a"}]}]}}',
    )
    touch(
        tmp_path / ".claude" / "settings.local.json",
        '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"b"}]}]}}',
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    shareabilities = {a.shareable.value for a in inv.artifacts if a.kind.value == "hook"}
    assert shareabilities == {"committed", "gitignored"}


def test_frontmatter_hooks_parsed_and_unified(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _agent(
        tmp_path / ".claude",
        "guarded",
        "---\nname: guarded\nhooks:\n  PreToolUse:\n    - hooks:\n"
        "        - type: command\n          command: ./c.sh\n---\nbody\n",
    )
    touch(
        tmp_path / ".claude" / "settings.json",
        '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"x"}]}]}}',
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    agent = next(a for a in inv.artifacts if a.kind.value == "agent")
    assert parse_frontmatter_hooks(agent) is not None
    events = {event.value for config in inv.hook_configs for event in config.root}
    assert events == {"PreToolUse", "Stop"}  # frontmatter + settings unified


def test_hook_configs_excludes_frontmatter_hooks_from_shadowed_artifacts(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    home = tmp_path / "home"
    _agent(
        tmp_path / ".claude",
        "guarded",
        "---\nname: guarded\nhooks:\n  PreToolUse:\n    - hooks:\n"
        "        - type: command\n          command: ./c.sh\n---\nbody\n",
    )
    _agent(
        home / ".claude",
        "guarded",
        "---\nname: guarded\nhooks:\n  Stop:\n    - hooks:\n"
        "        - type: command\n          command: ./s.sh\n---\nbody\n",
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path, home_dir=home))
    # project outranks user for agents, so the user-scope "guarded" is shadowed and never
    # loaded — its Stop hook must not be reported as in effect
    events = {event.value for config in inv.hook_configs for event in config.root}
    assert events == {"PreToolUse"}


def test_parse_hooks_accepts_plugin_hooks_json_wrapper(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(
        tmp_path / ".claude" / "settings.json",
        '{"hooks":{"hooks":{"PreToolUse":[{"matcher":"Bash",'
        '"hooks":[{"type":"command","command":"x"}]}]},"description":"d"}}',
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    hook = next(a for a in inv.artifacts if a.kind.value == "hook")
    config = parse_hooks(hook)
    assert config is not None
    assert {event.value for event in config.root} == {"PreToolUse"}


def test_parse_hooks_accepts_empty_matcher(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(
        tmp_path / ".claude" / "settings.json",
        '{"hooks":{"Notification":[{"matcher":"",'
        '"hooks":[{"type":"command","command":"notify-send x"}]}]}}',
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    assert len(inv.hook_configs) == 1  # empty matcher means match-all, not invalid


def test_parse_hooks_fail_soft_on_unknown_event(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(
        tmp_path / ".claude" / "settings.json",
        '{"hooks":{"FutureEvent":[{"hooks":[{"type":"command","command":"x"}]}]}}',
    )
    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    hook = next(a for a in inv.artifacts if a.kind.value == "hook")
    assert parse_hooks(hook) is None  # unknown event skips, never raises
    assert inv.hook_configs == []


def test_render_inventory_groups_by_scope_and_lists_effective(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _agent(tmp_path / ".claude", "reviewer")
    text = render_inventory(ScopeInventory.scan(ScopeRoots.discover(start=tmp_path)))
    assert "[project]" in text
    assert "reviewer" in text
    assert "effective (what Claude Code uses):" in text
    assert "hook configs:" in text


def test_render_inventory_html_is_self_contained_and_escaped(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _agent(tmp_path / ".claude", "reviewer", "body with <script>evil()</script> & a < bracket")
    html = render_inventory_html(ScopeInventory.scan(ScopeRoots.discover(start=tmp_path)))

    assert html.startswith("<!doctype html>")
    assert "reviewer" in html
    assert "effective" in html
    assert "innerHTML" not in html  # the blocked token never appears
    assert "http://" not in html and "https://" not in html  # zero network references
    assert "<script>evil()" not in html  # untrusted contents are escaped
    assert "&lt;script&gt;evil()" in html  # ...to their entity form


def test_render_inventory_html_redacts_secret_in_hook_command(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(
        tmp_path / ".claude" / "settings.json",
        '{"hooks":{"PreToolUse":[{"hooks":[{"type":"command",'
        '"command":"curl -H \\"Authorization: Bearer sk-live-abc123XYZ789\\" https://x"}]}]}}',
    )
    html = render_inventory_html(ScopeInventory.scan(ScopeRoots.discover(start=tmp_path)))
    assert "sk-live-abc123XYZ789" not in html
    assert "[redacted]" in html


def test_symlinked_file_does_not_escape_base(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    secret = tmp_path.parent / f"secret-{tmp_path.name}"
    touch(secret, "SECRET")
    touch(tmp_path / ".claude" / "agents" / "ok.md", "real")
    (tmp_path / ".claude" / "agents" / "exfil.md").symlink_to(secret)

    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    assert _names(inv) == {"ok"}  # symlink escaping the base is skipped


def test_dangling_symlink_skips_itself(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(tmp_path / ".claude" / "agents" / "ok.md", "real")
    (tmp_path / ".claude" / "agents" / "gone.md").symlink_to(tmp_path / "no-such-target")

    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    assert _names(inv) == {"ok"}  # one broken link must not abort the scan


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads through chmod 0")
def test_permission_denied_file_skips_itself(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(tmp_path / ".claude" / "agents" / "ok.md", "real")
    blocked = tmp_path / ".claude" / "agents" / "blocked.md"
    touch(blocked, "x")
    blocked.chmod(0)

    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    assert _names(inv) == {"ok"}


def test_non_utf8_file_skips_itself(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    touch(tmp_path / ".claude" / "agents" / "ok.md", "real")
    (tmp_path / ".claude" / "agents" / "latin1.md").write_bytes(b"caf\xe9")

    inv = ScopeInventory.scan(ScopeRoots.discover(start=tmp_path))
    assert _names(inv) == {"ok"}
