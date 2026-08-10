"""Behavioral tests for cop_worker.mcp.server_handlers routing and error paths."""

from __future__ import annotations

import json

from cop_worker.crypto import sign_message
from cop_worker.mcp import server_handlers as sh
from cop_worker.mcp.coordinator import ProtocolCoordinator, get_coordinator
from cop_worker.mcp.messages import ActionMessage, StartGameMessage
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.session_registry import SessionRegistry

SECRET = "s3cret"
SHA = "a" * 64
_ROLES = {"cop": "us", "police": "them"}


def _coord() -> ProtocolCoordinator:
    return ProtocolCoordinator(registry=SessionRegistry())


def _sg():
    return StartGameMessage("G_g1", _ROLES, SHA, "1.0", "http://localhost:5000/mcp", "t")


def _start(tmp_path, coord, msg=None, sig=None, role="cop", callbacks=None, config=SHA, raw=None):
    msg = msg or _sg()
    payload = raw if raw is not None else json.dumps(msg.to_dict())
    signature = sig if sig is not None else sign_message(msg.to_dict(), SECRET)
    args = (role, SECRET, config, tmp_path, {}, callbacks or {}, payload, signature)
    return sh.handle_start_game(*args, coordinator=coord)


def _act(tmp_path, coord, msg, callbacks=None, sig=None, config=SHA, raw=None):
    payload = raw if raw is not None else json.dumps(msg.to_dict())
    signature = sig if sig is not None else sign_message(msg.to_dict(), SECRET)
    args = ("cop", SECRET, config, tmp_path, {}, callbacks or {}, msg.game_id, payload, signature)
    return sh.handle_action(*args, coordinator=coord)


def _action_msg(phase, step=1, **kw):
    return ActionMessage("G_g1", step, "cop", SHA, "t", phase, **kw)


def test_start_game_success_idempotent_and_guard(tmp_path):
    coord = _coord()
    assert _start(tmp_path, coord)["ok"] is True
    assert _start(tmp_path, coord)["ok"] is True  # READY is idempotent
    coord.begin_step("G_g1", 1, "cop", 1)
    denied = _start(tmp_path, coord)
    assert denied["ok"] is False and "Protocol violation" in denied["error"]


def test_start_game_rejections_and_callbacks(tmp_path):
    coord = _coord()
    assert "Signature" in _start(tmp_path, coord, sig="0" * 64)["error"]
    assert "Config mismatch" in _start(tmp_path, coord, config="b" * 64)["error"]
    assert "My role" in _start(tmp_path, coord, role="initiator")["error"]
    bad = _sg()
    bad.endpoint = "ftp://nope"
    assert _start(tmp_path, coord, msg=bad)["ok"] is False
    assert _start(tmp_path, coord, raw="{not json")["ok"] is False
    ok = _start(tmp_path, coord, callbacks={"on_start_game": lambda m: {"ok": True, "extra": 1}})
    assert ok["ok"] is True and ok["extra"] == 1
    rejected = _start(tmp_path, _coord(), callbacks={"on_start_game": lambda m: {"ok": False}})
    assert "Local Step-0 rejected" in rejected["error"]


def test_action_full_lifecycle(tmp_path):
    coord = _coord()
    coord.on_handshake_complete("G_g1", 1, "cop")
    cbs = {"on_action": lambda gid, m: {"ok": True, "h_commit": "c" * 64}}
    assert _act(tmp_path, coord, _action_msg("commit", h_commit="b" * 64), cbs)["ok"] is True
    assert coord.get_state("G_g1", 1, "cop") == ProtocolState.BOTH_COMMITTED
    cbs = {"on_action": lambda gid, m: {"ok": True, "move": "N"}}
    reveal = _action_msg("reveal", move="N", hint="going north", intent="truth")
    assert _act(tmp_path, coord, reveal, cbs)["ok"] is True
    assert coord.get_state("G_g1", 1, "cop") == ProtocolState.STEP_VERIFIED
    assert _act(tmp_path, coord, _action_msg("game_end", step=1, reason="capture"))["ok"] is True
    assert _act(tmp_path, coord, _action_msg("final_audit", nonces={"1": "n"}))["ok"] is True
    assert coord.get_state("G_g1", 1, "cop") == ProtocolState.RESULT_AGREEMENT
    summary = _action_msg("audit_summary", signed_audit_summary={"sig": "x"})
    assert _act(tmp_path, coord, summary)["ok"] is True
    assert _act(tmp_path, coord, _action_msg("result_agreement"))["ok"] is True
    assert coord.get_state("G_g1", 1, "cop") == ProtocolState.DONE


def test_action_idempotency_conflict_and_rollback(tmp_path):
    coord = _coord()
    coord.on_handshake_complete("G_g1", 1, "cop")
    commit = _action_msg("commit", h_commit="b" * 64)
    assert _act(tmp_path, coord, commit)["ok"] is True
    dup = _act(tmp_path, coord, commit)
    assert dup["ok"] is True and dup.get("idempotent") is True
    conflict = _act(tmp_path, coord, _action_msg("commit", h_commit="d" * 64))
    assert conflict["ok"] is False and "Conflicting" in conflict["error"]
    coord2 = _coord()
    coord2.on_handshake_complete("G_g1", 1, "cop")

    def _boom(gid, m):
        raise RuntimeError("callback exploded")

    failed = _act(tmp_path, coord2, commit, {"on_action": _boom})
    assert failed["ok"] is False and "callback exploded" in failed["error"]
    assert coord2.get_state("G_g1", 1, "cop") == ProtocolState.READY


def test_action_rejections(tmp_path):
    coord = _coord()
    commit = _action_msg("commit", h_commit="b" * 64)
    assert "Protocol violation" in _act(tmp_path, coord, commit)["error"]  # IDLE, no handshake
    assert "Signature" in _act(tmp_path, coord, commit, sig="0" * 64)["error"]
    assert "Config mismatch" in _act(tmp_path, coord, commit, config="e" * 64)["error"]
    bad_step = _action_msg("commit", step=-1, h_commit="b" * 64)
    assert "step must be" in _act(tmp_path, coord, bad_step)["error"]
    reveal = _action_msg("reveal", move="N")
    assert "Protocol violation" in _act(tmp_path, coord, reveal)["error"]
    assert _act(tmp_path, coord, commit, raw="{broken")["ok"] is False
    assert _act(tmp_path, coord, _action_msg("abort", reason="peer gave up"))["ok"] is True
    assert coord.get_state("G_g1", 1, "cop") == ProtocolState.TECHNICAL_LOSS


def test_notify_helpers_drive_global_coordinator():
    coord = get_coordinator()
    gid = "COV85NOTIFY_g2"
    coord.on_handshake_complete(gid, 2, "cop")
    sh.notify_step_begin(gid, 2, "cop", 1)
    assert coord.get_state(gid, 2, "cop") == ProtocolState.COMPUTING_MOVE
    sh.notify_commit_sent(gid, 2, "cop", 1)
    sh.notify_reveal_sent(gid, 2, "cop", 1)
    assert coord.get_state(gid, 2, "cop") == ProtocolState.STEP_VERIFIED
    sh.notify_audit_begin(gid, 2, "cop")
    assert coord.get_state(gid, 2, "cop") == ProtocolState.AUDITING
    ok, err, _prev = coord.check_final_audit_guard(gid, 2, "cop")
    assert ok and err is None
    sh.notify_done(gid, 2, "cop")
    assert coord.get_state(gid, 2, "cop") == ProtocolState.DONE
    coord.on_handshake_complete("COV85LOSS_g3", 3, "cop")
    sh.notify_technical_loss("COV85LOSS_g3", 3, "cop", reason="test")
    assert coord.get_state("COV85LOSS_g3", 3, "cop") == ProtocolState.TECHNICAL_LOSS
