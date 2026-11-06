"""e_organon.services.image.budget: the pixel budget (ORGANON_MAX_PIXELS) every image tool that decodes keeps.

The image is measured from its header first and refused over the budget: the decode that follows allocates in proportion to
the pixels, so the budget has to be checked before it."""

from typing import TYPE_CHECKING

from e_organon.models.error import ImageTooLargeError

if TYPE_CHECKING:
    from e_organon.ports.raster import RasterPort


##### GUARD #####
class BudgetImage:
    """The header's width x height against `max_pixels`."""

    __slots__ = ("_max_pixels", "_raster")

    def __init__(self, raster: RasterPort, *, max_pixels: int) -> None:
        self._raster = raster
        self._max_pixels = max_pixels

    ##### PUBLIC #####

    async def check(self, raw: bytes) -> tuple[int, int]:
        """The image's size, or `ImageTooLargeError`."""
        width, height = await self._raster.size(raw)
        match width * height <= self._max_pixels:
            case False:
                msg = f"{width}x{height} is {width * height} pixels; the limit is {self._max_pixels}"
                raise ImageTooLargeError(msg)
            case _:
                return width, height
