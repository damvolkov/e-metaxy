"""e_organon.services.tekton.cancel: tekton/cancel — a running task interrupted; a finished one comes back unchanged."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import CancelIn, TaskOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("cancel",)


##### TOOL #####
class CancelTektonService(ToolFlow[CancelIn, TaskOut]):
    """tekton/cancel: the task after its run was interrupted; its session can be continued."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: CancelIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=TaskOut.of(await self._bridge.cancel(data.task)))
