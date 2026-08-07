"""Asymmetric signing for Step-0 declarations and audit summaries.

Uses Ed25519 from the `cryptography` package (available via python-jose[cryptography]).
Private keys are NEVER written to disk — callers must keep them in memory only.
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def generate_key_pair() -> tuple[bytes, bytes]:
    """Generate an ephemeral Ed25519 key pair.

    Returns:
        (private_key_bytes, public_key_bytes) — raw 32-byte representations.

    IMPORTANT: private_key_bytes must NEVER be written to disk or committed.
    Keep it in memory only for the duration of the session.
    """
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    return private_bytes, public_bytes


def sign(private_key_bytes: bytes, message: bytes) -> bytes:
    """Sign a message with an Ed25519 private key.

    Args:
        private_key_bytes: Raw 32-byte private key (from generate_key_pair).
        message: Arbitrary bytes to sign.

    Returns:
        64-byte Ed25519 signature.
    """
    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    return private_key.sign(message)


def verify(public_key_bytes: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an Ed25519 signature.

    Args:
        public_key_bytes: Raw 32-byte public key.
        message: The original message bytes.
        signature: 64-byte signature to verify.

    Returns:
        True if the signature is valid, False otherwise.
    """
    from cryptography.exceptions import InvalidSignature

    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
