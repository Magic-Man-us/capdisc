"""The capture engine: scans artifact locations into `CapturedArtifact` records, parses each
capture's hook config, and resolves the effective (collision-winning) set."""

from __future__ import annotations

from pydantic import JsonValue, ValidationError

from ...base import FrozenModel, InputModel
from ...frontmatter import read_frontmatter
from ...hooks import HookConfig
from ..locations import Artifact, Location
from ..types import (
    ArtifactContents,
    ArtifactKind,
    ArtifactName,
    ArtifactPath,
    ResolutionMode,
    ResolutionRank,
    ScopeKind,
    Shareability,
)
from .roots import ScanRoot, ScopeRoots, artifact_kinds


class CapturedArtifact(FrozenModel):
    """One definition found on disk: its placement, exact path, contents, and resolution rank."""

    kind: ArtifactKind
    scope: ScopeKind
    shareable: Shareability
    resolution: ResolutionMode
    name: ArtifactName
    path: ArtifactPath
    contents: ArtifactContents
    precedence: ResolutionRank


class _WrappedHooks(InputModel):
    """A plugin hooks.json body: the event map under a `hooks` key (description etc. ignored)."""

    hooks: JsonValue = None


def parse_hooks(captured: CapturedArtifact) -> HookConfig | None:
    """Parse a captured hook artifact into a typed `HookConfig`.

    Ingest is fail-soft: a config using an event, handler type, or structure newer than we model
    skips rather than crashing the scan — unknown *fields* are already tolerated by
    `FrozenWireModel`, so this only trips on shape we cannot represent at all.

    Args:
        captured: A captured hook artifact; its contents are a settings.json `hooks` slice
            (the bare event map) or a plugin hooks.json (that same map under a `hooks` key).

    Returns:
        The typed config, or None if it cannot be parsed.
    """
    try:
        return HookConfig.model_validate_json(captured.contents)
    except ValidationError:
        pass
    try:
        wrapped = _WrappedHooks.model_validate_json(captured.contents).hooks
        return None if wrapped is None else HookConfig.model_validate(wrapped)
    except ValidationError:
        return None


def _frontmatter_hooks_value(text: str) -> JsonValue | None:
    """The `hooks` value from a markdown file's frontmatter, or None if absent or not a mapping."""
    data = read_frontmatter(text)
    return None if data is None else data.get("hooks")


def parse_frontmatter_hooks(captured: CapturedArtifact) -> HookConfig | None:
    """Parse the hooks a host agent or skill declares in its frontmatter.

    These are the component-scope hooks, active while their host is. Fail-soft like `parse_hooks`.

    Args:
        captured: A captured agent or skill artifact whose frontmatter may declare `hooks`.

    Returns:
        The typed config, or None if it declares none or they cannot be parsed.
    """
    hooks = _frontmatter_hooks_value(captured.contents)
    if hooks is None:
        return None
    try:
        return HookConfig.model_validate(hooks)
    except ValidationError:
        return None


def _ranked_roots(artifact: Artifact, roots: list[ScanRoot]) -> list[ScanRoot]:
    """The scan roots an artifact loads from, ordered by its own precedence.

    Roots are keyed by the artifact's scope order, then by scan position so a nearer project dir
    outranks a farther one. Position in the result is the collision rank (0 wins).

    Args:
        artifact: The artifact descriptor whose scope order and kind-filter apply.
        roots: All scan roots to filter and rank.

    Returns:
        The applicable roots, highest precedence first; roots whose scope the artifact has no
        location for (e.g. a managed dir for a command), or whose `kinds` exclude it, are dropped.
    """
    order = {location.scope: index for index, location in enumerate(artifact.locations)}
    ranked = [
        (position, root)
        for position, root in enumerate(roots)
        if root.scope in order and (root.kinds is None or artifact.kind in root.kinds)
    ]
    ranked.sort(key=lambda pair: (order[pair[1].scope], pair[0]))
    return [root for _, root in ranked]


class ScopeInventory(FrozenModel):
    """A single snapshot of every definition across every scanned location — the concrete
    grounding of the abstract location taxonomy. One instance holds the lot."""

    artifacts: list[CapturedArtifact] = []

    @staticmethod
    def _scan_artifact(artifact: Artifact, roots: ScopeRoots) -> list[CapturedArtifact]:
        """Capture every on-disk definition for one artifact descriptor.

        A scope can hold more than one location (a hook lives in both `settings.json` and
        `settings.local.json`), so every location for the matched scope is scanned, not just one.

        Args:
            artifact: The artifact descriptor to scan for.
            roots: The scan roots to look under.

        Returns:
            Every capture found, each carrying its location's scope/shareability and the
            artifact's collision rank.
        """
        by_scope: dict[ScopeKind, list[Location]] = {}
        for location in artifact.locations:
            by_scope.setdefault(location.scope, []).append(location)

        captured: list[CapturedArtifact] = []
        for precedence, root in enumerate(_ranked_roots(artifact, roots.roots)):
            for location in by_scope[root.scope]:
                captured.extend(
                    CapturedArtifact(
                        kind=artifact.kind,
                        scope=location.scope,
                        shareable=location.shareable,
                        resolution=artifact.resolution,
                        name=hit.name,
                        path=hit.path,
                        contents=hit.contents,
                        precedence=precedence,
                    )
                    for hit in location.storage.discover(root.base)
                )

        return captured

    @property
    def hook_configs(self) -> list[HookConfig]:
        """Every hook config in effect across the snapshot: settings/plugin `hooks` entries plus
        those declared in an agent's or skill's frontmatter. Unparseable captures are skipped.

        Reads from `effective`, not `artifacts` — an agent or skill shadowed by a
        higher-precedence same-named capture never loads, so its frontmatter hooks never run."""
        configs: list[HookConfig] = []
        for captured in self.effective:
            if captured.kind is ArtifactKind.hook:
                config = parse_hooks(captured)
            elif captured.kind in (ArtifactKind.agent, ArtifactKind.skill):
                config = parse_frontmatter_hooks(captured)
            else:
                config = None
            if config is not None:
                configs.append(config)
        return configs

    @property
    def effective(self) -> list[CapturedArtifact]:
        """What takes effect: for each name-collision (kind, name) the lowest-rank capture, plus
        every additive capture (hooks) unchanged. A plain property — derived from the precedence
        rank on each capture, so it is order-independent rather than relying on scan order."""
        best: dict[tuple[ArtifactKind, ArtifactName], CapturedArtifact] = {}
        additive: list[CapturedArtifact] = []
        for captured in self.artifacts:
            if captured.resolution is ResolutionMode.additive:
                additive.append(captured)
                continue
            identity = (captured.kind, captured.name)
            current = best.get(identity)
            if current is None or captured.precedence < current.precedence:
                best[identity] = captured
        return list(best.values()) + additive

    @classmethod
    def scan(cls, roots: ScopeRoots) -> ScopeInventory:
        """Scan every artifact's locations under `roots` into one snapshot.

        Walks each artifact's locations under every applicable root, dispatching to each storage
        shape's `discover`. Each capture's rank is its position in that artifact's own precedence
        order, so the right scope wins per kind (skills rank user over project, subagents the
        reverse) and nearer project dirs win on collision.

        Args:
            roots: The scan roots, as resolved by `ScopeRoots.discover`.

        Returns:
            The inventory snapshot of every captured artifact.
        """
        captured = [
            capture
            for artifact in artifact_kinds()
            for capture in cls._scan_artifact(artifact, roots)
        ]
        return cls(artifacts=captured)
