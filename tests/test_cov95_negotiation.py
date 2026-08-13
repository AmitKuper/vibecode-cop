"""Cover build/verify negotiation error branches and profile guard."""

from __future__ import annotations

import copy

import pytest

from cop_worker.protocol.introspector import IntrospectionResult
from cop_worker.protocol.reference_v3 import (
    ReferenceV3Error,
    ReferenceV3Profile,
    build_negotiation,
    default_terms,
    verify_negotiation,
)


def _greeting(role: str, group_id: str, sub_game=1, opponent_group=None, terms=None):
    return build_negotiation(
        terms=terms or default_terms({"setting": "New York"}),
        nonce="ab" * 16,
        group_id=group_id,
        group_name=group_id,
        role=role,
        sub_game_number=sub_game,
        opponent_group=opponent_group,
    )


def _ours_theirs():
    terms = default_terms({"setting": "New York"})
    ours = _greeting("thief", "vibecode", terms=terms)
    theirs = _greeting("police", "oppgrp", opponent_group="vibecode", terms=terms)
    return ours, theirs


def test_profile_from_introspection_rejects_non_v3():
    intro = IntrospectionResult(
        server_name="stranger",
        server_version="1",
        protocol_version="x",
        tools=[],
        resources=[],
        prompts=[],
        raw_capabilities={},
        schema_digest="d",
    )
    with pytest.raises(ReferenceV3Error, match="not reference-v3"):
        ReferenceV3Profile.from_introspection(intro)


def test_build_negotiation_rejects_bad_role_and_subgame():
    with pytest.raises(ReferenceV3Error, match="police/thief"):
        _greeting("robber", "vibecode")
    with pytest.raises(ReferenceV3Error, match="police/thief"):
        _greeting("thief", "vibecode", sub_game=9)


def test_verify_negotiation_happy_path():
    ours, theirs = _ours_theirs()
    result = verify_negotiation(ours, theirs)
    assert result.opponent_group == "oppgrp"
    assert result.opponent_role == "police"


def test_verify_negotiation_incomplete_terms():
    ours, theirs = _ours_theirs()
    theirs = copy.deepcopy(theirs)
    theirs["terms"].pop(next(iter(theirs["terms"])))
    with pytest.raises(ReferenceV3Error, match="SPAR-N02"):
        verify_negotiation(ours, theirs)


def test_verify_negotiation_terms_differ():
    ours, _ = _ours_theirs()
    other = _greeting(
        "police", "oppgrp", opponent_group="vibecode", terms=default_terms({"setting": "Boston"})
    )
    with pytest.raises(ReferenceV3Error, match="SPAR-N03"):
        verify_negotiation(ours, other)


def test_verify_negotiation_subgame_mismatch():
    terms = default_terms({"setting": "New York"})
    ours = _greeting("thief", "vibecode", sub_game=1, terms=terms)
    theirs = _greeting("police", "oppgrp", sub_game=2, opponent_group="vibecode", terms=terms)
    with pytest.raises(ReferenceV3Error, match="SPAR-N06"):
        verify_negotiation(ours, theirs)


def test_verify_negotiation_missing_group_id():
    ours, theirs = _ours_theirs()
    theirs = copy.deepcopy(theirs)
    theirs["group_id"] = ""
    theirs["identity"] = {}
    with pytest.raises(ReferenceV3Error, match="SPAR-N08"):
        verify_negotiation(ours, theirs)


def test_verify_negotiation_game_uid_mismatch():
    ours, theirs = _ours_theirs()
    theirs = copy.deepcopy(theirs)
    theirs["game_uid"] = "0" * 64
    with pytest.raises(ReferenceV3Error, match="SPAR-N10"):
        verify_negotiation(ours, theirs)
