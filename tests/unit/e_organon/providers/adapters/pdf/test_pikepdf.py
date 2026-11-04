"""tests/unit/e_organon/providers/adapters/pdf/pikepdf: a PDF's structure read and edited in memory — every field kind
named, merge and split by page, a form filled with its appearances, and a broken file as `ParseError`."""

import pytest

from e_organon.infra.errors import ParseError
from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
from support.pdf import A4, blank, form


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
