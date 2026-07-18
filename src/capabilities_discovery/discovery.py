from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from .base import InputModel
from .catalog import (
    CATALOG_ID_MAX,
    BuiltinTool,
    Catalog,
    CatalogMcpServer,
    CatalogSkill,
    CatalogTool,
    SkillRef,
    catalog_id,
)
from .frontmatter import read_frontmatter
from .scope import ArtifactKind, ScopeInventory, ScopeRoots

_SKILL_REF: TypeAdapter[SkillRef] = TypeAdapter(SkillRef)  # one place a skill name becomes a ref
_DESCRIPTION_SCAN_MAX = 800

# The built-in Claude Code tools any subagent may be granted. read_only / needs_network
# record each tool's real behaviour as catalog metadata (surfaced in the inventory report).
BUILTIN_TOOLS: list[CatalogTool] = [
    CatalogTool(
        id="builtin.read",
        ref=BuiltinTool.read.value,
        description="Read a file from the filesystem.",
        tags=["file", "files", "read", "open", "load", "view", "contents"],
        read_only=True,
    ),
    CatalogTool(
        id="builtin.write",
        ref=BuiltinTool.write.value,
        description="Write or overwrite a file on the filesystem.",
        tags=["file", "files", "write", "create", "generate", "save", "output", "produce"],
        read_only=False,
    ),
    CatalogTool(
        id="builtin.edit",
        ref=BuiltinTool.edit.value,
        description="Edit a file by replacing an exact string.",
        tags=["file", "files", "edit", "modify", "change", "replace", "update", "line"],
        read_only=False,
    ),
    CatalogTool(
        id="builtin.glob",
        ref=BuiltinTool.glob.value,
        description="Find files by glob pattern.",
        tags=["file", "files", "find", "search", "glob", "pattern", "match", "locate"],
        read_only=True,
    ),
    CatalogTool(
        id="builtin.grep",
        ref=BuiltinTool.grep.value,
        description="Search file contents with a regular expression.",
        tags=["search", "grep", "find", "pattern", "regex", "contents", "match", "code"],
        read_only=True,
    ),
    CatalogTool(
        id="builtin.bash",
        ref=BuiltinTool.bash.value,
        description="Run a shell command in the workspace.",
        tags=["shell", "run", "execute", "command", "build", "script", "terminal"],
        read_only=False,
    ),
    CatalogTool(
        id="builtin.web_fetch",
        ref=BuiltinTool.web_fetch.value,
        description="Fetch and read a web page over the network.",
        tags=["web", "fetch", "network", "url", "page", "download", "http"],
        read_only=True,
        needs_network=True,
    ),
    CatalogTool(
        id="builtin.web_search",
        ref=BuiltinTool.web_search.value,
        description="Search the web and read result snippets.",
        tags=["web", "search", "network", "query", "results", "internet"],
        read_only=True,
        needs_network=True,
    ),
    CatalogTool(
        id="builtin.task",
        ref=BuiltinTool.task.value,
        description="Spawn a subagent to handle a delegated task.",
        tags=["agent", "delegate", "subagent", "spawn", "task"],
        read_only=False,
    ),
]


class _SkillFrontmatter(InputModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] = []


def _parse_frontmatter(text: str) -> _SkillFrontmatter | None:
    """Parse a SKILL.md's YAML frontmatter into its typed fields.

    Args:
        text: The full SKILL.md body, frontmatter and all.

    Returns:
        The parsed frontmatter, or None when there is no frontmatter or it doesn't validate.
    """
    data = read_frontmatter(text)
    if data is None:
        return None
    try:
        return _SkillFrontmatter.model_validate(data)
    except ValidationError:
        return None


def _disambiguated_ids(ref: str, count: int) -> list[str]:
    """Mint `count` distinct ids for skills sharing `ref`: the bare id, then `-2`, `-3`, ….

    Args:
        ref: The skill ref the ids are minted for.
        count: How many colliding skills share this ref.

    Returns:
        `count` distinct ids, in the order a caller's own content-sorted list should be assigned
        them — this function only mints the id strings; which skill gets which is the caller's
        choice. The base is trimmed so each suffix survives the id length cap; if that trim
        happens to reproduce an id already minted (the base's own tail already reads e.g. "-2"),
        one more character is trimmed until the candidate is unique.
    """
    base = catalog_id("skill", ref)
    ids = [base]
    seen = {base}
    for suffix in range(2, count + 1):
        tail = f"-{suffix}"
        trim = len(tail)
        candidate = base[: CATALOG_ID_MAX - trim] + tail
        while candidate in seen and trim < len(base):
            trim += 1
            candidate = base[: CATALOG_ID_MAX - trim] + tail
        seen.add(candidate)
        ids.append(candidate)
    return ids


def skill_ref(skill_md: Path) -> SkillRef | None:
    """Resolve the `SkillRef` a SKILL.md file declares.

    Shared by the skill index and plugin discovery so a plugin's declared skill refs match the
    refs of the indexed skills they point at — both go through the same `SkillRef` normalization.

    Args:
        skill_md: Path to a `SKILL.md` file; read with errors ignored.

    Returns:
        The ref from the frontmatter `name` (falling back to the parent dir name), or None when
        the file is unreadable, lacks a usable description, or the name won't normalize.
    """
    try:
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    frontmatter = _parse_frontmatter(text)
    if frontmatter is None or not frontmatter.description:
        return None
    try:
        return _SKILL_REF.validate_python(frontmatter.name or skill_md.parent.name)
    except ValidationError:
        return None


def _card(skill_id: str, ref: str, frontmatter: _SkillFrontmatter) -> CatalogSkill | None:
    """Assemble one `CatalogSkill` from a skill's id, ref, and parsed frontmatter.

    Args:
        skill_id: The unique catalog id minted for this skill.
        ref: The skill's normalized ref.
        frontmatter: Its parsed frontmatter; the description is truncated to the scan cap and
            an absent one becomes empty.

    Returns:
        The card, or None if the fields don't validate.
    """
    try:
        return CatalogSkill(
            id=skill_id,
            ref=ref,
            description=(frontmatter.description or "")[:_DESCRIPTION_SCAN_MAX],
            tags=frontmatter.tags,
        )
    except ValidationError:
        return None


def scan_indexed_skills(roots: ScopeRoots) -> list[tuple[CatalogSkill, Path]]:
    """Index every SKILL.md the scope inventory captures under `roots` into `(card, path)` pairs.

    The inventory owns where skills live (project walk-up, user, managed, plugin, nested); this
    classifies each capture — parsing its contents, deduping a skill cached across locations by
    (name, description), and disambiguating colliding ids.

    Args:
        roots: The scope roots to scan; passed straight to `ScopeInventory.scan`.

    Returns:
        One `(card, path)` per distinct skill — a stable id and the path to load its body —
        skipping captures with no description and dropping later duplicates of a (name,
        description) already seen.
    """
    seen: set[tuple[str, str]] = set()
    by_ref: dict[str, list[tuple[_SkillFrontmatter, Path]]] = {}
    for captured in ScopeInventory.scan(roots).artifacts:
        if captured.kind is not ArtifactKind.skill:
            continue
        frontmatter = _parse_frontmatter(captured.contents)
        if frontmatter is None or not frontmatter.description:
            continue
        name = frontmatter.name or captured.path.parent.name
        key = (name, frontmatter.description)
        if key in seen:
            continue
        try:
            ref = _SKILL_REF.validate_python(name)
        except ValidationError:
            continue
        seen.add(key)
        by_ref.setdefault(ref, []).append((frontmatter, captured.path))

    indexed: list[tuple[CatalogSkill, Path]] = []
    for ref, entries in by_ref.items():
        # sorted by content, never by scan order — the id a colliding skill gets must depend
        # only on which skills exist, not on which scope root or filesystem order happened to
        # surface it first; otherwise a consumer that persisted the id could silently resolve
        # to a different skill after an unrelated scan-root change.
        ordered = sorted(entries, key=lambda item: (item[0].description or "", str(item[1])))
        for skill_id, (frontmatter, path) in zip(
            _disambiguated_ids(ref, len(ordered)), ordered, strict=True
        ):
            card = _card(skill_id, ref, frontmatter)
            if card is None:
                continue
            indexed.append((card, path))
    return indexed


def scan_skills(roots: ScopeRoots) -> list[CatalogSkill]:
    """Index the skill cards captured under `roots`, discarding their on-disk paths.

    Args:
        roots: The scope roots to scan.

    Returns:
        One card per distinct skill, skipping malformed ones.
    """
    return [card for card, _ in scan_indexed_skills(roots)]


def scan_environment(
    roots: ScopeRoots,
    mcp_servers: Sequence[CatalogMcpServer] = (),
) -> Catalog:
    """Build a live catalog from the captured skills and connected MCP servers — the entries
    recall ranks against. Built-in tools are not retrieved by text (their descriptions never match
    a task's goal language), so they are not in the catalog; every generated agent gets the fixed
    `DEFAULT_TOOLS` set at selection time instead.

    Args:
        roots: The scope roots to scan for skills.
        mcp_servers: Connected MCP server cards to include; pass `enumerate_mcp_servers()` to
            harvest them. The empty default keeps the scan hermetic.

    Returns:
        A `Catalog` of the captured skills and `mcp_servers`.
    """
    return Catalog(entries=[*scan_skills(roots), *mcp_servers])
