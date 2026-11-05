"""e_organon.services.image.cutout: image/cutout — the ink of a photographed signature as a transparent PNG, kept in the outbox.

The photo is measured from its header first and refused over the pixel budget (ORGANON_MAX_PIXELS): the decode that
follows allocates in proportion to the pixels, so the budget has to be checked before it. Four steps: the path made
safe, the size measured, the ink cut, the PNG kept."""

from typing import TYPE_CHECKING

from e_organon.models.doc import FileOut
from e_organon.models.error import ImageTooLargeError
from e_organon.models.flow import Done, Event, Step
from e_organon.models.image import CutoutIn
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.cutout import CutoutPort
    from e_organon.services.files import AllowedFiles

STEPS: tuple[str, ...] = ("resolve", "measure", "cut", "keep")


##### TOOL #####
class CutoutImageService(ToolFlow[CutoutIn, FileOut]):
    """image/cutout: the ink of a photo, alone, on a transparent PNG."""

    __slots__ = ("_artifacts", "_cutout", "_files", "_max_pixels")

    def __init__(self, cutout: CutoutPort, files: AllowedFiles, artifacts: ArtifactEngine, *, max_pixels: int) -> None:
        self._cutout = cutout
        self._files = files
        self._artifacts = artifacts
        self._max_pixels = max_pixels

    ##### PRIVATE #####

    async def _events_measure(self, raw: bytes) -> None:
        width, height = await self._cutout.size(raw)
        match width * height <= self._max_pixels:
            case False:
                msg = f"{width}x{height} is {width * height} pixels; the limit is {self._max_pixels}"
                raise ImageTooLargeError(msg)

    async def _events_run(self, data: CutoutIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        await self._events_measure(raw)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        png = await self._cutout.cut(raw, color=data.color, crop=data.crop)
        yield Step(name=STEPS[3], index=3, total=len(STEPS))
        kept = await self._artifacts.keep(png, f"{path.stem}-cutout", ".png")
        yield Done(result=FileOut(path=str(kept), size=len(png)))
