"""e_organon.services.tekton.peers: tekton/peers — the Claude Code sessions open in a terminal right now."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import PeersIn, PeersOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("list",)


##### TOOL #####
class PeersTektonService(ToolFlow[PeersIn, PeersOut]):
    """tekton/peers: live sessions by name, idle or busy; `tekton/send` reaches one."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: PeersIn) -> AsyncIterator[Event]:  # noqa: ARG002 — the workflow takes no argument
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=PeersOut(peers=await self._bridge.peers()))
