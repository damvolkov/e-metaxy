import pytest

from e_metaxy.adapters.passphrase import PassphraseAdapter
from e_metaxy.core.crypto import Crypto
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.crypto import CryptoSettings


@pytest.fixture
async def owner() -> PassphraseAdapter:
    crypto = Crypto(CryptoSettings(secret=Secret("k" * 48)))
    return PassphraseAdapter(crypto, await crypto.hash_password("open sesame"))


@pytest.mark.parametrize(("secret", "admitted"), [("open sesame", True), ("close sesame", False), ("", False)])
async def test_passphrase_admits(owner: PassphraseAdapter, secret: str, admitted: bool) -> None:
    assert await owner.admits(secret) is admitted


async def test_passphrase_broken_hash_refuses() -> None:
    owner = PassphraseAdapter(Crypto(CryptoSettings(secret=Secret("k" * 48))), "not-an-argon2-hash")
    assert await owner.admits("anything") is False
