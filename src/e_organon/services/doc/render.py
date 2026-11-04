"""e_organon.services.doc.render: doc/render — PDF pages as PNG images, kept in the outbox: a thumbnail, a proof, what a
person (or a vision step) sees."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut, FilesOut, RenderIn
from e_organon.models.flow import Done, Event, Step
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.render import RenderPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "render", "keep")


##### TOOL #####
class RenderDocService(ToolFlow[RenderIn, FilesOut]):
    """doc/render: the asked pages (all when none) as PNG."""

    __slots__ = ("_artifacts", "_files", "_render")

    def __init__(self, render: RenderPort, files: AllowedFiles, artifacts: ArtifactEngine) -> None:
        self._render = render
        self._files = files
        self._artifacts = artifacts

    ##### PRIVATE #####

    async def _events_run(self, data: RenderIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        pages = data.pages or list(range(await self._render.count(raw)))
        images = [(index, await self._render.page(raw, index, data.dpi)) for index in pages]
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        files = [
            FileOut(path=str(await self._artifacts.keep(image, f"{path.stem}-p{index}", ".png")), size=len(image))
            for index, image in images
        ]
        yield Done(result=FilesOut(files=files))
