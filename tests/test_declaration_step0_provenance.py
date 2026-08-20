"""Pins Step-0 declaration provenance (external review 2026-08-20).

The declaration must read as PRE-game evidence: stamped with the series
start, and carrying a checksum for any hardware spec the opponent actually
transmitted (both were wrong: declared_at == ended_at, sha hard-coded "").
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from league_artifacts.core import _sha  # noqa: E402
from league_artifacts.declaration import build_declaration  # noqa: E402

ARGS = {
    "game_id": "opp-vs-vibecode",
    "game_uid": "uid-1",
    "opponent": "opp",
    "members": ["A", "B"],
    "cop_commit": "c" * 7,
    "started_at": "2026-08-20T10:00:00+00:00",
    "ended_at": "2026-08-20T10:30:00+00:00",
}


def test_declared_at_is_series_start_not_end():
    dec = build_declaration(**ARGS)
    assert dec["declared_at"] == ARGS["started_at"]
    assert dec["game_ended_at"] == ARGS["ended_at"]
    assert dec["declared_at"] < dec["game_ended_at"]


def test_opponent_hardware_sha_from_transmitted_spec():
    spec = {"os": "Linux", "cpu_cores": 8}
    dec = build_declaration(**ARGS, opp_identity={"hardware_spec": spec})
    assert dec["groups"]["group_2"]["hardware_spec_sha256"] == _sha(spec)


def test_opponent_own_sha_wins_when_transmitted():
    spec = {"os": "Linux"}
    oi = {"hardware_spec": spec, "hardware_spec_sha256": "their-sha"}
    dec = build_declaration(**ARGS, opp_identity=oi)
    assert dec["groups"]["group_2"]["hardware_spec_sha256"] == "their-sha"


def test_opponent_empty_spec_keeps_empty_sha():
    dec = build_declaration(**ARGS, opp_identity={})
    assert dec["groups"]["group_2"]["hardware_spec"] == {}
    assert dec["groups"]["group_2"]["hardware_spec_sha256"] == ""
