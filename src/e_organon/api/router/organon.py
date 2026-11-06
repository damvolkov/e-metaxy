"""api.router.organon: the organon/ section — organon's own tools, streamed or batched by the request's Accept.

`organon/find` ranks the MCP door's tools against a need (`graph.services.organon.find`); `api.stream` decides the
reading. `organon/submit` queues a job tool by its name, `202` with the job and its `Location`, as `Prefer:
respond-async` does for the tool's own route: the way in for a client that cannot send the header (MCP). The MCP twins
(`mcp/tools/organon`) are these handlers. The jobs themselves are `api/router/jobs`."""

from typing import Any, Final

import msgspec
from litestar import Request, Response, post
from litestar.di import NamedDependency, Provide
from litestar.handlers import HTTPRouteHandler
from litestar.params import JSONBody
from litestar.status_codes import HTTP_202_ACCEPTED

from e_organon.api.deps import DepKey, caller, graph
from e_organon.api.router.jobs import refused
from e_organon.api.security import SECURITY
from e_organon.api.stream import answer
from e_organon.infra.auth.guard import OPT
from e_organon.infra.auth.models import Access, Caller
from e_organon.infra.state import State
from e_organon.models.error import UnknownToolError
from e_organon.models.job import AcceptedJob
from e_organon.models.organon import FindIn, SubmitIn

TOOL_DEPS: Final[dict[str, Provide]] = {DepKey.GRAPH.value: Provide(graph, sync_to_thread=False)}
SUBMIT_DEPS: Final[dict[str, Provide]] = TOOL_DEPS | {DepKey.CALLER.value: Provide(caller, sync_to_thread=False)}


##### HANDLERS #####
async def find(data: JSONBody[FindIn], request: Request[Any, Any, Any], graph: NamedDependency[State]) -> Any:
    """organon/find: the tools that answer a need."""
    return await answer(request, graph.services.organon.find, data)


async def submit(
    data: JSONBody[SubmitIn], graph: NamedDependency[State], caller: NamedDependency[Caller]
) -> Response[AcceptedJob]:
    """organon/submit: a tool queued as a job by its name; the caller owns the job."""
    accepted = await graph.services.jobs.enqueue(data.tool, data.input, caller)
    return Response(accepted, status_code=HTTP_202_ACCEPTED, headers={"Location": f"/jobs/{accepted.job}"})


##### ROUTES #####
OPTIONS: Final[dict[str, Any]] = {"tags": ["organon"], "opt": OPT[Access.USER], "security": SECURITY}
ROUTES: tuple[HTTPRouteHandler, ...] = (
    post("/organon/find", name="organon.find", status_code=200, dependencies=TOOL_DEPS, **OPTIONS)(find),
    post(
        "/organon/submit",
        name="organon.submit",
        status_code=HTTP_202_ACCEPTED,
        dependencies=SUBMIT_DEPS,
        exception_handlers={UnknownToolError: refused, msgspec.ValidationError: refused},
        **OPTIONS,
    )(submit),
)
