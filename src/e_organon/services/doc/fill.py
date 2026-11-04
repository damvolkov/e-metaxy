"""e_organon.services.doc.fill: doc/fill — a PDF form's fields written by name, appearances drawn, kept in the outbox.

The names are the full names `doc/inspect` lists; a name the form does not have refuses the whole fill."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut, FillIn
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.pdf import PdfPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "fill", "keep")


##### TOOL #####
class FillDocService(ToolFlow[FillIn, FileOut]):
    """doc/fill: a filled copy of a PDF form."""

    __slots__ = ("_artifacts", "_files", "_pdf")

    def __init__(self, pdf: PdfPort, files: AllowedFiles, artifacts: ArtifactEngine) -> None:
        self._pdf = pdf
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    async def _events_run(self, data: FillIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        filled = await self._pdf.fill(raw, data.values)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        kept = await self._artifacts.keep(filled, f"{path.stem}-filled", ".pdf")
        yield Done(result=FileOut(path=str(kept), size=len(filled)))
