"""Fast unit tests for the ProtocolCoordinator state machine.

The coordinator is a synchronous state authority — no network, no async, no LLM.
Each test uses a fresh SessionRegistry for isolation.
"""

from __future__ import annotations

from cop_worker.mcp.coordinator import ProtocolCoordinator, gamelet_from_game_id
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.session_registry import SessionRegistry

GID, GL, ROLE = "match_g1", 1, "cop"


def _coord():
    return ProtocolCoordinator(registry=SessionRegistry())


# --- helper -----------------------------------------------------------------


def test_gamelet_from_game_id():
    assert gamelet_from_game_id("abc_g3") == 3
    assert gamelet_from_game_id("legacy") == 0  # non-strict fallback


def test_gamelet_from_game_id_strict_raises():
    import pytest

    with pytest.raises(ValueError):
        gamelet_from_game_id("legacy", strict=True)


def test_get_state_none_for_unknown_session():
    assert _coord().get_state("nope", 1, "cop") is None


# --- active outbound lifecycle ----------------------------------------------


def test_full_active_lifecycle_to_done():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.READY
    c.begin_step(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.COMPUTING_MOVE
    c.on_commit_exchange_complete(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.BOTH_COMMITTED
    c.on_reveal_exchange_complete(GID, GL, ROLE, step=1)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.STEP_VERIFIED
    c.on_audit_begin(GID, GL, ROLE)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.AUDITING
    c.on_final_audit_complete(GID, GL, ROLE)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.RESULT_AGREEMENT
    c.on_done(GID, GL, ROLE)
    assert c.get_state(GID, GL, ROLE) == ProtocolState.DONE


def test_handshake_is_idempotent():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.on_handshake_complete(GID, GL, ROLE)  # second call is a no-op
    assert c.get_state(GID, GL, ROLE) == ProtocolState.READY


def test_technical_loss_transition():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.on_technical_loss(GID, GL, ROLE, reason="peer timeout")
    assert c.get_state(GID, GL, ROLE) == ProtocolState.TECHNICAL_LOSS


# --- inbound commit guard + idempotency -------------------------------------


def test_inbound_commit_accept_then_idempotent_then_conflict():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    ok, err, cached, prev = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    assert ok and err is None and cached is None and prev == ProtocolState.READY
    c.record_commit_response(GID, GL, ROLE, 1, "h1", {"ack": True})
    # exact duplicate → cached idempotent response
    ok2, _, cached2, _ = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    assert ok2 and cached2 == {"ack": True, "idempotent": True}
    # conflicting duplicate (different h_commit, same step) → rejected
    ok3, err3, _, _ = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "DIFFERENT")
    assert not ok3 and "Conflicting" in err3


def test_inbound_commit_out_of_order_rejected():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.check_and_advance_inbound_commit(GID, GL, ROLE, 2, "h2")
    ok, err, _, _ = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")  # step regress
    assert not ok and "Out-of-order" in err


def test_rollback_inbound_commit_reverts_state_and_counter():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    ok, _, _, prev = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    assert ok
    c.rollback_inbound_commit(GID, GL, ROLE, prev)
    assert c.get_state(GID, GL, ROLE) == prev
    # counter reverted → the same step is accepted again
    ok2, err2, _, _ = c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    assert ok2 and err2 is None


# --- inbound reveal + final audit -------------------------------------------


def test_inbound_reveal_and_final_audit_flow():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")  # → COMMIT_RECEIVED
    c.on_passive_commit_sent(GID, GL, ROLE, 1, "h1")  # → BOTH_COMMITTED
    ok, err, _, prev = c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "N")
    assert ok and err is None and prev is not None
    c.record_reveal_response(GID, GL, ROLE, 1, "N", {"ack": True})
    ok_dup, _, cached, _ = c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "N")
    assert ok_dup and cached["idempotent"] is True
    ok_conf, err_conf, _, _ = c.check_and_advance_inbound_reveal(GID, GL, ROLE, 1, "S")
    assert not ok_conf and "Conflicting" in err_conf


def test_snapshot_idempotency_is_json_safe():
    c = _coord()
    c.on_handshake_complete(GID, GL, ROLE)
    c.check_and_advance_inbound_commit(GID, GL, ROLE, 1, "h1")
    c.record_commit_response(GID, GL, ROLE, 1, "h1", {"ack": True})
    snap = c.snapshot_idempotency(GID, GL, ROLE)
    assert isinstance(snap, dict)
