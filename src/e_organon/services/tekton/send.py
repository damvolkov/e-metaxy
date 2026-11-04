"""e_organon.services.tekton.send: tekton/send — a message delivered to an open session's inbox."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import SendIn
from e_organon.ports.coder import CoderReceipt
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("send",)


##### TOOL #####
class SendTektonService(ToolFlow[SendIn, CoderReceipt]):
    """tekton/send: whether the message reached the peer — delivery, not what the session answers."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: SendIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=await self._bridge.send(data.peer, data.text))
