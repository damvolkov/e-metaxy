"""tests/unit/e_organon/providers/adapters/redact/pymupdf: what is struck is gone — the term is in no extractor's output (pdfium,
the content streams, MuPDF), an image under a box is blank in the render and absent from the file, the metadata and the earlier
revisions are dropped — and what is not struck stays; a regex that never ends is cut; a broken file is a `ParseError`."""

import hashlib
import io
import time
from typing import TYPE_CHECKING

import pikepdf
import pytest

from e_organon.infra.errors import ParseError
from e_organon.ports.redact import RedactBox, RedactPort
from e_organon.providers.adapters.pdf.pikepdf import PikepdfAdapter
from e_organon.providers.adapters.redact.pymupdf import PymupdfAdapter
from support.hostile import garbage_pdf
from support.ink import ink_png
from support.redact import (
    A4,
    IMAGE_BOX,
    TERM,
    aaaa,
    mupdf_text,
    pdfium_text,
    red_left,
    secret,
    stream_text,
    with_history,
)
from support.shot import reddish, shot

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

NONE: tuple[()] = ()


@pytest.fixture
def redactor() -> PymupdfAdapter:
    return PymupdfAdapter(timeout=2.0, max_pages=50)


async def struck(
    redactor: PymupdfAdapter,
    data: bytes,
    *,
    terms: Sequence[str] = NONE,
    regex: bool = False,
    boxes: Sequence[RedactBox] = NONE,
    pages: Sequence[int] = NONE,
) -> bytes:
    return (await redactor.redact(data, terms=terms, regex=regex, boxes=boxes, pages=pages)).data


def test_redact_adapter_is_a_port(redactor: PymupdfAdapter) -> None:
    assert isinstance(redactor, RedactPort)


async def test_redact_health(redactor: PymupdfAdapter) -> None:
    assert await redactor.health()


async def test_redact_a_term_is_in_no_extractor_after(redactor: PymupdfAdapter) -> None:
    before = secret()
    assert all(TERM in read(before) for read in (pdfium_text, mupdf_text, stream_text))
    after = await struck(redactor, before, terms=[TERM])
    assert [TERM in read(after) for read in (pdfium_text, mupdf_text, stream_text)] == [False] * 3
    assert [word in pdfium_text(after) for word in ("Cliente", "BRAVO-456", "pagina dos")] == [True] * 3


async def test_redact_a_term_is_struck_on_every_page_and_counted(redactor: PymupdfAdapter) -> None:
    done = await redactor.redact(secret(), terms=[TERM], regex=False, boxes=NONE, pages=NONE)
    assert (done.count, "pagina dos" in pdfium_text(done.data)) == (2, True)


async def test_redact_a_literal_ignores_case_and_means_what_it_says(redactor: PymupdfAdapter) -> None:
    after = await struck(redactor, secret(), terms=["alfa-123"])
    assert TERM not in pdfium_text(after)
    untouched = await struck(redactor, secret(), terms=["ALFA.123"])
    assert TERM in pdfium_text(untouched)


@pytest.mark.parametrize(("rotate", "crop"), [(90, None), (270, (50, 50, 500, 800))], ids=["90", "cropped-270"])
async def test_redact_a_term_is_found_on_a_turned_or_cropped_page(
    redactor: PymupdfAdapter, rotate: int, crop: tuple[float, float, float, float] | None
) -> None:
    after = await struck(redactor, secret(rotate=rotate, crop=crop), terms=["BRAVO-456"])
    assert ("BRAVO" in pdfium_text(after), "Cliente" in pdfium_text(after)) == (False, True)


async def test_redact_a_regex_strikes_every_match(redactor: PymupdfAdapter) -> None:
    after = await struck(redactor, secret(), terms=[r"[A-Z]+-\d{3}"], regex=True)
    assert [each in pdfium_text(after) for each in (TERM, "BRAVO-456", "Cliente")] == [False, False, True]


async def test_redact_pages_limit_where_a_term_is_looked_for(redactor: PymupdfAdapter) -> None:
    after = await struck(redactor, secret(), terms=[TERM], pages=[1])
    first, second = pdfium_text(after).split("\f")[:2]
    assert (TERM in first, TERM in second) == (True, False)


async def test_redact_a_box_takes_the_text_and_the_image_under_it(redactor: PymupdfAdapter) -> None:
    assert red_left(secret())
    left, bottom, right, top = IMAGE_BOX
    box = RedactBox(page=0, x=left - 5, y=bottom - 5, width=right - left + 10, height=top - bottom + 10)
    after = await struck(redactor, secret(), boxes=[box])
    assert (red_left(after), "Cliente" in pdfium_text(after)) == (False, True)


async def test_redact_a_box_over_text_removes_it(redactor: PymupdfAdapter) -> None:
    after = await struck(redactor, secret(), boxes=[RedactBox(page=0, x=90, y=640, width=200, height=40)])
    assert ("BRAVO" in pdfium_text(after), "Cliente" in pdfium_text(after)) == (False, True)


@pytest.mark.parametrize(
    ("rotate", "crop"), [(90, None), (180, None), (270, (50, 50, 500, 800))], ids=["90", "180", "cropped-270"]
)
async def test_redact_a_box_is_as_displayed_on_a_turned_or_cropped_page(
    redactor: PymupdfAdapter, rotate: int, crop: tuple[float, float, float, float] | None
) -> None:
    ### the box is placed as `doc/stamp` places things: from the displayed page's bottom-left, the page's own geometry applied.
    data = secret(rotate=rotate, crop=crop)
    geometry = (await PikepdfAdapter().geometry(data))[0]
    (x0, y0), (x1, y1) = geometry.shown(100, 645), geometry.shown(300, 665)
    box = RedactBox(page=0, x=min(x0, x1), y=min(y0, y1), width=abs(x1 - x0), height=abs(y1 - y0))
    after = await struck(redactor, data, boxes=[box])
    assert ("BRAVO" in pdfium_text(after), "Cliente" in pdfium_text(after)) == (False, True)


async def test_redact_drops_the_metadata(redactor: PymupdfAdapter) -> None:
    after = await struck(redactor, secret(), terms=[TERM])
    with pikepdf.open(io.BytesIO(after)) as pdf:
        assert (TERM in str(dict(pdf.docinfo)), "/Metadata" in pdf.Root, TERM.encode() in after) == (
            False,
            False,
            False,
        )


async def test_redact_drops_the_earlier_revisions(redactor: PymupdfAdapter, tmp_path: Path) -> None:
    history = with_history(secret(), tmp_path)
    assert TERM.encode() in history
    after = await struck(redactor, history, terms=[TERM])
    assert TERM.encode() not in after


async def test_redact_with_nothing_found_still_cleans_and_counts_zero(redactor: PymupdfAdapter) -> None:
    done = await redactor.redact(secret(), terms=["no-such-text"], regex=False, boxes=NONE, pages=NONE)
    assert (done.count, TERM.encode() in done.data) == (0, False)


async def test_redact_the_same_input_is_the_same_bytes(redactor: PymupdfAdapter) -> None:
    raw = secret()
    first = await struck(redactor, raw, terms=[TERM])
    second = await struck(redactor, raw, terms=[TERM])
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()


async def test_redact_a_regex_that_never_ends_is_cut(redactor: PymupdfAdapter) -> None:
    ### catastrophic backtracking on a page that says `aaaa…`: the timeout is the guard, not the page size.
    started = time.perf_counter()
    with pytest.raises(ParseError, match="regular expression"):
        await struck(PymupdfAdapter(timeout=0.5, max_pages=50), aaaa(), terms=[r"(a|aa)+c"], regex=True)
    assert time.perf_counter() - started < 5


async def test_redact_a_regex_that_does_not_compile_is_a_parse_error(redactor: PymupdfAdapter) -> None:
    with pytest.raises(ParseError, match="regular expression"):
        await struck(redactor, secret(), terms=["("], regex=True)


async def test_redact_a_box_on_a_missing_page_is_a_parse_error(redactor: PymupdfAdapter) -> None:
    with pytest.raises(ParseError, match="page 9"):
        await struck(redactor, secret(), boxes=[RedactBox(page=9, x=0, y=0, width=10, height=10)])


async def test_redact_a_broken_file_is_a_parse_error(redactor: PymupdfAdapter) -> None:
    with pytest.raises(ParseError):
        await struck(redactor, garbage_pdf(), terms=[TERM])


async def test_redact_too_many_pages_is_a_parse_error() -> None:
    with pytest.raises(ParseError, match="pages"):
        await struck(PymupdfAdapter(timeout=2.0, max_pages=1), secret(), terms=[TERM])


async def test_redact_what_is_not_a_pdf_is_a_parse_error(redactor: PymupdfAdapter) -> None:
    with pytest.raises(ParseError, match="not a readable PDF"):
        await struck(redactor, ink_png(), terms=[TERM])


async def test_redact_an_encrypted_pdf_is_a_parse_error(redactor: PymupdfAdapter) -> None:
    sink = io.BytesIO()
    with pikepdf.open(io.BytesIO(secret())) as pdf:
        pdf.save(sink, encryption=pikepdf.Encryption(owner="o", user="u"))
    with pytest.raises(ParseError, match="encrypted"):
        await struck(redactor, sink.getvalue(), terms=[TERM])


async def test_redact_a_box_over_part_of_an_image_blanks_that_part_and_keeps_the_rest(redactor: PymupdfAdapter) -> None:
    left, bottom, right, top = IMAGE_BOX
    half = RedactBox(page=0, x=left, y=bottom, width=(right - left) / 2, height=top - bottom)
    page = shot(await struck(redactor, secret(), boxes=[half]))
    row = int(A4[1] - (top + bottom) / 2)
    assert (
        reddish(page[row, int(left) : int(left + 45)]).any(),
        reddish(page[row, int(left + 55) : int(right)]).all(),
    ) == (
        False,
        True,
    )
