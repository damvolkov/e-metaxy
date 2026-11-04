"""e_organon.services.tekton.catalog: tekton/catalog — the commands, skills and agents the coder offers in a project.

Read from the CLI's own initialize answer: no prompt, no model turn, no cost."""

from typing import TYPE_CHECKING

from e_organon.models.flow import Done, Event, Step
from e_organon.models.tekton import CatalogIn
from e_organon.ports.coder import CoderCatalog
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.bridge import BridgeEngine

STEPS: tuple[str, ...] = ("read",)


##### TOOL #####
class CatalogTektonService(ToolFlow[CatalogIn, CoderCatalog]):
    """tekton/catalog: what the coder can do in one project."""

    __slots__ = ("_bridge",)

    def __init__(self, bridge: BridgeEngine) -> None:
        self._bridge = bridge

    ##### PRIVATE #####

    async def _events_run(self, data: CatalogIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        yield Done(result=await self._bridge.catalog(data.project))
