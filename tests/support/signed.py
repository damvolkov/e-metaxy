"""tests/support/signed: what a validator says of a signed PDF — the first signature's status under a trusted CA."""

import io
from typing import TYPE_CHECKING

from asn1crypto import x509 as asn1_x509
from cryptography.hazmat.primitives.serialization import Encoding
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

if TYPE_CHECKING:
    from pyhanko.sign.validation.status import PdfSignatureStatus

    from support.pki import Pki


async def validated(pdf: bytes, pki: Pki) -> tuple[int, PdfSignatureStatus]:
    """How many signatures the PDF carries, and the first one's status with `pki.ca` as the trust root."""
    reader = PdfFileReader(io.BytesIO(pdf))
    root = asn1_x509.Certificate.load(pki.ca.public_bytes(Encoding.DER))
    return len(reader.embedded_signatures), await async_validate_pdf_signature(
        reader.embedded_signatures[0], ValidationContext(trust_roots=[root])
    )
