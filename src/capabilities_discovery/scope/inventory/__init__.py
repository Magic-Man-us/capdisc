"""Scan every artifact location under a set of scope roots into a `ScopeInventory` snapshot."""

from __future__ import annotations

from .capture import CapturedArtifact, ScopeInventory, parse_frontmatter_hooks, parse_hooks
from .render import render_inventory, render_inventory_html
from .roots import ScanRoot, ScopeRoots, artifact_kinds, default_managed_dir

__all__ = [
    "CapturedArtifact",
    "ScanRoot",
    "ScopeInventory",
    "ScopeRoots",
    "artifact_kinds",
    "default_managed_dir",
    "parse_frontmatter_hooks",
    "parse_hooks",
    "render_inventory",
    "render_inventory_html",
]
