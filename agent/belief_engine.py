"""Bayesian belief engine for opponent position estimation."""

from __future__ import annotations

import numpy as np

from agent.observation import BeliefState


class BeliefEngine:
    """Updates belief distribution given observations."""

    def __init__(self, grid_size: int, role: str):
        self.grid_size = grid_size
        self.role = role  # "cop" or "thief"
        self._belief = BeliefState.uniform(grid_size)

    def predict(self, known_barriers: list[tuple[int, int]]) -> BeliefEngine:
        """Propagate belief through all legal opponent transitions."""
        n = self.grid_size
        moves = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]  # STAY,N,S,W,E

        new_prob = np.zeros((n, n))
        old_prob = self._belief.prob

        # Set of passable cells
        barrier_set = set(map(tuple, known_barriers))

        for r in range(n):
            for c in range(n):
                if (r, c) in barrier_set or old_prob[r][c] < 1e-10:
                    continue
                # Distribute probability to all reachable neighbors
                reachable = []
                for dr, dc in moves:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < n and 0 <= nc < n and (nr, nc) not in barrier_set:
                        reachable.append((nr, nc))
                if reachable:
                    share = old_prob[r][c] / len(reachable)
                    for nr, nc in reachable:
                        new_prob[nr][nc] += share

        new_belief = BeliefState(
            self.grid_size,
            new_prob,
            self._belief.entropy,
            self._belief.confidence,
            self._belief.step,
        )
        engine = BeliefEngine(self.grid_size, self.role)
        engine._belief = new_belief.normalize().mask_barriers(known_barriers)
        return engine

    def observe_scent(
        self,
        scent_field: list[list[float]],
        known_barriers: list[tuple[int, int]],
    ) -> BeliefEngine:
        """Fuse scent observation into belief via likelihood."""
        scent = np.array(scent_field)
        likelihood = scent + 0.01  # avoid zero
        new_prob = self._belief.prob * likelihood
        new_belief = (
            BeliefState(self.grid_size, new_prob, 0.0, 0.0, self._belief.step)
            .normalize()
            .mask_barriers(known_barriers)
        )
        engine = BeliefEngine(self.grid_size, self.role)
        engine._belief = new_belief
        return engine

    def step_complete(self, step: int) -> BeliefEngine:
        new_belief = BeliefState(
            self.grid_size,
            self._belief.prob.copy(),
            self._belief.entropy,
            self._belief.confidence,
            step,
        )
        engine = BeliefEngine(self.grid_size, self.role)
        engine._belief = new_belief
        return engine

    @property
    def belief(self) -> BeliefState:
        return self._belief
