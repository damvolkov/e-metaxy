"""e_organon.models.image: what the image/ tools take — a file by path under ORGANON_ROOTS; what they give is a `FileOut`
(`models.doc`), the file in the outbox, named by its content."""

import msgspec

from e_organon.models.doc import FileOut
from e_organon.ports.barcode import SCALE, BarcodeFormat, BarcodeHit
from e_organon.ports.raster import RasterSpec


##### CUTOUT #####
class CutoutIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: the photo (`~` expands). `color`: the ink keeps its own colour; off, it is black. `crop`: the PNG is cut to
    the ink with a small margin; off, it is the photo's size. `lines`: long straight runs are printed lines, not ink; off
    keeps every stroke, a straight underline of the signature included."""

    path: str
    color: bool = True
    crop: bool = True
    lines: bool = True


##### CONVERT #####
class ConvertIn(RasterSpec, frozen=True, kw_only=True):
    """`path`: the image (`~` expands); the rest is the `RasterSpec` (`ports.raster`): `format` (jpeg, png, webp, tiff, avif;
    the source's by default), `width`/`height` the box with `fit` (contain, cover, stretch), `crop` the (left, top, right,
    bottom) pixels kept, `rotate` clockwise degrees, `quality` of the lossy codecs, `srgb` colour to sRGB, `keep` the
    EXIF and colour profile (stripped by default)."""

    path: str


##### BARCODE #####
class BarcodeIn(msgspec.Struct, frozen=True, kw_only=True):
    """`path`: an image to read every barcode of; or `text`: a text to write as one, of `format` (qrcode by default), `scale`
    pixels a module, `hrt` the human-readable line under a linear code. One of the two."""

    path: str | None = None
    text: str | None = None
    format: BarcodeFormat = BarcodeFormat.QRCODE
    scale: SCALE = 8
    hrt: bool = True

    def __post_init__(self) -> None:
        match (self.path is None, self.text is None):
            case (True, True) | (False, False):
                msg = "give a path to read or a text to write, one of the two"
                raise ValueError(msg)


class BarcodeOut(msgspec.Struct, frozen=True, kw_only=True):
    """What was read: the `codes` found, each with its text, format and four corners in pixels; or what was written: the PNG
    as `file`."""

    codes: list[BarcodeHit] = []
    file: FileOut | None = None
