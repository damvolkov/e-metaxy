"""tests/unit/e_organon/providers/adapters/compose/typst: a template over data is a PDF/A-2b whose text is the data's, the
same bytes every time; the template reads its own folder and nothing outside it; one that does not compile says where."""

import hashlib
import io
import time
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
    pdf = await TypstAdapter(timeout=10.0).compose(HELLO, DATA, tmp_path)
    assert (pdf[:5], text_of(pdf).strip()) == (b"%PDF-", "Hola, Ñandú: 1, 2, 3")


async def test_typst_declares_pdf_a_2b(tmp_path: Path) -> None:
    with pikepdf.open(io.BytesIO(await TypstAdapter(timeout=10.0).compose(HELLO, DATA, tmp_path))) as pdf:
        assert (str(pdf.open_metadata()["pdfaid:part"]), "/OutputIntents" in pdf.Root) == ("2", True)


async def test_typst_the_same_input_is_the_same_bytes(tmp_path: Path) -> None:
    ### the key order of the data does not matter either: it is written sorted.
    first = await TypstAdapter(timeout=10.0).compose(HELLO, DATA, tmp_path)
    second = await TypstAdapter(timeout=10.0).compose(HELLO, dict(reversed(DATA.items())), tmp_path)
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()


async def test_typst_the_template_reads_files_under_its_root(tmp_path: Path) -> None:
    (tmp_path / "name.txt").write_text("desde el disco")
    pdf = await TypstAdapter(timeout=10.0).compose(b'#read("name.txt")', {}, tmp_path)
    assert text_of(pdf).strip() == "desde el disco"


async def test_typst_the_template_cannot_read_outside_its_root(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("nope")
    inside = tmp_path / "templates"
    inside.mkdir()
    with pytest.raises(ParseError, match=r"escape the project root|file not found"):
        await TypstAdapter(timeout=10.0).compose(b'#read("../secret.txt")', {}, inside)


async def test_typst_a_template_that_does_not_compile_says_where(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match=r"unknown variable"):
        await TypstAdapter(timeout=10.0).compose(b"#nope", {}, tmp_path)


async def test_typst_health() -> None:
    assert await TypstAdapter(timeout=10.0).health()


@pytest.mark.parametrize(
    "source",
    [
        b'#import "@preview/cetz:0.3.0": canvas',
        b'#include "@local/anything:1.0.0"',
        b'#let name = "@pre" + "view/cetz:0.3.0"\n#import name: canvas',
    ],
    ids=["import", "include", "built-at-runtime"],
)
async def test_typst_a_package_is_never_fetched(tmp_path: Path, source: bytes) -> None:
    ### the first two are refused before compiling; the third slips past a text scan and meets a process with no way out.
    with pytest.raises(ParseError):
        await TypstAdapter(timeout=10.0).compose(source, {}, tmp_path)


async def test_typst_a_static_package_refusal_says_why(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match=r"packages are not available"):
        await TypstAdapter(timeout=10.0).compose(b'#import "@preview/cetz:0.3.0"', {}, tmp_path)


@pytest.mark.parametrize(
    "path", ["/etc/passwd", "../secret.txt", "/etc/../etc/hostname"], ids=["absolute", "up", "dotdot"]
)
async def test_typst_a_read_outside_the_folder_is_refused(tmp_path: Path, path: str) -> None:
    inside = tmp_path / "templates"
    inside.mkdir()
    with pytest.raises(ParseError, match=r"escape the project root|file not found"):
        await TypstAdapter(timeout=10.0).compose(f'#read("{path}")'.encode(), {}, inside)


async def test_typst_a_template_that_does_not_end_is_cut_at_the_timeout(tmp_path: Path) -> None:
    started = time.perf_counter()
    with pytest.raises(ParseError, match=r"longer than 0.5"):
        await TypstAdapter(timeout=0.5).compose(b"#for i in range(30000) { for j in range(30000) { } }", {}, tmp_path)
    assert time.perf_counter() - started < 3


async def test_typst_after_a_cut_the_next_template_composes(tmp_path: Path) -> None:
    adapter = TypstAdapter(timeout=0.5)
    with pytest.raises(ParseError):
        await adapter.compose(b"#for i in range(30000) { for j in range(30000) { } }", {}, tmp_path)
    assert (await adapter.compose(HELLO, DATA, tmp_path))[:5] == b"%PDF-"


async def test_typst_a_template_that_asks_for_too_much_memory_fails_cleanly(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match=r"memory allocation"):
        await TypstAdapter(timeout=10.0).compose(b"#for i in range(2000000000) { }", {}, tmp_path)
