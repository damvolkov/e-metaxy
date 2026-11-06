"""e_organon.services.image.convert: image/convert — an image reshaped (format, size, crop, rotation, colour) and kept in the outbox.

Four steps: the path made safe, the size measured against the pixel budget, the image converted, the file kept. The
EXIF orientation is applied and the metadata stripped, so the same picture and spec are the same bytes."""

from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from e_organon.models.doc import FileOut
from e_organon.models.flow import Done, Event, Step
from e_organon.models.image import ConvertIn
from e_organon.ports.raster import RasterFormat
from e_organon.services.flow import ToolFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from e_organon.engines.artifact import ArtifactEngine
    from e_organon.ports.raster import RasterPort
    from e_organon.services.files import AllowedFiles
    from e_organon.services.image.budget import BudgetImage

STEPS: tuple[str, ...] = ("resolve", "measure", "convert", "keep")
SUFFIXES: Final[Mapping[RasterFormat, str]] = MappingProxyType(
    {
        RasterFormat.JPEG: ".jpg",
        RasterFormat.PNG: ".png",
        RasterFormat.WEBP: ".webp",
        RasterFormat.TIFF: ".tif",
        RasterFormat.AVIF: ".avif",
    }
)


##### TOOL #####
class ConvertImageService(ToolFlow[ConvertIn, FileOut]):
    """image/convert: the image in another shape."""

    __slots__ = ("_artifacts", "_budget", "_files", "_raster")

    def __init__(self, raster: RasterPort, files: AllowedFiles, artifacts: ArtifactEngine, budget: BudgetImage) -> None:
        self._raster = raster
        self._files = files
        self._artifacts = artifacts
        self._budget = budget

    ##### PRIVATE #####

    async def _events_run(self, data: ConvertIn) -> AsyncIterator[Event]:
        yield Step(name=STEPS[0], index=0, total=len(STEPS))
        path, raw = await self._files.read(data.path)
        yield Step(name=STEPS[1], index=1, total=len(STEPS))
        await self._budget.check(raw)
        yield Step(name=STEPS[2], index=2, total=len(STEPS))
        image = await self._raster.convert(raw, data)
        yield Step(name=STEPS[3], index=3, total=len(STEPS))
        kept = await self._artifacts.keep(image.data, f"{path.stem}-convert", SUFFIXES[image.format])
        yield Done(result=FileOut(path=str(kept), size=len(image.data)))
