"""e_organon.mcp.tools.organon: organon itself as tools — the jobs a tool made when asked to answer later.

A tool queued over REST with `Prefer: respond-async` answers `202` with its job — a header an MCP call cannot carry, so
the door only reads jobs, it does not make them; `organon_job` reads that job, held up to
`wait` seconds until it settles, and `organon_cancel` stops it. The answer is the job: its `state`, and in `progress` the
`steps` entered so far and, at the end, `done` (the tool's answer) or `failed` (its `kind` and `reason`)."""

from typing import Final

from litestar.di import NamedDependency
from litestar.handlers import HTTPRouteHandler
from litestar.params import JSONBody

from e_organon.api.router import doc as router
from e_organon.infra.auth.models import Access
from e_organon.infra.mcp.models import MCPTool
from e_organon.infra.state import State
from e_organon.mcp.refusals import REFUSALS
from e_organon.models.job import CancelJobIn, Job, StatusJobIn

##### TOOLS — what a client is told #####
JOB: Final = MCPTool(
    name="organon_job",
    title="Check a job",
    description=(
        "A job — a tool run in the background — by `job`: its `state` (available, running, completed, failed, "
        "cancelled), its `progress` (`steps` entered so far; at the end `done`, the tool's answer, or `failed`) and its "
        "`errors`. `wait`: seconds to hold the answer until it settles (0-25; 0 answers at once)."
    ),
)
CANCEL: Final = MCPTool(
    name="organon_cancel",
    title="Cancel a job",
    description="A job by `job`, stopped where it awaits; one already settled comes back as it is.",
    read_only=False,
    destructive=True,
)


##### HANDLERS #####
async def job(data: JSONBody[StatusJobIn], graph: NamedDependency[State]) -> Job:
    return await graph.services.jobs.status(data.job, data.wait)


async def cancel(data: JSONBody[CancelJobIn], graph: NamedDependency[State]) -> Job:
    return await graph.services.jobs.cancel(data.job)


##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = tuple(
    tool.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(handler)
    for tool, handler in ((JOB, job), (CANCEL, cancel))
)
