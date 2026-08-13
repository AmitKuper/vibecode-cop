"""Cover the passive (peer-first) coordinator lifecycle and reveal guards."""

from __future__ import annotations

from cop_worker.mcp.coordinator import ProtocolCoordinator
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.session_registry import SessionRegistry

GID, GL, ROLE = "match_g1", 1, "cop"


def _coord():
    return ProtocolCoordinator(registry=SessionRegistry())


def test_passive_lifecycle_peer_commits_and_reveals_first():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    ok, err, _, _ = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    assert ok and err is None
    assert c.get_state(GID, GL, ROLE) == ProtocolState.COMMIT_RECEIVED
    # We send our commit after the peer's -> BOTH_COMMITTED via the peer-first branch.
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.BOTH_COMMITTED
    # Idempotent second call is a no-op.
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.BOTH_COMMITTED

    ok, err, _, prev = c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "NORTH")
    assert ok and c.get_state(GID, GL, ROLE) == ProtocolState.REVEAL_RECEIVED
    c.on_reveal_exchange_complete(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.STEP_VERIFIED
    c.on_reveal_exchange_complete(GID, GL, ROLE, step=1)  # idempotent
    assert c.get_state(GID, GL, ROLE) == ProtocolState.STEP_VERIFIED


def test_begin_step_from_step_verified_advances_step():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "NORTH")
    c.on_reveal_exchange_complete(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.STEP_VERIFIED
    c.begin_step(GID, GL, ROLE, step=2)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.COMPUTING_MOVE


def test_handshake_complete_in_unexpected_state_warns_and_returns():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.begin_step(GID, GL, ROLE, step=1)  # -> COMPUTING_MOVE
    c.on_handshake_complete(GID, GL, ROLE)  # unexpected state, warns, no change
    assert c.get_state(GID, GL, ROLE) == ProtocolState.COMPUTING_MOVE


def test_inbound_reveal_out_of_order_is_rejected():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "NORTH")
    c.on_reveal_exchange_complete(GID, GL, ROLE, step=1)
    # Replaying step 1 (no cached idempotency record) is rejected as out of order.
    ok, err, _, _ = c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "SOUTH")
    assert not ok and "Out-of-order reveal" in err


def test_rollback_inbound_reveal_restores_state_and_ignores_unknown():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    ok, err, _, prev = c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "NORTH")
    assert c.get_state(GID, GL, ROLE) == ProtocolState.REVEAL_RECEIVED
    c.rollback_inbound_reveal(GID, GL, ROLE, prev)
    assert c.get_state(GID, GL, ROLE) == prev
    # Unknown session is a silent no-op.
    c.rollback_inbound_reveal("nope", 9, ROLE, ProtocolState.READY)
