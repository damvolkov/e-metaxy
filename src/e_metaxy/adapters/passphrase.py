"""e_metaxy.adapters.passphrase: the owner proven by a passphrase — its argon2 hash, checked by the crypto engine."""

from typing import ClassVar

from beartype import beartype

from e_metaxy.core.crypto import Crypto
from e_metaxy.core.errors import CryptoError


@beartype
class PassphraseAdapter:
    """Admits the secret whose hash the deployment holds; the slow check runs off the event loop."""

    name: ClassVar[str] = "passphrase"

    __slots__ = ("_crypto", "_hashed")

    def __init__(self, crypto: Crypto, hashed: str) -> None:
        self._crypto = crypto
        self._hashed = hashed

    async def admits(self, secret: str) -> bool:
        try:
            return bool(secret) and await self._crypto.verify_password(secret, self._hashed)
        except CryptoError:
            return False
