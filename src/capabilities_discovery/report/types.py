"""Domain-primitive aliases for the report package."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

ComponentCount = Annotated[
    int,
    Field(
        ge=0,
        title="Component count",
        description="Number of components (skills, agents, hooks, or MCP servers) in a group.",
    ),
]
SectionId = Annotated[
    str,
    Field(
        pattern=r"^[a-z]+$",
        title="Section id",
        description="Nav/anchor id of one report tab.",
        examples=["overview", "skills"],
    ),
]
SectionLabel = Annotated[
    str,
    Field(
        min_length=1,
        max_length=40,
        title="Section label",
        description="Human-readable nav label of one report tab.",
        examples=["Scan roots"],
    ),
]
SectionCount = Annotated[
    int,
    Field(
        ge=0,
        title="Section count",
        description="Item count shown next to a report tab's nav label.",
    ),
]
