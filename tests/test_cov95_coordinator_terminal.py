"""Cover coordinator cleanup_session and technical-loss terminal transitions."""

from __future__ import annotations

import json

from cop_worker.mcp.coordinator import ProtocolCoordinator
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.session_registry import SessionRegistry

GID, GL, ROLE = "match_g1", 1, "cop"


def _coord():
    return ProtocolCoordinator(registry=SessionRegistry())


def _drive_to_done(c):
    c.on_handshake_complete(GID, GL, ROLE)
    c.begin_step(GID, GL, ROLE, step=1)
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    c.on_reveal_exchange_complete(GID, GL, ROLE, step=1)
    c.on_audit_begin(GID, GL, ROLE)
    c.on_final_audit_complete(GID, GL, ROLE)
    c.on_done(GID, GL, ROLE)


def test_cleanup_session_removes_terminal_session():
    c = _coord()
    _drive_to_done(c)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.DONE
    c.cleanup_session(GID, GL, ROLE)
    assert c.get_state(GID, GL, ROLE) is None


def test_cleanup_session_unknown_is_noop():
    c = _coord()
    c.cleanup_session("ghost", 2, ROLE)  # state None -> remove branch, no error
    assert c.get_state("ghost", 2, ROLE) is None


def test_cleanup_session_keeps_non_terminal_session():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)  # READY (non-terminal)
    c.cleanup_session(GID, GL, ROLE)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.READY


def test_on_technical_loss_writes_evidence_and_transitions(tmp_path):
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    evidence_path = tmp_path / "tl.json"
    c.on_technical_loss(
        GID,
        GL,
        ROLE,
        reason="peer vanished",
        evidence={"detail": "no ack"},
        evidence_path=str(evidence_path),
    )
    assert c.get_state(GID, GL, ROLE) == ProtocolState.TECHNICAL_LOSS
    data = json.loads(evidence_path.read_text())
    assert data["reason"] == "peer vanished"
    assert data["protocol_state"] == ProtocolState.TECHNICAL_LOSS.value
