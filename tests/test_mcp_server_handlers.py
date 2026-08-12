"""Fast unit tests for MCP server_handlers (start_game / action / notify).

Builds real signed messages with sign_message and drives the sync handlers with
a fresh ProtocolCoordinator — no network, no async, no LLM.
"""

from __future__ import annotations

from cop_worker.mcp import server_handlers as sh
from cop_worker.mcp.protocol import ProtocolState
from tests.helpers_mcp_server_handlers import (
    CFG,
    GD,
    GID,
    SECRET,
    _action,
    _coord,
    _handshake,
    _start,
    _start_game,
)

# --- start_game -------------------------------------------------------------


def test_start_game_happy_path_reaches_ready():
    coord = _coord()
    mj, sig = _start()
    resp = _start_game(coord, mj, sig)
    assert resp["ok"] is True
    assert coord.get_state(GID, 1, "cop") == ProtocolState.READY


def test_start_game_is_idempotent():
    coord = _coord()
    mj, sig = _start()
    _start_game(coord, mj, sig)
    resp2 = _start_game(coord, mj, sig)
    assert resp2["ok"] is True


def test_start_game_config_mismatch_rejected():
    coord = _coord()
    mj, sig = _start()
    resp = _start_game(coord, mj, sig, cfg="b" * 64)
    assert resp["ok"] is False and "mismatch" in resp["error"].lower()


def test_start_game_bad_signature_rejected():
    coord = _coord()
    mj, _ = _start()
    resp = _start_game(coord, mj, "0" * 64)
    assert resp["ok"] is False and "signature" in resp["error"].lower()


def test_start_game_callback_gate():
    coord = _coord()
    mj, sig = _start()
    resp = _start_game(coord, mj, sig, callbacks={"on_start_game": lambda m: {"ok": True, "x": 1}})
    assert resp["ok"] is True and resp["x"] == 1
    # a rejecting callback blocks READY
    coord2 = _coord()
    resp2 = _start_game(coord2, mj, sig, callbacks={"on_start_game": lambda m: {"ok": False}})
    assert resp2["ok"] is False


# --- action: commit / reveal ------------------------------------------------


def test_action_commit_happy_path():
    coord = _coord()
    _handshake(coord)
    mj, sig = _action(phase="commit", h_commit="b" * 64)
    resp = sh.handle_action("cop", SECRET, CFG, GD, {}, {}, GID, mj, sig, coordinator=coord)
    assert resp["ok"] is True


def test_action_signature_and_config_and_invalid_paths():
    coord = _coord()
    _handshake(coord)
    mj, _ = _action(phase="commit", h_commit="b" * 64)
    assert (
        sh.handle_action("cop", SECRET, CFG, GD, {}, {}, GID, mj, "0" * 64, coordinator=coord)["ok"]
        is False
    )  # bad sig
    mj2, sig2 = _action(phase="commit", h_commit="b" * 64)
    assert (
        sh.handle_action("cop", SECRET, "c" * 64, GD, {}, {}, GID, mj2, sig2, coordinator=coord)[
            "ok"
        ]
        is False
    )  # config mismatch


def test_action_commit_then_reveal_with_passive_advance():
    coord = _coord()
    # callback returns peer's h_commit (commit) and move (reveal) to advance the SM
    cbs = {
        "on_action": lambda gid, m: (
            {"ok": True, "h_commit": "c" * 64} if m.phase == "commit" else {"ok": True, "move": "N"}
        )
    }
    _handshake(coord)
    cm, cs = _action(phase="commit", h_commit="b" * 64)
    assert sh.handle_action("cop", SECRET, CFG, GD, {}, cbs, GID, cm, cs, coordinator=coord)["ok"]
    rm, rs = _action(phase="reveal", move="N")
    assert sh.handle_action("cop", SECRET, CFG, GD, {}, cbs, GID, rm, rs, coordinator=coord)["ok"]
    assert coord.get_state(GID, 1, "cop") == ProtocolState.STEP_VERIFIED


# --- notify_* wrappers (drive module-singleton coordinator; just must not raise) ---


def test_notify_wrappers_do_not_raise():
    g = "NOTIFY_g1"
    sh.notify_step_begin(g, 1, "cop", 1)
    sh.notify_commit_sent(g, 1, "cop", 1)
    sh.notify_reveal_sent(g, 1, "cop", 1)
    sh.notify_audit_begin(g, 1, "cop")
    sh.notify_done(g, 1, "cop")
    sh.notify_technical_loss(g, 1, "cop", reason="x")
