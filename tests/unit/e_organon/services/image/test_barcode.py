"""tests/unit/e_organon/services/image/barcode: image/barcode over the real adapters — an image read in three steps into its
codes, a text written in two into a PNG in the outbox that reads back; exactly one of the two is asked for."""

from typing import TYPE_CHECKING

import anyio
import msgspec
import pytest

from e_organon.models.flow import Done, Failed, Step
from e_organon.models.image import BarcodeIn, BarcodeOut
from e_organon.ports.barcode import BarcodeFormat
from support.barcode import EAN_TEXT, QR_TEXT, page, png
from support.raster import opened

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.services.image.barcode import BarcodeImageService


async def test_barcode_reads_every_code_of_an_image(barcoder: BarcodeImageService, pictures: Path) -> None:
    events = [event async for event in barcoder.events(BarcodeIn(path=str(pictures / "codes.png")))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "measure", "read"]
    assert isinstance(events[-1], Done)
    out = events[-1].result
    assert isinstance(out, BarcodeOut)
    assert (sorted(hit.text for hit in out.codes), out.file) == (sorted([QR_TEXT, EAN_TEXT]), None)


async def test_barcode_writes_a_text_into_the_outbox_and_it_reads_back(
    barcoder: BarcodeImageService, pictures: Path
) -> None:
    events = [e async for e in barcoder.events(BarcodeIn(text="hola", format=BarcodeFormat.CODE128, scale=3))]
    assert [event.name for event in events if isinstance(event, Step)] == ["write", "keep"]
    assert isinstance(events[-1], Done)
    file = events[-1].result.file
    written = await anyio.Path(file.path).read_bytes()
    back = [e async for e in barcoder.events(BarcodeIn(path=file.path))][-1]
    assert (
        file.path.startswith(str(pictures / "outbox" / "code128-")),
        file.size,
        opened(written).format,
        [hit.text for hit in back.result.codes],  # ty: ignore[unresolved-attribute]
    ) == (True, len(written), "PNG", ["hola"])


async def test_barcode_same_text_same_file(barcoder: BarcodeImageService) -> None:
    first, second = [[e async for e in barcoder.events(BarcodeIn(text="x"))][-1] for _ in range(2)]
    assert first == second


async def test_barcode_a_text_the_format_cannot_hold_fails_with_a_parse_error(barcoder: BarcodeImageService) -> None:
    events = [e async for e in barcoder.events(BarcodeIn(text="abc", format=BarcodeFormat.EAN13))]
    assert isinstance(events[-1], Failed)
    assert events[-1].kind == "ParseError"


async def test_barcode_an_image_without_codes_has_an_empty_list(barcoder: BarcodeImageService, pictures: Path) -> None:
    (pictures / "blank.png").write_bytes(png(page(qr=False)))
    done = [e async for e in barcoder.events(BarcodeIn(path=str(pictures / "blank.png")))][-1]
    assert isinstance(done, Done)
    assert done.result.codes == []


async def test_barcode_refuses_outside_the_roots(barcoder: BarcodeImageService) -> None:
    events = [event async for event in barcoder.events(BarcodeIn(path="/etc/hostname"))]
    assert events[-1].kind == "OutsideRootsError"  # ty: ignore[unresolved-attribute]


@pytest.mark.parametrize(
    "body", [{}, {"path": "/x", "text": "y"}, {"text": "x", "scale": 0}, {"text": "x", "scale": 65}]
)
async def test_barcode_input_asks_for_exactly_one_of_path_and_text(body: dict) -> None:
    with pytest.raises(msgspec.ValidationError):
        msgspec.convert(body, BarcodeIn)
