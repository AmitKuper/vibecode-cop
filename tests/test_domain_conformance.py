"""Phase 1 cross-repository domain conformance tests.

These tests verify that apply_joint_action() produces correct TransitionResults
for the shared fixture vectors in tests/fixtures/transcript_vectors.json.
Both repositories (cop and thief) must pass identically.

Also tests:
  - Strict Board.from_dict() validation (no silent defaults)
  - Config validator against Appendix-F constraints
  - DomainState schema validation
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.board import Board
from agent.domain.config_validator import GameConfig, validate_game_config
from agent.domain.transition import apply_joint_action
from agent.domain.types import DomainState
from agent.rules_outcomes import GameOutcome

_VECTORS_PATH = Path(__file__).parent / "fixtures" / "transcript_vectors.json"
_CONFIG_PATH = Path(__file__).parent.parent / "config" / "game.json"


def _load_vectors() -> list[dict]:
    return json.loads(_VECTORS_PATH.read_text(encoding="utf-8"))["vectors"]


def _make_state(v: dict) -> DomainState:
    s = v["state"]
    return DomainState(
        turn=s["turn"],
        grid_size=s["grid_size"],
        cop_position=tuple(s["cop_position"]),
        thief_position=tuple(s["thief_position"]),
        barriers=[tuple(b) for b in s["barriers"]],
        cop_barriers_remaining=s["cop_barriers_remaining"],
        scent_grid=s.get("scent_grid", []),
    )


# ---------------------------------------------------------------------------
# 1. Cross-repository transcript conformance vectors
# ---------------------------------------------------------------------------


class TestTranscriptConformance:
    @pytest.mark.parametrize("vector", _load_vectors(), ids=[v["id"] for v in _load_vectors()])
    def test_vector(self, vector: dict):
        """Each vector must produce the expected TransitionResult."""
        state = _make_state(vector)
        result = apply_joint_action(state, vector["cop_action"], vector["thief_action"])
        exp = vector["expected"]

        assert result.outcome == GameOutcome(exp["outcome"]), (
            f"[{vector['id']}] outcome: got {result.outcome}, expected {exp['outcome']}"
        )
        assert result.cop_action_legal == exp["cop_action_legal"], (
            f"[{vector['id']}] cop_action_legal mismatch"
        )
        assert result.thief_action_legal == exp["thief_action_legal"], (
            f"[{vector['id']}] thief_action_legal mismatch"
        )
        assert result.barrier_placed == exp["barrier_placed"], (
            f"[{vector['id']}] barrier_placed mismatch"
        )
        assert result.capture == exp["capture"], f"[{vector['id']}] capture mismatch"
        assert result.trapped == exp["trapped"], f"[{vector['id']}] trapped mismatch"
        assert list(result.new_state.cop_position) == exp["new_cop_position"], (
            f"[{vector['id']}] cop_position: got {result.new_state.cop_position}"
        )
        assert list(result.new_state.thief_position) == exp["new_thief_position"], (
            f"[{vector['id']}] thief_position: got {result.new_state.thief_position}"
        )
        assert result.new_state.turn == exp["new_turn"], (
            f"[{vector['id']}] turn: got {result.new_state.turn}"
        )
        if "barrier_position" in exp and exp["barrier_position"] is not None:
            assert result.barrier_position == tuple(exp["barrier_position"]), (
                f"[{vector['id']}] barrier_position: got {result.barrier_position}"
            )
        if "cop_barriers_remaining" in exp:
            assert result.new_state.cop_barriers_remaining == exp["cop_barriers_remaining"], (
                f"[{vector['id']}] cop_barriers_remaining mismatch"
            )

    def test_simultaneous_barrier_blocks_legal_thief_move_without_protocol_loss(self):
        state = DomainState(
            turn=23,
            grid_size=7,
            cop_position=(5, 1),
            thief_position=(6, 0),
            cop_barriers_remaining=14,
        )

        result = apply_joint_action(state, "PLACE_E", "SOUTH")

        assert result.cop_action_legal is True
        assert result.thief_action_legal is True
        assert result.barrier_position == (6, 1)
        assert result.new_state.thief_position == (6, 0)
        assert result.capture is False


# ---------------------------------------------------------------------------
# 2. Board.from_dict() strict validation
# ---------------------------------------------------------------------------


class TestBoardFromDictStrict:
    def test_missing_cop_position_raises(self):
        with pytest.raises(ValueError, match="cop_position"):
            Board.from_dict({"thief_position": [3, 3]})

    def test_missing_thief_position_raises(self):
        with pytest.raises(ValueError, match="thief_position"):
            Board.from_dict({"cop_position": [0, 0]})

    def test_both_positions_present_succeeds(self):
        board = Board.from_dict({"cop_position": [0, 0], "thief_position": [3, 3]})
        assert board.cop_position == [0, 0]
        assert board.thief_position == [3, 3]
        assert board.turn == 0
        assert board.barriers == []

    def test_optional_fields_use_safe_defaults(self):
        board = Board.from_dict({"cop_position": [1, 1], "thief_position": [5, 5]})
        assert board.grid_size == 7
        assert board.move_history == []

    def test_extra_fields_are_ignored(self):
        board = Board.from_dict(
            {
                "cop_position": [0, 0],
                "thief_position": [3, 3],
                "extra_field": "ignored",
            }
        )
        assert board.cop_position == [0, 0]


# ---------------------------------------------------------------------------
# 3. DomainState strict schema validation
# ---------------------------------------------------------------------------


class TestDomainStateSchema:
    def test_valid_state_accepted(self):
        state = DomainState(
            turn=0,
            grid_size=7,
            cop_position=(0, 0),
            thief_position=(3, 3),
        )
        assert state.turn == 0

    def test_cop_out_of_bounds_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="cop_position"):
            DomainState(
                turn=0,
                grid_size=7,
                cop_position=(8, 8),
                thief_position=(3, 3),
            )

    def test_thief_out_of_bounds_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="thief_position"):
            DomainState(
                turn=0,
                grid_size=7,
                cop_position=(0, 0),
                thief_position=(10, 10),
            )

    def test_barrier_out_of_bounds_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DomainState(
                turn=0,
                grid_size=7,
                cop_position=(0, 0),
                thief_position=(3, 3),
                barriers=[(9, 9)],
            )


# ---------------------------------------------------------------------------
# 4. Config validator — Appendix-F constraints
# ---------------------------------------------------------------------------


class TestConfigValidator:
    def test_game_json_passes_all_constraints(self):
        """The shared config/game.json must satisfy all Appendix-F fixed values."""
        if not _CONFIG_PATH.exists():
            pytest.skip(f"config not found at {_CONFIG_PATH}")
        config = validate_game_config(_CONFIG_PATH)
        assert config.grid_size == 7
        assert config.max_barriers == 14
        assert config.max_moves >= 35
        assert config.network.num_gamelets == 6
        assert config.scoring.capture_cop == 20
        assert config.scoring.survival_thief == 10

    def test_wrong_grid_size_rejected(self):
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError), match="grid_size"):
            GameConfig(grid_size=9, max_barriers=14, max_moves=35)

    def test_wrong_barrier_count_rejected(self):
        from pydantic import ValidationError

        with pytest.raises((ValidationError, ValueError), match="max_barriers"):
            GameConfig(grid_size=7, max_barriers=10, max_moves=35)

    def test_wrong_gamelet_count_rejected(self):
        from pydantic import ValidationError

        from agent.domain.config_validator import NetworkLeagueConfig

        with pytest.raises((ValidationError, ValueError), match="num_gamelets"):
            GameConfig(
                grid_size=7,
                max_barriers=14,
                max_moves=35,
                network=NetworkLeagueConfig(num_gamelets=5),
            )

    def test_wrong_scoring_capture_cop_rejected(self):
        from pydantic import ValidationError

        from agent.domain.config_validator import ScoringConfig

        with pytest.raises((ValidationError, ValueError), match="capture_cop"):
            GameConfig(
                grid_size=7,
                max_barriers=14,
                max_moves=35,
                scoring=ScoringConfig(capture_cop=10),
            )


# ---------------------------------------------------------------------------
# 5. apply_joint_action() scent field update
# ---------------------------------------------------------------------------


class TestScentUpdate:
    def test_scent_initializes_on_first_turn(self):
        state = DomainState(
            turn=0,
            grid_size=7,
            cop_position=(0, 0),
            thief_position=(3, 3),
            scent_grid=[],
        )
        result = apply_joint_action(state, "STAY", "STAY")
        assert len(result.new_state.scent_grid) == 7
        # Center cell [3][3] should have highest emission (0.9)
        assert result.new_state.scent_grid[3][3] == pytest.approx(0.9, abs=1e-4)

    def test_scent_decays_when_thief_moves_away(self):
        # Put non-zero scent at center, then move thief to corner
        initial_scent = [[0.5] * 7 for _ in range(7)]
        state = DomainState(
            turn=0,
            grid_size=7,
            cop_position=(0, 0),
            thief_position=(3, 3),
            scent_grid=initial_scent,
        )
        result = apply_joint_action(state, "STAY", "EAST")
        # After decay + new emission at [4,3], old cells decay to 0.9*0.5 = 0.45
        # (plus possible new emission kernel values)
        assert result.new_state.scent_grid[3][3] > 0  # still has residual scent
