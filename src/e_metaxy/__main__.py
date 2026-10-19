"""e_metaxy: `python -m e_metaxy` / `e-metaxy` — serve the bridge with granian (Rust ASGI) on loopback.

Two bootstrap commands write the deployment's secrets as env lines, ready for its env file: `e-metaxy keys` the
master secret that signs the access tokens, `e-metaxy owner` the argon2 hash of the passphrase that approves a
client. The values are single-quoted: an argon2 hash is full of `$`, which compose would interpolate."""

import asyncio
import getpass
import sys
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
from typing import Final

from granian.constants import Interfaces
from granian.server import Server

from e_metaxy.core.crypto import Crypto
from e_metaxy.core.settings import settings as st
from e_metaxy.core.settings.base import Secret
from e_metaxy.core.settings.crypto import CryptoSettings

USAGE: Final = "usage: e-metaxy [serve | keys | owner]"


def serve() -> None:
    Server(
        "e_metaxy.main:create_app",
        address=st.metaxy.host,
        port=st.metaxy.port,
        interface=Interfaces.ASGI,
        factory=True,
        workers=1,
        log_access=False,
    ).serve()


def keys() -> None:
    secret = Crypto.generate_keys().secret
    sys.stdout.write(f"CRYPTO__SECRET='{secret.get_secret_value() if secret else ''}'\n")


def owner() -> None:
    passphrase = getpass.getpass("owner passphrase: ")
    match passphrase:
        case "":
            sys.exit("an empty passphrase admits no one")
        case _ if getpass.getpass("again: ") != passphrase:
            sys.exit("the two passphrases differ")
    ### hashing needs no signing key: a throwaway one keeps the command independent of the deployment's.
    crypto = Crypto(CryptoSettings(secret=Secret("-" * 48)))
    sys.stdout.write(f"METAXY_AUTH_OWNER_HASH='{asyncio.run(crypto.hash_password(passphrase))}'\n")


COMMANDS: Final[Mapping[str, Callable[[], None]]] = MappingProxyType({"serve": serve, "keys": keys, "owner": owner})


def main(argv: Sequence[str] | None = None) -> None:
    match list(sys.argv[1:] if argv is None else argv):
        case []:
            serve()
        case [name] if name in COMMANDS:
            COMMANDS[name]()
        case _:
            sys.exit(USAGE)


if __name__ == "__main__":
    main()
