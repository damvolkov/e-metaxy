"""tests/unit/e_organon/providers/adapters/barcode/zxing: barcodes written and read back, found where they were put — in
any orientation, inverted, several to a page, on a picture a camera stored turned."""

from typing import TYPE_CHECKING

import pytest
import zxingcpp

from e_organon.infra.errors import ParseError
from e_organon.ports.barcode import BarcodeFormat
from support.barcode import EAN_AT, EAN_TEXT, QR_AT, QR_TEXT, box, code, inside, jpeg_stored_turned, page, png
from support.raster import opened

if TYPE_CHECKING:
    from e_organon.providers.adapters.barcode.zxing import ZxingAdapter

### UPC-A is read as the EAN-13 it is a case of (a leading zero), UPC-E as its expanded UPC-A: zxing reports what the bars say.
READ = {BarcodeFormat.UPCA: ("0036000291452", "ean13"), BarcodeFormat.UPCE: ("0012345000065", "upce")}
TEXTS = {
    BarcodeFormat.QRCODE: "hello ñ",
    BarcodeFormat.DATAMATRIX: "dm-1",
    BarcodeFormat.AZTEC: "aztec 1",
    BarcodeFormat.PDF417: "pdf417",
    BarcodeFormat.CODE128: "ABC-123",
    BarcodeFormat.CODE39: "CODE39",
    BarcodeFormat.EAN13: "5901234123457",
    BarcodeFormat.EAN8: "96385074",
    BarcodeFormat.UPCA: "036000291452",
    BarcodeFormat.UPCE: "01234565",
    BarcodeFormat.ITF: "123456",
}


async def test_zxing_health(barcode: ZxingAdapter) -> None:
    assert await barcode.health()


@pytest.mark.parametrize("kind", list(BarcodeFormat))
async def test_zxing_what_it_writes_it_reads(barcode: ZxingAdapter, kind: BarcodeFormat) -> None:
    image = await barcode.write(TEXTS[kind], kind, scale=4, hrt=False)
    (hit,) = await barcode.read(image)
    assert (opened(image).format, hit.text, hit.format) == ("PNG", *READ.get(kind, (TEXTS[kind], kind.value)))


async def test_zxing_same_input_same_bytes(barcode: ZxingAdapter) -> None:
    once = await barcode.write(QR_TEXT, BarcodeFormat.QRCODE, scale=5, hrt=False)
    assert once == await barcode.write(QR_TEXT, BarcodeFormat.QRCODE, scale=5, hrt=False)


async def test_zxing_scale_is_pixels_per_module(barcode: ZxingAdapter) -> None:
    small = opened(await barcode.write("x", BarcodeFormat.QRCODE, scale=2, hrt=False))
    big = opened(await barcode.write("x", BarcodeFormat.QRCODE, scale=6, hrt=False))
    assert big.width == small.width * 3


async def test_zxing_hrt_adds_the_human_readable_line_to_a_linear_code(barcode: ZxingAdapter) -> None:
    plain = opened(await barcode.write(EAN_TEXT, BarcodeFormat.EAN13, scale=3, hrt=False))
    with_text = opened(await barcode.write(EAN_TEXT, BarcodeFormat.EAN13, scale=3, hrt=True))
    assert with_text.height > plain.height


@pytest.mark.parametrize(
    ("text", "kind"),
    [("abc", BarcodeFormat.EAN13), ("123456789012345678", BarcodeFormat.EAN13), ("é", BarcodeFormat.CODE39)],
)
async def test_zxing_a_text_the_format_cannot_hold_is_a_parse_error(
    barcode: ZxingAdapter, text: str, kind: BarcodeFormat
) -> None:
    with pytest.raises(ParseError, match="cannot write"):
        await barcode.write(text, kind, scale=2, hrt=False)


async def test_zxing_reads_every_code_of_a_page_where_it_sits(barcode: ZxingAdapter) -> None:
    sheet = page(ean=True)
    qr_box = box(code(QR_TEXT, zxingcpp.BarcodeFormat.QRCode), QR_AT)
    ean_box = box(code(EAN_TEXT, zxingcpp.BarcodeFormat.EAN13, 2), EAN_AT)
    hits = {hit.text: hit for hit in await barcode.read(png(sheet))}
    assert (
        sorted(hits),
        hits[QR_TEXT].format,
        hits[EAN_TEXT].format,
        inside(hits[QR_TEXT].corners, qr_box),
        inside(hits[EAN_TEXT].corners, ean_box),
    ) == (sorted([QR_TEXT, EAN_TEXT]), "qrcode", "ean13", True, True)


async def test_zxing_corners_run_clockwise_from_the_codes_top_left(barcode: ZxingAdapter) -> None:
    (hit,) = await barcode.read(png(page()))
    (left_top, right_top, right_bottom, left_bottom) = hit.corners
    assert (left_top[0] < right_top[0], left_top[1] < left_bottom[1], right_bottom[0] > left_bottom[0]) == (True,) * 3


async def test_zxing_reads_a_turned_page(barcode: ZxingAdapter) -> None:
    (hit,) = await barcode.read(png(page().rotate(90, expand=True)))
    assert hit.text == QR_TEXT


async def test_zxing_reads_light_on_dark(barcode: ZxingAdapter) -> None:
    (hit,) = await barcode.read(png(page(dark=True)))
    assert hit.text == QR_TEXT


async def test_zxing_positions_are_of_the_picture_as_seen(barcode: ZxingAdapter) -> None:
    qr_box = box(code(QR_TEXT, zxingcpp.BarcodeFormat.QRCode), QR_AT)
    (hit,) = await barcode.read(jpeg_stored_turned(page()))
    assert inside(hit.corners, qr_box, 8)


async def test_zxing_a_page_without_codes_has_none(barcode: ZxingAdapter) -> None:
    assert await barcode.read(png(page(qr=False))) == ()


async def test_zxing_no_image_is_a_parse_error(barcode: ZxingAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await barcode.read(b"nothing here")
