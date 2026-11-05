"""tests/unit/e_organon/services/doc/stamp: doc/stamp over the real adapters — the stamp lands where a field, a text anchor
or a box says (read back from the page's own matrix), and a field or an anchor that is not there fails the run."""

from typing import TYPE_CHECKING

import pytest

from e_organon.models.doc import AtAnchor, AtBox, AtField, StampIn
from e_organon.models.flow import Step
from support.pdf import placements

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
    from e_organon.services.doc.stamp import StampDocService
    from support.stamp import Refusal, Stamped

TOLERANCE = 3.0


async def test_stamp_steps_then_the_pdf(stamper: StampDocService, vault: Path) -> None:
    order = StampIn(
        path=str(vault / "labelled.pdf"), image=str(vault / "ink.png"), at=AtBox(page=0, x=10, y=10, width=50)
    )
    events = [event async for event in stamper.events(order)]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "locate", "stamp", "keep"]


async def test_stamp_a_field_fits_the_image_inside_its_widget(stamped: Stamped, vault: Path) -> None:
    """`firma` is [100, 480, 300, 520]: a 2:1 image in 200x40 is 80x40, centred: x 160, y 480."""
    out = await stamped(StampIn(path=str(vault / "form.pdf"), image=str(vault / "ink.png"), at=AtField(field="firma")))
    assert placements(out) == [pytest.approx((80.0, 0.0, 0.0, 40.0, 160.0, 480.0))]


async def test_stamp_an_anchor_lands_on_the_texts_box(
    stamped: Stamped, vault: Path, render_hits: list[tuple[float, float, float, float]]
) -> None:
    left, bottom, right, top = render_hits[0]
    out = await stamped(
        StampIn(path=str(vault / "labelled.pdf"), image=str(vault / "ink.png"), at=AtAnchor(anchor="firma:"))
    )
    [(w, _, _, h, x, y)] = placements(out)
    assert (left - TOLERANCE <= x, x + w <= right + TOLERANCE, bottom - TOLERANCE <= y, y + h <= top + TOLERANCE) == (
        True,
    ) * 4


async def test_stamp_an_anchor_by_occurrence_offset_and_width(
    stamped: Stamped, vault: Path, render_hits: list[tuple[float, float, float, float]]
) -> None:
    left, bottom, *_ = render_hits[1]
    at = AtAnchor(anchor="firma:", occurrence=2, offset=(50.0, -10.0), width=60.0)
    out = await stamped(StampIn(path=str(vault / "labelled.pdf"), image=str(vault / "ink.png"), at=at))
    assert placements(out) == [pytest.approx((60.0, 0.0, 0.0, 30.0, left + 50, bottom - 10), abs=TOLERANCE)]


async def test_stamp_a_box_is_where_it_says(stamped: Stamped, vault: Path) -> None:
    at = AtBox(page=0, x=20, y=30, width=100, height=100)
    out = await stamped(StampIn(path=str(vault / "labelled.pdf"), image=str(vault / "ink.png"), at=at, opacity=0.5))
    assert placements(out) == [(100.0, 0.0, 0.0, 50.0, 20.0, 55.0)]


async def test_stamp_a_text(stamped: Stamped, vault: Path, render: PdfiumAdapter) -> None:
    order = StampIn(
        path=str(vault / "labelled.pdf"), text="Aprobado", at=AtBox(page=0, x=20, y=30, width=100, height=12)
    )
    hits = await render.find(await stamped(order), "aprobado")
    assert [(hit.page, 18 <= hit.rect[0] <= 24, 30 <= hit.rect[1] <= 36) for hit in hits] == [(0, True, True)]


@pytest.mark.parametrize(
    ("at", "kind"),
    [
        (AtField(field="nope"), "FieldNotFoundError"),
        (AtAnchor(anchor="nowhere"), "AnchorNotFoundError"),
        (AtAnchor(anchor="firma:", occurrence=3), "AnchorNotFoundError"),
        (AtBox(page=9, x=0, y=0, width=10), "ParseError"),
    ],
    ids=["field", "anchor", "occurrence", "page"],
)
async def test_stamp_what_is_not_there_fails_the_run(
    refused: Refusal, vault: Path, at: AtField | AtAnchor | AtBox, kind: str
) -> None:
    refusal = await refused(StampIn(path=str(vault / "labelled.pdf"), image=str(vault / "ink.png"), at=at))
    assert refusal.kind == kind


async def test_stamp_refuses_a_path_outside_the_roots(refused: Refusal) -> None:
    refusal = await refused(StampIn(path="/etc/hostname", text="x", at=AtBox(page=0, x=0, y=0, width=10)))
    assert refusal.kind == "OutsideRootsError"
