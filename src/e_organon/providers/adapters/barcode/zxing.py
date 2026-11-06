"""providers/adapters/barcode/zxing: barcodes read and written with zxing-cpp (C++, in process).

The reader is given the picture as seen — EXIF orientation applied, grey — so the corners it reports are the ones a person
would point at. The writer asks zxing for the code and Pillow for the PNG, which is reproducible: the same text, format and scale
give the same bytes. Everything runs in a worker thread: zxing releases the GIL while it scans."""

import io
import warnings
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Final, Self

import anyio
import numpy as np
import zxingcpp
from PIL import Image, ImageOps, UnidentifiedImageError

from e_organon.infra.errors import ParseError
from e_organon.ports.barcode import BarcodeFormat, BarcodeHit
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from collections.abc import Mapping

FORMATS: Final[Mapping[BarcodeFormat, zxingcpp.BarcodeFormat]] = MappingProxyType(
    {
        BarcodeFormat.QRCODE: zxingcpp.BarcodeFormat.QRCode,
        BarcodeFormat.DATAMATRIX: zxingcpp.BarcodeFormat.DataMatrix,
        BarcodeFormat.AZTEC: zxingcpp.BarcodeFormat.Aztec,
        BarcodeFormat.PDF417: zxingcpp.BarcodeFormat.PDF417,
        BarcodeFormat.CODE128: zxingcpp.BarcodeFormat.Code128,
        BarcodeFormat.CODE39: zxingcpp.BarcodeFormat.Code39,
        BarcodeFormat.EAN13: zxingcpp.BarcodeFormat.EAN13,
        BarcodeFormat.EAN8: zxingcpp.BarcodeFormat.EAN8,
        BarcodeFormat.UPCA: zxingcpp.BarcodeFormat.UPCA,
        BarcodeFormat.UPCE: zxingcpp.BarcodeFormat.UPCE,
        BarcodeFormat.ITF: zxingcpp.BarcodeFormat.ITF,
    }
)


##### ADAPTER #####
class ZxingAdapter:
    """Barcode reading and writing; nothing to open, nothing to close."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("zxing", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.THREAD)

    ##### PRIVATE #####

    @staticmethod
    def _read_open(data: bytes) -> Image.Image:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                return ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        except (
            UnidentifiedImageError,
            OSError,
            SyntaxError,
            ValueError,
            EOFError,
            Image.DecompressionBombError,
        ) as error:
            msg = f"not a readable image: {error}"
            raise ParseError(msg) from error

    @staticmethod
    def _read_hit(code: zxingcpp.Barcode) -> BarcodeHit:
        corners = code.position
        top_left, top_right, bottom_right, bottom_left = (
            (corner.x, corner.y)
            for corner in (corners.top_left, corners.top_right, corners.bottom_right, corners.bottom_left)
        )
        return BarcodeHit(
            text=code.text,
            format=code.format.name.lower(),
            corners=(top_left, top_right, bottom_right, bottom_left),
        )

    def _read_run(self, data: bytes) -> tuple[BarcodeHit, ...]:
        return tuple(self._read_hit(code) for code in zxingcpp.read_barcodes(self._read_open(data)))

    @staticmethod
    def _write_run(text: str, kind: BarcodeFormat, *, scale: int, hrt: bool) -> bytes:
        try:
            code = zxingcpp.create_barcode(text, FORMATS[kind])
        except ValueError as error:
            msg = f"cannot write {text!r} as {kind.value}: {error}"
            raise ParseError(msg) from error
        bitmap = zxingcpp.write_barcode_to_image(code, scale=scale, add_hrt=hrt)
        sink = io.BytesIO()
        Image.fromarray(np.asarray(bitmap)).save(sink, "PNG")
        return sink.getvalue()

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def read(self, data: bytes) -> tuple[BarcodeHit, ...]:
        return await anyio.to_thread.run_sync(self._read_run, data)

    async def write(self, text: str, kind: BarcodeFormat, *, scale: int, hrt: bool) -> bytes:
        return await anyio.to_thread.run_sync(lambda: self._write_run(text, kind, scale=scale, hrt=hrt))
