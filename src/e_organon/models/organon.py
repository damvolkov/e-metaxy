"""e_organon.models.organon: what organon says of itself — the tools it serves, found by what a caller needs."""

from typing import Any

import msgspec


##### FIND #####
class FindIn(msgspec.Struct, frozen=True, kw_only=True):
    """`query`: what the caller needs, in words. `section`: only the tools of that section (`doc`, `tekton`…)."""

    query: str
    section: str = ""


class Found(msgspec.Struct, frozen=True, kw_only=True):
    """A tool: its name, what it does, and the JSON Schema of its arguments."""

    name: str
    description: str
    schema: dict[str, Any]


class FindOut(msgspec.Struct, frozen=True, kw_only=True):
    """The tools that answer the query, best first."""

    tools: list[Found]
