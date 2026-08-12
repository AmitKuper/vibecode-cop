"""Adversarial protocol state machine tests — concurrency safety.

Verifies the 16-state machine rejects illegal orderings, duplicates,
and race conditions while accepting the valid happy path.
"""

from __future__ import annotations

import threading

from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.session_registry import SessionEntry, SessionRegistry

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
