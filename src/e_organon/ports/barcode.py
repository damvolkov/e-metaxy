"""ports/barcode: the barcodes on an image, read with where they sit, and a text written as one — what a label, a ticket or a
document with a QR needs."""

from enum import StrEnum, auto
from typing import Annotated, Protocol, runtime_checkable

import msgspec

from e_organon.ports.provider import Provider

SCALE = Annotated[int, msgspec.Meta(ge=1, le=64)]


##### VALUES #####
class BarcodeFormat(StrEnum):
    """What can be written: the matrix codes and the common linear ones. More are read than written."""

    QRCODE = auto()
    DATAMATRIX = auto()
    AZTEC = auto()
    PDF417 = auto()
    CODE128 = auto()
    CODE39 = auto()
    EAN13 = auto()
    EAN8 = auto()
    UPCA = auto()
    UPCE = auto()
    ITF = auto()


class BarcodeHit(msgspec.Struct, frozen=True, kw_only=True):
    """A barcode found: its `text`, its `format` (lower case: `qrcode`, `ean13`, `code128`…) and its four `corners` as (x, y)
    pixels of the picture as seen (EXIF orientation applied), clockwise from the code's own top-left."""

    text: str
    format: str
    corners: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]


##### PORT #####
@runtime_checkable
class BarcodePort(Provider, Protocol):
    """`read` every valid barcode of an image, in any orientation, light on dark too — none is an empty tuple —; `write` a
    text as a PNG at `scale` pixels per module, with its human-readable line under a linear code when `hrt`. Bytes that are
    no image, or a text the format cannot hold (digits only for EAN, a wrong length), are a `ParseError`."""

    async def read(self, data: bytes) -> tuple[BarcodeHit, ...]: ...

    async def write(self, text: str, kind: BarcodeFormat, *, scale: int, hrt: bool) -> bytes: ...
