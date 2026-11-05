"""api.lifespan.mcp: the MCP engine built over the door's tools, its session manager run for the app's life.

The tools are the door's routes (`mcp/registry`), read into the engine's registry (`infra/mcp`): what a client lists,
what the bridge calls. The server is built here, after the engines the tools reach exist, and lands under `system.mcp`
(`mcp/state`), where the endpoint's mount forwards to it. Who is asking is the token middleware's, before the server sees
the request; each tool admits the caller at its own access. The transport refuses any Host or Origin that is not this
service's: MCP_HOSTS and MCP_ORIGINS say which, and empty they are this port on `127.0.0.1` and `localhost`.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.metadata import version

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.infra.logger import logger
from e_organon.infra.mcp.registry import MCPRegistry
from e_organon.infra.mcp.server import MCPServer
from e_organon.infra.settings import settings as st
from e_organon.mcp.instructions import INSTRUCTIONS
from e_organon.mcp.registry import routes
from e_organon.mcp.state import MCPState
from e_organon.services.organon.find import FindOrganonService


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Build the server over the door's tools, run its session manager, then mount the section under `system.mcp`."""
    hosts = tuple(st.MCP_HOSTS) or (f"127.0.0.1:{st.APP_PORT}", f"localhost:{st.APP_PORT}")
    origins = tuple(st.MCP_ORIGINS) or tuple(f"http://{host}" for host in hosts)
    registry = MCPRegistry(routes(bridge=bool(st.TEKTON_PROFILES), ocr=st.OCR_ENABLED))
    ### `organon/find` ranks this very registry: it can exist only now, and is no job (`api/lifespan/jobs`).
    system = AppState.of(app).system
    system.services.organon.find = FindOrganonService(registry)
    server = MCPServer(
        registry,
        name="e-organon",
        version=version("e-organon"),
        instructions=INSTRUCTIONS,
        hosts=hosts,
        origins=origins,
    )
    async with server.run():
        system.mcp = MCPState(server=server)
        logger.info("mcp ready", tools=len(server.registry), step="START")
        yield
