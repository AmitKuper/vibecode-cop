"""Cover watchdog heartbeat read/write and failure-evidence emission."""

from __future__ import annotations

import json

from cop_worker.reliability import watchdog


def test_write_and_read_heartbeat(tmp_path):
    hb = tmp_path / "hb.json"
    watchdog.write_heartbeat(
        str(hb),
        pid=1234,
        game_uid="uid",
        session_id="sess",
        step=3,
        state_path=str(tmp_path / "state.json"),
    )
    rec = watchdog._read_heartbeat(str(hb))
    assert rec is not None
    assert rec.pid == 1234 and rec.current_step == 3


def test_read_heartbeat_missing_returns_none(tmp_path):
    assert watchdog._read_heartbeat(str(tmp_path / "nope.json")) is None


def test_write_failure_evidence_hashes_existing_state(tmp_path):
    state = tmp_path / "state.json"
    state.write_text('{"turn": 5}', encoding="utf-8")
    rec = watchdog.HeartbeatRecord(
        pid=99,
        game_uid="uid",
        session_id="sess",
        last_heartbeat_monotonic=0.0,
        last_heartbeat_utc="2026-01-01T00:00:00Z",
        current_step=5,
        state_path=str(state),
    )
    evidence = tmp_path / "evidence.json"
    watchdog._write_failure_evidence(str(evidence), rec, "stale")
    data = json.loads(evidence.read_text())
    assert data["reason"] == "stale"
    assert len(data["recovery_state_sha256"]) == 64  # state file was hashed
    # A technical-loss sibling record is written alongside.
    tl = tmp_path / "technical_loss_watchdog.json"
    assert json.loads(tl.read_text())["protocol_state"] == "technical_loss"
