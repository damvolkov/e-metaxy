"""tests/unit/e_organon/providers/adapters/compose/typst: a template over data is a PDF/A-2b whose text is the data's, the
same bytes every time; the template reads its own folder and nothing outside it; one that does not compile says where."""

import hashlib
import io
from typing import TYPE_CHECKING

import pikepdf
import pypdfium2 as pdfium
import pytest

from e_organon.infra.errors import ParseError
from e_organon.providers.adapters.compose.typst import TypstAdapter

if TYPE_CHECKING:
    from pathlib import Path

HELLO = b'#let data = json(bytes(sys.inputs.data))\nHola, #data.name: #data.items.map(str).join(", ")\n'
DATA = {"name": "Ñandú", "items": [1, 2, 3]}


def text_of(pdf: bytes) -> str:
    return pdfium.PdfDocument(pdf)[0].get_textpage().get_text_range()


async def test_typst_composes_the_data_into_a_pdf(tmp_path: Path) -> None:
    pdf = await TypstAdapter().compose(HELLO, DATA, tmp_path)
    assert (pdf[:5], text_of(pdf).strip()) == (b"%PDF-", "Hola, Ñandú: 1, 2, 3")


async def test_typst_declares_pdf_a_2b(tmp_path: Path) -> None:
    with pikepdf.open(io.BytesIO(await TypstAdapter().compose(HELLO, DATA, tmp_path))) as pdf:
        assert (str(pdf.open_metadata()["pdfaid:part"]), "/OutputIntents" in pdf.Root) == ("2", True)


async def test_typst_the_same_input_is_the_same_bytes(tmp_path: Path) -> None:
    ### the key order of the data does not matter either: it is written sorted.
    first = await TypstAdapter().compose(HELLO, DATA, tmp_path)
    second = await TypstAdapter().compose(HELLO, dict(reversed(DATA.items())), tmp_path)
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()


async def test_typst_the_template_reads_files_under_its_root(tmp_path: Path) -> None:
    (tmp_path / "name.txt").write_text("desde el disco")
    pdf = await TypstAdapter().compose(b'#read("name.txt")', {}, tmp_path)
    assert text_of(pdf).strip() == "desde el disco"


async def test_typst_the_template_cannot_read_outside_its_root(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("nope")
    inside = tmp_path / "templates"
    inside.mkdir()
    with pytest.raises(ParseError, match="escape the project root"):
        await TypstAdapter().compose(b'#read("../secret.txt")', {}, inside)


async def test_typst_a_template_that_does_not_compile_says_where(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="unknown variable"):
        await TypstAdapter().compose(b"#nope", {}, tmp_path)


async def test_typst_health() -> None:
    assert await TypstAdapter().health()
