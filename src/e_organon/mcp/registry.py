"""e_organon.mcp.registry: the MCP door's whole surface — every tool route, resource by resource, one tuple `main` registers
like the API's routers and the MCP lifespan reads into the engine's registry. A new tool is a new handler in its
resource's module, never an edit here but its module's line.

`CORE` is what every deployment serves; `routes` adds what a deployment turns on — the OCR engine (`doc_ocr`), the #tekton
bridge — and `ROUTES` is everything, the surface the tests hold the door to."""

from typing import Final

from litestar.handlers import HTTPRouteHandler

from e_organon.mcp.tools import doc, health, image, organon, tekton

CORE: Final[tuple[HTTPRouteHandler, ...]] = (*health.ROUTES, *doc.ROUTES, *image.ROUTES, *organon.ROUTES)


def routes(*, bridge: bool, ocr: bool) -> tuple[HTTPRouteHandler, ...]:
    """The tools of a deployment: the core, and each optional section that is on."""
    return (*CORE, *(doc.OCR_ROUTES if ocr else ()), *(tekton.ROUTES if bridge else ()))


ROUTES: Final[tuple[HTTPRouteHandler, ...]] = routes(bridge=True, ocr=True)
