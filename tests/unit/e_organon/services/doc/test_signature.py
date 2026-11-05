"""tests/unit/e_organon/services/doc/signature: doc/signature — the cutout's steps then the stamp's as one run, the photo's
ink on the PDF at the anchor; a photo without ink or an anchor that is not there is the run's failure."""

from typing import TYPE_CHECKING

import anyio
from PIL import Image

from e_organon.models.doc import AtAnchor, FileOut, SignatureIn
from e_organon.models.flow import Done, Failed, Step
from support.pdf import placements

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.services.doc.signature import SignatureDocService


async def test_signature_is_the_cutout_then_the_stamp(signer: SignatureDocService, vault: Path) -> None:
    order = SignatureIn(
        path=str(vault / "labelled.pdf"), photo=str(vault / "firma.jpg"), at=AtAnchor(anchor="firma:", width=80)
    )
    events = [event async for event in signer.events(order)]
    names = [("cutout", "resolve"), ("cutout", "measure"), ("cutout", "cut"), ("cutout", "keep")]
    names += [("stamp", "resolve"), ("stamp", "locate"), ("stamp", "stamp"), ("stamp", "keep")]
    assert [(event.name, event.index, event.total) for event in events if isinstance(event, Step)] == [
        (f"{part}.{step}", index, 8) for index, (part, step) in enumerate(names)
    ]
    assert isinstance(events[-1], Done)
    assert isinstance(events[-1].result, FileOut)
    [(w, _, _, h, _, _)] = placements(await anyio.Path(events[-1].result.path).read_bytes())
    with Image.open(next((vault / "outbox").glob("firma-cutout-*.png"))) as ink:
        assert (w, round(h * ink.width / w)) == (80.0, ink.height)


async def test_signature_a_sheet_without_ink_fails_in_the_cutout(signer: SignatureDocService, vault: Path) -> None:
    Image.new("RGB", (200, 100), (235, 235, 235)).save(vault / "blank.png")
    events = [
        event
        async for event in signer.events(
            SignatureIn(path=str(vault / "labelled.pdf"), photo=str(vault / "blank.png"), at=AtAnchor(anchor="firma:"))
        )
    ]
    assert isinstance(events[-1], Failed)
    assert (events[-1].kind, [type(event) for event in events[:-1]]) == ("ParseError", [Step] * 3)


async def test_signature_an_anchor_that_is_not_there_fails_in_the_stamp(
    signer: SignatureDocService, vault: Path
) -> None:
    events = [
        event
        async for event in signer.events(
            SignatureIn(path=str(vault / "labelled.pdf"), photo=str(vault / "firma.jpg"), at=AtAnchor(anchor="nowhere"))
        )
    ]
    assert isinstance(events[-1], Failed)
    assert (events[-1].kind, [event.name for event in events if isinstance(event, Step)][-1]) == (
        "AnchorNotFoundError",
        "stamp.locate",
    )
