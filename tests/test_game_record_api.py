"""Game-record replay API + session capture (split from test_game_record.py)."""

from __future__ import annotations

import asyncio
import json

from helpers_game_record import RESULTS, _record, live_client


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

    asyncio.run(session.send_turn(dict(turn), dict(record)))
    asyncio.run(session.send_turn(dict(turn), dict(record)))  # idempotent retry
    assert len(session.sent_turns) == 1, "a retry must not duplicate the capture"
    assert session.sent_turns[0]["smell_grid"] == {"3,3": 0.8}


def test_archived_history_records_are_listed_and_replayable():
    """A rematch rotates results/record_* - the per-run archive under
    results/history/ must stay reachable in the viewer (and only records:
    the history prefix is not a directory-traversal door)."""
    hist = RESULTS / "history"
    hist.mkdir(parents=True, exist_ok=True)  # fresh clone (CI) has no archive yet
    seeded = hist / "record_test-archived_g01_20260101-000000.json"
    seeded.write_text(json.dumps(_record()), encoding="utf-8")
    try:
        assert f"history/{seeded.name}" in live_client.get("/api/replay/logs").json()
        d = live_client.get("/api/replay/steps", params={"log": f"history/{seeded.name}"}).json()
        assert d["overall"].startswith("RECORDED")
        assert len(d["steps"]) == 4
    finally:
        seeded.unlink()
    # non-record files in history/ (result archives) are refused
    r = live_client.get("/api/replay/steps", params={"log": "history/result_x.json"})
    assert r.status_code == 404
