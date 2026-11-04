"""tests/unit/e_organon/providers/adapters/render/pdfium: pages drawn as PNG at the asked resolution."""

import io

import pytest
from PIL import Image

from e_organon.infra.errors import ParseError
from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
from support.pdf import blank


@pytest.fixture
async def render() -> PdfiumAdapter:
    async with PdfiumAdapter() as opened:
        return opened


async def test_pdfium_health(render: PdfiumAdapter) -> None:
    assert await render.health()


async def test_pdfium_counts_and_draws_a_page(render: PdfiumAdapter) -> None:
    image = Image.open(io.BytesIO(await render.page(blank(2), 1, 72)))
    assert (await render.count(blank(2)), image.format, image.size) == (2, "PNG", (595, 842))


async def test_pdfium_refuses_a_page_outside(render: PdfiumAdapter) -> None:
    with pytest.raises(ParseError, match="outside"):
        await render.page(blank(1), 3, 72)


async def test_pdfium_refuses_what_is_not_a_pdf(render: PdfiumAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable PDF"):
        await render.count(b"hello")
