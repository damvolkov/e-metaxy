"""e_organon.mcp.tools.image: the image/ section as tools — the twin of `api/router/image`, whose very handlers they are.

The MCP engine asks for JSON, so a tool always answers in batch: the result, or the `Failed` reason as its error. Paths are
under the vault or the workspaces; the written file lands in the outbox, content-named, and is the next tool's input."""

from typing import Final

from litestar.handlers import HTTPRouteHandler

from e_organon.api.router import image as router
from e_organon.infra.auth.models import Access
from e_organon.infra.mcp.models import MCPTool
from e_organon.mcp.refusals import REFUSALS

##### TOOLS — what a client is told #####
CUTOUT: Final = MCPTool(
    name="image_cutout",
    title="Cut ink out of a photo",
    description=(
        "A photo of ink on paper (a signature) by `path`, as a transparent PNG of the ink alone: paper tint, uneven light "
        "and shadows gone, soft edges. `color` keeps the ink's own colour (default; off, black); `crop` cuts to the ink "
        "(default); `lines` (default) drops printed lines — turn it off if the signature has its own straight underline. Returns the PNG's `path`, the next tool's input (doc_stamp)."
    ),
    read_only=False,
)

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    tool.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(handler)
    for tool, handler in ((CUTOUT, router.cutout),)
)
