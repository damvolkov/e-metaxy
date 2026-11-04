"""e_organon.services.tekton.find: tekton/find — recorded sessions, newest first, of a project or all of them."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import FindIn, FindOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("search",)


##### TOOL #####
class FindTektonService(ToolFlow[FindIn, FindOut]):
    """tekton/find: sessions whose title, branch or tag holds a text, in one project or in all."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: FindIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=FindOut(sessions=await self._bridge.find(data.project, data.text, data.limit)))
