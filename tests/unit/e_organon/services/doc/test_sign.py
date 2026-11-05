"""tests/unit/e_organon/services/doc/sign: doc/sign over the real adapters and a throwaway CA — the PDF comes back signed
and valid under it; with `at` its appearance is drawn first (text, image or a photographed signature) and the signature
seals that; what cannot be a visible or a signable PDF fails the run."""

from typing import TYPE_CHECKING

import anyio
import msgspec
import pytest

from e_organon.models.doc import AtBox, FileOut, SignIn
from e_organon.models.flow import Done, Failed, Step
from support.signed import validated

if TYPE_CHECKING:
    from pathlib import Path

    from e_organon.providers.adapters.render.pdfium import PdfiumAdapter
    from e_organon.services.doc.sign import SignDocService
    from support.pki import Pki

BOX = AtBox(page=0, x=50, y=700, width=120)


async def signed(sealer: SignDocService, order: SignIn) -> bytes:
    out = await sealer.run(order)
    assert isinstance(out, FileOut)
    return await anyio.Path(out.path).read_bytes()


async def test_sign_steps_then_the_signed_pdf(sealer: SignDocService, vault: Path) -> None:
    events = [event async for event in sealer.events(SignIn(path=str(vault / "labelled.pdf")))]
    assert [event.name for event in events if isinstance(event, Step)] == ["resolve", "appear", "sign", "keep"]
    assert isinstance(events[-1], Done)


async def test_sign_invisible_validates_against_the_ca(sealer: SignDocService, vault: Path, pki: Pki) -> None:
    count, status = await validated(await signed(sealer, SignIn(path=str(vault / "labelled.pdf"))), pki)
    assert (count, status.intact, status.trusted, status.bottom_line) == (1, True, True, True)


async def test_sign_with_a_text_draws_it_then_seals_it(
    sealer: SignDocService, render: PdfiumAdapter, vault: Path, pki: Pki
) -> None:
    pdf = await signed(sealer, SignIn(path=str(vault / "labelled.pdf"), at=BOX, text="APROBADO"))
    _, status = await validated(pdf, pki)
    assert (len(await render.find(pdf, "aprobado")), status.bottom_line) == (1, True)


@pytest.mark.parametrize("appearance", [{"image": "ink.png"}, {"photo": "firma.jpg"}], ids=["image", "photo"])
async def test_sign_with_a_picture_draws_it_then_seals_it(
    sealer: SignDocService, vault: Path, pki: Pki, appearance: dict[str, str]
) -> None:
    order = SignIn(
        path=str(vault / "labelled.pdf"), at=BOX, **{key: str(vault / name) for key, name in appearance.items()}
    )
    pdf = await signed(sealer, order)
    _, status = await validated(pdf, pki)
    assert (status.intact, status.bottom_line) == (True, True)


@pytest.mark.parametrize(
    "order",
    [
        {"path": "a.pdf", "at": {"type": "box", "page": 0, "x": 1, "y": 1, "width": 5}},
        {"path": "a.pdf", "text": "x"},
        {"path": "a.pdf", "at": {"type": "box", "page": 0, "x": 1, "y": 1, "width": 5}, "text": "x", "image": "b.png"},
    ],
    ids=["nothing-to-draw", "no-place", "two-appearances"],
)
async def test_sign_a_visible_signature_needs_one_appearance_and_an_invisible_none(order: dict[str, object]) -> None:
    with pytest.raises(msgspec.ValidationError, match="exactly one"):
        msgspec.convert(order, SignIn)


async def test_sign_what_is_no_pdf_fails_the_run(sealer: SignDocService, vault: Path) -> None:
    (vault / "not.pdf").write_bytes(b"hello")
    events = [event async for event in sealer.events(SignIn(path=str(vault / "not.pdf")))]
    assert isinstance(events[-1], Failed)
    assert events[-1].kind == "ParseError"


async def test_sign_a_failed_appearance_is_the_runs_failure(sealer: SignDocService, vault: Path) -> None:
    order = SignIn(path=str(vault / "labelled.pdf"), at=BOX, image=str(vault / "nope.png"))
    events = [event async for event in sealer.events(order)]
    assert isinstance(events[-1], Failed)
    assert events[-1].kind == "OutsideRootsError"
