"""Multi-algorithm comparison helper for RL evaluation.

Extracted from evaluate.py to keep each file under 150 lines.
"""

from __future__ import annotations

import logging

from agent.rl.config import RLGameConfig
from agent.rl.evaluate import evaluate, print_results

logger = logging.getLogger(__name__)


def compare(
    dqn_cop,
    dqn_thief,
    ppo_cop,
    ppo_thief,
    config: RLGameConfig | None = None,
    n_games: int = 200,
) -> dict:
    """Run four matchups and summarise which algorithm/role performs best.

    Matchups:
      1. DQN cop  vs DQN thief   (symmetric baseline)
      2. PPO cop  vs PPO thief   (symmetric baseline)
      3. DQN cop  vs PPO thief   (cross-algo)
      4. PPO cop  vs DQN thief   (cross-algo)
    """
    results = {}
    matchups = [
        ("DQN cop vs DQN thief", dqn_cop, dqn_thief),
        ("PPO cop vs PPO thief", ppo_cop, ppo_thief),
        ("DQN cop vs PPO thief", dqn_cop, ppo_thief),
        ("PPO cop vs DQN thief", ppo_cop, dqn_thief),
    ]
    for label, cop, thief in matchups:
        logger.info(f"Evaluating: {label} ...")
        r = evaluate(cop, thief, config, n_games)
        results[label] = r
        print_results(label, r)

    cop_rates = {
        "DQN": (
            results["DQN cop vs DQN thief"]["cop_win_rate"]
            + results["DQN cop vs PPO thief"]["cop_win_rate"]
        )
        / 2,
        "PPO": (
            results["PPO cop vs PPO thief"]["cop_win_rate"]
            + results["PPO cop vs DQN thief"]["cop_win_rate"]
        )
        / 2,
    }
    thief_rates = {
        "DQN": (
            results["DQN cop vs DQN thief"]["thief_win_rate"]
            + results["PPO cop vs DQN thief"]["thief_win_rate"]
        )
        / 2,
        "PPO": (
            results["PPO cop vs PPO thief"]["thief_win_rate"]
            + results["DQN cop vs PPO thief"]["thief_win_rate"]
        )
        / 2,
    }
    best_cop = max(cop_rates, key=cop_rates.get)
    best_thief = max(thief_rates, key=thief_rates.get)

    print(
        f"\n{'=' * 50}\n"
        f"  COMPARISON SUMMARY\n"
        f"{'=' * 50}\n"
        f"  Best cop   algorithm: {best_cop} (avg win rate {cop_rates[best_cop]:.1%})\n"
        f"  Best thief algorithm: {best_thief} (avg win rate {thief_rates[best_thief]:.1%})\n"
        f"{'=' * 50}\n"
    )
    results["_summary"] = {
        "best_cop_algo": best_cop,
        "best_thief_algo": best_thief,
        "cop_rates": cop_rates,
        "thief_rates": thief_rates,
    }
    return results
