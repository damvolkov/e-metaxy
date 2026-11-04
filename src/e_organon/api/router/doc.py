"""api.router.doc: the doc/ section — one route per canonical tool, each streamed or batched by the request's Accept.

A handler only hands the request and its arguments to the tool's workflow on the sealed graph
(`graph.services.doc.<tool>`); `api.stream` decides the reading. The MCP twins (`mcp/tools/doc`) call the same tools."""

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
from e_organon.models.doc import ConvertIn

TOOL_DEPS: Final[dict[str, Provide]] = {DepKey.GRAPH.value: Provide(graph, sync_to_thread=False)}


##### HANDLERS #####
async def convert(data: JSONBody[ConvertIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """doc/convert: a document as Markdown — `text/event-stream` for its steps, JSON `ConvertOut` otherwise."""
    return await answer(request, graph.services.doc.convert, data)


##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = (
    post(
        "/doc/convert",
        name="doc.convert",
        status_code=200,
        tags=["doc"],
        opt=OPT[Access.USER],
        security=SECURITY,
        dependencies=TOOL_DEPS,
    )(convert),
)
