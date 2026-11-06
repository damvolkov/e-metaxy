"""tests/unit/e_organon/services/doc/ocr: doc/ocr over the real PDF adapters and an engine of the tests' own — a PDF page is
drawn at the asked resolution and its words come back in points on the displayed page (origin bottom-left, as doc/stamp
places things), an image is one page a pixel a point, and the budgets and a refusal end the run in `Failed`."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.doc import OcrIn
from e_organon.models.error import OutsideRootsError
from e_organon.models.flow import Done, Failed, Step
from e_organon.services.doc.ocr import OcrDocService

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
    from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
    from e_organon.services.files import AllowedFiles
    from support.ocr import FakeOcr


async def test_ocr_steps_then_the_pages_read(reader: OcrDocService, vault: Path) -> None:
    events = [event async for event in reader.events(OcrIn(path=str(vault / "three.pdf"), pages=[1]))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "measure", "read"]
    assert isinstance(events[-1], Done)


@pytest.mark.parametrize(("dpi", "box"), [(72, (10, 782, 110, 822)), (144, (5, 812, 55, 832))], ids=["72dpi", "144dpi"])
async def test_ocr_pdf_words_in_points_from_the_bottom_left(
    reader: OcrDocService, vault: Path, dpi: int, box: tuple[float, float, float, float]
) -> None:
    out = await reader.run(OcrIn(path=str(vault / "labelled.pdf"), dpi=dpi))
    page = out.pages[0]
    assert ((page.width, page.height), page.words[0].text, page.words[0].box) == ((595, 842), "uno", box)


async def test_ocr_text_breaks_lines_where_the_words_do(reader: OcrDocService, vault: Path) -> None:
    out = await reader.run(OcrIn(path=str(vault / "labelled.pdf")))
    assert out.pages[0].text == "uno dos\ntres"


async def test_ocr_reads_the_asked_pages_or_all(reader: OcrDocService, vault: Path) -> None:
    one = await reader.run(OcrIn(path=str(vault / "three.pdf"), pages=[2]))
    every = await reader.run(OcrIn(path=str(vault / "three.pdf")))
    assert ([page.page for page in one.pages], [page.page for page in every.pages]) == ([2], [0, 1, 2])


async def test_ocr_a_turned_page_is_read_as_displayed(reader: OcrDocService, vault: Path) -> None:
    out = await reader.run(OcrIn(path=str(vault / "sideways.pdf"), dpi=72))
    assert (out.pages[0].width, out.pages[0].height) == (842, 595)


async def test_ocr_an_image_is_one_page_a_pixel_a_point(reader: OcrDocService, vault: Path, fake_ocr: FakeOcr) -> None:
    out = await reader.run(OcrIn(path=str(vault / "ink.png"), language="spa"))
    page = out.pages[0]
    width, height, language = fake_ocr.seen[0]
    assert (page.page, (page.width, page.height), page.words[0].box, language) == (
        0,
        (width, height),
        (10, height - 60, 110, height - 20),
        "spa",
    )


@pytest.mark.parametrize("name", ["labelled.pdf", "ink.png"], ids=["page", "image"])
async def test_ocr_over_the_pixel_budget_is_refused_unread(
    fake_ocr: FakeOcr, pdf: PikepdfAdapter, render: PdfiumAdapter, files: AllowedFiles, vault: Path, name: str
) -> None:
    tight = OcrDocService(fake_ocr, pdf, render, files, max_pixels=10_000)
    events = [event async for event in tight.events(OcrIn(path=str(vault / name)))]
    assert isinstance(events[-1], Failed)
    assert (events[-1].kind, "pixels" in events[-1].reason, fake_ocr.seen) == ("ImageTooLargeError", True, [])


async def test_ocr_a_path_outside_the_roots_fails_the_run(reader: OcrDocService) -> None:
    events = [event async for event in reader.events(OcrIn(path="/etc/hostname"))]
    assert isinstance(events[-1], Failed)
    assert events[-1].kind == OutsideRootsError.__name__


async def test_ocr_a_page_the_pdf_lacks_fails_the_run(reader: OcrDocService, vault: Path) -> None:
    events = [event async for event in reader.events(OcrIn(path=str(vault / "three.pdf"), pages=[1, 7]))]
    assert events[-1] == Failed(kind="PageNotFoundError", reason="page 7 is outside 0-2")
