"""api.router.image: the image/ section — one route per canonical tool, each streamed, batched or queued by the request.

A handler only hands the request and its arguments to the tool's workflow on the sealed graph
(`graph.services.image.<tool>`); `api.stream` decides the reading. The MCP twins (`mcp/tools/image`) are these handlers."""

from typing import Any, Final

from litestar import Request, post
from litestar.di import NamedDependency, Provide
from litestar.handlers import HTTPRouteHandler
from litestar.params import JSONBody

from e_organon.api.deps import DepKey, graph
from e_organon.api.security import SECURITY
from e_organon.api.stream import answer
from e_organon.infra.auth.guard import OPT
from e_organon.infra.auth.models import Access
from e_organon.infra.state import State
from e_organon.models.image import CutoutIn

TOOL_DEPS: Final[dict[str, Provide]] = {DepKey.GRAPH.value: Provide(graph, sync_to_thread=False)}


##### HANDLERS #####
async def cutout(data: JSONBody[CutoutIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """image/cutout: the ink of a photo as a transparent PNG."""
    return await answer(request, graph.services.image.cutout, data)


##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    post(
        f"/image/{handler.__name__}",
        name=f"image.{handler.__name__}",
        status_code=200,
        tags=["image"],
        opt=OPT[Access.USER],
        security=SECURITY,
        dependencies=TOOL_DEPS,
    )(handler)
    for handler in (cutout,)
)
