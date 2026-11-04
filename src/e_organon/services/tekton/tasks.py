"""e_organon.services.tekton.tasks: tekton/tasks — the newest tasks first: what is running, what finished."""

from typing import TYPE_CHECKING

from e_organon.engines.bridge import TaskState
from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import TaskOut, TasksIn, TasksOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("list",)


##### TOOL #####
class TasksTektonService(ToolFlow[TasksIn, TasksOut]):
    """tekton/tasks: the ledger's newest tasks, of one state or all."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: TasksIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        state = None if data.state is None else TaskState(data.state)
        tasks = await self._bridge.tasks(state, data.limit)
        yield Done(result=TasksOut(tasks=[TaskOut.of(task) for task in tasks]))
