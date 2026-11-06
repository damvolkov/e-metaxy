"""tests/support/raster: small images with a known picture — four coloured quadrants, so an orientation, a crop or a rotation
can be read off a pixel — in any format, with the EXIF orientation or a colour profile on request."""

import io
import struct
from collections.abc import Awaitable, Callable

from PIL import Image, ImageCms

from e_organon.ports.raster import RasterSpec

type Write = Callable[[bytes, RasterSpec], Awaitable[bytes]]

RED, GREEN, BLUE, YELLOW = (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)
W, H = 120, 80


def quadrants(size: tuple[int, int] = (W, H), mode: str = "RGB") -> Image.Image:
    """Top-left red, top-right green, bottom-left blue, bottom-right yellow."""
    image = Image.new("RGB", size)
    half_w, half_h = size[0] // 2, size[1] // 2
    for box, colour in (
        ((0, 0, half_w, half_h), RED),
        ((half_w, 0, size[0], half_h), GREEN),
        ((0, half_h, half_w, size[1]), BLUE),
        ((half_w, half_h, size[0], size[1]), YELLOW),
    ):
        image.paste(colour, box)
    return image.convert(mode)


def encode(image: Image.Image, codec: str, **params: object) -> bytes:
    sink = io.BytesIO()
    image.save(sink, codec, **params)
    return sink.getvalue()


def exif_of(orientation: int, *, artist: str = "ana") -> Image.Exif:
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x013B] = artist
    return exif


def sample(codec: str = "PNG", mode: str = "RGB", **params: object) -> bytes:
    return encode(quadrants(mode=mode), codec, **params)


def wide_gamut() -> bytes:
    """A minimal ICC profile (matrix and gamma 2.2, Display P3's primaries adapted to D50): an RGB image that carries it
    must change when taken to sRGB."""

    def xyz(x: float, y: float, z: float) -> bytes:
        return b"XYZ \0\0\0\0" + b"".join(struct.pack(">i", round(v * 65536)) for v in (x, y, z))

    curve = b"curv\0\0\0\0" + struct.pack(">IH", 1, round(2.2 * 256)) + b"\0\0"
    tags = {
        b"wtpt": xyz(0.9642, 1.0, 0.8249),
        b"rXYZ": xyz(0.5151, 0.2412, -0.0011),
        b"gXYZ": xyz(0.2920, 0.6922, 0.0419),
        b"bXYZ": xyz(0.1571, 0.0666, 0.7841),
        b"rTRC": curve,
        b"gTRC": curve,
        b"bTRC": curve,
    }
    table, body, offset = b"", b"", 128 + 4 + 12 * len(tags)
    for name, data in tags.items():
        table += name + struct.pack(">II", offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    header = (
        struct.pack(">I4sI4s4s4s", offset + len(body), b"", 0x02100000, b"mntr", b"RGB ", b"XYZ ")
        + b"\0" * 12
        + b"acsp"
        + b"\0" * 24
        + struct.pack(">iii", round(0.9642 * 65536), 65536, round(0.8249 * 65536))
    )
    return (header + b"\0" * (128 - len(header))) + struct.pack(">I", len(tags)) + table + body


def srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def opened(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


def near(pixel: object, colour: tuple[int, int, int], slack: int = 40) -> bool:
    return all(abs(a - b) <= slack for a, b in zip(pixel, colour, strict=True))  # ty: ignore[invalid-argument-type]


def rgb(image: Image.Image, xy: tuple[int, int]) -> tuple[int, int, int]:
    """The pixel as RGB, whatever the mode."""
    red, green, blue = image.convert("RGB").getpixel(xy)  # ty: ignore[not-iterable]
    return red, green, blue


def alpha(image: Image.Image, xy: tuple[int, int]) -> int:
    """The pixel's alpha, 255 where the mode has none."""
    return image.convert("RGBA").getpixel(xy)[3]  # ty: ignore[not-subscriptable]
