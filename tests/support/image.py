"""tests/support/image: the shape of the image-tool fixtures — a builder of each tool with a pixel budget."""

from collections.abc import Callable

from e_organon.services.image.convert import ConvertImageService
from e_organon.services.image.cutout import CutoutImageService

type Build = Callable[..., CutoutImageService]
type BuildConvert = Callable[..., ConvertImageService]
