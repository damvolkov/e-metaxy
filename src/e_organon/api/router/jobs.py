"""api.router.jobs: the jobs a tool asked to answer later became — read, followed, stopped.

`GET /jobs/{id}` is the job as it stands; `GET /jobs/{id}/events` the server-sent events of its tool, the steps as it
enters them and then `done` or `failed`, until it settles (the same events `Accept: text/event-stream` gives the tool's
own route); `DELETE /jobs/{id}` stops it. Who asks is the guard's, at user access, as the tools'. A job is its owner's (the admin reaches all): an id nobody holds,
or another account's, is 404."""

from typing import Any, Final

from litestar import Request, Response, delete, get
from litestar.di import NamedDependency, Provide
from litestar.handlers import HTTPRouteHandler
from litestar.params import FromPath
from litestar.response.sse import ServerSentEvent
from litestar.status_codes import HTTP_200_OK, HTTP_404_NOT_FOUND

from e_organon.api.deps import DepKey, caller, graph
from e_organon.api.security import SECURITY
from e_organon.api.stream import follow
from e_organon.infra.auth.guard import OPT
from e_organon.infra.auth.models import Access, Caller
from e_organon.infra.state import State
from e_organon.models.error import UnknownJobError
from e_organon.models.job import Job


def missing(_request: Request[Any, Any, Any], exc: UnknownJobError) -> Response[dict[str, str]]:
    """A job nobody holds."""
    return Response({"detail": str(exc)}, status_code=HTTP_404_NOT_FOUND)


##### HANDLERS #####
async def show(job_id: FromPath[str], graph: NamedDependency[State], caller: NamedDependency[Caller]) -> Job:
    """The job as it stands: its state, progress, errors, when it was made and when it settled."""
    return await graph.services.jobs.status(job_id, caller)


async def events(
    job_id: FromPath[str], graph: NamedDependency[State], caller: NamedDependency[Caller]
) -> ServerSentEvent:
    """The job's events, polled until it settles."""
    jobs = graph.services.jobs
    ### an id nobody holds is refused here, before the stream starts: a 404 cannot follow a 200.
    _ = await jobs.status(job_id, caller)
    return follow(jobs.events(job_id, caller))


async def stop(job_id: FromPath[str], graph: NamedDependency[State], caller: NamedDependency[Caller]) -> Job:
    """The job stopped where it awaits; one already settled comes back as it is."""
    return await graph.services.jobs.cancel(job_id, caller)


##### CHAINS #####
DEPS: Final[dict[str, Provide]] = {
    DepKey.GRAPH.value: Provide(graph, sync_to_thread=False),
    DepKey.CALLER.value: Provide(caller, sync_to_thread=False),
}
OPTIONS: Final[dict[str, Any]] = {
    "tags": ["jobs"],
    "dependencies": DEPS,
    "exception_handlers": {UnknownJobError: missing},
    "opt": OPT[Access.USER],
    "security": SECURITY,
}

##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = (
    get("/jobs/{job_id:str}", name="jobs.show", **OPTIONS)(show),
    get("/jobs/{job_id:str}/events", name="jobs.events", **OPTIONS)(events),
    delete("/jobs/{job_id:str}", name="jobs.stop", status_code=HTTP_200_OK, **OPTIONS)(stop),
)
