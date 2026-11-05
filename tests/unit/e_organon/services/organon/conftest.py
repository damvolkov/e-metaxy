"""tests/unit/e_organon/services/organon: the catalog over the door's real registry, tekton's tools included, and over a
registry of three tools of the tests' own, one word apart."""

from typing import TYPE_CHECKING

import pytest

from e_organon.infra.mcp.models import MCPEntry, MCPTool
from e_organon.infra.mcp.registry import MCPRegistry
from e_organon.mcp.registry import ROUTES
from e_organon.models.organon import FindIn
from e_organon.services.organon.find import FindOrganonService

if TYPE_CHECKING:
    from support.catalog import Ranked


@pytest.fixture
def find() -> FindOrganonService:
    return FindOrganonService(MCPRegistry(ROUTES))


@pytest.fixture
def weighed() -> FindOrganonService:
    """`wave_alpha` has the word in its name, `wave_beta` in its title, `wave_gamma` in its description only."""
    entries = [
        MCPEntry(
            tool=MCPTool(name="wave_gamma", title="Gamma", description="Rides the zebra."),
            path="/mcp/tools/wave_gamma",
            arguments={"type": "object"},
        ),
        MCPEntry(
            tool=MCPTool(name="wave_beta", title="Zebra", description="Beta."),
            path="/mcp/tools/wave_beta",
            arguments={"type": "object"},
        ),
        MCPEntry(
            tool=MCPTool(name="wave_zebra", title="Alpha", description="Alpha."),
            path="/mcp/tools/wave_zebra",
            arguments={"type": "object", "properties": {"id": {"type": "string"}}},
        ),
    ]
    return FindOrganonService(entries)


@pytest.fixture
def ranked() -> Ranked:
    """The names a service answers a query with, in order — the section narrowing when given."""

    async def names(service: FindOrganonService, query: str, section: str = "") -> list[str]:
        return [found.name for found in (await service.run(FindIn(query=query, section=section))).tools]

    return names
