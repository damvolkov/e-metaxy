"""api.lifespan.jobs: every tool a kind of the dispatch, then the dispatch entered — registration is open until then.

The kinds are the tools the services concern built, read off `system.services` — `<section>/<word>` for each, none
listed twice by hand — but the sections in `NOT_JOBS`. Each section runs on a queue of its own with the slots its
setting says (`SLOTS`: a section with tools and no row there stops the start). The engines concern built the dispatch,
PgQueuer on the queue's database with memory behind it; entered here, after the registration, it runs for the app's
life: a queue that cannot be reached is a warning and memory alone, never a crash. `system.services.jobs` is the service
the routes read the jobs through."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any, Final

from litestar import Litestar

from e_organon.api.state import AppState
from e_organon.infra.logger import logger
from e_organon.infra.settings import settings as st
from e_organon.infra.state import State
from e_organon.services.flow import ToolFlow
from e_organon.services.jobs import JobsService

### tekton has its own supervisor and ledger; organon/ answers at once, a job for it would only be latency.
NOT_JOBS: Final[frozenset[str]] = frozenset({"tekton", "organon"})


##### ROWS #####
def tools(services: State) -> dict[str, ToolFlow[Any, Any]]:
    """Every tool of every section but `NOT_JOBS`, by `<section>/<word>`."""
    return {
        f"{section}/{word}": tool
        for section, node in services.items()
        if isinstance(node, State) and section not in NOT_JOBS
        for word, tool in node.items()
        if isinstance(tool, ToolFlow)
    }


def slots() -> Mapping[str, int]:
    """How many jobs of each section run at once: a row per section that has jobs."""
    return {"doc": st.ORGANON_SLOTS_DOC}


@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None]:
    """Register every tool as a kind, then enter the dispatch for the app's life; it closes, cancelling what runs, when
    the app stops."""
    system = AppState.of(app).system
    dispatch = system.engines.dispatch
    jobs = JobsService(dispatch, tools(system.services), poll=st.QUEUE_POLL.total_seconds())
    jobs.register({section: slots()[section] for section in set(jobs.kinds.values())})
    system.services.jobs = jobs
    async with dispatch:
        logger.info("dispatch ready", engine=dispatch.engine, kinds=len(dispatch.kinds), step="START")
        yield
