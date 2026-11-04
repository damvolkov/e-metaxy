"""e_organon.services.tekton.start: tekton/start — a prompt run in Claude Code on this machine, in the background.

The bridge opens the task under the profile's policy and answers at once with it; the run proceeds on its own, and
`tekton/status` watches it. One step: the order placed."""

from typing import TYPE_CHECKING

from e_organon.engines.bridge import TaskOrder
from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import StartIn, TaskOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("order",)


##### TOOL #####
class StartTektonService(ToolFlow[StartIn, TaskOut]):
    """tekton/start: a prompt run on a coder under a profile, in a project."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: StartIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        order = TaskOrder(
            prompt=data.prompt, profile=data.profile, cwd=data.project, session=data.session, fork=data.fork
        )
        yield Done(result=TaskOut.of(await self._bridge.start(order)))
