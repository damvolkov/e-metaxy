"""e_organon.services.tekton.update: tekton/update — a session renamed and/or tagged."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import UpdateIn
from e_organon.ports.coder import CoderSession
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("update",)


##### TOOL #####
class UpdateTektonService(ToolFlow[UpdateIn, CoderSession]):
    """tekton/update: the session after its title and/or tag were set."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: UpdateIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=await self._bridge.update(data.session, data.title, data.tag))
