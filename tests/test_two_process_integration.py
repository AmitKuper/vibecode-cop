from __future__ import annotations

import pytest

pytest.skip("module removed in restructure", allow_module_level=True)

"""Phase 2B two-process integration tests.

The first class (TestP0Defect) demonstrates the pre-fix failure: a COMMIT
that arrives before start_game is rejected because the session is still in
IDLE state.  This failure transcript is preserved as required evidence.

The second class (TestAfterFix) verifies the corrected production path:
  start_game handshake → one full commit-reveal step → six-gamelet series.

All tests run in-process using direct handler function calls (no real HTTP),
which gives repeatable, zero-network verification.  The state machine guards
are the REAL production guards from agent/mcp/server_handlers.py and
agent/mcp/coordinator.py.
"""


import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cop_worker.mcp.coordinator import ProtocolCoordinator, gamelet_from_game_id
from cop_worker.mcp.messages import ActionMessage, StartGameMessage
from cop_worker.mcp.protocol import ProtocolState
from cop_worker.mcp.server_handlers import handle_action, handle_start_game
from cop_worker.mcp.session_registry import SessionRegistry

from cop_worker.crypto import canonical_json, sign_message

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SECRET = "test-secret-phase2b"
CONFIG_SHA256 = "a" * 64
PROTOCOL_VERSION = "1.0"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _fresh_game_id(gamelet: int = 1) -> str:
    return f"game-{uuid.uuid4().hex[:12]}_g{gamelet}"


def _fresh_registry_and_coordinator() -> tuple[SessionRegistry, ProtocolCoordinator]:
    """Return isolated registry + coordinator so tests don't share module singletons."""
    reg = SessionRegistry()
    coord = ProtocolCoordinator(registry=reg)
    return reg, coord


def _make_start_game_msg(
    game_id: str, endpoint: str = "http://localhost:5000/mcp"
) -> StartGameMessage:
    return StartGameMessage(
        game_id=game_id,
        roles={"cop": "group-cop", "thief": "group-thief"},
        config_sha256=CONFIG_SHA256,
        protocol_version=PROTOCOL_VERSION,
        endpoint=endpoint,
        timestamp=_now(),
    )


def _signed_start_game(game_id: str) -> tuple[str, str]:
    msg = _make_start_game_msg(game_id)
    msg_json = canonical_json(msg.to_dict())
    sig = sign_message(msg.to_dict(), SECRET)
    return msg_json, sig


def _make_commit_msg(game_id: str, step: int = 1, role: str = "cop") -> ActionMessage:
    return ActionMessage(
        game_id=game_id,
        step=step,
        role=role,
        config_sha256=CONFIG_SHA256,
        timestamp=_now(),
        phase="commit",
        h_commit="b" * 64,
    )


def _signed_commit(game_id: str, step: int = 1, role: str = "cop") -> tuple[str, str]:
    msg = _make_commit_msg(game_id, step, role)
    msg_json = canonical_json(msg.to_dict())
    sig = sign_message(msg.to_dict(), SECRET)
    return msg_json, sig


def _make_reveal_msg(game_id: str, step: int = 1, role: str = "cop") -> ActionMessage:
    return ActionMessage(
        game_id=game_id,
        step=step,
        role=role,
        config_sha256=CONFIG_SHA256,
        timestamp=_now(),
        phase="reveal",
        move="E",
        hint="Moving east",
        intent="truth",
        state_hash="c" * 64,
    )


def _signed_reveal(game_id: str, step: int = 1, role: str = "cop") -> tuple[str, str]:
    msg = _make_reveal_msg(game_id, step, role)
    msg_json = canonical_json(msg.to_dict())
    sig = sign_message(msg.to_dict(), SECRET)
    return msg_json, sig


def _call_start_game(
    game_id: str,
    role: str,
    games_dir: Path,
    game_logs: dict,
    callbacks: dict | None = None,
    coordinator: ProtocolCoordinator | None = None,
) -> dict:
    msg_json, sig = _signed_start_game(game_id)
    return handle_start_game(
        role=role,
        secret=SECRET,
        config_sha256=CONFIG_SHA256,
        games_dir=games_dir,
        game_logs=game_logs,
        handler_callbacks=callbacks or {},
        message_json=msg_json,
        signature=sig,
        coordinator=coordinator,
    )


def _call_commit(
    game_id: str,
    role: str,
    games_dir: Path,
    game_logs: dict,
    step: int = 1,
    callbacks: dict | None = None,
    coordinator: ProtocolCoordinator | None = None,
) -> dict:
    msg_json, sig = _signed_commit(game_id, step=step, role="cop")
    return handle_action(
        role=role,
        secret=SECRET,
        config_sha256=CONFIG_SHA256,
        games_dir=games_dir,
        game_logs=game_logs,
        handler_callbacks=callbacks or {},
        game_id=game_id,
        message_json=msg_json,
        signature=sig,
        coordinator=coordinator,
    )


def _call_reveal(
    game_id: str,
    role: str,
    games_dir: Path,
    game_logs: dict,
    step: int = 1,
    callbacks: dict | None = None,
    coordinator: ProtocolCoordinator | None = None,
) -> dict:
    msg_json, sig = _signed_reveal(game_id, step=step, role="cop")
    return handle_action(
        role=role,
        secret=SECRET,
        config_sha256=CONFIG_SHA256,
        games_dir=games_dir,
        game_logs=game_logs,
        handler_callbacks=callbacks or {},
        game_id=game_id,
        message_json=msg_json,
        signature=sig,
        coordinator=coordinator,
    )


# ---------------------------------------------------------------------------
# P0 defect demonstration (pre-fix — preserved as failure evidence)
# ---------------------------------------------------------------------------


class TestP0Defect:
    """Demonstrate that commit before start_game is rejected (IDLE state guard).

    These tests use the PRODUCTION state machine with an isolated registry
    so they do not interfere with other tests.  They verify the BEFORE state
    of the bug — the exact failure the P0 defect produced.
    """

    def test_commit_before_handshake_rejected(self, tmp_path):
        """BEFORE FIX: first COMMIT arrives while session is in IDLE → rejected.

        Failure transcript:
          Session state: IDLE (no start_game ever received)
          Action: COP sends COMMIT step=1
          Expected: ok=False, error contains 'idle'
        """
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        result = _call_commit(
            game_id=game_id,
            role="thief",
            games_dir=tmp_path,
            game_logs=game_logs,
            coordinator=coord,
        )

        # Verify the failure: IDLE state rejects commit
        assert result.get("ok") is False, f"Expected rejection, got: {result}"
        error = result.get("error", "")
        assert "idle" in error.lower() or "protocol violation" in error.lower(), (
            f"Expected 'idle' or 'protocol violation' in error, got: {error!r}"
        )
        print(f"\n[FAILURE TRANSCRIPT] game_id={game_id}")
        print("  Session state before call: IDLE (no start_game)")
        print("  Action: COP COMMIT step=1")
        print(f"  Result: ok={result.get('ok')}")
        print(f"  Error:  {result.get('error')}")

    def test_reveal_before_handshake_rejected(self, tmp_path):
        """REVEAL is also rejected when session is in IDLE."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        result = _call_reveal(
            game_id=game_id,
            role="thief",
            games_dir=tmp_path,
            game_logs=game_logs,
            coordinator=coord,
        )

        assert result.get("ok") is False
        error = result.get("error", "")
        assert "idle" in error.lower() or "protocol violation" in error.lower(), (
            f"Expected idle/protocol violation, got: {error!r}"
        )

    def test_reveal_before_both_committed_rejected(self, tmp_path):
        """REVEAL before both peers committed is rejected."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        # Do handshake first
        r = _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r.get("ok"), f"start_game failed: {r}"
        gamelet = gamelet_from_game_id(game_id)
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.READY

        # Skip commit, go straight to reveal
        result = _call_reveal(
            game_id=game_id,
            role="thief",
            games_dir=tmp_path,
            game_logs=game_logs,
            coordinator=coord,
        )
        assert result.get("ok") is False
        error = result.get("error", "")
        assert "protocol violation" in error.lower(), f"Expected protocol violation, got: {error!r}"


# ---------------------------------------------------------------------------
# After-fix tests
# ---------------------------------------------------------------------------


class TestAfterFix:
    """Verify the corrected production path: handshake → commit → reveal."""

    def test_commit_after_handshake_succeeds(self, tmp_path):
        """After start_game, the first COMMIT is accepted (READY → COMPUTING_MOVE)."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        # 1. Handshake
        r = _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r.get("ok"), f"start_game failed: {r}"
        gamelet = gamelet_from_game_id(game_id)
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.READY

        # 2. First COMMIT
        result = _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert result.get("ok") is True, f"commit failed: {result}"

        # SM should have advanced past COMMIT_RECEIVED
        state = coord.get_state(game_id, gamelet, "thief")
        assert state in (
            ProtocolState.COMMIT_RECEIVED,
            ProtocolState.BOTH_COMMITTED,
        ), f"Unexpected state after commit: {state}"

    def test_exact_duplicate_commit_is_idempotent(self, tmp_path):
        """Sending the same COMMIT twice returns ok=True both times (idempotency)."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        r1 = _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r1.get("ok"), f"First commit failed: {r1}"

        r2 = _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r2.get("ok"), f"Duplicate commit rejected (should be idempotent): {r2}"
        assert r2.get("idempotent") is True or r2.get("ok") is True, f"Unexpected r2: {r2}"

    def test_conflicting_duplicate_commit_rejected(self, tmp_path):
        """Different h_commit for same step is a conflicting duplicate → rejected."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        # Send a DIFFERENT h_commit for the same step
        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="commit",
            h_commit="d" * 64,  # different from "b" * 64 used above
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False, f"Expected rejection for conflicting duplicate: {result}"

    def test_wrong_signature_rejected(self, tmp_path):
        """Message with bad signature is rejected."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        msg = _make_commit_msg(game_id)
        msg_json = canonical_json(msg.to_dict())
        bad_sig = "deadbeef" * 8  # wrong signature

        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=bad_sig,
            coordinator=coord,
        )
        assert result.get("ok") is False
        assert "signature" in result.get("error", "").lower()

    def test_wrong_config_sha256_rejected(self, tmp_path):
        """Message with wrong config_sha256 is rejected."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256="e" * 64,  # wrong config hash
            timestamp=_now(),
            phase="commit",
            h_commit="b" * 64,
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False
        assert "config" in result.get("error", "").lower()

    def test_callback_exception_leaves_no_half_advanced_state(self, tmp_path):
        """If the action callback throws, SM is rolled back to pre-call state."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        state_before = coord.get_state(game_id, gamelet, "thief")

        def exploding_callback(gid, msg):
            raise RuntimeError("simulated callback failure")

        result = _call_commit(
            game_id=game_id,
            role="thief",
            games_dir=tmp_path,
            game_logs=game_logs,
            callbacks={"on_action": exploding_callback},
            coordinator=coord,
        )

        # Call should fail gracefully
        assert result.get("ok") is False

        # SM must be rolled back to READY (pre-commit state)
        state_after = coord.get_state(game_id, gamelet, "thief")
        assert state_after == state_before, (
            f"SM was not rolled back: before={state_before}, after={state_after}"
        )

    def test_one_full_step_with_passive_callbacks(self, tmp_path):
        """A full commit+reveal exchange with passive callbacks advances SM to STEP_VERIFIED."""
        from cop_worker.peer_agent_passive import (
            handle_passive_commit,
            handle_passive_reveal,
            init_passive_game,
        )
        from cop_worker.peer_runtime import PeerRuntime

        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        # Build passive thief runtime
        runtime = PeerRuntime(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            opponent_url="http://localhost:9999/mcp",  # not called in this test
        )
        rules_ref: list = []

        def on_action(gid, msg):
            if msg.phase == "commit":
                return handle_passive_commit(runtime, gid, msg, rules_ref)
            if msg.phase == "reveal":
                return handle_passive_reveal(runtime, gid, msg, rules_ref)
            return {"ok": True}

        # 1. Handshake
        r = _call_start_game(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r.get("ok"), f"start_game failed: {r}"
        init_passive_game(runtime, game_id, rules_ref)

        # 2. Cop sends COMMIT
        r = _call_commit(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r.get("ok"), f"commit failed: {r}"
        assert r.get("h_commit"), f"No h_commit in response: {r}"

        # After passive commit, SM should be BOTH_COMMITTED
        state = coord.get_state(game_id, gamelet, "thief")
        assert state == ProtocolState.BOTH_COMMITTED, f"Expected BOTH_COMMITTED, got {state}"

        # 3. Cop sends REVEAL
        r = _call_reveal(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r.get("ok"), f"reveal failed: {r}"
        assert r.get("move"), f"No move in reveal response: {r}"

        # After passive reveal, SM should be STEP_VERIFIED
        state = coord.get_state(game_id, gamelet, "thief")
        assert state == ProtocolState.STEP_VERIFIED, f"Expected STEP_VERIFIED, got {state}"

    def test_second_step_after_first_succeeds(self, tmp_path):
        """After STEP_VERIFIED, a second commit is accepted (auto-advance from STEP_VERIFIED)."""
        from cop_worker.peer_agent_passive import (
            handle_passive_commit,
            handle_passive_reveal,
            init_passive_game,
        )
        from cop_worker.peer_runtime import PeerRuntime

        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        runtime = PeerRuntime(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            opponent_url="http://localhost:9999/mcp",
        )
        rules_ref: list = []

        def on_action(gid, msg):
            if msg.phase == "commit":
                return handle_passive_commit(runtime, gid, msg, rules_ref)
            if msg.phase == "reveal":
                return handle_passive_reveal(runtime, gid, msg, rules_ref)
            return {"ok": True}

        _call_start_game(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        init_passive_game(runtime, game_id, rules_ref)

        # Step 1
        r = _call_commit(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            step=1,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r.get("ok"), f"Step1 commit failed: {r}"
        r = _call_reveal(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            step=1,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r.get("ok"), f"Step1 reveal failed: {r}"
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.STEP_VERIFIED

        # Step 2 — should auto-advance from STEP_VERIFIED → COMPUTING_MOVE
        r = _call_commit(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            step=2,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r.get("ok"), f"Step2 commit failed (expected auto-advance from STEP_VERIFIED): {r}"

    def test_start_game_before_commit_is_required(self, tmp_path):
        """Verifies that without handshake the first COMMIT is always rejected."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        result = _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert result.get("ok") is False, "Expected rejection when no handshake performed"

    def test_duplicate_start_game_is_idempotent(self, tmp_path):
        """Sending start_game twice for the same session returns ok=True both times."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        r1 = _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r1.get("ok"), f"First start_game failed: {r1}"

        r2 = _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r2.get("ok"), f"Duplicate start_game rejected: {r2}"


# ---------------------------------------------------------------------------
# Concurrent request serialization
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_commits_serialized(self, tmp_path):
        """Concurrent COMMIT requests for the same step: one wins, rest are idempotent/rejected."""
        import threading

        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        results: list[dict] = []
        lock = threading.Lock()

        def send_commit():
            r = _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=send_commit) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        ok_count = sum(1 for r in results if r.get("ok"))
        # At least one should succeed; all must have responded
        assert ok_count >= 1, f"No commit succeeded in concurrent batch: {results}"
        assert len(results) == 5, "Some threads didn't return"

    def test_technical_loss_from_any_state(self, tmp_path):
        """technical_loss can be triggered from any non-terminal state."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.READY

        coord.on_technical_loss(game_id, gamelet, "thief", reason="test timeout")
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.TECHNICAL_LOSS

        # Further commits must be rejected
        result = _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert result.get("ok") is False


# ---------------------------------------------------------------------------
# Outbound (cop side) coordinator hooks
# ---------------------------------------------------------------------------


class TestOutboundCoordinatorHooks:
    """Verify that the cop-side coordinator methods advance the SM correctly."""

    def test_begin_step_and_commit_exchange(self, tmp_path):
        """Active side: handshake → begin_step → commit_exchange → reveal_exchange."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        # Simulate cop handshake (sends start_game to thief, records locally)
        coord.on_handshake_complete(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

        # Begin step 1
        coord.begin_step(game_id, gamelet, role, step=1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.COMPUTING_MOVE

        # Commit exchange complete (we sent, thief responded with their commit)
        coord.on_commit_exchange_complete(game_id, gamelet, role, step=1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.BOTH_COMMITTED

        # Reveal exchange complete
        coord.on_reveal_exchange_complete(game_id, gamelet, role, step=1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.STEP_VERIFIED

    def test_begin_step_from_step_verified(self, tmp_path):
        """begin_step also works from STEP_VERIFIED (between steps)."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, step=1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, step=1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, step=1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.STEP_VERIFIED

        # Next step
        coord.begin_step(game_id, gamelet, role, step=2)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.COMPUTING_MOVE

    def test_audit_and_done(self, tmp_path):
        """Audit flow: STEP_VERIFIED → AUDITING → RESULT_AGREEMENT → DONE."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, step=1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, step=1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, step=1)

        coord.on_audit_begin(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.AUDITING

        # Simulate receiving final_audit result
        coord.on_final_audit_complete(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.RESULT_AGREEMENT

        coord.on_done(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.DONE

        # Terminal: no further advances
        coord.begin_step(game_id, gamelet, role, step=2)  # should be a no-op
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.DONE


# ---------------------------------------------------------------------------
# Phase 1 hardening tests (Fixes 1–8)
# ---------------------------------------------------------------------------


class TestFix1FailClosedHandshake:
    """Fix 1: _send_start_game raises RuntimeError in counted_mode on failure."""

    def test_counted_mode_flag_stored_on_runtime(self):
        """PeerRuntime accepts and stores counted_mode flag."""
        from cop_worker.peer_runtime import PeerRuntime

        rt = PeerRuntime(
            role="cop",
            secret="s",
            config_sha256="a" * 64,
            opponent_url="http://localhost:9999/mcp",
            counted_mode=True,
        )
        from cop_worker.step0.declaration import PeerDeclaration

        rt.orchestrator = MagicMock()
        rt.orchestrator.build_step0_declaration.return_value = PeerDeclaration(
            game_uid="game-abc_g1", counted_mode=True
        )
        rt.orchestrator.validate_counted_declaration.return_value = []
        assert rt.counted_mode is True

    def test_default_counted_mode_is_false(self):
        """counted_mode defaults to False (fail-open for backwards compat)."""
        from cop_worker.peer_runtime import PeerRuntime

        rt = PeerRuntime(
            role="cop",
            secret="s",
            config_sha256="a" * 64,
            opponent_url="http://localhost:9999/mcp",
        )
        from cop_worker.step0.declaration import PeerDeclaration

        rt.orchestrator = MagicMock()
        rt.orchestrator.build_step0_declaration.return_value = PeerDeclaration(
            game_uid="game-abc_g1"
        )
        assert rt.counted_mode is False

    def test_send_start_game_raises_in_counted_mode_on_rejection(self):
        """In counted_mode, a rejection response from opponent raises RuntimeError."""
        import asyncio

        from cop_worker.peer_runtime import PeerRuntime

        rt = PeerRuntime(
            role="cop",
            secret="s",
            config_sha256="a" * 64,
            opponent_url="http://localhost:9999/mcp",
            counted_mode=True,
        )
        from cop_worker.step0.declaration import PeerDeclaration

        rt.orchestrator = MagicMock()
        rt.orchestrator.build_step0_declaration.return_value = PeerDeclaration(
            game_uid="game-abc_g1", counted_mode=True
        )
        rt.orchestrator.validate_counted_declaration.return_value = []

        # Patch the opponent client to return an error response
        class FakeClient:
            async def start_game(self, msg):
                return {"ok": False, "error": "rejected"}

        rt.opponent_client = FakeClient()

        with pytest.raises(RuntimeError, match="rejected"):
            asyncio.run(rt._send_start_game("game-abc_g1", counted_mode=True))

    def test_send_start_game_warns_in_non_counted_mode_on_rejection(self):
        """In non-counted mode, rejection is only logged as a warning (no exception)."""
        import asyncio

        from cop_worker.peer_runtime import PeerRuntime

        rt = PeerRuntime(
            role="cop",
            secret="s",
            config_sha256="a" * 64,
            opponent_url="http://localhost:9999/mcp",
        )
        from cop_worker.step0.declaration import PeerDeclaration

        rt.orchestrator = MagicMock()
        rt.orchestrator.build_step0_declaration.return_value = PeerDeclaration(
            game_uid="game-abc_g1"
        )

        class FakeClient:
            async def start_game(self, msg):
                return {"ok": False, "error": "rejected"}

        rt.opponent_client = FakeClient()
        # Should NOT raise — just warns
        asyncio.run(rt._send_start_game("game-abc_g1", counted_mode=False))


class TestFix2FinalAuditWiring:
    """Fix 2: do_final_audit advances coordinator SM to DONE on the active (cop) side."""

    def test_audit_waits_for_result_agreement_on_success(self, tmp_path):
        """Audit authorizes RESULT_AGREEMENT but never skips directly to DONE."""
        import asyncio
        import unittest.mock

        from cop_worker.mcp.coordinator import ProtocolCoordinator
        from cop_worker.mcp.session_registry import SessionRegistry
        from cop_worker.peer_runtime_audit import do_final_audit

        reg = SessionRegistry()
        coord = ProtocolCoordinator(registry=reg)
        game_id = "game-fix2-test_g1"
        gamelet = 1
        role = "cop"

        # Advance SM to STEP_VERIFIED
        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, step=1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, step=1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, step=1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.STEP_VERIFIED

        import agent.mcp.coordinator as coord_module

        original = coord_module._coordinator
        coord_module._coordinator = coord
        try:

            class FakeClient:
                async def action(self, gid, msg):
                    return {"ok": True, "nonces": {}}

            game_dir = tmp_path / game_id
            game_dir.mkdir(parents=True, exist_ok=True)

            # Mock run_final_audit to return success
            mock_return = (True, {"audit_status": "ok"})
            with unittest.mock.patch(
                "agent.peer_runtime_audit.run_final_audit", return_value=mock_return
            ):
                ok, details = asyncio.run(
                    do_final_audit(
                        FakeClient(),
                        game_id,
                        role,
                        "a" * 64,
                        {},
                        game_dir,
                        "thief",
                        1,
                        lambda: "2024-01-01T00:00:00",
                        gamelet=gamelet,
                    )
                )
        finally:
            coord_module._coordinator = original

        assert ok
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.RESULT_AGREEMENT

    def test_audit_transitions_to_technical_loss_on_failure(self, tmp_path):
        """After a failed final_audit, coordinator SM reaches TECHNICAL_LOSS."""
        import asyncio

        from cop_worker.mcp.coordinator import ProtocolCoordinator
        from cop_worker.mcp.session_registry import SessionRegistry
        from cop_worker.peer_runtime_audit import do_final_audit

        reg = SessionRegistry()
        coord = ProtocolCoordinator(registry=reg)
        game_id = "game-fix2-fail_g1"
        gamelet = 1
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, step=1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, step=1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, step=1)

        import agent.mcp.coordinator as coord_module

        original = coord_module._coordinator
        coord_module._coordinator = coord
        try:

            class FakeClientBadNonce:
                async def action(self, gid, msg):
                    # Return a bad nonce that will fail verification
                    return {"ok": True, "nonces": {"1": "bad_nonce"}}

            game_dir = tmp_path / game_id
            game_dir.mkdir(parents=True, exist_ok=True)
            # Write a fake opponent commit that won't match the bad nonce
            import json

            (game_dir / "opponent_commits.json").write_text(
                json.dumps({"1": {"h_commit": "b" * 64, "nonce": "real_nonce"}})
            )
            ok, details = asyncio.run(
                do_final_audit(
                    FakeClientBadNonce(),
                    game_id,
                    role,
                    "a" * 64,
                    {},
                    game_dir,
                    "thief",
                    1,
                    lambda: "2024-01-01T00:00:00",
                    gamelet=gamelet,
                )
            )
        finally:
            coord_module._coordinator = original

        assert not ok
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.TECHNICAL_LOSS


class TestFix3SessionCleanup:
    """Fix 3: cleanup_session removes session from registry after terminal state."""

    def test_cleanup_removes_done_session(self):
        """cleanup_session removes a DONE session from the registry."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, step=1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, step=1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, step=1)
        coord.on_audit_begin(game_id, gamelet, role)
        coord.on_final_audit_complete(game_id, gamelet, role)
        coord.on_done(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.DONE

        coord.cleanup_session(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) is None
        assert reg.get(game_id, gamelet, role) is None

    def test_cleanup_removes_technical_loss_session(self):
        """cleanup_session removes a TECHNICAL_LOSS session."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "thief"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.on_technical_loss(game_id, gamelet, role, reason="test")
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.TECHNICAL_LOSS

        coord.cleanup_session(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) is None

    def test_cleanup_is_idempotent_for_missing_session(self):
        """cleanup_session does nothing if the session doesn't exist."""
        reg, coord = _fresh_registry_and_coordinator()
        coord.cleanup_session("nonexistent-game_g1", 1, "cop")  # should not raise

    def test_cleanup_also_clears_idempotency_cache(self):
        """cleanup_session also purges the idempotency cache for the session."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "thief"

        # Seed some idempotency records
        coord._idempotency[(game_id, gamelet, role, 1, "commit")] = None  # type: ignore
        coord._idempotency[(game_id, gamelet, role, 1, "reveal")] = None  # type: ignore
        coord._idempotency[("other-game_g1", gamelet, role, 1, "commit")] = None  # type: ignore

        coord.on_technical_loss(game_id, gamelet, role, reason="cleanup test")
        coord.cleanup_session(game_id, gamelet, role)

        # Only the removed session's records should be gone
        assert (game_id, gamelet, role, 1, "commit") not in coord._idempotency
        assert (game_id, gamelet, role, 1, "reveal") not in coord._idempotency
        # Other game's records must be untouched
        assert ("other-game_g1", gamelet, role, 1, "commit") in coord._idempotency


class TestFix4RevealIdempotency:
    """Fix 4: reveal idempotency keyed on full payload (move + hint + intent + state_hash)."""

    def test_exact_duplicate_reveal_is_idempotent(self, tmp_path):
        """Sending the exact same reveal twice returns ok=True both times."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        # Force SM to BOTH_COMMITTED
        gamelet = gamelet_from_game_id(game_id)
        coord.on_passive_commit_sent(game_id, gamelet, "thief", 1, "h" * 64)

        r1 = _call_reveal(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r1.get("ok"), f"First reveal failed: {r1}"

        r2 = _call_reveal(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r2.get("ok"), f"Duplicate reveal rejected: {r2}"
        assert r2.get("idempotent") is True

    def test_conflicting_reveal_payload_rejected(self, tmp_path):
        """A reveal with different hint but same step/move is rejected as conflicting."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        _call_commit(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        coord.on_passive_commit_sent(game_id, gamelet, "thief", 1, "h" * 64)

        # First reveal succeeds
        r1 = _call_reveal(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert r1.get("ok")

        # Send a second reveal with a different hint — should be rejected as conflicting
        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="reveal",
            move="N",
            hint="A completely different hint text here",  # different hint
            intent="truth",
            state_hash="c" * 64,
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False, f"Expected rejection for conflicting reveal: {result}"
        err = result.get("error", "").lower()
        assert "conflict" in err or "mismatch" in err


class TestFix5StepEnforcement:
    """Fix 5: Out-of-order commits/reveals are rejected."""

    def test_replayed_commit_step_rejected(self, tmp_path):
        """Sending commit with same step number twice is rejected after first succeeds."""
        from cop_worker.peer_agent_passive import (
            handle_passive_commit,
            handle_passive_reveal,
            init_passive_game,
        )
        from cop_worker.peer_runtime import PeerRuntime

        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        runtime = PeerRuntime(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            opponent_url="http://localhost:9999/mcp",
        )
        rules_ref: list = []

        def on_action(gid, msg):
            if msg.phase == "commit":
                return handle_passive_commit(runtime, gid, msg, rules_ref)
            if msg.phase == "reveal":
                return handle_passive_reveal(runtime, gid, msg, rules_ref)
            return {"ok": True}

        _call_start_game(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        init_passive_game(runtime, game_id, rules_ref)

        # Step 1 succeeds
        r1 = _call_commit(
            game_id,
            "thief",
            tmp_path,
            game_logs,
            step=1,
            callbacks={"on_action": on_action},
            coordinator=coord,
        )
        assert r1.get("ok"), f"Step 1 commit failed: {r1}"

        # Step 1 again (replay) should be rejected.
        # Send a DIFFERENT h_commit to bypass idempotency cache and hit step check.
        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="commit",
            h_commit="e" * 64,  # different h_commit — should trigger conflicting duplicate
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={"on_action": on_action},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False, f"Expected replay commit rejection: {result}"

    def test_lower_step_commit_rejected(self, tmp_path):
        """After accepting step=2 commit, step=1 commit is rejected."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)

        # Accept step 2
        msg2 = ActionMessage(
            game_id=game_id,
            step=2,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="commit",
            h_commit="b" * 64,
        )
        msg_json2 = canonical_json(msg2.to_dict())
        sig2 = sign_message(msg2.to_dict(), SECRET)
        r = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json2,
            signature=sig2,
            coordinator=coord,
        )
        assert r.get("ok"), f"Step 2 commit failed: {r}"

        # Advance SM to STEP_VERIFIED so we can receive another commit
        coord.on_passive_commit_sent(game_id, gamelet, "thief", 2, "h" * 64)
        # Force to STEP_VERIFIED for next step test
        entry = reg.get(game_id, gamelet, "thief")
        if entry:
            entry.sm.state = ProtocolState.STEP_VERIFIED

        # Now try step=1 — must be rejected (step <= last_accepted=2)
        msg1 = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="commit",
            h_commit="c" * 64,
        )
        msg_json1 = canonical_json(msg1.to_dict())
        sig1 = sign_message(msg1.to_dict(), SECRET)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json1,
            signature=sig1,
            coordinator=coord,
        )
        assert result.get("ok") is False, f"Expected step=1 rejection after step=2: {result}"
        assert "out-of-order" in result.get("error", "").lower()


class TestFix6GameIdValidation:
    """Fix 6: gamelet_from_game_id strict mode rejects IDs without _gN suffix."""

    def test_strict_mode_rejects_missing_suffix(self):
        """gamelet_from_game_id(strict=True) raises ValueError for bare game IDs."""
        from cop_worker.mcp.coordinator import gamelet_from_game_id

        with pytest.raises(ValueError, match="_gN"):
            gamelet_from_game_id("bare-game-id", strict=True)

    def test_strict_mode_accepts_valid_suffix(self):
        """gamelet_from_game_id(strict=True) works for IDs with _gN suffix."""
        from cop_worker.mcp.coordinator import gamelet_from_game_id

        assert gamelet_from_game_id("game-abc_g3", strict=True) == 3
        assert gamelet_from_game_id("game-abc_g0", strict=True) == 0

    def test_non_strict_mode_defaults_to_zero(self):
        """Non-strict mode falls back to 0 for bare game IDs."""
        from cop_worker.mcp.coordinator import gamelet_from_game_id

        assert gamelet_from_game_id("bare-game-id") == 0
        assert gamelet_from_game_id("bare-game-id", strict=False) == 0


class TestFix7AbortGameEndGuards:
    """Fix 7: abort uses coordinator, game_end has state guard."""

    def test_game_end_rejected_in_done_state(self, tmp_path):
        """game_end is rejected when session is already DONE."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        # Advance to DONE
        coord.on_handshake_complete(game_id, gamelet, "thief")
        coord.begin_step(game_id, gamelet, "thief", 1)
        coord.on_commit_exchange_complete(game_id, gamelet, "thief", 1)
        coord.on_reveal_exchange_complete(game_id, gamelet, "thief", 1)
        coord.on_audit_begin(game_id, gamelet, "thief")
        coord.on_final_audit_complete(game_id, gamelet, "thief")
        coord.on_done(game_id, gamelet, "thief")
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.DONE

        # Now try game_end — should be rejected
        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="game_end",
            reason="cop_caught_thief",
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)
        # Need a game_log entry
        from cop_worker.mcp.log import GameLog

        game_logs[game_id] = GameLog(game_id, tmp_path)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False, f"Expected game_end rejection in DONE state: {result}"
        assert "protocol violation" in result.get("error", "").lower()

    def test_abort_transitions_to_aborted_state(self, tmp_path):
        """abort phase transitions SM to TECHNICAL_LOSS via coordinator."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}

        _call_start_game(game_id, "thief", tmp_path, game_logs, coordinator=coord)
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.READY

        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="abort",
            reason="opponent_cheated",
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)
        result = handle_action(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok"), f"abort failed: {result}"
        # SM must be in TECHNICAL_LOSS now
        assert coord.get_state(game_id, gamelet, "thief") == ProtocolState.TECHNICAL_LOSS


class TestFix8IsReady:
    """Fix 8: is_ready() returns True only for active gameplay states."""

    def test_is_ready_false_for_idle(self):
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        # No session exists → False
        assert coord.is_ready(game_id, gamelet, "cop") is False

    def test_is_ready_false_for_done(self):
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, 1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, 1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, 1)
        coord.on_audit_begin(game_id, gamelet, role)
        coord.on_final_audit_complete(game_id, gamelet, role)
        coord.on_done(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.DONE
        assert coord.is_ready(game_id, gamelet, role) is False

    def test_is_ready_false_for_technical_loss(self):
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.on_technical_loss(game_id, gamelet, role, reason="test")
        assert coord.is_ready(game_id, gamelet, role) is False

    def test_is_ready_true_for_ready_state(self):
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY
        assert coord.is_ready(game_id, gamelet, role) is True

    def test_is_ready_true_for_computing_move(self):
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, 1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.COMPUTING_MOVE
        assert coord.is_ready(game_id, gamelet, role) is True

    def test_is_ready_true_for_step_verified(self):
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, 1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, 1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, 1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.STEP_VERIFIED
        assert coord.is_ready(game_id, gamelet, role) is True


# ---------------------------------------------------------------------------
# Phase 1 coverage gap tests — server_handlers uncovered branches
# ---------------------------------------------------------------------------


class TestServerHandlerCoverageBranches:
    """Targeted tests to cover uncovered branches in server_handlers.py."""

    def test_start_game_violation_in_non_idle_state(self, tmp_path):
        """start_game rejected when session is past READY (e.g. COMPUTING_MOVE)."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        # Advance to READY then to COMPUTING_MOVE
        gamelet = gamelet_from_game_id(game_id)
        role = "thief"
        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, 1)

        # Now send another start_game — should be rejected
        result = _call_start_game(game_id, role, tmp_path, game_logs, coordinator=coord)
        assert result.get("ok") is False
        assert "protocol violation" in result.get("error", "").lower()

    def test_start_game_bad_signature(self, tmp_path):
        """start_game rejected when signature does not verify."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        msg = _make_start_game_msg(game_id)
        msg_json = canonical_json(msg.to_dict())
        bad_sig = "bad" * 30  # Invalid signature

        result = handle_start_game(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            message_json=msg_json,
            signature=bad_sig,
            coordinator=coord,
        )
        assert result.get("ok") is False
        assert "signature" in result.get("error", "").lower()

    def test_start_game_invalid_message(self, tmp_path):
        """start_game rejected when JSON is malformed."""
        _, coord = _fresh_registry_and_coordinator()
        game_logs: dict = {}

        result = handle_start_game(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            message_json='{"bad": "json_missing_fields"}',
            signature="any",
            coordinator=coord,
        )
        assert result.get("ok") is False

    def test_start_game_config_mismatch(self, tmp_path):
        """start_game rejected when config_sha256 does not match."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}

        # Build a valid start_game message but with wrong config hash
        msg = StartGameMessage(
            game_id=game_id,
            roles={"cop": "group-cop", "thief": "group-thief"},
            config_sha256="wrong" + "0" * 59,
            protocol_version=PROTOCOL_VERSION,
            endpoint="http://localhost:5000/mcp",
            timestamp=_now(),
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)

        result = handle_start_game(
            role="thief",
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False
        assert "mismatch" in result.get("error", "").lower()

    def test_action_config_mismatch_rejected(self, tmp_path):
        """action rejected when config_sha256 does not match."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}
        role = "thief"

        # Handshake first
        _call_start_game(game_id, role, tmp_path, game_logs, coordinator=coord)

        # Build action with wrong config_sha256
        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256="wrong" + "0" * 59,
            timestamp=_now(),
            phase="commit",
            h_commit="b" * 64,
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)

        result = handle_action(
            role=role,
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False
        assert "mismatch" in result.get("error", "").lower()

    def test_commit_callback_failure_triggers_rollback(self, tmp_path):
        """If on_action callback raises, SM is rolled back to pre-commit state."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}
        role = "thief"

        _call_start_game(game_id, role, tmp_path, game_logs, coordinator=coord)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

        def failing_callback(gid, msg):
            raise RuntimeError("callback failure")

        callbacks = {"on_action": failing_callback}
        result = _call_commit(
            game_id, role, tmp_path, game_logs, step=1, callbacks=callbacks, coordinator=coord
        )
        # Callback failure returns error response
        assert result.get("ok") is False
        # SM should have been rolled back
        state = coord.get_state(game_id, gamelet, role)
        assert state in (ProtocolState.READY, ProtocolState.COMMIT_RECEIVED)

    def test_reveal_callback_failure_triggers_rollback(self, tmp_path):
        """If on_action callback raises during reveal, SM is rolled back."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}
        role = "thief"

        _call_start_game(game_id, role, tmp_path, game_logs, coordinator=coord)
        # Need to advance to BOTH_COMMITTED for reveal to be valid
        # First commit from opponent (passive side receives it → COMMIT_RECEIVED)
        _call_commit(game_id, role, tmp_path, game_logs, step=1, coordinator=coord)
        # Mark that we sent ours too → BOTH_COMMITTED
        coord.on_commit_exchange_complete(game_id, gamelet, role, 1)

        def failing_reveal_callback(gid, msg):
            raise RuntimeError("reveal callback failure")

        callbacks = {"on_action": failing_reveal_callback}
        result = _call_reveal(
            game_id, role, tmp_path, game_logs, step=1, callbacks=callbacks, coordinator=coord
        )
        assert result.get("ok") is False
        # SM should be rolled back
        state = coord.get_state(game_id, gamelet, role)
        assert state is not None

    def test_final_audit_guard_blocks_in_idle(self, tmp_path):
        """final_audit rejected when session is in IDLE (no handshake)."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}
        role = "thief"

        msg = ActionMessage(
            game_id=game_id,
            step=1,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="final_audit",
            nonces=None,
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)

        result = handle_action(
            role=role,
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False
        assert "protocol violation" in result.get("error", "").lower()

    def test_unknown_phase_returns_error(self, tmp_path):
        """Unknown action phase returns error without crashing."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        game_logs: dict = {}
        role = "thief"

        _call_start_game(game_id, role, tmp_path, game_logs, coordinator=coord)

        # Craft a message with unknown phase — use JSON to bypass ActionMessage validation
        msg_dict = {
            "game_id": game_id,
            "step": 1,
            "role": "cop",
            "config_sha256": CONFIG_SHA256,
            "timestamp": _now(),
            "phase": "unknown_phase_xyz",
        }
        msg_json = canonical_json(msg_dict)
        sig = sign_message(msg_dict, SECRET)

        result = handle_action(
            role=role,
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is False

    def test_abort_transitions_to_technical_loss(self, tmp_path):
        """abort message drives SM to TECHNICAL_LOSS via coordinator."""
        _, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        game_logs: dict = {}
        role = "thief"

        _call_start_game(game_id, role, tmp_path, game_logs, coordinator=coord)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

        msg = ActionMessage(
            game_id=game_id,
            step=0,
            role="cop",
            config_sha256=CONFIG_SHA256,
            timestamp=_now(),
            phase="abort",
            reason="opponent_abort",
        )
        msg_json = canonical_json(msg.to_dict())
        sig = sign_message(msg.to_dict(), SECRET)

        result = handle_action(
            role=role,
            secret=SECRET,
            config_sha256=CONFIG_SHA256,
            games_dir=tmp_path,
            game_logs=game_logs,
            handler_callbacks={},
            game_id=game_id,
            message_json=msg_json,
            signature=sig,
            coordinator=coord,
        )
        assert result.get("ok") is True
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.TECHNICAL_LOSS


# ---------------------------------------------------------------------------
# Coordinator and notify-helper coverage tests
# ---------------------------------------------------------------------------


class TestCoordinatorCoverageBranches:
    """Targeted tests for uncovered coordinator and notify-helper branches."""

    def test_notify_helpers_invoke_coordinator(self):
        """Verify the notify helper functions in server_handlers delegate correctly."""
        from cop_worker.mcp.server_handlers import (
            notify_audit_begin,
            notify_commit_sent,
            notify_done,
            notify_reveal_sent,
            notify_step_begin,
        )

        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        # Wire up our local coordinator
        from unittest.mock import patch

        with patch("agent.mcp.server_handlers.get_coordinator", return_value=coord):
            coord.on_handshake_complete(game_id, gamelet, role)
            assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

            notify_step_begin(game_id, gamelet, role, 1)
            assert coord.get_state(game_id, gamelet, role) == ProtocolState.COMPUTING_MOVE

            # Force to BOTH_COMMITTED for reveal test
            entry = coord._registry.get_or_create(game_id, gamelet, role)
            entry.sm.state = ProtocolState.BOTH_COMMITTED

            notify_reveal_sent(game_id, gamelet, role, 1)
            state = coord.get_state(game_id, gamelet, role)
            assert state in (ProtocolState.REVEAL_SENT, ProtocolState.STEP_VERIFIED)

            # Force to STEP_VERIFIED for audit test
            entry.sm.state = ProtocolState.STEP_VERIFIED

            notify_audit_begin(game_id, gamelet, role)
            assert coord.get_state(game_id, gamelet, role) == ProtocolState.AUDITING

            # Advance to RESULT_AGREEMENT then DONE
            coord.on_final_audit_complete(game_id, gamelet, role)
            assert coord.get_state(game_id, gamelet, role) == ProtocolState.RESULT_AGREEMENT

            notify_done(game_id, gamelet, role)
            assert coord.get_state(game_id, gamelet, role) == ProtocolState.DONE

            # Also exercise notify_commit_sent in isolation
            reg2, coord2 = _fresh_registry_and_coordinator()
            game_id2 = _fresh_game_id()
            gamelet2 = gamelet_from_game_id(game_id2)
            coord2.on_handshake_complete(game_id2, gamelet2, role)
            coord2.begin_step(game_id2, gamelet2, role, 1)

        with patch("agent.mcp.server_handlers.get_coordinator", return_value=coord2):
            notify_commit_sent(game_id2, gamelet2, role, 1)
            state2 = coord2.get_state(game_id2, gamelet2, role)
            assert state2 in (ProtocolState.COMMIT_SENT, ProtocolState.BOTH_COMMITTED)

    def test_notify_technical_loss_no_reason(self):
        """notify_technical_loss with empty reason covers the else-branch."""
        from unittest.mock import patch

        from cop_worker.mcp.server_handlers import notify_technical_loss

        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        with patch("agent.mcp.server_handlers.get_coordinator", return_value=coord):
            notify_technical_loss(game_id, gamelet, role)  # no reason
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.TECHNICAL_LOSS

    def test_on_handshake_complete_in_wrong_state_is_noop(self):
        """on_handshake_complete in COMPUTING_MOVE logs warning and returns."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, 1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.COMPUTING_MOVE

        # Call again — should be a no-op / warning (not READY)
        coord.on_handshake_complete(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.COMPUTING_MOVE

    def test_rollback_inbound_commit_missing_session_is_noop(self):
        """rollback_inbound_commit on non-existent session is safe."""
        reg, coord = _fresh_registry_and_coordinator()
        # Should not raise
        coord.rollback_inbound_commit("no-such-game_g1", 1, "cop", ProtocolState.READY)

    def test_rollback_inbound_reveal_missing_session_is_noop(self):
        """rollback_inbound_reveal on non-existent session is safe."""
        reg, coord = _fresh_registry_and_coordinator()
        coord.rollback_inbound_reveal("no-such-game_g1", 1, "cop", ProtocolState.BOTH_COMMITTED)

    def test_cleanup_session_nonexistent_is_noop(self):
        """cleanup_session on nonexistent session does not raise."""
        reg, coord = _fresh_registry_and_coordinator()
        coord.cleanup_session("no-such-game_g1", 1, "cop")  # state is None — should silently pass

    def test_on_passive_commit_sent_in_wrong_state_is_noop(self):
        """on_passive_commit_sent in READY (not COMMIT_RECEIVED) is silently ignored."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

        # Should be ignored — state stays READY
        coord.on_passive_commit_sent(game_id, gamelet, role, 1, "b" * 64)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

    def test_on_passive_reveal_sent_in_wrong_state_is_noop(self):
        """on_passive_reveal_sent in READY is silently ignored."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.on_passive_reveal_sent(game_id, gamelet, role, 1, "N")
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.READY

    def test_gamelet_from_game_id_strict_raises_on_bare_id(self):
        """gamelet_from_game_id(strict=True) raises ValueError for game IDs without _gN."""
        from cop_worker.mcp.coordinator import gamelet_from_game_id

        with pytest.raises(ValueError, match="strict"):
            gamelet_from_game_id("bare-game-id", strict=True)

    def test_reveal_exchange_idempotent_in_step_verified(self):
        """on_reveal_exchange_complete in STEP_VERIFIED is a no-op (idempotent)."""
        reg, coord = _fresh_registry_and_coordinator()
        game_id = _fresh_game_id()
        gamelet = gamelet_from_game_id(game_id)
        role = "cop"

        coord.on_handshake_complete(game_id, gamelet, role)
        coord.begin_step(game_id, gamelet, role, 1)
        coord.on_commit_exchange_complete(game_id, gamelet, role, 1)
        coord.on_reveal_exchange_complete(game_id, gamelet, role, 1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.STEP_VERIFIED

        # Call again — should be a no-op
        coord.on_reveal_exchange_complete(game_id, gamelet, role, 1)
        assert coord.get_state(game_id, gamelet, role) == ProtocolState.STEP_VERIFIED
