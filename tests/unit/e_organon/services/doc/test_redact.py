"""tests/unit/e_organon/services/doc/redact: doc/redact over the real MuPDF adapter — a path under the roots becomes a copy in
the outbox with the struck text and image gone for every reader, the same file for the same input; what is not a PDF, or lies
outside the roots, fails the run."""

from typing import TYPE_CHECKING

import anyio
import pytest

from e_organon.models.doc import RedactIn
from e_organon.models.flow import Done, Failed, Step
from e_organon.ports.redact import RedactBox
from support.redact import IMAGE_BOX, TERM, mupdf_text, pdfium_text, red_left, stream_text

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.services.doc.redact import RedactDocService


async def redacted(redactor: RedactDocService, order: RedactIn) -> bytes:
    out = await redactor.run(order)
    return await anyio.Path(out.path).read_bytes()


async def test_redact_steps_then_the_copy(redactor: RedactDocService, secret: Path) -> None:
    events = [event async for event in redactor.events(RedactIn(path=str(secret), terms=[TERM]))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "redact", "keep"]
    assert isinstance(events[-1], Done)


async def test_redact_a_term_is_gone_for_every_reader(redactor: RedactDocService, secret: Path) -> None:
    out = await redactor.run(RedactIn(path=str(secret), terms=[TERM]))
    after = await anyio.Path(out.path).read_bytes()
    assert (out.count, out.size, [TERM in read(after) for read in (pdfium_text, mupdf_text, stream_text)]) == (
        2,
        len(after),
        [False] * 3,
    )


async def test_redact_a_box_takes_the_image_under_it(redactor: RedactDocService, secret: Path) -> None:
    left, bottom, right, top = IMAGE_BOX
    box = RedactBox(page=0, x=left, y=bottom, width=right - left, height=top - bottom)
    assert red_left(await anyio.Path(secret).read_bytes())
    assert not red_left(await redacted(redactor, RedactIn(path=str(secret), boxes=[box])))


async def test_redact_a_regex_over_some_pages(redactor: RedactDocService, secret: Path) -> None:
    after = await redacted(redactor, RedactIn(path=str(secret), terms=[r"ALFA-\d+"], regex=True, pages=[0]))
    first, second = pdfium_text(after).split("\f")[:2]
    assert (TERM in first, TERM in second) == (False, True)


async def test_redact_the_same_input_is_the_same_file(redactor: RedactDocService, secret: Path) -> None:
    first, second = [await redactor.run(RedactIn(path=str(secret), terms=[TERM])) for _ in range(2)]
    assert first == second


@pytest.mark.parametrize(
    ("name", "kind"),
    [("ink.png", "ParseError"), ("../outside.pdf", "OutsideRootsError")],
    ids=["not-a-pdf", "outside"],
)
async def test_redact_what_cannot_be_read_fails_the_run(
    redactor: RedactDocService, vault: Path, secret: Path, name: str, kind: str
) -> None:
    events = [event async for event in redactor.events(RedactIn(path=str(vault / name), terms=[TERM]))]
    last = events[-1]
    assert isinstance(last, Failed)
    assert last.kind == kind
