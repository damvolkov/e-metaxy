"""e_organon.services.doc.inspect: doc/inspect — a PDF at a glance, in a few hundred bytes of JSON.

Pages and their sizes, metadata, and every form field with its page, rectangle and value: what an agent needs to decide
what `doc/fill` should write where, without ever reading the PDF itself."""

from typing import TYPE_CHECKING

from e_organon.models.doc import InspectIn, InspectOut
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.ports.pdf import PdfPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "read")


##### TOOL #####
class InspectDocService(ToolFlow[InspectIn, InspectOut]):
    """doc/inspect: a PDF's pages, metadata and form fields."""

    __slots__ = ("_files", "_pdf")

    def __init__(self, pdf: PdfPort, files: AllowedFiles) -> None:
        self._pdf = pdf
        self._files = files

    ##### PRIVATE #####

    async def _events_run(self, data: InspectIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        info = await self._pdf.info(raw)
        yield Done(
            result=InspectOut(name=path.name, pages=list(info.pages), metadata=info.metadata, fields=list(info.fields))
        )
