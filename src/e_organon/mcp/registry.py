"""e_organon.mcp.registry: the MCP door's whole surface — every tool route, resource by resource, one tuple `main` registers
like the API's routers and the MCP lifespan reads into the engine's registry. A new tool is a new handler in its
resource's module, never an edit here but its module's line."""

from typing import Final

from litestar.handlers import HTTPRouteHandler

from e_organon.mcp.tools import doc, health, organon, tekton

### the tools every deployment serves; `ROUTES` adds the #tekton bridge, served only where it is configured.
CORE: Final[tuple[HTTPRouteHandler, ...]] = (*health.ROUTES, *doc.ROUTES, *organon.ROUTES)
ROUTES: Final[tuple[HTTPRouteHandler, ...]] = (*CORE, *tekton.ROUTES)
