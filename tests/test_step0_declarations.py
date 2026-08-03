"""Tests for Step-0 declaration schema, signing, and validator."""

import json

from agent.step0.declaration import DeclarationAgreement, PeerDeclaration, SignedDeclaration
from agent.step0.signing import generate_key_pair, sign, verify
from agent.step0.validator import validate_for_counted_mode

# ---------------------------------------------------------------------------
# PeerDeclaration
# ---------------------------------------------------------------------------


def _make_decl(**overrides) -> PeerDeclaration:
    defaults = {"game_uid": "game-001"}
    defaults.update(overrides)
    return PeerDeclaration(**defaults)


def test_peer_declaration_canonical_bytes_deterministic():
    decl = _make_decl(team_name="alpha", git_sha="abc123")
    b1 = decl.canonical_bytes()
    b2 = decl.canonical_bytes()
    assert b1 == b2
    # Must be valid JSON
    json.loads(b1)


def test_peer_declaration_canonical_bytes_sorted_keys():
    decl = _make_decl()
    raw = decl.canonical_bytes().decode()
    # Keys in canonical JSON are sorted
    parsed = json.loads(raw)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_peer_declaration_declaration_hash_is_hex64():
    decl = _make_decl()
    h = decl.declaration_hash()
    assert len(h) == 64
    int(h, 16)  # raises ValueError if not hex


# ---------------------------------------------------------------------------
# SignedDeclaration round-trip
# ---------------------------------------------------------------------------


def test_signed_declaration_round_trip():
    decl = _make_decl(team_name="beta", git_sha="deadbeef")
    signed = SignedDeclaration(declaration=decl, signature_hex="cafebabe")
    d = signed.to_dict()
    restored = SignedDeclaration.from_dict(d)
    assert restored.declaration.team_name == "beta"
    assert restored.declaration.git_sha == "deadbeef"
    assert restored.signature_hex == "cafebabe"


def test_signed_declaration_round_trip_empty_sig():
    decl = _make_decl()
    signed = SignedDeclaration(declaration=decl, signature_hex="")
    assert SignedDeclaration.from_dict(signed.to_dict()).signature_hex == ""


# ---------------------------------------------------------------------------
# validate_for_counted_mode
# ---------------------------------------------------------------------------


def _valid_decl() -> PeerDeclaration:
    return _make_decl(
        git_sha="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        group_id="AB123456",
        model_sha256="sha256ofmodel",
        canonical_config_sha256="sha256ofconfig",
        scent_model_hash="sha256ofscent",
    )


def test_validate_counted_mode_valid():
    errors = validate_for_counted_mode(_valid_decl())
    assert errors == []


def test_validate_counted_mode_rejects_empty_git_sha():
    decl = _valid_decl()
    decl.git_sha = ""
    errors = validate_for_counted_mode(decl)
    assert any("git_sha" in e for e in errors)


def test_validate_counted_mode_rejects_placeholder_git_sha():
    decl = _valid_decl()
    decl.git_sha = "placeholder"
    errors = validate_for_counted_mode(decl)
    assert any("git_sha" in e for e in errors)


def test_validate_counted_mode_rejects_unknown_git_sha():
    decl = _valid_decl()
    decl.git_sha = "unknown"
    errors = validate_for_counted_mode(decl)
    assert any("git_sha" in e for e in errors)


def test_validate_counted_mode_rejects_bad_length_group_id():
    decl = _valid_decl()
    decl.group_id = "SHORT"
    errors = validate_for_counted_mode(decl)
    assert any("group_id" in e for e in errors)


def test_validate_counted_mode_rejects_placeholder_group_id():
    decl = _valid_decl()
    decl.group_id = "XXXXXXXX"
    errors = validate_for_counted_mode(decl)
    assert any("placeholder" in e.lower() for e in errors)


def test_validate_counted_mode_rejects_empty_model_sha():
    decl = _valid_decl()
    decl.model_sha256 = ""
    errors = validate_for_counted_mode(decl)
    assert any("model_sha256" in e for e in errors)


def test_validate_counted_mode_rejects_placeholder_model_sha():
    decl = _valid_decl()
    decl.model_sha256 = "placeholder"
    errors = validate_for_counted_mode(decl)
    assert any("model_sha256" in e for e in errors)


def test_validate_counted_mode_rejects_missing_canonical_config():
    decl = _valid_decl()
    decl.canonical_config_sha256 = ""
    errors = validate_for_counted_mode(decl)
    assert any("canonical_config_sha256" in e for e in errors)


def test_validate_counted_mode_rejects_missing_scent_hash():
    decl = _valid_decl()
    decl.scent_model_hash = ""
    errors = validate_for_counted_mode(decl)
    assert any("scent_model_hash" in e for e in errors)


# ---------------------------------------------------------------------------
# DeclarationAgreement
# ---------------------------------------------------------------------------


def test_declaration_agreement_canonical_bytes_deterministic():
    agreement = DeclarationAgreement(
        game_uid="g1",
        agreement_hash="abc",
        local_declaration_hash="lll",
        remote_declaration_hash="rrr",
        timestamp_utc="2026-01-01T00:00:00+00:00",
    )
    assert agreement.canonical_bytes() == agreement.canonical_bytes()


def test_declaration_agreement_from_declarations_order_independent():
    h1 = "a" * 64
    h2 = "b" * 64
    ag1 = DeclarationAgreement.from_declarations("game-x", h1, h2)
    ag2 = DeclarationAgreement.from_declarations("game-x", h2, h1)
    # Agreement hash must be the same regardless of local/remote order
    assert ag1.agreement_hash == ag2.agreement_hash


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
