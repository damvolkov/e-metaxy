"""e_organon.services.tekton.status: tekton/status — a task's state, held until it ends when asked to wait.

The wait is a stream: one `wait` step per `TICK` seconds while the task runs — a client sees the service is alive and
the task is not done — then the task. An MCP client times out long before a coder finishes, so a wait is capped well
under that."""

import math
from itertools import count
from typing import TYPE_CHECKING, Final

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import StatusIn, TaskOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

WAIT_CAP: Final[float] = 25.0
TICK: Final[float] = 2.0


##### TOOL #####
class StatusTektonService(ToolFlow[StatusIn, TaskOut]):
    """tekton/status: a task now, or once it ends or the wait runs out."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: StatusIn) -> AsyncIterator[Event]:
        wait = min(max(data.wait, 0.0), WAIT_CAP)
        total, ticks = max(1, math.ceil(wait / TICK)), count()
        async for _ in self._bridge.watch(data.task, wait, TICK):
            yield Step(name="wait", index=next(ticks), total=total)
        yield Done(result=TaskOut.of(await self._bridge.status(data.task)))
