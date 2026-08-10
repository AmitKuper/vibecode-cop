"""Converts LocalObservation+BeliefState to RL input tensor WITHOUT hidden coords."""

from __future__ import annotations

import numpy as np

from cop_worker.observation import BeliefState, LocalObservation
from cop_worker.rl.obs_mode import decoded_scent_enabled


def local_obs_to_tensor(obs: LocalObservation, belief: BeliefState, decoder=None) -> np.ndarray:
    """
    Build flat feature vector from local-only information.
    No opponent_position field (LocalObservation doesn't have one by design).

    When ``decoder`` is an :class:`~cop_worker.scent_decoder.EmitterDecoder` and
    ``COPTHIEF_DECODED_SCENT=1``, the raw opponent-scent channel is replaced by the posterior
    obtained by *inverting* the clamped wire law, and the belief channel is replaced by that
    same posterior. The clamped field saturates to a flat 0.9 blanket over ~40/49 cells, so
    the raw channel is uninformative on ~95% of steps, while the inverse pins the emitter to
    a single cell essentially always. The tensor LAYOUT is unchanged, so checkpoints trained
    either way stay mutually loadable.

    The decoder is stateful (it needs the previous frame), so the caller owns one per episode
    and resets it between games.
    """
    n = obs.grid_size
    if decoder is not None and decoded_scent_enabled():
        posterior = decoder.decode(obs.opponent_scent)
        scent_source: np.ndarray = posterior
        belief = BeliefState(grid_size=n, prob=posterior, step=obs.step).normalize()
    else:
        scent_source = np.array(obs.opponent_scent, dtype=float)
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
    scent_flat = scent_source.flatten()[: n * n]
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
