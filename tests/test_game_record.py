"""Game-record artifact: capture, merge, and replayability of BOTH sides.

The sealed log proves integrity but drops the wire experience (received scent
bytes, hints, claims). record_<game>_gNN.json keeps it; these tests pin the
whole chain: session capture -> per-step merge -> replay timeline -> API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ref3_match.game_record import build_game_record  # noqa: E402

from cop_worker.gui import app as live_gui  # noqa: E402
from cop_worker.replay.game_record import record_timeline  # noqa: E402

live_client = TestClient(live_gui.app)
RESULTS = Path(__file__).resolve().parents[1] / "results"


def _row() -> dict:
    """A settled sub-game row: we are the thief; the peer cop reveals at audit."""
    sent = [
        {
            "step": s,
            "sender": "thief",
            "commit": f"aa{s:02d}",
            "hint": f"going north {s}",
            "smell_grid": {"3,3": 0.8, "3,4": 0.5},
        }
        for s in (1, 2)
    ]
    received = [
        {
            "step": s,
            "sender": "police",
            "commit": f"bb{s:02d}",
            "hint": "you cannot hide",
            "smell_grid": {"0,0": 0.8},
            "barrier_placed": [1, 1] if s == 2 else None,
        }
        for s in (1, 2)
    ]
    ours = [
        {
            "commit": f"aa{s:02d}",
            "nonce": "n",
            "payload": {"step": s, "position": [3, 3 - s], "move": "N", "intent": "truth"},
        }
        for s in (1, 2)
    ]
    theirs = [
        {
            "commit": f"bb{s:02d}",
            "nonce": "m",
            "payload": {"step": s, "position": [0, s], "move": "S"},
        }
        for s in (1, 2)
    ]
    return {
        "wire_turns": {"sent": sent, "received": received},
        "our_records": ours,
        "opp_records": theirs,
        "summary": {"outcome": "survival", "audit": "Verified OK"},
    }


def _record() -> dict:
    return build_game_record("a-vs-b", "uid", 1, "thief", "peer", _row())


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
    assert board["thief"] == [3, 1] and board["cop"] == [0, 2]
    # our field lands on the thief channel, theirs on the cop channel
    assert board["scent_thief"]["3,3"] == 0.8
    assert board["scent_cop"] == {"0,0": 0.8}


def test_steps_api_serves_record_files_without_verification_claims():
    seeded = RESULTS / "record_test-synthetic_g01.json"
    seeded.write_text(json.dumps(_record()), encoding="utf-8")
    try:
        names = live_client.get("/api/replay/logs").json()
        assert seeded.name in names
        d = live_client.get("/api/replay/steps", params={"log": seeded.name}).json()
        assert d["overall"].startswith("RECORDED"), "records are observational, never 'Verified OK'"
        assert len(d["steps"]) == 4
        assert d["steps"][1]["payload"]["hint"] == "you cannot hide"
    finally:
        seeded.unlink()


def test_session_captures_outbound_wire_turns_once_per_step():
    from cop_worker.protocol.reference_v3 import ReferenceV3Session

    sent_calls = []

    async def caller(tool, args):
        sent_calls.append(tool)
        return {"ok": True}

    session = ReferenceV3Session(caller)
    commit = "ab" * 32  # 64 hex chars, as validate_turn requires
    turn = {
        "type": "turn",
        "sender": "thief",
        "step": 1,
        "commit": commit,
        "hint": "h",
        "smell_grid": {"3,3": 0.8},
    }
    record = {"commit": commit, "nonce": "n", "payload": {"step": 1}}
    import asyncio

    asyncio.run(session.send_turn(dict(turn), dict(record)))
    asyncio.run(session.send_turn(dict(turn), dict(record)))  # idempotent retry
    assert len(session.sent_turns) == 1, "a retry must not duplicate the capture"
    assert session.sent_turns[0]["smell_grid"] == {"3,3": 0.8}
