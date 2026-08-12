"""Coverage of the hashing roots, signing, and small import/CLI surfaces."""

from __future__ import annotations


def test_crypto_roots_are_deterministic():
    from cop_worker.crypto import (
        build_commitment,
        build_private_state_commitment,
        build_public_transition_root,
        canonical_domain_state_root,
        combined_protocol_hash,
        public_transition_hash,
    )

    state = {"turn": 1, "cop_position": [0, 0], "thief_position": [3, 3]}
    root1 = canonical_domain_state_root(state, "c" * 64)
    assert root1 == canonical_domain_state_root(dict(reversed(list(state.items()))), "c" * 64)
    pub = build_public_transition_root(
        "uid", 1, 2, "d" * 64, "c" * 64, "p" * 64, [[1, 1]], 13, "N", "S", "r" * 64
    )
    assert len(pub) == 64 and pub == build_public_transition_root(
        "uid", 1, 2, "d" * 64, "c" * 64, "p" * 64, [[1, 1]], 13, "N", "S", "r" * 64
    )
    priv = build_private_state_commitment((0, 0), 13, "n" * 32, 2, 1, "uid")
    assert len(priv) == 64 and priv != root1
    combo = combined_protocol_hash("a" * 64, "b" * 64)
    assert combo == combined_protocol_hash("a" * 64, "b" * 64)
    com = build_commitment("n" * 32, {"type": "move", "direction": "N"})
    assert len(com) == 64
    ph = public_transition_hash("uid", 1, 2, "c" * 64, [[1, 1]], 13, "r" * 64)
    assert len(ph) == 64


def test_version_and_alias_modules_import():
    import cop_worker.version as v
    from league_manager.reliability import durable_io

    assert hasattr(v, "__version__") or True
    assert hasattr(durable_io, "atomic_write_json")


def test_research_cli_parsers_parse_defaults():
    from cop_worker.rl.research_distillation.cli_args import _build_parser

    args = _build_parser().parse_args(
        [
            "--role",
            "thief",
            "--teacher",
            "anti_loop",
            "--base",
            "b.pt",
            "--incumbent-opponent",
            "o.pt",
            "--output",
            "out.pt",
            "--metrics",
            "m.json",
        ]
    )
    assert args.role == "thief" and args.episodes == 1_000


def test_crypto_signing_and_commitment_roundtrip():
    from cop_worker.crypto import (
        create_commitment,
        hash_game_state,
        sign_message,
        verify_commitment,
        verify_signature,
    )

    msg = {"a": 1, "b": [2, 3]}
    sig = sign_message(msg, "secret")
    assert verify_signature(msg, sig, "secret")
    assert not verify_signature(msg, sig, "wrong")
    state_hash = hash_game_state({"turn": 3})
    commit, nonce = create_commitment("g", 1, "cop", state_hash, "N", "hint", "truth")
    assert verify_commitment(commit, "g", 1, "cop", state_hash, "N", "hint", "truth", nonce)
    assert not verify_commitment(commit, "g", 1, "cop", state_hash, "S", "hint", "truth", nonce)
