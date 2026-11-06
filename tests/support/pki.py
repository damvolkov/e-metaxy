"""tests/support/pki: a throwaway certificate authority and a signer under it, made in memory with `cryptography` — a PKCS#12
for the tool, the CA's certificate for the validator. Nothing here is a real key and nothing of it is ever committed."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

if TYPE_CHECKING:
    from pathlib import Path

PASSWORD = "test-only-password"  # noqa: S105 — a throwaway key's password, no secret


@dataclass(frozen=True, slots=True)
class Pki:
    """The signer's PKCS#12 on disk, its password, and the CA that issued it (to trust)."""

    p12: Path
    password: str
    ca: x509.Certificate


def _name(common: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def make(directory: Path) -> Pki:
    """A CA, a leaf for digital signatures under it, and the leaf's PKCS#12 written into `directory`."""
    now = datetime.now(UTC)
    ca_key, leaf_key = (rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2))
    ca = (
        x509.CertificateBuilder()
        .subject_name(_name("organon test CA"))
        .issuer_name(_name("organon test CA"))
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(_name("organon test signer"))
        .issuer_name(ca.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    path = directory / "signer.p12"
    path.write_bytes(
        pkcs12.serialize_key_and_certificates(
            b"signer", leaf_key, leaf, [ca], serialization.BestAvailableEncryption(PASSWORD.encode())
        )
    )
    return Pki(p12=path, password=PASSWORD, ca=ca)
