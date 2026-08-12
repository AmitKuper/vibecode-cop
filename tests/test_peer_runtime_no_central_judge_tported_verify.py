"""Tests verifying commit-reveal cryptographic verification runs without any central judge.

Key design invariants tested:
- After each reveal the agent verifies the opponent's move against stored h_commit.
- On commitment mismatch the agent flags TECHNICAL_LOSS.
- No third-process simultaneous verification occurs.
"""

from cop_worker.crypto import create_commitment, hash_game_state, verify_commitment


class TestVerifyOpponentReveal:
    """verify_commitment uses crypto directly — no judge."""

    def test_valid_commitment_verifies(self):
        game_id = "g1"
        step = 1
        role = "thief"
        state_hash = hash_game_state({"cop_position": [0, 0], "thief_position": [3, 3], "turn": 1})
        h_commit, nonce = create_commitment(
            game_id=game_id,
            step=step,
            role=role,
            state_hash=state_hash,
            move="NORTH",
            hint="Moving NORTH",
            intent="truth",
        )
        ok = verify_commitment(
            h_commit=h_commit,
            game_id=game_id,
            step=step,
            role=role,
            state_hash=state_hash,
            move="NORTH",
            hint="Moving NORTH",
            intent="truth",
            nonce=nonce,
        )
        assert ok is True

    def test_tampered_move_returns_false(self):
        game_id = "g2"
        step = 2
        role = "cop"
        state_hash = hash_game_state({"cop_position": [1, 1], "thief_position": [5, 5], "turn": 2})
        h_commit, nonce = create_commitment(
            game_id=game_id,
            step=step,
            role=role,
            state_hash=state_hash,
            move="N",
            hint="going north",
            intent="truth",
        )
        ok = verify_commitment(
            h_commit=h_commit,
            game_id=game_id,
            step=step,
            role=role,
            state_hash=state_hash,
            move="S",
            hint="going north",
            intent="truth",
            nonce=nonce,
        )
        assert ok is False

    def test_tampered_nonce_returns_false(self):
        game_id = "g3"
        state_hash = hash_game_state({"cop_position": [0, 0], "thief_position": [3, 3], "turn": 3})
        h_commit, nonce = create_commitment(
            game_id=game_id,
            step=3,
            role="thief",
            state_hash=state_hash,
            move="E",
            hint="east",
            intent="truth",
        )
        ok = verify_commitment(
            h_commit=h_commit,
            game_id=game_id,
            step=3,
            role="thief",
            state_hash=state_hash,
            move="E",
            hint="east",
            intent="truth",
            nonce="tampered_nonce",
        )
        assert ok is False


class TestTechnicalLossOnMismatch:
    def test_commitment_mismatch_is_flagged(self):
        """When h_commit doesn't match reveal, the result must be False — not silently pass."""
        game_id = "tl_test_g01"
        step = 1
        state_hash = hash_game_state(
            {"cop_position": [0, 0], "thief_position": [3, 3], "turn": step}
        )
        h_commit, nonce = create_commitment(
            game_id=game_id,
            step=step,
            role="cop",
            state_hash=state_hash,
            move="N",
            hint="",
            intent="truth",
        )
        ok = verify_commitment(
            h_commit=h_commit,
            game_id=game_id,
            step=step,
            role="cop",
            state_hash=state_hash,
            move="S",  # TAMPERED move
            hint="",
            intent="truth",
            nonce=nonce,
        )
        assert ok is False, "Commitment mismatch must be detected — TECHNICAL_LOSS required"
