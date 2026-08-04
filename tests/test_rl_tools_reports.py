"""Comprehensive tests for rl/, tools/, agents/, reports/ modules.

Covers uncovered lines identified in the coverage report.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stubs for optional heavy dependencies that may not be installed
# ---------------------------------------------------------------------------

# Stub crewai so importing agent.tools.* and agent.agents.* never fails
_crewai_agent_stub = MagicMock()
_crewai_task_stub = MagicMock()
_crewai_mod = MagicMock()
_crewai_mod.Agent = _crewai_agent_stub
_crewai_mod.Task = _crewai_task_stub


class _ToolDecorator:
    """Transparent decorator that replaces crewai.tools.tool."""

    def __call__(self, func):
        return func


_crewai_tools_mod = MagicMock()
_crewai_tools_mod.tool = _ToolDecorator()

# Install stubs before any project import (override even if real crewai is installed)
sys.modules["crewai"] = _crewai_mod
sys.modules["crewai.tools"] = _crewai_tools_mod

# ---------------------------------------------------------------------------
# Project imports (after stubs)
# ---------------------------------------------------------------------------
from agent.board import Board  # noqa: E402
from agent.rl.config import RLGameConfig  # noqa: E402
from agent.rl.env_helpers import apply_place_action, manhattan_dist, random_starts  # noqa: E402
from agent.rl.env_rewards import RewardsMixin  # noqa: E402
from agent.rl.environment import CopThiefEnv  # noqa: E402
from agent.rl.observation import cop_observation, observation_shape, thief_observation  # noqa: E402
from agent.rules_engine import GameOutcome, RulesEngine  # noqa: E402
from agent.rules_outcomes import check_game_status  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_board(cop=(0, 0), thief=(3, 3), grid=7, barriers=None):
    return Board(
        cop_position=list(cop),
        thief_position=list(thief),
        grid_size=grid,
        barriers=barriers or [],
    )


def _make_env(barrier_quota=0, random_starts_flag=False):
    cfg = RLGameConfig(cop_barrier_quota=barrier_quota, random_starts=random_starts_flag)
    return CopThiefEnv(cfg)


# ===========================================================================
# 1. agent/board.py
# ===========================================================================


class TestBoardPlaceBarrier:
    def test_place_barrier_ok(self):
        b = _make_board()
        assert b.place_barrier(1, 1) is True
        assert [1, 1] in b.barriers

    def test_place_barrier_out_of_bounds(self):
        b = _make_board()
        assert b.place_barrier(-1, 0) is False
        assert b.place_barrier(0, 7) is False

    def test_place_barrier_already_exists(self):
        b = _make_board(barriers=[[2, 2]])
        assert b.place_barrier(2, 2) is False

    def test_apply_move_invalid_action(self):
        b = _make_board()
        result = b.apply_move("cop", "JUMP")
        assert result is False

    def test_apply_move_invalid_role(self):
        b = _make_board()
        result = b.apply_move("judge", "NORTH")
        assert result is False

    def test_apply_move_blocked_by_barrier(self):
        b = _make_board(cop=(0, 0), barriers=[[0, 1]])
        result = b.apply_move("cop", "SOUTH")
        assert result is False

    def test_get_position_invalid_role(self):
        b = _make_board()
        with pytest.raises(ValueError):
            b.get_position("ghost")

    def test_to_dict_round_trip(self):
        b = _make_board(cop=(1, 2), thief=(4, 5), barriers=[[0, 0]])
        d = b.to_dict()
        b2 = Board.from_dict(d)
        assert b2.cop_position == [1, 2]
        assert b2.thief_position == [4, 5]
        assert b2.barriers == [[0, 0]]

    def test_to_state_alias(self):
        b = _make_board()
        assert b.to_state() == b.to_dict()

    def test_from_state_alias(self):
        b = _make_board(cop=(2, 3))
        s = b.to_state()
        b2 = Board.from_state(s)
        assert b2.cop_position == [2, 3]

    def test_from_dict_requires_both_positions(self):
        """Board.from_dict must not silently default cop/thief positions (Phase 1 fix).

        Silent defaults would let a role-filtered observation reconstruct private
        opponent state. Both positions are required.
        """
        with pytest.raises(ValueError, match="cop_position"):
            Board.from_dict({})
        with pytest.raises(ValueError, match="thief_position"):
            Board.from_dict({"cop_position": [0, 0]})
        # Full state succeeds and returns correct optional defaults
        b = Board.from_dict({"cop_position": [0, 0], "thief_position": [3, 3]})
        assert b.cop_position == [0, 0]
        assert b.thief_position == [3, 3]
        assert b.grid_size == 7


# ===========================================================================
# 2. agent/rules_outcomes.py
# ===========================================================================


class TestCheckGameStatus:
    def test_capture_returns_cop_win(self):
        b = _make_board(cop=(3, 3), thief=(3, 3))
        assert check_game_status(b, 35) == GameOutcome.COP_WIN

    def test_max_turns_returns_thief_win(self):
        b = _make_board()
        b.turn = 35
        assert check_game_status(b, 35) == GameOutcome.THIEF_WIN

    def test_thief_trapped_when_only_stay_available(self):
        # Thief at corner [0,6] with barriers at [0,5] and [1,6]: no orthogonal
        # escape. STAY does not count as an escape — binding rule §3.4.
        b = _make_board(thief=(0, 6), grid=7, barriers=[[0, 5], [1, 6]])
        assert check_game_status(b, 35) == GameOutcome.COP_WIN

    def test_ongoing(self):
        b = _make_board()
        assert check_game_status(b, 35) == GameOutcome.ONGOING


# ===========================================================================
# 3. agent/rl/env_helpers.py
# ===========================================================================


class TestEnvHelpers:
    def test_random_starts_different_positions(self):
        cop, thief = random_starts(7, [])
        assert cop != thief
        assert len(cop) == 2
        assert len(thief) == 2

    def test_random_starts_avoids_barriers(self):
        barriers = [[x, y] for x in range(7) for y in range(6)]  # only row 6 free
        # With one row free there are 7 cells; cop and thief must be among them
        cop, thief = random_starts(7, barriers)
        for pos in (cop, thief):
            assert pos[1] == 6

    def test_manhattan_dist(self):
        b = _make_board(cop=(0, 0), thief=(3, 4))
        assert manhattan_dist(b) == 7

    def test_apply_place_action_no_quota(self):
        b = _make_board(cop=(3, 3))
        remaining = apply_place_action(b, "PLACE_N", 7, 0)
        assert remaining == 0  # nothing placed
        assert b.barriers == []

    def test_apply_place_action_places_barrier(self):
        b = _make_board(cop=(3, 3))
        remaining = apply_place_action(b, "PLACE_N", 7, 5)
        assert remaining == 4
        assert [3, 2] in b.barriers

    def test_apply_place_action_out_of_bounds(self):
        b = _make_board(cop=(0, 0))
        # PLACE_N would go to (0, -1) → out of bounds
        remaining = apply_place_action(b, "PLACE_N", 7, 5)
        assert remaining == 5
        assert b.barriers == []

    def test_apply_place_action_on_thief_is_capture(self):
        b = _make_board(cop=(3, 3), thief=(3, 2))
        # PLACE_N lands on thief → legal capture, barrier consumed (§3.4).
        remaining = apply_place_action(b, "PLACE_N", 7, 5)
        assert remaining == 4
        assert b.is_capture() is True


# ===========================================================================
# 4. agent/rl/env_rewards.py
# ===========================================================================


class TestRewardsMixin:
    def _make_mixin(self, cfg=None, board=None, prev_dist=3):
        """Create a concrete RewardsMixin instance."""

        class Concrete(RewardsMixin):
            pass

        obj = Concrete.__new__(Concrete)
        obj.config = cfg or RLGameConfig()
        obj._board = board or _make_board()
        obj._prev_dist = prev_dist
        return obj

    def test_rewards_cop_win(self):
        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.COP_WIN)
        assert cop_r == m.config.cop_capture_reward
        assert thief_r == -m.config.thief_survival_reward

    def test_rewards_thief_win(self):
        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.THIEF_WIN)
        assert cop_r == -m.config.thief_survival_reward
        assert thief_r == m.config.cop_capture_reward

    def test_rewards_ongoing(self):
        m = self._make_mixin()
        cop_r, thief_r = m._rewards(GameOutcome.ONGOING)
        assert cop_r == -m.config.step_penalty
        assert thief_r == m.config.step_penalty

    def test_shaped_rewards_terminal(self):
        m = self._make_mixin()
        cop_r, thief_r = m._shaped_rewards(GameOutcome.COP_WIN)
        assert cop_r == m.config.cop_capture_reward

    def test_shaped_rewards_ongoing_updates_prev_dist(self):
        cfg = RLGameConfig(shaped_reward_scale=0.1)
        board = _make_board(cop=(0, 0), thief=(2, 0))  # dist=2
        m = self._make_mixin(cfg=cfg, board=board, prev_dist=5)
        cop_r, thief_r = m._shaped_rewards(GameOutcome.ONGOING)
        # delta = 5 - 2 = 3 → cop gets +0.3, thief gets -0.3
        assert m._prev_dist == 2
        assert abs(cop_r - (-cfg.step_penalty + 0.1 * 3)) < 1e-9


# ===========================================================================
# 5. agent/rl/environment.py
# ===========================================================================


class TestCopThiefEnv:
    def test_n_cop_actions_no_barriers(self):
        env = _make_env(barrier_quota=0)
        assert env.n_cop_actions == 5

    def test_n_cop_actions_with_barriers(self):
        env = _make_env(barrier_quota=5)
        assert env.n_cop_actions == 9

    def test_n_thief_actions(self):
        env = _make_env()
        assert env.n_thief_actions == 5

    def test_n_cop_channels_no_barriers(self):
        env = _make_env(barrier_quota=0)
        assert env.n_cop_channels == 4

    def test_n_cop_channels_with_barriers(self):
        env = _make_env(barrier_quota=5)
        assert env.n_cop_channels == 5

    def test_reset_returns_obs(self):
        env = _make_env()
        cop_obs, thief_obs = env.reset()
        assert len(cop_obs) == 4
        assert len(thief_obs) == 4

    def test_reset_random_starts(self):
        env = _make_env(random_starts_flag=True)
        cop_obs, thief_obs = env.reset()
        assert len(cop_obs) == 4

    def test_step_stay_stay(self):
        env = _make_env()
        env.reset()
        # STAY=4 for both
        result = env.step(4, 4)
        assert len(result) == 6
        cop_obs, thief_obs, cop_r, thief_r, done, info = result
        assert isinstance(done, bool)
        assert "outcome" in info

    def test_step_cop_wins(self):
        # Start cop adjacent to thief; move cop to thief's cell
        cfg = RLGameConfig(cop_start=[2, 3], thief_start=[3, 3])
        env = CopThiefEnv(cfg)
        env.reset()
        # cop EAST=2 → [3,3]; thief STAY=4
        _, _, _, _, done, info = env.step(2, 4)
        assert done
        assert info["winner"] == "cop"

    def test_step_done_thief_wins_turn_limit(self):
        # RulesEngine enforces min 35 turns; set board turn to 35 so after
        # apply_moves it becomes 36 >= 35 → thief wins.
        cfg = RLGameConfig(max_steps=35)
        env = CopThiefEnv(cfg)
        env.reset()
        env._board.turn = 35
        _, _, _, _, done, info = env.step(4, 4)
        assert done
        assert info["winner"] == "thief"

    def test_observation_shape_thief(self):
        env = _make_env()
        shape = env.observation_shape("thief")
        assert shape == (4, 7, 7)

    def test_observation_shape_cop(self):
        env = _make_env()
        shape = env.observation_shape("cop")
        assert shape == (4, 7, 7)

    def test_observation_shape_cop_with_barriers(self):
        env = _make_env(barrier_quota=5)
        shape = env.observation_shape("cop")
        assert shape == (5, 7, 7)

    def test_step_barrier_action(self):
        env = _make_env(barrier_quota=5)
        env.reset()
        # PLACE_N = action index 5
        cop_obs, thief_obs, cop_r, thief_r, done, info = env.step(5, 4)
        assert isinstance(done, bool)

    def test_step_shaped_rewards(self):
        cfg = RLGameConfig(use_shaped_rewards=True)
        env = CopThiefEnv(cfg)
        env.reset()
        _, _, cop_r, thief_r, done, info = env.step(4, 4)
        assert isinstance(cop_r, float)

    def test_action_meanings(self):
        env = _make_env()
        meanings = env.action_meanings()
        assert "NORTH" in meanings

    def test_step_illegal_cop_move_corrected(self):
        # cop at (0,0); WEST=3 is illegal → corrected to STAY
        cfg = RLGameConfig(cop_start=[0, 0], thief_start=[3, 3])
        env = CopThiefEnv(cfg)
        env.reset()
        # Index 3 = WEST
        _, _, _, _, done, info = env.step(3, 4)
        assert isinstance(done, bool)


# ===========================================================================
# 6. agent/rl/observation.py
# ===========================================================================


class TestObservation:
    def _board_and_rules(self):
        b = _make_board()
        r = RulesEngine(b)
        return b, r

    def test_cop_observation_4_channels(self):
        b, r = self._board_and_rules()
        obs = cop_observation(b, r, 35, barriers_remaining=0, barrier_quota=0)
        assert len(obs) == 4

    def test_cop_observation_5_channels(self):
        b, r = self._board_and_rules()
        obs = cop_observation(b, r, 35, barriers_remaining=3, barrier_quota=5)
        assert len(obs) == 5

    def test_thief_observation_no_cop_pos(self):
        b, _ = self._board_and_rules()
        obs = thief_observation(b, 35)
        assert len(obs) == 4

    def test_thief_observation_with_cop_scent(self):
        b, _ = self._board_and_rules()
        n = b.grid_size
        scent = [[0.0] * n for _ in range(n)]
        scent[1][1] = 0.9  # cop was around (1,1)
        obs = thief_observation(b, 35, cop_scent_field=scent)
        assert len(obs) == 4
        # Channel 1 should reflect the scent field
        assert obs[1][1][1] == 0.9

    def test_observation_shape_thief(self):
        assert observation_shape(7, "thief", 0) == (4, 7, 7)

    def test_observation_shape_cop_no_barriers(self):
        assert observation_shape(7, "cop", 0) == (4, 7, 7)

    def test_observation_shape_cop_with_barriers(self):
        assert observation_shape(7, "cop", 5) == (5, 7, 7)


# ===========================================================================
# 7. agent/rl/networks.py
# ===========================================================================


class TestNetworks:
    def test_dqnnet_mlp_forward(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=5, hidden=64, net_type="mlp", in_channels=4)
        x = torch.zeros(1, 4, 7, 7)
        out = net(x)
        assert out.shape == (1, 5)

    def test_dqnnet_cnn_forward(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=5, hidden=64, net_type="cnn", in_channels=4)
        x = torch.zeros(1, 4, 7, 7)
        out = net(x)
        assert out.shape == (1, 5)

    def test_pponet_mlp_forward(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=64, net_type="mlp", in_channels=4)
        x = torch.zeros(1, 4, 7, 7)
        logits, value = net(x)
        assert logits.shape == (1, 5)
        assert value.shape == (1, 1)

    def test_pponet_cnn_forward(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=64, net_type="cnn", in_channels=4)
        x = torch.zeros(1, 4, 7, 7)
        logits, value = net(x)
        assert logits.shape == (1, 5)

    def test_pponet_get_action_deterministic(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=64, net_type="mlp")
        x = torch.zeros(1, 4, 7, 7)
        action, log_prob, entropy, value = net.get_action(x, deterministic=True)
        # action has shape [batch_size] = [1]
        assert action.numel() == 1
        assert 0 <= int(action.item()) < 5

    def test_pponet_get_action_stochastic(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet

        net = PPONet(grid_size=7, n_actions=5, hidden=64, net_type="mlp")
        x = torch.zeros(1, 4, 7, 7)
        action, log_prob, entropy, value = net.get_action(x, deterministic=False)
        assert 0 <= int(action.item()) < 5

    def test_dqnnet_5channel(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import DQNNet

        net = DQNNet(grid_size=7, n_actions=9, hidden=64, net_type="mlp", in_channels=5)
        x = torch.zeros(1, 5, 7, 7)
        out = net(x)
        assert out.shape == (1, 9)


# ===========================================================================
# 8. agent/rl/policy.py and policy_loader.py
# ===========================================================================


class TestRLPolicy:
    def _make_policy(self, role="thief", algo="dqn", barrier_quota=0):
        pytest.importorskip("torch")
        from agent.rl.networks import DQNNet, PPONet
        from agent.rl.policy import RLPolicy

        if algo == "dqn":
            net = DQNNet(grid_size=7, n_actions=5, hidden=64)
        else:
            net = PPONet(grid_size=7, n_actions=5, hidden=64)
        return RLPolicy(net, role=role, algo=algo, max_steps=35, barrier_quota=barrier_quota)

    def test_select_move_dqn_thief(self):
        policy = self._make_policy("thief", "dqn")
        b = _make_board()
        r = RulesEngine(b)
        move = policy.select_move(b, r)
        assert move in ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]

    def test_select_move_ppo_thief(self):
        policy = self._make_policy("thief", "ppo")
        b = _make_board()
        r = RulesEngine(b)
        move = policy.select_move(b, r)
        assert move in ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]

    def test_select_move_cop(self):
        policy = self._make_policy("cop", "dqn")
        b = _make_board()
        r = RulesEngine(b)
        move = policy.select_move(b, r)
        assert move in ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]

    def test_select_move_with_cop_scent_field(self):
        policy = self._make_policy("thief", "dqn")
        b = _make_board()
        r = RulesEngine(b)
        n = b.grid_size
        scent = [[0.0] * n for _ in range(n)]
        scent[1][1] = 0.5
        move = policy.select_move(b, r, cop_scent_field=scent)
        assert move in ["NORTH", "SOUTH", "EAST", "WEST", "STAY"]

    def test_select_action_dqn(self):
        policy = self._make_policy("thief", "dqn")
        obs = [[[0.0] * 7 for _ in range(7)] for _ in range(4)]
        idx, lp, ent = policy.select_action(obs)
        assert 0 <= idx < 5

    def test_select_action_ppo_training(self):
        policy = self._make_policy("thief", "ppo")
        obs = [[[0.0] * 7 for _ in range(7)] for _ in range(4)]
        idx, lp, ent = policy.select_action(obs, training=True)
        assert 0 <= idx < 5

    def test_select_action_ppo_not_training(self):
        policy = self._make_policy("thief", "ppo")
        obs = [[[0.0] * 7 for _ in range(7)] for _ in range(4)]
        idx, lp, ent = policy.select_action(obs, training=False)
        assert 0 <= idx < 5

    def test_build_obs_cop(self):
        policy = self._make_policy("cop", "dqn", barrier_quota=0)
        b = _make_board()
        r = RulesEngine(b)
        obs = policy._build_obs(b, r)
        assert len(obs) == 4

    def test_build_obs_thief(self):
        policy = self._make_policy("thief", "dqn")
        b = _make_board()
        r = RulesEngine(b)
        obs = policy._build_obs(b, r)
        assert len(obs) == 4

    def test_select_move_cop_barrier_quota(self):
        pytest.importorskip("torch")
        from agent.rl.networks import DQNNet
        from agent.rl.policy import RLPolicy

        net = DQNNet(grid_size=7, n_actions=9, hidden=64, in_channels=5)
        policy = RLPolicy(net, role="cop", algo="dqn", barrier_quota=5, barriers_remaining=3)
        b = _make_board()
        r = RulesEngine(b)
        move = policy.select_move(b, r)
        # Move could be PLACE_* or movement
        assert isinstance(move, str)

    def test_select_move_from_dict(self):
        policy = self._make_policy("thief", "dqn")
        state = {"cop_position": [0, 0], "thief_position": [3, 3]}
        move = policy.select_move_from_dict(state)
        assert isinstance(move, str)


class TestPolicyLoader:
    def test_rebuild_net_mlp_dqn(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import DQNNet
        from agent.rl.policy_loader import rebuild_net

        net = DQNNet(grid_size=7, n_actions=5, hidden=64)
        sd = net.state_dict()
        ckpt = {"n_actions": 5, "n_channels": 4}
        rebuilt = rebuild_net(sd, ckpt, "dqn", torch.device("cpu"))
        assert rebuilt is not None

    def test_rebuild_net_mlp_ppo(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet
        from agent.rl.policy_loader import rebuild_net

        net = PPONet(grid_size=7, n_actions=5, hidden=64)
        sd = net.state_dict()
        ckpt = {"n_actions": 5, "n_channels": 4}
        rebuilt = rebuild_net(sd, ckpt, "ppo", torch.device("cpu"))
        assert rebuilt is not None

    def test_rebuild_net_infers_channels(self):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import DQNNet
        from agent.rl.policy_loader import rebuild_net

        net = DQNNet(grid_size=7, n_actions=5, hidden=64, in_channels=4)
        sd = net.state_dict()
        ckpt = {}  # no n_actions / n_channels → must infer
        rebuilt = rebuild_net(sd, ckpt, "dqn", torch.device("cpu"))
        assert rebuilt is not None

    def test_load_checkpoint_file_not_found(self):
        pytest.importorskip("torch")
        from agent.rl.policy import RLPolicy

        with pytest.raises(FileNotFoundError):
            RLPolicy.load("thief", models_dir=Path("/nonexistent_dir_xyz"))

    def test_load_checkpoint_from_file(self, tmp_path):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import DQNNet
        from agent.rl.policy_loader import load_checkpoint

        net = DQNNet(grid_size=7, n_actions=5, hidden=64)
        ckpt = {"net": net.state_dict(), "n_actions": 5, "n_channels": 4}
        path = tmp_path / "thief_dqn.pt"
        torch.save(ckpt, path)
        policy = load_checkpoint(path, "thief", max_steps=35)
        assert policy.role == "thief"
        assert policy.algo == "dqn"

    def test_load_checkpoint_ppo_from_file(self, tmp_path):
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet
        from agent.rl.policy_loader import load_checkpoint

        net = PPONet(grid_size=7, n_actions=5, hidden=64)
        ckpt = {"net": net.state_dict(), "n_actions": 5, "n_channels": 4, "updates": 100}
        path = tmp_path / "thief_ppo.pt"
        torch.save(ckpt, path)
        policy = load_checkpoint(path, "thief", max_steps=35)
        assert policy.algo == "ppo"

    def test_load_checkpoint_cop_with_saved_barrier_quota(self, tmp_path):
        # Verify that barrier_quota is preserved from the checkpoint when explicitly saved.
        torch = pytest.importorskip("torch")
        from agent.rl.networks import PPONet
        from agent.rl.policy_loader import load_checkpoint

        net = PPONet(grid_size=7, n_actions=9, hidden=256, net_type="cnn", in_channels=5)
        ckpt = {"net": net.state_dict(), "updates": 100, "barrier_quota": 14, "n_channels": 5}
        path = tmp_path / "cop_ppo.pt"
        torch.save(ckpt, path)
        policy = load_checkpoint(path, "cop", max_steps=35)
        assert policy.barrier_quota == 14


# ===========================================================================
# 9. agent/peer_turn_helpers.py
# ===========================================================================


class TestPeerTurnHelpers:
    def _make_runtime(self, role="thief"):
        rt = MagicMock()
        rt.role = role
        rt.game_id = "game123"
        rt.config_sha256 = "abc123"
        rt.secret = "test-secret"
        rt.opponent_client = MagicMock()
        rt.board = _make_board()
        return rt

    @pytest.mark.asyncio
    async def test_send_commit_success(self):
        from agent.peer_turn_helpers import send_commit

        rt = self._make_runtime()
        rt.opponent_client.action = AsyncMock(return_value={"h_commit": "abc"})
        result = await send_commit(rt, 1, "hashvalue")
        assert result == {"h_commit": "abc"}

    @pytest.mark.asyncio
    async def test_send_commit_exception_returns_none(self):
        from agent.peer_turn_helpers import send_commit

        rt = self._make_runtime()
        rt.opponent_client.action = AsyncMock(side_effect=Exception("network error"))
        result = await send_commit(rt, 1, "hashvalue")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_reveal_success(self):
        from agent.peer_turn_helpers import send_reveal

        rt = self._make_runtime()
        rt.opponent_client.action = AsyncMock(return_value={"move": "NORTH"})
        payload = {"move": "NORTH", "hint": "", "intent": "truth", "state_hash": "x"}
        result = await send_reveal(rt, 1, payload)
        assert result == {"move": "NORTH"}

    @pytest.mark.asyncio
    async def test_send_reveal_exception_returns_none(self):
        from agent.peer_turn_helpers import send_reveal

        rt = self._make_runtime()
        rt.opponent_client.action = AsyncMock(side_effect=Exception("timeout"))
        payload = {"move": "STAY", "hint": "", "intent": "truth", "state_hash": "x"}
        result = await send_reveal(rt, 1, payload)
        assert result is None

    @pytest.mark.asyncio
    async def test_select_move_rl_success(self):
        from agent.peer_turn_helpers import select_move

        rt = self._make_runtime()
        rt._build_observation = MagicMock(return_value=[])
        rt._select_move_rl = MagicMock(return_value="NORTH")
        board_state = {"cop_position": [0, 0], "thief_position": [3, 3], "turn": 0}
        move = await select_move(rt, board_state)
        assert move == "NORTH"

    @pytest.mark.asyncio
    async def test_select_move_rl_failure_falls_back(self):
        from agent.peer_turn_helpers import select_move

        rt = self._make_runtime(role="thief")
        rt._build_observation = MagicMock(return_value=[])
        rt._select_move_rl = MagicMock(side_effect=Exception("RL failure"))
        board_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
            "grid_size": 7,
            "barriers": [],
            "move_history": [],
        }
        move = await select_move(rt, board_state)
        assert isinstance(move, str)

    @pytest.mark.asyncio
    async def test_select_move_rl_returns_none_falls_back(self):
        from agent.peer_turn_helpers import select_move

        rt = self._make_runtime(role="cop")
        rt._build_observation = MagicMock(return_value=[])
        rt._select_move_rl = MagicMock(return_value=None)
        board_state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "turn": 0,
            "grid_size": 7,
            "barriers": [],
            "move_history": [],
        }
        move = await select_move(rt, board_state)
        assert isinstance(move, str)

    def test_get_watchdog_timeout_default(self):
        with patch(
            "agent.config.shared_config.load_shared_config", side_effect=Exception("no config")
        ):
            from agent.peer_turn_helpers import get_watchdog_timeout as gwt

            result = gwt()
        assert result == 60.0

    def test_get_watchdog_timeout_from_config(self):
        from agent.peer_turn_helpers import get_watchdog_timeout

        fake_cfg = {"network_and_league": {"watchdog_timeout_sec": 30}}
        with patch("agent.config.shared_config.load_shared_config", return_value=fake_cfg):
            result = get_watchdog_timeout()
        assert result == 30.0


# ===========================================================================
# 10. agent/peer_turn_loop.py
# ===========================================================================


class TestPeerTurnLoop:
    def _make_runtime(self, role="thief"):
        rt = MagicMock()
        rt.role = role
        rt.game_id = "game123"
        rt.config_sha256 = "sha"
        rt.board = _make_board()
        rt.game_dir = Path("/tmp/game123")
        return rt

    @pytest.mark.asyncio
    async def test_run_peer_turn_commit_fails(self):
        from agent.peer_turn_loop import run_peer_turn

        rt = self._make_runtime()
        rules = RulesEngine(rt.board)
        with (
            patch(
                "agent.peer_turn_loop.build_board_state",
                return_value={"cop_position": [0, 0], "thief_position": [3, 3], "turn": 0},
            ),
            patch("agent.peer_turn_loop.hash_game_state", return_value="h"),
            patch("agent.peer_turn_loop.select_move", new_callable=AsyncMock, return_value="STAY"),
            patch("agent.peer_turn_loop.create_commitment", return_value=("hc", "n")),
            patch("agent.peer_turn_loop.send_commit", new_callable=AsyncMock, return_value=None),
            patch("agent.peer_turn_loop.append_opponent_commit"),
        ):
            winner, abort = await run_peer_turn(rt, 1, rules)
        assert winner is None
        assert "COMMIT exchange failed" in abort

    @pytest.mark.asyncio
    async def test_run_peer_turn_no_h_commit_in_response(self):
        from agent.peer_turn_loop import run_peer_turn

        rt = self._make_runtime()
        rules = RulesEngine(rt.board)
        with (
            patch(
                "agent.peer_turn_loop.build_board_state",
                return_value={"cop_position": [0, 0], "thief_position": [3, 3], "turn": 0},
            ),
            patch("agent.peer_turn_loop.hash_game_state", return_value="h"),
            patch("agent.peer_turn_loop.select_move", new_callable=AsyncMock, return_value="STAY"),
            patch("agent.peer_turn_loop.create_commitment", return_value=("hc", "n")),
            patch("agent.peer_turn_loop.send_commit", new_callable=AsyncMock, return_value={}),
            patch("agent.peer_turn_loop.append_opponent_commit"),
        ):
            winner, abort = await run_peer_turn(rt, 1, rules)
        assert abort is not None

    @pytest.mark.asyncio
    async def test_run_peer_turn_reveal_fails(self):
        from agent.peer_turn_loop import run_peer_turn

        rt = self._make_runtime()
        rules = RulesEngine(rt.board)
        with (
            patch(
                "agent.peer_turn_loop.build_board_state",
                return_value={"cop_position": [0, 0], "thief_position": [3, 3], "turn": 0},
            ),
            patch("agent.peer_turn_loop.hash_game_state", return_value="h"),
            patch("agent.peer_turn_loop.select_move", new_callable=AsyncMock, return_value="STAY"),
            patch("agent.peer_turn_loop.create_commitment", return_value=("hc", "n")),
            patch(
                "agent.peer_turn_loop.send_commit",
                new_callable=AsyncMock,
                return_value={"h_commit": "hc"},
            ),
            patch("agent.peer_turn_loop.append_opponent_commit"),
            patch("agent.peer_turn_loop.send_reveal", new_callable=AsyncMock, return_value=None),
            patch("agent.peer_turn_loop.append_opponent_reveal"),
        ):
            winner, abort = await run_peer_turn(rt, 1, rules)
        assert "REVEAL exchange failed" in abort

    @pytest.mark.asyncio
    async def test_run_peer_turn_loop_timeout(self):
        from agent.peer_turn_loop import run_peer_turn_loop

        rt = self._make_runtime()
        rules = RulesEngine(rt.board)

        async def _timeout(*a, **k):
            raise TimeoutError()

        with (
            patch("agent.peer_turn_loop.get_watchdog_timeout", return_value=0.001),
            patch("agent.peer_turn_loop.run_peer_turn", side_effect=_timeout),
        ):
            winner, abort, step = await run_peer_turn_loop(rt, rules, max_turns=2)
        assert abort is not None

    @pytest.mark.asyncio
    async def test_run_peer_turn_loop_exception(self):
        from agent.peer_turn_loop import run_peer_turn_loop

        rt = self._make_runtime()
        rules = RulesEngine(rt.board)

        async def _fail(*a, **k):
            raise RuntimeError("unexpected")

        with (
            patch("agent.peer_turn_loop.get_watchdog_timeout", return_value=5.0),
            patch("agent.peer_turn_loop.run_peer_turn", side_effect=_fail),
        ):
            winner, abort, step = await run_peer_turn_loop(rt, rules, max_turns=1)
        assert abort == "unexpected"

    @pytest.mark.asyncio
    async def test_run_peer_turn_loop_no_winner_thief_wins(self):
        from agent.peer_turn_loop import run_peer_turn_loop

        rt = self._make_runtime()
        rules = RulesEngine(rt.board)

        async def _no_winner(*a, **k):
            return None, None

        with (
            patch("agent.peer_turn_loop.get_watchdog_timeout", return_value=5.0),
            patch("agent.peer_turn_loop.run_peer_turn", side_effect=_no_winner),
        ):
            winner, abort, step = await run_peer_turn_loop(rt, rules, max_turns=1)
        assert winner == "thief"

    @pytest.mark.asyncio
    async def test_run_peer_turn_barrier_placement(self):
        from agent.peer_turn_loop import run_peer_turn

        rt = self._make_runtime(role="cop")
        rt._cop_barriers_remaining = 5
        rules = RulesEngine(rt.board)
        with (
            patch(
                "agent.peer_turn_loop.build_board_state",
                return_value={"cop_position": [3, 3], "thief_position": [6, 6], "turn": 0},
            ),
            patch("agent.peer_turn_loop.hash_game_state", return_value="h"),
            patch("agent.peer_turn_loop.select_move", new_callable=AsyncMock, return_value="STAY"),
            patch("agent.peer_turn_loop.create_commitment", return_value=("hc", "n")),
            patch(
                "agent.peer_turn_loop.send_commit",
                new_callable=AsyncMock,
                return_value={"h_commit": "hc"},
            ),
            patch("agent.peer_turn_loop.append_opponent_commit"),
            patch(
                "agent.peer_turn_loop.send_reveal",
                new_callable=AsyncMock,
                return_value={"move": "PLACE_N"},
            ),
            patch("agent.peer_turn_loop.append_opponent_reveal"),
        ):
            winner, abort = await run_peer_turn(rt, 1, rules)
        # PLACE_N from opponent (thief) is not a valid thief move → becomes STAY
        assert winner is None or winner == "cop"


# ===========================================================================
# 11. agent/tools/board_tool.py
# ===========================================================================


class TestBoardTool:
    def test_apply_move_returns_updated_state(self):
        from agent.tools.board_tool import apply_move

        state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "grid_size": 7,
            "barriers": [],
            "turn": 0,
            "move_history": [],
        }
        result = apply_move(state, "cop", "EAST")
        assert result["cop_position"] == [1, 0]

    def test_apply_move_invalid_role_returns_state(self):
        from agent.tools.board_tool import apply_move

        state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "grid_size": 7,
            "barriers": [],
            "turn": 0,
            "move_history": [],
        }
        # invalid role raises inside apply_move → returns unchanged state
        result = apply_move(state, "ghost", "NORTH")
        assert result == state

    def test_apply_both_moves(self):
        from agent.tools.board_tool import apply_both_moves

        state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "grid_size": 7,
            "barriers": [],
            "turn": 0,
            "move_history": [],
        }
        result = apply_both_moves(state, "EAST", "WEST")
        assert result["cop_position"] == [1, 0]
        assert result["thief_position"] == [2, 3]

    def test_get_legal_moves(self):
        from agent.tools.board_tool import get_legal_moves

        state = {
            "cop_position": [0, 0],
            "thief_position": [3, 3],
            "grid_size": 7,
            "barriers": [],
            "turn": 0,
            "move_history": [],
        }
        moves = get_legal_moves(state, "cop")
        assert "EAST" in moves
        assert "SOUTH" in moves

    def test_check_board_state(self):
        from agent.tools.board_tool import check_board_state

        state = {
            "cop_position": [1, 1],
            "thief_position": [4, 4],
            "grid_size": 7,
            "barriers": [],
            "turn": 0,
            "move_history": [],
        }
        result = check_board_state(state)
        assert result["cop_position"] == [1, 1]
        assert result["same_position"] is False


# ===========================================================================
# 12. agent/tools/game_state_tool.py
# ===========================================================================


class TestGameStateTool:
    def test_get_observation_cop(self):
        from agent.tools.game_state_tool import get_observation

        state = {"cop_position": [3, 3], "thief_position": [6, 6], "turn": 5}
        obs = get_observation("g1", "cop", state)
        assert obs["own_position"] == [3, 3]
        assert "candidate_actions" in obs

    def test_get_observation_thief(self):
        from agent.tools.game_state_tool import get_observation

        state = {"cop_position": [0, 0], "thief_position": [4, 4], "turn": 2}
        obs = get_observation("g1", "thief", state)
        assert obs["own_position"] == [4, 4]

    def test_get_observation_empty_state(self):
        from agent.tools.game_state_tool import get_observation

        obs = get_observation("g1", "cop", {})
        assert obs["own_position"] == [0, 0]

    def test_load_game_state_missing(self, tmp_path):
        from agent.tools.game_state_tool import load_game_state

        result = load_game_state("nosuchgame", memory_dir=tmp_path)
        assert result == {}

    def test_save_and_load_game_state(self, tmp_path):
        from agent.tools.game_state_tool import load_game_state, save_game_state

        state = {"cop_position": [1, 2], "turn": 3}
        ok = save_game_state("g2", state, memory_dir=tmp_path)
        assert ok is True
        loaded = load_game_state("g2", memory_dir=tmp_path)
        assert loaded["turn"] == 3


# ===========================================================================
# 13. agent/tools/protocol_tool.py
# ===========================================================================


class TestProtocolTool:
    def test_analyze_tool_names(self):
        from agent.tools.protocol_tool import analyze_tool_names

        result = analyze_tool_names(["start_game", "commit_move", "reveal", "ping"])
        assert "start_game" in result
        assert "commit" in result.lower()

    def test_infer_game_flow_commit_reveal(self):
        from agent.tools.protocol_tool import infer_game_flow

        result = infer_game_flow(["start_game", "action", "commit", "reveal"])
        assert "Commit-Reveal" in result

    def test_infer_game_flow_unknown(self):
        from agent.tools.protocol_tool import infer_game_flow

        result = infer_game_flow(["foo", "bar"])
        assert "Unknown" in result

    def test_summarize_protocol(self):
        from agent.tools.protocol_tool import summarize_protocol

        tools = ["start_game", "action", "ping"]
        result = summarize_protocol(tools)
        assert "Total tools: 3" in result

    def test_analyze_tool_names_health(self):
        from agent.tools.protocol_tool import analyze_tool_names

        result = analyze_tool_names(["health_check"])
        assert "health" in result.lower()


# ===========================================================================
# 14. agent/tools/read_skill_tool.py
# ===========================================================================


class TestReadSkillTool:
    def test_read_skill_file_not_found(self):
        from agent.tools.read_skill_tool import read_skill_file

        result = json.loads(read_skill_file("/nonexistent/path/skill.py"))
        assert "error" in result

    def test_read_skill_file_valid(self, tmp_path):
        from agent.tools.read_skill_tool import read_skill_file

        f = tmp_path / "skill.py"
        f.write_text(
            "async def start_game(): pass\nasync def action(): pass\nasync def ping(): pass\n"
        )
        result = json.loads(read_skill_file(str(f)))
        assert result["syntax_ok"] is True
        assert result["has_start_game"] is True
        assert result["has_action"] is True
        assert result["has_ping"] is True

    def test_read_skill_file_syntax_error(self, tmp_path):
        from agent.tools.read_skill_tool import read_skill_file

        f = tmp_path / "bad.py"
        f.write_text("def broken(\n")
        result = json.loads(read_skill_file(str(f)))
        assert result["syntax_ok"] is False
        assert result["syntax_error"] != ""


# ===========================================================================
# 15. agent/tools/strategy_tool.py
# ===========================================================================


class TestStrategyTool:
    def test_call_strategy_no_model(self):
        from agent.tools import strategy_tool as st

        st._rl_policies = {}
        # No model file exists → should raise RuntimeError
        with pytest.raises(RuntimeError, match="No trained RL model"):
            st.call_strategy({"role": "cop", "board_state": {}})

    def test_call_strategy_no_board_state(self):
        from agent.tools import strategy_tool as st

        st._rl_policies["cop"] = None
        with pytest.raises(RuntimeError):
            st.call_strategy({"role": "cop"})

    def test_load_rl_policy_caches_none(self):
        import pathlib
        from unittest.mock import patch

        from agent.tools import strategy_tool as st

        st._rl_policies = {}
        # Make no model path exist so the function caches None
        with patch.object(pathlib.Path, "exists", return_value=False):
            policy = st._load_rl_policy("cop")
        assert policy is None
        assert "cop" in st._rl_policies


# ===========================================================================
# 16. agent/agents/__init__.py and agent factories
# ===========================================================================


class TestAgentFactories:
    def _mock_llm(self):
        return MagicMock()

    def test_create_strategy_agent(self):
        from agent.agents.strategy_agent import create_strategy_agent

        agent = create_strategy_agent(self._mock_llm())
        assert agent is not None

    def test_create_select_move_task(self):
        from agent.agents.strategy_agent import create_select_move_task

        task = create_select_move_task(MagicMock())
        assert task is not None

    def test_create_game_manager_agent(self):
        from agent.agents.game_manager_agent import create_game_manager_agent

        agent = create_game_manager_agent(self._mock_llm())
        assert agent is not None

    def test_create_update_state_task(self):
        from agent.agents.game_manager_agent import create_update_state_task

        task = create_update_state_task(MagicMock())
        assert task is not None

    def test_create_verify_commitment_task(self):
        from agent.agents.game_manager_agent import create_verify_commitment_task

        task = create_verify_commitment_task(MagicMock())
        assert task is not None

    def test_create_protocol_discovery_agent(self):
        from agent.agents.protocol_discovery_agent import create_protocol_discovery_agent

        agent = create_protocol_discovery_agent(self._mock_llm())
        assert agent is not None

    def test_create_analyze_protocol_task(self):
        from agent.agents.protocol_discovery_agent import create_analyze_protocol_task

        task = create_analyze_protocol_task(MagicMock())
        assert task is not None

    def test_create_verify_protocol_task(self):
        from agent.agents.protocol_discovery_agent import create_verify_protocol_task

        task = create_verify_protocol_task(MagicMock())
        assert task is not None

    def test_create_mcp_explorer_agent(self):
        from agent.agents.mcp_explorer_agent import create_mcp_explorer_agent

        agent = create_mcp_explorer_agent(self._mock_llm())
        assert agent is not None

    def test_create_mcp_explorer_task(self):
        from agent.agents.mcp_explorer_agent import create_mcp_explorer_task

        task = create_mcp_explorer_task(MagicMock())
        assert task is not None

    def test_create_skill_validator_agent(self):
        from agent.agents.mcp_skill_validator import create_skill_validator_agent

        agent = create_skill_validator_agent(self._mock_llm())
        assert agent is not None

    def test_create_skill_validator_task(self):
        from agent.agents.mcp_skill_validator import create_skill_validator_task

        task = create_skill_validator_task(MagicMock())
        assert task is not None

    def test_agents_init_exports(self):
        from agent import agents

        assert hasattr(agents, "create_strategy_agent")
        assert hasattr(agents, "create_mcp_explorer_agent")
        assert hasattr(agents, "create_game_manager_agent")
        assert hasattr(agents, "create_protocol_discovery_agent")


# ===========================================================================
# 17. agent/reports/delivery_store.py
# ===========================================================================


class TestDeliveryStore:
    @pytest.mark.asyncio
    async def test_load_history_missing_file(self, tmp_path):
        from agent.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        history = store.load_history("g1")
        assert history == []

    @pytest.mark.asyncio
    async def test_record_and_load(self, tmp_path):
        from agent.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        await store.record_delivery("g1", {"plugin": "file", "status": "sent"})
        history = store.load_history("g1")
        assert len(history) == 1
        assert history[0]["plugin"] == "file"

    @pytest.mark.asyncio
    async def test_has_successful_delivery_true(self, tmp_path):
        from agent.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        await store.record_delivery("g1", {"plugin": "file", "status": "sent"})
        result = await store.has_successful_delivery("g1", "file")
        assert result is True

    @pytest.mark.asyncio
    async def test_has_successful_delivery_false(self, tmp_path):
        from agent.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        result = await store.has_successful_delivery("g1", "file")
        assert result is False

    def test_get_delivery_path(self, tmp_path):
        from agent.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        path = store.get_delivery_path("g1")
        assert path == tmp_path / "g1" / "report_delivery.json"

    @pytest.mark.asyncio
    async def test_load_history_bad_json(self, tmp_path):
        from agent.reports.delivery_store import DeliveryStore

        store = DeliveryStore(tmp_path)
        bad_path = tmp_path / "g1" / "report_delivery.json"
        bad_path.parent.mkdir(parents=True)
        bad_path.write_text("not json")
        history = store.load_history("g1")
        assert history == []


# ===========================================================================
# 18. agent/reports/example_plugin.py
# ===========================================================================


class TestExamplePlugin:
    @pytest.mark.asyncio
    async def test_generate_success(self, tmp_path):
        from agent.reports.example_plugin import ExampleCustomPlugin

        plugin = ExampleCustomPlugin()
        game_state = {
            "winner": "cop",
            "move_history": [{"cop": "NORTH", "thief": "SOUTH"}],
            "cop_position": [3, 3],
            "thief_position": [5, 5],
        }
        # Ensure the game_id subdirectory exists
        game_dir = tmp_path
        (game_dir / "test_game").mkdir()
        result = await plugin.generate("test_game", game_state, str(game_dir))
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_generate_failure(self, tmp_path):
        from agent.reports.example_plugin import ExampleCustomPlugin

        plugin = ExampleCustomPlugin()
        # Passing bad game_dir that can't create files
        result = await plugin.generate("g", {}, "/nonexistent_dir_xyz/abc")
        assert result["ok"] is False


# ===========================================================================
# 19. agent/reports/file_report.py
# ===========================================================================


class TestFileReportPlugin:
    def _make_context(self, game_dir: Path, fmt="json"):
        from agent.reports.base import ReportContext

        return ReportContext(
            game_id="testgame",
            role="cop",
            group_id="grp1",
            opponent_group_id="grp2",
            game_dir=game_dir,
            game_state={
                "cop_position": [1, 1],
                "thief_position": [4, 4],
                "move_history": [{"cop": "NORTH", "thief": "SOUTH"}],
            },
            result={"winner": "cop"},
            start_timestamp="2024-01-01T00:00:00",
            end_timestamp="2024-01-01T01:00:00",
            config_hash="abc123",
            log_hash="def456",
            required_files={},
            optional_files={},
        )

    @pytest.mark.asyncio
    async def test_generate_json(self, tmp_path):
        from agent.reports.file_report import FileReportPlugin

        plugin = FileReportPlugin("test_json", "json")
        ctx = self._make_context(tmp_path)
        result = await plugin.generate(ctx)
        assert result.ok is True
        assert (tmp_path / "report.json").exists()

    @pytest.mark.asyncio
    async def test_generate_markdown(self, tmp_path):
        from agent.reports.file_report import FileReportPlugin

        plugin = FileReportPlugin("test_md", "markdown")
        ctx = self._make_context(tmp_path)
        result = await plugin.generate(ctx)
        assert result.ok is True
        assert (tmp_path / "report.md").exists()

    @pytest.mark.asyncio
    async def test_generate_json_content(self, tmp_path):
        from agent.reports.file_report import FileReportPlugin

        plugin = FileReportPlugin("test_json", "json")
        ctx = self._make_context(tmp_path)
        await plugin.generate(ctx)
        with open(tmp_path / "report.json") as f:
            data = json.load(f)
        assert data["game_id"] == "testgame"
        assert data["winner"] == "cop"

    @pytest.mark.asyncio
    async def test_generate_markdown_content(self, tmp_path):
        from agent.reports.file_report import FileReportPlugin

        plugin = FileReportPlugin("test_md", "markdown")
        ctx = self._make_context(tmp_path)
        await plugin.generate(ctx)
        content = (tmp_path / "report.md").read_text()
        assert "testgame" in content
        assert "COP" in content

    @pytest.mark.asyncio
    async def test_generate_exception_returns_failed_result(self, tmp_path):
        from agent.reports.file_report import FileReportPlugin

        plugin = FileReportPlugin("test_json", "json")
        ctx = self._make_context(tmp_path)
        # Force an exception during file write
        with patch("builtins.open", side_effect=OSError("disk full")):
            result = await plugin.generate(ctx)
        assert result.ok is False
        assert result.status == "failed"


# ===========================================================================
# 20. agent/reports/gatekeeper.py
# ===========================================================================


class TestReportGatekeeper:
    @pytest.mark.asyncio
    async def test_can_send_dry_run(self):
        from agent.reports.gatekeeper import ReportGatekeeper

        gk = ReportGatekeeper()
        ok, reason = await gk.can_send("g1", "file", [], mode="dry_run")
        assert ok is True

    @pytest.mark.asyncio
    async def test_can_send_already_sent(self):
        from agent.reports.gatekeeper import ReportGatekeeper

        gk = ReportGatekeeper()
        history = [{"plugin": "file", "status": "sent", "game_id": "g1", "timestamp": "2024-01-01"}]
        ok, reason = await gk.can_send("g1", "file", history, mode="send")
        assert ok is False
        assert "Already sent" in reason

    @pytest.mark.asyncio
    async def test_can_send_daily_limit(self):
        from datetime import datetime

        from agent.reports.gatekeeper import ReportGatekeeper

        gk = ReportGatekeeper(max_sends_per_day=2)
        now = datetime.now()
        history = [
            {"plugin": "other", "status": "sent", "game_id": "g2", "timestamp": now.isoformat()},
            {"plugin": "other2", "status": "sent", "game_id": "g3", "timestamp": now.isoformat()},
        ]
        ok, reason = await gk.can_send("g1", "file", history, mode="send")
        assert ok is False
        assert "Daily limit" in reason

    @pytest.mark.asyncio
    async def test_can_send_max_retries(self):
        from agent.reports.gatekeeper import ReportGatekeeper

        gk = ReportGatekeeper(max_retries=2)
        history = [
            {"plugin": "file", "status": "failed", "game_id": "g1", "timestamp": "2024-01-01"},
            {"plugin": "file", "status": "failed", "game_id": "g1", "timestamp": "2024-01-01"},
        ]
        ok, reason = await gk.can_send("g1", "file", history, mode="send")
        assert ok is False
        assert "retries" in reason.lower()

    @pytest.mark.asyncio
    async def test_can_send_ok(self):
        from agent.reports.gatekeeper import ReportGatekeeper

        gk = ReportGatekeeper()
        ok, reason = await gk.can_send("g1", "file", [], mode="send")
        assert ok is True
        assert reason == "OK"

    def test_record_send(self):
        from agent.reports.gatekeeper import ReportGatekeeper

        gk = ReportGatekeeper()
        record = gk.record_send("g1", "file", "send", "sent", destination="/tmp/report.json")
        assert record["status"] == "sent"
        assert record["game_id"] == "g1"
        assert record["destination"] == "/tmp/report.json"
