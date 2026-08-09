"""Step-0 scent-model declaration and game_uid emission are configuration, not constants.

Pins the imreeyal pairing requirements: declaring ``subtractive_chebyshev_v1`` must put the
kit-recomputed ``81ebee59…`` on the wire (their pasted book-model sha reproduces at no kit
commit — ours is the registry value), and a known opponent group must surface our derived
``game_uid`` top-level in the greeting (kit §7.3: both-declare-differ refuses, omission
never refuses).
"""

from __future__ import annotations

import pytest

from cop_worker.protocol.reference_v3 import (
    SCENT_LOCKS,
    ReferenceV3Error,
    build_negotiation,
    default_terms,
    derive_game_uid,
)

CHEB = "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4"
BOOK = "934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9"


def _greeting(**kw) -> dict:
    return build_negotiation(
        terms=default_terms({"setting": "New York"}),
        nonce="ab" * 16,
        group_id="vibecode",
        group_name="vibecode",
        role="thief",
        sub_game_number=1,
        **kw,
    )


def test_registry_carries_both_kit_hashes() -> None:
    assert SCENT_LOCKS == {
        "multiplicative_book_v1": BOOK,
        "subtractive_chebyshev_v1": CHEB,
    }


def test_default_declaration_stays_book_model() -> None:
    assert _greeting()["scent_model_sha256"] == BOOK


def test_chebyshev_declaration_puts_the_kit_hash_on_the_wire() -> None:
    wire = _greeting(scent_model="subtractive_chebyshev_v1")
    assert wire["scent_model_sha256"] == CHEB


def test_unknown_model_is_a_refusal_not_a_default() -> None:
    with pytest.raises(ReferenceV3Error, match="unknown scent model"):
        _greeting(scent_model="no_such_model_v9")


def test_known_opponent_group_declares_the_derived_game_uid() -> None:
    wire = _greeting(opponent_group="imreeyal")
    expected = derive_game_uid(wire["terms"], "vibecode", "imreeyal")
    assert wire["game_uid"] == expected


def test_unknown_opponent_omits_game_uid_and_omission_never_refuses() -> None:
    assert "game_uid" not in _greeting()
