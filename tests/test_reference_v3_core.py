"""Fast unit tests for the reference-v3 canonical primitives (both copies).

Pure crypto/canonicalisation — no network, no LLM. Includes the kit's own
core-vector self-check.
"""

from __future__ import annotations

import pytest

from cop_worker.protocol import reference_v3 as cop_rv
from league_manager.protocol import reference_v3 as lm_rv

MODS = [cop_rv, lm_rv]


@pytest.mark.parametrize("rv", MODS)
def test_core_vectors_self_check(rv):
    rv.assert_core_vectors()  # kit's pinned vectors — must not raise


@pytest.mark.parametrize("rv", MODS)
def test_canonical_json_sorted_compact_unicode(rv):
    assert rv.canonical_json({"b": 1, "a": "é"}) == '{"a":"é","b":1}'
    assert len(rv.canonical_hash({"x": 1})) == 64


@pytest.mark.parametrize("rv", MODS)
def test_reference_commit_and_terms_signature(rv):
    payload = {"move": "N"}
    h = rv.reference_commit(payload, "nonce123")
    assert len(h) == 64 and h == rv.reference_commit(payload, "nonce123")
    assert rv.terms_signature({"a": 1}, "n") == rv.reference_commit({"a": 1}, "n")


@pytest.mark.parametrize("rv", MODS)
def test_reference_commit_rejects_bad_input(rv):
    with pytest.raises(rv.ReferenceV3Error):
        rv.reference_commit({"m": 1}, "")  # empty nonce
    with pytest.raises(rv.ReferenceV3Error):
        rv.reference_commit("not-a-dict", "n")


@pytest.mark.parametrize("rv", MODS)
def test_derive_game_id_and_uid_are_order_independent(rv):
    assert rv.derive_game_id("teamB", "teamA") == rv.derive_game_id("teamA", "teamB")
    terms = rv.default_terms()
    uid1 = rv.derive_game_uid(terms, "a", "b")
    uid2 = rv.derive_game_uid(terms, "b", "a")
    assert uid1 == uid2 and len(uid1) == 36  # UUID string


@pytest.mark.parametrize("rv", MODS)
def test_default_terms_is_closed_14_key_agreement(rv):
    terms = rv.default_terms()
    assert terms["num_games"] == 6 and terms["board_size"] == 7
    assert rv.default_terms({"setting": "Tel Aviv"})["setting"] == "Tel Aviv"


@pytest.mark.parametrize("rv", MODS)
def test_default_terms_rejects_unknown_key(rv):
    with pytest.raises(rv.ReferenceV3Error):
        rv.default_terms({"totally_unknown": 1})
