"""Artifact writing and summary metrics for the DDQN trainer."""

from __future__ import annotations

from pathlib import Path

import torch

from cop_worker.rl.research_value_training.networks import DuelingDoubleQNetwork


def _finalize_ddqn(
    online: DuelingDoubleQNetwork,
    role: str,
    episodes: int,
    seed: int,
    hidden_size: int,
    input_size: int,
    n_actions: int,
    fixed_start_probability: float,
    population_names: list[str],
    environment_steps: int,
    wins: list[int],
    lengths: list[int],
    losses: list[float],
    output: Path,
) -> dict:
    """Persist the trained artifact and return the training summary metrics."""
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "role": role,
            "algorithm": "DuelingDoubleDQN",
            "input_size": input_size,
            "n_actions": n_actions,
            "hidden_size": hidden_size,
            "training_episodes": episodes,
            "environment_steps": environment_steps,
            "seed": seed,
            "fixed_start_probability": fixed_start_probability,
            "opponent_population": list(population_names),
            "state_dict": online.state_dict(),
        },
        output,
    )
    metrics = {
        "algorithm": "DuelingDoubleDQN",
        "role": role,
        "episodes": episodes,
        "environment_steps": environment_steps,
        "training_win_rate_last_500": sum(wins[-500:]) / max(len(wins[-500:]), 1),
        "average_length_last_500": sum(lengths[-500:]) / max(len(lengths[-500:]), 1),
        "mean_loss_last_1000": sum(losses[-1000:]) / max(len(losses[-1000:]), 1),
        "opponent_population": list(population_names),
    }
    return metrics
