"""providers/adapters/sign/pyhanko: a PDF signed in PAdES with pyHanko, the key in a PKCS#12 read once at open.

The signature is an incremental update — invisible, `ETSI.CAdES.detached` — over SHA-256; with a TSA URL the signature
also carries its trusted time-stamp (PAdES B-T). It is made with the key and the time of the moment, so two signatures of one
PDF differ: unlike the other tools' outputs, this one is not byte-deterministic by nature. The file and its password are
the adapter's arguments, never a request's; a key that does not load stops the start."""

import io
import secrets
from typing import TYPE_CHECKING, ClassVar, Self

import anyio
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.misc import PdfError
from pyhanko.sign import fields, signers, timestamps

from e_organon.infra.errors import ParseError, ProviderError
from e_organon.infra.logger import logger
from e_organon.ports.provider import Isolation, Locality, ProviderSpec, Workload

if TYPE_CHECKING:
    from pathlib import Path


##### ADAPTER #####
class PyhankoAdapter:
    """PAdES signing over one loaded signer."""

    spec: ClassVar[ProviderSpec] = ProviderSpec("pyhanko", Locality.EMBEDDED, Workload.CPU_BOUND, Isolation.LOOP)

    __slots__ = ("_p12", "_password", "_signer", "_stamper")

    def __init__(self, *, p12: Path, password: str, tsa_url: str | None) -> None:
        self._p12, self._password = p12, password
        self._stamper = None if tsa_url is None else timestamps.HTTPTimeStamper(tsa_url)
        self._signer: signers.SimpleSigner | None = None

    ##### PRIVATE #####

    def _enter_signer(self) -> signers.SimpleSigner:
        try:
            loaded = signers.SimpleSigner.load_pkcs12(str(self._p12), passphrase=self._password.encode())
        except (OSError, ValueError, TypeError) as error:
            msg = f"the signing key {self._p12} could not be loaded: {error}"
            raise ProviderError(msg) from error
        match loaded:
            case None:
                msg = f"the signing key {self._p12} could not be loaded: it holds no key and certificate"
                raise ProviderError(msg)
            case signer:
                return signer

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        self._signer = await anyio.to_thread.run_sync(self._enter_signer)
        logger.info("pyhanko ready", timestamped=self._stamper is not None)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._signer = None

    async def health(self) -> bool:
        return self._signer is not None

    async def sign(self, data: bytes) -> bytes:
        match self._signer:
            case None:
                msg = "PyhankoAdapter is not open: the lifespan opens it, callers never do"
                raise ProviderError(msg)
            case signer:
                ### a field name no earlier signature holds: a signed PDF can be signed again.
                meta = signers.PdfSignatureMetadata(
                    field_name=f"organon-{secrets.token_hex(4)}",
                    md_algorithm="sha256",
                    subfilter=fields.SigSeedSubFilter.PADES,
                )
                try:
                    writer = IncrementalPdfFileWriter(io.BytesIO(data))
                    out = await signers.PdfSigner(meta, signer=signer, timestamper=self._stamper).async_sign_pdf(writer)
                except (PdfError, ValueError) as error:
                    msg = f"not a signable PDF: {error}"
                    raise ParseError(msg) from error
                return out.getvalue()
