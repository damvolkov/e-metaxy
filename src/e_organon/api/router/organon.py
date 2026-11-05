"""api.router.organon: the organon/ section — organon's own tools, streamed or batched by the request's Accept.

`organon/find` ranks the MCP door's tools against a need (`graph.services.organon.find`); `api.stream` decides the
reading. The MCP twin (`mcp/tools/organon`) is this handler. The jobs a tool made when asked to answer later are
`api/router/jobs`."""

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
from e_organon.models.organon import FindIn

TOOL_DEPS: Final[dict[str, Provide]] = {DepKey.GRAPH.value: Provide(graph, sync_to_thread=False)}


##### HANDLERS #####
async def find(data: JSONBody[FindIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """organon/find: the tools that answer a need."""
    return await answer(request, graph.services.organon.find, data)


##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    post(
        f"/organon/{handler.__name__}",
        name=f"organon.{handler.__name__}",
        status_code=200,
        tags=["organon"],
        opt=OPT[Access.USER],
        security=SECURITY,
        dependencies=TOOL_DEPS,
    )(handler)
    for handler in (find,)
)
