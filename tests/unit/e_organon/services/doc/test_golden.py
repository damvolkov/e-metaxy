"""tests/unit/e_organon/services/doc/golden: the new tools against inputs kept in `tests/resources/golden` — what each must give,
told by meaning and not by bytes (a PNG or a PDF written by another library version would differ and still be right):

- image/cutout: the ink's mask (alpha from 128) is the stored one to an IoU of 0.99;
- doc/stamp: the placement matrix on the contract is where `Firma:` plus the offset says (151.2, 695.8, 60 wide), and
  pdfium shows the red stamp on exactly those pixels;
- doc/signature: the cut photo's ink — blue — is on the page, inside the stamp's rectangle."""

import io
from typing import TYPE_CHECKING

import anyio
import numpy as np
import pytest
from PIL import Image

from e_organon.models.doc import AtAnchor, FileOut, SignatureIn, StampIn
from e_organon.models.flow import Done
from e_organon.models.image import CutoutIn
from support.pdf import placements
from support.shot import box_of, reddish, shot

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.services.doc.signature import SignatureDocService
    from e_organon.services.doc.stamp import StampDocService
    from e_organon.services.image.cutout import CutoutImageService

AT = AtAnchor(anchor="Firma:", offset=(50.0, -4.0), width=60.0)


async def written(events: list) -> bytes:
    assert isinstance(events[-1], Done), events[-1]
    assert isinstance(events[-1].result, FileOut)
    return await anyio.Path(events[-1].result.path).read_bytes()


async def test_golden_cutout_leaves_the_stored_mask(cutter: CutoutImageService, golden: Path) -> None:
    out = await written([e async for e in cutter.events(CutoutIn(path=str(golden / "signature.jpg"), crop=False))])
    found = np.asarray(Image.open(io.BytesIO(out)).convert("RGBA"))[..., 3] >= 128
    stored = np.asarray(Image.open(golden / "signature.mask.png").convert("L")) >= 128
    assert (found & stored).sum() / (found | stored).sum() >= 0.99


async def test_golden_stamp_is_where_the_anchor_says_and_pdfium_shows_it(
    stamper: StampDocService, golden: Path
) -> None:
    order = StampIn(path=str(golden / "contract.pdf"), image=str(golden / "red.png"), at=AT)
    out = await written([e async for e in stamper.events(order)])
    assert placements(out) == [pytest.approx((60.0, 0.0, 0.0, 30.0, 151.2, 695.8), abs=0.5)]
    left, top, right, bottom = box_of(reddish(shot(out)))
    assert (left, top, right, bottom) == pytest.approx((151, 116, 212, 147), abs=1)


async def test_golden_signature_puts_the_inks_blue_inside_the_stamp(signer: SignatureDocService, golden: Path) -> None:
    order = SignatureIn(path=str(golden / "contract.pdf"), photo=str(golden / "signature.jpg"), at=AT)
    page = shot(await written([e async for e in signer.events(order)]))
    blue = (page[..., 2].astype(int) - page[..., 0].astype(int)) > 25
    left, top, right, bottom = box_of(blue)
    ### the stamp's rectangle in pixels: x 151-211, and 60 wide at the cut ink's aspect below; the ink is inside it.
    assert (left >= 150, right <= 213, top >= 100, bottom <= 160, blue.sum() > 60) == (True,) * 5
