"""Tests for the Step-0 declaration schema (PeerDeclaration, SignedDeclaration, agreement)."""

import json

from cop_worker.step0.declaration import DeclarationAgreement, SignedDeclaration
from tests.helpers_step0_declarations import _make_decl

# ---------------------------------------------------------------------------
# PeerDeclaration
# ---------------------------------------------------------------------------


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
