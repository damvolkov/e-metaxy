"""tests/unit/e_organon/providers/adapters/render/pdfium: pages drawn as PNG at the asked resolution."""

import io

import pytest
from PIL import Image

from e_organon.infra.errors import ParseError
from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
from support.pdf import blank, labelled


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


async def test_pdfium_finds_a_text_in_page_order(render: PdfiumAdapter) -> None:
    hits = await render.find(labelled(), "firma:")
    left, bottom, right, top = hits[0].rect
    assert [hit.page for hit in hits] == [0, 0]
    assert (99 <= left <= 102, 700 - 4 <= bottom <= 700, 700 + 8 <= top <= 700 + 16, 30 <= right - left <= 50) == (
        True,
        True,
        True,
        True,
    )
    assert hits[1].rect[1] < hits[0].rect[1]


async def test_pdfium_finds_nothing_where_the_text_is_not(render: PdfiumAdapter) -> None:
    assert await render.find(labelled(), "nowhere") == ()


async def test_pdfium_refuses_more_pages_than_its_budget() -> None:
    with pytest.raises(ParseError, match=r"2 pages; the limit is 1"):
        await PdfiumAdapter(max_pages=1).count(blank(2))
