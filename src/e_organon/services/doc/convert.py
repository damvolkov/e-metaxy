"""e_organon.services.doc.convert: doc/convert — any document to Markdown, read by the engine that reads it best.

The workflow is `processors/doc`'s DocProcessor: liteparse page by page, docling-serve where a page's signals ask for
it (tables, figures, scans) and the server is there, anytomd for every other format. Two steps: the path made safe,
then the reading."""

from typing import TYPE_CHECKING

from e_organon.models.doc import ConvertIn, ConvertOut
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.services.files import AllowedFiles
    from processors.doc import DocProcessor

STEPS: tuple[str, ...] = ("resolve", "read")


##### TOOL #####
class ConvertDocService(ToolFlow[ConvertIn, ConvertOut]):
    """doc/convert: a document under the allowed roots, as Markdown."""

    __slots__ = ("_doc", "_files")

    def __init__(self, doc: DocProcessor, files: AllowedFiles) -> None:
        self._doc = doc
        self._files = files

    ##### PRIVATE #####

    async def _events_run(self, data: ConvertIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path = await self._files.resolve(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        markdown = await self._doc.text(path, name=path.name)
        yield Done(result=ConvertOut(name=path.name, markdown=markdown))
