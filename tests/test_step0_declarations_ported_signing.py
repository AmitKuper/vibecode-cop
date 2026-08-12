"""Tests for Step-0 declaration signing and verification."""

from cop_worker.step0.signing import generate_key_pair, sign, verify
from tests.helpers_step0_declarations import _valid_decl

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def test_sign_verify_round_trip():
    priv, pub = generate_key_pair()
    message = b"hello step-0"
    sig = sign(priv, message)
    assert verify(pub, message, sig) is True


def test_verify_rejects_tampered_message():
    priv, pub = generate_key_pair()
    message = b"original message"
    sig = sign(priv, message)
    assert verify(pub, b"tampered message", sig) is False


def test_verify_rejects_tampered_signature():
    priv, pub = generate_key_pair()
    message = b"original"
    sig = bytearray(sign(priv, message))
    sig[0] ^= 0xFF  # flip bits in first byte
    assert verify(pub, message, bytes(sig)) is False


def test_different_keys_dont_verify():
    priv1, pub1 = generate_key_pair()
    _priv2, pub2 = generate_key_pair()
    message = b"test"
    sig = sign(priv1, message)
    assert verify(pub2, message, sig) is False


def test_key_pair_lengths():
    priv, pub = generate_key_pair()
    assert len(priv) == 32
    assert len(pub) == 32


def test_sign_declaration_bytes():
    """Signing canonical declaration bytes works end-to-end."""
    priv, pub = generate_key_pair()
    decl = _valid_decl()
    message = decl.canonical_bytes()
    sig = sign(priv, message)
    assert verify(pub, message, sig) is True
