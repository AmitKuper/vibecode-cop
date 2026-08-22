"""Pins kit §5 series-label folding into game_id/game_uid (wgroup counted prep).

Two counted series between the same teams must not collapse to one uid: with
a label, the uid seed switches from the sorted pair to the LABELED game_id.
Without a label every derivation is byte-identical to the pre-label code —
all nine played pairings keep their historical ids.
"""

from __future__ import annotations

import hashlib
import uuid

from cop_worker.protocol.reference_v3 import (
    ReferenceV3Error,
    build_negotiation,
    canonical_json,
    default_terms,
    derive_game_id,
    derive_game_uid,
    verify_negotiation,
)

TERMS = default_terms()


def _spec_uid(terms: dict, seed_tail: str) -> str:
    digest = hashlib.sha256(f"{canonical_json(terms)}|{seed_tail}".encode()).digest()
    return str(uuid.UUID(bytes=digest[:16]))


def test_labeled_uid_matches_the_kit_section5_formula():
    # their spec: seed_tail = game_id (incl. label) when a label is used
    assert derive_game_id("wgroup", "vibecode", "counted1") == "vibecode-vs-wgroup-counted1"
    assert derive_game_uid(TERMS, "wgroup", "vibecode", "counted1") == _spec_uid(
        TERMS, "vibecode-vs-wgroup-counted1"
    )


def test_unlabeled_derivation_is_byte_identical_to_history():
    # seed_tail = "|".join(sorted pair) — the form every played series used
    assert derive_game_id("wgroup", "vibecode") == "vibecode-vs-wgroup"
    assert derive_game_uid(TERMS, "wgroup", "vibecode") == _spec_uid(TERMS, "vibecode|wgroup")
    assert derive_game_uid(TERMS, "a", "b", None) == derive_game_uid(TERMS, "b", "a")


def test_label_changes_the_uid():
    plain = derive_game_uid(TERMS, "wgroup", "vibecode")
    labeled = derive_game_uid(TERMS, "wgroup", "vibecode", "counted1")
    relabeled = derive_game_uid(TERMS, "wgroup", "vibecode", "counted2")
    assert len({plain, labeled, relabeled}) == 3


def _greeting(group: str, role: str, label=None, opponent=None):
    return build_negotiation(
        terms=TERMS,
        nonce="ab" * 16,
        group_id=group,
        group_name=group,
        role=role,
        sub_game_number=1,
        opponent_group=opponent,
        series_label=label,
    )


def test_handshake_agrees_when_both_fold_the_same_label():
    ours = _greeting("vibecode", "police", "counted1", opponent="wgroup")
    theirs = _greeting("wgroup", "thief", "counted1", opponent="vibecode")
    negotiated = verify_negotiation(ours, theirs, "counted1")
    assert negotiated.game_id == "vibecode-vs-wgroup-counted1"
    assert negotiated.game_uid == theirs["game_uid"] == ours["game_uid"]


def test_handshake_refuses_a_label_disagreement():
    # we fold the agreed label; a peer that forgot it declares the unlabeled uid
    ours = _greeting("vibecode", "police", "counted1", opponent="wgroup")
    theirs = _greeting("wgroup", "thief", None, opponent="vibecode")
    try:
        verify_negotiation(ours, theirs, "counted1")
    except ReferenceV3Error as exc:
        assert "SPAR-N10" in str(exc)
    else:
        raise AssertionError("a label disagreement must refuse (SPAR-N10)")


def test_game_id_only_scope_keeps_the_core_uid(monkeypatch):
    # per-pairing dialect (agreed in writing 2026-08-22): the label names the
    # game_id ONLY; the uid stays the kit CORE derivation for every series
    monkeypatch.setenv("COPTHIEF_LABEL_SCOPE", "game_id_only")
    core = _spec_uid(TERMS, "vibecode|wgroup")
    assert derive_game_uid(TERMS, "wgroup", "vibecode") == core
    assert derive_game_uid(TERMS, "wgroup", "vibecode", "F001") == core
    assert derive_game_uid(TERMS, "wgroup", "vibecode", "C001") == core
    # the label still separates artifacts via the game_id
    assert derive_game_id("wgroup", "vibecode", "F001") == "vibecode-vs-wgroup-F001"


def test_game_id_only_scope_handshake_reconciles_with_a_core_peer(monkeypatch):
    # our labeled greeting must carry the CORE uid a core-only peer derives
    monkeypatch.setenv("COPTHIEF_LABEL_SCOPE", "game_id_only")
    ours = _greeting("vibecode", "police", "F001", opponent="wgroup")
    theirs = _greeting("wgroup", "thief", "F001", opponent="vibecode")
    negotiated = verify_negotiation(ours, theirs, "F001")
    assert negotiated.game_id == "vibecode-vs-wgroup-F001"
    assert negotiated.game_uid == _spec_uid(TERMS, "vibecode|wgroup")


def test_default_scope_is_unchanged(monkeypatch):
    monkeypatch.delenv("COPTHIEF_LABEL_SCOPE", raising=False)
    assert derive_game_uid(TERMS, "wgroup", "vibecode", "counted1") == _spec_uid(
        TERMS, "vibecode-vs-wgroup-counted1"
    )
