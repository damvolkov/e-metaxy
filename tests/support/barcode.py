"""tests/support/barcode: pages with barcodes at known places — a code drawn by zxing-cpp itself pasted at a box on a white
page, so the corners a reader reports can be held to where it was put."""

import numpy as np
import zxingcpp
from PIL import Image

from support.raster import encode, exif_of

PAGE = (400, 300)
QR_AT = (40, 30)
EAN_AT = (180, 200)
QR_TEXT = "https://example.org/organon?x=1"
EAN_TEXT = "5901234123457"


def code(text: str, kind: zxingcpp.BarcodeFormat, scale: int = 4) -> Image.Image:
    bitmap = zxingcpp.write_barcode_to_image(zxingcpp.create_barcode(text, kind), scale=scale)
    return Image.fromarray(np.asarray(bitmap))


def page(*, qr: bool = True, ean: bool = False, dark: bool = False) -> Image.Image:
    """White page (black, with `dark`, the codes inverted) holding a QR at `QR_AT` and an EAN-13 at `EAN_AT`."""
    sheet = Image.new("L", PAGE, 0 if dark else 255)
    pasted = [
        (code(QR_TEXT, zxingcpp.BarcodeFormat.QRCode), QR_AT, qr),
        (code(EAN_TEXT, zxingcpp.BarcodeFormat.EAN13, 2), EAN_AT, ean),
    ]
    [sheet.paste(img.point(lambda v: 255 - v) if dark else img, at) for img, at, wanted in pasted if wanted]
    return sheet


def png(sheet: Image.Image) -> bytes:
    return encode(sheet, "PNG")


def box(image: Image.Image, at: tuple[int, int]) -> tuple[int, int, int, int]:
    return at[0], at[1], at[0] + image.width, at[1] + image.height


def inside(corners: tuple[tuple[int, int], ...], where: tuple[int, int, int, int], slack: int = 6) -> bool:
    left, top, right, bottom = where
    return all(left - slack <= x <= right + slack and top - slack <= y <= bottom + slack for x, y in corners)


def jpeg_stored_turned(sheet: Image.Image) -> bytes:
    """The page as a camera stores it: pixels rotated a quarter turn, EXIF orientation 6 saying how to show it upright."""

    return encode(sheet.rotate(90, expand=True), "JPEG", exif=exif_of(6), quality=95)
