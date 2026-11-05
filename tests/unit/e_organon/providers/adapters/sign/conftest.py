"""tests/unit/e_organon/providers/adapters/sign: a throwaway CA and signer in a temporary directory, and the adapter opened
on its PKCS#12."""

from typing import TYPE_CHECKING

import pytest

from e_organon.providers.adapters.sign.pyhanko import PyhankoAdapter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from support.pki import Pki


@pytest.fixture
async def signer(pki: Pki) -> AsyncIterator[PyhankoAdapter]:
    async with PyhankoAdapter(p12=pki.p12, password=pki.password, tsa_url=None) as opened:
        yield opened
