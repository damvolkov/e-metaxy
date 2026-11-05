"""ports/sign: a PDF signed with a key the provider holds — what proves who sealed it and that it was not changed."""

from typing import Protocol, runtime_checkable

from e_organon.ports.provider import Provider


##### PORT #####
@runtime_checkable
class SignPort(Provider, Protocol):
    """`sign` the PDF with an invisible, incremental signature (the document's earlier bytes are untouched, so a PDF may be
    signed again): the signed bytes. The key never leaves the provider. A PDF that cannot be signed is a `ParseError`."""

    async def sign(self, data: bytes) -> bytes: ...
