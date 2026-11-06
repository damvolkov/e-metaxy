"""e_organon.mcp.tools.organon: organon itself as tools — the catalog of its tools, and the jobs a tool made when asked
to answer later.

`organon_find` is the twin of `api/router/organon`, whose very handler it is: the tools that answer a need, ranked.

A tool queued over REST with `Prefer: respond-async` answers `202` with its job — a header an MCP call cannot carry, so
`organon_submit` is the way in: any tool that runs as a job, by its name and its input; `organon_job` reads that job,
held up to `wait` seconds until it settles, and `organon_cancel` stops it. The answer is the job: its `state`, and in `progress` the
`steps` entered so far and, at the end, `done` (the tool's answer) or `failed` (its `kind` and `reason`)."""

from typing import Final

from litestar.di import NamedDependency
from litestar.handlers import HTTPRouteHandler
from litestar.params import JSONBody

from e_organon.api.router import jobs as jobs_router
from e_organon.api.router import organon as router
from e_organon.infra.auth.models import Access, Caller
from e_organon.infra.mcp.models import MCPTool
from e_organon.infra.state import State
from e_organon.mcp.refusals import REFUSALS
from e_organon.models.job import CancelJobIn, Job, StatusJobIn

##### TOOLS — what a client is told #####
FIND: Final = MCPTool(
    name="organon_find",
    title="Find a tool",
    description=(
        "The tools that answer a need, best first (at most 5): `query` in words, `section` (doc, tekton…) to narrow. "
        "Each comes with its description and its arguments' JSON Schema."
    ),
)
SUBMIT: Final = MCPTool(
    name="organon_submit",
    title="Run a tool as a job",
    description=(
        "A tool run in the background: `tool` is its name as `organon_find` lists it with a slash (`doc/convert`), `input` "
        "its arguments. Answers at once with the `job` to follow with organon_job; the input is checked first, a "
        "tool that is no job (tekton, organon) refused."
    ),
    read_only=False,
)
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
async def job(data: JSONBody[StatusJobIn], graph: NamedDependency[State], caller: NamedDependency[Caller]) -> Job:
    return await graph.services.jobs.status(data.job, caller, data.wait)


async def cancel(data: JSONBody[CancelJobIn], graph: NamedDependency[State], caller: NamedDependency[Caller]) -> Job:
    return await graph.services.jobs.cancel(data.job, caller)


##### ROUTES #####
ROUTES: tuple[HTTPRouteHandler, ...] = (
    FIND.route(Access.USER, dependencies=router.TOOL_DEPS, exception_handlers=REFUSALS)(router.find),
    SUBMIT.route(Access.USER, dependencies=router.SUBMIT_DEPS, exception_handlers=REFUSALS)(router.submit),
    *(
        tool.route(Access.USER, dependencies=jobs_router.DEPS, exception_handlers=REFUSALS)(handler)
        for tool, handler in ((JOB, job), (CANCEL, cancel))
    ),
)
