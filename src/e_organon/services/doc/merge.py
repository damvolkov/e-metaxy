"""e_organon.services.doc.merge: doc/merge — PDFs joined into one, in the order given, kept in the outbox."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut, MergeIn
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.pdf import PdfPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "merge", "keep")


##### TOOL #####
class MergeDocService(ToolFlow[MergeIn, FileOut]):
    """doc/merge: one PDF from many."""

    __slots__ = ("_artifacts", "_files", "_pdf")

    def __init__(self, pdf: PdfPort, files: AllowedFiles, artifacts: ArtifactEngine) -> None:
        self._pdf = pdf
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    async def _events_run(self, data: MergeIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        parts = [(await self._files.read(path))[1] for path in data.paths]
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        merged = await self._pdf.merge(parts)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        kept = await self._artifacts.keep(merged, data.name, ".pdf")
        yield Done(result=FileOut(path=str(kept), size=len(merged)))
