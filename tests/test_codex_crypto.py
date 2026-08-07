"""Tests for cryptographic commitment utilities."""

import hashlib
import json

from cop_worker.crypto import build_commitment


def test_build_commitment_returns_64_char_hex():
    """build_commitment must return a 64-char hex SHA256 string."""
    h = build_commitment("mynonce", {"dir": "N"})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_build_commitment_is_deterministic():
    """Same nonce + action must always produce the same hash."""
    h1 = build_commitment("nonce42", {"move": "S"})
    h2 = build_commitment("nonce42", {"move": "S"})
    assert h1 == h2


def test_build_commitment_different_nonce_produces_different_hash():
    """Different nonces must produce different hashes."""
    h1 = build_commitment("nonce_a", {"move": "N"})
    h2 = build_commitment("nonce_b", {"move": "N"})
    assert h1 != h2


def test_build_commitment_different_action_produces_different_hash():
    """Different actions must produce different hashes."""
    h1 = build_commitment("nonce_c", {"move": "N"})
    h2 = build_commitment("nonce_c", {"move": "S"})
    assert h1 != h2


def test_build_commitment_matches_manual_sha256():
    """build_commitment must match manual SHA256(nonce + canonical_json(action))."""
    nonce = "testnonce"
    action = {"dir": "E"}
    action_json = json.dumps(action, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256((nonce + action_json).encode()).hexdigest()
    assert build_commitment(nonce, action) == expected
