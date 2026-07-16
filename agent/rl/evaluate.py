"""Evaluation utilities for trained cop/thief agents.

Supports mixing algorithm types: e.g., DQN cop vs PPO thief.
All agents must implement select_action(obs, training=False) -> int.

Re-exports ``compare`` from eval_compare for backward compatibility.
"""

from __future__ import annotations

import logging

from agent.rl.config import RLGameConfig
from agent.rl.environment import CopThiefEnv

logger = logging.getLogger(__name__)


def evaluate(
    cop_agent,
    thief_agent,
    config: RLGameConfig | None = None,
    n_games: int = 200,
) -> dict:
    """Play n_games with both agents in greedy (non-training) mode.

    Args:
        cop_agent:   Any agent with select_action(obs, training=False) -> int.
        thief_agent: Same interface.
        config:      Game config; defaults to RLGameConfig() if None.
        n_games:     Number of evaluation episodes.

    Returns:
        Dict with win rates, avg game length, and per-episode lists.
    """
    env = CopThiefEnv(config or RLGameConfig())
    cop_wins = 0
    thief_wins = 0
    lengths = []
    cop_rewards = []
    thief_rewards = []

    for _ in range(n_games):
        cop_obs, thief_obs = env.reset()
        done = False
        ep_cop_r = 0.0
        ep_thief_r = 0.0
        info: dict = {}

        while not done:
            cop_act = _get_action(cop_agent, cop_obs)
            thief_act = _get_action(thief_agent, thief_obs)
            cop_obs, thief_obs, cop_r, thief_r, done, info = env.step(cop_act, thief_act)
            ep_cop_r += cop_r
            ep_thief_r += thief_r

        if info.get("winner") == "cop":
            cop_wins += 1
        else:
            thief_wins += 1
        lengths.append(info.get("turn", 0))
        cop_rewards.append(ep_cop_r)
        thief_rewards.append(ep_thief_r)

    return {
        "n_games": n_games,
        "cop_wins": cop_wins,
        "thief_wins": thief_wins,
        "cop_win_rate": cop_wins / n_games,
        "thief_win_rate": thief_wins / n_games,
        "avg_game_length": sum(lengths) / n_games,
        "avg_cop_reward": sum(cop_rewards) / n_games,
        "avg_thief_reward": sum(thief_rewards) / n_games,
        "game_lengths": lengths,
    }


def print_results(label: str, results: dict) -> None:
    print(
        f"\n{'='*50}\n"
        f"  {label}\n"
        f"{'='*50}\n"
        f"  Games:           {results['n_games']}\n"
        f"  Cop  win rate:   {results['cop_win_rate']:.1%}  ({results['cop_wins']} wins)\n"
        f"  Thief win rate:  {results['thief_win_rate']:.1%}  ({results['thief_wins']} wins)\n"
        f"  Avg game length: {results['avg_game_length']:.1f} steps\n"
        f"  Avg cop reward:  {results['avg_cop_reward']:.3f}\n"
        f"  Avg thief reward:{results['avg_thief_reward']:.3f}\n"
    )


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _get_action(agent, obs: list) -> int:
    """Unified action selection for DQN and PPO agents.

    DQN: greedy (argmax Q) — deterministic, correct for evaluation.
    PPO: stochastic (sample from policy) — PPO learns a distribution;
         forcing argmax can collapse to a degenerate fixed action.
    """
    is_ppo = hasattr(agent, "_rollout")  # PPOAgent has _rollout, DQNAgent does not
    result = agent.select_action(obs, training=is_ppo)
    return result[0] if isinstance(result, tuple) else result


# Re-export for backward compatibility
from agent.rl.eval_compare import compare  # noqa: E402, F401
