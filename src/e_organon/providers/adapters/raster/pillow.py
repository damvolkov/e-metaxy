"""providers/adapters/raster/pillow: raster images read, reshaped and written with Pillow, in process.

Pillow won the bench against libvips (`docs/bench/image.md`): vips was faster (0.57 of the time) but used 1.6 times the
memory and ships no wheel; Pillow is already here and writes JPEG, PNG, WebP, TIFF and AVIF out of its own wheels. The
order is fixed — EXIF orientation first, so every number a caller gives speaks of the picture as seen —, crop, resize, rotate,
colour, write. A JPEG that is only resized is shrunk on load (`draft`: the DCT scales by 1/2, 1/4, 1/8 before the pixels
exist), which is where most of its time goes. Nothing the encoders add that varies is left in: no timestamps, no software tag,
no metadata unless `keep`; the same input and spec are the same bytes. Everything runs in a worker thread: Pillow releases
the GIL in decode, resize and encode."""

import io
import struct
import warnings
from math import ceil
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self

import anyio
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from e_organon.infra.errors import ParseError
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload
from e_organon.ports.raster import RasterFit, RasterFormat, RasterImage, RasterSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

### how each codec is asked: Pillow's name for it and the parameters that make it reproducible (lossless TIFF; the lossy ones take
### the spec's quality).
CODECS: Final[Mapping[RasterFormat, Callable[[int], Mapping[str, Any]]]] = MappingProxyType(
    {
        RasterFormat.JPEG: lambda quality: {"format": "JPEG", "quality": quality},
        RasterFormat.PNG: lambda _quality: {"format": "PNG", "compress_level": 6},
        RasterFormat.WEBP: lambda quality: {"format": "WEBP", "quality": quality},
        RasterFormat.TIFF: lambda _quality: {"format": "TIFF", "compression": "tiff_adobe_deflate"},
        RasterFormat.AVIF: lambda quality: {"format": "AVIF", "quality": quality},
    }
)
ROTATIONS: Final[Mapping[int, Image.Transpose | None]] = MappingProxyType(
    {0: None, 90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180, 270: Image.Transpose.ROTATE_90}
)
### modes a codec takes as they are; any other is taken to RGB(A) first.
PLAIN: Final[frozenset[str]] = frozenset({"L", "LA", "RGB", "RGBA"})
ALPHA: Final[frozenset[str]] = frozenset({"LA", "RGBA", "PA"})
### what Pillow raises on bytes that are no image, or are cut short.
UNREADABLE: Final[tuple[type[Exception], ...]] = (
    UnidentifiedImageError,
    OSError,
    SyntaxError,
    ValueError,
    EOFError,
    struct.error,
    Image.DecompressionBombError,
)
### the orientations that turn the picture on its side: the stored box is the shown one with width and height swapped.
UPRIGHT: Final[int] = 1


##### ADAPTER #####
class PillowAdapter:
    """Raster conversion; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("pillow", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

    ##### PRIVATE #####

    @staticmethod
    def _common_open(data: bytes) -> Image.Image:
        """The image, header only: Pillow warns above 89 MP and refuses above 179 MP; the service's budget is the limit that
        counts (checked from `size` before any decode), so only the refusal is let through."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                return Image.open(io.BytesIO(data))
        except UNREADABLE as error:
            msg = f"not a readable image: {error}"
            raise ParseError(msg) from error

    @staticmethod
    def _convert_load(image: Image.Image) -> Image.Image:
        try:
            image.load()
        except UNREADABLE as error:
            msg = f"not a readable image: {error}"
            raise ParseError(msg) from error
        return image

    @staticmethod
    def _convert_draft(image: Image.Image, spec: RasterSpec) -> None:
        """A JPEG that is only resized in `contain` is decoded at 1/2, 1/4 or 1/8 when the box allows: never below the box."""
        match (image.format, spec.crop, spec.fit):
            case ("JPEG", None, RasterFit.CONTAIN) if image.getexif().get(0x0112, UPRIGHT) == UPRIGHT:
                scale = min((spec.width or image.width) / image.width, (spec.height or image.height) / image.height, 1)
                image.draft(None, (ceil(image.width * scale), ceil(image.height * scale)))

    @staticmethod
    def _convert_crop(image: Image.Image, crop: tuple[int, int, int, int] | None) -> Image.Image:
        match crop:
            case None:
                return image
            case (left, top, right, bottom) if 0 <= left < right <= image.width and 0 <= top < bottom <= image.height:
                return image.crop(crop)
            case _:
                msg = f"crop {crop} is outside the {image.width}x{image.height} picture"
                raise ParseError(msg)

    @staticmethod
    def _convert_resize(image: Image.Image, spec: RasterSpec) -> Image.Image:
        box = (spec.width or image.width, spec.height or image.height)
        match spec.fit:
            case RasterFit.CONTAIN:
                image.thumbnail(box, Image.Resampling.LANCZOS)
                return image
            case RasterFit.COVER:
                return ImageOps.fit(image, box, Image.Resampling.LANCZOS)
            case RasterFit.STRETCH:
                return image.resize(box, Image.Resampling.LANCZOS)

    @staticmethod
    def _convert_rotate(image: Image.Image, degrees: int) -> Image.Image:
        match ROTATIONS[degrees]:
            case None:
                return image
            case turn:
                return image.transpose(turn)

    @staticmethod
    def _convert_plain(image: Image.Image) -> Image.Image:
        """A mode the codecs take: 16-bit grey shrinks to 8, a palette becomes colour (with alpha where it has one), the
        rest of the exotic ones RGB."""
        match image.mode:
            case mode if mode in PLAIN:
                return image
            case "1":
                return image.convert("L")
            case "I;16" | "I;16L" | "I;16B" | "I":
                return image.point(lambda value: value * (1 / 256)).convert("L")
            case "P" | "PA":
                return image.convert("RGBA" if image.mode == "PA" or "transparency" in image.info else "RGB")
            case _:
                return image.convert("RGB")

    @staticmethod
    def _convert_color(image: Image.Image, icc: bytes | None, *, srgb: bool) -> tuple[Image.Image, bytes | None]:
        """The pixels in sRGB when the file carries a profile of its own (the sRGB one is kept as the profile to embed on
        `keep`), a profile that lcms cannot read leaves them as they are. CMYK needs it to reach RGB at all."""
        profile = icc
        match (srgb and icc is not None, image.mode):
            case (True, "RGB" | "RGBA" | "CMYK") if icc is not None:
                try:
                    source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                    target = ImageCms.createProfile("sRGB")
                    out_mode = "RGB" if image.mode == "CMYK" else image.mode
                    image = ImageCms.profileToProfile(image, source, target, outputMode=out_mode) or image
                    profile = ImageCms.ImageCmsProfile(target).tobytes()
                except ImageCms.PyCMSError:
                    pass
        return (image.convert("RGB") if image.mode == "CMYK" else image), profile

    @staticmethod
    def _convert_target(source: str | None) -> RasterFormat:
        """The source's own format when it can be written, PNG when not (a GIF, a BMP)."""
        return RasterFormat.__members__.get((source or "").upper(), RasterFormat.PNG)

    @staticmethod
    def _convert_flat(image: Image.Image) -> Image.Image:
        """What a codec without alpha (JPEG) gets: the picture over white."""
        match image.mode:
            case "RGBA" | "LA":
                base = Image.new("RGBA", image.size, (255, 255, 255, 255))
                flat = Image.alpha_composite(base, image.convert("RGBA")).convert("RGB")
                return flat.convert("L") if image.mode == "LA" else flat
            case _:
                return image

    def _convert_run(self, data: bytes, spec: RasterSpec) -> RasterImage:
        image = self._common_open(data)
        source = image.format
        icc = image.info.get("icc_profile")
        self._convert_draft(image, spec)
        image = ImageOps.exif_transpose(self._convert_load(image))
        exif = image.getexif().tobytes()
        image = self._convert_resize(self._convert_crop(image, spec.crop), spec)
        image = self._convert_rotate(image, spec.rotate)
        image, icc = self._convert_color(self._convert_plain(image), icc, srgb=spec.srgb)
        target = spec.format or self._convert_target(source)
        image = self._convert_flat(image) if target is RasterFormat.JPEG else image
        extra = {"exif": exif, "icc_profile": icc} if spec.keep else {}
        sink = io.BytesIO()
        image.save(sink, **CODECS[target](spec.quality), **{k: v for k, v in extra.items() if v})
        return RasterImage(data=sink.getvalue(), format=target)

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def size(self, data: bytes) -> tuple[int, int]:
        return await anyio.to_thread.run_sync(lambda: self._common_open(data).size)

    async def convert(self, data: bytes, spec: RasterSpec) -> RasterImage:
        return await anyio.to_thread.run_sync(self._convert_run, data, spec)
