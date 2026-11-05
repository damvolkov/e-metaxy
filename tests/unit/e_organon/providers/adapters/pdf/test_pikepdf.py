"""tests/unit/e_organon/providers/adapters/pdf/pikepdf: a PDF's structure read and edited in memory — every field kind
named, merge and split by page, a form filled with its appearances, and a broken file as `ParseError`."""

import io

import pikepdf
import pytest

from e_organon.infra.errors import ParseError
from e_organon.ports.pdf import PageGeometry, PdfBox
from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
from support.ink import ink_png
from support.pdf import A4, blank, form, placements


@pytest.fixture
async def pdf() -> PikepdfAdapter:
    async with PikepdfAdapter() as opened:
        return opened


async def test_pikepdf_health(pdf: PikepdfAdapter) -> None:
    assert await pdf.health()


async def test_pikepdf_info_names_every_field_kind(pdf: PikepdfAdapter) -> None:
    info = await pdf.info(form())
    kinds = {field.name: field.kind for field in info.fields}
    assert (info.pages, info.metadata["Title"], kinds) == (
        (A4,),
        "Solicitud",
        {
            "persona.nombre": "text",
            "acepta": "checkbox",
            "sexo": "radio",
            "enviar": "button",
            "pais": "choice",
            "firma": "signature",
        },
    )
    assert next(field for field in info.fields if field.name == "acepta").rect == (100.0, 660.0, 115.0, 675.0)


async def test_pikepdf_merge_and_split(pdf: PikepdfAdapter) -> None:
    merged = await pdf.merge([blank(2), blank(3)])
    first, rest = await pdf.split(merged, [(0, 0), (1, 4)])
    assert [len((await pdf.info(part)).pages) for part in (merged, first, rest)] == [5, 1, 4]


@pytest.mark.parametrize("pages", [(1, 0), (0, 9)], ids=["backwards", "past-the-end"])
async def test_pikepdf_split_refuses_a_range_outside_the_document(pdf: PikepdfAdapter, pages: tuple[int, int]) -> None:
    with pytest.raises(ParseError, match="outside"):
        await pdf.split(blank(2), [pages])


async def test_pikepdf_fill_writes_text_checkbox_and_choice(pdf: PikepdfAdapter) -> None:
    filled = await pdf.fill(form(), {"persona.nombre": "Ana", "acepta": "true", "pais": "ES"})
    values = {field.name: field.value for field in (await pdf.info(filled)).fields}
    unchecked = await pdf.fill(filled, {"acepta": "no"})
    again = {field.name: field.value for field in (await pdf.info(unchecked)).fields}
    assert (values["persona.nombre"], values["acepta"], values["pais"], again["acepta"]) == ("Ana", "Yes", "ES", "Off")


async def test_pikepdf_merge_keeps_the_forms(pdf: PikepdfAdapter) -> None:
    merged = await pdf.merge([form(), blank(1)])
    assert len((await pdf.info(merged)).fields) == 6


async def test_pikepdf_fill_refuses_an_unknown_field(pdf: PikepdfAdapter) -> None:
    with pytest.raises(ParseError, match="no field named nope; the form has acepta"):
        await pdf.fill(form(), {"nope": "x"})


async def test_pikepdf_fill_a_document_without_a_form(pdf: PikepdfAdapter) -> None:
    with pytest.raises(ParseError, match="the form has none"):
        await pdf.fill(blank(1), {"x": "y"})


async def test_pikepdf_refuses_what_is_not_a_pdf(pdf: PikepdfAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable PDF"):
        await pdf.info(b"hello")


async def test_pikepdf_stamps_an_image_fitted_in_its_box(pdf: PikepdfAdapter) -> None:
    """A 2:1 image in a 100x100 box: 100 wide, 50 high, centred; the page's own content untouched."""
    out = await pdf.stamp(blank(1), 0, PdfBox(x=50, y=60, width=100, height=100), image=ink_png(), text=None, opacity=1)
    assert placements(out) == [(100.0, 0.0, 0.0, 50.0, 50.0, 85.0)]


async def test_pikepdf_stamps_an_image_by_width_and_keeps_its_aspect(pdf: PikepdfAdapter) -> None:
    out = await pdf.stamp(blank(1), 0, PdfBox(x=10, y=20, width=80), image=ink_png(), text=None, opacity=1)
    assert placements(out) == [(80.0, 0.0, 0.0, 40.0, 10.0, 20.0)]


async def test_pikepdf_stamps_on_the_page_asked(pdf: PikepdfAdapter) -> None:
    out = await pdf.stamp(blank(2), 1, PdfBox(x=0, y=0, width=10), image=ink_png(), text=None, opacity=1)
    with pikepdf.open(io.BytesIO(out)) as opened:
        assert [len(page.get_images()) for page in opened.pages] == [0, 1]


async def test_pikepdf_stamps_a_text_and_an_opacity(pdf: PikepdfAdapter) -> None:
    out = await pdf.stamp(
        blank(1), 0, PdfBox(x=100, y=100, width=200, height=12), image=None, text="Aprobado €", opacity=0.5
    )
    with pikepdf.open(io.BytesIO(out)) as opened:
        page = opened.pages[0]
        ops = [str(operator) for _, operator in pikepdf.parse_content_stream(page)]
        alpha = float(page.Resources.ExtGState[next(iter(page.Resources.ExtGState.keys()))].ca)
    assert (ops.count("Tj"), alpha) == (1, 0.5)
    hits = await PdfiumAdapter().find(out, "Aprobado")
    assert [(hit.page, round(hit.rect[0])) for hit in hits] == [(0, 100)]


async def test_pikepdf_refuses_a_page_outside(pdf: PikepdfAdapter) -> None:
    with pytest.raises(ParseError, match="outside"):
        await pdf.stamp(blank(1), 3, PdfBox(x=0, y=0, width=10), image=ink_png(), text=None, opacity=1)


async def test_pikepdf_refuses_what_is_not_an_image(pdf: PikepdfAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable image"):
        await pdf.stamp(blank(1), 0, PdfBox(x=0, y=0, width=10), image=b"hello", text=None, opacity=1)


async def test_pikepdf_geometry_reads_the_crop_box_and_an_inherited_turn(pdf: PikepdfAdapter) -> None:
    data = io.BytesIO()
    with pikepdf.new() as made:
        _ = [made.add_blank_page(page_size=A4) for _ in range(2)]
        made.pages[1].obj.CropBox = pikepdf.Array([10, 20, 300, 400])
        made.Root.Pages.Rotate = 270
        made.save(data)
    first, second = await pdf.geometry(data.getvalue())
    assert (first, second) == (
        PageGeometry(left=0, bottom=0, right=595, top=842, rotate=270),
        PageGeometry(left=10, bottom=20, right=300, top=400, rotate=270),
    )
