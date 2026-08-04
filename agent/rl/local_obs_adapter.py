"""Converts LocalObservation+BeliefState to RL input tensor WITHOUT hidden coords."""

from __future__ import annotations

import numpy as np

from agent.observation import BeliefState, LocalObservation


def local_obs_to_tensor(obs: LocalObservation, belief: BeliefState) -> np.ndarray:
    """
    Build flat feature vector from local-only information.
    No opponent_position field (LocalObservation doesn't have one by design).
    """
    n = obs.grid_size
    # Own position one-hot (n*n)
    own_oh = np.zeros(n * n)
    x, y = obs.own_position
    own_oh[y * n + x] = 1.0
    # Barrier grid (n*n)
    barrier_grid = np.zeros(n * n)
    for bx, by in obs.known_barriers:
        if 0 <= bx < n and 0 <= by < n:
            barrier_grid[by * n + bx] = 1.0
    # Opponent scent (n*n) flattened
    scent_flat = np.array(obs.opponent_scent).flatten()[: n * n]
    # Belief heatmap (n*n) flattened
    belief_flat = belief.prob.flatten()
    # Scalar features
    scalars = np.array(
        [
            obs.own_barriers_remaining / max(obs.grid_size, 1),
            obs.step / 100.0,
            obs.gamelet / 6.0,
            belief.entropy / max(np.log(n * n), 1.0),
            belief.confidence,
        ]
    )
    return np.concatenate([own_oh, barrier_grid, scent_flat, belief_flat, scalars])


def obs_tensor_shape(grid_size: int) -> int:
    """Return the total length of the flat feature vector."""
    n = grid_size
    return 4 * n * n + 5  # own_oh, barrier, scent, belief, scalars
