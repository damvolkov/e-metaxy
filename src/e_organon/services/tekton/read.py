"""e_organon.services.tekton.read: tekton/read — a session and its last turns: what it was about, where it stopped."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import ReadIn
from e_organon.ports.coder import SessionRead
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("read",)


##### TOOL #####
class ReadTektonService(ToolFlow[ReadIn, SessionRead]):
    """tekton/read: a session found by what a caller copies — its id, a prefix of it, or its exact title."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: ReadIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=await self._bridge.read(data.session, data.last))
