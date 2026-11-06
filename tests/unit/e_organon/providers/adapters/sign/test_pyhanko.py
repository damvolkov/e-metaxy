"""tests/unit/e_organon/providers/adapters/sign/pyhanko: a PDF signed with a PKCS#12 validates with pyHanko's own validator
— intact, valid, trusted under the CA — and a change after signing breaks it; a bad key file or password fails at open."""

from typing import TYPE_CHECKING

import pytest

from e_organon.infra.errors import ProviderError
from e_organon.providers.adapters.sign.pyhanko import PyhankoAdapter
from support.pdf import blank
from support.signed import validated

if TYPE_CHECKING:
    from pathlib import Path

    from support.pki import Pki


async def test_pyhanko_signature_validates_against_the_ca(signer: PyhankoAdapter, pki: Pki) -> None:
    count, status = await validated(await signer.sign(blank(1)), pki)
    assert (count, status.intact, status.valid, status.trusted, status.bottom_line) == (1, True, True, True, True)


async def test_pyhanko_a_change_after_signing_breaks_the_validation(signer: PyhankoAdapter, pki: Pki) -> None:
    signed = await signer.sign(blank(1))
    ### a byte inside the signed range (the page's box) moved by one: same length, so the file still parses.
    tampered = signed.replace(b"0 0 595 842", b"0 0 596 842", 1)
    assert tampered != signed
    _, status = await validated(tampered, pki)
    assert (status.intact, status.bottom_line) == (False, False)


async def test_pyhanko_a_signed_pdf_can_be_signed_again(signer: PyhankoAdapter, pki: Pki) -> None:
    twice = await signer.sign(await signer.sign(blank(1)))
    count, status = await validated(twice, pki)
    assert (count, status.bottom_line) == (2, True)


async def test_pyhanko_health_while_open(signer: PyhankoAdapter) -> None:
    assert await signer.health()


async def test_pyhanko_a_wrong_password_fails_at_open(pki: Pki) -> None:
    with pytest.raises(ProviderError, match="could not be loaded"):
        await PyhankoAdapter(p12=pki.p12, password="nope", tsa_url=None).__aenter__()


async def test_pyhanko_a_missing_file_fails_at_open(tmp_path: Path) -> None:
    with pytest.raises(ProviderError, match="could not be loaded"):
        await PyhankoAdapter(p12=tmp_path / "none.p12", password="", tsa_url=None).__aenter__()


async def test_pyhanko_unopened_it_is_refused(pki: Pki) -> None:
    adapter = PyhankoAdapter(p12=pki.p12, password=pki.password, tsa_url=None)
    with pytest.raises(ProviderError, match="not open"):
        await adapter.sign(blank(1))
