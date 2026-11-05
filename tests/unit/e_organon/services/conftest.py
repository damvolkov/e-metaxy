"""tests/unit/e_organon/services: the job service over a real dispatch engine on memory, three tools of the tests' own
registered as kinds of the `doc` queue."""

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

import pytest

from e_organon.engines.dispatch import DispatchEngine
from e_organon.infra.background import Background
from e_organon.services.jobs import JobsService
from support.tools import BoomTool, ShoutTool, SlowTool, crash

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from e_organon.services.flow import ToolFlow


@pytest.fixture
def shout() -> ShoutTool:
    return ShoutTool()


@pytest.fixture
def boom() -> BoomTool:
    return BoomTool()


@pytest.fixture
def slow() -> SlowTool:
    return SlowTool()


@pytest.fixture
def dispatch() -> DispatchEngine:
    """Memory only, a progress write at every report."""
    return DispatchEngine(None, Background(), {}, throttle=0.0)


@pytest.fixture
def jobs(
    dispatch: DispatchEngine, shout: ShoutTool, boom: BoomTool, slow: SlowTool
) -> AbstractAsyncContextManager[JobsService]:
    """The service with the dispatch entered once everything is registered, as the lifespan does: `doc/shout`,
    `doc/boom`, `doc/slow`, two slots, and `doc/crash`, a work that dies without a word. A scope to `async with`: the
    dispatch's task group enters and leaves in the test's own task."""
    tools: dict[str, ToolFlow] = {"doc/shout": shout, "doc/boom": boom, "doc/slow": slow}
    service = JobsService(dispatch, tools, poll=0.01)
    service.register({"doc": 2})
    dispatch.register("doc/crash", crash, queue="doc")

    @asynccontextmanager
    async def opened() -> AsyncGenerator[JobsService]:
        async with dispatch:
            yield service

    return opened()
