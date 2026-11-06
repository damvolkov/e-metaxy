"""ports/raster: a raster image read, reshaped and written — what a thumbnail, a format change, a colour fix or the reading
of its metadata needs, with no pixel left to the caller.

Pixels are the oriented image's: the EXIF orientation is applied first, so `crop`, `width`, `height` and `rotate` all speak
of the picture as a person sees it."""

from enum import StrEnum, auto
from typing import Annotated, Literal, Protocol, runtime_checkable

import msgspec

from e_organon.ports.provider import Provider

SIDE = Annotated[int, msgspec.Meta(ge=1, le=65535)]
QUALITY = Annotated[int, msgspec.Meta(ge=1, le=100)]


##### VALUES #####
class RasterFormat(StrEnum):
    """What an image is written as: the codecs every wheel of the service carries."""

    JPEG = auto()
    PNG = auto()
    WEBP = auto()
    TIFF = auto()
    AVIF = auto()


class RasterFit(StrEnum):
    """How the image meets the `width` x `height` box: `contain` fits inside it keeping the aspect (never enlarged), `cover`
    fills it keeping the aspect and cuts the centre off what overflows, `stretch` is the box exactly."""

    CONTAIN = auto()
    COVER = auto()
    STRETCH = auto()


class RasterSpec(msgspec.Struct, frozen=True, kw_only=True):
    """What `convert` does, in this order: crop to `crop` (left, top, right, bottom, in pixels), resize to the box, rotate
    `rotate` degrees clockwise, colour to sRGB when `srgb`, write as `format` at `quality` (lossy codecs; a missing format is the
    source's, PNG when that one cannot be written). Metadata is stripped; `keep` leaves the EXIF and the colour profile."""

    format: RasterFormat | None = None
    width: SIDE | None = None
    height: SIDE | None = None
    fit: RasterFit = RasterFit.CONTAIN
    crop: tuple[int, int, int, int] | None = None
    rotate: Literal[0, 90, 180, 270] = 0
    quality: QUALITY = 85
    srgb: bool = True
    keep: bool = False


class RasterImage(msgspec.Struct, frozen=True, kw_only=True):
    """An image written: its bytes and the format they are in."""

    data: bytes
    format: RasterFormat


##### PORT #####
@runtime_checkable
class RasterPort(Provider, Protocol):
    """`size` is an image's width and height read from its header, nothing decoded; `convert` the image written as the spec
    says, with the format it chose (a first frame only, for an animation). Bytes that are no image, or a spec that cannot hold (a crop outside the
    picture), are a `ParseError`."""

    async def size(self, data: bytes) -> tuple[int, int]: ...

    async def convert(self, data: bytes, spec: RasterSpec) -> RasterImage: ...
