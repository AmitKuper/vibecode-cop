from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Adversarial protocol state machine tests.

Verifies the 16-state machine rejects illegal orderings, duplicates,
and race conditions while accepting the valid happy path.
"""


import threading

import pytest
from cop_worker.mcp.protocol import ProtocolState, ProtocolStateMachine
from cop_worker.mcp.session_registry import SessionEntry, SessionRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fresh_sm() -> ProtocolStateMachine:
    return ProtocolStateMachine()


def advance_to(sm: ProtocolStateMachine, *states: ProtocolState) -> None:
    """Transition through a sequence of states."""
    for s in states:
        sm.transition(s)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_session_setup(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        assert sm.state == ProtocolState.READY

    def test_one_step_cop_commits_first(self):
        """Cop sends commit before receiving thief commit."""
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,  # cop sends commit
            ProtocolState.BOTH_COMMITTED,  # thief commit received
            ProtocolState.REVEAL_SENT,  # cop sends reveal
            ProtocolState.STEP_VERIFIED,  # thief reveal received
        )
        assert sm.state == ProtocolState.STEP_VERIFIED

    def test_one_step_thief_commits_first(self):
        """Thief commit arrives before cop has sent its own."""
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_RECEIVED,  # thief commit arrives first
            ProtocolState.BOTH_COMMITTED,  # cop then sends its commit
            ProtocolState.REVEAL_RECEIVED,  # thief reveal arrives first
            ProtocolState.STEP_VERIFIED,  # cop sends reveal
        )
        assert sm.state == ProtocolState.STEP_VERIFIED

    def test_multi_step_loop(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        for _ in range(3):
            advance_to(
                sm,
                ProtocolState.COMPUTING_MOVE,
                ProtocolState.COMMIT_SENT,
                ProtocolState.BOTH_COMMITTED,
                ProtocolState.REVEAL_SENT,
                ProtocolState.STEP_VERIFIED,
            )
            sm.advance_step()
        assert sm.step == 3

    def test_full_audit_flow(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
            ProtocolState.STEP_VERIFIED,
            ProtocolState.AUDITING,
            ProtocolState.RESULT_AGREEMENT,
            ProtocolState.REPORTING,
            ProtocolState.DONE,
        )
        assert sm.state == ProtocolState.DONE


# ---------------------------------------------------------------------------
# Illegal orderings
# ---------------------------------------------------------------------------


class TestIllegalOrderings:
    def test_reveal_before_both_committed(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
        )
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.REVEAL_SENT)

    def test_commit_before_computing_move(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.COMMIT_SENT)

    def test_skip_negotiating(self):
        sm = fresh_sm()
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.READY)

    def test_skip_to_done_from_idle(self):
        sm = fresh_sm()
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.DONE)

    def test_auditing_before_step_verified(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
        )
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.AUDITING)

    def test_computing_move_from_idle(self):
        sm = fresh_sm()
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.COMPUTING_MOVE)

    def test_result_agreement_before_auditing(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
        )
        with pytest.raises(ValueError, match="Illegal transition"):
            sm.transition(ProtocolState.RESULT_AGREEMENT)


# ---------------------------------------------------------------------------
# Duplicate messages
# ---------------------------------------------------------------------------


class TestDuplicateMessages:
    def test_duplicate_commit_sent(self):
        """Sending commit twice is illegal once in COMMIT_SENT."""
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
        )
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.COMMIT_SENT)

    def test_duplicate_reveal_sent(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
        )
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.REVEAL_SENT)

    def test_duplicate_start_game(self):
        """Once READY, another STEP0_NEGOTIATING must be rejected."""
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY)
        with pytest.raises(ValueError):
            sm.transition(ProtocolState.STEP0_NEGOTIATING)


# ---------------------------------------------------------------------------
# Terminal state enforcement
# ---------------------------------------------------------------------------


class TestTerminalStates:
    def test_done_rejects_all(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
            ProtocolState.STEP_VERIFIED,
            ProtocolState.AUDITING,
            ProtocolState.RESULT_AGREEMENT,
            ProtocolState.REPORTING,
            ProtocolState.DONE,
        )
        for target in ProtocolState:
            with pytest.raises(ValueError, match="terminal"):
                sm.transition(target)

    def test_aborted_rejects_all(self):
        sm = fresh_sm()
        advance_to(sm, ProtocolState.STEP0_NEGOTIATING)
        sm.transition(ProtocolState.ABORTED)
        for target in ProtocolState:
            with pytest.raises(ValueError, match="terminal"):
                sm.transition(target)

    def test_technical_loss_rejects_all(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
        )
        sm.transition(ProtocolState.TECHNICAL_LOSS)
        for target in ProtocolState:
            with pytest.raises(ValueError, match="terminal"):
                sm.transition(target)

    def test_abort_reachable_from_any_non_terminal(self):
        """ABORTED must be reachable from every non-terminal state."""
        non_terminal = [
            s
            for s in ProtocolState
            if s not in (ProtocolState.DONE, ProtocolState.TECHNICAL_LOSS, ProtocolState.ABORTED)
        ]
        for state in non_terminal:
            sm = fresh_sm()
            sm.state = state
            ok, err = sm.can_transition(ProtocolState.ABORTED)
            assert ok, f"ABORTED should be reachable from {state.value}: {err}"

    def test_technical_loss_reachable_from_any_non_terminal(self):
        non_terminal = [
            s
            for s in ProtocolState
            if s not in (ProtocolState.DONE, ProtocolState.TECHNICAL_LOSS, ProtocolState.ABORTED)
        ]
        for state in non_terminal:
            sm = fresh_sm()
            sm.state = state
            ok, err = sm.can_transition(ProtocolState.TECHNICAL_LOSS)
            assert ok, f"TECHNICAL_LOSS should be reachable from {state.value}: {err}"


# ---------------------------------------------------------------------------
# Concurrency safety
# ---------------------------------------------------------------------------


class TestConcurrencySafety:
    def test_session_registry_create_is_idempotent(self):
        """get_or_create returns the same object for the same key under concurrent calls."""
        registry = SessionRegistry()
        results: list[SessionEntry] = []
        errors: list[Exception] = []

        def create():
            try:
                results.append(registry.get_or_create("g1", 0, "cop"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 20
        # All threads must have received the same SessionEntry object
        assert all(r is results[0] for r in results)

    def test_concurrent_state_transitions_serialized(self):
        """Only one of two concurrent commit-received calls should succeed."""
        registry = SessionRegistry()
        entry = registry.get_or_create("g2", 0, "cop")
        # Pre-advance to COMPUTING_MOVE
        entry.sm.transition(ProtocolState.STEP0_NEGOTIATING)
        entry.sm.transition(ProtocolState.READY)
        entry.sm.transition(ProtocolState.COMPUTING_MOVE)

        success_count = 0
        error_count = 0
        lock = threading.Lock()

        def try_commit_received():
            nonlocal success_count, error_count
            with entry.lock:
                ok, _ = entry.sm.guard_commit_received()
                if ok and entry.sm.state == ProtocolState.COMPUTING_MOVE:
                    try:
                        entry.sm.transition(ProtocolState.COMMIT_RECEIVED)
                        with lock:
                            success_count += 1
                    except ValueError:
                        with lock:
                            error_count += 1
                else:
                    with lock:
                        error_count += 1

        threads = [threading.Thread(target=try_commit_received) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only the first thread that holds the lock can transition; others see COMMIT_RECEIVED
        # and fail guard_commit_received (which only allows COMPUTING_MOVE or COMMIT_SENT).
        assert success_count == 1
        assert error_count == 4

    def test_lock_per_session_not_global(self):
        """Different game_ids get different locks — they do not block each other."""
        registry = SessionRegistry()
        entry_a = registry.get_or_create("game_a", 0, "cop")
        entry_b = registry.get_or_create("game_b", 0, "cop")
        assert entry_a.lock is not entry_b.lock


# ---------------------------------------------------------------------------
# Guard helpers
# ---------------------------------------------------------------------------


class TestGuardHelpers:
    def test_guard_commit_received_ok_in_computing_move(self):
        sm = fresh_sm()
        advance_to(
            sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY, ProtocolState.COMPUTING_MOVE
        )
        ok, err = sm.guard_commit_received()
        assert ok
        assert err is None

    def test_guard_commit_received_ok_after_commit_sent(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
        )
        ok, err = sm.guard_commit_received()
        assert ok

    def test_guard_commit_received_fail_in_both_committed(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
        )
        ok, _ = sm.guard_commit_received()
        assert not ok

    def test_guard_reveal_received_ok_in_both_committed(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
        )
        ok, err = sm.guard_reveal_received()
        assert ok
        assert err is None

    def test_guard_reveal_received_fail_in_computing_move(self):
        sm = fresh_sm()
        advance_to(
            sm, ProtocolState.STEP0_NEGOTIATING, ProtocolState.READY, ProtocolState.COMPUTING_MOVE
        )
        ok, _ = sm.guard_reveal_received()
        assert not ok

    def test_guard_final_audit_ok_in_auditing(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
            ProtocolState.BOTH_COMMITTED,
            ProtocolState.REVEAL_SENT,
            ProtocolState.STEP_VERIFIED,
            ProtocolState.AUDITING,
        )
        ok, _ = sm.guard_final_audit_received()
        assert ok


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_from_dict_round_trip(self):
        sm = fresh_sm()
        advance_to(
            sm,
            ProtocolState.STEP0_NEGOTIATING,
            ProtocolState.READY,
            ProtocolState.COMPUTING_MOVE,
            ProtocolState.COMMIT_SENT,
        )
        sm.advance_step()

        data = sm.to_dict()
        assert data["state"] == "commit_sent"
        assert data["step"] == 1

        sm2 = ProtocolStateMachine.from_dict(data)
        assert sm2.state == sm.state
        assert sm2.step == sm.step

    def test_all_states_serializable(self):
        for state in ProtocolState:
            sm = fresh_sm()
            sm.state = state
            data = sm.to_dict()
            sm2 = ProtocolStateMachine.from_dict(data)
            assert sm2.state == state
