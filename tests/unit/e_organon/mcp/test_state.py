"""tests/unit/e_organon/mcp/state: the OST parity of the door — `system.mcp` is the section of `e_organon/mcp/state.py`, its server
the engine's over the door's registry, built by the lifespan that runs it."""

from typing import TYPE_CHECKING

from e_organon.infra.mcp.server import MCPServer
from e_organon.mcp.instructions import INSTRUCTIONS
from e_organon.mcp.registry import routes
from e_organon.mcp.state import MCPState

if TYPE_CHECKING:
    from litestar import Litestar
    from litestar.testing import AsyncTestClient


async def test_state_section_holds_the_server(client: AsyncTestClient[Litestar]) -> None:
    """The branch `mcp` is the package `e_organon.mcp`: its section is that package's `state`, its server the engine's."""
    section = client.app.state.system.mcp
    assert (type(section).__module__, type(section), type(section.server), len(section.server.registry)) == (
        "e_organon.mcp.state",
        MCPState,
        MCPServer,
        len(routes(bridge=True, ocr=False)),
    )
    assert section.server.instructions == INSTRUCTIONS
