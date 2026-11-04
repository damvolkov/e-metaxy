"""e_organon.services.doc.split: doc/split — a PDF cut into page ranges, one file per range, kept in the outbox."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut, FilesOut, SplitIn
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.pdf import PdfPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "split", "keep")


##### TOOL #####
class SplitDocService(ToolFlow[SplitIn, FilesOut]):
    """doc/split: page ranges as their own PDFs."""

    __slots__ = ("_artifacts", "_files", "_pdf")

    def __init__(self, pdf: PdfPort, files: AllowedFiles, artifacts: ArtifactEngine) -> None:
        self._pdf = pdf
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    async def _events_run(self, data: SplitIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        parts = await self._pdf.split(raw, data.ranges)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        files = [
            FileOut(path=str(await self._artifacts.keep(part, f"{path.stem}-p{first}-{last}", ".pdf")), size=len(part))
            for part, (first, last) in zip(parts, data.ranges, strict=True)
        ]
        yield Done(result=FilesOut(files=files))
