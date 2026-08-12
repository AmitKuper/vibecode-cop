"""Shared constants and signed-message builders for the server_handlers tests."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cop_worker.crypto import sign_message
from cop_worker.mcp import server_handlers as sh
from cop_worker.mcp.coordinator import ProtocolCoordinator
from cop_worker.mcp.messages_game import ActionMessage, StartGameMessage
from cop_worker.mcp.session_registry import SessionRegistry

SECRET = "sekret"
CFG = "a" * 64
GID = "M_g1"
GD = Path(tempfile.mkdtemp(prefix="sh_test_"))  # scratch games dir for GameLog


def _coord():
    return ProtocolCoordinator(registry=SessionRegistry())


def _start(**over):
    fields = {
        "game_id": GID,
        "roles": {"cop": "p1", "police": "p2"},
        "config_sha256": CFG,
        "protocol_version": "1.0",
        "endpoint": "http://localhost:5000/mcp",
        "timestamp": "2026-01-01T00:00:00Z",
    }
    fields.update(over)
    msg = StartGameMessage(**fields)
    d = msg.to_dict()
    return json.dumps(d), sign_message(d, SECRET)


def _action(**over):
    fields = {
        "game_id": GID,
        "step": 1,
        "role": "cop",
        "config_sha256": CFG,
        "timestamp": "t",
        "phase": "commit",
    }
    fields.update(over)
    msg = ActionMessage(**fields)
    d = msg.to_dict()
    return json.dumps(d), sign_message(d, SECRET)


def _start_game(coord, msg_json, sig, role="cop", cfg=CFG, callbacks=None):
    return sh.handle_start_game(
        role, SECRET, cfg, GD, {}, callbacks or {}, msg_json, sig, coordinator=coord
    )


def _handshake(coord, callbacks=None):
    mj, sig = _start()
    _start_game(coord, mj, sig, callbacks=callbacks)
