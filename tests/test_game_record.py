"""Game-record artifact: capture and merge of BOTH sides' wire experience.

The sealed log proves integrity but drops the wire experience (received scent
bytes, hints, claims). record_<game>_gNN.json keeps it; this module pins the
merge and timeline; the replay-API surface is pinned in
tests/test_game_record_api.py (fixtures shared via helpers_game_record.py).
"""

from __future__ import annotations

from helpers_game_record import _record

from cop_worker.replay.game_record import record_timeline


def test_record_merges_wire_and_seals_per_step_for_both_sides():
    doc = _record()
    assert doc["_schema"] == "game_record_v1"
    step1 = doc["steps"][0]
    # ours: sealed position + the wire extras the seal never carried
    assert step1["ours"]["position"] == [3, 2]
    assert step1["ours"]["hint"] == "going north 1"
    assert step1["ours"]["smell_grid"]["3,3"] == 0.8
    # theirs: the ACTUAL received scent bytes + audit-revealed position, marked
    assert step1["theirs"]["smell_grid"] == {"0,0": 0.8}
    assert step1["theirs"]["position"] == [0, 1]
    assert step1["theirs"]["position_source"] == "audit_reveal"
    assert doc["steps"][1]["theirs"]["barrier_placed"] == [1, 1]


def test_record_timeline_is_chronological_with_recorded_scent():
    label, entries = record_timeline(_record())
    assert label.startswith("RECORDED")
    # thief (us) moves first within each protocol step
    assert [(e["step"], e["side"]) for e in entries] == [
        (1, "ours"),
        (1, "opponent"),
        (2, "ours"),
        (2, "opponent"),
    ]
    board = entries[-1]["board"]
    assert board["scent_source"] == "recorded"
    # wire positions are [row,col]; the board normalizes to the viewer's (x,y)
    # so markers align with the "row,col"-keyed scent and barrier cells
    assert board["thief"] == [1, 3] and board["cop"] == [2, 0]
    # our field lands on the thief channel, theirs on the cop channel
    assert board["scent_thief"]["3,3"] == 0.8
    assert board["scent_cop"] == {"0,0": 0.8}
