"""Targeted tests for modules the 2026-08-10 additions left under the CI coverage gate.

This part pins the domain config validator and the runtime transition bridge.
"""

from __future__ import annotations

import pytest

from cop_worker.board import Board
from cop_worker.domain.config_validator import GameConfig
from cop_worker.domain.runtime_transition import (
    IllegalJointActionError,
    apply_runtime_transition,
    legal_actions_for_role,
    locked_config,
    state_from_runtime,
)
from cop_worker.rules_engine import RulesEngine


class TestConfigValidator:
    def test_appendix_f_violations_are_named(self) -> None:
        with pytest.raises(ValueError, match="max_barriers must be 14"):
            GameConfig(max_barriers=10)
        with pytest.raises(ValueError, match="grid_size must be >= 7"):
            GameConfig(grid_size=5)
        with pytest.raises(ValueError, match="max_moves must be >= 35"):
            GameConfig(max_moves=20)

    def test_defaults_are_the_signed_terms(self) -> None:
        cfg = GameConfig()
        assert (cfg.grid_size, cfg.max_barriers, cfg.max_moves) == (7, 14, 35)
        assert cfg.scoring.capture_cop == 20 and cfg.scoring.survival_thief == 10


class _Runtime:
    """Minimal stand-in for the legacy runtime the bridge synchronizes."""

    def __init__(self) -> None:
        self.board = Board(cop_position=[0, 0], thief_position=[3, 3], grid_size=7)
        self._cop_barriers_remaining = 14


class TestRuntimeTransition:
    def test_locked_config_falls_back_to_defaults(self) -> None:
        assert isinstance(locked_config(_Runtime()), GameConfig)

    def test_apply_synchronizes_board_and_caches_state(self) -> None:
        runtime = _Runtime()
        rules = RulesEngine(runtime.board)
        result = apply_runtime_transition(runtime, rules, "E", "W")
        assert result.cop_action_legal and result.thief_action_legal
        assert runtime.board.cop_position == [1, 0]
        assert runtime.board.thief_position == [2, 3]
        # The cached DomainState short-circuits the next rebuild.
        assert state_from_runtime(runtime, rules) is runtime._domain_state

    def test_illegal_joint_action_names_the_offender(self) -> None:
        runtime = _Runtime()
        rules = RulesEngine(runtime.board)
        with pytest.raises(IllegalJointActionError, match="cop"):
            apply_runtime_transition(runtime, rules, "W", "STAY")  # cop off-board

    def test_legal_actions_per_role_respect_the_edges(self) -> None:
        runtime = _Runtime()
        rules = RulesEngine(runtime.board)
        cop_legal = legal_actions_for_role(runtime, rules, "cop")
        thief_legal = legal_actions_for_role(runtime, rules, "thief")
        assert "W" not in cop_legal and "N" not in cop_legal  # corner (0,0)
        assert set(thief_legal) >= {"N", "S", "E", "W", "STAY"}  # centre (3,3)


class TestRemainingBranches:
    def test_survival_threshold_violation_named(self) -> None:
        with pytest.raises(ValueError, match="survival_threshold must be >= 35"):
            GameConfig(survival_threshold=10)

    def test_illegal_action_error_message_names_both_actions(self) -> None:
        err = IllegalJointActionError(("cop",), "W", "STAY")
        assert "cop" in str(err) and "'W'" in str(err)

    def test_locked_config_returns_the_runtime_config_when_set(self) -> None:
        runtime = _Runtime()
        runtime.game_config = GameConfig()
        assert locked_config(runtime) is runtime.game_config
