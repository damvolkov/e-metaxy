"""tests/unit/e_organon/services/doc/geometry: a stamp where a person sees it, whatever the page's turn or crop — measured on
what pdfium *displays*, never on the matrix that was written. A box is in the page as displayed; a text anchor's rectangle is
the PDF's, user space, and the stamp must still sit on the text; the image is upright on a page turned any way."""

import anyio
import pytest

from e_organon.models.doc import AtAnchor, AtBox, StampIn
from support.ink import quadrants_png, red_png
from support.pdf import labelled
from support.shot import box_of, dark, reddish, shot

CROP = (50.0, 80.0, 545.0, 742.0)
PAGES = {
    "upright": (0, None),
    "r90": (90, None),
    "r180": (180, None),
    "r270": (270, None),
    "cropped": (0, CROP),
    "r90-cropped": (90, CROP),
    "r270-cropped": (270, CROP),
}
TOLERANCE = 3


@pytest.mark.parametrize("page", PAGES.values(), ids=PAGES.keys())
async def test_geometry_a_box_is_in_the_page_as_displayed(stamped, vault, page: tuple) -> None:
    rotate, crop = page
    await anyio.Path(vault / "page.pdf").write_bytes(labelled(rotate=rotate, crop=crop, second=False))
    await anyio.Path(vault / "quad.png").write_bytes(quadrants_png())
    height = shot(labelled(rotate=rotate, crop=crop, second=False)).shape[0]
    order = StampIn(
        path=str(vault / "page.pdf"), image=str(vault / "quad.png"), at=AtBox(page=0, x=60, y=40, width=120, height=60)
    )
    seen = shot(await stamped(order))
    ### the box is 120 x 60 with its bottom-left 60 right, 40 up: rows count from the top, so its top row is height - 100.
    left, top = 60, height - 100
    centres = {
        "red": (left + 30, top + 15),
        "green": (left + 90, top + 15),
        "blue": (left + 30, top + 45),
        "black": (left + 90, top + 45),
    }
    colours = {name: tuple(int(v) for v in seen[row, col]) for name, (col, row) in centres.items()}
    assert colours == {"red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255), "black": (0, 0, 0)}


@pytest.mark.parametrize("page", PAGES.values(), ids=PAGES.keys())
async def test_geometry_an_anchor_stamp_sits_on_the_text_as_displayed(stamped, vault, page: tuple) -> None:
    rotate, crop = page
    await anyio.Path(vault / "page.pdf").write_bytes(labelled(rotate=rotate, crop=crop, second=False))
    await anyio.Path(vault / "red.png").write_bytes(red_png())
    ### where the text really is on the displayed page: its ink, black on white, the stamp being red.
    text = box_of(dark(shot(labelled(rotate=rotate, crop=crop, second=False))))
    order = StampIn(path=str(vault / "page.pdf"), image=str(vault / "red.png"), at=AtAnchor(anchor="Firma:"))
    stamp = box_of(reddish(shot(await stamped(order))))
    centre = lambda box: ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)  # noqa: E731 — two boxes, one measure
    assert all(abs(a - b) <= TOLERANCE for a, b in zip(centre(stamp), centre(text), strict=True)), (stamp, text)
    assert (text[0] - TOLERANCE <= stamp[0], stamp[2] <= text[2] + TOLERANCE) == (True, True)
    assert (text[1] - TOLERANCE <= stamp[1], stamp[3] <= text[3] + TOLERANCE) == (True, True)
