from __future__ import annotations

from pathlib import Path

from capabilities_discovery.catalog import CATALOG_ID_MAX
from capabilities_discovery.discovery import scan_indexed_skills, scan_skills
from capabilities_discovery.scope import ScopeRoots
from helpers import touch


def _skill(base: Path, sub: str, name: str, desc: str) -> None:
    """Write a SKILL.md under ``<base>/skills/<sub>/`` — the layout the scope inventory scans."""
    lines = ["---", f"name: {name}", f"description: {desc}", "---", "", f"Body for {name}."]
    touch(base / "skills" / sub / "SKILL.md", "\n".join(lines))


def _plugin_roots(tmp_path: Path, *plugins: Path) -> ScopeRoots:
    return ScopeRoots.discover(start=tmp_path / "start", plugin_dirs=list(plugins))


def test_scan_finds_nested_skill_md(tmp_path: Path) -> None:
    # plugin layouts nest SKILL.md at uneven depths under the skills dir
    plugin = tmp_path / "p"
    _skill(plugin, "cache/local/forge", "forge", "Generate artifacts from a spec.")
    assert [c.ref for c in scan_skills(_plugin_roots(tmp_path, plugin))] == ["forge"]


def test_scan_slugifies_titlecase_names(tmp_path: Path) -> None:
    plugin = tmp_path / "p"
    _skill(plugin, "agent", "Agent Development", "Author Claude Code agents and subagents.")
    card = scan_skills(_plugin_roots(tmp_path, plugin))[0]
    assert card.ref == "agent-development"
    assert card.id == "skill.agent-development"


def test_scan_dedupes_cached_copies(tmp_path: Path) -> None:
    cache, market = tmp_path / "cache", tmp_path / "market"
    _skill(cache, "forge", "forge", "Generate artifacts from a typed spec.")
    _skill(market, "forge", "forge", "Generate artifacts from a typed spec.")
    # identical copy across two plugin install dirs collapses to one
    assert [c.ref for c in scan_skills(_plugin_roots(tmp_path, cache, market))] == ["forge"]


def test_scan_disambiguates_same_name_distinct_skills(tmp_path: Path) -> None:
    p1, p2 = tmp_path / "p1", tmp_path / "p2"
    _skill(p1, "access", "access", "Manage Discord channel access.")
    _skill(p2, "access", "access", "Manage Telegram channel access.")
    ids = sorted(c.id for c in scan_skills(_plugin_roots(tmp_path, p1, p2)))
    assert ids == ["skill.access", "skill.access-2"]


def test_disambiguated_ids_are_stable_regardless_of_scan_order(tmp_path: Path) -> None:
    # a consumer that persisted a colliding skill's id must never see it silently resolve to a
    # different skill just because a scope root was added, removed, or scanned in another order
    p1, p2 = tmp_path / "p1", tmp_path / "p2"
    _skill(p1, "access", "access", "Manage Discord channel access.")
    _skill(p2, "access", "access", "Manage Telegram channel access.")

    forward = {c.description: c.id for c in scan_skills(_plugin_roots(tmp_path, p1, p2))}
    reverse = {c.description: c.id for c in scan_skills(_plugin_roots(tmp_path, p2, p1))}
    assert forward == reverse


def test_scan_disambiguates_long_colliding_names(tmp_path: Path) -> None:
    # the -N suffix must survive the id length cap, or disambiguation never terminates
    name = "long-skill-name-" + "x" * 60
    p1, p2 = tmp_path / "p1", tmp_path / "p2"
    _skill(p1, "a", name, "Manage Discord channel access.")
    _skill(p2, "b", name, "Manage Telegram channel access.")
    ids = [c.id for c in scan_skills(_plugin_roots(tmp_path, p1, p2))]
    assert len(set(ids)) == 2
    assert all(len(i) <= CATALOG_ID_MAX for i in ids)
    assert any(i.endswith("-2") for i in ids)


def test_scan_disambiguates_when_truncated_base_already_ends_in_suffix(tmp_path: Path) -> None:
    # edge case: when the id-length-capped base already ends in "-2", naively appending "-2"
    # again must not silently reproduce the same id as the un-suffixed base
    name = "a" * 56 + "-2"
    p1, p2 = tmp_path / "p1", tmp_path / "p2"
    _skill(p1, "a", name, "Manage Discord channel access.")
    _skill(p2, "b", name, "Manage Telegram channel access.")
    ids = [c.id for c in scan_skills(_plugin_roots(tmp_path, p1, p2))]
    assert len(set(ids)) == 2


def test_scan_merges_multiple_roots(tmp_path: Path) -> None:
    home, plugin = tmp_path / "home", tmp_path / "plug"
    _skill(home / ".claude", "local", "local-skill", "A user skill in the skills root here.")
    _skill(plugin, "plug", "plug-skill", "A skill from a plugin tree here.")
    roots = ScopeRoots.discover(start=tmp_path / "start", home_dir=home, plugin_dirs=[plugin])
    refs = {card.ref for card, _ in scan_indexed_skills(roots)}
    assert refs == {"local-skill", "plug-skill"}
