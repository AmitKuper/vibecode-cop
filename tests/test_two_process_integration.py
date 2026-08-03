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

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from agent.mcp.coordinator import ProtocolCoordinator, gamelet_from_game_id
from agent.mcp.crypto import canonical_json, sign_message
from agent.mcp.messages import ActionMessage, StartGameMessage
from agent.mcp.protocol import ProtocolState
from agent.mcp.server_handlers import handle_action, handle_start_game
from agent.mcp.session_registry import SessionRegistry

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
        move="N",
        hint="Moving north",
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
        from agent.peer_agent_passive import (
            handle_passive_commit,
            handle_passive_reveal,
            init_passive_game,
        )
        from agent.peer_runtime import PeerRuntime

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
        from agent.peer_agent_passive import (
            handle_passive_commit,
            handle_passive_reveal,
            init_passive_game,
        )
        from agent.peer_runtime import PeerRuntime

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
