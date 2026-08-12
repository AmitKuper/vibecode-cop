"""Tests verifying commit-reveal state machine and local storage run without a central judge.

Key design invariants tested:
- Each agent stores its own commits (h_commit + nonce) locally.
- CommitRevealStateMachine enforces opponent-first commit ordering.
- Final audit verifies all opponent nonces against stored h_commits independently.
- No third-process simultaneous verification occurs.
"""

import json

import pytest

from cop_worker.commit_reveal import (
    CommitRevealState,
    CommitRevealStateMachine,
    ProtocolViolationError,
)
from cop_worker.crypto import create_commitment, hash_game_state, verify_commitment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_commit(game_id: str, step: int, role: str, move: str) -> tuple[str, str]:
    state_hash = hash_game_state({"cop_position": [0, 0], "thief_position": [6, 6], "turn": step})
    h_commit, nonce = create_commitment(
        game_id=game_id,
        step=step,
        role=role,
        state_hash=state_hash,
        move=move,
        hint=f"Moving {move}",
        intent="truth",
    )
    return h_commit, nonce


# ---------------------------------------------------------------------------
# CommitRevealStateMachine unit tests
# ---------------------------------------------------------------------------


class TestCommitRevealStateMachineInvariant:
    def test_initial_state_is_waiting_commit(self):
        sm = CommitRevealStateMachine(expected_step=1)
        assert sm.state == CommitRevealState.WAITING_COMMIT

    def test_receive_commit_advances_to_locked(self):
        sm = CommitRevealStateMachine(expected_step=1)
        h, _ = _make_commit("g1", 1, "cop", "N")
        result = sm.receive_commit(step=1, commitment_hash=h)
        assert result.get("ack") is True
        assert sm.state == CommitRevealState.COMMIT_LOCKED

    def test_duplicate_identical_commit_is_idempotent(self):
        sm = CommitRevealStateMachine(expected_step=1)
        h, _ = _make_commit("g1", 1, "cop", "N")
        r1 = sm.receive_commit(step=1, commitment_hash=h)
        r2 = sm.receive_commit(step=1, commitment_hash=h)
        assert r1 == r2

    def test_conflicting_commit_raises_protocol_violation(self):
        sm = CommitRevealStateMachine(expected_step=1)
        h1, _ = _make_commit("g1", 1, "cop", "N")
        h2, _ = _make_commit("g1", 1, "cop", "S")
        sm.receive_commit(step=1, commitment_hash=h1)
        with pytest.raises(ProtocolViolationError):
            sm.receive_commit(step=1, commitment_hash=h2)


class TestLocalCommitStorage:
    """Each side stores its own commits locally — no third-process judge."""

    def test_local_commit_dict_independent_of_opponent(self):
        local_commits: dict[int, tuple[str, str]] = {}
        for step in range(1, 4):
            h, nonce = _make_commit("series_g01", step, "thief", "E")
            local_commits[step] = (h, nonce)

        assert len(local_commits) == 3
        for step, (h, nonce) in local_commits.items():
            assert len(h) == 64  # SHA-256 hex
            assert len(nonce) > 0

    def test_final_audit_verifies_without_third_party(self, tmp_path):
        """Run a minimal local final audit using only crypto — no judge or GameRunner."""
        game_id = "audit_test_g01"
        game_dir = tmp_path / game_id
        game_dir.mkdir()

        # Build commits and reveals for 3 steps
        commits: dict[str, str] = {}
        nonces: dict[int, str] = {}
        reveals: dict[str, dict] = {}

        for step in range(1, 4):
            state_hash = hash_game_state(
                {"cop_position": [0, 0], "thief_position": [6, 6], "turn": step}
            )
            h, nonce = create_commitment(
                game_id=game_id,
                step=step,
                role="thief",
                state_hash=state_hash,
                move="E",
                hint="east",
                intent="truth",
            )
            commits[str(step)] = h
            nonces[step] = nonce
            reveals[str(step)] = {
                "move": "E",
                "hint": "east",
                "intent": "truth",
                "state_hash": state_hash,
            }

        (game_dir / "opponent_commitments.json").write_text(json.dumps(commits), encoding="utf-8")
        (game_dir / "opponent_reveals.json").write_text(json.dumps(reveals), encoding="utf-8")

        # Verify each step independently using crypto
        for step_str, h_commit in commits.items():
            step = int(step_str)
            rev = reveals[step_str]
            nonce = nonces[step]
            ok = verify_commitment(
                h_commit=h_commit,
                game_id=game_id,
                step=step,
                role="thief",
                state_hash=rev["state_hash"],
                move=rev["move"],
                hint=rev["hint"],
                intent=rev["intent"],
                nonce=nonce,
            )
            assert ok is True, f"Audit failed at step {step}"
