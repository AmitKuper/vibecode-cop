"""Fast unit tests for the self-play CopThiefEnv.

Deterministic, tiny episodes — no LLM, no network, no training.
"""

from __future__ import annotations

from cop_worker.rl.config import RLGameConfig
from cop_worker.rl.environment import ACTIONS, COP_ACTIONS, CopThiefEnv

STAY = ACTIONS.index("STAY")


def test_reset_returns_role_observations():
    env = CopThiefEnv(RLGameConfig(cop_start=[0, 0], thief_start=[3, 3]))
    cop_obs, thief_obs = env.reset()
    assert len(cop_obs) == 4  # no barrier quota → 4 channels
    assert len(thief_obs) == 4
    assert len(cop_obs[0]) == 7 and len(cop_obs[0][0]) == 7


def test_cop_observation_has_five_channels_with_quota():
    env = CopThiefEnv(RLGameConfig(cop_start=[0, 0], thief_start=[3, 3], cop_barrier_quota=14))
    cop_obs, _ = env.reset()
    assert len(cop_obs) == 5
    assert env.n_cop_actions == len(COP_ACTIONS)


def test_step_stay_advances_turn_without_terminating():
    env = CopThiefEnv(RLGameConfig(cop_start=[0, 0], thief_start=[6, 6]))
    env.reset()
    _c, _t, cop_r, thief_r, done, info = env.step(STAY, STAY)
    assert not done
    assert info["turn"] == 1
    assert info["winner"] is None
    # non-terminal step: cop pays the step penalty, thief gains it
    assert cop_r < 0 < thief_r


def test_barrier_placement_on_thief_is_capture():
    env = CopThiefEnv(RLGameConfig(cop_start=[2, 3], thief_start=[3, 3], cop_barrier_quota=5))
    env.reset()
    place_e = COP_ACTIONS.index("PLACE_E")  # barrier lands on thief cell (3,3)
    _c, _t, cop_r, thief_r, done, info = env.step(place_e, STAY)
    assert done and info["winner"] == "cop"
    assert cop_r > 0 > thief_r


def test_shaped_rewards_config_path_runs():
    env = CopThiefEnv(
        RLGameConfig(cop_start=[0, 0], thief_start=[6, 6], use_shaped_rewards=True)
    )
    env.reset()
    _c, _t, cop_r, thief_r, done, _info = env.step(STAY, STAY)
    assert isinstance(cop_r, float) and isinstance(thief_r, float) and not done


def test_random_starts_are_within_bounds_and_distinct():
    env = CopThiefEnv(RLGameConfig(random_starts=True))
    env.reset()
    assert env._board.cop_position != env._board.thief_position
    for coord in env._board.cop_position + env._board.thief_position:
        assert 0 <= coord < 7


def test_metadata_helpers():
    env = CopThiefEnv(RLGameConfig())
    assert env.n_actions == 5
    assert env.action_meanings() == list(ACTIONS)
    assert env.observation_shape("thief") == (4, 7, 7)
    assert env.observation_shape("cop")[1:] == (7, 7)
