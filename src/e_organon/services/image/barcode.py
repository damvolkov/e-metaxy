"""e_organon.services.image.barcode: image/barcode — the barcodes of an image read with where they sit, or a text written as one
and kept in the outbox.

Reading: the path made safe, the size measured against the pixel budget, the image read. Writing: the barcode drawn, the PNG
kept. The same input gives the same answer."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut
from e_organon.models.flow import Done, Event, Step
from e_organon.models.image import BarcodeIn, BarcodeOut
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.barcode import BarcodePort
    from e_organon.services.files import AllowedFiles
    from e_organon.services.image.budget import BudgetImage

READ: tuple[str, ...] = ("resolve", "measure", "read")
WRITE: tuple[str, ...] = ("write", "keep")


##### TOOL #####
class BarcodeImageService(ToolFlow[BarcodeIn, BarcodeOut]):
    """image/barcode: every code of an image, or a code of a text."""

    __slots__ = ("_artifacts", "_barcode", "_budget", "_files")

    def __init__(
        self, barcode: BarcodePort, files: AllowedFiles, artifacts: ArtifactEngine, budget: BudgetImage
    ) -> None:
        self._barcode = barcode
        self._files = files
        self._artifacts = artifacts
        self._budget = budget

    ##### PRIVATE #####

    async def _events_read(self, path: str) -> AsyncIterator[Event]:
        yield Step(name=READ[0], index=0, total=len(READ))
        _, raw = await self._files.read(path)
        yield Step(name=READ[1], index=1, total=len(READ))
        await self._budget.check(raw)
        yield Step(name=READ[2], index=2, total=len(READ))
        yield Done(result=BarcodeOut(codes=list(await self._barcode.read(raw))))

    async def _events_write(self, data: BarcodeIn) -> AsyncIterator[Event]:
        yield Step(name=WRITE[0], index=0, total=len(WRITE))
        png = await self._barcode.write(data.text or "", data.format, scale=data.scale, hrt=data.hrt)
        yield Step(name=WRITE[1], index=1, total=len(WRITE))
        kept = await self._artifacts.keep(png, f"{data.format.value}", ".png")
        yield Done(result=BarcodeOut(file=FileOut(path=str(kept), size=len(png))))

    async def _events_run(self, data: BarcodeIn) -> AsyncIterator[Event]:
        match data:
            case BarcodeIn(path=str() as path):
                events = self._events_read(path)
            case _:
                events = self._events_write(data)
        async for event in events:
            yield event
